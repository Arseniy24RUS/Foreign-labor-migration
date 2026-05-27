# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import run_full_model as model  # noqa: E402

PANEL = ROOT / "data/processed/emiss_vrp_employment_productivity_panel_joined.csv"
WORLD = ROOT / "data/forecasts_preliminary/world_growth_target_oecd_ltm_2025_2050.csv"
POP_DIR = ROOT / "data/population_repo_PLACEHOLDER"
UNEMP = ROOT / "data/processed/unemployment_rate_ilo_15plus_2017_2025_matched.csv"
POP_CACHE = ROOT / "outputs/model_run/population_long_noMIG.csv"
V4_OUT = ROOT / "outputs/model_run_v5"
V4_AUDIT = ROOT / "outputs/codex_audit_v5"
CONTROL_YEARS = {2030, 2036, 2050}


def test_core_files_exist():
    assert PANEL.exists(), "Economic panel is missing"
    assert WORLD.exists(), "World growth scenario is missing"
    assert (POP_DIR / "POP_wide_male_noMIG.xlsx").exists(), "Male noMIG population file is missing"
    assert (POP_DIR / "POP_wide_female_noMIG.xlsx").exists(), "Female noMIG population file is missing"
    assert UNEMP.exists(), "ILO unemployment-rate table is missing"


def test_panel_model_universe_has_required_shape_and_no_duplicates():
    df = pd.read_csv(PANEL)
    required = {
        "territory_id",
        "territory_name",
        "is_nonoverlap_model_region",
        "activity_id",
        "activity_name",
        "is_model_activity",
        "year",
        "employment_persons",
        "official_productivity_index_hybrid_pct",
    }
    assert required.issubset(df.columns)
    subset = df[
        df["is_nonoverlap_model_region"].astype(str).str.lower().isin(["true", "1"])
        & df["is_model_activity"].astype(str).str.lower().isin(["true", "1"])
    ]
    assert subset["territory_id"].nunique() == 85
    assert subset["activity_id"].nunique() == 20
    assert subset["year"].min() == 2017
    assert subset["year"].max() == 2024
    assert not subset.duplicated(["territory_id", "activity_id", "year"]).any()


def test_world_growth_percent_conversion():
    wg, qa = model.read_world_growth(WORLD, 2025, 2050)
    assert qa["unit_rule"] == "pct_column_divided_by_100"
    assert qa["is_oecd_ltm"] is True
    assert qa["scenario"] == "BAU1"
    assert "OECD" in qa["source"]
    assert qa["flat_imf_32_after_2027"] is False
    values = dict(zip(wg["forecast_year"], wg["target_real_vrp_growth"]))
    assert set(values) == set(range(2025, 2051))
    assert values[2030] != pytest.approx(0.032)


def test_population_parser_reads_by_age_format_without_negative_values():
    pop, qa = model.read_population_scenario_cached(POP_DIR, "noMIG", POP_CACHE if POP_CACHE.exists() else None)
    assert qa["territories"] == 95
    assert qa["years"] == [2022, 2100]
    assert qa["ages"] == [0, 100]
    assert qa["negative_cells"] == 0
    assert (pop["population_persons"] >= 0).all()
    assert {"territory_name_population", "territory_norm", "sex", "age", "year", "population_persons"}.issubset(pop.columns)

def test_unemployment_table_matches_all_model_regions_and_formula():
    rates, qa = model.read_unemployment_rates(UNEMP, 2025, 2036)
    assert qa["status"] == "loaded"
    assert qa["official_years"] == [2017, 2025]
    assert rates["forecast_year"].min() == 2025
    assert rates["forecast_year"].max() == 2036
    latest = rates[rates["forecast_year"].eq(2025)]
    assert latest["territory_id"].nunique() >= 85
    rf = pd.read_csv(UNEMP)
    rf_2025 = rf[(rf["territory_name"].eq("Российская Федерация")) & (rf["year"].eq(2025))]["unemployment_rate_ilo_15plus_pct"].iloc[0]
    assert rf_2025 == pytest.approx(2.2)
    employed = 1000.0
    u = 2.2
    unemployed = employed * u / (100.0 - u)
    assert unemployed == pytest.approx(22.4948875)


