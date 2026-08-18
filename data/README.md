# data/

Raw data never enters git. This directory is a working area only.

```
data/
  raw/         downloaded PeMS files, exactly as they came — never edited
  interim/     cleaned and filtered, still per-station
  processed/   virtual trips, ready for training
```

## What to put in `raw/`

From the [PeMS Data Clearinghouse](https://pems.dot.ca.gov/) (free account required):

| Type | District | Note |
|---|---|---|
| Station 5-Minute | 7 — Los Angeles | one gzipped file per day, no header row |
| Station Metadata | 7 — Los Angeles | tab-separated, has a header; coordinates and postmiles live here |

Caltrans blocks scripted downloading, so these are fetched by hand through the
browser. Keep the original filenames — the loader matches on
`*station_5min*.txt.gz`.

## Rule

`raw/` is read-only once written. Every transformation produces a new file in
`interim/` or `processed/`. If a result cannot be rebuilt from `raw/` by running
the pipeline, it does not count.
