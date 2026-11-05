// Bilgi Makası paneli: /panel altındaki her şey (worker.js buraya yönlendirir).
//
// Giriş: Telegram'da /panel yazınca kapı 10 dk geçerli, tek kullanımlık bir bağlantı verir (girisGonder). Bağlantı
// açılınca 30 günlük bm_oturum çerezi konur, bağlantı mesajı "kullanıldı" olur ve sohbete giriş bildirimi gider.
// İmza anahtarı PANEL_SECRET (her kurulumda yenilenir: tüm oturumlar kapanır); tarayıcıya hiçbir gizli değer gitmez.
//
// Okuma (GET, çerez gerekir):
//   /panel/api/durum        videos.json, stats.json, oneriler.json, konu_sirasi.json, stats_gecmis.jsonl, saatler
//   /panel/api/video/<tag>  GitHub Release'teki video.mp4'ün kısa ömürlü imzalı adresine 302
//   /panel/api/meta/<tag>   metadata.json (başlık, açıklama, etiketler, atıflar): düzenleme formu için
// İşlem (POST, çerez + "X-Panel: 1" başlığı gerekir):
//   /panel/api/islem        {action, ...} doğrulanır, işle.yml'e {"panel": {...}} olayı olarak iletilir;
//                           Python tarafı (telegram_bot.process_panel) Telegram düğmeleriyle aynı kodu çalıştırır.
//   /panel/api/cikis        oturumu kapatır

import { SAYFA_HTML, UYGULAMA_JS, girisHataSayfasi, KUYRUK_BASI, SINIR } from "./panel_ui.js";

const TR_OFFSET = 3 * 3600 * 1000; // Türkiye UTC+3
const GIRIS_SURE = 10 * 60; // giriş bağlantısı 10 dakika
const OTURUM_SURE = 30 * 86400; // oturum 30 gün
const CEREZ = "bm_oturum";
const ONBELLEK_MS = 20 * 1000;
const TAG_RE = /^short-\d{8}-\d{4,6}(-\d{1,3})?$/; // uret.yml: short-YYYYMMDD-HHMMSS (eskiler HHMM)
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
const VIDEO_KILIT = new Map(); // etiket -> {t, iz}: bir videoya işlem sürerken (kayıt değişmeden) ikinci işlem yapılmaz
const VIDEO_KILIT_MS = 90 * 1000;
// release dosyasının imzalı adresi yalnız bu GitHub alan adlarından olabilir
const IMZALI_ALANLAR = new Set(["objects.githubusercontent.com", "release-assets.githubusercontent.com",
  "github-releases.githubusercontent.com"]);

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

// İmzalanan metin amacı da içerir ("giris:<exp>:<mesaj>" / "oturum:<dönem>:<exp>"): giriş bağlantısı çerez yerine,
// çerez de bağlantı yerine kullanılamaz. PANEL_EPOCH (isteğe bağlı) değiştirilirse bütün oturumlar kapanır.
async function imzala(env, metin) {
  return b64url(await crypto.subtle.sign("HMAC", await anahtar(env), enc.encode(metin)));
}

async function imzaDogru(env, metin, sig64) {
  let sig;
  try { sig = b64urlCoz(sig64); } catch { return false; }
  return crypto.subtle.verify("HMAC", await anahtar(env), sig, enc.encode(metin)); // sabit sürede karşılaştırır
}

function sureUygun(exp, enUzun) {
  const now = Math.floor(Date.now() / 1000);
  return exp > now && exp <= now + enUzun + 60;
}

const oturumMetni = (env, exp) => `oturum:${env.PANEL_EPOCH || 0}:${exp}`;

async function oturumDogru(env, token) {
  const m = /^(\d{9,11})\.([A-Za-z0-9_-]{43})$/.exec(token || "");
  return !!m && (await imzaDogru(env, oturumMetni(env, m[1]), m[2])) && sureUygun(Number(m[1]), OTURUM_SURE);
}

