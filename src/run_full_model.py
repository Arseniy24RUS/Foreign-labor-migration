#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end reproducible model of residual foreign labor migration need.

The core identity is unchanged:
    real output = employment * labor productivity.

Required employment is projected from target real GRP growth and productivity
growth. Foreign labor migration need is then computed as the non-negative
residual deficit after domestic employment capacity from the noMIG population
scenario is allocated to region-sector cells.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


TRUE_VALUES = {"true", "1", "yes", "y", "да", "истина"}
LEGACY_PRODUCTIVITY_SCENARIOS = ("baseline", "low_productivity", "high_productivity")
CHAMPION_PRODUCTIVITY_SCENARIO = "champion"
PRODUCTIVITY_SCENARIOS = LEGACY_PRODUCTIVITY_SCENARIOS + (CHAMPION_PRODUCTIVITY_SCENARIO,)
WORKING_AGE_DEFINITIONS = {"15-64": (15, 64), "15-69": (15, 69), "15-72": (15, 72)}
LEGACY_SUPPLY_ALLOCATION_SCENARIOS = ("fixed_2024_sector_shares", "demand_weighted_sector_shares", "bounded_transition")
SUPPLY_ALLOCATION_SCENARIOS = LEGACY_SUPPLY_ALLOCATION_SCENARIOS + ("empirical_bounded_transition",)
UNEMPLOYMENT_RESERVE_POLICIES = ("none", "equal_sector_split", "supply_share_split")
DEFAULT_UNEMPLOYMENT_RATE_PATH = "data/processed/unemployment_rate_ilo_15plus_2017_2025_matched.csv"
PRIMARY_WORLD_GROWTH_SOURCE = "OECD Economic Outlook 117 long-term scenarios / OECD Long-Term Model"
PRIMARY_WORLD_GROWTH_URL = "https://www.oecd.org/en/topics/sub-issues/economic-outlook/long-run-economic-scenarios-2025-update.html"
WORLD_GROWTH_ACCESS_DATE = "2026-05-27"
V5_PRODUCTIVITY_MODEL = "hierarchical_mean_reverting_factor_productivity_forecast"
CONTROL_YEARS = (2030, 2036, 2050)


def as_bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(TRUE_VALUES)


def normalize_name(value: object) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip().lower().replace("ё", "е")
    s = re.sub(r"[\u2010-\u2015−–—]", "-", s)
    s = re.sub(r"[\.,;:'\"`«»()\[\]]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    repl = {
        "ханты мансийский автономный округ югра": "ханты-мансийский автономный округ - югра",
        "ханты-мансийский автономный округ югра": "ханты-мансийский автономный округ - югра",
        "ямало ненецкий автономный округ": "ямало-ненецкий автономный округ",
        "северная осетия алания": "республика северная осетия - алания",
        "республика северная осетия алания": "республика северная осетия - алания",
    }
    return repl.get(s, s)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_safe(value: object) -> object:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def find_population_files(population_dir: Path, scenario: str) -> tuple[Path, Path]:
    male_name = f"POP_wide_male_{scenario}.xlsx"
    female_name = f"POP_wide_female_{scenario}.xlsx"
    for d in [population_dir] + [p for p in population_dir.glob("**/") if p.is_dir()]:
        male = d / male_name
        female = d / female_name
        if male.exists() and female.exists():
            return male, female
    raise FileNotFoundError(f"Population files {male_name} and {female_name} were not found under {population_dir}")


def parse_age_label(label: object) -> int | None:
    text = str(label).strip()
    if re.fullmatch(r"\d+\+?", text):
        return int(re.match(r"\d+", text).group(0))
    return None


def read_population_by_age_xlsx(path: Path, sex: str, scenario: str) -> pd.DataFrame:
    """Read repository POP_wide files with by_age sheet: Territory, Year, age columns."""
    df = pd.read_excel(path, sheet_name="by_age")
    df.columns = [str(c).strip() for c in df.columns]
    if len(df.columns) < 3:
        raise ValueError(f"Population sheet by_age in {path} has too few columns")

    territory_col = next((c for c in df.columns if c.lower() in {"территория", "territory", "region"}), df.columns[0])
    year_col = next((c for c in df.columns if c.lower() in {"год", "year"}), df.columns[1])
    age_cols = [c for c in df.columns if parse_age_label(c) is not None]
    if not age_cols:
        raise ValueError(f"No age columns found in by_age sheet of {path}")

    out = df[[territory_col, year_col] + age_cols].copy()
    out[territory_col] = out[territory_col].ffill()
    out = out.dropna(subset=[territory_col, year_col])
    out = out.melt(
        id_vars=[territory_col, year_col],
        value_vars=age_cols,
        var_name="age_label",
        value_name="population_persons",
    )
    out = out.rename(columns={territory_col: "territory_name_population", year_col: "year"})
    out["age"] = out["age_label"].map(parse_age_label).astype(int)
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out["population_persons"] = pd.to_numeric(out["population_persons"], errors="coerce")
    out = out.dropna(subset=["year", "population_persons"])
    out["year"] = out["year"].astype(int)
    out["territory_name_population"] = out["territory_name_population"].astype(str).str.strip()
    out["territory_norm"] = out["territory_name_population"].map(normalize_name)
    out["sex"] = sex
    out["population_scenario"] = scenario
    out = out.sort_values(["territory_name_population", "sex", "year", "age"])
    return out[
        [
            "territory_name_population",
            "territory_norm",
            "sex",
            "age",
            "age_label",
            "year",
            "population_persons",
            "population_scenario",
        ]
    ]


def read_population_scenario(population_dir: Path, scenario: str) -> tuple[pd.DataFrame, dict]:
    male, female = find_population_files(population_dir, scenario)
    pop = pd.concat(
        [
            read_population_by_age_xlsx(male, "male", scenario),
            read_population_by_age_xlsx(female, "female", scenario),
        ],
        ignore_index=True,
    )
    qa = {
        "population_files": [str(male), str(female)],
        "rows": int(len(pop)),
        "territories": int(pop["territory_norm"].nunique()),
        "years": [int(pop["year"].min()), int(pop["year"].max())],
        "ages": [int(pop["age"].min()), int(pop["age"].max())],
        "negative_cells": int((pop["population_persons"] < 0).sum()),
        "missing_population_cells": int(pop["population_persons"].isna().sum()),
    }
    if qa["negative_cells"] or qa["missing_population_cells"]:
        raise ValueError(f"Population data failed numeric QA: {qa}")
    return pop, qa


