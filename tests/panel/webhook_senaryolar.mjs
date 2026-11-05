// Telegram webhook yolunun (POST /, gizli başlık) davranışı: temsilî olaylar ve kapının yaptığı tüm giden istekler.
// fixtures/webhook_golden.json panelden ÖNCEKİ worker.js ile üretildi; yeni kapı aynı çağrıları yapmalı.
//   node tests/panel/webhook_senaryolar.mjs <worker.js yolu> > tests/panel/fixtures/webhook_golden.json
import { pathToFileURL } from "node:url";
import { ORTAM, fetchKur, ctxYap, saatKur, saatBirak, cacheKur } from "./sahte.mjs";

export const SABIT_SAAT = Date.parse("2026-11-05T00:45:00+03:00");
const SOHBET = Number(ORTAM.CHAT_ID);
const TAG = "short-20261104-1019";
const KB = { inline_keyboard: [[{ text: "✅ Onayla", callback_data: `ok:${TAG}` }, { text: "❌ Reddet", callback_data: `no:${TAG}` }]] };

function cq(data, from = SOHBET) {
  return { update_id: 1, callback_query: { id: "cq1", from: { id: from }, data,
    message: { message_id: 2, chat: { id: SOHBET }, reply_markup: KB } } };
}
function msg(text, ek = {}) {
  return { update_id: 2, message: { message_id: 50, chat: { id: SOHBET }, from: { id: SOHBET }, text, ...ek } };
}

export const SENARYOLAR = [
  ["düğme ok (saat seçenekleri)", cq(`ok:${TAG}`)],
  ["düğme back", cq(`back:${TAG}`)],
  ["düğme at:best", cq(`at:${TAG}:best`)],
  ["düğme at:y19", cq(`at:${TAG}:y19`)],
  ["düğme no", cq(`no:${TAG}`)],
  ["düğme cancel", cq(`cancel:${TAG}`)],
  ["düğme rt", cq(`rt:${TAG}`)],
  ["düğme tp (kilitlenmez)", cq("tp:_:1")],
  ["düğme noop", cq("noop:x")],
  ["düğme at, GitHub reddetti", cq(`at:${TAG}:now`), { dispatchDurum: 500 }],
  ["mesaj /start", msg("/start")],
  ["mesaj /yardim", msg("/yardim")],
  ["mesaj /durum", msg("/durum")],
  ["mesaj /uret konu", msg("/uret kara delikler")],
  ["yanıt mesajı", msg("Teşekkürler, çok güzel olmuş!", { reply_to_message: { message_id: 77 } })],
  ["sohbet mesajı (işlem yok)", msg("merhaba")],
  ["metinsiz mesaj", { update_id: 3, message: { message_id: 51, chat: { id: SOHBET }, photo: [{}] } }],
  ["başka kişi (düğme)", cq(`no:${TAG}`, 999)],
  ["başka kişi (mesaj)", { update_id: 4, message: { message_id: 52, chat: { id: 999 }, text: "/durum" } }],
  ["yanlış gizli başlık", msg("/durum"), { gizli: "yanlis" }],
  ["gizli başlık yok", msg("/durum"), { gizli: null }],
  ["bozuk JSON", "{bozuk", {}],
  ["GET /", null, { method: "GET" }],
  ["GET /baska/yol", null, { method: "GET", yol: "/baska/yol" }],
];

export async function calistir(worker, senaryolar = SENARYOLAR) {
  const out = [];
  saatKur(SABIT_SAAT);
  cacheKur();
  const log = console.log;
  let loglar = [];
  console.log = (...a) => loglar.push(a.map(String).join(" "));
  try {
    for (const [ad, olay, ayar = {}] of senaryolar) {
      loglar = [];
      const { cagrilar } = fetchKur(ayar);
      const { ctx, bitir } = ctxYap();
      const headers = { "content-type": "application/json" };
      if (ayar.gizli !== null) headers["X-Telegram-Bot-Api-Secret-Token"] = ayar.gizli || ORTAM.WEBHOOK_SECRET;
      const method = ayar.method || "POST";
      const req = new Request("https://bilgimakasi-kapi.bilgimakasi.workers.dev" + (ayar.yol || "/"), {
        method, headers, body: method === "GET" ? undefined : (typeof olay === "string" ? olay : JSON.stringify(olay)) });
      const r = await worker.fetch(req, { ...ORTAM }, ctx);
      await bitir();
      out.push({ ad, yanit: { status: r.status, govde: await r.text() }, loglar,
        cagrilar: cagrilar.map((c) => ({ method: c.method, url: c.url, govde: c.govde,
          ...(c.url.includes("api.github.com") ? { yetki: c.basliklar.authorization } : {}) })) });
    }
  } finally {
    saatBirak();
    console.log = log;
  }
  return out;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const mod = await import(pathToFileURL(process.argv[2]).href);
  process.stdout.write(JSON.stringify(await calistir(mod.default), null, 1) + "\n");
}
