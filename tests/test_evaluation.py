"""Тесты метрик и временного разделения."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from traffic_engine.evaluation import (
    coverage,
    crossing_rate,
    evaluate_quantiles,
    mae,
    pinball_loss,
    temporal_split,
)


def test_pinball_at_median_equals_half_mae():
    """При tau=0.5 pinball loss — это половина средней абсолютной ошибки."""
    y = np.array([1.0, 2.0, 10.0])
    p = np.full(3, 3.0)
    assert pinball_loss(y, p, 0.5) == pytest.approx(mae(y, p) / 2)


def test_pinball_is_minimised_at_the_true_quantile():
    """Свойство, ради которого эта функция и используется."""
    rng = np.random.default_rng(0)
    y = rng.lognormal(np.log(50), 0.3, size=20_000)
    for tau in (0.5, 0.9):
        truth = float(np.quantile(y, tau))
        here = pinball_loss(y, np.full_like(y, truth), tau)
        for shift in (-5.0, -1.0, 1.0, 5.0):
            assert pinball_loss(y, np.full_like(y, truth + shift), tau) > here


def test_pinball_punishes_underestimate_more_at_high_tau():
    y = np.array([100.0])
    under = pinball_loss(y, np.array([90.0]), 0.9)  # недооценили на 10
    over = pinball_loss(y, np.array([110.0]), 0.9)  # переоценили на 10
    assert under == pytest.approx(9.0)
    assert over == pytest.approx(1.0)
    assert under > over


def test_tau_outside_range_is_rejected():
    with pytest.raises(ValueError):
        pinball_loss([1.0], [1.0], 0.0)
    with pytest.raises(ValueError):
        pinball_loss([1.0], [1.0], 1.0)


def test_coverage_counts_values_at_or_below():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    assert coverage(y, np.full(4, 2.0)) == pytest.approx(0.5)
    assert coverage(y, np.full(4, 100.0)) == 1.0
    assert coverage(y, np.zeros(4)) == 0.0


def test_evaluate_quantiles_reports_coverage_error():
    rng = np.random.default_rng(1)
    y = rng.normal(10, 2, size=10_000)
    preds = {t: np.full(10_000, float(np.quantile(y, t))) for t in (0.5, 0.9)}
    out = evaluate_quantiles(y, preds).set_index("tau")
    assert abs(out.loc[0.5, "coverage_error"]) < 0.01
    assert abs(out.loc[0.9, "coverage_error"]) < 0.01


def test_crossing_rate_finds_inverted_quantiles():
    ok = {0.5: np.array([10.0, 11.0]), 0.9: np.array([14.0, 15.0])}
    assert crossing_rate(ok) == 0.0
    # во второй точке P90 ниже P50 — так быть не должно
    bad = {0.5: np.array([10.0, 20.0]), 0.9: np.array([14.0, 15.0])}
    assert crossing_rate(bad) == pytest.approx(0.5)


def _series(days: int) -> pd.Series:
    idx = pd.date_range("2026-01-01", periods=days * 288, freq="5min", tz="America/Los_Angeles")
    return pd.Series(np.arange(len(idx), dtype=float), index=idx)


def test_temporal_split_does_not_overlap_and_keeps_order():
    s = _series(20)
    sp = temporal_split(s, train_frac=0.65, validation_frac=0.15)
    assert len(sp.train) + len(sp.validation) + len(sp.test) == len(s)
    assert sp.train.index.max() < sp.validation.index.min()
    assert sp.validation.index.max() < sp.test.index.min()


def test_temporal_split_cuts_on_whole_days():
    """Границы должны проходить по суткам, иначе один час пик разрежется."""
    s = _series(20)
    sp = temporal_split(s)
    assert sp.train.index.max().hour == 23
    assert sp.validation.index.min().hour == 0


def test_temporal_split_needs_three_days():
    with pytest.raises(ValueError):
        temporal_split(_series(2))
