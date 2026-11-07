import {
  formatMoney, formatChange, formatTime, weekdayShort, sparkPaths, greetingFor, formatUptime,
} from "./format.js";

const $ = (id) => document.getElementById(id);
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Estado compartilhado com voice.js
const sexta = (window.sexta = {
  cameraStream: null,
  micStream: null,
  analyser: null,
  muted: false,
  panel: {},
  setState(state, label) {
    document.body.dataset.state = state;
    $("core-label").textContent = label || {
      idle: "EM ESPERA", listening: "OUVINDO", thinking: "PROCESSANDO", speaking: "FALANDO",
    }[state] || "";
  },
  setStatus(text) { $("status").textContent = text || ""; },
  chip(id, cls) { const el = $(`chip-${id}`); el.classList.remove("ok", "warn", "bad"); if (cls) el.classList.add(cls); },
});

// ---------- Fundo animado: rede de partículas + grade em perspectiva ----------
function startBackground() {
  const canvas = $("bg");
  const ctx = canvas.getContext("2d");
  let w = 0, h = 0, dpr = 1, nodes = [], t = 0, frame = 0;

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const count = Math.round((w * h) / 18000);
    nodes = Array.from({ length: count }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.25, vy: (Math.random() - 0.5) * 0.25,
      r: Math.random() * 1.4 + 0.4,
    }));
  }

  function drawGrid() {
    // Grade em perspectiva "rolando" no chão da cena.
    const horizon = h * 0.62;
    ctx.strokeStyle = "rgba(54, 214, 255, 0.07)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = -12; i <= 12; i++) {
      ctx.moveTo(w / 2 + i * 40, horizon);
      ctx.lineTo(w / 2 + i * 260, h);
    }
    const offset = (t * 0.4) % 1;
    for (let k = 0; k < 10; k++) {
      const p = (k + offset) / 10;
      const y = horizon + (h - horizon) * p * p;
      ctx.moveTo(0, y); ctx.lineTo(w, y);
    }
    ctx.stroke();
  }

  function step() {
    t += 0.016;
    ctx.clearRect(0, 0, w, h);
    drawGrid();
    const level = sexta.level || 0;
    const linkDist = 120;
    for (const n of nodes) {
      n.x += n.vx * (1 + level * 6); n.y += n.vy * (1 + level * 6);
      if (n.x < 0 || n.x > w) n.vx *= -1;
      if (n.y < 0 || n.y > h) n.vy *= -1;
    }
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < linkDist * linkDist) {
          const alpha = (1 - Math.sqrt(d2) / linkDist) * 0.18;
          ctx.strokeStyle = `rgba(54, 214, 255, ${alpha})`;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
      ctx.fillStyle = "rgba(158, 234, 255, 0.7)";
      ctx.beginPath(); ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2); ctx.fill();
    }
    frame = requestAnimationFrame(step);
  }

  resize();
  window.addEventListener("resize", resize);
  if (reduceMotion) { drawGrid(); return; }
  step();
  document.addEventListener("visibilitychange", () => {
    cancelAnimationFrame(frame);
    if (document.visibilityState === "visible") step();
  });
}

// ---------- Animação de números ----------
function countTo(el, value, format) {
  const target = Number(value);
  if (!Number.isFinite(target)) { el.textContent = "--"; return; }
  const from = Number(el.dataset.value);
  el.dataset.value = String(target);
  if (reduceMotion || !Number.isFinite(from) || from === target) { el.textContent = format(target); return; }
  const start = performance.now(), dur = 900;
  const tick = (now) => {
    const k = Math.min(1, (now - start) / dur);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = format(from + (target - from) * e);
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// ---------- Histórico para os minigráficos (fica só neste aparelho) ----------
const HISTORY_KEY = "sexta.history.v1";
let history = {};
try { history = JSON.parse(localStorage.getItem(HISTORY_KEY) || "{}"); } catch { history = {}; }
function pushHistory(key, value, max = 288) {
  if (!Number.isFinite(value)) return history[key] || [];
  const arr = (history[key] = history[key] || []);
  arr.push(value);
  if (arr.length > max) arr.splice(0, arr.length - max);
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history)); } catch { /* sem armazenamento */ }
  return arr;
}
function drawSpark(svg, values, w, h) {
  const p = sparkPaths(values, w, h);
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.classList.remove("up", "down");
  if (!p) { svg.innerHTML = ""; return; }
  if (p.trend) svg.classList.add(p.trend);
  svg.innerHTML = `<path class="area" d="${p.area}"/><path class="line" d="${p.line}"/>`;
}

// ---------- Relógio ----------
function tickClock() {
  const now = new Date();
  const hm = now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const ss = String(now.getSeconds()).padStart(2, "0");
  $("clock-time").innerHTML = `${hm}<small>${ss}</small>`;
  $("clock-date").textContent = now.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
  $("greeting").textContent = `${greetingFor(now.getHours())}, Wender`;
}

