// Kapı ve panel testleri (gerçek ağ yok): /opt/node22/bin/node --test tests/panel/worker.test.mjs
import { test, describe, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import worker from "../../cloudflare/worker.js";
import { SAYFA_HTML, UYGULAMA_JS } from "../../cloudflare/panel_ui.js";
import { calistir, SENARYOLAR, SABIT_SAAT } from "./webhook_senaryolar.mjs";
import { ORTAM, BURASI, META, fetchKur, ctxYap, saatKur, saatIlerlet, saatBirak, cacheKur, imza } from "./sahte.mjs";

const HOST = "https://bilgimakasi-kapi.bilgimakasi.workers.dev";
const SN = () => Math.floor(Date.now() / 1000);
let sessiz = console.log;

async function istek(yol, { method = "GET", cerez, basliklar = {}, govde, env = ORTAM, fetchAyar } = {}) {
  const f = fetchKur(fetchAyar);
  const { ctx, bitir } = ctxYap();
  const h = { ...basliklar };
  if (cerez) h.cookie = `bm_oturum=${cerez}`;
  const r = await worker.fetch(new Request(HOST + yol, { method, headers: h,
    body: govde === undefined ? undefined : typeof govde === "string" ? govde : JSON.stringify(govde) }), { ...env }, ctx);
  await bitir();
  return { r, cagrilar: f.cagrilar };
}
const oturum = async (sure = 30 * 86400) => imza("oturum", SN() + sure);
const POST = (govde, cerez, ek = {}) => ({ method: "POST", cerez, govde,
  basliklar: { "content-type": "application/json", "x-panel": "1", ...ek } });
const dispatchlar = (c) => c.filter((x) => x.url.endsWith("/actions/workflows/isle.yml/dispatches"));
const panelOlayi = (c) => JSON.parse(dispatchlar(c)[0].govde.inputs.update).panel;

before(() => { saatKur(SABIT_SAAT); cacheKur(); console.log = () => {}; });
after(() => { saatBirak(); console.log = sessiz; });

// ------------------------------------------------------------------ webhook
describe("Telegram webhook davranışı değişmedi", () => {
  test("temsilî olaylarda giden istekler panelden önceki kapıyla aynı", async () => {
    const golden = JSON.parse(readFileSync(join(BURASI, "fixtures", "webhook_golden.json"), "utf8"));
    const yeni = await calistir(worker);
    saatKur(SABIT_SAAT); cacheKur(); console.log = () => {};
    assert.equal(yeni.length, golden.length);
    for (let i = 0; i < golden.length; i++) {
      const g = golden[i], y = yeni[i];
      if (g.ad === "mesaj /start" || g.ad === "mesaj /yardim") {
        // tek bilinçli fark: yardım metnine /panel satırı eklendi
        const eski = g.cagrilar[0].govde.text, yeniMetin = y.cagrilar[0].govde.text;
        assert.equal(yeniMetin, eski.replace("/yardim: bu liste", "/panel: yönetim paneline giriş bağlantısı\n/yardim: bu liste"));
        assert.deepEqual({ ...y, cagrilar: [] }, { ...g, cagrilar: [] });
        continue;
      }
      assert.deepEqual(y, g, g.ad);
    }
  });

  test("/panel komutu: kapı giriş bağlantısını kendisi yollar, GitHub'a gitmez", async () => {
    for (const metin of ["/panel", "/panel@BilgiMakasiBot", "  /panel  "]) {
      const { r, cagrilar } = await istek("/", { method: "POST", basliklar: { "X-Telegram-Bot-Api-Secret-Token": ORTAM.WEBHOOK_SECRET },
        govde: { message: { message_id: 5, chat: { id: 424242 }, text: metin } } });
      assert.equal(r.status, 200);
      assert.equal(cagrilar.length, 1, metin);
      assert.match(cagrilar[0].url, /\/sendMessage$/);
      const g = cagrilar[0].govde;
      assert.equal(g.chat_id, 424242);
      assert.equal(g.disable_web_page_preview, true);
      const m = /https:\/\/bilgimakasi-kapi\.bilgimakasi\.workers\.dev\/panel\/giris\?t=(\d+)\.([\w-]{43})/.exec(g.text);
      assert.ok(m, g.text);
      assert.equal(Number(m[1]), SN() + 600);
      assert.equal(g.reply_markup.inline_keyboard[0][0].url, m[0]);
      assert.ok(!g.text.includes(ORTAM.PANEL_SECRET));
    }
  });

  test("/panel başkasından gelirse cevap yok", async () => {
    const { cagrilar } = await istek("/", { method: "POST", basliklar: { "X-Telegram-Bot-Api-Secret-Token": ORTAM.WEBHOOK_SECRET },
      govde: { message: { message_id: 5, chat: { id: 1 }, text: "/panel" } } });
    assert.equal(cagrilar.length, 0);
  });

  test("PANEL_SECRET yoksa /panel kurulum notu verir, panel 503", async () => {
    const env = { ...ORTAM, PANEL_SECRET: undefined };
    const { cagrilar } = await istek("/", { method: "POST", env, basliklar: { "X-Telegram-Bot-Api-Secret-Token": ORTAM.WEBHOOK_SECRET },
      govde: { message: { message_id: 5, chat: { id: 424242 }, text: "/panel" } } });
    assert.match(cagrilar[0].govde.text, /Panel henüz kurulmadı/);
    assert.equal((await istek("/panel", { env })).r.status, 503);
  });
});

// ------------------------------------------------------------------ giriş
describe("giriş ve oturum", () => {
  test("geçerli bağlantı: 30 günlük güvenli çerez + /panel'e yönlendirme", async () => {
    const t = await imza("giris", SN() + 300);
    const { r } = await istek("/panel/giris?t=" + t);
    assert.equal(r.status, 302);
    assert.equal(r.headers.get("location"), "/panel");
    const c = r.headers.get("set-cookie");
    assert.match(c, /^bm_oturum=\d+\.[\w-]{43}; /);
    for (const k of ["HttpOnly", "Secure", "SameSite=Strict", "Path=/panel", "Max-Age=2592000"]) assert.ok(c.includes(k), k);
    const deger = /^bm_oturum=([^;]+)/.exec(c)[1];
    assert.equal(Number(deger.split(".")[0]), SN() + 30 * 86400);
    assert.equal((await istek("/panel/api/durum", { cerez: deger })).r.status, 200);
  });

  test("süresi dolmuş, bozuk, çok uzun ömürlü ve yanlış anahtarlı bağlantılar reddedilir", async () => {
    const gecerli = await imza("giris", SN() + 300);
    const [exp, sig] = gecerli.split(".");
    const kotu = [
      await imza("giris", SN() - 1), // süresi dolmuş
      `${exp}.${sig.slice(0, -1)}${sig.endsWith("A") ? "B" : "A"}`, // imza değişti
      `${Number(exp) + 1}.${sig}`, // süre değişti
      await imza("giris", SN() + 3600), // 10 dk'dan uzun
      await imza("giris", SN() + 300, "baska-anahtar"),
      await imza("oturum", SN() + 300), // oturum imzası giriş bağlantısı olarak kullanılamaz
      "", "abc", `${exp}.${sig}x`, `${exp}..${sig}`,
    ];
    for (const t of kotu) {
      const { r } = await istek("/panel/giris?t=" + encodeURIComponent(t));
      assert.equal(r.status, 403, t);
      assert.equal(r.headers.get("set-cookie"), null);
      const html = await r.text();
      assert.match(html, /\/panel/);
      assert.match(html, /süresi dolmuş/);
    }
  });

  test("bağlantı 10 dakika sonra geçersiz olur", async () => {
    const t = await imza("giris", SN() + 600);
    saatIlerlet(601 * 1000);
    assert.equal((await istek("/panel/giris?t=" + t)).r.status, 403);
  });

  test("API çerezsiz, bozuk, süresi dolmuş veya giriş imzalı çerezle 401", async () => {
    const iyi = await oturum();
    const kotu = [null, "x", iyi.slice(0, -2) + "zz", await imza("oturum", SN() - 5), await imza("giris", SN() + 300),
      await imza("oturum", SN() + 400 * 86400)];
    for (const c of kotu) {
      for (const yol of ["/panel/api/durum", "/panel/api/video/short-20261104-1019", "/panel/api/meta/short-20261104-1019"]) {
        const { r, cagrilar } = await istek(yol, { cerez: c });
        assert.equal(r.status, 401, `${yol} ${c}`);
        assert.equal((await r.json()).giris, true);
        assert.equal(cagrilar.length, 0, "yetkisiz istekte GitHub'a gidilmez");
      }
      const { r } = await istek("/panel/api/islem", POST({ action: "report" }, c));
      assert.equal(r.status, 401);
    }
  });

  test("çıkış çerezi siler (POST + X-Panel)", async () => {
    const c = await oturum();
    const { r } = await istek("/panel/api/cikis", POST({}, c));
    assert.equal(r.status, 200);
    assert.match(r.headers.get("set-cookie"), /^bm_oturum=; .*Max-Age=0/);
    assert.equal((await istek("/panel/api/cikis", { cerez: c })).r.status, 405);
  });
});

// ------------------------------------------------------------------ CSRF
describe("CSRF ve yöntem denetimi", () => {
  test("X-Panel başlığı olmadan, yabancı Origin ile veya JSON olmayan gövdeyle işlem yapılmaz", async () => {
    const c = await oturum();
    let x = await istek("/panel/api/islem", { method: "POST", cerez: c, govde: { action: "report" },
      basliklar: { "content-type": "application/json" } });
    assert.equal(x.r.status, 403);
    x = await istek("/panel/api/islem", POST({ action: "report" }, c, { "x-panel": "0" }));
    assert.equal(x.r.status, 403);
    x = await istek("/panel/api/islem", POST({ action: "report" }, c, { origin: "https://kotu.example" }));
    assert.equal(x.r.status, 403);
    assert.equal(dispatchlar(x.cagrilar).length, 0);
    x = await istek("/panel/api/islem", POST({ action: "report" }, c, { "content-type": "text/plain" }));
    assert.equal(x.r.status, 415);
    x = await istek("/panel/api/islem", { cerez: c });
    assert.equal(x.r.status, 405);
    x = await istek("/panel/api/durum", POST({}, c));
    assert.equal(x.r.status, 405);
    x = await istek("/panel/api/islem", POST({ action: "report" }, c, { origin: HOST }));
    assert.equal(x.r.status, 202);
  });
});

// ------------------------------------------------------------------ sayfa
describe("sayfa", () => {
  test("/panel HTML'i, app.js ve güvenlik başlıkları; sayfada gizli değer yok", async () => {
    const { r } = await istek("/panel");
    assert.equal(r.status, 200);
    assert.match(r.headers.get("content-type"), /text\/html/);
    const csp = r.headers.get("content-security-policy");
    assert.match(csp, /script-src 'self'/);
    assert.match(csp, /frame-ancestors 'none'/);
    const html = await r.text();
    assert.match(html, /<html lang="tr">/);
    assert.match(html, /\/panel\/app\.js/);
    const js = await (await istek("/panel/app.js")).r.text();
    assert.equal(js, UYGULAMA_JS);
    new Function(js); // sözdizimi
    for (const gizli of Object.values(ORTAM)) {
      if (gizli === ORTAM.REPO) continue;
      assert.ok(!html.includes(gizli) && !js.includes(gizli), "sayfada gizli değer var: " + gizli);
    }
    assert.ok(!/424242/.test(html + js));
    assert.equal(SAYFA_HTML, html);
    assert.equal((await istek("/panel/yok")).r.status, 404);
    assert.equal((await istek("/panel", { method: "POST" })).r.status, 405);
  });
});

// ------------------------------------------------------------------ okuma API
describe("okuma API", () => {
  beforeEach(() => cacheKur());

  test("durum: tüm dosyalar tek yanıtta, ham içerik + PAT ile", async () => {
    const c = await oturum();
    const { r, cagrilar } = await istek("/panel/api/durum", { cerez: c });
    assert.equal(r.status, 200);
    assert.equal(r.headers.get("cache-control"), "no-store");
    const d = await r.json();
    assert.equal(d.videos.length, 10);
    assert.equal(d.stats.time, "2026-11-05T00:39+03:00");
    assert.equal(d.oneriler.items.length, 3);
    assert.equal(d.konu_sirasi.length, 3);
    assert.ok(d.stats_gecmis.length >= 10 && d.stats_gecmis[0].hesap.youtube);
    assert.ok(d.stats_gecmis.every((x) => Object.keys(x).join() === "time,hesap"), "video başına değerler tarayıcıya gitmez");
    assert.deepEqual(d.saatler.en_iyi.youtube, ["18:00", "21:00"]);
    assert.deepEqual(d.uyarilar, []);
    assert.equal(cagrilar.length, 5);
    for (const x of cagrilar) {
      assert.match(x.url, /\/contents\/state\/[\w.]+\?ref=main$/);
      assert.equal(x.basliklar.accept, "application/vnd.github.raw");
      assert.equal(x.basliklar.authorization, `Bearer ${ORTAM.GH_PAT}`);
    }
    assert.ok(!JSON.stringify(d).includes(ORTAM.GH_PAT));
  });

  test("durum ~20 sn önbellekte; oturuma özel", async () => {
    saatIlerlet(21000); // önceki testin izolat içi önbelleği geçsin
    const c1 = await oturum(), c2 = await oturum(29 * 86400);
    assert.equal((await istek("/panel/api/durum", { cerez: c1 })).cagrilar.length, 5);
    assert.equal((await istek("/panel/api/durum", { cerez: c1 })).cagrilar.length, 0);
    assert.equal((await istek("/panel/api/durum", { cerez: c2 })).cagrilar.length, 5, "başka oturum önbelleği paylaşmaz");
    saatIlerlet(21000);
    assert.equal((await istek("/panel/api/durum", { cerez: c1 })).cagrilar.length, 5, "20 sn sonra tazelenir");
  });

  test("durum: eksik yeni dosyalar boş döner, okuma hatası uyarı olur, videos.json yetki hatası anlaşılır mesaj", async () => {
    saatIlerlet(30000);
    const c = await oturum(20 * 86400);
    const kok = join(BURASI, "..", "..", "state"); // depodaki state/: konu_sirasi ve stats_gecmis olmayabilir
    let { r } = await istek("/panel/api/durum", { cerez: c, fetchAyar: { dosyaHata: { "konu_sirasi.json": 404, "stats_gecmis.jsonl": 404 } } });
    let d = await r.json();
    assert.deepEqual(d.konu_sirasi, []);
    assert.deepEqual(d.stats_gecmis, []);
    assert.deepEqual(d.uyarilar, []);
    saatIlerlet(30000);
    ({ r } = await istek("/panel/api/durum", { cerez: c, fetchAyar: { kok, dosyaHata: { "stats.json": 500 } } }));
    d = await r.json();
    assert.equal(d.stats, null);
    assert.equal(d.uyarilar.length, 1);
    saatIlerlet(30000);
    ({ r } = await istek("/panel/api/durum", { cerez: c, fetchAyar: { dosyaHata: { "videos.json": 403 } } }));
    assert.equal(r.status, 502);
    assert.match((await r.json()).hata, /Contents: Read-only/);
  });

  test("video: imzalı adrese 302, etiket denetimi", async () => {
    const c = await oturum();
    const { r, cagrilar } = await istek("/panel/api/video/short-20261104-1019", { cerez: c });
    assert.equal(r.status, 302);
    assert.equal(r.headers.get("location"), "https://release-assets.githubusercontent.com/signed/video.mp4?sig=abc&exp=300");
    assert.equal(r.headers.get("cache-control"), "no-store");
    const asset = cagrilar.find((x) => x.url.endsWith("/releases/assets/11"));
    assert.equal(asset.basliklar.accept, "application/octet-stream");
    assert.equal(asset.redirect, "manual");
    for (const kotu of ["short-abc", "..%2F..%2Fsecrets", "short-1%0A", "baska-20261104", "short-2026%2F11"]) {
      const x = await istek("/panel/api/video/" + kotu, { cerez: c });
      assert.equal(x.r.status, 400, kotu);
      assert.equal(x.cagrilar.length, 0);
    }
    assert.equal((await istek("/panel/api/video/short-20990101-0000", { cerez: c })).r.status, 404);
  });

  test("meta: düzenleme formu için başlık, bilgi metni ve korunan satırlar", async () => {
    const c = await oturum();
    const { r, cagrilar } = await istek("/panel/api/meta/short-20261104-1019", { cerez: c });
    assert.equal(r.status, 200);
    const m = await r.json();
    assert.equal(m.title, META.title);
    assert.equal(m.description, META.description);
    assert.equal(m.bilgi, "1919'da Boston'da patlayan bir tank, 8 metrelik melas dalgasıyla bir mahalleyi yuttu.");
    assert.deepEqual(m.ekler, ["#tarih #boston #ilginçbilgiler", "📷 John Doe (CC BY-SA 4.0)"]);
    assert.deepEqual(m.hashtags, META.hashtags);
    const imzali = cagrilar.find((x) => x.url.startsWith("https://release-assets.githubusercontent.com/"));
    assert.equal(imzali.basliklar.authorization, undefined, "imzalı adrese PAT gönderilmez");
  });
});

// ------------------------------------------------------------------ işlemler
describe("işlemler (isle.yml'e panel olayı)", () => {
  const T = "short-20261104-1019"; // onay_bekliyor, telegram_message_id 2
  const Z = "short-20261104-2023"; // zamanlandi, telegram_message_id 44
  const Y = "short-20261104-1307"; // yayinlandi

  async function gonder(govde, ek) {
    saatIlerlet(16000); // tekrar engelini geç
    const c = await oturum();
    const x = await istek("/panel/api/islem", { ...POST(govde, c), ...(ek || {}) });
    return { ...x, j: await x.r.json() };
  }

  const IYI = [
    [{ action: "approve", tag: T, code: "best" }, { action: "approve", tag: T, code: "best" }],
    [{ action: "approve", tag: T, code: "now" }, { action: "approve", tag: T, code: "now" }],
    [{ action: "approve", tag: T, code: "b12" }, { action: "approve", tag: T, code: "b12" }],
    [{ action: "approve", tag: T, code: "y19" }, { action: "approve", tag: T, code: "y19" }],
    [{ action: "reject", tag: T }, { action: "reject", tag: T }],
    [{ action: "cancel", tag: Z }, { action: "cancel", tag: Z }],
    [{ action: "edit", tag: T, title: "  Yeni   başlık  ", description: "Satır 1  \r\nSatır 2\n\n#etiket" },
      { action: "edit", tag: T, title: "Yeni başlık", description: "Satır 1\nSatır 2\n\n#etiket" }],
    [{ action: "edit", tag: Z, title: "Ç".repeat(100), description: "ğ".repeat(2000) },
      { action: "edit", tag: Z, title: "Ç".repeat(100), description: "ğ".repeat(2000) }],
    [{ action: "produce_suggestion", index: 1, topic: undefined }, { action: "produce_suggestion", index: 1,
      topic: "'Kasım' adının hikâyesi: Ayın adı 1945'e kadar Teşrinisani'ydi; yeni adı, halk takviminde yılı Hızır (6 Mayıs) ve Kasım (8 Kasım) diye ikiye bölen ve kışın başladığı kabul edilen 'Kasım günü'nden geliyor" }],
    [{ action: "produce_topic", topic: "  kara   delikler " }, { action: "produce_topic", topic: "kara delikler" }],
    [{ action: "produce_topic" }, { action: "produce_topic", topic: "" }],
    [{ action: "refresh_suggestions" }, { action: "refresh_suggestions" }],
    [{ action: "report" }, { action: "report" }],
    [{ action: "queue_set", queue: [" a  b ", "c", "c", ""] }, { action: "queue_set", queue: ["a b", "c"] }],
    [{ action: "queue_set", queue: [] }, { action: "queue_set", queue: [] }],
  ];
  for (const [govde, beklenen] of IYI) {
    test(`${govde.action} ${govde.code || govde.tag || ""} -> isle.yml olayı`, async () => {
      const { r, j, cagrilar } = await gonder(govde);
      assert.equal(r.status, 202, JSON.stringify(j));
      assert.equal(j.mesaj, "⏳ İşleniyor (30-60 sn)…");
      const d = dispatchlar(cagrilar);
      assert.equal(d.length, 1);
      assert.equal(d[0].govde.ref, "main");
      assert.equal(d[0].basliklar.authorization, `Bearer ${ORTAM.GH_PAT}`);
      const p = panelOlayi(cagrilar);
      assert.match(p.rid, /^[0-9a-f-]{36}$/);
      assert.ok(p.at);
      delete p.rid; delete p.at;
      assert.deepEqual(p, JSON.parse(JSON.stringify(beklenen)));
      // durum değiştiren video işlemlerinde Telegram'daki düğme de kilitlenir (kapının düğme basışındaki gibi)
      const tgCagri = cagrilar.filter((x) => x.url.includes("api.telegram.org"));
      if (["approve", "reject", "cancel", "retry"].includes(govde.action)) {
        assert.equal(tgCagri.length, 1);
        assert.match(tgCagri[0].url, /editMessageReplyMarkup$/);
        assert.deepEqual(tgCagri[0].govde.reply_markup, { inline_keyboard: [[{ text: "⏳ İşleniyor…", callback_data: "noop:x" }]] });
        assert.equal(tgCagri[0].govde.chat_id, ORTAM.CHAT_ID);
        assert.ok(cagrilar.indexOf(tgCagri[0]) < cagrilar.indexOf(d[0]), "kilit dispatch'ten önce");
      } else {
        assert.equal(tgCagri.length, 0);
      }
    });
  }

  test("retry yalnız sorunlu videoda (fikstüre hata kaydı eklenerek)", async () => {
    // sorunlu video yok: 409 döner
    const { r, j, cagrilar } = await gonder({ action: "retry", tag: Y });
    assert.equal(r.status, 409, j.hata);
    assert.equal(dispatchlar(cagrilar).length, 0);
  });

  const KOTU = [
    [{ action: "sil_hepsini" }, 400, /Bilinmeyen/],
    [[], 400, /Geçersiz/],
    [{ action: "approve", tag: "../x", code: "best" }, 400, /etiket/],
    [{ action: "approve", tag: T }, 400, /saat/],
    [{ action: "approve", tag: T, code: "y99" }, 400, /saat/],
    [{ action: "approve", tag: "short-20990101-0000", code: "best" }, 404, /bulunamadı/],
    [{ action: "approve", tag: Z, code: "best" }, 409, /durumu değişmiş/],
    [{ action: "reject", tag: Y }, 409, /durumu değişmiş/],
    [{ action: "cancel", tag: T }, 409, /durumu değişmiş/],
    [{ action: "edit", tag: Y, title: "a", description: "b" }, 409, /durumu değişmiş/],
    [{ action: "edit", tag: T, title: "", description: "b" }, 400, /Başlık boş/],
    [{ action: "edit", tag: T, title: "a".repeat(101), description: "b" }, 400, /Başlık en fazla 100/],
    [{ action: "edit", tag: T, title: "a", description: "b".repeat(2001) }, 400, /Açıklama en fazla 2000/],
    [{ action: "edit", tag: T, title: "a\u0000", description: "b" }, 400, /geçersiz karakter/],
    [{ action: "edit", tag: T, title: "a" }, 400, /Açıklama eksik/],
    [{ action: "produce_suggestion", index: 7 }, 409, /değişmiş/],
    [{ action: "produce_suggestion", index: 0, topic: "eski konu" }, 409, /değişmiş/],
    [{ action: "produce_suggestion", index: "0" }, 400, /öneri/],
    [{ action: "produce_topic", topic: "x".repeat(301) }, 400, /300/],
    [{ action: "queue_set", queue: "a" }, 400, /sırası/],
    [{ action: "queue_set", queue: Array.from({ length: 31 }, (_, i) => "konu " + i) }, 400, /30/],
    [{ action: "queue_set", queue: ["y".repeat(301)] }, 400, /300/],
    [{ action: "queue_set", queue: [5] }, 400, /eksik/],
  ];
  for (const [govde, kod, mesaj] of KOTU) {
    test(`doğrulama: ${JSON.stringify(govde).slice(0, 70)} -> ${kod}`, async () => {
      const { r, j, cagrilar } = await gonder(govde);
      assert.equal(r.status, kod, JSON.stringify(j));
      assert.match(j.hata, mesaj);
      assert.equal(dispatchlar(cagrilar).length, 0);
      assert.equal(cagrilar.filter((x) => x.url.includes("telegram")).length, 0);
    });
  }

  test("geçmiş saat seçilemez (Bugün 12:00, saat 13:00'te)", async () => {
    saatKur(Date.parse("2026-11-05T13:00:00+03:00")); // saat yalnız ileri gider (tekrar engeli saate bakar)
    const { r, j } = await gonder({ action: "approve", tag: T, code: "b12" });
    assert.equal(r.status, 409);
    assert.match(j.hata, /geçti/);
    assert.equal((await gonder({ action: "approve", tag: T, code: "b19" })).r.status, 202);
  });

  test("çift dokunma: aynı işlem 15 sn içinde ikinci kez iletilmez", async () => {
    const c = await oturum();
    saatIlerlet(20000);
    const a = await istek("/panel/api/islem", POST({ action: "reject", tag: T }, c));
    const b = await istek("/panel/api/islem", POST({ action: "reject", tag: T }, c));
    assert.equal(a.r.status, 202);
    assert.equal(b.r.status, 409);
    assert.match((await b.r.json()).hata, /az önce/);
    assert.equal(dispatchlar(b.cagrilar).length, 0);
  });

  test("GitHub dispatch'i reddederse 502 ve Telegram düğmesi geri konur", async () => {
    const { r, j, cagrilar } = await gonder({ action: "approve", tag: T, code: "best" }, { fetchAyar: { dispatchDurum: 403 } });
    assert.equal(r.status, 502);
    assert.match(j.hata, /iletilemedi \(403\)/);
    const tg = cagrilar.filter((x) => x.url.includes("telegram"));
    assert.equal(tg.length, 2);
    assert.deepEqual(tg[1].govde.reply_markup, { inline_keyboard: [[{ text: "✅ Onayla", callback_data: `ok:${T}` },
      { text: "❌ Reddet", callback_data: `no:${T}` }]] });
    // başarısız işlem tekrar engeline takılmaz
    assert.equal((await gonder({ action: "approve", tag: T, code: "best" })).r.status, 202);
  });
});

test("webhook senaryo listesi boş değil", () => assert.ok(SENARYOLAR.length > 20));
