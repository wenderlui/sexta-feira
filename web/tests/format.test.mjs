import { test } from "node:test";
import assert from "node:assert/strict";
import { formatMoney, formatChange, weekdayShort } from "../format.js";

test("formatMoney usa padrão brasileiro", () => {
  assert.equal(formatMoney(101000.5), "101.001");
  assert.equal(formatMoney(5.4123), "5,41");
  assert.equal(formatMoney(0.2345), "0,2345");
  assert.equal(formatMoney(null), "--");
});

test("formatChange marca alta e baixa", () => {
  assert.deepEqual(formatChange(1.5), { text: "+1,50%", cls: "up" });
  assert.deepEqual(formatChange(-2.1), { text: "-2,10%", cls: "down" });
  assert.deepEqual(formatChange(undefined), { text: "--", cls: "" });
});

test("weekdayShort não muda de dia por causa do fuso", () => {
  assert.match(weekdayShort("2026-11-07"), /^sáb/);
});

import { sparkPaths, greetingFor, formatUptime } from "../format.js";

test("sparkPaths desenha linha e tendência", () => {
  const p = sparkPaths([1, 2, 3], 100, 20, 0);
  assert.equal(p.line, "M0.0 20.0L50.0 10.0L100.0 0.0");
  assert.equal(p.trend, "up");
  assert.equal(sparkPaths([5]), null);
  assert.equal(sparkPaths([3, 3]).trend, "");
});

test("greetingFor e formatUptime", () => {
  assert.equal(greetingFor(8), "bom dia");
  assert.equal(greetingFor(20), "boa noite");
  assert.equal(formatUptime(3 * 3600 + 120), "3h 2min");
  assert.equal(formatUptime(90000), "1d 1h");
});
