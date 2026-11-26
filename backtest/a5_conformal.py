"""A5: horizon-wise conformalized quantile adjustment (log1p) on dev-season forecasts.

See docs/research/experiments/A5_conformal.md. Reads results/dev_members (never changed).
Two calibration windows: (a) prior-season residuals (LOSO), (b) rolling in-season window
of the last W origins whose truth was published before the reference date, with a
prior-season warm start. Writes results/a5/summary.json.

Usage: python backtest/a5_conformal.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from a4_intervals import load_model  # noqa: E402
from dev_members import DEV_SEASONS, EAKF, GBQR, MIX  # noqa: E402
from hub_data import load_model_output, load_oracle  # noqa: E402
from run_flusight import summarize  # noqa: E402

MODELS = [EAKF, GBQR, MIX]
W = 8  # rolling window, origins (pre-registered)
HORIZONS = [0, 1, 2, 3]
KEYS = ["reference_date", "location", "horizon", "target_end_date"]
WEEK = pd.Timedelta(days=7)


def wide(df: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """One row per forecast (h>=0) with log1p quantiles as columns, truth z_y, and CQR scores."""
    d = df[df["horizon"] >= 0].copy()
    d["tau"] = d["output_type_id"].astype(float).round(4)
    w = d.pivot_table(index=KEYS, columns="tau", values="value", aggfunc="first").reset_index()
    w = w.merge(truth, on=["location", "target_end_date"], how="inner").dropna(subset=["oracle_value"])
    zy = np.log1p(w["oracle_value"].to_numpy(float))
    lq = {t: np.log1p(w[t].to_numpy(float)) for t in (0.05, 0.25, 0.75, 0.95)}
    w["E50"] = np.maximum(lq[0.25] - zy, zy - lq[0.75])
    w["E90"] = np.maximum(lq[0.05] - zy, zy - lq[0.95])
    w["ref"] = pd.to_datetime(w["reference_date"])
    w["ted"] = pd.to_datetime(w["target_end_date"])
    return w


def cqr_q(scores: np.ndarray, alpha: float) -> float:
    n = len(scores)
    if n == 0:
        return 0.0
    k = min(int(np.ceil((n + 1) * (1 - alpha))), n)
    return float(np.sort(scores)[k - 1])


def qpair(cal: pd.DataFrame) -> tuple[float, float]:
    return cqr_q(cal["E50"].to_numpy(), 0.5), cqr_q(cal["E90"].to_numpy(), 0.10)


def adjust(df: pd.DataFrame, qs: pd.DataFrame) -> pd.DataFrame:
    """Shift each quantile level outward on log1p by an amount interpolated from (Q50, Q90).

    qs has columns reference_date, horizon, Q50, Q90. Rows without a Q (horizon -1) are unchanged.
    """
    out = df.merge(qs, on=["reference_date", "horizon"], how="left")
    tau = out["output_type_id"].astype(float).to_numpy()
    dist = np.abs(tau - 0.5)
    q50, q90 = out["Q50"].to_numpy(float), out["Q90"].to_numpy(float)
    has = np.isfinite(q50)
    # piecewise linear in |tau-0.5|: 0 -> 0, 0.25 -> Q50, >=0.45 -> Q90
    shift = np.where(dist <= 0.25, dist / 0.25 * q50, q50 + (np.minimum(dist, 0.45) - 0.25) / 0.20 * (q90 - q50))
    shift = np.where(has, shift * np.sign(tau - 0.5), 0.0)
    z = np.log1p(out["value"].to_numpy(float)) + shift
    v = np.where(has, np.maximum(np.round(np.expm1(z)), 0), out["value"].to_numpy(float))
    out["value"] = v
    out = out.drop(columns=["Q50", "Q90"]).sort_values(["reference_date", "location", "horizon", "output_type_id"])
    out["tau"] = out["output_type_id"].astype(float)
    out = out.sort_values(["reference_date", "location", "horizon", "tau"])
    out["value"] = out.groupby(["reference_date", "location", "horizon"])["value"].cummax()
    return out.drop(columns="tau")


def window_a(test_w: pd.DataFrame, train_w: pd.DataFrame) -> pd.DataFrame:
    recs = []
    for h in HORIZONS:
        q50, q90 = qpair(train_w[train_w["horizon"] == h])
        for r in test_w["reference_date"].unique():
            recs.append({"reference_date": r, "horizon": h, "Q50": q50, "Q90": q90})
    return pd.DataFrame(recs)


def window_b(test_w: pd.DataFrame, train_w: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    t_orig = sorted(test_w["ref"].unique())
    s_orig = sorted(train_w["ref"].unique())
    recs, warm_share = [], []
    for i, r in enumerate(t_orig):
        for h in HORIZONS:
            th = test_w[test_w["horizon"] == h]
            ins = th[(th["ref"] < r) & (th["ref"] >= r - W * WEEK) & (th["ted"] <= r - WEEK)]
            k = ins["ref"].nunique()
            need = W - k
            cal = ins
            if need > 0:
                start = max(0, i - need)
                block = s_orig[start:start + need]
                sh = train_w[(train_w["horizon"] == h) & train_w["ref"].isin(block)]
                cal = pd.concat([ins, sh], ignore_index=True)
            warm_share.append(need / W)
            q50, q90 = qpair(cal)
            recs.append({"reference_date": pd.Timestamp(r).strftime("%Y-%m-%d"), "horizon": h, "Q50": q50, "Q90": q90})
    return pd.DataFrame(recs), {"mean_warm_share": round(float(np.mean(warm_share)), 4)}


def score(d: pd.DataFrame, oracle: pd.DataFrame, base: pd.DataFrame, label: str) -> dict:
    s, _ = summarize(d, oracle, base, label)
    return {"wis": s["wis_mean"], "wis_h": {h: v["wis"] for h, v in s["by_horizon"].items()},
            "relWIS_base": round(s["relWIS"], 4), "relWIS_base_h": s["relWIS_by_horizon"],
            "cov50": round(s["cov50"], 4), "cov90": round(s["cov90"], 4), "n": s["n_finite_paired"]}


def main() -> None:
    t0 = time.time()
    out_dir = os.path.join(HERE, "results", "a5")
    os.makedirs(out_dir, exist_ok=True)
    oracle = load_oracle()
    base = load_model_output("FluSight-baseline")
    truth = oracle[["location", "target_end_date", "oracle_value"]].drop_duplicates(["location", "target_end_date"])
    truth = truth.assign(target_end_date=truth["target_end_date"].dt.strftime("%Y-%m-%d"))
    res: dict = {"W": W, "load_s": None}
    data = {m: load_model(m) for m in MODELS}
    res["load_s"] = round(time.time() - t0, 1)
    for model in MODELS:
        df = data[model]
        ws = {s: wide(df[df["season"] == s], truth) for s in DEV_SEASONS}
        res[model] = {}
        for test in DEV_SEASONS:
            train = [s for s in DEV_SEASONS if s != test][0]
            te = df[df["season"] == test].drop(columns="season")
            r: dict = {"train": train, "U": score(te, oracle, base, "U")}
            for name in ("a", "b"):
                t1 = time.time()
                if name == "a":
                    qs, extra = window_a(ws[test], ws[train]), {}
                else:
                    qs, extra = window_b(ws[test], ws[train])
                adj = adjust(te, qs)
                rt = time.time() - t1
                sc = score(adj, oracle, base, name)
                u = r["U"]
                sc["relWIS_vs_U"] = round(sc["wis"] / u["wis"], 4)
                sc["relWIS_vs_U_h"] = {h: round(sc["wis_h"][h] / u["wis_h"][h], 4) for h in u["wis_h"]}
                sc["Q_by_h"] = {int(h): {"Q50_mean": round(float(g["Q50"].mean()), 4),
                                         "Q90_mean": round(float(g["Q90"].mean()), 4)}
                                for h, g in qs.groupby("horizon")}
                sc["adjust_runtime_s"] = round(rt, 2)
                sc.update(extra)
                sc["pass_cov"] = bool(0.45 <= sc["cov50"] <= 0.55 and 0.85 <= sc["cov90"] <= 0.95)
                sc["pass_wis"] = bool(sc["relWIS_vs_U"] <= 1.0)
                sc["pass_fold"] = sc["pass_cov"] and sc["pass_wis"]
                r[name] = sc
                print(model, test, name, json.dumps({k: sc[k] for k in ("cov50", "cov90", "relWIS_vs_U",
                                                                        "relWIS_base", "pass_fold")}), flush=True)
            res[model][test] = r
        res[model]["pass"] = {n: all(res[model][s][n]["pass_fold"] for s in DEV_SEASONS) for n in ("a", "b")}
    res["runtime_s"] = round(time.time() - t0, 1)
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("runtime", res["runtime_s"])


if __name__ == "__main__":
    main()
