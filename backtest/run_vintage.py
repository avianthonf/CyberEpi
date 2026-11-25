"""Vintage-correct ("as-of") FluSight backtest.

The original driver (`run_flusight.py`) runs the filter once over the final,
fully revised admissions series. A live forecaster never sees that series:
at origin R it only has the data version the CDC published before R, in
which the most recent weeks are usually under-reported and later revised.

This driver rebuilds that view. For every origin R it:

1. picks the latest published data version (`as_of`) from the hub's
   `target-data/time-series.csv` whose newest week is <= R-7 and whose
   publication label is <= R;
2. re-runs the filter from the season warm-up to week R-7 on that version
   only (weeks missing from the version are processed as "no observation");
3. emits forecasts for R exactly as the original driver would.

Scoring is against the final values (`oracle-output.csv`), as the hub does,
and is reported relative to both FluSight-baseline and FluSight-ensemble.

ED-visit input (the model's second observation stream):
`--ili final`   final ED values (small leakage; versions do not exist before
                Nov 2025, so this is the only option for earlier seasons);
`--ili vintage` as-published ED values too (fully vintage-correct); origins
                before the first archived ED version are skipped;
`--ili none`    admissions only.

Usage:
    python3 backtest/run_vintage.py --seasons 2024-25,2025-26 \
        --locations US,06 --ncpus 4 --label vintage --ili none
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from functools import lru_cache

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eakf import EakfConfig
from hub_data import HUB_DIR, PRIMARY_TARGET, ed_frac_by_location, load_locations, load_model_output, load_oracle
from run_flusight import SEASONS, _stable_seed, run_location, season_origins, summarize

WEEK = pd.Timedelta(weeks=1)


@lru_cache(maxsize=1)
def load_vintages() -> pd.DataFrame:
    """All published versions of weekly flu admissions (location, week, as_of)."""
    df = pd.read_csv(
        os.path.join(HUB_DIR, "time-series.csv"),
        usecols=["as_of", "target", "target_end_date", "location", "observation"],
        parse_dates=["as_of", "target_end_date"],
        dtype={"location": str},
    )
    df = df[df["target"] == PRIMARY_TARGET].drop(columns="target")
    df["observation"] = pd.to_numeric(df["observation"], errors="coerce")
    return df


@lru_cache(maxsize=1)
def vintage_index() -> pd.DataFrame:
    """One row per published version: its label and its newest data week."""
    v = load_vintages()
    return v.groupby("as_of", as_index=False)["target_end_date"].max().rename(
        columns={"target_end_date": "max_week"})


def pick_vintage(origin: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Latest version usable at origin R: published by R, newest week <= R-7."""
    idx = vintage_index()
    ok = idx[(idx["as_of"] <= origin) & (idx["max_week"] <= origin - WEEK)]
    if ok.empty:
        return None
    row = ok.loc[ok["as_of"].idxmax()]
    return row["as_of"], row["max_week"]


@lru_cache(maxsize=None)
def _vintage_by_loc(as_of: pd.Timestamp) -> dict[str, pd.Series]:
    v = load_vintages()
    sub = v[v["as_of"] == as_of]
    return {loc: g.set_index("target_end_date")["observation"].sort_index()
            for loc, g in sub.groupby("location")}


def series_at(as_of: pd.Timestamp, loc: str, last_week: pd.Timestamp) -> pd.Series:
    """Admissions series as published in version `as_of`, on a full weekly
    grid ending at `last_week` (missing weeks -> NaN, i.e. no observation)."""
    s = _vintage_by_loc(as_of).get(loc)
    if s is None or s.empty:
        return pd.Series(dtype=float)
    grid = pd.date_range(end=last_week, start=min(s.index.min(), last_week), freq="7D")
    return s.reindex(grid)


