// Paneli yerelde gerçek kapı koduyla (worker.js) sunar; GitHub/Telegram taklit edilir, ağ isteği yapılmaz.
//   KOK=<state klasörü> PORT=8787 SAAT=<ISO> [VIDEO=<yerel video>] node tests/panel/sunucu.mjs
// /__giris: giriş bağlantısı üretip panele yönlendirir (Telegram'daki /panel bağlantısının yerine).
import { createServer } from "node:http";
import { readFileSync, statSync } from "node:fs";
import worker from "../../cloudflare/worker.js";
import { ORTAM, fetchKur, ctxYap, saatKurAkan, cacheKur, imza } from "./sahte.mjs";

const PORT = Number(process.env.PORT || 8787);
const KOK = process.env.KOK;
if (process.env.SAAT) saatKurAkan(Date.parse(process.env.SAAT));
cacheKur();
const yerel = `http://127.0.0.1:${PORT}`;
const { cagrilar } = fetchKur({ kok: KOK, imzaliAdres: `${yerel}/__imzali/` });

function videoGonder(req, res) {
  const yol = process.env.VIDEO;
  if (!yol) { res.writeHead(404).end(); return; }
  const boy = statSync(yol).size;
  const m = /bytes=(\d*)-(\d*)/.exec(req.headers.range || "");
  const tur = yol.endsWith(".webm") ? "video/webm" : "video/mp4";
  if (m) {
    const a = m[1] ? Number(m[1]) : 0, b = m[2] ? Number(m[2]) : boy - 1;
    res.writeHead(206, { "content-type": tur, "content-range": `bytes ${a}-${b}/${boy}`, "accept-ranges": "bytes",
      "content-length": b - a + 1 });
    res.end(readFileSync(yol).subarray(a, b + 1));
  } else {
    res.writeHead(200, { "content-type": tur, "content-length": boy, "accept-ranges": "bytes" });
    res.end(readFileSync(yol));
  }
}

createServer(async (req, res) => {
  try {
    if (req.url.startsWith("/__imzali/video.mp4")) return videoGonder(req, res);
    if (req.url === "/__giris") {
      const t = await imza("giris", Math.floor(Date.now() / 1000) + 300);
      res.writeHead(302, { location: "/panel/giris?t=" + t }).end();
      return;
    }
    if (req.url === "/__cagrilar") {
      res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(cagrilar));
      return;
    }
    const parcalar = [];
    for await (const p of req) parcalar.push(p);
    const govde = parcalar.length ? Buffer.concat(parcalar) : undefined;
    const headers = new Headers();
    for (const [k, v] of Object.entries(req.headers)) headers.set(k, Array.isArray(v) ? v.join(", ") : v);
    const istek = new Request(yerel + req.url, { method: req.method, headers,
      body: ["GET", "HEAD"].includes(req.method) ? undefined : govde, redirect: "manual" });
    const { ctx } = ctxYap();
    const r = await worker.fetch(istek, { ...ORTAM }, ctx);
    const h = {};
    r.headers.forEach((v, k) => { if (k !== "set-cookie") h[k] = v; });
    const cerez = r.headers.getSetCookie();
    if (cerez.length) h["set-cookie"] = cerez;
    res.writeHead(r.status, h);
    res.end(Buffer.from(await r.arrayBuffer()));
  } catch (e) {
    console.error(e);
    res.writeHead(500).end(String(e));
  }
}).listen(PORT, "127.0.0.1", () => console.log("hazir " + yerel));
