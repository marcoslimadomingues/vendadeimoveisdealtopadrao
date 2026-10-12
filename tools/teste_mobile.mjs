// Emulação de celular (390x844, DPR 2, mobile) via Chrome DevTools Protocol: mede overflow horizontal
// e salva capturas em fatias. Requer Node >= 22 (WebSocket global) e Google Chrome.
//
// Uso: node tools/teste_mobile.mjs <tag> <url> [<url> ...]
//      PORT_APP=8947 node tools/teste_mobile.mjs depois http://127.0.0.1:8947/ http://127.0.0.1:8947/imoveis/
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const OUT = process.env.MOBILE_OUT || join(process.cwd(), "build", "mobile");
const [tag, ...urls] = process.argv.slice(2);
if (!tag || !urls.length) { console.error("uso: node tools/teste_mobile.mjs <tag> <url>..."); process.exit(2); }
mkdirSync(OUT, { recursive: true });

const porta = 9300 + Math.floor(Math.random() * 500);
const perfil = mkdtempSync(join(tmpdir(), "chrome-mobile-"));
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--no-sandbox", `--remote-debugging-port=${porta}`,
  `--user-data-dir=${perfil}`, "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
const dorme = (ms) => new Promise((r) => setTimeout(r, ms));

async function alvo() {
  for (let i = 0; i < 40; i++) {
    try {
      const lista = await (await fetch(`http://127.0.0.1:${porta}/json/list`)).json();
      const pg = lista.find((t) => t.type === "page");
      if (pg) return pg.webSocketDebuggerUrl;
    } catch { /* ainda subindo */ }
    await dorme(250);
  }
  throw new Error("Chrome não respondeu");
}

const ws = new WebSocket(await alvo());
await new Promise((r) => (ws.onopen = r));
let seq = 0; const pend = new Map(); const eventos = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); } else eventos.push(d.method);
};
const cmd = (method, params = {}) => new Promise((res) => { const id = ++seq; pend.set(id, res); ws.send(JSON.stringify({ id, method, params })); });

const MEDE = `(() => {
  const vw = document.documentElement.clientWidth, out = [];
  document.querySelectorAll('body *').forEach((e) => {
    const r = e.getBoundingClientRect();
    if (r.width > 0 && r.right > vw + 1) {
      let p = e.parentElement, rol = false;
      while (p && p !== document.body) { if (/(auto|scroll)/.test(getComputedStyle(p).overflowX)) { rol = true; break; } p = p.parentElement; }
      if (!rol) out.push(e.tagName.toLowerCase() + (e.className ? '.' + String(e.className).split(' ')[0] : '') + ' w=' + Math.round(r.width) + ' right=' + Math.round(r.right));
    }
  });
  const pequenos = [...document.querySelectorAll('a, button')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.height < 32 && getComputedStyle(e).display !== 'inline'; }).length;
  const largos = [...document.querySelectorAll('body *')].map((e) => ({ e, w: e.getBoundingClientRect().width }))
    .filter((x) => x.w > vw + 1).slice(0, 12)
    .map((x) => x.e.tagName.toLowerCase() + (x.e.className ? '.' + String(x.e.className).split(' ')[0] : '') + ' w=' + Math.round(x.w));
  return { vw, scrollWidth: document.documentElement.scrollWidth, estouram: out.length, exemplos: out.slice(0, 8), largos, alvosPequenos: pequenos };
})()`;

await cmd("Page.enable");
let n = 0;
for (const url of urls) {
  n++;
  await cmd("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await cmd("Emulation.setUserAgentOverride", { userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36" });
  await cmd("Page.navigate", { url });
  await dorme(1800);
  const med = (await cmd("Runtime.evaluate", { expression: MEDE, returnByValue: true })).result.result.value;
  const lm = (await cmd("Page.getLayoutMetrics")).result;
  const alt = Math.ceil(lm.cssContentSize.height);
  console.log(JSON.stringify({ url, altura: alt, ...med }));
  const fatia = 1400;
  for (let k = 0, y = 0; y < alt; k++, y += fatia) {
    const h = Math.min(fatia, alt - y);
    const shot = await cmd("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      clip: { x: 0, y, width: 390, height: h, scale: 1 } });
    writeFileSync(join(OUT, `${tag}_${n}_${k}.png`), Buffer.from(shot.result.data, "base64"));
  }
}
ws.close(); chrome.kill();
