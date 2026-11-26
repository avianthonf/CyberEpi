"""Dev-season as-of forecasts of both live models and their equal-weight linear pool.

For every reference date of 2023-24 and 2024-25 (all locations) this writes, to
backtest/results/dev_members/ (hub format, flat):

  <ref>-CyberEpi-EAKF.csv    model 1, backtest/model_config.json settings
  <ref>-CyberEpi-GBQR.csv    model 2, backtest/model2_config.json settings
  <ref>-CyberEpi-MIX_LP.csv  shadow.mix_linear_pool of the two above

Vintage rule: admissions at R come from the latest published hub version usable
at R (run_vintage.pick_vintage). ED visit fractions are the final values for both
models: the as-published ED archive starts Nov 2025, so no vintage exists for dev
seasons (same convention as the D-0 ablation and gbqr.ED_SOURCE="final").

Then scores EAKF, GBQR and MIX_LP against FluSight-baseline per season (pooled WIS
via run_flusight.summarize) and tabulates median log error of MIX_LP by as-of
phase (3-week log growth: rising > +0.05/wk, declining < -0.05/wk, else peak) and
horizon. Log error = log((median+1)/(observed+1)); negative = forecast too low.

Usage:
    python3 backtest/dev_members.py --ncpus 8
    python3 backtest/dev_members.py --ncpus 8 --max-refs 4   # timing run
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gbqr  # noqa: E402
import shadow  # noqa: E402
from hub_data import PRIMARY_TARGET, load_locations, load_model_output, load_oracle  # noqa: E402
from run_flusight import SEASONS, season_origins, summarize  # noqa: E402
from run_vintage import WEEK, _run_job, load_vintages, pick_vintage, series_at, vintage_index  # noqa: E402

EAKF = "CyberEpi-EAKF"
GBQR = "CyberEpi-GBQR"
MIX = "CyberEpi-MIX_LP"
DEV_SEASONS = ["2023-24", "2024-25"]
COLS = ["reference_date", "target", "horizon", "target_end_date", "location",
        "output_type", "output_type_id", "value"]
PHASE_THRESHOLD = 0.05  # log units per week
GBQR_PARAMS: dict = {}  # set in main() before workers fork


def _load_cfg(name: str) -> dict:
    with open(os.path.join(HERE, name)) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Hub-format frame: exact columns, ISO dates, integer counts, '%g' quantile ids."""
    out = df[COLS].copy()
    out["reference_date"] = pd.to_datetime(out["reference_date"]).dt.strftime("%Y-%m-%d")
    out["target_end_date"] = pd.to_datetime(out["target_end_date"]).dt.strftime("%Y-%m-%d")
    out["location"] = out["location"].astype(str)
    out["horizon"] = out["horizon"].astype(int)
    out["output_type_id"] = out["output_type_id"].astype(float).map(lambda x: f"{x:g}")
    out["value"] = np.maximum(np.round(out["value"].astype(float)), 0).astype(int)
    return out.sort_values(["reference_date", "horizon", "location", "output_type_id"]).reset_index(drop=True)


def _write_hub(df: pd.DataFrame, out: str, model: str) -> None:
    for ref, g in df.groupby("reference_date"):
        g.to_csv(os.path.join(out, f"{ref}-{model}.csv"), index=False)


