"""Разделение выборки по времени.

Случайное перемешивание для временных данных — грубая ошибка. Поездка,
начавшаяся в 7:05, почти не отличается от начавшейся в 7:10; если одна
попала в обучение, а другая в тест, модель фактически подсмотрела ответ.
Метрики выйдут прекрасными, а работать модель не будет. Это называется
утечкой данных.

Поэтому делим строго по календарю: раннее — обучение, следующее —
подбор параметров, самое позднее — финальная проверка, к которой не
прикасаются до конца работы.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TemporalSplit:
    """Три непересекающихся отрезка времени."""

    train: pd.Series
    validation: pd.Series
    test: pd.Series

    def describe(self) -> str:
        lines = []
        for name, part in (
            ("train", self.train),
            ("validation", self.validation),
            ("test", self.test),
        ):
            if len(part):
                lines.append(
                    f"{name:11s} {len(part):6,} поездок  "
                    f"{part.index.min():%d.%m %H:%M} … {part.index.max():%d.%m %H:%M}"
                )
            else:
                lines.append(f"{name:11s} пусто")
        return "\n".join(lines)


def temporal_split(
    y: pd.Series,
    *,
    train_frac: float = 0.65,
    validation_frac: float = 0.15,
) -> TemporalSplit:
    """Разрезать ряд по времени в заданных пропорциях.

    Границы проводятся по **календарным сутками**, а не по номеру
    строки: иначе один и тот же утренний час пик окажется разрезан
    между обучением и тестом, и соседние поездки попадут в разные
    части. Это ослабленная версия той же утечки.
    """
    if not 0 < train_frac < 1 or not 0 <= validation_frac < 1:
        raise ValueError("доли должны лежать между 0 и 1")
    if train_frac + validation_frac >= 1:
        raise ValueError("на тест не остаётся места")

    y = y.dropna().sort_index()
    days = pd.Index(sorted({ts.date() for ts in y.index}))
    n = len(days)
    if n < 3:
        raise ValueError(f"нужно минимум трое суток, найдено {n}")

    n_train = max(1, int(round(n * train_frac)))
    n_val = max(1, int(round(n * validation_frac)))
    if n_train + n_val >= n:
        n_val = 1
        n_train = n - 2

    train_days = set(days[:n_train])
    val_days = set(days[n_train : n_train + n_val])

    date = pd.Index([ts.date() for ts in y.index])
    in_train = date.isin(train_days)
    in_val = date.isin(val_days)

    return TemporalSplit(
        train=y[in_train],
        validation=y[in_val],
        test=y[~in_train & ~in_val],
    )
