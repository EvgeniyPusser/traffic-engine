"""Тесты загрузчика Station 5-Minute.

Данные тут синтетические и намеренно кривые — они проверяют разбор
формата, а не описывают дорогу. Настоящие выводы делаются только на
реальной выгрузке.
"""

from __future__ import annotations

import gzip

import pandas as pd
import pytest

from traffic_engine.ingestion.station_5min import (
    PemsFormatError,
    build_column_names,
    infer_lane_count,
    load_station_5min,
)


def test_lane_count_from_column_number():
    assert infer_lane_count(12) == 0
    assert infer_lane_count(12 + 5) == 1
    assert infer_lane_count(12 + 5 * 8) == 8


def test_bad_column_number_raises():
    # 14 колонок = 12 базовых + 2 лишних, а на полосу нужно 5
    with pytest.raises(PemsFormatError):
        infer_lane_count(14)
    with pytest.raises(PemsFormatError):
        infer_lane_count(5)


def test_column_names_are_built_in_order():
    names = build_column_names(12 + 5 * 2)
    assert names[:3] == ["timestamp", "station", "district"]
    assert names[12:17] == [
        "lane1_samples",
        "lane1_flow",
        "lane1_avg_occ",
        "lane1_avg_speed",
        "lane1_observed",
    ]
    assert names[-1] == "lane2_observed"


def _write_sample(path, rows):
    with gzip.open(path, "wt") as fh:
        fh.write("\n".join(rows) + "\n")


def test_load_parses_timestamp_and_types(tmp_path):
    p = tmp_path / "d07_text_station_5min_2025_03_14.txt.gz"
    _write_sample(
        p,
        [
            "03/14/2025 08:00:00,716933,7,405,S,ML,0.5,20,100,180,0.0421,64.3,"
            "10,90,0.04,65.0,100,10,90,0.044,63.6,100",
            "03/14/2025 08:05:00,716933,7,405,S,ML,0.5,20,50,150,0.0510,58.1,"
            "10,75,0.05,59.0,50,10,75,0.052,57.2,50",
        ],
    )

    df = load_station_5min(p)

    assert list(df.columns)[:12] == [
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
    assert len(df) == 2
    assert df["station"].tolist() == [716933, 716933]
    assert df["avg_speed"].tolist() == [64.3, 58.1]
    assert str(df["timestamp"].dt.tz) == "America/Los_Angeles"
    assert df["timestamp"].iloc[0].hour == 8


def test_keep_lanes_adds_lane_columns(tmp_path):
    p = tmp_path / "s.txt.gz"
    _write_sample(
        p,
        ["03/14/2025 08:00:00,1,7,405,S,ML,0.5,20,100,180,0.04,64.0,10,90,0.04,65.0,100"],
    )
    df = load_station_5min(p, keep_lanes=True)
    assert "lane1_avg_speed" in df.columns
    assert df["lane1_avg_speed"].iloc[0] == 65.0


def test_missing_speed_becomes_nan_not_zero(tmp_path):
    """Пустая скорость должна стать NaN.

    Если она превратится в 0, участок будет проезжаться бесконечно
    долго — и одна битая строка испортит все поездки через неё.
    """
    p = tmp_path / "s.txt.gz"
    _write_sample(
        p,
        ["03/14/2025 08:00:00,1,7,405,S,ML,0.5,0,0,,,,0,,,,0"],
    )
    df = load_station_5min(p)
    assert pd.isna(df["avg_speed"].iloc[0])
    assert df["avg_speed"].iloc[0] != 0


def test_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_station_5min(tmp_path / "нет-такого.txt.gz")
