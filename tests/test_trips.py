"""Тесты виртуальных поездок.

Скорости здесь подобраны так, чтобы ответ считался в уме. Это проверка
арифметики и того, что скорость берётся в правильный момент, а не
утверждения о дороге.
"""

from __future__ import annotations

import pandas as pd
import pytest

from traffic_engine.features.trips import segment_lengths, speed_matrix, virtual_trips


def _speed_frame(rows: list[list[float]], n_slots: int | None = None) -> pd.DataFrame:
    n = n_slots or len(rows)
    idx = pd.date_range("2026-01-05 07:00", periods=n, freq="5min", tz="America/Los_Angeles")
    return pd.DataFrame(rows, index=idx, columns=[1, 2, 3][: len(rows[0])])


def test_segment_lengths_ignore_direction():
    # на запад постмили убывают — длина всё равно положительная
    assert segment_lengths([43.0, 40.0, 34.0]).tolist() == [3.0, 6.0]
    assert segment_lengths([34.0, 40.0, 43.0]).tolist() == [6.0, 3.0]


def test_needs_at_least_two_stations():
    with pytest.raises(ValueError):
        segment_lengths([5.0])


def test_constant_speed_gives_distance_over_speed():
    """10 миль при 60 миль/ч — ровно 10 минут."""
    speed = _speed_frame([[60.0, 60.0, 60.0]] * 12)
    t = virtual_trips(speed, [0.0, 5.0, 10.0])
    assert t.iloc[0] == pytest.approx(10.0)


def test_speed_is_taken_on_arrival_not_on_departure():
    """Главное свойство метода.

    Первый сегмент — 30 миль при 60 миль/ч, то есть ровно 30 минут,
    шесть пятиминутных интервалов. Значит на второй станции надо взять
    скорость из строки 6, а не из строки 0.

    В строке 0 вторая станция едет 60, в строке 6 — 15. Правильный
    ответ: 30 + (10 / 15) * 60 = 70 минут. Наивный одновременный срез
    дал бы 30 + 10 = 40.
    """
    rows = [[60.0, 60.0]] * 6 + [[60.0, 15.0]] * 20
    speed = _speed_frame(rows)
    postmiles = [0.0, 30.0, 40.0]
    speed = speed.copy()
    speed.columns = [1, 2]
    speed[3] = speed[2]
    speed = speed[[1, 2, 3]]

    honest = virtual_trips(speed, postmiles)
    naive = virtual_trips(speed, postmiles, simultaneous=True)

    assert honest.iloc[0] == pytest.approx(70.0)
    assert naive.iloc[0] == pytest.approx(40.0)
    assert honest.iloc[0] > naive.iloc[0]


def test_trip_running_past_the_end_becomes_nan():
    """Поездка, которой не хватает данных, должна стать NaN, а не числом.

    Три станции, то есть два сегмента. Первый — 10 миль при 6 миль/ч,
    сто минут, двадцать интервалов. К моменту прибытия на вторую
    станцию выборка давно кончилась, и взять там скорость неоткуда.
    """
    speed = _speed_frame([[6.0, 6.0, 6.0]] * 3)
    t = virtual_trips(speed, [0.0, 10.0, 20.0])
    assert t.isna().all()


def test_single_segment_never_overruns():
    """Один сегмент переполниться не может — и это не поблажка.

    Скорость на входе нужна только в момент отправления, а она есть по
    определению. Дальше метод ничего не запрашивает, так что поездка
    целиком опирается на наблюдённые данные, даже если заканчивается
    за пределами выборки.
    """
    speed = _speed_frame([[6.0, 6.0]] * 3)
    t = virtual_trips(speed, [0.0, 10.0])
    assert t.iloc[-1] == pytest.approx(100.0)
    assert t.notna().all()


def test_absurdly_low_speed_is_clipped():
    """Ползущая пробка не должна давать поездку длиной в сутки."""
    speed = _speed_frame([[0.01, 0.01]] * 200)
    t = virtual_trips(speed, [0.0, 1.0])
    # при отсечке в 5 миль/ч миля занимает 12 минут, а не 6000
    assert t.iloc[0] == pytest.approx(12.0)


def test_uneven_time_grid_is_rejected():
    idx = pd.DatetimeIndex(["2026-01-05 07:00", "2026-01-05 07:05", "2026-01-05 07:20"])
    speed = pd.DataFrame([[60.0, 60.0]] * 3, index=idx, columns=[1, 2])
    with pytest.raises(ValueError, match="неравномерн"):
        virtual_trips(speed, [0.0, 1.0])


def test_speed_matrix_keeps_travel_order():
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-05 07:00"] * 3),
            "station": [10, 20, 30],
            "avg_speed": [50.0, 60.0, 70.0],
        }
    )
    wide = speed_matrix(df, [30, 10, 20])
    assert list(wide.columns) == [30, 10, 20]
    assert wide.iloc[0].tolist() == [70.0, 50.0, 60.0]


def test_speed_matrix_reports_missing_station():
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-05 07:00"]),
            "station": [10],
            "avg_speed": [50.0],
        }
    )
    with pytest.raises(KeyError):
        speed_matrix(df, [10, 999])
