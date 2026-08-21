"""Тесты квантильных моделей и починки пересечений."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from traffic_engine.features.state import forecast_matrix
from traffic_engine.models.postprocess import sort_quantiles
from traffic_engine.models.quantile_gbm import QuantileGBM
from traffic_engine.models.quantile_linear import QuantileLinear


def _dataset(n: int = 900, seed: int = 1):
    """Ответ линейно зависит от одного признака, шум растёт вместе с ним.

    Такой набор различает модели: предсказание среднего провалит
    калибровку хвоста, а квантильная модель — нет.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-05", periods=n, freq="5min", tz="America/Los_Angeles")
    x = rng.uniform(0, 10, n)
    y = 5 + x + rng.normal(0, 0.5 + 0.3 * x, n)
    return pd.DataFrame({"x": x, "noise": rng.normal(size=n)}, index=idx), pd.Series(y, index=idx)


# ---------- sort_quantiles ----------


def test_sorting_fixes_crossing():
    pred = {0.5: np.array([10.0, 10.0]), 0.9: np.array([12.0, 8.0]), 0.95: np.array([13.0, 9.0])}
    fixed = sort_quantiles(pred)
    assert np.all(fixed[0.5] <= fixed[0.9])
    assert np.all(fixed[0.9] <= fixed[0.95])
    # вторая строка была переставлена: 10, 8, 9 → 8, 9, 10
    assert fixed[0.5][1] == 8.0
    assert fixed[0.95][1] == 10.0


def test_sorting_leaves_correct_rows_untouched():
    pred = {0.5: np.array([1.0]), 0.9: np.array([2.0]), 0.95: np.array([3.0])}
    fixed = sort_quantiles(pred)
    for tau in pred:
        assert fixed[tau] == pred[tau]


def test_sorting_rejects_ragged_input():
    with pytest.raises(ValueError):
        sort_quantiles({0.5: np.zeros(3), 0.9: np.zeros(2)})


# ---------- forecast_matrix ----------


def test_horizon_shifts_state_but_not_calendar():
    idx = pd.date_range("2026-01-05", periods=10, freq="5min", tz="America/Los_Angeles")
    f = pd.DataFrame({"hour": idx.hour, "tt_lag0": np.arange(10.0)}, index=idx)
    out = forecast_matrix(f, horizon_minutes=15)
    # календарь на месте
    assert out["hour"].tolist() == f["hour"].tolist()
    # состояние отстало ровно на три строки
    assert out["tt_lag0"].iloc[5] == pytest.approx(f["tt_lag0"].iloc[2])
    assert out["tt_lag0"].iloc[:3].isna().all()


def test_zero_horizon_changes_nothing():
    idx = pd.date_range("2026-01-05", periods=5, freq="5min", tz="America/Los_Angeles")
    f = pd.DataFrame({"hour": idx.hour, "tt_lag0": np.arange(5.0)}, index=idx)
    pd.testing.assert_frame_equal(forecast_matrix(f, horizon_minutes=0), f)


def test_horizon_must_be_on_the_grid():
    idx = pd.date_range("2026-01-05", periods=3, freq="5min", tz="America/Los_Angeles")
    f = pd.DataFrame({"hour": idx.hour, "tt_lag0": [1.0, 2.0, 3.0]}, index=idx)
    with pytest.raises(ValueError):
        forecast_matrix(f, horizon_minutes=7)
    with pytest.raises(ValueError):
        forecast_matrix(f, horizon_minutes=-5)


# ---------- модели ----------


@pytest.mark.parametrize("make", [QuantileLinear, QuantileGBM])
def test_model_is_calibrated_on_data_it_was_shown(make):
    """Обещал P90 — накрой примерно 90%. Это минимальное требование."""
    X, y = _dataset()
    m = make().fit(X, y)
    pred = sort_quantiles(m.predict(X))
    for tau in (0.5, 0.9, 0.95):
        assert (y.to_numpy() <= pred[tau]).mean() == pytest.approx(tau, abs=0.06)


@pytest.mark.parametrize("make", [QuantileLinear, QuantileGBM])
def test_model_widens_the_band_where_noise_grows(make):
    """Разброс растёт с x, значит и P90 − P50 должен расти."""
    X, y = _dataset()
    m = make().fit(X, y)
    pred = sort_quantiles(m.predict(X))
    width = pred[0.9] - pred[0.5]
    low, high = X["x"] < 3, X["x"] > 7
    assert width[high].mean() > width[low].mean() * 1.5


@pytest.mark.parametrize("make", [QuantileLinear, QuantileGBM])
def test_predict_before_fit_raises(make):
    X, _ = _dataset(50)
    with pytest.raises(RuntimeError):
        make().predict(X)


@pytest.mark.parametrize("make", [QuantileLinear, QuantileGBM])
def test_missing_feature_raises_instead_of_guessing(make):
    X, y = _dataset(200)
    m = make().fit(X, y)
    with pytest.raises(ValueError):
        m.predict(X.drop(columns=["x"]))


@pytest.mark.parametrize("make", [QuantileLinear, QuantileGBM])
def test_bad_tau_raises(make):
    X, y = _dataset(100)
    with pytest.raises(ValueError):
        make(taus=(0.5, 1.0)).fit(X, y)


def test_gbm_importances_rank_the_real_feature_first():
    X, y = _dataset()
    m = QuantileGBM().fit(X, y)
    assert m.importances(0.9).index[0] == "x"


def test_linear_coefficient_has_the_right_sign():
    X, y = _dataset()
    m = QuantileLinear().fit(X, y)
    assert m.coefficients(0.5)["x"] > 0
