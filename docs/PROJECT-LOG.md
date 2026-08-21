# Project log

A running record of decisions, findings, and things that turned out to be wrong.
Newest entries at the bottom. This file exists because the reasoning behind a
choice is worth more than the choice, and because a project that hides its
mistakes is not worth reading.

---

## The claim

A navigation app answers `54 minutes`. That is a conditional mean. Nobody plans
around a mean.

What a person with a deadline needs is a distribution: the typical case, the bad
case, the probability of being late, and how much time to add to be reliably on
time. This project estimates that distribution for one freeway corridor in Los
Angeles from Caltrans PeMS loop-detector data, and measures honestly how much
better it is than a lookup table.

## Why the quantile level is not arbitrary

Arriving early costs idle time. Arriving late costs a penalty, a missed job, a
customer. The two are not symmetric, and the asymmetry determines the answer.

If you promise a time `q` and minimise total cost over many trips, the optimal
promise is exactly the quantile at

```
τ = cost_late / (cost_late + cost_early)
```

`P90` therefore means precisely *being one minute late hurts nine times more than
standing idle for one minute*. τ is computed from the economics of the trip, not
chosen because 90 is a round number. This is also why the models are fit with
pinball loss rather than squared error: squared error asks for the mean,
asymmetric absolute error asks for a quantile. **The loss function is the
question.**

## Why this is not trivial arithmetic

Expected value is additive — `E[T] = Σ E[Tᵢ]` — regardless of dependence between
segments. Quantiles are not, and the naive alternatives fail in opposite
directions:

| Naive approach | What it silently assumes | Effect on the tail |
|---|---|---|
| Sum the segment means | no risk exists | catastrophic underestimate |
| Treat segments as independent | ρ = 0 | underestimates P90 |
| Sum the segment P90s | ρ = 1 (comonotonic) | overestimates P90 |

A simulation over 400,000 trips on a 10-segment route makes the point sharply:
with independent segments, ρ = 0.6, and perfect correlation, the **mean is
56.66 minutes in all three cases** — identical to two decimals — while P95 is
73.7, 101.3, and 113.8. The mean is structurally blind to the dependence
structure, because linearity of expectation never asks about it.

Congestion propagates along a corridor: a bad afternoon is bad on every segment
at once. Independence is therefore not a conservative simplification but a
systematic understatement of risk. The true tail cannot be derived from
per-segment statistics at all. It has to be measured.

## Scope, and what was deliberately cut

The original specification had thirteen responsibilities and five model tiers.
That is a team-year, and an unfinished repository is worse than a small finished
one. Cut, with reasons:

| Cut | Why |
|---|---|
| Spatio-temporal graph model | a year of work; belongs in "future work" |
| ARIMA / Prophet | adds nothing to the claim that boosting does not |
| PostgreSQL, storage abstraction layer | Parquet suffices while data fits on disk |
| Prediction API (FastAPI) | only needed for an integration that does not exist |
| Incidents, lane closures, roadworks | separate feeds, separate work |
| Weather | same, and its contribution is probably smaller than it feels |
| Tolls, fuel, the `Score(R,t)` objective | decorative without real prices |
| Lane-level modelling | station aggregate is enough |
| All of Los Angeles | one corridor |
| Docker, MLflow | tempting; irrelevant to the claim |

Holidays and the calendar were **kept** — twenty lines of code, and the data
turned out to demand them (see below).

---

## 2026-08-18 — Skeleton

Repository created as a standalone project rather than a subdirectory of an
existing application, because portfolio work has to open on its own with its own
README on the first screen.

Ingestion, station metadata, and a data-quality report. `station_5min` files
carry no header row and the column count varies by station (12 station-level
fields plus five per lane, up to eight lanes), so column names are reconstructed
from the count and a mismatch raises rather than silently shifting speed into the
occupancy field. 23 tests, CI on Python 3.11 and 3.12.

### Wrong turn worth recording

The first CI configuration passed `--python` to `uv sync` but not to `uv run`.
uv then saw a different interpreter request, silently discarded the environment
and rebuilt it without the dev extras, so `pytest` ran with no dependencies
installed. Both matrix jobs failed in 18 seconds. Fix: set `UV_PYTHON` once at
job level so every uv invocation agrees.

---

## 2026-08-18 — First contact with real data

