// Bilgi Makası paneli: /panel altındaki her şey (worker.js buraya yönlendirir).
//
// Giriş: Telegram'da /panel yazınca kapı 10 dk geçerli bir bağlantı verir (girisMesaji). Bağlantı açılınca
// 30 günlük bm_oturum çerezi konur. İmza anahtarı PANEL_SECRET; tarayıcıya hiçbir gizli değer gitmez.
//
// Okuma (GET, çerez gerekir):
//   /panel/api/durum        videos.json, stats.json, oneriler.json, konu_sirasi.json, stats_gecmis.jsonl, saatler
//   /panel/api/video/<tag>  GitHub Release'teki video.mp4'ün kısa ömürlü imzalı adresine 302
//   /panel/api/meta/<tag>   metadata.json (başlık, açıklama, etiketler, atıflar): düzenleme formu için
// İşlem (POST, çerez + "X-Panel: 1" başlığı gerekir):
//   /panel/api/islem        {action, ...} doğrulanır, işle.yml'e {"panel": {...}} olayı olarak iletilir;
//                           Python tarafı (telegram_bot.process_panel) Telegram düğmeleriyle aynı kodu çalıştırır.
//   /panel/api/cikis        oturumu kapatır

import { SAYFA_HTML, UYGULAMA_JS, girisHataSayfasi } from "./panel_ui.js";

const TR_OFFSET = 3 * 3600 * 1000; // Türkiye UTC+3
const GIRIS_SURE = 10 * 60; // giriş bağlantısı 10 dakika
const OTURUM_SURE = 30 * 86400; // oturum 30 gün
const CEREZ = "bm_oturum";
const ONBELLEK_MS = 20 * 1000;
const TAG_RE = /^short-[0-9-]+$/;
const KODLAR = ["best", "now", "b12", "b19", "y12", "y19"];
// telegram_bot.PANEL_VIDEO_ACTIONS ile aynı: işlem yalnız bu durumlardaki videoya yapılır
const VIDEO_ISLEM = {
  approve: ["onay_bekliyor"], reject: ["onay_bekliyor"], cancel: ["zamanlandi"],
  retry: ["hata", "kismen", "baglanti_yok"], edit: ["onay_bekliyor", "zamanlandi"],
};
const KILITLI = ["approve", "reject", "cancel", "retry"]; // Telegram'daki düğme de "⏳ İşleniyor" olur
const DIGER_ISLEM = ["produce_suggestion", "produce_topic", "refresh_suggestions", "report", "queue_set"];
// shortgen/telegram_bot.py BEST_TIMES / EXTRA_TIMES varsayılanlarıyla aynı (test karşılaştırır)
export const BEST_TIMES = { youtube: ["18:00", "21:00"], instagram: ["12:30", "20:00"], tiktok: ["19:30", "22:00"] };
export const EXTRA_TIMES = { youtube: ["15:00"], instagram: ["17:00"], tiktok: ["17:00"] };

const enc = new TextEncoder();
const BELLEK = new Map(); // izolat içi kısa önbellek (workers.dev'de Cache API çalışmayabilir)
const SON_ISLEM = new Map(); // aynı işlemin art arda gönderilmesini engeller (çift dokunma)

class Hata extends Error {
  constructor(status, mesaj) { super(mesaj); this.status = status; }
}

