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
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eakf import EAKF, EakfConfig
from forecast import emit_rows
from hub_data import load_locations, load_model_output, load_oracle, load_truth, nssp_ili_by_location
from seir_fast import FluParams
from wis import weighted_interval_score


def _stable_seed(*parts: object) -> int:
    """Deterministic cross-run seed (Python's built-in `hash()` is salted)."""
    h = hashlib.sha256(b"|".join(str(p).encode() for p in parts)).digest()
    return int.from_bytes(h[:4], "big") % 10_000


SEASONS = {
    "2023-24": ("2023-10-01", "2024-06-30"),
    "2024-25": ("2024-10-01", "2025-06-30"),
    "2025-26": ("2025-10-01", "2026-06-30"),
}
WARMUP_WEEKS = 8


def _q_lookup(ql: np.ndarray, qv: np.ndarray, lev: float) -> float:
    """Exact quantile lookup; np.interp fallback for non-standard grids."""
    idx = np.nonzero(np.isclose(ql, lev))[0]
    if len(idx):
        return float(qv[idx[0]])
    return float(np.interp(lev, ql, qv))


def season_origins(baseline: pd.DataFrame, season: str) -> np.ndarray:
    lo, hi = SEASONS[season]
    rd = baseline["reference_date"]
    return np.sort(baseline.loc[(rd >= lo) & (rd <= hi), "reference_date"].unique())


