"""Метрики для квантильного прогноза.

Главная здесь не MAE, а **покрытие**. Модель, обещающая P90, обязана
накрывать 90% поездок отложенного периода. Обещала 90, накрыла 78 —
модель врёт, и никакой хороший MAE этого не оправдывает.

Покрытие при этом нельзя смотреть в одиночку: пообещай «сто минут
всегда» — и покрытие будет идеальным при полной бесполезности. Поэтому
рядом всегда идёт pinball loss, который наказывает и за промах, и за
чрезмерную осторожность.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, tau: float) -> float:
    """Средняя квантильная (pinball) ошибка.

    Недооценка штрафуется с весом ``tau``, переоценка — с весом
    ``1 - tau``. Минимум по постоянному предсказанию достигается ровно
    на квантиле уровня ``tau`` — именно поэтому этой функцией и учат
    модель предсказывать квантиль.
    """
    if not 0.0 < tau < 1.0:
        raise ValueError(f"tau должен лежать строго между 0 и 1, получено {tau}")
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    d = y_true - y_pred
    return float(np.mean(np.where(d >= 0, tau * d, (tau - 1.0) * d)))


def coverage(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Доля наблюдений, оказавшихся не выше предсказания.

    Для честной модели уровня ``tau`` результат должен быть близок к
    ``tau``. Отклонение вниз означает, что человек будет опаздывать
    чаще обещанного; вверх — что он выезжает слишком рано.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(y_true <= y_pred))


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Средняя абсолютная ошибка. Уместна только для оценки P50."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Корень из средней квадратичной ошибки."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def evaluate_quantiles(
    y_true: np.ndarray,
    predictions: dict[float, np.ndarray],
) -> pd.DataFrame:
    """Сводная таблица по всем уровням квантилей.

    Parameters
    ----------
    predictions
        Словарь ``{tau: предсказания}``.

    Returns
    -------
    pandas.DataFrame
        Столбцы: ``tau``, ``pinball``, ``coverage``, ``coverage_error``,
        ``mean_pred``. ``coverage_error`` — насколько фактическое
        покрытие отклонилось от обещанного; это и есть мера честности.
    """
    rows = []
    for tau in sorted(predictions):
        p = predictions[tau]
        cov = coverage(y_true, p)
        rows.append(
            {
                "tau": tau,
                "pinball": pinball_loss(y_true, p, tau),
                "coverage": cov,
                "coverage_error": cov - tau,
                "mean_pred": float(np.mean(p)),
            }
        )
    return pd.DataFrame(rows)


def crossing_rate(predictions: dict[float, np.ndarray]) -> float:
    """Доля точек, где предсказанные квантили идут не по возрастанию.

    Независимо обученные квантильные модели могут выдать P90 ниже P50 —
    это называется quantile crossing и физически бессмысленно. Метрику
    стоит считать всегда: она мгновенно показывает, что модели между
    собой не согласованы.
    """
    taus = sorted(predictions)
    if len(taus) < 2:
        return 0.0
    stacked = np.vstack([np.asarray(predictions[t], dtype=float) for t in taus])
    bad = np.any(np.diff(stacked, axis=0) < 0, axis=0)
    return float(np.mean(bad))