// giriş bağlantısı: <exp>.<bağlantı mesajının numarası>.<imza>
async function girisCoz(env, token) {
  const m = /^(\d{9,11})\.(\d{1,12})\.([A-Za-z0-9_-]{43})$/.exec(token || "");
  if (!m || !(await imzaDogru(env, `giris:${m[1]}:${m[2]}`, m[3])) || !sureUygun(Number(m[1]), GIRIS_SURE)) return null;
  return { mid: Number(m[2]) };
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

const KULLANILDI = "✅ Bu giriş bağlantısı kullanıldı. Yeni bağlantı için /panel yaz.";

// Telegram'daki /panel komutu (worker.js çağırır). Önce boş bir mesaj gider; bağlantı o mesajın numarasıyla imzalanır
// ve mesaj bağlantıya çevrilir. Bağlantı ilk açılışta bu mesajı sabit "kullanıldı" metnine çevirir; Telegram aynı
// metne ikinci düzenlemeyi "message is not modified" diye reddettiği için bağlantı ikinci kez kullanılamaz.
export async function girisGonder(env, chatId, origin) {
  if (!env.PANEL_SECRET) {
    await tg(env, "sendMessage", { chat_id: chatId,
      text: "Panel henüz kurulmadı: GitHub'da 'Telegram kapısını kur' işini bir kez çalıştır." });
    return;
  }
  const r = await tg(env, "sendMessage", { chat_id: chatId, text: "🖥 Giriş bağlantısı hazırlanıyor…" });
  const mid = r.ok ? ((await r.json().catch(() => ({}))).result || {}).message_id : null;
  if (!Number.isInteger(mid)) return;
  const exp = Math.floor(Date.now() / 1000) + GIRIS_SURE;
  const url = `${origin}/panel/giris?t=${exp}.${mid}.${await imzala(env, `giris:${exp}:${mid}`)}`;
  await tg(env, "editMessageText", {
    chat_id: chatId, message_id: mid,
    text: "🖥 Bilgi Makası paneli\n\nGiriş bağlantın (10 dakika geçerli, tek kullanımlık):\n" + url +
      "\n\nBağlantıyı açtığın tarayıcıda oturum 30 gün açık kalır. Bağlantıyı kimseyle paylaşma." +
      "\nTüm oturumları kapatmak için GitHub'da 'Telegram kapısını kur' işini çalıştır.",
    disable_web_page_preview: true,
    reply_markup: { inline_keyboard: [[{ text: "🖥 Paneli aç", url }]] },
  });
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

// ---------------------------------------------------------------- gizli değer temizliği
// Paylaşım hataları (videos.json platforms.*.error, stats.json error) ağ hatası metni içerebilir; requests bu metne
// tam adresi koyar ve Instagram anahtarı adreste (access_token=...) durur. Tarayıcıya gitmeden önce maskelenir.
// shortgen/publish.py _redact ile aynı kurallar.
const GIZLI_KALIPLAR = [
  [/(access_token|input_token|refresh_token|client_secret|key|code)=[^&\s'")]+/gi, "$1=***"],
  [/((?:access_token|input_token|refresh_token|id_token|client_secret)["']?\s*:\s*["']?)[^"'\s,}&)]+/gi, "$1***"],
  [/bot\d+:[\w-]+/g, "bot***"],
  [/\b(EAA|IGAA|IGQ|ya29\.|AIza|github_pat_|gh[pousr]_)[\w.-]{16,}/g, "***"],
  [/\b(Bearer|OAuth)\s+[\w.~+/-]{8,}=*/gi, "$1 ***"],
];

export function gizle(metin, env = {}) {
  let s = String(metin);
  for (const k of ["GH_PAT", "TELEGRAM_BOT_TOKEN", "PANEL_SECRET", "WEBHOOK_SECRET"]) {
    const v = env[k];
    if (typeof v === "string" && v.length >= 8) s = s.split(v).join("***");
  }
  for (const [re, yeni] of GIZLI_KALIPLAR) s = s.replace(re, yeni);
  return s;
}

// Hata metinleri yalnız bu alanlarda durur (platforms.*.error/note, stats platforms.*.error/note). Yalnız bunları
// taramak hem başlık/konu gibi sıradan metnin yanlışlıkla maskelenmesini önler hem de video sayısı arttıkça
// işlemci süresini düşük tutar (Workers ücretsiz planı istek başına 10 ms işlemci süresi verir).
const GIZLI_ALANLAR = new Set(["error", "note", "hata", "mesaj", "detay", "yanit"]);

function gizliTemizle(x, env, alanda = false) {
  if (typeof x === "string") return alanda ? gizle(x, env) : x;
  if (Array.isArray(x)) return x.map((y) => gizliTemizle(y, env, alanda));
  if (x && typeof x === "object") {
    const o = {};
    for (const [k, v] of Object.entries(x)) o[k] = gizliTemizle(v, env, alanda || GIZLI_ALANLAR.has(k));
    return o;
  }
  return x;
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

function imzaliAdres(loc) {
  let u;
  try { u = new URL(loc); } catch { return null; }
  return u.protocol === "https:" && IMZALI_ALANLAR.has(u.hostname) && !u.port && !u.username && !u.password ? u.href : null;
}

// release dosyasının kısa ömürlü imzalı indirme adresi (GitHub 302 ile verir). PAT yalnız bu deponun release dosyası
// adresine gider; yönlendirme de yalnız GitHub'ın dosya alan adlarına olabilir (yanıt beklenmedikse 502, yetkisiz).
async function dosyaAdresi(env, tag, ad) {
  const asset = ((await surum(env, tag)).assets || []).find((a) => a && a.name === ad);
  if (!asset) throw new Hata(404, `Videonun ${ad} dosyası bulunamadı.`);
  const onek = `https://api.github.com/repos/${env.REPO}/releases/assets/`;
  if (typeof asset.url !== "string" || !asset.url.startsWith(onek) || !/^\d{1,15}$/.test(asset.url.slice(onek.length))) {
    throw new Hata(502, "GitHub'dan beklenmeyen bir dosya adresi geldi; video açılmadı.");
  }
  if (asset.state !== "uploaded") throw new Hata(502, `Videonun ${ad} dosyası henüz hazır değil.`);
  const r = await fetch(asset.url, { headers: ghBasliklari(env, "application/octet-stream"), redirect: "manual" });
  if (r.status >= 300 && r.status < 400) {
    const adres = imzaliAdres(r.headers.get("location") || "");
    if (!adres) throw new Hata(502, "GitHub'dan beklenmeyen bir yönlendirme geldi; video açılmadı.");
    return { adres };
  }
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

const OKUNAMADI = {
  stats: (k) => `İstatistikler okunamadı (${k}); İstatistik sekmesi eksik olabilir.`,
  oneriler: (k) => `Gündem önerileri okunamadı (${k}); Konular sekmesinde öneri görünmeyebilir.`,
  konu_sirasi: (k) => `Konu sırası okunamadı (${k}); sıra boş görünebilir.`,
  stats_gecmis: (k) => `İstatistik geçmişi okunamadı (${k}); grafikler eksik olabilir.`,
};

// stats_gecmis satırı {"time":…,"hesap":{…},"video":{…}}: video bölümü hiç ayrıştırılmaz (yanıt ve CPU küçük kalır)
function gecmisSatiri(s) {
  const i = s.indexOf(',"video":');
  const x = (i > 0 && jsonCoz(s.slice(0, i) + "}", null)) || jsonCoz(s, null);
  return x && x.time ? { time: x.time, hesap: x.hesap || {} } : null;
}

async function durumOku(env) {
  const adlar = Object.keys(DOSYALAR);
  const sonuc = await Promise.all(adlar.map((a) => dosya(env, DOSYALAR[a])));
  const f = Object.fromEntries(adlar.map((a, i) => [a, sonuc[i]]));
  if (f.videos.hata) {
    throw new Hata(502, f.videos.hata === 401 || f.videos.hata === 403 || f.videos.hata === 404
      ? `GitHub depo içeriği okunamadı (${f.videos.hata}). Kapının GitHub anahtarına (KAPI_PAT) 'Contents: Read-only' izni eklenmeli.`
      : `GitHub'a ulaşılamadı (${f.videos.hata}). Birazdan tekrar dene.`);
  }
  const uyarilar = adlar.filter((a) => f[a].hata).map((a) => OKUNAMADI[a](f[a].hata));
  const kuyruk = jsonCoz(f.konu_sirasi.metin, null);
  const gecmis = (f.stats_gecmis.metin || "").split("\n").filter((s) => s.trim())
    .slice(-400).map(gecmisSatiri).filter(Boolean); // grafikler yalnız hesap toplamlarını kullanır
  return {
    zaman: new Date().toISOString(),
    videos: gizliTemizle(jsonCoz(f.videos.metin, []) || [], env),
    stats: gizliTemizle(jsonCoz(f.stats.metin, null), env),
    oneriler: jsonCoz(f.oneriler.metin, null),
    konu_sirasi: Array.isArray(kuyruk) ? kuyruk : (kuyruk && Array.isArray(kuyruk.konular) ? kuyruk.konular : []),
    konu_sirasi_rid: (kuyruk && typeof kuyruk.rid === "string" && kuyruk.rid) || null, // son panel kaydı (izleme için)
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
// KUYRUK_BASI (panel_ui.js) telegram_bot._TAIL ile aynı: açıklamanın sonundaki etiket ve görsel atfı paragrafları
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

// panelden gelen açıklamada görsel atfı / kaynak paragrafı olmaz: onları paylaşım sona kendisi ekler (atıf korunur)
function aciklamaDenetle(s) {
  if (enc.encode(s).length > SINIR.aciklamaBayt) {
    throw new Hata(400, "Açıklama çok uzun: emoji ve özel karakterler daha çok yer kaplar. Biraz kısalt.");
  }
  for (const p of s.split(/\n\s*\n/)) {
    if (ekParagraf(p) && !p.split("\n").filter((l) => l.trim()).every((l) => l.trim().startsWith("#"))) {
      throw new Hata(400, "Görsel atfı ve kaynak satırları sona kendiliğinden eklenir; bu satırları açıklamadan çıkar.");
    }
  }
  return s;
}

function konuListesi(x, ad) {
  if (!Array.isArray(x)) throw new Hata(400, `${ad} eksik.`);
  const q = [];
  for (const y of x) {
    const s = metinAl(y, "Konu", 0, 300);
    if (s && !q.includes(s)) q.push(s);
  }
  if (q.length > 30) throw new Hata(400, "Sırada en fazla 30 konu olabilir.");
  return q;
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
      p.title = metinAl(b.title, "Başlık", 1, SINIR.baslik);
      p.description = aciklamaDenetle(metinAl(b.description, "Açıklama", 1, SINIR.aciklama, true));
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
    p.queue = konuListesi(b.queue, "Konu sırası");
    // sayfanın düzenlemeye başladığı liste: Python bununla üç yollu birleştirir, arada üretimin kullandığı konu
    // (sıradan çıkan) eski sayfadan kaydedilince geri gelmez
    if (b.queue_base !== undefined) p.queue_base = konuListesi(b.queue_base, "Konu sırası tabanı");
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
  // aynı videoya ikinci bir işlem (ör. onaydan hemen sonra ret): önceki işlem kaydı değiştirene kadar beklenir;
  // isle.yml çalışmaları aynı anda yürüyebildiği için ikisi birden işlenmesin
  const iz = video && JSON.stringify(video);
  const k = video && VIDEO_KILIT.get(p.tag);
  if (k && Date.now() - k.t < VIDEO_KILIT_MS && k.iz === iz) {
    throw new Hata(409, "Bu video için bir işlem sürüyor; sonucu bekle.");
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
  if (video) {
    if (VIDEO_KILIT.size > 100) VIDEO_KILIT.clear();
    VIDEO_KILIT.set(p.tag, { t: Date.now(), iz });
  }
  return json(202, { ok: true, mesaj: "⏳ İşleniyor (30-60 sn)…", rid: p.rid });
}

// ---------------------------------------------------------------- yönlendirme
const CIKIS_CEREZ = `${CEREZ}=; HttpOnly; Secure; SameSite=Strict; Path=/panel; Max-Age=0`;

async function api(req, env, ctx, url, yol) {
  const cerez = cerezAl(req);
  if (!(await oturumDogru(env, cerez))) {
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

function kisaTarayici(ua) {
  ua = String(ua || "");
  const os = /iPhone|iPad|iPod/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS X|Macintosh/.test(ua) ? "macOS"
    : /Windows/.test(ua) ? "Windows" : /CrOS/.test(ua) ? "ChromeOS" : /Linux/.test(ua) ? "Linux" : "";
  const t = /Edg(A|iOS)?\//.test(ua) ? "Edge" : /OPR\/|Opera/.test(ua) ? "Opera" : /SamsungBrowser/.test(ua) ? "Samsung"
    : /Firefox\/|FxiOS/.test(ua) ? "Firefox" : /Chrome\/|CriOS/.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "";
  return [t, os].filter(Boolean).join(" / ") || "bilinmeyen tarayıcı";
}

function trSaat(ms) {
  const t = new Date(ms + TR_OFFSET);
  return `${String(t.getUTCHours()).padStart(2, "0")}:${String(t.getUTCMinutes()).padStart(2, "0")}`;
}

async function giris(req, env, url, ctx) {
  const t = url.searchParams.get("t") || "";
  const g = await girisCoz(env, t);
  const ek = { "referrer-policy": "no-referrer" };
  if (!g) return sayfa(403, girisHataSayfasi(), ek);
  // bağlantı tarayıcılar/ön yükleyiciler HEAD ile yoklarsa harcanmasın; yalnız gerçek GET bağlantıyı kullanır
  if (req.method !== "GET") return new Response(null, { status: req.method === "HEAD" ? 200 : 405, headers: { ...ek } });
  // tek kullanım: bağlantı mesajı sabit metne çevrilir; zaten o metindeyse Telegram "not modified" der
  let r, aciklama = "";
  try {
    r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/editMessageText`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: env.CHAT_ID, message_id: g.mid, text: KULLANILDI }),
    });
    if (!r.ok) aciklama = String(((await r.json().catch(() => ({}))) || {}).description || "");
  } catch (e) {
    console.log("giriş: Telegram'a ulaşılamadı", String(e).slice(0, 200));
    return sayfa(503, girisHataSayfasi("ulasilamadi"), ek);
  }
  if (!r.ok) {
    if (r.status === 400 && /not modified/i.test(aciklama)) return sayfa(403, girisHataSayfasi("kullanildi"), ek);
    if (r.status === 400 && /not found|can't be edited/i.test(aciklama)) return sayfa(403, girisHataSayfasi(), ek);
    console.log("giriş: editMessageText", r.status, aciklama.slice(0, 200));
    return sayfa(503, girisHataSayfasi("ulasilamadi"), ek);
  }
  const exp = Math.floor(Date.now() / 1000) + OTURUM_SURE;
  const yer = [req.cf && req.cf.country, kisaTarayici(req.headers.get("user-agent")), trSaat(Date.now())].filter(Boolean);
  const bildirim = tg(env, "sendMessage", { chat_id: env.CHAT_ID,
    text: `🖥 Panele giriş yapıldı · ${yer.join(" · ")}\nSen değilsen GitHub'da 'Telegram kapısını kur' işini çalıştır; ` +
      "tüm oturumlar kapanır." }).catch((e) => console.log("giriş bildirimi gitmedi", String(e).slice(0, 200)));
  if (ctx && ctx.waitUntil) ctx.waitUntil(bildirim);
  return new Response(null, {
    status: 302,
    headers: {
      location: "/panel",
      "set-cookie": `${CEREZ}=${exp}.${await imzala(env, oturumMetni(env, exp))}; HttpOnly; Secure; SameSite=Strict; ` +
        `Path=/panel; Max-Age=${OTURUM_SURE}`,
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
    if (yol === "/panel/giris") return await giris(req, env, url, ctx);
    if (yol.startsWith("/panel/api/")) return await api(req, env, ctx, url, yol.slice("/panel/api/".length));
    return json(404, { hata: "Bulunamadı." });
  } catch (e) {
    if (e instanceof Hata) return json(e.status, { hata: e.message });
    console.log("panel hata", e && e.stack);
    return json(500, { hata: "Beklenmeyen bir hata oluştu. Birazdan tekrar dene." });
  }
}
