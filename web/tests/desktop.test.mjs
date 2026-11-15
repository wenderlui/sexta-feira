import test from "node:test";
import assert from "node:assert/strict";
import { escapeHtml, miniMarkdown, statusClass, logLevel, formatUptime, trimHistory } from "../desktop-lib.js";

test("escapa HTML (nada de script vindo da IA)", () => {
  assert.equal(escapeHtml('<img src=x onerror="a">'), "&lt;img src=x onerror=&quot;a&quot;&gt;");
  assert.ok(!miniMarkdown("<script>alert(1)</script>").includes("<script>"));
});

test("markdown simples", () => {
  assert.equal(miniMarkdown("**oi** `x`"), "<strong>oi</strong> <code>x</code>");
  assert.match(miniMarkdown("- a\n- b"), /<ul><li>a<\/li><li>b<\/li><\/ul>/);
  assert.match(miniMarkdown("```py\nprint(1)\n```"), /<pre><code>print\(1\)\n<\/code><\/pre>/);
});

test("estado dos serviços", () => {
  assert.equal(statusClass(true), "ok");
  assert.equal(statusClass(false), "bad");
  assert.equal(statusClass(null), "off");
});

test("nível das linhas do registro", () => {
  assert.equal(logLevel("2026 sexta ERROR falhou"), "error");
  assert.equal(logLevel("2026 sexta WARNING lento"), "warn");
  assert.equal(logLevel("2026 sexta.ipad INFO mic"), "ipad");
  assert.equal(logLevel("INFO ok"), "info");
});

test("tempo ligado", () => {
  assert.equal(formatUptime(59), "0min");
  assert.equal(formatUptime(3720), "1h 2min");
  assert.equal(formatUptime(90000), "1d 1h");
});

test("histórico limitado", () => {
  assert.equal(trimHistory(Array.from({ length: 50 }, (_, i) => i), 40)[0], 10);
});
