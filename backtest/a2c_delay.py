"""A2c: consistent admission-delay observation operator in model 1, dev seasons (2023-24, 2024-25).

Arms (see docs/research/experiments/A2c_delay_consistent.md):
  U            unmodified (byte-identity vs results/dev_members checked for every reference date)
  DELAY        A2b forward-only Erlang-2 delay, mean 6 d (reference)
  CONS6        consistent filter observation + forward emission, mean 6 d (primary)
  CONS4, CONS8 same at mean 4 d and 8 d (sensitivity; reported, do not affect the verdict)

Verdict: CONS6 passes only if, on each fold, (1) declining h3 bias cut by >= 1/3 with the same sign,
(2) peak |bias| <= U + 0.02 for h0-3, (3) relWIS vs U <= 1.00 at every horizon, (4) mean cov90 over h0-3
>= U - 0.03.

Usage: python backtest/a2c_delay.py --ncpus 8
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

from a2_structure import _identity  # noqa: E402
from dev_members import DEV_SEASONS, _as_of_growth, _load_cfg, _normalize, _phase  # noqa: E402
from hub_data import load_locations, load_model_output, load_oracle  # noqa: E402
from run_flusight import SEASONS, season_origins, summarize  # noqa: E402
from run_vintage import _run_job, load_vintages, vintage_index  # noqa: E402

ARMS = {
    "U": {},
    "DELAY": {"delay_mean_days": 6.0},
    "CONS6": {"delay_mean_days": 6.0, "delay_consistent": True},
    "CONS4": {"delay_mean_days": 4.0, "delay_consistent": True},
    "CONS8": {"delay_mean_days": 8.0, "delay_consistent": True},
}
PRIMARY = "CONS6"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ncpus", type=int, default=8)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--max-refs", type=int, default=0, help="first N origins per season (identity smoke)")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "a2c"))
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

    jobs = []
    for arm in arms:
        for s in DEV_SEASONS:
            for loc in locs:
                a = dict(base_args)
                a.update(ARMS[arm])
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
    print(f"{len(arms)} arms in {runtime:.0f}s")

    out: dict = {"runtime_s_all_arms": runtime, "n_arms": len(arms), "seasons": {}}
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
            ph = m[m["phase"] != "unknown"].groupby(["phase", "horizon"])["le_v"].median()
            for (p_, h), val in ph.items():
                bias_rows.append({"arm": arm, "phase": p_, "horizon": int(h), "bias": float(val)})
            so["arms"][arm] = {"per_horizon": per_h, "rel_vs_U_all": float(m["wis_v"].mean() / m["wis_u"].mean()),
                               "relWIS_base_all": float(m["wis_v"].mean() / m["wis_base"].mean())}
        bias = pd.DataFrame(bias_rows)
        bias.to_csv(os.path.join(args.out, f"phase_bias_{s}.csv"), index=False)
        bt = bias.pivot_table(index=["phase", "horizon"], columns="arm", values="bias")
        cov_u = np.mean([so["arms"]["U"]["per_horizon"][h]["cov90"] for h in range(4)])
        # Pre-registered pass rule per arm on this fold.
        for arm in arms:
            if arm == "U":
                continue
            d_u, d_v = bt.loc[("declining", 3), "U"], bt.loc[("declining", 3), arm]
            decl = abs(d_v) <= (2 / 3) * abs(d_u) and np.sign(d_v) == np.sign(d_u)
            peak = all(abs(bt.loc[("peak", h), arm]) <= abs(bt.loc[("peak", h), "U"]) + 0.02 for h in range(4))
            rel = all(so["arms"][arm]["per_horizon"][h]["rel_vs_U"] <= 1.0 for h in range(4))
            cov_v = np.mean([so["arms"][arm]["per_horizon"][h]["cov90"] for h in range(4)])
            cov = bool(cov_v >= cov_u - 0.03)
            so["arms"][arm]["pass"] = {"declining_cut": bool(decl), "no_peak_cost": bool(peak),
                                       "relWIS_le_U": bool(rel), "cov90_ok": cov,
                                       "fold_pass": bool(decl and peak and rel and cov)}
        so["bias_table"] = {f"{p_}|{h}": row.to_dict() for (p_, h), row in bt.iterrows()}
        out["seasons"][s] = so
        print(f"== {s}")
        print(bt.to_string(float_format=lambda x: f"{x:.3f}"))
        for arm in arms:
            a_ = so["arms"][arm]
            print(f"  {arm}: rel_vs_U " + " ".join(f"h{h}={d['rel_vs_U']:.3f}" for h, d in a_["per_horizon"].items())
                  + " | vsBase " + " ".join(f"{d['relWIS_base']:.3f}" for d in a_["per_horizon"].values())
                  + " | cov50/90 " + " ".join(f"{d['cov50']:.2f}/{d['cov90']:.2f}" for d in a_["per_horizon"].values())
                  + f" | {a_.get('pass', '')}")
    if PRIMARY in arms:
        out["verdict_primary"] = "PASS" if all(out["seasons"][s]["arms"][PRIMARY]["pass"]["fold_pass"]
                                               for s in DEV_SEASONS) else "FAIL"
        print(f"VERDICT {PRIMARY}: {out['verdict_primary']}")
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
