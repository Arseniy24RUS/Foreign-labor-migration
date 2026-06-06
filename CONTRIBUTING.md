# Contributing / Участие

Thank you for improving `Foreign-labor-migration`. Contributions are welcome when they preserve reproducibility, make assumptions explicit, and avoid silent changes to source definitions.

Спасибо за вклад в `Foreign-labor-migration`. Особенно полезны изменения, которые повышают воспроизводимость, явно фиксируют предпосылки и не меняют определения источников без документации.

## Scope

Good contributions include:

- Methodology clarifications, sensitivity checks, and validation tests.
- Better source provenance, metadata, and data QA.
- Dashboard accessibility, i18n, and usability fixes.
- Small bug fixes in preprocessing or model formulas.
- Documentation that helps another researcher reproduce a run.

Please open an issue before large methodological changes, new source families, or changes that alter published headline metrics.

## Data and Provenance

- Do not add restricted or non-redistributable source files unless their terms allow it.
- Preserve source labels, URLs, access dates, hashes, and units.
- Prefer compact derived CSV/JSON files for dashboard inputs.
- If a source refresh changes a metric definition, document the change in `docs/methodology.md` or an issue.

## Development Setup

```bash
python -m pip install -r requirements.txt
npm install
```

Recommended checks before a pull request:

```bash
python src/check_project_inputs.py --root .
pytest
npm run test:i18n
```

If a check cannot run locally, explain why in the pull request.

## Pull Requests

- Keep changes scoped and describe the research consequence.
- Include the scenario, command, and output directory for any model rerun.
- Separate code, data refreshes, and visual-only edits when practical.
- Do not rewrite generated dashboard data by hand.
- Do not remove source provenance or third-party notices.

## Русский

Перед большим изменением методологии, новым источником данных или изменением итоговых показателей создайте issue. В pull request укажите, какие предпосылки изменились, какие команды запускались и какие проверки прошли. Если проверку невозможно запустить локально, кратко объясните причину.

