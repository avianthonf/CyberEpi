"""Parameter sweep for the EAKF flu harness (calibration phase)."""
from __future__ import annotations

import itertools
import json
import sys

import pandas as pd

from hub_data import load_locations, load_model_output, load_oracle, load_truth
from run_flusight import SEASONS, run_location, summarize
from eakf import EakfConfig

LOCS = "US,06,48".split(",")
SEASON = "2024-25"

truth = load_truth()
oracle = load_oracle()
baseline = load_model_output("FluSight-baseline")
baseline["output_type_id"] = baseline["output_type_id"].astype(float)
locs = load_locations().set_index("location")

from run_flusight import season_origins
origins = set(season_origins(baseline, SEASON))

results = []
for sd_beta, r_rel, s_obs, sbf in itertools.product(
        [0.01, 0.02, 0.03], [0.20, 0.30], [0.01, 0.04], [0.03, 0.05, 0.08]):
    rows_per = []
    for loc in LOCS:
        pop = float(locs.loc[loc, "population"])
        tw = truth[truth["location"] == loc].set_index("date")["value"]
        cfg = EakfConfig(n_members=150, sd_beta=sd_beta, sd_hir=0.005,
                         r_rel=r_rel, inflation=1.01, s_obs=s_obs,
                         sd_beta_fwd=sbf, seed=1)
        rows, _ = run_location(loc, pop, tw, cfg, origins,
                               SEASONS[SEASON][0], SEASONS[SEASON][1], 7)
        if rows:
            rows_per.append(pd.DataFrame(rows))
    if not rows_per:
        continue
    rdf = pd.concat(rows_per, ignore_index=True)
    summ, _ = summarize(rdf, oracle, baseline, f"sweep")
    results.append({"sd_beta": sd_beta, "r_rel": r_rel, "s_obs": s_obs,
                    "sd_beta_fwd": sbf, **{k: summ[k] for k in
                                           ("relWIS", "wis_mean", "cov50", "cov90", "cov95")}})
    print(results[-1])

out = pd.DataFrame(results).sort_values("relWIS")
out.to_csv("backtest/out/flu/sweep.csv", index=False)
print(out.head(8).to_string(index=False))