def run_location(
    loc: str,
    pop: float,
    truth_weeks: pd.Series,
    cfg: EakfConfig,
    origins: set[np.datetime64],
    season_start: str,
    season_end: str,
    run_rng_seed: int,
    ili_map: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """One filter run for a location within one season. Returns (rows, trace)."""
    p = FluParams(N_pop=pop)
    filt = EAKF(p, cfg)

    weeks = truth_weeks.sort_index()
    wk = weeks[
        (weeks.index >= pd.Timestamp(season_start) - pd.Timedelta(weeks=WARMUP_WEEKS)) & (weeks.index <= pd.Timestamp(season_end))
    ]

    rows: list[dict] = []
    trace: list[dict] = []
    for w_end, y in wk.items():
        ili = None
        if ili_map is not None:
            ili = ili_map.get(w_end.normalize().to_datetime64())
        diag = filt.step_week(None if pd.isna(y) else float(y), ili)
        ref = np.datetime64((w_end + pd.Timedelta(days=7)).date())
        if ref in origins:
            # Per-origin RNG: emission draws depend only on (loc, season,
            # origin), so batch and prospective single-origin runs emit
            # bit-identical rows for the same origin.
            emit_rng = np.random.default_rng(run_rng_seed + _stable_seed(loc, ref))
            recs = emit_rows(
                filt.X,
                p,
                location=str(loc),
                reference_date=ref,
                last_obs_week_value=(None if pd.isna(y) else float(y)),
                s_obs=cfg.s_obs,
                sd_beta_fwd=cfg.sd_beta_fwd,
                rng=emit_rng,
            )
            rows.extend(recs)
            trace.append(
                {
                    "location": loc,
                    "reference_date": str(ref),
                    "rt": filt.mean_rt(),
                    "hir": filt.mean_hir(),
                    "c": filt.mean_c(),
                    "chi2": (diag.get("adm") or {}).get("chi2"),
                }
            )
    return rows, trace


def summarize(rows: pd.DataFrame, oracle: pd.DataFrame, baseline: pd.DataFrame, label: str) -> tuple[dict, pd.DataFrame]:
    """Compute WIS per (loc, ref, horizon) for our rows and the baseline.

    Scoring follows FluSight practice: horizons 0..3 only. Horizon -1 rows
    (nowcast of the already-reported week) are emitted for calibration
    diagnostics but excluded from WIS/relWIS, matching the hub's policy.

    Returns (summary, cmp_tab). Summary statistics computed over finite
    paired (wis, wis_base) rows only; excluded/missing counts reported.
    """
    rows = rows[rows["horizon"] >= 0].copy()
    o = oracle[["location", "target_end_date", "oracle_value"]].drop_duplicates(["location", "target_end_date"])
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
            med = _q_lookup(ql, qv, 0.5)
            recs.append(
                {
                    "location": loc,
                    "reference_date": ref,
                    "horizon": h,
                    "observed": y,
                    "median": med,
                    "wis": wis,
                    "cov50": float(_q_lookup(ql, qv, 0.25) <= y <= _q_lookup(ql, qv, 0.75)),
                    "cov90": float(_q_lookup(ql, qv, 0.05) <= y <= _q_lookup(ql, qv, 0.95)),
                    "cov95": float(_q_lookup(ql, qv, 0.025) <= y <= _q_lookup(ql, qv, 0.975)),
                }
            )
        out = pd.DataFrame(recs)
        out["model"] = name
        return out

    ours = wis_table(rows, label)
    keys = ours[["location", "reference_date", "horizon"]].drop_duplicates()
    base_sub = baseline.merge(keys, on=["location", "reference_date", "horizon"], how="inner")
    base = wis_table(base_sub, "FluSight-baseline")

    cmp_tab = ours.merge(
        base[["location", "reference_date", "horizon", "wis"]].rename(columns={"wis": "wis_base"}),
        on=["location", "reference_date", "horizon"],
        how="inner",
    )

    # Filter for finite paired scores before computing statistics
    n_comparison_rows = len(cmp_tab)
    valid = cmp_tab[np.isfinite(cmp_tab["wis"]) & np.isfinite(cmp_tab["wis_base"])].copy()
    n_excluded = n_comparison_rows - len(valid)

    # All statistics over finite-paired rows only
    n_finite_ours = int(np.isfinite(ours["wis"]).sum()) if "wis" in ours.columns else 0
    n_finite_base = int(np.isfinite(base["wis"]).sum()) if "wis" in base.columns else 0

    summary = {
        "n_comparison_rows": n_comparison_rows,
        "n_finite_paired": len(valid),
        "n_excluded_nonfinite": n_excluded,
        "n_scored_ours": n_finite_ours,
        "n_scored_base": n_finite_base,
        "wis_mean": float(valid["wis"].mean()) if len(valid) > 0 else float("nan"),
        "wis_baseline_mean": float(valid["wis_base"].mean()) if len(valid) > 0 else float("nan"),
        "relWIS": (
            float(valid["wis"].mean() / valid["wis_base"].mean())
            if len(valid) > 0 and valid["wis_base"].mean() != 0
            else float("nan")
        ),
        "cov50": float(valid["cov50"].mean()) if len(valid) > 0 else float("nan"),
        "cov90": float(valid["cov90"].mean()) if len(valid) > 0 else float("nan"),
        "cov95": float(valid["cov95"].mean()) if len(valid) > 0 else float("nan"),
    }

    # Per-horizon stats: filter finite within each horizon group, compute relWIS inside
    by_hor_dict = {}
    for h in sorted(valid["horizon"].unique()):
        h_valid = valid[valid["horizon"] == h]
        mean_wis = h_valid["wis"].mean()
        mean_wis_base = h_valid["wis_base"].mean()
        relwis_h = float(mean_wis / mean_wis_base) if mean_wis_base != 0 else float("nan")
        by_hor_dict[int(h)] = {
            "wis": round(float(mean_wis), 4),
            "wis_base": round(float(mean_wis_base), 4),
            "relWIS": round(relwis_h, 4),
            "n": len(h_valid),
        }
    summary["by_horizon"] = by_hor_dict

    # Separate relWIS_by_horizon for backward compatibility (if needed by callers)
    summary["relWIS_by_horizon"] = {int(h): by_hor_dict[h]["relWIS"] for h in by_hor_dict}

    return summary, cmp_tab


def _run_job(job: dict) -> dict:
    """Worker: run one (season, location) filter + forecast job.

    Module-level so it is picklable for multiprocessing. Loads shared
    inputs from the module-level lru_cache-backed loaders (cheap under fork).
    """
    truth = load_truth()
    locs = load_locations().set_index("location")
    ili_all = nssp_ili_by_location()
    ili_maps = {
        location: dict(zip(sub["week_end"].values, sub["ili_frac"].values, strict=True))
        for location, sub in ili_all.groupby("location")
    }
    season, loc, a = job["season"], job["loc"], job["args"]
    if loc not in locs.index:
        return {"status": "skipped", "reason": "unknown location", "season": season, "loc": loc}
    pop = float(locs.loc[loc, "population"])
    tw = truth[truth["location"] == loc].set_index("date")["value"]
    if len(tw) < 30:
        return {"status": "skipped", "reason": "thin truth", "season": season, "loc": loc}
    origins = job.get("origins_override")
    if origins is None:
        origins = set(season_origins(load_model_output("FluSight-baseline"), season))
    cfg = EakfConfig(
        n_members=a["members"],
        sd_beta=a["sd_beta"],
        sd_hir=a["sd_hir"],
        r_rel=a["r_rel"],
        r_ili_rel=a["r_ili_rel"],
        sd_lc=a["sd_lc"],
        inflation=a["inflation"],
        s_obs=a["s_obs"],
        use_ili=not a["no_ili"],
        sd_beta_fwd=a["sd_beta_fwd"],
        seed=a["seed"],
    )
    rows, trace = run_location(
        loc,
        pop,
        tw,
        cfg,
        origins,
        SEASONS[season][0],
        SEASONS[season][1],
        ili_map=ili_maps.get(loc),
        run_rng_seed=a["seed"] + _stable_seed(loc, season),
    )
    return {"status": "ok", "season": season, "loc": loc, "rows": rows, "trace": trace}


def _season_of(ref: pd.Timestamp) -> str:
    for name, (lo, hi) in SEASONS.items():
        if pd.Timestamp(lo) <= ref <= pd.Timestamp(hi):
            return name
    raise ValueError(f"reference date {ref.date()} outside known seasons {list(SEASONS)}")


def prospective(ref_str: str, args) -> None:
    """Single-origin prospective run: emit hub-format forecasts for one
    reference_date R using truth through week R-7.

    Deterministic and identical to the batch run's rows at the same origin:
    same warmup, same seeds, same observation sequence.
    """
    ref = pd.Timestamp(ref_str)
    if ref.dayofweek != 5:
        raise SystemExit(f"--reference-date must be a Saturday (hub origin); got {ref.date()}")
    season = _season_of(ref)
    origins_override = {np.datetime64(ref.date())}
    job_args = {
        "members": args.members,
        "sd_beta": args.sd_beta,
        "sd_hir": args.sd_hir,
        "r_rel": args.r_rel,
        "r_ili_rel": args.r_ili_rel,
        "sd_lc": args.sd_lc,
        "inflation": args.inflation,
        "s_obs": args.s_obs,
        "sd_beta_fwd": args.sd_beta_fwd,
        "seed": args.seed,
        "no_ili": args.no_ili,
    }
    jobs = [
        {"season": season, "loc": location, "args": job_args, "origins_override": origins_override}
        for location in args.locations.split(",")
    ]
    if args.ncpus > 1:
        import multiprocessing as mp

        ctx = mp.get_context("fork")
        with ctx.Pool(processes=args.ncpus) as pool:
            results = pool.map(_run_job, jobs)
    else:
        results = [_run_job(j) for j in jobs]

    all_rows: list[pd.DataFrame] = []
    for r in results:
        if r.get("status") != "ok" or not r["rows"]:
            print(f"[warn] {r.get('loc')}: {r.get('reason', 'no rows')}")
            continue
        all_rows.append(pd.DataFrame(r["rows"]))
    if not all_rows:
        print("no forecasts produced")
        return
    rows = pd.concat(all_rows, ignore_index=True)
    out_path = os.path.join(args.out, f"rows-{args.label}-{ref.date()}.csv")
    rows.to_csv(out_path, index=False)
    print(f"wrote {len(rows)} rows for {rows['location'].nunique()} locations at origin {ref.date()} -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locations", default="US,06,12,36,48")
    ap.add_argument("--seasons", default="2024-25,2025-26")
    ap.add_argument(
        "--reference-date",
        default=None,
        help="prospective mode: single origin R (Saturday); emits forecasts using truth through week R-7, no scoring",
    )
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
    ap.add_argument("--ncpus", type=int, default=1, help="parallel workers over (season, location) jobs")
    ap.add_argument("--out", default="backtest/out/flu")
    ap.add_argument("--label", default="CyberEpi-EAKF")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    if args.reference_date:
        prospective(args.reference_date, args)
        return
    oracle = load_oracle()
    baseline = load_model_output("FluSight-baseline")
    baseline["output_type_id"] = baseline["output_type_id"].astype(float)

    job_args = {
        "members": args.members,
        "sd_beta": args.sd_beta,
        "sd_hir": args.sd_hir,
        "r_rel": args.r_rel,
        "r_ili_rel": args.r_ili_rel,
        "sd_lc": args.sd_lc,
        "inflation": args.inflation,
        "s_obs": args.s_obs,
        "sd_beta_fwd": args.sd_beta_fwd,
        "seed": args.seed,
        "no_ili": args.no_ili,
    }
    jobs = [
        {"season": season, "loc": location, "args": job_args}
        for season in args.seasons.split(",")
        for location in args.locations.split(",")
    ]
    if args.ncpus > 1:
        import multiprocessing as mp

        ctx = mp.get_context("fork")
        with ctx.Pool(processes=args.ncpus) as pool:
            results = pool.map(_run_job, jobs)
    else:
        results = [_run_job(j) for j in jobs]

    all_rows: list[pd.DataFrame] = []
    all_trace: list[pd.DataFrame] = []
    for r in results:
        if r.get("status") != "ok":
            print(f"[warn] {r.get('season')} {r.get('loc')}: {r.get('reason', r.get('status'))}")
            continue
        if not r["rows"]:
            continue
        rdf = pd.DataFrame(r["rows"])
        rdf["season"] = r["season"]
        all_rows.append(rdf)
        all_trace.append(pd.DataFrame(r["trace"]).assign(season=r["season"]))
        tdf = pd.DataFrame(r["trace"])
        print(f"{r['season']} {r['loc']}: origins={len(tdf)} rt_final={tdf.rt.iloc[-1]:.3f} hir_final={tdf.hir.iloc[-1]:.5f}")

    if not all_rows:
        print("no forecasts produced")
        return
    rows = pd.concat(all_rows, ignore_index=True)
    rows.to_csv(os.path.join(args.out, f"rows-{args.label}.csv"), index=False)
    pd.concat(all_trace, ignore_index=True).to_csv(os.path.join(args.out, f"trace-{args.label}.csv"), index=False)

    summaries = {}
    for season in args.seasons.split(","):
        rs = rows[rows["season"] == season]
        if rs.empty:
            continue
        summ, cmp_tab = summarize(rs, oracle, baseline, args.label)
        summaries[season] = summ
        cmp_tab.to_csv(os.path.join(args.out, f"cmp-{args.label}-{season}.csv"), index=False)
        print(
            f"== {season}: relWIS={summ['relWIS']:.3f} wis={summ['wis_mean']:.1f} "
            f"base={summ['wis_baseline_mean']:.1f} cov50={summ['cov50']:.2f} "
            f"cov90={summ['cov90']:.2f} (n={summ['n_scored_ours']})"
        )
    with open(os.path.join(args.out, f"summary-{args.label}.json"), "w") as f:
        json.dump(summaries, f, indent=2, default=str)


if __name__ == "__main__":
    main()
