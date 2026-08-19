"""Тесты справочника-baseline."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from traffic_engine.models.baseline import QuantileLookupBaseline, group_keys, is_off_day


def _index(days: int, start: str = "2026-01-05") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=days * 288, freq="5min", tz="America/Los_Angeles")


def test_weekend_is_off_day():
    # 3 января 2026 — суббота, 5 января — понедельник
    idx = pd.DatetimeIndex(["2026-01-03 08:00", "2026-01-05 08:00"])
    assert is_off_day(idx).tolist() == [True, False]


def test_holiday_on_a_weekday_counts_as_off():
    """1 января 2026 — четверг, но пика в тот день не было."""
    idx = pd.DatetimeIndex(["2026-01-01 08:00", "2026-01-08 08:00"])
    assert is_off_day(idx).tolist() == [True, False]


def test_group_key_is_daytype_and_hour():
    idx = pd.DatetimeIndex(["2026-01-05 07:30", "2026-01-05 08:05"])
    keys = group_keys(idx)
    assert list(keys) == [(False, 7), (False, 8)]


def test_baseline_reproduces_group_quantiles():
    """На известном наборе справочник должен вернуть ровно свои квантили."""
    idx = _index(20)
    rng = np.random.default_rng(3)
    # будни в 8 утра — медленно, всё остальное — быстро
    slow = (~is_off_day(idx)) & (idx.hour == 8)
    y = pd.Series(
        np.where(slow, rng.normal(30, 4, len(idx)), rng.normal(9, 1, len(idx))), index=idx
    )

    m = QuantileLookupBaseline(taus=(0.5, 0.9)).fit(y)
    pred = m.predict(idx)

    morning = slow
    assert pred[0.5][morning].mean() == pytest.approx(np.quantile(y[morning], 0.5), abs=0.3)
    assert pred[0.9][morning].mean() == pytest.approx(np.quantile(y[morning], 0.9), abs=0.3)
    # и утро должно быть заметно медленнее прочего времени
    assert pred[0.5][morning].mean() > pred[0.5][~morning].mean() + 10


def test_quantiles_do_not_cross():
    idx = _index(20)
    rng = np.random.default_rng(4)
    y = pd.Series(rng.lognormal(np.log(10), 0.4, len(idx)), index=idx)
    pred = QuantileLookupBaseline().fit(y).predict(idx)
    assert np.all(pred[0.5] <= pred[0.9])
    assert np.all(pred[0.9] <= pred[0.95])


def test_thin_cell_falls_back_instead_of_guessing():
    """Ячейка с тремя наблюдениями не должна давать собственный P95."""
    idx = _index(20)
    rng = np.random.default_rng(5)
    y = pd.Series(rng.normal(10, 2, len(idx)), index=idx)
    # оставляем только три наблюдения в буднее 3 утра
    keep = ~((~is_off_day(idx)) & (idx.hour == 3))
    y_thin = pd.concat([y[keep], y[~keep].iloc[:3]]).sort_index()

    m = QuantileLookupBaseline(min_samples=30).fit(y_thin)
    assert (False, 3) in m.thin_cells_
    target = pd.DatetimeIndex(["2026-01-06 03:10"]).tz_localize("America/Los_Angeles")
    pred = m.predict(target)
    # значение должно совпасть с общим квантилем по будням, а не с оценкой по трём точкам
    assert pred[0.9][0] == pytest.approx(m.fallback_[0.9].loc[False])


def test_unseen_hour_does_not_produce_nan():
    idx = _index(20)
    y = pd.Series(np.full(len(idx), 10.0), index=idx)
    y = y[y.index.hour != 4]
    m = QuantileLookupBaseline().fit(y)
    target = pd.DatetimeIndex(["2026-01-06 04:00"]).tz_localize("America/Los_Angeles")
    pred = m.predict(target)
    assert np.isfinite(pred[0.9][0])


def test_predict_before_fit_raises():
    with pytest.raises(RuntimeError):
        QuantileLookupBaseline().predict(_index(1))