// ---------------------------------------------------------------- imza
function b64url(buf) {
  let s = "";
  for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlCoz(s) {
  const b = atob(s.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(b, (c) => c.charCodeAt(0));
}

function anahtar(env) {
  return crypto.subtle.importKey("raw", enc.encode(env.PANEL_SECRET), { name: "HMAC", hash: "SHA-256" },
    false, ["sign", "verify"]);
}

// amaç ("giris" / "oturum") imzaya katılır: giriş bağlantısı çerez yerine, çerez de bağlantı yerine kullanılamaz
async function imzala(env, amac, exp) {
  const sig = await crypto.subtle.sign("HMAC", await anahtar(env), enc.encode(`${amac}:${exp}`));
  return `${exp}.${b64url(sig)}`;
}

async function dogrula(env, amac, token, enUzun) {
  const m = /^(\d{9,11})\.([A-Za-z0-9_-]{43})$/.exec(token || "");
  if (!m) return false;
  let sig;
  try { sig = b64urlCoz(m[2]); } catch { return false; }
  // crypto.subtle.verify imzayı sabit sürede karşılaştırır
  const ok = await crypto.subtle.verify("HMAC", await anahtar(env), sig, enc.encode(`${amac}:${m[1]}`));
  const exp = Number(m[1]), now = Math.floor(Date.now() / 1000);
  return ok && exp > now && exp <= now + enUzun + 60;
}

async function sha(s) {
  const d = await crypto.subtle.digest("SHA-256", enc.encode(s));
  return [...new Uint8Array(d)].slice(0, 16).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function cerezAl(req) {
  for (const c of (req.headers.get("cookie") || "").split(";")) {
    const i = c.indexOf("=");
    if (i > 0 && c.slice(0, i).trim() === CEREZ) return c.slice(i + 1).trim();
  }
  return "";
}

// Telegram'daki /panel komutuna kapının vereceği cevap (worker.js gönderir)
export async function girisMesaji(env, chatId, origin) {
  if (!env.PANEL_SECRET) {
    return { chat_id: chatId, text: "Panel henüz kurulmadı: GitHub'da 'Telegram kapısını kur' işini bir kez çalıştır." };
  }
  const url = `${origin}/panel/giris?t=${await imzala(env, "giris", Math.floor(Date.now() / 1000) + GIRIS_SURE)}`;
  return {
    chat_id: chatId,
    text: "🖥 Bilgi Makası paneli\n\nGiriş bağlantın (10 dakika geçerli):\n" + url +
      "\n\nBağlantıyı açtığın tarayıcıda oturum 30 gün açık kalır. Bağlantıyı kimseyle paylaşma.",
    disable_web_page_preview: true,
    reply_markup: { inline_keyboard: [[{ text: "🖥 Paneli aç", url }]] },
  };
}

// ---------------------------------------------------------------- yanıtlar
const GUVENLIK = {
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "referrer-policy": "same-origin",
};

function json(status, data, ek = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...GUVENLIK, ...ek },
  });
}

function sayfa(status, html, ek = {}) {
  return new Response(html, {
    status,
    headers: {
      "content-type": "text/html; charset=utf-8", "cache-control": "no-store", ...GUVENLIK,
      "content-security-policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' " +
        "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; media-src 'self' " +
        "https: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
      ...ek,
    },
  });
}

// ---------------------------------------------------------------- GitHub
function ghBasliklari(env, accept) {
  return {
    authorization: `Bearer ${env.GH_PAT}`, accept, "user-agent": "bilgimakasi-kapi", "x-github-api-version": "2022-11-28",
  };
}

async function dosya(env, yol) {
  const r = await fetch(`https://api.github.com/repos/${env.REPO}/contents/${yol}?ref=main`,
    { headers: ghBasliklari(env, "application/vnd.github.raw") });
  if (r.status === 404) return { yok: true };
  if (!r.ok) return { hata: r.status };
  return { metin: await r.text() };
}

function jsonCoz(metin, yedek) {
  try { return JSON.parse(metin); } catch { return yedek; }
}

async function surum(env, tag) {
  const r = await fetch(`https://api.github.com/repos/${env.REPO}/releases/tags/${encodeURIComponent(tag)}`,
    { headers: ghBasliklari(env, "application/vnd.github+json") });
  if (r.status === 404) throw new Hata(404, "Bu videonun GitHub kaydı bulunamadı.");
  if (!r.ok) throw new Hata(502, `GitHub'a ulaşılamadı (${r.status}).`);
  return r.json();
}

