"""
Rent figures for Where to Live SG, from rent_contracts.csv (written by rent_manual.py in Gate 2).

Each row of rent_contracts.csv is one real URA rental contract that was already filtered to:
non-landed private homes, within 1 km of the area's MRT station, in the latest 4 quarters.
This file only counts and summarises those contracts for the family's bedrooms and budget.
Nothing is estimated: too few contracts -> the status says so and no figure is shown.
"""

import pandas as pd

MIN_CONTRACTS = 5   # set this to the same value as MIN_CONTRACTS in rent_manual.py

# Columns that identify one contract. "family" is left out on purpose:
# the Gate 2 file can list the same contract once per family.
KEY_COLS = ["area", "project", "bedrooms", "area_sqm", "rent_sgd",
            "lease_month", "lease_mmyy", "quarter", "source_file", "source_row"]


HOME_TYPES = ["condo", "ec", "landed"]   # internal keys; the page translates them


def home_type_of(property_type):
    """Group URA property types into the three choices the family sees."""
    t = str(property_type).lower()
    if "executive" in t:
        return "ec"
    if any(w in t for w in ("landed properties",)) and "non" not in t:
        return "landed"
    if any(w in t for w in ("house", "terrace", "detached", "bungalow", "cluster")):
        return "landed"
    return "condo"


def load_contracts(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    need = {"area", "bedrooms", "rent_sgd"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError("rent_contracts.csv is missing columns: " + ", ".join(sorted(missing)))
    df["bedrooms"] = pd.to_numeric(df["bedrooms"], errors="coerce")
    df["rent_sgd"] = pd.to_numeric(df["rent_sgd"].astype(str).str.replace(",", ""), errors="coerce")
    if "area_sqm" in df.columns:
        df["area_sqm_num"] = pd.to_numeric(df["area_sqm"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    df["home_type"] = df["property_type"].map(home_type_of) if "property_type" in df.columns else "condo"
    keys = [c for c in KEY_COLS if c in df.columns]
    df = df.drop_duplicates(subset=keys).dropna(subset=["bedrooms", "rent_sgd"])
    return df


def _pct(values, p):
    # Same method as the Gate 2 script: linear between the two nearest values.
    s = sorted(values)
    k = (len(s) - 1) * p
    f, c = int(k // 1), int(-(-k // 1))
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def summary(df, area, bedrooms, budget_min, budget_max, sqm_min=None, sqm_max=None, home_type=("condo",)):
    types = [home_type] if isinstance(home_type, str) else list(home_type)
    rows = df[(df["area"] == area) & (df["bedrooms"] == bedrooms) & (df["home_type"].isin(types))]
    if sqm_min is not None and "area_sqm_num" in rows:
        rows = rows[rows["area_sqm_num"] >= sqm_min]
    if sqm_max is not None and "area_sqm_num" in rows:
        rows = rows[rows["area_sqm_num"] <= sqm_max]
    rents = rows["rent_sgd"].tolist()
    n = len(rents)
    out = {"n": n, "p25": None, "median": None, "p75": None,
           "in_budget": sum(budget_min <= r <= budget_max for r in rents)}
    if n == 0:
        out["status"] = "NONE FOUND"
    elif n < MIN_CONTRACTS:
        out["status"] = "TOO FEW (<%d)" % MIN_CONTRACTS
    else:
        out["status"] = "OK"
        out.update({"p25": round(_pct(rents, .25)), "median": round(_pct(rents, .5)),
                    "p75": round(_pct(rents, .75))})
    return out


def bedrooms_available(df):
    return sorted(int(b) for b in df["bedrooms"].dropna().unique())


def home_types_available(df):
    have = set(df["home_type"].unique())
    return [h for h in HOME_TYPES if h in have]
