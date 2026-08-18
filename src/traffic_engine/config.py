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


# Рабочий коридор, выбранный по реальным данным (неделя января 2026).
#
# Изначально предполагалась I-405 — самый известный затор в США. Данные
# этот выбор отменили: из 114 станций основного хода I-405 South лишь 6
# имеют настоящие измерения, средняя наблюдаемость 7.7%. Всё остальное
# PeMS достраивает. Строить на этом прогноз нельзя.
#
# SR-210 West прошла отбор по двум условиям сразу: 15 подряд идущих
# исправных станций на 9.3 мили без разрывов больше 1.24 мили — и
# настоящий утренний затор, ради которого проект и затевался
# (свободный ход 8.1 мин, P95 = 14.8 мин, максимум за неделю 27.7 мин).
#
# Подробности отбора — в docs/corridor-selection.md.
DEFAULT_CORRIDOR = Corridor(
    name="SR-210 West, Myrtle Ave → Sunflower Ave",
    freeway=210,
    direction="W",
    postmile_from=34.049,
    postmile_to=43.389,
)

# Минимальная доля неимпутированных значений, при которой станция
# считается пригодной. Порог 90 оставляет 243 станции из 1916 по всему
# округу — жёстко, но иначе в цепочку попадают достроенные числа.
MIN_STATION_OBSERVED = 90.0

# Максимальный разрыв между соседними исправными станциями, мили.
# Больше — и скорость на входе сегмента перестаёт что-либо говорить
# о том, что происходит в его середине.
MAX_STATION_GAP_MILES = 2.0


def ensure_dirs() -> None:
    """Создать рабочие каталоги, если их нет."""
    for d in (RAW_DIR, INTERIM_DIR, PROCESSED_DIR):
        d.mkdir(parents=True, exist_ok=True)