def test_productivity_index_104_6_becomes_0_046():
    base = pd.DataFrame(
        {
            "territory_id": ["T1"],
            "territory_name": ["Регион"],
            "activity_id": ["A"],
            "activity_name": ["Отрасль"],
            "employment_persons": [100.0],
            "official_productivity_index_hybrid_pct": [104.6],
            "official_prod_index_hybrid_pct": [104.6],
            "official_productivity_growth_from_index": [0.046],
            "official_productivity_growth_for_model": [0.046],
            "historical_productivity_cagr_2017_2022": [np.nan],
            "sector_productivity_cagr_median": [np.nan],
            "region_productivity_cagr_median": [np.nan],
            "global_productivity_cagr_median": [0.0],
        }
    )
    out = model.productivity_forecast(base, "baseline")
    assert out.loc[0, "official_productivity_growth_from_index"] == pytest.approx(0.046)
    assert out.loc[0, "productivity_growth_forecast"] > 0


@pytest.fixture(scope="session")
def model_run_dir(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("model_run")
    audit_dir = tmp_path_factory.mktemp("codex_audit")
    args = argparse.Namespace(
        economic_panel=str(PANEL),
        world_growth=str(WORLD),
        population_dir=str(POP_DIR),
        population_long_cache=str(POP_CACHE),
        unemployment_rate=str(UNEMP),
        out_dir=str(out_dir),
        audit_dir=str(audit_dir),
        base_year=2024,
        start_year=2025,
        end_year=2027,
        work_age_min=15,
        work_age_max=72,
        population_scenario="noMIG",
        productivity_scenario="baseline",
        supply_allocation_scenario="bounded_transition",
        unemployment_reserve_policy="equal_sector_split",
        unemployment_mobilization_coef=1.0,
        migrant_retention_rate=1.0,
        skip_sensitivity=True,
    )
    model.run_model(args)
    return out_dir


def test_model_outputs_nonnegative_and_formula_consistent(model_run_dir):
    final = pd.read_csv(model_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    for col in [
        "employment_2024_persons",
        "labor_demand_required_persons",
        "working_age_population_persons",
        "domestic_sector_supply_allocated_persons",
        "foreign_labor_stock_need_persons",
        "annual_foreign_labor_quota_persons",
    ]:
        assert (pd.to_numeric(final[col], errors="coerce") >= 0).all(), col
    expected = final["gross_labor_deficit_persons"].clip(lower=0)
    assert np.allclose(final["foreign_labor_stock_need_persons"], expected, rtol=0, atol=1e-6)
    assert np.allclose(final["foreign_labor_migration_need_persons"], final["foreign_labor_stock_need_persons"], rtol=0, atol=1e-6)
    assert (final["annual_foreign_labor_quota_persons"] >= 0).all()


def test_unemployment_reserve_formula_and_sector_allocation(model_run_dir):
    final = pd.read_csv(model_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    region_year = final.drop_duplicates(["territory_id", "forecast_year"]).copy()
    expected = (
        region_year["domestic_employment_capacity_region_persons"]
        * region_year["unemployment_rate_ilo_15plus_pct"]
        / (100.0 - region_year["unemployment_rate_ilo_15plus_pct"])
        * region_year["unemployment_mobilization_coef"]
    )
    assert np.allclose(
        region_year["unemployment_reserve_region_persons"],
        expected,
        rtol=0,
        atol=1e-6,
    )

    allocated = final.groupby(["territory_id", "forecast_year"], as_index=False).agg(
        reserve_allocated=("unemployment_reserve_sector_allocated_persons", "sum"),
        reserve_region=("unemployment_reserve_region_persons", "first"),
    )
    assert np.allclose(allocated["reserve_allocated"], allocated["reserve_region"], rtol=0, atol=1e-6)
    assert set(final["unemployment_reserve_policy"].dropna().unique()) == {"equal_sector_split"}


def test_stock_flow_separation_and_quota_formula(model_run_dir):
    final = pd.read_csv(model_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    gross_before = final["labor_demand_required_persons"] - final["domestic_sector_supply_allocated_persons"]
    gross_after = (
        final["labor_demand_required_persons"]
        - final["domestic_sector_supply_total_with_unemployment_reserve_persons"]
    )
    assert np.allclose(final["gross_labor_deficit_before_unemployment_reserve_persons"], gross_before, atol=1e-6)
    assert np.allclose(final["gross_labor_deficit_persons"], gross_after, atol=1e-6)
    assert np.allclose(final["foreign_labor_stock_need_persons"], gross_after.clip(lower=0), atol=1e-6)
    assert np.allclose(
        final["foreign_labor_migration_need_persons"],
        final["foreign_labor_stock_need_persons"],
        atol=1e-6,
    )
    expected_new_flow = (
        final["foreign_labor_stock_need_persons"] - final["previous_foreign_labor_stock_need_persons"]
    ).clip(lower=0)
    expected_replacement = final["previous_foreign_labor_stock_need_persons"] * (
        1.0 - final["migrant_retention_rate"]
    )
    assert np.allclose(final["annual_new_foreign_labor_stock_delta_persons"], expected_new_flow, atol=1e-6)
    assert np.allclose(final["annual_replacement_foreign_labor_flow_persons"], expected_replacement, atol=1e-6)
    assert np.allclose(
        final["annual_foreign_labor_quota_persons"],
        expected_new_flow + expected_replacement,
        atol=1e-6,
    )


def test_productivity_trajectory_and_supply_shares_are_complete(model_run_dir):
    final = pd.read_csv(model_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    productivity = pd.read_csv(model_run_dir / "productivity_forecast_assumptions_region_sector_year.csv")
    required_keys = ["territory_id", "activity_id", "forecast_year"]
    final_keys = final[required_keys].drop_duplicates()
    prod_keys = productivity[required_keys + ["productivity_growth_forecast_yearly"]].drop_duplicates(required_keys)
    merged = final_keys.merge(prod_keys, on=required_keys, how="left")
    assert not merged["productivity_growth_forecast_yearly"].isna().any()

    shares = final.groupby(["territory_id", "forecast_year"], as_index=False)["supply_allocation_share"].sum()
    assert np.allclose(shares["supply_allocation_share"], 1.0, atol=1e-6)
    assert set(final["supply_allocation_scenario"].dropna().unique()) == {"bounded_transition"}


def test_model_outputs_have_no_duplicate_scenario_keys(model_run_dir):
    final = pd.read_csv(model_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    keys = [
        "territory_id",
        "activity_id",
        "forecast_year",
        "population_scenario",
        "working_age_definition",
        "productivity_scenario",
        "supply_allocation_scenario",
    ]
    assert not final.duplicated(keys).any()


def test_summaries_reconcile_with_detail(model_run_dir):
    final = pd.read_csv(model_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    by_year = pd.read_csv(model_run_dir / "summary_by_year.csv")
    detail_year = (
        final.groupby(["population_scenario", "working_age_definition", "productivity_scenario", "supply_allocation_scenario", "forecast_year"], as_index=False)[
            "foreign_labor_migration_need_persons"
        ]
        .sum()
        .sort_values("forecast_year")
        .reset_index(drop=True)
    )
    summary_year = by_year[detail_year.columns].sort_values("forecast_year").reset_index(drop=True)
    assert np.allclose(detail_year["foreign_labor_migration_need_persons"], summary_year["foreign_labor_migration_need_persons"], atol=1e-6)

    by_region = pd.read_csv(model_run_dir / "summary_by_region.csv")
    by_sector = pd.read_csv(model_run_dir / "summary_by_sector.csv")
    assert final["foreign_labor_migration_need_persons"].sum() == pytest.approx(by_region["foreign_labor_migration_need_persons"].sum())
    assert final["foreign_labor_migration_need_persons"].sum() == pytest.approx(by_sector["foreign_labor_migration_need_persons"].sum())


def test_base_employment_reconciles_to_panel_for_included_cells(model_run_dir):
    final = pd.read_csv(model_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    base_from_output = final[final["forecast_year"].eq(final["forecast_year"].min())][
        ["territory_id", "activity_id", "employment_2024_persons"]
    ].drop_duplicates()
    panel = pd.read_csv(PANEL)
    panel_base = panel[
        panel["is_nonoverlap_model_region"].astype(str).str.lower().isin(["true", "1"])
        & panel["is_model_activity"].astype(str).str.lower().isin(["true", "1"])
        & panel["year"].eq(2024)
        & (pd.to_numeric(panel["employment_persons"], errors="coerce") > 0)
    ][["territory_id", "activity_id", "employment_persons"]]
    merged = base_from_output.merge(panel_base, on=["territory_id", "activity_id"], how="inner")
    assert len(merged) == len(base_from_output)
    assert np.allclose(merged["employment_2024_persons"], merged["employment_persons"], atol=1e-9)


@pytest.fixture(scope="session")
def v4_run_dir():
    if not (V4_OUT / "foreign_labor_migration_need_region_sector_year.csv").exists():
        args = argparse.Namespace(
            economic_panel=str(PANEL),
            world_growth=str(WORLD),
            population_dir=str(POP_DIR),
            population_long_cache=str(POP_CACHE),
            unemployment_rate=str(UNEMP),
            out_dir=str(V4_OUT),
            audit_dir=str(V4_AUDIT),
            base_year=2024,
            start_year=2025,
            end_year=2050,
            work_age_min=15,
            work_age_max=72,
            population_scenario="noMIG",
            productivity_scenario="champion",
            supply_allocation_scenario="empirical_bounded_transition",
            unemployment_reserve_policy="equal_sector_split",
            unemployment_mobilization_coef=1.0,
            migrant_retention_rate=1.0,
            skip_sensitivity=True,
        )
        model.run_model(args)
    return V4_OUT


def test_v4_keys_years_and_control_years(v4_run_dir):
    final = pd.read_csv(v4_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    assert not final.duplicated(["territory_id", "activity_id", "forecast_year"]).any()
    assert set(final["forecast_year"].unique()) == set(range(2025, 2051))
    assert CONTROL_YEARS.issubset(set(final["forecast_year"].unique()))
    for name in [
        "summary_by_year.csv",
        "recommended_quota_by_region.csv",
        "recommended_quota_by_sector.csv",
        "recommended_quota_control_years_2030_2036_2050.csv",
    ]:
        df = pd.read_csv(v4_run_dir / name)
        assert CONTROL_YEARS.issubset(set(pd.to_numeric(df["forecast_year"], errors="coerce").dropna().astype(int))), name


def test_v4_quota_stock_and_cumulative_formulas(v4_run_dir):
    final = pd.read_csv(v4_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    assert (final["recommended_annual_quota_persons"] >= 0).all()
    assert (final["foreign_labor_stock_need_persons"] >= 0).all()
    final = final.sort_values(["territory_id", "activity_id", "forecast_year"]).copy()
    assert (final.groupby(["territory_id", "activity_id"])["cumulative_recommended_quota_persons"].diff().fillna(0) >= -1e-8).all()
    expected_quota = final["annual_new_stock_delta_persons"] + final["annual_replacement_flow_persons"]
    assert np.allclose(final["recommended_annual_quota_persons"], expected_quota, atol=1e-6)
    assert np.allclose(final["recommended_annual_quota_persons"], final["annual_foreign_labor_quota_persons"], atol=1e-6)
    assert np.allclose(final["cumulative_recommended_quota_persons"], final["cumulative_foreign_labor_quota_persons"], atol=1e-6)


def test_v4_empirical_transition_constraints(v4_run_dir):
    final = pd.read_csv(v4_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    shares = final.groupby(["territory_id", "forecast_year"], as_index=False)["supply_allocation_share"].sum()
    assert np.allclose(shares["supply_allocation_share"], 1.0, atol=1e-8)
    assert (final["supply_allocation_share"] >= -1e-12).all()
    violation = pd.to_numeric(final["share_transition_cap_violation"], errors="coerce").fillna(0.0)
    assert (violation <= 1e-8).all()
    assert (V4_AUDIT / "sector_share_transition_calibration.csv").exists()


def test_v4_productivity_has_no_artificial_2036_plateau(v4_run_dir):
    final = pd.read_csv(v4_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    p36 = final[final["forecast_year"].eq(2036)][["territory_id", "activity_id", "productivity_growth_forecast_yearly"]]
    p50 = final[final["forecast_year"].eq(2050)][["territory_id", "activity_id", "productivity_growth_forecast_yearly"]]
    merged = p36.merge(p50, on=["territory_id", "activity_id"], suffixes=("_2036", "_2050"))
    identical_share = np.isclose(
        merged["productivity_growth_forecast_yearly_2036"],
        merged["productivity_growth_forecast_yearly_2050"],
        rtol=0,
        atol=1e-12,
    ).mean()
    assert identical_share < 0.95
    assert set(final["productivity_forecast_model"].dropna().unique()) == {"hierarchical_mean_reverting_factor_productivity_forecast"}
    assert (v4_run_dir / "productivity_forecast_region_sector_year.csv").exists()
    assert (V4_AUDIT / "productivity_backtest_report.csv").exists()
    assert (V4_AUDIT / "productivity_forecast_backtest_report.csv").exists()


def test_v5_productivity_clipping_qa_passes(v4_run_dir):
    qa = pd.read_csv(V4_AUDIT / "productivity_clipping_qa.csv")
    assert set([2030, 2036, 2050]).issubset(set(pd.to_numeric(qa["forecast_year"], errors="coerce").dropna().astype(int)))
    assert (pd.to_numeric(qa["clipped_share"], errors="coerce").fillna(0.0) <= 0.20).all()
    focus = qa[qa["okved_section"].isin(["B", "I"])]
    assert not focus.empty
    assert (pd.to_numeric(focus["clipped_share"], errors="coerce").fillna(0.0) <= 0.20).all()


def test_v4_unemployment_demand_and_stock_formulas(v4_run_dir):
    final = pd.read_csv(v4_run_dir / "foreign_labor_migration_need_region_sector_year.csv")
    region_year = final.drop_duplicates(["territory_id", "forecast_year"]).copy()
    expected_unemployment = (
        region_year["domestic_employment_capacity_region_persons"]
        * region_year["unemployment_rate_ilo_15plus_pct"]
        / (100.0 - region_year["unemployment_rate_ilo_15plus_pct"])
        * region_year["unemployment_mobilization_coef"]
    )
    assert np.allclose(region_year["unemployment_reserve_region_persons"], expected_unemployment, atol=1e-6)

    final = final.sort_values(["territory_id", "activity_id", "forecast_year"]).copy()
    prev_required = final.groupby(["territory_id", "activity_id"])["labor_demand_required_persons"].shift(1)
    prev_required = prev_required.fillna(final["employment_2024_persons"])
    expected_demand = prev_required * (1 + final["target_real_vrp_growth"]) / (1 + final["productivity_growth_forecast_yearly"])
    assert np.allclose(final["labor_demand_required_persons"], expected_demand, atol=1e-6)

    gross_after = final["labor_demand_required_persons"] - final["domestic_sector_supply_total_with_unemployment_reserve_persons"]
    assert np.allclose(final["foreign_labor_stock_need_persons"], gross_after.clip(lower=0), atol=1e-6)


def test_dashboard_summaries_expose_explicit_quota_stock_metrics(v4_run_dir):
    dashboard_dir = ROOT / "docs/data"
    forecast = pd.read_csv(dashboard_dir / "region_sector_forecast.csv")
    required = {
        "recommended_annual_quota_persons",
        "foreign_labor_stock_need_persons",
        "cumulative_recommended_quota_persons",
        "dashboard_value_persons",
    }
    assert required.issubset(forecast.columns)
    assert np.allclose(forecast["dashboard_value_persons"], forecast["recommended_annual_quota_persons"], atol=1e-6)
    for name in ["summary_by_year.json", "summary_by_region_top.json", "summary_by_sector.json"]:
        data = json.loads((dashboard_dir / name).read_text(encoding="utf-8"))
        assert data, name
        assert {"recommended_annual_quota_persons", "foreign_labor_stock_need_persons", "cumulative_recommended_quota_persons", "value_persons"}.issubset(data[0])
    metadata = json.loads((dashboard_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "OECD" in metadata["world_growth_source"]
    assert metadata["world_growth_scenario"] == "BAU1"
