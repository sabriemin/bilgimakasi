// Bilgi Makası paneli: /panel altındaki her şey (worker.js buraya yönlendirir).
//
// Giriş: Telegram'da /panel yazınca kapı 10 dk geçerli, tek kullanımlık bir bağlantı verir (girisGonder). Bağlantı
// açılınca 30 günlük bm_oturum çerezi konur, bağlantı mesajı "kullanıldı" olur ve sohbete giriş bildirimi gider.
// İmza anahtarı PANEL_SECRET (her kurulumda yenilenir: tüm oturumlar kapanır); tarayıcıya hiçbir gizli değer gitmez.
//
// Okuma (GET, çerez gerekir):
//   /panel/api/durum        videos.json, stats.json, oneriler.json, konu_sirasi.json, stats_gecmis.jsonl, saatler
//   /panel/api/video/<tag>  GitHub Release'teki video.mp4'ün kısa ömürlü imzalı adresine 302
//   /panel/api/plan         yayin_plani.json + videos.json (14 günlük yayın takvimi, seriler), secim/plan_s1.json
//                           (Karar Senin hikâyesi), claude_usage.json (dönem harcaması), yenilikler.json
//   /panel/api/meta/<tag>   metadata.json (başlık, açıklama, etiketler, atıflar): düzenleme formu için
// İşlem (POST, çerez + "X-Panel: 1" başlığı gerekir):
//   /panel/api/islem        {action, ...} doğrulanır, işle.yml'e {"panel": {...}} olayı olarak iletilir;
//                           takvim: {action: "schedule", tag, schedule: {youtube?, instagram?, tiktok?: UTC ISO}};
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
  schedule: ["onay_bekliyor", "zamanlandi"],
};
const KILITLI = ["approve", "reject", "cancel", "retry", "schedule"]; // Telegram'daki düğme de "⏳ İşleniyor" olur
const DIGER_ISLEM = ["produce_suggestion", "produce_topic", "refresh_suggestions", "report", "queue_set"];
// öneri sırasının kaba üst sınırı: sekiz seri × 3 = 24 öneri (0-23); asıl denetim kayıtlı listedeki sıra ve konu
const ONERI_SIRA_SINIRI = 40;
// shortgen/telegram_bot.py BEST_TIMES / EXTRA_TIMES varsayılanlarıyla aynı (test karşılaştırır)
export const BEST_TIMES = { youtube: ["18:00", "21:00"], instagram: ["12:30", "20:00"], tiktok: ["19:30", "22:00"] };
export const EXTRA_TIMES = { youtube: [], instagram: [], tiktok: [] };
const PLATFORMLAR = ["youtube", "instagram", "tiktok"];
const PF_ADI = { youtube: "YouTube", instagram: "Instagram", tiktok: "TikTok" };
// takvim saatleri (telegram_bot._check_schedule): en erken şimdi+2 dk, en geç 30 gün sonrası, dakikaya yuvarlanır
const SAAT_EN_ERKEN = 2 * 60e3, SAAT_EN_GEC = 30 * 86400e3;
const YAKIN_MS = 10 * 60e3; // telegram_bot.EDIT_GUARD_MIN: paylaşıma bu kadar kala metin ve saat değişmez
const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,9})?)?(Z|[+-]\d{2}:\d{2})$/;

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
export function ghBasliklari(env, accept) {
  return {
    authorization: `Bearer ${env.GH_PAT}`, accept, "user-agent": "bilgimakasi-kapi", "x-github-api-version": "2022-11-28",
  };
}

export async function dosya(env, yol) {
  const r = await fetch(`https://api.github.com/repos/${env.REPO}/contents/${yol}?ref=main`,
    { headers: ghBasliklari(env, "application/vnd.github.raw") });
  if (r.status === 404) return { yok: true };
  if (!r.ok) return { hata: r.status };
  return { metin: await r.text() };
}

