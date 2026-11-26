"""Score every archived FluSight team forecast (wk inc flu hosp, h=0..3).

Evidence about which methods work on this exact task: each team model's WIS
against the latest truth, by season, horizon and epidemic phase, plus relWIS
vs FluSight-ensemble and FluSight-baseline on identical rows and the CDC-style
pairwise relative WIS.

Usage:
  python3 backtest/archive_scores.py --hub /path/to/FluSight-forecast-hub \
      --out backtest/results/archive [--ncpus 4]

Writes rows.parquet (one row per model/location/date/horizon; not committed)
and summary CSVs (committed).
"""
from __future__ import annotations

import argparse
import glob
import os
from multiprocessing import Pool

import numpy as np
import pandas as pd

LEVELS = np.array([0.01, 0.025] + [round(0.05 * i, 2) for i in range(1, 20)] + [0.975, 0.99])
HORIZONS = [0, 1, 2, 3]
REFS = ("FluSight-ensemble", "FluSight-baseline")


def season_of(d: pd.Series) -> pd.Series:
    y = d.dt.year - (d.dt.month < 8)
    return y.astype(str) + "-" + (y + 1).astype(str).str[-2:]


def load_model(path: str) -> pd.DataFrame | None:
    model = os.path.basename(path.rstrip("/"))
    files = sorted(glob.glob(os.path.join(path, "*.csv")) + glob.glob(os.path.join(path, "*.parquet")))
    parts = []
    for f in files:
        try:
            df = pd.read_parquet(f) if f.endswith(".parquet") else pd.read_csv(
                f, dtype={"location": str, "output_type_id": str})
        except Exception:
            continue
        if "target" not in df.columns:
            continue
        df = df[(df["target"] == "wk inc flu hosp") & (df["output_type"] == "quantile")]
        if df.empty:
            continue
        df = df[df["horizon"].astype(float).isin(HORIZONS)]
        df = df[["reference_date", "location", "horizon", "target_end_date", "output_type_id", "value"]].copy()
        for c in ("reference_date", "target_end_date"):
            df[c] = pd.to_datetime(df[c].astype(str)).dt.strftime("%Y-%m-%d")
        df["output_type_id"] = pd.to_numeric(df["output_type_id"], errors="coerce").round(3)
        parts.append(df)
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    df["location"] = df["location"].astype(str).str.zfill(2).replace({"US": "US"})
    df.loc[df["location"].str.upper() == "US", "location"] = "US"
    df["horizon"] = df["horizon"].astype(int)
    df = df.dropna(subset=["output_type_id", "value"])
    df = df[df["output_type_id"].isin(LEVELS.round(3))]
    wide = df.pivot_table(index=["reference_date", "location", "horizon", "target_end_date"],
                          columns="output_type_id", values="value", aggfunc="first")
    wide = wide.reindex(columns=LEVELS.round(3)).dropna()
    if wide.empty:
        return None
    q = np.sort(wide.to_numpy(dtype=float), axis=1)
    out = wide.index.to_frame(index=False)
    out["model"] = model
    out["q"] = list(q)
    return out


def score(args):
    path, truth = args
    df = load_model(path)
    if df is None:
        return None
    df["target_end_date"] = pd.to_datetime(df["target_end_date"]).dt.strftime("%Y-%m-%d")
    df = df.merge(truth, on=["location", "target_end_date"], how="inner")
    if df.empty:
        return None
    q = np.vstack(df["q"].to_numpy())
    y = df["truth"].to_numpy(dtype=float)
    tau = LEVELS[None, :]
    diff = y[:, None] - q
    pin = np.maximum(tau * diff, (tau - 1) * diff)
    # (alpha/2)*IS_alpha = pinball(alpha/2) + pinball(1-alpha/2) and 0.5|y-m| = pinball(0.5),
    # so WIS = sum of the 23 pinball losses / (K + 1/2), K = 11 intervals.
    wis = pin.sum(axis=1) / 11.5
    df["wis"] = wis
    df["cov50"] = (y >= q[:, 6]) & (y <= q[:, 16])
    df["cov90"] = (y >= q[:, 3]) & (y <= q[:, 19])
    df["median"] = q[:, 11]
    df["below_median"] = y < q[:, 11]
    return df.drop(columns=["q"])


