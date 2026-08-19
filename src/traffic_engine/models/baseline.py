"""Baseline: справочник эмпирических квантилей.

Никакого обучения. Берём историю, группируем поездки по типу дня и часу
и внутри каждой группы считаем нужный квантиль напрямую. Планка, которую
обязана перебить любая модель.

Почему разбиение именно такое
-----------------------------
В исходном плане было (день недели × 5-минутный слот). На месяце данных
это даёт **четыре наблюдения на ячейку** — P90 по четырём числам есть
шум, и перебить такой baseline смогла бы любая ошибка в коде. Слабый
baseline не облегчает работу, а лишает результат смысла.

Замеренная плотность на январе 2026:

============================  ======  ========================
Разбиение                     Ячеек   Наблюдений на ячейку
============================  ======  ========================
день недели × 5-мин слот        2016   4
будни/выходные × 5-мин слот      576   15
день недели × час                168   48
будни/выходные × час              48   186
============================  ======  ========================

Выбрано последнее. Для устойчивой оценки P90 нужно порядка пятидесяти
наблюдений, для P95 — порядка ста; 186 даёт запас. Разбиение по
5-минутным слотам вернётся, когда наберётся год данных.

Отдельно про праздники. 1 января утреннего пика не было вовсе — ровные
девять минут весь день. Поэтому праздник считается «выходным» вне
зависимости от дня недели: иначе он затащит своё спокойствие в
буднюю группу и занизит её квантили.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Федеральные праздники США, попадающие в имеющийся период.
# Список расширяется по мере добавления месяцев; держать его здесь, а не
# тянуть внешнюю библиотеку, — сознательный выбор: так видно, что учтено.
US_HOLIDAYS_2026 = {
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # Martin Luther King Jr. Day
    "2026-02-16",  # Washington's Birthday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-10-12",  # Columbus Day
    "2026-11-11",  # Veterans Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
}


def is_off_day(index: pd.DatetimeIndex, holidays: set[str] | None = None) -> np.ndarray:
    """Выходной или праздник — в противоположность рабочему дню."""
    holidays = US_HOLIDAYS_2026 if holidays is None else holidays
    hol = {pd.Timestamp(h).date() for h in holidays}
    weekend = index.dayofweek >= 5
    holiday = np.array([ts.date() in hol for ts in index])
    return weekend | holiday


def group_keys(index: pd.DatetimeIndex, holidays: set[str] | None = None) -> pd.MultiIndex:
    """Ключ группы: (нерабочий день, час суток)."""
    return pd.MultiIndex.from_arrays(
        [is_off_day(index, holidays), index.hour],
        names=["off_day", "hour"],
    )


@dataclass
class QuantileLookupBaseline:
    """Справочник квантилей по (тип дня × час).

    Parameters
    ----------
    taus
        Уровни квантилей, которые нужно уметь выдавать.
    min_samples
        Минимальное число наблюдений в ячейке. Если меньше — ячейка
        считается ненадёжной и подменяется общим квантилем по своему
        типу дня. Молча выдавать оценку по трём точкам хуже, чем
        честно откатиться на более грубую группировку.
    """

    taus: tuple[float, ...] = (0.5, 0.9, 0.95)
    min_samples: int = 30
    holidays: set[str] | None = None

    table_: pd.DataFrame | None = field(default=None, init=False)
    fallback_: pd.DataFrame | None = field(default=None, init=False)
    thin_cells_: list[tuple[bool, int]] = field(default_factory=list, init=False)

    def fit(self, y: pd.Series) -> QuantileLookupBaseline:
        y = y.dropna()
        if not isinstance(y.index, pd.DatetimeIndex):
            raise TypeError("индекс должен быть DatetimeIndex")

        keys = group_keys(y.index, self.holidays)
        grouped = y.groupby(keys)

        self.table_ = pd.DataFrame({tau: grouped.quantile(tau) for tau in self.taus})
        counts = grouped.size()
        self.thin_cells_ = [tuple(k) for k in counts[counts < self.min_samples].index]

        # запас на случай тонкой ячейки — квантиль по всему типу дня
        by_daytype = y.groupby(keys.get_level_values("off_day"))
        self.fallback_ = pd.DataFrame({tau: by_daytype.quantile(tau) for tau in self.taus})
        return self

    def predict(self, index: pd.DatetimeIndex) -> dict[float, np.ndarray]:
        """Предсказать все квантили для заданных моментов отправления."""
        if self.table_ is None or self.fallback_ is None:
            raise RuntimeError("сначала fit")

        keys = group_keys(index, self.holidays)
        off = keys.get_level_values("off_day")
        out: dict[float, np.ndarray] = {}

        for tau in self.taus:
            values = self.table_[tau].reindex(keys).to_numpy(dtype=float)
            # тонкие и вовсе отсутствующие ячейки — на грубую оценку
            thin = np.array([tuple(k) in set(self.thin_cells_) for k in keys])
            need = np.isnan(values) | thin
            if need.any():
                values = values.copy()
                values[need] = self.fallback_[tau].reindex(off[need]).to_numpy(dtype=float)
            out[tau] = values
        return out

    def cell_counts(self, y: pd.Series) -> pd.Series:
        """Сколько наблюдений пришлось на каждую ячейку — для отчёта."""
        return y.dropna().groupby(group_keys(y.dropna().index, self.holidays)).size()
