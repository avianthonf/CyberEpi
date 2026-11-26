"""A2: model 1 structure diagnostics on dev seasons (2023-24, 2024-25), as-of admissions, ED final.

Arms (see docs/research/experiments/A2_model1_structure.md):
  U            unmodified (byte-identity vs results/dev_members checked for every reference date)
  D1           diagnostic from the U run: admissions innovation y - prior mean, by as-of phase
  D3_t6_hl{2,4,8}  forward log-beta reversion toward the trailing 6-week posterior mean
  D3_season_hl4    forward log-beta reversion toward the season-to-date posterior mean
  D2           ED intercept b = min ED value Jun-Sep before the season (final values; ED final-only)

Usage: python backtest/a2_structure.py --ncpus 8
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

from dev_members import DEV_SEASONS, EAKF, _as_of_growth, _load_cfg, _normalize, _phase  # noqa: E402
from hub_data import ed_frac_by_location, load_locations, load_model_output, load_oracle  # noqa: E402
from run_flusight import SEASONS, season_origins, summarize  # noqa: E402
from run_vintage import _run_job, load_vintages, vintage_index  # noqa: E402

ARMS = {
    "U": {},
    "D3_t6_hl2": {"beta_revert_hl_wk": 2.0, "beta_anchor": "trailing6"},
    "D3_t6_hl4": {"beta_revert_hl_wk": 4.0, "beta_anchor": "trailing6"},
    "D3_t6_hl8": {"beta_revert_hl_wk": 8.0, "beta_anchor": "trailing6"},
    "D3_season_hl4": {"beta_revert_hl_wk": 4.0, "beta_anchor": "season"},
    "D2": {"ed_intercept": "summer_min"},
}


def ed_baselines(season: str) -> dict[str, float]:
    """Per-location min ED fraction over Jun-Sep of the season's start year (final values)."""
    yr = int(season[:4])
    ed = ed_frac_by_location()
    w = ed[(ed["week_end"] >= f"{yr}-06-01") & (ed["week_end"] <= f"{yr}-09-30")]
    return w.groupby("location")["ili_frac"].min().to_dict()