@lru_cache(maxsize=1)
def load_ed_vintages() -> pd.DataFrame:
    """As-published ED flu-visit fractions: (vintage, max_week, location, week_end, ili_frac).

    Two hub sources: weekly archive files `target-ed-visits-prop_<last week>.csv`
    (labelled by their newest week) and the `as_of` rows of time-series.csv.
    """
    parts = []
    for f in glob.glob(os.path.join(HUB_DIR, "target-data-archive", "target-ed-visits-prop_*.csv")):
        d = pd.read_csv(f, parse_dates=["date"], dtype={"location": str})
        label = pd.Timestamp(os.path.basename(f).split("_")[1][:-4])
        parts.append(pd.DataFrame({"vintage": label, "location": d["location"],
                                   "week_end": d["date"], "ili_frac": d["value"]}))
    ts = pd.read_csv(os.path.join(HUB_DIR, "time-series.csv"),
                     usecols=["as_of", "target", "target_end_date", "location", "observation"],
                     parse_dates=["as_of", "target_end_date"], dtype={"location": str})
    ts = ts[ts["target"] == "wk inc flu prop ed visits"]
    parts.append(pd.DataFrame({"vintage": ts["as_of"], "location": ts["location"],
                               "week_end": ts["target_end_date"], "ili_frac": ts["observation"]}))
    ed = pd.concat(parts, ignore_index=True).dropna()
    ed["max_week"] = ed.groupby("vintage")["week_end"].transform("max")
    return ed


def ed_map_at(origin: pd.Timestamp, loc: str) -> dict | None:
    """ED values for `loc` from the newest version usable at origin R."""
    ed = load_ed_vintages()
    ok = ed[(ed["vintage"] <= origin) & (ed["max_week"] <= origin - WEEK)]
    if ok.empty:
        return None
    sub = ok[(ok["vintage"] == ok["vintage"].max()) & (ok["location"] == loc)]
    return dict(zip(sub["week_end"].values, sub["ili_frac"].values, strict=True))


def _cfg(a: dict) -> EakfConfig:
    return EakfConfig(
        n_members=a["members"], sd_beta=a["sd_beta"], sd_hir=a["sd_hir"],
        r_rel=a["r_rel"], r_ili_rel=a["r_ili_rel"], sd_lc=a["sd_lc"],
        inflation=a["inflation"], s_obs=a["s_obs"], use_ili=a["ili"] != "none",
        sd_beta_fwd=a["sd_beta_fwd"], seed=a["seed"],
    )


def _run_job(job: dict) -> dict:
    season, loc, a = job["season"], job["loc"], job["args"]
    locs = load_locations().set_index("location")
    if loc not in locs.index:
        return {"status": "skipped", "reason": "unknown location", "season": season, "loc": loc}
    pop = float(locs.loc[loc, "population"])
    ili_map = None
    if a["ili"] == "final":
        ed = ed_frac_by_location()
        sub = ed[ed["location"] == loc]
        ili_map = dict(zip(sub["week_end"].values, sub["ili_frac"].values, strict=True))
    cfg = _cfg(a)
    run_seed = a["seed"] + _stable_seed(loc, season)

    rows: list[dict] = []
    trace: list[dict] = []
    for origin in job["origins"]:
        R = pd.Timestamp(origin)
        pick = pick_vintage(R)
        if pick is None:
            trace.append({"location": loc, "reference_date": str(R.date()), "as_of": None, "stale_weeks": None})
            continue
        as_of, max_week = pick
        if a["ili"] == "vintage":
            ili_map = ed_map_at(R, loc)
            if not ili_map:
                continue
        tw = series_at(as_of, loc, R - WEEK)
        if tw.notna().sum() < 10:
            continue
        r_rows, _ = run_location(
            loc, pop, tw, cfg, {np.datetime64(R.date())},
            SEASONS[season][0], SEASONS[season][1],
            ili_map=ili_map, run_rng_seed=run_seed,
        )
        rows.extend(r_rows)
        trace.append({"location": loc, "reference_date": str(R.date()),
                      "as_of": str(as_of.date()),
                      "stale_weeks": int((R - WEEK - max_week) / WEEK)})
    return {"status": "ok", "season": season, "loc": loc, "rows": rows, "trace": trace}


