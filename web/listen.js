// Escuta contínua em PCM: guarda sempre o último segundo de áudio para não cortar
// o começo da frase ("Sexta-feira…") e decide sozinha quando a fala começou e terminou.
// Funções puras, testadas em web/tests/listen.test.mjs.

export function rms(samples) {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return samples.length ? Math.sqrt(sum / samples.length) : 0;
}

/**
 * Recebe pedaços de áudio (Float32Array) e devolve a fala completa quando ela termina.
 * O limiar se adapta ao ruído da sala, para funcionar com o iPad a alguns metros.
 */
export class Segmenter {
  constructor(sampleRate, opts = {}) {
    this.rate = sampleRate;
    this.o = {
      prerollMs: 1000, silenceMs: 1500, maxMs: 15000, minSpeechMs: 350,
      startChunks: 2, factor: 3, minLevel: 0.006, ...opts,
    };
    this.floor = 0.004;     // ruído de fundo estimado
    this.pre = [];          // últimos pedaços antes da fala
    this.preLen = 0;
    this.cur = null;        // fala em andamento
    this.loudRun = 0;
  }

  threshold() { return Math.max(this.o.minLevel, this.floor * this.o.factor); }

  get recording() { return !!this.cur; }

  reset() { this.cur = null; this.loudRun = 0; this.pre = []; this.preLen = 0; }

  /** Devolve {samples, speechMs, peak} quando uma fala termina; senão null. */
  push(chunk) {
    const level = rms(chunk);
    const loud = level > this.threshold();
    const ms = (chunk.length / this.rate) * 1000;
    if (!this.cur) {
      // Fora da fala: atualiza o ruído de fundo devagar.
      if (!loud) this.floor = this.floor * 0.95 + level * 0.05;
      this.pre.push(chunk); this.preLen += chunk.length;
      const maxPre = (this.o.prerollMs / 1000) * this.rate;
      while (this.preLen - this.pre[0].length > maxPre) this.preLen -= this.pre.shift().length;
      this.loudRun = loud ? this.loudRun + 1 : 0;
      if (this.loudRun >= this.o.startChunks) {
        this.cur = { chunks: this.pre, ms: 0, speechMs: 0, quietMs: 0, peak: 0 };
        this.pre = []; this.preLen = 0;
      }
      return null;
    }
    const c = this.cur;
    c.chunks.push(chunk);
    c.ms += ms;
    for (let i = 0; i < chunk.length; i++) c.peak = Math.max(c.peak, Math.abs(chunk[i]));
    if (loud) { c.speechMs += ms; c.quietMs = 0; } else c.quietMs += ms;
    if (c.quietMs < this.o.silenceMs && c.ms < this.o.maxMs) return null;
    this.cur = null; this.loudRun = 0;
    if (c.speechMs < this.o.minSpeechMs) return null;
    return { samples: concat(c.chunks), speechMs: Math.round(c.speechMs), peak: c.peak };
  }
}

export function concat(chunks) {
  const out = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
  let o = 0;
  for (const c of chunks) { out.set(c, o); o += c.length; }
  return out;
}

/** Reduz para 16 kHz (o que o Whisper usa) tirando a média de cada bloco. */
export function downsample(samples, fromRate, toRate = 16000) {
  if (fromRate <= toRate) return samples;
  const ratio = fromRate / toRate;
  const out = new Float32Array(Math.floor(samples.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const a = Math.floor(i * ratio), b = Math.min(samples.length, Math.floor((i + 1) * ratio));
    let s = 0;
    for (let j = a; j < b; j++) s += samples[j];
    out[i] = s / Math.max(1, b - a);
  }
  return out;
}

/** WAV 16 bits mono, com o volume ajustado para a voz de longe chegar clara. */
export function encodeWav(samples, rate, { normalize = true } = {}) {
  let peak = 0;
  for (let i = 0; i < samples.length; i++) peak = Math.max(peak, Math.abs(samples[i]));
  const gain = normalize && peak > 0 ? Math.min(20, 0.9 / peak) : 1;
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i] * gain));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buf;
}

// Divide a resposta em frases: a primeira começa a tocar enquanto o PC gera as próximas.
export function sentences(text, min = 40) {
  const parts = text.match(/[^.!?…]+[.!?…]*["')\]]*\s*/g) || [text];
  const out = [];
  for (const p of parts) {
    if (out.length && (out[out.length - 1].length < min || p.trim().length < 12)) out[out.length - 1] += p;
    else out.push(p);
  }
  return out.map((p) => p.trim()).filter(Boolean);
}
