// Formatação de números e datas para o painel (pt-BR).

export function formatMoney(value, currency) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const n = Number(value);
  // Valores grandes sem centavos (cabem no painel); moedas baratas (ex.: POL) com 4 casas.
  const digits = Math.abs(n) >= 1000 ? 0 : Math.abs(n) >= 1 ? 2 : 4;
  return new Intl.NumberFormat("pt-BR", {
    style: currency ? "currency" : "decimal",
    currency: currency || undefined,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
}

export function formatChange(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return { text: "--", cls: "" };
  }
  const n = Number(value);
  const sign = n > 0 ? "+" : "";
  return {
    text: `${sign}${n.toFixed(2).replace(".", ",")}%`,
    cls: n > 0 ? "up" : n < 0 ? "down" : "",
  };
}

export function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export function weekdayShort(isoDate) {
  // "2026-11-07" -> "sáb." sem cair no dia anterior por causa do fuso.
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("pt-BR", { weekday: "short" });
}

// Gera os caminhos SVG (linha e área) de um minigráfico num viewBox w×h.
export function sparkPaths(values, w = 200, h = 48, pad = 3) {
  const v = (values || []).filter((x) => Number.isFinite(x));
  if (v.length < 2) return null;
  const min = Math.min(...v);
  const max = Math.max(...v);
  const span = max - min || Math.abs(max) * 0.001 || 1;
  const pts = v.map((x, i) => [
    (i / (v.length - 1)) * w,
    h - pad - ((x - min) / span) * (h - pad * 2),
  ]);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join("");
  const area = `${line}L${w} ${h}L0 ${h}Z`;
  return { line, area, trend: v.at(-1) > v[0] ? "up" : v.at(-1) < v[0] ? "down" : "" };
}

export function greetingFor(hour) {
  if (hour < 5) return "boa madrugada";
  if (hour < 12) return "bom dia";
  if (hour < 18) return "boa tarde";
  return "boa noite";
}

export function formatUptime(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}min` : `${m}min`;
}
