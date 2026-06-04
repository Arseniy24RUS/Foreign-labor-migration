# Foreign Labor Migration · Regional and Sectoral Demand Dashboard

[English](#english) · [Русский](#русский)

[![Live demo](https://img.shields.io/badge/demo-GitHub%20Pages-blue)](https://arseniy24rus.github.io/Foreign-labor-migration/)
[![Code: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Data/docs: CC BY 4.0](https://img.shields.io/badge/data%20%26%20docs-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Python](https://img.shields.io/badge/python-data%20pipeline-informational)](requirements.txt)

---

## English

### Overview

`Foreign-labor-migration` is a reproducible research software project for estimating and visualizing the demand for foreign labour resources across Russian regions and economic sectors. It combines a Python modelling pipeline, compact dashboard-ready datasets and a static GitHub Pages interface for exploring regional and sectoral scenarios.

The project is intended for demographic analysis, labour-market research, regional policy studies and teaching. It translates heterogeneous input assumptions into interpretable regional indicators and dashboard layers that can be inspected, compared and reused.

### Research question

The central question of the project is: how may the need for foreign labour resources differ across Russian regions and sectors under alternative assumptions about population, employment, productivity, unemployment and economic growth? The model does not produce an official forecast. It is a scenario-based analytical instrument that helps make assumptions explicit and compare their implications.

### Live dashboard

GitHub Pages: <https://arseniy24rus.github.io/Foreign-labor-migration/>

### Repository structure

```text
.github/workflows/    GitHub Pages and automation workflows
data/                 Compact CSV, JSON and GeoJSON inputs for the dashboard
docs/                 Static dashboard files and generated web assets
src/                  Python scripts for checking inputs and building model outputs
tests/                Input and reproducibility checks
requirements.txt      Python dependencies
README.md             Project documentation
```

### Main workflow

The repository separates modelling from publication. Python scripts prepare and validate analytical inputs, while the `docs/` directory contains static files served by GitHub Pages. This allows the dashboard to remain lightweight and reproducible.

Typical workflow:

```bash
# 1. Install Python dependencies
python -m pip install -r requirements.txt

# 2. Check input files and structure
python src/check_project_inputs.py

# 3. Run the full model with explicit assumptions
python src/run_full_model.py \
  --base-dir . \
  --output-dir outputs \
  --years 2025 2050 \
  --working-ages 15 72

# 4. Build dashboard-ready inputs
python src/build_dashboard_inputs.py \
  --base-dir . \
  --outputs-dir outputs \
  --docs-dir docs
```

### Methodological logic

The project operationalizes labour-resource demand as a regional and sectoral scenario problem. Its inputs may include regional population assumptions, employment structure, economic growth targets, productivity dynamics, unemployment constraints and supply allocation rules. The outputs are intended to show where foreign labour demand may become more pronounced, how sectoral structure affects regional demand, and how assumptions influence spatial patterns.

### Data provenance

All dashboard-ready datasets should be stored in compact, versioned formats in `data/` and `docs/`. Each source dataset should be accompanied by a clear description of source, year, spatial unit, variable definitions and preprocessing steps. Official statistics and third-party datasets remain subject to their own terms of use.

### Validation

The minimum validation layer includes file-existence checks, schema checks, non-negativity checks for core indicators, consistency of regional identifiers, dashboard asset checks and reproducibility checks for generated outputs. The recommended quality target is that a clean clone of the repository can rebuild the dashboard inputs from documented commands.

### Limitations

The model is scenario-based. It should not be interpreted as a deterministic prediction or an official estimate of labour migration. Results depend on input assumptions, regional classifications, sectoral aggregation, the selected working-age interval, treatment of productivity and the quality of source statistics.

### Citation

If you use this repository, dashboard, data structure or methodological logic, please cite:

> Sitkovskiy, A. M. (2026). Foreign Labor Migration: regional and sectoral demand dashboard. GitHub. https://github.com/Arseniy24RUS/Foreign-labor-migration

### License

Unless otherwise stated, source code is released under the MIT License. Data, documentation and dashboard text are released under Creative Commons Attribution 4.0 International (CC BY 4.0). External source data may be governed by the terms of their original providers.

---

## Русский

### Обзор

`Foreign-labor-migration` — воспроизводимый исследовательский программный проект для оценки и визуализации потребности регионов и отраслей России в иностранных трудовых ресурсах. Он объединяет Python-пайплайн моделирования, компактные наборы данных для дашборда и статический интерфейс GitHub Pages для изучения региональных и отраслевых сценариев.

Проект предназначен для демографического анализа, исследований рынка труда, региональной политики и преподавания. Он переводит разнородные входные предпосылки в интерпретируемые региональные показатели и слои дашборда, которые можно изучать, сравнивать и повторно использовать.

### Научная постановка задачи

Центральный вопрос проекта: как может различаться потребность в иностранных трудовых ресурсах между субъектами РФ и секторами экономики при альтернативных предпосылках о населении, занятости, производительности, безработице и экономическом росте? Модель не является официальным прогнозом. Это сценарный аналитический инструмент, позволяющий явно фиксировать предпосылки и сравнивать их последствия.

### Публичный дашборд

GitHub Pages: <https://arseniy24rus.github.io/Foreign-labor-migration/>

### Структура репозитория

```text
.github/workflows/    Workflow для GitHub Pages и автоматизации
data/                 Компактные CSV, JSON и GeoJSON-данные для дашборда
docs/                 Статические файлы дашборда и сгенерированные веб-ресурсы
src/                  Python-скрипты проверки входов и построения выходов модели
tests/                Проверки входных данных и воспроизводимости
requirements.txt      Python-зависимости
README.md             Документация проекта
```

### Основной рабочий процесс

Репозиторий разделяет моделирование и публикацию. Python-скрипты готовят и валидируют аналитические входы, а каталог `docs/` содержит статические файлы, публикуемые через GitHub Pages. Это позволяет сохранять дашборд лёгким и воспроизводимым.

Типовой процесс:

```bash
# 1. Установка Python-зависимостей
python -m pip install -r requirements.txt

# 2. Проверка входных файлов и структуры
python src/check_project_inputs.py

# 3. Запуск полной модели с явными предпосылками
python src/run_full_model.py \
  --base-dir . \
  --output-dir outputs \
  --years 2025 2050 \
  --working-ages 15 72

# 4. Формирование входов для дашборда
python src/build_dashboard_inputs.py \
  --base-dir . \
  --outputs-dir outputs \
  --docs-dir docs
```

### Методологическая логика

Проект рассматривает потребность в трудовых ресурсах как региональную и отраслевую сценарную задачу. Среди входов могут использоваться региональные демографические предпосылки, структура занятости, целевые параметры экономического роста, динамика производительности, ограничения по безработице и правила распределения предложения труда. Выходы помогают увидеть, где потребность в иностранной рабочей силе может быть более выраженной, как отраслевая структура влияет на региональный спрос и как предпосылки меняют пространственную картину.

### Происхождение данных

Все данные, готовые для дашборда, должны храниться в компактных версионированных форматах в `data/` и `docs/`. Каждый источник данных должен сопровождаться описанием источника, года, пространственной единицы, переменных и этапов предобработки. Официальная статистика и сторонние наборы данных сохраняют собственные условия использования.

### Валидация

Минимальный слой валидации включает проверку наличия файлов, проверку схемы данных, неотрицательности ключевых показателей, согласованности региональных идентификаторов, доступности ресурсов дашборда и воспроизводимости сгенерированных выходов. Целевое качество: чистый клон репозитория должен позволять пересобрать входы дашборда по документированным командам.

### Ограничения

Модель является сценарной. Её результаты не следует трактовать как детерминированный прогноз или официальную оценку трудовой миграции. Итоги зависят от входных предпосылок, региональной классификации, отраслевой агрегации, выбранного интервала трудоспособных возрастов, трактовки производительности и качества исходной статистики.

### Как цитировать

При использовании репозитория, дашборда, структуры данных или методологической логики, пожалуйста, цитируйте:

> Ситковский А. М. Foreign Labor Migration: regional and sectoral demand dashboard. GitHub, 2026. https://github.com/Arseniy24RUS/Foreign-labor-migration

### Лицензия

Если явно не указано иное, исходный код распространяется по лицензии MIT. Данные, документация и тексты дашборда распространяются по лицензии Creative Commons Attribution 4.0 International (CC BY 4.0). Внешние исходные данные могут регулироваться условиями их первоначальных поставщиков.
