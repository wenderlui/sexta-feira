// Confere a tela no tamanho do iPad deitado: alinhamento dos botões, sobreposição,
// rolagem, tela de AJUSTES e se as preferências ficam salvas no PC.
// Uso: node scripts/verificar-tela.mjs http://127.0.0.1:8000 [pasta-das-fotos]
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const base = process.argv[2] || "http://127.0.0.1:8000";
const shots = process.argv[3];
const problems = [];
const ok = (cond, msg) => { if (!cond) problems.push(msg); };

const browser = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
// iPad Air 11" deitado
const page = await browser.newPage({ viewport: { width: 1180, height: 820 }, deviceScaleFactor: 1 });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(base);
await page.waitForTimeout(2500);

// 1) Sem rolagem e sem nada saindo da tela
const size = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
ok(size.w <= 1180, `rolagem horizontal: largura ${size.w}`);
ok(size.h <= 820, `rolagem vertical: altura ${size.h}`);

// 2) Painéis não se sobrepõem
const boxes = await page.$$eval(".hud > section", (els) => els.map((e) => {
  const r = e.getBoundingClientRect(); return { n: e.className, x: r.x, y: r.y, w: r.width, h: r.height };
}));
for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
  const a = boxes[i], b = boxes[j];
  const overlap = a.x < b.x + b.w - 1 && b.x < a.x + a.w - 1 && a.y < b.y + b.h - 1 && b.y < a.y + a.h - 1;
  ok(!overlap, `painéis sobrepostos: ${a.n} e ${b.n}`);
}

// 3) Botões de baixo: mesma altura, mesmo centro, alvo de toque >= 44 px, sem quebrar linha
const btns = await page.$$eval(".controls > button", (els) => els.map((e) => {
  const r = e.getBoundingClientRect(); return { t: e.textContent.trim(), y: r.y + r.height / 2, h: r.height, w: r.width, bottom: r.bottom };
}));
const ys = btns.map((b) => b.y);
ok(Math.max(...ys) - Math.min(...ys) < 1.5, `botões desalinhados: centros ${ys.map((y) => y.toFixed(1)).join(", ")}`);
ok(btns.every((b) => b.h >= 44 && b.w >= 44), "algum botão menor que 44 px (difícil de tocar)");
ok(btns.every((b) => b.bottom <= 820), "botões saindo da tela");
const hudBottom = Math.max(...boxes.map((b) => b.y + b.h));
const barTop = await page.$eval(".controls", (e) => e.getBoundingClientRect().top);
ok(hudBottom <= barTop + 1, `painéis por baixo da barra de botões (${hudBottom.toFixed(0)} > ${barTop.toFixed(0)})`);

// 4) Relógio grande
const clockPx = await page.$eval("#clock-time", (e) => parseFloat(getComputedStyle(e).fontSize));
ok(clockPx >= 48, `relógio pequeno: ${clockPx}px`);
if (shots) await page.screenshot({ path: `${shots}/painel.png` });

// 5) AJUSTES abre, troca abas, fecha com ESC
await page.click("#btn-settings");
ok(await page.isVisible("#settings"), "AJUSTES não abriu");
for (const tab of ["tab-conexoes", "tab-cameras", "tab-voz", "tab-sobre", "tab-casa"]) {
  await page.click(`[data-tab=${tab}]`);
  if (tab === "tab-conexoes") await page.waitForSelector("#tab-conexoes .conn");
  if (tab === "tab-cameras") {
    await page.waitForFunction(() => document.querySelector("#rule-start").value !== "");
    if (shots) await page.screenshot({ path: `${shots}/ajustes-cameras.png` });
  }
  if (tab === "tab-casa") await page.waitForFunction(() => !document.querySelector("#casa-hint").textContent.includes("Carregando"));
  ok(await page.isVisible(`#${tab}`), `aba ${tab} não aparece`);
  if (tab === "tab-conexoes") {
    ok((await page.$$(".conn")).length >= 8, "faltam conexões no catálogo");
    const spill = await page.$$eval("#tab-conexoes .conn", (cards) => cards.filter((c) => {
      const box = c.getBoundingClientRect();
      return [...c.querySelectorAll("*")].some((e) => {
        const r = e.getBoundingClientRect();
        return r.width && (r.right > box.right + 1 || r.left < box.left - 1);
      });
    }).map((c) => c.querySelector("h3").textContent));
    ok(spill.length === 0, `conteúdo vazando dos cartões: ${spill.join(", ")}`);
    if (shots) await page.screenshot({ path: `${shots}/ajustes-conexoes.png` });
  }
}
const card = await page.$eval(".modal-card", (e) => { const r = e.getBoundingClientRect(); return { b: r.bottom, r: r.right }; });
ok(card.b <= 820 && card.r <= 1180, "janela de ajustes sai da tela");