// release dosyasının kısa ömürlü imzalı indirme adresi (GitHub 302 ile verir)
async function dosyaAdresi(env, tag, ad) {
  const asset = ((await surum(env, tag)).assets || []).find((a) => a.name === ad);
  if (!asset) throw new Hata(404, `Videonun ${ad} dosyası bulunamadı.`);
  const r = await fetch(asset.url, { headers: ghBasliklari(env, "application/octet-stream"), redirect: "manual" });
  const loc = r.headers.get("location");
  if (r.status >= 300 && r.status < 400 && loc) return { adres: loc };
  if (r.ok) return { yanit: r }; // yönlendirmeden doğrudan geldiyse
  throw new Hata(502, `Video dosyası alınamadı (${r.status}).`);
}

async function dispatch(env, panel) {
  return fetch(`https://api.github.com/repos/${env.REPO}/actions/workflows/isle.yml/dispatches`, {
    method: "POST",
    headers: { ...ghBasliklari(env, "application/vnd.github+json"), "content-type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs: { update: JSON.stringify({ panel }) } }),
  });
}

async function tg(env, method, body) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
  if (!r.ok) console.log(method, r.status, await r.text());
  return r;
}

function kb(rows) {
  return { inline_keyboard: rows.map((r) => r.map(([text, data]) => ({ text, callback_data: data }))) };
}

// telegram_bot._kb_rows ile aynı
function durumDugmeleri(tag, status) {
  return {
    onay_bekliyor: [[["✅ Onayla", `ok:${tag}`], ["❌ Reddet", `no:${tag}`]]],
    zamanlandi: [[["🚫 Paylaşımı iptal et", `cancel:${tag}`]]],
    hata: [[["🔁 Hatalıları tekrar dene", `rt:${tag}`]]],
    kismen: [[["🔁 Hatalıları tekrar dene", `rt:${tag}`]]],
  }[status] || [];
}

// ---------------------------------------------------------------- durum
const DOSYALAR = {
  videos: "state/videos.json", stats: "state/stats.json", oneriler: "state/oneriler.json",
  konu_sirasi: "state/konu_sirasi.json", stats_gecmis: "state/stats_gecmis.jsonl",
};

async function durumOku(env) {
  const adlar = Object.keys(DOSYALAR);
  const sonuc = await Promise.all(adlar.map((a) => dosya(env, DOSYALAR[a])));
  const f = Object.fromEntries(adlar.map((a, i) => [a, sonuc[i]]));
  if (f.videos.hata) {
    throw new Hata(502, f.videos.hata === 401 || f.videos.hata === 403 || f.videos.hata === 404
      ? `GitHub depo içeriği okunamadı (${f.videos.hata}). GH_SECRETS_PAT'e 'Contents: Read-only' izni eklenmeli.`
      : `GitHub'a ulaşılamadı (${f.videos.hata}). Birazdan tekrar dene.`);
  }
  const uyarilar = adlar.filter((a) => f[a].hata).map((a) => `${DOSYALAR[a]} okunamadı (${f[a].hata})`);
  const kuyruk = jsonCoz(f.konu_sirasi.metin, null);
  const gecmis = (f.stats_gecmis.metin || "").split("\n").filter((s) => s.trim())
    .slice(-400).map((s) => jsonCoz(s, null)).filter((x) => x && x.time)
    .map((x) => ({ time: x.time, hesap: x.hesap || {} })); // grafikler yalnız hesap toplamlarını kullanır: yanıt küçük kalır
  return {
    zaman: new Date().toISOString(),
    videos: jsonCoz(f.videos.metin, []) || [],
    stats: jsonCoz(f.stats.metin, null),
    oneriler: jsonCoz(f.oneriler.metin, null),
    konu_sirasi: Array.isArray(kuyruk) ? kuyruk : (kuyruk && Array.isArray(kuyruk.konular) ? kuyruk.konular : []),
    stats_gecmis: gecmis,
    saatler: { en_iyi: BEST_TIMES, ek: EXTRA_TIMES },
    uyarilar,
  };
}