// ---------- Dados ----------
const failures = new Set();
function refreshStatus() {
  if (failures.size) {
    sexta.setStatus(`sem dados: ${[...failures].join(", ")}`);
    sexta.chip("link", "warn");
  } else {
    sexta.setStatus(navigator.onLine ? "" : "offline");
    sexta.chip("link", navigator.onLine ? "ok" : "bad");
  }
}

async function getJSON(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function load(name, path, render) {
  try {
    const data = await getJSON(path);
    sexta.panel[name] = data;
    render(data);
    failures.delete(name);
  } catch (e) {
    console.warn(e);
    failures.add(name);
  }
  refreshStatus();
}

function renderWeather(w) {
  $("weather-city").textContent = w.city;
  $("weather-icon").textContent = w.icon;
  countTo($("weather-temp"), w.temperature, (v) => Math.round(v));
  $("weather-desc").textContent = w.description;
  $("weather-extra").textContent =
    `Sensação ${Math.round(w.feels_like)}° · Umidade ${w.humidity}% · Vento ${Math.round(w.wind_kmh)} km/h`;
  $("weather-days").innerHTML = w.days
    .map((d) => `<li><div class="d-name">${weekdayShort(d.date).replace(".", "")}</div><div>${d.icon}</div>
      <div>${Math.round(d.max)}° / ${Math.round(d.min)}°</div>
      <div class="muted">${d.rain_chance ?? 0}% chuva</div></li>`)
    .join("");
  const today = w.days?.[0];
  const hhmm = (iso) => (iso ? iso.slice(11, 16) : "--:--");
  $("weather-sun").innerHTML = today?.sunrise
    ? `<span>Nascer do sol <b>${hhmm(today.sunrise)}</b></span><span>Pôr do sol <b>${hhmm(today.sunset)}</b></span>`
    : "";
}

function renderCrypto(c) {
  const tbody = $("crypto-rows");
  if (!tbody.querySelector("tr[data-sym]")) {
    tbody.innerHTML = c.coins.map((coin) => `<tr data-sym="${coin.symbol}">
      <td class="sym">${coin.symbol}</td><td class="usd num">--</td><td class="brl num">--</td>
      <td class="chg">--</td><td class="sp"><svg class="spark" preserveAspectRatio="none"></svg></td></tr>`).join("");
  }
  for (const coin of c.coins) {
    const row = tbody.querySelector(`tr[data-sym="${coin.symbol}"]`);
    if (!row) continue;
    const prev = Number(row.querySelector(".usd").dataset.value);
    countTo(row.querySelector(".usd"), coin.usd, (v) => formatMoney(v));
    countTo(row.querySelector(".brl"), coin.brl, (v) => formatMoney(v));
    const ch = formatChange(coin.change_24h);
    const chg = row.querySelector(".chg");
    chg.textContent = ch.text; chg.className = `chg ${ch.cls}`;
    drawSpark(row.querySelector("svg"), pushHistory(coin.symbol, coin.usd), 64, 20);
    if (Number.isFinite(prev) && prev !== coin.usd) {
      row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash");
    }
  }
  $("crypto-meta").textContent = `${c.source} · ${formatTime(c.updated_at)}`;
}

function renderUsdt(u) {
  countTo($("usdt-price"), u.price, (v) => formatMoney(v));
  const ch = formatChange(u.change_24h);
  $("usdt-change").textContent = u.change_24h != null ? `${ch.text} 24h` : "";
  $("usdt-change").className = ch.cls;
  drawSpark($("usdt-spark"), pushHistory("USDTBRL", u.price), 200, 48);
  $("usdt-convert").innerHTML = [100, 1000, 5000]
    .map((n) => `<div><b>${n.toLocaleString("pt-BR")} USDT</b>R$ ${Math.round(n * u.price).toLocaleString("pt-BR")}</div>`)
    .join("");
  $("usdt-meta").textContent = `${u.source} · atualizado ${formatTime(u.updated_at)}`;
}

function setBar(id, pct) {
  const el = $(`bar-${id}`);
  const v = Number.isFinite(pct) ? Math.max(0, Math.min(100, pct)) : 0;
  el.style.width = `${v}%`;
  el.classList.toggle("hot", v >= 85);
}

function renderSystem(s) {
  setBar("cpu", s.cpu); $("val-cpu").textContent = s.cpu != null ? `${Math.round(s.cpu)}%` : "--";
  setBar("ram", s.ram_percent);
  $("val-ram").textContent = s.ram_used_gb != null ? `${Math.round(s.ram_used_gb)}/${Math.round(s.ram_total_gb)} GB` : "--";
  if (s.gpu) {
    setBar("gpu", s.gpu.util); $("val-gpu").textContent = `${Math.round(s.gpu.util)}% · ${Math.round(s.gpu.temp_c)}°`;
    setBar("vram", (s.gpu.mem_used_mb / s.gpu.mem_total_mb) * 100);
    $("val-vram").textContent = `${(s.gpu.mem_used_mb / 1024).toFixed(1)}/${Math.round(s.gpu.mem_total_mb / 1024)} GB`;
    $("system-meta").textContent = s.gpu.name;
  } else {
    $("val-gpu").textContent = "--"; $("val-vram").textContent = "--";
  }
  $("system-uptime").textContent = `no ar há ${formatUptime(s.uptime_s)}`;
}

async function loadAssistant() {
  try {
    const st = await getJSON("/api/assistant/status");
    sexta.assistant = st;
    sexta.chip("ai", st.online && st.chat_model_ready ? "ok" : st.online ? "warn" : "bad");
    sexta.chip("voice", st.stt_available ? "ok" : "warn");
  } catch {
    sexta.chip("ai", "bad");
  }
}

// ---------- Câmera e microfone ----------
let audioCtx = null;
let meterFrame = 0;

function setPressed(btn, on) { btn.setAttribute("aria-pressed", String(on)); }

async function toggleCamera() {
  const btn = $("btn-camera");
  const video = $("camera-preview");
  if (sexta.cameraStream) {
    sexta.cameraStream.getTracks().forEach((t) => t.stop());
    sexta.cameraStream = null;
    video.srcObject = null; video.hidden = true;
    setPressed(btn, false);
    return;
  }
  try {
    sexta.cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
    });
    video.srcObject = sexta.cameraStream; video.hidden = false;
    setPressed(btn, true);
  } catch (e) { mediaError("câmera", e); }
}

