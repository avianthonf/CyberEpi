"""Forecast calibration: per-horizon shift and widening of quantiles.

The honest backtest showed forecasts that are systematically too low (truth
above the median ~65% of the time; median low by 13-39% in log terms,
growing with horizon) and 90% intervals covering ~74%. Per horizon h, in
log1p space with m = log1p(median):

    v' = expm1(m + b_h + k_h * (log1p(v) - m))

b_h shifts the whole forecast (b > 0 raises it); k_h > 1 widens it. Quantile
order is preserved.

(b_h, k_h) are fitted on a grid by minimising mean quantile (pinball) loss,
which is proportional to WIS, on every past season's as-published backtest
rows. Leave-one-season-out validation (fit on two seasons, score the third)
is reported to show the correction generalises. Backtest headline scores
stay frozen (ROADMAP.md); the live 2026-27 season is the real test.

Usage:
    python3 backtest/calibrate.py fit rows1.csv rows2.csv ... \
        [--out backtest/results/calibration.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hub_data import load_oracle

K_GRID = np.round(np.arange(0.8, 2.51, 0.05), 2)
B_GRID = np.round(np.arange(0.0, 0.61, 0.02), 2)
DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "calibration.json")


def _transform(lq: np.ndarray, m: np.ndarray, b: float, k: float) -> np.ndarray:
    return np.maximum(np.round(np.expm1(m + b + k * (lq - m))), 0.0)


def adjust(values: np.ndarray, levels: np.ndarray, b: float, k: float) -> np.ndarray:
    """Calibrate one forecast's quantile values (aligned to `levels`)."""
    lq = np.log1p(np.maximum(values, 0.0))
    m = lq[np.argmin(np.abs(levels - 0.5))]
    return _transform(lq, m, b, k)


def apply(rows: pd.DataFrame, params: dict[int, tuple[float, float]]) -> pd.DataFrame:
    """Return a copy of hub-format rows calibrated per horizon {h: (b, k)}."""
    out = rows.copy()
    lev = out["output_type_id"].astype(float)
    for _, idx in out.groupby(["location", "reference_date", "horizon"]).groups.items():
        bk = params.get(int(out.at[idx[0], "horizon"]))
        if bk is None:
            continue
        order = lev.loc[idx].sort_values().index
        new = adjust(out.loc[order, "value"].to_numpy(float), lev.loc[order].to_numpy(float), *bk)
        out.loc[order, "value"] = new.astype(int)
    return out


def load_params(path: str = DEFAULT_PATH) -> dict[int, tuple[float, float]]:
    with open(path) as f:
        p = json.load(f)["params"]
    return {int(h): (float(v["b"]), float(v["k"])) for h, v in p.items()}


def _arrays(rows: pd.DataFrame) -> dict[str, np.ndarray]:
    """Pivot rows to quantile matrices joined to final truth."""
    o = load_oracle()[["location", "target_end_date", "oracle_value"]].drop_duplicates(
        ["location", "target_end_date"])
    r = rows[rows["horizon"] >= 0].copy()
    r["output_type_id"] = r["output_type_id"].astype(float)
    r["target_end_date"] = pd.to_datetime(r["target_end_date"])
    wide = r.pivot_table(index=["season", "location", "reference_date", "horizon", "target_end_date"],
                         columns="output_type_id", values="value").dropna()
    wide = wide.reset_index().merge(o, on=["location", "target_end_date"], how="inner")
    wide = wide[np.isfinite(wide["oracle_value"])]
    levels = np.array(sorted(c for c in wide.columns if isinstance(c, float)))
    q = wide[list(levels)].to_numpy(float)
    lq = np.log1p(np.maximum(q, 0.0))
    return {"levels": levels, "q": q, "lq": lq,
            "m": lq[:, [int(np.argmin(np.abs(levels - 0.5)))]],
            "y": wide["oracle_value"].to_numpy(float),
            "h": wide["horizon"].to_numpy(int), "season": wide["season"].to_numpy(str)}


def _loss(levels: np.ndarray, q: np.ndarray, y: np.ndarray) -> float:
    d = y[:, None] - q
    return float(np.mean(np.maximum(levels * d, (levels - 1) * d)))


def _best(a: dict, sel: np.ndarray) -> tuple[float, float, float, float]:
    """Grid-search (b, k) on rows `sel`; returns (b, k, loss, loss at b=0,k=1)."""
    lv, lq, m, y = a["levels"], a["lq"][sel], a["m"][sel], a["y"][sel]
    base = _loss(lv, a["q"][sel], y)
    best = (0.0, 1.0, base)
    for b in B_GRID:
        for k in K_GRID:
            loss = _loss(lv, _transform(lq, m, b, k), y)
            if loss < best[2]:
                best = (float(b), float(k), loss)
    return best[0], best[1], best[2], base


def _cov(a: dict, q: np.ndarray, sel: np.ndarray, lo: float, hi: float) -> float:
    i = int(np.argmin(np.abs(a["levels"] - lo)))
    j = int(np.argmin(np.abs(a["levels"] - hi)))
    return float(np.mean((q[:, i] <= a["y"][sel]) & (a["y"][sel] <= q[:, j])))


def fit(rows: pd.DataFrame) -> dict:
    a = _arrays(rows)
    seasons = sorted(set(a["season"]))
    report: dict = {"params": {}, "loso": {}}
    for h in sorted(set(a["h"])):
        sel = a["h"] == h
        b, k, loss, base = _best(a, sel)
        qa = _transform(a["lq"][sel], a["m"][sel], b, k)
        report["params"][int(h)] = {
            "b": b, "k": k, "n": int(sel.sum()), "loss_ratio": loss / base,
            "cov50": [_cov(a, a["q"][sel], sel, .25, .75), _cov(a, qa, sel, .25, .75)],
            "cov90": [_cov(a, a["q"][sel], sel, .05, .95), _cov(a, qa, sel, .05, .95)],
        }
        # Leave one season out: fit on the others, score the held-out season.
        for s in seasons:
            tr, te = sel & (a["season"] != s), sel & (a["season"] == s)
            bt, kt, _, _ = _best(a, tr)
            qt = _transform(a["lq"][te], a["m"][te], bt, kt)
            report["loso"].setdefault(s, {})[int(h)] = {
                "b": bt, "k": kt,
                "loss_ratio": _loss(a["levels"], qt, a["y"][te]) / _loss(a["levels"], a["q"][te], a["y"][te]),
                "cov90": [_cov(a, a["q"][te], te, .05, .95), _cov(a, qt, te, .05, .95)],
            }
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit")
    f.add_argument("rows", nargs="+")
    f.add_argument("--out", default=DEFAULT_PATH)
    args = ap.parse_args()
    rows = pd.concat([pd.read_csv(p, dtype={"location": str}) for p in args.rows], ignore_index=True)
    rep = fit(rows)
    rep["sources"] = [os.path.basename(p) for p in args.rows]
    print(json.dumps(rep, indent=1))
    with open(args.out, "w") as fh:
        json.dump(rep, fh, indent=2)


if __name__ == "__main__":
    main()
