const DATA_PATHS = {
  metadata: "data/metadata.json",
  forecast: "data/region_sector_forecast.csv",
  factualHistory: "data/factual_history_region_sector.csv",
  factualSummaryYear: "data/factual_summary_by_year.json",
  geojson: "data/russia_regions.geojson",
  crosswalk: "data/region_geo_crosswalk.json",
  unmatched: "data/map_unmatched_regions.json"
};

const NUMERIC_COLUMNS = [
  "forecast_year",
  "dashboard_value_persons",
  "foreign_labor_migration_need_persons",
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
  "gross_labor_deficit_persons",
  "foreign_labor_stock_need_persons",
  "annual_new_foreign_labor_stock_delta_persons",
  "annual_replacement_foreign_labor_flow_persons",
  "annual_foreign_labor_quota_persons",
  "cumulative_foreign_labor_quota_persons",
  "annual_labor_demand_delta_persons",
  "cumulative_delta_from_2024_persons",
  "positive_annual_labor_need_persons",
  "positive_cumulative_labor_need_persons"
];

const FACTUAL_NUMERIC_COLUMNS = [
  "year",
  "employment_persons",
  "vrp_constant_2016_mln_rub",
  "labour_productivity_constant_2016_thousand_rub_per_person",
  "official_productivity_index_hybrid_pct"
];

const SECTOR_META = {
  A: { label: "Агро", icon: "leaf" },
  B: { label: "Добыча", icon: "mine" },
  C: { label: "Производство", icon: "factory" },
  D: { label: "Энергия", icon: "bolt" },
  E: { label: "Вода", icon: "drop" },
  F: { label: "Стройка", icon: "crane" },
  G: { label: "Торговля", icon: "store" },
  H: { label: "Транспорт", icon: "truck" },
  I: { label: "Гостиницы", icon: "utensils" },
  J: { label: "Связь", icon: "network" },
  K: { label: "Финансы", icon: "coin" },
  L: { label: "Недвижимость", icon: "building" },
  M: { label: "Наука", icon: "compass" },
  N: { label: "Админ", icon: "clipboard" },
  O: { label: "Госуправление", icon: "columns" },
  P: { label: "Образование", icon: "book" },
  Q: { label: "Здоровье", icon: "health" },
  R: { label: "Культура", icon: "spark" },
  S: { label: "Услуги", icon: "hand" },
  T: { label: "Домохозяйства", icon: "home" }
};

const state = {
  meta: {},
  rows: [],
  factualRows: [],
  factualSummaryYear: [],
  geojson: null,
  crosswalk: [],
  unmatched: null,
  filters: {},
  sort: { key: "dashboard_value_persons", dir: "desc" },
  factualSort: { key: "year", dir: "desc" },
  metricKey: "recommended_annual_quota_persons",
  selectedMapRegionId: null,
  tableMode: "forecast",
  tableRows: [],
  factualTableRows: [],
  exportRows: []
};

const fmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const fmtShort = new Intl.NumberFormat("ru-RU", {
  notation: "compact",
  compactDisplay: "short",
  maximumFractionDigits: 1
});
const fmtDecimal = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });
const fmtPercent = new Intl.NumberFormat("ru-RU", {
  style: "percent",
  maximumFractionDigits: 1
});
const CONTROL_YEARS = [2030, 2036, 2050];
const METRIC_OPTIONS = {
  recommended_annual_quota_persons: "Рекомендуемая годовая квота",
  foreign_labor_stock_need_persons: "Дефицит на конец года",
  cumulative_recommended_quota_persons: "Накопленная квота с 2025 г."
};

function byId(id) {
  return document.getElementById(id);
}

async function fetchJson(path, optional = false) {
  const response = await fetch(path);
  if (!response.ok) {
    if (optional) return null;
    throw new Error(`Не удалось загрузить ${path}`);
  }
  return response.json();
}

