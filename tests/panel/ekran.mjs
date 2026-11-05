// Panel ekran görüntüleri (Playwright + Chromium): 390x844 ve 1280x900, açık ve koyu tema, her sekme.
//   OUT=<klasör> [FONTS=<Google Fonts önbelleği>] [VIDEO=<örnek video>] node tests/panel/ekran.mjs
// Sunucu (sunucu.mjs) ayrı süreçte sabit saatle çalışır; yazı tipleri yerelden verilir, dış ağa çıkılmaz.
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, existsSync, mkdtempSync, cpSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createRequire } from "node:module";
import { BURASI, FIKSTUR } from "./sahte.mjs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT || "/opt/node22/lib/node_modules/playwright");
const OUT = process.env.OUT || join(BURASI, "ekran");
const FONTS = process.env.FONTS;
const SAAT = process.env.SAAT || "2026-11-05T00:45:00+03:00";
mkdirSync(OUT, { recursive: true });

// örnek duruma ek: bir sorunlu (kısmen paylaşılmış) video, Sorunlu bölümü de görünsün
function durumHazirla(sorunlu) {
  const kok = mkdtempSync(join(tmpdir(), "panel_ekran_"));
  cpSync(FIKSTUR, kok, { recursive: true });
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

async function sunucuBaslat(kok, port) {
  const p = spawn(process.execPath, [join(BURASI, "sunucu.mjs")], {
    env: { ...process.env, KOK: kok, PORT: String(port), SAAT, VIDEO: process.env.VIDEO || "" }, stdio: ["ignore", "pipe", "inherit"] });
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
  const port = 8790;
  const sunucu = await sunucuBaslat(durumHazirla(false), port);
  const URL = `http://127.0.0.1:${port}`;
  const hatalar = [];
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
          await page.click(".kart .btn-ana");
          await page.waitForSelector("dialog[open] .secenek");
          await page.screenshot({ animations: "disabled", path: join(OUT, `onay_secenekleri_${ek}.png`) }); kayit.push(join(OUT, `onay_secenekleri_${ek}.png`));
          await page.click(`dialog[open] .secenek >> nth=${ad === "mobil" ? 0 : 1}`); // farklı işlem: kapının tekrar engeline takılmasın
          await page.waitForSelector(".bildirim");
          await page.waitForSelector('.kart [aria-busy="true"]');
          await page.screenshot({ animations: "disabled", path: join(OUT, `islem_suruyor_${ek}.png`) }); kayit.push(join(OUT, `islem_suruyor_${ek}.png`));
          await page.goto(`${URL}/panel#videolar`);
          await bekle(page);
          await page.click(".kart >> nth=1 >> text=Düzenle");
          await page.waitForSelector("dialog[open] #f-baslik");
          await page.screenshot({ animations: "disabled", path: join(OUT, `duzenle_${ek}.png`) }); kayit.push(join(OUT, `duzenle_${ek}.png`));
          await page.keyboard.press("Escape");
          await page.click(".kart >> nth=1 >> text=Reddet");
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
  await browser.close();
  console.log(kayit.join("\n"));
  if (hatalar.length) { console.error("SORUNLAR:\n" + hatalar.join("\n")); process.exitCode = 1; }
}

main().catch((e) => { console.error(e); process.exit(1); });
