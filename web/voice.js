// Conversa por voz: ouvir (Whisper no PC), pensar (Ollama) e falar (voz do iPad).
const $ = (id) => document.getElementById(id);
const sexta = window.sexta;

const WAKE = /\bsexta(?:[\s-]*feira)?\b[\s,.!?:]*/i;
const FOLLOW_UP_MS = 10000;      // depois de responder, aceita a próxima fala sem "Sexta-feira"
const HISTORY_KEY = "sexta.chat.v1";

let history = [];
try { history = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]").slice(-20); } catch { history = []; }
let busy = false;
let lastReplyAt = 0;
let continuous = false;

// ---------- Registro da conversa ----------
function addMsg(role, text, sources = []) {
  const li = document.createElement("li");
  li.className = role === "user" ? "user" : role === "assistant" ? "ai" : "sys";
  li.textContent = text;
  const links = sources.filter((s) => s.href).slice(0, 3);
  if (links.length) {
    const span = document.createElement("span");
    span.className = "src";
    span.append("Fontes: ");
    links.forEach((s, i) => {
      const a = document.createElement("a");
      a.href = s.href; a.target = "_blank"; a.rel = "noopener";
      a.textContent = new URL(s.href).hostname.replace(/^www\./, "");
      span.append(a);
      if (i < links.length - 1) span.append(" · ");
    });
    li.append(span);
  }
  const log = $("chat-log");
  log.append(li);
  while (log.children.length > 40) log.firstChild.remove();
  log.scrollTop = log.scrollHeight;
}
function remember(role, content) {
  history.push({ role, content });
  history = history.slice(-20);
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history)); } catch { /* ok */ }
}
for (const m of history.slice(-6)) addMsg(m.role, m.content);
if (!history.length) addMsg("sys", "Estou ouvindo: comece com \"Sexta-feira…\". Também dá para segurar FALAR ou escrever abaixo.");

// ---------- Falar (voz do próprio iPad) ----------
let voice = null;
function pickVoice() {
  const voices = window.speechSynthesis?.getVoices() || [];
  const pt = voices.filter((v) => /^pt[-_]BR/i.test(v.lang));
  voice = pt.find((v) => /luciana|francisca|premium|enhanced|aprimorad/i.test(v.name)) || pt[0] || null;
}
if (window.speechSynthesis) {
  pickVoice();
  window.speechSynthesis.onvoiceschanged = pickVoice;
}
let unlocked = false;
function unlockSpeech() {
  // O iOS só libera a fala depois de um toque do usuário.
  if (unlocked || !window.speechSynthesis) return;
  unlocked = true;
  const u = new SpeechSynthesisUtterance(" ");
  u.volume = 0;
  window.speechSynthesis.speak(u);
}
document.addEventListener("pointerdown", unlockSpeech, { once: true });

function speak(text) {
  return new Promise((resolve) => {
    if (sexta.muted || !window.speechSynthesis || !text) return resolve();
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "pt-BR";
    if (voice) u.voice = voice;
    u.rate = 1.05;
    u.onend = u.onerror = () => resolve();
    sexta.setState("speaking");
    window.speechSynthesis.speak(u);
  });
}

// ---------- Câmera: um quadro para a visão ----------
function grabFrame() {
  const video = $("camera-preview");
  if (!sexta.cameraStream || !video.videoWidth) return null;
  const scale = Math.min(1, 768 / video.videoWidth);
  const c = document.createElement("canvas");
  c.width = Math.round(video.videoWidth * scale);
  c.height = Math.round(video.videoHeight * scale);
  c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", 0.75).split(",")[1];
}

// ---------- Pensar ----------
async function ask(text) {
  text = (text || "").trim();
  if (!text || busy) return;
  busy = true;
  addMsg("user", text);
  remember("user", text);
  sexta.setState("thinking");
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history, image: grabFrame() }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || `erro ${r.status}`);
    const reply = data.text || "Não consegui pensar numa resposta.";
    addMsg("assistant", reply, data.sources || []);
    remember("assistant", reply);
    await speak(reply);
    lastReplyAt = Date.now();
  } catch (e) {
    console.warn(e);
    addMsg("sys", `Não consegui responder: ${e.message}`);
  } finally {
    busy = false;
    sexta.setState(continuous ? "listening" : "idle", continuous ? "ESCUTANDO" : undefined);
  }
}
sexta.ask = ask;

// ---------- Ouvir ----------
function recorderMime() {
  const types = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm"];
  return types.find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || "";
}

function record(stream) {
  const mimeType = recorderMime();
  const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks = [];
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const done = new Promise((resolve) => {
    rec.onstop = () => resolve(new Blob(chunks, { type: rec.mimeType || mimeType || "audio/mp4" }));
  });
  rec.start();
  return { stop: () => { if (rec.state !== "inactive") rec.stop(); return done; }, startedAt: Date.now() };
}

