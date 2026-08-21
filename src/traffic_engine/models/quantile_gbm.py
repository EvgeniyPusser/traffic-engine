"""Градиентный бустинг с квантильной целью.

Третий уровень лестницы. Справочник **делит данные**: каждая ячейка
(тип дня × час) видит только свои наблюдения, поэтому дробное разбиение
описывает календарь точнее, но оценивает каждый квантиль по меньшему
числу примеров. Выхода внутри справочника нет.

Бустинг делит не данные, а **признаки**: каждое дерево видит всю
выборку и само решает, где резать. Пятница может получить собственную
поправку, оценённую при этом по всем поездкам, а не только по
пятничным.

Отдельная модель на каждое τ — так устроен квантильный objective в
LightGBM. Побочный эффект: модели друг о друге не знают и изредка
выдают P90 выше P95. Долю таких строк надо измерять
(``crossing_rate``) и чинить сортировкой (``sort_quantiles``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DEFAULT_TAUS = (0.5, 0.9, 0.95)

DEFAULT_PARAMS = {
    "n_estimators": 600,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 40,
    "subsample": 0.9,
    "subsample_freq": 1,
    "colsample_bytree": 0.9,
    "verbose": -1,
    "random_state": 7,
}


@dataclass
class QuantileGBM:
    """Обёртка над LightGBM: одна модель на каждое τ.

    Ранняя остановка обязательна и требует отдельной выборки. Отбирать
    число деревьев по тесту — та же утечка, что и обучение на нём.
    """

    taus: tuple[float, ...] = DEFAULT_TAUS
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    early_stopping_rounds: int = 50

    models_: dict = field(default_factory=dict, init=False)
    feature_names_: list[str] = field(default_factory=list, init=False)
    best_iterations_: dict = field(default_factory=dict, init=False)

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series | np.ndarray,
        *,
        eval_X: pd.DataFrame | None = None,
        eval_y: pd.Series | np.ndarray | None = None,
    ) -> QuantileGBM:
        import lightgbm as lgb

        if not all(0 < t < 1 for t in self.taus):
            raise ValueError("уровни квантилей должны лежать строго между 0 и 1")
        self.feature_names_ = list(X.columns)
        y = np.asarray(y, dtype=float)

        for tau in self.taus:
            model = lgb.LGBMRegressor(objective="quantile", alpha=tau, **self.params)
            kwargs = {}
            if eval_X is not None and eval_y is not None:
                kwargs["eval_set"] = [(eval_X, np.asarray(eval_y, dtype=float))]
                kwargs["callbacks"] = [
                    lgb.early_stopping(self.early_stopping_rounds, verbose=False)
                ]
            model.fit(X, y, **kwargs)
            self.models_[tau] = model
            self.best_iterations_[tau] = getattr(model, "best_iteration_", None)
        return self

    def predict(self, X: pd.DataFrame) -> dict[float, np.ndarray]:
        """Предсказания как есть, без сортировки.

        Сортировку делает вызывающий — и только после того, как измерил
        долю пересечений. Иначе дефект модели исчезает из отчёта.
        """
        if not self.models_:
            raise RuntimeError("модель не обучена")
        missing = set(self.feature_names_) - set(X.columns)
        if missing:
            raise ValueError(f"нет признаков: {sorted(missing)}")
        X = X[self.feature_names_]
        return {tau: m.predict(X) for tau, m in self.models_.items()}

    def importances(self, tau: float | None = None) -> pd.Series:
        """Сколько раз каждый признак использовался для разреза."""
        if not self.models_:
            raise RuntimeError("модель не обучена")
        tau = tau if tau is not None else max(self.taus)
        model = self.models_[tau]
        return pd.Series(model.feature_importances_, index=self.feature_names_).sort_values(
            ascending=False
        )
