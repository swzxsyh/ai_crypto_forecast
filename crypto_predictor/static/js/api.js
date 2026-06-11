export async function fetchChartData({ symbol = "", startUtc = "", endUtc = "" } = {}) {
  const params = new URLSearchParams();
  if (symbol) {
    params.set("symbol", symbol);
  }
  if (startUtc) {
    params.set("start_utc", startUtc);
  }
  if (endUtc) {
    params.set("end_utc", endUtc);
  }
  const query = params.toString();
  const url = query ? `/api/chart-data?${query}` : "/api/chart-data";
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`图表数据加载失败：${response.status}`);
  }

  return response.json();
}