COMPLETED_SEASONS = {"2023-24", "2024-25", "2025-26"}  # 2026-27 is in progress; its phases are provisional


def phases(truth: pd.DataFrame) -> pd.DataFrame:
    """Epidemic phase of each (location, week) from final truth.

    near_peak: within 2 weeks of the season peak; rising: before that;
    declining: after that. Seasons with a peak under 1 per 100k are 'low'.
    """
    t = truth.copy()
    t["d"] = pd.to_datetime(t["target_end_date"])
    t["season"] = season_of(t["d"])
    out = []
    for (_, _), g in t.groupby(["location", "season"]):
        g = g.sort_values("d")
        if g["season"].iloc[0] not in COMPLETED_SEASONS:
            # Season still in progress: idxmax would be the peak so far, not the season peak.
            ph = np.array(["provisional"] * len(g))
        else:
            pk = g.loc[g["truth"].idxmax(), "d"]
            dw = (g["d"] - pk).dt.days // 7
            ph = np.where(dw.abs() <= 2, "near_peak", np.where(dw < 0, "rising", "declining"))
        out.append(pd.DataFrame({"location": g["location"], "target_end_date": g["target_end_date"],
                                 "phase": ph}))
    return pd.concat(out, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", required=True)
    ap.add_argument("--out", default="backtest/results/archive")
    ap.add_argument("--ncpus", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    tr = pd.read_csv(os.path.join(a.hub, "target-data/target-hospital-admissions.csv"), dtype={"location": str})
    truth = tr.rename(columns={"date": "target_end_date", "value": "truth"})[["location", "target_end_date", "truth"]]
    truth["location"] = truth["location"].where(truth["location"] == "US", truth["location"].str.zfill(2))

    paths = sorted(p for p in glob.glob(os.path.join(a.hub, "model-output/*"))
                   if os.path.isdir(p))
    with Pool(a.ncpus) as pool:
        res = [r for r in pool.map(score, [(p, truth) for p in paths]) if r is not None]
    rows = pd.concat(res, ignore_index=True)
    rows["season"] = season_of(pd.to_datetime(rows["reference_date"]))
    rows = rows.merge(phases(truth), on=["location", "target_end_date"], how="left")
    rows.to_parquet(os.path.join(a.out, "rows.parquet"))

    key = ["location", "reference_date", "horizon"]
    summ = []
    for ref in REFS:
        r = rows[rows["model"] == ref][key + ["wis"]].rename(columns={"wis": "wis_ref"})
        m = rows.merge(r, on=key)
        for by in (["season"], ["season", "horizon"], ["season", "phase"]):
            g = m.groupby(["model"] + by).agg(n=("wis", "size"), wis=("wis", "mean"), wis_ref=("wis_ref", "mean"),
                                              cov50=("cov50", "mean"), cov90=("cov90", "mean"),
                                              below_median=("below_median", "mean")).reset_index()
            g["rel"] = g["wis"] / g["wis_ref"]
            g["ref"] = ref
            g["by"] = "+".join(by)
            summ.append(g)
    summ = pd.concat(summ, ignore_index=True)
    summ.to_csv(os.path.join(a.out, "summary.csv"), index=False)

    # CDC-style pairwise relative WIS per season (models with >= 50% of the season's rows)
    pw = []
    for s, g in rows.groupby("season"):
        piv = g.pivot_table(index=key, columns="model", values="wis")
        keep = piv.columns[piv.notna().mean() >= 0.5]
        piv = piv[keep]
        models = list(piv.columns)
        theta = {}
        for i in models:
            ratios = []
            for j in models:
                if i == j:
                    continue
                both = piv[[i, j]].dropna()
                if len(both) and both[j].mean() > 0:
                    ratios.append(both[i].mean() / both[j].mean())
            theta[i] = float(np.exp(np.mean(np.log(ratios)))) if ratios else np.nan
        base = theta.get("FluSight-baseline", np.nan)
        for i in models:
            pw.append({"season": s, "model": i, "n": int(piv[i].notna().sum()),
                       "pairwise_rel_wis": theta[i] / base})
    pd.DataFrame(pw).sort_values(["season", "pairwise_rel_wis"]).to_csv(
        os.path.join(a.out, "pairwise.csv"), index=False)
    print(f"{rows['model'].nunique()} models, {len(rows)} scored rows")


if __name__ == "__main__":
    main()
