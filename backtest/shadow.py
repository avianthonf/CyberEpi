"""Shadow mode: lab models that run live every week but are never submitted.

Each lab model writes a hub-format file to forecasts/shadow/<model>/<ref>-<model>.csv.
The weekly workflow commits these files, so each one is timestamped in git
before the data it will be scored on exists. score_live.py scores them next to
the submitted models. Rules: docs/research/SHADOW_PROTOCOL.md.

Adding a lab model: write a function `(ref, ctx) -> DataFrame` in hub format
(reference_date, target, horizon, target_end_date, location, output_type,
output_type_id, value) and add it to MODELS. A model that fails is skipped
with an error message; it never blocks the submitted models.

Usage: python3 backtest/shadow.py --forecasts forecasts --reference-date 2026-12-05
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback

import numpy as np
import pandas as pd

LEVELS = np.array([0.01, 0.025] + [round(0.05 * i, 2) for i in range(1, 20)] + [0.975, 0.99])
KEY = ["reference_date", "target", "horizon", "target_end_date", "location"]


def read_submitted(forecasts: str, model: str, ref: str) -> pd.DataFrame | None:
    f = os.path.join(forecasts, "model-output", model, f"{ref}-{model}.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f, dtype={"location": str, "output_type_id": str})
    df = df[(df["target"] == "wk inc flu hosp") & (df["output_type"] == "quantile")].copy()
    df["output_type_id"] = df["output_type_id"].astype(float).round(3)
    return df


def wide(df: pd.DataFrame) -> pd.DataFrame:
    w = df.pivot_table(index=KEY, columns="output_type_id", values="value", aggfunc="first")
    return w.reindex(columns=LEVELS.round(3))


def to_long(w: pd.DataFrame) -> pd.DataFrame:
    out = w.stack().rename("value").reset_index()
    out["output_type"] = "quantile"
    out["value"] = out["value"].clip(lower=0)
    return out[KEY[:2] + ["horizon", "target_end_date", "location", "output_type", "output_type_id", "value"]]


def members(ctx) -> list[pd.DataFrame]:
    ms = [read_submitted(ctx.forecasts, m, ctx.ref) for m in ("CyberEpi-EAKF", "CyberEpi-GBQR")]
    if any(m is None for m in ms):
        raise RuntimeError("needs both CyberEpi-EAKF and CyberEpi-GBQR files for this week")
    return [wide(m) for m in ms]


def mix_quantile_average(ref, ctx) -> pd.DataFrame:
    """Equal-weight quantile average (Vincentization) of models 1 and 2."""
    a, b = members(ctx)
    a, b = a.align(b, join="inner")
    return to_long((a + b) / 2)


def mix_linear_pool(ref, ctx) -> pd.DataFrame:
    """Equal-weight linear pool: average the two CDFs, then read off quantiles.

    Wider than the quantile average when the members disagree, which is when
    our two models' phase biases point in opposite directions.
    """
    a, b = members(ctx)
    a, b = a.align(b, join="inner")
    qa, qb = a.to_numpy(float), b.to_numpy(float)
    out = np.empty_like(qa)
    for i in range(len(qa)):
        grid = np.unique(np.concatenate([qa[i], qb[i]]))
        # piecewise-linear CDF of each member through its quantiles, flat in the tails
        cdf = 0.5 * (np.interp(grid, np.sort(qa[i]), LEVELS) + np.interp(grid, np.sort(qb[i]), LEVELS))
        cdf = np.maximum.accumulate(cdf)
        out[i] = np.interp(LEVELS, cdf + np.arange(len(cdf)) * 1e-12, grid)
    return to_long(pd.DataFrame(out, index=a.index, columns=a.columns))


def _lab(module: str):
    """Lazy import of backtest/lab/<module>.run. Lab modules import this file as
    `shadow`, so importing them at load time would be circular."""

    def fn(ref, ctx):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lab"))
        return __import__(module).run(ref, ctx)

    return fn


def bocd_mix(ref, ctx) -> pd.DataFrame:
    """BOCD mixture; also writes the per-location changepoint weights."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lab"))
    df, diag = __import__("bocd_mix").run_with_diagnostics(ref, ctx)
    d = os.path.join(ctx.forecasts, "shadow", "diagnostics")
    os.makedirs(d, exist_ok=True)
    diag.to_csv(os.path.join(d, f"bocd_mix-{ref}.csv"), index=False)
    return df


# name -> function. Names follow the hub's team-model convention but are never submitted.
# Lab models B2-B5 are specified in docs/research/SYNTHESIS.md §5.
MODELS = {
    "CyberEpi-MIX_QA": mix_quantile_average,
    "CyberEpi-MIX_LP": mix_linear_pool,
    "CyberEpi-BOCD_MIX": bocd_mix,
    "CyberEpi-ETS_DECL": _lab("ets_decl"),
    "CyberEpi-EAKF_ACI": _lab("eakf_aci"),
    "CyberEpi-MIX_LAG": _lab("mix_lag"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--forecasts", default="forecasts")
    ap.add_argument("--reference-date", required=True)
    a = ap.parse_args()
    ctx = argparse.Namespace(forecasts=a.forecasts, ref=a.reference_date)
    failed = 0
    for name, fn in MODELS.items():
        try:
            df = fn(a.reference_date, ctx)
            d = os.path.join(a.forecasts, "shadow", name)
            os.makedirs(d, exist_ok=True)
            df.to_csv(os.path.join(d, f"{a.reference_date}-{name}.csv"), index=False)
            print(f"{name}: {df['location'].nunique()} locations, {len(df)} rows")
        except Exception:
            failed += 1
            print(f"::warning::shadow model {name} failed:\n{traceback.format_exc()}", file=sys.stderr)
    return 0 if failed < len(MODELS) else 1


if __name__ == "__main__":
    sys.exit(main())
