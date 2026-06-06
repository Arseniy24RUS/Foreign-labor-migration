# Methodology / Методология

## English

### Research Purpose

`Foreign-labor-migration` estimates residual demand for foreign labor resources by Russian region, economic activity, and forecast year. The model is a scenario instrument, not an official forecast and not an automatic legal quota. Its purpose is to make assumptions visible, quantify where domestic labor resources may be insufficient under those assumptions, and expose the difference between a stock deficit and an annual quota-like flow.

The main public model universe is 85 non-overlapping Russian regions by 20 model economic activities. The base employment year is 2024. The default forecast horizon is 2025-2050.

### Data Sources

The model uses compact, versioned inputs stored in the repository:

- Economic panel: `data/processed/emiss_vrp_employment_productivity_panel_joined.csv`, derived from EMISS/Rosstat regional employment, gross regional product, and labor productivity index inputs in `data/raw_emiss/`.
- Population scenarios: `data/population_repo_PLACEHOLDER/POP_wide_*_noMIG.xlsx` and `POP_wide_*_withMIG.xlsx`, read by sex, age, territory, and year. The default analytical base is `noMIG`.
- Unemployment reserve: `data/processed/unemployment_rate_ilo_15plus_2017_2025_matched.csv`, parsed from the official EMISS/Rosstat unemployment-rate workbook for the ILO methodology, population aged 15+.
- Growth target: `data/forecasts_preliminary/world_growth_target_oecd_ltm_2025_2050.csv`, a model-ready table computed from the OECD Economic Outlook 117 long-term scenarios / OECD Long-Term Model, default scenario `BAU1`.
- Geodata: `docs/data/russia_regions.geojson` plus `docs/data/region_geo_crosswalk.json` and map diagnostics.
- Dashboard outputs: compact CSV and JSON files in `docs/data/`, generated from model output CSV files.

Third-party source data remain governed by their original terms. The repository's own documentation, dashboard text, compact derived content, and figures are licensed under CC BY 4.0; source code is MIT-licensed.

### Data Versioning and Provenance

The reproducibility contract is file-based:

- Raw source files are kept under `data/raw_emiss/` or a clearly named external-input directory whenever redistribution is appropriate.
- Processed analytical inputs are stored under `data/processed/` with stable column names.
- Dashboard-ready files are stored under `docs/data/` and should be regenerated from the model outputs rather than hand-edited.
- Model runs write `qa_model_summary.json`, `run_config.json`, validation tables, and audit reports under the chosen `outputs/` and audit directories.
- Key inputs are hashed with SHA-256 in model QA output where the pipeline reads them directly.
- Source URLs, access dates, source labels, scenario names, and unit-conversion rules are preserved in data columns or QA metadata.

When a source is refreshed, update the source label, access date, data file hash, preprocessing notes, and dashboard metadata together. Do not silently overwrite a model-ready file with a changed source definition.

### Preprocessing Pipeline

Preprocessing is designed to make the modeling universe explicit before estimating deficits:

1. Normalize territory names by lowercasing, replacing `ё` with `е`, standardizing dash variants, removing punctuation, and applying a small set of known aliases for autonomous okrug and regional naming variants.
2. Filter the economic panel to non-overlapping model regions and model activities.
3. Use 2024 employment as the base employment level for each region-sector cell.
4. Convert productivity index values such as `104.6` into growth rates such as `0.046`.
5. Build historical productivity growth from available GRP and employment history where possible.
6. Sum population files to working-age resources for definitions `15-64`, `15-69`, and `15-72`.
7. Match population territories to the economic panel and write crosswalk diagnostics.
8. Expand ILO unemployment rates to the forecast horizon by carrying the latest official regional value forward.
9. Convert OECD growth percentage columns to decimals and require a complete 2025-2050 annual sequence for the OECD LTM input.
10. Validate map matching between model regions and the GeoJSON layer.

### Notation

Let:

