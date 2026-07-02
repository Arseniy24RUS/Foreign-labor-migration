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

  function currentLanguage() {
    return window.AppI18n?.getLanguage?.() === "ru" ? "ru" : "en";
  }

  function translate(key, fallback) {
    return window.t?.(key, {}, fallback) || window.AppI18n?.t?.(key, {}, fallback) || fallback;
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
      card.style.display = "none";
    });
  }

  function removeAtlasMetricButtons() {
    document.querySelectorAll(".metric-toggle").forEach((node) => node.remove());
  }

  function patchTrendTexts() {
    const trend = TREND_TEXT[currentLanguage()] || TREND_TEXT.en;
    setText("#trend-heading", trend.heading);
    setText(".trend-panel .section-heading p", trend.description);
  }

  function patchMethodologyTexts() {
    if (currentLanguage() !== "ru") return;
    setHtml('[data-i18n-html="method.logicText"]', METHOD_TEXT_RU.logic);
    setHtml('[data-i18n-html="method.migrationText"]', METHOD_TEXT_RU.migration);
    setHtml('[data-i18n-html="method.noMigText"]', METHOD_TEXT_RU.noMig);
    setHtml('[data-i18n-html="method.limitsText"]', METHOD_TEXT_RU.limits);
    setText('[data-i18n="method.horizonText"]', METHOD_TEXT_RU.horizon);
  }

  function patchTexts() {
    patchTrendTexts();
    patchMethodologyTexts();
  }

  function installQuotaTrendOverride() {
    if (
      typeof window.Plotly !== "object" ||
      typeof window.groupBy !== "function" ||
      typeof window.chartLayout !== "function" ||
      typeof window.plotConfig !== "function"
    ) {
      return false;
    }

    window.renderQuotaTrend = function renderQuotaTrendAnnualOnly(horizonRows) {
      const annualQuotaData = window.groupBy(horizonRows, ["forecast_year"], "recommended_annual_quota_persons")
        .sort((a, b) => Number(a.forecast_year) - Number(b.forecast_year));

      const traces = [{
        x: annualQuotaData.map((row) => row.forecast_year),
        y: annualQuotaData.map((row) => row.value_persons),
        type: "bar",
        name: translate("metric.recommendedAnnualQuota", "Рекомендуемая годовая квота"),
        marker: { color: "#0B5ED7", opacity: 0.82 },
        hovertemplate: translate("chart.quota.annualHover", "Год %{x}<br>Рекомендуемая квота: %{y:,.0f} человек<extra></extra>")
      }];

      window.Plotly.react("chart-year", traces, window.chartLayout("", {
        xaxis: { title: translate("chart.common.year", "Год"), dtick: window.innerWidth < 720 ? 5 : 2, fixedrange: true },
        yaxis: { title: translate("chart.quota.annualAxis", "Рекомендуемая квота"), rangemode: "tozero", fixedrange: true },
        showlegend: false,
        shapes: typeof window.controlYearShapes === "function" ? window.controlYearShapes() : [],
        annotations: typeof window.controlYearAnnotations === "function" ? window.controlYearAnnotations() : [],
        margin: { t: 40, r: 14, b: 40, l: 64 },
        bargap: 0.18
      }), window.plotConfig());
    };

    return true;
  }

  function refreshDashboard() {
    hideKpiCards();
    removeAtlasMetricButtons();
    patchTexts();
    installQuotaTrendOverride();
    try {
      if (typeof window.render === "function") window.render();
    } catch (_) {
      // Data may still be loading; scheduled retries below will apply the change after initialization.
    }
  }

  function install() {
    refreshDashboard();
    window.addEventListener("app:i18n", () => window.setTimeout(refreshDashboard, 0));

    let attempts = 0;
    const timer = window.setInterval(() => {
      refreshDashboard();
      attempts += 1;
      if (attempts >= 30) window.clearInterval(timer);
    }, 200);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install, { once: true });
  } else {
    install();
  }
})();
