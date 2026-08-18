"""Первичный отчёт о качестве выгрузки Station 5-Minute.

Задача этого модуля — не чинить данные, а **честно показать, что в них
не так**, до того как что-либо будет обучено. Выводы:

* сколько строк восстановлено самим PeMS, а не измерено;
* где скорость отсутствует при ненулевом потоке (типичная поломка петли);
* сколько 5-минутных интервалов вообще пропущено;
* какие станции стоит выбросить целиком.

Отдельно про восстановленные значения. PeMS не оставляет пропусков: если
детектор молчит, система подставляет оценку. Внешне такая строка не
отличается от измеренной, и единственный признак — ``pct_observed``.
Обучаться на восстановленных данных значит учить модель повторять чужой
алгоритм заполнения, а не наблюдать дорогу.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# Ниже этого порога наблюдаемости строка считается в основном достроенной.
OBSERVED_THRESHOLD = 50.0

# Физически осмысленный диапазон скорости на автомагистрали, миль/час.
SPEED_MIN = 1.0
SPEED_MAX = 100.0


@dataclass
class QualityReport:
    """Результат первичной проверки."""

    n_rows: int
    n_stations: int
    time_from: pd.Timestamp | None
    time_to: pd.Timestamp | None
    expected_intervals: int
    observed_intervals: int
    findings: dict[str, Any] = field(default_factory=dict)
    per_station: pd.DataFrame | None = None

    @property
    def interval_coverage(self) -> float:
        """Доля реально присутствующих 5-минутных интервалов."""
        if not self.expected_intervals:
            return 0.0
        return self.observed_intervals / self.expected_intervals

    def to_text(self) -> str:
        lines = [
            "ОТЧЁТ О КАЧЕСТВЕ — PeMS Station 5-Minute",
            "=" * 60,
            f"строк:                 {self.n_rows:,}",
            f"станций:               {self.n_stations:,}",
            f"период:                {self.time_from}  →  {self.time_to}",
            f"5-минутных интервалов: {self.observed_intervals:,} из "
            f"{self.expected_intervals:,} ({100 * self.interval_coverage:.1f}%)",
            "",
            "НАХОДКИ",
            "-" * 60,
        ]
        for key, value in self.findings.items():
            if isinstance(value, float):
                lines.append(f"{key:<44} {value:>12.2f}")
            else:
                lines.append(f"{key:<44} {value:>12,}")
        return "\n".join(lines)


def profile_station_5min(df: pd.DataFrame, *, per_station: bool = True) -> QualityReport:
    """Построить отчёт по датафрейму, загруженному ``load_station_5min``."""
    n_rows = len(df)
    stations = df["station"].nunique()

    ts = df["timestamp"].dropna()
    t_from = ts.min() if len(ts) else None
    t_to = ts.max() if len(ts) else None

    if t_from is not None and t_to is not None and stations:
        slots = int((t_to - t_from).total_seconds() // 300) + 1
        expected = slots * stations
    else:
        expected = 0
    observed = n_rows

    speed = df["avg_speed"]
    flow = df["total_flow"]
    occ = df["avg_occupancy"]
    pct = df["pct_observed"]

    findings: dict[str, Any] = {
        "строк с пропущенной скоростью": int(speed.isna().sum()),
        "  из них при ненулевом потоке": int((speed.isna() & (flow > 0)).sum()),
        "строк с пропущенным потоком": int(flow.isna().sum()),
        "строк с нулевым потоком": int((flow == 0).sum()),
        "скорость вне диапазона 1..100": int(((speed < SPEED_MIN) | (speed > SPEED_MAX)).sum()),
        "занятость вне диапазона 0..1": int(((occ < 0) | (occ > 1)).sum()),
        f"наблюдаемость ниже {OBSERVED_THRESHOLD:.0f}%": int((pct < OBSERVED_THRESHOLD).sum()),
        "полностью достроенных строк (0%)": int((pct == 0).sum()),
        "средняя наблюдаемость, %": float(pct.mean()),
        "медиана скорости, миль/ч": float(speed.median()),
        "дубликатов (станция+время)": int(df.duplicated(["station", "timestamp"]).sum()),
        "меток времени NaT (переход на летнее)": int(df["timestamp"].isna().sum()),
    }

    per_station_df = None
    if per_station:
        per_station_df = (
            df.groupby("station")
            .agg(
                rows=("timestamp", "size"),
                mean_observed=("pct_observed", "mean"),
                speed_nulls=("avg_speed", lambda s: int(s.isna().sum())),
                median_speed=("avg_speed", "median"),
                median_flow=("total_flow", "median"),
            )
            .sort_values("mean_observed")
        )

    return QualityReport(
        n_rows=n_rows,
        n_stations=stations,
        time_from=t_from,
        time_to=t_to,
        expected_intervals=expected,
        observed_intervals=observed,
        findings=findings,
        per_station=per_station_df,
    )


def unusable_stations(
    report: QualityReport,
    *,
    min_observed: float = OBSERVED_THRESHOLD,
) -> list[int]:
    """Станции, которые лучше выбросить целиком.

    Одна станция с вечно достроенными значениями портит весь коридор:
    время проезда считается по цепочке, и слабое звено протаскивает
    ошибку во все поездки, проходящие через него.
    """
    if report.per_station is None:
        return []
    bad = report.per_station[report.per_station["mean_observed"] < min_observed]
    return [int(s) for s in bad.index]
