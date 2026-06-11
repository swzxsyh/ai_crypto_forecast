import { fetchChartData } from "./api.js";

const chartTranslations = {
  zh: {
    entry: "入场价",
    target: "目标价",
    actual: "实际结果价",
    profit: "预计盈利",
    loss: "预计亏损",
    price: "价格",
    pnl: "盈亏 USDT",
  },
  en: {
    entry: "Entry Price",
    target: "Target Price",
    actual: "Actual Result",
    profit: "Expected Profit",
    loss: "Expected Loss",
    price: "Price",
    pnl: "P/L USDT",
  },
};

function getActiveTimezone() {
  return document.body?.dataset?.timezone || "UTC";
}

function chartText(key) {
  const language = document.body?.dataset?.language || "zh";
  return chartTranslations[language]?.[key] || chartTranslations.zh[key] || key;
}

function formatUtcLabel(utcText) {
  const timezone = getActiveTimezone();
  const date = new Date(utcText);
  if (Number.isNaN(date.getTime())) {
    return utcText;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: timezone,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
    .format(date)
    .replace(/\//g, "-");
}

export function createPredictionChart(chartEl, symbolSelect) {
  const chart = echarts.init(chartEl);
  const customInput = document.getElementById("chartSymbolCustom");
  const startInput = document.getElementById("chartStartDate");
  const endInput = document.getElementById("chartEndDate");

  async function load() {
    let symbol = symbolSelect.value;
    if (symbol === "custom" && customInput) {
      symbol = customInput.value.trim();
    }

    const payload = await fetchChartData({
      symbol: symbol || "",
      startUtc: dateInputToUtcIso(startInput?.value || "", getActiveTimezone(), 0),
      endUtc: dateInputToUtcIso(endInput?.value || "", getActiveTimezone(), 1),
    });
    const points = payload.points || [];
    chart.setOption(buildChartOption(points), true);
  }

  symbolSelect.addEventListener("change", load);

  if (customInput) {
    customInput.addEventListener("change", () => {
      if (customInput.value.trim()) {
        load();
      }
    });
    customInput.addEventListener("keypress", (event) => {
      if (event.key === "Enter") {
        load();
      }
    });
  }

  [startInput, endInput].forEach((input) => {
    if (input) {
      input.addEventListener("change", load);
    }
  });

  window.addEventListener("resize", () => chart.resize());
  load();

  return { chart, load };
}

function dateInputToUtcIso(dateText, timezone, addDays) {
  if (!dateText) {
    return "";
  }

  const [year, month, day] = dateText.split("-").map((part) => Number.parseInt(part, 10));
  if (!year || !month || !day) {
    return "";
  }

  const utcDate = zonedDateTimeToUtc(year, month, day + addDays, 0, 0, 0, timezone);
  return utcDate.toISOString();
}

function zonedDateTimeToUtc(year, month, day, hour, minute, second, timezone) {
  const utcGuess = Date.UTC(year, month - 1, day, hour, minute, second);
  let utcDate = new Date(utcGuess);
  for (let i = 0; i < 2; i += 1) {
    const offset = getTimezoneOffsetMs(utcDate, timezone);
    utcDate = new Date(utcGuess - offset);
  }
  return utcDate;
}

function getTimezoneOffsetMs(date, timezone) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    hourCycle: "h23",
  }).formatToParts(date);

  const values = Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
  const asUtc = Date.UTC(
    Number(values.year),
    Number(values.month) - 1,
    Number(values.day),
    Number(values.hour),
    Number(values.minute),
    Number(values.second),
  );
  return asUtc - date.getTime();
}

function buildChartOption(points) {
  const times = points.map((point) => formatUtcLabel(point.time_utc));
  const entryPrices = points.map((point) => point.entry_price);
  const targetPrices = points.map((point) => point.target_price);
  const actualPrices = points.map((point) => point.actual_result_price);
  const expectedProfits = points.map((point) => point.expected_profit);
  const expectedLosses = points.map((point) => -Math.abs(point.expected_loss));

  return {
    tooltip: {
      trigger: "axis",
      valueFormatter: (value) => (value == null ? "-" : Number(value).toFixed(4)),
    },
    legend: {
      top: 0,
      data: [chartText("entry"), chartText("target"), chartText("actual"), chartText("profit"), chartText("loss")],
    },
    grid: {
      top: 54,
      left: 58,
      right: 58,
      bottom: 58,
    },
    xAxis: {
      type: "category",
      data: times,
      axisLabel: {
        rotate: 30,
      },
    },
    yAxis: [
      {
        type: "value",
        name: chartText("price"),
        scale: true,
      },
      {
        type: "value",
        name: chartText("pnl"),
        scale: true,
      },
    ],
    dataZoom: [
      {
        type: "inside",
      },
      {
        type: "slider",
        height: 22,
        bottom: 18,
      },
    ],
    series: [
      buildLineSeries(chartText("entry"), entryPrices, 0, "#2f6fdd", "solid"),
      buildLineSeries(chartText("target"), targetPrices, 0, "#8d5cf6", "dashed"),
      buildLineSeries(chartText("actual"), actualPrices, 0, "#202938", "solid"),
      buildLineSeries(chartText("profit"), expectedProfits, 1, "#1f9d6a", "solid"),
      buildLineSeries(chartText("loss"), expectedLosses, 1, "#d24b5a", "solid"),
    ],
  };
}

function buildLineSeries(name, data, yAxisIndex, color, lineType) {
  return {
    name,
    type: "line",
    yAxisIndex,
    smooth: true,
    connectNulls: false,
    symbol: "circle",
    symbolSize: 7,
    data,
    lineStyle: {
      width: 2.5,
      type: lineType,
      color,
    },
    itemStyle: {
      color,
    },
    areaStyle:
      yAxisIndex === 1
        ? {
            opacity: 0.06,
          }
        : undefined,
  };
}
