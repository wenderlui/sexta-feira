// Conversa por voz: ouvir (Whisper no PC), pensar (Ollama) e falar (voz do iPad).
const $ = (id) => document.getElementById(id);
import { Segmenter, downsample, encodeWav } from "./listen.js";

const sexta = window.sexta;

// Aceita também como o Whisper às vezes escreve: "sexta feira", "sesta", "cesta", "6ª feira".
const WAKE = /^[\s,.!?:"'-]*(?:(?:ei|oi|ok|olá|ola|hey)[\s,]+)?(?:sexta|sesta|cesta|sexto|6ª|6a)(?:[\s-]*feira)?\b[\s,.!?:]*/i;
const WAKE_ANYWHERE = /\b(?:sexta|sesta|cesta)(?:[\s-]*feira)?\b[\s,.!?:]*/i;
const FOLLOW_UP_MS = 20000;      // depois de responder, aceita a próxima fala sem "Sexta-feira"
const HISTORY_KEY = "sexta.chat.v1";

let history = [];
try { history = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]").slice(-20); } catch { history = []; }
let busy = false;
let lastReplyAt = 0;
let continuous = false;

// Manda um recado de diagnóstico para o registro do PC (logs/servidor.log).
function diag(msg) {
  fetch("/api/log", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ msg }) }).catch(() => {});
}
sexta.diag = diag;

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

// Voz do PC (Kokoro), tocada pelo mesmo áudio do microfone: no iPad é o único
// jeito de ela falar enquanto o microfone está ligado.
let serverTtsOff = false;
let playing = null;
let playCtx = null;
function outputCtx() {
  if (sexta.audioCtx) return sexta.audioCtx;
  playCtx ||= new (window.AudioContext || window.webkitAudioContext)();
  return playCtx;
}
document.addEventListener("pointerdown", () => { playCtx?.resume?.(); });

function stopSpeaking() {
  window.speechSynthesis?.cancel();
  if (playing) { try { playing.stop(); } catch { /* ok */ } playing = null; }
}
sexta.stopSpeaking = stopSpeaking;

async function speakServer(text) {
  const t0 = Date.now();
  const r = await fetch("/api/tts", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
    signal: AbortSignal.timeout?.(20000),
  });
  if (r.status === 503) { serverTtsOff = true; throw new Error("tts-off"); }
  if (!r.ok) throw new Error(`voz do PC falhou (${r.status})`);
  const data = await r.arrayBuffer();
  const ctx = outputCtx();
  if (ctx.state !== "running") await ctx.resume().catch(() => {});
  const buffer = await new Promise((ok, fail) => ctx.decodeAudioData(data, ok, fail));
  sexta.setState("speaking");
  diag(`voz do PC: ${Date.now() - t0} ms para gerar, ${buffer.duration.toFixed(1)} s de fala, áudio ${ctx.state}`);
  await new Promise((resolve) => {
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    const guard = setTimeout(resolve, buffer.duration * 1000 + 1500);
    src.onended = () => { clearTimeout(guard); resolve(); };
    playing = src;
    src.start();
  });
  playing = null;
}

async function speak(text) {
  if (sexta.muted || !text) return;
  if (!serverTtsOff) {
    try { return await speakServer(text); }
    catch (e) { if (e.message !== "tts-off") diag(`voz do PC: ${e.message}`); }
  }
  return speakBrowser(text);
}

// Reserva: voz do próprio Safari (pode sair muda com o microfone ligado no iPad).
function speakBrowser(text) {
  return new Promise((resolve) => {
    if (sexta.muted || !window.speechSynthesis || !text) return resolve();
    const synth = window.speechSynthesis;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "pt-BR";
    if (voice) u.voice = voice;
    u.rate = 1.05;
    u.volume = 1;
    const t0 = Date.now();
    let started = false, finished = false;
    // Se o iOS não avisar que terminou, não deixamos a escuta travada.
    const guard = setTimeout(() => done("tempo esgotado"), 5000 + text.length * 150);
    async function done(how) {
      if (finished) return;
      finished = true;
      clearTimeout(guard);
      diag(`fala ${how}: ${Date.now() - t0} ms, começou=${started}, voz ${voice?.name || "padrão"}, desbloqueada=${unlocked}`);
      // Religa o áudio do microfone, pausado para a voz poder sair no iPad.
      try { await sexta.audioCtx?.resume(); } catch { /* ok */ }
      resolve();
    }
    u.onstart = () => { started = true; };
    u.onend = () => done("terminou");
    u.onerror = (e) => done(`erro ${e.error || "?"}`);
    sexta.setState("speaking");
    // No iOS, com o microfone gravando, a voz pode sair muda: pausamos a captura enquanto ela fala.
    Promise.resolve(sexta.audioCtx?.suspend?.()).catch(() => {}).finally(() => {
      // Pequena pausa depois do cancel(): o Safari às vezes ignora um speak() imediato.
      setTimeout(() => synth.speak(u), 120);
    });
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
    if (continuous) {
      // O iOS costuma pausar o microfone enquanto fala; reabre antes de ouvir de novo.
      try { diag(`depois de falar: ${await sexta.reviveMic()}`); }
      catch (e) { diag(`não reabriu o microfone: ${e.message}`); }
    }
  } catch (e) {
    console.warn(e);
    diag(`chat falhou: ${e.message}`);
    addMsg("sys", `Não consegui responder: ${e.message}`);
  } finally {
    busy = false;
    sexta.setState(continuous ? "listening" : "idle", continuous ? (lastReplyAt ? "PODE CONTINUAR" : "ESCUTANDO") : undefined);
    if (continuous) setTimeout(() => {
      if (continuous && !busy && Date.now() - lastReplyAt >= FOLLOW_UP_MS) sexta.setState("listening", "ESCUTANDO");
    }, FOLLOW_UP_MS + 100);
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
  stopSpeaking();
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
    } else { addMsg("sys", e.message); diag(`transcrição falhou: ${e.message}`); }
    sexta.setState(continuous ? "listening" : "idle");
    return;
  }
  text = text.trim();
  if (!text) { sexta.setState(continuous ? "listening" : "idle"); return; }
  if (requireWake && Date.now() - lastReplyAt > FOLLOW_UP_MS) {
    if (!WAKE.test(text) && !WAKE_ANYWHERE.test(text.slice(0, 40))) {
      // Mostra o que ouviu, para você saber que o microfone funciona.
      sexta.setState("listening", "ESCUTANDO");
      showHeard(text);
      return;
    }
  }
  text = text.replace(WAKE, "").replace(WAKE_ANYWHERE, "").trim() || "Oi";
  await ask(text);
}

