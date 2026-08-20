"""Проверки констант коридора.

Метаданных PeMS в репозитории нет (данные не коммитятся), поэтому здесь
проверяется только внутренняя непротиворечивость: список станций не
должен молча разъехаться с описанием коридора.
"""

from __future__ import annotations

from traffic_engine.config import CORRIDOR_STATIONS, DEFAULT_CORRIDOR, MIN_DAY_OBSERVED


def test_corridor_has_twelve_distinct_stations():
    assert len(CORRIDOR_STATIONS) == 12
    assert len(set(CORRIDOR_STATIONS)) == 12


def test_corridor_bounds_are_ordered_westbound():
    """Запад — убывание постмили, поэтому from < to."""
    assert DEFAULT_CORRIDOR.direction == "W"
    assert DEFAULT_CORRIDOR.postmile_from < DEFAULT_CORRIDOR.postmile_to


def test_day_gate_is_stricter_than_station_gate():
    """Сутки отбираем жёстче, чем станции: 95 против 90."""
    from traffic_engine.config import MIN_STATION_OBSERVED

    assert MIN_DAY_OBSERVED > MIN_STATION_OBSERVED