- `r` be a region, `s` be an economic activity, and `t` be a forecast year.
- `E_{r,s,2024}` be base employment in 2024.
- `g_t` be the annual real output growth target.
- `p_{r,s,t}` be annual labor productivity growth.
- `L_{r,s,t}` be required employment demand.
- `W_{r,t}` be working-age population under the selected age definition.
- `c_{r}` be the capped 2024 employment-to-working-age ratio.
- `q_{r,s,t}` be the region-sector domestic supply allocation share.
- `u_{r,t}` be the ILO unemployment rate in percent.
- `m` be the unemployment mobilization coefficient.
- `rho` be the migrant retention rate.

### Economic Demand Identity

The core model identity is:

```text
real output = employment * labor productivity
```

Therefore required employment evolves as:

```text
L_{r,s,t} = L_{r,s,t-1} * (1 + g_t) / (1 + p_{r,s,t})
```

For the first forecast year, `L_{r,s,t-1}` is `E_{r,s,2024}`. Higher output growth increases required employment. Higher productivity growth reduces required employment for the same output target.

### Productivity Terms

The default v5 publication scenario uses a hierarchical mean-reverting productivity forecast:

```text
log(1 + p_{r,s,t}) =
  common_t + sector_factor_{s,t} + region_factor_{r,t} + cell_residual_{r,s,t}
```

The common component mean-reverts toward a historical median. Sector components mean-revert with reliability weights based on coverage and volatility. Region factors and cell residuals mean-revert toward zero. Forecasts are clipped by sector empirical percentiles and global bounds so very short, noisy histories do not dominate the horizon.

The model also retains legacy productivity scenarios:

- `baseline`
- `low_productivity`
- `high_productivity`

These use shrinkage across official hybrid index growth, cell historical CAGR, sector median, region median, and global median, with scenario shifts and fixed clipping.

### Domestic Labor Supply

For each region and working-age definition:

```text
c_r = min(E_{r,2024} / W_{r,2024}, 0.90)
domestic_capacity_{r,t} = W_{r,t} * c_r
```

The cap prevents the model from implying implausibly high employment rates when the population and employment sources are not perfectly aligned.

Domestic capacity is allocated across sectors with one of four scenarios:

- `fixed_2024_sector_shares`: keep 2024 sector employment shares.
- `demand_weighted_sector_shares`: gradually blend 2024 shares with demand shares.
- `bounded_transition`: move shares toward demand shares with a fixed annual cap.
- `empirical_bounded_transition`: estimate region-sector share-change caps from 2017-2024 employment history and project shares to a capped simplex so each regional year sums to one.

Allocated domestic supply is:

```text
domestic_supply_{r,s,t} = domestic_capacity_{r,t} * q_{r,s,t}
```

### Unemployment Reserve

The unemployment-rate input is a percent of the labor force, not a percent of employed persons. If `E` is the domestic employment capacity and `u` is the unemployment rate in percent:

```text
unemployment_reserve_{r,t} = E * u_{r,t} / (100 - u_{r,t}) * m
```

The reserve can be disabled, split equally by sector, or split by supply allocation share. The default publication setting is `equal_sector_split` with `m = 1.0`.

Total domestic supply after reserve is:

```text
domestic_total_{r,s,t} =
  domestic_supply_{r,s,t} + unemployment_reserve_allocated_{r,s,t}
```

### Deficit, Stock Need, and Quota Terms

The gross labor deficit after the unemployment reserve is:

```text
deficit_{r,s,t} = L_{r,s,t} - domestic_total_{r,s,t}
```

The foreign labor stock need is the non-negative residual:

```text
stock_need_{r,s,t} = max(0, deficit_{r,s,t})
```

The model keeps the legacy alias `foreign_labor_migration_need_persons`, but the preferred interpretation is `foreign_labor_stock_need_persons`: the end-of-year stock deficit for a region-sector cell.

The annual recommended quota-like flow is separated from the stock:

```text
new_stock_delta_{r,s,t} = max(0, stock_need_{r,s,t} - stock_need_{r,s,t-1})
replacement_flow_{r,s,t} = stock_need_{r,s,t-1} * (1 - rho)
recommended_annual_quota_{r,s,t} = new_stock_delta_{r,s,t} + replacement_flow_{r,s,t}
```

By default `rho = 1.0`, so no replacement flow is added. If a user sets a lower retention rate, the quota includes replacement for prior-year stock.

### Assumptions

The default publication scenario is:

