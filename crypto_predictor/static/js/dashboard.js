import { createPredictionChart } from "./chart.js";

function getActiveTimezone() {
  return document.body?.dataset?.timezone || "UTC";
}

function formatUtcToZone(utcText, timezone) {
  if (!utcText) {
    return "-";
  }

  const date = new Date(utcText);
  if (Number.isNaN(date.getTime())) {
    return utcText;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
    .format(date)
    .replace(/\//g, "-");
}

function renderUtcNodes() {
  const timezone = getActiveTimezone();
  document.querySelectorAll(".js-utc-time[data-utc]").forEach((node) => {
    const utcText = node.getAttribute("data-utc") || "";
    node.textContent = formatUtcToZone(utcText, timezone);
  });
}

renderUtcNodes();

const refreshRaw = document.body?.dataset?.autoRefreshSeconds ?? "0";
const refreshSeconds = Number.parseInt(refreshRaw, 10);
const fragmentTargets = {
  stats: "stats-fragment",
  predictions: "predictions-fragment",
  orders: "orders-fragment",
  auto: "auto-fragment",
  advice: "advice-fragment",
};
let autoFollowupTimerId = null;

function isAutoFormBeingEdited() {
  const form = document.querySelector(".auto-form-wrap");
  if (!form) {
    return false;
  }
  if (form.dataset.dirty === "1") {
    return true;
  }
  return document.activeElement ? form.contains(document.activeElement) : false;
}

async function refreshDashboardFragments({ forceAuto = false } = {}) {
  const response = await fetch(`/api/dashboard-fragments${window.location.search}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Dashboard refresh failed: ${response.status}`);
  }

  const fragments = await response.json();
  Object.entries(fragmentTargets).forEach(([key, elementId]) => {
    if (key === "auto" && !forceAuto && isAutoFormBeingEdited()) {
      return;
    }
    const target = document.getElementById(elementId);
    if (target && typeof fragments[key] === "string") {
      target.innerHTML = fragments[key];
    }
  });

  renderUtcNodes();
  bindTableTooltips();
  bindAutoSymbolControls();
  bindAutoToggleForms();
  bindPaginationLinks();
}

async function navigateDashboardPage(href, { forceAuto = false } = {}) {
  const url = new URL(href, window.location.origin);
  window.history.pushState({}, "", `${url.pathname}${url.search}`);
  await refreshDashboardFragments({ forceAuto });
}

function scheduleAutoFollowupRefreshes() {
  if (autoFollowupTimerId !== null) {
    window.clearInterval(autoFollowupTimerId);
  }

  let remainingRefreshes = 30;
  autoFollowupTimerId = window.setInterval(() => {
    if (document.hidden) {
      return;
    }

    refreshDashboardFragments().catch((error) => {
      console.warn(error);
    });

    remainingRefreshes -= 1;
    if (remainingRefreshes <= 0 && autoFollowupTimerId !== null) {
      window.clearInterval(autoFollowupTimerId);
      autoFollowupTimerId = null;
    }
  }, 2000);
}

if (Number.isFinite(refreshSeconds) && refreshSeconds > 0) {
  let timerId = null;

  const schedule = () => {
    if (timerId !== null) {
      window.clearTimeout(timerId);
    }
    timerId = window.setTimeout(() => {
      if (!document.hidden) {
        refreshDashboardFragments()
          .catch((error) => {
            console.warn(error);
          })
          .finally(schedule);
        return;
      }
      schedule();
    }, refreshSeconds * 1000);
  };

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      schedule();
    }
  });

  schedule();
}

/* Floating header tooltips */
let activeTooltip = null;

document.querySelectorAll(".th-tip").forEach((tipEl) => {
  tipEl.addEventListener("mouseover", () => {
    // Create a shared floating tooltip element.
    if (!activeTooltip) {
      activeTooltip = document.createElement("div");
      activeTooltip.className = "js-tooltip";
      document.body.appendChild(activeTooltip);
    }

    // Set tooltip text.
    const tipText = tipEl.getAttribute("data-tip") || "";
    activeTooltip.textContent = tipText;

    // Position tooltip above the header icon.
    const rect = tipEl.getBoundingClientRect();
    const tooltipHeight = 60;
    const tooltipLeft = rect.left + rect.width / 2 - 120;
    const tooltipTop = rect.top - tooltipHeight - 8;

    activeTooltip.style.left = tooltipLeft + "px";
    activeTooltip.style.top = tooltipTop + "px";
    activeTooltip.classList.add("show");
  });

  tipEl.addEventListener("mouseout", () => {
    if (activeTooltip) {
      activeTooltip.classList.remove("show");
    }
  });
});

