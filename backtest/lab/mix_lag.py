"""CyberEpi-MIX_LAG (SYNTHESIS §5 item 5, B5; source 12 E3): equal-weight linear pool with lagged members.

Members: CyberEpi-EAKF and CyberEpi-GBQR at ref, plus the same two at ref - 7 days, read from
forecasts/model-output. The spec says "three members" but lists four files. This module pools all
four with equal weight 1/4 each (implementation choice; flagged for the integrator). Nothing is learned.

Lag check: each lagged file must exist, and its first add commit (git log --diff-filter=A) must be
dated before ref (00:00 UTC), so the member was already public when the reference week was forecast.
If any lagged file fails the check, the whole week falls back to the two-member pool (identical to
CyberEpi-MIX_LP) and a flag is written to forecasts/shadow/diagnostics/mix_lag-<ref>.json.

Coverage: rows are keyed by (target_end_date, location), since lagged horizons differ for the same
target. The lagged file at ref-7 covers targets ref-14..ref+14, so the horizon 3 target (ref+21) has
no lagged member. Those rows are pooled from the two current members only; their count is in the flag.

Frozen constants (pre-registered, not tuned): LAG_DAYS = 7; MEMBERS as above; equal weights.
No 2025-26 data is used for any choice.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import subprocess

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backtest/
from shadow import KEY, LEVELS, mix_linear_pool, read_submitted, to_long, wide  # noqa: E402

MEMBERS = ("CyberEpi-EAKF", "CyberEpi-GBQR")
LAG_DAYS = 7


def _committed_before(forecasts: str, model: str, date: str, ref: str) -> tuple[bool, str]:
    rel = os.path.join("forecasts", "model-output", model, f"{date}-{model}.csv")
    repo = os.path.dirname(os.path.abspath(forecasts))
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--reverse", "--format=%cI", "--", rel],
                             cwd=repo, capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return False, f"git query failed: {e}"
    first = out.split("\n")[0].strip()
    if not first:
        return False, f"no git history for {rel}"
    if pd.Timestamp(first).tz_convert("UTC") >= pd.Timestamp(ref, tz="UTC"):
        return False, f"{rel} first committed {first}, not before {ref}"
    return True, first


def _linear_pool(arrs: list[np.ndarray]) -> np.ndarray:
    """Equal-weight linear pool over aligned (n, 23) quantile arrays (mirrors shadow.mix_linear_pool)."""
    out = np.empty_like(arrs[0])
    for i in range(len(arrs[0])):
        grid = np.unique(np.concatenate([a[i] for a in arrs]))
        cdf = np.mean([np.interp(grid, np.sort(a[i]), LEVELS) for a in arrs], axis=0)
        cdf = np.maximum.accumulate(cdf)
        out[i] = np.interp(LEVELS, cdf + np.arange(len(cdf)) * 1e-12, grid)
    return out


def _by_target(w: pd.DataFrame) -> pd.DataFrame:
    return w.reset_index().set_index(["target_end_date", "location"]).sort_index()


def run(ref: str, ctx) -> pd.DataFrame:
    lag_ref = (dt.date.fromisoformat(ref) - dt.timedelta(days=LAG_DAYS)).isoformat()
    current = [read_submitted(ctx.forecasts, m, ref) for m in MEMBERS]
    if any(c is None for c in current):
        raise RuntimeError(f"needs {' and '.join(MEMBERS)} files for {ref}")

    lagged, reasons = [], []
    for m in MEMBERS:
        ok, why = _committed_before(ctx.forecasts, m, lag_ref, ref)
        df = read_submitted(ctx.forecasts, m, lag_ref) if ok else None
        if df is None:
            reasons.append(f"{m}@{lag_ref}: {why if not ok else 'file missing'}")
        else:
            lagged.append(df)

    diag = os.path.join(ctx.forecasts, "shadow", "diagnostics")
    os.makedirs(diag, exist_ok=True)
    flag = {"ref": ref, "lag_ref": lag_ref, "flag": None, "reasons": reasons, "rows_two_member": 0}
    if reasons:
        flag["flag"] = "fallback_two_member"
        with open(os.path.join(diag, f"mix_lag-{ref}.json"), "w") as fh:
            json.dump(flag, fh, indent=1)
        return mix_linear_pool(ref, ctx)

    cur = [_by_target(wide(f)) for f in current]
    lag = [_by_target(wide(f)) for f in lagged]
    cols = LEVELS.round(3)
    cur_common = cur[0].index.intersection(cur[1].index)
    full = cur_common.intersection(lag[0].index).intersection(lag[1].index)
    partial = cur_common.difference(full)
    pooled_full = _linear_pool([f.loc[full, cols].to_numpy(float) for f in cur + lag])
    pooled_part = _linear_pool([f.loc[partial, cols].to_numpy(float) for f in cur])

    flag["rows_two_member"] = int(len(partial)) * len(cols)
    with open(os.path.join(diag, f"mix_lag-{ref}.json"), "w") as fh:
        json.dump(flag, fh, indent=1)

    combined = full.append(partial)
    pooled = pd.DataFrame(np.vstack([pooled_full, pooled_part]), index=combined, columns=cols).sort_index()
    meta = cur[0].loc[pooled.index]
    idx = pd.MultiIndex.from_arrays(
        [meta["reference_date"], meta["target"], meta["horizon"],
         pooled.index.get_level_values(0), pooled.index.get_level_values(1)], names=KEY)
    pooled.index = idx
    pooled.columns.name = "output_type_id"
    return to_long(pooled)
