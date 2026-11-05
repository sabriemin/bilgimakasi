// Panel ekran görüntüleri (Playwright + Chromium): 390x844 ve 1280x900, açık ve koyu tema, her sekme.
//   OUT=<klasör> [PORT=8790] [FONTS=<Google Fonts önbelleği>] [VIDEO=<örnek video>] [BOLUM=seriler] node tests/panel/ekran.mjs
// BOLUM=seriler: yalnız Konular sekmesindeki altı serili öneriler (panel_konular_*.png, 390x844 ve 1280x800).
// PORT, PORT+1 ve PORT+2 kullanılır. Takvim bölümü dokunmatik uzun basışla sürükleme ve Saat seç sayfasını da dener.
// Sunucu (sunucu.mjs) ayrı süreçte sabit saatle çalışır; yazı tipleri yerelden verilir, dış ağa çıkılmaz.
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, existsSync, mkdtempSync, cpSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createRequire } from "node:module";
import { BURASI, FIKSTUR, ALTI_SERI } from "./sahte.mjs";
import { SERI_NOTU } from "../../cloudflare/panel_ui.js";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT || "/opt/node22/lib/node_modules/playwright");
const OUT = process.env.OUT || join(BURASI, "ekran");
const FONTS = process.env.FONTS;
const SAAT = process.env.SAAT || "2026-11-05T00:45:00+03:00";
mkdirSync(OUT, { recursive: true });

// örnek duruma ek: bir sorunlu (kısmen paylaşılmış) video, Sorunlu bölümü de görünsün; seriler: altı serili öneriler
function durumHazirla(sorunlu, seriler = false) {
  const kok = mkdtempSync(join(tmpdir(), "panel_ekran_"));
  cpSync(FIKSTUR, kok, { recursive: true });
  if (seriler) writeFileSync(join(kok, "oneriler.json"), JSON.stringify(ALTI_SERI, null, 1));
  if (sorunlu) {
    const vs = JSON.parse(readFileSync(join(kok, "videos.json"), "utf8"));
    vs.push({ tag: "short-20261103-150200", title: "Kahve Avrupa'ya Gelince Neden Yasaklandı?", topic: "Kahvenin 1500'lerde Mekke ve İstanbul'da yasaklanması",
      category: "tarih", template: "gazete", created: "2026-11-03T15:02:00", status: "kismen", telegram_message_id: 30,
      platforms: { youtube: { status: "ok", id: "abc", url: "https://youtube.com/shorts/abc", at: "2026-11-03T21:00:05+03:00" },
        instagram: { status: "hata", error: "Instagram yükleme hatası: 400 {\"error\":{\"message\":\"Media upload has failed with error code 2207026\"}}" },
        tiktok: { status: "atlandi", note: "anahtarlar tanımlı değil" } },
      publish_at: "2026-11-03T18:00:00+00:00", published: "2026-11-03T21:00:40+03:00" });
    writeFileSync(join(kok, "videos.json"), JSON.stringify(vs, null, 1));
  }
  return kok;
}

async function sunucuBaslat(kok, port, saat = SAAT) {
  const p = spawn(process.execPath, [join(BURASI, "sunucu.mjs")], {
    env: { ...process.env, KOK: kok, PORT: String(port), SAAT: saat, VIDEO: process.env.VIDEO || "" }, stdio: ["ignore", "pipe", "inherit"] });
  await new Promise((ok, hata) => {
    p.stdout.on("data", (d) => { if (String(d).includes("hazir")) ok(); });
    p.on("exit", (c) => hata(new Error("sunucu kapandı " + c)));
  });
  return p;
}

async function yaziTipleri(ctx) {
  if (FONTS && existsSync(join(FONTS, "google.css"))) {
    const css = readFileSync(join(FONTS, "google.css"), "utf8");
    await ctx.route("https://fonts.googleapis.com/**", (r) => r.fulfill({ contentType: "text/css", body: css }));
    await ctx.route("https://fonts.gstatic.com/**", (r) => {
      const ad = new URL(r.request().url()).pathname.slice(1).replace(/\//g, "_");
      const yol = join(FONTS, ad);
      return existsSync(yol) ? r.fulfill({ contentType: "font/woff2", body: readFileSync(yol) }) : r.abort();
    });
  } else { // depodaki TTF'ler (DM Mono yalnız Medium)
    const f = join(BURASI, "..", "..", "shortgen", "assets", "fonts");
    const yuz = (aile, dosya, w) => `@font-face{font-family:'${aile}';font-weight:${w};src:url(https://fonts.gstatic.com/yerel/${dosya})}`;
    const css = [yuz("Anton", "Anton-Regular.ttf", 400), yuz("Courier Prime", "CourierPrime-Regular.ttf", 400),
      yuz("Courier Prime", "CourierPrime-Bold.ttf", 700), yuz("DM Mono", "DMMono-Medium.ttf", 400), yuz("DM Mono", "DMMono-Medium.ttf", 500)].join("\n");
    await ctx.route("https://fonts.googleapis.com/**", (r) => r.fulfill({ contentType: "text/css", body: css }));
    await ctx.route("https://fonts.gstatic.com/yerel/**", (r) =>
      r.fulfill({ contentType: "font/ttf", body: readFileSync(join(f, new URL(r.request().url()).pathname.split("/").pop())) }));
  }
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1|fonts\.)/, (r) => r.abort()); // başka hiçbir dış istek yok
}

