import { formatMoney, formatChange, formatTime, weekdayShort } from "./format.js";

const $ = (id) => document.getElementById(id);

// ---------- Relógio ----------
function tickClock() {
  const now = new Date();
  $("clock-time").textContent = now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  $("clock-date").textContent = now.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
}

// ---------- Status ----------
const failures = new Set();
function setStatus() {
  const el = $("status");
  if (failures.size) {
    el.textContent = `Sem dados: ${[...failures].join(", ")}`;
    el.classList.add("error");
  } else {
    el.textContent = navigator.onLine ? "Online" : "Offline";
    el.classList.remove("error");
  }
}

async function getJSON(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// ---------- Clima ----------
async function loadWeather() {
  try {
    const w = await getJSON("/api/weather");
    $("weather-city").textContent = w.city;
    $("weather-icon").textContent = w.icon;
    $("weather-temp").textContent = w.temperature != null ? Math.round(w.temperature) : "--";
    $("weather-desc").textContent = w.description;
    $("weather-extra").textContent =
      `Sensação ${Math.round(w.feels_like)}°C · Umidade ${w.humidity}% · Vento ${Math.round(w.wind_kmh)} km/h`;
    $("weather-days").innerHTML = w.days
      .map((d) => `<li><div>${weekdayShort(d.date)}</div><div>${d.icon}</div>
        <div>${Math.round(d.max)}° / ${Math.round(d.min)}°</div>
        <div class="muted">${d.rain_chance ?? 0}% chuva</div></li>`)
      .join("");
    failures.delete("clima");
  } catch (e) {
    console.warn(e);
    failures.add("clima");
  }
  setStatus();
}

// ---------- Cripto ----------
async function loadCrypto() {
  try {
    const c = await getJSON("/api/crypto");
    $("crypto-rows").innerHTML = c.coins
      .map((coin) => {
        const ch = formatChange(coin.change_24h);
        return `<tr><td><strong>${coin.symbol}</strong></td>
          <td>${formatMoney(coin.usd)}</td><td>${formatMoney(coin.brl)}</td>
          <td class="${ch.cls}">${ch.text}</td></tr>`;
      })
      .join("");
    $("crypto-meta").textContent = `${c.source} · atualizado ${formatTime(c.updated_at)}`;
    failures.delete("cripto");
  } catch (e) {
    console.warn(e);
    failures.add("cripto");
  }
  setStatus();
}

// ---------- USDT/BRL ----------
async function loadUsdt() {
  try {
    const u = await getJSON("/api/usdtbrl");
    $("usdt-price").textContent = formatMoney(u.price);
    $("usdt-meta").textContent = `${u.source} · atualizado ${formatTime(u.updated_at)}`;
    failures.delete("USDT/BRL");
  } catch (e) {
    console.warn(e);
    failures.add("USDT/BRL");
  }
  setStatus();
}

// ---------- Câmera e microfone ----------
let cameraStream = null;
let micStream = null;
let audioCtx = null;
let meterFrame = 0;

function setPressed(btn, on) {
  btn.setAttribute("aria-pressed", String(on));
}

async function toggleCamera() {
  const btn = $("btn-camera");
  const video = $("camera-preview");
  if (cameraStream) {
    cameraStream.getTracks().forEach((t) => t.stop());
    cameraStream = null;
    video.srcObject = null;
    video.hidden = true;
    $("camera-off").hidden = false;
    setPressed(btn, false);
    return;
  }
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    video.srcObject = cameraStream;
    video.hidden = false;
    $("camera-off").hidden = true;
    setPressed(btn, true);
  } catch (e) {
    alertMedia("câmera", e);
  }
}

async function toggleMic() {
  const btn = $("btn-mic");
  if (micStream) {
    micStream.getTracks().forEach((t) => t.stop());
    micStream = null;
    cancelAnimationFrame(meterFrame);
    if (audioCtx) await audioCtx.close();
    audioCtx = null;
    $("mic-level").style.width = "0";
    $("orb").classList.remove("listening");
    setPressed(btn, false);
    return;
  }
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    audioCtx = new AudioContext();
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    audioCtx.createMediaStreamSource(micStream).connect(analyser);
    const buf = new Uint8Array(analyser.fftSize);
    const draw = () => {
      analyser.getByteTimeDomainData(buf);
      let peak = 0;
      for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
      $("mic-level").style.width = `${Math.min(100, (peak / 128) * 160)}%`;
      meterFrame = requestAnimationFrame(draw);
    };
    draw();
    $("orb").classList.add("listening");
    setPressed(btn, true);
  } catch (e) {
    alertMedia("microfone", e);
  }
}

function alertMedia(what, err) {
  console.warn(err);
  const insecure = !window.isSecureContext;
  $("status").textContent = insecure
    ? `Sem acesso à ${what}: abra pelo endereço HTTPS do Tailscale.`
    : `Sem acesso à ${what}: permita nas configurações do Safari.`;
  $("status").classList.add("error");
}

function toggleFullscreen() {
  const el = document.documentElement;
  if (document.fullscreenElement) document.exitFullscreen?.();
  else (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
}

// ---------- Inicialização ----------
async function start() {
  tickClock();
  setInterval(tickClock, 1000 * 15);

  let refresh = { weather: 600, crypto: 300, usdtbrl: 60 };
  try {
    refresh = (await getJSON("/api/config")).refresh_seconds;
  } catch (e) {
    console.warn(e);
  }
  loadWeather();
  loadCrypto();
  loadUsdt();
  setInterval(loadWeather, refresh.weather * 1000);
  setInterval(loadCrypto, refresh.crypto * 1000);
  setInterval(loadUsdt, refresh.usdtbrl * 1000);

  $("btn-camera").addEventListener("click", toggleCamera);
  $("btn-mic").addEventListener("click", toggleMic);
  $("btn-fullscreen").addEventListener("click", toggleFullscreen);
  window.addEventListener("online", setStatus);
  window.addEventListener("offline", setStatus);

  // Ao voltar para o app, atualiza tudo (o iOS pausa timers em segundo plano).
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      loadWeather();
      loadCrypto();
      loadUsdt();
    }
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch((e) => console.warn(e));
  }
}

start();