let heardTimer = 0;
function showHeard(text) {
  const label = $("core-label");
  label.textContent = `OUVI: ${text.slice(0, 40)}`;
  label.title = "Comece com \"Sexta-feira\" para ela responder.";
  clearTimeout(heardTimer);
  heardTimer = setTimeout(() => { if (continuous && !busy) sexta.setState("listening", "ESCUTANDO"); }, 3500);
}

talk.addEventListener("pointerdown", holdStart);
talk.addEventListener("pointerup", holdEnd);
talk.addEventListener("pointercancel", holdEnd);
talk.addEventListener("pointerleave", () => hold && holdEnd());
talk.addEventListener("contextmenu", (e) => e.preventDefault());

// --- Escuta automática com palavra de ativação ---
// Liga sozinha ao abrir; só para quando você toca em MUDO (a escolha fica salva neste iPad).
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

// Captura PCM direto do microfone (com 1 s de pré-gravação), em vez de ligar o
// gravador só depois que a fala começa: assim o "Sexta-feira" do começo não se perde.
let tap = null;
function attachTap() {
  const ctx = sexta.audioCtx, src = sexta.micSource;
  if (!ctx || !src || tap?.src === src) return;
  detachTap();
  const node = ctx.createScriptProcessor(4096, 1, 1);
  const seg = new Segmenter(ctx.sampleRate);
  node.onaudioprocess = (ev) => {
    const input = ev.inputBuffer.getChannelData(0);
    const paused = !continuous || busy || hold || processing || document.body.dataset.state === "speaking";
    if (paused) { if (seg.recording) seg.reset(); return; }
    const wasRec = seg.recording;
    const done = seg.push(new Float32Array(input));
    if (!wasRec && seg.recording) sexta.setState("listening", "OUVINDO");
    if (done) onUtterance(done, ctx.sampleRate);
    else if (wasRec && !seg.recording) sexta.setState("listening", "ESCUTANDO");
  };
  src.connect(node);
  // O Safari só processa se o nó estiver ligado à saída; o ganho zero garante silêncio.
  const mute = ctx.createGain();
  mute.gain.value = 0;
  node.connect(mute);
  mute.connect(ctx.destination);
  tap = { node, src, seg };
}
function detachTap() {
  if (!tap) return;
  try { tap.src.disconnect(tap.node); } catch { /* ok */ }
  try { tap.node.disconnect(); } catch { /* ok */ }
  tap.node.onaudioprocess = null;
  tap = null;
}

async function onUtterance({ samples, speechMs, peak }, rate) {
  processing = true;
  try {
    const pcm = downsample(samples, rate, 16000);
    const blob = new Blob([encodeWav(pcm, 16000)], { type: "audio/wav" });
    diag(`gravei ${Math.round((pcm.length / 16000) * 1000)} ms (fala ${speechMs} ms), pico ${peak.toFixed(2)}`);
    await handleAudio(blob, { requireWake: true });
  } finally {
    processing = false;
  }
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
  attachTap();
  let lastSound = Date.now(), warned = false;
  diag(`escuta ligada; áudio ${sexta.audioRunning?.() ? "ativo" : "pausado"}; ${sexta.audioCtx?.sampleRate} Hz`);
  vadTimer = setInterval(() => {
    attachTap(); // o microfone pode ter sido reaberto depois de ela falar
    if ((sexta.level || 0) > 0.01) {
      lastSound = Date.now();
      if (warned) { warned = false; sexta.setStatus(""); }
    } else if (!warned && Date.now() - lastSound > 8000) {
      // Nível zerado por muito tempo: no iPad, quase sempre é o áudio pausado.
      warned = true;
      sexta.setStatus("não estou ouvindo nada: toque na tela");
      diag(`microfone em silêncio total; áudio ${sexta.audioRunning?.() ? "ativo" : "pausado"}`);
    }
  }, 500);
  return true;
}

async function stopListening() {
  continuous = false;
  clearInterval(vadTimer);
  detachTap();
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
