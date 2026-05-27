Эта папка содержит компактные данные, которые напрямую загружает `docs/index.html`.

Ключевые файлы:

- `region_sector_forecast.csv`
- `factual_history_region_sector.csv`
- `summary_by_year.json`
- `summary_by_region_top.json`
- `summary_by_sector.json`
- `metadata.json`
- `russia_regions.geojson`

Пересборка после нового запуска модели:

```bash
python src/build_dashboard_inputs.py --model-out-dir outputs/model_run_v5 --dashboard-data-dir docs/data
```

Основной показатель дашборда `dashboard_value_persons` равен `recommended_annual_quota_persons`. Поле `foreign_labor_stock_need_persons` остается stock-дефицитом на конец года, а не накопленной квотой.
