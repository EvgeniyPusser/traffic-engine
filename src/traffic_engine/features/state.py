"""Признаки: календарь и состояние коридора перед выездом.

Справочник по (тип дня × час) знает только то, «как бывает обычно».
Он не может отличить сегодняшний вторник от прошлого. Единственное, что
способно его перебить, — свежие показания самого коридора: если полчаса
назад дорога уже стояла, сегодняшняя поездка почти наверняка будет
долгой, каким бы обычным ни был день недели.

Утечка
------
Метка (честная виртуальная поездка, вышедшая в момент ``t``) использует
скорости в моменты ``t`` и **позже** — машина едет и по дороге видит
новые данные. Признак имеет право смотреть только на ``t`` и **раньше**.

Поэтому все признаки состояния строятся из мгновенных срезов скорости в
моменты ``t, t−5, …, t−30``, каждый из которых на момент выезда уже
измерен. Ни один признак не заглядывает вперёд.

Что считается
-------------
``tt_lag{k}``
    Время проезда коридора по мгновенному срезу скорости ``k`` минут
    назад. Не настоящая поездка, а «сколько заняло бы, если бы дорога
    осталась такой же». Дешёвая и честная сводка обстановки одним числом.
``tt_trend``
    ``tt_lag0 − tt_lag15``. Знак говорит, затор нарастает или спадает.
``speed_min``
    Скорость на самой медленной станции коридора сейчас. Узкое место
    видно раньше, чем оно успевает испортить среднее.
``speed_mean``
    Средняя скорость по станциям сейчас.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from traffic_engine.features.trips import segment_lengths
from traffic_engine.models.baseline import is_off_day

SLOT_MINUTES = 5
DEFAULT_LAGS = (0, 5, 10, 15, 20, 25, 30)

MIN_SPEED_MPH = 5.0
MAX_SPEED_MPH = 90.0

# Признаки, известные заранее на любой срок: календарь не надо ждать.
CALENDAR_COLUMNS = (
    "hour",
    "minute_of_day",
    "tod_sin",
    "tod_cos",
    "day_of_week",
    "is_off_day",
)


def snapshot_travel_time(
    speed: pd.DataFrame,
    postmiles: np.ndarray | list[float],
    *,
    min_speed: float = MIN_SPEED_MPH,
    max_speed: float = MAX_SPEED_MPH,
) -> pd.Series:
    """Время проезда по мгновенному срезу скоростей.

    Все скорости берутся в один момент — тот, что стоит в индексе. Это
    не поездка (машина не умеет быть везде сразу), а сводка обстановки:
    сколько заняла бы дорога, если бы за время пути ничего не менялось.

    Как метка такая величина неверна; как признак — законна, потому что
    в момент выезда она уже известна целиком.
    """
    seg = segment_lengths(postmiles)
    if speed.shape[1] != len(seg) + 1:
        raise ValueError(f"станций {speed.shape[1]}, постмилей {len(postmiles)} — не сходится")
    v = np.clip(speed.to_numpy(dtype=float), min_speed, max_speed)
    # время каждого сегмента считается по скорости на его входной станции
    minutes = (seg / v[:, :-1]).sum(axis=1) * 60.0
    return pd.Series(minutes, index=speed.index, name="tt_snapshot")


def calendar_features(index: pd.DatetimeIndex, *, holidays=None) -> pd.DataFrame:
    """Календарь: то, что известно за год вперёд.

    Минуты суток закодированы синусом и косинусом, а не числом от 0 до
    1439. Иначе 23:55 и 00:05 оказываются на разных концах шкалы, хотя
    на дороге это один и тот же ночной час.
    """
    minute_of_day = index.hour * 60 + index.minute
    angle = 2 * np.pi * minute_of_day / (24 * 60)
    return pd.DataFrame(
        {
            "hour": index.hour.to_numpy(),
            "minute_of_day": minute_of_day.to_numpy(),
            "tod_sin": np.sin(angle),
            "tod_cos": np.cos(angle),
            "day_of_week": index.dayofweek.to_numpy(),
            "is_off_day": is_off_day(index, holidays).astype(int),
        },
        index=index,
    )


def corridor_state(
    speed: pd.DataFrame,
    postmiles: np.ndarray | list[float],
    *,
    lags: tuple[int, ...] = DEFAULT_LAGS,
) -> pd.DataFrame:
    """Состояние коридора на момент выезда и за предыдущие полчаса."""
    if any(k % SLOT_MINUTES for k in lags):
        raise ValueError(f"лаги должны быть кратны {SLOT_MINUTES} минутам")

    tt = snapshot_travel_time(speed, postmiles)
    v = speed.to_numpy(dtype=float)

    out = pd.DataFrame(index=speed.index)
    for k in lags:
        out[f"tt_lag{k}"] = tt.shift(k // SLOT_MINUTES)
    if 0 in lags and 15 in lags:
        out["tt_trend"] = out["tt_lag0"] - out["tt_lag15"]
    out["speed_min"] = np.nanmin(v, axis=1)
    out["speed_mean"] = np.nanmean(v, axis=1)
    return out


def build_features(
    speed: pd.DataFrame,
    postmiles: np.ndarray | list[float],
    *,
    lags: tuple[int, ...] = DEFAULT_LAGS,
    holidays=None,
) -> pd.DataFrame:
    """Полная матрица признаков: календарь + состояние коридора.

    Строки с пропусками не удаляются здесь — это решение принимает тот,
    кто обучает, и принимает его вместе с метками, чтобы признаки и
    метки не разъехались.
    """
    cal = calendar_features(speed.index, holidays=holidays)
    state = corridor_state(speed, postmiles, lags=lags)
    return pd.concat([cal, state], axis=1)


def forecast_matrix(
    features: pd.DataFrame,
    *,
    horizon_minutes: int,
    calendar_columns: tuple[str, ...] = CALENDAR_COLUMNS,
) -> pd.DataFrame:
    """Матрица признаков для решения, принимаемого заранее.

    Горизонт — вот что отличает прогноз от измерения. При
    ``horizon_minutes = 0`` вопрос звучит «выезжаю сейчас, сколько
    займёт», и на коротком коридоре ответ почти целиком содержится в
    сегодняшних скоростях: ``tt_lag0`` коррелирует с меткой на 0.99.
    Формально утечки нет — скорости в момент выезда действительно
    известны, — но задача при этом перестаёт быть прогнозом.

    Настоящий вопрос проекта другой: «мне нужно быть на месте к восьми,
    когда выезжать». Решение принимается в момент ``t``, а выезд
    произойдёт в ``t + h``. Значит признаки состояния берутся на ``t``,
    а метка — с поездки, вышедшей в ``t + h``.

    Здесь это и делается: календарь остаётся на момент выезда (он
    известен на год вперёд), а все остальные колонки сдвигаются на
    ``h`` минут назад.
    """
    if horizon_minutes < 0 or horizon_minutes % SLOT_MINUTES:
        raise ValueError(f"горизонт должен быть неотрицательным и кратным {SLOT_MINUTES} минутам")
    known = [c for c in calendar_columns if c in features.columns]
    state = [c for c in features.columns if c not in known]
    shifted = features[state].shift(horizon_minutes // SLOT_MINUTES)
    return pd.concat([features[known], shifted], axis=1)
