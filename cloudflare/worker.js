// Bilgi Makası Telegram kapısı (Cloudflare Worker, 7/24 açık).
// Telegram her düğme basışını ve mesajı buraya gönderir (webhook).
// Kapı anında "⏳ Alındı" der; işin kendisini GitHub'daki isle.yml'e iletir.
// Yalnız arayüz olan adımları (Onayla -> saat seçenekleri, Geri) kendisi anında yapar.
// /panel altındaki adresler yönetim panelidir (cloudflare/panel.js); /panel komutuna giriş bağlantısını kapı verir.
// Zamanlayıcı (Cloudflare cron, dakikada bir; bot_kapi.yml kurar): saati 3 dakika içinde gelecek bir paylaşım varsa
// onay.yml'i o anı hedefleyerek başlatır ki takvimde seçilen her saat (yalnız seyrek GitHub cron saatleri değil) tutsun.
//
// Gizli değerler (bot_kapi.yml yükler): TELEGRAM_BOT_TOKEN, CHAT_ID, GH_PAT (KAPI_PAT: yalnız bilgimakasi için
// Actions okuma/yazma + Contents okuma), WEBHOOK_SECRET, PANEL_SECRET, REPO; isteğe bağlı PANEL_EPOCH

import { panel, girisGonder, dosya, jsonCoz, ghBasliklari, paylasimAnlari } from "./panel.js";

const TR_OFFSET = 3 * 3600 * 1000; // Türkiye UTC+3, yaz saati yok

async function tg(env, method, body) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) console.log(method, r.status, await r.text());
  return r;
}

function kb(rows) {
  return { inline_keyboard: rows.map((r) => r.map(([text, data]) => ({ text, callback_data: data }))) };
}

// telegram_bot._slots ile aynı seçenekler (kodlar aynı; saati Python işlerken hesaplar)
function slots() {
  const now = new Date(Date.now() + TR_OFFSET); // UTC alanları = Türkiye saati
  const y = now.getUTCFullYear(), m = now.getUTCMonth(), d = now.getUTCDate();
  const out = [["best", "🎯 Her platform en iyi saatinde"], ["now", "⚡ Şimdi"]];
  for (const [code, label, add, h] of [["b12", "Bugün 12:00", 0, 12], ["b19", "Bugün 19:00", 0, 19],
                                       ["y12", "Yarın 12:00", 1, 12], ["y19", "Yarın 19:00", 1, 19]]) {
    if (Date.UTC(y, m, d + add, h) > now.getTime() + 15 * 60 * 1000) out.push([code, "🕒 " + label]);
  }
  return out;
}

async function dispatch(env, update) {
  const r = await fetch(`https://api.github.com/repos/${env.REPO}/actions/workflows/isle.yml/dispatches`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GH_PAT}`,
      accept: "application/vnd.github+json",
      "user-agent": "bilgimakasi-kapi",
      "content-type": "application/json",
    },
    body: JSON.stringify({ ref: "main", inputs: { update: JSON.stringify(update) } }),
  });
  if (r.status !== 204) {
    const t = await r.text();
    console.log("dispatch", r.status, t);
    await tg(env, "sendMessage", { chat_id: env.CHAT_ID, text: `⚠️ İşlem GitHub'a iletilemedi (${r.status}). Birazdan tekrar dene.` });
    return false;
  }
  return true;
}

const HELP = "Merhaba! Yeni videolar buraya onaya gelir.\n\n" +
  "/oneri: gündemden 5 konu önerisi (butonla üret)\n" +
  "/uret [konu]: hemen yeni video üret (konu isteğe bağlı)\n" +
  "/durum: bekleyen ve zamanlanan videolar\n" +
  "/rapor: izlenme, takipçi, beğeni, kaydetme raporu\n" +
  "/saatler: platformların en iyi paylaşım saatleri\n" +
  "/panel: yönetim paneline giriş bağlantısı\n" +
  "/yardim: bu liste";

