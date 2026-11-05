// Kapı (worker.js + panel.js) testleri için sahte ortam: GitHub, Telegram ve Cloudflare Cache API taklit edilir.
// Hiçbir gerçek ağ isteği yapılmaz; bilinmeyen bir adrese istek giderse hata fırlatılır.
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

export const BURASI = dirname(fileURLToPath(import.meta.url));
export const FIKSTUR = join(BURASI, "fixtures", "state");

export const ORTAM = {
  TELEGRAM_BOT_TOKEN: "123456:TEST-bot-token-gizli",
  CHAT_ID: "424242",
  GH_PAT: "github_pat_TEST_gizli_anahtar",
  WEBHOOK_SECRET: "webhook-gizli-deger",
  PANEL_SECRET: "panel-gizli-anahtar-0123456789abcdef",
  REPO: "sabriemin/bilgimakasi",
};

// ---- sabit saat (Date.now ve new Date()) ----
const GercekDate = globalThis.Date;
let sabit = null;
class SahteDate extends GercekDate {
  constructor(...a) { if (a.length === 0 && sabit != null) super(sabit); else super(...a); }
  static now() { return sabit != null ? sabit : GercekDate.now(); }
}
export function saatKur(ms) { sabit = ms; globalThis.Date = SahteDate; }
// sunucu için: verilen andan başlayıp gerçek saatle ilerler
export function saatKurAkan(ms) {
  const fark = ms - GercekDate.now();
  globalThis.Date = class extends GercekDate {
    constructor(...a) { if (a.length === 0) super(GercekDate.now() + fark); else super(...a); }
    static now() { return GercekDate.now() + fark; }
  };
}
export function saatIlerlet(ms) { sabit += ms; }
export function saatBirak() { sabit = null; globalThis.Date = GercekDate; }

// ---- Cache API ----
export function cacheKur() {
  const depo = new Map();
  globalThis.caches = {
    default: {
      async match(req) {
        const k = typeof req === "string" ? req : req.url;
        const e = depo.get(k);
        if (!e) return undefined;
        const yas = (Date.now() - e.t) / 1000;
        if (yas > e.maxAge) { depo.delete(k); return undefined; }
        return new Response(e.govde, { headers: e.basliklar });
      },
      async put(req, res) {
        const k = typeof req === "string" ? req : req.url;
        const m = /max-age=(\d+)/.exec(res.headers.get("cache-control") || "");
        depo.set(k, { t: Date.now(), maxAge: m ? Number(m[1]) : 0, govde: await res.text(),
          basliklar: Object.fromEntries(res.headers) });
      },
    },
  };
  return depo;
}

// ---- GitHub + Telegram ----
export function fiksturOku(ad, kok = FIKSTUR) {
  const p = join(kok, ad);
  return existsSync(p) ? readFileSync(p, "utf8") : null;
}

export const META = {
  title: "Bir Mahalleyi Melas Dalgası Yuttu: 1919 Boston Faciası",
  description: "1919'da Boston'da patlayan bir tank, 8 metrelik melas dalgasıyla bir mahalleyi yuttu.\n\n" +
    "#tarih #boston #ilginçbilgiler\n\n📷 John Doe (CC BY-SA 4.0)",
  hashtags: ["tarih", "boston", "ilginçbilgiler"],
  topic: "1919 Boston melas seli",
  credits: [{ author: "John Doe", license: "CC BY-SA 4.0", page: "https://commons.wikimedia.org/x", title: "x" }],
};

/**
 * Sahte fetch kurar. ayar: { kok, dosyaHata: {ad: status}, dispatchDurum, tgDurum, imzaliAdres }
 * Dönen nesnede cagrilar listesi tüm giden istekleri tutar.
 */
export function fetchKur(ayar = {}) {
  const kok = ayar.kok || FIKSTUR;
  const cagrilar = [];
  const repo = ORTAM.REPO;
  const videolar = () => JSON.parse(fiksturOku("videos.json", kok) || "[]");
  globalThis.fetch = async (girdi, init = {}) => {
    const req = new Request(girdi, init);
    const url = req.url;
    const basliklar = Object.fromEntries(req.headers);
    let govde = null;
    if (req.method !== "GET" && req.method !== "HEAD") {
      const t = await req.text();
      try { govde = JSON.parse(t); } catch { govde = t; }
    }
    const kayit = { method: req.method, url, basliklar, govde, redirect: init.redirect || "follow" };
    cagrilar.push(kayit);
    const json = (s, d) => new Response(JSON.stringify(d), { status: s, headers: { "content-type": "application/json" } });
    let m;
    if ((m = /^https:\/\/api\.telegram\.org\/bot([^/]+)\/(\w+)$/.exec(url))) {
      const s = (ayar.tgDurum || {})[m[2]] || 200;
      return json(s, s === 200 ? { ok: true, result: { message_id: 999 } } : { ok: false, description: "hata" });
    }
    if (url.startsWith(`https://api.github.com/repos/${repo}/`)) {
      const yol = url.slice(`https://api.github.com/repos/${repo}/`.length);
      if ((m = /^contents\/state\/([\w.]+)\?ref=main$/.exec(yol))) {
        const s = (ayar.dosyaHata || {})[m[1]];
        if (s) return new Response("{\"message\":\"x\"}", { status: s });
        const t = fiksturOku(m[1], kok);
        return t == null ? new Response("{\"message\":\"Not Found\"}", { status: 404 }) : new Response(t, { status: 200 });
      }
      if (yol === "actions/workflows/isle.yml/dispatches" && req.method === "POST") {
        return new Response(null, { status: ayar.dispatchDurum || 204 });
      }
      if ((m = /^releases\/tags\/(.+)$/.exec(yol))) {
        const tag = decodeURIComponent(m[1]);
        if (!videolar().some((v) => v.tag === tag)) return json(404, { message: "Not Found" });
        return json(200, { tag_name: tag, assets: [
          { name: "video.mp4", url: `https://api.github.com/repos/${repo}/releases/assets/11` },
          { name: "metadata.json", url: `https://api.github.com/repos/${repo}/releases/assets/12` },
          { name: "script.json", url: `https://api.github.com/repos/${repo}/releases/assets/13` },
        ] });
      }
      if ((m = /^releases\/assets\/(\d+)$/.exec(yol))) {
        const ad = { 11: "video.mp4", 12: "metadata.json" }[m[1]];
        const adres = (ayar.imzaliAdres || "https://release-assets.githubusercontent.com/signed/") + ad + "?sig=abc&exp=300";
        return new Response(null, { status: 302, headers: { location: adres } });
      }
    }
    if (/\/metadata\.json\?sig=/.test(url)) {
      return json(200, META);
    }
    throw new Error("Beklenmeyen istek: " + req.method + " " + url);
  };
  return { cagrilar };
}

export function ctxYap() {
  const bekle = [];
  return { ctx: { waitUntil: (p) => bekle.push(p), passThroughOnException() {} }, bitir: () => Promise.all(bekle) };
}

const enc = new TextEncoder();
function b64url(buf) {
  let s = "";
  for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
// test için bağımsız imzalayıcı (panel.js'in içini kullanmadan)
export async function imza(amac, exp, anahtar = ORTAM.PANEL_SECRET) {
  const k = await crypto.subtle.importKey("raw", enc.encode(anahtar), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return `${exp}.${b64url(await crypto.subtle.sign("HMAC", k, enc.encode(`${amac}:${exp}`)))}`;
}
