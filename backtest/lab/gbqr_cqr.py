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
  Warm table (_WARM_ORIGINS, _WARM_B64 below): E50/E90 of the 2024-25 dev-season CyberEpi-GBQR
  (backtest/results/dev_members, unmodified) scored against hub oracle-output with a5_conformal.wide(), all 27
  origins. Encoding: int16 array of shape (origin, horizon 0-3, location, [E50, E90]) in units of 1e-3 log1p,
  locations in sorted code order (53), zlib-compressed and base64-encoded.
  Only 2024-25 is used, by choice: A5 window (b) warm-starts from the one other season aligned by in-season
  index; live, the most recent prior season fits that rule (A5's 2023-24 fold borrowed a later season).

Warm-start block (A5 rule): i = in-season week index of ref, (ref - 2024-11-23) // 7 mod 52 (refs before the
calendar season start, index >= 40, count as i = 0), capped at the table length; the block is the
need = W - k origins S[max(0, i - need) : max(0, i - need) + need]. A5 indexed the origin list, which skips
2025-01-25; the calendar index differs from it by at most one origin after January.

Truth vintage: the newest target-data-archive snapshot dated <= ref (same reader as EAKF_ACI). Raises when the
GBQR file for ref or no archive snapshot exists; the shadow runner then skips this model.
"""
from __future__ import annotations

import base64
import os
import sys
import zlib

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backtest/
from shadow import LEVELS, read_submitted, to_long, wide  # noqa: E402
from eakf_aci import _truth  # noqa: E402

MODEL = "CyberEpi-GBQR"
W = 8
WEEK = pd.Timedelta(days=7)
_WARM_ORIGINS = (
    "2024-11-23", "2024-11-30", "2024-12-07", "2024-12-14", "2024-12-21", "2024-12-28", "2025-01-04",
    "2025-01-11", "2025-01-18", "2025-02-01", "2025-02-08", "2025-02-15", "2025-02-22", "2025-03-01",
    "2025-03-08", "2025-03-15", "2025-03-22", "2025-03-29", "2025-04-05", "2025-04-12", "2025-04-19",
    "2025-04-26", "2025-05-03", "2025-05-10", "2025-05-17", "2025-05-24", "2025-05-31",
)
_WARM_B64 = (
    "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"
)
WARM = np.frombuffer(zlib.decompress(base64.b64decode(_WARM_B64)), dtype="<i2").reshape(
    len(_WARM_ORIGINS), 4, 53, 2).astype(float) / 1000.0
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


def _warm_block(ref: str, need: int) -> list[int]:
    i = ((pd.Timestamp(ref) - pd.Timestamp(_WARM_ORIGINS[0])).days // 7) % 52
    # refs before the calendar season start wrap to ~45-51: treat them as season start (A5 i = 0)
    i = 0 if i >= 40 else min(i, len(_WARM_ORIGINS))
    start = max(0, i - need)
    return list(range(start, min(start + need, len(_WARM_ORIGINS))))


def _pairs(ref: str, ctx, truth: pd.Series) -> dict[int, tuple[float, float]]:
    cal = _in_season(ref, ctx, truth)
    qs = {}
    for h in range(4):
        ins = cal[cal["horizon"] == h]
        k = ins["origin"].nunique()
        e50, e90 = ins["E50"].to_numpy(float), ins["E90"].to_numpy(float)
        need = W - k
        if need > 0:
            block = WARM[_warm_block(ref, need), h].reshape(-1, 2)
            e50 = np.concatenate([e50, block[:, 0]])
            e90 = np.concatenate([e90, block[:, 1]])
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
