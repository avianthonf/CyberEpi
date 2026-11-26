"""A1: model 2 (GBQR) maturity-matched labels and backfill-corrected edge, dev seasons only.

Runs model 2 as-of on every dev reference date (2023-24, 2024-25) for each variant:
  base      current model 2 (model2_config.json)
  drop{m}   training labels within m weeks of R-7 dropped (gbqr.LABEL_DROP_M = m)
  backfill  as-of admissions rescaled by f(age) from older vintages (gbqr.BACKFILL)
Scores each against FluSight-baseline and against `base`, and reports the share of
truth below the forecast median by as-of phase (dev_members phase rule).
ED inputs are final values (no ED vintages before Nov 2025); admissions are as-of.

Usage (Python 3.10+, lightgbm):
    python3 backtest/a1_labels.py --ncpus 8 --variants base,drop2,drop3,drop4,backfill
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gbqr  # noqa: E402
from dev_members import DEV_SEASONS, _as_of_growth, _load_cfg, _normalize, _phase  # noqa: E402
from hub_data import load_model_output, load_oracle  # noqa: E402
from run_flusight import SEASONS, season_origins, summarize  # noqa: E402
from run_vintage import load_vintages, vintage_index  # noqa: E402

MODEL = "CyberEpi-GBQR"
PARAMS: dict = {}
N_BOOT = 1000


def _set_variant(v: str) -> None:
    gbqr.LABEL_DROP_M = int(v[4:]) if v.startswith("drop") else 0
    gbqr.BACKFILL = v == "backfill"


def _one(job: tuple[str, str]) -> list[dict]:
    variant, ref = job
    _set_variant(variant)
    return gbqr.forecast_origin(pd.Timestamp(ref), PARAMS, live=False)


def _season(d: pd.Timestamp) -> str:
    s = d.strftime("%Y-%m-%d")
    return next((k for k in DEV_SEASONS if SEASONS[k][0] <= s <= SEASONS[k][1]), "?")


def main() -> None:
    global PARAMS
    ap = argparse.ArgumentParser()
    ap.add_argument("--ncpus", type=int, default=8)
    ap.add_argument("--variants", default="base,drop2,drop3,drop4,backfill")
    ap.add_argument("--refs", default="", help="comma list of reference dates (default: all dev origins)")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "a1_labels"))
    args = ap.parse_args()
    if gbqr.ED_SOURCE != "final":
        raise SystemExit("GBQR_ED must be 'final' on dev seasons (no ED vintages before Nov 2025)")
    os.makedirs(args.out, exist_ok=True)
    PARAMS = _load_cfg("model2_config.json")
    baseline = load_model_output("FluSight-baseline")
    if args.refs:
        refs = args.refs.split(",")
    else:
        refs = sorted({pd.Timestamp(x).strftime("%Y-%m-%d") for s in DEV_SEASONS for x in season_origins(baseline, s)})
    variants = args.variants.split(",")
    load_vintages()
    vintage_index()

    oracle = load_oracle()
    base_out = baseline.copy()
    base_out["output_type_id"] = base_out["output_type_id"].astype(float)
    tabs: dict[str, pd.DataFrame] = {}
    runtime: dict[str, float] = {}
    for v in variants:
        t = time.time()
        with mp.get_context("fork").Pool(args.ncpus) as pool:
            res = pool.map(_one, [(v, r) for r in refs], chunksize=1)
        runtime[v] = time.time() - t
        df = _normalize(pd.DataFrame([r for rows in res for r in rows]))
        df.to_csv(os.path.join(args.out, f"{v}.csv.gz"), index=False)
        _, tab = summarize(df, oracle, base_out, MODEL)
        tab = tab[np.isfinite(tab["wis"]) & np.isfinite(tab["wis_base"])].copy()
        tab["reference_date"] = pd.to_datetime(tab["reference_date"])
        tab["season"] = tab["reference_date"].map(_season)
        tabs[v] = tab
        print(f"{v}: {df['reference_date'].nunique()} refs, {len(tab)} scored rows in {runtime[v]:.0f}s", flush=True)

    keys = ["location", "reference_date", "horizon"]
    g = {(loc, r): _as_of_growth(loc, r) for loc, r in
         tabs[variants[0]][["location", "reference_date"]].drop_duplicates().itertuples(index=False)}
    rng = np.random.default_rng(0)
    out: dict = {"refs": refs, "runtime_s": runtime, "variants": {}}
    ref_tab = tabs.get("base")
    for v, tab in tabs.items():
        tab["phase"] = [_phase(g[(loc, r)]) for loc, r in zip(tab["location"], tab["reference_date"], strict=True)]
        tab["below"] = (tab["observed"] < tab["median"]).astype(float)
        res: dict = {}
        for s in DEV_SEASONS:
            sub = tab[tab["season"] == s]
            r = {"relWIS": float(sub["wis"].mean() / sub["wis_base"].mean()), "n": len(sub),
                 "cov50": float(sub["cov50"].mean()), "cov90": float(sub["cov90"].mean())}
            for ph in ("rising", "peak", "declining"):
                q = sub[sub["phase"] == ph]
                r[f"below_median_{ph}"] = float(q["below"].mean())
                r[f"n_{ph}"] = len(q)
                r[f"relWIS_{ph}"] = float(q["wis"].mean() / q["wis_base"].mean())
            if ref_tab is not None:
                b = ref_tab[ref_tab["season"] == s][keys + ["wis"]].rename(columns={"wis": "wis_ref"})
                m = sub.merge(b, on=keys, how="inner")
                r["relWIS_vs_base"] = float(m["wis"].mean() / m["wis_ref"].mean())
                for ph in ("rising", "peak", "declining"):
                    q = m[m["phase"] == ph]
                    r[f"relWIS_vs_base_{ph}"] = float(q["wis"].mean() / q["wis_ref"].mean())
                # Block bootstrap over reference dates.
                per = m.groupby("reference_date")[["wis", "wis_ref"]].sum()
                idx = rng.integers(0, len(per), size=(N_BOOT, len(per)))
                a, bb = per["wis"].to_numpy()[idx].sum(1), per["wis_ref"].to_numpy()[idx].sum(1)
                r["relWIS_vs_base_ci90"] = [float(x) for x in np.quantile(a / bb, [0.05, 0.95])]
            res[s] = r
        res["mean_relWIS"] = float(np.mean([res[s]["relWIS"] for s in DEV_SEASONS]))
        out["variants"][v] = res
        print(v, json.dumps(res, indent=1, default=float))
    out["backfill_ratios"] = {r: gbqr.backfill_ratios(pd.Timestamp(r)) for r in refs}
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)


if __name__ == "__main__":
    main()