31 days of PeMS District 7, January 2026. 9,854,208 rows of raw 5-minute station
measurements, downloaded by hand — Caltrans deliberately blocks programmatic
access, so there is no API client in this repository and there cannot be one.

### Finding 1: four fifths of PeMS is imputed, not measured

Mean `pct_observed` across the district over the week: **18.4%**.

When a detector goes silent, PeMS fills the value in. The imputed row is
indistinguishable from a measured one — plausible speed, plausible flow — except
through `pct_observed`. Train without checking it and the model learns to
reproduce someone else's fill algorithm while reporting excellent metrics.

Station health is close to binary, which makes the threshold easy:

| Mean observed | Mainline stations (of 1916) |
|---|---|
| > 0% | 394 |
| > 50% | 364 |
| > 90% | 279 |
| > 99% | 277 |

There is almost nothing in between. A 90% cutoff discards the garbage and costs
almost nothing.

### Finding 2: I-405 is unusable

The corridor had been chosen a priori — the most famous traffic jam in the United
States, instantly legible to any reader. The data vetoed it:

| | Mainline stations | Healthy (≥90%) | Mean observed |
|---|---|---|---|
| I-405 North | 105 | 6 | 10.7% |
| I-405 South | 114 | 6 | 7.7% |

Six working detectors over forty miles. No chain, no travel time.

### Corridor selection

Two requirements, both binding: an unbroken chain of healthy detectors (≥90%
observed, gaps ≤2 miles), **and** a travel time distribution actually worth
modelling. The second turned out to be decisive.

| Corridor | Contiguous stations | Miles | Free flow | P50 | P95 | Buffer |
|---|---|---|---|---|---|---|
| SR-118 E | 16 | 11.3 | 9.7 | 10.1 | 11.3 | 1.2 min (12%) |
| **SR-210 W** | **15** | **9.3** | **8.1** | **8.7** | **14.8** | **6.1 min (70%)** |
| SR-118 W | 13 | 6.9 | 5.9 | 6.2 | 6.9 | 0.7 min (11%) |
| SR-23 N | 12 | 6.2 | 5.4 | 5.5 | 6.2 | 0.7 min (13%) |
| I-10 E | 8 | 4.6 | 3.9 | 4.2 | 9.5 | 5.2 min (123%) |

The longest candidate was the most useless: a 12% buffer describes a road where
the navigation app is already right. I-10 E has the largest relative buffer but
only 4.6 miles, too short to make a credible argument about route reliability.

**Selected: SR-210 West**, Myrtle Ave → Sunflower Ave, 15 contiguous stations,
9.3 miles, through Irwindale, Azusa and Glendora. Observability on the corridor
is 99.5% with zero missing speeds across the month.

---

## 2026-08-18 — Virtual trips and first results

### Labels

PeMS has no travel-time column, so labels are constructed. For each departure
slot `t`, a vehicle enters the first station, traverses the first segment at that
station's speed at `t`, arrives at the second station at `t + Δ₁`, and uses the
speed observed **there, at that later moment**. The sum is the travel time
actually experienced by a vehicle departing at `t`. 8,927 trips over January.

### Result

| | minutes |
|---|---|
| free flow (P5) | 8.0 |
| P50 | 8.9 |
| P90 | 14.0 |
| P95 | 19.3 |
| P99 | 31.2 |
| max | 43.2 |

Buffer `P95 − P50` = **10.4 minutes, 117% on top of the typical trip**. To arrive
on time nineteen trips out of twenty you must budget more than double what the
trip usually takes. The navigation app says nine minutes.

Weekday departures at 07:00, all of January, sorted:

```
 8.3  8.7  8.7 12.9 14.9 16.6 17.6 18.9 19.1 23.0 24.5
24.9 27.1 28.5 28.6 29.5 29.7 30.6 31.6 33.3 35.4 37.7
```

Same place, same time, same kind of day — 8.3 to 37.7 minutes, a factor of 4.5.
The mean of that row, 23 minutes, describes none of those days.

Weekday morning peak (06:00–09:00, 792 trips): P50 19.2, P90 31.5, P95 33.7,
against 8.0 at free flow.

### Finding 3: a claim of mine was wrong

`trips.py` originally asserted that the naive simultaneous-snapshot method
"systematically underestimates" travel time. It does not.

| Method | P50 | P90 | P95 | mean |
|---|---|---|---|---|
| progressive (honest) | 8.9 | 14.0 | 19.3 | 10.4 |
| simultaneous (naive) | 8.9 | 14.1 | 19.2 | 10.4 |

