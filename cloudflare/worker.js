// Bilgi Makası Telegram kapısı (Cloudflare Worker, 7/24 açık).
// Telegram her düğme basışını ve mesajı buraya gönderir (webhook).
// Kapı anında "⏳ Alındı" der; işin kendisini GitHub'daki isle.yml'e iletir.
// Yalnız arayüz olan adımları (Onayla -> saat seçenekleri, Geri) kendisi anında yapar.
// /panel altındaki adresler yönetim panelidir (cloudflare/panel.js); /panel komutuna giriş bağlantısını kapı verir.
//
// Gizli değerler (bot_kapi.yml yükler): TELEGRAM_BOT_TOKEN, CHAT_ID, GH_PAT, WEBHOOK_SECRET, PANEL_SECRET, REPO

import { panel, girisMesaji } from "./panel.js";

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
      await tg(env, "editMessageReplyMarkup", { chat_id: chat, message_id: mid, reply_markup: kb(rows) });
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
    await tg(env, "sendMessage", await girisMesaji(env, m.chat.id, origin));
    return;
  }
  const isReply = !!(m.reply_to_message && !text.startsWith("/"));
  if (!text.startsWith("/") && !isReply) return; // sohbet mesajı: işlem yok
  await tg(env, "sendChatAction", { chat_id: m.chat.id, action: "typing" });
  await dispatch(env, update);
}

export default {
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
