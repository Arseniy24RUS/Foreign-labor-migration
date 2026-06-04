const fs = require("node:fs");
const path = require("node:path");
const { expect, test } = require("@playwright/test");

const screenshotDir = path.join(process.cwd(), "qa-screenshots", "Foreign-labor-migration");

function ensureScreenshotDir() {
  fs.mkdirSync(screenshotDir, { recursive: true });
}

async function openDashboard(browser, options) {
  const consoleErrors = [];
  const context = await browser.newContext(options);
  const page = await context.newPage();

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => {
    consoleErrors.push(error.message);
  });

  await page.goto("/");
  await expect(page.locator(".fatal-error")).toHaveCount(0);
  await expect(page.locator("h1")).toBeVisible();
  await page.waitForFunction(() => {
    return window.AppI18n
      && document.querySelector("#kpi-year-total")?.textContent?.trim()
      && document.querySelector("#kpi-year-total").textContent.trim() !== "-"
      && document.querySelector("#chart-year")?.classList.contains("js-plotly-plot")
      && document.querySelector("#chart-map svg");
  });

  return { context, page, consoleErrors };
}

async function expectRussianUi(page) {
  await expect(page.locator("html")).toHaveAttribute("lang", "ru");
  await expect(page.getByRole("heading", { name: "Потребность в трудовых ресурсах по отраслям и регионам России" })).toBeVisible();
  await expect(page.getByTestId("language-toggle")).toHaveText("EN");
  await expect(page.getByRole("link", { name: /Обзор/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Фильтры" })).toBeVisible();
  await expect(page.locator("#filter-district option").first()).toHaveText("Все округа");
  await expect(page.locator("#filter-region-options")).toContainText("Алтайский край");
  await expect(page.locator("#detail-table thead")).toContainText("Рекомендуемая годовая квота");
  await expect(page.locator("#chart-map")).toContainText("человек");
}

async function expectEnglishUi(page) {
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: "Labor Resource Demand by Industry and Region in Russia" })).toBeVisible();
  await expect(page.getByTestId("language-toggle")).toHaveText("RU");
  await expect(page.getByRole("link", { name: /Overview/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Filters" })).toBeVisible();
  await expect(page.locator("#filter-district option").first()).toHaveText("All districts");
  await expect(page.locator("#filter-region-options")).toContainText("Altai Krai");
  await expect(page.locator("#detail-table thead")).toContainText("Recommended annual quota");
  await expect(page.locator("#chart-map")).toContainText("persons");
}

test("ru-RU default loads Russian and toggles to English on desktop", async ({ browser }) => {
  ensureScreenshotDir();
  const { context, page, consoleErrors } = await openDashboard(browser, {
    locale: "ru-RU",
    viewport: { width: 1440, height: 1100 }
  });

  await expectRussianUi(page);
  await page.screenshot({ path: path.join(screenshotDir, "desktop-ru.png") });

  await page.getByTestId("language-toggle").click();
  await expectEnglishUi(page);
  await page.screenshot({ path: path.join(screenshotDir, "desktop-en.png") });

  expect(consoleErrors).toEqual([]);
  await context.close();
});

test("en-US default loads English and toggles to Russian on mobile", async ({ browser }) => {
  ensureScreenshotDir();
  const { context, page, consoleErrors } = await openDashboard(browser, {
    isMobile: true,
    locale: "en-US",
    viewport: { width: 390, height: 844 }
  });

  await expectEnglishUi(page);
  await page.screenshot({ path: path.join(screenshotDir, "mobile-en.png") });

  await page.getByTestId("language-toggle").click();
  await expectRussianUi(page);
  await page.screenshot({ path: path.join(screenshotDir, "mobile-ru.png") });

  expect(consoleErrors).toEqual([]);
  await context.close();
});
