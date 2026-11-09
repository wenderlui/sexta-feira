// Tela de AJUSTES: casa, conexões, voz e onde ficam os dados.
// Tudo é salvo no PC (data/ajustes.json) pela API; senhas nunca voltam para o iPad.
const $ = (id) => document.getElementById(id);
const sexta = window.sexta;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : `erro ${r.status}`);
  return data;
}
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) e.append(k?.nodeType ? k : document.createTextNode(k ?? ""));
  return e;
}

// ---------- Abrir / fechar ----------
const modal = $("settings");
let lastFocus = null;
function open() {
  lastFocus = document.activeElement;
  modal.hidden = false;
  showTab(currentTab());
  $("settings-close").focus();
}
function close() {
  modal.hidden = true;
  voiceDirty = false;
  lastFocus?.focus?.();
}
$("btn-settings").addEventListener("click", open);
$("settings-close").addEventListener("click", close);
modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden) close(); });

// ---------- Abas ----------
const TAB_KEY = "sexta.settingsTab";
function currentTab() { try { return localStorage.getItem(TAB_KEY) || "tab-casa"; } catch { return "tab-casa"; } }
function showTab(id) {
  for (const b of modal.querySelectorAll("[role=tab]")) b.setAttribute("aria-selected", String(b.dataset.tab === id));
  for (const p of modal.querySelectorAll("[role=tabpanel]")) p.hidden = p.id !== id;
  try { localStorage.setItem(TAB_KEY, id); } catch { /* ok */ }
  ({ "tab-casa": loadDevices, "tab-conexoes": loadConnections, "tab-cameras": loadCameras,
     "tab-voz": loadVoice, "tab-sobre": loadData })[id]?.();
}
for (const b of modal.querySelectorAll("[role=tab]")) b.addEventListener("click", () => showTab(b.dataset.tab));

// ---------- Casa ----------
const KIND_ICON = { luz: "💡", tomada: "🔌", interruptor: "🔘", ventilador: "🌀", tv: "📺", controle: "🎛️", ar: "❄️", "câmera": "📷" };
async function loadDevices() {
  const hint = $("casa-hint"), box = $("devices");
  try {
    const { devices, errors } = await api("/api/home/devices");
    box.replaceChildren(...devices.map(deviceButton));
    hint.textContent = devices.length
      ? `${devices.length} aparelho(s). Toque para ligar ou desligar, ou peça por voz: "Sexta-feira, acende a luz da sala".`
      : "Nenhum aparelho ainda. Conecte o Home Assistant ou a Govee na aba CONEXÕES.";
    if (errors.length) hint.textContent += ` Avisos: ${errors.join("; ")}`;
  } catch (e) { hint.textContent = `Não consegui ler os aparelhos: ${e.message}`; }
}
function deviceButton(d) {
  const canToggle = d.kind !== "câmera";
  const btn = el("button", { class: "device", type: "button", "aria-pressed": d.on == null ? undefined : String(!!d.on),
    disabled: canToggle ? undefined : "" },
  el("span", {}, KIND_ICON[d.kind] || "◻️"),
  el("span", {}, el("b", {}, d.name), el("small", {}, `${d.source}${d.state ? " · " + d.state : ""}`)));
  btn.addEventListener("click", async () => {
    const action = d.on == null ? "ligar" : d.on ? "desligar" : "ligar";
    btn.disabled = true;
    try {
      await api(`/api/home/devices/${encodeURIComponent(d.id)}`, { method: "POST", body: JSON.stringify({ action }) });
      d.on = action === "ligar";
      btn.setAttribute("aria-pressed", String(d.on));
    } catch (e) { sexta.setStatus?.(`${d.name}: ${e.message}`); }
    btn.disabled = false;
  });
  return btn;
}

