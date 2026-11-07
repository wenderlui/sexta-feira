import { test } from "node:test";
import assert from "node:assert/strict";
import { formatMoney, formatChange, weekdayShort } from "../format.js";

test("formatMoney usa padrão brasileiro", () => {
  assert.equal(formatMoney(101000.5), "101.000,50");
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