async function fetchText(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Не удалось загрузить ${path}`);
  return response.text();
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let inQuotes = false;
  const pushValue = () => {
    row.push(value);
    value = "";
  };
  const pushRow = () => {
    if (row.length || value.length) {
      pushValue();
      rows.push(row);
    }
    row = [];
  };

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (char === "\"") {
      if (inQuotes && next === "\"") {
        value += "\"";
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === "," && !inQuotes) {
      pushValue();
    } else if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") i += 1;
      pushRow();
    } else {
      value += char;
    }
  }
  if (value.length || row.length) pushRow();

  const header = rows.shift() || [];
  if (header[0]) header[0] = header[0].replace(/^\uFEFF/, "");
  return rows
    .filter((items) => items.length === header.length)
    .map((items) => Object.fromEntries(header.map((key, index) => [key, items[index] ?? ""])));
}

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function prepareRows(rows) {
  return rows.map((row) => {
    const out = { ...row };
    NUMERIC_COLUMNS.forEach((column) => {
      if (column in out) out[column] = toNumber(out[column]);
    });
    if (!("dashboard_value_persons" in out)) {
      const metric = state.meta.value_column || "foreign_labor_migration_need_persons";
      out.dashboard_value_persons = toNumber(out[metric]);
    }
    out.sector_label = `${out.okved_section || ""} — ${out.activity_name || ""}`;
    out.scenario_label = [
      out.population_scenario,
      out.working_age_definition,
      out.productivity_scenario,
      out.supply_allocation_scenario
    ].filter(Boolean).join(" × ");
    return out;
  });
}

function prepareFactualRows(rows) {
  return rows.map((row) => {
    const out = { ...row };
    FACTUAL_NUMERIC_COLUMNS.forEach((column) => {
      if (column in out) out[column] = toNumber(out[column]);
    });
    out.sector_label = `${out.okved_section || ""} — ${out.activity_name || ""}`;
    return out;
  });
}

function uniqueSorted(rows, key, numeric = false) {
  const values = [...new Set(rows.map((row) => row[key]).filter((value) => value !== "" && value != null))];
  return values.sort((a, b) => numeric ? Number(a) - Number(b) : String(a).localeCompare(String(b), "ru"));
}

function fillSelect(id, values, options = {}) {
  const select = byId(id);
  const {
    allLabel = "Все",
    includeAll = true,
    value = null,
    formatter = (item) => item
  } = options;
  select.innerHTML = "";
  if (includeAll) {
    const option = document.createElement("option");
    option.value = "__all__";
    option.textContent = allLabel;
    select.appendChild(option);
  }
  values.forEach((item) => {
    const option = document.createElement("option");
    option.value = String(item);
    option.textContent = formatter(item);
    select.appendChild(option);
  });
  select.value = value == null ? select.options[0]?.value || "" : String(value);
  select.disabled = !includeAll && values.length <= 1;
}

function sum(rows, key = "dashboard_value_persons") {
  return rows.reduce((total, row) => total + toNumber(row[key]), 0);
}

function weightedAverage(rows, valueKey, weightKey = "employment_2024_persons") {
  let weightedSum = 0;
  let weightSum = 0;
  const fallbackValues = [];
  rows.forEach((row) => {
    const value = Number(row[valueKey]);
    if (!Number.isFinite(value)) return;
    const weight = toNumber(row[weightKey]);
    fallbackValues.push(value);
    if (weight > 0) {
      weightedSum += value * weight;
      weightSum += weight;
    }
  });
  if (weightSum > 0) return weightedSum / weightSum;
  if (!fallbackValues.length) return 0;
  return fallbackValues.reduce((total, value) => total + value, 0) / fallbackValues.length;
}

function formatPercentField(value) {
  const number = Number(value);
  return Number.isFinite(number) ? fmtPercent.format(number) : "н/д";
}

function metricValue(row, key = state.metricKey) {
  return toNumber(row[key || "recommended_annual_quota_persons"]);
}

function withSelectedMetric(rows) {
  return rows.map((row) => ({
    ...row,
    dashboard_value_persons: metricValue(row)
  }));
}

function metricLabel() {
  return METRIC_OPTIONS[state.metricKey] || "Рекомендуемая годовая квота";
}

function groupBy(rows, keys, valueKey = "dashboard_value_persons") {
  const map = new Map();
  rows.forEach((row) => {
    const keyValues = keys.map((key) => row[key] || "");
    const id = keyValues.join("||");
    if (!map.has(id)) {
      const entry = Object.fromEntries(keys.map((key, index) => [key, keyValues[index]]));
      entry.value_persons = 0;
      entry.rows = 0;
      map.set(id, entry);
    }
    const entry = map.get(id);
    entry.value_persons += toNumber(row[valueKey]);
    entry.rows += 1;
  });
  return [...map.values()];
}

function applyFilters(rows, { ignoreYear = false, ignoreSector = false } = {}) {
  return rows.filter((row) => {
    const f = state.filters;
    if (!ignoreYear && f.year && row.forecast_year !== Number(f.year)) return false;
    if (f.district !== "__all__" && row.federal_district_name !== f.district) return false;
    if (f.regions?.length && !f.regions.includes(row.territory_id)) return false;
    if (!ignoreSector && f.sector !== "__all__" && row.activity_id !== f.sector) return false;
    return true;
  });
}

function applyFactualFilters(rows) {
  return rows.filter((row) => {
    const f = state.filters;
    if (f.district !== "__all__" && row.federal_district_name !== f.district) return false;
    if (f.regions?.length && !f.regions.includes(row.territory_id)) return false;
    if (f.sector !== "__all__" && row.activity_id !== f.sector) return false;
    return true;
  });
}

function chartLayout(title = "", extra = {}) {
  return {
    title: title ? { text: title, font: { size: 14 } } : undefined,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, Segoe UI, system-ui, sans-serif", color: "#071b48", size: 12 },
    margin: { t: title ? 42 : 18, r: 14, b: 42, l: 58 },
    colorway: ["#0B5ED7", "#0AA77A", "#2388FF", "#E23B52", "#6A7FA6"],
    hoverlabel: { bgcolor: "#ffffff", bordercolor: "#c4d4ea", font: { color: "#071b48" } },
    ...extra
  };
}

function plotConfig() {
  return {
    responsive: true,
    displayModeBar: false,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d"]
  };
}

function controlYearShapes() {
  return CONTROL_YEARS.map((year) => ({
    type: "line",
    x0: year,
    x1: year,
    y0: 0,
    y1: 1,
    yref: "paper",
    line: { color: "#6A7FA6", width: 1, dash: "dot" }
  }));
}

function controlYearAnnotations() {
  return CONTROL_YEARS.map((year) => ({
    x: year,
    y: 1,
    yref: "paper",
    text: String(year),
    showarrow: false,
    yanchor: "bottom",
    font: { size: 10, color: "#475569" }
  }));
}

function ensurePlotly() {
  if (!window.Plotly) {
    throw new Error("Plotly не загружен. Проверьте локальный файл assets/plotly-2.35.2.min.js.");
  }
}

function updateHeader() {
  const meta = state.meta;
  byId("metric-caption").textContent = `Показатель карты и атласа: ${metricLabel()}, человек`;
  const sourceText = [];
  if (meta.world_growth_source) sourceText.push(`Макроэкономический ориентир: ${meta.world_growth_source}.`);
  if (meta.world_growth_scenario) sourceText.push(`Сценарий: ${meta.world_growth_scenario}.`);
  if (meta.generated_at_utc) sourceText.push(`Расчет сформирован: ${new Date(meta.generated_at_utc).toLocaleString("ru-RU")}.`);
  sourceText.push("Все файлы дашборда загружаются как статические ресурсы из папки docs/.");
  byId("source-note").textContent = sourceText.join(" ");
}

function updateYearTimeline(options = {}) {
  const input = byId("filter-year");
  const value = Number(input?.value || state.filters.year || 0);
  const valueTarget = byId("timeline-year-value");
  if (valueTarget) valueTarget.textContent = value ? String(value) : "-";
  const buttons = Array.from(document.querySelectorAll("#year-timeline-ticks button"));
  const years = buttons.map((button) => Number(button.dataset.year));
  const currentIndex = years.indexOf(value);
  const progress = currentIndex >= 0 && years.length > 1 ? (currentIndex / (years.length - 1)) * 100 : 0;
  document.querySelector(".year-timeline-track")?.style.setProperty("--timeline-progress", `${progress}%`);
  let activeButton = null;
  buttons.forEach((button) => {
    const active = Number(button.dataset.year) === value;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.setAttribute("aria-selected", active ? "true" : "false");
    button.tabIndex = active ? 0 : -1;
    if (active) activeButton = button;
  });
  if (options.scrollActive) {
    activeButton?.scrollIntoView({ behavior: options.smooth ? "smooth" : "auto", block: "nearest", inline: "center" });
  }
}

function setupYearTimeline(years, defaultYear) {
  const input = byId("filter-year");
  const ticks = byId("year-timeline-ticks");
  if (!input || !ticks) return;
  const numericYears = years.map(Number);
  input.value = String(defaultYear);
  ticks.style.setProperty("--timeline-year-count", String(numericYears.length));
  ticks.innerHTML = numericYears.map((year, index) => {
    const marker = CONTROL_YEARS.includes(year) ? " control-year" : "";
    const phase = index === 0 ? " start-year" : index === numericYears.length - 1 ? " end-year" : "";
    return `<button class="year-tick${marker}${phase}" type="button" role="option" data-year="${year}" aria-pressed="false" aria-selected="false">
      <span>${year}</span>
    </button>`;
  }).join("");

  const commitYear = (year, focusActive = false) => {
    input.value = String(year);
    updateYearTimeline({ scrollActive: true, smooth: true });
    readFiltersAndRender();
    if (focusActive) {
      ticks.querySelector(`button[data-year="${year}"]`)?.focus();
    }
  };

  ticks.querySelectorAll("button[data-year]").forEach((button) => {
    button.addEventListener("click", () => {
      commitYear(Number(button.dataset.year));
    });
  });

  ticks.addEventListener("keydown", (event) => {
    const current = Number(input.value || defaultYear);
    const currentIndex = numericYears.indexOf(current);
    const keyTargets = {
      ArrowLeft: numericYears[Math.max(0, currentIndex - 1)],
      ArrowRight: numericYears[Math.min(numericYears.length - 1, currentIndex + 1)],
      Home: numericYears[0],
      End: numericYears[numericYears.length - 1]
    };
    if (!(event.key in keyTargets)) return;
    event.preventDefault();
    commitYear(keyTargets[event.key], true);
  });

  updateYearTimeline({ scrollActive: true });
}

function selectedRegionIds() {
  return Array.from(document.querySelectorAll("#filter-region-options input[type='checkbox']:checked"))
    .map((input) => input.value);
}

function updateRegionSummary() {
  const selected = selectedRegionIds();
  const summary = byId("filter-region-summary");
  if (!summary) return;
  if (!selected.length) {
    summary.textContent = "Все регионы";
    return;
  }
  const names = selected.map((id) => state.regionNameById?.get(id) || id);
  summary.textContent = names.length <= 2 ? names.join(", ") : `${names.length} регионов`;
}

function renderRegionFilter(regions) {
  state.regionNameById = new Map(regions.map((row) => [row.territory_id, row.territory_name]));
  const container = byId("filter-region-options");
  if (!container) return;
  container.innerHTML = regions.map((row) => {
    const id = `region-${row.territory_id}`;
    return `<label class="region-option" for="${escapeHtml(id)}">
      <input id="${escapeHtml(id)}" type="checkbox" value="${escapeHtml(row.territory_id)}" />
      <span>${escapeHtml(row.territory_name)}</span>
    </label>`;
  }).join("");
  container.addEventListener("change", () => {
    updateRegionSummary();
    readFiltersAndRender();
  });
  byId("filter-region-clear")?.addEventListener("click", () => {
    container.querySelectorAll("input[type='checkbox']").forEach((input) => {
      input.checked = false;
    });
    updateRegionSummary();
    readFiltersAndRender();
  });
  updateRegionSummary();
}

function setupFilters() {
  const years = uniqueSorted(state.rows, "forecast_year", true);
  const defaultYear = years[years.length - 1];
  setupYearTimeline(years, defaultYear);
  fillSelect("filter-district", uniqueSorted(state.rows, "federal_district_name"), { allLabel: "Все округа" });
  const regions = groupBy(state.rows, ["territory_id", "territory_name"])
    .sort((a, b) => a.territory_name.localeCompare(b.territory_name, "ru"));
  renderRegionFilter(regions);
  const sectors = groupBy(state.rows, ["activity_id", "okved_section", "activity_name"])
    .sort((a, b) => String(a.okved_section).localeCompare(String(b.okved_section), "ru"));
  fillSelect("filter-sector", sectors.map((row) => row.activity_id), {
    allLabel: "Все отрасли",
    formatter: (id) => {
      const row = sectors.find((item) => item.activity_id === id);
      return row ? `${row.okved_section} — ${row.activity_name}` : id;
    }
  });

  ["filter-district", "filter-sector"]
    .forEach((id) => byId(id).addEventListener("change", readFiltersAndRender));
  byId("reset-filters").addEventListener("click", () => {
    byId("filter-year").value = String(defaultYear);
    byId("filter-district").value = "__all__";
    state.selectedMapRegionId = null;
    byId("filter-region-options").querySelectorAll("input[type='checkbox']").forEach((input) => {
      input.checked = false;
    });
    updateRegionSummary();
    byId("filter-sector").value = "__all__";
    byId("table-search").value = "";
    readFiltersAndRender();
  });
  byId("table-search").addEventListener("input", renderTable);
  byId("download-csv").addEventListener("click", downloadCsv);
  document.querySelectorAll("[data-table-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.tableMode = button.dataset.tableMode;
      byId("table-search").value = "";
      renderTable();
    });
  });
  document.querySelectorAll("[data-metric-key]").forEach((button) => {
    button.addEventListener("click", () => {
      state.metricKey = button.dataset.metricKey || "recommended_annual_quota_persons";
      document.querySelectorAll("[data-metric-key]").forEach((item) => {
        const active = item.dataset.metricKey === state.metricKey;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", active ? "true" : "false");
      });
      updateHeader();
      render();
    });
  });
  byId("detail-table").querySelector("thead").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-sort]");
    if (!button) return;
    const key = button.dataset.sort;
    const sortState = state.tableMode === "forecast" ? state.sort : state.factualSort;
    if (sortState.key === key) {
      sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
    } else if (state.tableMode === "forecast") {
      state.sort = { key, dir: key === "dashboard_value_persons" ? "desc" : "asc" };
    } else {
      state.factualSort = { key, dir: key === "year" ? "desc" : "asc" };
    }
    renderTable();
  });

  readFilters();
  updateYearTimeline();
}

function readFilters() {
  state.filters = {
    year: Number(byId("filter-year").value),
    district: byId("filter-district").value,
    regions: selectedRegionIds(),
    sector: byId("filter-sector").value
  };
}

function readFiltersAndRender() {
  const previousRegions = state.filters.regions || [];
  readFilters();
  if (!state.filters.regions.length && previousRegions.length) {
    state.selectedMapRegionId = null;
  }
  updateYearTimeline();
  render();
}

function scenarioLabel() {
  const meta = state.meta || {};
  return [
    ...(meta.population_scenario || []),
    ...(meta.working_age_definition || []),
    ...(meta.productivity_scenario || []),
    ...(meta.supply_allocation_scenario || [])
  ].filter(Boolean).join(" / ") || "базовый";
}

function scenarioShortLabel() {
  const meta = state.meta || {};
  const population = meta.population_scenario?.[0] || "noMIG";
  const productivity = meta.productivity_scenario?.[0] || "baseline";
  return `${population} / ${productivity}`;
}

function scenarioDetailLabel() {
  const meta = state.meta || {};
  return [
    ...(meta.working_age_definition || []),
    ...(meta.supply_allocation_scenario || [])
  ].filter(Boolean).join(" / ") || "возраст / распределение";
}

function latestCumulativeQuota(rows) {
  if (!rows.length) return 0;
  const years = rows.map((row) => Number(row.forecast_year)).filter(Number.isFinite);
  const finalYear = Math.max(...years);
  const finalRows = rows.filter((row) => Number(row.forecast_year) === finalYear);
  const cumulative = sum(finalRows, "cumulative_recommended_quota_persons");
  return cumulative || sum(finalRows, "cumulative_foreign_labor_quota_persons") || sum(rows, "recommended_annual_quota_persons");
}

function renderKpis(selectedRows, horizonRows) {
  const positiveRows = selectedRows.filter((row) => row.recommended_annual_quota_persons > 0);
  const positiveCellShare = selectedRows.length ? positiveRows.length / selectedRows.length : 0;
  const productivity = weightedAverage(selectedRows, "productivity_growth_forecast_yearly");
  byId("kpi-year-total").textContent = fmt.format(sum(selectedRows, "recommended_annual_quota_persons"));
  byId("kpi-stock-total").textContent = fmt.format(sum(selectedRows, "foreign_labor_stock_need_persons"));
  byId("kpi-horizon-total").textContent = fmt.format(latestCumulativeQuota(horizonRows));
  byId("kpi-reserve-total").textContent = fmt.format(sum(selectedRows, "unemployment_reserve_sector_allocated_persons"));
  byId("kpi-productivity").textContent = formatPercentField(productivity);
  byId("kpi-positive-share").textContent = fmtPercent.format(positiveCellShare);
}

function sectorIconSvg(type) {
  const icons = {
    leaf: "<path d='M7 18c8-9 18-11 30-7-1 12-10 22-24 22H8c5-5 10-10 18-14' /><path d='M8 36c7-8 14-13 24-17' />",
    mine: "<path d='M6 36h36M12 36l8-22 8 22M20 14h11l5 22M15 25h18' />",
    factory: "<path d='M5 37h38V21l-10 5v-5l-10 5V14H5v23Z' /><path d='M11 30h4m5 0h4m5 0h4' />",
    bolt: "<path d='M27 5 12 27h10l-2 16 16-24H25l2-14Z' />",
    drop: "<path d='M24 6s-12 14-12 24a12 12 0 0 0 24 0C36 20 24 6 24 6Z' /><path d='M18 31a6 6 0 0 0 6 6' />",
    crane: "<path d='M8 38h26M14 38V10h20M14 15h24l4 6M34 10v28M22 38V25h8v13' />",
    store: "<path d='M7 18h34l-3-8H10l-3 8Zm2 0v20h30V18M15 38V26h10v12M30 26h6' />",
    truck: "<path d='M5 31V15h24v16M29 21h7l7 8v2H29V21ZM12 36a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm24 0a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z' />",
    utensils: "<path d='M14 6v16M9 6v16m10-16v16M9 22h10v20M32 6c5 4 7 10 4 17l-3 7v12M30 6v36' />",
    network: "<path d='M10 15a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm28 14a5 5 0 1 0 0-10 5 5 0 0 0 0 10ZM17 43a5 5 0 1 0 0-10 5 5 0 0 0 0 10ZM14 13l18 9M34 29 22 36M13 34l-2-19' />",
    coin: "<path d='M24 10c9 0 16 4 16 9s-7 9-16 9S8 24 8 19s7-9 16-9Zm-16 9v10c0 5 7 9 16 9s16-4 16-9V19M15 25v10m9-7v10m9-13v10' />",
    building: "<path d='M9 39V9h30v30M15 16h4m5 0h4m5 0h4M15 24h4m5 0h4m5 0h4M20 39v-8h8v8' />",
    compass: "<path d='M24 7a17 17 0 1 0 0 34 17 17 0 0 0 0-34Zm8 9-5 12-12 5 5-12 12-5Z' />",
    clipboard: "<path d='M16 9h16v6H16V9Zm-5 4h26v29H11V13Zm8 11h12M19 31h12' />",
    columns: "<path d='M6 38h36M9 15h30M12 15v20m8-20v20m8-20v20m8-20v20M24 7 8 15h32L24 7Z' />",
    book: "<path d='M8 10h14a6 6 0 0 1 6 6v24a6 6 0 0 0-6-6H8V10Zm20 6a6 6 0 0 1 6-6h6v24h-6a6 6 0 0 0-6 6V16Z' />",
    health: "<path d='M24 39S8 30 8 18a8 8 0 0 1 14-5 8 8 0 0 1 14 5c0 12-12 18-12 21Z' /><path d='M18 24h12M24 18v12' />",
    spark: "<path d='M24 6l4 12 12 4-12 4-4 12-4-12-12-4 12-4 4-12Z' /><path d='M38 6l2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6Z' />",
    hand: "<path d='M14 25V13a3 3 0 0 1 6 0v10M20 23V10a3 3 0 0 1 6 0v13M26 23V12a3 3 0 0 1 6 0v15M32 26v-7a3 3 0 0 1 6 0v10c0 8-5 13-13 13h-3c-6 0-10-4-13-10l-3-7a3 3 0 0 1 5-3l3 5Z' />",
    home: "<path d='M7 23 24 9l17 14M12 21v20h24V21M20 41V29h8v12' />"
  };
  return `<svg viewBox="0 0 48 48" aria-hidden="true">${icons[type] || icons.spark}</svg>`;
}

function renderSectorQuickLinks(selectedRows) {
  const container = byId("sector-quick-icons");
  if (!container) return;
  const totals = new Map(
    groupBy(selectedRows, ["activity_id"]).map((row) => [row.activity_id, row.value_persons])
  );
  const sectors = groupBy(state.rows, ["activity_id", "okved_section", "activity_name"])
    .sort((a, b) => String(a.okved_section).localeCompare(String(b.okved_section), "ru"));
  container.innerHTML = sectors.map((row) => {
    const meta = SECTOR_META[row.okved_section] || { label: row.okved_section, icon: "spark" };
    const value = totals.get(row.activity_id) || 0;
    const active = state.filters.sector === row.activity_id ? " active" : "";
    return `<button class="sector-button${active}" type="button" data-sector-id="${escapeHtml(row.activity_id)}" title="${escapeHtml(row.activity_name)}">
      ${sectorIconSvg(meta.icon)}
      <span><strong>${escapeHtml(meta.label)}</strong><small>${escapeHtml(row.okved_section)} · ${fmtShort.format(value)}</small></span>
    </button>`;
  }).join("");
  container.querySelectorAll("[data-sector-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const select = byId("filter-sector");
      select.value = state.filters.sector === button.dataset.sectorId ? "__all__" : button.dataset.sectorId;
      readFiltersAndRender();
    });
  });
}

function renderFactualBase(factualRows) {
  const baseYear = Number(state.meta.base_year || 2024);
  const firstYear = Math.min(...uniqueSorted(factualRows, "year", true).map(Number), baseYear);
  const baseRows = factualRows.filter((row) => row.year === baseYear);
  const firstRows = factualRows.filter((row) => row.year === firstYear);
  const baseEmployment = sum(baseRows, "employment_persons");
  const firstEmployment = sum(firstRows, "employment_persons");
  const delta = baseEmployment - firstEmployment;
  const productivityYears = uniqueSorted(
    factualRows.filter((row) => row.labour_productivity_constant_2016_thousand_rub_per_person > 0),
    "year",
    true
  ).map(Number);
  const productivityYear = productivityYears[productivityYears.length - 1];
  const productivityRows = factualRows.filter((row) => row.year === productivityYear);
  const productivityEmployment = sum(productivityRows, "employment_persons");
  const productivityVrp = sum(productivityRows, "vrp_constant_2016_mln_rub");
  const productivity = productivityEmployment ? (productivityVrp * 1000) / productivityEmployment : 0;
  const complete = baseRows.length
    ? baseRows.filter((row) => row.employment_persons > 0).length / baseRows.length
    : 0;

  byId("fact-base-employment").textContent = baseEmployment ? fmt.format(baseEmployment) : "н/д";
  byId("fact-employment-delta").textContent = firstEmployment ? `${delta >= 0 ? "+" : ""}${fmt.format(delta)}` : "н/д";
  byId("fact-productivity").textContent = productivity ? fmtDecimal.format(productivity) : "н/д";
  byId("fact-coverage").textContent = baseRows.length ? fmtPercent.format(complete) : "н/д";
  byId("fact-caption").textContent = factualRows.length
    ? `Фактические ряды ${firstYear}-${baseYear}; значения фильтруются по округу, региону и ОКВЭД.`
    : "Фактическая история не найдена в статических данных.";
}

function renderEconomicLink(factualRows, horizonRows) {
  const scatterTarget = byId("chart-growth-scatter");
  const decompositionTarget = byId("chart-growth-decomposition");
  if (!scatterTarget || !decompositionTarget) return;

  const cellMap = new Map();
  factualRows.forEach((row) => {
    const key = `${row.territory_id}||${row.activity_id}`;
    if (!cellMap.has(key)) cellMap.set(key, []);
    cellMap.get(key).push(row);
  });
  const points = [];
  cellMap.forEach((items) => {
    items.sort((a, b) => a.year - b.year);
    for (let i = 1; i < items.length; i += 1) {
      const prev = items[i - 1];
      const cur = items[i];
      if (prev.employment_persons <= 0 || cur.employment_persons <= 0 || prev.vrp_constant_2016_mln_rub <= 0 || cur.vrp_constant_2016_mln_rub <= 0) continue;
      points.push({
        x: Math.log(cur.employment_persons / prev.employment_persons),
        y: Math.log(cur.vrp_constant_2016_mln_rub / prev.vrp_constant_2016_mln_rub),
        label: `${cur.territory_name}<br>${cur.okved_section} — ${cur.activity_name}<br>${prev.year}-${cur.year}`
      });
    }
  });

  const xValues = points.map((point) => point.x);
  const yValues = points.map((point) => point.y);
  const xMean = xValues.reduce((a, b) => a + b, 0) / Math.max(1, xValues.length);
  const yMean = yValues.reduce((a, b) => a + b, 0) / Math.max(1, yValues.length);
  const slopeDen = xValues.reduce((total, value) => total + (value - xMean) ** 2, 0);
  const slope = slopeDen ? xValues.reduce((total, value, index) => total + (value - xMean) * (yValues[index] - yMean), 0) / slopeDen : 0;
  const intercept = yMean - slope * xMean;
  const minX = Math.min(...xValues, -0.05);
  const maxX = Math.max(...xValues, 0.05);
  Plotly.react("chart-growth-scatter", [{
    x: xValues,
    y: yValues,
    customdata: points.map((point) => point.label),
    type: "scatter",
    mode: "markers",
    name: "Ячейки регион × отрасль",
    marker: { size: 6, color: "#0B5ED7", opacity: 0.34 },
    hovertemplate: "%{customdata}<br>Δln занятости: %{x:.2%}<br>Δln ВРП: %{y:.2%}<extra></extra>"
  }, {
    x: [minX, maxX],
    y: [intercept + slope * minX, intercept + slope * maxX],
    type: "scatter",
    mode: "lines",
    name: "Линейная связь",
    line: { color: "#E23B52", width: 2.5 },
    hovertemplate: "Оценка: Δln ВРП = a + b × Δln занятости<extra></extra>"
  }], chartLayout("", {
    xaxis: { title: "Δln занятости", tickformat: ".0%", zeroline: true, fixedrange: true },
    yaxis: { title: "Δln реального ВРП", tickformat: ".0%", zeroline: true, fixedrange: true },
    legend: { orientation: "h", x: 0, y: 1.14, font: { size: 11 } },
    margin: { t: 46, r: 14, b: 48, l: 64 }
  }), plotConfig());

  const factualEmployment = groupBy(factualRows, ["year"], "employment_persons")
    .sort((a, b) => Number(a.year) - Number(b.year));
  const factualVrp = new Map(groupBy(factualRows, ["year"], "vrp_constant_2016_mln_rub").map((row) => [Number(row.year), row.value_persons]));
  const factualSeries = [];
  for (let i = 1; i < factualEmployment.length; i += 1) {
    const prev = factualEmployment[i - 1];
    const cur = factualEmployment[i];
    const prevVrp = factualVrp.get(Number(prev.year));
    const curVrp = factualVrp.get(Number(cur.year));
    if (!prevVrp || !curVrp || !prev.value_persons || !cur.value_persons) continue;
    const empGrowth = Math.log(cur.value_persons / prev.value_persons);
    const vrpGrowth = Math.log(curVrp / prevVrp);
    factualSeries.push({ year: Number(cur.year), employment: empGrowth, productivity: vrpGrowth - empGrowth, source: "факт" });
  }
  const forecastYears = uniqueSorted(horizonRows, "forecast_year", true).map(Number);
  const forecastSeries = forecastYears.map((year) => {
    const rows = horizonRows.filter((row) => Number(row.forecast_year) === year);
    const target = weightedAverage(rows, "target_real_vrp_growth");
    const productivity = weightedAverage(rows, "productivity_growth_forecast_yearly");
    return {
      year,
      employment: Math.log((1 + target) / (1 + productivity)),
      productivity: Math.log(1 + productivity),
      source: "прогноз"
    };
  });
  const selected = [
    ...factualSeries.slice(-7),
    ...forecastSeries.filter((row) => CONTROL_YEARS.includes(row.year) || row.year === state.filters.year)
  ];
  const labels = selected.map((row) => `${row.year} ${row.source}`);
  Plotly.react("chart-growth-decomposition", [{
    x: labels,
    y: selected.map((row) => row.employment),
    type: "bar",
    name: "Вклад занятости",
    marker: { color: "#0B5ED7", opacity: 0.82 },
    hovertemplate: "%{x}<br>Вклад занятости: %{y:.2%}<extra></extra>"
  }, {
    x: labels,
    y: selected.map((row) => row.productivity),
    type: "bar",
    name: "Вклад производительности",
    marker: { color: "#0AA77A", opacity: 0.82 },
    hovertemplate: "%{x}<br>Вклад производительности: %{y:.2%}<extra></extra>"
  }], chartLayout("", {
    xaxis: { title: "Год", fixedrange: true },
    yaxis: { title: "Лог-темп роста", tickformat: ".1%", zeroline: true, fixedrange: true },
    legend: { orientation: "h", x: 0, y: 1.14, font: { size: 11 } },
    margin: { t: 46, r: 14, b: 64, l: 62 },
    barmode: "relative"
  }), plotConfig());
}

function renderTrend(horizonRows, factualRows) {
  const forecastData = groupBy(horizonRows, ["forecast_year"], "labor_demand_required_persons")
    .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year));
  const factualData = groupBy(factualRows, ["year"], "employment_persons")
    .sort((a, b) => Number(a.year) - Number(b.year));
  const needData = groupBy(horizonRows, ["forecast_year"])
    .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year));
  const traces = [{
    x: factualData.map((row) => row.year),
    y: factualData.map((row) => row.value_persons),
    type: "scatter",
    mode: "lines+markers",
    name: "Факт: занятость",
    line: { color: "#0AA77A", width: 3 },
    marker: { size: 6, color: "#0AA77A", line: { width: 1.5, color: "#ffffff" } },
    hovertemplate: "Год %{x}<br>Фактическая занятость: %{y:,.0f} человек<extra></extra>"
  }, {
    x: forecastData.map((row) => row.forecast_year),
    y: forecastData.map((row) => row.value_persons),
    type: "scatter",
    mode: "lines+markers",
    name: "Прогноз: требуемая занятость",
    line: { color: "#0B5ED7", width: 3, shape: "spline", smoothing: 0.35 },
    marker: { size: 6, color: "#0B5ED7", line: { width: 1.5, color: "#ffffff" } },
    hovertemplate: "Год %{x}<br>Требуемая занятость: %{y:,.0f} человек<extra></extra>"
  }, {
    x: needData.map((row) => row.forecast_year),
    y: needData.map((row) => row.value_persons),
    type: "scatter",
    mode: "lines",
    name: "Остаточная потребность",
    line: { color: "#E23B52", width: 2, dash: "dot" },
    hovertemplate: "Год %{x}<br>Остаточная потребность: %{y:,.0f} человек<extra></extra>"
  }];
  Plotly.react("chart-year", traces, chartLayout("", {
    xaxis: { title: "Год", dtick: window.innerWidth < 720 ? 4 : 2, fixedrange: true },
    yaxis: { title: "Человек", rangemode: "tozero", fixedrange: true },
    legend: { orientation: "h", x: 0, y: 1.12, font: { size: 11 } },
    shapes: [{
      type: "line",
      x0: 2024,
      x1: 2024,
      y0: 0,
      y1: 1,
      yref: "paper",
      line: { color: "#6A7FA6", width: 1, dash: "dash" }
    }],
    annotations: [{
      x: 2024,
      y: 1,
      yref: "paper",
      text: "база 2024",
      showarrow: false,
      xanchor: "right",
      yanchor: "bottom",
      font: { size: 11, color: "#475569" }
    }],
    margin: { t: 40, r: 14, b: 38, l: 64 }
  }), plotConfig());
}

function renderQuotaTrend(horizonRows) {
  const annualQuotaData = groupBy(horizonRows, ["forecast_year"], "recommended_annual_quota_persons")
    .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year));
  const cumulativeQuotaData = groupBy(horizonRows, ["forecast_year"], "cumulative_recommended_quota_persons")
    .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year));
  const stockData = groupBy(horizonRows, ["forecast_year"], "foreign_labor_stock_need_persons")
    .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year));
  const traces = [{
    x: annualQuotaData.map((row) => row.forecast_year),
    y: annualQuotaData.map((row) => row.value_persons),
    type: "bar",
    name: "Рекомендуемая годовая квота",
    marker: { color: "#0B5ED7", opacity: 0.82 },
    hovertemplate: "Год %{x}<br>Рекомендуемая квота: %{y:,.0f} человек<extra></extra>"
  }, {
    x: cumulativeQuotaData.map((row) => row.forecast_year),
    y: cumulativeQuotaData.map((row) => row.value_persons),
    type: "scatter",
    mode: "lines+markers",
    name: "Накопленная квота с 2025 г.",
    yaxis: "y2",
    line: { color: "#0AA77A", width: 3, shape: "spline", smoothing: 0.35 },
    marker: { size: 5, color: "#0AA77A", line: { width: 1, color: "#ffffff" } },
    hovertemplate: "Год %{x}<br>Накопленная квота с 2025 г.: %{y:,.0f} человек<extra></extra>"
  }, {
    x: stockData.map((row) => row.forecast_year),
    y: stockData.map((row) => row.value_persons),
    type: "scatter",
    mode: "lines+markers",
    name: "Дефицит на конец года",
    yaxis: "y2",
    line: { color: "#E23B52", width: 2.5, dash: "dot" },
    marker: { size: 5, color: "#E23B52", line: { width: 1, color: "#ffffff" } },
    hovertemplate: "Год %{x}<br>Дефицит на конец года: %{y:,.0f} человек<extra></extra>"
  }];
  Plotly.react("chart-year", traces, chartLayout("", {
    xaxis: { title: "Год", dtick: window.innerWidth < 720 ? 5 : 2, fixedrange: true },
    yaxis: { title: "Рекомендуемая квота", rangemode: "tozero", fixedrange: true },
    yaxis2: {
      title: "Дефицит / накопленная квота",
      overlaying: "y",
      side: "right",
      rangemode: "tozero",
      fixedrange: true,
      showgrid: false
    },
    legend: { orientation: "h", x: 0, y: 1.18, font: { size: 11 } },
    shapes: controlYearShapes(),
    annotations: controlYearAnnotations(),
    margin: { t: 54, r: 78, b: 40, l: 64 },
    bargap: 0.18
  }), plotConfig());
}

function renderResourceBalance(horizonRows) {
  const chart = byId("chart-resource");
  if (!chart) return;
  const requiredData = groupBy(horizonRows, ["forecast_year"], "labor_demand_required_persons")
    .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year));
  const reserveData = groupBy(horizonRows, ["forecast_year"], "unemployment_reserve_sector_allocated_persons")
    .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year));
  const migrantData = groupBy(horizonRows, ["forecast_year"], "foreign_labor_stock_need_persons")
    .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year));
  const traces = [{
    x: requiredData.map((row) => row.forecast_year),
    y: requiredData.map((row) => row.value_persons),
    type: "scatter",
    mode: "lines",
    name: "Всего требуется трудовых ресурсов",
    line: { color: "#071B48", width: 3 },
    hovertemplate: "Год %{x}<br>Требуемая занятость: %{y:,.0f} человек<extra></extra>"
  }, {
    x: reserveData.map((row) => row.forecast_year),
    y: reserveData.map((row) => row.value_persons),
    type: "bar",
    name: "Мобилизационный резерв безработных",
    yaxis: "y2",
    marker: { color: "#F59E0B", opacity: 0.78 },
    hovertemplate: "Год %{x}<br>Резерв безработных: %{y:,.0f} человек<extra></extra>"
  }, {
    x: migrantData.map((row) => row.forecast_year),
    y: migrantData.map((row) => row.value_persons),
    type: "bar",
    name: "Внешние мигранты: дефицит на конец года",
    yaxis: "y2",
    marker: { color: "#E23B52", opacity: 0.78 },
    hovertemplate: "Год %{x}<br>Дефицит на конец года: %{y:,.0f} человек<extra></extra>"
  }];
  Plotly.react("chart-resource", traces, chartLayout("", {
    xaxis: { title: "Год", dtick: window.innerWidth < 720 ? 5 : 2, fixedrange: true },
    yaxis: { title: "Всего требуется", rangemode: "tozero", fixedrange: true },
    yaxis2: {
      title: "Резерв / мигранты",
      overlaying: "y",
      side: "right",
      rangemode: "tozero",
      fixedrange: true,
      showgrid: false
    },
    legend: { orientation: "h", x: 0, y: 1.18, font: { size: 11 } },
    shapes: controlYearShapes(),
    annotations: controlYearAnnotations(),
    margin: { t: 54, r: 82, b: 40, l: 64 },
    barmode: "group",
    bargap: 0.18
  }), plotConfig());
}

function renderProductivityAndShares(horizonRows, sectorRows) {
  const productivityChart = byId("chart-productivity");
  const sharesChart = byId("chart-sector-shares");
  if (!productivityChart || !sharesChart) return;

  const years = uniqueSorted(horizonRows, "forecast_year", true).map(Number);
  const productivitySeries = years.map((year) => {
    const rows = horizonRows.filter((row) => Number(row.forecast_year) === year);
    return {
      year,
      yearly: weightedAverage(rows, "productivity_growth_forecast_yearly"),
      static: weightedAverage(rows, "productivity_growth_forecast_static"),
      target: weightedAverage(rows, "target_real_vrp_growth")
    };
  });
  const traces = [{
    x: productivitySeries.map((row) => row.year),
    y: productivitySeries.map((row) => row.yearly),
    type: "scatter",
    mode: "lines+markers",
    name: "Годовой прогноз производительности",
    line: { color: "#0B5ED7", width: 3, shape: "spline", smoothing: 0.35 },
    marker: { size: 5, color: "#0B5ED7", line: { width: 1, color: "#ffffff" } },
    hovertemplate: "Год %{x}<br>Рост производительности: %{y:.2%}<extra></extra>"
  }];
  const hasStaticForecast = productivitySeries.some((row) => Math.abs(row.static - row.yearly) > 0.00001);
  if (hasStaticForecast) {
    traces.push({
      x: productivitySeries.map((row) => row.year),
      y: productivitySeries.map((row) => row.static),
      type: "scatter",
      mode: "lines",
      name: "Статическая оценка производительности",
      line: { color: "#6A7FA6", width: 2, dash: "dot" },
      hovertemplate: "Год %{x}<br>Статическая оценка: %{y:.2%}<extra></extra>"
    });
  }
  traces.push({
    x: productivitySeries.map((row) => row.year),
    y: productivitySeries.map((row) => row.target),
    type: "scatter",
    mode: "lines",
    name: "Целевой рост ВРП",
    line: { color: "#0AA77A", width: 2.4, dash: "dash" },
    hovertemplate: "Год %{x}<br>Целевой рост ВРП: %{y:.2%}<extra></extra>"
  });

  Plotly.react("chart-productivity", traces, chartLayout("", {
    xaxis: { title: "Год", dtick: window.innerWidth < 720 ? 5 : 2, fixedrange: true },
    yaxis: { title: "Темп роста", tickformat: ".1%", fixedrange: true },
    legend: { orientation: "h", x: 0, y: 1.2, font: { size: 11 } },
    shapes: controlYearShapes(),
    annotations: controlYearAnnotations(),
    margin: { t: 58, r: 14, b: 42, l: 58 }
  }), plotConfig());

  const sectors = groupBy(state.rows, ["activity_id", "okved_section", "activity_name"])
    .sort((a, b) => String(a.okved_section).localeCompare(String(b.okved_section), "ru"));
  const baseBySector = new Map(
    groupBy(sectorRows, ["activity_id"], "employment_2024_persons")
      .map((row) => [row.activity_id, row.value_persons])
  );
  const forecastBySector = new Map(
    groupBy(sectorRows, ["activity_id"], "domestic_sector_supply_allocated_persons")
      .map((row) => [row.activity_id, row.value_persons])
  );
  const totalBaseEmployment = sum(sectorRows, "employment_2024_persons");
  const totalForecastSupply = sum(sectorRows, "domestic_sector_supply_allocated_persons");
  const sectorLabels = sectors.map((sector) => `${sector.okved_section} — ${sector.activity_name}`);
  const baseShares = sectors.map((sector) => totalBaseEmployment
    ? (baseBySector.get(sector.activity_id) || 0) / totalBaseEmployment
    : 0);
  const forecastShares = sectors.map((sector) => totalForecastSupply
    ? (forecastBySector.get(sector.activity_id) || 0) / totalForecastSupply
    : 0);

  Plotly.react("chart-sector-shares", [{
    x: sectors.map((sector) => sector.okved_section),
    y: baseShares,
    customdata: sectorLabels,
    type: "bar",
    name: "Доля занятости 2024",
    marker: { color: "#6A7FA6", opacity: 0.82 },
    hovertemplate: "%{customdata}<br>Доля занятости 2024: %{y:.1%}<extra></extra>"
  }, {
    x: sectors.map((sector) => sector.okved_section),
    y: forecastShares,
    customdata: sectorLabels,
    type: "bar",
    name: "Прогнозная доля внутреннего ресурса",
    marker: { color: "#0B5ED7", opacity: 0.82 },
    hovertemplate: "%{customdata}<br>Прогнозная доля: %{y:.1%}<extra></extra>"
  }], chartLayout("", {
    xaxis: { title: "Секция ОКВЭД", fixedrange: true },
    yaxis: { title: "Доля", tickformat: ".0%", rangemode: "tozero", fixedrange: true },
    legend: { orientation: "h", x: 0, y: 1.18, font: { size: 11 } },
    margin: { t: 54, r: 14, b: 42, l: 58 },
    barmode: "group",
    bargap: 0.18
  }), plotConfig());
}

function renderRanking(chartId, data, labelKey, leftMargin) {
  const top = data
    .filter((row) => row.value_persons > 0)
    .sort((a, b) => b.value_persons - a.value_persons)
    .slice(0, window.innerWidth < 720 ? 10 : 20)
    .reverse();
  const fullLabels = top.map((row) => row[labelKey]);
  const axisLabels = fullLabels.map((label) => shortenLabel(label, window.innerWidth < 720 ? 34 : 64));
  Plotly.react(chartId, [{
    x: top.map((row) => row.value_persons),
    y: axisLabels,
    customdata: fullLabels,
    type: "bar",
    orientation: "h",
    marker: { color: top.map((_, index) => index), colorscale: [[0, "#b9dcff"], [1, "#0B5ED7"]], showscale: false },
    hovertemplate: "%{customdata}<br>%{x:,.0f} человек<extra></extra>"
  }], chartLayout("", {
    xaxis: { title: "Человек", fixedrange: true },
    yaxis: { automargin: true, fixedrange: true },
    margin: { t: 10, r: 10, b: 36, l: window.innerWidth < 720 ? 116 : leftMargin }
  }), plotConfig());
}

function renderHeatmap(selectedRows) {
  const allRegions = groupBy(selectedRows, ["territory_id", "territory_name"])
    .sort((a, b) => a.territory_name.localeCompare(b.territory_name, "ru"));
  const allSectors = groupBy(state.rows, ["activity_id", "okved_section", "activity_name"])
    .sort((a, b) => String(a.okved_section).localeCompare(String(b.okved_section), "ru"));
  const valueMap = new Map();
  selectedRows.forEach((row) => {
    const key = `${row.territory_id}||${row.activity_id}`;
    valueMap.set(key, (valueMap.get(key) || 0) + row.dashboard_value_persons);
  });
  const z = allRegions.map((region) => allSectors.map((sector) => valueMap.get(`${region.territory_id}||${sector.activity_id}`) || 0));
  const custom = allRegions.map((region) => allSectors.map((sector) => [
    region.territory_name,
    `${sector.okved_section} — ${sector.activity_name}`
  ]));
  const dynamicHeight = Math.max(
    window.innerWidth < 720 ? 840 : 980,
    allRegions.length * (window.innerWidth < 720 ? 13 : 15) + 150
  );
  Plotly.react("chart-heatmap", [{
    x: allSectors.map((sector) => sector.okved_section),
    y: allRegions.map((region) => shortenLabel(region.territory_name, window.innerWidth < 720 ? 24 : 52)),
    z,
    customdata: custom,
    type: "heatmap",
    colorscale: [[0, "#F4F8FF"], [0.22, "#D6E9FF"], [0.58, "#62A8F8"], [1, "#0B5ED7"]],
    colorbar: { title: "человек", tickformat: ",.0f" },
    hovertemplate: "%{customdata[0]}<br>%{customdata[1]}<br>%{z:,.0f} человек<extra></extra>"
  }], chartLayout("", {
    height: dynamicHeight,
    xaxis: { title: "Секция ОКВЭД", side: "top", fixedrange: true },
    yaxis: { automargin: true, fixedrange: true, tickfont: { size: window.innerWidth < 720 ? 9 : 10 } },
    margin: { t: 54, r: 14, b: 26, l: window.innerWidth < 720 ? 126 : 230 }
  }), plotConfig());
}

function renderAtlas(selectedRows) {
  const sankeyTarget = byId("chart-atlas-sankey");
  const bubbleTarget = byId("chart-bubble-matrix");
  if (!sankeyTarget || !bubbleTarget) return;

  const regionTotals = groupBy(selectedRows, ["territory_id", "territory_name", "federal_district_name"])
    .sort((a, b) => b.value_persons - a.value_persons);
  const sectorTotals = groupBy(selectedRows, ["activity_id", "okved_section", "activity_name"])
    .sort((a, b) => b.value_persons - a.value_persons);
  const topRegionIds = new Set(regionTotals.slice(0, 12).map((row) => row.territory_id));
  const topSectorIds = new Set(sectorTotals.slice(0, 10).map((row) => row.activity_id));
  const atlasRows = selectedRows.map((row) => ({
    ...row,
    atlas_region: topRegionIds.has(row.territory_id) ? row.territory_name : "Прочие регионы",
    atlas_sector: topSectorIds.has(row.activity_id) ? `${row.okved_section} — ${row.activity_name}` : "Прочие отрасли",
    atlas_district: row.federal_district_name || "Федеральный округ не указан"
  }));
  const districtRegion = groupBy(atlasRows, ["atlas_district", "atlas_region"]);
  const regionSector = groupBy(atlasRows, ["atlas_region", "atlas_sector"]);
  const labels = [];
  const nodeIndex = new Map();
  const addNode = (label) => {
    if (!nodeIndex.has(label)) {
      nodeIndex.set(label, labels.length);
      labels.push(label);
    }
    return nodeIndex.get(label);
  };
  const sources = [];
  const targets = [];
  const values = [];
  districtRegion.filter((row) => row.value_persons > 0).forEach((row) => {
    sources.push(addNode(row.atlas_district));
    targets.push(addNode(row.atlas_region));
    values.push(row.value_persons);
  });
  regionSector.filter((row) => row.value_persons > 0).forEach((row) => {
    sources.push(addNode(row.atlas_region));
    targets.push(addNode(row.atlas_sector));
    values.push(row.value_persons);
  });
  Plotly.react("chart-atlas-sankey", [{
    type: "sankey",
    arrangement: "snap",
    node: {
      label: labels.map((label) => shortenLabel(label, 34)),
      pad: 12,
      thickness: 13,
      line: { color: "#c4d4ea", width: 0.5 },
      color: labels.map((label) => label.startsWith("Прочие") ? "#94a3b8" : "#0B5ED7")
    },
    link: {
      source: sources,
      target: targets,
      value: values,
      color: "rgba(11, 94, 215, 0.22)"
    },
    hovertemplate: "%{source.label} → %{target.label}<br>%{value:,.0f} человек<extra></extra>"
  }], chartLayout("", {
    margin: { t: 18, r: 8, b: 18, l: 8 },
    font: { family: "Inter, Segoe UI, system-ui, sans-serif", size: 11, color: "#071b48" }
  }), plotConfig());

  const topCells = selectedRows
    .filter((row) => row.dashboard_value_persons > 0)
    .sort((a, b) => b.dashboard_value_persons - a.dashboard_value_persons)
    .slice(0, 100);
  const maxBubble = Math.max(...topCells.map((row) => row.dashboard_value_persons), 1);
  Plotly.react("chart-bubble-matrix", [{
    x: topCells.map((row) => row.okved_section),
    y: topCells.map((row) => shortenLabel(row.territory_name, window.innerWidth < 720 ? 24 : 42)),
    customdata: topCells.map((row) => [
      row.territory_name,
      `${row.okved_section} — ${row.activity_name}`,
      row.dashboard_value_persons,
      row.foreign_labor_stock_need_persons,
      row.cumulative_recommended_quota_persons
    ]),
    mode: "markers",
    type: "scatter",
    marker: {
      size: topCells.map((row) => 8 + 34 * Math.sqrt(row.dashboard_value_persons / maxBubble)),
      sizemode: "diameter",
      color: topCells.map((row) => row.foreign_labor_stock_need_persons),
      colorscale: [[0, "#b9dcff"], [0.65, "#0B5ED7"], [1, "#E23B52"]],
      showscale: true,
      colorbar: { title: "Дефицит", tickformat: ",.0f" },
      line: { color: "#ffffff", width: 1.2 },
      opacity: 0.84
    },
    hovertemplate: "%{customdata[0]}<br>%{customdata[1]}<br>" +
      `${metricLabel()}: %{customdata[2]:,.0f}<br>` +
      "Дефицит на конец года: %{customdata[3]:,.0f}<br>Накопленная квота: %{customdata[4]:,.0f}<extra></extra>"
  }], chartLayout("", {
    xaxis: { title: "Секция ОКВЭД", fixedrange: true },
    yaxis: { automargin: true, fixedrange: true, tickfont: { size: window.innerWidth < 720 ? 9 : 10 } },
    margin: { t: 18, r: 64, b: 42, l: window.innerWidth < 720 ? 118 : 190 }
  }), plotConfig());
}

function shortenLabel(value, maxLength) {
  const text = String(value || "");
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(4, maxLength - 1)).trim()}…`;
}

