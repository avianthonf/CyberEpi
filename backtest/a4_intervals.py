"""A4: NegBin count-aware intervals on dev-season forecasts (post-processing only).

See docs/research/experiments/A4_negbin_intervals.md. Reads results/dev_members (never changed);
NB dispersion pooled across locations with shrinkage, fitted LOSO on the other dev season.

Usage: python backtest/a4_intervals.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from scipy.stats import nbinom

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dev_members import DEV_SEASONS, EAKF, GBQR, MIX  # noqa: E402
from hub_data import load_model_output, load_oracle  # noqa: E402
from run_flusight import summarize  # noqa: E402

MODELS = [EAKF, GBQR, MIX]
K_SHRINK = 50.0
PHI_GRID = np.logspace(-3, 1, 201)
MU_FLOOR = 0.5
SMALL = 10.0


def season_of(ref: str) -> str:
    return "2023-24" if ref < "2024-08-01" else "2024-25"


def load_model(model: str) -> pd.DataFrame:
    fs = sorted(glob.glob(os.path.join(HERE, "results", "dev_members", f"*-{model}.csv")))
    df = pd.concat([pd.read_csv(f, dtype={"location": str}) for f in fs], ignore_index=True)
    df["season"] = df["reference_date"].map(season_of)
    return df


def nb_params(mu: np.ndarray, phi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = 1.0 / phi
    return n, n / (n + mu)


def fit_phi(mu: np.ndarray, y: np.ndarray) -> float:
    ll = [nbinom.logpmf(y, *nb_params(mu, np.full_like(mu, p))).sum() for p in PHI_GRID]
    return float(PHI_GRID[int(np.argmax(ll))])


def centres(df: pd.DataFrame, oracle: pd.DataFrame) -> pd.DataFrame:
    m = df[(df["horizon"] >= 0) & np.isclose(df["output_type_id"].astype(float), 0.5)]
    m = m[["season", "reference_date", "location", "horizon", "target_end_date", "value"]]
    o = oracle[["location", "target_end_date", "oracle_value"]].drop_duplicates(["location", "target_end_date"])
    o = o.assign(target_end_date=o["target_end_date"].dt.strftime("%Y-%m-%d"))
    return m.merge(o, on=["location", "target_end_date"], how="inner").dropna(subset=["value", "oracle_value"])


def fit_dispersion(c: pd.DataFrame) -> tuple[float, dict]:
    mu = np.maximum(c["value"].to_numpy(float), MU_FLOOR)
    y = np.round(c["oracle_value"].to_numpy(float)).astype(int)
    pool = fit_phi(mu, y)
    out = {}
    for loc, g in c.groupby("location"):
        gm = np.maximum(g["value"].to_numpy(float), MU_FLOOR)
        gy = np.round(g["oracle_value"].to_numpy(float)).astype(int)
        n = len(g)
        out[loc] = (n * fit_phi(gm, gy) + K_SHRINK * pool) / (n + K_SHRINK)
    return pool, out


def recalibrate(df: pd.DataFrame, phis: dict, pool: float) -> pd.DataFrame:
    df = df.copy()
    med = df[np.isclose(df["output_type_id"].astype(float), 0.5)].set_index(
        ["reference_date", "location", "horizon"])["value"]
    key = pd.MultiIndex.from_frame(df[["reference_date", "location", "horizon"]])
    m = med.reindex(key).to_numpy(float)
    mu = np.maximum(m, MU_FLOOR)
    phi = df["location"].map(phis).fillna(pool).to_numpy(float)
    q = nbinom.ppf(df["output_type_id"].astype(float).to_numpy(), *nb_params(mu, phi))
    is_med = np.isclose(df["output_type_id"].astype(float), 0.5)
    q = np.where(is_med, m, q)
    df["value"] = q
    df = df.sort_values(["reference_date", "location", "horizon", "output_type_id"])
    df["value"] = df.groupby(["reference_date", "location", "horizon"])["value"].cummax()
    return df


def cov_table(cmp: pd.DataFrame, small: set) -> dict:
    s = cmp["location"].isin(small)
    out = {}
    for name, sub in (("all", cmp), ("small", cmp[s]), ("large", cmp[~s]),
                      ("obs_lt10_rows", cmp[cmp["observed"] < SMALL])):
        out[name] = {"cov50": round(float(sub["cov50"].mean()), 4), "cov90": round(float(sub["cov90"].mean()), 4),
                     "n": int(len(sub))}
    return out


def main() -> None:
    t0 = time.time()
    out_dir = os.path.join(HERE, "results", "a4")
    os.makedirs(out_dir, exist_ok=True)
    oracle = load_oracle()
    base = load_model_output("FluSight-baseline")
    truth_o = oracle[["location", "target_end_date", "oracle_value"]].drop_duplicates(["location", "target_end_date"])
    res: dict = {"k_shrink": K_SHRINK, "mu_floor": MU_FLOOR}
    data = {m: load_model(m) for m in MODELS}
    # One small-count set per fold, shared by all models: truth median over the scored (h>=0)
    # target window of the fold, union of all three models' rows.
    smalls = {}
    for test in DEV_SEASONS:
        ted = pd.concat([d.loc[(d["season"] == test) & (d["horizon"] >= 0), "target_end_date"] for d in data.values()])
        tt = truth_o[(truth_o["target_end_date"] >= ted.min()) & (truth_o["target_end_date"] <= ted.max())]
        smalls[test] = set(tt.groupby("location")["oracle_value"].median().loc[lambda s: s < SMALL].index)
        res[f"small_locs_{test}"] = sorted(smalls[test])
    for model in MODELS:
        df = data[model]
        c = centres(df, oracle)
        res[model] = {}
        for test in DEV_SEASONS:
            train = [s for s in DEV_SEASONS if s != test][0]
            pool, phis = fit_dispersion(c[c["season"] == train])
            te = df[df["season"] == test].drop(columns="season")
            small = smalls[test]
            nb = recalibrate(te, phis, pool)
            # Post-hoc arm (not the decision): NB only for locations small in the training season (no look-ahead).
            gate = smalls[train]
            nbs = pd.concat([te[~te["location"].isin(gate)], nb[nb["location"].isin(gate)]], ignore_index=True)
            r = {"train": train, "phi_pool": pool, "phi_shrunk_median": float(np.median(list(phis.values()))),
                 "n_small_locs": len(small), "nb_small_gate": sorted(gate)}
            cmps = {}
            for arm, d in (("U", te), ("NB", nb), ("NB_small", nbs)):
                summ, cmp = summarize(d, oracle, base, arm)
                cmps[arm] = cmp
                r[arm] = {"relWIS_base": round(summ["relWIS"], 4), "relWIS_base_h": summ["relWIS_by_horizon"],
                          "wis": round(summ["wis_mean"], 3), "cov": cov_table(cmp, small)}
                summ_wis = {h: v["wis"] for h, v in summ["by_horizon"].items()}
                r[arm]["wis_h"] = summ_wis
            r["relWIS_vs_U"] = round(r["NB"]["wis"] / r["U"]["wis"], 4)
            r["relWIS_vs_U_h"] = {h: round(r["NB"]["wis_h"][h] / r["U"]["wis_h"][h], 4) for h in r["U"]["wis_h"]}
            r["NB_small_relWIS_vs_U"] = round(r["NB_small"]["wis"] / r["U"]["wis"], 4)
            r["NB_small_relWIS_vs_U_h"] = {h: round(r["NB_small"]["wis_h"][h] / r["U"]["wis_h"][h], 4)
                                           for h in r["U"]["wis_h"]}
            r["gate_cov"] = {a: cov_table(cmps[a], gate)["small"] for a in ("U", "NB_small")}
            for strat in ("small", "large"):
                s = cmps["U"]["location"].isin(small) if strat == "small" else ~cmps["U"]["location"].isin(small)
                sn = cmps["NB"]["location"].isin(small) if strat == "small" else ~cmps["NB"]["location"].isin(small)
                r[f"relWIS_vs_U_{strat}"] = round(float(cmps["NB"][sn]["wis"].mean() / cmps["U"][s]["wis"].mean()), 4)
            cu, cn = r["U"]["cov"]["small"], r["NB"]["cov"]["small"]
            r["pass_cov"] = bool(abs(cn["cov50"] - .5) < abs(cu["cov50"] - .5) and abs(cn["cov90"] - .9) < abs(cu["cov90"] - .9))
            r["pass_wis"] = bool(r["relWIS_vs_U"] <= 1.0)
            r["pass_fold"] = r["pass_cov"] and r["pass_wis"]
            res[model][test] = r
            print(model, test, json.dumps({k: r[k] for k in ("phi_pool", "relWIS_vs_U", "pass_cov", "pass_wis")}),
                  r["U"]["cov"]["small"], r["NB"]["cov"]["small"], flush=True)
        res[model]["pass"] = all(res[model][s]["pass_fold"] for s in DEV_SEASONS)
    res["runtime_s"] = round(time.time() - t0, 1)
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("runtime", res["runtime_s"])


if __name__ == "__main__":
    main()