async function ensureMic() {
  if (sexta.micStream) return sexta.micStream;
  sexta.micStream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 512;
  audioCtx.createMediaStreamSource(sexta.micStream).connect(analyser);
  sexta.analyser = analyser;
  const buf = new Uint8Array(analyser.fftSize);
  const core = document.querySelector(".core");
  const draw = () => {
    analyser.getByteTimeDomainData(buf);
    let peak = 0;
    for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
    const level = Math.min(1, (peak / 128) * 1.6);
    sexta.level = level;
    $("mic-level").style.width = `${level * 100}%`;
    core.style.setProperty("--level", level.toFixed(3));
    meterFrame = requestAnimationFrame(draw);
  };
  draw();
  return sexta.micStream;
}

async function releaseMic() {
  if (!sexta.micStream) return;
  sexta.micStream.getTracks().forEach((t) => t.stop());
  sexta.micStream = null; sexta.analyser = null; sexta.level = 0;
  cancelAnimationFrame(meterFrame);
  if (audioCtx) await audioCtx.close();
  audioCtx = null;
  $("mic-level").style.width = "0";
  document.querySelector(".core").style.setProperty("--level", "0");
}
sexta.ensureMic = ensureMic;
sexta.releaseMic = releaseMic;

function mediaError(what, err) {
  console.warn(err);
  sexta.setStatus(!window.isSecureContext
    ? `sem acesso à ${what}: abra pelo endereço HTTPS do Tailscale`
    : `sem acesso à ${what}: permita nos Ajustes do Safari`);
}
sexta.mediaError = mediaError;

function toggleFullscreen() {
  const el = document.documentElement;
  if (document.fullscreenElement || document.webkitFullscreenElement) {
    (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
  } else (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
}

// ---------- Inicialização ----------
async function boot() {
  const steps = ["INICIALIZANDO SISTEMAS", "CONECTANDO AO NÚCLEO", "CARREGANDO SENSORES", "PRONTA"];
  for (const s of steps) {
    $("boot-text").textContent = s;
    await new Promise((r) => setTimeout(r, reduceMotion ? 0 : 420));
  }
  $("boot").classList.add("done");
}

async function start() {
  startBackground();
  boot();
  tickClock();
  setInterval(tickClock, 1000);

  let refresh = { weather: 600, crypto: 300, usdtbrl: 60 };
  try { refresh = (await getJSON("/api/config")).refresh_seconds; } catch (e) { console.warn(e); }

  const all = () => {
    load("weather", "/api/weather", renderWeather);
    load("crypto", "/api/crypto", renderCrypto);
    load("usdtbrl", "/api/usdtbrl", renderUsdt);
  };
  all();
  load("system", "/api/system", renderSystem);
  loadAssistant();
  setInterval(() => load("weather", "/api/weather", renderWeather), refresh.weather * 1000);
  setInterval(() => load("crypto", "/api/crypto", renderCrypto), refresh.crypto * 1000);
  setInterval(() => load("usdtbrl", "/api/usdtbrl", renderUsdt), refresh.usdtbrl * 1000);
  setInterval(() => { if (document.visibilityState === "visible") load("system", "/api/system", renderSystem); }, 5000);
  setInterval(loadAssistant, 30000);

  $("btn-camera").addEventListener("click", toggleCamera);
  $("btn-fullscreen").addEventListener("click", toggleFullscreen);
  $("btn-mute").addEventListener("click", () => {
    sexta.muted = !sexta.muted;
    setPressed($("btn-mute"), sexta.muted);
    if (sexta.muted) window.speechSynthesis?.cancel();
  });
  window.addEventListener("online", refreshStatus);
  window.addEventListener("offline", refreshStatus);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") { all(); loadAssistant(); }
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch((e) => console.warn(e));
  }
}

start();