def _read_hub(folder: str, model: str, ref: str) -> pd.DataFrame | None:
    """Flat-file replacement for shadow.read_submitted (same filtering and id rounding)."""
    f = os.path.join(folder, f"{ref}-{model}.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f, dtype={"location": str, "output_type_id": str})
    df = df[(df["target"] == PRIMARY_TARGET) & (df["output_type"] == "quantile")].copy()
    df["output_type_id"] = df["output_type_id"].astype(float).round(3)
    return df


def _gbqr_one(ref_str: str) -> list[dict]:
    return gbqr.forecast_origin(pd.Timestamp(ref_str), GBQR_PARAMS, live=False)


def _as_of_growth(loc: str, ref: pd.Timestamp) -> float:
    """3-week log growth of as-of admissions: (log1p(last) - log1p(3 weeks earlier)) / 3."""
    pick = pick_vintage(ref)
    if pick is None:
        return float("nan")
    s = series_at(pick[0], loc, ref - WEEK)
    if len(s) < 4:
        return float("nan")
    last, prev = s.iloc[-1], s.iloc[-4]
    if pd.isna(last) or pd.isna(prev):
        return float("nan")
    return float((np.log1p(last) - np.log1p(prev)) / 3)


def _phase(g: float) -> str:
    if np.isnan(g):
        return "unknown"
    if g > PHASE_THRESHOLD:
        return "rising"
    if g < -PHASE_THRESHOLD:
        return "declining"
    return "peak"


def main() -> None:
    global GBQR_PARAMS
    ap = argparse.ArgumentParser()
    ap.add_argument("--ncpus", type=int, default=8)
    ap.add_argument("--max-refs", type=int, default=0, help="first N reference dates per season (timing runs)")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "dev_members"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if gbqr.ED_SOURCE != "final":
        raise SystemExit("GBQR_ED must be 'final' for dev members (no ED vintages before Nov 2025)")

    t0 = time.time()
    cfg = _load_cfg("model_config.json")
    if cfg["no_ili"]:
        raise SystemExit("model_config.json sets no_ili; this driver assumes ED is used")
    GBQR_PARAMS = _load_cfg("model2_config.json")
    eakf_args = {k: cfg[k] for k in ("members", "sd_beta", "sd_hir", "r_rel", "inflation", "s_obs",
                                     "sd_beta_fwd", "sd_lc", "r_ili_rel", "seed")}
    eakf_args["ili"] = "final"

    baseline = load_model_output("FluSight-baseline")
    origins = {}
    for s in DEV_SEASONS:
        o = list(season_origins(baseline, s))
        origins[s] = o[: args.max_refs] if args.max_refs else o
    refs = sorted({pd.Timestamp(x).strftime("%Y-%m-%d") for s in DEV_SEASONS for x in origins[s]})
    print(f"{len(refs)} reference dates; {sum(len(v) for v in origins.values())} season-origins")

    load_vintages()
    vintage_index()
    locs = load_locations()["location"].astype(str).tolist()

    # Model 1: one job per (season, location); run_vintage re-runs the filter per origin on that origin's vintage.
    t = time.time()
    jobs = [{"season": s, "loc": loc, "args": eakf_args, "origins": origins[s]}
            for s in DEV_SEASONS for loc in locs]
    with mp.get_context("fork").Pool(args.ncpus) as pool:
        res = pool.map(_run_job, jobs, chunksize=1)
    bad = [(r["season"], r["loc"], r.get("reason")) for r in res if r["status"] != "ok"]
    frames = [pd.DataFrame(r["rows"]) for r in res if r["status"] == "ok" and r["rows"]]
    eakf_df = _normalize(pd.concat(frames, ignore_index=True))
    print(f"EAKF: {len(eakf_df)} rows, {eakf_df['reference_date'].nunique()} refs, "
          f"{len(bad)} skipped jobs {bad[:3]} in {time.time() - t:.0f}s")

    # Model 2: one call per reference date (it refits on all locations known at R).
    t = time.time()
    with mp.get_context("fork").Pool(args.ncpus) as pool:
        gres = pool.map(_gbqr_one, refs, chunksize=1)
    gbqr_df = _normalize(pd.DataFrame([r for rows in gres for r in rows]))
    print(f"GBQR: {len(gbqr_df)} rows, {gbqr_df['reference_date'].nunique()} refs in {time.time() - t:.0f}s")

    _write_hub(eakf_df, args.out, EAKF)
    _write_hub(gbqr_df, args.out, GBQR)

    # Equal-weight linear pool, read back from the flat files written above.
    t = time.time()
    shadow.read_submitted = lambda forecasts, model, ref: _read_hub(forecasts, model, ref)
    mix_frames = []
    for ref in refs:
        if not (os.path.exists(os.path.join(args.out, f"{ref}-{EAKF}.csv"))
                and os.path.exists(os.path.join(args.out, f"{ref}-{GBQR}.csv"))):
            print(f"[warn] {ref}: missing a member; no MIX_LP")
            continue
        m = shadow.mix_linear_pool(ref, SimpleNamespace(forecasts=args.out, ref=ref))
        m = _normalize(m)
        mix_frames.append(m)
    mix_df = pd.concat(mix_frames, ignore_index=True)
    _write_hub(mix_df, args.out, MIX)
    print(f"MIX_LP: {len(mix_df)} rows, {mix_df['reference_date'].nunique()} refs in {time.time() - t:.0f}s")

    # Scoring against FluSight-baseline per season, pooled.
    oracle = load_oracle()
    base = load_model_output("FluSight-baseline")
    base["output_type_id"] = base["output_type_id"].astype(float)
    summary: dict = {"refs": refs, "seasons": {}}
    rd = {m: df.assign(_rd=pd.to_datetime(df["reference_date"])) for m, df in
          ((EAKF, eakf_df), (GBQR, gbqr_df), (MIX, mix_df))}
    for model, df in rd.items():
        summary["seasons"][model] = {}
        for s in DEV_SEASONS + ["pooled"]:
            if s == "pooled":
                sub = df
            else:
                lo, hi = SEASONS[s]
                sub = df[(df["_rd"] >= lo) & (df["_rd"] <= hi)]
            sub = sub.drop(columns="_rd")
            sc, _ = summarize(sub, oracle, base, model)
            summary["seasons"][model][s] = {k: sc[k] for k in ("relWIS", "wis_mean", "wis_baseline_mean",
                                                               "n_finite_paired", "cov50", "cov90")}
            print(f"{model} {s}: relWIS vs baseline={sc['relWIS']:.3f} "
                  f"(n={sc['n_finite_paired']}, cov50={sc['cov50']:.2f}, cov90={sc['cov90']:.2f})")

    # MIX_LP median log error by as-of phase x horizon.
    mix_med = mix_df[mix_df["output_type_id"] == "0.5"].copy()
    mix_med["reference_date"] = pd.to_datetime(mix_med["reference_date"])
    mix_med["target_end_date"] = pd.to_datetime(mix_med["target_end_date"])
    o = oracle[["location", "target_end_date", "oracle_value"]].drop_duplicates(["location", "target_end_date"])
    mix_med = mix_med.merge(o, on=["location", "target_end_date"], how="inner")
    growth = {(loc, r): _as_of_growth(loc, r) for loc, r in
              mix_med[["location", "reference_date"]].drop_duplicates().itertuples(index=False)}
    mix_med["growth"] = [growth[(loc, r)] for loc, r in zip(mix_med["location"], mix_med["reference_date"], strict=True)]
    mix_med["phase"] = mix_med["growth"].map(_phase)
    mix_med["season"] = [next((s for s in DEV_SEASONS if SEASONS[s][0] <= d.strftime("%Y-%m-%d") <= SEASONS[s][1]), "?")
                         for d in mix_med["reference_date"]]
    mix_med["log_err"] = np.log((mix_med["value"].astype(float) + 1) / (mix_med["oracle_value"].astype(float) + 1))
    unk = int((mix_med["phase"] == "unknown").sum())
    tab = (mix_med[mix_med["phase"] != "unknown"]
           .groupby(["season", "phase", "horizon"])["log_err"]
           .agg(median="median", n="size").reset_index())
    tab.to_csv(os.path.join(args.out, "mix_lp_phase_error.csv"), index=False)
    print(f"MIX_LP median log error by season x phase x horizon (unknown-phase rows excluded: {unk}):")
    print(tab.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