```text
population_scenario = noMIG
working_age_definition = 15-72
productivity_scenario = champion
supply_allocation_scenario = empirical_bounded_transition
unemployment_reserve_policy = equal_sector_split
unemployment_mobilization_coef = 1.0
migrant_retention_rate = 1.0
```

Important assumptions:

- `noMIG` is the default demographic base because `withMIG` already embeds migration into the population trajectory.
- Demand is modeled as residual labor need, not as observed migration.
- Regional and sectoral comparability depend on the EMISS/Rosstat classification and the non-overlap region universe.
- The output growth target is applied as a common annual target across region-sector cells; regional heterogeneity enters through base structure, productivity, population, unemployment, and allocation shares.
- The unemployment reserve is a first approximation and does not represent occupation, education, health, mobility, or legal eligibility.
- Administrative quota design would require an additional occupation-by-qualification layer and legal filters.

### Sensitivity Checks

Recommended sensitivity checks:

- Compare working-age definitions `15-64`, `15-69`, and `15-72`.
- Compare `noMIG` with `withMIG` only as a sensitivity exercise.
- Compare legacy productivity scenarios and the champion mean-reverting forecast.
- Compare fixed, demand-weighted, bounded, and empirical bounded allocation rules.
- Vary `unemployment_mobilization_coef` below 1.0 to test partial mobilization.
- Vary `migrant_retention_rate` to separate new stock demand from replacement flows.
- Inspect control years 2030, 2036, and 2050.
- Check clipped productivity shares, share-transition cap violations, duplicate keys, and non-negative quota outputs in audit files.

### Limitations

The model should be read with these limitations:

- It estimates residual labor demand, not actual migrant arrivals.
- It does not model occupations, wages, vacancies, skill mismatch, visa rules, recruitment channels, or employer compliance.
- Productivity is statistically damped over a short history and is not a structural technology forecast.
- The unemployment reserve assumes comparability between model employment capacity and labor-force survey concepts.
- Equal sector splitting of unemployment is neutral but not behaviorally rich.
- GeoJSON boundaries and regional definitions can differ from statistical reporting units.
- The stock need should not be summed across years as unique migrants.
- Preliminary or placeholder source inputs should be replaced only with documented provenance and version metadata.

### Reproducible Commands

Install dependencies:

```bash
python -m pip install -r requirements.txt
npm install
```

Check project inputs:

```bash
python src/check_project_inputs.py --root .
```

Refresh optional source-derived inputs when the source files are available:

```bash
python src/parse_unemployment_rate_ilo.py \
  --input-xlsx data/raw_emiss/Уровень\ безработицы\ по\ методологии\ МОТ\ 15plus.xlsx \
  --ref-territories data/processed/emiss_ref_territories.csv \
  --out-dir data/processed

python src/fetch_oecd_ltm_world_growth.py \
  --scenario BAU1 \
  --start-year 2025 \
  --end-year 2050 \
  --out data/forecasts_preliminary/world_growth_target_oecd_ltm_2025_2050.csv
```

Run the default v5 publication model:

```bash
python src/run_full_model.py \
  --out-dir outputs/model_run_v5 \
  --audit-dir outputs/codex_audit_v5 \
  --start-year 2025 \
  --end-year 2050 \
  --work-age-min 15 \
  --work-age-max 72 \
  --population-scenario noMIG \
  --productivity-scenario champion \
  --supply-allocation-scenario empirical_bounded_transition \
  --unemployment-reserve-policy equal_sector_split \
  --unemployment-mobilization-coef 1.0 \
  --migrant-retention-rate 1.0 \
  --skip-sensitivity
```

Build dashboard inputs:

```bash
python src/build_dashboard_inputs.py \
  --model-out-dir outputs/model_run_v5 \
  --dashboard-data-dir docs/data
```

Run local checks:

```bash
pytest
npm run test:i18n
```

## Русский

### Цель исследования

`Foreign-labor-migration` оценивает остаточную потребность в иностранных трудовых ресурсах по регионам России, видам экономической деятельности и годам прогноза. Это сценарный инструмент, а не официальный прогноз и не автоматическая юридическая квота. Его задача - явно зафиксировать предпосылки, показать, где внутреннего трудового ресурса может быть недостаточно, и разделить stock-дефицит и годовой поток, похожий на квоту.

