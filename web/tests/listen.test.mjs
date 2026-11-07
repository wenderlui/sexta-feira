import test from "node:test";
import assert from "node:assert/strict";
import { Segmenter, downsample, encodeWav, rms } from "../listen.js";

const RATE = 48000, CHUNK = 4096;
const noise = (amp) => Float32Array.from({ length: CHUNK }, () => (Math.random() * 2 - 1) * amp);
const tone = (amp) => Float32Array.from({ length: CHUNK }, (_, i) => Math.sin(i / 8) * amp);

test("guarda o começo da fala (pré-gravação) e entrega quando ela termina", () => {
  const seg = new Segmenter(RATE);
  for (let i = 0; i < 30; i++) assert.equal(seg.push(noise(0.002)), null);
  // Voz baixa, como de 2 metros de distância.
  for (let i = 0; i < 12; i++) assert.equal(seg.push(tone(0.05)), null);
  assert.ok(seg.recording);
  let out = null;
  for (let i = 0; i < 25 && !out; i++) out = seg.push(noise(0.002));
  assert.ok(out, "deveria terminar depois do silêncio");
  const seconds = out.samples.length / RATE;
  assert.ok(seconds > 12 * CHUNK / RATE + 0.8, `inclui pré-gravação (${seconds.toFixed(2)} s)`);
  assert.ok(out.peak > 0.04);
});

test("ignora estalos curtos", () => {
  const seg = new Segmenter(RATE);
  for (let i = 0; i < 20; i++) seg.push(noise(0.002));
  seg.push(tone(0.3)); seg.push(tone(0.3));
  let out = null;
  for (let i = 0; i < 25; i++) out = seg.push(noise(0.002)) || out;
  assert.equal(out, null);
});

test("WAV 16 kHz com volume normalizado", () => {
  const pcm = downsample(tone(0.05), RATE, 16000);
  assert.equal(pcm.length, Math.floor(CHUNK / 3));
  const wav = new DataView(encodeWav(pcm, 16000));
  assert.equal(String.fromCharCode(wav.getUint8(0), wav.getUint8(1), wav.getUint8(2), wav.getUint8(3)), "RIFF");
  assert.equal(wav.getUint32(24, true), 16000);
  let peak = 0;
  for (let i = 44; i < wav.byteLength; i += 2) peak = Math.max(peak, Math.abs(wav.getInt16(i, true)));
  assert.ok(peak > 0.8 * 0x7fff);
  assert.ok(rms(pcm) > 0);
});
