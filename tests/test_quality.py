"""Тесты отчёта о качестве."""

from __future__ import annotations

import pandas as pd

from traffic_engine.quality import profile_station_5min
from traffic_engine.quality.profile import unusable_stations


def _frame(rows):
    df = pd.DataFrame(
        rows,
        columns=[
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
        ],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def test_counts_missing_speed_with_traffic():
    df = _frame(
        [
            ["2025-03-14 08:00", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 64.0],
            # поток есть, скорости нет — сломанная петля
            ["2025-03-14 08:05", 1, 7, 405, "S", "ML", 0.5, 20, 100, 175, 0.04, None],
        ]
    )
    rep = profile_station_5min(df)
    assert rep.findings["строк с пропущенной скоростью"] == 1
    assert rep.findings["  из них при ненулевом потоке"] == 1


def test_detects_fully_imputed_rows():
    df = _frame(
        [
            ["2025-03-14 08:00", 1, 7, 405, "S", "ML", 0.5, 0, 0, 100, 0.03, 60.0],
            ["2025-03-14 08:05", 1, 7, 405, "S", "ML", 0.5, 20, 100, 110, 0.03, 61.0],
        ]
    )
    rep = profile_station_5min(df)
    assert rep.findings["полностью достроенных строк (0%)"] == 1
    assert rep.findings["средняя наблюдаемость, %"] == 50.0


def test_detects_duplicates():
    df = _frame(
        [
            ["2025-03-14 08:00", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 64.0],
            ["2025-03-14 08:00", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 64.0],
        ]
    )
    rep = profile_station_5min(df)
    assert rep.findings["дубликатов (станция+время)"] == 1


def test_flags_speed_out_of_range():
    df = _frame(
        [
            ["2025-03-14 08:00", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 250.0],
            ["2025-03-14 08:05", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 60.0],
        ]
    )
    rep = profile_station_5min(df)
    assert rep.findings["скорость вне диапазона 1..100"] == 1


def test_unusable_stations_picks_the_bad_one():
    df = _frame(
        [
            ["2025-03-14 08:00", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 64.0],
            ["2025-03-14 08:05", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 64.0],
            ["2025-03-14 08:00", 2, 7, 405, "S", "ML", 0.5, 0, 0, 180, 0.04, 64.0],
            ["2025-03-14 08:05", 2, 7, 405, "S", "ML", 0.5, 0, 0, 180, 0.04, 64.0],
        ]
    )
    rep = profile_station_5min(df)
    assert unusable_stations(rep) == [2]


def test_interval_coverage_notices_gaps():
    # два интервала подряд для одной станции — покрытие полное
    df = _frame(
        [
            ["2025-03-14 08:00", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 64.0],
            ["2025-03-14 08:05", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 64.0],
        ]
    )
    assert profile_station_5min(df).interval_coverage == 1.0

    # пропущен интервал 08:05 — покрытие 2/3
    df2 = _frame(
        [
            ["2025-03-14 08:00", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 64.0],
            ["2025-03-14 08:10", 1, 7, 405, "S", "ML", 0.5, 20, 100, 180, 0.04, 64.0],
        ]
    )
    assert profile_station_5min(df2).interval_coverage < 0.7
