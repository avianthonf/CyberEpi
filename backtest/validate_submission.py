"""Structural validation of a FluSight hub submission directory.

Mirrors hub rule checks from the FluSight-forecast-hub model-output README
(the authoritative check is the hubValidations R package run on the hub PR;
this catches everything locally without R):

  - filename <reference_date>-<model_id>.csv, reference_date is a Saturday
  - exactly the 8 hubverse columns, no more
  - reference_date constant within file, matches filename
  - target_end_date == reference_date + 7*horizon
  - quantile primary target: exactly the 23 required levels per
    (location, horizon), horizons within -1..3
  - values non-negative integers for 'wk inc flu hosp'
  - quantile values non-decreasing within each (location, horizon)
  - locations valid against data/flusight/locations.csv
  - metadata yml carries the required keys and cc-by-4.0-style license

Usage: python3 backtest/validate_submission.py backtest/submission \
           [--model-id CyberEpi-EAKF]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hub_data import PRIMARY_TARGET, STANDARD_QUANTILES, load_locations
COLUMNS = ["reference_date", "target", "horizon", "target_end_date",
           "location", "output_type", "output_type_id", "value"]

REQUIRED_META_KEYS = [
    "team_name", "team_abbr", "model_name", "model_abbr",
    "model_contributors", "license", "designated_model", "data_inputs",
    "methods", "methods_long", "ensemble_of_models", "ensemble_of_hub_models",
    "website_url",
]


class Failures:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def check(self, cond: bool, msg: str) -> None:
        if not cond:
            self.errors.append(msg)


def validate_forecast_file(path: str, model_id: str, valid_locs: set[str]) -> list[str]:
    f = Failures()
    base = os.path.basename(path)
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-(.+)\.csv", base)
    f.check(m is not None, f"{base}: filename must be YYYY-MM-DD-<model_id>.csv")
    if m is None:
        return f.errors
    ref_str, file_model = m.group(1), m.group(2)
    ref = pd.Timestamp(ref_str)
    f.check(ref.dayofweek == 5, f"{base}: reference_date {ref_str} is not a Saturday")
    f.check(file_model == model_id, f"{base}: model id {file_model!r} != {model_id!r}")

    df = pd.read_csv(path, dtype={"location": str, "output_type_id": str})
    f.check(list(df.columns) == COLUMNS or set(df.columns) == set(COLUMNS),
            f"{base}: columns must be exactly {COLUMNS}, got {list(df.columns)}")
    f.check(set(df.columns) == set(COLUMNS), f"{base}: missing/extra columns")

    f.check((df["reference_date"] == ref_str).all(),
            f"{base}: reference_date column must equal filename date everywhere")

    df["target_end_date"] = pd.to_datetime(df["target_end_date"])
    expected_ted = ref + pd.to_timedelta(7 * df["horizon"].astype(int), unit="D")
    f.check(bool((df["target_end_date"] == expected_ted).all()),
            f"{base}: target_end_date != reference_date + 7*horizon for some rows")

    prim = df[df["target"] == PRIMARY_TARGET]
    f.check(bool((prim["output_type"] == "quantile").all()),
            f"{base}: {PRIMARY_TARGET!r} rows must be quantile")
    f.check(bool(prim["horizon"].astype(int).between(-1, 3).all()),
            f"{base}: horizons must be in -1..3")

    vals = pd.to_numeric(prim["value"], errors="coerce")
    f.check(bool(vals.notna().all()), f"{base}: non-numeric values present")
    f.check(bool((vals >= 0).all()), f"{base}: negative values present")
    f.check(bool(np.allclose(vals, np.round(vals))),
            f"{base}: {PRIMARY_TARGET!r} values must be integers")

    want = set(round(float(q), 6) for q in STANDARD_QUANTILES)
    for (loc, h), g in prim.groupby(["location", "horizon"]):
        got = set(round(float(q), 6) for q in g["output_type_id"].astype(float))
        f.check(got == want, f"{base}: loc={loc} h={h}: quantile set mismatch "
                             f"(missing {sorted(want - got)}, extra {sorted(got - want)})")
        gg = g.assign(q=g["output_type_id"].astype(float)).sort_values("q")
        f.check(bool(np.all(np.diff(pd.to_numeric(gg["value"]).to_numpy()) >= 0)),
                f"{base}: loc={loc} h={h}: quantile values not non-decreasing")

    f.check(set(df["location"]).issubset(valid_locs),
            f"{base}: unknown locations {sorted(set(df['location']) - valid_locs)}")
    return f.errors


def validate_metadata(path: str, model_id: str) -> list[str]:
    f = Failures()
    f.check(os.path.basename(path) == f"{model_id}.yml",
            f"{path}: metadata filename must be {model_id}.yml")
    text: str
    with open(path) as fh:
        text = fh.read()
    for key in REQUIRED_META_KEYS:
        f.check(re.search(rf"^{key}:", text, re.M) is not None,
                f"{path}: missing required key {key!r}")
    m = re.search(r"^license:\s*(\S+)", text, re.M)
    f.check(m is not None and m.group(1) in
            {"cc-by-4.0", "cc-by-sa-4.0", "cc0-1.0", "CC-BY-4.0", "MIT", "agpl-3.0"},
            f"{path}: license should be an accepted value (cc-by-4.0 encouraged)")
    return f.errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("submission_dir")
    ap.add_argument("--model-id", default="CyberEpi-EAKF")
    ap.add_argument("--locations-csv",
                    default=os.path.join(os.path.dirname(__file__), "..",
                                         "data", "flusight", "locations.csv"))
    args = ap.parse_args()

    valid_locs = set(load_locations()["location"])
    errors: list[str] = []

    meta = os.path.join(args.submission_dir, "model-metadata", f"{args.model_id}.yml")
    if os.path.exists(meta):
        errors += validate_metadata(meta, args.model_id)
    else:
        errors.append(f"missing metadata file {meta}")

    mo_dir = os.path.join(args.submission_dir, "model-output", args.model_id)
    files = sorted(f for f in os.listdir(mo_dir)) if os.path.isdir(mo_dir) else []
    if not files:
        errors.append(f"no forecast files in {mo_dir}")
    for fn in files:
        errors += validate_forecast_file(os.path.join(mo_dir, fn),
                                         args.model_id, valid_locs)

    if errors:
        print(f"FAIL ({len(errors)} problem(s))")
        for e in errors:
            print(" -", e)
        return 1
    print(f"PASS: {len(files)} forecast file(s) + metadata for {args.model_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