def read_population_scenario_cached(population_dir: Path, scenario: str, cache_path: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Read population scenario from a cache CSV when available, otherwise from XLSX.

    The demographic XLSX parser is deliberately retained for reproducibility, but
    the already-produced long CSV is much faster for iterative model runs.
    """
    if cache_path is not None and cache_path.exists():
        pop = pd.read_csv(cache_path)
        required = {"territory_name_population", "territory_norm", "sex", "age", "year", "population_persons"}
        missing = [c for c in required if c not in pop.columns]
        if missing:
            raise ValueError(f"Population cache is missing required columns: {missing}")
        pop["age"] = pd.to_numeric(pop["age"], errors="coerce").astype(int)
        pop["year"] = pd.to_numeric(pop["year"], errors="coerce").astype(int)
        pop["population_persons"] = pd.to_numeric(pop["population_persons"], errors="coerce")
        if "population_scenario" not in pop.columns:
            pop["population_scenario"] = scenario
        qa = {
            "population_files": [str(cache_path)],
            "cache_used": True,
            "rows": int(len(pop)),
            "territories": int(pop["territory_norm"].nunique()),
            "years": [int(pop["year"].min()), int(pop["year"].max())],
            "ages": [int(pop["age"].min()), int(pop["age"].max())],
            "negative_cells": int((pop["population_persons"] < 0).sum()),
            "missing_population_cells": int(pop["population_persons"].isna().sum()),
        }
        if qa["negative_cells"] or qa["missing_population_cells"]:
            raise ValueError(f"Population cache failed numeric QA: {qa}")
        return pop, qa
    pop, qa = read_population_scenario(population_dir, scenario)
    qa["cache_used"] = False
    return pop, qa

def read_world_growth(path: Path, start_year: int, end_year: int) -> tuple[pd.DataFrame, dict]:
    wg = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in wg.columns}
    year_col = cols.get("year") or cols.get("forecast_year")
    if year_col is None:
        raise ValueError(f"World growth scenario has no year/forecast_year column: {path}")

    preferred = [
        "world_real_gdp_growth_target_pct",
        "target_real_vrp_growth_pct",
        "target_real_vrp_growth",
        "world_growth_target",
        "target_growth",
    ]
    growth_col = next((cols[c] for c in preferred if c in cols), None)
    if growth_col is None:
        numeric_cols = [c for c in wg.columns if c != year_col and pd.api.types.is_numeric_dtype(wg[c])]
        if not numeric_cols:
            raise ValueError(f"World growth scenario has no numeric growth column: {path}")
        growth_col = numeric_cols[0]

    meta_cols = [c for c in ["source", "source_url", "scenario", "note"] if c in wg.columns]
    out = wg[[year_col, growth_col] + meta_cols].copy().rename(columns={year_col: "forecast_year", growth_col: "target_growth_raw"})
    out["forecast_year"] = out["forecast_year"].astype(int)
    out["target_real_vrp_growth"] = pd.to_numeric(out["target_growth_raw"], errors="coerce")
    if str(growth_col).lower().endswith("_pct") or str(growth_col).lower().endswith("pct"):
        out["target_real_vrp_growth"] = out["target_real_vrp_growth"] / 100.0
        unit_rule = "pct_column_divided_by_100"
    else:
        mask = out["target_real_vrp_growth"].abs() > 1
        out.loc[mask, "target_real_vrp_growth"] = out.loc[mask, "target_real_vrp_growth"] / 100.0
        unit_rule = "decimal_column_or_percent_heuristic"

    years = pd.DataFrame({"forecast_year": range(start_year, end_year + 1)})
    is_oecd_ltm = (
        "oecd" in str(path).lower()
        or ("source" in wg.columns and wg["source"].astype(str).str.contains("OECD", case=False, na=False).any())
    )
    keep_cols = ["forecast_year", "target_real_vrp_growth"] + meta_cols
    out = years.merge(out[keep_cols], on="forecast_year", how="left")
    if is_oecd_ltm:
        missing_years = out.loc[out["target_real_vrp_growth"].isna(), "forecast_year"].astype(int).tolist()
        if missing_years:
            raise ValueError(
                "OECD LTM world growth input is incomplete; model v5 will not use fill-forward/backward. "
                f"Missing years: {missing_years}; path: {path}"
            )
        if "source" in out.columns and not out["source"].astype(str).str.contains("OECD", case=False, na=False).all():
            raise ValueError("OECD LTM input must carry an OECD source label in every row.")
    else:
        out["target_real_vrp_growth"] = out["target_real_vrp_growth"].ffill().bfill()
    if out["target_real_vrp_growth"].isna().any():
        raise ValueError("World growth scenario has unresolved missing values")
    post_2027 = out.loc[out["forecast_year"].gt(2027), "target_real_vrp_growth"]
    flat_imf_32 = bool(len(post_2027) and np.allclose(post_2027.to_numpy(dtype=float), 0.032, rtol=0, atol=1e-6))
    if is_oecd_ltm and flat_imf_32:
        raise ValueError("OECD LTM validation failed: post-2027 values look like a flat IMF 3.2% technical extension.")

    source = str(wg["source"].dropna().iloc[0]) if "source" in wg.columns and wg["source"].notna().any() else PRIMARY_WORLD_GROWTH_SOURCE
    source_url = str(wg["source_url"].dropna().iloc[0]) if "source_url" in wg.columns and wg["source_url"].notna().any() else PRIMARY_WORLD_GROWTH_URL
    scenario = str(wg["scenario"].dropna().iloc[0]) if "scenario" in wg.columns and wg["scenario"].notna().any() else ""
    if is_oecd_ltm and "OECD" not in source.upper():
        raise ValueError(f"Expected OECD LTM source label, got: {source}")

    qa = {
        "path": str(path),
        "growth_column": growth_col,
        "unit_rule": unit_rule,
        "years": [int(out["forecast_year"].min()), int(out["forecast_year"].max())],
        "source": source,
        "source_url": source_url,
        "scenario": scenario,
        "is_oecd_ltm": bool(is_oecd_ltm),
        "flat_imf_32_after_2027": flat_imf_32,
        "access_date": WORLD_GROWTH_ACCESS_DATE,
    }
    return out[["forecast_year", "target_real_vrp_growth"] + meta_cols], qa


def read_unemployment_rates(path: Path | None, start_year: int, end_year: int) -> tuple[pd.DataFrame, dict]:
    """Read matched ILO unemployment-rate data and expand it to forecast years.

    The indicator is a percentage of the labour force aged 15+. If forecast years
    exceed the official period, the latest available regional value is carried
    forward. This creates a conservative, transparent reserve layer; it is not a
    structural unemployment forecast.
    """
    if path is None or str(path).strip() == "":
        return pd.DataFrame(), {"status": "disabled", "reason": "no_path"}
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(), {"status": "disabled", "reason": f"path_not_found:{path}"}

    if path.suffix.lower() in {".xlsx", ".xls"}:
        # Lightweight fallback for users who pass the raw workbook directly.
        # The project patch also provides src/parse_unemployment_rate_ilo.py;
        # the model itself accepts raw xlsx to remain self-contained.
        raw = pd.read_excel(path, sheet_name="Данные")
        territory_col = raw.columns[0]
        year_cols: list[tuple[object, int]] = []
        for col in raw.columns[1:]:
            try:
                year = int(float(col))
            except Exception:
                continue
            if 1900 <= year <= 2200:
                year_cols.append((col, year))
        rows = []
        for _, row in raw.iterrows():
            name = str(row[territory_col]).strip()
            if not name or name.lower() == "nan":
                continue
            for col, year in year_cols:
                rows.append(
                    {
                        "territory_name": name,
                        "territory_norm": normalize_name(name),
                        "year": year,
                        "unemployment_rate_ilo_15plus_pct": pd.to_numeric(row[col], errors="coerce"),
                    }
                )
        df = pd.DataFrame(rows)
    else:
        df = pd.read_csv(path)

    if "territory_id" not in df.columns and "territory_name" not in df.columns and "territory_name_source" in df.columns:
        df = df.rename(columns={"territory_name_source": "territory_name"})
    if "territory_norm" not in df.columns:
        territory_col = "territory_name" if "territory_name" in df.columns else "territory_name_source"
        df["territory_norm"] = df[territory_col].map(normalize_name)

    required = {"year", "unemployment_rate_ilo_15plus_pct"}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Unemployment-rate data is missing required columns: {missing}")
    if "territory_id" not in df.columns:
        # Territory-id matching is intentionally not performed here; direct raw-xlsx
        # mode can be used only if territory_norm later matches the economic base.
        df["territory_id"] = ""
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["unemployment_rate_ilo_15plus_pct"] = pd.to_numeric(df["unemployment_rate_ilo_15plus_pct"], errors="coerce")
    df = df.dropna(subset=["year", "unemployment_rate_ilo_15plus_pct"]).copy()
    df["year"] = df["year"].astype(int)
    if df["unemployment_rate_ilo_15plus_pct"].lt(0).any() or df["unemployment_rate_ilo_15plus_pct"].ge(100).any():
        raise ValueError("Unemployment rate must be in [0, 100) percent")

    key_cols = ["territory_id"] if df["territory_id"].astype(str).str.len().gt(0).any() else ["territory_norm"]
    compact_cols = key_cols + ["territory_norm", "year", "unemployment_rate_ilo_15plus_pct"]
    if "territory_name" in df.columns:
        compact_cols.insert(len(key_cols), "territory_name")
    compact_cols = list(dict.fromkeys([c for c in compact_cols if c in df.columns]))
    compact = df[compact_cols].drop_duplicates(key_cols + ["year"]).sort_values(key_cols + ["year"])

    years = pd.DataFrame({"forecast_year": range(start_year, end_year + 1)})
    expanded_pieces = []
    for _, group in compact.groupby(key_cols, dropna=False):
        group = group.sort_values("year")
        meta = {c: group.iloc[0][c] for c in group.columns if c not in {"year", "unemployment_rate_ilo_15plus_pct"}}
        g = years.copy()
        hist = group[["year", "unemployment_rate_ilo_15plus_pct"]].rename(columns={"year": "forecast_year"})
        g = g.merge(hist, on="forecast_year", how="left")
        # For forecast years beyond the official series, carry latest official regional value forward.
        # For an early missing year, use the closest available value backward.
        g["unemployment_rate_ilo_15plus_pct"] = g["unemployment_rate_ilo_15plus_pct"].ffill().bfill()
        latest_year_used = int(group["year"].max())
        g["unemployment_rate_source_year_used"] = np.minimum(g["forecast_year"], latest_year_used)
        for col, value in meta.items():
            g[col] = value
        expanded_pieces.append(g)
    expanded = pd.concat(expanded_pieces, ignore_index=True) if expanded_pieces else pd.DataFrame()
    qa = {
        "status": "loaded",
        "path": str(path),
        "rows_raw": int(len(df)),
        "territories": int(compact[key_cols[0]].nunique()) if len(compact) else 0,
        "official_years": [int(df["year"].min()), int(df["year"].max())] if len(df) else [],
        "forecast_years": [start_year, end_year],
        "future_rule": "carry_latest_available_regional_rate_forward",
        "reserve_formula": "unemployed = employed * u_pct / (100 - u_pct)",
    }
    return expanded, qa

def load_economic_base(panel_path: Path, base_year: int, audit_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    panel = pd.read_csv(panel_path)
    required = [
        "territory_id",
        "territory_name",
        "activity_id",
        "activity_name",
        "year",
        "employment_persons",
        "is_nonoverlap_model_region",
        "is_model_activity",
    ]
    missing = [c for c in required if c not in panel.columns]
    if missing:
        raise ValueError(f"Economic panel is missing required columns: {missing}")

    model = panel[as_bool(panel["is_nonoverlap_model_region"]) & as_bool(panel["is_model_activity"])].copy()
    model["year"] = model["year"].astype(int)
    model["employment_persons"] = pd.to_numeric(model["employment_persons"], errors="coerce")
    if model.duplicated(["territory_id", "activity_id", "year"]).any():
        raise ValueError("Economic model panel has duplicate territory_id/activity_id/year keys")

    base_all = model[model["year"] == base_year].copy()
    excluded = base_all[~(base_all["employment_persons"] > 0)].copy()
    excluded["exclusion_reason"] = "missing_or_nonpositive_base_year_employment"
    write_csv(excluded, audit_dir / "excluded_base_cells_2024.csv")

    base = base_all[base_all["employment_persons"] > 0].copy()
    if base.empty:
        raise ValueError(f"No positive base-year employment rows found for {base_year}")
    base["territory_norm"] = base["territory_name"].map(normalize_name)

    prod_col = "productivity_per_employee_thousand_rub_2016"
    if prod_col not in model.columns:
        prod_col = "labour_productivity_constant_2016_thousand_rub_per_person"
    model["productivity_real"] = pd.to_numeric(model.get(prod_col), errors="coerce")
    model["official_prod_index_hybrid_pct"] = pd.to_numeric(model.get("official_productivity_index_hybrid_pct"), errors="coerce")

    hist = model[(model["year"].between(2017, 2022)) & (model["productivity_real"] > 0)][
        ["territory_id", "activity_id", "year", "productivity_real"]
    ]
    piv = hist.pivot_table(index=["territory_id", "activity_id"], columns="year", values="productivity_real", aggfunc="mean")
    if 2017 in piv.columns and 2022 in piv.columns:
        cagr = ((piv[2022] / piv[2017]) ** (1 / 5) - 1).replace([np.inf, -np.inf], np.nan)
    else:
        cagr = pd.Series(np.nan, index=piv.index)
    cagr = cagr.rename("historical_productivity_cagr_2017_2022_raw").reset_index()

    base = base.merge(cagr, on=["territory_id", "activity_id"], how="left")
    base["historical_productivity_cagr_2017_2022"] = base["historical_productivity_cagr_2017_2022_raw"].clip(-0.10, 0.15)
    base["official_prod_index_hybrid_pct"] = pd.to_numeric(base.get("official_productivity_index_hybrid_pct"), errors="coerce")
    base["official_productivity_growth_from_index"] = base["official_prod_index_hybrid_pct"] / 100.0 - 1.0
    base["official_productivity_growth_for_model"] = base["official_productivity_growth_from_index"].clip(-0.10, 0.15)
    base["sector_productivity_cagr_median"] = base.groupby("activity_id")["historical_productivity_cagr_2017_2022"].transform("median")
    base["region_productivity_cagr_median"] = base.groupby("territory_id")["historical_productivity_cagr_2017_2022"].transform("median")
    global_cagr = float(base["historical_productivity_cagr_2017_2022"].median(skipna=True))
    if not np.isfinite(global_cagr):
        global_cagr = 0.02
    base["global_productivity_cagr_median"] = global_cagr

    return model, base, excluded


def productivity_forecast(base: pd.DataFrame, scenario: str) -> pd.DataFrame:
    shifts = {"baseline": 0.0, "low_productivity": -0.01, "high_productivity": 0.01}
    if scenario not in shifts:
        raise ValueError(f"Unknown productivity scenario: {scenario}")

    def shrink(row: pd.Series) -> tuple[float, str]:
        sources: list[tuple[str, float, float]] = []
        if pd.notna(row.get("official_productivity_growth_for_model")):
            sources.append(("official_hybrid_index_2024", float(row["official_productivity_growth_for_model"]), 0.35))
        for col, label, weight in [
            ("historical_productivity_cagr_2017_2022", "cell_historical_cagr_2017_2022", 0.30),
            ("sector_productivity_cagr_median", "sector_median", 0.20),
            ("region_productivity_cagr_median", "region_median", 0.10),
            ("global_productivity_cagr_median", "global_median", 0.05),
        ]:
            val = row.get(col)
            if pd.notna(val) and float(val) > -0.95:
                sources.append((label, float(val), weight))
        if not sources:
            sources.append(("default_2pct", 0.02, 1.0))
        weight_sum = sum(w for _, _, w in sources)
        g = math.exp(sum(math.log1p(max(-0.95, v)) * w for _, v, w in sources) / weight_sum) - 1.0
        g = float(np.clip(g + shifts[scenario], -0.03, 0.07))
        return g, "; ".join(f"{label}:{weight:g}" for label, _, weight in sources)

    out = base.copy()
    pairs = out.apply(shrink, axis=1, result_type="expand")
    out["productivity_growth_forecast"] = pairs[0].astype(float)
    out["productivity_source_explanation"] = pairs[1]
    out["productivity_scenario"] = scenario
    out["productivity_forecast_clip_min"] = -0.03
    out["productivity_forecast_clip_max"] = 0.07
    return out


def build_productivity_trajectory(prod_base: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    """Expand cell-level productivity assumptions into annual trajectories.

    The current EMISS/Rosstat evidence is too short for robust structural
    forecasts at every region-sector cell. The trajectory therefore starts from
    the shrinkage estimate and gradually converges toward the sector median,
    which preserves regional heterogeneity but avoids treating one noisy point
    forecast as a fixed 12-year constant.
    """
    out_rows = []
    tmp = prod_base.copy()
    tmp["productivity_growth_forecast_static"] = pd.to_numeric(tmp["productivity_growth_forecast"], errors="coerce")
    tmp["sector_productivity_growth_forecast_median"] = tmp.groupby("activity_id")["productivity_growth_forecast_static"].transform("median")
    tmp["global_productivity_growth_forecast_median"] = float(tmp["productivity_growth_forecast_static"].median(skipna=True))
    for _, row in tmp.iterrows():
        g0 = float(row["productivity_growth_forecast_static"])
        sector_g = row.get("sector_productivity_growth_forecast_median")
        if pd.isna(sector_g):
            sector_g = row.get("global_productivity_growth_forecast_median", g0)
        sector_g = float(sector_g)
        for year in range(start_year, end_year + 1):
            year_index = year - start_year
            convergence_weight = min(0.35, 0.03 * year_index)
            g_year = (1.0 - convergence_weight) * g0 + convergence_weight * sector_g
            g_year = float(np.clip(g_year, -0.03, 0.07))
            d = row.to_dict()
            d.update(
                {
                    "forecast_year": year,
                    "productivity_growth_forecast_static": g0,
                    "productivity_growth_forecast_yearly": g_year,
                    "sector_productivity_growth_forecast_median": sector_g,
                    "productivity_trajectory_convergence_weight": convergence_weight,
                    "productivity_trajectory_rule": "cell_shrinkage_estimate_gradually_converges_to_sector_median",
                }
            )
            out_rows.append(d)
    return pd.DataFrame(out_rows)


def pct_index_to_log_growth(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return np.log(values.where(values > 0) / 100.0)


def weighted_average(values: pd.Series, weights: pd.Series) -> float:
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce").fillna(0.0).clip(lower=0.0)
    mask = v.notna() & np.isfinite(v) & (w > 0)
    if mask.any():
        return float(np.average(v[mask], weights=w[mask]))
    mask = v.notna() & np.isfinite(v)
    if mask.any():
        return float(v[mask].mean())
    return 0.0


def weighted_group_average(df: pd.DataFrame, keys: list[str], value_col: str, weight_col: str, out_col: str) -> pd.DataFrame:
    rows = []
    for key, group in df.groupby(keys, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        row = dict(zip(keys, key))
        row[out_col] = weighted_average(group[value_col], group[weight_col])
        rows.append(row)
    return pd.DataFrame(rows)


def build_productivity_history(model: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """Build log-growth training targets for the v4 productivity model."""
    keys = [
        "territory_id",
        "territory_name",
        "federal_district_name",
        "activity_id",
        "okved_section",
        "activity_name",
    ]
    base_keys = base[keys + ["employment_persons"]].rename(columns={"employment_persons": "employment_2024_persons"})
    keep = [
        "territory_id",
        "activity_id",
        "year",
        "employment_persons",
        "vrp_constant_2016_thousand_rub",
        "official_productivity_index_region_total_pct",
        "official_productivity_index_rf_activity_pct",
        "official_productivity_index_hybrid_pct",
        "official_productivity_coverage_scope",
    ]
    keep = [c for c in keep if c in model.columns]
    hist = model[model["year"].between(2017, 2024)][keep].merge(base_keys, on=["territory_id", "activity_id"], how="inner")
    hist["year"] = pd.to_numeric(hist["year"], errors="coerce").astype(int)
    hist["employment_persons"] = pd.to_numeric(hist["employment_persons"], errors="coerce")
    hist["vrp_constant_2016_thousand_rub"] = pd.to_numeric(hist.get("vrp_constant_2016_thousand_rub"), errors="coerce")
    hist["productivity_level_rub_per_worker"] = np.where(
        (hist["vrp_constant_2016_thousand_rub"] > 0) & (hist["employment_persons"] > 0),
        hist["vrp_constant_2016_thousand_rub"] * 1000.0 / hist["employment_persons"],
        np.nan,
    )
    hist = hist.sort_values(["territory_id", "activity_id", "year"]).copy()
    hist["productivity_log_growth_observed"] = np.log(
        hist["productivity_level_rub_per_worker"]
        / hist.groupby(["territory_id", "activity_id"])["productivity_level_rub_per_worker"].shift(1)
    )
    hist.loc[~hist["year"].between(2018, 2022), "productivity_log_growth_observed"] = np.nan
    hist["official_region_total_productivity_log_growth"] = pct_index_to_log_growth(
        hist.get("official_productivity_index_region_total_pct", pd.Series(index=hist.index, dtype=float))
    )
    hist["official_rf_sector_productivity_log_growth"] = pct_index_to_log_growth(
        hist.get("official_productivity_index_rf_activity_pct", pd.Series(index=hist.index, dtype=float))
    )
    hist["official_hybrid_region_sector_log_growth"] = pct_index_to_log_growth(
        hist.get("official_productivity_index_hybrid_pct", pd.Series(index=hist.index, dtype=float))
    )

    hist["productivity_growth_for_training"] = hist["productivity_log_growth_observed"]
    hist["productivity_source_for_training"] = np.where(
        hist["productivity_log_growth_observed"].notna(),
        "observed_vrp_employment",
        "",
    )
    official_mask = hist["productivity_growth_for_training"].isna() & hist["official_hybrid_region_sector_log_growth"].notna()
    hist.loc[official_mask, "productivity_growth_for_training"] = hist.loc[official_mask, "official_hybrid_region_sector_log_growth"]
    hist.loc[official_mask, "productivity_source_for_training"] = "official_hybrid_index"

    raw = hist["productivity_growth_for_training"].copy()
    sector_year = raw.groupby([hist["activity_id"], hist["year"]]).transform("median")
    region_year = raw.groupby([hist["territory_id"], hist["year"]]).transform("median")
    global_year = raw.groupby(hist["year"]).transform("median")
    default_log_growth = math.log1p(0.02)
    missing = hist["productivity_growth_for_training"].isna()
    fill_sector = missing & sector_year.notna()
    hist.loc[fill_sector, "productivity_growth_for_training"] = sector_year[fill_sector]
    hist.loc[fill_sector, "productivity_source_for_training"] = "imputed_sector_year_median"
    missing = hist["productivity_growth_for_training"].isna()
    fill_region = missing & region_year.notna()
    hist.loc[fill_region, "productivity_growth_for_training"] = region_year[fill_region]
    hist.loc[fill_region, "productivity_source_for_training"] = "imputed_region_year_median"
    missing = hist["productivity_growth_for_training"].isna()
    fill_global = missing & global_year.notna()
    hist.loc[fill_global, "productivity_growth_for_training"] = global_year[fill_global]
    hist.loc[fill_global, "productivity_source_for_training"] = "imputed_global_year_median"
    missing = hist["productivity_growth_for_training"].isna()
    hist.loc[missing, "productivity_growth_for_training"] = default_log_growth
    hist.loc[missing, "productivity_source_for_training"] = "imputed_default_2pct"
    hist["imputed_training_target"] = hist["productivity_source_for_training"].astype(str).str.startswith("imputed_")
    hist["productivity_growth_for_training"] = hist["productivity_growth_for_training"].clip(math.log(0.90), math.log(1.15))
    return hist


def forecast_candidate(values: np.ndarray, horizon: int, method: str, target: float = 0.0) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.full(horizon, target, dtype=float)
    last = float(values[-1])
    if method == "last":
        return np.full(horizon, last, dtype=float)
    if method == "recent_mean":
        return np.full(horizon, float(np.mean(values[-min(3, len(values)) :])), dtype=float)
    if method == "mean_revert":
        phi = 0.85
        return np.array([target + (last - target) * (phi ** h) for h in range(1, horizon + 1)], dtype=float)
    if method == "damped_linear":
        if len(values) >= 3:
            slope = float(np.median(np.diff(values[-4:])))
        elif len(values) >= 2:
            slope = float(values[-1] - values[-2])
        else:
            slope = 0.0
        damp = 0.65
        return np.array([last + slope * damp * (1 - damp ** h) / (1 - damp) for h in range(1, horizon + 1)], dtype=float)
    if method == "ets_damped":
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing

            if len(values) < 4:
                return np.full(horizon, np.nan)
            fit = ExponentialSmoothing(
                values,
                trend="add",
                damped_trend=True,
                seasonal=None,
                initialization_method="estimated",
            ).fit(optimized=True)
            return np.asarray(fit.forecast(horizon), dtype=float)
        except Exception:
            return np.full(horizon, np.nan)
    raise ValueError(f"Unknown forecast method: {method}")


def select_component_model(series: pd.Series, component_type: str, component_id: str, shrink_target: float = 0.0) -> tuple[str, pd.DataFrame]:
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    methods = ["ets_damped", "damped_linear", "mean_revert", "recent_mean", "last"]
    rows = []
    for method in methods:
        errors = []
        ape = []
        if len(values) >= 4:
            for origin in range(3, len(values)):
                pred = forecast_candidate(values[:origin], 1, method, target=shrink_target)[0]
                if not np.isfinite(pred):
                    continue
                err = pred - values[origin]
                errors.append(err)
                denom = max(abs(values[origin]), 1e-6)
                ape.append(abs(err) / denom)
        if errors:
            arr = np.asarray(errors, dtype=float)
            mae = float(np.mean(np.abs(arr)))
            rmse = float(np.sqrt(np.mean(arr**2)))
            mape = float(np.mean(ape))
        else:
            mae = rmse = mape = np.nan
        rows.append(
            {
                "report_section": "component_backtest",
                "component_type": component_type,
                "component_id": component_id,
                "method": method,
                "observations": int(len(values)),
                "mae_log_growth": mae,
                "rmse_log_growth": rmse,
                "mape_log_growth": mape,
            }
        )
    report = pd.DataFrame(rows)
    candidates = report[report["rmse_log_growth"].notna()].sort_values(["rmse_log_growth", "mae_log_growth"])
    chosen = str(candidates.iloc[0]["method"]) if len(candidates) else ("mean_revert" if shrink_target == 0.0 else "recent_mean")
    report["chosen_method"] = chosen
    return chosen, report


def estimate_decay_phi(values: pd.Series, default_half_life: float = 5.0) -> float:
    v = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(v) >= 3 and np.std(v[:-1]) > 1e-9 and np.std(v[1:]) > 1e-9:
        corr = float(np.corrcoef(v[:-1], v[1:])[0, 1])
        if np.isfinite(corr) and 0.35 <= corr <= 0.95:
            return corr
    return float(2 ** (-1 / default_half_life))


def robust_median(values: Iterable[float], default: float = 0.0) -> float:
    arr = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna().to_numpy(dtype=float)
    if len(arr) == 0:
        return float(default)
    value = float(np.median(arr))
    return value if np.isfinite(value) else float(default)


def mean_reverting_path(last: float, target: float, phi: float, horizon: int) -> np.ndarray:
    phi = float(np.clip(phi, 0.50, 0.95))
    last = float(last) if np.isfinite(last) else 0.0
    target = float(target) if np.isfinite(target) else 0.0
    return np.array([target + (last - target) * (phi**step) for step in range(1, horizon + 1)], dtype=float)


def select_mean_reversion_phi(
    series: pd.Series,
    component_type: str,
    component_id: str,
    target_strategy: str = "median",
    default_phi: float = 0.75,
    target_clip_abs: float | None = None,
) -> tuple[float, float, pd.DataFrame]:
    """Select a bounded mean-reversion speed by one-step rolling-origin tests."""
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)

    def target_for(arr: np.ndarray) -> float:
        if target_strategy == "zero":
            target = 0.0
        else:
            target = robust_median(arr, 0.0)
        if target_clip_abs is not None:
            target = float(np.clip(target, -target_clip_abs, target_clip_abs))
        return float(target)

    final_target = target_for(values)
    phi_grid = np.round(np.linspace(0.50, 0.95, 10), 2)
    rows = []
    for phi in phi_grid:
        errors = []
        ape = []
        if len(values) >= 4:
            for origin in range(3, len(values)):
                train_values = values[:origin]
                origin_target = target_for(train_values)
                pred = float(origin_target + (train_values[-1] - origin_target) * phi)
                if not np.isfinite(pred):
                    continue
                err = pred - values[origin]
                errors.append(err)
                ape.append(abs(err) / max(abs(values[origin]), 1e-6))
        if errors:
            arr = np.asarray(errors, dtype=float)
            mae = float(np.mean(np.abs(arr)))
            rmse = float(np.sqrt(np.mean(arr**2)))
            mape = float(np.mean(ape))
        else:
            mae = rmse = mape = np.nan
        rows.append(
            {
                "report_section": "component_backtest",
                "component_type": component_type,
                "component_id": component_id,
                "method": f"mean_revert_phi_{phi:.2f}",
                "observations": int(len(values)),
                "mae_log_growth": mae,
                "rmse_log_growth": rmse,
                "mape_log_growth": mape,
                "selected_phi": float(phi),
                "long_run_target": final_target,
            }
        )
    report = pd.DataFrame(rows)
    candidates = report[report["rmse_log_growth"].notna()].sort_values(["rmse_log_growth", "mae_log_growth"])
    if len(candidates):
        chosen_phi = float(candidates.iloc[0]["selected_phi"])
    else:
        chosen_phi = float(np.clip(default_phi, 0.50, 0.95))
    chosen_method = f"mean_revert_phi_{chosen_phi:.2f}"
    report["chosen_method"] = chosen_method
    return final_target, chosen_phi, report


def build_champion_productivity_forecast(
    model: pd.DataFrame,
    base: pd.DataFrame,
    start_year: int,
    end_year: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    history = build_productivity_history(model, base)
    train = history[history["year"].between(2018, 2024)].copy()
    train["_weight"] = train["employment_persons"].fillna(train["employment_2024_persons"]).clip(lower=0.0)
    train.loc[train["_weight"].le(0), "_weight"] = train["employment_2024_persons"].fillna(1.0)

    common = weighted_group_average(train, ["year"], "productivity_growth_for_training", "_weight", "common_t")
    sector_avg = weighted_group_average(train, ["activity_id", "year"], "productivity_growth_for_training", "_weight", "sector_avg")
    region_avg = weighted_group_average(train, ["territory_id", "year"], "productivity_growth_for_training", "_weight", "region_avg")
    train = train.merge(common, on="year", how="left").merge(sector_avg, on=["activity_id", "year"], how="left").merge(region_avg, on=["territory_id", "year"], how="left")
    train["sector_factor"] = train["sector_avg"] - train["common_t"]
    train["region_factor"] = train["region_avg"] - train["common_t"]
    train["cell_residual"] = train["productivity_growth_for_training"] - train["common_t"] - train["sector_factor"] - train["region_factor"]

    forecast_years = list(range(start_year, end_year + 1))
    horizon = len(forecast_years)
    backtest_reports = []

    common_series = common.set_index("year")["common_t"].sort_index()
    common_target, common_phi, common_report = select_mean_reversion_phi(
        common_series,
        "common",
        "common_t",
        target_strategy="median",
        default_phi=0.75,
        target_clip_abs=0.05,
    )
    backtest_reports.append(common_report)
    common_values = pd.to_numeric(common_series, errors="coerce").dropna().to_numpy(dtype=float)
    common_last = float(common_values[-1]) if len(common_values) else common_target
    common_forecast = pd.DataFrame(
        {
            "forecast_year": forecast_years,
            "common_forecast": mean_reverting_path(common_last, common_target, common_phi, horizon),
        }
    )

    sector_series = (
        train[["activity_id", "year", "sector_factor"]]
        .drop_duplicates(["activity_id", "year"])
        .sort_values(["activity_id", "year"])
    )
    sector_forecast_rows = []
    sector_reliability = {}
    for activity_id, group in sector_series.groupby("activity_id"):
        s = group.set_index("year")["sector_factor"].sort_index()
        coverage = train[train["activity_id"].eq(activity_id)].groupby("year")["imputed_training_target"].mean()
        non_imputed_share = 1.0 - float(coverage.mean()) if len(coverage) else 0.0
        volatility = float(s.std(skipna=True)) if len(s) else 0.0
        reliability = float(np.clip(non_imputed_share / (1.0 + volatility / 0.04), 0.35, 1.0))
        sector_reliability[activity_id] = reliability
        target, phi, report = select_mean_reversion_phi(
            s,
            "sector",
            str(activity_id),
            target_strategy="median",
            default_phi=0.75,
            target_clip_abs=0.04,
        )
        backtest_reports.append(report)
        s_values = pd.to_numeric(s, errors="coerce").dropna().to_numpy(dtype=float)
        last = float(s_values[-1]) if len(s_values) else target
        values = mean_reverting_path(last * reliability, target * reliability, phi, horizon)
        for year, value in zip(forecast_years, values):
            sector_forecast_rows.append(
                {
                    "activity_id": activity_id,
                    "forecast_year": year,
                    "sector_factor_forecast": value,
                    "sector_factor_method": f"mean_revert_phi_{phi:.2f}",
                    "sector_factor_phi": phi,
                    "sector_factor_long_run_target": target * reliability,
                    "sector_factor_reliability": reliability,
                }
            )
    sector_forecast = pd.DataFrame(sector_forecast_rows)

    region_factor_hist = (
        train[["territory_id", "year", "region_factor"]]
        .drop_duplicates(["territory_id", "year"])
        .sort_values(["territory_id", "year"])
    )
    region_forecast_rows = []
    for territory_id, group in region_factor_hist.groupby("territory_id"):
        s = group.set_index("year")["region_factor"].sort_index()
        _, region_phi, report = select_mean_reversion_phi(
            s,
            "region",
            str(territory_id),
            target_strategy="zero",
            default_phi=0.80,
            target_clip_abs=None,
        )
        backtest_reports.append(report)
        s_values = pd.to_numeric(s, errors="coerce").dropna().to_numpy(dtype=float)
        last = float(s_values[-1]) if len(s_values) else 0.0
        for year, value in zip(forecast_years, mean_reverting_path(last, 0.0, region_phi, horizon)):
            region_forecast_rows.append(
                {
                    "territory_id": territory_id,
                    "forecast_year": year,
                    "region_factor_forecast": value,
                    "region_factor_method": f"mean_revert_phi_{region_phi:.2f}_to_zero",
                    "region_factor_phi": region_phi,
                }
            )
    region_forecast = pd.DataFrame(region_forecast_rows)

    residual_params: dict[tuple[object, object], dict[str, float]] = {}
    residual_hist = train[["territory_id", "activity_id", "year", "cell_residual"]].sort_values(
        ["territory_id", "activity_id", "year"]
    )
    for (territory_id, activity_id), group in residual_hist.groupby(["territory_id", "activity_id"]):
        s = group.set_index("year")["cell_residual"].sort_index()
        _, residual_phi, report = select_mean_reversion_phi(
            s,
            "cell_residual",
            f"{territory_id}|{activity_id}",
            target_strategy="zero",
            default_phi=0.80,
            target_clip_abs=None,
        )
        backtest_reports.append(report)
        s_values = pd.to_numeric(s, errors="coerce").dropna().to_numpy(dtype=float)
        last = float(s_values[-1]) if len(s_values) else 0.0
        residual_params[(territory_id, activity_id)] = {
            "last": last,
            "phi": residual_phi,
        }
    coverage = (
        train.groupby(["territory_id", "activity_id"], as_index=False)
        .agg(
            training_years=("year", "nunique"),
            imputed_training_share=("imputed_training_target", "mean"),
            observed_training_years=("productivity_source_for_training", lambda s: int((s == "observed_vrp_employment").sum())),
            official_training_years=("productivity_source_for_training", lambda s: int((s == "official_hybrid_index").sum())),
        )
    )
    coverage["training_source_coverage_flag"] = np.select(
        [
            coverage["observed_training_years"].ge(4),
            (coverage["observed_training_years"] + coverage["official_training_years"]).ge(4),
            coverage["imputed_training_share"].lt(0.5),
        ],
        ["observed_history", "observed_plus_official", "limited_observed_history"],
        default="mostly_imputed_training",
    )

    caps = (
        train.groupby("activity_id")["productivity_growth_for_training"]
        .quantile([0.01, 0.99])
        .unstack()
        .rename(columns={0.01: "sector_log_growth_p01", 0.99: "sector_log_growth_p99"})
        .reset_index()
    )
    global_p01 = float(train["productivity_growth_for_training"].quantile(0.01))
    global_p99 = float(train["productivity_growth_for_training"].quantile(0.99))
    caps["sector_log_growth_p01"] = caps["sector_log_growth_p01"].fillna(global_p01)
    caps["sector_log_growth_p99"] = caps["sector_log_growth_p99"].fillna(global_p99)
    caps["productivity_log_cap_lower"] = np.maximum(caps["sector_log_growth_p01"], math.log(0.95))
    caps["productivity_log_cap_upper"] = np.minimum(caps["sector_log_growth_p99"], math.log(1.08))
    invalid_caps = caps["productivity_log_cap_lower"] >= caps["productivity_log_cap_upper"]
    caps.loc[invalid_caps, "productivity_log_cap_lower"] = math.log(0.95)
    caps.loc[invalid_caps, "productivity_log_cap_upper"] = math.log(1.08)

    base_meta = base.copy()
    rows = []
    for _, cell in base_meta.iterrows():
        residual_param = residual_params.get((cell["territory_id"], cell["activity_id"]), {"last": 0.0, "phi": 0.80})
        residual_values = mean_reverting_path(residual_param["last"], 0.0, residual_param["phi"], horizon)
        for year, residual_value in zip(forecast_years, residual_values):
            rows.append(
                {
                    "territory_id": cell["territory_id"],
                    "territory_name": cell["territory_name"],
                    "federal_district_name": cell.get("federal_district_name", ""),
                    "activity_id": cell["activity_id"],
                    "okved_section": cell.get("okved_section", ""),
                    "activity_name": cell["activity_name"],
                    "employment_persons": cell["employment_persons"],
                    "forecast_year": year,
                    "cell_residual_forecast": residual_value,
                    "cell_residual_phi": residual_param["phi"],
                }
            )
    forecast = pd.DataFrame(rows)
    forecast = (
        forecast.merge(common_forecast, on="forecast_year", how="left")
        .merge(sector_forecast, on=["activity_id", "forecast_year"], how="left")
        .merge(region_forecast, on=["territory_id", "forecast_year"], how="left")
        .merge(coverage, on=["territory_id", "activity_id"], how="left")
        .merge(caps, on="activity_id", how="left")
    )
    forecast["productivity_log_growth_raw"] = (
        forecast["common_forecast"]
        + forecast["sector_factor_forecast"].fillna(0.0)
        + forecast["region_factor_forecast"].fillna(0.0)
        + forecast["cell_residual_forecast"].fillna(0.0)
    )
    forecast["productivity_log_growth_clipped"] = forecast["productivity_log_growth_raw"].clip(
        lower=forecast["productivity_log_cap_lower"],
        upper=forecast["productivity_log_cap_upper"],
    )
    forecast["productivity_forecast_is_clipped"] = (
        (forecast["productivity_log_growth_clipped"] - forecast["productivity_log_growth_raw"]).abs() > 1e-12
    )
    forecast["productivity_growth_forecast_yearly"] = np.exp(forecast["productivity_log_growth_clipped"]) - 1.0
    forecast["productivity_growth_forecast_pct"] = forecast["productivity_growth_forecast_yearly"] * 100.0
    forecast["productivity_growth_forecast"] = forecast["productivity_growth_forecast_yearly"]
    forecast["productivity_growth_forecast_static"] = forecast.groupby(["territory_id", "activity_id"])[
        "productivity_growth_forecast_yearly"
    ].transform("first")
    forecast["productivity_trajectory_convergence_weight"] = 0.0
    forecast["sector_productivity_growth_forecast_median"] = forecast.groupby(["activity_id", "forecast_year"])[
        "productivity_growth_forecast_yearly"
    ].transform("median")
    forecast["productivity_scenario"] = CHAMPION_PRODUCTIVITY_SCENARIO
    forecast["productivity_forecast_model"] = V5_PRODUCTIVITY_MODEL
    forecast["productivity_trajectory_rule"] = V5_PRODUCTIVITY_MODEL
    forecast["forecast_quality_flag"] = np.select(
        [
            forecast["productivity_forecast_is_clipped"],
            forecast["training_source_coverage_flag"].eq("mostly_imputed_training"),
            forecast["training_source_coverage_flag"].eq("limited_observed_history"),
        ],
        ["clipped_to_sector_or_absolute_cap", "mostly_imputed_training", "limited_observed_history"],
        default="ok",
    )

    backtest = pd.concat(backtest_reports, ignore_index=True) if backtest_reports else pd.DataFrame()
    qa = {
        "productivity_forecast_model": V5_PRODUCTIVITY_MODEL,
        "common_factor_method": f"mean_revert_phi_{common_phi:.2f}",
        "common_factor_phi": common_phi,
        "common_long_run_target": common_target,
        "region_factor_phi_min": float(forecast["region_factor_phi"].min()),
        "region_factor_phi_max": float(forecast["region_factor_phi"].max()),
        "cell_residual_phi_min": float(forecast["cell_residual_phi"].min()),
        "cell_residual_phi_max": float(forecast["cell_residual_phi"].max()),
        "forecast_rows": int(len(forecast)),
        "history_rows": int(len(history)),
        "clipped_forecast_cells": int(forecast["productivity_forecast_is_clipped"].sum()),
        "mostly_imputed_cell_forecasts": int(forecast["training_source_coverage_flag"].eq("mostly_imputed_training").sum()),
    }
    return history, forecast, backtest, qa


def build_productivity_clipping_qa(forecast: pd.DataFrame, control_years: Iterable[int]) -> pd.DataFrame:
    checks = forecast[forecast["forecast_year"].isin(list(control_years))].copy()
    if checks.empty:
        return pd.DataFrame(
            columns=[
                "forecast_year",
                "activity_id",
                "okved_section",
                "activity_name",
                "cells",
                "clipped_cells",
                "clipped_share",
                "qa_status",
            ]
        )
    out = (
        checks.groupby(["forecast_year", "activity_id", "okved_section", "activity_name"], as_index=False)
        .agg(
            cells=("territory_id", "count"),
            clipped_cells=("productivity_forecast_is_clipped", "sum"),
            min_growth=("productivity_growth_forecast_yearly", "min"),
            median_growth=("productivity_growth_forecast_yearly", "median"),
            max_growth=("productivity_growth_forecast_yearly", "max"),
        )
        .sort_values(["forecast_year", "activity_id"])
    )
    out["clipped_share"] = out["clipped_cells"] / out["cells"].replace(0, np.nan)
    out["qa_status"] = np.where(out["clipped_share"].gt(0.20), "fail_sector_clipped_share_gt_20pct", "ok")
    return out


def write_and_validate_productivity_clipping(forecast: pd.DataFrame, audit_dir: Path) -> pd.DataFrame:
    clipping_qa = build_productivity_clipping_qa(forecast, CONTROL_YEARS)
    write_csv(clipping_qa, audit_dir / "productivity_clipping_qa.csv")
    failed = clipping_qa[clipping_qa["qa_status"].ne("ok")].copy()
    if not failed.empty:
        cols = ["forecast_year", "okved_section", "activity_name", "clipped_cells", "cells", "clipped_share"]
        problem_table = failed[cols].to_string(index=False)
        raise ValueError(
            "Productivity clipping QA failed: at least one sector has >20% clipped cells "
            f"in control years {CONTROL_YEARS}.\n{problem_table}"
        )
    return clipping_qa


def build_productivity_dashboard_summary(forecast: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, group in forecast.groupby(["forecast_year", "activity_id", "okved_section", "activity_name"], dropna=False):
        year, activity_id, okved_section, activity_name = keys
        weight = pd.to_numeric(group.get("employment_persons", pd.Series(1.0, index=group.index)), errors="coerce").fillna(0.0)
        rows.append(
            {
                "forecast_year": year,
                "activity_id": activity_id,
                "okved_section": okved_section,
                "activity_name": activity_name,
                "weighted_productivity_growth_forecast_yearly": weighted_average(
                    group["productivity_growth_forecast_yearly"], weight
                ),
                "median_productivity_growth_forecast_yearly": float(group["productivity_growth_forecast_yearly"].median()),
                "clipped_share": float(group["productivity_forecast_is_clipped"].mean()),
                "mostly_imputed_training_share": float(group["training_source_coverage_flag"].eq("mostly_imputed_training").mean()),
                "cells": int(len(group)),
            }
        )
    return pd.DataFrame(rows)


def build_productivity_coverage_report(base: pd.DataFrame) -> pd.DataFrame:
    scope = "official_productivity_coverage_scope"
    if scope not in base.columns:
        base = base.copy()
        base[scope] = np.where(base["official_prod_index_hybrid_pct"].notna(), "official_or_hybrid_available", "no_official_index")
    return (
        base.groupby(["activity_id", "okved_section", "activity_name", scope], dropna=False)
        .agg(
            region_cells=("territory_id", "count"),
            territories=("territory_id", "nunique"),
            official_index_nonnull=("official_prod_index_hybrid_pct", lambda s: int(s.notna().sum())),
            historical_cagr_nonnull=("historical_productivity_cagr_2017_2022_raw", lambda s: int(s.notna().sum())),
        )
        .reset_index()
        .sort_values(["activity_id", scope])
    )


def economic_labor_demand(prod_yearly: pd.DataFrame, world_growth: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    growth_by_year = dict(zip(world_growth["forecast_year"], world_growth["target_real_vrp_growth"]))
    key_cols = ["territory_id", "activity_id"]
    required_cols = set(key_cols + ["forecast_year", "employment_persons", "productivity_growth_forecast_yearly"])
    missing = [c for c in required_cols if c not in prod_yearly.columns]
    if missing:
        raise ValueError(f"Productivity trajectory is missing required columns: {missing}")

    records: list[dict] = []
    for _, cell in prod_yearly.sort_values(key_cols + ["forecast_year"]).groupby(key_cols, sort=False):
        first = cell.iloc[0]
        base_emp = float(first["employment_persons"])
        prev_required = base_emp
        cell_by_year = cell.set_index("forecast_year")
        for year in range(start_year, end_year + 1):
            if year not in cell_by_year.index:
                raise ValueError(f"No productivity forecast for {first['territory_id']} / {first['activity_id']} / {year}")
            r = cell_by_year.loc[year]
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
            gy = float(growth_by_year[year])
            gp = float(r["productivity_growth_forecast_yearly"])
            required = prev_required * (1.0 + gy) / (1.0 + gp)
            records.append(
                {
                    "territory_id": first["territory_id"],
                    "territory_name": first["territory_name"],
                    "territory_norm": normalize_name(first["territory_name"]),
                    "federal_district_name": first.get("federal_district_name", ""),
                    "activity_id": first["activity_id"],
                    "okved_section": first.get("okved_section", ""),
                    "activity_name": first["activity_name"],
                    "forecast_year": year,
                    "employment_2024_persons": base_emp,
                    "target_real_vrp_growth": gy,
                    "productivity_growth_forecast": gp,
                    "productivity_growth_forecast_yearly": gp,
                    "productivity_growth_forecast_pct": float(r.get("productivity_growth_forecast_pct", gp * 100.0)),
                    "productivity_growth_forecast_static": float(r.get("productivity_growth_forecast_static", gp)),
                    "productivity_trajectory_convergence_weight": float(r.get("productivity_trajectory_convergence_weight", 0.0)),
                    "productivity_forecast_model": r.get("productivity_forecast_model", r.get("productivity_trajectory_rule", "")),
                    "training_source_coverage_flag": r.get("training_source_coverage_flag", ""),
                    "forecast_quality_flag": r.get("forecast_quality_flag", ""),
                    "productivity_forecast_is_clipped": bool(r.get("productivity_forecast_is_clipped", False)),
                    "labor_demand_required_persons": required,
                    "annual_labor_demand_delta_persons": required - prev_required,
                    "cumulative_delta_from_2024_persons": required - base_emp,
                    "positive_annual_labor_need_persons": max(0.0, required - prev_required),
                    "positive_cumulative_labor_need_persons": max(0.0, required - base_emp),
                    "productivity_scenario": first.get("productivity_scenario", "baseline"),
                }
            )
            prev_required = required
    return pd.DataFrame(records)

def build_crosswalk(pop_long: pd.DataFrame, base: pd.DataFrame, processed_dir: Path, audit_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    econ = base[["territory_id", "territory_name", "territory_norm"]].drop_duplicates()
    pop = pop_long[["territory_name_population", "territory_norm"]].drop_duplicates()
    pop_one = pop.sort_values("territory_name_population").drop_duplicates("territory_norm")
    econ_cross = econ.merge(pop_one, on="territory_norm", how="left")
    econ_cross["match_status"] = np.where(econ_cross["territory_name_population"].notna(), "matched", "unmatched_economic")

    population_only = pop[~pop["territory_norm"].isin(set(econ["territory_norm"]))].copy()
    population_only["territory_id"] = ""
    population_only["territory_name"] = ""
    population_only["match_status"] = "population_only_not_in_model_universe"
    crosswalk = pd.concat(
        [
            econ_cross[["territory_id", "territory_name", "territory_name_population", "territory_norm", "match_status"]],
            population_only[["territory_id", "territory_name", "territory_name_population", "territory_norm", "match_status"]],
        ],
        ignore_index=True,
    ).sort_values(["match_status", "territory_norm"])

    unmatched_econ = econ_cross[econ_cross["territory_name_population"].isna()].copy()
    unmatched_pop = population_only.copy()
    write_csv(crosswalk, processed_dir / "territory_name_crosswalk_population_economy.csv")
    write_csv(unmatched_econ, audit_dir / "unmatched_economic_territories.csv")
    write_csv(unmatched_pop, audit_dir / "unmatched_population_territories.csv")
    return crosswalk, unmatched_econ, unmatched_pop


def build_working_age_resources(pop_long: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    for label, (age_min, age_max) in WORKING_AGE_DEFINITIONS.items():
        part = pop_long[(pop_long["age"] >= age_min) & (pop_long["age"] <= age_max)]
        grouped = (
            part.groupby(["territory_name_population", "territory_norm", "year", "population_scenario"], as_index=False)[
                "population_persons"
            ]
            .sum()
            .rename(columns={"population_persons": "working_age_population_persons"})
        )
        grouped["working_age_definition"] = label
        grouped["work_age_min"] = age_min
        grouped["work_age_max"] = age_max
        pieces.append(grouped)
    return pd.concat(pieces, ignore_index=True)


def employment_ratios(base: pd.DataFrame, resources: pd.DataFrame, working_age_definition: str) -> pd.DataFrame:
    emp_region = (
        base.groupby(["territory_id", "territory_name", "territory_norm"], as_index=False)["employment_persons"]
        .sum()
        .rename(columns={"employment_persons": "employment_2024_region_persons"})
    )
    pop_2024 = resources[(resources["year"] == 2024) & (resources["working_age_definition"] == working_age_definition)][
        ["territory_norm", "working_age_population_persons"]
    ].rename(columns={"working_age_population_persons": "working_age_population_2024_persons"})
    ratios = emp_region.merge(pop_2024, on="territory_norm", how="left")
    ratios["employment_to_workage_ratio_2024_raw"] = (
        ratios["employment_2024_region_persons"] / ratios["working_age_population_2024_persons"]
    )
    ratios["employment_to_workage_ratio_2024"] = ratios["employment_to_workage_ratio_2024_raw"].clip(upper=0.90)
    ratios["ratio_clipped_flag"] = ratios["employment_to_workage_ratio_2024"] != ratios["employment_to_workage_ratio_2024_raw"]
    ratios["working_age_definition"] = working_age_definition
    return ratios


def base_sector_shares(base: pd.DataFrame) -> pd.DataFrame:
    shares = base[
        [
            "territory_id",
            "activity_id",
            "employment_persons",
        ]
    ].copy()
    shares["region_employment_2024_persons"] = shares.groupby("territory_id")["employment_persons"].transform("sum")
    shares["sector_share_in_region_2024"] = shares["employment_persons"] / shares["region_employment_2024_persons"]
    return shares[["territory_id", "activity_id", "region_employment_2024_persons", "sector_share_in_region_2024"]]


def median_abs_deviation(values: pd.Series) -> float:
    v = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(v) == 0:
        return np.nan
    med = float(np.median(v))
    return float(np.median(np.abs(v - med)))


def calibrate_sector_share_transition(model: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    keys = ["territory_id", "activity_id"]
    base_keys = base[keys + ["territory_name", "federal_district_name", "okved_section", "activity_name"]].drop_duplicates()
    hist = model[model["year"].between(2017, 2024)][keys + ["year", "employment_persons"]].merge(base_keys, on=keys, how="inner")
    hist["employment_persons"] = pd.to_numeric(hist["employment_persons"], errors="coerce").fillna(0.0).clip(lower=0.0)
    hist["region_employment_persons"] = hist.groupby(["territory_id", "year"])["employment_persons"].transform("sum")
    hist["sector_share"] = np.where(hist["region_employment_persons"] > 0, hist["employment_persons"] / hist["region_employment_persons"], np.nan)
    hist = hist.sort_values(["territory_id", "activity_id", "year"]).copy()
    hist["delta_share"] = hist.groupby(["territory_id", "activity_id"])["sector_share"].diff()
    hist["abs_delta_share"] = hist["delta_share"].abs()
    cell = (
        hist.groupby(keys, as_index=False)
        .agg(
            abs_delta_share_median=("abs_delta_share", "median"),
            abs_delta_share_mad=("abs_delta_share", median_abs_deviation),
            abs_delta_share_p75=("abs_delta_share", lambda s: float(pd.to_numeric(s, errors="coerce").quantile(0.75))),
            abs_delta_share_p90=("abs_delta_share", lambda s: float(pd.to_numeric(s, errors="coerce").quantile(0.90))),
            abs_delta_share_observations=("abs_delta_share", lambda s: int(pd.to_numeric(s, errors="coerce").notna().sum())),
        )
        .merge(base_keys, on=keys, how="left")
    )
    cell["raw_empirical_share_change_cap"] = cell["abs_delta_share_median"] + 1.4826 * cell["abs_delta_share_mad"]
    reliable = cell["abs_delta_share_observations"].ge(3) & cell["raw_empirical_share_change_cap"].notna()
    reliable_caps = cell.loc[reliable, ["activity_id", "raw_empirical_share_change_cap"]].copy()
    sector_caps = reliable_caps.groupby("activity_id")["raw_empirical_share_change_cap"].median()
    global_cap = float(reliable_caps["raw_empirical_share_change_cap"].median()) if len(reliable_caps) else 0.01

    def choose_cap(row: pd.Series) -> tuple[float, str]:
        if bool(row["abs_delta_share_observations"] >= 3) and pd.notna(row["raw_empirical_share_change_cap"]):
            return float(row["raw_empirical_share_change_cap"]), "cell"
        sector_cap = sector_caps.get(row["activity_id"], np.nan)
        if pd.notna(sector_cap):
            return float(sector_cap), "sector_fallback"
        return global_cap, "global_fallback"

    pairs = cell.apply(choose_cap, axis=1, result_type="expand")
    cell["empirical_share_change_cap"] = pairs[0].astype(float).clip(lower=0.0025, upper=0.025)
    cell["fallback_level"] = pairs[1]
    return cell[
        [
            "territory_id",
            "territory_name",
            "federal_district_name",
            "activity_id",
            "okved_section",
            "activity_name",
            "abs_delta_share_median",
            "abs_delta_share_mad",
            "abs_delta_share_p75",
            "abs_delta_share_p90",
            "abs_delta_share_observations",
            "empirical_share_change_cap",
            "fallback_level",
        ]
    ]


def project_to_capped_simplex(target: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> tuple[np.ndarray, bool]:
    target = np.asarray(target, dtype=float)
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    lower = np.minimum(lower, upper)
    if lower.sum() > 1.0 + 1e-10 or upper.sum() < 1.0 - 1e-10:
        raw = np.clip(target, lower, upper)
        total = raw.sum()
        return (raw / total if total > 0 else np.full_like(raw, 1.0 / len(raw))), False
    lo = float(np.min(target - upper) - 1.0)
    hi = float(np.max(target - lower) + 1.0)
    x = np.clip(target, lower, upper)
    for _ in range(100):
        mid = (lo + hi) / 2.0
        x = np.clip(target - mid, lower, upper)
        total = x.sum()
        if total > 1.0:
            lo = mid
        else:
            hi = mid
        if abs(total - 1.0) < 1e-12:
            break
    x = np.clip(target - (lo + hi) / 2.0, lower, upper)
    residual = 1.0 - x.sum()
    if abs(residual) > 1e-10:
        if residual > 0:
            slack = upper - x
            room = slack.sum()
            if room > 0:
                x = x + slack * (residual / room)
        else:
            slack = x - lower
            room = slack.sum()
            if room > 0:
                x = x + slack * (residual / room)
    return x, bool(abs(x.sum() - 1.0) <= 1e-8 and np.all(x >= lower - 1e-8) and np.all(x <= upper + 1e-8))


def allocation_shares(
    econ: pd.DataFrame,
    base: pd.DataFrame,
    scenario: str,
    start_year: int,
    end_year: int,
    transition_calibration: pd.DataFrame | None = None,
) -> pd.DataFrame:
    base_shares = base_sector_shares(base)
    if scenario == "fixed_2024_sector_shares":
        out = econ[["territory_id", "activity_id", "forecast_year"]].merge(base_shares, on=["territory_id", "activity_id"], how="left")
        out["supply_allocation_share"] = out["sector_share_in_region_2024"]
        return out

    demand = econ[["territory_id", "activity_id", "forecast_year", "labor_demand_required_persons"]].copy()
    demand["region_labor_demand_required_persons"] = demand.groupby(["territory_id", "forecast_year"])[
        "labor_demand_required_persons"
    ].transform("sum")
    demand["demand_share_region_year"] = demand["labor_demand_required_persons"] / demand["region_labor_demand_required_persons"]
    demand = demand.merge(base_shares, on=["territory_id", "activity_id"], how="left")

    if scenario == "demand_weighted_sector_shares":
        span = max(1, end_year - start_year)
        demand["transition_progress"] = (demand["forecast_year"] - start_year) / span
        demand["demand_weight"] = 0.50 * demand["transition_progress"].clip(0, 1)
        demand["supply_allocation_share"] = (
            (1 - demand["demand_weight"]) * demand["sector_share_in_region_2024"]
            + demand["demand_weight"] * demand["demand_share_region_year"]
        )
        demand["supply_allocation_share"] = demand["supply_allocation_share"] / demand.groupby(["territory_id", "forecast_year"])[
            "supply_allocation_share"
        ].transform("sum")
        return demand.drop(columns=["transition_progress", "demand_weight"])

    if scenario == "empirical_bounded_transition":
        rows: list[dict] = []
        base_map = base_shares.set_index(["territory_id", "activity_id"])["sector_share_in_region_2024"].to_dict()
        demand_map = demand.set_index(["territory_id", "forecast_year", "activity_id"])["demand_share_region_year"].to_dict()
        region_activities = base_shares.groupby("territory_id")["activity_id"].apply(list).to_dict()
        if transition_calibration is None or transition_calibration.empty:
            cap_map = {key: 0.02 for key in base_map}
            fallback_map = {key: "default_0_02" for key in base_map}
        else:
            cap_map = transition_calibration.set_index(["territory_id", "activity_id"])["empirical_share_change_cap"].to_dict()
            fallback_map = transition_calibration.set_index(["territory_id", "activity_id"])["fallback_level"].to_dict()
        for territory_id, activities in region_activities.items():
            prev = np.array([float(base_map[(territory_id, a)]) for a in activities], dtype=float)
            for year in range(start_year, end_year + 1):
                target = np.array([float(demand_map.get((territory_id, year, a), prev[i])) for i, a in enumerate(activities)], dtype=float)
                if target.sum() > 0:
                    target = target / target.sum()
                caps = np.array([float(cap_map.get((territory_id, a), 0.02)) for a in activities], dtype=float)
                lower = np.maximum(0.0, prev - caps)
                upper = np.minimum(1.0, prev + caps)
                current, converged = project_to_capped_simplex(target, lower, upper)
                violation = np.maximum(0.0, np.abs(current - prev) - caps)
                for i, activity_id in enumerate(activities):
                    rows.append(
                        {
                            "territory_id": territory_id,
                            "activity_id": activity_id,
                            "forecast_year": year,
                            "sector_share_in_region_2024": float(base_map[(territory_id, activity_id)]),
                            "region_employment_2024_persons": np.nan,
                            "demand_share_region_year": float(target[i]),
                            "supply_allocation_share_prev": float(prev[i]),
                            "supply_allocation_share": float(current[i]),
                            "empirical_share_change_cap": float(caps[i]),
                            "share_transition_abs_change": float(abs(current[i] - prev[i])),
                            "share_transition_cap_violation": float(violation[i]),
                            "share_transition_projection_converged": bool(converged),
                            "share_transition_fallback_level": fallback_map.get((territory_id, activity_id), "default_0_02"),
                        }
                    )
                prev = current
        return pd.DataFrame(rows)

    if scenario != "bounded_transition":
        raise ValueError(f"Unknown supply allocation scenario: {scenario}")

    rows: list[dict] = []
    base_map = base_shares.set_index(["territory_id", "activity_id"])["sector_share_in_region_2024"].to_dict()
    demand_map = demand.set_index(["territory_id", "forecast_year", "activity_id"])["demand_share_region_year"].to_dict()
    region_activities = base_shares.groupby("territory_id")["activity_id"].apply(list).to_dict()
    for territory_id, activities in region_activities.items():
        prev = {a: float(base_map[(territory_id, a)]) for a in activities}
        for year in range(start_year, end_year + 1):
            raw_next = {}
            for activity_id in activities:
                target = float(demand_map.get((territory_id, year, activity_id), prev[activity_id]))
                raw_next[activity_id] = max(0.0, prev[activity_id] + float(np.clip(target - prev[activity_id], -0.02, 0.02)))
            total = sum(raw_next.values()) or 1.0
            current = {activity_id: value / total for activity_id, value in raw_next.items()}
            for activity_id, share in current.items():
                rows.append(
                    {
                        "territory_id": territory_id,
                        "activity_id": activity_id,
                        "forecast_year": year,
                        "sector_share_in_region_2024": float(base_map[(territory_id, activity_id)]),
                        "region_employment_2024_persons": np.nan,
                        "supply_allocation_share": share,
                    }
                )
            prev = current
    return pd.DataFrame(rows)


def domestic_supply(
    econ: pd.DataFrame,
    base: pd.DataFrame,
    resources: pd.DataFrame,
    ratios: pd.DataFrame,
    working_age_definition: str,
    scenario: str,
    start_year: int,
    end_year: int,
    unemployment_rates: pd.DataFrame | None = None,
    unemployment_reserve_policy: str = "equal_sector_split",
    unemployment_mobilization_coef: float = 1.0,
    transition_calibration: pd.DataFrame | None = None,
) -> pd.DataFrame:
    res = resources[resources["working_age_definition"] == working_age_definition].copy()
    res = res[(res["year"] >= start_year) & (res["year"] <= end_year)].rename(columns={"year": "forecast_year"})
    region_capacity = res.merge(
        ratios[
            [
                "territory_id",
                "territory_norm",
                "employment_to_workage_ratio_2024_raw",
                "employment_to_workage_ratio_2024",
            ]
        ],
        on="territory_norm",
        how="inner",
    )
    region_capacity["domestic_employment_capacity_region_persons"] = (
        region_capacity["working_age_population_persons"] * region_capacity["employment_to_workage_ratio_2024"]
    )

    unemployment_reserve_policy = unemployment_reserve_policy or "none"
    if unemployment_reserve_policy not in UNEMPLOYMENT_RESERVE_POLICIES:
        raise ValueError(f"Unknown unemployment reserve policy: {unemployment_reserve_policy}")
    region_capacity["unemployment_rate_ilo_15plus_pct"] = 0.0
    region_capacity["unemployment_rate_source_year_used"] = pd.NA
    region_capacity["unemployment_reserve_region_persons"] = 0.0
    region_capacity["unemployment_mobilization_coef"] = float(unemployment_mobilization_coef)

    if unemployment_reserve_policy != "none" and unemployment_rates is not None and len(unemployment_rates):
        ur = unemployment_rates.copy()
        if "forecast_year" not in ur.columns and "year" in ur.columns:
            ur = ur.rename(columns={"year": "forecast_year"})
        if "territory_id" not in ur.columns:
            ur["territory_id"] = ""
        # Prefer stable territory_id matching; fall back to territory_norm for raw direct mode.
        merge_cols = ["territory_id", "forecast_year"] if ur["territory_id"].astype(str).str.len().gt(0).any() else ["territory_norm", "forecast_year"]
        ur_keep = merge_cols + ["unemployment_rate_ilo_15plus_pct"]
        if "unemployment_rate_source_year_used" in ur.columns:
            ur_keep.append("unemployment_rate_source_year_used")
        ur_keep = list(dict.fromkeys(ur_keep))
        region_capacity = region_capacity.merge(ur[ur_keep].drop_duplicates(merge_cols), on=merge_cols, how="left", suffixes=("", "_from_ur"))
        if "unemployment_rate_ilo_15plus_pct_from_ur" in region_capacity.columns:
            region_capacity["unemployment_rate_ilo_15plus_pct"] = region_capacity["unemployment_rate_ilo_15plus_pct_from_ur"].fillna(0.0)
            region_capacity = region_capacity.drop(columns=["unemployment_rate_ilo_15plus_pct_from_ur"])
        else:
            region_capacity["unemployment_rate_ilo_15plus_pct"] = pd.to_numeric(
                region_capacity["unemployment_rate_ilo_15plus_pct"], errors="coerce"
            ).fillna(0.0)
        if "unemployment_rate_source_year_used_from_ur" in region_capacity.columns:
            region_capacity["unemployment_rate_source_year_used"] = region_capacity["unemployment_rate_source_year_used_from_ur"]
            region_capacity = region_capacity.drop(columns=["unemployment_rate_source_year_used_from_ur"])
        region_capacity["unemployment_rate_ilo_15plus_pct"] = pd.to_numeric(
            region_capacity["unemployment_rate_ilo_15plus_pct"], errors="coerce"
        ).fillna(0.0)
        u = region_capacity["unemployment_rate_ilo_15plus_pct"].clip(lower=0.0, upper=99.999)
        # u = U / (E + U). Therefore U = E * u / (100 - u).
        region_capacity["unemployment_reserve_region_persons"] = (
            region_capacity["domestic_employment_capacity_region_persons"] * u / (100.0 - u) * float(unemployment_mobilization_coef)
        )

    alloc = allocation_shares(econ, base, scenario, start_year, end_year, transition_calibration=transition_calibration)
    supply = region_capacity.merge(alloc, on=["territory_id", "forecast_year"], how="inner")
    supply["domestic_sector_supply_allocated_persons"] = (
        supply["domestic_employment_capacity_region_persons"] * supply["supply_allocation_share"]
    )
    if unemployment_reserve_policy == "equal_sector_split":
        supply["unemployment_reserve_allocation_share"] = 1.0 / supply.groupby(["territory_id", "forecast_year"])[
            "activity_id"
        ].transform("count")
    elif unemployment_reserve_policy == "supply_share_split":
        supply["unemployment_reserve_allocation_share"] = supply["supply_allocation_share"]
    else:
        supply["unemployment_reserve_allocation_share"] = 0.0
    supply["unemployment_reserve_sector_allocated_persons"] = (
        supply["unemployment_reserve_region_persons"] * supply["unemployment_reserve_allocation_share"]
    )
    supply["domestic_sector_supply_total_with_unemployment_reserve_persons"] = (
        supply["domestic_sector_supply_allocated_persons"] + supply["unemployment_reserve_sector_allocated_persons"]
    )
    supply["supply_allocation_scenario"] = scenario
    supply["unemployment_reserve_policy"] = unemployment_reserve_policy
    keep_cols = [
        "territory_id",
        "activity_id",
        "forecast_year",
        "working_age_population_persons",
        "employment_to_workage_ratio_2024_raw",
        "employment_to_workage_ratio_2024",
        "domestic_employment_capacity_region_persons",
        "sector_share_in_region_2024",
        "supply_allocation_share",
        "demand_share_region_year",
        "supply_allocation_share_prev",
        "empirical_share_change_cap",
        "share_transition_abs_change",
        "share_transition_cap_violation",
        "share_transition_projection_converged",
        "share_transition_fallback_level",
        "domestic_sector_supply_allocated_persons",
        "unemployment_rate_ilo_15plus_pct",
        "unemployment_rate_source_year_used",
        "unemployment_mobilization_coef",
        "unemployment_reserve_region_persons",
        "unemployment_reserve_allocation_share",
        "unemployment_reserve_sector_allocated_persons",
        "domestic_sector_supply_total_with_unemployment_reserve_persons",
        "supply_allocation_scenario",
        "unemployment_reserve_policy",
    ]
    return supply[[c for c in keep_cols if c in supply.columns]]

def finalize_need(
    econ: pd.DataFrame,
    supply: pd.DataFrame,
    population_scenario: str,
    working_age_definition: str,
    migrant_retention_rate: float = 1.0,
) -> pd.DataFrame:
    final = econ.merge(supply, on=["territory_id", "activity_id", "forecast_year"], how="left", validate="one_to_one")
    missing_supply = int(final["domestic_sector_supply_allocated_persons"].isna().sum())
    if missing_supply:
        raise ValueError(f"Domestic supply was not matched for {missing_supply} model cells")
    if "domestic_sector_supply_total_with_unemployment_reserve_persons" not in final.columns:
        final["domestic_sector_supply_total_with_unemployment_reserve_persons"] = final["domestic_sector_supply_allocated_persons"]
    final["gross_labor_deficit_before_unemployment_reserve_persons"] = (
        final["labor_demand_required_persons"] - final["domestic_sector_supply_allocated_persons"]
    )
    final["gross_labor_deficit_persons"] = (
        final["labor_demand_required_persons"] - final["domestic_sector_supply_total_with_unemployment_reserve_persons"]
    )
    final["foreign_labor_stock_need_persons"] = final["gross_labor_deficit_persons"].clip(lower=0)
    # Backward-compatible alias for previous dashboard/scripts.
    final["foreign_labor_migration_need_persons"] = final["foreign_labor_stock_need_persons"]
    final["no_foreign_labor_need_flag"] = final["foreign_labor_stock_need_persons"].eq(0)
    final["population_scenario"] = population_scenario
    final["working_age_definition"] = working_age_definition
    final["migrant_retention_rate"] = float(np.clip(migrant_retention_rate, 0.0, 1.0))

    final = final.sort_values(["territory_id", "activity_id", "forecast_year"]).copy()
    final["previous_foreign_labor_stock_need_persons"] = final.groupby(["territory_id", "activity_id"])[
        "foreign_labor_stock_need_persons"
    ].shift(1).fillna(0.0)
    final["annual_new_foreign_labor_stock_delta_persons"] = (
        final["foreign_labor_stock_need_persons"] - final["previous_foreign_labor_stock_need_persons"]
    ).clip(lower=0)
    final["annual_replacement_foreign_labor_flow_persons"] = (
        final["previous_foreign_labor_stock_need_persons"] * (1.0 - final["migrant_retention_rate"])
    )
    final["annual_foreign_labor_quota_persons"] = (
        final["annual_new_foreign_labor_stock_delta_persons"] + final["annual_replacement_foreign_labor_flow_persons"]
    )
    final["cumulative_foreign_labor_quota_persons"] = final.groupby(["territory_id", "activity_id"])[
        "annual_foreign_labor_quota_persons"
    ].cumsum()
    final["annual_new_stock_delta_persons"] = final["annual_new_foreign_labor_stock_delta_persons"]
    final["annual_replacement_flow_persons"] = final["annual_replacement_foreign_labor_flow_persons"]
    final["recommended_annual_quota_persons"] = final["annual_foreign_labor_quota_persons"]
    final["cumulative_recommended_quota_persons"] = final["cumulative_foreign_labor_quota_persons"]

    required_order = [
        "territory_id",
        "territory_name",
        "federal_district_name",
        "activity_id",
        "okved_section",
        "activity_name",
        "forecast_year",
        "employment_2024_persons",
        "target_real_vrp_growth",
        "productivity_growth_forecast",
        "productivity_growth_forecast_yearly",
        "productivity_growth_forecast_pct",
        "productivity_growth_forecast_static",
        "productivity_trajectory_convergence_weight",
        "productivity_forecast_model",
        "training_source_coverage_flag",
        "forecast_quality_flag",
        "productivity_forecast_is_clipped",
        "labor_demand_required_persons",
        "working_age_population_persons",
        "employment_to_workage_ratio_2024_raw",
        "employment_to_workage_ratio_2024",
        "domestic_employment_capacity_region_persons",
        "sector_share_in_region_2024",
        "supply_allocation_share",
        "demand_share_region_year",
        "supply_allocation_share_prev",
        "empirical_share_change_cap",
        "share_transition_abs_change",
        "share_transition_cap_violation",
        "share_transition_projection_converged",
        "share_transition_fallback_level",
        "domestic_sector_supply_allocated_persons",
        "unemployment_rate_ilo_15plus_pct",
        "unemployment_rate_source_year_used",
        "unemployment_mobilization_coef",
        "unemployment_reserve_region_persons",
        "unemployment_reserve_allocation_share",
        "unemployment_reserve_sector_allocated_persons",
        "domestic_sector_supply_total_with_unemployment_reserve_persons",
        "gross_labor_deficit_before_unemployment_reserve_persons",
        "gross_labor_deficit_persons",
        "foreign_labor_stock_need_persons",
        "previous_foreign_labor_stock_need_persons",
        "annual_new_foreign_labor_stock_delta_persons",
        "annual_replacement_foreign_labor_flow_persons",
        "annual_foreign_labor_quota_persons",
        "cumulative_foreign_labor_quota_persons",
        "annual_new_stock_delta_persons",
        "annual_replacement_flow_persons",
        "recommended_annual_quota_persons",
        "cumulative_recommended_quota_persons",
        "foreign_labor_migration_need_persons",
        "no_foreign_labor_need_flag",
        "population_scenario",
        "working_age_definition",
        "productivity_scenario",
        "supply_allocation_scenario",
        "unemployment_reserve_policy",
        "migrant_retention_rate",
    ]
    required_order = [c for c in required_order if c in final.columns]
    return final[required_order + [c for c in final.columns if c not in required_order]]

def summarize_outputs(final: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    scenario_cols = [
        "population_scenario",
        "working_age_definition",
        "productivity_scenario",
        "supply_allocation_scenario",
        "unemployment_reserve_policy",
    ]
    by_year = (
        final.groupby(scenario_cols + ["forecast_year"], as_index=False)
        .agg(
            labor_demand_required_persons=("labor_demand_required_persons", "sum"),
            domestic_sector_supply_allocated_persons=("domestic_sector_supply_allocated_persons", "sum"),
            unemployment_reserve_sector_allocated_persons=("unemployment_reserve_sector_allocated_persons", "sum"),
            domestic_sector_supply_total_with_unemployment_reserve_persons=(
                "domestic_sector_supply_total_with_unemployment_reserve_persons",
                "sum",
            ),
            gross_labor_deficit_before_unemployment_reserve_persons=(
                "gross_labor_deficit_before_unemployment_reserve_persons",
                "sum",
            ),
            gross_labor_deficit_persons=("gross_labor_deficit_persons", "sum"),
            foreign_labor_stock_need_persons=("foreign_labor_stock_need_persons", "sum"),
            annual_new_foreign_labor_stock_delta_persons=("annual_new_foreign_labor_stock_delta_persons", "sum"),
            annual_replacement_foreign_labor_flow_persons=("annual_replacement_foreign_labor_flow_persons", "sum"),
            annual_foreign_labor_quota_persons=("annual_foreign_labor_quota_persons", "sum"),
            cumulative_foreign_labor_quota_persons=("annual_foreign_labor_quota_persons", "sum"),
            annual_new_stock_delta_persons=("annual_new_stock_delta_persons", "sum"),
            annual_replacement_flow_persons=("annual_replacement_flow_persons", "sum"),
            recommended_annual_quota_persons=("recommended_annual_quota_persons", "sum"),
            cumulative_recommended_quota_persons=("recommended_annual_quota_persons", "sum"),
            foreign_labor_migration_need_persons=("foreign_labor_migration_need_persons", "sum"),
            positive_region_sector_deficit_cells=("foreign_labor_stock_need_persons", lambda s: int((s > 0).sum())),
            positive_recommended_quota_cells=("recommended_annual_quota_persons", lambda s: int((s > 0).sum())),
        )
        .sort_values(scenario_cols + ["forecast_year"])
    )
    by_year["cumulative_foreign_labor_quota_persons"] = by_year.groupby(scenario_cols)[
        "annual_foreign_labor_quota_persons"
    ].cumsum()
    by_year["cumulative_recommended_quota_persons"] = by_year.groupby(scenario_cols)[
        "recommended_annual_quota_persons"
    ].cumsum()

    final_year = int(final["forecast_year"].max())
    final_year_df = final[final["forecast_year"].eq(final_year)]
    region_horizon = (
        final.groupby(scenario_cols + ["territory_id", "territory_name", "federal_district_name"], as_index=False)
        .agg(
            annual_foreign_labor_quota_horizon_persons=("annual_foreign_labor_quota_persons", "sum"),
            recommended_annual_quota_horizon_persons=("recommended_annual_quota_persons", "sum"),
            labor_demand_required_horizon_persons=("labor_demand_required_persons", "sum"),
            domestic_sector_supply_total_horizon_persons=("domestic_sector_supply_total_with_unemployment_reserve_persons", "sum"),
            unemployment_reserve_horizon_persons=("unemployment_reserve_sector_allocated_persons", "sum"),
            foreign_labor_migration_need_persons=("foreign_labor_migration_need_persons", "sum"),
        )
    )
    region_final = (
        final_year_df.groupby(scenario_cols + ["territory_id", "territory_name", "federal_district_name"], as_index=False)
        .agg(foreign_labor_stock_need_final_year_persons=("foreign_labor_stock_need_persons", "sum"))
    )
    by_region = region_horizon.merge(region_final, on=scenario_cols + ["territory_id", "territory_name", "federal_district_name"], how="left").sort_values(
        "foreign_labor_stock_need_final_year_persons", ascending=False
    )

    sector_horizon = (
        final.groupby(scenario_cols + ["activity_id", "okved_section", "activity_name"], as_index=False)
        .agg(
            annual_foreign_labor_quota_horizon_persons=("annual_foreign_labor_quota_persons", "sum"),
            recommended_annual_quota_horizon_persons=("recommended_annual_quota_persons", "sum"),
            labor_demand_required_horizon_persons=("labor_demand_required_persons", "sum"),
            domestic_sector_supply_total_horizon_persons=("domestic_sector_supply_total_with_unemployment_reserve_persons", "sum"),
            unemployment_reserve_horizon_persons=("unemployment_reserve_sector_allocated_persons", "sum"),
            foreign_labor_migration_need_persons=("foreign_labor_migration_need_persons", "sum"),
        )
    )
    sector_final = (
        final_year_df.groupby(scenario_cols + ["activity_id", "okved_section", "activity_name"], as_index=False)
        .agg(foreign_labor_stock_need_final_year_persons=("foreign_labor_stock_need_persons", "sum"))
    )
    by_sector = sector_horizon.merge(sector_final, on=scenario_cols + ["activity_id", "okved_section", "activity_name"], how="left").sort_values(
        "foreign_labor_stock_need_final_year_persons", ascending=False
    )
    return by_year, by_region, by_sector


def write_recommended_quota_outputs(final: pd.DataFrame, out_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detail_cols = [
        "territory_id",
        "territory_name",
        "federal_district_name",
        "activity_id",
        "okved_section",
        "activity_name",
        "forecast_year",
        "target_real_vrp_growth",
        "productivity_growth_forecast_yearly",
        "labor_demand_required_persons",
        "domestic_sector_supply_allocated_persons",
        "unemployment_rate_ilo_15plus_pct",
        "unemployment_reserve_sector_allocated_persons",
        "domestic_sector_supply_total_with_unemployment_reserve_persons",
        "foreign_labor_stock_need_persons",
        "recommended_annual_quota_persons",
        "cumulative_recommended_quota_persons",
        "supply_allocation_share",
        "sector_share_in_region_2024",
        "forecast_quality_flag",
    ]
    detail = final[[c for c in detail_cols if c in final.columns]].copy()
    write_csv(detail, out_dir / "recommended_quota_region_sector_year.csv")

    region = (
        final.groupby(["territory_id", "territory_name", "federal_district_name", "forecast_year"], as_index=False)
        .agg(
            foreign_labor_stock_need_persons=("foreign_labor_stock_need_persons", "sum"),
            recommended_annual_quota_persons=("recommended_annual_quota_persons", "sum"),
            cumulative_recommended_quota_persons=("cumulative_recommended_quota_persons", "sum"),
            domestic_sector_supply_total_with_unemployment_reserve_persons=(
                "domestic_sector_supply_total_with_unemployment_reserve_persons",
                "sum",
            ),
            unemployment_reserve_sector_allocated_persons=("unemployment_reserve_sector_allocated_persons", "sum"),
            labor_demand_required_persons=("labor_demand_required_persons", "sum"),
        )
        .sort_values(["forecast_year", "recommended_annual_quota_persons"], ascending=[True, False])
    )
    sector = (
        final.groupby(["activity_id", "okved_section", "activity_name", "forecast_year"], as_index=False)
        .agg(
            foreign_labor_stock_need_persons=("foreign_labor_stock_need_persons", "sum"),
            recommended_annual_quota_persons=("recommended_annual_quota_persons", "sum"),
            cumulative_recommended_quota_persons=("cumulative_recommended_quota_persons", "sum"),
            domestic_sector_supply_total_with_unemployment_reserve_persons=(
                "domestic_sector_supply_total_with_unemployment_reserve_persons",
                "sum",
            ),
            unemployment_reserve_sector_allocated_persons=("unemployment_reserve_sector_allocated_persons", "sum"),
            labor_demand_required_persons=("labor_demand_required_persons", "sum"),
        )
        .sort_values(["forecast_year", "recommended_annual_quota_persons"], ascending=[True, False])
    )
    write_csv(region, out_dir / "recommended_quota_by_region.csv")
    write_csv(sector, out_dir / "recommended_quota_by_sector.csv")

    control_years = [year for year in CONTROL_YEARS if final["forecast_year"].min() <= year <= final["forecast_year"].max()]
    total = (
        final[final["forecast_year"].isin(control_years)]
        .groupby(["forecast_year"], as_index=False)
        .agg(
            foreign_labor_stock_need_persons=("foreign_labor_stock_need_persons", "sum"),
            recommended_annual_quota_persons=("recommended_annual_quota_persons", "sum"),
            cumulative_recommended_quota_persons=("cumulative_recommended_quota_persons", "sum"),
            domestic_sector_supply_total_with_unemployment_reserve_persons=(
                "domestic_sector_supply_total_with_unemployment_reserve_persons",
                "sum",
            ),
            unemployment_reserve_sector_allocated_persons=("unemployment_reserve_sector_allocated_persons", "sum"),
            labor_demand_required_persons=("labor_demand_required_persons", "sum"),
        )
    )
    total["summary_level"] = "total"
    total["territory_id"] = ""
    total["territory_name"] = "Российская Федерация, модельная вселенная"
    total["activity_id"] = ""
    total["okved_section"] = ""
    total["activity_name"] = "Все разделы ОКВЭД"
    control = total[
        [
            "summary_level",
            "territory_id",
            "territory_name",
            "activity_id",
            "okved_section",
            "activity_name",
            "forecast_year",
            "foreign_labor_stock_need_persons",
            "recommended_annual_quota_persons",
            "cumulative_recommended_quota_persons",
            "domestic_sector_supply_total_with_unemployment_reserve_persons",
            "unemployment_reserve_sector_allocated_persons",
            "labor_demand_required_persons",
        ]
    ]
    write_csv(control, out_dir / "recommended_quota_control_years_2030_2036_2050.csv")
    return detail, region, sector


def write_v4_final_report(
    path: Path,
    result: dict,
    by_year: pd.DataFrame,
    by_region: pd.DataFrame,
    by_sector: pd.DataFrame,
    quality: dict,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    control = by_year[by_year["forecast_year"].isin(CONTROL_YEARS)].copy()
    control_lines = "\n".join(
        f"| {int(r.forecast_year)} | {fmt_int(r.recommended_annual_quota_persons)} | {fmt_int(r.foreign_labor_stock_need_persons)} | {fmt_int(r.cumulative_recommended_quota_persons)} |"
        for r in control.itertuples()
    )
    final_year = int(result["end_year"])
    top_regions = by_region[by_region["forecast_year"].eq(final_year)] if "forecast_year" in by_region.columns else by_region
    if top_regions.empty:
        top_regions = by_region
    top_regions = top_regions.sort_values("recommended_annual_quota_persons", ascending=False).head(20)
    top_sectors = by_sector[by_sector["forecast_year"].eq(final_year)] if "forecast_year" in by_sector.columns else by_sector
    if top_sectors.empty:
        top_sectors = by_sector
    top_sectors = top_sectors.sort_values("recommended_annual_quota_persons", ascending=False).head(20)
    region_lines = "\n".join(f"| {r.territory_name} | {fmt_int(r.recommended_annual_quota_persons)} | {fmt_int(r.foreign_labor_stock_need_persons)} |" for r in top_regions.itertuples())
    sector_lines = "\n".join(f"| {r.okved_section} | {r.activity_name} | {fmt_int(r.recommended_annual_quota_persons)} | {fmt_int(r.foreign_labor_stock_need_persons)} |" for r in top_sectors.itertuples())
    text = f"""# Финальный отчёт v5

Дата сборки: {datetime.now(timezone.utc).isoformat()}

## 1. Итоговая квота

Административный показатель v5 — `recommended_annual_quota_persons`. Он равен положительному годовому приросту дефицита на конец года плюс замещающий приток: `annual_new_stock_delta_persons + annual_replacement_flow_persons`. В базовой версии `migrant_retention_rate=1.0`, поэтому замещающий приток равен нулю. `foreign_labor_stock_need_persons` сохраняется как дефицит на конец конкретного года и не суммируется как уникальные мигранты.

## 2. Единый baseline

Публичная линия одна: noMIG x возраст 15-72 x champion productivity x empirical_bounded_transition x unemployment equal sector split. Альтернативные алгоритмы используются только в QA/backtesting.

## 3. Производительность труда

Champion-модель: `{V5_PRODUCTIVITY_MODEL}`. История переводится в логарифмические темпы; приоритет training target: наблюдаемая производительность по ВРП/занятости, затем официальный гибридный индекс, затем иерархическая импутация. Прогноз раскладывается на общий, отраслевой, региональный факторы и остаток ячейки, а компоненты возвращаются к робастным долгосрочным уровням.

## 4. Отраслевые доли

`empirical_bounded_transition` использует исторические изменения долей занятости 2017-2024. Для каждой ячейки рассчитывается эмпирический cap, после чего доли проектируются на simplex с ограничениями суммы 1, неотрицательности и годового изменения.

## 5. Резерв безработных

Резерв МОТ сохранён: `U = E * u/(100-u)`, мобилизация 100%, распределение равными долями внутри региона. Последний официальный уровень 2025 протягивается вперёд.

## 6. Контрольные годы

| Год | Рекомендуемая годовая квота | Дефицит на конец года | Накопленная квота |
|---:|---:|---:|---:|
{control_lines}

## 7. Топ-20 регионов, {final_year}

| Регион | Годовая квота | Дефицит на конец года |
|---|---:|---:|
{region_lines}

## 8. Топ-20 отраслей, {final_year}

| ОКВЭД | Отрасль | Годовая квота | Дефицит на конец года |
|---|---|---:|---:|
{sector_lines}

## 9. Ограничения

- Нет профессионально-квалификационной матрицы: квота пока регионально-отраслевая.
- Резерв безработных распределяется равными долями и не учитывает профессию, образование и готовность к межотраслевому переходу.
- Новые субъекты, отсутствующие в экономической панели, не включены в 85-региональную модельную вселенную.
- Производительность является статистически демпфированным прогнозом по короткой истории, а не структурной технологической моделью.

## QA-сводка

```json
{json.dumps(json_safe(quality), ensure_ascii=False, indent=2)}
```
"""
    path.write_text(text, encoding="utf-8")

def scenario_sensitivity(
    base: pd.DataFrame,
    prod_all: pd.DataFrame,
    world_growth: pd.DataFrame,
    resources: pd.DataFrame,
    population_scenario: str,
    start_year: int,
    end_year: int,
    unemployment_rates: pd.DataFrame | None = None,
    unemployment_reserve_policy: str = "equal_sector_split",
    unemployment_mobilization_coef: float = 1.0,
    migrant_retention_rate: float = 1.0,
) -> pd.DataFrame:
    rows = []
    for prod_scenario in LEGACY_PRODUCTIVITY_SCENARIOS:
        prod_base = prod_all[prod_all["productivity_scenario"] == prod_scenario]
        prod_yearly = build_productivity_trajectory(prod_base, start_year, end_year)
        econ = economic_labor_demand(prod_yearly, world_growth, start_year, end_year)
        for working_age_definition in WORKING_AGE_DEFINITIONS:
            ratios = employment_ratios(base, resources, working_age_definition)
            for allocation_scenario in LEGACY_SUPPLY_ALLOCATION_SCENARIOS:
                supply = domestic_supply(
                    econ,
                    base,
                    resources,
                    ratios,
                    working_age_definition,
                    allocation_scenario,
                    start_year,
                    end_year,
                    unemployment_rates=unemployment_rates,
                    unemployment_reserve_policy=unemployment_reserve_policy,
                    unemployment_mobilization_coef=unemployment_mobilization_coef,
                )
                final = finalize_need(
                    econ,
                    supply,
                    population_scenario,
                    working_age_definition,
                    migrant_retention_rate=migrant_retention_rate,
                )
                summary = (
                    final.groupby(
                        [
                            "population_scenario",
                            "working_age_definition",
                            "productivity_scenario",
                            "supply_allocation_scenario",
                            "unemployment_reserve_policy",
                            "forecast_year",
                        ],
                        as_index=False,
                    )
                    .agg(
                        labor_demand_required_persons=("labor_demand_required_persons", "sum"),
                        domestic_sector_supply_total_with_unemployment_reserve_persons=(
                            "domestic_sector_supply_total_with_unemployment_reserve_persons",
                            "sum",
                        ),
                        unemployment_reserve_sector_allocated_persons=("unemployment_reserve_sector_allocated_persons", "sum"),
                        foreign_labor_stock_need_persons=("foreign_labor_stock_need_persons", "sum"),
                        annual_foreign_labor_quota_persons=("annual_foreign_labor_quota_persons", "sum"),
                        foreign_labor_migration_need_persons=("foreign_labor_migration_need_persons", "sum"),
                        positive_region_sector_deficit_cells=("foreign_labor_stock_need_persons", lambda s: int((s > 0).sum())),
                    )
                )
                rows.append(summary)
    return pd.concat(rows, ignore_index=True)

def build_limitations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "limitation_id": "L01",
                "limitation": "Оценка является остаточной трудовой потребностью, а не прямым числом мигрантов.",
                "implication": "Для квот нужен следующий слой ОКВЭД x профессия x квалификация и правовая фильтрация.",
            },
            {
                "limitation_id": "L02",
                "limitation": "База использует noMIG, чтобы не включать миграцию в демографический ресурс.",
                "implication": "withMIG допустим только как чувствительный сценарий, не как базовый остаточный расчёт.",
            },
            {
                "limitation_id": "L03",
                "limitation": "Ячейки ОКВЭД T с отсутствующей занятостью 2024 исключены без импутации.",
                "implication": "Их вклад не переносится на другие отрасли и фиксируется в QA.",
            },
            {
                "limitation_id": "L04",
                "limitation": "Прогноз производительности использует shrinkage и клиппинг, но не является структурной моделью технологий.",
                "implication": "Высокошумные регионально-отраслевые ряды не должны трактоваться как точечный прогноз.",
            },
            {
                "limitation_id": "L05",
                "limitation": "Новые субъекты не включены, если они отсутствуют в экономической панели.",
                "implication": "Федеральные итоги сопоставимы с текущей модельной экономической вселенной.",
            },
            {
                "limitation_id": "L06",
                "limitation": "Уровень безработицы по МОТ задан в процентах к рабочей силе, поэтому численность безработных рассчитывается алгебраически как E*u/(100-u).",
                "implication": "Расчет точен при сопоставимости базы занятых E с занятостью обследования рабочей силы; это проверяется в QA и оговаривается как допущение.",
            },
            {
                "limitation_id": "L07",
                "limitation": "Резерв безработных в базовом сценарии распределяется по отраслям региона равными долями.",
                "implication": "Это нейтральная первая аппроксимация, но она не учитывает профессию, образование и отраслевые барьеры входа.",
            },
            {
                "limitation_id": "L08",
                "limitation": "Годовая квота отделена от запаса потребности; по умолчанию не добавляется замещение выбывающих мигрантов.",
                "implication": "Для административной квоты можно задать коэффициент удержания через --migrant-retention-rate.",
            },
        ]
    )


def write_validation_workbook(path: Path, tables: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in tables.items():
            safe_name = re.sub(r"[\[\]\:\*\?\/\\]", "_", sheet_name)[:31]
            if df is None:
                df = pd.DataFrame()
            shown = df.head(10000).copy()
            shown.to_excel(writer, sheet_name=safe_name, index=False)
        notes = pd.DataFrame(
            [
                {"note": "Sheets are capped at 10,000 rows for workbook readability; full CSV files are authoritative."},
                {"note": f"Generated at {datetime.now(timezone.utc).isoformat()}"},
            ]
        )
        notes.to_excel(writer, sheet_name="notes", index=False)


def fmt_int(value: float) -> str:
    if pd.isna(value):
        return "н/д"
    return f"{value:,.0f}".replace(",", " ")


def write_report(
    path: Path,
    result: dict,
    by_year: pd.DataFrame,
    by_region: pd.DataFrame,
    by_sector: pd.DataFrame,
    sensitivity: pd.DataFrame,
    limitations: pd.DataFrame,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    year_lines = "\n".join(
        f"| {int(r.forecast_year)} | {fmt_int(r.recommended_annual_quota_persons)} | {fmt_int(r.foreign_labor_stock_need_persons)} | {fmt_int(r.cumulative_recommended_quota_persons)} | {fmt_int(r.labor_demand_required_persons)} |"
        for r in by_year.itertuples()
    )
    region_lines = "\n".join(
        f"| {r.territory_name} | {fmt_int(getattr(r, 'recommended_annual_quota_horizon_persons', np.nan))} | {fmt_int(r.foreign_labor_stock_need_final_year_persons)} |" for r in by_region.head(10).itertuples()
    )
    sector_lines = "\n".join(
        f"| {r.okved_section} | {r.activity_name} | {fmt_int(getattr(r, 'recommended_annual_quota_horizon_persons', np.nan))} | {fmt_int(r.foreign_labor_stock_need_final_year_persons)} |"
        for r in by_sector.head(10).itertuples()
    )
    limitation_lines = "\n".join(f"- {r.limitation} {r.implication}" for r in limitations.itertuples())
    sensitivity_total = (
        sensitivity.groupby(["working_age_definition", "productivity_scenario", "supply_allocation_scenario"], as_index=False)[
            "foreign_labor_migration_need_persons"
        ]
        .sum()
        .sort_values("foreign_labor_migration_need_persons")
    )
    sens_lines = "\n".join(
        f"| {r.working_age_definition} | {r.productivity_scenario} | {r.supply_allocation_scenario} | {fmt_int(r.foreign_labor_migration_need_persons)} |"
        for r in sensitivity_total.itertuples()
    )
    text = f"""# Валидационный отчёт расчётной модели

Дата сборки: {datetime.now(timezone.utc).isoformat()}

## Структура входных данных

- Экономическая панель: `data/processed/emiss_vrp_employment_productivity_panel_joined.csv`.
- Факты ЭМИСС в длинном виде: `data/processed/emiss_vrp_employment_productivity_fact_long.csv`.
- Демография: `POP_wide_male_noMIG.xlsx` и `POP_wide_female_noMIG.xlsx`, лист `by_age`.
- Целевой рост: `data/forecasts_preliminary/world_growth_target_oecd_ltm_2025_2050.csv`.

Используется только модельная экономическая вселенная: непересекающиеся регионы и модельные секции ОКВЭД. РФ, федеральные округа и перекрывающиеся родительские территории исключены.

## Источники и сценарии

Базовый источник мирового роста: {PRIMARY_WORLD_GROWTH_SOURCE}, дата обращения {WORLD_GROWTH_ACCESS_DATE}, URL: {PRIMARY_WORLD_GROWTH_URL}. В v5 годовые темпы считаются из уровней OECD LTM `W.GDPVTRD.BAU1.A`; техническое продление IMF 3,2% после 2027 г. не используется.

Базовая демография: `noMIG`. Этот сценарий выбран потому, что `withMIG` уже содержит миграционную компоненту, которую модель оценивает как остаточный дефицит.

Основной публикационный сценарий: `{result["population_scenario"]} x {result["working_age_definition"]} x {result["productivity_scenario"]} x {result["supply_allocation_scenario"]}`.

## Формулы модели

`Y = L x P`, где `Y` — реальный выпуск/ВРП, `L` — занятость, `P` — производительность труда.

`L_required[t+1] = L_required[t] x (1 + target_real_vrp_growth[t+1]) / (1 + productivity_growth_forecast[region, sector])`.

`domestic_capacity[region, year] = working_age_population[region, year] x employment_to_workage_ratio_2024`.

`foreign_labor_migration_need = max(0, labor_demand_required - domestic_sector_supply)`.

Отрицательные остатки одной отрасли не вычитаются из дефицита другой отрасли.

## Прогноз производительности

В v5 для основной линии используется champion-модель `{V5_PRODUCTIVITY_MODEL}`: лог-темпы раскладываются на общий, отраслевой, региональный факторы и остаток ячейки, а затем каждый компонент возвращается к робастному долгосрочному уровню. Индекс `104.6` трактуется как `log(104.6 / 100)` в обучающей истории и возвращается пользователю как процентный темп.

## Результаты по годам

| Год | Рекомендуемая годовая квота | Дефицит на конец года | Накопленная квота | Требуемая занятость |
|---:|---:|---:|---:|---:|
{year_lines}

## Топ-10 регионов

| Регион | Квота за горизонт | Дефицит на конец финального года |
|---|---:|---:|
{region_lines}

## Топ-10 отраслей

| ОКВЭД | Отрасль | Квота за горизонт | Дефицит на конец финального года |
|---|---|---:|---:|
{sector_lines}

## Чувствительность

| Возраст | Производительность | Распределение | Суммарная потребность |
|---|---|---|---:|
{sens_lines}

## Ограничения

{limitation_lines}

Итоговая административная квота v5 — `recommended_annual_quota_persons`. `foreign_labor_stock_need_persons` является дефицитом на конец года и не суммируется по годам как уникальные мигранты. Для государственных квот нужен следующий слой: матрица `ОКВЭД x профессия x квалификация` и правовая фильтрация допустимых категорий занятости.

## Файлы результата

- `foreign_labor_migration_need_region_sector_year.csv`
- `recommended_quota_region_sector_year.csv`
- `recommended_quota_by_region.csv`
- `recommended_quota_by_sector.csv`
- `productivity_forecast_region_sector_year.csv`
- `qa_model_summary.json`
- `outputs/codex_audit/model_validation_tables.xlsx`
"""
    path.write_text(text, encoding="utf-8")


def write_subagent_findings(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """# Subagent Findings

## data-engineer
Проверены структура проекта, raw/processed файлы, годы, типы, ключи, фильтры регионов и ОКВЭД. Найдены mojibake-имена raw EMISS, 29 исключаемых ячеек OKVED_T в 2024 году и необходимость обновить manifest.

## demography-agent
Проверены POP XLSX. Реальный формат: лист `by_age`, колонки `Территория`, `Год`, возраста `0..99`, `100+`; территории внутри блока требуют forward-fill. Отрицательных и пропущенных значений населения не найдено.

## labor-economist-agent
Проверена формула `Y = L x P`, перевод индекса производительности и IMF-сценарий. Формула спроса корректна; прежние outputs устарели относительно добавленных POP-файлов.

## qa-auditor
Проверены дубликаты, отрицательные значения, dashboard fallback, коэффициенты занятость/возраст. Нужны QA-таблицы по ratios, unmatched regions, productivity outliers и freshness.

## reporting-agent
Проверены публикационные deliverables. Финальный CSV, summary-файлы, validation report/workbook и dashboard final metadata отсутствовали до текущей реализации.
""",
        encoding="utf-8",
    )


def run_model(args: argparse.Namespace) -> dict:
    out_dir = Path(args.out_dir)
    audit_dir = Path(args.audit_dir)
    processed_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    start_year = int(args.start_year)
    end_year = int(args.end_year)
    working_age_definition = f"{args.work_age_min}-{args.work_age_max}"
    if working_age_definition not in WORKING_AGE_DEFINITIONS:
        WORKING_AGE_DEFINITIONS[working_age_definition] = (int(args.work_age_min), int(args.work_age_max))

    model_panel, base, excluded = load_economic_base(Path(args.economic_panel), args.base_year, audit_dir)
    world_growth, world_qa = read_world_growth(Path(args.world_growth), start_year, end_year)
    pop_cache = Path(args.population_long_cache) if args.population_long_cache else None
    pop_long, population_qa = read_population_scenario_cached(Path(args.population_dir), args.population_scenario, pop_cache)
    population_long_path = out_dir / f"population_long_{args.population_scenario}.csv"
    write_csv(pop_long, population_long_path)

    unemployment_rates, unemployment_qa = read_unemployment_rates(
        Path(args.unemployment_rate) if args.unemployment_rate else None, start_year, end_year
    )

    resources = build_working_age_resources(pop_long)
    resources = resources[(resources["year"] >= 2024) & (resources["year"] <= end_year)].copy()
    write_csv(resources, out_dir / "working_age_population_by_region_year.csv")

    crosswalk, unmatched_econ, unmatched_pop = build_crosswalk(pop_long, base, processed_dir, audit_dir)
    if len(unmatched_econ):
        raise ValueError(f"Unmatched economic territories in population data: {len(unmatched_econ)}")

    legacy_prod_all = pd.concat([productivity_forecast(base, scenario) for scenario in LEGACY_PRODUCTIVITY_SCENARIOS], ignore_index=True)
    prod_cols = [
        "territory_id",
        "territory_name",
        "federal_district_name",
        "activity_id",
        "okved_section",
        "activity_name",
        "employment_persons",
        "official_productivity_coverage_scope",
        "official_prod_index_hybrid_pct",
        "official_productivity_growth_from_index",
        "historical_productivity_cagr_2017_2022_raw",
        "historical_productivity_cagr_2017_2022",
        "sector_productivity_cagr_median",
        "region_productivity_cagr_median",
        "global_productivity_cagr_median",
        "productivity_growth_forecast",
        "productivity_source_explanation",
        "productivity_scenario",
        "productivity_forecast_clip_min",
        "productivity_forecast_clip_max",
    ]
    productivity_qa = {}
    if args.productivity_scenario == CHAMPION_PRODUCTIVITY_SCENARIO:
        prod_history, champion_prod_yearly, productivity_backtest, productivity_qa = build_champion_productivity_forecast(
            model_panel,
            base,
            start_year,
            end_year,
        )
        write_csv(prod_history, out_dir / "productivity_history_region_sector_year.csv")
        write_csv(champion_prod_yearly, out_dir / "productivity_forecast_region_sector_year.csv")
        write_csv(build_productivity_dashboard_summary(champion_prod_yearly), out_dir / "productivity_dashboard_summary.csv")
        clipping_qa = write_and_validate_productivity_clipping(champion_prod_yearly, audit_dir)
        productivity_qa["max_sector_clipped_share_control_years"] = (
            float(clipping_qa["clipped_share"].max()) if not clipping_qa.empty else 0.0
        )

        legacy_baseline = build_productivity_trajectory(
            legacy_prod_all[legacy_prod_all["productivity_scenario"] == "baseline"],
            start_year,
            end_year,
        )
        comparison = champion_prod_yearly.merge(
            legacy_baseline[
                [
                    "territory_id",
                    "activity_id",
                    "forecast_year",
                    "productivity_growth_forecast_yearly",
                ]
            ].rename(columns={"productivity_growth_forecast_yearly": "v3_productivity_growth_forecast_yearly"}),
            on=["territory_id", "activity_id", "forecast_year"],
            how="left",
        )
        comparison["v5_minus_v3_productivity_growth"] = (
            comparison["productivity_growth_forecast_yearly"] - comparison["v3_productivity_growth_forecast_yearly"]
        )
        comparison["weight"] = pd.to_numeric(comparison["employment_persons"], errors="coerce").fillna(0.0)
        comparison_rows = []
        for year, group in comparison.groupby("forecast_year"):
            comparison_rows.append(
                {
                    "forecast_year": year,
                    "v3_weighted_growth": weighted_average(group["v3_productivity_growth_forecast_yearly"], group["weight"]),
                    "v5_weighted_growth": weighted_average(group["productivity_growth_forecast_yearly"], group["weight"]),
                    "v5_minus_v3_weighted_growth": weighted_average(group["v5_minus_v3_productivity_growth"], group["weight"]),
                }
            )
        comparison_by_year = pd.DataFrame(comparison_rows)
        write_csv(comparison_by_year, audit_dir / "productivity_v3_vs_v5_comparison_by_year.csv")
        if not productivity_backtest.empty:
            comparison_rows = comparison_by_year.assign(
                report_section="v3_vs_v5_weighted_forecast",
                component_type="weighted_productivity_growth",
                component_id=comparison_by_year["forecast_year"].astype(str),
                method="champion_minus_v3",
                observations=len(base),
                mae_log_growth=np.nan,
                rmse_log_growth=np.nan,
                mape_log_growth=np.nan,
                chosen_method=V5_PRODUCTIVITY_MODEL,
            )
            suspicious = comparison.loc[
                comparison["productivity_growth_forecast_yearly"].abs().sort_values(ascending=False).head(100).index,
                [
                    "territory_id",
                    "territory_name",
                    "activity_id",
                    "activity_name",
                    "forecast_year",
                    "productivity_growth_forecast_yearly",
                    "forecast_quality_flag",
                ],
            ].copy()
            suspicious["report_section"] = "suspicious_high_abs_productivity_growth"
            suspicious["component_type"] = "region_sector_cell"
            suspicious["component_id"] = suspicious["territory_id"].astype(str) + "|" + suspicious["activity_id"].astype(str) + "|" + suspicious["forecast_year"].astype(str)
            suspicious["method"] = "champion"
            suspicious["observations"] = np.nan
            suspicious["mae_log_growth"] = np.nan
            suspicious["rmse_log_growth"] = np.nan
            suspicious["mape_log_growth"] = np.nan
            suspicious["chosen_method"] = suspicious["forecast_quality_flag"]
            for frame in (comparison_rows, suspicious):
                for col in productivity_backtest.columns:
                    if col not in frame.columns:
                        frame[col] = np.nan
            productivity_backtest = pd.concat([productivity_backtest, comparison_rows[productivity_backtest.columns], suspicious[productivity_backtest.columns]], ignore_index=True)
        write_csv(productivity_backtest, audit_dir / "productivity_backtest_report.csv")
        write_csv(productivity_backtest, audit_dir / "productivity_forecast_backtest_report.csv")

        prod_all = champion_prod_yearly.sort_values("forecast_year").drop_duplicates(["territory_id", "activity_id"]).copy()
        prod_yearly_all = champion_prod_yearly.copy()
    else:
        prod_all = legacy_prod_all.copy()
        prod_cols = [c for c in prod_cols if c in prod_all.columns]
        prod_yearly_all = pd.concat(
            [
                build_productivity_trajectory(prod_all[prod_all["productivity_scenario"] == scenario], start_year, end_year)
                for scenario in LEGACY_PRODUCTIVITY_SCENARIOS
            ],
            ignore_index=True,
        )

    prod_cols = [c for c in prod_cols if c in prod_all.columns]
    write_csv(prod_all[prod_cols], out_dir / "productivity_forecast_assumptions_region_sector.csv")
    prod_yearly_cols = prod_cols + [
        "forecast_year",
        "productivity_growth_forecast_static",
        "productivity_growth_forecast_yearly",
        "productivity_growth_forecast_pct",
        "sector_productivity_growth_forecast_median",
        "productivity_trajectory_convergence_weight",
        "productivity_trajectory_rule",
        "productivity_forecast_model",
        "training_source_coverage_flag",
        "forecast_quality_flag",
        "productivity_forecast_is_clipped",
    ]
    prod_yearly_cols = [c for c in prod_yearly_cols if c in prod_yearly_all.columns]
    write_csv(prod_yearly_all[prod_yearly_cols], out_dir / "productivity_forecast_assumptions_region_sector_year.csv")

    coverage = build_productivity_coverage_report(base)
    write_csv(coverage, audit_dir / "productivity_coverage_report.csv")

    ratios_all = pd.concat([employment_ratios(base, resources, definition) for definition in WORKING_AGE_DEFINITIONS], ignore_index=True)
    write_csv(ratios_all, audit_dir / "employment_workage_ratio_2024.csv")
    ratios = ratios_all[ratios_all["working_age_definition"] == working_age_definition].copy()

    transition_calibration = pd.DataFrame()
    if args.supply_allocation_scenario == "empirical_bounded_transition":
        transition_calibration = calibrate_sector_share_transition(model_panel, base)
        write_csv(transition_calibration, audit_dir / "sector_share_transition_calibration.csv")

    selected_prod_yearly = prod_yearly_all[prod_yearly_all["productivity_scenario"] == args.productivity_scenario].copy()
    econ = economic_labor_demand(selected_prod_yearly, world_growth, start_year, end_year)
    write_csv(econ, out_dir / "economic_labor_demand_forecast_region_sector_year.csv")

    supply = domestic_supply(
        econ,
        base,
        resources,
        ratios,
        working_age_definition,
        args.supply_allocation_scenario,
        start_year,
        end_year,
        unemployment_rates=unemployment_rates,
        unemployment_reserve_policy=args.unemployment_reserve_policy,
        unemployment_mobilization_coef=args.unemployment_mobilization_coef,
        transition_calibration=transition_calibration,
    )
    final = finalize_need(
        econ,
        supply,
        args.population_scenario,
        working_age_definition,
        migrant_retention_rate=args.migrant_retention_rate,
    )
    write_csv(final, out_dir / "foreign_labor_migration_need_region_sector_year.csv")

    share_transition_qa = {}
    if args.supply_allocation_scenario == "empirical_bounded_transition":
        share_sums = final.groupby(["territory_id", "forecast_year"])["supply_allocation_share"].sum()
        cap_violation = pd.to_numeric(final.get("share_transition_cap_violation", pd.Series(0, index=final.index)), errors="coerce").fillna(0.0)
        share_transition_qa = {
            "share_sum_max_abs_error": float((share_sums - 1.0).abs().max()),
            "negative_share_cells": int((final["supply_allocation_share"] < -1e-12).sum()),
            "cap_violation_cells": int((cap_violation > 1e-8).sum()),
            "projection_not_converged_cells": int((final.get("share_transition_projection_converged", pd.Series(True, index=final.index)) == False).sum()),
        }
        top_shifts = final.sort_values("share_transition_abs_change", ascending=False).head(100)
        write_csv(top_shifts, audit_dir / "sector_share_transition_top_100_shifts.csv")
        bounded_alloc = allocation_shares(econ, base, "bounded_transition", start_year, end_year)
        empirical_alloc = final[
            [
                "territory_id",
                "activity_id",
                "forecast_year",
                "supply_allocation_share",
                "empirical_share_change_cap",
            ]
        ].rename(columns={"supply_allocation_share": "empirical_bounded_transition_share"})
        transition_compare = empirical_alloc.merge(
            bounded_alloc[["territory_id", "activity_id", "forecast_year", "supply_allocation_share"]].rename(
                columns={"supply_allocation_share": "v3_bounded_transition_share"}
            ),
            on=["territory_id", "activity_id", "forecast_year"],
            how="left",
        )
        transition_compare["empirical_minus_v3_share"] = (
            transition_compare["empirical_bounded_transition_share"] - transition_compare["v3_bounded_transition_share"]
        )
        write_csv(transition_compare, audit_dir / "bounded_vs_empirical_transition_comparison.csv")
        (audit_dir / "sector_share_transition_qa_summary.json").write_text(
            json.dumps(json_safe(share_transition_qa), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    by_year, by_region, by_sector = summarize_outputs(final)
    write_csv(by_year, out_dir / "summary_by_year.csv")
    write_csv(by_region, out_dir / "summary_by_region.csv")
    write_csv(by_sector, out_dir / "summary_by_sector.csv")
    recommended_detail, recommended_region, recommended_sector = write_recommended_quota_outputs(final, out_dir)

    if args.skip_sensitivity or args.productivity_scenario == CHAMPION_PRODUCTIVITY_SCENARIO:
        sensitivity = pd.DataFrame(
            columns=[
                "population_scenario",
                "working_age_definition",
                "productivity_scenario",
                "supply_allocation_scenario",
                "unemployment_reserve_policy",
                "forecast_year",
                "foreign_labor_stock_need_persons",
                "annual_foreign_labor_quota_persons",
                "foreign_labor_migration_need_persons",
            ]
        )
    else:
        sensitivity = scenario_sensitivity(
            base,
            prod_all,
            world_growth,
            resources,
            args.population_scenario,
            start_year,
            end_year,
            unemployment_rates=unemployment_rates,
            unemployment_reserve_policy=args.unemployment_reserve_policy,
            unemployment_mobilization_coef=args.unemployment_mobilization_coef,
            migrant_retention_rate=args.migrant_retention_rate,
        )
    write_csv(sensitivity, audit_dir / "scenario_sensitivity_summary.csv")

    limitations = build_limitations()
    write_csv(limitations, audit_dir / "limitations.csv")
    write_subagent_findings(audit_dir / "subagent_findings.md")

    final_sorted = final.sort_values(["territory_id", "activity_id", "forecast_year"]).copy()
    prev_required = final_sorted.groupby(["territory_id", "activity_id"])["labor_demand_required_persons"].shift(1)
    prev_required = prev_required.fillna(final_sorted["employment_2024_persons"])
    demand_expected = prev_required * (1.0 + final_sorted["target_real_vrp_growth"]) / (
        1.0 + final_sorted["productivity_growth_forecast_yearly"]
    )
    region_year = final.drop_duplicates(["territory_id", "forecast_year"]).copy()
    unemployment_expected = (
        region_year["domestic_employment_capacity_region_persons"]
        * region_year["unemployment_rate_ilo_15plus_pct"]
        / (100.0 - region_year["unemployment_rate_ilo_15plus_pct"])
        * region_year["unemployment_mobilization_coef"]
    )
    cumulative_diff = final_sorted.groupby(["territory_id", "activity_id"])["cumulative_recommended_quota_persons"].diff().fillna(0.0)
    if {2036, 2050}.issubset(set(final["forecast_year"].unique())):
        p36 = final[final["forecast_year"].eq(2036)][["territory_id", "activity_id", "productivity_growth_forecast_yearly"]]
        p50 = final[final["forecast_year"].eq(2050)][["territory_id", "activity_id", "productivity_growth_forecast_yearly"]]
        plateau = p36.merge(p50, on=["territory_id", "activity_id"], suffixes=("_2036", "_2050"))
        productivity_plateau_share = float(
            np.isclose(
                plateau["productivity_growth_forecast_yearly_2036"],
                plateau["productivity_growth_forecast_yearly_2050"],
                rtol=0,
                atol=1e-12,
            ).mean()
        )
    else:
        productivity_plateau_share = np.nan
    share_sums_all = final.groupby(["territory_id", "forecast_year"])["supply_allocation_share"].sum()
    quota_expected = final["annual_new_stock_delta_persons"] + final["annual_replacement_flow_persons"]
    numeric_checks = {
        "negative_population_cells": int((pop_long["population_persons"] < 0).sum()),
        "negative_labor_demand_cells": int((final["labor_demand_required_persons"] < 0).sum()),
        "negative_migration_need_cells": int((final["foreign_labor_stock_need_persons"] < 0).sum()),
        "need_formula_max_abs_error": float(
            (
                final["foreign_labor_stock_need_persons"]
                - final["gross_labor_deficit_persons"].clip(lower=0)
            )
            .abs()
            .max()
        ),
        "annual_quota_negative_cells": int((final["annual_foreign_labor_quota_persons"] < 0).sum()),
        "recommended_quota_negative_cells": int((final["recommended_annual_quota_persons"] < 0).sum()),
        "stock_need_negative_cells": int((final["foreign_labor_stock_need_persons"] < 0).sum()),
        "cumulative_recommended_quota_decrease_cells": int((cumulative_diff < -1e-8).sum()),
        "quota_formula_max_abs_error": float((final["recommended_annual_quota_persons"] - quota_expected).abs().max()),
        "unemployment_formula_max_abs_error": float((region_year["unemployment_reserve_region_persons"] - unemployment_expected).abs().max()),
        "demand_formula_max_abs_error": float((final_sorted["labor_demand_required_persons"] - demand_expected).abs().max()),
        "share_sum_max_abs_error": float((share_sums_all - 1.0).abs().max()),
        "negative_supply_share_cells": int((final["supply_allocation_share"] < -1e-12).sum()),
        "productivity_equal_2036_2050_share": productivity_plateau_share,
        "control_years_missing": [int(y) for y in CONTROL_YEARS if y < start_year or y > end_year or y not in set(final["forecast_year"].unique())],
        "unemployment_reserve_total_horizon_persons": float(final["unemployment_reserve_sector_allocated_persons"].sum()),
        "duplicate_final_keys": int(
            final.duplicated(
                [
                    "territory_id",
                    "activity_id",
                    "forecast_year",
                    "population_scenario",
                    "working_age_definition",
                    "productivity_scenario",
                    "supply_allocation_scenario",
                ]
            ).sum()
        ),
    }
    numeric_checks.update({f"share_transition_{k}": v for k, v in share_transition_qa.items()})

    quality_summary = {
        "model_version": "foreign_labor_quota_v5_oecd_champion_mean_reverting_productivity_empirical_transition"
        if args.productivity_scenario == CHAMPION_PRODUCTIVITY_SCENARIO
        else "reproducible_balance_model_v3_compatible",
        "control_years": [y for y in CONTROL_YEARS if start_year <= y <= end_year],
        "recommended_annual_quota_persons_final_year": float(
            final[final["forecast_year"].eq(end_year)]["recommended_annual_quota_persons"].sum()
        ),
        "foreign_labor_stock_need_persons_final_year": float(
            final[final["forecast_year"].eq(end_year)]["foreign_labor_stock_need_persons"].sum()
        ),
        "cumulative_recommended_quota_persons_final_year": float(
            final[final["forecast_year"].eq(end_year)]["cumulative_recommended_quota_persons"].sum()
        ),
        "productivity": productivity_qa,
        "share_transition": share_transition_qa,
        "numeric_checks": numeric_checks,
    }
    (audit_dir / "model_quality_summary.json").write_text(
        json.dumps(json_safe(quality_summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = {
        "status": "complete",
        "model_version": quality_summary["model_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(final)),
        "base_model_cells_2024_included": int(len(base)),
        "base_model_cells_2024_excluded": int(len(excluded)),
        "population_scenario": args.population_scenario,
        "working_age_definition": working_age_definition,
        "productivity_scenario": args.productivity_scenario,
        "supply_allocation_scenario": args.supply_allocation_scenario,
        "start_year": start_year,
        "end_year": end_year,
        "total_foreign_labor_stock_need_horizon_sum_persons": float(final["foreign_labor_stock_need_persons"].sum()),
        "total_annual_foreign_labor_quota_horizon_persons": float(final["annual_foreign_labor_quota_persons"].sum()),
        "total_recommended_annual_quota_horizon_persons": float(final["recommended_annual_quota_persons"].sum()),
        "final_year_foreign_labor_stock_need_persons": float(
            final[final["forecast_year"].eq(end_year)]["foreign_labor_stock_need_persons"].sum()
        ),
        "final_year_recommended_annual_quota_persons": float(
            final[final["forecast_year"].eq(end_year)]["recommended_annual_quota_persons"].sum()
        ),
        "final_year_cumulative_recommended_quota_persons": float(
            final[final["forecast_year"].eq(end_year)]["cumulative_recommended_quota_persons"].sum()
        ),
        "unemployment_reserve_total_horizon_persons": float(final["unemployment_reserve_sector_allocated_persons"].sum()),
        "total_foreign_labor_need_persons": float(final["foreign_labor_stock_need_persons"].sum()),
        "final_path": str(out_dir / "foreign_labor_migration_need_region_sector_year.csv"),
        "population_long_path": str(population_long_path),
        "population_qa": population_qa,
        "world_growth_qa": world_qa,
        "unemployment_qa": unemployment_qa,
        "unemployment_reserve_policy": args.unemployment_reserve_policy,
        "unemployment_mobilization_coef": args.unemployment_mobilization_coef,
        "migrant_retention_rate": args.migrant_retention_rate,
        "territory_crosswalk": {
            "rows": int(len(crosswalk)),
            "unmatched_economic_territories": int(len(unmatched_econ)),
            "population_only_territories": int(len(unmatched_pop)),
        },
        "numeric_checks": numeric_checks,
        "input_files": {
            "economic_panel": {
                "path": str(Path(args.economic_panel)),
                "sha256": sha256_file(Path(args.economic_panel)),
            },
            "world_growth": {
                "path": str(Path(args.world_growth)),
                "sha256": sha256_file(Path(args.world_growth)),
            },
            "population_files": population_qa["population_files"],
            "unemployment_rate": {
                "path": str(Path(args.unemployment_rate)) if args.unemployment_rate else "",
                "sha256": sha256_file(Path(args.unemployment_rate)) if args.unemployment_rate and Path(args.unemployment_rate).exists() else "",
            },
        },
    }
    (out_dir / "qa_model_summary.json").write_text(json.dumps(json_safe(result), ensure_ascii=False, indent=2), encoding="utf-8")

    run_config = {
        "command": " ".join(sys.argv),
        "assumptions": {
            "base_demography": "noMIG is the base because withMIG already includes migration.",
            "main_publication_scenario": f"{args.population_scenario} x {working_age_definition} x {args.productivity_scenario} x {args.supply_allocation_scenario}",
            "foreign_labor_need_interpretation": "foreign_labor_stock_need_persons is stock; recommended_annual_quota_persons is the administrative yearly quota/flow. Never sum stock-year values as unique migrants.",
            "unemployment_reserve": "ILO unemployment-rate reserve is computed as unemployed = employed * u_pct / (100 - u_pct) and allocated by the selected policy.",
        },
        "result": result,
    }
    (out_dir / "run_config.json").write_text(json.dumps(json_safe(run_config), ensure_ascii=False, indent=2), encoding="utf-8")

    workbook_tables = {
        "summary_by_year": by_year,
        "summary_by_region_top": by_region.head(100),
        "summary_by_sector": by_sector,
        "recommended_quota": recommended_detail,
        "recommended_by_region": recommended_region.head(10000),
        "recommended_by_sector": recommended_sector,
        "productivity_coverage": coverage,
        "productivity_quality": pd.DataFrame([productivity_qa]),
        "share_transition_qa": pd.DataFrame([share_transition_qa]) if share_transition_qa else pd.DataFrame(),
        "employment_workage_ratio": ratios_all,
        "unemployment_reserve_sample": final[[c for c in ["territory_name", "forecast_year", "unemployment_rate_ilo_15plus_pct", "unemployment_reserve_region_persons"] if c in final.columns]].drop_duplicates().head(10000),
        "excluded_base_cells": excluded,
        "unmatched_population": unmatched_pop,
        "scenario_sensitivity": sensitivity,
        "limitations": limitations,
    }
    write_validation_workbook(audit_dir / "model_validation_tables.xlsx", workbook_tables)
    write_report(audit_dir / "model_validation_report.md", result, by_year, by_region, by_sector, sensitivity, limitations)
    write_v4_final_report(audit_dir / "final_report_ru.md", result, by_year, recommended_region, recommended_sector, quality_summary)

    return result


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Forecast labor demand and residual foreign labor migration need.")
    ap.add_argument("--economic-panel", default="data/processed/emiss_vrp_employment_productivity_panel_joined.csv")
    ap.add_argument("--world-growth", default="data/forecasts_preliminary/world_growth_target_oecd_ltm_2025_2050.csv")
    ap.add_argument("--population-dir", default="data/population_repo_PLACEHOLDER")
    ap.add_argument("--population-long-cache", default="outputs/model_run/population_long_noMIG.csv")
    ap.add_argument("--unemployment-rate", default=DEFAULT_UNEMPLOYMENT_RATE_PATH)
    ap.add_argument("--out-dir", default="outputs/model_run")
    ap.add_argument("--audit-dir", default="outputs/codex_audit")
    ap.add_argument("--base-year", type=int, default=2024)
    ap.add_argument("--start-year", type=int, default=2025)
    ap.add_argument("--end-year", type=int, default=2050)
    ap.add_argument("--work-age-min", type=int, default=15)
    ap.add_argument("--work-age-max", type=int, default=72)
    ap.add_argument("--population-scenario", choices=["noMIG", "withMIG"], default="noMIG")
    ap.add_argument("--productivity-scenario", choices=list(PRODUCTIVITY_SCENARIOS), default=CHAMPION_PRODUCTIVITY_SCENARIO)
    ap.add_argument("--supply-allocation-scenario", choices=list(SUPPLY_ALLOCATION_SCENARIOS), default="empirical_bounded_transition")
    ap.add_argument("--unemployment-reserve-policy", choices=list(UNEMPLOYMENT_RESERVE_POLICIES), default="equal_sector_split")
    ap.add_argument("--unemployment-mobilization-coef", type=float, default=1.0)
    ap.add_argument("--migrant-retention-rate", type=float, default=1.0)
    ap.add_argument("--skip-sensitivity", action="store_true")
    return ap.parse_args()


if __name__ == "__main__":
    print(json.dumps(json_safe(run_model(parse_args())), ensure_ascii=False, indent=2))