const GORUNUMLER = [["mobil", { width: 390, height: 844 }, 2], ["masaustu", { width: 1280, height: 900 }, 1]];
const SEKMELER = ["videolar", "takvim", "istatistik", "konular"];

async function bekle(page) {
  await page.waitForSelector("main#icerik");
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(150);
}

async function main() {
  const browser = await chromium.launch();
  const kayit = [];
  const port = Number(process.env.PORT || 8790);
  const hatalar = [];
  if (process.env.BOLUM === "seriler") {
    await seriEkranlari(browser, port + 1, kayit, hatalar);
    return bitir(browser, kayit, hatalar);
  }
  const sunucu = await sunucuBaslat(durumHazirla(false), port);
  const URL = `http://127.0.0.1:${port}`;
  try {
    for (const tema of ["light", "dark"]) {
      for (const [ad, viewport, dsf] of GORUNUMLER) {
        const ctx = await browser.newContext({ viewport, deviceScaleFactor: dsf, colorScheme: tema, locale: "tr-TR",
          timezoneId: "Europe/Istanbul" });
        await yaziTipleri(ctx);
        const page = await ctx.newPage();
        page.on("pageerror", (e) => hatalar.push(`${ad}/${tema}: ${e.message}`));
        page.on("console", (m) => { if (m.type() === "error") hatalar.push(`${ad}/${tema} console: ${m.text()}`); });
        await page.goto(URL + "/__giris");
        await bekle(page);
        for (const sekme of SEKMELER) {
          await page.goto(`${URL}/panel#${sekme}`);
          await bekle(page);
          const genislik = await page.evaluate(() => document.documentElement.scrollWidth);
          if (genislik > viewport.width) hatalar.push(`${ad}/${tema}/${sekme}: yatay kaydırma (${genislik}px)`);
          const dosya = join(OUT, `${sekme}_${ad}_${tema === "light" ? "acik" : "koyu"}.png`);
          await page.screenshot({ animations: "disabled", path: dosya, fullPage: true });
          kayit.push(dosya);
        }
        // etkileşimler: yalnız mobil açık ve masaüstü koyu (yeterli kapsam)
        if ((ad === "mobil" && tema === "light") || (ad === "masaustu" && tema === "dark")) {
          const ek = `${ad}_${tema === "light" ? "acik" : "koyu"}`;
          await page.goto(`${URL}/panel#videolar`);
          await bekle(page);
          // iki görünüm ayrı videoyu onaylar: kapı aynı videoya 90 sn içinde ikinci işlemi almaz
          const onayKarti = `.kart >> nth=${ad === "mobil" ? 0 : 1}`;
          await page.click(`${onayKarti} >> .btn-ana`);
          await page.waitForSelector("dialog[open] .secenek");
          await page.screenshot({ animations: "disabled", path: join(OUT, `onay_secenekleri_${ek}.png`) }); kayit.push(join(OUT, `onay_secenekleri_${ek}.png`));
          await page.click(`dialog[open] .secenek >> nth=${ad === "mobil" ? 0 : 1}`);
          await page.waitForSelector(".bildirim");
          await page.waitForSelector('.kart [aria-busy="true"]');
          // aynı kartın diğer düğmeleri de kilitli (onay sürerken Reddet gönderilemez)
          const kilitsiz = await page.$$eval(`.kart:has([aria-busy="true"]) .dugmeler button:not([disabled])`, (b) => b.length);
          if (kilitsiz) hatalar.push(`${ad}/${tema}: işlem sürerken kartta ${kilitsiz} düğme açık`);
          await page.screenshot({ animations: "disabled", path: join(OUT, `islem_suruyor_${ek}.png`) }); kayit.push(join(OUT, `islem_suruyor_${ek}.png`));
          await page.goto(`${URL}/panel#videolar`);
          await bekle(page);
          const digerKart = `.kart >> nth=${ad === "mobil" ? 1 : 0}`; // işlemi sürmeyen kart (sayfa yeniden yüklenmez)
          await page.click(`${digerKart} >> text=Düzenle`);
          await page.waitForSelector("dialog[open] #f-baslik");
          await page.screenshot({ animations: "disabled", path: join(OUT, `duzenle_${ek}.png`) }); kayit.push(join(OUT, `duzenle_${ek}.png`));
          await page.keyboard.press("Escape");
          await page.click(`${digerKart} >> text=Reddet`);
          await page.waitForSelector("dialog[open]");
          await page.screenshot({ animations: "disabled", path: join(OUT, `reddet_onay_${ek}.png`) }); kayit.push(join(OUT, `reddet_onay_${ek}.png`));
          await page.keyboard.press("Escape");
          if (process.env.VIDEO) {
            await page.click(".kart >> nth=2 >> .oynat");
            await page.waitForFunction(() => { const v = document.querySelector(".kart.acik video"); return v && v.currentTime > 0.6; }, null, { timeout: 15000 });
            await page.evaluate(() => document.querySelector(".kart.acik video").pause());
            await page.waitForTimeout(800); // kaydırma bitsin
            await page.screenshot({ animations: "disabled", path: join(OUT, `oynatici_${ek}.png`) }); kayit.push(join(OUT, `oynatici_${ek}.png`));
          }
          await page.goto(`${URL}/panel#istatistik`);
          await bekle(page);
          const g = await page.$(".grafik");
          const kutu = await g.boundingBox();
          await page.mouse.move(kutu.x + kutu.width * 0.55, kutu.y + kutu.height / 2);
          await page.waitForSelector(".ipucu:not([hidden])");
          const gk = await page.$(".grafik-kart");
          await gk.screenshot({ animations: "disabled", path: join(OUT, `grafik_ipucu_${ek}.png`) }); kayit.push(join(OUT, `grafik_ipucu_${ek}.png`));
          await page.goto(`${URL}/panel#konular`);
          await bekle(page);
          await page.fill("#yeni-konu", "Ankara'nın başkent seçilmesinde tren istasyonunun rolü");
          await page.press("#yeni-konu", "Enter");
          await page.click(".kuyruk li >> nth=1 >> [aria-label='Yukarı taşı']");
          await page.screenshot({ animations: "disabled", path: join(OUT, `konular_duzenleniyor_${ek}.png`), fullPage: true });
          kayit.push(join(OUT, `konular_duzenleniyor_${ek}.png`));
        }
        await ctx.close();
      }
    }
    // giriş ekranı (çerez yok) ve geçersiz bağlantı sayfası
    for (const tema of ["light", "dark"]) {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, colorScheme: tema });
      await yaziTipleri(ctx);
      const page = await ctx.newPage();
      await page.goto(URL + "/panel");
      await page.waitForSelector(".giris-kart");
      await page.evaluate(() => document.fonts.ready);
      const t = tema === "light" ? "acik" : "koyu";
      await page.screenshot({ animations: "disabled", path: join(OUT, `giris_${t}.png`) }); kayit.push(join(OUT, `giris_${t}.png`));
      await page.goto(URL + "/panel/giris?t=123.abc");
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ animations: "disabled", path: join(OUT, `gecersiz_baglanti_${t}.png`) }); kayit.push(join(OUT, `gecersiz_baglanti_${t}.png`));
      await ctx.close();
    }
  } finally {
    sunucu.kill();
  }
  // sorunlu video örneği
  const s2 = await sunucuBaslat(durumHazirla(true), port + 1);
  try {
    for (const tema of ["light", "dark"]) {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, colorScheme: tema });
      await yaziTipleri(ctx);
      const page = await ctx.newPage();
      page.on("pageerror", (e) => hatalar.push(`sorunlu/${tema}: ${e.message}`));
      await page.goto(`http://127.0.0.1:${port + 1}/__giris`);
      await bekle(page);
      const el = await page.$("#b-sorunlu");
      await el.scrollIntoViewIfNeeded();
      const kart = await page.$("#b-sorunlu + .izgara .kart");
      const dosya = join(OUT, `sorunlu_kart_${tema === "light" ? "acik" : "koyu"}.png`);
      // sabit alt sekme çubuğu öğe görüntüsünün üstüne binmesin
      await kart.screenshot({ animations: "disabled", path: dosya, style: ".sekmeler{display:none!important}" }); kayit.push(dosya);
      await ctx.close();
    }
  } finally {
    s2.kill();
  }
  await takvimEkranlari(browser, port + 2, kayit, hatalar);
  await seriEkranlari(browser, port + 1, kayit, hatalar);
  return bitir(browser, kayit, hatalar);
}

