# traffic-engine

[![CI](https://github.com/EvgeniyPusser/traffic-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/EvgeniyPusser/traffic-engine/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

**Travel time is a distribution, not a number.**

A navigation app tells you `Estimated travel time: 54 minutes`. That number is an
average, and nobody plans their life around an average. What a person actually
needs to know is *when to leave so that they arrive on time* — and that question
has a different answer.

This project estimates the full distribution of travel time on a freeway corridor
in Los Angeles from Caltrans PeMS loop-detector data, and reports the quantiles
that decisions are actually made on:

```
expected      54 min
P50           51 min      typical day
P90           71 min      late once in ten trips
P95           83 min      late once in twenty
buffer        32 min      P95 − P50: what you must add to be reliably on time
```

---

## Status

**Stage 3 of 3 — models trained and evaluated on a held-out month.**

| Stage | | |
|---|---|---|
| 1 | Ingestion, schema, data quality report | done |
| 2 | Virtual trips → labelled dataset; baseline | done |
| 3 | Quantile models, temporal validation | done |
| 4 | Write-up and an interactive page | in progress |

---

## Results so far

**Corridor:** SR-210 West, Myrtle Ave → Sunflower Ave, 9.34 miles, 12 detector
stations. **Period:** January–April 2026, 108 usable days of 120, **30,981
virtual trips**.

| | minutes |
|---|---|
| free flow | 8.0 |
| P50 | 8.8 |
| P90 | 16.0 |
| P95 | 20.8 |
| P99 | 30.4 |
| worst trip observed | 50.0 |
| **buffer P95 − P50** | **11.9 (135% on top of the typical trip)** |

To arrive on time nineteen trips out of twenty you must budget more than double
what the trip usually takes. A navigation app reports about ten minutes.

### Models, measured on April — held out until the final run

The question is not *"I am leaving now, how long will it take"* — on a 9-mile
corridor that is a sensor reading, not a forecast, and the current corridor speed
answers it with correlation 0.99. The question is **"I must arrive by eight, when
do I leave"**, so every model below is evaluated at a decision **horizon**: the
decision is taken `h` minutes before departure and may use nothing measured after
that moment.

Pinball loss at τ = 0.9, lower is better:

| Horizon | single number | lookup table | linear QR | GBM, calendar only | **GBM** |
|---|---|---|---|---|---|
| 0 min | 1.433 | 0.357 | 0.054 | 0.424 | **0.050** |
| 30 min | 1.433 | 0.357 | 0.352 | 0.407 | **0.218** |
| **60 min** | 1.433 | 0.357 | 0.578 | 0.409 | **0.296** |

At an hour's notice the boosted model cuts the loss 17% below the lookup table
**and** is better calibrated — 89.6% coverage against 92.9% where 90% was
promised. In the morning peak that is about four minutes less waiting for the
same promise.

**Where the advantage ends.** Freshness is the model's whole capital, and it is
spent quickly. Gain over the lookup table by horizon: 86% at 0 minutes, 39% at
30, 17% at 60, **7% at 90**, and 3% at twelve hours. The feature rankings say the
same thing without words — past an hour, day-of-week and time-of-day rise to the
top and the model is doing what the lookup table already does, only in a more
complicated way.

So the product rule is:

```
less than ~90 minutes to departure  →  the model, fresh sensor data pays
more                                →  the calendar answer; the model adds
                                       percentage points, not minutes
```

Three results worth more than the win itself:

- **The single number is late on one trip in four** while promising nine in ten
  (75.7% coverage).
- **The gain comes from the feature, not the model.** Boosting on calendar
  features alone *loses* to the lookup table at every horizon. All of the
  improvement comes from one new input: what the corridor was doing in the
  half-hour before the decision. The prediction that boosting would win was
  right; the reason given for it was wrong, and that is written up as such.
- **Quantile crossing is reported before it is repaired** — up to 20% of rows at
  zero horizon. Sorting fixes it, and hiding it behind the sort would have
  concealed a real property of training one model per τ.

Full model report: [`docs/model-results.md`](docs/model-results.md). Working
notes, including every result that came out against expectation, are in
[`docs/PROJECT-LOG.md`](docs/PROJECT-LOG.md). The distribution chart is
[`docs/sr210-travel-time.html`](docs/sr210-travel-time.html).

---

## Known weaknesses

Stated here rather than buried, because a result whose limits are not named is
not a result.

- **A 1.84-mile gap.** Three consecutive detectors on the corridor died on
  16 February 2026 — one controller cabinet, three stations, the same morning —
  and never returned. The chain was cut from 15 stations to 12 to recover March
  and April. That stretch is now traversed entirely at its entry speed, and there
  is nothing in the data to check it against. Cost measured on identical January
  slots: +0.12 min mean bias.
- **Loop type unverified.** Double-loop stations measure speed directly;
  single-loop stations infer it from flow and occupancy assuming an average
  vehicle length, which biases with truck share. Which type this corridor uses
  has not been established.
- **Four months is thin for P95.** A tail estimate rests on rare events, and four
  months hold few of them.
- **One corridor.** Nothing here generalises to Los Angeles without being
  re-measured.
- **Calibration is an average.** The model hits 89.6% coverage across the day and
  87.2% inside the morning peak, where accuracy matters most. A per-hour
  correction would fix this and was not done.

---

## Why quantiles, and which quantile

The choice of P90 over P50 is not a matter of taste. It follows from the cost of
being wrong.

Arriving early costs you idle time. Arriving late costs you a penalty, a missed
next job, an angry customer. These are not equal. If you promise a time `q` and
minimise total cost over many trips, the optimal promise is exactly the quantile

```
τ = cost_late / (cost_late + cost_early)
```

So `P90` means precisely: *being one minute late hurts nine times more than
standing idle for one minute.* Different jobs have different ratios, and
therefore different quantiles. You compute τ from your own economics; you do not
pick it because it is a round number.

**Prior art, stated plainly.** The idea of a time cushion is not new here.
Transportation engineering has measured it for two decades: the FHWA *buffer
index* is `(P95 − mean) / mean` and the *planning time index* is
`P95 / free-flow time`. Those are corridor statistics, computed annually, and
they exist to decide where to widen a road.

Two things are different here, and they are the contribution:

1. **The quantile follows from the cost of being late**, through τ, instead of
   being fixed at 95 by convention.
2. **It is computed per departure moment**, not as a yearly figure for the
   corridor — which is what turns a planning statistic into an answer to
   *"when do I leave?"*.

One deliberate deviation: the buffer reported below is `P95 − P50`, not
`P95 − mean`. The mean is the very quantity this project argues against, and the
median is what a traveller actually experiences as a normal trip.

This is also why the models here are fit with **pinball loss** rather than
squared error. Squared error asks for the mean. Asymmetric absolute error asks
for a quantile. The loss function *is* the question.

### The part that makes this non-trivial

Expected value is additive: `E[T] = ΣE[Tᵢ]`, always, no assumptions needed.
Quantiles are not. And the error goes in both directions depending on what you
assume:

| Naive approach | What it silently assumes | Effect on the tail |
|---|---|---|
| Sum the segment means | there is no risk at all | catastrophic underestimate |
| Treat segments as independent | ρ = 0 | underestimates P90 |
| Sum the segment P90s | ρ = 1 (comonotonic) | overestimates P90 |

Congestion propagates along a corridor — a bad afternoon is bad on every segment
at once — so independence is not a conservative simplification, it is a
systematic understatement of risk. The true tail cannot be derived arithmetically
from per-segment statistics. It has to be measured, which is what this project
does.

---

## Method

**Labels.** PeMS has no "this trip took 54 minutes" column, so the labels are
constructed. For each departure time `t`, a *virtual trip* is driven through the
corridor over historical data: enter at the first station, use its speed at time
`t` to compute the time to the next station, arrive there at `t₁`, use *that*
station's speed at `t₁`, and so on. The sum is the travel time actually
experienced by a vehicle departing at `t`.

Taking all station speeds at the same instant instead would introduce a
systematic bias, and correlation between segments would be lost — which is
precisely the quantity that matters most here.

**Horizon.** Every model is evaluated at a decision horizon `h`: the decision is
made at `t`, departure happens at `t + h`, and no feature may use anything
measured after `t`. Without this the task collapses into a sensor reading — see
the model report.

**Models,** simplest first, each compared honestly against the last:

1. **Baseline** — empirical quantiles of historical travel time by (day type ×
   hour). No learning, just a lookup table. This is the bar to beat.
2. **Quantile regression** with pinball loss — same features as the boosted
   model, almost none of the flexibility, which is what isolates the two.
3. **Gradient boosting** (LightGBM) with quantile objective, one model per τ.

**Validation.** Strictly chronological — train on the earliest period, validate
on the next, and touch the most recent period only once, at the end. Random
shuffling would leak the future into the past and inflate every metric.

**Metrics.** MAE and pinball loss for P50/P90/P95, plus **empirical coverage**:
if the model promises P90, then on held-out data the realised time must fall
below it in ~90% of trips. Coverage failure matters more than a good MAE —
a well-calibrated interval that is honest beats a sharp one that lies.

---

## Data

PeMS data is free but requires a Caltrans account, and Caltrans deliberately
blocks programmatic access — the files are downloaded by hand through a browser.
There is no API client in this repository, by necessity.

1. Register at [pems.dot.ca.gov](https://pems.dot.ca.gov/).
2. Go to **Data Clearinghouse**.
3. Download **Type: Station 5-Minute**, **District: 7 (Los Angeles)** for the
   period of interest. One file per day, gzipped CSV, no header row.
4. Download **Type: Station Metadata** for the same district — without it the
   detectors have no coordinates and no position along the freeway.
5. Put everything in `data/raw/`. It is gitignored; raw data never enters the
   repository.

### Schema of one observation

`station_5min` files have no header. The first 12 fields describe the station as
a whole; after that come five fields per lane, and the number of lanes varies by
station, so the column count differs between files and must be inferred.

| # | Field | Meaning |
|---|---|---|
| 1 | `timestamp` | local California time, `MM/DD/YYYY HH:MM:SS` |
| 2 | `station` | detector station id, joins to metadata |
| 3 | `district` | Caltrans district; Los Angeles is 7 |
| 4 | `freeway` | route number, e.g. 405 |
| 5 | `direction` | N / S / E / W |
| 6 | `lane_type` | ML mainline, HV HOV, OR on-ramp, FR off-ramp, … |
| 7 | `station_length` | miles of freeway attributed to this station |
| 8 | `samples` | raw samples received in the 5-minute window |
| 9 | `pct_observed` | **percentage of values not imputed**, 0–100 |
| 10 | `total_flow` | vehicles in the 5-minute window, all lanes |
| 11 | `avg_occupancy` | fraction of time a vehicle was over the loop, 0–1 |
| 12 | `avg_speed` | miles per hour |
| … | `laneN_*` | `samples`, `flow`, `avg_occ`, `avg_speed`, `observed` |

**`pct_observed` is the most important field in the file.** PeMS never leaves
gaps: when a detector goes silent, the system fills the value in. An imputed row
is indistinguishable from a measured one except through this column. Training on
imputed data teaches the model to reproduce someone else's fill algorithm rather
than to observe the road.

### Time

Timestamps are local California wall-clock time with no timezone marker. Twice a
year this is genuinely ambiguous: one hour repeats in November and one hour does
not exist in March. The loader localises explicitly to `America/Los_Angeles` and
marks those rows `NaT` rather than guessing — the quality report counts them.

---

## Quick start

```bash
git clone <repo>
cd traffic-engine

uv sync --extra dev          # or: python -m venv .venv && pip install -e ".[dev]"

uv run pytest                # tests use synthetic fixtures, no data needed
```

Once you have real files in `data/raw/`:

```bash
# what is in the data, and how much of it is trustworthy
uv run traffic-engine profile data/raw/d07_text_station_5min_2025_03_14.txt.gz

# a whole month at once
uv run traffic-engine profile data/raw/

# stations along a corridor, ordered in the direction of travel
uv run traffic-engine meta data/raw/d07_text_meta_2025_03_14.txt --freeway 405 --direction S
```

---

## Layout

```
src/traffic_engine/
  config.py              paths, corridor definition, quality thresholds
  ingestion/
    station_5min.py      the 5-minute loader; column count → schema
    meta.py              station metadata; ordering stations by postmile
  quality/
    profile.py           what is measured vs. what PeMS imputed
  features/
    trips.py             virtual trips: speeds taken at arrival, not departure
    state.py             calendar + corridor state; the forecast horizon
  models/
    baseline.py          empirical quantile lookup, with a thin-cell fallback
    quantile_linear.py   linear quantile regression on pinball loss
    quantile_gbm.py      LightGBM, quantile objective, one model per tau
    postprocess.py       sorting away quantile crossing
  evaluation/
    metrics.py           pinball loss, coverage, quantile crossing
    split.py             chronological train/validation/test, split on whole days
  cli.py                 profile, meta
tests/                   synthetic fixtures; format parsing, not road behaviour
data/                    gitignored
docs/                    working notes and the distribution chart
```

---

## Deliberately out of scope

Spatio-temporal graph models, ARIMA, PostgreSQL, a prediction API, incident and
weather feeds, tolls and fuel, lane-level modelling, and the whole of Los Angeles
beyond a single corridor. Each is defensible; none of them is needed to establish
the claim, and a finished small thing is worth more than an unfinished large one.

The scope was cut deliberately and the reasoning is written down rather than
implied.

---

## License

MIT
