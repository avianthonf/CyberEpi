"""Score the live forecasts against the latest truth: submitted, lab and hub references.

Scores every forecast in forecasts/model-output (submitted) and forecasts/shadow
(lab models, never submitted) plus the hub's FluSight-ensemble and
FluSight-baseline, for wk inc flu hosp, on the rows whose target week already has
truth in the hub's target-data. Reference dates before --since (default: start
of the 2026-27 season) are ignored for every model. Rules for the lab models:
SHADOW_PROTOCOL.md.

Writes, to --out (default backtest/results/live):
  scores.csv   one row per (model, reference_date, location, horizon)
  summary.csv  one row per model: WIS, coverage, relWIS vs CyberEpi-EAKF and
               FluSight-ensemble on identical rows; a model with no scored rows
               gets a row with n_rows=0 and a notice

With no scored rows at all (truth not out for any target), both files are written
with headers/zero-row entries and a notice is printed; the exit code is 0.

Usage:
  python3 backtest/score_live.py [--hub ../flusight-forecast-hub] [--forecasts forecasts]
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_scores import LEVELS, load_model  # noqa: E402  (reuses the hub-format loader)
from wis import weighted_interval_score  # noqa: E402

KEY = ["location", "reference_date", "horizon", "target_end_date"]
REF_MODEL = "CyberEpi-EAKF"
HUB_REFS = ("FluSight-ensemble", "FluSight-baseline")
SCORE_COLS = ["model", "kind", "reference_date", "location", "horizon", "target_end_date",
              "truth", "median", "wis", "cov50", "cov95"]
SUMMARY_COLS = ["model", "kind", "n_rows", "n_ref_weeks", "wis", "cov50", "cov95",
                f"rel_wis_vs_{REF_MODEL}", "rel_wis_vs_FluSight-ensemble"]


def model_paths(forecasts: str, hub: str) -> list[tuple[str, str, str]]:
    """(name, path, kind) for every model to score."""
    out = []
    for kind, sub in (("submitted", "model-output"), ("lab", "shadow")):
        for p in sorted(glob.glob(os.path.join(forecasts, sub, "*"))):
            if os.path.isdir(p) and os.path.basename(p) != "diagnostics":
                out.append((os.path.basename(p), p, kind))
    for name in HUB_REFS:
        p = os.path.join(hub, "model-output", name)
        if os.path.isdir(p):
            out.append((name, p, "reference"))
        else:
            print(f"::notice::hub reference {name} not found under {hub}; not scored")
    return out


def load_truth(hub: str) -> pd.DataFrame:
    tr = pd.read_csv(os.path.join(hub, "target-data", "target-hospital-admissions.csv"),
                     dtype={"location": str})
    tr["location"] = tr["location"].where(tr["location"] == "US", tr["location"].str.zfill(2))
    tr["target_end_date"] = pd.to_datetime(tr["date"]).dt.strftime("%Y-%m-%d")
    return tr.rename(columns={"value": "truth"})[["location", "target_end_date", "truth"]].dropna()


def score_models(paths: list[tuple[str, str, str]], truth: pd.DataFrame, since: str) -> pd.DataFrame:
    parts = []
    for name, path, kind in paths:
        df = load_model(path)
        if df is None:
            print(f"::notice::{name}: no usable quantile forecasts; not scored")
            continue
        df = df[df["reference_date"] >= since].copy()
        df["target_end_date"] = pd.to_datetime(df["target_end_date"]).dt.strftime("%Y-%m-%d")
        df = df.merge(truth, on=["location", "target_end_date"], how="inner")
        if df.empty:
            print(f"::notice::{name}: no forecast target week has truth yet; not scored")
            continue
        q = np.vstack(df["q"].to_numpy())
        y = df["truth"].to_numpy(dtype=float)
        df["wis"] = weighted_interval_score(LEVELS, q, y)
        df["cov50"] = (y >= q[:, 6]) & (y <= q[:, 16])
        df["cov95"] = (y >= q[:, 1]) & (y <= q[:, 21])
        df["median"] = q[:, 11]
        df["kind"] = kind
        parts.append(df.drop(columns=["q"]))
    if not parts:
        return pd.DataFrame(columns=SCORE_COLS)
    return pd.concat(parts, ignore_index=True)


def rel_wis(rows: pd.DataFrame, model: str, ref: str) -> float:
    """Mean WIS of model / mean WIS of ref on rows both have scores for."""
    a = rows[rows["model"] == model][KEY + ["wis"]]
    b = rows[rows["model"] == ref][KEY + ["wis"]]
    both = a.merge(b, on=KEY, suffixes=("", "_ref"))
    if both.empty or both["wis_ref"].mean() == 0:
        return float("nan")
    return float(both["wis"].mean() / both["wis_ref"].mean())


def summarise(rows: pd.DataFrame, paths: list[tuple[str, str, str]]) -> pd.DataFrame:
    recs = []
    for name, _, kind in paths:
        g = rows[rows["model"] == name]
        if g.empty:
            recs.append({"model": name, "kind": kind, "n_rows": 0})
            continue
        rec = {"model": name, "kind": kind, "n_rows": len(g),
               "n_ref_weeks": g["reference_date"].nunique(), "wis": g["wis"].mean(),
               "cov50": g["cov50"].mean(), "cov95": g["cov95"].mean()}
        for ref in (REF_MODEL, "FluSight-ensemble"):
            rec[f"rel_wis_vs_{ref}"] = np.nan if name == ref else rel_wis(rows, name, ref)
        recs.append(rec)
    return pd.DataFrame(recs, columns=SUMMARY_COLS)


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", default=os.path.join(here, "..", "..", "flusight-forecast-hub"))
    ap.add_argument("--forecasts", default="forecasts")
    ap.add_argument("--out", default=os.path.join("backtest", "results", "live"))
    ap.add_argument("--since", default="2026-09-01", help="score reference dates on or after this")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    truth = load_truth(a.hub)
    print(f"latest truth: target week {truth['target_end_date'].max()}")
    paths = model_paths(a.forecasts, a.hub)
    rows = score_models(paths, truth, a.since)

    if rows.empty:
        print("::notice::no scored forecasts yet: no forecast target week has truth. "
              "Scores are written once truth exists.")
    summ = summarise(rows, paths)
    if not summ.empty:
        print(summ.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    rows.to_csv(os.path.join(a.out, "scores.csv"), index=False)
    summ.to_csv(os.path.join(a.out, "summary.csv"), index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
