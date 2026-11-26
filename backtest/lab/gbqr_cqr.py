"""CyberEpi-GBQR_CQR (lab, A5 window b): horizon-wise CQR adjustment of submitted CyberEpi-GBQR, live.

Method is A5 window (b) (docs/research/experiments/A5_conformal.md, backtest/a5_conformal.py), applied to
the submitted model 2 forecast for `ref`:
  - Scores per origin/horizon/location: z = log1p(value), z_y = log1p(truth),
    E50 = max(q0.25 - z_y, z_y - q0.75), E90 = max(q0.05 - z_y, z_y - q0.95).
  - Calibration set: (i) submitted CyberEpi-GBQR origins ref-7k, k = 1..W, scored against truth, keeping only
    target_end_date <= ref - 7 days (truth published before ref); (ii) if fewer than W origins contribute at a
    horizon, the top-up of W - k origins from the frozen warm table (below).
  - Q50 = k-th smallest E50 with k = ceil((n+1)*0.5), Q90 likewise with alpha = 0.10; k capped at n.
  - Shift: |tau - 0.5| -> np.interp([0, .25, .45], [0, Q50, Q90]); the median is unchanged. Back-transform with
    expm1, round to integers, clip at 0, and enforce non-decreasing order across levels.
  - Horizon -1 rows are left unmodified.

Frozen constants (pre-registered 2026-11-26 with the protocol row; not tuned on live scores):
  W = 8 origins, pairs 0.25/0.75 (E50) and 0.05/0.95 (E90), A5 rounding and monotone rule.
  Warm table backtest/lab/gbqr_cqr_warm.csv: E50/E90 of the 2024-25 dev season CyberEpi-GBQR
  (backtest/results/dev_members, unmodified) scored against hub oracle-output with A5's wide() scoring, all 27
  origins, rounded to 4 dp. The table is data, not code, because it has 5,724 rows.
  Only 2024-25 is used. A5's 2023-24 fold takes its warm start from a later season, and this live model needs a
  past one; 2024-25 is the most recent prior season.

Warm-start block (A5 rule): i = index of ref in the dev calendar, (ref - first dev origin) // 7 mod 52, clipped
to the table length; the block is the need = W - k origins S[max(0, i - need) : max(0, i - need) + need]. For a
ref after the table's last origin, the index is clipped; this is an approximation, flagged for the verdict.

Truth vintage: the newest target-data-archive snapshot dated <= ref (same reader as EAKF_ACI). Raises when the
GBQR file for ref or no archive snapshot exists; the shadow runner then skips this model.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backtest/
from shadow import LEVELS, read_submitted, to_long, wide  # noqa: E402
from eakf_aci import _truth  # noqa: E402

MODEL = "CyberEpi-GBQR"
W = 8
WEEK = pd.Timedelta(days=7)
WARM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gbqr_cqr_warm.csv")
COLS = LEVELS.round(3)
MEDIAN = int(np.argmin(np.abs(COLS - 0.5)))


def _cqr_q(scores: np.ndarray, alpha: float) -> float:
    n = len(scores)
    if n == 0:
        raise RuntimeError("empty calibration set")
    k = min(int(np.ceil((n + 1) * (1 - alpha))), n)
    return float(np.sort(scores)[k - 1])


def _in_season(ref: str, ctx, truth: pd.Series) -> pd.DataFrame:
    """Scores (horizon, origin, E50, E90) from submitted GBQR origins ref-7..ref-7W, truth-published rows only."""
    cutoff = (pd.Timestamp(ref) - WEEK).strftime("%Y-%m-%d")
    tr = truth.rename("truth").reset_index()
    parts = []
    for j in range(1, W + 1):
        origin = (pd.Timestamp(ref) - j * WEEK).strftime("%Y-%m-%d")
        df = read_submitted(ctx.forecasts, MODEL, origin)
        if df is None:
            continue
        w = wide(df).reset_index()
        w = w[(w["horizon"] >= 0) & (w["target_end_date"] <= cutoff)]
        w = w.merge(tr, on=["location", "target_end_date"], how="inner")
        if w.empty:
            continue
        zy = np.log1p(w["truth"].to_numpy(float))
        lq = {t: np.log1p(w[t].to_numpy(float)) for t in (0.05, 0.25, 0.75, 0.95)}
        parts.append(pd.DataFrame({
            "horizon": w["horizon"].to_numpy(int),
            "origin": origin,
            "E50": np.maximum(lq[0.25] - zy, zy - lq[0.75]),
            "E90": np.maximum(lq[0.05] - zy, zy - lq[0.95]),
        }))
    if not parts:
        return pd.DataFrame(columns=["horizon", "origin", "E50", "E90"])
    return pd.concat(parts, ignore_index=True)


def _warm_block(ref: str, warm: pd.DataFrame, need: int) -> list[str]:
    origins = sorted(warm["reference_date"].unique())
    i = ((pd.Timestamp(ref) - pd.Timestamp(origins[0])).days // 7) % 52
    # refs before the calendar season start wrap to ~45-51: treat them as season start (A5 i = 0)
    i = 0 if i >= 40 else min(i, len(origins))
    start = max(0, i - need)
    return origins[start:start + need]


def _pairs(ref: str, ctx, truth: pd.Series) -> dict[int, tuple[float, float]]:
    cal = _in_season(ref, ctx, truth)
    warm = pd.read_csv(WARM, dtype={"location": str})
    qs = {}
    for h in range(4):
        ins = cal[cal["horizon"] == h]
        k = ins["origin"].nunique()
        e50, e90 = ins["E50"].to_numpy(float), ins["E90"].to_numpy(float)
        need = W - k
        if need > 0:
            block = warm[(warm["horizon"] == h) & warm["reference_date"].isin(_warm_block(ref, warm, need))]
            e50 = np.concatenate([e50, block["E50"].to_numpy(float)])
            e90 = np.concatenate([e90, block["E90"].to_numpy(float)])
        qs[h] = (_cqr_q(e50, 0.5), _cqr_q(e90, 0.10))
    return qs


def _adjust(w: pd.DataFrame, qs: dict[int, tuple[float, float]]) -> pd.DataFrame:
    vals = w[COLS].to_numpy(float)
    h = w.index.get_level_values("horizon").to_numpy(int)
    has = np.isin(h, list(qs))
    q50 = np.array([qs[x][0] if x in qs else 0.0 for x in h])[:, None]
    q90 = np.array([qs[x][1] if x in qs else 0.0 for x in h])[:, None]
    dist = np.abs(COLS - 0.5)[None, :]
    shift = np.where(dist <= 0.25, dist / 0.25 * q50,
                     q50 + (np.minimum(dist, 0.45) - 0.25) / 0.20 * (q90 - q50))
    shift = shift * np.sign(COLS - 0.5)[None, :]
    adj = np.maximum(np.round(np.expm1(np.log1p(vals) + shift)), 0)
    adj[:, MEDIAN] = vals[:, MEDIAN]
    adj = np.maximum.accumulate(adj, axis=1)
    out = vals.copy()
    out[has] = adj[has]
    return pd.DataFrame(out, index=w.index, columns=w.columns)


def run(ref: str, ctx) -> pd.DataFrame:
    hub = getattr(ctx, "hub", None) or "data/flusight"
    truth = _truth(hub, ref)
    submitted = read_submitted(ctx.forecasts, MODEL, ref)
    if submitted is None:
        raise RuntimeError(f"needs the submitted {MODEL} file for {ref}")
    base = wide(submitted)
    qs = _pairs(ref, ctx, truth)
    return to_long(_adjust(base, qs))