async function bitir(browser, kayit, hatalar) {
  await browser.close();
  console.log(kayit.join("\n"));
  if (hatalar.length) { console.error("SORUNLAR:\n" + hatalar.join("\n")); process.exitCode = 1; }
}

// ---------------------------------------------------------------- Konular: öneri serileri
// Altı serili öneriler (sahte.mjs ALTI_SERI): kalıbı sabit seriler (efsane, nasil, uretim, olsaydin) sıraya eklenmez
// ve nedenini söyler; yedi süzgeç çipi telefonda kendi satırında kayar, sayfa yana kaymaz.
// Görüntüler: Tümü ve iki yeni serinin süzgeci (açık tema), Tümü (koyu tema), olsaydin önerisinin Üret onayı (telefon).
const SERI_GORUNUMLER = [["mobil", { width: 390, height: 844 }, 2], ["masaustu", { width: 1280, height: 800 }, 1]];
const KALIPLI = ["efsane", "nasil", "uretim", "olsaydin"];

async function seriEkranlari(browser, port, kayit, hatalar) {
  const sunucu = await sunucuBaslat(durumHazirla(false, true), port);
  const URL = `http://127.0.0.1:${port}`;
  try {
    for (const tema of ["light", "dark"]) {
      for (const [ad, viewport, dsf] of SERI_GORUNUMLER) {
        const t = tema === "light" ? "acik" : "koyu", yer = `seriler/${ad}/${tema}`;
        const ctx = await browser.newContext({ viewport, deviceScaleFactor: dsf, colorScheme: tema, locale: "tr-TR",
          timezoneId: "Europe/Istanbul" });
        await yaziTipleri(ctx);
        const page = await ctx.newPage();
        page.on("pageerror", (e) => hatalar.push(`${yer}: ${e.message}`));
        page.on("console", (m) => { if (m.type() === "error") hatalar.push(`${yer} console: ${m.text()}`); });
        await page.goto(`${URL}/__giris`);
        await bekle(page);
        await page.goto(`${URL}/panel#konular`);
        await bekle(page);
        const denetle = async (filtre, beklenen) => {
          const d = await page.evaluate(() => {
            const s = document.querySelector(".cipler");
            const cip = [...s.children].map((c) => c.getBoundingClientRect());
            const sec = s.querySelector('[aria-pressed="true"]').getBoundingClientRect();
            return { sayfa: document.documentElement.scrollWidth, gen: window.innerWidth,
              kartlar: [...document.querySelectorAll(".oneri[data-seri]")].map((k) => ({ seri: k.dataset.seri,
                sira: [...k.querySelectorAll("button")].some((b) => b.textContent.includes("Sıraya ekle")),
                not: Boolean(k.querySelector(".oneri-not")) })),
              boy: Math.min(...cip.map((r) => r.height)), secili: [sec.left, sec.right],
              sRect: [s.getBoundingClientRect().left, s.getBoundingClientRect().right] };
          });
          if (d.kartlar.length !== beklenen) hatalar.push(`${yer}/${filtre}: ${d.kartlar.length} öneri kartı (${beklenen} bekleniyordu)`);
          if (filtre !== "tumu" && d.kartlar.some((k) => k.seri !== filtre)) hatalar.push(`${yer}/${filtre}: başka serinin kartı görünüyor`);
          for (const k of d.kartlar) {
            const kalipli = KALIPLI.includes(k.seri);
            if (k.sira === kalipli || k.not !== kalipli) hatalar.push(`${yer}: ${k.seri} kartında sıra düğmesi/notu yanlış`);
          }
          if (d.sayfa > d.gen) hatalar.push(`${yer}/${filtre}: yatay kaydırma (${d.sayfa}px)`);
          if (d.boy < 44) hatalar.push(`${yer}/${filtre}: süzgeç çipi ${d.boy}px (en az 44)`);
          if (d.secili[0] < Math.max(0, d.sRect[0]) || d.secili[1] > Math.min(d.gen, d.sRect[1])) {
            hatalar.push(`${yer}/${filtre}: seçili çip görünmüyor (${d.secili})`);
          }
        };
        const ekranAl = async (filtre) => {
          const dosya = join(OUT, `panel_konular_${filtre}_${ad}_${t}.png`);
          await page.screenshot({ animations: "disabled", path: dosya, fullPage: true }); kayit.push(dosya);
        };
        await denetle("tumu", 18);
        await ekranAl("tumu");
        if (tema === "light") {
          for (const filtre of ["uretim", "olsaydin"]) {
            await page.click(`.cip[data-seri="${filtre}"]`);
            await page.waitForTimeout(150);
            await denetle(filtre, 3);
            await ekranAl(filtre);
          }
          if (ad === "mobil") { // olsaydin önerisinin Üret onayı: serinin notu söylenir
            await page.click(".oneri >> nth=0 >> text=Üret");
            await page.waitForSelector("dialog[open]");
            const metin = await page.textContent("dialog[open]");
            if (!metin.includes(SERI_NOTU.olsaydin + "Video yaklaşık 15 dakikada")) {
              hatalar.push(`${yer}: olsaydin onay metni: ${metin}`);
            }
            await page.waitForTimeout(250);
            const dosya = join(OUT, `panel_konular_olsaydin_onay_${ad}_${t}.png`);
            await page.screenshot({ animations: "disabled", path: dosya }); kayit.push(dosya);
            await page.click("dialog[open] >> text=Vazgeç");
          }
        }
        await ctx.close();
      }
    }
  } finally {
    sunucu.kill();
  }
}