async function transcribe(blob) {
  const r = await fetch("/api/transcribe", { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
  if (r.status === 503) { const e = new Error("stt-off"); e.code = 503; throw e; }
  if (!r.ok) throw new Error(`transcrição falhou (${r.status})`);
  return (await r.json()).text || "";
}

// Reserva: reconhecimento de voz do próprio Safari, se o Whisper não estiver no PC.
const BrowserSR = window.SpeechRecognition || window.webkitSpeechRecognition;
let serverSttOff = false;

// --- Segurar para falar ---
let hold = null;
let holdSR = null;
const talk = $("btn-talk");

async function holdStart(e) {
  e.preventDefault();
  if (busy || hold || holdSR) return;
  unlockSpeech();
  window.speechSynthesis?.cancel();
  talk.classList.add("active");
  sexta.setState("listening");
  if (serverSttOff && BrowserSR) {
    holdSR = new BrowserSR();
    holdSR.lang = "pt-BR"; holdSR.interimResults = false;
    holdSR.onresult = (ev) => ask(ev.results[0][0].transcript);
    holdSR.onend = () => { holdSR = null; if (!busy) sexta.setState("idle"); };
    holdSR.start();
    return;
  }
  try {
    hold = record(await sexta.ensureMic());
  } catch (err) {
    sexta.mediaError("microfone", err);
    talk.classList.remove("active"); sexta.setState("idle");
  }
}

async function holdEnd() {
  talk.classList.remove("active");
  if (holdSR) { holdSR.stop(); return; }
  if (!hold) return;
  const h = hold; hold = null;
  const blob = await h.stop();
  if (!continuous) sexta.releaseMic();
  if (Date.now() - h.startedAt < 400) { sexta.setState("idle"); return; }
  await handleAudio(blob, { requireWake: false });
}

async function handleAudio(blob, { requireWake }) {
  sexta.setState("thinking", "TRANSCREVENDO");
  let text = "";
  try {
    text = await transcribe(blob);
  } catch (e) {
    if (e.code === 503) {
      serverSttOff = true;
      if (continuous) { await stopListening(); showMuted(true); }
      addMsg("sys", BrowserSR
        ? "O Whisper ainda não está instalado no PC. Vou usar o reconhecimento do Safari ao segurar FALAR."
        : "O Whisper ainda não está instalado no PC. Escreva sua pergunta por enquanto.");
    } else addMsg("sys", e.message);
    sexta.setState(continuous ? "listening" : "idle");
    return;
  }
  text = text.trim();
  if (!text) { sexta.setState(continuous ? "listening" : "idle"); return; }
  if (requireWake && Date.now() - lastReplyAt > FOLLOW_UP_MS) {
    if (!WAKE.test(text)) { sexta.setState("listening", "ESCUTANDO"); return; }
  }
  text = text.replace(WAKE, "").trim() || "Oi";
  await ask(text);
}

talk.addEventListener("pointerdown", holdStart);
talk.addEventListener("pointerup", holdEnd);
talk.addEventListener("pointercancel", holdEnd);
talk.addEventListener("pointerleave", () => hold && holdEnd());
talk.addEventListener("contextmenu", (e) => e.preventDefault());

// --- Escuta automática com palavra de ativação ---
// Liga sozinha ao abrir; só para quando você toca em MUDO (a escolha fica salva neste iPad).
const VAD = { on: 0.1, startMs: 160, silenceMs: 1300, maxMs: 15000 };
const MUTED_KEY = "sexta.micMuted";
let vadTimer = 0;
let processing = false;

function savedMuted() {
  try { return localStorage.getItem(MUTED_KEY) === "1"; } catch { return false; }
}
function saveMuted(on) {
  try { localStorage.setItem(MUTED_KEY, on ? "1" : "0"); } catch { /* ok */ }
}
function showMuted(on) {
  const btn = $("btn-mic");
  btn.setAttribute("aria-pressed", String(on));
  btn.querySelector(".lbl").textContent = on ? "MUDO" : "OUVINDO";
  btn.title = on ? "Microfone desligado. Toque para voltar a ouvir." : "Ouvindo. Toque para silenciar o microfone.";
}

async function startListening() {
  if (continuous) return true;
  if (serverSttOff) {
    addMsg("sys", "A escuta automática precisa do Whisper no PC. Por enquanto, segure FALAR.");
    return false;
  }
  try { await sexta.ensureMic(); } catch (err) { sexta.mediaError("microfone", err); return false; }
  continuous = true;
  sexta.setState("listening", "ESCUTANDO");
  let loudSince = 0, quietSince = 0, rec = null;
  vadTimer = setInterval(async () => {
    if (!continuous || busy || hold || processing || document.body.dataset.state === "speaking") return;
    const now = Date.now();
    const loud = (sexta.level || 0) > VAD.on;
    if (!rec) {
      loudSince = loud ? loudSince || now : 0;
      if (loudSince && now - loudSince > VAD.startMs) {
        rec = record(sexta.micStream);
        quietSince = 0;
        sexta.setState("listening", "OUVINDO");
      }
      return;
    }
    quietSince = loud ? 0 : quietSince || now;
    if ((quietSince && now - quietSince > VAD.silenceMs) || now - rec.startedAt > VAD.maxMs) {
      const r = rec; rec = null; loudSince = 0;
      processing = true;
      try {
        const blob = await r.stop();
        if (now - r.startedAt > 700) await handleAudio(blob, { requireWake: true });
        else sexta.setState("listening", "ESCUTANDO");
      } finally {
        processing = false;
      }
    }
  }, 50);
  return true;
}

async function stopListening() {
  continuous = false;
  clearInterval(vadTimer);
  await sexta.releaseMic();
  sexta.setState("idle", "MICROFONE MUDO");
}

$("btn-mic").addEventListener("click", async () => {
  unlockSpeech();
  const muted = $("btn-mic").getAttribute("aria-pressed") === "true";
  if (muted) {
    if (await startListening()) { saveMuted(false); showMuted(false); }
  } else {
    await stopListening();
    saveMuted(true); showMuted(true);
  }
});

// Ao abrir o app: começa a ouvir, a não ser que você tenha deixado no MUDO.
(async () => {
  const muted = savedMuted();
  showMuted(muted);
  if (muted) { sexta.setState("idle", "MICROFONE MUDO"); return; }
  if (!(await startListening())) { showMuted(true); }
})();

// --- Texto ---
$("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  unlockSpeech();
  const input = $("chat-input");
  const text = input.value;
  input.value = "";
  input.blur();
  ask(text);
});