export function jsonCoz(metin, yedek) {
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

// ---------------------------------------------------------------- paylaşım anı
function okPlatformlar(v) {
  return new Set(Object.entries((v && v.platforms) || {}).filter(([, r]) => r && r.status === "ok").map(([p]) => p));
}

// telegram_bot._due_at ile aynı: paylaşım işinin zamanlanmış videoda bir şey paylaşacağı an (ms) = publish_at ile
// bekleyen (paylaşılmamış) en erken platform saatinin geç olanı. Zamanlanmamış videoda null.
export function paylasimAni(v) {
  if (!v || v.status !== "zamanlandi") return null;
  const ok = okPlatformlar(v);
  const takvim = v.schedule && typeof v.schedule === "object" ? v.schedule : {};
  const bekleyen = Object.entries(takvim).filter(([p, t]) => t && !ok.has(p)).map(([, t]) => Date.parse(t))
    .filter(Number.isFinite);
  const aday = [Date.parse(v.publish_at || ""), bekleyen.length ? Math.min(...bekleyen) : NaN].filter(Number.isFinite);
  return aday.length ? Math.max(...aday) : null;
}

// zamanlanmış videolardaki [enAz, enCok] içindeki paylaşım anları, sıralı ve tekil (telegram_bot._due_times)
export function paylasimAnlari(vs, enAz = -Infinity, enCok = Infinity) {
  const anlar = new Set();
  for (const v of vs || []) {
    const t = paylasimAni(v);
    if (t != null && t >= enAz && t <= enCok) anlar.add(t);
  }
  return [...anlar].sort((a, b) => a - b);
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

// Panel yalnız işi süren videoları ve son VIDEO_GUN gün içindeki bitmiş videoları gösterir: videos.json büyüdükçe
// yanıt ve işlemci süresi (ücretsiz plan istek başına 10 ms) sabit kalsın.
const VIDEO_GUN = 120, VIDEO_BITMIS_EN_COK = 150;
const BITMIS = new Set(["yayinlandi", "reddedildi", "iptal"]);

function gorunenVideolar(vs) {
  const sinir = Date.now() - VIDEO_GUN * 86400e3;
  const tarih = (v) => Date.parse((v && (v.published || v.created)) || "") || 0;
  let bitmis = 0;
  const out = [];
  for (let i = vs.length - 1; i >= 0; i--) { // en yeniler sonda
    const v = vs[i];
    if (!v || typeof v !== "object") continue;
    if (BITMIS.has(v.status)) {
      if (bitmis >= VIDEO_BITMIS_EN_COK || tarih(v) < sinir) continue;
      bitmis++;
    }
    out.push(v);
  }
  return out.reverse();
}

// Yalnız hata/not alanlarını yerinde maskeler (kopya yok): platforms.*.error/note, stats platforms.*.error/note
function gizliYerinde(x, env, derin = 0) {
  if (!x || typeof x !== "object" || derin > 4) return x;
  if (Array.isArray(x)) {
    for (const y of x) gizliYerinde(y, env, derin + 1);
    return x;
  }
  for (const [k, v] of Object.entries(x)) {
    if (GIZLI_ALANLAR.has(k)) x[k] = gizliTemizle(v, env, true);
    else if (v && typeof v === "object") gizliYerinde(v, env, derin + 1);
  }
  return x;
}

// Metnin son n dolu satırı (tüm dosyayı bölmeden)
function sonSatirlar(metin, n) {
  const out = [];
  let son = metin.length;
  while (son > 0 && out.length < n) {
    const i = metin.lastIndexOf("\n", son - 1);
    const satir = metin.slice(i + 1, son);
    if (satir.trim()) out.push(satir);
    son = i < 0 ? 0 : i;
  }
  return out.reverse();
}

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
  const gecmis = sonSatirlar(f.stats_gecmis.metin || "", 400).map(gecmisSatiri).filter(Boolean); // yalnız hesap toplamları
  const tum = jsonCoz(f.videos.metin, []);
  const videos = gizliYerinde(gorunenVideolar(Array.isArray(tum) ? tum : []), env);
  return {
    zaman: new Date().toISOString(),
    videos,
    videos_toplam: Array.isArray(tum) ? tum.length : 0,
    stats: gizliYerinde(jsonCoz(f.stats.metin, null), env),
    oneriler: jsonCoz(f.oneriler.metin, null),
    konu_sirasi: Array.isArray(kuyruk) ? kuyruk : (kuyruk && Array.isArray(kuyruk.konular) ? kuyruk.konular : []),
    konu_sirasi_rid: (kuyruk && typeof kuyruk.rid === "string" && kuyruk.rid) || null, // son panel kaydı (izleme için)
    stats_gecmis: gecmis,
    saatler: { en_iyi: BEST_TIMES, ek: EXTRA_TIMES },
    uyarilar,
  };
}

// /durum ve /plan yanıtı ~20 sn önbellekte (oturuma özel: önbellek kişiler arasında paylaşılmaz)
async function onbellekli(ad, uret, ctx, oturum) {
  const anah = `${ad}:${oturum}`;
  const m = BELLEK.get(anah);
  if (m && Date.now() - m.t < ONBELLEK_MS) return m.govde;
  const cache = globalThis.caches && caches.default;
  const istek = new Request(`https://panel-onbellek.bilgimakasi.invalid/${ad}/${oturum}`);
  if (cache) {
    const hit = await cache.match(istek).catch(() => null);
    if (hit) {
      const govde = await hit.text();
      BELLEK.set(anah, { t: Date.now(), govde });
      return govde;
    }
  }
  const govde = JSON.stringify(await uret());
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

const durum = (env, ctx, oturum) => onbellekli("durum", () => durumOku(env), ctx, oturum);
const planDurumu = (env, ctx, oturum) => onbellekli("plan", () => planOku(env), ctx, oturum);

// ---------------------------------------------------------------- yayın planı (Takvim ve Seriler)
// /panel/api/plan: haftalık plan (state/yayin_plani.json, shortgen/takvim.py ile tek kaynak) önümüzdeki 14 günün
// gerçek videolarıyla birleşir; seriler, Karar Senin hikâye planı, Claude harcaması ve yenilikler. Dosyası olmayan
// bölüm null döner (eski durumda panel yine çalışır). Bütün metinler tarayıcıda textContent ile yazılır.
const PLAN_DOSYALARI = {
  videos: "state/videos.json", plan: "state/yayin_plani.json", hikaye: "state/secim/plan_s1.json",
  claude: "state/claude_usage.json", yenilikler: "state/yenilikler.json",
};
const PLAN_OKUNAMADI = {
  videos: "Videolar okunamadı", plan: "Yayın planı okunamadı", hikaye: "Karar Senin hikâye planı okunamadı",
  claude: "Claude harcaması okunamadı", yenilikler: "Yenilikler okunamadı",
};
export const PLAN_GUN = 14;
const GUN_ADLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]; // takvim.py: Pazartesi = 0
const SERI_DURUMLARI = ["yayında", "örnek bekliyor", "kuruluyor"];
const ESLESME_MS = 90 * 60e3; // aynı serinin videosu plan saatine bu kadar yakınsa o saatin videosu sayılır
const SAAT_ESLESME_MS = 30 * 60e3; // başka serinin videosu tam plan saatindeyse (±30 dk) o saati doldurur
const TAKVIMDE = new Set(["zamanlandi", "yayinlaniyor", "yayinlandi", "kismen", "hata", "baglanti_yok"]);
const ANAHTAR_RE = /^[a-z][a-z0-9_]{0,23}$/;
const HM_RE = /^([01]\d|2[0-3]):([0-5]\d)$/;
const TARIH_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

const yazi = (x, n = 200) => (typeof x === "string" ? x.trim().slice(0, n) : "");
const tamSayi = (x, a, b) => (Number.isInteger(x) && x >= a && x <= b ? x : null);
const gunKodu = (ms) => new Date(ms + TR_OFFSET).toISOString().slice(0, 10); // TR takvim günü "YYYY-AA-GG"
const gunBasiMs = (kod) => Date.parse(kod + "T00:00:00Z") - TR_OFFSET;
const hm = (s) => { const m = HM_RE.exec(s); return m ? Number(m[1]) * 60 + Number(m[2]) : null; };
function hmYaz(x) { // "9:30" -> "09:30"; geçersizse ""
  const m = /^(\d{1,2}):(\d{2})$/.exec(typeof x === "string" ? x.trim() : "");
  const s = m ? `${m[1].padStart(2, "0")}:${m[2]}` : "";
  return hm(s) == null ? "" : s;
}

// state/yayin_plani.json -> {seriler, sablon_seri, hafta: 7 gün (Pazartesi ilk), istisnalar}; geçersizse null
export function planCoz(d) {
  if (!d || typeof d !== "object" || !Array.isArray(d.hafta)) return null;
  const seriler = [];
  for (const s of Array.isArray(d.seriler) ? d.seriler.slice(0, 20) : []) {
    if (!s || !ANAHTAR_RE.test(s.key) || seriler.some((x) => x.key === s.key)) continue;
    seriler.push({ key: s.key, ad: yazi(s.ad, 60) || s.key, ikon: yazi(s.ikon, 8), sablon: yazi(s.sablon, 30),
      yeni_sablon: yazi(s.yeni_sablon, 30), durum: SERI_DURUMLARI.includes(s.durum) ? s.durum : "yayında",
      not: yazi(s.not, 300), baslangic: TARIH_RE.test(s.baslangic || "") ? s.baslangic : "" });
  }
  const hafta = GUN_ADLARI.map(() => []);
  for (const g of d.hafta) {
    const i = GUN_ADLARI.findIndex((a) => a.toLocaleLowerCase("tr") === String((g && g.gun) || "").toLocaleLowerCase("tr"));
    if (i < 0 || !Array.isArray(g.slotlar)) continue;
    for (const x of g.slotlar.slice(0, 12)) {
      const saat = hmYaz(x && x.saat);
      if (saat && ANAHTAR_RE.test(x.seri)) hafta[i].push({ saat, seri: x.seri });
    }
    hafta[i].sort((a, b) => hm(a.saat) - hm(b.saat));
  }
  if (!hafta.some((g) => g.length)) return null;
  for (const g of hafta) { // planda olup seri listesinde olmayan seri de görünsün
    for (const x of g) if (!seriler.some((s) => s.key === x.seri)) seriler.push({ key: x.seri, ad: x.seri, ikon: "", sablon: "", yeni_sablon: "", durum: "yayında", not: "", baslangic: "" });
  }
  const sablon_seri = {};
  for (const [k, v] of Object.entries(d.sablon_seri && typeof d.sablon_seri === "object" ? d.sablon_seri : {})) {
    if (ANAHTAR_RE.test(k) && ANAHTAR_RE.test(v)) sablon_seri[k] = v;
  }
  const istisnalar = [];
  for (const x of Array.isArray(d.istisnalar) ? d.istisnalar.slice(0, 100) : []) {
    const [gun, saat] = String((x && x.zaman) || "").split(" ");
    if (TARIH_RE.test(gun || "") && hmYaz(saat)) istisnalar.push({ zaman: `${gun} ${hmYaz(saat)}`, seri: ANAHTAR_RE.test(x.seri) ? x.seri : "", neden: yazi(x.neden, 200) });
  }
  return { seriler, sablon_seri, hafta, istisnalar };
}

// takvim.seri_of: önce anlatım kalıbı (plan serisi ise), sonra şablon; ikisi de değilse "genel"
export function seriOf(v, plan) {
  if (plan.seriler.some((s) => s.key === v.structure)) return v.structure;
  return plan.sablon_seri[String(v.template || "")] || "genel";
}

// videonun takvimdeki anları: paylaşılmış platformların saati, bekleyen platform saatleri ve publish_at
function videoAnlari(v) {
  const out = new Set();
  const ekle = (x) => { const t = Date.parse(x || ""); if (Number.isFinite(t)) out.add(t); };
  const pf = v.platforms && typeof v.platforms === "object" ? v.platforms : {};
  const ok = okPlatformlar(v);
  for (const [p, t] of Object.entries(v.schedule && typeof v.schedule === "object" ? v.schedule : {})) if (!ok.has(p)) ekle(t);
  for (const p of ok) ekle(pf[p] && pf[p].at);
  if (!ok.size || v.status === "zamanlandi") ekle(v.publish_at);
  if (!out.size) ekle(v.published);
  return [...out].sort((a, b) => a - b);
}

function videoOzeti(v, seri, an) {
  const pf = v.platforms && typeof v.platforms === "object" ? v.platforms : {};
  const linkler = {};
  for (const p of PLATFORMLAR) {
    const u = pf[p] && pf[p].status === "ok" && typeof pf[p].url === "string" && /^https:\/\//.test(pf[p].url) ? pf[p].url : null;
    if (u) linkler[p] = u;
  }
  return { tag: v.tag, title: yazi(v.title, 160) || v.tag, status: v.status, seri, an: new Date(an).toISOString(), linkler };
}

// Önümüzdeki `gun` gün: her gün planın saatleri, eşleşen video ya da boş; plana uymayan videolar da kendi saatinde.
export function yayinTakvimi(plan, videos, simdi, gun = PLAN_GUN) {
  const bugun = gunKodu(simdi), bas = gunBasiMs(bugun), son = bas + gun * 86400e3;
  const seri = Object.fromEntries(plan.seriler.map((s) => [s.key, s]));
  const kapali = new Map(plan.istisnalar.map((x) => [x.zaman, x]));
  const adaylar = [];
  for (const v of videos || []) {
    if (!v || typeof v !== "object" || typeof v.tag !== "string" || !TAKVIMDE.has(v.status)) continue;
    const anlar = videoAnlari(v).filter((t) => t >= bas && t < son);
    if (anlar.length) adaylar.push({ v, anlar, seri: seriOf(v, plan), kullanildi: false });
  }
  const gunler = [];
  for (let i = 0; i < gun; i++) {
    const g0 = bas + i * 86400e3, kod = gunKodu(g0 + 43200e3);
    const hg = (new Date(g0 + TR_OFFSET + 43200e3).getUTCDay() + 6) % 7;
    const ogeler = plan.hafta[hg].map((x) => {
      const an = g0 + hm(x.saat) * 60e3, k = kapali.get(`${kod} ${x.saat}`);
      const s = seri[x.seri] || {};
      const o = { saat: x.saat, an: new Date(an).toISOString(), seri: x.seri, plan: true, gecti: an < simdi };
      if (k && (!k.seri || k.seri === x.seri)) { o.kapali = true; o.neden = k.neden; }
      if (s.baslangic && kod < s.baslangic) { o.baslamadi = true; o.baslangic = s.baslangic; }
      return o;
    });
    gunler.push({ tarih: kod, gun_adi: GUN_ADLARI[hg], bugun: kod === bugun, ogeler, g0 });
  }
  const tumOgeler = gunler.flatMap((g) => g.ogeler);
  // 1) aynı serinin en yakın videosu (±90 dk), 2) başka serinin tam o saatteki videosu (±30 dk)
  for (const [ayni, pay] of [[true, ESLESME_MS], [false, SAAT_ESLESME_MS]]) {
    for (const o of tumOgeler) {
      if (o.video) continue;
      const an = Date.parse(o.an);
      let enIyi = null, fark = Infinity;
      for (const a of adaylar) {
        if (a.kullanildi || (ayni && a.seri !== o.seri)) continue;
        for (const t of a.anlar) if (Math.abs(t - an) <= pay && Math.abs(t - an) < fark) { enIyi = a; fark = Math.abs(t - an); }
      }
      if (enIyi) {
        enIyi.kullanildi = true;
        o.video = videoOzeti(enIyi.v, enIyi.seri, enIyi.anlar[0]);
        if (!ayni) o.video.seri_farkli = true;
      }
    }
  }
  for (const a of adaylar) { // plan dışı: ilk anının gününe
    if (a.kullanildi) continue;
    const g = gunler.find((x) => x.tarih === gunKodu(a.anlar[0]));
    if (!g) continue;
    const t = a.anlar[0];
    g.ogeler.push({ saat: new Date(t + TR_OFFSET).toISOString().slice(11, 16), an: new Date(t).toISOString(), seri: a.seri,
      plan: false, gecti: t < simdi, video: videoOzeti(a.v, a.seri, t) });
  }
  for (const g of gunler) { g.ogeler.sort((a, b) => Date.parse(a.an) - Date.parse(b.an)); delete g.g0; }
  return gunler;
}

// Her seri: şablonu, durumu, haftalık saatleri, sıradaki plan saati, son paylaşılan video, bekleyen videolar
export function seriOzetleri(plan, videos, gunler, simdi) {
  const kisa = (g) => ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"][g];
  return plan.seriler.map((s) => {
    const slot = [];
    plan.hafta.forEach((g, i) => g.forEach((x) => { if (x.seri === s.key) slot.push(`${kisa(i)} ${x.saat}`); }));
    const sonraki = gunler.flatMap((g) => g.ogeler).find((o) => o.plan && o.seri === s.key && !o.gecti && !o.kapali && !o.baslamadi);
    let son = null, onay = 0, plan_ = 0;
    for (const v of videos || []) {
      if (!v || typeof v !== "object" || seriOf(v, plan) !== s.key) continue;
      if (v.status === "onay_bekliyor") onay++;
      else if (v.status === "zamanlandi" || v.status === "yayinlaniyor") plan_++;
      else if (v.status === "yayinlandi" || v.status === "kismen") {
        const t = Date.parse(v.published || "") || videoAnlari(v).pop() || 0;
        if (t <= simdi && (!son || t > son.t)) son = { t, v };
      }
    }
    return { ...s, haftalik: slot.length, saatler: slot,
      sonraki: sonraki ? { an: sonraki.an, saat: sonraki.saat, tarih: gunKodu(Date.parse(sonraki.an)),
        video: sonraki.video ? { tag: sonraki.video.tag, title: sonraki.video.title, status: sonraki.video.status } : null } : null,
      son_video: son ? { tag: son.v.tag, title: yazi(son.v.title, 160) || son.v.tag, an: new Date(son.t).toISOString() } : null,
      onay_bekleyen: onay, zamanlanan: plan_ };
  });
}

// script._period ile aynı dönem: kredi her ay CLAUDE_BUDGET_RESET_DAY'de (varsayılan 24) yenilenir; gün 1 ise "YYYY-AA"
export function claudeOzeti(kullanim, env = {}, simdi = Date.now()) {
  const u = kullanim && typeof kullanim === "object" && !Array.isArray(kullanim) ? kullanim : {};
  const gun = Math.min(Math.max(parseInt(env.CLAUDE_BUDGET_RESET_DAY || "24", 10) || 1, 1), 28);
  const tavan = Number(env.CLAUDE_MONTHLY_BUDGET_USD) > 0 ? Number(env.CLAUDE_MONTHLY_BUDGET_USD) : 90;
  const t = new Date(simdi);
  let y = t.getUTCFullYear(), m = t.getUTCMonth();
  if (t.getUTCDate() < gun) { m -= 1; if (m < 0) { m = 11; y -= 1; } }
  const p2 = (n) => String(n).padStart(2, "0");
  const anahtar = gun === 1 ? `${y}-${p2(m + 1)}` : `${y}-${p2(m + 1)}-${p2(gun)}`;
  const bitis = new Date(Date.UTC(y, m + 1, gun) - 86400e3).toISOString().slice(0, 10);
  const harcanan = Number(u[anahtar]) || 0;
  const oran = harcanan / tavan;
  const gecmis = Object.entries(u).filter(([k, v]) => k !== anahtar && /^\d{4}-\d{2}(-\d{2})?$/.test(k) && typeof v === "number")
    .sort(([a], [b]) => (a < b ? 1 : -1)).slice(0, 6).map(([donem, h]) => ({ donem, harcanan: Math.round(h * 100) / 100 }));
  return { donem: anahtar, baslangic: `${y}-${p2(m + 1)}-${p2(gun)}`, bitis, tavan, harcanan: Math.round(harcanan * 100) / 100,
    kalan: Math.round(Math.max(0, tavan - harcanan) * 100) / 100, oran: Math.round(oran * 1000) / 1000,
    uyari: oran >= 0.8, doldu: oran >= 1, gecmis };
}

// state/secim/plan_s1.json (Karar Senin sezon planı) -> salt okunur hikâye; geçersizse null
export function hikayeCoz(d) {
  if (!d || typeof d !== "object" || !Array.isArray(d.donum_noktalari)) return null;
  const AB = (x) => ({ A: yazi(x && x.A, 200), B: yazi(x && x.B, 200) });
  const oy = (x) => ({ A: Number.isFinite(x && x.A) ? Math.max(0, x.A) : null, B: Number.isFinite(x && x.B) ? Math.max(0, x.B) : null });
  const belge = typeof d.plan_belgesi === "string" && /^https:\/\/claude\.ai\/[\w/-]+$/.test(d.plan_belgesi) ? d.plan_belgesi : null;
  return {
    sezon: tamSayi(d.sezon, 1, 99) || 1, ad: yazi(d.ad, 80), ozet: yazi(d.ozet, 600), bolum_sayisi: tamSayi(d.bolum_sayisi, 1, 50),
    bolum_suresi: yazi(d.bolum_suresi, 40), yayin: yazi(d.yayin, 80), ilk_bolum: yazi(d.ilk_bolum, 40), oylama: yazi(d.oylama, 120),
    sablon: yazi(d.sablon, 40), plan_belgesi: belge, karakter_notu: yazi(d.karakter_notu, 120),
    karakterler: (Array.isArray(d.karakterler) ? d.karakterler.slice(0, 20) : []).filter((k) => k && yazi(k.ad))
      .map((k) => ({ ad: yazi(k.ad, 40), yas: tamSayi(k.yas, 0, 120), rol: yazi(k.rol, 120) })),
    donum_noktalari: d.donum_noktalari.slice(0, 30).filter((x) => x && tamSayi(x.bolum, 1, 99))
      .map((x) => ({ bolum: x.bolum, yas: tamSayi(x.yas, 0, 120), baslik: yazi(x.baslik, 120), ikilem: yazi(x.ikilem, 300), bilgi: yazi(x.bilgi, 300) })),
    bolumler: (Array.isArray(d.bolumler) ? d.bolumler.slice(0, 50) : []).filter((x) => x && tamSayi(x.bolum, 1, 99))
      .map((x) => ({ bolum: x.bolum, yayin: yazi(x.yayin, 40), secenekler: AB(x.secenekler), oylar: oy(x.oylar),
        kazanan: x.kazanan === "A" || x.kazanan === "B" ? x.kazanan : "" })),
  };
}

// state/yenilikler.json: [{tarih, metin}] -> en yeni üstte, en çok 12
export function yeniliklerCoz(d) {
  const l = Array.isArray(d) ? d : d && Array.isArray(d.yenilikler) ? d.yenilikler : null;
  if (!l) return null;
  return l.filter((x) => x && TARIH_RE.test(x.tarih || "") && yazi(x.metin)).map((x, i) => ({ tarih: x.tarih, metin: yazi(x.metin, 240), i }))
    .sort((a, b) => (a.tarih === b.tarih ? a.i - b.i : a.tarih < b.tarih ? 1 : -1)).slice(0, 12).map(({ tarih, metin }) => ({ tarih, metin }));
}

async function planOku(env) {
  const adlar = Object.keys(PLAN_DOSYALARI);
  const sonuc = await Promise.all(adlar.map((a) => dosya(env, PLAN_DOSYALARI[a])));
  const f = Object.fromEntries(adlar.map((a, i) => [a, sonuc[i]]));
  const uyarilar = adlar.filter((a) => f[a].hata).map((a) => `${PLAN_OKUNAMADI[a]} (${f[a].hata}).`);
  const simdi = Date.now();
  const tum = jsonCoz(f.videos.metin, []);
  const videos = Array.isArray(tum) ? tum : [];
  const plan = f.plan.metin == null ? null : planCoz(jsonCoz(f.plan.metin, null));
  if (f.plan.metin != null && !plan) uyarilar.push("Yayın planı dosyası (state/yayin_plani.json) bozuk; takvim gösterilemiyor.");
  const takvim = plan ? yayinTakvimi(plan, videos, simdi) : null;
  return {
    zaman: new Date(simdi).toISOString(),
    plan: plan && { seriler: plan.seriler, hafta: plan.hafta.map((g, i) => ({ gun: GUN_ADLARI[i], slotlar: g })), istisnalar: plan.istisnalar },
    takvim,
    seriler: plan ? seriOzetleri(plan, videos, takvim, simdi) : null,
    hikaye: f.hikaye.metin == null ? null : hikayeCoz(jsonCoz(f.hikaye.metin, null)),
    claude: f.claude.hata ? null : claudeOzeti(jsonCoz(f.claude.metin || "{}", {}), env, simdi),
    yenilikler: f.yenilikler.metin == null ? null : yeniliklerCoz(jsonCoz(f.yenilikler.metin, null)),
    uyarilar,
  };
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

// Takvimden gelen platform saatleri (telegram_bot._check_schedule ile aynı kurallar). Onay bekleyen videoda paylaşılmamış
// her platform verilmeli (bu bir onaydır; kalanları iptal edilmiş videoda paylaşılmış platform olabilir); zamanlanmış
// videoda yalnız henüz paylaşılmamış platformlar, verilmeyenler aynı kalır. Paylaşılmış platformun saati verilemez.
function saatleriAl(b, video) {
  const fazla = Object.keys(b).filter((k) => !["action", "tag", "schedule"].includes(k));
  if (fazla.length) throw new Hata(400, "İstekte bilinmeyen alan var.");
  const s = b.schedule;
  if (!s || typeof s !== "object" || Array.isArray(s) || !Object.keys(s).length) throw new Hata(400, "Platform saatleri eksik.");
  if (Object.keys(s).some((k) => !PLATFORMLAR.includes(k))) throw new Hata(400, "Bilinmeyen platform.");
  const onay = video.status === "onay_bekliyor";
  const ok = okPlatformlar(video);
  const paylasilan = PLATFORMLAR.filter((p) => p in s && ok.has(p));
  if (paylasilan.length) {
    throw new Hata(409, `${paylasilan.map((p) => PF_ADI[p]).join(", ")} zaten paylaşıldı; saati değiştirilemez. Sayfa yenileniyor.`);
  }
  const eksik = PLATFORMLAR.filter((p) => !(p in s) && !ok.has(p));
  if (onay && eksik.length) {
    throw new Hata(400, ok.size ? `Onay için ${eksik.map((p) => PF_ADI[p]).join(", ")} saati de seçilmeli.`
      : "Onay için üç platformun da saati seçilmeli.");
  }
  const simdi = Date.now();
  const an = paylasimAni(video);
  if (!onay && an != null && an <= simdi + YAKIN_MS) {
    throw new Hata(409, "Bir paylaşım şu an sürüyor ya da 10 dakika içinde başlayacak; saatler şimdi değiştirilemez.");
  }
  const out = {};
  for (const p of PLATFORMLAR) {
    if (!(p in s)) continue;
    const ham = typeof s[p] === "string" && ISO_RE.test(s[p]) ? Date.parse(s[p]) : NaN;
    if (!Number.isFinite(ham)) throw new Hata(400, `${PF_ADI[p]} saati geçersiz.`);
    const t = Math.round(ham / 60e3) * 60e3;
    if (t < simdi + SAAT_EN_ERKEN) throw new Hata(409, `${PF_ADI[p]} için seçilen saat geçti ya da çok yakın; en erken 2 dakika sonrası seçilebilir.`);
    if (t > simdi + SAAT_EN_GEC) throw new Hata(400, `${PF_ADI[p]} saati en çok 30 gün sonrası olabilir.`);
    out[p] = new Date(t).toISOString().slice(0, 19) + "+00:00";
  }
  if (!onay) {
    const eski = video.schedule && typeof video.schedule === "object" ? video.schedule
      : Object.fromEntries(PLATFORMLAR.map((p) => [p, video.publish_at]));
    if (Object.keys(out).every((p) => Date.parse(eski[p] || "") === Date.parse(out[p]))) {
      throw new Hata(400, "Saatlerde değişiklik yok.");
    }
  }
  return out;
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
    if (action === "schedule") p.schedule = saatleriAl(b, video);
    if (action === "edit") {
      // paylaşım işi publish_at'te başlar ve durumu yüklemeden sonra kaydeder (telegram_bot.EDIT_GUARD_MIN ile aynı)
      if (video.status === "zamanlandi" && video.publish_at && Date.parse(video.publish_at) <= Date.now() + 10 * 60e3) {
        throw new Hata(409, "Bir paylaşım şu an sürüyor ya da 10 dakika içinde başlayacak; şimdi düzenlenemez. Paylaşılmayan platform kalırsa sonra yeniden dene.");
      }
      p.title = metinAl(b.title, "Başlık", 1, SINIR.baslik);
      p.description = aciklamaDenetle(metinAl(b.description, "Açıklama", 1, SINIR.aciklama, true));
    }
  } else if (action === "produce_suggestion") {
    if (!Number.isInteger(b.index) || b.index < 0 || b.index >= ONERI_SIRA_SINIRI) throw new Hata(400, "Geçersiz öneri.");
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
  if (yol === "durum" || yol === "plan") {
    return new Response(await (yol === "plan" ? planDurumu : durum)(env, ctx, oturum), {
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