// ---------------------------------------------------------------- Takvim
// Öğlen saatinde (13:10) dolu bir takvim: kısmen paylaşılmış (GTA: Instagram 12:30'da paylaşıldı), paylaşımı 8 dk
// sonra başlayan (kilitli), zamanlanmış (Açlık Oyunları TikTok'u 5'in katı olmayan 22:02'de) ve onay bekleyen videolar.
const TAKVIM_SAAT = "2026-11-05T13:10:00+03:00";
const GTA = "short-20261104-2023", ACLIK = "short-20261104-2048", ONAY = ["short-20261104-1019", "short-20261104-1057"];
function takvimDurumu() {
  const kok = mkdtempSync(join(tmpdir(), "panel_takvim_"));
  cpSync(FIKSTUR, kok, { recursive: true });
  const vs = JSON.parse(readFileSync(join(kok, "videos.json"), "utf8"));
  const bul = (t) => vs.find((v) => v.tag === t);
  Object.assign(bul(GTA), { publish_at: "2026-11-05T15:00:00+00:00",
    platforms: { instagram: { status: "ok", url: "https://www.instagram.com/reel/x/", at: "2026-11-05T12:30:05+03:00" } } });
  const k = bul("short-20261104-2100");
  Object.assign(k, { publish_at: "2026-11-05T10:18:00+00:00", schedule: { ...k.schedule, youtube: "2026-11-05T10:18:00+00:00" } });
  bul(ACLIK).schedule.tiktok = "2026-11-05T19:02:00+00:00";
  writeFileSync(join(kok, "videos.json"), JSON.stringify(vs, null, 1));
  return kok;
}

