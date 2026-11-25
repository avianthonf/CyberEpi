"""Pre-registered tuning for the honest backtest.

Rule (fixed before any test-season result was seen):
  * tune on season 2023-24 only, with as-of (vintage) admissions;
  * candidate grid below (16 configs);
  * select the config with the lowest relWIS vs FluSight-baseline among
    those with cov90 >= 0.85 (all 53 locations, horizons 0..3);
  * freeze it; score 2024-25 and 2025-26 once with run_vintage.py.

Usage: python3 backtest/tune_vintage.py --ncpus 4
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "honest", "tune")
GRID = {
    "sd_beta": [0.03, 0.05],
    "s_obs": [0.04, 0.10],
    "sd_beta_fwd": [0.03, 0.05],
    "ili": ["none", "final"],
}
TUNE_SEASON = "2023-24"
MIN_COV90 = 0.85


def label(c: dict) -> str:
    return f"tune-b{c['sd_beta']}-o{c['s_obs']}-f{c['sd_beta_fwd']}-{c['ili']}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ncpus", type=int, default=4)
    ap.add_argument("--locations", required=True)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    results = []
    for vals in itertools.product(*GRID.values()):
        c = dict(zip(GRID, vals, strict=True))
        lab = label(c)
        summ_path = os.path.join(OUT, f"summary-{lab}.json")
        if not os.path.exists(summ_path):
            cmd = [sys.executable, os.path.join(HERE, "run_vintage.py"),
                   "--seasons", TUNE_SEASON, "--locations", args.locations,
                   "--ncpus", str(args.ncpus), "--out", OUT, "--label", lab,
                   "--sd-beta", str(c["sd_beta"]), "--s-obs", str(c["s_obs"]),
                   "--sd-beta-fwd", str(c["sd_beta_fwd"]), "--ili", c["ili"]]
            subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        s = json.load(open(summ_path))["seasons"][TUNE_SEASON]["FluSight-baseline"]
        results.append({**c, "relWIS": s["relWIS"], "cov50": s["cov50"], "cov90": s["cov90"]})
        print(results[-1], flush=True)

    ok = [r for r in results if r["cov90"] >= MIN_COV90]
    chosen = min(ok or results, key=lambda r: r["relWIS"])
    with open(os.path.join(OUT, "selection.json"), "w") as f:
        json.dump({"rule": __doc__.strip(), "grid": results, "chosen": chosen,
                   "coverage_rule_met": bool(ok)}, f, indent=2)
    print("CHOSEN", chosen)


if __name__ == "__main__":
    main()
