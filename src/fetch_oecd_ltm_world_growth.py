#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch OECD Economic Outlook long-term world GDP growth target for v5.

The model consumes annual growth rates, while OECD LTM publishes annual levels.
This script downloads the world potential real GDP volume level and converts it
to year-over-year growth for 2025-2050.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


OECD_SOURCE = "OECD Economic Outlook 117 long-term scenarios / OECD Long-Term Model"
OECD_SOURCE_URL = "https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,DSD_EO_LTB@DF_EO_LTB/W..{scenario}.A"
OECD_INFO_URL = "https://www.oecd.org/en/topics/sub-issues/economic-outlook/long-run-economic-scenarios-2025-update.html"


def build_url(scenario: str, start_year: int, end_year: int) -> str:
    base = OECD_SOURCE_URL.format(scenario=scenario)
    params = {
        "startPeriod": start_year - 1,
        "endPeriod": end_year,
        "dimensionAtObservation": "AllDimensions",
        "format": "csvfilewithlabels",
    }
    return f"{base}?{urlencode(params)}"


def first_existing(columns: list[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    lower = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    return None


def read_oecd_levels(url: str, scenario: str, start_year: int, end_year: int) -> pd.DataFrame:
    try:
        request = Request(
            url,
            headers={
                "User-Agent": "ForeignLaborMigrationModel/5.0 (+https://mgimo.ru/)",
                "Accept": "text/csv, */*",
            },
        )
        with urlopen(request, timeout=60) as response:
            payload = response.read()
        raw = pd.read_csv(io.BytesIO(payload))
    except Exception as exc:  # pragma: no cover - exact urllib/pandas errors vary
        raise RuntimeError(
            "OECD LTM API is unavailable or returned an unreadable CSV. "
            f"URL: {url}. Original error: {exc}"
        ) from exc

    if raw.empty:
        raise RuntimeError(f"OECD LTM API returned an empty table. URL: {url}")

    time_col = first_existing(raw.columns.tolist(), ["TIME_PERIOD", "Time period", "year"])
    value_col = first_existing(raw.columns.tolist(), ["OBS_VALUE", "Observation value", "value"])
    ref_col = first_existing(raw.columns.tolist(), ["REF_AREA", "Reference area"])
    measure_col = first_existing(raw.columns.tolist(), ["MEASURE", "Measure"])
    scenario_col = first_existing(raw.columns.tolist(), ["SCENARIO", "Scenario"])
    freq_col = first_existing(raw.columns.tolist(), ["FREQ", "Frequency of observation"])
    missing = [
        name
        for name, col in {
            "time": time_col,
            "value": value_col,
            "ref_area": ref_col,
            "measure": measure_col,
            "scenario": scenario_col,
            "freq": freq_col,
        }.items()
        if col is None
    ]
    if missing:
        raise RuntimeError(
            "OECD LTM CSV schema changed: missing required columns "
            f"{missing}. Available columns: {list(raw.columns)}"
        )

    df = raw.copy()
    df["_year"] = pd.to_numeric(df[time_col], errors="coerce").astype("Int64")
    df["_level"] = pd.to_numeric(df[value_col], errors="coerce")
    mask = (
        df[ref_col].astype(str).eq("W")
        & df[measure_col].astype(str).eq("GDPVTRD")
        & df[scenario_col].astype(str).eq(scenario)
        & df[freq_col].astype(str).eq("A")
        & df["_year"].between(start_year - 1, end_year)
    )
    levels = (
        df.loc[mask, ["_year", "_level"]]
        .dropna()
        .rename(columns={"_year": "year", "_level": "gdpvtrd_level"})
        .sort_values("year")
        .drop_duplicates("year", keep="last")
    )
    levels["year"] = levels["year"].astype(int)

    required_years = set(range(start_year - 1, end_year + 1))
    missing_years = sorted(required_years - set(levels["year"]))
    if missing_years:
        raise RuntimeError(
            "OECD LTM data are incomplete for the requested horizon. "
            f"Missing years: {missing_years}. URL: {url}"
        )
    if not np.isfinite(levels["gdpvtrd_level"]).all() or (levels["gdpvtrd_level"] <= 0).any():
        raise RuntimeError("OECD LTM GDPVTRD levels contain non-positive or non-finite values.")
    return levels


def make_growth_table(levels: pd.DataFrame, scenario: str, start_year: int, end_year: int, url: str) -> pd.DataFrame:
    out = levels.copy()
    out["world_real_gdp_growth_target"] = out["gdpvtrd_level"].pct_change()
    out = out[out["year"].between(start_year, end_year)].copy()
    out["world_real_gdp_growth_target_pct"] = out["world_real_gdp_growth_target"] * 100.0

    post_2027 = out[out["year"] > 2027]["world_real_gdp_growth_target"]
    if len(post_2027) and np.allclose(post_2027.to_numpy(dtype=float), 0.032, rtol=0, atol=1e-6):
        raise RuntimeError(
            "OECD LTM validation failed: post-2027 growth is indistinguishable from a flat IMF 3.2% extension."
        )

    out["source"] = OECD_SOURCE
    out["source_url"] = url
    out["scenario"] = scenario
    out["note"] = (
        "Computed from OECD EO117 LTM W.GDPVTRD."
        f"{scenario}.A annual level; growth = level_t / level_(t-1) - 1. "
        "Downloaded via the W..SCENARIO.A data key and filtered to MEASURE=GDPVTRD because "
        "the narrow OECD SDMX key may omit early observations. "
        f"Reference page: {OECD_INFO_URL}"
    )
    return out[
        [
            "year",
            "world_real_gdp_growth_target_pct",
            "world_real_gdp_growth_target",
            "source",
            "source_url",
            "scenario",
            "note",
        ]
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch OECD LTM world real GDP growth target for 2025-2050.")
    parser.add_argument("--scenario", default="BAU1")
    parser.add_argument("--start-year", type=int, default=2025)
    parser.add_argument("--end-year", type=int, default=2050)
    parser.add_argument("--out", default="data/forecasts_preliminary/world_growth_target_oecd_ltm_2025_2050.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_year < 2025 or args.end_year > 2050 or args.start_year > args.end_year:
        raise SystemExit("Expected horizon inside 2025-2050 with start-year <= end-year.")
    url = build_url(args.scenario, args.start_year, args.end_year)
    levels = read_oecd_levels(url, args.scenario, args.start_year, args.end_year)
    growth = make_growth_table(levels, args.scenario, args.start_year, args.end_year, url)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    growth.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(growth)} OECD LTM growth rows to {out_path}")


if __name__ == "__main__":
    main()