async function handle(update, env, origin) {
  const cq = update.callback_query;
  if (cq) {
    const [action, tag] = cq.data.split(":");
    const chat = cq.message.chat.id, mid = cq.message.message_id;
    if (action === "noop") {
      await tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text: "İşleniyor, biraz bekle…" });
      return;
    }
    if (action === "ok") { // arayüz adımı: saat seçenekleri anında
      const s = slots();
      const rows = [];
      for (let i = 0; i < s.length; i += 2) rows.push(s.slice(i, i + 2).map(([c, l]) => [l, `at:${tag}:${c}`]));
      rows.push([["↩️ Geri", `back:${tag}`]]);
      const markup = kb(rows);
      // her platform için saati elle seçmek: panel Takvim sekmesinde bu videonun saat sayfasıyla açılır
      markup.inline_keyboard.splice(-1, 0, [{ text: "🗓 Takvimde seç", url: `${origin}/panel#takvim/${encodeURIComponent(tag)}` }]);
      await tg(env, "editMessageReplyMarkup", { chat_id: chat, message_id: mid, reply_markup: markup });
      await tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text: "Ne zaman paylaşılsın?" });
      return;
    }
    if (action === "back") {
      await tg(env, "editMessageReplyMarkup", { chat_id: chat, message_id: mid,
        reply_markup: kb([[["✅ Onayla", `ok:${tag}`], ["❌ Reddet", `no:${tag}`]]]) });
      await tg(env, "answerCallbackQuery", { callback_query_id: cq.id });
      return;
    }
    // durum değiştiren adımlar: anında geri bildirim + çift basışı engelle + GitHub'a ilet
    await tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text: "⏳ Alındı, işleniyor (30-60 sn)…" });
    const lock = ["at", "no", "cancel", "cm", "rt"].includes(action); // tp (öneri listesi) kilitlenmez
    if (lock) {
      await tg(env, "editMessageReplyMarkup", { chat_id: chat, message_id: mid,
        reply_markup: kb([[["⏳ İşleniyor…", "noop:x"]]]) });
    }
    let ok = false;
    try { ok = await dispatch(env, update); } catch (e) {
      console.log("dispatch hata", e && e.stack);
      await tg(env, "sendMessage", { chat_id: env.CHAT_ID, text: "⚠️ İşlem GitHub'a iletilemedi. Birazdan tekrar dene." });
    }
    if (!ok && lock) { // basılan klavyeyi geri koy ki tekrar denenebilsin
      await tg(env, "editMessageReplyMarkup", { chat_id: chat, message_id: mid,
        reply_markup: cq.message.reply_markup || { inline_keyboard: [] } });
    }
    return;
  }
  const m = update.message;
  if (!m || !m.text) return;
  const text = m.text.trim();
  if (text.startsWith("/start") || text.startsWith("/yardim")) {
    await tg(env, "sendMessage", { chat_id: m.chat.id, text: HELP });
    return;
  }
  if (/^\/panel(@\w+)?(\s|$)/.test(text)) { // panel giriş bağlantısı: imzayı kapı atar, GitHub'a gitmez
    await girisGonder(env, m.chat.id, origin);
    return;
  }
  const isReply = !!(m.reply_to_message && !text.startsWith("/"));
  if (!text.startsWith("/") && !isReply) return; // sohbet mesajı: işlem yok
  await tg(env, "sendChatAction", { chat_id: m.chat.id, action: "typing" });
  await dispatch(env, update);
}

// ---------------------------------------------------------------- zamanlayıcı
// bu kadar içinde gelecek paylaşım için iş başlatılır (cron dakikada bir; iş ~1 dk'da kurulur, Actions dakikası beklemeye
// harcanmasın); telegram_bot.DUE_WINDOW ile aynı
const ONCE_MS = 3 * 60e3;
const ESKI_MS = 3 * 3600e3; // bundan eski bekleyen saat için başlatılmaz (takılı bir kayıt döngü yapmasın)
const TEKRAR_MS = 30 * 60e3; // aynı hedefle son 30 dk'da başlatılmış iş varsa yenisi başlatılmaz
const BASLAMAMIS = ["queued", "pending", "waiting", "requested"]; // state grubunda sırasını bekleyen iş

// onay.yml "hedef" girdisi ve iş adındaki an: UTC, dakika (ör. 2026-11-05T15:00Z); telegram_bot._due_inputs ile aynı
export const hedefAdi = (ms) => new Date(ms).toISOString().slice(0, 16) + "Z";

function gh(env, yol, init = {}) {
  return fetch(`https://api.github.com/repos/${env.REPO}/${yol}`, {
    ...init, headers: { ...ghBasliklari(env, "application/vnd.github+json"), ...(init.headers || {}) },
  });
}

