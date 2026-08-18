"""Загрузчик файла метаданных станций PeMS.

Файл вида ``d07_text_meta_2025_03_14.txt`` — табуляция, **со строкой
заголовка**. Именно отсюда берутся координаты и положение станции вдоль
трассы; без него 5-минутные замеры — просто числа без места на карте.

Ключевое поле — ``abs_pm`` (absolute postmile): непрерывная координата
вдоль автомагистрали. По ней станции выстраиваются в порядок движения и
считаются расстояния между соседями. Широта и долгота для этого не
годятся: дорога не прямая, и расстояние по прямой короче реального.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Имена в заголовке у разных выгрузок слегка отличаются регистром и
# подчёркиваниями, поэтому приводим к своему единому виду.
_RENAME = {
    "id": "station",
    "fwy": "freeway",
    "dir": "direction",
    "district": "district",
    "county": "county",
    "city": "city",
    "state_pm": "state_pm",
    "abs_pm": "abs_pm",
    "latitude": "latitude",
    "longitude": "longitude",
    "length": "length",
    "type": "lane_type",
    "lanes": "lanes",
    "name": "name",
}


def load_station_meta(path: str | Path) -> pd.DataFrame:
    """Прочитать метаданные станций.

    Returns
    -------
    pandas.DataFrame
        Со столбцами ``station``, ``freeway``, ``direction``, ``abs_pm``,
        ``latitude``, ``longitude``, ``lanes``, ``lane_type`` и прочими,
        какие нашлись в файле.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    df = pd.read_csv(path, sep="\t", dtype={"Type": "string", "Dir": "string"})
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df = df.rename(columns={k: v for k, v in _RENAME.items() if k in df.columns})

    for col in ("station", "freeway", "abs_pm", "latitude", "longitude", "lanes", "length"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def corridor_stations(
    meta: pd.DataFrame,
    *,
    freeway: int,
    direction: str,
    postmile_from: float,
    postmile_to: float,
    mainline_only: bool = True,
) -> pd.DataFrame:
    """Выбрать станции коридора и выстроить их по ходу движения.

    ``mainline_only`` отсекает въезды, съезды и выделенные полосы: для
    времени проезда по коридору нужен только основной ход (``ML``).
    """
    sel = meta[(meta["freeway"] == freeway) & (meta["direction"] == direction)]
    if mainline_only and "lane_type" in sel.columns:
        sel = sel[sel["lane_type"] == "ML"]

    lo, hi = sorted((postmile_from, postmile_to))
    sel = sel[(sel["abs_pm"] >= lo) & (sel["abs_pm"] <= hi)]

    # Порядок движения: для южного и западного направления постмили убывают.
    ascending = direction in ("N", "E")
    return sel.sort_values("abs_pm", ascending=ascending).reset_index(drop=True)
