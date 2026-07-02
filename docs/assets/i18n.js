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
