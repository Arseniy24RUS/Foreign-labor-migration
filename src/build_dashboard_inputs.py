#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create compact JSON/CSV inputs for the static GitHub Pages dashboard."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
from pathlib import Path

import pandas as pd


FINAL_VALUE_COL = "recommended_annual_quota_persons"
FALLBACK_VALUE_CANDIDATES = [
    "annual_foreign_labor_quota_persons",
    "foreign_labor_stock_need_persons",
    "foreign_labor_migration_need_persons",
    "positive_cumulative_labor_need_persons",
    "positive_annual_labor_need_persons",
    "labor_demand_required_persons",
]


def normalize_name(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip().lower().replace("ё", "е")
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)
    text = re.sub(r"[.,;:'\"`«»()\[\]]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


REGION_GEO_ALIASES = {
    "Город Москва столица Российской Федерации город федерального значения": "Город Москва",
    "Город Санкт-Петербург город федерального значения": "Город Санкт-Петербург",
    "Город федерального значения Севастополь": "Город Севастополь",
    "Ненецкий автономный округ (Архангельская область)": "Ненецкий автономный округ",
    "Архангельская область (кроме Ненецкого автономного округа)": "Архангельская область",
    "Ханты-Мансийский автономный округ - Югра (Тюменская область)": "Ханты-Мансийский автономный округ – Югра",
    "Ямало-Ненецкий автономный округ (Тюменская область)": "Ямало-Ненецкий автономный округ",
    "Тюменская область (кроме Ханты-Мансийского автономного округа-Югры и Ямало-Ненецкого автономного округа)": "Тюменская область",
    "Республика Северная Осетия-Алания": "Республика Северная Осетия – Алания",
}


def choose_input(out_dir: Path, explicit: str | None) -> tuple[Path, str]:
    if explicit:
        return Path(explicit), "explicit"
    final = out_dir / "foreign_labor_migration_need_region_sector_year.csv"
    if final.exists():
        return final, "final_migration_need"
    pending = out_dir / "foreign_labor_migration_need_PENDING_demography.csv"
    if pending.exists():
        return pending, "pending_demography"
    economic = out_dir / "economic_labor_demand_forecast_region_sector_year.csv"
    if economic.exists():
        return economic, "pending_demography"
    raise FileNotFoundError(
        "No model output for dashboard was found. Run src/run_full_model.py first."
    )


def choose_value_column(df: pd.DataFrame, source_status: str) -> tuple[str, str, str, list[str]]:
    warnings: list[str] = []
    if FINAL_VALUE_COL in df.columns:
        return (
            FINAL_VALUE_COL,
            "recommended_annual_migration_quota_flow",
            "Рекомендуемая годовая квота иностранных работников после учета внутреннего ресурса и резерва безработных",
            warnings,
        )
    for candidate in FALLBACK_VALUE_CANDIDATES:
        if candidate in df.columns:
            warnings.append(
                "Экономический спрос рассчитан, демографический блок ожидается; "
                "показатель не является миграционной квотой."
            )
            label = (
                "Экономическая трудовая потребность до демографической балансировки"
                if candidate != "labor_demand_required_persons"
                else "Требуемая занятость по экономическому блоку"
            )
            return candidate, "economic_labor_need_pending_demography", label, warnings
    raise ValueError(
        "Dashboard source must contain a final migration-need metric or an economic fallback metric."
    )


def read_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def scenario_values(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    return sorted(str(v) for v in df[column].dropna().unique().tolist())


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def build_geo_crosswalk(slim: pd.DataFrame, dest: Path) -> dict:
    geo_path = dest / "russia_regions.geojson"
    crosswalk_path = dest / "region_geo_crosswalk.json"
    unmatched_path = dest / "map_unmatched_regions.json"
    source_path = dest / "geojson_source.txt"
    if not geo_path.exists():
        diagnostics = {
            "status": "geojson_missing",
            "geojson_path": "data/russia_regions.geojson",
            "matched_regions": 0,
            "unmatched_dashboard_regions": sorted(slim["territory_name"].dropna().unique().tolist()),
            "unmatched_geo_features": [],
            "notes": [
                "GeoJSON не найден; карта будет добавлена после подключения геослоя."
            ],
        }
        write_json(unmatched_path, diagnostics)
        crosswalk_path.write_text("[]\n", encoding="utf-8")
        return diagnostics

    geo = json.loads(geo_path.read_text(encoding="utf-8-sig"))
    features = geo.get("features", [])
    geo_names = []
    for feature in features:
        props = feature.get("properties", {})
        name = props.get("Name_full") or props.get("name") or props.get("NAME") or props.get("Name")
        if name:
            geo_names.append(str(name))
    geo_by_norm = {normalize_name(name): name for name in geo_names}

    rows = (
        slim[["territory_id", "territory_name"]]
        .drop_duplicates()
        .sort_values(["territory_name", "territory_id"])
        .to_dict(orient="records")
    )
    crosswalk = []
    matched_geo_norms: set[str] = set()
    for row in rows:
        territory_name = str(row["territory_name"])
        target_name = REGION_GEO_ALIASES.get(territory_name, territory_name)
        norm = normalize_name(target_name)
        geo_name = geo_by_norm.get(norm)
        match_method = "alias" if territory_name in REGION_GEO_ALIASES else "normalized_name"
        if geo_name:
            matched_geo_norms.add(normalize_name(geo_name))
        crosswalk.append(
            {
                "territory_id": row["territory_id"],
                "territory_name": territory_name,
                "geo_name": geo_name,
                "geo_key": geo_name,
                "match_method": match_method if geo_name else "unmatched",
                "notes": (
                    "parent/autonomous okrug alias; verify non-overlap interpretation"
                    if territory_name in REGION_GEO_ALIASES
                    and any(
                        token in territory_name
                        for token in ["кроме", "автономный округ", "Севастополь", "Москва", "Санкт-Петербург"]
                    )
                    else ""
                ),
            }
        )

    unmatched_dashboard = [
        row for row in crosswalk if not row["geo_name"]
    ]
    unmatched_geo = [
        name for name in geo_names if normalize_name(name) not in matched_geo_norms
    ]
    diagnostics = {
        "status": "ok" if not unmatched_dashboard else "partial_match",
        "geojson_path": "data/russia_regions.geojson",
        "geo_feature_count": len(features),
        "dashboard_region_count": len(rows),
        "matched_regions": len(rows) - len(unmatched_dashboard),
        "unmatched_dashboard_regions": unmatched_dashboard,
        "unmatched_geo_features": sorted(unmatched_geo),
        "notes": [
            "GeoJSON matched through Name_full with explicit aliases for federal cities and autonomous okrug naming variants.",
            "Extra GeoJSON features may remain outside the 85-region model universe.",
        ],
    }
    write_json(crosswalk_path, crosswalk)
    write_json(unmatched_path, diagnostics)
    source_path.write_text(
        "\n".join(
            [
                "Source: user-provided file `Карта_субъектов_РФ_с_данными.geojson`.",
                "Copied to `docs/data/russia_regions.geojson` for static GitHub Pages use.",
                "Feature key used by the dashboard: properties.Name_full.",
                "The source layer contains 89 features; the model universe contains 85 regions.",
                "Original feature properties also include legacy demographic/election attributes that are not used by this dashboard.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return diagnostics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-out-dir", default="outputs/model_run")
    ap.add_argument("--input", default=None)
    ap.add_argument("--dashboard-data-dir", default="docs/data")
    args = ap.parse_args()

    model_out_dir = Path(args.model_out_dir)
    source, source_status = choose_input(model_out_dir, args.input)
    dest = Path(args.dashboard_data_dir)
    dest.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(source)
    if "forecast_year" not in df.columns and "year" in df.columns:
        df = df.rename(columns={"year": "forecast_year"})
    value_col, metric_kind, metric_label, warnings = choose_value_column(df, source_status)
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce").fillna(0).clip(lower=0)

    default_values = {
        "population_scenario": "pending_demography" if metric_kind != "residual_migration_need" else "",
        "working_age_definition": "pending_demography" if metric_kind != "residual_migration_need" else "",
        "supply_allocation_scenario": "pending_demography" if metric_kind != "residual_migration_need" else "",
    }
    for column, default in default_values.items():
        if column not in df.columns:
            df[column] = default
    if "productivity_scenario" not in df.columns:
        df["productivity_scenario"] = "baseline"
    if "federal_district_name" not in df.columns:
        df["federal_district_name"] = ""

    keep = [
        c
        for c in [
            "territory_id",
            "territory_name",
            "federal_district_name",
            "activity_id",
            "okved_section",
            "activity_name",
            "forecast_year",
            value_col,
            "recommended_annual_quota_persons",
            "cumulative_recommended_quota_persons",
            "annual_new_stock_delta_persons",
            "annual_replacement_flow_persons",
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
            "domestic_sector_supply_allocated_persons",
            "unemployment_rate_ilo_15plus_pct",
            "unemployment_reserve_sector_allocated_persons",
            "domestic_sector_supply_total_with_unemployment_reserve_persons",
            "foreign_labor_stock_need_persons",
            "annual_new_foreign_labor_stock_delta_persons",
            "annual_replacement_foreign_labor_flow_persons",
            "annual_foreign_labor_quota_persons",
            "cumulative_foreign_labor_quota_persons",
            "positive_annual_labor_need_persons",
            "positive_cumulative_labor_need_persons",
            "population_scenario",
            "working_age_definition",
            "productivity_scenario",
            "supply_allocation_scenario",
        ]
        if c in df.columns
    ]
    keep = list(dict.fromkeys(keep))
    slim = df[keep].copy()
    slim["dashboard_value_persons"] = slim[value_col]
    slim.to_csv(dest / "region_sector_forecast.csv", index=False, encoding="utf-8-sig")

    yearly_metric_columns = [
        c
        for c in [
            "dashboard_value_persons",
            "labor_demand_required_persons",
            "domestic_sector_supply_allocated_persons",
            "unemployment_reserve_sector_allocated_persons",
            "domestic_sector_supply_total_with_unemployment_reserve_persons",
            "foreign_labor_stock_need_persons",
            "annual_new_foreign_labor_stock_delta_persons",
            "annual_replacement_foreign_labor_flow_persons",
            "annual_foreign_labor_quota_persons",
            "cumulative_foreign_labor_quota_persons",
            "annual_new_stock_delta_persons",
            "annual_replacement_flow_persons",
            "recommended_annual_quota_persons",
            "cumulative_recommended_quota_persons",
        ]
        if c in slim.columns
    ]
    by_year = (
        slim.groupby("forecast_year", as_index=False)[yearly_metric_columns]
        .sum()
        .rename(columns={"dashboard_value_persons": "value_persons"})
        .sort_values("forecast_year")
    )
    summary_metric_columns = [
        c
        for c in [
            "dashboard_value_persons",
            "recommended_annual_quota_persons",
            "foreign_labor_stock_need_persons",
            "cumulative_recommended_quota_persons",
        ]
        if c in slim.columns
    ]
    by_region = (
        slim.groupby(["territory_id", "territory_name"], as_index=False)[summary_metric_columns]
        .sum()
        .rename(columns={"dashboard_value_persons": "value_persons"})
        .sort_values("value_persons", ascending=False)
    )
    by_sector = (
        slim.groupby(["activity_id", "okved_section", "activity_name"], as_index=False)[summary_metric_columns]
        .sum()
        .rename(columns={"dashboard_value_persons": "value_persons"})
        .sort_values("value_persons", ascending=False)
    )

    write_json(dest / "summary_by_year.json", by_year.to_dict(orient="records"))
    write_json(dest / "summary_by_region_top.json", by_region.head(100).to_dict(orient="records"))
    write_json(dest / "summary_by_sector.json", by_sector.to_dict(orient="records"))

    qa = read_optional_json(model_out_dir / "qa_model_summary.json")
    run_config = read_optional_json(model_out_dir / "run_config.json")
    map_diagnostics = build_geo_crosswalk(slim, dest)
    dashboard_status = (
        "final_migration_need"
        if metric_kind in {"residual_migration_need", "annual_migration_quota_flow", "recommended_annual_migration_quota_flow"}
        else "pending_demography"
    )
    metadata = {
        "dashboard_title": "Потребность в трудовых ресурсах по отраслям и регионам России",
        "source_csv": source.name,
        "source_status": source_status,
        "value_column": value_col,
        "dashboard_value_column": "dashboard_value_persons",
        "metric_kind": metric_kind,
        "metric_label_ru": metric_label,
        "metric_options": {
            "recommended_annual_quota_persons": "Рекомендуемая годовая квота",
            "foreign_labor_stock_need_persons": "Дефицит на конец года",
            "cumulative_recommended_quota_persons": "Накопленная квота с 2025 г.",
        },
        "rows": int(len(slim)),
        "dashboard_status": dashboard_status,
        "status_label_ru": (
            "Расчет рекомендуемой годовой квоты и stock-дефицита завершен"
            if metric_kind in {"annual_migration_quota_flow", "recommended_annual_migration_quota_flow"}
            else "Расчет остаточной миграционной потребности завершен"
            if dashboard_status == "final_migration_need"
            else "Экономический спрос рассчитан, демографический блок ожидается"
        ),
        "warnings": warnings
        + [
            "Расчет не является автоматической квотой без профессионально-квалификационной матрицы.",
            "Показатель dashboard_value_persons по умолчанию является рекомендуемой годовой квотой/потоком, а не stock-дефицитом.",
            "Запас потребности сохранен в поле foreign_labor_stock_need_persons.",
            "Старое поле annual_foreign_labor_quota_persons сохранено как alias; административная квота v5 = recommended_annual_quota_persons.",
        ],
        "year_range": [
            int(slim["forecast_year"].min()),
            int(slim["forecast_year"].max()),
        ],
        "region_count": int(slim["territory_id"].nunique()),
        "sector_count": int(slim["activity_id"].nunique()),
        "population_scenario": scenario_values(slim, "population_scenario"),
        "working_age_definition": scenario_values(slim, "working_age_definition"),
        "productivity_scenario": scenario_values(slim, "productivity_scenario"),
        "supply_allocation_scenario": scenario_values(slim, "supply_allocation_scenario"),
        "generated_at_utc": qa.get("generated_at_utc") or datetime.now(timezone.utc).isoformat(),
        "model_version": qa.get("model_version"),
        "world_growth_source": qa.get("world_growth_qa", {}).get("source") or qa.get("world_growth_qa", {}).get("imf_source"),
        "world_growth_url": qa.get("world_growth_qa", {}).get("source_url") or qa.get("world_growth_qa", {}).get("imf_url"),
        "world_growth_access_date": qa.get("world_growth_qa", {}).get("access_date"),
        "world_growth_scenario": qa.get("world_growth_qa", {}).get("scenario"),
        "assumptions": run_config.get("assumptions", {}),
        "map": map_diagnostics,
    }
    write_json(dest / "metadata.json", metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
