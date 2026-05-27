#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse official EMISS/Rosstat unemployment-rate XLSX into model-ready CSV files.

Input indicator: unemployment rate by ILO methodology, population aged 15+,
percent of labour force, by Russian territory and year.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import pandas as pd


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


def classify_territory(raw_name: str, indent: int) -> str:
    name = raw_name.strip()
    lname = name.lower()
    if name == "Российская Федерация":
        return "rf_total"
    if "без учета новых субъектов" in lname:
        return "rf_without_new_subjects"
    if "федеральный округ" in lname:
        return "federal_district"
    if "кроме" in lname or indent >= 12:
        return "nested_or_part_region"
    return "subject_or_parent_region"


def parse_unemployment_xlsx(input_xlsx: Path, raw_copy_name: str | None = None) -> pd.DataFrame:
    df = pd.read_excel(input_xlsx, sheet_name="Данные")
    territory_col = df.columns[0]
    year_cols: list[tuple[object, int]] = []
    for col in df.columns[1:]:
        try:
            year = int(float(col))
        except Exception:
            continue
        if 1900 <= year <= 2200:
            year_cols.append((col, year))
    if not year_cols:
        raise ValueError("No year columns were found in the unemployment-rate workbook")

    file_hash = sha256_file(input_xlsx)
    raw_copy_name = raw_copy_name or input_xlsx.name
    rows = []
    for _, row in df.iterrows():
        raw_name = str(row[territory_col])
        if raw_name.strip() == "" or raw_name.strip().lower() == "nan":
            continue
        indent = len(raw_name) - len(raw_name.lstrip())
        name = raw_name.strip()
        for col, year in year_cols:
            value = pd.to_numeric(row[col], errors="coerce")
            rows.append(
                {
                    "territory_name_source": name,
                    "territory_norm": normalize_name(name),
                    "indent_spaces": indent,
                    "territory_kind_source": classify_territory(name, indent),
                    "year": year,
                    "unemployment_rate_ilo_15plus_pct": float(value) if pd.notna(value) else None,
                    "indicator_name": "Уровень безработицы (по методологии МОТ), население 15 лет и старше",
                    "unit": "percent_of_labor_force",
                    "source_file": raw_copy_name,
                    "source_file_sha256": file_hash,
                    "source_note": "User-supplied official EMISS/Rosstat XLSX; parsed from sheet Данные.",
                }
            )
    out = pd.DataFrame(rows)
    if out["unemployment_rate_ilo_15plus_pct"].dropna().lt(0).any():
        raise ValueError("Unemployment rate contains negative values")
    if out["unemployment_rate_ilo_15plus_pct"].dropna().ge(100).any():
        raise ValueError("Unemployment rate must be below 100%")
    return out


def match_to_ref(long: pd.DataFrame, ref_path: Path) -> pd.DataFrame:
    ref = pd.read_csv(ref_path)
    ref["territory_norm"] = ref["territory_name"].map(normalize_name)
    cols = [
        "territory_id",
        "territory_name",
        "territory_level",
        "federal_district_id",
        "federal_district_name",
        "is_rf_total",
        "is_federal_district",
        "is_nonoverlap_model_region",
        "is_overlapping_parent_region",
        "is_part_without_autonomous_okryg",
        "is_nested_official_autonomous_okryg",
        "territory_norm",
    ]
    matched = long.merge(ref[[c for c in cols if c in ref.columns]], on="territory_norm", how="left")
    matched["match_status"] = matched["territory_id"].notna().map({True: "matched_to_emiss_ref", False: "unmatched"})
    return matched


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse unemployment rate by ILO methodology XLSX into model-ready CSV files.")
    ap.add_argument("--input-xlsx", default="data/raw_emiss/Уровень безработицы по методологии МОТ 15plus.xlsx")
    ap.add_argument("--ref-territories", default="data/processed/emiss_ref_territories.csv")
    ap.add_argument("--out-dir", default="data/processed")
    ap.add_argument("--copy-raw-to", default=None, help="Optional destination for a stable raw copy inside the project.")
    args = ap.parse_args()

    input_xlsx = Path(args.input_xlsx)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_copy_name = input_xlsx.name
    if args.copy_raw_to:
        raw_copy = Path(args.copy_raw_to)
        raw_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_xlsx, raw_copy)
        raw_copy_name = raw_copy.name

    long = parse_unemployment_xlsx(input_xlsx, raw_copy_name=raw_copy_name)
    matched = match_to_ref(long, Path(args.ref_territories))

    long_path = out_dir / "unemployment_rate_ilo_15plus_2017_2025_long.csv"
    matched_path = out_dir / "unemployment_rate_ilo_15plus_2017_2025_matched.csv"
    long.to_csv(long_path, index=False, encoding="utf-8-sig")
    matched.to_csv(matched_path, index=False, encoding="utf-8-sig")

    model_mask = matched["is_nonoverlap_model_region"].astype(str).str.lower().isin(["true", "1"])
    latest_year = int(long["year"].max())
    latest_model = matched[model_mask & matched["year"].eq(latest_year)]
    qa = {
        "source_file": str(input_xlsx),
        "source_sha256": sha256_file(input_xlsx),
        "rows_source_territories": int(long["territory_name_source"].nunique()),
        "rows_long": int(len(long)),
        "years": [int(long["year"].min()), int(long["year"].max())],
        "matched_rows": int(matched["territory_id"].notna().sum()),
        "unmatched_rows": int(matched["territory_id"].isna().sum()),
        "matched_territories": int(matched.loc[matched["territory_id"].notna(), "territory_id"].nunique()),
        "model_nonoverlap_territories_with_latest_rate": int(latest_model["territory_id"].nunique()),
        "latest_year": latest_year,
        "mean_latest_model_rate_pct": float(latest_model["unemployment_rate_ilo_15plus_pct"].mean()),
        "min_latest_model_rate_pct": float(latest_model["unemployment_rate_ilo_15plus_pct"].min()),
        "max_latest_model_rate_pct": float(latest_model["unemployment_rate_ilo_15plus_pct"].max()),
        "long_csv": str(long_path),
        "matched_csv": str(matched_path),
    }
    (out_dir / "unemployment_rate_ilo_15plus_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(qa, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
