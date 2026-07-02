(function () {
  const SUPPORTED = new Set(["en", "ru"]);
  const STORAGE_KEY = "lang";
  const state = {
    language: resolveInitialLanguage(),
    dictionary: {}
  };

  function normalizeLanguage(value) {
    const language = String(value || "").trim().toLowerCase().split("-")[0];
    return SUPPORTED.has(language) ? language : "";
  }

  function resolveInitialLanguage() {
    try {
      const stored = normalizeLanguage(window.localStorage?.getItem(STORAGE_KEY));
      if (stored) return stored;
    } catch (_) {
      // localStorage can be unavailable in hardened browser contexts.
    }

    const browserLanguages = [
      ...(Array.isArray(navigator.languages) ? navigator.languages : []),
      navigator.language || ""
    ].join(" ").toLowerCase();
    return browserLanguages.includes("ru") ? "ru" : "en";
  }

  function dictionaryValue(key) {
    if (Object.prototype.hasOwnProperty.call(state.dictionary, key)) {
      return state.dictionary[key];
    }
    return String(key).split(".").reduce((value, part) => {
      if (value && Object.prototype.hasOwnProperty.call(value, part)) return value[part];
      return undefined;
    }, state.dictionary);
  }

  function interpolate(value, params = {}) {
    return String(value).replace(/\{([a-zA-Z0-9_]+)\}/g, (match, name) => {
      return Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match;
    });
  }

  function t(key, params = {}, fallback = "") {
    const value = dictionaryValue(key);
    if (typeof value === "string" || typeof value === "number") {
      return interpolate(value, params);
    }
    return fallback || key;
  }

  function apply(root = document) {
    if (!root) return;
    document.documentElement.lang = state.language;
    document.title = t("app.title", {}, document.title);

    root.querySelectorAll?.("[data-i18n]").forEach((node) => {
      node.textContent = t(node.dataset.i18n, {}, node.textContent);
    });
    root.querySelectorAll?.("[data-i18n-html]").forEach((node) => {
      node.innerHTML = t(node.dataset.i18nHtml, {}, node.innerHTML);
    });
    [
      ["data-i18n-aria-label", "aria-label"],
      ["data-i18n-title", "title"],
      ["data-i18n-alt", "alt"],
      ["data-i18n-placeholder", "placeholder"]
    ].forEach(([dataName, attribute]) => {
      root.querySelectorAll?.(`[${dataName}]`).forEach((node) => {
        const key = node.getAttribute(dataName);
        node.setAttribute(attribute, t(key, {}, node.getAttribute(attribute) || ""));
      });
    });

    const toggle = document.querySelector("[data-testid='language-toggle']");
    if (toggle) {
      toggle.textContent = state.language === "ru" ? "EN" : "RU";
      toggle.setAttribute("aria-label", t("language.toggleLabel"));
      toggle.setAttribute("title", t("language.toggleTitle"));
    }
  }

  async function loadLanguage(language) {
    const normalized = normalizeLanguage(language) || "en";
    const response = await fetch(`locales/${normalized}.json`);
    if (!response.ok) throw new Error(`Locale not found: ${normalized}`);
    state.dictionary = await response.json();
    state.language = normalized;
    try {
      window.localStorage?.setItem(STORAGE_KEY, normalized);
    } catch (_) {
      // Ignore storage failures; the current session still has the selected language.
    }
    apply();
    window.dispatchEvent(new CustomEvent("app:i18n", { detail: { language: normalized } }));
    return normalized;
  }

  async function setLanguage(language) {
    const normalized = normalizeLanguage(language);
    if (!normalized) return state.language;
    if (normalized === state.language && Object.keys(state.dictionary).length) {
      apply();
      return state.language;
    }
    return loadLanguage(normalized);
  }

  function getLanguage() {
    return state.language;
  }

  function toggleLanguage() {
    return setLanguage(state.language === "ru" ? "en" : "ru");
  }

  function setupToggle() {
    document.querySelector("[data-testid='language-toggle']")?.addEventListener("click", () => {
      toggleLanguage();
    });
    apply();
  }

  const ready = loadLanguage(state.language).catch(() => {
    if (state.language !== "en") return loadLanguage("en");
    state.dictionary = {};
    return "en";
  });

  window.AppI18n = {
    t,
    getLanguage,
    setLanguage,
    toggleLanguage,
    apply,
    ready
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => ready.then(setupToggle), { once: true });
  } else {
    ready.then(setupToggle);
  }
})();

