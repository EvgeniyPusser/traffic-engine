"""Починка предсказаний после обучения.

Модели обучаются по одной на каждое τ и друг о друге ничего не знают,
поэтому изредка выдают P90 выше P95. Такая пара — не «почти верно», а
бессмыслица: она утверждает, что доля поездок короче 90-го процентиля
больше, чем короче 95-го.
"""

from __future__ import annotations

import numpy as np


def sort_quantiles(predictions: dict[float, np.ndarray]) -> dict[float, np.ndarray]:
    """Отсортировать предсказания по строкам, убрав пересечения.

    Починка стандартная и не может навредить: если в строке P90 и P95
    переставлены местами, обмен уменьшает сумму pinball-штрафов сразу
    для обоих τ — потому что каждое значение переезжает к тому уровню,
    которому оно и подходит. При правильном порядке сортировка не меняет
    ничего.

    Скрывать факт пересечений не следует: считать долю до починки
    (``crossing_rate``) и указывать её в отчёте — часть честности.
    """
    if not predictions:
        return {}
    taus = sorted(predictions)
    lengths = {len(predictions[t]) for t in taus}
    if len(lengths) != 1:
        raise ValueError("предсказания разной длины")
    matrix = np.sort(np.vstack([np.asarray(predictions[t], dtype=float) for t in taus]), axis=0)
    return {tau: matrix[i] for i, tau in enumerate(taus)}