// ---------- Conexões ----------
const STATUS = {
  on: ["CONECTADO", "on"], off: ["DESCONECTADO", ""], soon: ["EM BREVE", "soon"],
  via_ha_on: ["VIA HOME ASSISTANT", "on"], via_ha_off: ["FALTA HOME ASSISTANT", ""],
};
async function loadConnections() {
  const box = $("connections");
  try {
    const { connections } = await api("/api/connections");
    box.replaceChildren(...connections.map(connectionCard));
  } catch (e) { box.replaceChildren(el("p", { class: "muted" }, `Não consegui carregar: ${e.message}`)); }
}
function connectionCard(c) {
  const [label, cls] = STATUS[c.status] || [c.status, ""];
  const card = el("article", { class: "conn" },
    el("h3", {}, el("span", {}, c.icon), c.name, el("em", { class: `badge ${cls}` }, label)),
    el("p", {}, c.desc));
  if (c.kind !== "native") return card;
  const note = el("span", { class: "saved-note", role: "status" });
  const form = el("form", { autocomplete: "off" });
  for (const f of c.fields) {
    const id = `conn-${c.id}-${f.key}`;
    const input = el("input", { id, name: f.key, type: f.type === "password" ? "password" : "text",
      inputmode: f.type === "url" ? "url" : undefined, autocapitalize: "off", spellcheck: "false",
      placeholder: f.type === "password" && c.saved[f.key] ? `salvo (${c.saved[f.key]}) — deixe vazio para manter` : (f.placeholder || "") });
    if (f.type !== "password") input.value = c.saved[f.key] || "";
    form.append(el("div", { class: "field" }, el("label", { for: id }, f.label), input,
      f.help ? el("small", {}, f.help) : ""));
  }
  const save = el("button", { class: "btn primary", type: "submit" }, "SALVAR E TESTAR");
  const remove = el("button", { class: "btn", type: "button" }, "DESCONECTAR");
  form.append(el("div", { class: "field" }, el("span"), el("div", {}, save, " ", remove)), note);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    save.disabled = true; note.textContent = "Testando…"; note.style.color = "";
    const values = Object.fromEntries(new FormData(form).entries());
    try {
      const r = await api(`/api/connections/${c.id}`, { method: "PUT", body: JSON.stringify({ values }) });
      note.textContent = r.ok ? `Salvo no PC e conectado (${r.detail}).` : `Salvo no PC, mas: ${r.detail}`;
      note.style.color = r.ok ? "" : "var(--amber)";
      if (r.ok) setTimeout(loadConnections, 1200);
    } catch (err) { note.textContent = err.message; note.style.color = "var(--down)"; }
    save.disabled = false;
  });
  remove.addEventListener("click", async () => {
    await api(`/api/connections/${c.id}`, { method: "DELETE" }).catch(() => {});
    loadConnections();
  });
  card.append(form);
  return card;
}

// ---------- Voz ----------
let voiceDirty = false;
let voiceLoad = 0;
async function loadVoice() {
  const ticket = ++voiceLoad;
  const p = await api("/api/settings").catch(() => null);
  // Não sobrescreve o que você está mexendo, nem aplica uma resposta antiga.
  if (!p || ticket !== voiceLoad || voiceDirty) return;
  const fill = (sel, opts, value) => {
    sel.replaceChildren(...Object.entries(opts).map(([v, t]) => el("option", { value: v }, t)));
    sel.value = value;
  };
  $("pref-engine").value = p.tts_engine;
  fill($("pref-edge"), p.options.edge_voice, p.edge_voice);
  fill($("pref-kokoro"), p.options.tts_voice, p.tts_voice);
  $("pref-speed").value = p.tts_speed;
  $("pref-speed-val").textContent = `${Number(p.tts_speed).toFixed(2)}×`;
}
$("voice-form").addEventListener("input", () => { voiceDirty = true; $("voice-saved").textContent = ""; });
$("pref-speed").addEventListener("input", (e) => { $("pref-speed-val").textContent = `${Number(e.target.value).toFixed(2)}×`; });
$("voice-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const body = { tts_engine: f.get("tts_engine"), edge_voice: f.get("edge_voice"),
    tts_voice: f.get("tts_voice"), tts_speed: Number(f.get("tts_speed")) };
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify(body) });
    voiceDirty = false;
    $("voice-saved").textContent = "Salvo no PC. Vale para as próximas respostas.";
  } catch (err) { $("voice-saved").textContent = err.message; }
});
$("voice-test").addEventListener("click", () => sexta.speak?.("Oi, Wender. Esta é a minha voz agora."));

// ---------- Onde ficam os dados ----------
const DATA_ROWS = [
  ["Voz, velocidade e conexões", "No PC, em data/ajustes.json (senhas e chaves nunca vêm para o iPad)."],
  ["Últimas conversas", "Neste iPad (até 20 mensagens), para mostrar o histórico ao abrir."],
  ["Câmera e microfone ligados ou não", "Neste iPad, para voltar como você deixou."],
  ["Gráficos de preço", "Neste iPad (últimas leituras)."],
  ["Registro de funcionamento", "No PC, em logs/servidor.log. O último áudio fica em logs/ para diagnóstico."],
  ["Áudio e imagens da câmera", "Vão só para o seu PC, pela rede privada do Tailscale. Não ficam guardados."],
  ["Texto das respostas faladas", "Com a voz natural, vai para a Microsoft gerar o áudio. Com a voz local, não sai do PC."],
];
function loadData() {
  $("data-info").replaceChildren(el("div", { class: "conn-grid" },
    DATA_ROWS.map(([t, d]) => el("article", { class: "conn" }, el("h3", {}, t), el("p", {}, d)))));
}