function topSectorsByRegion(rows) {
  const grouped = groupBy(rows, ["territory_id", "okved_section", "activity_name"]);
  const byRegion = new Map();
  grouped.forEach((row) => {
    if (!byRegion.has(row.territory_id)) byRegion.set(row.territory_id, []);
    byRegion.get(row.territory_id).push(row);
  });
  byRegion.forEach((items, key) => {
    const positiveItems = items
      .filter((item) => item.value_persons > 0)
      .sort((a, b) => b.value_persons - a.value_persons)
      .slice(0, 3);
    byRegion.set(key, positiveItems.length
      ? positiveItems.map((item) => `${item.okved_section}: ${fmtShort.format(item.value_persons)}`).join("; ")
      : "нет положительных отраслей");
  });
  return byRegion;
}

function renderMap(selectedRows) {
  const fallback = byId("map-fallback");
  fallback.classList.add("hidden");
  if (!state.geojson || !state.crosswalk.length) {
    byId("map-status").textContent = "GeoJSON не найден; карта будет добавлена после подключения геослоя.";
    fallback.classList.remove("hidden");
    fallback.innerHTML = fallbackRegionList(selectedRows);
    byId("chart-map").innerHTML = "";
    return;
  }
  const crosswalkById = new Map(state.crosswalk.map((row) => [row.territory_id, row]));
  const byRegion = groupBy(selectedRows, ["territory_id", "territory_name"]);
  const sectors = topSectorsByRegion(selectedRows);
  const valueByGeo = new Map();
  const tooltipByGeo = new Map();
  const regionIdByGeo = new Map();
  const districtZoom = state.filters.district && state.filters.district !== "__all__" && !(state.filters.regions || []).length;
  const zoomRegionIds = (state.filters.regions || []).length
    ? state.filters.regions
    : districtZoom
    ? byRegion.map((row) => row.territory_id)
    : [];
  const selectedGeoKeys = zoomRegionIds
    .map((id) => crosswalkById.get(id)?.geo_key)
    .filter(Boolean);
  byRegion.forEach((row) => {
    const match = crosswalkById.get(row.territory_id);
    if (!match || !match.geo_key) return;
    valueByGeo.set(match.geo_key, row.value_persons);
    regionIdByGeo.set(match.geo_key, row.territory_id);
    tooltipByGeo.set(match.geo_key, {
      region: row.territory_name,
      value: row.value_persons,
      topSectors: sectors.get(row.territory_id) || "нет положительных отраслей"
    });
  });
  byId("map-status").textContent = selectedGeoKeys.length
    ? districtZoom
      ? `Карта увеличена по федеральному округу: ${state.filters.district}.`
      : `Карта увеличена по выбранным регионам: ${selectedGeoKeys.length}.`
    : state.unmatched?.status === "ok"
    ? "Геослой подключен; сопоставлены все 85 модельных регионов."
    : "Геослой подключен; часть сопоставлений требует проверки.";
  renderSvgMap(valueByGeo, tooltipByGeo, selectedGeoKeys, regionIdByGeo);
}

