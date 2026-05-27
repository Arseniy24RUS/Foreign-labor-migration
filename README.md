# Foreign Labor Migration Dashboard

Статический GitHub Pages-дашборд и воспроизводимый набор данных для модели потребности в иностранных трудовых ресурсах по регионам и отраслям России.

## Что внутри

- `docs/` - готовый статический сайт для GitHub Pages.
- `docs/data/` - компактные CSV, JSON и GeoJSON, которые дашборд загружает в браузере.
- `data/` - входные и подготовленные данные модели.
- `src/` - актуальные скрипты расчета и подготовки данных дашборда.
- `.github/workflows/pages.yml` - автоматическая публикация `docs/` через GitHub Actions.

В архив намеренно не включены локальные `outputs/`, скриншоты, кэши, старые архивные скрипты, patch/manifest-файлы и прочий рабочий мусор.

## Публикация на GitHub Pages

1. Распакуйте архив.
2. Загрузите содержимое распакованной папки в корень GitHub-репозитория.
3. Убедитесь, что основная ветка называется `main`.
4. В настройках репозитория откройте `Settings -> Pages` и используйте публикацию через `GitHub Actions`.
5. После push workflow `Deploy static dashboard to GitHub Pages` опубликует папку `docs/`.

Дашборд уже содержит все нужные файлы в `docs/data`, поэтому для публикации не нужен Node.js, сборщик или серверная часть.

## Локальная проверка

```bash
python -m http.server 8000 --directory docs
```

Затем откройте `http://localhost:8000`.

Проверить входные данные модели:

```bash
python src/check_project_inputs.py --root .
```

Пересчитать модель и заново подготовить данные дашборда:

```bash
python src/run_full_model.py \
  --economic-panel data/processed/emiss_vrp_employment_productivity_panel_joined.csv \
  --world-growth data/forecasts_preliminary/world_growth_target_oecd_ltm_2025_2050.csv \
  --unemployment-rate data/processed/unemployment_rate_ilo_15plus_2017_2025_matched.csv \
  --population-dir data/population_repo_PLACEHOLDER \
  --population-long-cache outputs/model_run/population_long_noMIG.csv \
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
  --migrant-retention-rate 1.0

python src/build_dashboard_inputs.py \
  --model-out-dir outputs/model_run_v5 \
  --dashboard-data-dir docs/data
```

`outputs/` не хранится в репозитории: это тяжелые воспроизводимые результаты, которые создаются локально.