/* Tab switching */
const ACTIVE_TAB_KEY = "dashboard_active_tab";
let predictionChartController = null;

function ensurePredictionChart() {
  if (predictionChartController) {
    return;
  }

  const chartEl = document.getElementById("predictionChart");
  const chartSymbol = document.getElementById("chartSymbol");
  if (!chartEl || !chartSymbol) {
    return;
  }

  try {
    if (!window.echarts) {
      console.warn("ECharts is not loaded; chart panel will be skipped.");
      return;
    }
    predictionChartController = createPredictionChart(chartEl, chartSymbol);
  } catch (error) {
    console.warn("Failed to initialize prediction chart", error);
  }
}

function activateTab(tabId) {
  if (!tabId || !document.getElementById(tabId)) {
    return;
  }

  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-pane").forEach((pane) => {
    pane.classList.toggle("active", pane.id === tabId);
  });

  if (tabId === "chart-tab") {
    ensurePredictionChart();
    setTimeout(() => window.dispatchEvent(new Event("resize")), 100);
  }

  sessionStorage.setItem(ACTIVE_TAB_KEY, tabId);
}

function bindTabs() {
  document.querySelectorAll(".tab-btn").forEach((button) => {
    if (button.dataset.tabBound === "1") {
      return;
    }
    button.dataset.tabBound = "1";
    button.type = "button";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      activateTab(button.dataset.tab);
    });
  });

  const savedTab = sessionStorage.getItem(ACTIVE_TAB_KEY);
  if (savedTab && document.getElementById(savedTab)) {
    activateTab(savedTab);
  }
}

bindTabs();
function bindTableTooltips() {
  document.querySelectorAll(".th-tip").forEach((tipEl) => {
    if (tipEl.dataset.tooltipBound === "1") {
      return;
    }
    tipEl.dataset.tooltipBound = "1";

    tipEl.addEventListener("mouseover", () => {
      if (!activeTooltip) {
        activeTooltip = document.createElement("div");
        activeTooltip.className = "js-tooltip";
        document.body.appendChild(activeTooltip);
      }

      const tipText = tipEl.getAttribute("data-tip") || "";
      activeTooltip.textContent = tipText;

      const rect = tipEl.getBoundingClientRect();
      const tooltipHeight = 60;
      const tooltipLeft = rect.left + rect.width / 2 - 120;
      const tooltipTop = rect.top - tooltipHeight - 8;

      activeTooltip.style.left = tooltipLeft + "px";
      activeTooltip.style.top = tooltipTop + "px";
      activeTooltip.classList.add("show");
    });

    tipEl.addEventListener("mouseout", () => {
      if (activeTooltip) {
        activeTooltip.classList.remove("show");
      }
    });
  });
}

function handleAutoSymbolChange(sel) {
  const label = document.getElementById("autoSymbolsCustomLabel");
  if (label) label.style.display = sel.value === "custom" ? "" : "none";
}

function bindAutoSymbolControls() {
  const select = document.getElementById("autoSymbolsPreset");
  if (!select || select.dataset.autoSymbolBound === "1") {
    return;
  }
  select.dataset.autoSymbolBound = "1";
  select.addEventListener("change", () => handleAutoSymbolChange(select));
}

window.handleAutoSymbolChange = handleAutoSymbolChange;
bindAutoSymbolControls();

function bindAutoToggleForms() {
  document.querySelectorAll(".auto-form-wrap").forEach((form) => {
    if (form.dataset.autoSubmitBound === "1") {
      return;
    }
    form.dataset.autoSubmitBound = "1";
    form.addEventListener("input", () => {
      form.dataset.dirty = "1";
    });
    form.addEventListener("change", () => {
      form.dataset.dirty = "1";
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const submitButton = form.querySelector('button[type="submit"]');
      if (submitButton) {
        submitButton.disabled = true;
      }

      try {
        await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-Requested-With": "fetch" },
        });
        form.dataset.dirty = "0";
        await refreshDashboardFragments({ forceAuto: true });
        scheduleAutoFollowupRefreshes();
      } catch (error) {
        console.warn(error);
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
        }
      }
    });
  });
}

bindAutoToggleForms();

function bindPaginationLinks() {
  document.querySelectorAll(".pager-link[href]").forEach((link) => {
    if (link.dataset.paginationBound === "1") {
      return;
    }
    link.dataset.paginationBound = "1";
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      try {
        await navigateDashboardPage(link.href, {
          forceAuto: link.dataset.forceAuto === "1",
        });
      } catch (error) {
        console.warn(error);
      }
    });
  });
}

window.addEventListener("popstate", () => {
  refreshDashboardFragments({ forceAuto: true }).catch((error) => {
    console.warn(error);
  });
});

bindPaginationLinks();

