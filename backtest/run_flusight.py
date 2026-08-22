"""FluSight backtest driver.

Per season, per location: restart the filter with priors, process weekly
admission truth (7-day reporting lag), and at each hub origin (reference_date
where FluSight-baseline submitted) emit quantile forecasts in hubverse format.

Score afterwards vs oracle truth; relWIS computed against FluSight-baseline
on shared (location, reference_date, horizon) keys.

Timestamps: truth 'date' is the Saturday week end. At origin R (Saturday),
observations through week ending R-7 are available; when our loop just
processed truth week w, if w+7 is an origin we emit forecasts for that origin.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eakf import EAKF, EakfConfig
from forecast import emit_rows
from hub_data import (load_locations, load_model_output, load_oracle,
                      load_truth, nssp_ili_by_location)
from seir_fast import FluParams
from wis import weighted_interval_score

SEASONS = {
    "2023-24": ("2023-10-01", "2024-06-30"),
    "2024-25": ("2024-10-01", "2025-06-30"),
    "2025-26": ("2025-10-01", "2026-06-30"),
}
WARMUP_WEEKS = 8


def season_origins(baseline: pd.DataFrame, season: str) -> np.ndarray:
    lo, hi = SEASONS[season]
    rd = baseline["reference_date"]
    return np.sort(baseline.loc[(rd >= lo) & (rd <= hi), "reference_date"].unique())


def run_location(
    loc: str, pop: float, truth_weeks: pd.Series, cfg: EakfConfig,
    origins: set[np.datetime64], season_start: str, season_end: str,
    run_rng_seed: int, ili_map: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """One filter run for a location within one season. Returns (rows, trace)."""
    p = FluParams(N_pop=pop)
    filt = EAKF(p, cfg)
    rng = np.random.default_rng(run_rng_seed)

    weeks = truth_weeks.sort_index()
    wk = weeks[(weeks.index >= pd.Timestamp(season_start) - pd.Timedelta(weeks=WARMUP_WEEKS))
               & (weeks.index <= pd.Timestamp(season_end))]

    rows: list[dict] = []
    trace: list[dict] = []
    for w_end, y in wk.items():
        ili = None
        if ili_map is not None:
            ili = ili_map.get(w_end.normalize().to_datetime64())
        diag = filt.step_week(None if pd.isna(y) else float(y), ili)
        ref = np.datetime64((w_end + pd.Timedelta(days=7)).date())
        if ref in origins:
            recs = emit_rows(
                filt.X, p, location=str(loc), reference_date=ref,
                last_obs_week_value=(None if pd.isna(y) else float(y)),
                s_obs=cfg.s_obs, sd_beta_fwd=cfg.sd_beta_fwd, rng=rng,
            )
            rows.extend(recs)
            trace.append({
                "location": loc, "reference_date": str(ref),
                "rt": filt.mean_rt(), "hir": filt.mean_hir(),
                "c": filt.mean_c(),
                "chi2": (diag.get("adm") or {}).get("chi2"),
            })
    return rows, trace


def summarize(rows: pd.DataFrame, oracle: pd.DataFrame,
              baseline: pd.DataFrame, label: str) -> dict:
    """Compute WIS per (loc, ref, horizon) for our rows and the baseline."""
    o = (oracle[["location", "target_end_date", "oracle_value"]]
         .drop_duplicates(["location", "target_end_date"]))
    rows = rows.copy()
    rows["reference_date"] = pd.to_datetime(rows["reference_date"], errors="coerce")
    baseline = baseline.copy()
    baseline["reference_date"] = pd.to_datetime(baseline["reference_date"], errors="coerce")
    rows["target_end_date"] = pd.to_datetime(rows["target_end_date"], errors="coerce")

    def wis_table(df: pd.DataFrame, name: str) -> pd.DataFrame:
        d = df.merge(o, on=["location", "target_end_date"], how="inner")
        recs = []
        for (loc, ref, h), g in d.groupby(["location", "reference_date", "horizon"]):
            g = g.sort_values("output_type_id")
            ql = g["output_type_id"].to_numpy(float)
            qv = g["value"].to_numpy(float)
            y = float(g["oracle_value"].iloc[0])
            wis = float(weighted_interval_score(ql, qv, y))
            med = np.interp(0.5, ql, qv)
            recs.append({"location": loc, "reference_date": ref, "horizon": h,
                         "observed": y, "median": med, "wis": wis,
                         "cov50": float(np.interp(0.25, ql, qv) <= y <= np.interp(0.75, ql, qv)),
                         "cov90": float(np.interp(0.05, ql, qv) <= y <= np.interp(0.95, ql, qv)),
                         "cov95": float(np.interp(0.025, ql, qv) <= y <= np.interp(0.975, ql, qv))})
        out = pd.DataFrame(recs)
        out["model"] = name
        return out

    ours = wis_table(rows, label)
    keys = ours[["location", "reference_date", "horizon"]].drop_duplicates()
    base_sub = baseline.merge(keys, on=["location", "reference_date", "horizon"], how="inner")
    base = wis_table(base_sub, "FluSight-baseline")

    cmp_tab = ours.merge(
        base[["location", "reference_date", "horizon", "wis"]].rename(columns={"wis": "wis_base"}),
        on=["location", "reference_date", "horizon"], how="inner")

    summary = {
        "n_scored_ours": len(ours), "n_scored_base": len(base),
        "wis_mean": float(cmp_tab["wis"].mean()),
        "wis_baseline_mean": float(cmp_tab["wis_base"].mean()),
        "relWIS": float(cmp_tab["wis"].mean() / cmp_tab["wis_base"].mean()),
        "cov50": float(cmp_tab["cov50"].mean()),
        "cov90": float(cmp_tab["cov90"].mean()),
        "cov95": float(cmp_tab["cov95"].mean()),
        "by_horizon": cmp_tab.groupby("horizon").agg(
            wis=("wis", "mean"), wis_base=("wis_base", "mean"),
            relWIS=("wis", "mean"), n=("wis", "size")).round(4).to_dict("index"),
    }
    bh = cmp_tab.groupby("horizon").apply(
        lambda g: g["wis"].mean() / g["wis_base"].mean(), include_groups=False)
    summary["relWIS_by_horizon"] = {int(k): float(v) for k, v in bh.round(4).items()}
    return summary, cmp_tab


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locations", default="US,06,12,36,48")
    ap.add_argument("--seasons", default="2024-25,2025-26")
    ap.add_argument("--members", type=int, default=300)
    ap.add_argument("--sd-beta", type=float, default=0.05)
    ap.add_argument("--sd-hir", type=float, default=0.005)
    ap.add_argument("--r-rel", type=float, default=0.15)
    ap.add_argument("--inflation", type=float, default=1.03)
    ap.add_argument("--s-obs", type=float, default=0.10)
    ap.add_argument("--sd-beta-fwd", type=float, default=0.05)
    ap.add_argument("--sd-lc", type=float, default=0.01)
    ap.add_argument("--r-ili-rel", type=float, default=0.10)
    ap.add_argument("--no-ili", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="backtest/out/flu")
    ap.add_argument("--label", default="CyberEpi-EAKF")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    truth = load_truth()
    oracle = load_oracle()
    baseline = load_model_output("FluSight-baseline")
    baseline["output_type_id"] = baseline["output_type_id"].astype(float)
    locs = load_locations().set_index("location")

    all_rows: list[pd.DataFrame] = []
    all_trace: list[pd.DataFrame] = []
    summaries = {}
    ili_all = nssp_ili_by_location()
    ili_maps = {loc: dict(zip(sub["week_end"].values, sub["ili_frac"].values))
                for loc, sub in ili_all.groupby("location")}
    for season in args.seasons.split(","):
        origins = set(season_origins(baseline, season))
        for loc in args.locations.split(","):
            if loc not in locs.index:
                print(f"[warn] unknown location {loc}; skipped"); continue
            pop = float(locs.loc[loc, "population"])
            tw = truth[truth["location"] == loc].set_index("date")["value"]
            if len(tw) < 30:
                print(f"[warn] thin truth for {loc}; skipped"); continue
            cfg = EakfConfig(n_members=args.members, sd_beta=args.sd_beta,
                             sd_hir=args.sd_hir, r_rel=args.r_rel,
                             r_ili_rel=args.r_ili_rel, sd_lc=args.sd_lc,
                             inflation=args.inflation, s_obs=args.s_obs,
                             use_ili=not args.no_ili,
                             sd_beta_fwd=args.sd_beta_fwd, seed=args.seed)
            rows, trace = run_location(loc, pop, tw, cfg, origins,
                                       SEASONS[season][0], SEASONS[season][1],
                                       ili_map=ili_maps.get(loc),
                                       run_rng_seed=args.seed + hash((loc, season)) % 10_000)
            if not rows:
                continue
            rdf = pd.DataFrame(rows)
            rdf["season"] = season
            all_rows.append(rdf); all_trace.append(pd.DataFrame(trace).assign(season=season))
            tdf = pd.DataFrame(trace)
            print(f"{season} {loc}: origins={len(tdf)} "
                  f"rt_final={tdf.rt.iloc[-1]:.3f} hir_final={tdf.hir.iloc[-1]:.5f}")

    if not all_rows:
        print("no forecasts produced"); return
    rows = pd.concat(all_rows, ignore_index=True)
    rows.to_csv(os.path.join(args.out, f"rows-{args.label}.csv"), index=False)
    pd.concat(all_trace, ignore_index=True).to_csv(
        os.path.join(args.out, f"trace-{args.label}.csv"), index=False)

    for season in args.seasons.split(","):
        rs = rows[rows["season"] == season]
        summ, cmp_tab = summarize(rs, oracle, baseline, args.label)
        summaries[season] = summ
        cmp_tab.to_csv(os.path.join(args.out, f"cmp-{args.label}-{season}.csv"), index=False)
        print(f"== {season}: relWIS={summ['relWIS']:.3f} wis={summ['wis_mean']:.1f} "
              f"base={summ['wis_baseline_mean']:.1f} cov50={summ['cov50']:.2f} "
              f"cov90={summ['cov90']:.2f} (n={summ['n_scored_ours']})")
    with open(os.path.join(args.out, f"summary-{args.label}.json"), "w") as f:
        json.dump(summaries, f, indent=2, default=str)


if __name__ == "__main__":
    main()
