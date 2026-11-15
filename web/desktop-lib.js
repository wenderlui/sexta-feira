// Funções puras do programa do PC (testadas em web/tests/desktop.test.mjs).

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Markdown simples e seguro: escapa tudo antes; depois só **negrito**, `código`, ```blocos``` e listas.
export function miniMarkdown(text) {
  const parts = String(text ?? "").split(/```/);
  return parts.map((part, i) => {
    if (i % 2 === 1) return `<pre><code>${escapeHtml(part.replace(/^\w*\n/, ""))}</code></pre>`;
    return escapeHtml(part)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/^\s*[-*•] (.+)$/gm, "<li>$1</li>")
      .replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m.replace(/\n/g, "")}</ul>`)
      .replace(/\n/g, "<br>");
  }).join("");
}

// ok: true (verde), false (vermelho), null (cinza = desligado / não configurado)
export function statusClass(ok) {
  return ok === true ? "ok" : ok === false ? "bad" : "off";
}

export function logLevel(line) {
  if (/\b(ERROR|CRITICAL|Traceback|Exception)\b/.test(line)) return "error";
  if (/\bWARNING\b/.test(line)) return "warn";
  if (/sexta\.ipad/.test(line)) return "ipad";
  return "info";
}

export function formatUptime(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}min`;
  return `${m}min`;
}

// Mantém só as últimas N mensagens (o servidor usa as 12 últimas de qualquer forma).
export function trimHistory(history, max = 40) {
  return history.length > max ? history.slice(history.length - max) : history;
}
