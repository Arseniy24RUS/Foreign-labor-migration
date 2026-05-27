#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Preflight checks for the reproducible migration model."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pandas as pd


RAW_ALIASES = {
    "ВРП.xlsx": [".xlsx"],
    "Число занятых.xlsx": [".xlsx"],
    "Индекс производительности труда.xlsx": [".xlsx"],
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repair_mojibake_name(name: str) -> str | None:
    try:
        repaired = name.encode("cp866").decode("utf-8")
    except UnicodeError:
        return None
    return repaired if repaired != name else None


def ensure_raw_aliases(raw_dir: Path) -> list[dict]:
    """Create canonical UTF-8 copies for mojibake raw EMISS names; never delete originals."""
    actions: list[dict] = []
    if not raw_dir.exists():
        return actions
    for source in raw_dir.iterdir():
        if not source.is_file():
            continue
        repaired = repair_mojibake_name(source.name)
        if repaired is None:
            continue
        target = raw_dir / repaired
        if target.exists():
            status = "canonical_exists"
            copied = False
        else:
            shutil.copy2(source, target)
            status = "canonical_copy_created"
            copied = True
        actions.append(
            {
                "source": str(source),
                "canonical": str(target),
                "status": status,
                "copied": copied,
                "source_sha256": sha256_file(source),
                "canonical_sha256": sha256_file(target),
                "hash_match": sha256_file(source) == sha256_file(target),
            }
        )
    return actions


def file_info(path: Path) -> dict:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
        "sha256": sha256_file(path) if path.exists() and path.is_file() else None,
    }


def inspect_population(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    xl = pd.ExcelFile(path)
    info = {"exists": True, "sheets": xl.sheet_names}
    if "by_age" in xl.sheet_names:
        cols = pd.read_excel(path, sheet_name="by_age", nrows=0).columns.astype(str).tolist()
        df = pd.read_excel(path, sheet_name="by_age", usecols=[0, 1])
        info.update(
            {
                "by_age_columns_first_12": cols[:12],
                "by_age_rows": int(len(df)),
                "year_min": int(pd.to_numeric(df.iloc[:, 1], errors="coerce").min()),
                "year_max": int(pd.to_numeric(df.iloc[:, 1], errors="coerce").max()),
                "territory_blocks": int(df.iloc[:, 0].dropna().nunique()),
            }
        )
    return info


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--report", default="outputs/input_check_report.json")
    ap.add_argument("--no-create-raw-aliases", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    raw_dir = root / "data/raw_emiss"
    alias_actions = [] if args.no_create_raw_aliases else ensure_raw_aliases(raw_dir)

    files = {
        "economic_panel": root / "data/processed/emiss_vrp_employment_productivity_panel_joined.csv",
        "fact_long": root / "data/processed/emiss_vrp_employment_productivity_fact_long.csv",
        "world_growth": root / "data/forecasts_preliminary/world_growth_target_imf2026.csv",
        "raw_vrp": raw_dir / "ВРП.xlsx",
        "raw_employment": raw_dir / "Число занятых.xlsx",
        "raw_productivity_index": raw_dir / "Индекс производительности труда.xlsx",
        "pop_male_noMIG": root / "data/population_repo_PLACEHOLDER/POP_wide_male_noMIG.xlsx",
        "pop_female_noMIG": root / "data/population_repo_PLACEHOLDER/POP_wide_female_noMIG.xlsx",
    }
    report = {
        "status": "complete",
        "raw_alias_actions": alias_actions,
        "files": {k: file_info(v) for k, v in files.items()},
    }

    panel_path = files["economic_panel"]
    if panel_path.exists():
        df = pd.read_csv(panel_path)
        model = df[
            df["is_nonoverlap_model_region"].astype(str).str.lower().isin(["true", "1"])
            & df["is_model_activity"].astype(str).str.lower().isin(["true", "1"])
        ].copy()
        base = model[model["year"].astype(int).eq(2024)]
        report["economic_panel"] = {
            "rows": int(len(df)),
            "columns": list(df.columns),
            "years": sorted(pd.to_numeric(df["year"], errors="coerce").dropna().astype(int).unique().tolist()),
            "model_rows": int(len(model)),
            "model_territories": int(model["territory_id"].nunique()),
            "model_activities": int(model["activity_id"].nunique()),
            "model_duplicate_keys": int(model.duplicated(["territory_id", "activity_id", "year"]).sum()),
            "base_2024_rows": int(len(base)),
            "base_2024_missing_or_nonpositive_employment": int((pd.to_numeric(base["employment_persons"], errors="coerce") <= 0).sum() + base["employment_persons"].isna().sum()),
        }

    world_path = files["world_growth"]
    if world_path.exists():
        wg = pd.read_csv(world_path)
        report["world_growth"] = {"rows": int(len(wg)), "columns": list(wg.columns), "head": wg.head(5).to_dict(orient="records")}

    report["population"] = {
        "male_noMIG": inspect_population(files["pop_male_noMIG"]),
        "female_noMIG": inspect_population(files["pop_female_noMIG"]),
    }

    missing = [k for k, v in report["files"].items() if not v["exists"]]
    report["missing_required_files"] = missing
    report["status"] = "ok" if not missing else "missing_files"

    report_path = root / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