Основная модельная вселенная: 85 непересекающихся регионов России и 20 модельных видов экономической деятельности. Базовый год занятости - 2024. Стандартный горизонт прогноза - 2025-2050.

### Источники данных

Модель использует компактные версионированные входы репозитория:

- Экономическая панель: `data/processed/emiss_vrp_employment_productivity_panel_joined.csv`, подготовленная из данных ЕМИСС/Росстата по занятости, ВРП и индексам производительности труда.
- Демографические сценарии: `data/population_repo_PLACEHOLDER/POP_wide_*_noMIG.xlsx` и `POP_wide_*_withMIG.xlsx`, читаемые по полу, возрасту, территории и году. Базовый аналитический сценарий - `noMIG`.
- Резерв безработицы: `data/processed/unemployment_rate_ilo_15plus_2017_2025_matched.csv`, подготовленный из официального файла ЕМИСС/Росстата по уровню безработицы по методологии МОТ для населения 15 лет и старше.
- Целевой рост: `data/forecasts_preliminary/world_growth_target_oecd_ltm_2025_2050.csv`, таблица для модели на основе OECD Economic Outlook 117 long-term scenarios / OECD Long-Term Model, сценарий `BAU1`.
- Геоданные: `docs/data/russia_regions.geojson`, кроссволк регионов и диагностика сопоставления карты.
- Выходы дашборда: компактные CSV и JSON в `docs/data/`, формируемые из модельных CSV.

Сторонние исходные данные остаются на условиях их поставщиков. Собственная документация, тексты дашборда, компактные производные материалы и фигуры репозитория распространяются по CC BY 4.0; исходный код - по MIT.

### Версионирование и происхождение данных

Воспроизводимость строится вокруг файлов:

- Исходные файлы хранятся в `data/raw_emiss/` или в явно названном каталоге внешнего источника, если их можно распространять.
- Обработанные аналитические входы хранятся в `data/processed/`.
- Файлы для дашборда хранятся в `docs/data/` и должны пересобираться из выходов модели, а не редактироваться вручную.
- Запуск модели пишет `qa_model_summary.json`, `run_config.json`, валидационные таблицы и audit-отчеты в каталоги `outputs/` и audit.
- Для ключевых входов в QA сохраняются SHA-256 хэши.
- URL источников, даты доступа, названия сценариев и правила преобразования единиц фиксируются в данных или метаданных.

При обновлении источника нужно одновременно обновлять метку источника, дату доступа, хэш, описание предобработки и метаданные дашборда. Нельзя молча заменять файл, если изменилась дефиниция источника.

### Предобработка

Основные шаги:

1. Нормализация названий территорий: нижний регистр, замена `ё` на `е`, унификация тире, удаление пунктуации и применение известных алиасов.
2. Фильтрация экономической панели до непересекающихся модельных регионов и модельных отраслей.
3. Использование занятости 2024 года как базового уровня для каждой ячейки регион-отрасль.
4. Перевод индексов производительности вида `104.6` в темпы роста вида `0.046`.
5. Построение исторических темпов производительности по ВРП и занятости там, где это возможно.
6. Суммирование демографических файлов в трудоспособный ресурс для определений `15-64`, `15-69`, `15-72`.
7. Сопоставление демографических территорий с экономической панелью и запись диагностики.
8. Расширение официальных рядов безработицы на прогнозный горизонт переносом последнего доступного регионального значения.
9. Перевод процентных темпов OECD в доли и проверка полной последовательности 2025-2050.
10. Проверка сопоставления модельных регионов с GeoJSON-слоем.

### Обозначения

Пусть:

- `r` - регион, `s` - вид деятельности, `t` - год прогноза.
- `E_{r,s,2024}` - занятость в базовом 2024 году.
- `g_t` - целевой годовой темп роста реального выпуска.
- `p_{r,s,t}` - годовой темп роста производительности труда.
- `L_{r,s,t}` - требуемая занятость.
- `W_{r,t}` - численность населения в выбранном трудоспособном возрасте.
- `c_r` - ограниченное отношение занятости 2024 года к трудоспособному населению.
- `q_{r,s,t}` - доля распределения внутреннего предложения труда по отрасли.
- `u_{r,t}` - уровень безработицы по МОТ в процентах.
- `m` - коэффициент мобилизации резерва безработных.
- `rho` - коэффициент удержания мигрантов.

