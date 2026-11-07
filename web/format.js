// Formatação de números e datas para o painel (pt-BR).

export function formatMoney(value, currency) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const n = Number(value);
  // Moedas baratas (ex.: POL) precisam de mais casas decimais.
  const digits = Math.abs(n) >= 1 ? 2 : 4;
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
