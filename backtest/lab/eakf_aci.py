"""CyberEpi-EAKF_ACI (SYNTHESIS §5 item 4, B4): adaptive conformal (ACI) recalibration of EAKF quantiles.

Per location, horizon and nominal level (50%, 90%) the state alpha_t is the working miscoverage.
After each truth becomes available, alpha <- alpha + GAMMA * (alpha_nom - miss), where miss = 1
if the truth fell outside the interval that was actually issued for that forecast. The interval
for the current week is the EAKF quantile curve read at levels (alpha/2, 1 - alpha/2).

Frozen constants (pre-registered, not tuned):
  GAMMA = 0.01   fixed in advance by SYNTHESIS §3 B4 / 07 §5 item 4. No data used to choose it.
  NOMINAL: 50% and 90% central intervals, alpha_nom = 0.5 and 0.1, initial alpha = alpha_nom.
  Grid pairs: 50% uses levels 0.25/0.75; 90% uses 0.05/0.95 (both on the hub LEVELS grid).

Truth vintage: the newest target-data-archive snapshot dated <= ref, and only target weeks ending
strictly before ref are used. The reference week's own truth is never used.

Issued intervals are recorded per reference date at the first run, so re-running a week is
idempotent and past updates use the interval that was really issued.

State file: <forecasts>/shadow/diagnostics/aci_state.json (contains alpha, issued intervals,
processed keys, running coverage and history per week).

Hub: ctx.hub if set, else data/flusight (repo symlink, includes target-data-archive/). Raises when
no archive snapshot dated on or before ref exists.
"""
from __future__ import annotations

import sys
import glob
import json
import os
import re

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backtest/
from shadow import KEY, LEVELS, read_submitted, to_long, wide  # noqa: E402

MODEL = "CyberEpi-EAKF"
GAMMA = 0.01
NOMINAL = {"50": 0.5, "90": 0.1}
PAIRS = {"50": (0.25, 0.75), "90": (0.05, 0.95)}
STATE_REL = os.path.join("shadow", "diagnostics", "aci_state.json")


def _grid_index(level: float) -> int:
    return int(np.argmin(np.abs(LEVELS - level)))


def _adjusted_row(raw: np.ndarray, bounds: dict) -> np.ndarray:
    """Replace the 50%/90% grid quantiles by the ACI bounds, then keep the row monotone."""
    out = raw.astype(float).copy()
    for lev, (lo_l, hi_l) in PAIRS.items():
        lo, hi = bounds[lev]
        out[_grid_index(lo_l)] = lo
        out[_grid_index(hi_l)] = hi
    return np.maximum.accumulate(out)


def _raw_bounds(raw: np.ndarray, alpha: dict) -> dict:
    return {lev: (float(np.interp(alpha[lev] / 2, LEVELS, raw)),
                  float(np.interp(1 - alpha[lev] / 2, LEVELS, raw))) for lev in PAIRS}


def _truth(hub: str, ref: str) -> pd.DataFrame:
    d = os.path.join(hub, "target-data-archive")
    snaps = []
    for f in glob.glob(os.path.join(d, "target-hospital-admissions_*.csv")):
        m = re.search(r"_(\d{4}-\d{2}-\d{2})\.csv$", f)
        if m and m.group(1) <= ref:
            snaps.append((m.group(1), f))
    if not snaps:
        raise RuntimeError(f"no target-data-archive snapshot dated <= {ref} under {d}")
    _, path = max(snaps)
    tr = pd.read_csv(path, dtype={"location": str})
    tr["location"] = tr["location"].where(tr["location"] == "US", tr["location"].str.zfill(2))
    tr["target_end_date"] = pd.to_datetime(tr["date"]).dt.strftime("%Y-%m-%d")
    tr = tr.rename(columns={"value": "truth"})[["location", "target_end_date", "truth"]].dropna()
    return tr.set_index(["location", "target_end_date"])["truth"]


def _load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {"alpha": {}, "issued": {}, "processed": [], "cov": {"50": [0, 0], "90": [0, 0]},
                "history": []}
    with open(path) as fh:
        return json.load(fh)


