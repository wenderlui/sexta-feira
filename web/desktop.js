// Programa do PC: menus, conversa, modelos, serviços, registros e ajustes.
import { escapeHtml, miniMarkdown, statusClass, logLevel, formatUptime, trimHistory } from "./desktop-lib.js";

const $ = (id) => document.getElementById(id);
const HISTORY_KEY = "sexta.desktop.chat";
let desk = null;            // window.pywebview.api quando roda dentro do programa
let current = "inicio";

// ---------------------------------------------------------------- utilidades
async function api(path, opts = {}) {
  const init = { ...opts, headers: { ...(opts.body && typeof opts.body === "string" ? { "Content-Type": "application/json" } : {}), ...opts.headers } };
  const r = await fetch(path, init);
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.blob();
  if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
  return data;
}
const jsonBody = (o) => JSON.stringify(o);

let toastTimer;
function toast(msg, bad = false) {
  const t = $("toast");
  t.textContent = msg; t.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.className = "toast"), 3200);
}

function safeStore(fn, fallback) { try { return fn(); } catch { return fallback; } }

// ---------------------------------------------------------------- menus
const views = [...document.querySelectorAll("#menu button")].map((b) => b.dataset.view);
function go(view) {
  if (!views.includes(view)) return;
  current = view;
  document.querySelectorAll("#menu button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  if (view === "painel") { const f = $("hud"); if (!f.src) f.src = f.dataset.src; }
  if (view === "chat") $("input").focus();
  refresh();
}
document.querySelectorAll("#menu button").forEach((b) => b.addEventListener("click", () => go(b.dataset.view)));
document.addEventListener("keydown", (e) => {
  if (e.ctrlKey && /^[1-7]$/.test(e.key)) { e.preventDefault(); go(views[+e.key - 1]); }
  if (e.ctrlKey && e.code === "Space" && current === "chat") { e.preventDefault(); toggleMic(); }
  if (e.key === "Escape" && desk) desk.hide();
});

// ---------------------------------------------------------------- relógio e saudação
function tick() {
  const now = new Date();
  $("side-clock").textContent = now.toLocaleString("pt-BR", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  const h = now.getHours();
  $("hello").textContent = h < 5 ? "Boa madrugada, Wender" : h < 12 ? "Bom dia, Wender" : h < 18 ? "Boa tarde, Wender" : "Boa noite, Wender";
}
tick(); setInterval(tick, 15000);

// ---------------------------------------------------------------- serviços / início
function svcList(services) {
  return services.map((s) => `<li class="${statusClass(s.ok)}"><i></i><b>${escapeHtml(s.name)}</b><span>${escapeHtml(s.detail || "")}</span></li>`).join("");
}
function setBar(id, pct) { $(id).style.width = `${Math.max(0, Math.min(100, pct || 0))}%`; }

async function loadServices() {
  const d = await api("/api/desktop/services");
  $("offline").checked = !!d.offline;
  document.body.classList.toggle("is-offline", !!d.offline);
  $("side-model").textContent = `modelo: ${d.chat_model}`;
  $("chat-model").textContent = `${d.chat_model} · ${d.offline ? "offline, sem internet" : "local, pode pesquisar na internet"}`;
  $("brand-sub").textContent = d.offline ? "IA local · offline" : "IA local";
  const pc = d.pc || {};
  $("st-cpu").textContent = pc.cpu != null ? `${Math.round(pc.cpu)}%` : "—"; setBar("bar-cpu", pc.cpu);
  $("st-ram").textContent = pc.ram_used_gb != null ? `${pc.ram_used_gb} / ${pc.ram_total_gb} GB` : "—"; setBar("bar-ram", pc.ram_percent);
  if (pc.gpu) {
    $("st-gpu").textContent = `${Math.round(pc.gpu.util)}%`; setBar("bar-gpu", pc.gpu.util);
    $("st-vram").textContent = `${(pc.gpu.mem_used_mb / 1024).toFixed(1)} / ${(pc.gpu.mem_total_mb / 1024).toFixed(0)} GB`;
    setBar("bar-vram", (pc.gpu.mem_used_mb / pc.gpu.mem_total_mb) * 100);
    $("st-temp").textContent = `GPU ${Math.round(pc.gpu.temp_c)}°C`;
  }
  $("st-up").textContent = formatUptime(pc.uptime_s);
  $("home-svc").innerHTML = svcList(d.services);
  const bad = d.services.filter((s) => s.ok === false).map((s) => s.name);
  $("hello-sub").textContent = bad.length ? `Atenção: ${bad.join(", ")}.` : "Tudo rodando no seu PC.";
  $("core").className = "core" + (bad.length ? " warn" : "");
  $("svc-cards").innerHTML = d.services.map((s) => `
    <div class="card svc-card ${statusClass(s.ok)}"><i></i><h3>${escapeHtml(s.name)}</h3><p>${escapeHtml(s.detail || "")}</p>
    ${s.loaded?.length ? `<small>Na GPU: ${s.loaded.map(escapeHtml).join(", ")}</small>` : ""}</div>`).join("");
}

async function loadAlerts() {
  const { alerts } = await api("/api/alerts?limit=5");
  $("alerts").innerHTML = alerts.length ? alerts.map((a) => `<li class="${a.visto ? "seen" : ""}">
    <b>${escapeHtml(a.camera)}</b> ${escapeHtml((a.objetos || []).join(", "))} · ${new Date(a.quando).toLocaleString("pt-BR")}
    <span>${escapeHtml(a.descricao || "")}</span></li>`).join("") : `<li class="muted">Nenhum alerta.</li>`;
}

$("offline").addEventListener("change", async (e) => {
  try {
    await api("/api/settings", { method: "PUT", body: jsonBody({ offline: e.target.checked }) });
    toast(e.target.checked ? "Modo offline: só IA local, sem internet." : "Modo online: pode pesquisar na internet.");
    loadServices();
  } catch (err) { toast(err.message, true); e.target.checked = !e.target.checked; }
});

// ---------------------------------------------------------------- conversa
let history = safeStore(() => JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"), []);
const saveHistory = () => safeStore(() => localStorage.setItem(HISTORY_KEY, JSON.stringify(trimHistory(history))));

function bubble(m) {
  const div = document.createElement("div");
  div.className = `msg ${m.role}${m.pending ? " pending" : ""}${m.error ? " error" : ""}`;
  const src = (m.sources || []).slice(0, 5).map((s) => `<a href="${escapeHtml(s.href)}" target="_blank" rel="noopener">${escapeHtml(s.title || s.href)}</a>`).join("");
  div.innerHTML = `<div class="body">${m.pending ? "<span class='dots'><i></i><i></i><i></i></span>" : miniMarkdown(m.content)}</div>
    ${src ? `<div class="src">${src}</div>` : ""}
    ${m.role === "assistant" && !m.pending ? `<div class="tools"><button data-a="copy">Copiar</button><button data-a="say">Ouvir</button>${m.model ? `<small>${escapeHtml(m.model)}</small>` : ""}</div>` : ""}`;
  div.querySelector("[data-a=copy]")?.addEventListener("click", () => navigator.clipboard.writeText(m.content).then(() => toast("Copiado.")));
  div.querySelector("[data-a=say]")?.addEventListener("click", () => say(m.content));
  return div;
}
function renderChat() {
  const box = $("msgs");
  box.innerHTML = "";
  if (!history.length) box.innerHTML = `<div class="empty"><div class="core big"></div><p>Pergunte, peça uma pesquisa ou mande controlar a casa.</p></div>`;
  history.forEach((m) => box.appendChild(bubble(m)));
  box.scrollTop = box.scrollHeight;
}

async function ask(text) {
  text = text.trim();
  if (!text) return;
  history.push({ role: "user", content: text });
  const pending = { role: "assistant", content: "", pending: true };
  history.push(pending);
  renderChat();
  api("/api/wake", { method: "POST" }).catch(() => {});
  try {
    const msgs = history.filter((m) => !m.pending && !m.error).map(({ role, content }) => ({ role, content }));
    const r = await api("/api/chat", { method: "POST", body: jsonBody({ messages: msgs }) });
    Object.assign(pending, { content: r.text, sources: r.sources, model: r.model, pending: false });
    if ($("speak").checked) say(r.text);
  } catch (err) {
    Object.assign(pending, { content: `Não consegui responder: ${err.message}`, pending: false, error: true });
  }
  saveHistory(); renderChat();
  return pending;
}

$("composer").addEventListener("submit", (e) => { e.preventDefault(); const t = $("input").value; $("input").value = ""; autoGrow(); ask(t); });
$("input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("composer").requestSubmit(); } });
function autoGrow() { const i = $("input"); i.style.height = "auto"; i.style.height = Math.min(i.scrollHeight, 180) + "px"; }
$("input").addEventListener("input", autoGrow);
$("chat-clear").addEventListener("click", () => { history = []; saveHistory(); renderChat(); });
$("speak").checked = safeStore(() => localStorage.getItem("sexta.desktop.speak") === "1", false);
$("speak").addEventListener("change", (e) => safeStore(() => localStorage.setItem("sexta.desktop.speak", e.target.checked ? "1" : "0")));

$("quick").addEventListener("submit", async (e) => {
  e.preventDefault();
  const t = $("quick-in").value; $("quick-in").value = "";
  if (!t.trim()) return;
  $("quick-out").innerHTML = "<span class='dots'><i></i><i></i><i></i></span>";
  const m = await ask(t);
  $("quick-out").innerHTML = m ? miniMarkdown(m.content) : "";
});

// voz: falar
let audio;
async function say(text) {
  try {
    const blob = await api("/api/tts", { method: "POST", body: jsonBody({ text }) });
    audio?.pause();
    audio = new Audio(URL.createObjectURL(blob)); audio.play();
  } catch (err) { toast(`Voz: ${err.message}`, true); }
}

// voz: ouvir (grava enquanto o botão está ativo)
let rec = null;
async function toggleMic() {
  const btn = $("mic");
  if (rec) { rec.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    api("/api/wake", { method: "POST" }).catch(() => {});
    const chunks = [];
    rec = new MediaRecorder(stream);
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      btn.classList.remove("rec"); rec = null;
      const blob = new Blob(chunks, { type: chunks[0]?.type || "audio/webm" });
      try {
        const r = await api("/api/transcribe", { method: "POST", body: blob, headers: { "Content-Type": blob.type } });
        if (r.text?.trim()) ask(r.text); else toast("Não ouvi nada.");
      } catch (err) { toast(`Ouvir: ${err.message}`, true); }
    };
    rec.start(); btn.classList.add("rec");
  } catch (err) { toast(`Microfone: ${err.message}`, true); }
}
$("mic").addEventListener("click", toggleMic);

// ---------------------------------------------------------------- modelos
async function loadModels() {
  let d;
  try { d = await api("/api/models"); } catch (err) {
    $("models").innerHTML = `<tbody><tr><td class="muted">O Ollama não está respondendo (${escapeHtml(err.message)}). Abra o Ollama ou veja Serviços.</td></tr></tbody>`;
    return;
  }
  const rows = d.installed.map((m) => `<tr>
    <td><b>${escapeHtml(m.name)}</b>${m.role ? ` <em class="tag">${m.role}</em>` : ""}</td>
    <td>${escapeHtml(m.params || "")} ${escapeHtml(m.quant || "")}</td><td>${m.size_gb} GB</td>
    <td>${m.loaded ? `<span class="dot ok"></span> na GPU (${m.vram_gb} GB)` : `<span class="dot off"></span> em espera`}</td>
    <td class="act">
      ${m.name === d.chat_model ? "" : `<button data-use="${escapeHtml(m.name)}">Usar na conversa</button>`}
      ${m.loaded ? `<button class="ghost" data-unload="${escapeHtml(m.name)}">Liberar GPU</button>` : `<button class="ghost" data-load="${escapeHtml(m.name)}">Carregar</button>`}
    </td></tr>`).join("");
  $("models").innerHTML = `<thead><tr><th>Modelo</th><th>Tamanho</th><th>Disco</th><th>Estado</th><th></th></tr></thead><tbody>${rows || "<tr><td>Nenhum modelo instalado.</td></tr>"}</tbody>`;
  $("sugg").innerHTML = d.suggested.map((s) => `<li><b>${escapeHtml(s.name)}</b> <small>${s.size_gb} GB</small><span>${escapeHtml(s.note)}</span><code>ollama pull ${escapeHtml(s.name)}</code></li>`).join("") || "<li class='muted'>Você já tem todos os sugeridos.</li>";
}
$("models").addEventListener("click", async (e) => {
  const b = e.target.closest("button"); if (!b) return;
  b.disabled = true;
  try {
    if (b.dataset.use) { await api("/api/models/chat", { method: "PUT", body: jsonBody({ name: b.dataset.use }) }); toast(`Agora a conversa usa ${b.dataset.use}.`); }
    if (b.dataset.unload) { await api(`/api/models/${encodeURIComponent(b.dataset.unload)}/unload`, { method: "POST" }); toast("GPU liberada."); }
    if (b.dataset.load) { toast("Carregando na GPU…"); await api(`/api/models/${encodeURIComponent(b.dataset.load)}/load`, { method: "POST" }); toast("Pronto."); }
  } catch (err) { toast(err.message, true); }
  loadModels(); loadServices();
});
$("sugg").addEventListener("click", (e) => { const c = e.target.closest("code"); if (c) navigator.clipboard.writeText(c.textContent).then(() => toast("Comando copiado.")); });

// ---------------------------------------------------------------- registros
async function loadLogs() {
  const q = $("log-q").value.trim();
  const d = await api(`/api/logs?lines=400${q ? `&q=${encodeURIComponent(q)}` : ""}`);
  const el = $("log");
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
  el.innerHTML = d.lines.length ? d.lines.map((l) => `<span class="${logLevel(l)}">${escapeHtml(l)}</span>`).join("\n") : "Registro vazio.";
  if (atBottom) el.scrollTop = el.scrollHeight;
}
$("log-q").addEventListener("input", () => loadLogs().catch(() => {}));

// ---------------------------------------------------------------- ajustes
async function loadSettings() {
  const s = await api("/api/settings");
  const fill = (sel, opts, val) => { $(sel).innerHTML = Object.entries(opts).map(([k, v]) => `<option value="${escapeHtml(k)}"${k === val ? " selected" : ""}>${escapeHtml(v)}</option>`).join(""); };
  $("tts-engine").value = s.tts_engine;
  fill("edge-voice", s.options.edge_voice, s.edge_voice);
  fill("kokoro-voice", s.options.tts_voice, s.tts_voice);
  $("tts-speed").value = s.tts_speed; $("tts-speed-v").textContent = `${s.tts_speed}×`;
  if (desk) $("autostart").checked = (await desk.info()).autostart;
}
async function saveSetting(obj) {
  try { await api("/api/settings", { method: "PUT", body: jsonBody(obj) }); toast("Salvo."); } catch (err) { toast(err.message, true); }
}
$("tts-engine").addEventListener("change", (e) => saveSetting({ tts_engine: e.target.value }));
$("edge-voice").addEventListener("change", (e) => saveSetting({ edge_voice: e.target.value }));
$("kokoro-voice").addEventListener("change", (e) => saveSetting({ tts_voice: e.target.value }));
$("tts-speed").addEventListener("input", (e) => ($("tts-speed-v").textContent = `${e.target.value}×`));
$("tts-speed").addEventListener("change", (e) => saveSetting({ tts_speed: parseFloat(e.target.value) }));
$("tts-test").addEventListener("click", () => say("Olá, Wender. Todos os sistemas estão funcionando."));
$("autostart").addEventListener("change", async (e) => { if (desk) e.target.checked = await desk.set_autostart(e.target.checked); });
$("open-browser").addEventListener("click", () => desk?.open_browser());
document.querySelectorAll("[data-folder]").forEach((b) => b.addEventListener("click", () => desk?.open_folder(b.dataset.folder)));
$("restart").addEventListener("click", async () => {
  if (!desk) return;
  toast("Reiniciando o servidor…");
  const ok = await desk.restart_server();
  toast(ok ? "Servidor reiniciado." : "O servidor não voltou. Veja Registros.", !ok);
});
$("svc-refresh").addEventListener("click", () => loadServices().then(() => toast("Atualizado.")).catch((e) => toast(e.message, true)));

// ---------------------------------------------------------------- atualização periódica
async function refresh() {
  const jobs = { inicio: [loadServices, loadAlerts], servicos: [loadServices], modelos: [loadModels], registros: [loadLogs], ajustes: [loadSettings] }[current] || [];
  await Promise.all(jobs.map((fn) => fn().catch((err) => console.warn(fn.name, err))));
}
setInterval(() => {
  if (document.hidden) return;
  if (current === "registros" && !$("log-auto").checked) return;
  if (["inicio", "servicos", "registros", "modelos"].includes(current)) refresh();
}, 5000);

function enableDesktop() {
  desk = window.pywebview?.api || null;
  document.body.classList.toggle("desktop", !!desk);
  if (current === "ajustes") loadSettings();
}
window.addEventListener("pywebviewready", enableDesktop);
enableDesktop();
renderChat();
loadServices().catch((err) => toast(`Servidor: ${err.message}`, true));
loadAlerts().catch(() => {});
