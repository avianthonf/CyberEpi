"""FluSight hub + CDC feed data access layer for the backtest.

All loaders return clean pandas DataFrames. Locations are 2-digit FIPS strings,
with 'US' for national. Dates are pandas Timestamps (Saturday week-ends unless
noted otherwise).
"""
from __future__ import annotations

import glob
import os
from functools import lru_cache

import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
HUB_DIR = os.path.join(DATA_DIR, "flusight")

# FluSight standard 23 quantile levels (excluding point)
STANDARD_QUANTILES = np.array([
    0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5,
    0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975, 0.99,
])
PRIMARY_TARGET = "wk inc flu hosp"


@lru_cache(maxsize=1)
def load_locations() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(HUB_DIR, "locations.csv"), dtype={"location": str})
    return df[["abbreviation", "location", "location_name", "population"]]


@lru_cache(maxsize=1)
def load_truth() -> pd.DataFrame:
    df = pd.read_csv(
        os.path.join(HUB_DIR, "target-hospital-admissions.csv"),
        parse_dates=["date"], dtype={"location": str},
    )
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])


@lru_cache(maxsize=1)
def load_oracle() -> pd.DataFrame:
    df = pd.read_csv(
        os.path.join(HUB_DIR, "oracle-output.csv"),
        parse_dates=["as_of", "target_end_date"], dtype={"location": str},
    )
    return df[df["target"] == PRIMARY_TARGET].copy()


def reference_dates() -> np.ndarray:
    """All Saturday forecast origin dates present in the truth table."""
    return np.sort(load_truth()["date"].unique())


def load_model_output(model: str) -> pd.DataFrame:
    """Concatenate all weekly files for one hub model (quantile, primary target)."""
    files = sorted(glob.glob(os.path.join(HUB_DIR, "model-output", model, "*.csv")))
    if not files:
        raise FileNotFoundError(f"no model-output files for {model!r}")
    return pd.concat((f for f in (_read_mo(f) for f in files) if f is not None),
                     ignore_index=True)


def _read_mo(path: str) -> pd.DataFrame | None:
    df = pd.read_csv(path, dtype={"location": str, "output_type_id": str})
    keep = (df.get("target") == PRIMARY_TARGET) if "target" in df else pd.Series(True, index=df.index)
    if "output_type" in df:
        keep &= df["output_type"] == "quantile"
    df = df[keep]
    if df.empty:
        return None
    df["output_type_id"] = df["output_type_id"].astype(float)
    df["reference_date"] = pd.to_datetime(df["reference_date"])
    if "target_end_date" in df:
        df["target_end_date"] = pd.to_datetime(df["target_end_date"])
    return df[["reference_date", "horizon", "location", "target_end_date",
               "output_type_id", "value"]]


def nssp_ili_weekly() -> pd.DataFrame:
    """NSSP ED ILI-fraction, aggregated daily -> epi-week (Sun-Sat) per geography.

    Returns columns: (week_end Sat, geography, ili_frac in [0,1]).
    """
    df = pd.read_csv(os.path.join(DATA_DIR, "nssp", "ed_visits.csv"))
    df = df.loc[df["pathogen"] == "Influenza", ["date", "geography", "percent_visits"]]
    df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y %I:%M:%S %p")
    # Epi week: week ENDS on Saturday. weeks bin: days Sun..Sat -> label by Sat.
    df["week_end"] = df["date"].dt.to_period("W-SAT").dt.end_time.dt.normalize()
    wk = df.groupby(["week_end", "geography"], as_index=False)["percent_visits"].mean()
    wk["ili_frac"] = wk["percent_visits"] / 100.0
    return wk[["week_end", "geography", "ili_frac"]]


def nssp_ili_by_location() -> pd.DataFrame:
    """NSSP ILI fraction weekly, keyed by hub location (FIPS or 'US').

    'US' = population-weighted mean over states reporting that week.
    """
    wk = nssp_ili_weekly()
    locs = load_locations()
    name2fips = dict(zip(locs["location_name"], locs["location"]))
    wk["location"] = wk["geography"].map(name2fips)
    wk = wk.dropna(subset=["location"])[["week_end", "location", "ili_frac"]]
    pops = locs.set_index("location")["population"]
    wk["pop"] = wk["location"].map(pops)
    us = (wk.assign(w=lambda d: d["ili_frac"] * d["pop"])
            .groupby("week_end").agg(w=("w", "sum"), p=("pop", "sum")).reset_index())
    us["ili_frac"] = us["w"] / us["p"]
    us["location"] = "US"
    return pd.concat([wk[["week_end", "location", "ili_frac"]],
                      us[["week_end", "location", "ili_frac"]]], ignore_index=True)


def nwss_flu_weekly() -> pd.DataFrame:
    """NWSS Influenza A wastewater state-level weekly levels (Site_WVAL)."""
    df = pd.read_csv(os.path.join(DATA_DIR, "nwss", "wastewater.csv"))
    df = df.loc[df["Pathogen_Target"] == "Influenza A virus", :].copy()
    df["week_end"] = pd.to_datetime(df["Week_End"])
    df["wval"] = pd.to_numeric(df["Site_WVAL"], errors="coerce")
    st = df.groupby(["week_end", "State/Territory"], as_index=False)["wval"].mean()
    return st.rename(columns={"State/Territory": "state"})


def validate_downloads() -> dict:
    """Quick sanity report on all local datasets."""
    rep: dict[str, dict] = {}
    tr = load_truth()
    rep["flusight_targets"] = {
        "rows": len(tr), "date_min": str(tr["date"].min().date()),
        "date_max": str(tr["date"].max().date()), "locations": tr["location"].nunique(),
    }
    for m in ("FluSight-baseline", "FluSight-ensemble"):
        mo = load_model_output(m)
        rep[f"model_output/{m}"] = {
            "rows": len(mo), "origins": int(mo["reference_date"].nunique()),
            "horizons": sorted(mo["horizon"].unique().tolist()),
        }
    il = nssp_ili_weekly()
    rep["nssp_ili"] = {"rows": len(il), "weeks": il["week_end"].nunique()}
    nw = nwss_flu_weekly()
    rep["nwss_flu"] = {"rows": len(nw), "weeks": nw["week_end"].nunique()}
    return rep


if __name__ == "__main__":
    import json
    print(json.dumps(validate_downloads(), indent=2))