def _identity(df: pd.DataFrame, out: str) -> tuple[int, list]:
    dm = os.path.join(HERE, "results", "dev_members")
    ident, diff = 0, []
    tmp = os.path.join(out, "_tmp.csv")
    for ref, g in df.groupby("reference_date"):
        g.to_csv(tmp, index=False)
        with open(os.path.join(dm, f"{ref}-{EAKF}.csv"), "rb") as f1, open(tmp, "rb") as f2:
            if f1.read() == f2.read():
                ident += 1
            else:
                diff.append(ref)
    os.remove(tmp)
    return ident, diff


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ncpus", type=int, default=8)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--max-refs", type=int, default=0, help="first N origins per season (identity smoke)")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "a2"))
    args = ap.parse_args()
    arms = args.arms.split(",")
    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()

    cfg = _load_cfg("model_config.json")
    base_args = {k: cfg[k] for k in ("members", "sd_beta", "sd_hir", "r_rel", "inflation", "s_obs",
                                     "sd_beta_fwd", "sd_lc", "r_ili_rel", "seed")}
    base_args["ili"] = "final"  # no ED vintages before Nov 2025: ED final-only

    baseline = load_model_output("FluSight-baseline")
    origins = {}
    for s in DEV_SEASONS:
        o = list(season_origins(baseline, s))
        origins[s] = o[: args.max_refs] if args.max_refs else o
    load_vintages()
    vintage_index()
    oracle = load_oracle()
    locs = load_locations()["location"].astype(str).tolist()
    bvals = {s: ed_baselines(s) for s in DEV_SEASONS}

    jobs = []
    for arm in arms:
        for s in DEV_SEASONS:
            for loc in locs:
                a = dict(base_args)
                a.update(ARMS[arm])
                if a.get("ed_intercept") == "summer_min":
                    a["ed_intercept"] = float(bvals[s].get(loc, 0.0))
                if arm == "U":
                    a["filter_trace"] = True  # trace only; forecast rows unaffected
                jobs.append({"season": s, "loc": loc, "args": a, "origins": origins[s], "arm": arm})
    t = time.time()
    with mp.get_context("fork").Pool(args.ncpus) as pool:
        res = pool.map(_run_job, jobs, chunksize=1)
    runtime = time.time() - t
    dfs = {}
    for arm in arms:
        fr = [pd.DataFrame(r["rows"]) for j, r in zip(jobs, res, strict=True)
              if j["arm"] == arm and r["status"] == "ok" and r["rows"]]
        dfs[arm] = _normalize(pd.concat(fr, ignore_index=True))
    for i, a1 in enumerate(arms):
        for a2 in arms[i + 1:]:
            if dfs[a1].equals(dfs[a2]):
                raise SystemExit(f"arms {a1} and {a2} produced identical rows: option not wired through")
    tr = pd.concat([pd.DataFrame(r["trace"]).assign(season=j["season"]) for j, r in zip(jobs, res, strict=True)
                    if j["arm"] == "U" and r["status"] == "ok"], ignore_index=True)
    skips = tr["skip_reason"].value_counts().to_dict() if "skip_reason" in tr else {}
    print(f"{len(arms)} arms in {runtime:.0f}s; skips {skips}")

    out: dict = {"runtime_s_all_arms": runtime, "n_arms": len(arms), "skips": skips,
                 "ed_baseline_b": {s: bvals[s] for s in DEV_SEASONS}, "seasons": {}}
    if "U" in dfs:
        ident, diff = _identity(dfs["U"], args.out)
        out["identical_refs"], out["differing_refs"] = ident, diff
        print(f"identity vs dev_members: {ident} identical, {len(diff)} differ {diff[:5]}")
    if args.max_refs:
        print("smoke run: stopping after identity check")
        return

    base = load_model_output("FluSight-baseline")
    base["output_type_id"] = base["output_type_id"].astype(float)
    tabs = {}
    for arm, df in dfs.items():
        df = df.assign(_rd=pd.to_datetime(df["reference_date"]))
        for s in DEV_SEASONS:
            lo, hi = SEASONS[s]
            sub = df[(df["_rd"] >= lo) & (df["_rd"] <= hi)].drop(columns="_rd")
            _, cmp = summarize(sub, oracle, base, arm)
            tabs[(arm, s)] = cmp

    phase_cache: dict = {}

    def phase(loc, r):
        if (loc, r) not in phase_cache:
            phase_cache[(loc, r)] = _phase(_as_of_growth(loc, pd.Timestamp(r)))
        return phase_cache[(loc, r)]

    for s in DEV_SEASONS:
        u = tabs[("U", s)]
        u = u[np.isfinite(u["wis"])].copy()
        u["phase"] = [phase(lo_, r) for lo_, r in zip(u["location"], u["reference_date"], strict=True)]
        u["le"] = np.log((u["median"] + 1) / (u["observed"] + 1))
        so: dict = {"arms": {}}
        bias_rows = []
        for arm in arms:
            v = tabs[(arm, s)]
            m = u.merge(v[["location", "reference_date", "horizon", "wis", "median", "cov50", "cov90"]],
                        on=["location", "reference_date", "horizon"], suffixes=("_u", "_v"))
            m = m[np.isfinite(m["wis_v"])]
            m["le_v"] = np.log((m["median_v"] + 1) / (m["observed"] + 1))
            per_h = {}
            for h, g in m.groupby("horizon"):
                per_h[int(h)] = {"rel_vs_U": float(g["wis_v"].mean() / g["wis_u"].mean()),
                                 "relWIS_base": float(g["wis_v"].mean() / g["wis_base"].mean()),
                                 "cov50": float(g["cov50_v"].mean()), "cov90": float(g["cov90_v"].mean()),
                                 "n": len(g)}
            ph = (m[m["phase"] != "unknown"].groupby(["phase", "horizon"])["le_v"].median())
            for (p_, h), val in ph.items():
                bias_rows.append({"arm": arm, "phase": p_, "horizon": int(h), "bias": float(val)})
            so["arms"][arm] = {"per_horizon": per_h, "rel_vs_U_all": float(m["wis_v"].mean() / m["wis_u"].mean()),
                               "relWIS_base_all": float(m["wis_v"].mean() / m["wis_base"].mean())}
        bias = pd.DataFrame(bias_rows)
        bias.to_csv(os.path.join(args.out, f"phase_bias_{s}.csv"), index=False)
        bt = bias.pivot_table(index=["phase", "horizon"], columns="arm", values="bias")
        # Pre-registered pass rule per arm on this fold.
        for arm in arms:
            if arm == "U":
                continue
            d_u, d_v = bt.loc[("declining", 3), "U"], bt.loc[("declining", 3), arm]
            decl = abs(d_v) <= (2 / 3) * abs(d_u) and np.sign(d_v) == np.sign(d_u)
            peak = all(abs(bt.loc[("peak", h), arm]) <= abs(bt.loc[("peak", h), "U"]) + 0.02 for h in range(4))
            so["arms"][arm]["pass"] = {"declining_cut": bool(decl), "no_peak_cost": bool(peak),
                                       "fold_pass": bool(decl and peak)}
        # D-1: admissions innovation at the last update before each origin, by phase.
        ts = tr[(tr["season"] == s) & tr["adm_y"].notna() & tr["adm_ybar"].notna()].copy()
        ts["phase"] = [phase(lo_, r) for lo_, r in zip(ts["location"], ts["reference_date"], strict=True)]
        ts["log_innov"] = np.log((ts["adm_y"] + 1) / (ts["adm_ybar"] + 1))
        d1 = (ts[ts["phase"] != "unknown"].groupby("phase")
              .agg(n=("log_innov", "size"), median_log_innov=("log_innov", "median"),
                   mean_log_innov=("log_innov", "mean"), share_positive=("log_innov", lambda x: float((x > 0).mean())),
                   median_abs=("log_innov", lambda x: float(x.abs().median())))
              .reset_index())
        d1.to_csv(os.path.join(args.out, f"d1_innovation_{s}.csv"), index=False)
        so["D1"] = d1.to_dict("records")
        so["bias_table"] = {f"{p_}|{h}": row.to_dict() for (p_, h), row in bt.iterrows()}
        out["seasons"][s] = so
        print(f"== {s}")
        print(bt.to_string(float_format=lambda x: f"{x:.3f}"))
        for arm in arms:
            a_ = so["arms"][arm]
            print(f"  {arm}: rel_vs_U " + " ".join(f"h{h}={d['rel_vs_U']:.3f}" for h, d in a_["per_horizon"].items())
                  + " | vsBase " + " ".join(f"{d['relWIS_base']:.3f}" for d in a_["per_horizon"].values())
                  + f" | {a_.get('pass', '')}")
        print(d1.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