### Экономический спрос

Базовое тождество:

```text
реальный выпуск = занятость * производительность труда
```

Отсюда требуемая занятость:

```text
L_{r,s,t} = L_{r,s,t-1} * (1 + g_t) / (1 + p_{r,s,t})
```

В первый прогнозный год вместо `L_{r,s,t-1}` используется `E_{r,s,2024}`. Более высокий рост выпуска увеличивает требуемую занятость, более высокий рост производительности снижает ее при том же целевом выпуске.

### Производительность

Основной сценарий v5 использует иерархический mean-reverting прогноз:

```text
log(1 + p_{r,s,t}) =
  common_t + sector_factor_{s,t} + region_factor_{r,t} + cell_residual_{r,s,t}
```

Общая компонента возвращается к исторической медиане. Отраслевые компоненты возвращаются с учетом надежности, зависящей от покрытия и волатильности. Региональные факторы и остатки ячеек возвращаются к нулю. Прогнозы ограничиваются отраслевыми эмпирическими процентилями и глобальными границами, чтобы короткие шумные ряды не определяли весь горизонт.

Также сохранены legacy-сценарии `baseline`, `low_productivity` и `high_productivity`. Они используют shrinkage по официальному гибридному индексу, историческому CAGR ячейки, отраслевой медиане, региональной медиане и глобальной медиане.

### Внутреннее предложение труда

Для региона и определения трудоспособного возраста:

```text
c_r = min(E_{r,2024} / W_{r,2024}, 0.90)
domestic_capacity_{r,t} = W_{r,t} * c_r
```

Ограничение 0.90 предотвращает нереалистично высокие коэффициенты занятости при несовпадении демографических и экономических источников.

Внутренний ресурс распределяется по отраслям одним из сценариев:

- `fixed_2024_sector_shares`: сохранение отраслевых долей 2024 года.
- `demand_weighted_sector_shares`: постепенное смешение долей 2024 года с долями спроса.
- `bounded_transition`: движение к долям спроса с фиксированным годовым ограничением.
- `empirical_bounded_transition`: оценка ограничений изменения долей по истории 2017-2024 и проекция на capped simplex так, чтобы доли региона за год суммировались к единице.

Отраслевое внутреннее предложение:

```text
domestic_supply_{r,s,t} = domestic_capacity_{r,t} * q_{r,s,t}
```

### Резерв безработицы

Уровень безработицы задан в процентах к рабочей силе, а не к занятым. Если `E` - внутренняя емкость занятости, а `u` - уровень безработицы в процентах:

```text
unemployment_reserve_{r,t} = E * u_{r,t} / (100 - u_{r,t}) * m
```

Резерв можно отключить, распределить поровну по отраслям или распределить по долям внутреннего предложения. Базовая публикационная настройка - `equal_sector_split`, `m = 1.0`.

Итоговое внутреннее предложение:

```text
domestic_total_{r,s,t} =
  domestic_supply_{r,s,t} + unemployment_reserve_allocated_{r,s,t}
```

### Дефицит, stock-потребность и квота

Валовой дефицит после резерва безработицы:

```text
deficit_{r,s,t} = L_{r,s,t} - domestic_total_{r,s,t}
```

Stock-потребность в иностранной рабочей силе:

```text
stock_need_{r,s,t} = max(0, deficit_{r,s,t})
```

Поле `foreign_labor_migration_need_persons` сохранено как legacy alias, но предпочтительная интерпретация - `foreign_labor_stock_need_persons`: дефицит на конец года в ячейке регион-отрасль.

Годовой квотный поток отделен от stock:

```text
new_stock_delta_{r,s,t} = max(0, stock_need_{r,s,t} - stock_need_{r,s,t-1})
replacement_flow_{r,s,t} = stock_need_{r,s,t-1} * (1 - rho)
recommended_annual_quota_{r,s,t} = new_stock_delta_{r,s,t} + replacement_flow_{r,s,t}
```

По умолчанию `rho = 1.0`, поэтому замещение выбывающих мигрантов не добавляется. При меньшем коэффициенте удержания квота включает replacement flow.