def score(rows: pd.DataFrame, label: str) -> dict:
    """relWIS vs FluSight-baseline and vs FluSight-ensemble, per horizon."""
    oracle = load_oracle()
    out: dict = {}
    for ref_model in ("FluSight-baseline", "FluSight-ensemble"):
        ref = load_model_output(ref_model)
        ref["output_type_id"] = ref["output_type_id"].astype(float)
        summ, _ = summarize(rows, oracle, ref, label)
        out[ref_model] = summ
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locations", default="US,06,12,36,48")
    ap.add_argument("--seasons", default="2024-25,2025-26")
    ap.add_argument("--ili", choices=["none", "final", "vintage"], default="none")
    ap.add_argument("--members", type=int, default=300)
    ap.add_argument("--sd-beta", type=float, default=0.05)
    ap.add_argument("--sd-hir", type=float, default=0.005)
    ap.add_argument("--r-rel", type=float, default=0.15)
    ap.add_argument("--inflation", type=float, default=1.03)
    ap.add_argument("--s-obs", type=float, default=0.10)
    ap.add_argument("--sd-beta-fwd", type=float, default=0.05)
    ap.add_argument("--sd-lc", type=float, default=0.01)
    ap.add_argument("--r-ili-rel", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--ncpus", type=int, default=1)
    ap.add_argument("--out", default="backtest/out/honest")
    ap.add_argument("--label", default="vintage")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    a = {k: getattr(args, k) for k in (
        "members", "sd_beta", "sd_hir", "r_rel", "inflation", "s_obs",
        "sd_beta_fwd", "sd_lc", "r_ili_rel", "seed", "ili")}

    # Load shared data once in the parent so forked workers inherit it.
    load_vintages()
    vintage_index()
    if args.ili == "vintage":
        load_ed_vintages()
    baseline = load_model_output("FluSight-baseline")
    seasons = args.seasons.split(",")
    jobs = [
        {"season": s, "loc": loc, "args": a, "origins": list(season_origins(baseline, s))}
        for s in seasons for loc in args.locations.split(",")
    ]
    if args.ncpus > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(args.ncpus) as pool:
            results = pool.map(_run_job, jobs, chunksize=1)
    else:
        results = [_run_job(j) for j in jobs]

    frames, traces = [], []
    for r in results:
        if r.get("status") != "ok":
            print(f"[warn] {r['season']} {r['loc']}: {r.get('reason')}")
            continue
        traces.append(pd.DataFrame(r["trace"]).assign(season=r["season"]))
        if r["rows"]:
            frames.append(pd.DataFrame(r["rows"]).assign(season=r["season"]))
    if not frames:
        print("no forecasts produced")
        return
    rows = pd.concat(frames, ignore_index=True)
    rows.to_csv(os.path.join(args.out, f"rows-{args.label}.csv"), index=False)
    tr = pd.concat(traces, ignore_index=True)
    tr.to_csv(os.path.join(args.out, f"trace-{args.label}.csv"), index=False)

    summaries = {"config": a, "seasons": {}}
    for s in seasons:
        rs = rows[rows["season"] == s]
        if rs.empty:
            continue
        sc = score(rs, args.label)
        summaries["seasons"][s] = sc
        b, e = sc["FluSight-baseline"], sc["FluSight-ensemble"]
        print(f"== {s}: relWIS vs baseline={b['relWIS']:.3f} (n={b['n_finite_paired']}) "
              f"vs ensemble={e['relWIS']:.3f} (n={e['n_finite_paired']}) "
              f"cov50={b['cov50']:.2f} cov90={b['cov90']:.2f}")
    if len(seasons) > 1:
        sc = score(rows, args.label)
        summaries["pooled"] = sc
        print(f"== pooled: vs baseline={sc['FluSight-baseline']['relWIS']:.3f} "
              f"vs ensemble={sc['FluSight-ensemble']['relWIS']:.3f}")
    stale = tr["stale_weeks"].dropna()
    summaries["vintage_staleness_weeks"] = stale.value_counts().sort_index().to_dict()
    with open(os.path.join(args.out, f"summary-{args.label}.json"), "w") as f:
        json.dump(summaries, f, indent=2, default=str)


if __name__ == "__main__":
    main()