Identical to two decimals. The agreement is aggregate, not pointwise: the paired
difference has mean 0.00, standard deviation 0.61, and a range of −15.5 to +7.6
minutes. Conditioning on the phase of congestion shows why.

| Congestion is | Trips | honest − naive |
|---|---|---|
| building fast | 158 | **+1.79 min** |
| building | 595 | +0.22 |
| steady | 7312 | −0.01 |
| clearing | 773 | −0.34 |
| clearing fast | 83 | **−1.17 min** |

The naive method errs in both directions and the errors cancel in aggregate. The
cause is corridor length: a 9–20 minute trip spans two to four 5-minute slots, so
conditions barely change while the vehicle is in transit. On an hour-long route
across the city the morning wave would catch up with the vehicle and the two
methods would diverge.

The progressive method is kept — it costs nothing extra, it preserves the
sequential dependence between segments, and it will not break on long routes.
But crediting it with an improvement on this data would be false.

### Finding 4: the planned baseline needs coarsening

The specified baseline was empirical quantiles by (day of week × 5-minute slot).
One month gives **four observations per cell**:

| Grouping | Cells | Median obs. per cell |
|---|---|---|
| day of week × 5-min slot | 2016 | 4 |
| weekday/weekend × 5-min slot | 576 | 15 |
| day of week × hour | 168 | 48 |
| weekday/weekend × hour | 48 | 186 |

A P90 estimated from four numbers is noise, and beating such a baseline would
prove nothing. The baseline will use weekday/weekend × hour with smoothing; the
5-minute resolution returns when there is a year of data.

### Sanity checks that passed

Median travel time by hour, January 1–7 (each weekday appears once):

| Day | 06:00 | 07:00 | 08:00 | 13:00 |
|---|---|---|---|---|
| Thu **1 Jan** | 8.8 | 9.1 | 9.9 | 8.8 |
| Fri 2 Jan | 8.2 | 8.2 | 8.2 | **15.7** |
| Mon 5 Jan | 15.3 | 15.0 | 14.3 | 8.6 |
| Tue 6 Jan | 20.8 | 22.8 | 16.1 | 9.4 |
| Wed 7 Jan | 22.0 | **25.9** | 19.2 | 9.5 |

Three things indicate the numbers are real. The morning peak is present and
builds through the week, reaching 25.9 minutes against 8.1 at free flow. **New
Year's Day has no peak at all** — a flat nine minutes all day, because nobody
drove to work; calendar features are a necessity here, not an ornament. And
2 January peaks at 13:00 rather than in the morning: the post-holiday return
wave, which no day-of-week lookup table can predict. That is already a hint about
where the baseline will lose.

---

---

## 2026-08-21 — Four months, and a corridor that fell apart

120 days of District 7 downloaded by hand, January through April 2026. 121 files,
2.2 GB compressed.

### Finding 5: detector networks decay, and a selection made once goes stale

Three consecutive stations of the fifteen — `IRWINDALE 2`, `VERNON`, `AZUSA 1` —
went silent **on 16 February 2026, all three on the same day**, and never
returned through 30 April.

| Date | 717675 | 717676 | 717678 |
|---|---|---|---|
| 12–15 Feb | 100% | 100% | 100% |
| **16 Feb** | **0%** | **0%** | **0%** |
| 17 Feb – 30 Apr | 0% | 0% | 0% |

The simultaneity matters more than the failure. Three adjacent detectors do not
fail independently on the same morning; one controller cabinet did. Their
neighbours on both sides held 100% throughout.

The general lesson is worth more than the incident: **`pct_observed` is a state
on a date, not a property of a station.** A corridor chosen on one week of data
can be invalid by the third month. Station selection has to be validated over
the same period the work will use.

### The cut, and what it cost

The chain was shortened to **twelve stations** — same endpoints, same 9.34 miles.
Both chains measured on the same January, on 8,610 common departure slots:

| | P50 | P90 | P95 | mean |
|---|---|---|---|---|
| 15 stations | 8.90 | 13.96 | 19.12 | 10.39 |
| 12 stations | 8.93 | 14.23 | 19.47 | 10.51 |

Paired difference: mean **+0.12 min**, sd 0.47. The shorter chain reads slightly
slower, as expected — a long segment is traversed entirely at its entry speed,
and the entry sits upstream of congestion more often than downstream.

