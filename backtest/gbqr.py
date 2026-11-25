"""Model 2 (CyberEpi-GBQR): gradient-boosted quantile regression.

Pooled across locations; one LightGBM model per (horizon, quantile). See
MODEL2_PROTOCOL.md for the model definition and the evaluation rules.

At origin R everything comes from the admissions version published by R
(the same as-of rule as run_vintage.py), so training and features never see
later revisions.

Usage:
    python3 backtest/gbqr.py --seasons 2023-24,2024-25 --ncpus 4 --label gbqr-dev
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hub_data import PRIMARY_TARGET, STANDARD_QUANTILES, ed_frac_by_location, load_locations, load_model_output
from run_flusight import season_origins
from run_vintage import WEEK, ed_map_at, load_ed_vintages, load_vintages, pick_vintage, score, series_at, vintage_index

HORIZONS = (0, 1, 2, 3)
MAX_GAP = 2  # weeks the newest observation may lag R-7 (missing data version)
MAX_STEP = HORIZONS[-1] + 1 + MAX_GAP
FEATURES = ["lr", "d1", "d2", "d3", "d4", "ed", "ed_d1", "ed_d2", "sin_w", "cos_w"]
DEFAULT_PARAMS = {"num_leaves": 15, "n_estimators": 300, "learning_rate": 0.05, "min_data_in_leaf": 50}


ED_SOURCE = os.environ.get("GBQR_ED", "final")  # "final" or "vintage" (robustness check)


def _ed_at(ref: pd.Timestamp) -> pd.DataFrame | None:
    """ED fractions usable at R: final values, or the version published by R."""
    if ED_SOURCE == "final":
        ed = ed_frac_by_location()
        return ed[ed["week_end"] <= ref - WEEK]
    frames = []
    for loc in load_locations()["location"]:
        m = ed_map_at(ref, loc)
        if m:
            frames.append(pd.DataFrame({"week_end": list(m), "location": loc, "ili_frac": list(m.values())}))
    if not frames:
        return None
    ed = pd.concat(frames, ignore_index=True)
    ed["week_end"] = pd.to_datetime(ed["week_end"])
    return ed


def build_panel(ref: pd.Timestamp) -> pd.DataFrame | None:
    """Weekly panel (location, week) with features, from the version usable at R."""
    pick = pick_vintage(ref)
    if pick is None:
        return None
    as_of, _ = pick
    locs = load_locations().set_index("location")["population"]
    ed = _ed_at(ref)
    if ed is None:
        return None
    frames = []
    for loc, pop in locs.items():
        s = series_at(as_of, loc, ref - WEEK)
        if s.empty:
            continue
        df = pd.DataFrame({"week": s.index, "adm": s.to_numpy(float)})
        df["location"] = loc
        df["pop"] = float(pop)
        frames.append(df)
    p = pd.concat(frames, ignore_index=True)
    p = p.merge(ed.rename(columns={"week_end": "week"}), on=["location", "week"], how="left")
    p = p.sort_values(["location", "week"]).reset_index(drop=True)
    p["lr"] = np.log1p(p["adm"] / p["pop"] * 1e5)
    p["ed"] = np.log(p["ili_frac"] + 1e-4)
    g = p.groupby("location")
    for k in (1, 2, 3, 4):
        p[f"d{k}"] = p["lr"] - g["lr"].shift(k)
    p["ed_d1"] = p["ed"] - g["ed"].shift(1)
    p["ed_d2"] = p["ed"] - g["ed"].shift(2)
    doy = p["week"].dt.dayofyear.to_numpy()
    p["sin_w"] = np.sin(2 * np.pi * doy / 365.25)
    p["cos_w"] = np.cos(2 * np.pi * doy / 365.25)
    for k in range(1, MAX_STEP + 1):
        p[f"y{k}"] = g["lr"].shift(-k) - p["lr"]
    return p


def forecast_origin(ref: pd.Timestamp, params: dict) -> list[dict]:
    """Fit on everything known at R, emit hub-format rows for all locations."""
    import lightgbm as lgb

    p = build_panel(ref)
    if p is None:
        return []
    # Anchor each location at its newest observed week; if that lags R-7
    # (missing data version), forecast with a correspondingly longer step.
    obs = p.dropna(subset=["lr"])
    last = obs.loc[obs.groupby("location")["week"].idxmax()].copy()
    last["gap"] = ((ref - WEEK - last["week"]) / WEEK).astype(int)
    last = last[last["gap"] <= MAX_GAP]
    if last.empty:
        return []
    models: dict[int, list] = {}

    def fitted(k: int) -> list:
        if k not in models:
            train = p.dropna(subset=["lr", f"y{k}"])
            models[k] = [
                lgb.LGBMRegressor(objective="quantile", alpha=float(q), verbose=-1, n_jobs=1,
                                  **params).fit(train[FEATURES], train[f"y{k}"])
                for q in STANDARD_QUANTILES
            ]
        return models[k]

    rows: list[dict] = []
    for h in HORIZONS:
        parts = []
        for gap, grp in last.groupby("gap"):
            preds = np.column_stack([m.predict(grp[FEATURES]) for m in fitted(h + 1 + int(gap))])
            parts.append((grp, np.sort(preds, axis=1)))  # sorted: no quantile crossing
        sub = pd.concat([g for g, _ in parts])
        preds = np.vstack([pr for _, pr in parts])
        counts = np.expm1(sub["lr"].to_numpy()[:, None] + preds) * sub["pop"].to_numpy()[:, None] / 1e5
        counts = np.maximum(np.round(counts), 0)
        ted = str((ref + pd.Timedelta(weeks=h)).date())
        for loc, qv in zip(sub["location"], counts, strict=True):
            rows.extend({
                "reference_date": str(ref.date()), "target": PRIMARY_TARGET, "horizon": h,
                "location": loc, "target_end_date": ted, "output_type": "quantile",
                "output_type_id": f"{lev:g}", "value": int(v),
            } for lev, v in zip(STANDARD_QUANTILES, qv, strict=True))
    return rows


def _job(job: dict) -> list[dict]:
    rows = forecast_origin(pd.Timestamp(job["ref"]), job["params"])
    for r in rows:
        r["season"] = job["season"]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2023-24,2024-25")
    ap.add_argument("--ncpus", type=int, default=1)
    ap.add_argument("--out", default="backtest/out/model2")
    ap.add_argument("--label", default="gbqr")
    ap.add_argument("--params", default=json.dumps(DEFAULT_PARAMS))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    params = json.loads(args.params)

    load_vintages()
    vintage_index()
    ed_frac_by_location()
    if ED_SOURCE == "vintage":
        load_ed_vintages()
    baseline = load_model_output("FluSight-baseline")
    seasons = args.seasons.split(",")
    jobs = [{"season": s, "ref": str(pd.Timestamp(r).date()), "params": params}
            for s in seasons for r in season_origins(baseline, s)]
    if args.ncpus > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(args.ncpus) as pool:
            results = pool.map(_job, jobs, chunksize=1)
    else:
        results = [_job(j) for j in jobs]
    rows = pd.DataFrame([r for rs in results for r in rs])
    rows.to_csv(os.path.join(args.out, f"rows-{args.label}.csv"), index=False)

    summary = {"params": params, "seasons": {}}
    for s in seasons:
        sc = score(rows[rows["season"] == s], args.label)
        summary["seasons"][s] = sc
        b, e = sc["FluSight-baseline"], sc["FluSight-ensemble"]
        print(f"== {s}: vs baseline={b['relWIS']:.3f} vs ensemble={e['relWIS']:.3f} "
              f"(n={b['n_finite_paired']}) cov50={b['cov50']:.2f} cov90={b['cov90']:.2f}")
    with open(os.path.join(args.out, f"summary-{args.label}.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)


if __name__ == "__main__":
    main()
