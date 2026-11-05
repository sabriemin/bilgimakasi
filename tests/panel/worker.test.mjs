// Kapı ve panel testleri (gerçek ağ yok): /opt/node22/bin/node --test tests/panel/worker.test.mjs
import { test, describe, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import worker, { hedefAdi } from "../../cloudflare/worker.js";
import { SAYFA_HTML, UYGULAMA_JS, ONERI_SERILERI, SERI_NOTU } from "../../cloudflare/panel_ui.js";
import { calistir, SENARYOLAR, SABIT_SAAT } from "./webhook_senaryolar.mjs";
import { ORTAM, BURASI, META, FIKSTUR, fetchKur, ctxYap, saatKur, saatIlerlet, saatBirak, cacheKur, imza, oturumImza,
  girisImza, girisMesajiKur, TG_MESAJLAR, ALTI_SERI, YEDI_SERI } from "./sahte.mjs";
import { mkdtempSync, cpSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { createRequire } from "node:module";
import { gizle } from "../../cloudflare/panel.js";

const HOST = "https://bilgimakasi-kapi.bilgimakasi.workers.dev";
const SN = () => Math.floor(Date.now() / 1000);
let sessiz = console.log;

async function istek(yol, { method = "GET", cerez, basliklar = {}, govde, env = ORTAM, fetchAyar, cf } = {}) {
  const f = fetchKur(fetchAyar);
  const { ctx, bitir } = ctxYap();
  const h = { ...basliklar };
  if (cerez) h.cookie = `bm_oturum=${cerez}`;
  const req = new Request(HOST + yol, { method, headers: h,
    body: govde === undefined ? undefined : typeof govde === "string" ? govde : JSON.stringify(govde) });
  if (cf) Object.defineProperty(req, "cf", { value: cf });
  const r = await worker.fetch(req, { ...env }, ctx);
  await bitir();
  return { r, cagrilar: f.cagrilar };
}
const oturum = async (sure = 30 * 86400) => oturumImza(SN() + sure);
const giris = async (sure = 300) => girisImza(SN() + sure, girisMesajiKur()); // geçerli, kullanılmamış bağlantı
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
        // bilinçli farklar: yardım metnine /panel satırı eklendi, /oneri yedi seriden 21 öneri veriyor
        const eski = g.cagrilar[0].govde.text, yeniMetin = y.cagrilar[0].govde.text;
        assert.equal(yeniMetin, eski.replace("/yardim: bu liste", "/panel: yönetim paneline giriş bağlantısı\n/yardim: bu liste")
          .replace("/oneri: gündemden 5 konu önerisi", "/oneri: 7 seriden 21 konu önerisi"));
        assert.deepEqual({ ...y, cagrilar: [] }, { ...g, cagrilar: [] });
        continue;
      }
      if (g.ad === "düğme ok (saat seçenekleri)") {
        // bilinçli fark: saat seçeneklerine "↩️ Geri"nin üstünde panel takvimine giden bağlantı düğmesi eklendi;
        // saat düğmeleri (callback_data) ve diğer çağrılar aynı
        const beklenen = structuredClone(g);
        beklenen.cagrilar[0].govde.reply_markup.inline_keyboard.splice(-1, 0, [{ text: "🗓 Takvimde seç",
          url: "https://bilgimakasi-kapi.bilgimakasi.workers.dev/panel#takvim/short-20261104-1019" }]);
        assert.deepEqual(y, beklenen, g.ad);
        continue;
      }
      assert.deepEqual(y, g, g.ad);
    }
  });

  test("/panel komutu: kapı tek kullanımlık giriş bağlantısını kendisi yollar, GitHub'a gitmez", async () => {
    for (const metin of ["/panel", "/panel@BilgiMakasiBot", "  /panel  "]) {
      const { r, cagrilar } = await istek("/", { method: "POST", basliklar: { "X-Telegram-Bot-Api-Secret-Token": ORTAM.WEBHOOK_SECRET },
        govde: { message: { message_id: 5, chat: { id: 424242 }, text: metin } } });
      assert.equal(r.status, 200);
      assert.equal(cagrilar.length, 2, metin);
      // önce yer tutucu mesaj (numarası bağlantının imzasına girer), sonra o mesaj bağlantıya çevrilir
      assert.match(cagrilar[0].url, /\/sendMessage$/);
      assert.equal(cagrilar[0].govde.chat_id, 424242);
      assert.match(cagrilar[1].url, /\/editMessageText$/);
      const g = cagrilar[1].govde;
      assert.equal(g.chat_id, 424242);
      assert.equal(g.disable_web_page_preview, true);
      const m = /https:\/\/bilgimakasi-kapi\.bilgimakasi\.workers\.dev\/panel\/giris\?t=(\d+)\.(\d+)\.([\w-]{43})/.exec(g.text);
      assert.ok(m, g.text);
      assert.equal(Number(m[1]), SN() + 600);
      assert.equal(Number(m[2]), g.message_id, "bağlantı kendi mesajının numarasını taşır");
      assert.match(g.text, /tek kullanımlık/);
      assert.match(g.text, /Telegram kapısını kur/);
      assert.equal(g.reply_markup.inline_keyboard[0][0].url, m[0]);
      assert.ok(!g.text.includes(ORTAM.PANEL_SECRET));
      // bağlantı gerçekten çalışır (bir kez)
      const t = m[0].split("t=")[1];
      assert.equal((await istek("/panel/giris?t=" + t)).r.status, 302);
      assert.equal((await istek("/panel/giris?t=" + t)).r.status, 403);
    }
  });

  test("Onayla: saat seçeneklerinde kapının kendi adresiyle panel takvimine bağlantı satırı", async () => {
    const tag = "short-20261104-1057";
    const { cagrilar } = await istek("/", { method: "POST", basliklar: { "X-Telegram-Bot-Api-Secret-Token": ORTAM.WEBHOOK_SECRET },
      govde: { callback_query: { id: "c", from: { id: 424242 }, data: `ok:${tag}`, message: { message_id: 4, chat: { id: 424242 } } } } });
    const satirlar = cagrilar[0].govde.reply_markup.inline_keyboard;
    assert.deepEqual(satirlar[satirlar.length - 2], [{ text: "🗓 Takvimde seç", url: `${HOST}/panel#takvim/${tag}` }]);
    assert.deepEqual(satirlar[satirlar.length - 1], [{ text: "↩️ Geri", callback_data: `back:${tag}` }]);
    // URL düğmesi dışındaki bütün düğmeler callback düğmesi (saat seçimi aynı kaldı)
    assert.ok(satirlar.flat().every((d) => d.url ? d.text === "🗓 Takvimde seç" : /^(at|back):/.test(d.callback_data)));
    assert.equal(cagrilar.filter((c) => c.url.includes("api.github.com")).length, 0, "arayüz adımı GitHub'a gitmez");
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
  test("geçerli bağlantı: 30 günlük güvenli çerez + /panel'e yönlendirme, mesaj 'kullanıldı', giriş bildirimi", async () => {
    const t = await giris();
    const mid = Number(t.split(".")[1]);
    const ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36";
    const { r, cagrilar } = await istek("/panel/giris?t=" + t, { basliklar: { "user-agent": ua }, cf: { country: "TR" } });
    assert.equal(r.status, 302);
    const tg = cagrilar.filter((x) => x.url.includes("api.telegram.org"));
    assert.deepEqual(tg.map((x) => x.url.split("/").pop()), ["editMessageText", "sendMessage"]);
    assert.deepEqual(tg[0].govde, { chat_id: ORTAM.CHAT_ID, message_id: mid,
      text: "✅ Bu giriş bağlantısı kullanıldı. Yeni bağlantı için /panel yaz." });
    assert.equal(tg[1].govde.chat_id, ORTAM.CHAT_ID);
    assert.match(tg[1].govde.text, /^🖥 Panele giriş yapıldı · TR · Chrome \/ Android · 00:45\n/);
    assert.match(tg[1].govde.text, /Telegram kapısını kur/);
    assert.equal(r.headers.get("location"), "/panel");
    const c = r.headers.get("set-cookie");
    assert.match(c, /^bm_oturum=\d+\.[\w-]{43}; /);
    for (const k of ["HttpOnly", "Secure", "SameSite=Strict", "Path=/panel", "Max-Age=2592000"]) assert.ok(c.includes(k), k);
    const deger = /^bm_oturum=([^;]+)/.exec(c)[1];
    assert.equal(Number(deger.split(".")[0]), SN() + 30 * 86400);
    assert.equal(deger, await oturumImza(SN() + 30 * 86400));
    assert.equal((await istek("/panel/api/durum", { cerez: deger })).r.status, 200);
  });

  test("bağlantı tek kullanımlık: ikinci açılış 403 ve çerez yok", async () => {
    const t = await giris(600);
    assert.equal((await istek("/panel/giris?t=" + t)).r.status, 302);
    saatIlerlet(9 * 60 * 1000); // süresi dolmadan, 9 dk sonra yeniden
    const { r, cagrilar } = await istek("/panel/giris?t=" + t);
    assert.equal(r.status, 403);
    assert.equal(r.headers.get("set-cookie"), null);
    assert.match(await r.text(), /Bağlantı kullanıldı/);
    assert.equal(cagrilar.filter((x) => x.url.endsWith("/sendMessage")).length, 0, "kullanılmış bağlantıda giriş bildirimi yok");
  });

  test("bağlantı mesajı silinmişse 403; Telegram'a ulaşılamazsa 503 ve bağlantı harcanmaz", async () => {
    const yok = await girisImza(SN() + 300, 987654321);
    assert.equal((await istek("/panel/giris?t=" + yok)).r.status, 403);
    const t = await giris();
    for (const fetchAyar of [{ tgAgHatasi: ["editMessageText"] }, { tgDurum: { editMessageText: 502 } }]) {
      const { r } = await istek("/panel/giris?t=" + t, { fetchAyar });
      assert.equal(r.status, 503);
      assert.equal(r.headers.get("set-cookie"), null);
      assert.match(await r.text(), /Telegram'a ulaşılamadı/);
    }
    assert.equal((await istek("/panel/giris?t=" + t)).r.status, 302, "Telegram dönünce aynı bağlantı bir kez çalışır");
  });

  test("bağlantı başka bir mesajın numarasıyla kullanılamaz (numara imzanın içinde)", async () => {
    const [exp, mid, sig] = (await giris()).split(".");
    const baska = girisMesajiKur();
    assert.equal((await istek(`/panel/giris?t=${exp}.${baska}.${sig}`)).r.status, 403);
    assert.equal((await istek(`/panel/giris?t=${exp}.${mid}.${sig}`)).r.status, 302);
  });

  test("süresi dolmuş, bozuk, çok uzun ömürlü ve yanlış anahtarlı bağlantılar reddedilir", async () => {
    const mid = girisMesajiKur();
    const gecerli = await girisImza(SN() + 300, mid);
    const [exp, , sig] = gecerli.split(".");
    const kotu = [
      await girisImza(SN() - 1, mid), // süresi dolmuş
      `${exp}.${mid}.${sig.slice(0, -1)}${sig.endsWith("A") ? "B" : "A"}`, // imza değişti
      `${Number(exp) + 1}.${mid}.${sig}`, // süre değişti
      await girisImza(SN() + 3600, mid), // 10 dk'dan uzun
      await girisImza(SN() + 300, mid, "baska-anahtar"),
      await oturumImza(SN() + 300), // oturum imzası giriş bağlantısı olarak kullanılamaz
      await imza("giris", SN() + 300), // eski biçim (mesaj numarasız)
      "", "abc", `${exp}.${mid}.${sig}x`, `${exp}..${sig}`, `${exp}.${mid}..${sig}`,
    ];
    for (const t of kotu) {
      const { r, cagrilar } = await istek("/panel/giris?t=" + encodeURIComponent(t));
      assert.equal(r.status, 403, t);
      assert.equal(cagrilar.length, 0, "imzası geçersiz bağlantıda Telegram'a gidilmez");
      assert.equal(r.headers.get("set-cookie"), null);
      const html = await r.text();
      assert.match(html, /\/panel/);
      assert.match(html, /süresi dolmuş/);
    }
  });

  test("bağlantı 10 dakika sonra geçersiz olur", async () => {
    const t = await giris(600);
    saatIlerlet(601 * 1000);
    assert.equal((await istek("/panel/giris?t=" + t)).r.status, 403);
  });

  test("giriş bağlantısı HEAD ile yoklanınca harcanmaz", async () => {
    const t = await giris();
    const h = await istek("/panel/giris?t=" + t, { method: "HEAD" });
    assert.equal(h.r.status, 200);
    assert.equal(h.cagrilar.length, 0, "HEAD Telegram'a gitmez");
    assert.equal(h.r.headers.get("set-cookie"), null);
    assert.equal((await istek("/panel/giris?t=" + t)).r.status, 302, "ardından gelen GET yine giriş yapar");
  });

  test("API çerezsiz, bozuk, süresi dolmuş veya giriş imzalı çerezle 401", async () => {
    const iyi = await oturum();
    const kotu = [null, "x", iyi.slice(0, -2) + "zz", await oturumImza(SN() - 5), await imza("giris", SN() + 300),
      await oturumImza(SN() + 400 * 86400), await imza("oturum", SN() + 300) /* dönemsiz eski biçim */,
      await oturumImza(SN() + 300, 1) /* başka dönem */];
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

  test("PANEL_EPOCH değişince eski oturumlar kapanır", async () => {
    const c = await oturum(25 * 86400); // başka testlerin önbelleğiyle karışmasın diye ayrı oturum
    assert.equal((await istek("/panel/api/durum", { cerez: c })).r.status, 200);
    const env = { ...ORTAM, PANEL_EPOCH: "2" };
    assert.equal((await istek("/panel/api/durum", { cerez: c, env })).r.status, 401);
    assert.equal((await istek("/panel/api/durum", { cerez: await oturumImza(SN() + 3600, 2), env })).r.status, 200);
    saatIlerlet(21000); // izolat içi durum önbelleği sonraki testlere taşınmasın
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

  test("durum: hata/not alanlarındaki anahtarlar maskelenir, başlık ve konu olduğu gibi kalır", async () => {
    saatIlerlet(30000);
    const kok = mkdtempSync(join(tmpdir(), "panel-gizle-"));
    cpSync(FIKSTUR, kok, { recursive: true });
    const vs = JSON.parse(readFileSync(join(FIKSTUR, "videos.json"), "utf8"));
    vs[0].title = "Şifre code=gizlidegil ve OAuth yetkilendirmesi";
    vs[0].platforms = { instagram: { status: "hata",
      error: "HTTPSConnectionPool: /v21.0/me?access_token=EAAGm0PX4ZCpsBAKexampleexample123 gizli-deger-12345" },
    tiktok: { status: "ok", note: "Bearer abcdefgh12345678 ile" } };
    writeFileSync(join(kok, "videos.json"), JSON.stringify(vs));
    const { r } = await istek("/panel/api/durum", { cerez: await oturum(19 * 86400), fetchAyar: { kok },
      env: { ...ORTAM, GH_PAT: "gizli-deger-12345" } });
    const d = await r.json();
    const v = d.videos.find((x) => x.tag === vs[0].tag);
    assert.equal(v.title, vs[0].title, "sıradan metin maskelenmez");
    assert.equal(v.platforms.instagram.error, "HTTPSConnectionPool: /v21.0/me?access_token=*** ***");
    assert.equal(v.platforms.tiktok.note, "Bearer *** ile");
    assert.ok(!JSON.stringify(d).includes("EAAGm0PX4ZCps"));
    saatIlerlet(30000);
  });

  test("durum: eski bitmiş videolar gönderilmez, işi süren her video gönderilir", async () => {
    saatIlerlet(30000);
    const kok = mkdtempSync(join(tmpdir(), "panel-eski-"));
    cpSync(FIKSTUR, kok, { recursive: true });
    const vs = JSON.parse(readFileSync(join(FIKSTUR, "videos.json"), "utf8"));
    const eski = new Date(Date.now() - 200 * 86400e3).toISOString();
    vs.unshift({ ...vs[0], tag: "short-20260401-0900", status: "yayinlandi", created: eski, published: eski },
      { ...vs[0], tag: "short-20260402-0900", status: "kismen", created: eski });
    writeFileSync(join(kok, "videos.json"), JSON.stringify(vs));
    const { r } = await istek("/panel/api/durum", { cerez: await oturum(18 * 86400), fetchAyar: { kok } });
    const d = await r.json();
    assert.equal(d.videos_toplam, vs.length);
    assert.ok(!d.videos.some((v) => v.tag === "short-20260401-0900"), "200 günlük paylaşılmış video gitmez");
    assert.ok(d.videos.some((v) => v.tag === "short-20260402-0900"), "sorunlu video eski de olsa gider");
    assert.equal(d.videos.length, vs.length - 1);
    saatIlerlet(30000);
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
    assert.deepEqual(d.uyarilar, ["İstatistikler okunamadı (500); İstatistik sekmesi eksik olabilir."]);
    saatIlerlet(30000);
    ({ r } = await istek("/panel/api/durum", { cerez: c, fetchAyar: { dosyaHata: { "stats_gecmis.jsonl": 500 } } }));
    assert.deepEqual((await r.json()).uyarilar, ["İstatistik geçmişi okunamadı (500); grafikler eksik olabilir."]);
    saatIlerlet(30000);
    ({ r } = await istek("/panel/api/durum", { cerez: c, fetchAyar: { dosyaHata: { "videos.json": 403 } } }));
    assert.equal(r.status, 502);
    assert.match((await r.json()).hata, /Contents: Read-only/);
  });

  test("durum: hata metinlerindeki anahtarlar tarayıcıya gitmez (ad çözme hatası adresi gibi)", async () => {
    saatIlerlet(30000);
    const kok = mkdtempSync(join(tmpdir(), "panel_gizli_"));
    cpSync(FIKSTUR, kok, { recursive: true });
    const IG = "IGAAJx8TEStoken0123456789abcdefABCDEF_uzun-anahtar";
    const vs = JSON.parse(readFileSync(join(kok, "videos.json"), "utf8"));
    vs[0].status = "kismen";
    vs[0].platforms = {
      instagram: { status: "hata", error: "HTTPSConnectionPool(host='graph.instagram.com', port=443): Max retries exceeded " +
        `with url: /v26.0/18012345678901234?fields=status_code%2Cstatus&access_token=${IG} (Caused by ` +
        "NameResolutionError(\"<urllib3.connection.HTTPSConnection object>: Failed to resolve 'graph.instagram.com'\"))" },
      youtube: { status: "hata", error: `Telegram: Max retries exceeded with url: /bot${ORTAM.TELEGRAM_BOT_TOKEN}/sendMessage; ` +
        "yt ya29.a0AfB_byC1234567890abcdefghijklmnop; tt {'access_token': 'act.1234567890abcdefXYZ', 'scope': 'x'}" },
    };
    writeFileSync(join(kok, "videos.json"), JSON.stringify(vs));
    const st = JSON.parse(readFileSync(join(kok, "stats.json"), "utf8"));
    st.platforms.instagram = { error: `okunamadı (Max retries exceeded with url: /v26.0/me?fields=followers_count&access_token=${IG.slice(0, 40)})` };
    writeFileSync(join(kok, "stats.json"), JSON.stringify(st));
    const { r } = await istek("/panel/api/durum", { cerez: await oturum(19 * 86400), fetchAyar: { kok } });
    const metin = await r.text();
    for (const gizli of [IG, IG.slice(0, 24), ORTAM.TELEGRAM_BOT_TOKEN, "123456:", "ya29.a0AfB", "act.1234567890"]) {
      assert.ok(!metin.includes(gizli), "durum yanıtında gizli değer: " + gizli);
    }
    const d = JSON.parse(metin);
    const hata = d.videos[0].platforms.instagram.error;
    assert.match(hata, /access_token=\*\*\* \(Caused by NameResolutionError/);
    assert.ok(!hata.slice(0, 220).includes("IGAA"), "arayüzün gösterdiği ilk 220 karakterde anahtar yok");
    assert.match(d.videos[0].platforms.youtube.error, /\/bot\*\*\*\/sendMessage/);
    assert.match(d.stats.platforms.instagram.error, /access_token=\*\*\*\)/);
  });

  test("gizle(): kalıplar ve ortamdaki gizli değerler", () => {
    assert.equal(gizle("a?access_token=XYZ&b=1 key=abc code=9 client_secret=s"), "a?access_token=***&b=1 key=*** code=*** client_secret=***");
    assert.equal(gizle("https://api.telegram.org/bot123456789:AAHk-abcdefghijklmnopqrstuvwxyz012/getMe"), "https://api.telegram.org/bot***/getMe");
    assert.equal(gizle("token EAAGm0PX4ZCpsBAKexampleexample github_pat_11ABCDEFG0123456789_abcdefghij"), "token *** ***");
    assert.equal(gizle('{"access_token": "act.abc123def456"} Authorization: Bearer abcdefgh12345678'), '{"access_token": "***"} Authorization: Bearer ***');
    assert.equal(gizle("x gizli-deger-12345 y", { GH_PAT: "gizli-deger-12345" }), "x *** y");
    assert.equal(gizle("Media upload has failed with error code 2207026"), "Media upload has failed with error code 2207026");
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
    for (const kotu of ["short-abc", "..%2F..%2Fsecrets", "short-1%0A", "baska-20261104", "short-2026%2F11",
      "short-" + "1".repeat(5000), "short-20261104-1019-1-2", "short-2026110-1019", "short-20261104-123"]) {
      const x = await istek("/panel/api/video/" + kotu, { cerez: c });
      assert.equal(x.r.status, 400, kotu);
      assert.equal(x.cagrilar.length, 0);
    }
    assert.equal((await istek("/panel/api/video/short-20990101-0000", { cerez: c })).r.status, 404);
  });

  test("video/meta: release yanıtındaki yabancı dosya adresine PAT gönderilmez, yabancı yönlendirme izlenmez", async () => {
    const c = await oturum();
    const T = "short-20261104-1019";
    const degistir = (f) => (j) => ({ ...j, assets: j.assets.map((a) => (a.name === "video.mp4" || a.name === "metadata.json" ? f(a) : a)) });
    const kotuSurumler = [
      degistir((a) => ({ ...a, url: "https://attacker.example/steal" })),
      degistir((a) => ({ ...a, url: `https://api.github.com/repos/${ORTAM.REPO}/releases/assets/11/../../../../user` })),
      degistir((a) => ({ ...a, url: `https://api.github.com/repos/baska/depo/releases/assets/11` })),
      degistir((a) => ({ ...a, url: `https://api.github.com/repos/${ORTAM.REPO}/releases/assets/11?x=1` })),
      degistir((a) => ({ ...a, state: "starter" })),
    ];
    for (const surum of kotuSurumler) {
      for (const yol of ["video", "meta"]) {
        const { r, cagrilar } = await istek(`/panel/api/${yol}/${T}`, { cerez: c, fetchAyar: { surum } });
        assert.equal(r.status, 502, yol);
        assert.ok(!cagrilar.some((x) => !x.url.startsWith(`https://api.github.com/repos/${ORTAM.REPO}/releases/tags/`)),
          "yalnız release sorgusu yapılır: " + cagrilar.map((x) => x.url).join(" "));
      }
    }
    for (const konum of ["http://evil.example/x", "https://evil.example/x", "http://release-assets.githubusercontent.com/x",
      "https://release-assets.githubusercontent.com.evil.example/x", "https://user:pw@objects.githubusercontent.com/x",
      "https://objects.githubusercontent.com:8443/x", "javascript:alert(1)", "/goreli"]) {
      for (const yol of ["video", "meta"]) {
        const { r, cagrilar } = await istek(`/panel/api/${yol}/${T}`, { cerez: c, fetchAyar: { konum } });
        assert.equal(r.status, 502, `${yol} ${konum}`);
        assert.equal(r.headers.get("location"), null);
        assert.ok(!cagrilar.some((x) => x.url.includes("evil") || x.url.includes("goreli")), "yabancı adrese istek yok");
      }
    }
    for (const konum of ["https://objects.githubusercontent.com/github-production-release-asset/1?X-Amz=1",
      "https://github-releases.githubusercontent.com/1/2?sig=1"]) {
      const { r } = await istek(`/panel/api/video/${T}`, { cerez: c, fetchAyar: { konum } });
      assert.equal(r.status, 302);
      assert.equal(r.headers.get("location"), konum);
    }
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
    saatIlerlet(91000); // tekrar engelini ve aynı videonun işlem kilidini (90 sn) geç
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
    [{ action: "queue_set", queue: ["a", " b "], queue_base: ["b", "x  y"] },
      { action: "queue_set", queue: ["a", "b"], queue_base: ["b", "x y"] }],
    [{ action: "edit", tag: T, title: "B", description: "Bilgi.\n\n#yeni #etiket\n#iki" },
      { action: "edit", tag: T, title: "B", description: "Bilgi.\n\n#yeni #etiket\n#iki" }],
    // takvim: onay (üç platform) ve zamanlanmış videoda tek platform; saatler UTC'ye çevrilir, dakikaya yuvarlanır
    [{ action: "schedule", tag: T, schedule: { youtube: "2026-11-05T18:00:00+03:00", instagram: "2026-11-05T09:30:20Z",
      tiktok: "2026-11-06T19:29:40.000Z" } },
    { action: "schedule", tag: T, schedule: { youtube: "2026-11-05T15:00:00+00:00", instagram: "2026-11-05T09:30:00+00:00",
      tiktok: "2026-11-06T19:30:00+00:00" } }],
    [{ action: "schedule", tag: Z, schedule: { tiktok: "2026-11-06T17:00:00Z" } },
      { action: "schedule", tag: Z, schedule: { tiktok: "2026-11-06T17:00:00+00:00" } }],
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
      assert.equal(j.rid, p.rid, "yanıt isteğin numarasını verir (sayfa kaydı bununla izler)");
      assert.ok(p.at);
      delete p.rid; delete p.at;
      assert.deepEqual(p, JSON.parse(JSON.stringify(beklenen)));
      // durum değiştiren video işlemlerinde Telegram'daki düğme de kilitlenir (kapının düğme basışındaki gibi)
      const tgCagri = cagrilar.filter((x) => x.url.includes("api.telegram.org"));
      if (["approve", "reject", "cancel", "retry", "schedule"].includes(govde.action)) {
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

  test("seri öneriler: durum 'seri' alanını taşır, Üret yalnız sırayı ve konuyu gönderir", async () => {
    const kok = mkdtempSync(join(tmpdir(), "panel-seri-"));
    cpSync(FIKSTUR, kok, { recursive: true });
    const seriler = JSON.parse(readFileSync(join(BURASI, "fixtures", "oneriler_seriler.json"), "utf8")).items;
    writeFileSync(join(kok, "oneriler.json"), JSON.stringify({ date: "2026-11-05", items: seriler }));
    saatIlerlet(30000);
    const { r } = await istek("/panel/api/durum", { cerez: await oturum(17 * 86400), fetchAyar: { kok } });
    const d = await r.json();
    assert.deepEqual(d.oneriler.items.map((x) => x.seri), seriler.map((x) => x.seri));
    const it = seriler[11]; // Nasıl yapılır? serisinin son önerisi
    const { r: r2, j, cagrilar } = await gonder({ action: "produce_suggestion", index: 11, topic: it.topic }, { fetchAyar: { kok } });
    assert.equal(r2.status, 202, JSON.stringify(j));
    const p = panelOlayi(cagrilar);
    // kalıp kapıdan gelmez: Python tarafı kayıttaki seriden bulur (tarayıcı kalıp seçemez)
    assert.deepEqual(Object.keys(p).sort(), ["action", "at", "index", "rid", "topic"]);
    assert.deepEqual([p.action, p.index, p.topic], ["produce_suggestion", 11, it.topic]);
  });

  test("altı seri: uretim ve olsaydin önerileri de yalnız sıra ve konuyla üretilir; kalıp/seri gönderilemez", async () => {
    const kok = mkdtempSync(join(tmpdir(), "panel-alti-"));
    cpSync(FIKSTUR, kok, { recursive: true });
    writeFileSync(join(kok, "oneriler.json"), JSON.stringify(ALTI_SERI));
    saatIlerlet(30000);
    const { r } = await istek("/panel/api/durum", { cerez: await oturum(18 * 86400), fetchAyar: { kok } });
    const d = await r.json();
    assert.deepEqual(d.oneriler, ALTI_SERI, "öneriler (seri alanıyla) olduğu gibi gelir");
    const items = ALTI_SERI.items;
    assert.deepEqual([items[12].seri, items[14].seri, items[15].seri, items[17].seri], ["uretim", "uretim", "olsaydin", "olsaydin"]);
    for (const i of [12, 17]) {
      // tarayıcı kalıp ya da seri seçemez: fazladan alanlar dispatch'e geçmez, Python tarafı kayıttaki seriden bulur
      const { r: r2, j, cagrilar } = await gonder({ action: "produce_suggestion", index: i, topic: items[i].topic,
        kalip: "olsaydin", seri: "uretim", structure: "hikaye" }, { fetchAyar: { kok } });
      assert.equal(r2.status, 202, JSON.stringify(j));
      const p = panelOlayi(cagrilar);
      assert.deepEqual(Object.keys(p).sort(), ["action", "at", "index", "rid", "topic"], String(i));
      assert.deepEqual([p.action, p.index, p.topic], ["produce_suggestion", i, items[i].topic]);
    }
    // listede olmayan sıra (18 öneri: 0-17) ve sınır dışı/yanlış türde sıra reddedilir, hiçbir şey gönderilmez
    for (const [govde, durum, hata] of [[{ index: 18 }, 409, /değişmiş/], [{ index: 20 }, 409, /değişmiş/],
      [{ index: 40 }, 400, /öneri/],
      [{ index: -1 }, 400, /öneri/], [{ index: 12.5 }, 400, /öneri/], [{ index: "olsaydin" }, 400, /öneri/],
      [{ index: 15, topic: items[16].topic }, 409, /değişmiş/]]) {
      const { r: r3, j, cagrilar } = await gonder({ action: "produce_suggestion", ...govde }, { fetchAyar: { kok } });
      assert.equal(r3.status, durum, JSON.stringify(govde));
      assert.match(j.hata, hata);
      assert.equal(dispatchlar(cagrilar).length, 0);
    }
  });

  test("yedi seri: kitap önerileri de yalnız sıra ve konuyla üretilir; kalıp/seri gönderilemez", async () => {
    const kok = mkdtempSync(join(tmpdir(), "panel-yedi-"));
    cpSync(FIKSTUR, kok, { recursive: true });
    writeFileSync(join(kok, "oneriler.json"), JSON.stringify(YEDI_SERI));
    saatIlerlet(30000);
    const { r } = await istek("/panel/api/durum", { cerez: await oturum(20 * 86400), fetchAyar: { kok } });
    const d = await r.json();
    assert.deepEqual(d.oneriler, YEDI_SERI, "öneriler (seri alanıyla) olduğu gibi gelir");
    const items = YEDI_SERI.items;
    assert.deepEqual([18, 19, 20].map((i) => items[i].seri), ["kitap", "kitap", "kitap"]);
    for (const i of [18, 20]) {
      const { r: r2, j, cagrilar } = await gonder({ action: "produce_suggestion", index: i, topic: items[i].topic,
        kalip: "kitap", seri: "kitap", structure: "kitap", template: "kitap" }, { fetchAyar: { kok } });
      assert.equal(r2.status, 202, JSON.stringify(j));
      const p = panelOlayi(cagrilar);
      assert.deepEqual(Object.keys(p).sort(), ["action", "at", "index", "rid", "topic"], String(i));
      assert.deepEqual([p.action, p.index, p.topic], ["produce_suggestion", i, items[i].topic]);
    }
    // 21 öneri: 0-20 (20, eski 19 sınırına takılmaz); 21 listede yok, 40 sınır dışı,
    // başka önerinin konusuyla gelen sıra reddedilir
    for (const [govde, durum, hata] of [[{ index: 21 }, 409, /değişmiş/], [{ index: 39 }, 409, /değişmiş/],
      [{ index: 40 }, 400, /öneri/], [{ index: 18, topic: items[19].topic }, 409, /değişmiş/]]) {
      const { r: r3, j, cagrilar } = await gonder({ action: "produce_suggestion", ...govde }, { fetchAyar: { kok } });
      assert.equal(r3.status, durum, JSON.stringify(govde));
      assert.match(j.hata, hata);
      assert.equal(dispatchlar(cagrilar).length, 0);
    }
  });

  test("paylaşıma 10 dakikadan az kalan videoda düzenleme reddedilir", async () => {
    const kok = mkdtempSync(join(tmpdir(), "panel-yakin-"));
    cpSync(FIKSTUR, kok, { recursive: true });
    const vs = JSON.parse(readFileSync(join(FIKSTUR, "videos.json"), "utf8"));
    const z = vs.find((v) => v.tag === Z);
    saatIlerlet(91000);
    z.publish_at = new Date(Date.now() + 5 * 60e3).toISOString();
    writeFileSync(join(kok, "videos.json"), JSON.stringify(vs));
    const c = await oturum();
    const x = await istek("/panel/api/islem", { ...POST({ action: "edit", tag: Z, title: "a", description: "b" }, c),
      fetchAyar: { kok } });
    assert.equal(x.r.status, 409);
    assert.match((await x.r.json()).hata, /10 dakika/);
    assert.equal(dispatchlar(x.cagrilar).length, 0);
  });

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
    [{ action: "queue_set", queue: ["a"], queue_base: "a" }, 400, /tabanı eksik/],
    [{ action: "queue_set", queue: ["a"], queue_base: [3] }, 400, /eksik/],
    [{ action: "edit", tag: T, title: "a", description: "Bilgi.\n\nKaynaklar: Vikipedi" }, 400, /Görsel atfı ve kaynak satırları/],
    [{ action: "edit", tag: T, title: "a", description: "Bilgi.\n\n📷 Ben" }, 400, /Görsel atfı/],
    [{ action: "edit", tag: T, title: "a", description: "Bilgi.\n\n#etiket\n🎙 Seslendirme" }, 400, /Görsel atfı/],
    [{ action: "edit", tag: T, title: "a", description: "😀".repeat(1001) }, 400, /çok uzun/],
    [{ action: "schedule", tag: T, schedule: { youtube: "2026-11-06T15:00:00Z", instagram: "2026-11-06T17:00:00Z" } }, 400, /üç platformun/],
    [{ action: "schedule", tag: T, schedule: { youtube: "2026-11-06T15:00:00Z", instagram: "2026-11-06T17:00:00Z",
      tiktok: "2026-11-06T19:00:00Z", facebook: "2026-11-06T19:00:00Z" } }, 400, /Bilinmeyen platform/],
    [{ action: "schedule", tag: Z, schedule: { tiktok: "2026-11-06T19:00:00Z" }, code: "best" }, 400, /bilinmeyen alan/],
    [{ action: "schedule", tag: Z }, 400, /saatleri eksik/],
    [{ action: "schedule", tag: Z, schedule: {} }, 400, /saatleri eksik/],
    [{ action: "schedule", tag: Z, schedule: ["2026-11-06T19:00:00Z"] }, 400, /saatleri eksik/],
    [{ action: "schedule", tag: Z, schedule: { tiktok: "yarın 19:00" } }, 400, /TikTok saati geçersiz/],
    [{ action: "schedule", tag: Z, schedule: { tiktok: "2026-11-06T19:00:00" } }, 400, /geçersiz/], // saat dilimi yok
    [{ action: "schedule", tag: Z, schedule: { tiktok: 1762455600000 } }, 400, /geçersiz/],
    [{ action: "schedule", tag: Z, schedule: { tiktok: "2026-11-04T10:00:00Z" } }, 409, /geçti/],
    [{ action: "schedule", tag: Z, schedule: { tiktok: "2026-12-30T10:00:00Z" } }, 400, /30 gün/],
    [{ action: "schedule", tag: Z, schedule: { tiktok: "2026-11-05T16:30:00+00:00" } }, 400, /değişiklik yok/],
    [{ action: "schedule", tag: Y, schedule: { tiktok: "2026-11-06T19:00:00Z" } }, 409, /durumu değişmiş/],
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
    saatIlerlet(91000);
    const a = await istek("/panel/api/islem", POST({ action: "reject", tag: T }, c));
    const b = await istek("/panel/api/islem", POST({ action: "reject", tag: T }, c));
    assert.equal(a.r.status, 202);
    assert.equal(b.r.status, 409);
    assert.match((await b.r.json()).hata, /az önce/);
    assert.equal(dispatchlar(b.cagrilar).length, 0);
  });

  test("aynı videoya ikinci işlem (onay sonra ret) önceki işlem kaydı değiştirene kadar iletilmez", async () => {
    const c = await oturum();
    saatIlerlet(91000);
    assert.equal((await istek("/panel/api/islem", POST({ action: "approve", tag: T, code: "now" }, c))).r.status, 202);
    saatIlerlet(1000);
    for (const govde of [{ action: "reject", tag: T }, { action: "edit", tag: T, title: "x", description: "y" }]) {
      const x = await istek("/panel/api/islem", POST(govde, c));
      assert.equal(x.r.status, 409);
      assert.match((await x.r.json()).hata, /bir işlem sürüyor/);
      assert.equal(dispatchlar(x.cagrilar).length, 0);
      assert.equal(x.cagrilar.filter((y) => y.url.includes("telegram")).length, 0, "Telegram düğmesi de kilitlenmez");
    }
    // başka video etkilenmez
    assert.equal((await istek("/panel/api/islem", POST({ action: "cancel", tag: Z }, c))).r.status, 202);
    // 90 sn sonra kilit kendiliğinden kalkar
    saatIlerlet(91000);
    assert.equal((await istek("/panel/api/islem", POST({ action: "reject", tag: T }, c))).r.status, 202);
    // kayıt değiştiyse (önceki işlem işlendi) beklemeden yeni işlem yapılabilir
    saatIlerlet(1000);
    const kok = mkdtempSync(join(tmpdir(), "panel_kilit_"));
    cpSync(FIKSTUR, kok, { recursive: true });
    const vs = JSON.parse(readFileSync(join(kok, "videos.json"), "utf8"));
    vs.find((v) => v.tag === T).duzenleme = { title: "x", description: "y" };
    writeFileSync(join(kok, "videos.json"), JSON.stringify(vs));
    const x = await istek("/panel/api/islem", { ...POST({ action: "approve", tag: T, code: "best" }, c), fetchAyar: { kok } });
    assert.equal(x.r.status, 202);
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

// ------------------------------------------------------------------ takvim (schedule) kısmen paylaşılmış video
describe("takvim işlemi: kısmen paylaşılmış ve paylaşımı yaklaşan video", () => {
  const Z = "short-20261104-2023"; // GTA: youtube 15:00Z, instagram 09:30Z, tiktok 16:30Z
  const SAAT = Date.parse("2026-11-05T12:00:00Z"); // önceki testlerin işlem kilitlerinden sonra
  function kokYap(degistir) {
    const kok = mkdtempSync(join(tmpdir(), "panel_takvim_"));
    cpSync(FIKSTUR, kok, { recursive: true });
    const vs = JSON.parse(readFileSync(join(FIKSTUR, "videos.json"), "utf8"));
    degistir(vs.find((v) => v.tag === Z));
    writeFileSync(join(kok, "videos.json"), JSON.stringify(vs));
    return kok;
  }
  const kismen = (v) => { // Instagram 12:30'da paylaşıldı, sıradaki YouTube
    v.platforms = { instagram: { status: "ok", url: "u", at: "2026-11-05T12:30:05+03:00" } };
    v.publish_at = "2026-11-05T15:00:00+00:00";
  };
  async function gonder(kok, schedule) {
    saatIlerlet(91000);
    const c = await oturum();
    const x = await istek("/panel/api/islem", { ...POST({ action: "schedule", tag: Z, schedule }, c), fetchAyar: { kok } });
    return { ...x, j: await x.r.json() };
  }
  beforeEach(() => saatKur(SAAT));

  test("paylaşılmış platformun saati değiştirilemez, bekleyenin değiştirilebilir", async () => {
    const kok = kokYap(kismen);
    let x = await gonder(kok, { instagram: "2026-11-05T17:00:00Z" });
    assert.equal(x.r.status, 409);
    assert.match(x.j.hata, /Instagram zaten paylaşıldı/);
    assert.equal(dispatchlar(x.cagrilar).length, 0);
    x = await gonder(kok, { tiktok: "2026-11-05T19:00:00Z", youtube: "2026-11-05T18:00:00+00:00" });
    assert.equal(x.r.status, 202, x.j.hata);
    const p = panelOlayi(x.cagrilar);
    assert.deepEqual(p.schedule, { youtube: "2026-11-05T18:00:00+00:00", tiktok: "2026-11-05T19:00:00+00:00" });
  });

  test("kısmen paylaşılıp kalanları iptal edilen video: onayda yalnız paylaşılmamış platformlar", async () => {
    const kok = kokYap((v) => { kismen(v); Object.assign(v, { status: "onay_bekliyor", publish_at: null, schedule: null }); });
    let x = await gonder(kok, { youtube: "2026-11-05T18:00:00Z", instagram: "2026-11-05T18:00:00Z", tiktok: "2026-11-05T19:00:00Z" });
    assert.equal(x.r.status, 409);
    assert.match(x.j.hata, /Instagram zaten paylaşıldı/);
    x = await gonder(kok, { youtube: "2026-11-05T18:00:00Z" });
    assert.equal(x.r.status, 400);
    assert.equal(x.j.hata, "Onay için TikTok saati de seçilmeli.");
    assert.equal(dispatchlar(x.cagrilar).length, 0);
    x = await gonder(kok, { youtube: "2026-11-05T18:00:00Z", tiktok: "2026-11-05T19:00:30+00:00" });
    assert.equal(x.r.status, 202, x.j.hata);
    assert.deepEqual(panelOlayi(x.cagrilar).schedule, { youtube: "2026-11-05T18:00:00+00:00", tiktok: "2026-11-05T19:01:00+00:00" });
  });

  test("paylaşıma 10 dakikadan az kalan videoda saat değişmez; en erken 2 dakika sonrası seçilir", async () => {
    let kok = kokYap((v) => { kismen(v); v.publish_at = new Date(SAAT + 9 * 60e3).toISOString(); v.schedule.youtube = v.publish_at; });
    let x = await gonder(kok, { tiktok: "2026-11-05T19:00:00Z" });
    assert.equal(x.r.status, 409);
    assert.match(x.j.hata, /10 dakika/);
    // eskimiş publish_at (bekleyen bütün platformlar daha sonra) kilitlemez: paylaşım anı bekleyen en erken saattir
    kok = kokYap((v) => { kismen(v); v.publish_at = "2026-11-05T09:30:00+00:00"; });
    x = await gonder(kok, { tiktok: new Date(SAAT + 60e3 + 30e3).toISOString() });
    assert.equal(x.r.status, 409);
    assert.match(x.j.hata, /en erken 2 dakika/);
    x = await gonder(kok, { tiktok: new Date(Date.now() + 91000 + 3 * 60e3).toISOString() }); // gonder saati 91 sn ilerletir
    assert.equal(x.r.status, 202, x.j.hata);
  });
});

// ------------------------------------------------------------------ zamanlayıcı (Cloudflare cron)
describe("zamanlayıcı: saati yaklaşan paylaşım için onay.yml", () => {
  const SIMDI = Date.parse("2026-11-05T14:52:30Z");
  const iso = (ms) => new Date(ms).toISOString().replace(".000Z", "+00:00");
  const video = (dk, ek = {}) => ({ tag: "short-20261105-120000", title: "Deneme", status: "zamanlandi", platforms: {},
    publish_at: iso(SIMDI + dk * 60e3), schedule: { youtube: iso(SIMDI + dk * 60e3), instagram: iso(SIMDI + (dk + 60) * 60e3),
      tiktok: iso(SIMDI + (dk + 120) * 60e3) }, ...ek });
  async function calistir(vs, ayar = {}) {
    const kok = mkdtempSync(join(tmpdir(), "panel_cron_"));
    cpSync(FIKSTUR, kok, { recursive: true });
    if (vs) writeFileSync(join(kok, "videos.json"), JSON.stringify(vs));
    const f = fetchKur({ kok, ...ayar });
    const loglar = [];
    console.log = (...a) => loglar.push(a.map(String).join(" "));
    try {
      await worker.scheduled({ cron: "* * * * *", scheduledTime: Date.now() }, { ...ORTAM }, ctxYap().ctx);
    } finally { console.log = () => {}; }
    const yol = (c) => c.url.replace(`https://api.github.com/repos/${ORTAM.REPO}/`, "");
    return { cagrilar: f.cagrilar, loglar, yollar: f.cagrilar.map((c) => `${c.method} ${yol(c)}`),
      onay: f.cagrilar.filter((c) => c.url.endsWith("/actions/workflows/onay.yml/dispatches")) };
  }
  // onay.yml iş listesindeki bir iş: SIMDI'den dkOnce dakika önce başlatılmış; hedef null ise cron işi
  const is_ = (status, dkOnce, hedef, conclusion = null) => ({ display_title: hedef ? `Paylaşım ${hedef}` : "Telegram onaylarını işle",
    name: "Telegram onaylarını işle", status, conclusion, created_at: new Date(SIMDI - dkOnce * 60e3).toISOString() });
  beforeEach(() => saatKur(SIMDI));

  test("3 dakika içindeki paylaşım için bir kez, doğru girdilerle başlatır", async () => {
    const { yollar, onay, cagrilar, loglar } = await calistir([video(2.5)]);
    assert.deepEqual(yollar, ["GET contents/state/videos.json?ref=main", "GET actions/workflows/onay.yml/runs?per_page=20",
      "POST actions/workflows/onay.yml/dispatches"]);
    assert.deepEqual(onay[0].govde, { ref: "main", inputs: { dakika: "5", hedef: "2026-11-05T14:55Z" } });
    assert.ok(cagrilar.every((c) => c.basliklar.authorization === `Bearer ${ORTAM.GH_PAT}`));
    assert.match(loglar.join("\n"), /başlatıldı \(2026-11-05T14:55Z, 5 dk\)/);
    assert.ok(!loglar.join("\n").includes(ORTAM.GH_PAT));
    // saniyeli an dakikaya iner, kalan süre yukarı yuvarlanır (iş ~1 dk'da kurulur, boş bekleme olmasın)
    assert.equal(hedefAdi(Date.parse("2026-11-05T14:57:59Z")), "2026-11-05T14:57Z");
    const yakin = await calistir([video(1.2)]);
    assert.deepEqual(yakin.onay[0].govde.inputs, { dakika: "4", hedef: "2026-11-05T14:53Z" });
    assert.equal((await calistir([video(3.5)])).onay.length, 0, "3 dakikadan uzak");
    // Telegram'a hiçbir şey gitmez
    assert.equal(cagrilar.filter((c) => c.url.includes("telegram")).length, 0);
  });

  test("aynı hedefle bekleyen/çalışan ya da son 30 dk'da başlatılmış iş varsa başlatmaz", async () => {
    const hedef = "2026-11-05T14:55Z";
    for (const isler of [[is_("queued", 1, hedef)], [is_("in_progress", 25, hedef)], [is_("completed", 10, hedef)]]) {
      const x = await calistir([video(2.5)], { isler });
      assert.equal(x.onay.length, 0, JSON.stringify(isler));
      assert.match(x.loglar.join(" "), /iş zaten var/);
    }
    const iptal = is_("completed", 5, hedef, "cancelled"); // state grubunda çalışmadan iptal edilmiş
    for (const isler of [[is_("completed", 40, hedef)], [is_("queued", 1, "2026-11-05T13:57Z")], [is_("in_progress", 2, null)], [iptal]]) {
      assert.equal((await calistir([video(2.5)], { isler })).onay.length, 1, JSON.stringify(isler));
    }
  });

  test("bekleyen yoksa, saati uzaksa ya da 3 saatten eskiyse başlatmaz", async () => {
    for (const vs of [[], [video(30)], [video(4)], [video(-181)], [{ ...video(2), status: "onay_bekliyor" }], [{ ...video(2), status: "yayinlandi" }]]) {
      const x = await calistir(vs);
      assert.equal(x.onay.length, 0, JSON.stringify(vs));
      assert.deepEqual(x.yollar, ["GET contents/state/videos.json?ref=main"], "iş listesine bile bakılmaz");
    }
    // 3 saatten yeni, saati geçmiş paylaşım: hemen (2 dk dinleme)
    assert.deepEqual((await calistir([video(-30)])).onay[0].govde.inputs, { dakika: "2", hedef: "2026-11-05T14:22Z" });
    // takılı (3 saatten eski) kayıt diğer videonun paylaşımını engellemez
    const ikinci = { ...video(2), tag: "short-20261105-130000" };
    assert.equal((await calistir([video(-200), ikinci])).onay[0].govde.inputs.hedef, "2026-11-05T14:54Z");
  });

  test("paylaşım anı: paylaşılan platformlar sayılmaz; saati geçmiş ama publish_at'te denenecek platform erken başlatmaz", async () => {
    // YouTube paylaşıldı (saati geçmiş), sıradaki Instagram 2 dk sonra
    let v = video(-50, { platforms: { youtube: { status: "ok" } } });
    v.schedule.instagram = iso(SIMDI + 2 * 60e3); v.publish_at = v.schedule.instagram;
    assert.equal((await calistir([v])).onay[0].govde.inputs.hedef, "2026-11-05T14:54Z");
    // YouTube 30 dk önce hata aldı, publish_at 60 dk sonra (Instagram): şimdi başlatılmaz
    v = video(-30, { platforms: { youtube: { status: "hata", error: "x" } } });
    v.publish_at = v.schedule.instagram;
    assert.equal((await calistir([v])).onay.length, 0);
    // eskimiş publish_at, bekleyen platformlar 2,5 dk sonra: o ana göre
    v = video(2.5); v.publish_at = iso(SIMDI - 100 * 60e3);
    assert.equal((await calistir([v])).onay[0].govde.inputs.hedef, "2026-11-05T14:55Z");
  });

  test("saati geçmiş kaydın işi (hata almış, yüklüyor) sonraki videonun paylaşımını bekletmez; işler birbirini iptal etmez", async () => {
    const A = video(-40), B = { ...video(1.5), tag: "short-20261105-130000" }; // A 14:12:30'du, B 14:54:00
    const b = { dakika: "4", hedef: "2026-11-05T14:54Z" };
    for (const isler of [[is_("completed", 20, "2026-11-05T14:12Z", "failure")], [is_("in_progress", 39, "2026-11-05T14:12Z")]]) {
      const x = await calistir([A, B], { isler });
      assert.deepEqual(x.onay.map((o) => o.govde.inputs), [b], JSON.stringify(isler));
      assert.equal(x.yollar.filter((y) => y.includes("/runs")).length, 1, "iş listesi bir kez okunur");
    }
    // A'nın işi yok (30 dk'dan eski): önce A için (hemen paylaşır; B 2 dk'lık pencerede)
    let x = await calistir([A, B], { isler: [is_("completed", 45, "2026-11-05T14:12Z", "failure")] });
    assert.deepEqual(x.onay.map((o) => o.govde.inputs), [{ dakika: "2", hedef: "2026-11-05T14:12Z" }]);
    // B'nin işi kuyrukta, A'nınki onun yüzünden iptal oldu: başlamamış iş A'yı da paylaşır, yenisi başlatılmaz
    x = await calistir([A, B], { isler: [is_("queued", 1, "2026-11-05T14:54Z"), is_("completed", 2, "2026-11-05T14:12Z", "cancelled")] });
    assert.equal(x.onay.length, 0);
    assert.match(x.loglar.join(" "), /iş zaten var \(2026-11-05T14:12Z, 2026-11-05T14:54Z\)/);
    // iş listesi alınamazsa saati geçmiş A atlanır, B için başlatılır
    x = await calistir([A, B], { islerDurum: 500 });
    assert.deepEqual(x.onay.map((o) => o.govde.inputs), [b]);
  });

  test("GitHub hatalarında hata fırlatmaz; iş listesi alınamazsa yalnız saati gelmemiş paylaşım için başlatır", async () => {
    let x = await calistir([video(2.5)], { dosyaHata: { "videos.json": 500 } });
    assert.equal(x.onay.length, 0);
    assert.match(x.loglar.join(" "), /durum okunamadı \(500\)/);
    x = await calistir([video(2.5)], { islerDurum: 500 });
    assert.equal(x.onay.length, 1);
    x = await calistir([video(-10)], { islerDurum: 500 });
    assert.equal(x.onay.length, 0);
    assert.match(x.loglar.join(" "), /iş listesi alınamadı/);
    x = await calistir([video(2.5)], { onayDurum: 422 });
    assert.match(x.loglar.join(" "), /başlatılamadı \(422\)/);
    x = await calistir([video(2.5)], { ghAgHatasi: true });
    assert.match(x.loglar.join(" "), /zamanlayıcı hatası/);
    // ayar eksikse GitHub'a hiç gidilmez
    const f = fetchKur({});
    await worker.scheduled({}, { ...ORTAM, GH_PAT: undefined }, ctxYap().ctx);
    assert.equal(f.cagrilar.length, 0);
  });
});

// ------------------------------------------------------------------ Konular: öneri serileri
// Playwright (ekran.mjs'in kullandığı) yoksa tarayıcı testi atlanır; kapı istekleri tarayıcıdan doğrudan worker.fetch'e gider
let chromium = null;
try {
  ({ chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT || "/opt/node22/lib/node_modules/playwright"));
} catch { /* yok */ }
const KALIPLI = ["efsane", "nasil", "uretim", "olsaydin", "kitap"]; // kalıbı sabit seriler: sıraya eklenmez

describe("Konular: öneri serileri", () => {
  const DEPO = join(BURASI, "..", "..");

  test("yedi seri trends.SERILER sırasıyla; kalıbı sabit beş serinin notu var", () => {
    assert.deepEqual(ONERI_SERILERI.map(([k]) => k), ["populer", "konu", "efsane", "nasil", "uretim", "olsaydin", "kitap"]);
    assert.deepEqual(ONERI_SERILERI[6], ["kitap", "Kitap", "Bir Kitap Bir Dakika", "📖"]);
    assert.equal(new Set(ONERI_SERILERI.map(([, , , ik]) => ik)).size, ONERI_SERILERI.length, "simgeler ayrı (Konular 📚)");
    // olsaydin'in adı geçici (sahibi seçiyor): yalnız simgesi sabit; adı Python'la karşılaştırılır (sonraki test)
    assert.deepEqual(ONERI_SERILERI[4], ["uretim", "Üretim", "Nasıl üretiliyor?", "🏭"]);
    assert.equal(ONERI_SERILERI[5][3], "💭");
    for (const s of ONERI_SERILERI) assert.ok(s.length === 4 && s.every((x) => typeof x === "string" && x.trim()), String(s));
    assert.equal(new Set(ONERI_SERILERI.map(([, kisa]) => kisa)).size, ONERI_SERILERI.length, "süzgeç adları ayrı");
    assert.deepEqual(Object.keys(SERI_NOTU), KALIPLI);
    for (const k of KALIPLI) {
      const ad = ONERI_SERILERI.find(([x]) => x === k)[2];
      assert.ok(SERI_NOTU[k].startsWith(`“${ad}” kalıbıyla`), k);
      assert.ok(SERI_NOTU[k].endsWith(". "), "onay metninde 'Video yaklaşık…' cümlesinden önce gelir: " + k);
    }
    assert.match(SERI_NOTU.uretim, /aşama kartları şablonu/);
    assert.match(SERI_NOTU.olsaydin, /kart şablonunda sayaç ve hesap fişi kartlarıyla/);
    assert.match(SERI_NOTU.kitap, /kitap kapağı ve sayfalarıyla/);
    assert.match(SERI_NOTU.kitap, /kamu malı olmayan kitapta alıntı yerine künye sayfası/);
    // uygulama listeyi ve notları kapıdan (AYAR) alır: tarayıcıdaki kopya aynı
    assert.ok(UYGULAMA_JS.includes(JSON.stringify(ONERI_SERILERI)) && UYGULAMA_JS.includes(JSON.stringify(SERI_NOTU)));
  });

  test("Python'daki seriler panelde aynı sıra, ad ve simgeyle var; kalıbı sabit her serinin notu var", () => {
    // trends.py birleşince yedi seri olur; panel önden giderse fazlası zararsızdır (o seriden öneri gelmez)
    const tr = readFileSync(join(DEPO, "shortgen", "trends.py"), "utf8");
    const sozluk = (ad) => {
      const m = new RegExp(`^${ad} = \\{([^}]*)\\}`, "m").exec(tr);
      assert.ok(m, `trends.${ad} okunamadı`);
      return [...m[1].matchAll(/"(\w+)":\s*("([^"]*)")?/g)].map((x) => [x[1], x[3]]);
    };
    const seriler = sozluk("SERILER"), panel = ONERI_SERILERI.map(([k]) => k);
    assert.ok(seriler.length >= 4);
    assert.deepEqual(panel.filter((k) => seriler.some(([s]) => s === k)), seriler.map(([s]) => s), "panelde eksik ya da sırası farklı seri");
    for (const [k, ad] of seriler) if (ad !== undefined) assert.equal(ONERI_SERILERI.find(([x]) => x === k)[2], ad, k);
    for (const [k, ik] of sozluk("SERI_IKON")) if (ik !== undefined) assert.equal(ONERI_SERILERI.find(([x]) => x === k)[3], ik, k);
    for (const [k] of sozluk("SERI_KALIP")) assert.ok(SERI_NOTU[k], "kalıbı sabit serinin notu yok: " + k);
  });

  test("olsaydin serisinin geçici adı panelde tek yerde (ONERI_SERILERI); kapı kodunda hiç yok", () => {
    const kaynak = (ad) => readFileSync(join(DEPO, "cloudflare", ad), "utf8");
    const say = (metin, aranan) => metin.split(aranan).length - 1;
    const ui = kaynak("panel_ui.js");
    const [, kisa, ad] = ONERI_SERILERI.find(([k]) => k === "olsaydin");
    assert.equal(say(ui, ad), 1);
    assert.equal(say(ui, `"${kisa}"`), 1);
    assert.equal(say(ui, "SERI_ADI.olsaydin"), 1, "not adı listeden alır");
    for (const d of ["panel.js", "worker.js"]) {
      for (const x of [ad, kisa, "olsaydin"]) assert.equal(say(kaynak(d).toLocaleLowerCase("tr"), x.toLocaleLowerCase("tr")), 0, d + ": " + x);
    }
  });

  test("tarayıcıda (390 px): seri sırası, notlar, sıra düğmesi yok, süzgeç kendi satırında kayar", { skip: !chromium && "Playwright yok" },
    async () => {
      const kok = mkdtempSync(join(tmpdir(), "panel-alti-ui-"));
      cpSync(FIKSTUR, kok, { recursive: true });
      writeFileSync(join(kok, "oneriler.json"), JSON.stringify(YEDI_SERI));
      saatIlerlet(30000);
      const cerez = await oturum(19 * 86400); // başka testin önbelleğe aldığı durum gelmesin
      const gidenler = [];
      const tarayici = await chromium.launch();
      try {
        const ctx = await tarayici.newContext({ viewport: { width: 390, height: 844 }, locale: "tr-TR" });
        await ctx.addCookies([{ name: "bm_oturum", value: cerez, url: HOST }]);
        await ctx.route("**/*", async (route) => {
          const r = route.request();
          if (!r.url().startsWith(HOST + "/")) return route.abort(); // yazı tipi vb.: dış istek yok
          const f = fetchKur({ kok });
          const { ctx: c, bitir } = ctxYap();
          const govde = r.postDataBuffer();
          const y = await worker.fetch(new Request(r.url(), { method: r.method(), headers: await r.allHeaders(),
            body: govde || undefined }), { ...ORTAM }, c);
          await bitir();
          gidenler.push(...f.cagrilar);
          return route.fulfill({ status: y.status, headers: Object.fromEntries(y.headers), body: Buffer.from(await y.arrayBuffer()) });
        });
        const page = await ctx.newPage();
        const hatalar = [];
        page.on("pageerror", (e) => hatalar.push(e.message));
        await page.goto(HOST + "/panel#konular");
        await page.waitForSelector(".oneri");
        const ozet = () => page.evaluate(() => ({
          basliklar: [...document.querySelectorAll(".seri-baslik span")].map((x) => x.textContent),
          cipler: [...document.querySelectorAll(".cip")].map((c) => [c.dataset.seri, c.firstChild.textContent,
            c.querySelector("small").textContent, c.getAttribute("aria-pressed")]),
          kartlar: [...document.querySelectorAll(".oneri")].map((k) => [k.dataset.seri, k.querySelector(".oneri-no").textContent,
            [...k.querySelectorAll("button")].map((b) => b.textContent), (k.querySelector(".oneri-not") || {}).textContent || ""]),
        }));
        let o = await ozet();
        assert.deepEqual(o.basliklar, ONERI_SERILERI.map(([, , ad, ik]) => `${ik} ${ad}`));
        assert.deepEqual(o.cipler, [["tumu", "Tümü", "21", "true"], ...ONERI_SERILERI.map(([k, kisa]) => [k, kisa, "3", "false"])]);
        assert.deepEqual(o.kartlar.map(([s, no]) => [s, no]), YEDI_SERI.items.map((it, i) => [it.seri, `${i + 1}.`]));
        for (const [seri, , dugmeler, not] of o.kartlar) {
          assert.equal(dugmeler.includes("Sıraya ekle"), !KALIPLI.includes(seri), seri);
          assert.equal(Boolean(not), KALIPLI.includes(seri), seri);
          assert.ok(dugmeler.includes("Üret"), seri);
        }
        // telefonda: sayfa yana kaymaz, süzgeç kendi satırında kayar, her çip en az 44 px yüksek
        const olcu = () => page.evaluate(() => {
          const s = document.querySelector(".cipler"), sec = s.querySelector('[aria-pressed="true"]').getBoundingClientRect();
          return { sayfa: document.documentElement.scrollWidth, satir: [s.scrollWidth, s.clientWidth],
            boy: Math.min(...[...s.children].map((c) => c.getBoundingClientRect().height)), secili: [sec.left, sec.right],
            satirlar: new Set([...s.children].map((c) => Math.round(c.getBoundingClientRect().top))).size,
            kenar: ["sol-var", "sag-var"].filter((k) => s.classList.contains(k)) };
        });
        let m = await olcu();
        assert.ok(m.sayfa <= 390, "sayfa yana kayıyor: " + m.sayfa);
        assert.ok(m.satir[0] > m.satir[1], "çipler tek satırda, satır kendi içinde kayar");
        assert.equal(m.satirlar, 1);
        assert.ok(m.boy >= 44, "dokunma alanı: " + m.boy);
        assert.deepEqual(m.kenar, ["sag-var"], "sağda sığmayan çip var: sağ kenar solar");
        // en sondaki seriyi seç: yalnız o seri görünür, seçili çip yeniden çizimde görünür kalır
        await page.click('.cip[data-seri="kitap"]');
        o = await ozet();
        assert.deepEqual(o.basliklar, ["📖 Bir Kitap Bir Dakika"]);
        assert.deepEqual(o.kartlar.map(([s, no]) => [s, no]), [["kitap", "19."], ["kitap", "20."], ["kitap", "21."]]);
        assert.equal(o.cipler.find(([k]) => k === "kitap")[3], "true");
        m = await olcu();
        assert.ok(m.secili[0] >= 0 && m.secili[1] <= 390, "seçili çip görünür: " + m.secili);
        assert.deepEqual(m.kenar, ["sol-var"], "son çip seçili: satır sona kaydı, yalnız sol kenar solar");
        // kitap önerisinin Üret onayı serinin notunu söyler; Vazgeç ile hiçbir şey gönderilmez
        await page.click(".oneri >> nth=0 >> text=Üret");
        const kitapMetni = await page.textContent("dialog[open]");
        assert.ok(kitapMetni.includes(SERI_NOTU.kitap + "Video yaklaşık 15 dakikada hazır olur ve onaya gelir."), kitapMetni);
        await page.click("dialog[open] >> text=Vazgeç");
        await page.click('.cip[data-seri="olsaydin"]');
        o = await ozet();
        assert.deepEqual(o.basliklar, [ONERI_SERILERI[5][3] + " " + ONERI_SERILERI[5][2]]);
        assert.deepEqual(o.kartlar.map(([s, no]) => [s, no]), [["olsaydin", "16."], ["olsaydin", "17."], ["olsaydin", "18."]]);
        m = await olcu();
        assert.ok(m.secili[0] >= 0 && m.secili[1] <= 390, "seçili çip görünür: " + m.secili);
        await page.click('.cip[data-seri="uretim"]');
        o = await ozet();
        assert.deepEqual(o.basliklar, ["🏭 Nasıl üretiliyor?"]);
        assert.deepEqual(o.kartlar.map(([s]) => s), ["uretim", "uretim", "uretim"]);
        // Üret: onay penceresi serinin notunu söyler; gönderilen işlem yalnız sıra ve konu taşır
        await page.click('.cip[data-seri="olsaydin"]');
        await page.click(".oneri >> nth=0 >> text=Üret");
        const metin = await page.textContent("dialog[open]");
        assert.ok(metin.includes(SERI_NOTU.olsaydin + "Video yaklaşık 15 dakikada hazır olur ve onaya gelir."), metin);
        assert.ok(metin.includes(YEDI_SERI.items[15].topic));
        await page.click("dialog[open] .btn-ana");
        await page.waitForSelector(".bildirim");
        const d = gidenler.filter((x) => x.url.endsWith("/actions/workflows/isle.yml/dispatches"));
        assert.equal(d.length, 1);
        const p = JSON.parse(d[0].govde.inputs.update).panel;
        assert.deepEqual([p.action, p.index, p.topic], ["produce_suggestion", 15, YEDI_SERI.items[15].topic]);
        assert.deepEqual(Object.keys(p).sort(), ["action", "at", "index", "rid", "topic"]);
        assert.deepEqual(hatalar, []);
      } finally {
        await tarayici.close();
      }
    });
});

test("webhook senaryo listesi boş değil", () => assert.ok(SENARYOLAR.length > 20));
