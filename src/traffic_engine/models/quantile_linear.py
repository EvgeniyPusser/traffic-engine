"""Линейная квантильная регрессия на pinball loss.

Второй уровень лестницы, между справочником и бустингом. Модель проще
некуда: ответ — взвешенная сумма признаков. Ценность её не в точности, а
в том, что она отделяет два вопроса, которые иначе сливаются в один.

Если бустинг выигрывает у справочника, причин может быть две: появились
новые признаки — или дело в гибкости самих деревьев. Линейная модель
получает ровно те же признаки, что и бустинг, но гибкости почти лишена.
Разница между ней и справочником — вклад признаков; разница между
бустингом и ею — вклад нелинейности.

Признаки масштабируются перед обучением: солверу линейного
программирования разномасштабные колонки даются заметно тяжелее.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DEFAULT_TAUS = (0.5, 0.9, 0.95)


@dataclass
class QuantileLinear:
    """Одна линейная модель на каждое τ, обученная на pinball loss."""

    taus: tuple[float, ...] = DEFAULT_TAUS
    alpha: float = 0.0  # L1-штраф; 0 = чистая квантильная регрессия

    models_: dict = field(default_factory=dict, init=False)
    scaler_: object | None = field(default=None, init=False)
    feature_names_: list[str] = field(default_factory=list, init=False)

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> QuantileLinear:
        from sklearn.linear_model import QuantileRegressor
        from sklearn.preprocessing import StandardScaler

        if not all(0 < t < 1 for t in self.taus):
            raise ValueError("уровни квантилей должны лежать строго между 0 и 1")
        self.feature_names_ = list(X.columns)
        self.scaler_ = StandardScaler().fit(X)
        Z = self.scaler_.transform(X)
        y = np.asarray(y, dtype=float)
        for tau in self.taus:
            self.models_[tau] = QuantileRegressor(
                quantile=tau, alpha=self.alpha, solver="highs"
            ).fit(Z, y)
        return self

    def predict(self, X: pd.DataFrame) -> dict[float, np.ndarray]:
        if not self.models_:
            raise RuntimeError("модель не обучена")
        missing = set(self.feature_names_) - set(X.columns)
        if missing:
            raise ValueError(f"нет признаков: {sorted(missing)}")
        Z = self.scaler_.transform(X[self.feature_names_])
        return {tau: m.predict(Z) for tau, m in self.models_.items()}

    def coefficients(self, tau: float) -> pd.Series:
        """Веса на масштабированных признаках: сравнимы между собой."""
        if tau not in self.models_:
            raise KeyError(f"нет модели для tau={tau}")
        return pd.Series(self.models_[tau].coef_, index=self.feature_names_)