function featureName(feature) {
  const props = feature.properties || {};
  return props.Name_full || props.name || props.NAME || props.Name || "";
}

function collectCoordinates(geojson) {
  const coords = [];
  const visit = (node) => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number" && typeof node[1] === "number") {
      coords.push([node[0], node[1]]);
      return;
    }
    node.forEach(visit);
  };
  (geojson.features || []).forEach((feature) => visit(feature.geometry?.coordinates));
  return coords;
}

function polygonRings(feature) {
  const geometry = feature.geometry || {};
  if (geometry.type === "Polygon") return [geometry.coordinates];
  if (geometry.type === "MultiPolygon") return geometry.coordinates;
  return [];
}

function lambertRussiaRaw([lon, lat]) {
  const toRad = Math.PI / 180;
  const phi1 = 49 * toRad;
  const phi2 = 77 * toRad;
  const phi0 = 60 * toRad;
  const lambda0 = 105 * toRad;
  let normalizedLon = Number(lon);
  if (normalizedLon < 0) normalizedLon += 360;
  const lambda = normalizedLon * toRad;
  const phi = Math.max(-88, Math.min(88, Number(lat))) * toRad;
  const n = Math.log(Math.cos(phi1) / Math.cos(phi2))
    / Math.log(Math.tan(Math.PI / 4 + phi2 / 2) / Math.tan(Math.PI / 4 + phi1 / 2));
  const f = Math.cos(phi1) * Math.pow(Math.tan(Math.PI / 4 + phi1 / 2), n) / n;
  const rho = f / Math.pow(Math.tan(Math.PI / 4 + phi / 2), n);
  const rho0 = f / Math.pow(Math.tan(Math.PI / 4 + phi0 / 2), n);
  const theta = n * (lambda - lambda0);
  return [rho * Math.sin(theta), rho0 - rho * Math.cos(theta)];
}