async function durum(env, ctx, oturum) {
  const anah = `durum:${oturum}`; // oturuma özel: önbellek kişiler arasında paylaşılmaz
  const m = BELLEK.get(anah);
  if (m && Date.now() - m.t < ONBELLEK_MS) return m.govde;
  const cache = globalThis.caches && caches.default;
  const istek = new Request(`https://panel-onbellek.bilgimakasi.invalid/durum/${oturum}`);
  if (cache) {
    const hit = await cache.match(istek).catch(() => null);
    if (hit) {
      const govde = await hit.text();
      BELLEK.set(anah, { t: Date.now(), govde });
      return govde;
    }
  }
  const govde = JSON.stringify(await durumOku(env));
  if (BELLEK.size > 50) BELLEK.clear();
  BELLEK.set(anah, { t: Date.now(), govde });
  if (cache) {
    const p = cache.put(istek, new Response(govde, {
      headers: { "content-type": "application/json", "cache-control": `max-age=${ONBELLEK_MS / 1000}` },
    })).catch(() => {});
    if (ctx && ctx.waitUntil) ctx.waitUntil(p);
  }
  return govde;
}

// ---------------------------------------------------------------- meta
const KUYRUK_BASI = ["#", "📷", "🎙", "Görseller:", "Kaynaklar:", "Bu videoda yapay zekâ"];

// telegram_bot._is_tail ile aynı: açıklamanın sonundaki etiket ve görsel atfı paragrafları korunur
function ekParagraf(p) {
  const satirlar = p.split("\n").map((s) => s.trim()).filter(Boolean);
  return satirlar.length > 0 && satirlar.every((s) => KUYRUK_BASI.some((k) => s.startsWith(k)));
}

async function meta(env, tag) {
  const a = await dosyaAdresi(env, tag, "metadata.json");
  const r = a.yanit || await fetch(a.adres); // imzalı adres: yetki başlığı gönderilmez
  if (!r.ok) throw new Hata(502, `Video bilgisi alınamadı (${r.status}).`);
  const m = await r.json();
  const parcalar = String(m.description || "").split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean);
  return {
    tag,
    title: m.title || "",
    description: m.description || "",
    bilgi: parcalar.filter((p) => !ekParagraf(p)).join("\n\n"),
    ekler: parcalar.filter(ekParagraf),
    hashtags: m.hashtags || [],
    topic: m.topic || "",
    credits: (m.credits || []).map((c) => ({ author: c.author || "", license: c.license || "" })),
  };
}

// ---------------------------------------------------------------- işlem doğrulama
function uzunluk(s) { return [...s].length; } // Python len() gibi kod noktası sayar

function metinAl(x, ad, enAz, enCok, cokSatir = false) {
  if (typeof x !== "string") throw new Hata(400, `${ad} eksik.`);
  let s = x.replace(/\r\n?/g, "\n");
  s = cokSatir ? s.split("\n").map((l) => l.trimEnd()).join("\n").trim() : s.split(/\s+/).filter(Boolean).join(" ");
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u0008\u000b-\u001f\u007f]/.test(s)) throw new Hata(400, `${ad} geçersiz karakter içeriyor.`);
  if (uzunluk(s) < enAz) throw new Hata(400, `${ad} boş olamaz.`);
  if (uzunluk(s) > enCok) throw new Hata(400, `${ad} en fazla ${enCok} karakter olabilir.`);
  return s;
}

function slotZamani(kod, simdi = Date.now()) {
  const t = new Date(simdi + TR_OFFSET);
  const gun = kod[0] === "b" ? 0 : 1, saat = Number(kod.slice(1));
  return Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate() + gun, saat) - TR_OFFSET;
}

