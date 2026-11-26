"""A3: lag-aware observation error in model 1, dev seasons, as-of replay.

Pre-registration: docs/research/experiments/A3_eakf_obs_error.md.

For each dev season s the lag-0 SD multiplier per location is m = max(1, 1/share), where
share = sum(lag-0 value seen at R) / sum(final value) over the weeks R-7 of the OTHER dev
season (leave-one-season-out). Runs model 1 twice per (season, location): unmodified
(multiplier 1) and variant, same seeds; checks the unmodified arm is byte-identical to
backtest/results/dev_members; scores h=0..3 vs FluSight-baseline and variant vs unmodified,
coverage, and median log error by as-of phase.

Usage: python backtest/a3_obs_error.py --ncpus 8
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
from hub_data import load_locations, load_model_output, load_oracle  # noqa: E402
from run_flusight import SEASONS, season_origins, summarize  # noqa: E402
from run_vintage import WEEK, _run_job, load_vintages, pick_vintage, series_at, vintage_index  # noqa: E402


def lag0_shares(origins: list, locs: list[str], oracle: pd.DataFrame) -> pd.DataFrame:
    """Volume-weighted lag-0 share per location over weeks R-7 of the given origins."""
    fin = oracle.drop_duplicates(["location", "target_end_date"]).set_index(
        ["location", "target_end_date"])["oracle_value"]
    recs = []
    for o in origins:
        ref = pd.Timestamp(o)
        pick = pick_vintage(ref)
        if pick is None:
            continue
        wk = ref - WEEK
        for loc in locs:
            s = series_at(pick[0], loc, wk)
            if s.empty or pd.isna(s.iloc[-1]) or (loc, wk) not in fin.index:
                continue
            recs.append((loc, float(s.iloc[-1]), float(fin[(loc, wk)])))
    d = pd.DataFrame(recs, columns=["location", "lag0", "final"])
    g = d.groupby("location").agg(lag0=("lag0", "sum"), final=("final", "sum"), n=("lag0", "size")).reset_index()
    g["share"] = np.where(g["final"] > 0, g["lag0"] / g["final"], 1.0)
    g["mult"] = np.maximum(1.0, 1.0 / g["share"].clip(lower=1e-9))
    return g


def _score(df: pd.DataFrame, oracle, base) -> tuple[dict, pd.DataFrame]:
    return summarize(df, oracle, base, "m1")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ncpus", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(HERE, "results", "a3"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()

    cfg = _load_cfg("model_config.json")
    base_args = {k: cfg[k] for k in ("members", "sd_beta", "sd_hir", "r_rel", "inflation", "s_obs",
                                     "sd_beta_fwd", "sd_lc", "r_ili_rel", "seed")}
    base_args["ili"] = "final"  # no ED vintages before Nov 2025: final values, labelled as such

    baseline = load_model_output("FluSight-baseline")
    origins = {s: list(season_origins(baseline, s)) for s in DEV_SEASONS}
    load_vintages()
    vintage_index()
    oracle = load_oracle()
    locs = load_locations()["location"].astype(str).tolist()

    shares = {s: lag0_shares(origins[s], locs, oracle) for s in DEV_SEASONS}
    mult = {}
    for s in DEV_SEASONS:
        other = next(x for x in DEV_SEASONS if x != s)
        sh = shares[other]
        mult[s] = dict(zip(sh["location"], sh["mult"], strict=True))
        sh.assign(estimated_on=other, applied_to=s).to_csv(os.path.join(args.out, f"lag0_share_for_{s}.csv"), index=False)
        us = sh[sh["location"] == "US"]
        print(f"share from {other} -> {s}: US share={us['share'].iloc[0]:.3f}; "
              f"mult median={sh['mult'].median():.3f} max={sh['mult'].max():.3f}")

    jobs = []
    for arm in ("unmodified", "variant"):
        for s in DEV_SEASONS:
            for loc in locs:
                a = dict(base_args)
                a["lag0_sd_mult"] = float(mult[s].get(loc, 1.0)) if arm == "variant" else 1.0
                jobs.append({"season": s, "loc": loc, "args": a, "origins": origins[s], "arm": arm})
    t = time.time()
    with mp.get_context("fork").Pool(args.ncpus) as pool:
        res = pool.map(_run_job, jobs, chunksize=1)
    runtime = time.time() - t
    dfs, traces = {}, []
    for arm in ("unmodified", "variant"):
        fr = [pd.DataFrame(r["rows"]) for j, r in zip(jobs, res, strict=True)
              if j["arm"] == arm and r["status"] == "ok" and r["rows"]]
        dfs[arm] = _normalize(pd.concat(fr, ignore_index=True))
    for j, r in zip(jobs, res, strict=True):
        if j["arm"] == "unmodified" and r["status"] == "ok":
            traces.append(pd.DataFrame(r["trace"]).assign(season=j["season"]))
    tr = pd.concat(traces, ignore_index=True)
    print(f"both arms in {runtime:.0f}s; stale-week counts {tr['stale_weeks'].value_counts().to_dict()}")

    # Bit-identity: unmodified arm vs dev_members files, every reference date.
    dm = os.path.join(HERE, "results", "dev_members")
    ident, diff = 0, []
    for ref, g in dfs["unmodified"].groupby("reference_date"):
        p = os.path.join(dm, f"{ref}-{EAKF}.csv")
        g.to_csv(os.path.join(args.out, "_tmp.csv"), index=False)
        with open(p, "rb") as f1, open(os.path.join(args.out, "_tmp.csv"), "rb") as f2:
            if f1.read() == f2.read():
                ident += 1
            else:
                diff.append(ref)
    os.remove(os.path.join(args.out, "_tmp.csv"))
    print(f"identity vs dev_members: {ident} identical, {len(diff)} differ {diff[:5]}")

    base = load_model_output("FluSight-baseline")
    base["output_type_id"] = base["output_type_id"].astype(float)
    out: dict = {"runtime_s_both_arms": runtime, "identical_refs": ident, "differing_refs": diff,
                 "shares": {s: shares[s].to_dict("records") for s in DEV_SEASONS}, "seasons": {}}
    tabs = {}
    for arm, df in dfs.items():
        df = df.assign(_rd=pd.to_datetime(df["reference_date"]))
        for s in DEV_SEASONS:
            lo, hi = SEASONS[s]
            sub = df[(df["_rd"] >= lo) & (df["_rd"] <= hi)].drop(columns="_rd")
            sc, cmp = _score(sub, oracle, base)
            tabs[(arm, s)] = cmp
            out["seasons"].setdefault(s, {})[arm] = {k: sc[k] for k in ("relWIS", "wis_mean", "n_finite_paired",
                                                                        "cov50", "cov90")}
    for s in DEV_SEASONS:
        u, v = tabs[("unmodified", s)], tabs[("variant", s)]
        m = u.merge(v, on=["location", "reference_date", "horizon"], suffixes=("_u", "_v"))
        m = m[np.isfinite(m["wis_u"]) & np.isfinite(m["wis_v"])]
        per_h = {}
        for h, g in m.groupby("horizon"):
            per_h[int(h)] = {
                "rel_vs_unmodified": float(g["wis_v"].mean() / g["wis_u"].mean()),
                "relWIS_base_unmodified": float(g["wis_u"].mean() / g["wis_base_u"].mean()),
                "relWIS_base_variant": float(g["wis_v"].mean() / g["wis_base_u"].mean()),
                "cov50_u": float(g["cov50_u"].mean()), "cov50_v": float(g["cov50_v"].mean()),
                "cov90_u": float(g["cov90_u"].mean()), "cov90_v": float(g["cov90_v"].mean()),
                "n": len(g)}
        out["seasons"][s]["per_horizon"] = per_h
        out["seasons"][s]["rel_vs_unmodified_all"] = float(m["wis_v"].mean() / m["wis_u"].mean())
        # phase bias
        g = {(loc, r): _phase(_as_of_growth(loc, r)) for loc, r in
             m[["location", "reference_date"]].drop_duplicates().itertuples(index=False)}
        m["phase"] = [g[(lo_, r)] for lo_, r in zip(m["location"], m["reference_date"], strict=True)]
        for arm, sfx in (("unmodified", "_u"), ("variant", "_v")):
            m["le" + sfx] = np.log((m["median" + sfx] + 1) / (m["observed_u"] + 1))
        ph = (m[m["phase"] != "unknown"].groupby(["phase", "horizon"])
              .agg(le_unmodified=("le_u", "median"), le_variant=("le_v", "median"), n=("le_u", "size"))
              .reset_index())
        ph.to_csv(os.path.join(args.out, f"phase_bias_{s}.csv"), index=False)
        out["seasons"][s]["phase_bias"] = ph.to_dict("records")
        print(f"== {s}")
        for h, d in per_h.items():
            print(f"  h={h}: var/unmod={d['rel_vs_unmodified']:.4f} vsBase unmod={d['relWIS_base_unmodified']:.3f} "
                  f"var={d['relWIS_base_variant']:.3f} cov50 {d['cov50_u']:.2f}->{d['cov50_v']:.2f} "
                  f"cov90 {d['cov90_u']:.2f}->{d['cov90_v']:.2f} n={d['n']}")
        print(ph.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