// 6) Preferência salva no PC: muda a velocidade, recarrega a página e confere
await page.click("[data-tab=tab-voz]");
await page.waitForFunction(() => document.querySelector("#pref-edge").options.length > 0);
const before = await page.$eval("#pref-speed", (e) => e.value);
const target = before === "1.1" ? "1.05" : "1.1";
await page.$eval("#pref-speed", (e, v) => { e.value = v; e.dispatchEvent(new Event("input", { bubbles: true })); }, target);
await page.click("#voice-form button[type=submit]");
await page.waitForFunction(() => document.querySelector("#voice-saved").textContent.includes("Salvo"));
if (shots) await page.screenshot({ path: `${shots}/ajustes-voz.png` });
await page.keyboard.press("Escape");
ok(await page.isHidden("#settings"), "ESC não fechou os ajustes");
await page.reload(); await page.waitForTimeout(1500);
await page.click("#btn-settings"); await page.click("[data-tab=tab-voz]");
await page.waitForFunction(() => document.querySelector("#pref-edge").options.length > 0);
const after = await page.$eval("#pref-speed", (e) => e.value);
ok(after === target, `velocidade não ficou salva depois de recarregar (${before} -> ${target}, voltou ${after})`);
// devolve como estava
await page.$eval("#pref-speed", (e, v) => { e.value = v; e.dispatchEvent(new Event("input", { bubbles: true })); }, before);
await page.click("#voice-form button[type=submit]");

// 7) Celular em pé (iPhone): sem rolagem lateral, barra dentro da tela, botões tocáveis
const phone = await browser.newPage({ viewport: { width: 390, height: 664 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
phone.on("pageerror", (e) => errors.push(e.message));
await phone.goto(base); await phone.waitForTimeout(1500);
const pw = await phone.evaluate(() => document.documentElement.scrollWidth);
ok(pw <= 390, `celular: rolagem lateral (largura ${pw})`);
const pbtns = await phone.$$eval(".controls > button", (els) => els.filter((e) => e.offsetParent).map((e) => {
  const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, h: r.height, w: r.width, wrap: e.scrollWidth > e.clientWidth + 1 };
}));
ok(pbtns.every((b) => b.l >= 0 && b.r <= 390), "celular: botão saindo da tela");
ok(pbtns.every((b) => b.h >= 44 && b.w >= 44), "celular: botão menor que 44 px");
ok(pbtns.every((b) => !b.wrap), "celular: texto de botão cortado");
if (shots) await phone.screenshot({ path: `${shots}/celular.png` });
await phone.click("#btn-settings");
const pc = await phone.$eval(".modal-card", (e) => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right }; });
ok(pc.l >= 0 && pc.r <= 390, "celular: ajustes saem da tela");
ok(await phone.$eval(".tabs", (e) => e.scrollWidth <= e.clientWidth + 1), "celular: abas dos ajustes cortadas");

ok(errors.length === 0, `erros de JavaScript: ${errors.join(" | ")}`);
await browser.close();

if (problems.length) {
  console.log("PROBLEMAS:\n- " + problems.join("\n- "));
  process.exit(1);
}
console.log("Tela OK (iPad e celular): sem rolagem, painéis sem sobreposição, botões alinhados, ajustes salvando no PC.");