async function islemHazirla(env, b) {
  if (!b || typeof b !== "object" || Array.isArray(b)) throw new Hata(400, "Geçersiz istek.");
  const action = b.action;
  const p = { action };
  let video = null;
  if (action in VIDEO_ISLEM) {
    if (typeof b.tag !== "string" || !TAG_RE.test(b.tag)) throw new Hata(400, "Geçersiz video etiketi.");
    p.tag = b.tag;
    const f = await dosya(env, DOSYALAR.videos); // önbelleksiz: en güncel durum
    if (f.hata) throw new Hata(502, `GitHub'dan durum okunamadı (${f.hata}).`);
    video = (jsonCoz(f.metin, []) || []).find((v) => v && v.tag === b.tag);
    if (!video) throw new Hata(404, "Video bulunamadı.");
    if (!VIDEO_ISLEM[action].includes(video.status)) {
      throw new Hata(409, "Bu videonun durumu değişmiş, işlem yapılmadı. Sayfa yenileniyor.");
    }
    if (action === "approve") {
      if (!KODLAR.includes(b.code)) throw new Hata(400, "Geçersiz saat seçimi.");
      if (b.code[0] === "b" || b.code[0] === "y") {
        if (slotZamani(b.code) < Date.now()) throw new Hata(409, "Seçilen saat geçti, başka bir saat seç.");
      }
      p.code = b.code;
    }
    if (action === "edit") {
      p.title = metinAl(b.title, "Başlık", 1, 100);
      p.description = metinAl(b.description, "Açıklama", 1, 2000, true);
    }
  } else if (action === "produce_suggestion") {
    if (!Number.isInteger(b.index) || b.index < 0 || b.index > 19) throw new Hata(400, "Geçersiz öneri.");
    const f = await dosya(env, DOSYALAR.oneriler);
    const items = (jsonCoz(f.metin, null) || {}).items || [];
    const it = items[b.index];
    if (!it || (b.topic !== undefined && b.topic !== it.topic)) {
      throw new Hata(409, "Öneri listesi değişmiş. Sayfa yenileniyor, tekrar seç.");
    }
    p.index = b.index;
    p.topic = it.topic;
  } else if (action === "produce_topic") {
    p.topic = b.topic === undefined || b.topic === "" ? "" : metinAl(b.topic, "Konu", 0, 300);
  } else if (action === "queue_set") {
    if (!Array.isArray(b.queue)) throw new Hata(400, "Konu sırası eksik.");
    const q = [];
    for (const x of b.queue) {
      const s = metinAl(x, "Konu", 0, 300);
      if (s && !q.includes(s)) q.push(s);
    }
    if (q.length > 30) throw new Hata(400, "Sırada en fazla 30 konu olabilir.");
    p.queue = q;
  } else if (!DIGER_ISLEM.includes(action)) {
    throw new Hata(400, "Bilinmeyen işlem.");
  }
  return { p, video };
}

async function islem(req, env) {
  let b;
  try { b = await req.json(); } catch { throw new Hata(400, "Geçersiz istek."); }
  const { p, video } = await islemHazirla(env, b);
  const anah = JSON.stringify(p);
  const once = SON_ISLEM.get(anah);
  if (once && Date.now() - once < 15000) {
    throw new Hata(409, "Bu işlem az önce gönderildi; sonucu bekle.");
  }
  // Telegram'daki düğmeyi de kilitle (kapının düğme basışında yaptığı gibi): iki yerden aynı anda işlem olmasın
  const kilit = video && KILITLI.includes(p.action) && video.telegram_message_id;
  if (kilit) {
    await tg(env, "editMessageReplyMarkup", { chat_id: env.CHAT_ID, message_id: video.telegram_message_id,
      reply_markup: kb([[["⏳ İşleniyor…", "noop:x"]]]) }).catch(() => {});
  }
  p.rid = crypto.randomUUID();
  p.at = new Date().toISOString();
  let r;
  try { r = await dispatch(env, p); } catch (e) { r = { status: 0, text: async () => String(e) }; }
  if (r.status !== 204) {
    console.log("panel dispatch", r.status, await r.text());
    if (kilit) {
      await tg(env, "editMessageReplyMarkup", { chat_id: env.CHAT_ID, message_id: video.telegram_message_id,
        reply_markup: kb(durumDugmeleri(video.tag, video.status)) }).catch(() => {});
    }
    throw new Hata(502, `İşlem GitHub'a iletilemedi (${r.status}). Birazdan tekrar dene.`);
  }
  if (SON_ISLEM.size > 100) SON_ISLEM.clear();
  SON_ISLEM.set(anah, Date.now());
  return json(202, { ok: true, mesaj: "⏳ İşleniyor (30-60 sn)…" });
}

// ---------------------------------------------------------------- yönlendirme
const CIKIS_CEREZ = `${CEREZ}=; HttpOnly; Secure; SameSite=Strict; Path=/panel; Max-Age=0`;