### Базовые предпосылки

```text
population_scenario = noMIG
working_age_definition = 15-72
productivity_scenario = champion
supply_allocation_scenario = empirical_bounded_transition
unemployment_reserve_policy = equal_sector_split
unemployment_mobilization_coef = 1.0
migrant_retention_rate = 1.0
```

Ключевые предпосылки:

- `noMIG` выбран как база, потому что `withMIG` уже включает миграцию в демографическую траекторию.
- Спрос моделируется как остаточная трудовая потребность, а не как наблюдаемая миграция.
- Сопоставимость регионов и отраслей зависит от классификации ЕМИСС/Росстата и непересекающейся региональной вселенной.
- Целевой рост выпуска применяется как общий годовой ориентир; региональная неоднородность входит через структуру базы, производительность, население, безработицу и доли распределения.
- Резерв безработных - первая аппроксимация, без учета профессии, образования, здоровья, мобильности и правовой допустимости.
- Для административной квоты нужен дополнительный слой профессия-квалификация и правовые фильтры.

### Проверки чувствительности

Рекомендуемые проверки:

- Сравнить определения трудоспособного возраста `15-64`, `15-69`, `15-72`.
- Сравнить `noMIG` и `withMIG` только как чувствительность.
- Сравнить legacy-сценарии производительности и champion mean-reverting прогноз.
- Сравнить фиксированные, demand-weighted, bounded и empirical bounded правила распределения.
- Изменять `unemployment_mobilization_coef` ниже 1.0.
- Изменять `migrant_retention_rate`, чтобы разделять новый stock и замещение.
- Проверять контрольные годы 2030, 2036 и 2050.
- Смотреть долю clipped-прогнозов производительности, нарушения ограничений изменения долей, дубли ключей и неотрицательность квот в audit-файлах.

### Ограничения

- Модель оценивает остаточную потребность в труде, а не фактические прибытия мигрантов.
- В модели нет профессий, зарплат, вакансий, skill mismatch, визовых правил, каналов найма и комплаенса работодателей.
- Производительность статистически демпфируется по короткой истории и не является структурным технологическим прогнозом.
- Резерв безработицы предполагает сопоставимость модельной емкости занятости и понятий обследования рабочей силы.
- Равное распределение безработных по отраслям нейтрально, но поведенчески бедно.
- Границы GeoJSON и статистические единицы могут различаться.
- Stock-потребность нельзя суммировать по годам как число уникальных мигрантов.
- Предварительные или placeholder-входы нужно заменять только с документированным происхождением и версией.

### Воспроизводимые команды

Установка зависимостей:

```bash
python -m pip install -r requirements.txt
npm install
```

Проверка входов:

```bash
python src/check_project_inputs.py --root .
```

Обновление производных входов при наличии исходных файлов:

```bash
python src/parse_unemployment_rate_ilo.py \
  --input-xlsx data/raw_emiss/Уровень\ безработицы\ по\ методологии\ МОТ\ 15plus.xlsx \
  --ref-territories data/processed/emiss_ref_territories.csv \
  --out-dir data/processed

python src/fetch_oecd_ltm_world_growth.py \
  --scenario BAU1 \
  --start-year 2025 \
  --end-year 2050 \
  --out data/forecasts_preliminary/world_growth_target_oecd_ltm_2025_2050.csv
```

Запуск основной модели v5:

```bash
python src/run_full_model.py \
  --out-dir outputs/model_run_v5 \
  --audit-dir outputs/codex_audit_v5 \
  --start-year 2025 \
  --end-year 2050 \
  --work-age-min 15 \
  --work-age-max 72 \
  --population-scenario noMIG \
  --productivity-scenario champion \
  --supply-allocation-scenario empirical_bounded_transition \
  --unemployment-reserve-policy equal_sector_split \
  --unemployment-mobilization-coef 1.0 \
  --migrant-retention-rate 1.0 \
  --skip-sensitivity
```

Сборка данных дашборда:

```bash
python src/build_dashboard_inputs.py \
  --model-out-dir outputs/model_run_v5 \
  --dashboard-data-dir docs/data
```

Локальные проверки:

```bash
pytest
npm run test:i18n
```

