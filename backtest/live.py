"""Weekly live forecast for the CDC FluSight challenge.

One command does the whole week:

1. links the hub data files from a FluSight-forecast-hub checkout into
   data/flusight/ (the layout the backtest loaders expect);
2. checks the data is fresh: the newest admissions week must be the week
   ending one week before the reference date, otherwise it stops (the CDC
   releases data on Wednesdays; running too early would forecast from
   last week's data);
3. forecasts every location with the frozen settings in model_config.json;
4. writes hub-format files (model-output CSV + model-metadata) and runs the
   structural validator.

It never submits anything. Opening the pull request to the CDC hub is a
manual, owner-approved step (ROADMAP.md, checkpoint B).

Usage:
    python3 backtest/live.py --hub /path/to/FluSight-forecast-hub \
        [--reference-date 2026-11-28] [--out forecasts]

Reference date defaults to the Saturday ending the current week in US Eastern
time (the hub's definition: the Saturday following the Wednesday due date).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data", "flusight")

# data/flusight/<name>  <-  <hub>/<path>
HUB_FILES = {
    "locations.csv": "auxiliary-data/locations.csv",
    "target-hospital-admissions.csv": "target-data/target-hospital-admissions.csv",
    "target-ed-visits-prop.csv": "target-data/target-ed-visits-prop.csv",
}


def default_reference_date(today: dt.date) -> dt.date:
    """Saturday ending the epiweek (Sun-Sat) that contains `today`."""
    return today + dt.timedelta(days=(5 - today.weekday()) % 7)


def link_hub(hub: str) -> None:
    os.makedirs(DATA, exist_ok=True)
    for name, rel in HUB_FILES.items():
        src = os.path.join(os.path.abspath(hub), rel)
        if not os.path.exists(src):
            raise SystemExit(f"hub checkout is missing {rel}")
        dst = os.path.join(DATA, name)
        if os.path.lexists(dst):
            os.remove(dst)
        os.symlink(src, dst)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", required=True, help="path to a FluSight-forecast-hub checkout")
    ap.add_argument("--reference-date", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "forecasts"))
    ap.add_argument("--ncpus", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--team", default="CyberEpi")
    ap.add_argument("--model", default="EAKF")
    ap.add_argument("--name", default=os.environ.get("FORECAST_CONTRIBUTOR_NAME", ""))
    ap.add_argument("--email", default=os.environ.get("FORECAST_CONTRIBUTOR_EMAIL", ""))
    ap.add_argument("--affiliation", default=os.environ.get("FORECAST_CONTRIBUTOR_AFFILIATION", "Independent"))
    ap.add_argument("--allow-stale", action="store_true",
                    help="forecast even if this week's data is not out yet (testing only)")
    args = ap.parse_args()

    ref = (dt.date.fromisoformat(args.reference_date) if args.reference_date
           else default_reference_date(dt.datetime.now(ZoneInfo("America/New_York")).date()))
    if ref.weekday() != 5:
        raise SystemExit(f"reference date must be a Saturday, got {ref}")

    link_hub(args.hub)
    sys.path.insert(0, HERE)
    import pandas as pd
    from hub_data import load_locations, load_truth
    from run_flusight import prospective

    newest = load_truth()["date"].max().date()
    expected = ref - dt.timedelta(days=7)
    print(f"reference date {ref}; newest admissions week {newest}; expected {expected}")
    if newest < expected and not args.allow_stale:
        print("STALE: this week's CDC data is not in the hub checkout yet; not forecasting.")
        return 2
    if newest > expected:
        raise SystemExit("hub data is newer than the reference date; wrong --reference-date?")

    with open(os.path.join(HERE, "model_config.json")) as f:
        cfg = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    locations = ",".join(load_locations()["location"])
    work = os.path.join(args.out, "_work")
    os.makedirs(work, exist_ok=True)
    label = f"{args.team}-{args.model}"
    prospective(str(ref), SimpleNamespace(**cfg, locations=locations, ncpus=args.ncpus,
                                          out=work, label=label))
    rows_csv = os.path.join(work, f"rows-{label}-{ref}.csv")

    rows = pd.read_csv(rows_csv, dtype={"location": str})
    print(f"{rows['location'].nunique()} locations, horizons {sorted(rows['horizon'].unique())}")

    subprocess.run([sys.executable, os.path.join(HERE, "package_submission.py"), rows_csv,
                    "--team", args.team, "--model", args.model, "--out", args.out,
                    "--name", args.name, "--email", args.email,
                    "--affiliation", args.affiliation], check=True)
    draft = not (args.name and args.email)
    cmd = [sys.executable, os.path.join(HERE, "validate_submission.py"),
           args.out, "--model-id", label, "--hub", args.hub]
    if draft:
        cmd.append("--allow-empty-contributor")
    rc = subprocess.run(cmd).returncode
    if rc == 0 and draft:
        print("DRAFT: forecast is valid; contributor name/email not set, so not yet submittable.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