(function () {
  const TREND_TEXT = {
    ru: {
      heading: "Рекомендуемая квота по годам",
      description: "Годовая рекомендуемая квота внешней рабочей силы по выбранным регионам и отраслям."
    },
    en: {
      heading: "Recommended quota by year",
      description: "Annual recommended quota for external labor by selected regions and industries."
    }
  };

  const METHOD_TEXT_RU = {
    logic: "<strong>Выпуск<sub>регион, отрасль, год</sub> = занятость<sub>регион, отрасль, год</sub> × производительность труда<sub>регион, отрасль, год</sub></strong>. Выпуск рассчитывается как произведение численности занятых и производительности труда в соответствующей регионально-отраслевой ячейке.",
    migration: "<strong>Миграционная потребность = максимум(0; требуемая занятость − внутренний трудовой ресурс)</strong>. Если внутреннего трудового ресурса недостаточно для достижения целевого выпуска, положительная разница интерпретируется как потребность во внешней рабочей силе.",
    noMig: "<strong>Базовая численность населения = сценарий без миграции.</strong> Такой сценарий отделяет внутренний демографический ресурс от миграционного компонента, чтобы не учитывать миграцию дважды.",
    limits: "Оценка не является автоматической квотой. Для перехода к разрешениям нужна матрица <strong>ОКВЭД × профессия × квалификация</strong> и отдельная нормативная процедура.",
    horizon: "Макроэкономический ориентир роста взят из OECD Economic Outlook 117 Long-Term Model, сценарий BAU1. Горизонт прогноза — до 2050 года; техническое продление IMF 3,2% после 2027 года не используется."
  };

  function language() {
    return window.AppI18n?.getLanguage?.() === "ru" ? "ru" : "en";
  }

  function setText(selector, text) {
    const node = document.querySelector(selector);
    if (node) node.textContent = text;
  }

  function setHtml(selector, html) {
    const node = document.querySelector(selector);
    if (node) node.innerHTML = html;
  }

  function hideKpiCards() {
    ["kpi-horizon-total", "kpi-positive-share"].forEach((id) => {
      const card = document.getElementById(id)?.closest(".kpi-card");
      if (!card) return;
      card.hidden = true;
      card.setAttribute("aria-hidden", "true");
    });
  }

  function removeAtlasMetricButtons() {
    document.querySelectorAll(".metric-toggle").forEach((node) => {
      node.remove();
    });
  }

  function patchTexts() {
    const currentLanguage = language();
    const trend = TREND_TEXT[currentLanguage] || TREND_TEXT.en;
    setText('[data-i18n="trend.heading"]', trend.heading);
    setText('[data-i18n="trend.description"]', trend.description);

    if (currentLanguage === "ru") {
      setHtml('[data-i18n-html="method.logicText"]', METHOD_TEXT_RU.logic);
      setHtml('[data-i18n-html="method.migrationText"]', METHOD_TEXT_RU.migration);
      setHtml('[data-i18n-html="method.noMigText"]', METHOD_TEXT_RU.noMig);
      setHtml('[data-i18n-html="method.limitsText"]', METHOD_TEXT_RU.limits);
      setText('[data-i18n="method.horizonText"]', METHOD_TEXT_RU.horizon);
    }

    hideKpiCards();
    removeAtlasMetricButtons();
  }

  function installQuotaTrendOverride() {
    if (typeof renderQuotaTrend !== "function" || typeof groupBy !== "function" || typeof chartLayout !== "function") {
      return false;
    }

    renderQuotaTrend = function (horizonRows) {
      const annualQuotaData = groupBy(horizonRows, ["forecast_year"], "recommended_annual_quota_persons")
        .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year));
      const traces = [{
        x: annualQuotaData.map((row) => row.forecast_year),
        y: annualQuotaData.map((row) => row.value_persons),
        type: "bar",
        name: t("metric.recommendedAnnualQuota", {}, "Рекомендуемая годовая квота"),
        marker: { color: "#0B5ED7", opacity: 0.82 },
        hovertemplate: t("chart.quota.annualHover", {}, "Год %{x}<br>Рекомендуемая квота: %{y:,.0f} человек<extra></extra>")
      }];

      Plotly.react("chart-year", traces, chartLayout("", {
        xaxis: { title: t("chart.common.year", {}, "Год"), dtick: window.innerWidth < 720 ? 5 : 2, fixedrange: true },
        yaxis: { title: t("chart.quota.annualAxis", {}, "Рекомендуемая квота"), rangemode: "tozero", fixedrange: true },
        showlegend: false,
        shapes: controlYearShapes(),
        annotations: controlYearAnnotations(),
        margin: { t: 40, r: 14, b: 40, l: 64 },
        bargap: 0.18
      }), plotConfig());
    };
    return true;
  }

  function refreshAlreadyRenderedChart() {
    const chart = document.getElementById("chart-year");
    if (chart?.data?.length > 1 && typeof render === "function") {
      try {
        render();
      } catch (_) {
        // Rendering may be unavailable before data initialization.
      }
    }
  }

  function install() {
    patchTexts();
    if (installQuotaTrendOverride()) refreshAlreadyRenderedChart();

    window.addEventListener("app:i18n", () => {
      window.setTimeout(() => {
        patchTexts();
        if (installQuotaTrendOverride()) refreshAlreadyRenderedChart();
      }, 0);
    });

    let attempts = 0;
    const timer = window.setInterval(() => {
      patchTexts();
      const installed = installQuotaTrendOverride();
      if (installed) refreshAlreadyRenderedChart();
      attempts += 1;
      if (installed || attempts > 20) window.clearInterval(timer);
    }, 50);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => window.setTimeout(install, 0), { once: true });
  } else {
    window.setTimeout(install, 0);
  }
})();