// çipin ortası (ekrana getirilmiş)
async function cipKutusu(page, sec) {
  await page.evaluate((s) => document.querySelector(s).scrollIntoView({ block: "center" }), sec);
  await page.waitForTimeout(250);
  const b = await page.locator(sec).boundingBox();
  return { x: b.x + b.width / 2, y: b.y + Math.min(14, b.height / 2) };
}

// dokunmatik: 650 ms basılı tut (uzun basış 500 ms), sonra adım adım taşı (CDP dokunma olayları → pointer olayları)
const nokta = (x, y) => [{ x: Math.round(x), y: Math.round(y), id: 1, radiusX: 4, radiusY: 4, force: 1 }];
async function dokunSurukle(page, cdp, a, b, araEkran) {
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: nokta(a.x, a.y) });
  await page.waitForTimeout(650);
  const adim = 12;
  for (let i = 1; i <= adim; i++) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: nokta(a.x + (b.x - a.x) * i / adim, a.y + (b.y - a.y) * i / adim) });
    await page.waitForTimeout(30);
  }
  await page.waitForTimeout(120);
  if (araEkran) await araEkran();
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}
// dokunmatik: ms kadar basılı tut, sonra (varsa) dy kadar 10 adımda kaydır ve bırak; araEkran bırakmadan önce
async function dokunTut(page, cdp, a, ms, dy = 0, araEkran) {
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: nokta(a.x, a.y) });
  await page.waitForTimeout(ms);
  for (let i = 1; dy && i <= 10; i++) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: nokta(a.x, a.y + dy * i / 10) });
    await page.waitForTimeout(20);
  }
  if (araEkran) await araEkran();
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await page.waitForTimeout(250);
}
// iki rengin kontrast oranı ("rgb(r, g, b)")
function kontrast(a, b) {
  const L = (c) => {
    const [r, g, bl] = c.match(/\d+(\.\d+)?/g).slice(0, 3).map((x) => Number(x) / 255)
      .map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [x, y] = [L(a), L(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
}
const dialogKapat = async (page) => {
  await page.keyboard.press("Escape");
  await page.waitForSelector("dialog[open]", { state: "detached" }).catch(() => {});
  await page.waitForFunction(() => !document.querySelector("dialog[open]"));
};
async function fareSurukle(page, a, b, araEkran) {
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(a.x, a.y + 8, { steps: 2 });
  await page.mouse.move(b.x, b.y, { steps: 12 });
  await page.waitForTimeout(120);
  if (araEkran) await araEkran();
  await page.mouse.up();
}

async function takvimEkranlari(browser, port, kayit, hatalar) {
  const sunucu = await sunucuBaslat(takvimDurumu(), port, TAKVIM_SAAT);
  const URL = `http://127.0.0.1:${port}`;
  const ekran = async (page, ad, ek = {}) => {
    const dosya = join(OUT, ad + ".png");
    await page.screenshot({ animations: "disabled", path: dosya, ...ek });
    kayit.push(dosya);
  };
  try {
    let onaySirasi = 0;
    for (const tema of ["light", "dark"]) {
      for (const [ad, viewport, dsf] of GORUNUMLER) {
        const mobil = ad === "mobil";
        const ek = `${ad}_${tema === "light" ? "acik" : "koyu"}`;
        const ctx = await browser.newContext({ viewport, deviceScaleFactor: dsf, colorScheme: tema, locale: "tr-TR",
          timezoneId: "Europe/Istanbul", hasTouch: mobil, isMobile: mobil });
        await yaziTipleri(ctx);
        const page = await ctx.newPage();
        const sorun = (m) => hatalar.push(`takvim ${ek}: ${m}`);
        page.on("pageerror", (e) => sorun(e.message));
        page.on("console", (m) => { if (m.type() === "error") sorun("console: " + m.text()); });
        await page.goto(URL + "/__giris");
        await bekle(page);
        await page.goto(`${URL}/panel#takvim`);
        await bekle(page);
        await page.waitForSelector(".tk-govde .tk-cip");
        const genislik = await page.evaluate(() => document.documentElement.scrollWidth);
        if (genislik > viewport.width) sorun(`yatay kaydırma (${genislik}px)`);
        // beklenen içerik: prime bantları, paylaşılmış (kilitli ✅) ve yakında paylaşılan (🔒) çipler, onay tepsisi
        const icerik = await page.evaluate(() => ({
          prime: document.querySelectorAll(".tk-prime").length,
          paylasildi: document.querySelectorAll(".tk-cip.paylasildi").length,
          kilitli: document.querySelectorAll(".tk-cip.kilitli:not(.paylasildi)").length,
          tepsi: document.querySelectorAll(".tk-tepsi-satir").length,
          lejant: (document.querySelector(".tk-lejant") || {}).textContent || "",
        }));
        if (icerik.prime < 6 || !icerik.paylasildi || icerik.kilitli < 3 || icerik.tepsi !== 2 || !icerik.lejant.includes("⭐ En iyi saat (prime time)")) {
          sorun("eksik takvim içeriği " + JSON.stringify(icerik));
        }
        await ekran(page, `takvim_dolu_${ek}`, { fullPage: true });
        await page.evaluate(() => window.scrollTo(0, 0));
        await ekran(page, `takvim_ust_${ek}`);
        // masaüstünde 14 günün hepsi görünür; "Şimdi" etiketi her temada okunur (en az 4.5:1)
        const ust = await page.evaluate(() => {
          const s = document.querySelector(".tk-gunler"), r = s.getBoundingClientRect();
          const disarda = [...s.querySelectorAll(".tk-gun")].filter((g) => g.getBoundingClientRect().right > r.right + 0.5).length;
          const e = document.querySelector(".tk-simdi span"), st = e && getComputedStyle(e);
          return { disarda, renk: st && st.color, zemin: st && st.backgroundColor };
        });
        if (!mobil && ust.disarda) sorun(`gün şeridinde ${ust.disarda} gün görünmüyor`);
        if (!ust.renk || kontrast(ust.renk, ust.zemin) < 4.5) sorun("Şimdi etiketi kontrastı düşük: " + JSON.stringify(ust));

        // dokun: Saat seç sayfası (YouTube açık), +15 dk, takvime uygula → kaydedilmemiş değişiklik çubuğu
        const yt = `[data-cip="${GTA}:youtube"]`;
        await page.evaluate((s) => document.querySelector(s).scrollIntoView({ block: "center" }), yt);
        await page.click(yt);
        await page.waitForSelector("dialog[open] .tk-secici");
        await page.waitForTimeout(200);
        await ekran(page, `takvim_saat_sec_${ek}`);
        await page.click('dialog[open] [data-odak="youtube-ileri"]');
        const baslik = await page.textContent('dialog[open] [data-odak="youtube-bas"]');
        if (!baslik.includes("18:15") || !baslik.includes("değişti")) sorun("+15 dk uygulanmadı: " + baslik);
        await page.click("dialog[open] >> text=Takvime uygula");
        await page.waitForSelector(".tk-kayit");
        await page.waitForTimeout(200);
        const cubuk = await page.textContent(".tk-kayit");
        if (!cubuk.includes("Kaydedilmemiş değişiklik") || !/YouTube .*18:00 → .*18:15/.test(cubuk)) sorun("kayıt çubuğu: " + cubuk);
        await ekran(page, `takvim_kaydedilmemis_${ek}`);
        await page.click(".tk-kayit >> text=Vazgeç");
        await page.waitForSelector(".tk-kayit", { state: "detached" });

        // basılı tutup sürükle: TikTok 19:30 → 21:00 (90 dk aşağı, 1 dk = 1 px)
        const tt = `[data-cip="${GTA}:tiktok"]`;
        const a = await cipKutusu(page, tt);
        const b = { x: a.x, y: a.y + 90 };
        const araEkran = async () => {
          const etiket = await page.textContent(".tk-surukle-etiket").catch(() => "");
          if (!etiket.startsWith("21:00")) sorun("sürükleme etiketi: " + etiket);
          await ekran(page, `takvim_surukle_${ek}`);
        };
        if (mobil) await dokunSurukle(page, await ctx.newCDPSession(page), a, b, araEkran);
        else await fareSurukle(page, a, b, araEkran);
        await page.waitForSelector(".tk-kayit");
        const sonra = await page.evaluate((s) => ({ saat: document.querySelector(s + " time").textContent,
          kirli: document.querySelector(s).classList.contains("kirli"), cubuk: document.querySelector(".tk-kayit").textContent }), tt);
        if (sonra.saat !== "21:00" || !sonra.kirli || !/TikTok .*19:30 → .*21:00/.test(sonra.cubuk)) sorun("sürükleme taslağa yazılmadı: " + JSON.stringify(sonra));
        // bildirim yapışık gün şeridini (bırakma hedefi) ve kayıt çubuğunu örtmez
        const ortu = await page.evaluate(() => {
          const kesisir = (a, b) => a.bottom > b.top && a.top < b.bottom && a.right > b.left && a.left < b.right;
          const b = [...document.querySelectorAll(".bildirim")].map((e) => e.getBoundingClientRect());
          const g = document.querySelector(".tk-gunler").getBoundingClientRect(), k = document.querySelector(".tk-kayit").getBoundingClientRect();
          return { bildirim: b.length, serit: b.filter((r) => kesisir(r, g)).length, kayit: b.filter((r) => kesisir(r, k)).length };
        });
        if (!ortu.bildirim || ortu.serit || ortu.kayit) sorun("bildirim yeri: " + JSON.stringify(ortu));
        // gün şeridine bırak: YouTube 18:00 → yarın 18:00
        const yarin = await page.locator('.tk-gun[data-gun="1"]').boundingBox();
        const y0 = await cipKutusu(page, yt);
        const hedef = { x: yarin.x + yarin.width / 2, y: yarin.y + yarin.height / 2 };
        if (mobil) await dokunSurukle(page, await ctx.newCDPSession(page), y0, hedef);
        else await fareSurukle(page, y0, hedef);
        await page.waitForTimeout(200);
        const gun = await page.evaluate(() => ({ secili: document.querySelector('.tk-gun[aria-pressed="true"]').dataset.gun,
          cubuk: document.querySelector(".tk-kayit").textContent }));
        if (gun.secili !== "1" || !/YouTube .*18:00 → 6 Kas.* 18:00/.test(gun.cubuk)) sorun("güne bırakma: " + JSON.stringify(gun));
        // yarın YouTube 18:00'de iki video yan yana: dar çiplerde saat kesilmeden okunur
        const dar = await page.evaluate(() => [...document.querySelectorAll(".tk-cip.dar")].map((c) => {
          const t = c.querySelector("time").getBoundingClientRect(), r = c.getBoundingClientRect();
          return { cip: c.dataset.cip, gen: Math.round(r.width), saat: c.querySelector("time").textContent, tasma: Math.round(t.right - r.right) };
        }));
        if (dar.length < 2 || dar.some((d) => d.saat !== "18:00" || d.tasma > -1)) sorun("dar çipler: " + JSON.stringify(dar));
        await page.evaluate(() => window.scrollTo(0, 0));
        await ekran(page, `takvim_iki_degisiklik_${ek}`, { fullPage: true });
        await page.click(".tk-kayit >> text=Vazgeç");
        await page.waitForSelector(".tk-kayit", { state: "detached" });

        // basılı tutup kıpırdatmadan bırakmak dokunmadır: Saat seç açılır, 22:02 5 dk'ya yuvarlanmaz, değişiklik olmaz
        await page.click('.tk-gun[data-gun="0"]');
        await page.waitForTimeout(400);
        const tek = `[data-cip="${ACLIK}:tiktok"]`;
        const t0 = await cipKutusu(page, tek);
        let tutEtiket = "";
        const etiketOku = async () => { tutEtiket = await page.textContent(".tk-surukle-etiket").catch(() => ""); };
        if (mobil) await dokunTut(page, await ctx.newCDPSession(page), t0, 650, 0, etiketOku);
        else {
          await page.mouse.move(t0.x, t0.y);
          await page.mouse.down();
          await page.mouse.move(t0.x, t0.y + 6, { steps: 2 }); // sürükleme başlar (5 px) ama kıpırdama sayılmaz (8 px)
          await page.waitForTimeout(100);
          await etiketOku();
          await page.mouse.up();
        }
        await page.waitForSelector("dialog[open] .tk-pf", { timeout: 3000 }).catch(() => {});
        const tut = await page.evaluate((s) => ({ dlg: !!document.querySelector("dialog[open] .tk-pf"),
          kayit: !!document.querySelector(".tk-kayit"), saat: document.querySelector(s + " time").textContent }), tek);
        if (!tutEtiket.startsWith("22:02") || !tut.dlg || tut.kayit || tut.saat !== "22:02") sorun("basılı tutup bırakma: " + JSON.stringify({ tutEtiket, ...tut }));
        if (tut.dlg) await dialogKapat(page);
        if (mobil) {
          const cdp = await ctx.newCDPSession(page);
          // okurken dinlenen parmak (350 ms) sonra kaydırırsa çip taşınmaz
          const k0 = await cipKutusu(page, tek);
          await dokunTut(page, cdp, k0, 350, -200);
          const kaydir = await page.evaluate(() => ({ kayit: !!document.querySelector(".tk-kayit"), dlg: !!document.querySelector("dialog[open]") }));
          if (kaydir.kayit || kaydir.dlg) sorun("dinlenip kaydırma çipi taşıdı: " + JSON.stringify(kaydir));
          // yavaş dokunma (380 ms): Saat seç açılır
          const k1 = await cipKutusu(page, tek);
          await dokunTut(page, cdp, k1, 380);
          await page.waitForSelector("dialog[open] .tk-pf", { timeout: 3000 }).catch(() => {});
          if (!(await page.$("dialog[open] .tk-pf"))) sorun("yavaş dokunma Saat seç'i açmadı");
          else await dialogKapat(page);
        }

        // derin bağlantı: onay bekleyen video için "Takvime yerleştir" (önerilen boş prime saatler); iki görünüm onaylar
        const tag = ONAY[onaySirasi % 2];
        await page.goto(`${URL}/panel#takvim/${tag}`);
        await bekle(page);
        await page.waitForSelector("dialog[open] .tk-pf");
        const saatler = () => page.evaluate(() => Object.fromEntries(["youtube", "instagram", "tiktok"].map((p) =>
          [p, ((document.querySelector(`dialog[open] [data-odak="${p}-bas"] div`) || {}).textContent || "")])));
        const ilkOneri = await saatler();
        const yerlestir = await page.textContent("dialog[open]");
        if (!yerlestir.includes("Takvime yerleştir") || (yerlestir.match(/⭐/g) || []).length < 3) sorun("takvime yerleştir sayfası: " + yerlestir.slice(0, 200));
        await ekran(page, `takvim_yerlestir_${ek}`);
        if ((ad === "mobil" && tema === "light") || (ad === "masaustu" && tema === "dark")) {
          onaySirasi++;
          await page.click("dialog[open] >> text=Onayla ve zamanla");
          await page.waitForSelector(".bildirim");
          const giden = await (await fetch(`${URL}/__cagrilar`)).json();
          const g = giden.filter((c) => /isle\.yml\/dispatches$/.test(c.url)).map((c) => JSON.parse(c.govde.inputs.update).panel)
            .filter((p) => p && p.action === "schedule" && p.tag === tag);
          if (g.length !== 1 || Object.keys(g[0].schedule).sort().join() !== "instagram,tiktok,youtube") sorun("takvim onayı gönderilmedi: " + JSON.stringify(g));
          await page.waitForTimeout(300);
          await ekran(page, `takvim_onay_isleniyor_${ek}`);
          // sıradaki onay: işlenen onayın saatleri dolu sayılır (takvimde "kaydediliyor"), aynı boş saat önerilmez
          await page.click('.tk-gun[data-gun="1"]');
          await page.waitForTimeout(300);
          const isl = await page.$$eval(`.tk-cip.isleniyor[data-cip^="${tag}:"]`, (l) => l.length);
          await page.click(".tk-tepsi-satir button:not([disabled])");
          await page.waitForSelector("dialog[open] .tk-pf");
          await page.waitForTimeout(200);
          const ikinci = await saatler();
          const ayni = Object.keys(ikinci).filter((p) => ikinci[p] && ikinci[p] === ilkOneri[p]);
          if (isl !== 3 || ayni.length) sorun("art arda onay: " + JSON.stringify({ isl, ilkOneri, ikinci }));
          await ekran(page, `takvim_ikinci_oneri_${ek}`);
          await page.click("dialog[open] >> text=Vazgeç");
        } else {
          await page.click("dialog[open] >> text=Vazgeç");
        }
        await ctx.close();
      }
    }
  } finally {
    sunucu.kill();
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
