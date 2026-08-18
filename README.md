# traffic-engine

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

**Stage 1 of 3 — data ingestion and quality assessment.** No model has been
trained yet and no results are claimed yet.

| Stage | | |
|---|---|---|
| 1 | Ingestion, schema, data quality report | in progress |
| 2 | Virtual trips → labelled dataset; baseline | not started |
| 3 | Quantile models, temporal validation, write-up | not started |

What works today: reading raw PeMS `station_5min` and station-metadata files,
and producing an honest quality report on what is measured versus what PeMS
imputed.

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

**Models,** simplest first, each compared honestly against the last:

1. **Baseline** — empirical quantiles of historical travel time by (day of week ×
   5-minute slot). No learning, just a lookup table. This is the bar to beat.
2. **Quantile regression** with pinball loss.
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
  config.py              paths, corridor definition, timezone
  ingestion/
    station_5min.py      the 5-minute loader; column count → schema
    meta.py              station metadata; ordering stations by postmile
  quality/
    profile.py           what is measured vs. what PeMS imputed
  cli.py                 profile, meta
tests/                   synthetic fixtures; format parsing, not road behaviour
data/                    gitignored
notebooks/               exploration only, never production logic
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
