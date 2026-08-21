"""Тесты признаков состояния коридора."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from traffic_engine.features.state import (
    build_features,
    calendar_features,
    corridor_state,
    snapshot_travel_time,
)


def _speed(n: int, value: float = 60.0, stations: int = 3) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05", periods=n, freq="5min", tz="America/Los_Angeles")
    return pd.DataFrame(np.full((n, stations), value), index=idx, columns=[1, 2, 3])


PM = [0.0, 5.0, 10.0]  # два сегмента по пять миль


def test_snapshot_time_is_distance_over_speed():
    """10 миль при 60 mph — ровно 10 минут."""
    tt = snapshot_travel_time(_speed(3), PM)
    assert np.allclose(tt.to_numpy(), 10.0)


def test_snapshot_uses_entry_station_of_each_segment():
    """Скорость последней станции не влияет: за ней сегментов нет."""
    s = _speed(1)
    s.iloc[0, 2] = 5.0  # последняя станция встала
    assert snapshot_travel_time(s, PM).iloc[0] == pytest.approx(10.0)


def test_snapshot_rejects_mismatched_postmiles():
    with pytest.raises(ValueError):
        snapshot_travel_time(_speed(2), [0.0, 5.0])


def test_lags_look_backwards_only():
    """tt_lag5 в момент t должен равняться tt_lag0 в момент t−5."""
    s = _speed(10)
    s.iloc[:, :] = np.linspace(30, 70, 10)[:, None]
    st = corridor_state(s, PM, lags=(0, 5))
    assert st["tt_lag5"].iloc[5] == pytest.approx(st["tt_lag0"].iloc[4])
    # первая строка не может знать прошлого
    assert np.isnan(st["tt_lag5"].iloc[0])


def test_no_feature_sees_the_future():
    """Меняем будущее — прошлое не должно шевельнуться.

    Прямая проверка на утечку: если испортить скорости после момента t,
    признаки в момент t обязаны остаться прежними.
    """
    s = _speed(20)
    before = corridor_state(s, PM)
    s.iloc[12:, :] = 5.0  # катастрофа после 12-й строки
    after = corridor_state(s, PM)
    pd.testing.assert_frame_equal(before.iloc[:12], after.iloc[:12])


def test_trend_sign_follows_congestion():
    """Тренд сравнивает сейчас с тем, что было ровно 15 минут (3 строки) назад."""
    s = _speed(10)
    s.iloc[:, :] = 60.0
    s.iloc[7:, :] = 20.0  # затор начался на 7-й строке
    st = corridor_state(s, PM)
    # строка 9 стоит в заторе, строка 6 — ещё нет
    assert st["tt_trend"].iloc[9] > 0
    # а на строке 6 сравнивать не с чем: 15 минут назад было то же самое
    assert st["tt_trend"].iloc[6] == pytest.approx(0.0)


def test_bottleneck_is_the_slowest_station():
    s = _speed(1)
    s.iloc[0] = [60.0, 12.0, 60.0]
    st = corridor_state(s, PM, lags=(0,))
    assert st["speed_min"].iloc[0] == pytest.approx(12.0)
    assert st["speed_mean"].iloc[0] == pytest.approx(44.0)


def test_midnight_is_not_far_from_midnight():
    """23:55 и 00:05 должны оказаться рядом, а не на разных концах шкалы."""
    idx = pd.DatetimeIndex(["2026-01-05 23:55", "2026-01-06 00:05"])
    cal = calendar_features(idx)
    d = np.hypot(
        cal["tod_sin"].iloc[0] - cal["tod_sin"].iloc[1],
        cal["tod_cos"].iloc[0] - cal["tod_cos"].iloc[1],
    )
    assert d < 0.1
    # а сырое minute_of_day разошлось бы на весь диапазон
    assert abs(cal["minute_of_day"].iloc[0] - cal["minute_of_day"].iloc[1]) > 1400


def test_build_features_joins_without_losing_rows():
    s = _speed(30)
    f = build_features(s, PM)
    assert len(f) == 30
    assert {"hour", "is_off_day", "tt_lag0", "tt_trend", "speed_min"} <= set(f.columns)


def test_lag_must_be_on_the_grid():
    with pytest.raises(ValueError):
        corridor_state(_speed(5), PM, lags=(0, 7))
