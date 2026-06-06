# Third-Party Notices

This repository combines original research software and documentation with source data, libraries, geodata, logos, and institutional names from third parties. Original code is licensed under MIT. Original documentation, compact dashboard data, and content are licensed under CC BY 4.0. Third-party materials remain subject to the terms of their original providers.

## Official Statistics and Source Data

- Rosstat / EMISS: raw and processed Russian regional statistics may include employment, gross regional product, labor productivity indices, unemployment by ILO methodology for the population aged 15+, activity classifiers, and regional reference tables. These materials remain official statistical source materials and are not relicensed by this repository.
- OECD: the long-run world growth scenario is based on OECD Economic Outlook 117 long-term scenarios / OECD Long-Term Model data. The project stores a compact model-ready growth table with source labels and access metadata. OECD data and names remain governed by OECD terms.
- Population inputs: demographic scenario files in `data/population_repo_PLACEHOLDER/` are treated as external research inputs. Their original license, citation, and update policy should be preserved when replacing the placeholder source.
- IMF preliminary scenario file: `data/forecasts_preliminary/world_growth_target_imf2026.csv`, if used for comparison or legacy checks, remains subject to IMF source terms.

## Geodata

- `docs/data/russia_regions.geojson` and related crosswalk files are used to render the regional dashboard map. The source layer and any upstream geodata attributes remain subject to their original terms. The project-specific crosswalk, diagnostics, and preprocessing notes are covered by CC BY 4.0 unless otherwise stated.

## Libraries

The project uses third-party open-source libraries and tools, including:

- Python: pandas, numpy, openpyxl, pytest.
- JavaScript and dashboard QA: Playwright, http-server, Plotly.
- GitHub Pages and browser platform APIs.

Library names are listed for compatibility and attribution. Their code is not relicensed by this repository; use their package metadata and upstream repositories for license details.

## Logos, Names, and Trademarks

Images such as `docs/assets/fnisc.png` and `docs/assets/mgimo-home.png`, institutional names, logos, and trademarks are used only for identification, attribution, or project context. They are not covered by the repository MIT or CC BY 4.0 licenses unless the rights holder has explicitly granted that permission.

No third-party provider, institution, or library maintainer should be understood as endorsing the analysis unless an explicit statement says so.