// ---------- Câmeras (vigia da madrugada) ----------
// Hora do PC (fuso de Lowell), não a do aparelho: "2026-11-08T02:14:00-05:00" -> "02:14".
const hhmm = (iso) => String(iso).slice(11, 16);
const dia = (iso) => String(iso).slice(8, 10) + "/" + String(iso).slice(5, 7);
const camName = (c) => String(c).replace(/^camera\./, "").replace(/^blink_/, "").replace(/_/g, " ");
async function loadCameras() {
  try {
    const r = await api("/api/cameras/rule");
    const f = $("rule-form");
    f.enabled.value = String(r.enabled);
    f.start.value = r.start; f.end.value = r.end;
    for (const c of f.querySelectorAll("[name=objects]")) c.checked = r.objects.includes(c.value);
    const url = `${location.origin}/api/cameras/event`;
    $("ha-yaml").textContent =
`rest_command:
  sexta_camera:
    url: "${url}"
    method: POST
    headers:
      X-Sexta-Token: "${r.webhook_token}"
    content_type: "application/json"
    payload: '{"camera": "{{ camera }}"}'

# Automação (uma por câmera):
# gatilho: binary_sensor.blink_<camera>_motion passa a "on"
# ação: rest_command.sexta_camera com camera: camera.blink_<camera>`;
  } catch (e) { $("rule-saved").textContent = e.message; }
  loadAlertList();
}
async function loadAlertList() {
  const box = $("alert-list");
  try {
    const { alerts } = await api("/api/alerts?limit=10");
    box.replaceChildren(...(alerts.length ? alerts.map((a) => el("div", { class: "alert-row" },
      a.foto ? el("img", { src: `/api/alerts/${a.id}.jpg`, alt: "", loading: "lazy" }) : el("span", { class: "nophoto" }, "📷"),
      el("div", {}, el("b", {}, `${a.objetos.join(" e ")} · ${camName(a.camera)}`),
        el("small", {}, `${dia(a.quando)} às ${hhmm(a.quando)} — ${a.descricao || ""}`))))
      : [el("p", { class: "muted" }, "Nenhum alerta ainda.")]));
  } catch (e) { box.replaceChildren(el("p", { class: "muted" }, e.message)); }
}
$("rule-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = { enabled: f.enabled.value === "true", start: f.start.value, end: f.end.value,
    objects: [...f.querySelectorAll("[name=objects]:checked")].map((c) => c.value) };
  try {
    await api("/api/cameras/rule", { method: "PUT", body: JSON.stringify(body) });
    $("rule-saved").textContent = "Salvo no PC.";
  } catch (err) { $("rule-saved").textContent = err.message; }
});

// ---------- Alerta no painel ----------
const SEEN_KEY = "sexta.lastAlert";
let shownAlert = null;
async function pollAlerts() {
  try {
    const { alerts } = await api("/api/alerts?limit=5");
    const fresh = alerts.find((a) => !a.visto);
    if (!fresh || fresh.id === shownAlert) return;
    shownAlert = fresh.id;
    const hora = hhmm(fresh.quando);
    const nome = camName(fresh.camera);
    $("alert-title").textContent = `ALERTA: ${fresh.objetos.join(" e ")} na câmera ${nome}, ${hora}`;
    $("alert-desc").textContent = fresh.descricao || "";
    $("alert-photo").hidden = !fresh.foto;
    $("alert-banner").classList.toggle("no-photo", !fresh.foto);
    if (fresh.foto) $("alert-photo").src = `/api/alerts/${fresh.id}.jpg`;
    $("alert-banner").hidden = false;
    document.body.classList.add("has-alert");
    let last = null;
    try { last = localStorage.getItem(SEEN_KEY); localStorage.setItem(SEEN_KEY, fresh.id); } catch { /* ok */ }
    if (last !== fresh.id) sexta.speak?.(`Atenção: ${fresh.objetos.join(" e ")} na câmera ${nome}. ${fresh.descricao || ""}`);
  } catch { /* sem rede: tenta de novo */ }
}
$("alert-ok").addEventListener("click", async () => {
  if (shownAlert) await api(`/api/alerts/${shownAlert}/ack`, { method: "POST" }).catch(() => {});
  $("alert-banner").hidden = true;
  document.body.classList.remove("has-alert");
});
pollAlerts();
setInterval(pollAlerts, 5000);