// onay.yml'in son 20 işi (iş adı hedefi içerir); öğrenilemezse null
async function isListesi(env) {
  const r = await gh(env, "actions/workflows/onay.yml/runs?per_page=20");
  if (!r.ok) return null;
  const j = await r.json().catch(() => ({}));
  return Array.isArray(j.workflow_runs) ? j.workflow_runs : null;
}

// Bu paylaşım anını üstlenmiş iş var mı (telegram_bot._due_covered): aynı hedefle kuyrukta/çalışan ya da son 30 dk'da
// başlatılmış, iptal edilmemiş iş ("state" grubunda yenisi gelince bekleyen eski iş hiç çalışmadan iptal olur).
// Saati gelmiş paylaşımı henüz başlamamış herhangi bir iş de üstlenir: başlayınca saati gelenlerin hepsini paylaşır;
// yenisi başlatılırsa o işi iptal eder ve iki hedef birbirini iptal edip durur.
function isVar(isler, an, simdi) {
  const hedef = hedefAdi(an);
  return isler.some((x) => (an <= simdi && BASLAMAMIS.includes(x.status))
    || (`${x.display_title || ""} ${x.name || ""}`.includes(hedef)
      && (x.status !== "completed" || (x.conclusion !== "cancelled" && Date.parse(x.created_at) >= simdi - TEKRAR_MS))));
}

// Saati yaklaşan paylaşım varsa onay.yml'i başlatır. Kısa bir durum metni döndürür (günlük için).
// Anlara sırayla bakılır: üstlenen işi olan atlanır, ilk üstlenilmemiş an için iş başlatılır (saati geçmiş bir kaydın
// işi, ör. hata almış ya da hâlâ yükleyen iş, sonraki videonun paylaşımını bekletmesin).
export async function zamanliPaylasim(env, simdi = Date.now()) {
  if (!env.GH_PAT || !env.REPO) return "ayar yok";
  const f = await dosya(env, "state/videos.json");
  if (f.metin == null) return `durum okunamadı (${f.hata || "dosya yok"})`;
  const vs = jsonCoz(f.metin, []);
  // 3 saatten eski takılı bir kayıt sayılmaz (diğer videoların paylaşımını engellemesin, döngü yapmasın)
  const tumu = paylasimAnlari(Array.isArray(vs) ? vs : [], simdi - ESKI_MS);
  if (!tumu.length) return "bekleyen paylaşım yok";
  const anlar = tumu.filter((an) => an <= simdi + ONCE_MS);
  if (!anlar.length) return "erken";
  const isler = await isListesi(env);
  for (const an of anlar) {
    // iş listesi alınamadıysa saati geçmiş paylaşım için her dakika körlemesine iş başlatılmaz
    if (isler ? isVar(isler, an, simdi) : an < simdi) continue;
    const hedef = hedefAdi(an);
    const dakika = Math.min(15, Math.max(0, Math.ceil((an - simdi) / 60e3)) + 2);
    const r = await gh(env, "actions/workflows/onay.yml/dispatches", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ ref: "main", inputs: { dakika: String(dakika), hedef } }),
    });
    return r.status === 204 ? `başlatıldı (${hedef}, ${dakika} dk)` : `başlatılamadı (${r.status})`;
  }
  return isler ? `iş zaten var (${anlar.map(hedefAdi).join(", ")})` : "iş listesi alınamadı";
}

export default {
  // Cloudflare cron ("* * * * *"): hata fırlatmaz, yalnız kısa günlük yazar
  async scheduled(event, env, ctx) {
    try {
      console.log("zamanlayıcı:", await zamanliPaylasim(env, Date.now()));
    } catch (e) {
      console.log("zamanlayıcı hatası:", String((e && e.message) || e).slice(0, 200));
    }
  },
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (url.pathname === "/panel" || url.pathname.startsWith("/panel/")) return panel(req, env, ctx);
    if (req.method !== "POST") return new Response("Bilgi Makası kapısı çalışıyor.");
    if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    let update;
    try { update = await req.json(); } catch { return new Response("bad request", { status: 400 }); }
    const from = update.callback_query ? update.callback_query.from.id
      : update.message ? update.message.chat.id : null;
    if (String(from) !== String(env.CHAT_ID)) return new Response("ok"); // yalnız Sabri
    ctx.waitUntil(handle(update, env, url.origin).catch((e) => console.log("hata", e && e.stack)));
    return new Response("ok");
  },
};