def _alpha(state: dict, loc: str, h: int, lev: str) -> float:
    return state["alpha"].get(f"{loc}|{h}|{lev}", NOMINAL[lev])


def run(ref: str, ctx) -> pd.DataFrame:
    hub = getattr(ctx, "hub", None) or "data/flusight"
    truth = _truth(hub, ref)
    state_path = os.path.join(ctx.forecasts, STATE_REL)
    state = _load_state(state_path)
    processed = set(state["processed"])

    # 1) Learn from every past forecast whose target weeks now have truth (strictly before ref).
    past = []
    for f in sorted(glob.glob(os.path.join(ctx.forecasts, "model-output", MODEL, f"*-{MODEL}.csv"))):
        r = os.path.basename(f)[:10]
        if r < ref:
            past.append(r)
    for r in past:
        w = read_submitted(ctx.forecasts, MODEL, r)
        if w is None:
            continue
        w = wide(w).reset_index()
        issued = state["issued"].get(r)
        for (loc, h, tgt), grp in w.groupby(["location", "horizon", "target_end_date"]):
            if tgt >= ref or (loc, tgt) not in truth.index:
                continue
            key = f"{r}|{loc}|{h}"
            y = float(truth.loc[(loc, tgt)])
            pk = f"{key}|{tgt}"
            if pk in processed:
                continue
            raw = grp[LEVELS.round(3)].to_numpy(float)[0]
            if issued is not None and key in issued:
                bounds = {lev: tuple(issued[key][lev]) for lev in PAIRS}
            else:
                bounds = _raw_bounds(raw, NOMINAL)
            for lev in PAIRS:
                lo, hi = bounds[lev]
                miss = int(y < lo or y > hi)
                ak = f"{loc}|{int(h)}|{lev}"
                state["alpha"][ak] = _alpha(state, loc, int(h), lev) + GAMMA * (NOMINAL[lev] - miss)
                state["cov"][lev][0] += 1 - miss
                state["cov"][lev][1] += 1
            processed.add(pk)
    state["processed"] = sorted(processed)

    # 2) Issue the current week's intervals from the state (idempotent per reference date).
    cur = read_submitted(ctx.forecasts, MODEL, ref)
    if cur is None:
        raise RuntimeError(f"needs {MODEL} file for {ref}")
    cw = wide(cur)
    if ref not in state["issued"]:
        issued = {}
        for idx, raw in zip(cw.index, cw.to_numpy(float)):
            loc, h = idx[KEY.index("location")], int(idx[KEY.index("horizon")])
            alpha = {lev: _alpha(state, loc, h, lev) for lev in PAIRS}
            issued[f"{ref}|{loc}|{h}"] = {lev: list(b) for lev, b in
                                          _raw_bounds(raw, alpha).items()}
        state["issued"][ref] = issued
        # keep issued bounds only for the most recent weeks to bound state size
        for old in sorted(state["issued"])[:-60]:
            del state["issued"][old]
    issued = state["issued"][ref]

    rows = []
    for idx, raw in zip(cw.index, cw.to_numpy(float)):
        loc, h = idx[KEY.index("location")], int(idx[KEY.index("horizon")])
        bounds = {lev: tuple(issued[f"{ref}|{loc}|{h}"][lev]) for lev in PAIRS}
        rows.append(_adjusted_row(raw, bounds))
    out = pd.DataFrame(np.vstack(rows), index=cw.index, columns=cw.columns)

    # 3) Running coverage and state, one history entry per reference week.
    cov = {lev: (state["cov"][lev][0] / state["cov"][lev][1] if state["cov"][lev][1] else None)
           for lev in PAIRS}
    entry = {"ref": ref, "n_scored": state["cov"]["90"][1],
             "cov50_running": cov["50"], "cov90_running": cov["90"],
             "alpha90_mean": float(np.mean([v for k, v in state["alpha"].items()
                                            if k.endswith("|90")] or [NOMINAL["90"]]))}
    state["history"] = [e for e in state["history"] if e["ref"] != ref] + [entry]
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)

    return to_long(out)
