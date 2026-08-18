"""Пути и константы проекта.

Единственное место, где зашиты пути. Всё остальное берёт их отсюда.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("TRAFFIC_ENGINE_DATA", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

# Часовой пояс, в котором PeMS проставляет метки времени.
# Штампы в файлах — местное калифорнийское время, БЕЗ пометки о зоне
# и без учёта перехода на летнее время. См. README, раздел «Время».
PEMS_TIMEZONE = "America/Los_Angeles"

# Округ Caltrans, соответствующий Лос-Анджелесу.
LOS_ANGELES_DISTRICT = 7


@dataclass(frozen=True)
class Corridor:
    """Участок автомагистрали, на котором работаем.

    Границы заданы абсолютными постмилями (absolute postmile) — это
    непрерывная координата вдоль трассы из файла метаданных станций.
    """

    name: str
    freeway: int
    direction: str
    postmile_from: float
    postmile_to: float

    def __str__(self) -> str:  # pragma: no cover - косметика
        return (
            f"{self.name} (I-{self.freeway} {self.direction}, "
            f"PM {self.postmile_from}–{self.postmile_to})"
        )


# Кандидат по умолчанию. Окончательные границы — после просмотра метаданных.
DEFAULT_CORRIDOR = Corridor(
    name="I-405 South, I-10 → I-105",
    freeway=405,
    direction="S",
    postmile_from=0.0,
    postmile_to=0.0,  # ещё не заданы: заполнить по реальным метаданным
)


def ensure_dirs() -> None:
    """Создать рабочие каталоги, если их нет."""
    for d in (RAW_DIR, INTERIM_DIR, PROCESSED_DIR):
        d.mkdir(parents=True, exist_ok=True)