async function api(req, env, ctx, url, yol) {
  const cerez = cerezAl(req);
  if (!(await dogrula(env, "oturum", cerez, OTURUM_SURE))) {
    return json(401, { hata: "Oturum yok veya süresi doldu. Telegram'da /panel yazıp gelen bağlantıya dokun.", giris: true });
  }
  const oturum = await sha(cerez);
  const yazma = yol === "islem" || yol === "cikis";
  if (yazma) {
    if (req.method !== "POST") return json(405, { hata: "Yalnız POST." }, { allow: "POST" });
    const origin = req.headers.get("origin");
    if (req.headers.get("x-panel") !== "1" || (origin && origin !== url.origin)) {
      return json(403, { hata: "İstek reddedildi (güvenlik denetimi)." });
    }
    if (yol === "cikis") return json(200, { ok: true }, { "set-cookie": CIKIS_CEREZ });
    if (!(req.headers.get("content-type") || "").includes("application/json")) {
      return json(415, { hata: "İstek JSON olmalı." });
    }
    return islem(req, env);
  }
  if (req.method !== "GET" && req.method !== "HEAD") return json(405, { hata: "Yalnız GET." }, { allow: "GET" });
  if (yol === "durum") {
    return new Response(await durum(env, ctx, oturum), {
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...GUVENLIK },
    });
  }
  const m = /^(video|meta)\/(.+)$/.exec(yol);
  if (m) {
    let tag;
    try { tag = decodeURIComponent(m[2]); } catch { tag = ""; }
    if (!TAG_RE.test(tag)) return json(400, { hata: "Geçersiz video etiketi." });
    if (m[1] === "meta") return json(200, await meta(env, tag));
    const a = await dosyaAdresi(env, tag, "video.mp4");
    if (a.adres) {
      return new Response(null, {
        status: 302, headers: { location: a.adres, "cache-control": "no-store", "referrer-policy": "no-referrer" },
      });
    }
    return new Response(a.yanit.body, { headers: { "content-type": "video/mp4", "cache-control": "no-store" } });
  }
  return json(404, { hata: "Bulunamadı." });
}

async function giris(env, url) {
  const t = url.searchParams.get("t") || "";
  if (!(await dogrula(env, "giris", t, GIRIS_SURE))) {
    return sayfa(403, girisHataSayfasi(), { "referrer-policy": "no-referrer" });
  }
  const exp = Math.floor(Date.now() / 1000) + OTURUM_SURE;
  return new Response(null, {
    status: 302,
    headers: {
      location: "/panel",
      "set-cookie": `${CEREZ}=${await imzala(env, "oturum", exp)}; HttpOnly; Secure; SameSite=Strict; Path=/panel; ` +
        `Max-Age=${OTURUM_SURE}`,
      "cache-control": "no-store",
      "referrer-policy": "no-referrer",
    },
  });
}

export async function panel(req, env, ctx) {
  const url = new URL(req.url);
  const yol = url.pathname.replace(/\/+$/, "") || "/";
  try {
    if (!env.PANEL_SECRET) return json(503, { hata: "Panel kurulmamış (PANEL_SECRET yok)." });
    if (yol === "/panel" || yol === "/panel/app.js") {
      if (req.method !== "GET" && req.method !== "HEAD") return json(405, { hata: "Yalnız GET." });
      if (yol === "/panel") return sayfa(200, SAYFA_HTML);
      return new Response(UYGULAMA_JS, {
        headers: { "content-type": "text/javascript; charset=utf-8", "cache-control": "no-cache", ...GUVENLIK },
      });
    }
    if (yol === "/panel/giris") return await giris(env, url);
    if (yol.startsWith("/panel/api/")) return await api(req, env, ctx, url, yol.slice("/panel/api/".length));
    return json(404, { hata: "Bulunamadı." });
  } catch (e) {
    if (e instanceof Hata) return json(e.status, { hata: e.message });
    console.log("panel hata", e && e.stack);
    return json(500, { hata: "Beklenmeyen bir hata oluştu. Birazdan tekrar dene." });
  }
}