function renderSvgMap(valueByGeo, tooltipByGeo, selectedGeoKeys = [], regionIdByGeo = new Map()) {
  const container = byId("chart-map");
  const width = Math.max(640, container.clientWidth || 1120);
  const height = Math.max(300, container.clientHeight || 334);
  const legendWidth = width < 760 ? 104 : 132;
  const pad = { top: 18, right: legendWidth + 20, bottom: 26, left: 18 };
  const features = state.geojson.features || [];
  const selectedSet = selectedGeoKeys.length ? new Set(selectedGeoKeys) : null;
  const noModelDataSet = new Set(state.unmatched?.unmatched_geo_features || []);
  const projectionFeatures = selectedSet
    ? features.filter((feature) => selectedSet.has(featureName(feature)))
    : features;
  const coords = collectCoordinates({ features: projectionFeatures.length ? projectionFeatures : features });
  const projectedCoords = coords
    .map(lambertRussiaRaw)
    .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
  const xs = projectedCoords.map((coord) => coord[0]);
  const ys = projectedCoords.map((coord) => coord[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const availableWidth = width - pad.left - pad.right;
  const availableHeight = height - pad.top - pad.bottom;
  const scale = Math.min(availableWidth / (maxX - minX || 1), availableHeight / (maxY - minY || 1)) * 0.98;
  const projectedWidth = (maxX - minX) * scale;
  const projectedHeight = (maxY - minY) * scale;
  const offsetX = pad.left + (availableWidth - projectedWidth) / 2;
  const offsetY = pad.top + (availableHeight - projectedHeight) / 2;
  const project = (coord) => {
    const [x, y] = lambertRussiaRaw(coord);
    return [
      offsetX + (x - minX) * scale,
      offsetY + (maxY - y) * scale
    ];
  };
  const values = [...valueByGeo.values()].filter((value) => value > 0);
  const maxValue = Math.max(...values, 1);
  const pathParts = features.map((feature) => {
    const name = featureName(feature);
    const value = valueByGeo.get(name) || 0;
    const noModelData = noModelDataSet.has(name);
    const selectedClass = selectedSet?.has(name) ? " selected" : "";
    const noDataClass = noModelData ? " no-model-data" : "";
    const rings = polygonRings(feature);
    const d = rings.map((polygon) => polygon.map((ring) => {
      if (!ring.length) return "";
      const [first, ...rest] = ring;
      const [x0, y0] = project(first);
      return `M${x0.toFixed(2)},${y0.toFixed(2)} ${rest.map((coord) => {
        const [x, y] = project(coord);
        return `L${x.toFixed(2)},${y.toFixed(2)}`;
      }).join(" ")} Z`;
    }).join(" ")).join(" ");
    const tooltip = tooltipByGeo.get(name);
    const fill = noModelData ? "#a9b5c4" : colorForValue(value, maxValue);
    const dataTop = noModelData ? "нет модельных данных" : (tooltip?.topSectors || "нет данных");
    return `<path d="${d}" class="map-region${selectedClass}${noDataClass}" data-territory-id="${escapeHtml(regionIdByGeo.get(name) || "")}" data-region="${escapeHtml(tooltip?.region || name)}" data-value="${escapeHtml(fmt.format(value))}" data-top="${escapeHtml(dataTop)}" fill="${fill}" />`;
  }).join("");
  container.innerHTML = `
    <svg class="svg-map" viewBox="0 0 ${width} ${height}" role="img" aria-label="Картограмма субъектов Российской Федерации">
      <rect x="0" y="0" width="${width}" height="${height}" fill="#f8fafc" />
      <g>${pathParts}</g>
      ${mapLegend(width - legendWidth + 12, 42, 18, Math.min(220, height - 90), maxValue)}
    </svg>
    <div class="map-tooltip hidden" id="map-tooltip"></div>
  `;
  const tooltip = byId("map-tooltip");
  container.querySelectorAll(".map-region").forEach((path) => {
    path.addEventListener("mousemove", (event) => {
      tooltip.classList.remove("hidden");
      tooltip.innerHTML = `<strong>${path.dataset.region}</strong><br>Год: ${state.filters.year}<br>${path.dataset.value} человек<br>Топ-3 ОКВЭД: ${path.dataset.top}`;
      const rect = container.getBoundingClientRect();
      tooltip.style.left = `${Math.min(event.clientX - rect.left + 14, rect.width - 280)}px`;
      tooltip.style.top = `${Math.max(event.clientY - rect.top - 10, 12)}px`;
    });
    path.addEventListener("mouseleave", () => tooltip.classList.add("hidden"));
    path.addEventListener("click", (event) => {
      const territoryId = path.dataset.territoryId;
      if (!territoryId) return;
      state.selectedMapRegionId = territoryId;
      const inputs = Array.from(document.querySelectorAll("#filter-region-options input[type='checkbox']"));
      const input = inputs.find((item) => item.value === territoryId);
      if (!input) return;
      if (event.ctrlKey || event.metaKey || event.shiftKey) {
        input.checked = !input.checked;
      } else {
        inputs.forEach((item) => { item.checked = false; });
        input.checked = true;
      }
      updateRegionSummary();
      readFiltersAndRender();
    });
  });
}

function renderRegionPassport(selectedRows) {
  const target = byId("region-passport");
  if (!target) return;
  const selectedIds = state.filters.regions || [];
  const activeRegionId = state.selectedMapRegionId && selectedRows.some((row) => row.territory_id === state.selectedMapRegionId)
    ? state.selectedMapRegionId
    : selectedIds.length === 1
    ? selectedIds[0]
    : null;
  if (!activeRegionId) {
    const districtHint = state.filters.district && state.filters.district !== "__all__"
      ? "Карта приближена к округу. Выберите субъект на карте или в фильтре, чтобы открыть паспорт."
      : "Выберите субъект РФ на карте или в фильтре, чтобы открыть паспорт.";
    target.innerHTML = `<p>${escapeHtml(districtHint)}</p>`;
    return;
  }
  const sourceRows = selectedRows.filter((row) => row.territory_id === activeRegionId);
  if (!sourceRows.length) {
    target.innerHTML = "<p>Выберите регион на карте или в фильтре, чтобы открыть отраслевой паспорт.</p>";
    return;
  }
  const regionName = sourceRows[0]?.territory_name;
  const top = groupBy(sourceRows, ["activity_id", "okved_section", "activity_name"])
    .map((row) => {
      const rows = sourceRows.filter((item) => item.activity_id === row.activity_id);
      return {
        ...row,
        quota: sum(rows, "recommended_annual_quota_persons"),
        stock: sum(rows, "foreign_labor_stock_need_persons"),
        cumulative: sum(rows, "cumulative_recommended_quota_persons"),
        productivity: weightedAverage(rows, "productivity_growth_forecast_yearly"),
        reserve: sum(rows, "unemployment_reserve_sector_allocated_persons")
      };
    })
    .sort((a, b) => b.quota - a.quota)
    .slice(0, 5);
  target.innerHTML = `
    <strong>${escapeHtml(regionName || "Регион")}</strong>
    <div class="passport-list">
      ${top.map((row) => `<article>
        <span>${escapeHtml(row.okved_section)} — ${escapeHtml(row.activity_name)}</span>
        <b>${fmt.format(row.quota)}</b>
        <small>дефицит ${fmt.format(row.stock)} · накопленная ${fmt.format(row.cumulative)} · производительность ${formatPercentField(row.productivity)} · резерв ${fmt.format(row.reserve)}</small>
      </article>`).join("")}
    </div>
  `;
}

function colorForValue(value, maxValue) {
  if (!value) return "#edf3f9";
  const t = Math.max(0, Math.min(1, Math.sqrt(value / maxValue)));
  const stops = [
    [0, [219, 237, 255]],
    [0.45, [127, 186, 249]],
    [0.78, [11, 94, 215]],
    [1, [226, 59, 82]]
  ];
  let lower = stops[0];
  let upper = stops[stops.length - 1];
  for (let i = 1; i < stops.length; i += 1) {
    if (t <= stops[i][0]) {
      lower = stops[i - 1];
      upper = stops[i];
      break;
    }
  }
  const localT = (t - lower[0]) / (upper[0] - lower[0] || 1);
  const rgb = lower[1].map((channel, index) => Math.round(channel + (upper[1][index] - channel) * localT));
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

function mapLegend(x, y, width, height, maxValue) {
  const steps = 10;
  const rects = Array.from({ length: steps }, (_, index) => {
    const t = index / (steps - 1);
    const value = maxValue * t * t;
    const rectY = y + height - ((index + 1) * height / steps);
    return `<rect x="${x}" y="${rectY}" width="${width}" height="${height / steps + 0.5}" fill="${colorForValue(value, maxValue)}" />`;
  }).join("");
  const tickValues = [0, maxValue / 2, maxValue];
  const ticks = tickValues.map((value) => {
    const t = Math.sqrt(value / maxValue || 0);
    const tickY = y + height - t * height;
    return `<line x1="${x + width}" x2="${x + width + 6}" y1="${tickY}" y2="${tickY}" stroke="#475569" /><text x="${x + width + 10}" y="${tickY + 4}" font-size="12" fill="#1f2937">${fmtShort.format(value)}</text>`;
  }).join("");
  return `<g class="map-legend"><text x="${x}" y="${y - 16}" font-size="12" font-weight="700" fill="#1f2937">человек</text>${rects}<rect x="${x}" y="${y}" width="${width}" height="${height}" fill="none" stroke="#475569" />${ticks}</g>`;
}

function fallbackRegionList(rows) {
  const top = groupBy(rows, ["territory_name"])
    .sort((a, b) => b.value_persons - a.value_persons)
    .slice(0, 12);
  return `<strong>Табличный fallback карты</strong><ol>${top.map((row) => `<li>${escapeHtml(row.territory_name)} — ${fmt.format(row.value_persons)} человек</li>`).join("")}</ol>`;
}

function getCurrentTableRows() {
  const query = byId("table-search").value.trim().toLowerCase();
  let rows = state.tableMode === "forecast" ? [...state.tableRows] : [...state.factualTableRows];
  if (query) {
    rows = rows.filter((row) => [
      row.year,
      row.forecast_year,
      row.territory_name,
      row.federal_district_name,
      row.okved_section,
      row.activity_name
    ].some((value) => String(value || "").toLowerCase().includes(query)));
  }
  const sortState = state.tableMode === "forecast" ? state.sort : state.factualSort;
  rows.sort((a, b) => {
    const av = a[sortState.key];
    const bv = b[sortState.key];
    const numeric = typeof av === "number" || typeof bv === "number";
    const result = numeric
      ? toNumber(av) - toNumber(bv)
      : String(av || "").localeCompare(String(bv || ""), "ru");
    return sortState.dir === "asc" ? result : -result;
  });
  return rows;
}

function renderTable() {
  const rows = getCurrentTableRows();
  state.exportRows = rows;
  document.querySelectorAll("[data-table-mode]").forEach((button) => {
    const active = button.dataset.tableMode === state.tableMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const table = byId("detail-table");
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  const visibleRows = rows.slice(0, 300);
  if (state.tableMode === "forecast") {
    thead.innerHTML = `
      <tr>
        <th><button type="button" data-sort="territory_name">Регион</button></th>
        <th><button type="button" data-sort="federal_district_name">Округ</button></th>
        <th><button type="button" data-sort="okved_section">ОКВЭД</button></th>
        <th><button type="button" data-sort="activity_name">Отрасль</button></th>
        <th class="num"><button type="button" data-sort="recommended_annual_quota_persons">Рекомендуемая годовая квота</button></th>
        <th class="num"><button type="button" data-sort="foreign_labor_stock_need_persons">Дефицит на конец года</button></th>
        <th class="num"><button type="button" data-sort="labor_demand_required_persons">Требуемая занятость</button></th>
        <th class="num"><button type="button" data-sort="unemployment_reserve_sector_allocated_persons">Резерв безработных</button></th>
        <th class="num"><button type="button" data-sort="domestic_sector_supply_total_with_unemployment_reserve_persons">Внутренний ресурс с резервом</button></th>
        <th class="num"><button type="button" data-sort="employment_2024_persons">Занятость 2024</button></th>
        <th class="num"><button type="button" data-sort="productivity_growth_forecast_yearly">Прогноз производительности</button></th>
        <th class="num"><button type="button" data-sort="sector_share_in_region_2024">Доля отрасли 2024</button></th>
        <th class="num"><button type="button" data-sort="supply_allocation_share">Прогнозная доля</button></th>
      </tr>
    `;
    tbody.innerHTML = visibleRows.map((row) => `
      <tr>
        <td>${escapeHtml(row.territory_name)}</td>
        <td>${escapeHtml(row.federal_district_name)}</td>
        <td>${escapeHtml(row.okved_section)}</td>
        <td>${escapeHtml(row.activity_name)}</td>
        <td class="num">${fmt.format(row.recommended_annual_quota_persons || row.dashboard_value_persons)}</td>
        <td class="num">${fmt.format(row.foreign_labor_stock_need_persons)}</td>
        <td class="num">${row.labor_demand_required_persons ? fmt.format(row.labor_demand_required_persons) : "н/д"}</td>
        <td class="num">${fmt.format(row.unemployment_reserve_sector_allocated_persons)}</td>
        <td class="num">${row.domestic_sector_supply_total_with_unemployment_reserve_persons ? fmt.format(row.domestic_sector_supply_total_with_unemployment_reserve_persons) : "н/д"}</td>
        <td class="num">${row.employment_2024_persons ? fmt.format(row.employment_2024_persons) : "н/д"}</td>
        <td class="num">${formatPercentField(row.productivity_growth_forecast_yearly)}</td>
        <td class="num">${formatPercentField(row.sector_share_in_region_2024)}</td>
        <td class="num">${formatPercentField(row.supply_allocation_share)}</td>
      </tr>
    `).join("");
  } else {
    thead.innerHTML = `
      <tr>
        <th><button type="button" data-sort="year">Год</button></th>
        <th><button type="button" data-sort="territory_name">Регион</button></th>
        <th><button type="button" data-sort="federal_district_name">Округ</button></th>
        <th><button type="button" data-sort="okved_section">ОКВЭД</button></th>
        <th><button type="button" data-sort="activity_name">Отрасль</button></th>
        <th class="num"><button type="button" data-sort="employment_persons">Занятость</button></th>
        <th class="num"><button type="button" data-sort="vrp_constant_2016_mln_rub">ВРП 2016</button></th>
        <th class="num"><button type="button" data-sort="labour_productivity_constant_2016_thousand_rub_per_person">Производительность</button></th>
      </tr>
    `;
    tbody.innerHTML = visibleRows.map((row) => `
      <tr>
        <td>${fmt.format(row.year)}</td>
        <td>${escapeHtml(row.territory_name)}</td>
        <td>${escapeHtml(row.federal_district_name)}</td>
        <td>${escapeHtml(row.okved_section)}</td>
        <td>${escapeHtml(row.activity_name)}</td>
        <td class="num">${row.employment_persons ? fmt.format(row.employment_persons) : "н/д"}</td>
        <td class="num">${row.vrp_constant_2016_mln_rub ? fmtDecimal.format(row.vrp_constant_2016_mln_rub) : "н/д"}</td>
        <td class="num">${row.labour_productivity_constant_2016_thousand_rub_per_person ? fmtDecimal.format(row.labour_productivity_constant_2016_thousand_rub_per_person) : "н/д"}</td>
      </tr>
    `).join("");
  }
  const suffix = rows.length > visibleRows.length
    ? `; показаны первые ${fmt.format(visibleRows.length)}, CSV содержит все отфильтрованные и отсортированные строки`
    : "";
  const base = state.tableMode === "forecast"
    ? `${fmt.format(rows.length)} строк из ${fmt.format(state.tableRows.length)} за ${state.filters.year} год`
    : `${fmt.format(rows.length)} строк из ${fmt.format(state.factualTableRows.length)} за 2017-2024`;
  byId("table-count").textContent = `${base}${suffix}`;
}

function downloadCsv() {
  const rows = state.exportRows.length ? state.exportRows : getCurrentTableRows();
  const headers = state.tableMode === "forecast"
    ? [
        "forecast_year",
        "territory_id",
        "territory_name",
        "federal_district_name",
        "activity_id",
        "okved_section",
        "activity_name",
        "dashboard_value_persons",
        "recommended_annual_quota_persons",
        "annual_new_stock_delta_persons",
        "annual_replacement_flow_persons",
        "cumulative_recommended_quota_persons",
        "labor_demand_required_persons",
        "domestic_sector_supply_allocated_persons",
        "employment_2024_persons",
        "target_real_vrp_growth",
        "productivity_growth_forecast",
        "productivity_growth_forecast_yearly",
        "productivity_growth_forecast_static",
        "productivity_trajectory_convergence_weight",
        "sector_share_in_region_2024",
        "supply_allocation_share",
        "foreign_labor_stock_need_persons",
        "annual_foreign_labor_quota_persons",
        "cumulative_foreign_labor_quota_persons",
        "unemployment_rate_ilo_15plus_pct",
        "unemployment_reserve_sector_allocated_persons",
        "domestic_sector_supply_total_with_unemployment_reserve_persons",
        "population_scenario",
        "working_age_definition",
        "productivity_scenario",
        "supply_allocation_scenario"
      ]
    : [
        "year",
        "territory_id",
        "territory_name",
        "federal_district_name",
        "activity_id",
        "okved_section",
        "activity_name",
        "employment_persons",
        "vrp_constant_2016_mln_rub",
        "labour_productivity_constant_2016_thousand_rub_per_person",
        "official_productivity_index_hybrid_pct",
        "official_productivity_coverage_scope",
        "data_complete_constant_vrp_employment",
        "data_complete_all_three",
        "recommended_for_model_constant"
      ];
  const csv = [
    headers.join(","),
    ...rows.map((row) => headers.map((key) => csvCell(row[key])).join(","))
  ].join("\n");
  const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = state.tableMode === "forecast"
    ? `dashboard_forecast_detail_${state.filters.year}.csv`
    : "dashboard_factual_history_2017_2024.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  const text = String(value ?? "");
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, "\"\"")}"`;
  return text;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function render() {
  ensurePlotly();
  const selectedRows = withSelectedMetric(applyFilters(state.rows));
  const horizonRows = withSelectedMetric(applyFilters(state.rows, { ignoreYear: true }));
  const sectorRows = withSelectedMetric(applyFilters(state.rows, { ignoreSector: true }));
  const factualRows = applyFactualFilters(state.factualRows);
  state.tableRows = selectedRows;
  state.factualTableRows = factualRows;
  renderKpis(selectedRows, horizonRows);
  renderFactualBase(factualRows);
  renderEconomicLink(factualRows, horizonRows);
  renderSectorQuickLinks(sectorRows);
  renderQuotaTrend(horizonRows);
  renderResourceBalance(horizonRows);
  renderProductivityAndShares(horizonRows, sectorRows);
  renderRanking("chart-region", groupBy(selectedRows, ["territory_id", "territory_name"]), "territory_name", 220);
  renderRanking("chart-sector", groupBy(selectedRows, ["activity_id", "okved_section", "activity_name"]).map((row) => ({
    ...row,
    sector_label: `${row.okved_section} — ${row.activity_name}`
  })), "sector_label", 250);
  renderAtlas(selectedRows);
  renderMap(selectedRows);
  renderRegionPassport(selectedRows);
  renderTable();
}

async function init() {
  try {
    state.meta = await fetchJson(DATA_PATHS.metadata);
    updateHeader();
    const [csvText, factualText, factualSummaryYear, geojson, crosswalk, unmatched] = await Promise.all([
      fetchText(DATA_PATHS.forecast),
      fetchText(DATA_PATHS.factualHistory).catch(() => ""),
      fetchJson(DATA_PATHS.factualSummaryYear, true).catch(() => []),
      fetchJson(DATA_PATHS.geojson, true).catch(() => null),
      fetchJson(DATA_PATHS.crosswalk, true).catch(() => []),
      fetchJson(DATA_PATHS.unmatched, true).catch(() => null)
    ]);
    state.geojson = geojson;
    state.crosswalk = Array.isArray(crosswalk) ? crosswalk : [];
    state.unmatched = unmatched;
    state.rows = prepareRows(parseCsv(csvText));
    state.factualRows = factualText ? prepareFactualRows(parseCsv(factualText)) : [];
    state.factualSummaryYear = Array.isArray(factualSummaryYear) ? factualSummaryYear : [];
    setupFilters();
    render();
    window.addEventListener("resize", debounce(render, 250));
  } catch (error) {
    console.error(error);
    document.body.insertAdjacentHTML("beforeend", `<div class="fatal-error">${escapeHtml(error.message)}</div>`);
  }
}

function debounce(fn, delay) {
  let timer = 0;
  return () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(fn, delay);
  };
}

document.addEventListener("DOMContentLoaded", init);