The real cost is spatial, not statistical: **the largest gap grew from 1.24 to
1.84 miles**. Within the 2-mile threshold, but this is now the weakest point of
the method and is named as such in the README. Eight seconds of mean bias in
exchange for two additional months of data is not a close call.

### A second quality gate, at the day level

A station can be healthy on average and fail a particular day. Days are now kept
only if corridor `pct_observed` ≥ 95% (`MIN_DAY_OBSERVED`). **108 days of 120**
survive; mean corridor observability on those is 99.5%.

The gate caught 16 February on its own — the day the cabinet died — without being
told to look for it.

### Result on four months

30,981 virtual trips over 108 days:

| | Jan (15 st.) | Jan–Apr (12 st.) |
|---|---|---|
| free flow | 8.0 | 8.0 |
| P50 | 8.9 | 8.8 |
| P90 | 14.0 | 16.0 |
| P95 | 19.3 | 20.8 |
| P99 | 31.2 | 30.4 |
| max | 43.2 | 50.0 |
| buffer P95 − P50 | 10.4 (117%) | **11.9 (135%)** |

The centre of the distribution did not move. The tail did — which is exactly the
expected shape of the correction: rare events only become visible on a long
sample. January's worst trip was 43 minutes; four months contain a 50.

The chart also revealed structure invisible in January: a **second risk hump
between roughly 09:30 and 11:00**, where the median has already fallen back to
ten minutes while P90–P95 still reaches 23. The morning jam has cleared on most
days by ten — and on roughly one day in ten it has not. No single number,
mean or median, represents that hour.

---

## 2026-08-21 — The baseline, re-run on four months

Temporal split: train 1 Jan – 18 Mar (20,076), validation 19 Mar – 8 Apr (4,591),
test 9–30 Apr (6,314). The test period was untouched until this run.

| Grouping | Cells | Thin | Obs./cell | pinball τ=0.9 | P50 cov. | P90 | P95 |
|---|---|---|---|---|---|---|---|
| single number (10.7 min) | — | — | — | 1.434 | — | 75.7% | — |
| weekday/weekend × hour | 48 | 0 | 395 | **0.357** | 49.0% | 93.0% | 97.1% |
| Mon / Tue-Thu / Fri / Sat / Sun × hour | 120 | 0 | 120 | 0.422 | 49.3% | 92.4% | 95.7% |
| day of week × hour | 216 | 48 | 120 | 0.442 | 50.0% | **89.6%** | 92.6% |

Quantile crossing: 0% throughout.

**Confirmed.** The thin cells are gone — the January diagnosis ("not the model,
the sample size") was correct. And the median calibration repaired itself: on
January the P50 coverage drifted +23.3 points on test, here it is **−1.0**. That
drift was never a defect of the method, only of a month that is not homogeneous
inside itself.

**Not confirmed.** The expectation was that with enough data the finer grouping —
Friday as its own day, which January proved is real — would start winning. It
still loses on pinball, 0.422 against 0.357.

But it loses differently, and the difference is the interesting part: the coarse
grouping has the lower loss while systematically over-promising (claims P90,
covers 93%), and the day-of-week grouping is almost perfectly calibrated (89.6%)
while carrying a larger loss. **Neither dominates.**

This is not an unfinished experiment; it is a property of lookup tables. A table
**partitions the data**, and each cell sees only its own rows. Split finer and
the day-of-week structure is described better but every estimate rests on fewer
examples. Split coarser and the estimates stabilise but Friday is averaged with
Wednesday. There is no setting that escapes the trade — the escape is a model
that partitions *features* instead of *data*. Gradient boosting lets every tree
see all 20,000 training trips and decide for itself where to cut, so Friday can
receive its own correction estimated from the whole sample.

That is precisely where the baseline ends and the model begins.

---

## Open questions

- Four months is still thin for P95 — the tail rests on a handful of events.
- The 1.84-mile gap is unverifiable from within the data.
- Whether the corridor's stations are single- or double-loop is still unchecked.
  On single loops speed is inferred from flow and occupancy, not measured.
- Station metadata is dated July 2026 while measurements are January–April 2026.
  All stations matched, but this should be checked against an older metadata file
  for stations that moved.
- Whether the boosted model beats a well-smoothed empirical baseline at all is
  genuinely open. If it does not, that is a result and will be written up as one.
