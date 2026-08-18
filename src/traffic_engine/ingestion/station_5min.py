"""Загрузчик файлов PeMS «Station 5-Minute».

Формат выгрузки (Data Clearinghouse на pems.dot.ca.gov):

* один файл на сутки, имя вида ``d07_text_station_5min_2025_03_14.txt.gz``;
* CSV с запятой, **без строки заголовка** — имена колонок приходится
  восстанавливать по позиции;
* первые 12 колонок описывают станцию целиком;
* дальше идут блоки по 5 колонок на каждую полосу движения, и число
  полос у разных станций разное. Именно поэтому число колонок в файле
  заранее неизвестно и определяется по факту.

Порядок колонок:

===  ========================  ====================================================
  #  Колонка                   Смысл
===  ========================  ====================================================
  1  timestamp                 местное калифорнийское время, MM/DD/YYYY HH:MM:SS
  2  station                   идентификатор станции (сходится с метаданными)
  3  district                  округ Caltrans; Лос-Анджелес — 7
  4  freeway                   номер автомагистрали, например 405
  5  direction                 N / S / E / W
  6  lane_type                 ML основной ход, HV выделенная, OR въезд, FR съезд …
  7  station_length            длина участка, закреплённого за станцией, мили
  8  samples                   сколько замеров пришло за 5 минут
  9  pct_observed              доля НЕвосстановленных значений, 0–100
 10  total_flow                машин за 5 минут по всем полосам
 11  avg_occupancy             занятость, доля времени 0–1
 12  avg_speed                 средняя скорость, миль/час
===  ========================  ====================================================

Дальше для каждой полосы N: ``lane{N}_samples``, ``lane{N}_flow``,
``lane{N}_avg_occ``, ``lane{N}_avg_speed``, ``lane{N}_observed``.

Два поля решают, можно ли верить строке: ``pct_observed`` и ``samples``.
PeMS достраивает пропуски сам, и без ``pct_observed`` восстановленное
значение внешне неотличимо от измеренного.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

STATION_5MIN_BASE_COLUMNS: list[str] = [
    "timestamp",
    "station",
    "district",
    "freeway",
    "direction",
    "lane_type",
    "station_length",
    "samples",
    "pct_observed",
    "total_flow",
    "avg_occupancy",
    "avg_speed",
]

LANE_COLUMN_SUFFIXES: list[str] = [
    "samples",
    "flow",
    "avg_occ",
    "avg_speed",
    "observed",
]

_N_BASE = len(STATION_5MIN_BASE_COLUMNS)
_N_PER_LANE = len(LANE_COLUMN_SUFFIXES)

_TIMESTAMP_FORMAT = "%m/%d/%Y %H:%M:%S"

_NUMERIC_BASE_COLUMNS = [
    "station",
    "district",
    "freeway",
    "station_length",
    "samples",
    "pct_observed",
    "total_flow",
    "avg_occupancy",
    "avg_speed",
]


class PemsFormatError(ValueError):
    """Файл не похож на выгрузку Station 5-Minute."""


def infer_lane_count(n_columns: int) -> int:
    """Сколько полос описано в файле с ``n_columns`` колонками.

    Проверка тут не косметическая: если число колонок не укладывается в
    ``12 + 5·N``, значит это не тот тип выгрузки, и лучше упасть сразу,
    чем молча разъехаться на одну колонку и получить скорость в поле
    занятости.
    """
    if n_columns < _N_BASE:
        raise PemsFormatError(
            f"в файле {n_columns} колонок, а базовых полей одних только {_N_BASE}"
        )
    extra = n_columns - _N_BASE
    if extra % _N_PER_LANE != 0:
        raise PemsFormatError(
            f"{n_columns} колонок = {_N_BASE} базовых + {extra} лишних, "
            f"а {extra} не делится на {_N_PER_LANE} полей на полосу"
        )
    return extra // _N_PER_LANE


def build_column_names(n_columns: int) -> list[str]:
    """Восстановить имена колонок по их количеству."""
    n_lanes = infer_lane_count(n_columns)
    names = list(STATION_5MIN_BASE_COLUMNS)
    for lane in range(1, n_lanes + 1):
        names.extend(f"lane{lane}_{suffix}" for suffix in LANE_COLUMN_SUFFIXES)
    return names


def _peek_column_count(path: Path) -> int:
    """Прочитать одну строку и посчитать поля."""
    head = pd.read_csv(path, header=None, nrows=1)
    return head.shape[1]


def load_station_5min(
    path: str | Path,
    *,
    keep_lanes: bool = False,
    localize: bool = True,
) -> pd.DataFrame:
    """Прочитать один файл Station 5-Minute.

    Parameters
    ----------
    path
        Путь к ``.txt.gz`` или ``.txt``. Сжатие определяется по расширению.
    keep_lanes
        Оставить ли колонки по отдельным полосам. По умолчанию нет: они
        занимают львиную долю объёма, а первой версии не нужны.
    localize
        Пометить ли время как ``America/Los_Angeles``. См. README про то,
        почему это отдельное решение, а не само собой разумеющееся.

    Returns
    -------
    pandas.DataFrame
        Колонки как в описании модуля, ``timestamp`` уже разобран.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    names = build_column_names(_peek_column_count(path))
    usecols: Iterable[str] | None = None if keep_lanes else STATION_5MIN_BASE_COLUMNS

    df = pd.read_csv(
        path,
        header=None,
        names=names,
        usecols=usecols,
        dtype={"lane_type": "string", "direction": "string"},
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"], format=_TIMESTAMP_FORMAT)
    if localize:
        # ambiguous / nonexistent: осенью один час повторяется, весной один
        # пропадает. PeMS зону не пишет, поэтому решаем это явно, а не молча.
        df["timestamp"] = df["timestamp"].dt.tz_localize(
            "America/Los_Angeles",
            ambiguous="NaT",
            nonexistent="NaT",
        )

    for col in _NUMERIC_BASE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def load_station_5min_dir(
    directory: str | Path,
    *,
    pattern: str = "*station_5min*.txt.gz",
    **kwargs,
) -> pd.DataFrame:
    """Прочитать все суточные файлы из каталога и склеить."""
    directory = Path(directory)
    files = sorted(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"в {directory} нет файлов по шаблону {pattern}")
    frames = [load_station_5min(f, **kwargs) for f in files]
    return pd.concat(frames, ignore_index=True)
