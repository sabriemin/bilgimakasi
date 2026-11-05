// Bilgi Makası paneli: sayfa (HTML + CSS) ve tarayıcıda çalışan uygulama.
// uygulama() fonksiyonu sunucuda ÇALIŞMAZ: metne çevrilip /panel/app.js olarak tarayıcıya gönderilir
// (bu yüzden dışarıdaki hiçbir değişkene erişmemeli). Sayfada gizli değer, anahtar veya sohbet numarası yoktur.

const YAZI_TIPLERI = "https://fonts.googleapis.com/css2?family=Anton&family=Courier+Prime:wght@400;700" +
  "&family=DM+Mono:wght@400;500&display=swap";

const MAKAS_SVG = `<svg class="makas" viewBox="0 0 48 48" aria-hidden="true">
  <path d="M19.5 30.5 L35.5 3.5 L38.6 5.4 L24.2 32.6Z" fill="currentColor"/>
  <path d="M24.5 33.8 L44.6 13.6 L46.6 16.6 L28.4 36.4Z" fill="currentColor"/>
  <circle cx="13" cy="36" r="7" fill="none" stroke="#DD2027" stroke-width="4"/>
  <circle cx="27.5" cy="40" r="5.6" fill="none" stroke="#DD2027" stroke-width="4"/>
  <circle cx="25.6" cy="27.4" r="2.7" fill="#FCD521" stroke="currentColor" stroke-width="1.2"/>
</svg>`;

const CSS = `
:root{
  --red:#DD2027;--yellow:#FCD521;--ink:#141313;--paper:#E9E7E2;--off:#FAF9F5;
  --bg:var(--paper);--surface:var(--off);--surface-2:#F2F0EA;--text:var(--ink);--muted:#5d5850;
  --line:#d9d5cc;--line-strong:#b9b4a9;--ok:#1d7a4a;--ok-bg:#e3f1e8;--err:#c4161d;--err-bg:#fbe4e3;
  --plan-bg:#fff4bf;--label-bg:var(--ink);--label-text:var(--off);--btn-dark:var(--ink);--btn-dark-text:var(--off);
  --shadow:0 1px 0 rgba(20,19,19,.05),0 10px 24px -16px rgba(20,19,19,.35);
  --display:"Anton","Oswald","Arial Narrow",Impact,sans-serif;
  --mono:"DM Mono","Courier Prime",ui-monospace,Menlo,Consolas,monospace;
  --type:"Courier Prime","DM Mono",ui-monospace,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --radius:14px;--nav-h:64px;color-scheme:light;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#141313;--surface:#1f1d1c;--surface-2:#292624;--text:#F1EFEA;--muted:#aca69c;
  --line:#35312f;--line-strong:#504b47;--ok:#5fc791;--ok-bg:#183326;--err:#ff6266;--err-bg:#3a1617;
  --plan-bg:#3a3214;--label-bg:#F1EFEA;--label-text:#141313;--btn-dark:#F1EFEA;--btn-dark-text:#141313;
  --shadow:0 1px 0 rgba(0,0,0,.4),0 12px 28px -18px rgba(0,0,0,.9);color-scheme:dark;
}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;text-size-adjust:100%;scroll-padding:84px 0 calc(var(--nav-h) + env(safe-area-inset-bottom) + 12px)}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.45 var(--sans);overflow-x:hidden;
  padding-bottom:calc(var(--nav-h) + env(safe-area-inset-bottom) + 24px);-webkit-tap-highlight-color:transparent}
button,input,textarea{font:inherit;color:inherit}
a{color:inherit}
/* :root ile bileşenlerin kendi box-shadow kenarlığını (ör. .btn-cizgi) da geçer */
:root :focus-visible{outline:3px solid var(--ink);outline-offset:2px;box-shadow:0 0 0 6px var(--yellow)}
@media (prefers-color-scheme:dark){:root :focus-visible{outline-color:var(--yellow);box-shadow:none}}
[hidden]{display:none!important}
.yirtik{clip-path:polygon(0 7%,7% 0,15% 6%,24% 1%,34% 7%,45% 0,56% 6%,67% 1%,78% 7%,89% 0,100% 6%,99% 50%,100% 93%,
  92% 100%,82% 94%,71% 100%,59% 95%,47% 100%,35% 94%,23% 100%,12% 95%,0 100%,1% 52%)}
/* üst çubuk */
.ust{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--line)}
.ust-ic{max-width:1120px;margin:0 auto;padding:10px 16px;display:flex;align-items:center;gap:12px;min-height:60px}
.marka{display:flex;align-items:center;gap:6px;text-decoration:none;color:var(--text);flex:none}
.makas{width:34px;height:34px;color:var(--text);flex:none}
.marka-yazi{display:flex;flex-direction:column;gap:2px;line-height:1}
.marka-yazi b{font:400 15px/1 var(--display);letter-spacing:.03em;padding:4px 7px 3px;display:inline-block;width:max-content}
.marka-yazi .b1{background:var(--label-bg);color:var(--label-text)}
.marka-yazi .b2{background:var(--red);color:#fff;margin-left:8px}
.ust-bilgi{margin-left:auto;display:flex;align-items:center;gap:6px;min-width:0}
.guncel{font:12px/1.2 var(--mono);color:var(--muted);text-align:right;white-space:nowrap}
.ikon-btn{width:44px;height:44px;border-radius:12px;border:1px solid var(--line);background:var(--surface);
  display:grid;place-items:center;cursor:pointer;flex:none}
.ikon-btn svg{width:20px;height:20px}
.ikon-btn:active{transform:scale(.96)}
.donuyor svg{animation:don 1s linear infinite}
@keyframes don{to{transform:rotate(360deg)}}
/* sekmeler */
.sekmeler{position:fixed;left:0;right:0;bottom:0;z-index:30;background:var(--surface);border-top:1px solid var(--line);
  display:grid;grid-template-columns:repeat(4,1fr);padding-bottom:env(safe-area-inset-bottom)}
.sekme{height:var(--nav-h);border:0;background:none;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:3px;cursor:pointer;color:var(--muted);font:500 11.5px/1 var(--mono);position:relative;padding:0}
.sekme svg{width:24px;height:24px}
.sekme[aria-current=page]{color:var(--text)}
.sekme[aria-current=page]::before{content:"";position:absolute;top:0;left:22%;right:22%;height:3px;background:var(--red);
  border-radius:0 0 3px 3px}
.sekme .rozet{position:absolute;top:8px;left:calc(50% + 6px);min-width:18px;height:18px;border-radius:9px;
  background:var(--red);color:#fff;font:500 11px/18px var(--mono);padding:0 5px}
@media (min-width:860px){
  body{padding-bottom:40px}
  .sekmeler{position:static;display:flex;gap:4px;background:none;border:0;padding:0;margin-left:24px}
  .sekme{height:44px;flex-direction:row;gap:8px;padding:0 14px;border-radius:10px;font-size:13px}
  .sekme svg{width:20px;height:20px}
  .sekme[aria-current=page]{background:var(--surface);box-shadow:inset 0 0 0 1px var(--line)}
  .sekme[aria-current=page]::before{left:14px;right:14px;top:auto;bottom:-1px;border-radius:3px 3px 0 0}
  .sekme .rozet{position:static;margin-left:-2px}
}
main{max-width:1120px;margin:0 auto;padding:16px}
/* bölüm başlıkları */
.bolum{margin:24px 0 10px;display:flex;align-items:center;flex-wrap:wrap;gap:8px 10px;scroll-margin-top:76px}
.bolum:first-child{margin-top:4px}
.bolum h2{margin:0;font:400 21px/1 var(--display);letter-spacing:.02em;text-transform:uppercase;white-space:nowrap;
  background:var(--label-bg);color:var(--label-text);padding:7px 12px 6px}
.bolum .sayi{font:500 13px/1 var(--mono);background:var(--yellow);color:var(--ink);border-radius:999px;
  min-width:28px;height:28px;display:grid;place-items:center;padding:0 8px}
.bolum .not{font:13px/1.3 var(--mono);color:var(--muted);margin-left:auto;text-align:right}
@media (max-width:559px){.bolum .not{flex-basis:100%;margin-left:0;text-align:left;order:3}}
.bos{font:14px/1.4 var(--mono);color:var(--muted);padding:14px 16px;border:1.5px dashed var(--line-strong);border-radius:var(--radius)}
.ozet{display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 6px}
.ozet a{display:inline-flex;align-items:center;gap:8px;text-decoration:none;background:var(--surface);
  border:1px solid var(--line);border-radius:999px;padding:0 14px 0 12px;min-height:44px;font:500 13px/1 var(--mono)}
.ozet a b{font:400 18px/1 var(--display)}
.ozet a.dikkat{border-color:var(--red);box-shadow:inset 0 0 0 1px var(--red)}
.ozet a .nokta{width:9px;height:9px;border-radius:50%;background:var(--muted)}
/* kartlar */
.izgara{display:grid;grid-template-columns:1fr;gap:12px}
@media (min-width:760px){.izgara{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (min-width:1100px){.izgara.uclu{grid-template-columns:repeat(3,minmax(0,1fr))}}
.kart{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);
  padding:12px;display:flex;flex-direction:column;gap:12px;min-width:0}
.kart-ust{display:flex;gap:12px;align-items:flex-start;min-width:0}
.oynatici{position:relative;width:104px;flex:none;aspect-ratio:9/16;border-radius:10px;overflow:hidden;background:#141313}
.oynatici video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#141313}
.oynat{position:absolute;inset:0;border:0;cursor:pointer;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:8px;color:#FAF9F5;background:radial-gradient(120% 80% at 50% 30%,#2b2827 0,#141313 70%);
  font:500 11px/1 var(--mono);letter-spacing:.08em}
.oynat .daire{width:46px;height:46px;border-radius:50%;background:var(--red);display:grid;place-items:center;
  box-shadow:0 0 0 4px rgba(221,32,39,.25)}
.oynat .daire svg{width:20px;height:20px;margin-left:3px}
.oynat-yazi{position:absolute;left:0;right:0;bottom:12px;text-align:center;opacity:.8}
.kucult{position:absolute;top:8px;right:8px;z-index:2;width:40px;height:40px;border-radius:50%;border:0;
  background:rgba(20,19,19,.7);color:#fff;display:none;place-items:center;cursor:pointer}
.kucult svg{width:18px;height:18px}
.video-hata{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:8px;padding:10px;text-align:center;color:#FAF9F5;background:#141313;font:12px/1.35 var(--mono)}
.video-hata button{border:1px solid #FAF9F5;background:none;color:#FAF9F5;border-radius:8px;min-height:44px;padding:0 12px;cursor:pointer}
.kart.acik .kart-ust{flex-direction:column}
.kart.acik .oynatici{width:min(100%,420px,calc(72vh * 9 / 16));width:min(100%,420px,calc((100dvh - 160px) * 9 / 16));aspect-ratio:9/16;align-self:center;scroll-margin:84px 0 calc(var(--nav-h) + 16px)}
@media (min-width:860px){.kart.acik .oynatici{scroll-margin-bottom:16px}}
.kart.acik .oynat{display:none}
.kart.acik .kucult{display:grid}
.kart-bilgi{min-width:0;flex:1;display:flex;flex-direction:column;gap:6px}
.ust-satir{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px}
.tarih{font:12.5px/1.2 var(--mono);color:var(--muted)}
.tarih .ad{color:var(--text);font-weight:500}
.pil{font:500 11.5px/1 var(--mono);border-radius:999px;padding:5px 9px;white-space:nowrap;display:inline-flex;align-items:center;gap:5px}
.pil.onay{background:var(--yellow);color:var(--ink)}
.pil.plan{background:var(--btn-dark);color:var(--btn-dark-text)}
.pil.ok{background:var(--ok-bg);color:var(--ok)}
.pil.hata{background:var(--red);color:#fff}
.pil.notr{background:var(--surface-2);color:var(--muted);box-shadow:inset 0 0 0 1px var(--line)}
.pil.surec::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;animation:nabiz 1.2s ease-in-out infinite}
@keyframes nabiz{50%{opacity:.25}}
.pil.duz{background:none;box-shadow:inset 0 0 0 1px var(--line-strong);color:var(--muted)}
.baslik{margin:0;font:700 17px/1.28 var(--sans);letter-spacing:-.005em;overflow-wrap:anywhere}
.konu{margin:0;font:13.5px/1.42 var(--type);color:var(--muted);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.kart.acik .konu{-webkit-line-clamp:unset}
.pf-liste{list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}
.pf{display:flex;gap:10px;padding:10px 0;border-bottom:1px solid var(--line);align-items:flex-start}
.pf:last-child{border-bottom:0;padding-bottom:0}
.pf-ikon{width:32px;height:32px;border-radius:9px;display:grid;place-items:center;flex:none;background:var(--surface-2);color:var(--text)}
.pf-ikon svg{width:18px;height:18px}
.pf-govde{min-width:0;flex:1;display:flex;flex-direction:column;gap:3px}
.pf-ust{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.pf-ust b{font:600 14.5px/1.2 var(--sans)}
.pf-durum{font:500 12px/1 var(--mono);display:inline-flex;align-items:center;gap:4px}
.pf-durum svg{width:14px;height:14px}
.pf-durum.ok{color:var(--ok)}.pf-durum.hata{color:var(--err)}.pf-durum.plan{color:var(--text)}
.pf-durum.pasif{color:var(--muted)}.pf-durum.surec{color:var(--text)}
.pf-alt{font:12.5px/1.45 var(--mono);color:var(--muted);display:flex;flex-wrap:wrap;gap:2px 12px}
.pf-sayi{color:var(--text)}
.pf-alt a{color:var(--text);font-weight:500;text-underline-offset:3px;display:inline-flex;align-items:center;gap:3px;
  min-height:44px;padding:0 10px;margin:-10px -10px -10px -10px}
.pf-alt a svg{width:13px;height:13px}
.pf-hata{font:12.5px/1.4 var(--mono);color:var(--err);background:var(--err-bg);border-radius:8px;padding:6px 8px;overflow-wrap:anywhere}
.pf-not{font:12px/1.4 var(--mono);color:var(--muted);overflow-wrap:anywhere}
.mini-btn{border:1px solid var(--line-strong);background:none;border-radius:8px;min-height:44px;padding:0 12px;
  font:500 12px/1 var(--mono);cursor:pointer;color:var(--text)}
.dugmeler{display:flex;flex-wrap:wrap;gap:8px}
.btn{min-height:48px;border-radius:11px;border:0;cursor:pointer;padding:0 16px;display:inline-flex;align-items:center;
  justify-content:center;gap:8px;font:400 16.5px/1 var(--display);letter-spacing:.04em;text-transform:uppercase;
  text-decoration:none;flex:1 1 auto;white-space:nowrap;transition:transform .08s,filter .15s}
.btn svg{width:18px;height:18px;flex:none}
.btn:active{transform:translateY(1px) scale(.99)}
.btn-ana{background:var(--red);color:#fff}
.btn-koyu{background:var(--btn-dark);color:var(--btn-dark-text)}
.btn-cizgi{background:none;color:var(--text);box-shadow:inset 0 0 0 2px var(--line-strong)}
.btn-sari{background:var(--yellow);color:var(--ink)}
.btn[disabled]{cursor:not-allowed;opacity:.55}
.btn[aria-busy=true]{opacity:1;cursor:progress;filter:saturate(.6)}
.btn-kucuk{min-height:44px;font-size:14.5px;padding:0 12px;flex:0 0 auto}
.yukleniyor-ikon{width:16px;height:16px;border-radius:50%;border:2.5px solid currentColor;border-right-color:transparent;animation:don .8s linear infinite;flex:none}
.daha{margin-top:12px;width:100%}
details.diger{margin-top:22px}
details.diger summary{cursor:pointer;font:500 14px/1 var(--mono);color:var(--muted);padding:12px 0;list-style:none;display:flex;align-items:center;gap:8px}
details.diger summary::-webkit-details-marker{display:none}
details.diger summary::before{content:"+";font:400 18px/1 var(--display);width:24px;height:24px;display:grid;place-items:center;border-radius:6px;background:var(--surface-2)}
details.diger[open] summary::before{content:"–"}
.liste-satir{display:flex;gap:10px;align-items:baseline;padding:10px 0;border-bottom:1px solid var(--line);font-size:14px}
.liste-satir .tarih{flex:none}
/* takvim */
.gun{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px;box-shadow:var(--shadow)}
.gun+.gun{margin-top:10px}
.gun-bas{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.gun-bas h3{margin:0;font:400 20px/1.1 var(--display);letter-spacing:.02em;text-transform:uppercase}
.gun-bas .etiket{font:500 11.5px/1 var(--mono);background:var(--yellow);color:var(--ink);padding:5px 8px;border-radius:6px}
.gun-bas .say{margin-left:auto;font:12.5px/1 var(--mono);color:var(--muted)}
.gun.bosgun{padding:10px 14px;box-shadow:none;background:transparent;border-style:dashed}
.gun.bosgun h3{font-size:16px;color:var(--muted)}
.gun ol{list-style:none;margin:10px 0 0;padding:0}
.satir{display:grid;grid-template-columns:58px 1fr;gap:10px;padding:9px 0;border-top:1px solid var(--line);align-items:start}
.satir time{font:500 17px/1.25 var(--mono);letter-spacing:-.02em}
.satir .ne{min-width:0;display:flex;flex-direction:column;gap:2px}
.satir .pfad{display:inline-flex;align-items:center;gap:6px;font:500 12.5px/1.2 var(--mono);color:var(--muted)}
.satir .pfad svg{width:15px;height:15px;color:var(--text)}
.satir .vbaslik{font:600 14.5px/1.35 var(--sans);overflow-wrap:anywhere}
.satir .gecikti{color:var(--err)}
.saatler{margin-top:18px}
.saat-izgara{display:grid;grid-template-columns:1fr;gap:8px}
@media (min-width:640px){.saat-izgara{grid-template-columns:repeat(3,1fr)}}
.saat-kart{display:flex;gap:10px;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.saat-kart b{font:600 14px/1.2 var(--sans);display:block}
.saat-kart span{font:13px/1.35 var(--mono);color:var(--muted)}
/* istatistik */
.ozet-kart{margin-bottom:10px}
.ozet-ust{display:flex;align-items:center;gap:10px 12px;flex-wrap:wrap}
.ozet-ust small{display:block;font:12px/1.2 var(--mono);color:var(--muted)}
.ozet-ust b{font:600 15px/1.3 var(--sans)}
.ozet-ust .btn{margin-left:auto}
.toplamlar{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}
.toplamlar small{display:block;font:12px/1.2 var(--mono);color:var(--muted)}
.toplamlar strong{display:block;font:700 22px/1.2 var(--sans);font-size:clamp(16px,4.8vw,22px);letter-spacing:-.01em;white-space:nowrap}
.hesaplar{display:grid;grid-template-columns:1fr;gap:10px}
@media (min-width:760px){.hesaplar{grid-template-columns:repeat(3,1fr)}}
.hesap{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px;box-shadow:var(--shadow)}
.hesap-bas{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.hesap-bas b{font:400 20px/1 var(--display);letter-spacing:.03em}
.olcu{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.olcu div{min-width:0}
.olcu small{display:block;font:12px/1.2 var(--mono);color:var(--muted)}
.olcu strong{display:block;font:700 21px/1.2 var(--sans);font-size:clamp(16px,4.6vw,21px);letter-spacing:-.01em;white-space:nowrap}
.fark{font:500 12px/1.2 var(--mono);display:inline-flex;align-items:center;gap:2px;white-space:nowrap}
.fark.art{color:var(--ok)}.fark.az{color:var(--err)}.fark.yok{color:var(--muted)}
.hesap .pf-not{margin-top:8px}
.secici{display:inline-flex;background:var(--surface-2);border:1px solid var(--line);border-radius:12px;padding:3px;gap:2px;margin:20px 0 10px}
.secici button{border:0;background:none;min-height:44px;padding:0 14px;border-radius:9px;cursor:pointer;font:500 13px/1 var(--mono);color:var(--muted)}
.secici button[aria-pressed=true]{background:var(--surface);color:var(--text);box-shadow:0 1px 3px rgba(0,0,0,.12),inset 0 0 0 1px var(--line)}
.grafikler{display:grid;grid-template-columns:1fr;gap:10px}
@media (min-width:760px){.grafikler{grid-template-columns:repeat(3,1fr)}}
.grafik-kart{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px 12px 8px;min-width:0}
.grafik-kart h3{margin:0 0 2px;font:600 14px/1.2 var(--sans);display:flex;align-items:center;gap:8px}
.grafik-kart h3 svg{width:16px;height:16px}
.grafik-kart .alt{font:12px/1.2 var(--mono);color:var(--muted);margin-bottom:6px}
.grafik{position:relative;height:150px;touch-action:pan-y}
.grafik svg{display:block;width:100%;height:100%;overflow:visible}
.grafik text{font:11px var(--mono);fill:var(--muted);font-variant-numeric:tabular-nums}
.ipucu{position:absolute;pointer-events:none;background:var(--btn-dark);color:var(--btn-dark-text);border-radius:8px;
  padding:6px 8px;font:12px/1.3 var(--mono);white-space:nowrap;transform:translate(-50%,-100%);z-index:3}
.ipucu b{display:block;font:700 14px/1.2 var(--sans)}
.birikiyor{height:150px;display:grid;place-items:center;text-align:center;font:13px/1.4 var(--mono);color:var(--muted);
  border:1.5px dashed var(--line);border-radius:10px;padding:10px}
details.tablo summary{font:12px/1 var(--mono);color:var(--muted);cursor:pointer;min-height:44px;display:flex;align-items:center;gap:6px}
details.tablo summary::-webkit-details-marker{display:none}
details.tablo summary::before{content:"▸";font-size:13px}
details.tablo[open] summary::before{content:"▾"}
details.tablo table{width:100%;border-collapse:collapse;font:12px/1.4 var(--mono)}
details.tablo td{padding:3px 0;border-top:1px solid var(--line)}
details.tablo td:last-child{text-align:right;font-variant-numeric:tabular-nums}
.vtablo{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}
.vsatir{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px 8px;padding:10px 14px;border-top:1px solid var(--line)}
.vsatir:first-child{border-top:0}
.vsatir .vb{grid-column:1/-1;font:600 14px/1.35 var(--sans);overflow-wrap:anywhere;display:flex;gap:8px;align-items:baseline}
.vsatir .vb .sira{font:400 15px/1 var(--display);color:var(--red);flex:none;min-width:18px}
.vsatir .n{font:500 14px/1.2 var(--mono);font-variant-numeric:tabular-nums}
.vsatir .n small{display:block;font:11px/1.2 var(--mono);color:var(--muted);margin-bottom:2px}
.vsatir.bas{display:none}
@media (min-width:760px){
  .vsatir{grid-template-columns:minmax(0,1fr) repeat(4,96px);align-items:center}
  .vsatir .vb{grid-column:auto}
  .vsatir .n{text-align:right}
  .vsatir .n small{display:none}
  .vsatir.bas{display:grid;background:var(--surface-2);font:12px/1.2 var(--mono);color:var(--muted)}
  .vsatir.bas span:not(:first-child){text-align:right}
}
/* konular */
.kutu{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:14px;box-shadow:var(--shadow)}
.kutu p.aciklama{margin:0 0 12px;font:13.5px/1.45 var(--mono);color:var(--muted)}
.giris-satir{display:flex;gap:8px;flex-wrap:wrap}
.alan{flex:1 1 220px;min-width:0;min-height:48px;border-radius:11px;border:1.5px solid var(--line-strong);background:var(--bg);
  padding:10px 12px;font:16px/1.4 var(--sans)}
.alan:focus{outline:none;border-color:var(--text);box-shadow:0 0 0 3px rgba(252,213,33,.55)}
textarea.alan{min-height:180px;resize:vertical;width:100%;display:block}
.oneriler{display:flex;flex-direction:column;gap:10px}
.oneri{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px;display:flex;flex-direction:column;gap:8px;box-shadow:var(--shadow)}
.oneri-ust{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font:500 12px/1 var(--mono);color:var(--muted)}
.puan{background:var(--btn-dark);color:var(--btn-dark-text);border-radius:6px;padding:4px 7px}
.oneri h4{margin:0;font:600 15px/1.38 var(--sans);overflow-wrap:anywhere}
.oneri .kanca{margin:0;font:14px/1.4 var(--type);overflow-wrap:anywhere}
.oneri .gundem{margin:0;font:12.5px/1.4 var(--mono);color:var(--muted);overflow-wrap:anywhere}
.oneri .dugmeler .btn{flex:0 1 auto}
.kuyruk{list-style:none;margin:0 0 12px;padding:0;counter-reset:k}
.kuyruk li{display:grid;grid-template-columns:26px minmax(0,1fr);gap:6px 8px;align-items:start;padding:10px 0;border-bottom:1px solid var(--line)}
.kuyruk .ara{grid-column:2;justify-content:flex-end}
@media (min-width:560px){.kuyruk li{grid-template-columns:26px minmax(0,1fr) auto;align-items:center}.kuyruk .ara{grid-column:auto}}
.kuyruk li:first-child{padding-top:0}
.kuyruk .no{font:400 19px/1.2 var(--display);text-align:center;color:var(--muted)}
.kuyruk li:first-child .no{color:var(--red)}
.kuyruk .yazi{flex:1;min-width:0;font:14.5px/1.38 var(--sans);overflow-wrap:anywhere}
.kuyruk .ara{display:flex;gap:4px;flex:none}
.kuyruk .ikon-btn{width:44px;height:44px;border-radius:10px}
.kuyruk .ikon-btn[disabled]{opacity:.35;cursor:default}
.kaydet-cubuk{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:12px}
.kaydet-cubuk .durum{font:12.5px/1.3 var(--mono);color:var(--muted);flex:1 1 160px}
.kaydet-cubuk .durum.kirli{color:var(--err)}
.ikili{display:grid;grid-template-columns:1fr;gap:16px}
@media (min-width:960px){.ikili{grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);align-items:start}}
.ikili .bolum:first-child{margin-top:4px}
/* uyarı, bildirim, sayfa */
.serit{display:flex;gap:10px;align-items:center;border-radius:12px;padding:10px 12px;margin:0 0 12px;font:13.5px/1.4 var(--mono);flex-wrap:wrap}
.serit svg{width:20px;height:20px;flex:none}
.serit>span{flex:1 1 200px;min-width:0;overflow-wrap:anywhere}
.serit.hata{background:var(--err-bg);color:var(--err)}
.serit.bilgi{background:var(--plan-bg);color:var(--text)}
.serit .btn{flex:0 0 auto;margin-left:auto}
/* bildirimler: telefonda üst çubuğun hemen altında (alttaki Kaydet/Geri al düğmelerini örtmez), dokunmayı engellemez */
.bildirimler{position:fixed;left:0;right:0;top:calc(68px + env(safe-area-inset-top));z-index:60;
  display:flex;flex-direction:column;align-items:center;gap:8px;pointer-events:none;padding:0 16px}
@media (min-width:860px){.bildirimler{top:auto;bottom:24px}}
.bildirim{pointer-events:none;max-width:min(520px,100%);background:var(--btn-dark);color:var(--btn-dark-text);border-radius:12px;
  padding:12px 16px;font:14px/1.4 var(--sans);box-shadow:0 12px 30px -10px rgba(0,0,0,.5);animation:gel .2s ease-out}
.bildirim.hata{background:var(--red);color:#fff}
@keyframes gel{from{transform:translateY(8px);opacity:0}}
dialog{border:0;padding:0;background:var(--surface);color:var(--text);width:100%;max-width:100%;margin:auto auto 0;
  border-radius:20px 20px 0 0;max-height:90vh;max-height:90dvh;box-shadow:0 -10px 40px rgba(0,0,0,.3)}
dialog::backdrop{background:rgba(20,19,19,.55)}
dialog[open]{animation:yuksel .22s ease-out}
@keyframes yuksel{from{transform:translateY(24px);opacity:.4}}
@media (min-width:640px){dialog{max-width:520px;margin:auto;border-radius:18px}}
.sayfa-ic{padding:8px 16px calc(16px + env(safe-area-inset-bottom));display:flex;flex-direction:column;gap:12px}
.tutamac{width:44px;height:5px;border-radius:3px;background:var(--line-strong);margin:4px auto 0}
@media (min-width:640px){.tutamac{display:none}.sayfa-ic{padding-top:16px}}
.sayfa-bas{display:flex;align-items:flex-start;gap:10px}
.sayfa-bas h2{margin:4px 0 0;font:400 24px/1.05 var(--display);letter-spacing:.02em;text-transform:uppercase;flex:1}
.sayfa-alt{margin:-4px 0 0;font:13.5px/1.4 var(--mono);color:var(--muted);overflow-wrap:anywhere}
.secenekler{display:flex;flex-direction:column;gap:8px}
.secenek{display:flex;flex-direction:column;align-items:flex-start;gap:4px;text-align:left;min-height:60px;padding:11px 14px;
  border-radius:12px;border:1.5px solid var(--line-strong);background:var(--bg);cursor:pointer;width:100%}
.secenek b{font:600 16px/1.25 var(--sans)}
.secenek span{font:12.5px/1.35 var(--mono);color:var(--muted)}
.secenek:hover{border-color:var(--text)}
.secenek.vurgu{border-color:var(--red);box-shadow:inset 0 0 0 1px var(--red)}
.form-alan{display:flex;flex-direction:column;gap:6px}
.form-alan .alan{flex:none}
textarea.alan.tek{min-height:0;resize:none}
.form-alan label{display:flex;justify-content:space-between;gap:8px;font:500 13px/1.2 var(--mono)}
.form-alan label span{color:var(--muted);font-variant-numeric:tabular-nums}
.form-alan label span.asim{color:var(--err)}
.alan[aria-invalid=true]{border-color:var(--err)}
.alan-hata{margin:0;font:500 13px/1.4 var(--mono);color:var(--err)}
.kapat-onay{display:flex;flex-direction:column;gap:10px;border-radius:12px;padding:12px;background:var(--err-bg)}
.kapat-onay p{margin:0;font:600 15px/1.4 var(--sans);color:var(--text)}
.korunan{font:12.5px/1.45 var(--mono);color:var(--muted);background:var(--surface-2);border-radius:10px;padding:10px 12px;white-space:pre-wrap;overflow-wrap:anywhere}
.korunan b{display:block;color:var(--text);margin-bottom:4px;font-weight:500}
.sayfa-dugmeler{display:flex;gap:8px;flex-wrap:wrap}
.sayfa-dugmeler .btn{flex:1 1 140px}
.yuk{padding:40px 0;text-align:center;font:14px var(--mono);color:var(--muted)}
.giris{min-height:100vh;min-height:100dvh;display:grid;place-items:center;padding:24px 16px}
.giris-kart{max-width:420px;width:100%;background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:24px 20px;box-shadow:var(--shadow);text-align:center}
.giris-kart .marka{justify-content:center;margin-bottom:16px}
.giris-kart .makas{width:52px;height:52px}
.giris-kart .marka-yazi b{font-size:22px}
.giris-kart h1{font:400 28px/1.1 var(--display);text-transform:uppercase;letter-spacing:.02em;margin:0 0 10px}
.giris-kart p{font:14.5px/1.5 var(--type);margin:0 0 18px;color:var(--muted)}
.giris-kart p:last-child{margin-bottom:0}
.giris-kart code{font:700 15px var(--mono);color:var(--text);background:var(--yellow);color:var(--ink);padding:1px 6px;border-radius:5px}
.giris-kart .btn{width:100%}
.slogan{font:13px/1 var(--type);color:var(--muted);margin-top:14px}
.alt-bilgi{margin-top:32px;padding-top:14px;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px 12px;
  align-items:center;font:12.5px/1.45 var(--mono);color:var(--muted)}
.alt-bilgi span{flex:1 1 240px;min-width:0}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
`;

export const SAYFA_HTML = `<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#E9E7E2" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141313" media="(prefers-color-scheme: dark)">
<title>Bilgi Makası Paneli</title>
<link rel="icon" href="data:image/svg+xml,${encodeURIComponent(MAKAS_SVG.replace(/currentColor/g, "#141313"))}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="${YAZI_TIPLERI}">
<style>${CSS}</style>
</head>
<body>
<template id="makas">${MAKAS_SVG}</template>
<div id="uygulama"><div class="yuk">Yükleniyor…</div></div>
<div class="bildirimler" id="bildirimler" role="status" aria-live="polite"></div>
<dialog id="sayfa" aria-labelledby="sayfa-baslik"></dialog>
<script src="/panel/app.js" defer></script>
</body>
</html>`;

const GIRIS_HATALARI = {
  gecersiz: ["Bağlantı geçersiz", "Bu giriş bağlantısının süresi dolmuş ya da bağlantı bozuk. Telegram'da botu açıp " +
    "<code>/panel</code> yaz; gelen yeni bağlantıya 10 dakika içinde dokun."],
  kullanildi: ["Bağlantı kullanıldı", "Her giriş bağlantısı yalnız bir kez açılabilir. Telegram'da botu açıp " +
    "<code>/panel</code> yaz; gelen yeni bağlantıya 10 dakika içinde dokun."],
  ulasilamadi: ["Telegram'a ulaşılamadı", "Giriş bağlantısı şu an doğrulanamadı. Birkaç saniye sonra aynı bağlantıyı " +
    "yeniden aç; olmazsa Telegram'da <code>/panel</code> yazıp yeni bağlantı al."],
};

export function girisHataSayfasi(neden = "gecersiz") {
  const [baslik, metin] = GIRIS_HATALARI[neden] || GIRIS_HATALARI.gecersiz;
  return `<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>${baslik} · Bilgi Makası</title><link rel="stylesheet" href="${YAZI_TIPLERI}"><style>${CSS}</style></head>
<body><div class="giris"><div class="giris-kart">
<div class="marka">${MAKAS_SVG}<span class="marka-yazi"><b class="b1 yirtik">BİLGİ</b><b class="b2 yirtik">MAKASI</b></span></div>
<h1>${baslik}</h1>
<p>${metin}</p>
</div></div></body></html>`;
}

// Kapı (panel.js) ile tarayıcı aynı kuralları kullanır; uygulamaya AYAR olarak verilir.
// KUYRUK_BASI telegram_bot._TAIL ile aynı (Python testi karşılaştırır).
export const KUYRUK_BASI = ["#", "📷", "🎙", "Görseller:", "Kaynaklar:", "Bu videoda yapay zekâ"];
export const SINIR = { baslik: 100, aciklama: 2000, aciklamaBayt: 4000 };

// ------------------------------------------------------------------ tarayıcı uygulaması
function uygulama(AYAR) {
  "use strict";
  const TR = 3 * 3600 * 1000;
  const AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
  const GUNLER = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"];
  const PF = [["youtube", "YouTube"], ["instagram", "Instagram"], ["tiktok", "TikTok"]];
  const PF_AD = { youtube: "YouTube", instagram: "Instagram", tiktok: "TikTok" };
  const IZLEME_MS = 10000, IZLEME_SURE = 180000;
  const DURUM = {
    onay_bekliyor: ["Onay bekliyor", "onay"], zamanlandi: ["Zamanlandı", "plan"],
    yayinlaniyor: ["Paylaşılıyor", "plan surec"], yayinlandi: ["Paylaşıldı", "ok"],
    kismen: ["Kısmen paylaşıldı", "hata"], hata: ["Paylaşılamadı", "hata"], baglanti_yok: ["Bağlantı yok", "hata"],
    reddedildi: ["Reddedildi", "notr"], iptal: ["İptal", "notr"],
  };
  // işlem gerektirenler üstte (Sorunlu boşsa hiç gösterilmez)
  const BOLUMLER = [
    ["onay", "Onay bekleyen", (v) => v.status === "onay_bekliyor"],
    ["sorunlu", "Sorunlu", (v) => ["hata", "kismen", "baglanti_yok"].includes(v.status)],
    ["plan", "Zamanlanan", (v) => v.status === "zamanlandi" || v.status === "yayinlaniyor"],
    ["paylasilan", "Paylaşılan", (v) => v.status === "yayinlandi"],
  ];
  const PF_DA = { youtube: "YouTube'da aç", instagram: "Instagram'da aç", tiktok: "TikTok'ta aç" };
  const SEKMELER = [["videolar", "Videolar", "video"], ["takvim", "Takvim", "takvim"],
    ["istatistik", "İstatistik", "grafik"], ["konular", "Konular", "konu"]];
  const METRIKLER = [["followers", "Takipçi"], ["views", "İzlenme"], ["likes", "Beğeni"]];
  const IKON = {
    youtube: '<svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="4.5" fill="currentColor"/><path d="M10 9.2l5 2.8-5 2.8z" fill="var(--surface)"/></svg>',
    instagram: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="3.2" y="3.2" width="17.6" height="17.6" rx="5.2"/><circle cx="12" cy="12" r="4"/><circle cx="17.4" cy="6.6" r="1.2" fill="currentColor" stroke="none"/></svg>',
    tiktok: '<svg viewBox="0 0 24 24"><path d="M13.6 2.5h3.2c.3 2.3 1.8 3.8 4.2 4v3.2c-1.6 0-3-.5-4.2-1.3v6.4a6.3 6.3 0 1 1-6.3-6.3c.3 0 .6 0 .9.1v3.3a3.1 3.1 0 1 0 2.2 3z" fill="currentColor"/></svg>',
    video: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="6" y="2.5" width="12" height="19" rx="3"/><path d="M10.5 9.5l4 2.5-4 2.5z" fill="currentColor"/></svg>',
    takvim: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/><circle cx="8.5" cy="14.5" r="1.2" fill="currentColor" stroke="none"/><circle cx="12" cy="14.5" r="1.2" fill="currentColor" stroke="none"/></svg>',
    grafik: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 20.5h17"/><path d="M5 16l4.5-5 3.5 3 6.5-8"/><circle cx="19.5" cy="6" r="1.4" fill="currentColor"/></svg>',
    konu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1.4" fill="currentColor" stroke="none"/><circle cx="4.5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="4.5" cy="18" r="1.4" fill="currentColor" stroke="none"/></svg>',
    yenile: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>',
    kapat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    oynat: '<svg viewBox="0 0 24 24"><path d="M7 4.5l13 7.5-13 7.5z" fill="#fff"/></svg>',
    disari: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
    tamam: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    saat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>',
    uyari: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 3.5l9.5 16.5h-19z" stroke-linejoin="round"/><path d="M12 10v4.5M12 17.3v.2"/></svg>',
    yukari: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 14l6-6 6 6"/></svg>',
    asagi: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 10l6 6 6-6"/></svg>',
    sil: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/></svg>',
    arti: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  };

  const S = {
    D: null, imza: "", fark: 0, sekme: "videolar", yukleniyor: false, hata: "", giris: false, sonYukleme: 0,
    bekleyen: new Map(), kuyruk: null, kuyrukTaban: null, kuyrukKirli: false, metrik: "followers", uretKonu: "", yeniKonu: "",
    tumPaylasilan: false, ertelenen: false,
  };
  const $ = (id) => document.getElementById(id);

  // ---------------------------------------------------------------- yardımcılar
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "ikon") el.insertAdjacentHTML("afterbegin", IKON[v] || "");
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const k of kids.flat(Infinity)) {
      if (k == null || k === false || k === "") continue;
      el.append(k instanceof Node ? k : String(k));
    }
    return el;
  }
  const ikon = (ad) => { const s = document.createElement("span"); s.style.display = "contents"; s.innerHTML = IKON[ad] || ""; return s; };
  const pad = (n) => String(n).padStart(2, "0");
  const simdi = () => Date.now() + S.fark;
  function parca(ms) {
    const t = new Date(ms + TR);
    return { y: t.getUTCFullYear(), m: t.getUTCMonth(), d: t.getUTCDate(), g: t.getUTCDay(), hh: pad(t.getUTCHours()), mm: pad(t.getUTCMinutes()) };
  }
  const gunAdi = (ms) => { const p = parca(ms); return `${p.d} ${AYLAR[p.m]} ${GUNLER[p.g]}`; };
  const tamTarih = (ms) => { const p = parca(ms); return `${p.d} ${AYLAR[p.m]} ${GUNLER[p.g]} ${p.hh}:${p.mm}`; };
  const saatDk = (ms) => { const p = parca(ms); return `${p.hh}:${p.mm}`; };
  const kisaTarih = (ms) => { const p = parca(ms); return `${p.d} ${AYLAR[p.m].slice(0, 3)}`; };
  const gunNo = (ms) => Math.floor((ms + TR) / 86400000);
  const ms = (iso) => { const t = Date.parse(iso || ""); return Number.isFinite(t) ? t : null; };
  function tagZamani(tag) {
    const m = /^short-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})?/.exec(tag || "");
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)) : null; // etiket UTC saatidir
  }
  const sayi = (n) => (typeof n === "number" ? n.toLocaleString("tr-TR") : "—");
  const kompakt = (n, k) => new Intl.NumberFormat("tr-TR", { notation: "compact", maximumFractionDigits: k }).format(n);
  // hesap kartlarında büyük sayılar 3 anlamlı basamakla kısa yazılır (1,37 Mn, 100 B), tam değer title'da: dar sütunda sayı bölünmez
  const olcuEl = (n) => (typeof n === "number" && Math.abs(n) >= 100000
    ? h("strong", { title: sayi(n) }, new Intl.NumberFormat("tr-TR", { notation: "compact", maximumSignificantDigits: 3 }).format(n))
    : h("strong", null, sayi(n)));
  function eksenEtiketleri(ticks) { // ondalık basamak, etiketler birbirinden ayrılana kadar artar
    for (let k = 0; k <= 4; k++) {
      const e = ticks.map((t) => kompakt(t, k));
      if (new Set(e).size === e.length) return e;
    }
    return ticks.map(sayi);
  }
  const bayt = (s) => new TextEncoder().encode(s).length;
  const uzunluk = (s) => [...s].length;
  const guvenliUrl = (u) => (typeof u === "string" && /^https:\/\//.test(u) ? u : null);

  // ---------------------------------------------------------------- sunucu
  class PanelHata extends Error { constructor(m, s) { super(m); this.status = s; } }
  async function istek(yol, govde) {
    const opt = govde === undefined ? { credentials: "same-origin" } : {
      method: "POST", credentials: "same-origin",
      headers: { "content-type": "application/json", "x-panel": "1" }, body: JSON.stringify(govde),
    };
    let r;
    try { r = await fetch("/panel/api/" + yol, opt); } catch {
      throw new PanelHata("Bağlantı kurulamadı. İnternetini kontrol edip tekrar dene.", 0);
    }
    let j = null;
    try { j = await r.json(); } catch { /* boş */ }
    if (r.status === 401) { S.giris = true; ciz(); throw new PanelHata((j && j.hata) || "Oturum gerekli.", 401); }
    if (!r.ok) throw new PanelHata((j && j.hata) || `Sunucu hatası (${r.status}). Birazdan tekrar dene.`, r.status);
    return j;
  }

  async function yukle(sessiz) {
    if (S.yukleniyor) return;
    S.yukleniyor = true;
    ustCiz();
    try {
      const D = await istek("durum");
      S.fark = (ms(D.zaman) || Date.now()) - Date.now();
      S.sonYukleme = Date.now();
      S.hata = "";
      const imza = JSON.stringify([D.videos, D.stats, D.oneriler, D.konu_sirasi, D.stats_gecmis, D.uyarilar]);
      const degisti = imza !== S.imza;
      S.D = D; S.imza = imza; S.giris = false;
      // kaydedilmemiş ya da kaydı süren sıra sunucudaki eski listeyle ezilmez (kayıt görülünce izlemeyiDenetle alır)
      if (!S.kuyrukKirli && !S.bekleyen.has("queue_set")) { S.kuyruk = (D.konu_sirasi || []).slice(); S.kuyrukTaban = S.kuyruk.slice(); }
      izlemeyiDenetle();
      if (degisti || !sessiz) ciz(); else ustCiz();
    } catch (e) {
      if (e.status !== 401) { S.hata = e.message; if (!sessiz || !S.D) ciz(); else bildir(e.message, true); }
    } finally {
      S.yukleniyor = false;
      ustCiz();
    }
  }

  // ---------------------------------------------------------------- işlem + izleme
  function videoIzi(tag) {
    return (D) => JSON.stringify(((D && D.videos) || []).find((v) => v.tag === tag) || null);
  }
  const IZLER = {
    refresh_suggestions: (D) => JSON.stringify(D && D.oneriler),
    report: (D) => JSON.stringify(D && D.stats && D.stats.time),
    queue_set: (D) => JSON.stringify(D && D.konu_sirasi),
    produce_topic: (D) => String(((D && D.videos) || []).length),
    produce_suggestion: (D) => String(((D && D.videos) || []).length),
  };
  const BITTI = {
    refresh_suggestions: "✅ Yeni öneriler geldi.", report: "✅ İstatistikler güncellendi.",
    queue_set: "✅ Konu sırası kaydedildi.", produce_topic: "🎬 Yeni video geldi: Onay bekleyen'e bak.",
    produce_suggestion: "🎬 Yeni video geldi: Onay bekleyen'e bak.",
  };
  const ZAMAN_ASIMI = {
    produce_topic: "🎬 Üretim sürüyor (yaklaşık 15 dk). Video hazır olunca burada ve Telegram'da görünür.",
    produce_suggestion: "🎬 Üretim sürüyor (yaklaşık 15 dk). Video hazır olunca burada ve Telegram'da görünür.",
    refresh_suggestions: "🔎 Öneriler hâlâ hazırlanıyor; birkaç dakika sonra yenile.",
  };

  async function islem(anah, govde, etiket) {
    if (S.bekleyen.has(anah)) return false;
    const iz = govde.tag ? videoIzi(govde.tag) : (IZLER[govde.action] || (() => ""));
    S.bekleyen.set(anah, { basla: Date.now(), iz, once: iz(S.D), govde, etiket, gonderiliyor: true });
    ciz();
    try {
      const j = await istek("islem", govde);
      const b = S.bekleyen.get(anah);
      if (b) { b.gonderiliyor = false; b.rid = j && j.rid; }
      bildir("⏳ İşleniyor (30-60 sn)…");
      izlemeyiBaslat();
      ciz();
      return true;
    } catch (e) {
      S.bekleyen.delete(anah);
      ciz();
      if (e.status !== 401) bildir(e.message, true);
      if (e.status === 409) yukle(true);
      return false;
    }
  }

  let zamanlayici = null;
  function izlemeyiBaslat() {
    if (zamanlayici) return;
    zamanlayici = setInterval(() => {
      if (![...S.bekleyen.values()].some((b) => !b.gonderiliyor)) { clearInterval(zamanlayici); zamanlayici = null; return; }
      yukle(true);
    }, IZLEME_MS);
  }
  function bitti(b) {
    // konu sırası: Python kaydı panel isteğinin numarasıyla (rid) yazar; üretimin sıradan konu alması karışmaz
    if (b.govde.action === "queue_set" && S.D && S.D.konu_sirasi_rid !== undefined && b.rid) return S.D.konu_sirasi_rid === b.rid;
    return b.iz(S.D) !== b.once;
  }
  function izlemeyiDenetle() {
    for (const [anah, b] of S.bekleyen) {
      if (b.gonderiliyor) continue;
      if (bitti(b)) {
        S.bekleyen.delete(anah);
        if (b.govde.action === "queue_set") { // kaydedilen (birleştirilmiş) sıra artık sunucudaki
          S.kuyruk = (S.D.konu_sirasi || []).slice(); S.kuyrukTaban = S.kuyruk.slice(); S.kuyrukKirli = false;
        }
        bildir(BITTI[b.govde.action] || `✅ Güncellendi: ${b.etiket}`);
      } else if (Date.now() - b.basla > IZLEME_SURE) {
        S.bekleyen.delete(anah);
        bildir(ZAMAN_ASIMI[b.govde.action] || "Henüz bir değişiklik görünmüyor. Sonucu Telegram'daki mesajda gör; sorun varsa tekrar dene.",
          !ZAMAN_ASIMI[b.govde.action]);
      }
    }
  }

  function bildir(metin, hata) {
    const kap = $("bildirimler");
    const el = h("div", { class: "bildirim" + (hata ? " hata" : "") }, metin);
    kap.append(el);
    while (kap.children.length > 3) kap.firstChild.remove();
    setTimeout(() => el.remove(), hata ? 6000 : 4000);
  }

  // ---------------------------------------------------------------- çizim
  function guvenliMi() {
    // oynayan video veya yazı yazılan alan varken arka plan yenilemesi sayfayı yeniden çizmesin
    const a = document.activeElement;
    if (a && $("uygulama").contains(a) && (a.tagName === "INPUT" || a.tagName === "TEXTAREA")) return false;
    return ![...document.querySelectorAll("#uygulama video")].some((v) => !v.paused && !v.ended);
  }

  function ciz(zorla) {
    if (!zorla && S.D && !S.giris && !guvenliMi()) { S.ertelenen = true; ustCiz(); return; }
    S.ertelenen = false;
    const kok = $("uygulama");
    kok.replaceChildren();
    if (S.giris) { kok.append(girisEkrani()); return; }
    kok.append(ustCubuk());
    ustCiz();
    const main = h("main", { id: "icerik" });
    if (S.hata) {
      main.append(h("div", { class: "serit hata", role: "alert" }, ikon("uyari"), h("span", null, S.hata),
        h("button", { class: "btn btn-koyu btn-kucuk", onclick: () => yukle() }, "Tekrar dene")));
    }
    if (!S.D) { main.append(h("div", { class: "yuk" }, S.hata ? "" : "Yükleniyor…")); kok.append(main); return; }
    for (const u of S.D.uyarilar || []) main.append(h("div", { class: "serit bilgi" }, ikon("uyari"), h("span", null, u)));
    const icerik = { videolar: videolar, takvim: takvim, istatistik: istatistik, konular: konular }[S.sekme]();
    main.append(icerik);
    main.append(h("footer", { class: "alt-bilgi" }, h("span", null, "Oturum bu tarayıcıda 30 gün açık kalır. Bütün cihazlardaki "
      + "oturumları kapatmak için GitHub'da 'Telegram kapısını kur' işini çalıştır."),
    h("button", { class: "btn btn-cizgi btn-kucuk", onclick: cikisSor }, "Çıkış yap")));
    kok.append(main);
    grafikleriCiz();
    ustCiz();
  }

  function ertelenmisiCiz() { if (S.ertelenen && guvenliMi()) ciz(); }

  function cikisSor() {
    onayla({ baslik: "Çıkış yapılsın mı?", alt: null, metin: "Bu tarayıcıdaki oturum kapanır. Yeniden girmek için Telegram'da /panel yaz.",
      evet: "Çıkış yap", sonra: async () => {
        try { await istek("cikis", {}); } catch (e) { if (e.status !== 401) { bildir(e.message, true); return; } }
        S.giris = true; S.D = null; S.imza = ""; S.bekleyen.clear();
        ciz(true);
      } });
  }
  document.addEventListener("focusout", () => setTimeout(ertelenmisiCiz, 50));

  function marka() {
    const m = h("span", { class: "marka" });
    m.append(document.getElementById("makas").content.cloneNode(true));
    m.append(h("span", { class: "marka-yazi" }, h("b", { class: "b1 yirtik" }, "BİLGİ"), h("b", { class: "b2 yirtik" }, "MAKASI")));
    return m;
  }

  function ustCubuk() {
    const say = S.D ? S.D.videos.filter((v) => v.status === "onay_bekliyor").length : 0;
    const sorun = S.D ? S.D.videos.filter((v) => ["hata", "kismen", "baglanti_yok"].includes(v.status)).length : 0;
    const nav = h("nav", { class: "sekmeler", "aria-label": "Bölümler" }, SEKMELER.map(([id, ad, ik]) =>
      h("button", { class: "sekme", "aria-current": S.sekme === id ? "page" : null, onclick: () => sekmeyeGec(id) },
        ikon(ik), h("span", null, ad),
        id === "videolar" && say + sorun ? h("span", { class: "rozet", "aria-label": `${say + sorun} işlem bekliyor` }, say + sorun) : null)));
    return h("header", { class: "ust" }, h("div", { class: "ust-ic" }, marka(), nav,
      h("div", { class: "ust-bilgi" }, h("span", { class: "guncel", id: "guncel" }),
        h("button", { class: "ikon-btn", id: "yenile", "aria-label": "Yenile", title: "Yenile", onclick: () => yukle() }, ikon("yenile")))));
  }

  function ustCiz() {
    const g = $("guncel"), y = $("yenile");
    if (g) {
      if (S.sonYukleme) {
        const sn = Math.round((Date.now() - S.sonYukleme) / 1000);
        g.textContent = sn < 50 ? "Az önce güncellendi" : `${saatDk(S.sonYukleme + S.fark)} itibarıyla`;
      } else g.textContent = "";
    }
    if (y) y.classList.toggle("donuyor", S.yukleniyor);
  }

  function sekmeyeGec(id) {
    if (S.sekme === id) { window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    S.sekme = id;
    try { history.replaceState(null, "", "#" + id); } catch { /* yok */ }
    ciz(true);
    window.scrollTo(0, 0);
  }

  function girisEkrani() {
    return h("div", { class: "giris" }, h("div", { class: "giris-kart" }, marka(),
      h("h1", null, "Panele giriş"),
      h("p", null, "Telegram'da botu açıp ", h("code", null, "/panel"), " yaz. Gelen bağlantıya dokununca panel bu tarayıcıda 30 gün açık kalır."),
      h("div", { class: "slogan" }, "Kesip biçilmiş bilgi.")));
  }

  function bolumBasligi(id, ad, sayiDeg, not) {
    return h("div", { class: "bolum", id: "b-" + id }, h("h2", { class: "yirtik" }, ad),
      sayiDeg == null ? null : h("span", { class: "sayi" }, sayiDeg), not ? h("span", { class: "not" }, not) : null);
  }

  // ---------------------------------------------------------------- Videolar
  function takvimi(v) {
    if (v.schedule && typeof v.schedule === "object") return v.schedule;
    return v.publish_at ? Object.fromEntries(PF.map(([p]) => [p, v.publish_at])) : {};
  }
  function bekleyenTakvim(v) {
    const ok = new Set(Object.entries(v.platforms || {}).filter(([, r]) => r && r.status === "ok").map(([p]) => p));
    return Object.fromEntries(Object.entries(takvimi(v)).filter(([p, t]) => t && !ok.has(p)));
  }
  function sonrakiZaman(v) {
    const t = Object.values(bekleyenTakvim(v)).map(ms).filter((x) => x != null);
    return t.length ? Math.min(...t) : Infinity;
  }

  function videolar() {
    const vs = S.D.videos.slice();
    const kap = h("div");
    const gruplar = BOLUMLER.map(([id, ad, f]) => [id, ad, vs.filter(f)]).filter(([id, , l]) => id !== "sorunlu" || l.length);
    kap.append(h("div", { class: "ozet" }, gruplar.map(([id, ad, l]) =>
      h("a", { href: "#b-" + id, class: (id === "onay" || id === "sorunlu") && l.length ? "dikkat" : null,
        onclick: (e) => { e.preventDefault(); const b = $("b-" + id); if (b) b.scrollIntoView({ behavior: "smooth" }); } },
      h("b", null, l.length), ad))));
    for (const [id, ad, liste] of gruplar) {
      const sirali = id === "plan" ? liste.sort((a, b) => sonrakiZaman(a) - sonrakiZaman(b))
        : liste.sort((a, b) => (tagZamani(b.tag) || 0) - (tagZamani(a.tag) || 0));
      const not = id === "onay" && liste.length ? "Onayla veya reddet" : id === "sorunlu" && liste.length ? "Tekrar denenebilir" : null;
      kap.append(bolumBasligi(id, ad, liste.length, not));
      if (!liste.length) {
        kap.append(h("div", { class: "bos" }, { onay: "Onay bekleyen video yok.", plan: "Zamanlanmış paylaşım yok.",
          paylasilan: "Henüz paylaşılan video yok." }[id]));
        continue;
      }
      const gos = id === "paylasilan" && !S.tumPaylasilan ? sirali.slice(0, 6) : sirali;
      kap.append(h("div", { class: "izgara uclu" }, gos.map(kart)));
      if (gos.length < sirali.length) {
        kap.append(h("button", { class: "btn btn-cizgi daha", onclick: () => { S.tumPaylasilan = true; ciz(true); } },
          `Tümünü göster (${sirali.length})`));
      }
    }
    const diger = vs.filter((v) => !BOLUMLER.some(([, , f]) => f(v)));
    if (diger.length) {
      kap.append(h("details", { class: "diger" }, h("summary", null, `Reddedilen ve diğerleri (${diger.length})`),
        diger.sort((a, b) => (tagZamani(b.tag) || 0) - (tagZamani(a.tag) || 0)).map((v) =>
          h("div", { class: "liste-satir" }, h("span", { class: "tarih" }, kisaTarih(tagZamani(v.tag) || 0)),
            h("span", null, v.title), h("span", { class: "pil notr" }, (DURUM[v.status] || [v.status])[0])))));
    }
    return kap;
  }

  function oynatici(v) {
    const video = h("video", { preload: "none", playsinline: true, src: "/panel/api/video/" + encodeURIComponent(v.tag),
      "aria-label": "Video: " + v.title });
    const kap = h("div", { class: "oynatici" }, video);
    let yeniden = false;
    video.addEventListener("error", () => {
      if (!yeniden && video.currentTime > 0) { // imzalı adresin süresi dolduysa bir kez yeniden al
        yeniden = true;
        const t = video.currentTime;
        video.src = "/panel/api/video/" + encodeURIComponent(v.tag) + "?t=" + Date.now();
        video.currentTime = t;
        video.play().catch(() => {});
        return;
      }
      kap.append(h("div", { class: "video-hata" }, "Video açılamadı.",
        h("button", { onclick: (e) => { e.target.parentNode.remove(); video.load(); video.play().catch(() => {}); } }, "Tekrar dene")));
    });
    video.addEventListener("pause", () => setTimeout(ertelenmisiCiz, 50));
    video.addEventListener("ended", () => setTimeout(ertelenmisiCiz, 50));
    kap.append(h("button", { class: "oynat", "aria-label": "Videoyu oynat", onclick: (e) => {
      const k = e.currentTarget.closest(".kart");
      k.classList.add("acik");
      video.controls = true;
      video.play().catch(() => {});
      requestAnimationFrame(() => kap.scrollIntoView({ block: "nearest", behavior: "smooth" }));
    } }, h("span", { class: "daire" }, ikon("oynat")), h("span", { class: "oynat-yazi" }, "İZLE")));
    kap.append(h("button", { class: "kucult", "aria-label": "Videoyu küçült", onclick: (e) => {
      video.pause(); video.controls = false;
      e.currentTarget.closest(".kart").classList.remove("acik");
    } }, ikon("kapat")));
    return kap;
  }

  function platformSatiri(v, p, ad, takv) {
    const r = (v.platforms || {})[p] || {};
    let durum, sinif, zaman = null, ik = null;
    if (r.status === "ok") {
      durum = r.draft ? "Taslak gönderildi" : "Paylaşıldı"; sinif = "ok"; ik = "tamam";
      zaman = ms(r.at) || ms(v.published);
    } else if (r.status === "hata" && v.status === "zamanlandi") {
      durum = "Yeniden denenecek"; sinif = "plan"; ik = "saat"; zaman = ms(takv[p]);
    } else if (r.status === "hata") {
      durum = "Hata"; sinif = "hata"; ik = "uyari";
    } else if (r.status === "atlandi") {
      durum = "Bağlı değil"; sinif = "pasif";
    } else if (v.status === "yayinlaniyor") {
      durum = "Paylaşılıyor…"; sinif = "surec"; ik = "saat";
    } else if (takv[p] && v.status === "zamanlandi") {
      durum = "Zamanlandı"; sinif = "plan"; ik = "saat"; zaman = ms(takv[p]);
    } else {
      durum = "Paylaşılmadı"; sinif = "pasif";
    }
    const sv = (((S.D.stats || {}).platforms || {})[p] || {}).videos;
    const st = sv && sv[v.tag];
    const url = guvenliUrl(r.url);
    const alt = [];
    if (zaman) alt.push(h("span", null, tamTarih(zaman)));
    if (url) alt.push(h("a", { href: url, target: "_blank", rel: "noopener noreferrer", "aria-label": PF_DA[p] || "Aç" }, "Aç", ikon("disari")));
    if (st) {
      alt.push(h("span", { class: "pf-sayi" }, `${sayi(st.views || 0)} izlenme · ${sayi(st.likes || 0)} beğeni`
        + ("saves" in st ? ` · ${sayi(st.saves)} kaydetme` : "")));
    }
    const ekler = [];
    if (r.status === "hata" && r.error) ekler.push(h("div", { class: "pf-hata" }, String(r.error).slice(0, 220)));
    if (r.status === "ok" && r.draft) {
      ekler.push(h("div", { class: "pf-not" }, "TikTok'taki bildirime dokunup açıklamayı yapıştır ve Paylaş de.",
        r.caption ? h("div", { style: "margin-top:6px" }, h("button", { class: "mini-btn", onclick: (e) => {
          navigator.clipboard.writeText(r.caption).then(() => { e.target.textContent = "Kopyalandı ✓"; },
            () => bildir("Kopyalanamadı; açıklamayı Telegram'dan al.", true));
        } }, "Açıklamayı kopyala")) : null));
    } else if (r.note && r.status === "ok") {
      ekler.push(h("div", { class: "pf-not" }, "⚠️ " + String(r.note).slice(0, 200)));
    }
    return h("li", { class: "pf" }, h("span", { class: "pf-ikon", title: ad }, ikon(p)),
      h("div", { class: "pf-govde" },
        h("div", { class: "pf-ust" }, h("b", null, ad), h("span", { class: "pf-durum " + sinif }, ik ? ikon(ik) : null, durum)),
        alt.length ? h("div", { class: "pf-alt" }, alt) : null, ekler));
  }

  // ek.disabled: aynı videoda başka bir işlem sürerken diğer düğmeler de kilitli (çift işlem gitmesin)
  function dugme(anah, metin, sinif, onclick, ek) {
    const b = S.bekleyen.get(anah);
    if (b) {
      return h("button", { class: "btn " + sinif, disabled: true, "aria-busy": "true" },
        h("span", { class: "yukleniyor-ikon" }), b.gonderiliyor ? "Gönderiliyor…" : "İşleniyor…");
    }
    return h("button", { class: "btn " + sinif, onclick, ...(ek || {}) }, metin);
  }

  function kart(v) {
    const [dAd, dSinif] = DURUM[v.status] || [v.status, "notr"];
    const tz = tagZamani(v.tag);
    const takv = takvimi(v);
    const bilgi = h("div", { class: "kart-bilgi" },
      h("div", { class: "ust-satir" }, h("span", { class: "tarih", title: "Videonun üretildiği zaman" },
        h("span", { class: "ad" }, "Üretim"), " · ", tz ? tamTarih(tz) : v.tag),
        h("span", { class: "pil " + dSinif }, dAd), v.duzenleme ? h("span", { class: "pil duz" }, "düzenlendi") : null),
      h("h3", { class: "baslik" }, v.title || v.tag),
      v.topic ? h("p", { class: "konu" }, v.topic) : null);
    const k = h("article", { class: "kart", "data-tag": v.tag }, h("div", { class: "kart-ust" }, oynatici(v), bilgi));
    if (v.status !== "onay_bekliyor") {
      k.append(h("ul", { class: "pf-liste" }, PF.map(([p, ad]) => platformSatiri(v, p, ad, takv))));
    }
    const d = [];
    const t = v.tag;
    const mesgul = [...S.bekleyen.keys()].some((k) => k.endsWith(":" + t)); // bu videoda bir işlem sürüyor
    const kilit = mesgul ? { disabled: true } : null;
    if (v.status === "onay_bekliyor") {
      d.push(dugme("approve:" + t, "Onayla", "btn-ana", () => onaySayfasi(v), kilit));
      d.push(dugme("reject:" + t, "Reddet", "btn-cizgi", () => onayla({
        baslik: "Reddedilsin mi?", alt: v.title, metin: "Video paylaşılmaz ve listeden kalkar. Bu geri alınamaz.",
        evet: "Reddet", sonra: () => islem("reject:" + t, { action: "reject", tag: t }, v.title) }), kilit));
    }
    if (v.status === "zamanlandi") {
      const kismen = Object.values(v.platforms || {}).some((r) => r && r.status === "ok");
      const ad = kismen ? "Kalanları iptal et" : "Paylaşımı iptal et";
      d.push(dugme("cancel:" + t, ad, "btn-koyu", () => onayla({
        baslik: kismen ? "Kalan paylaşımlar iptal edilsin mi?" : "Paylaşım iptal edilsin mi?", alt: v.title,
        metin: (kismen ? "Henüz paylaşılmamış platformlar iptal edilir. " : "Zamanlanmış paylaşım iptal edilir. ")
          + "Video yeniden onay bekler; istersen tekrar onaylarsın.",
        evet: ad, sonra: () => islem("cancel:" + t, { action: "cancel", tag: t }, v.title) }), kilit));
    }
    if (["hata", "kismen", "baglanti_yok"].includes(v.status)) {
      d.push(dugme("retry:" + t, "Hatalıları tekrar dene", "btn-ana", () => islem("retry:" + t, { action: "retry", tag: t }, v.title), kilit));
    }
    const yakin = v.status === "zamanlandi" && v.publish_at && Date.parse(v.publish_at) <= Date.now() + 10 * 60e3;
    if ((v.status === "onay_bekliyor" || v.status === "zamanlandi") && !yakin) { // paylaşıma 10 dk kala düzenlenmez
      d.push(dugme("edit:" + t, "Düzenle", "btn-cizgi", () => duzenleSayfasi(v), kilit));
    }
    if (d.length) k.append(h("div", { class: "dugmeler" }, d));
    return k;
  }

  // ---------------------------------------------------------------- sayfalar (dialog)
  // koruma: düzenleme formu doluyken {kirli(), sor()}; boşluğa dokunma, Esc veya ✕ değişikliği sessizce atmasın
  let koruma = null;
  function kapatIste() {
    const dlg = $("sayfa");
    if (koruma && koruma.kirli()) koruma.sor(); else dlg.close();
  }
  function sayfaAc(baslik, alt, govde) {
    const dlg = $("sayfa");
    koruma = null;
    dlg.replaceChildren(h("div", { class: "tutamac" }), h("div", { class: "sayfa-ic" },
      h("div", { class: "sayfa-bas" }, h("h2", { id: "sayfa-baslik" }, baslik),
        h("button", { class: "ikon-btn", "aria-label": "Kapat", onclick: kapatIste }, ikon("kapat"))),
      alt ? h("p", { class: "sayfa-alt" }, alt) : null, govde));
    if (!dlg.open) dlg.showModal();
    return dlg;
  }
  $("sayfa").addEventListener("click", (e) => { if (e.target === e.currentTarget) kapatIste(); });
  $("sayfa").addEventListener("cancel", (e) => { if (koruma && koruma.kirli()) { e.preventDefault(); koruma.sor(); } });
  $("sayfa").addEventListener("close", () => { koruma = null; setTimeout(ertelenmisiCiz, 50); });

  function onayla({ baslik, alt, metin, evet, sonra }) {
    const dlg = sayfaAc(baslik, alt, [h("p", { style: "margin:0;font:15px/1.5 var(--sans)" }, metin),
      h("div", { class: "sayfa-dugmeler" },
        h("button", { class: "btn btn-cizgi", onclick: () => dlg.close() }, "Vazgeç"),
        h("button", { class: "btn btn-ana", onclick: () => { dlg.close(); sonra(); } }, evet))]);
  }

  function slotlar() {
    const t = new Date(simdi() + TR);
    const y = t.getUTCFullYear(), m = t.getUTCMonth(), d = t.getUTCDate();
    const out = [["best", "🎯 Her platform en iyi saatinde", "Her platform kendi en uygun boş saatinde paylaşılır."],
      ["now", "⚡ Şimdi", "Birkaç dakika içinde tüm platformlarda paylaşılır."]];
    for (const [kod, ad, ek, sa] of [["b12", "Bugün 12:00", 0, 12], ["b19", "Bugün 19:00", 0, 19],
      ["y12", "Yarın 12:00", 1, 12], ["y19", "Yarın 19:00", 1, 19]]) {
      const u = Date.UTC(y, m, d + ek, sa);
      if (u > t.getTime() + 15 * 60 * 1000) out.push([kod, "🕒 " + ad, tamTarih(u - TR)]);
    }
    return out;
  }

  function onaySayfasi(v) {
    const dlg = sayfaAc("Ne zaman paylaşılsın?", v.title, h("div", { class: "secenekler" }, slotlar().map(([kod, ad, ac]) =>
      h("button", { class: "secenek" + (kod === "best" ? " vurgu" : ""), onclick: () => {
        dlg.close();
        islem("approve:" + v.tag, { action: "approve", tag: v.tag, code: kod }, v.title);
      } }, h("b", null, ad), h("span", null, ac)))));
  }

  async function duzenleSayfasi(v) {
    const dlg = sayfaAc("Düzenle", v.title, h("div", { class: "yuk" }, "Video bilgisi alınıyor…"));
    let m;
    try { m = await istek("meta/" + encodeURIComponent(v.tag)); } catch (e) {
      if (dlg.open) dlg.close();
      if (e.status !== 401) bildir(e.message, true);
      return;
    }
    if (!dlg.open) return;
    const d = v.duzenleme || {};
    const SN = AYAR.sinir;
    const baslik = h("textarea", { class: "alan tek", id: "f-baslik", rows: "2", autocomplete: "off", enterkeyhint: "next",
      "aria-describedby": "h-baslik", onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); aciklama.focus(); } } });
    baslik.value = d.title || m.title || v.title || "";
    const aciklama = h("textarea", { class: "alan", id: "f-aciklama", rows: "8", "aria-describedby": "h-aciklama" });
    aciklama.value = d.description || m.bilgi || "";
    // kapıdaki (panel.js metinAl) sadeleştirmeyle aynı: sayaç ve "değişti mi" gönderilecek metne bakar
    const tekSatir = (x) => x.trim().split(/\s+/).filter(Boolean).join(" ");
    const cokSatir = (x) => x.replace(/\r\n?/g, "\n").split("\n").map((l) => l.trimEnd()).join("\n").trim();
    const ilk = [tekSatir(baslik.value), cokSatir(aciklama.value)];
    const ekParagraf = (p) => { const l = p.split("\n").map((x) => x.trim()).filter(Boolean);
      return l.length > 0 && l.every((x) => AYAR.kuyrukBasi.some((k) => x.startsWith(k))); };
    const sb = h("span"), sa = h("span");
    const hb = h("p", { class: "alan-hata", id: "h-baslik", role: "alert", hidden: true });
    const ha = h("p", { class: "alan-hata", id: "h-aciklama", role: "alert", hidden: true });
    const kaydet = h("button", { class: "btn btn-ana", type: "submit" }, "Kaydet");
    const kirli = () => tekSatir(baslik.value) !== ilk[0] || cokSatir(aciklama.value) !== ilk[1];
    const hataYaz = (alan, el, metin) => { el.textContent = metin; el.hidden = !metin; alan.setAttribute("aria-invalid", metin ? "true" : "false"); };
    const guncelle = () => {
      const bm = tekSatir(baslik.value), am = cokSatir(aciklama.value);
      const b = uzunluk(bm), a = uzunluk(am);
      sb.textContent = `${b}/${SN.baslik}`; sb.className = b > SN.baslik || !b ? "asim" : "";
      sa.textContent = `${a}/${SN.aciklama}`; sa.className = a > SN.aciklama || !a ? "asim" : "";
      const eb = !b ? "Başlık boş olamaz." : b > SN.baslik ? `Başlık en fazla ${SN.baslik} karakter olabilir (${b - SN.baslik} fazla).` : "";
      const ea = !a ? "Açıklama boş olamaz."
        : a > SN.aciklama ? `Açıklama en fazla ${SN.aciklama} karakter olabilir (${a - SN.aciklama} fazla).`
          : bayt(am) > SN.aciklamaBayt ? "Açıklama çok uzun: emoji ve özel karakterler daha çok yer kaplar. Biraz kısalt."
            : am.split(/\n\s*\n/).some((p) => ekParagraf(p) && !p.split("\n").filter((l) => l.trim()).every((l) => l.trim().startsWith("#")))
              ? "Görsel atfı ve kaynak satırları sona kendiliğinden eklenir; bu satırları açıklamadan çıkar." : "";
      hataYaz(baslik, hb, eb);
      hataYaz(aciklama, ha, ea);
      kaydet.disabled = !!(eb || ea) || !kirli();
      kaydet.title = !kirli() && !eb && !ea ? "Kaydetmek için başlığı veya açıklamayı değiştir." : "";
    };
    baslik.addEventListener("input", guncelle);
    aciklama.addEventListener("input", guncelle);
    guncelle();
    const dugmeler = h("div", { class: "sayfa-dugmeler" },
      h("button", { class: "btn btn-cizgi", type: "button", onclick: () => dlg.close() }, "Vazgeç"), kaydet);
    const donBtn = h("button", { class: "btn btn-cizgi", type: "button", onclick: () => {
      soru.hidden = true; dugmeler.hidden = false; aciklama.focus();
    } }, "Düzenlemeye dön");
    const soru = h("div", { class: "kapat-onay", role: "alertdialog", "aria-label": "Kaydedilmemiş değişiklik", hidden: true },
      h("p", null, "Değişiklikler kaydedilmedi. Kapatılsın mı?"),
      h("div", { class: "sayfa-dugmeler" }, donBtn,
        h("button", { class: "btn btn-ana", type: "button", onclick: () => dlg.close() }, "Kapat, değişiklikleri at")));
    const form = h("form", { class: "secenekler", onsubmit: (e) => {
      e.preventDefault();
      if (kaydet.disabled) return;
      dlg.close();
      islem("edit:" + v.tag, { action: "edit", tag: v.tag, title: baslik.value, description: aciklama.value }, v.title);
    } },
    h("div", { class: "form-alan" }, h("label", { for: "f-baslik" }, "Başlık", sb), baslik, hb),
    h("div", { class: "form-alan" }, h("label", { for: "f-aciklama" }, "Açıklama (bilgi metni)", sa), aciklama, ha),
    m.ekler && m.ekler.length ? h("div", { class: "korunan" }, h("b", null, "Sona kendiliğinden eklenir:"), m.ekler.join("\n\n"),
      h("div", { style: "margin-top:6px" }, "Görsel atfı her zaman korunur. Kendi # etiket satırını yazarsan yukarıdaki etiketlerin yerine o kullanılır."))
      : null,
    h("p", { class: "sayfa-alt", style: "margin:0" }, v.status === "zamanlandi"
      ? "Henüz paylaşılmamış platformlarda yeni metin kullanılır." : "Onaylayınca tüm platformlarda yeni metin kullanılır."),
    dugmeler, soru);
    dlg.querySelector(".sayfa-ic").lastChild.replaceWith(form);
    koruma = { kirli, sor: () => { dugmeler.hidden = true; soru.hidden = false; donBtn.focus(); } };
  }

  // ---------------------------------------------------------------- Takvim
  function takvim() {
    const kap = h("div");
    const bugun = gunNo(simdi());
    const satirlar = [];
    for (const v of S.D.videos) {
      if (v.status !== "zamanlandi") continue;
      for (const [p, t] of Object.entries(bekleyenTakvim(v))) {
        const z = ms(t);
        if (z != null) satirlar.push({ z, p, v });
      }
    }
    satirlar.sort((a, b) => a.z - b.z || a.p.localeCompare(b.p));
    const ileri = satirlar.filter((s) => gunNo(s.z) > bugun + 6).length;
    kap.append(bolumBasligi("takvim", "Önümüzdeki 7 gün", null,
      `${satirlar.filter((s) => gunNo(s.z) <= bugun + 6).length} paylaşım · Türkiye saati`));
    for (let g = 0; g < 7; g++) {
      const gun = satirlar.filter((s) => Math.max(gunNo(s.z), bugun) === bugun + g);
      const ornek = (bugun + g) * 86400000 - TR + 12 * 3600000;
      const etiket = g === 0 ? "Bugün" : g === 1 ? "Yarın" : null;
      const bas = h("div", { class: "gun-bas" }, h("h3", null, gunAdi(ornek)), etiket ? h("span", { class: "etiket" }, etiket) : null,
        h("span", { class: "say" }, gun.length ? `${gun.length} paylaşım` : "Paylaşım yok"));
      if (!gun.length) { kap.append(h("section", { class: "gun bosgun" }, bas)); continue; }
      kap.append(h("section", { class: "gun" }, bas, h("ol", null, gun.map((s) => {
        const gecti = s.z < simdi();
        return h("li", { class: "satir" }, h("time", { class: gecti ? "gecikti" : null }, gecti ? "Sırada" : saatDk(s.z)),
          h("div", { class: "ne" }, h("span", { class: "pfad" }, ikon(s.p), PF_AD[s.p] || s.p,
            gecti ? ` · ${saatDk(s.z)} saati geldi, paylaşım sırada` : ""), h("span", { class: "vbaslik" }, s.v.title)));
      }))));
    }
    if (ileri) kap.append(h("p", { class: "tarih", style: "margin:12px 2px 0" }, `7 günden sonra: ${ileri} paylaşım daha.`));
    const sa = S.D.saatler || {};
    kap.append(h("div", { class: "saatler" }, bolumBasligi("saatler", "En iyi saatler", null, "🎯 seçeneği bunları kullanır"),
      h("div", { class: "saat-izgara" }, PF.map(([p, ad]) => h("div", { class: "saat-kart" },
        h("span", { class: "pf-ikon" }, ikon(p)),
        h("div", null, h("b", null, ad), h("span", null, ((sa.en_iyi || {})[p] || []).join(" · ")
          + (((sa.ek || {})[p] || []).length ? ` (ek: ${sa.ek[p].join(", ")})` : "")))))),
      h("p", { class: "tarih", style: "margin:10px 2px 0" },
        "Ek saat, günün kalan asıl saatleri başka videolara ayrıldıysa kullanılır. Aynı platformda iki paylaşım arası en az 2 saat.")));
    return kap;
  }

  // ---------------------------------------------------------------- İstatistik
  function hesapSerisi(p, metrik) {
    return (S.D.stats_gecmis || []).map((l) => ({ z: ms(l.time), v: ((l.hesap || {})[p] || {})[metrik] }))
      .filter((x) => x.z != null && typeof x.v === "number").sort((a, b) => a.z - b.z);
  }

  function farkEl(simdiki, onceki) {
    if (typeof simdiki !== "number") return h("span", { class: "fark yok" }, "\u00a0");
    if (typeof onceki !== "number") return h("span", { class: "fark yok" }, "—");
    const f = simdiki - onceki;
    if (!f) return h("span", { class: "fark yok", title: "Önceki ölçüme göre" }, "± 0");
    return h("span", { class: "fark " + (f > 0 ? "art" : "az"), title: "Önceki ölçüme göre" },
      (f > 0 ? "▲ +" : "▼ −") + sayi(Math.abs(f)));
  }

  function oncekiHesap(p, simdikiZaman) {
    // önceki geçmiş satırı: son ölçümle aynı andaki satır atlanır
    const l = (S.D.stats_gecmis || []).filter((x) => ms(x.time) != null && ms(x.time) < (simdikiZaman - 60000) && (x.hesap || {})[p]);
    return l.length ? l[l.length - 1].hesap[p] : null;
  }

  function istatistik() {
    const st = S.D.stats;
    const kap = h("div");
    const z = st && ms(st.time);
    const rapor = dugme("report", "Raporu yenile", "btn-koyu btn-kucuk", () => islem("report", { action: "report" }, "rapor"));
    kap.append(bolumBasligi("hesaplar", "Hesaplar", null, null));
    const ozet = h("div", { class: "kutu ozet-kart" }, h("div", { class: "ozet-ust" },
      h("div", null, h("small", null, "Son ölçüm"), h("b", null, z ? tamTarih(z) : "Henüz ölçüm yok")), rapor));
    kap.append(ozet);
    if (!st) { kap.append(h("div", { class: "bos" }, "İstatistik yok. 'Raporu yenile' ile ilk ölçümü al.")); return kap; }
    const toplam = { followers: 0, views: 0, likes: 0 };
    const kartlar = PF.map(([p, ad]) => {
      const d = (st.platforms || {})[p] || {};
      if (d.error) {
        return h("div", { class: "hesap" }, h("div", { class: "hesap-bas" }, h("span", { class: "pf-ikon" }, ikon(p)), h("b", null, ad)),
          h("div", { class: "pf-hata" }, d.error));
      }
      const a = d.account || {}, once = oncekiHesap(p, z);
      for (const k of Object.keys(toplam)) if (typeof a[k] === "number") toplam[k] += a[k];
      return h("div", { class: "hesap" }, h("div", { class: "hesap-bas" }, h("span", { class: "pf-ikon" }, ikon(p)), h("b", null, ad)),
        h("div", { class: "olcu" }, METRIKLER.map(([k, kad]) => h("div", null, h("small", null, kad),
          olcuEl(a[k]), farkEl(a[k], once && once[k])))),
        d.note ? h("div", { class: "pf-not" }, "ℹ️ " + d.note) : null);
    });
    ozet.append(h("div", { class: "toplamlar" }, METRIKLER.map(([k, kad]) =>
      h("div", null, h("small", null, "Toplam " + kad.toLowerCase()), olcuEl(toplam[k])))));
    kap.append(h("div", { class: "hesaplar" }, kartlar));

    kap.append(h("div", { class: "secici", role: "group", "aria-label": "Grafikte gösterilen ölçü" }, METRIKLER.map(([k, ad]) =>
      h("button", { "aria-pressed": S.metrik === k ? "true" : "false", onclick: () => { S.metrik = k; ciz(true); } }, ad))));
    const madi = (METRIKLER.find((x) => x[0] === S.metrik) || [])[1];
    kap.append(h("div", { class: "grafikler" }, PF.map(([p, ad]) => {
      const seri = hesapSerisi(p, S.metrik);
      const gk = h("div", { class: "grafik-kart" }, h("h3", null, ikon(p), ad),
        h("div", { class: "alt" }, seri.length >= 2 ? `${madi} · ${kisaTarih(seri[0].z)} – ${kisaTarih(seri[seri.length - 1].z)}` : madi));
      if (seri.length < 2) {
        gk.append(h("div", { class: "birikiyor" }, seri.length || hesapSerisi(p, "followers").length >= 2
          ? (seri.length ? "Veri birikiyor" : `${ad} için ${madi.toLowerCase()} ölçülmüyor`)
          : "Veri birikiyor\n(her raporda bir nokta eklenir)"));
      } else {
        const g = h("div", { class: "grafik", tabindex: "0", role: "img",
          "aria-label": `${ad} ${madi.toLowerCase()}: ${tamTarih(seri[0].z)} ${sayi(seri[0].v)}, ${tamTarih(seri[seri.length - 1].z)} ${sayi(seri[seri.length - 1].v)}` });
        g._seri = seri;
        gk.append(g, h("details", { class: "tablo" }, h("summary", null, "Tablo"), h("table", null,
          seri.slice().reverse().slice(0, 30).map((x) => h("tr", null, h("td", null, tamTarih(x.z)), h("td", null, sayi(x.v)))))));
      }
      return gk;
    })));

    kap.append(bolumBasligi("vtablo", "Videolar", null, "en çok izlenen üstte"));
    const pl = st.platforms || {};
    const satir = Object.entries(st.titles || {}).map(([tag, baslik]) => {
      const yt = ((pl.youtube || {}).videos || {})[tag] || {}, ig = ((pl.instagram || {}).videos || {})[tag] || {};
      const v = S.D.videos.find((x) => x.tag === tag);
      return { baslik: (v && v.title) || baslik, yt: yt.views, ig: ig.views,
        top: (yt.views || 0) + (ig.views || 0), beg: (yt.likes || 0) + (ig.likes || 0) };
    }).sort((a, b) => b.top - a.top);
    if (!satir.length) kap.append(h("div", { class: "bos" }, "Paylaşılmış video istatistiği yok."));
    else {
      kap.append(h("div", { class: "vtablo", role: "table" },
        h("div", { class: "vsatir bas", role: "row" }, h("span", null, "Video"), h("span", null, "YouTube"), h("span", null, "Instagram"),
          h("span", null, "Toplam izlenme"), h("span", null, "Beğeni")),
        satir.map((s, i) => h("div", { class: "vsatir", role: "row" },
          h("div", { class: "vb" }, h("span", { class: "sira" }, i + 1), h("span", null, s.baslik)),
          h("div", { class: "n" }, h("small", null, "YouTube"), sayi(s.yt)),
          h("div", { class: "n" }, h("small", null, "Instagram"), sayi(s.ig)),
          h("div", { class: "n" }, h("small", null, "Toplam"), h("b", null, sayi(s.top))),
          h("div", { class: "n" }, h("small", null, "Beğeni"), sayi(s.beg))))));
    }
    const tt = ((pl.tiktok || {}).list || []).slice().sort((a, b) => (b.views || 0) - (a.views || 0));
    if (tt.length) {
      kap.append(bolumBasligi("tiktok", [h("span", { lang: "en" }, "TikTok"), " videoları"], null, "başlığa göre, en çok izlenen üstte"));
      kap.append(h("div", { class: "vtablo", role: "table" },
        h("div", { class: "vsatir bas", role: "row" }, h("span", null, "Video"), h("span", null, "İzlenme"), h("span", null, "Beğeni"),
          h("span", null, "Yorum"), h("span", null, "Paylaşım")),
        tt.map((s, i) => h("div", { class: "vsatir", role: "row" },
        h("div", { class: "vb" }, h("span", { class: "sira" }, i + 1), h("span", null, s.title || "—")),
        h("div", { class: "n" }, h("small", null, "İzlenme"), sayi(s.views)),
        h("div", { class: "n" }, h("small", null, "Beğeni"), sayi(s.likes)),
        h("div", { class: "n" }, h("small", null, "Yorum"), sayi(s.comments)),
        h("div", { class: "n" }, h("small", null, "Paylaşım"), sayi(s.shares))))));
    }
    return kap;
  }

  const NS = "http://www.w3.org/2000/svg";
  function s(tag, attrs, metin) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    if (metin != null) el.textContent = metin;
    return el;
  }
  function adimlar(min, max) {
    const ham = Math.max((max - min) / 3, 1); // sayılar tam sayı: adım en az 1
    const us = Math.pow(10, Math.floor(Math.log10(ham)));
    const adim = [1, 2, 5, 10].map((k) => k * us).find((k) => k >= ham) || us * 10;
    const a = Math.floor(min / adim) * adim, b = Math.ceil(max / adim) * adim;
    const out = [];
    for (let x = a; x <= b + adim / 2; x += adim) out.push(Math.round(x * 1000) / 1000);
    return out;
  }
  function grafikleriCiz() {
    for (const g of document.querySelectorAll(".grafik")) grafikCiz(g, g._seri);
  }
  let boyutZ = null;
  window.addEventListener("resize", () => { clearTimeout(boyutZ); boyutZ = setTimeout(grafikleriCiz, 120); });

  function grafikCiz(kap, seri) {
    if (!seri || !kap.isConnected) return;
    kap.replaceChildren();
    const W = Math.max(200, kap.clientWidth), H = kap.clientHeight || 150;
    const etiket = sayi(seri[seri.length - 1].v);
    let mn = Math.min(...seri.map((x) => x.v)), mx = Math.max(...seri.map((x) => x.v));
    if (mn === mx) { mn = Math.max(0, mn - 1); mx = mx + 1; }
    const ticks = adimlar(mn, mx);
    const eksen = eksenEtiketleri(ticks);
    const sol = Math.max(44, Math.max(...eksen.map((e) => e.length)) * 6.8 + 12), sag = Math.max(18, etiket.length * 7.4 + 14), ust = 14, alt = 22;
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const t0 = seri[0].z, t1 = seri[seri.length - 1].z;
    const X = (z) => sol + (t1 === t0 ? (W - sol - sag) / 2 : ((z - t0) / (t1 - t0)) * (W - sol - sag));
    const Y = (v) => ust + (1 - (v - y0) / (y1 - y0 || 1)) * (H - ust - alt);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, "aria-hidden": "true" });
    ticks.forEach((t, i) => {
      svg.append(s("line", { x1: sol, x2: W - sag, y1: Y(t), y2: Y(t), stroke: "var(--line)", "stroke-width": 1 }));
      svg.append(s("text", { x: sol - 8, y: Y(t) + 4, "text-anchor": "end" }, eksen[i]));
    });
    svg.append(s("text", { x: sol, y: H - 4, "text-anchor": "start" }, kisaTarih(t0)));
    svg.append(s("text", { x: X(t1), y: H - 4, "text-anchor": "end" }, kisaTarih(t1)));
    const nokta = seri.map((x) => [X(x.z), Y(x.v)]);
    const cizgi = nokta.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
    svg.append(s("path", { d: `${cizgi}L${nokta[nokta.length - 1][0].toFixed(1)},${Y(y0)}L${nokta[0][0].toFixed(1)},${Y(y0)}Z`,
      fill: "var(--red)", opacity: "0.1" }));
    svg.append(s("path", { d: cizgi, fill: "none", stroke: "var(--red)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    const [ex, ey] = nokta[nokta.length - 1];
    svg.append(s("circle", { cx: ex, cy: ey, r: 4, fill: "var(--red)", stroke: "var(--surface)", "stroke-width": 2 }));
    svg.append(s("text", { x: ex + 8, y: ey + 4, "text-anchor": "start", style: "fill:var(--text);font-weight:500" }, etiket));
    const dikey = s("line", { y1: ust, y2: H - alt, stroke: "var(--line-strong)", "stroke-width": 1, visibility: "hidden" });
    const isaret = s("circle", { r: 4, fill: "var(--red)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" });
    svg.append(dikey, isaret);
    const ip = h("div", { class: "ipucu", hidden: true });
    kap.append(svg, ip);
    let secili = -1;
    const goster = (i) => {
      if (i < 0) { dikey.setAttribute("visibility", "hidden"); isaret.setAttribute("visibility", "hidden"); ip.hidden = true; secili = -1; return; }
      secili = i;
      const [x, y] = nokta[i];
      dikey.setAttribute("x1", x); dikey.setAttribute("x2", x); dikey.setAttribute("visibility", "visible");
      isaret.setAttribute("cx", x); isaret.setAttribute("cy", y); isaret.setAttribute("visibility", "visible");
      ip.replaceChildren(h("b", null, sayi(seri[i].v)), tamTarih(seri[i].z));
      ip.hidden = false;
      ip.style.left = Math.min(Math.max(x, 70), W - 70) + "px";
      ip.style.top = Math.max(y - 10, 34) + "px";
    };
    const enYakin = (px) => {
      let en = 0;
      for (let i = 1; i < nokta.length; i++) if (Math.abs(nokta[i][0] - px) < Math.abs(nokta[en][0] - px)) en = i;
      return en;
    };
    kap.onpointermove = (e) => goster(enYakin(e.clientX - kap.getBoundingClientRect().left));
    kap.onpointerdown = kap.onpointermove;
    kap.onpointerleave = () => goster(-1);
    kap.onblur = () => goster(-1);
    kap.onkeydown = (e) => {
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        const i = secili < 0 ? nokta.length - 1 : secili + (e.key === "ArrowLeft" ? -1 : 1);
        goster(Math.min(nokta.length - 1, Math.max(0, i)));
      } else if (e.key === "Escape") goster(-1);
    };
  }

  // ---------------------------------------------------------------- Konular
  function kisalt(t, n) {
    t = String(t || "").trim();
    if (uzunluk(t) <= n) return t;
    const k = [...t].slice(0, n - 1).join("");
    return (k.slice(0, k.lastIndexOf(" ") > n * 0.6 ? k.lastIndexOf(" ") : k.length)).trim() + "…";
  }

  function konular() {
    const kap = h("div", { class: "ikili" });
    const sol = h("div"), sag = h("div");

    // şimdi üret
    const giris = h("input", { class: "alan", id: "uret-konu", placeholder: "Konu yaz (isteğe bağlı)",
      maxlength: "300", autocomplete: "off", enterkeyhint: "go", oninput: (e) => { S.uretKonu = e.target.value; } });
    giris.value = S.uretKonu;
    const uret = () => {
      const konu = giris.value.trim();
      const git = () => islem("produce_topic", { action: "produce_topic", topic: konu }, konu || "yeni video").then((ok) => {
        if (ok) { S.uretKonu = ""; ciz(true); }
      });
      onayla({ baslik: "Şimdi üretilsin mi?", alt: konu || "Konu otomatik seçilecek (önce konu sırası, sonra gündem).",
        metin: "Video yaklaşık 15 dakikada hazır olur ve onaya gelir.", evet: "Üret", sonra: git });
    };
    sol.append(bolumBasligi("uret", "Yeni video", null, null), h("div", { class: "kutu" },
      h("p", { class: "aciklama" }, "Konu yazmazsan önce konu sırasındaki ilk konu, o da yoksa gündem kullanılır. Video ~15 dakikada onaya gelir."),
      h("form", { class: "giris-satir", onsubmit: (e) => { e.preventDefault(); uret(); } }, giris,
        dugme("produce_topic", "Şimdi üret", "btn-ana", null, { type: "submit" }))));

    // öneriler
    const o = S.D.oneriler || {};
    const items = o.items || [];
    const tarih = ms(o.date ? o.date + "T12:00:00+03:00" : null);
    sol.append(bolumBasligi("oneriler", "Gündem önerileri", items.length || null, tarih ? gunAdi(tarih) : null));
    if (!items.length) sol.append(h("div", { class: "bos" }, "Öneri yok. Aşağıdan yeni öneriler iste."));
    const siraKilit = S.bekleyen.has("queue_set"); // kayıt sürerken sıra değiştirilmez (kayıt görülünce açılır)
    sol.append(h("div", { class: "oneriler" }, items.map((it, i) => {
      const sirada = (S.kuyruk || []).includes(kisalt(it.topic, 300));
      return h("article", { class: "oneri" },
        h("div", { class: "oneri-ust" }, h("span", null, it.scope === "TR" ? "🇹🇷 Türkiye" : "🌍 Dünya"),
          it.category ? h("span", null, "· " + it.category) : null, h("span", { class: "puan" }, `${it.score}/10`)),
        h("h4", null, it.topic),
        it.hook ? h("p", { class: "kanca" }, "🎣 " + it.hook) : null,
        it.trend ? h("p", { class: "gundem" }, "📈 " + it.trend) : null,
        h("div", { class: "dugmeler" },
          dugme("produce_suggestion:" + i, "Üret", "btn-ana btn-kucuk", () => onayla({ baslik: "Bu öneri üretilsin mi?", alt: it.topic,
            metin: "Video yaklaşık 15 dakikada hazır olur ve onaya gelir.", evet: "Üret",
            sonra: () => islem("produce_suggestion:" + i, { action: "produce_suggestion", index: i, topic: it.topic }, it.topic) })),
          h("button", { class: "btn btn-cizgi btn-kucuk", disabled: siraKilit || sirada || (S.kuyruk || []).length >= 30,
            onclick: () => { kuyrugaEkle(kisalt(it.topic, 300)); } }, sirada ? "Sırada ✓" : "Sıraya ekle")));
    })));
    sol.append(h("div", { style: "margin-top:12px" }, dugme("refresh_suggestions", "Yeni öneriler iste", "btn-koyu", () =>
      islem("refresh_suggestions", { action: "refresh_suggestions" }, "öneriler"), { style: "width:100%" })));

    // konu sırası
    const q = S.kuyruk || [];
    const kayitli = JSON.stringify(q) === JSON.stringify(S.D.konu_sirasi || []);
    sag.append(bolumBasligi("sira", "Konu sırası", q.length, "en fazla 30"));
    const kutu = h("div", { class: "kutu" }, h("p", { class: "aciklama" },
      "Otomatik üretimde (09:00 ve 18:00) gündem önerisinden önce sıradaki ilk konu kullanılır, sonra sıradan çıkar."));
    if (q.length) {
      kutu.append(h("ol", { class: "kuyruk" }, q.map((t, i) => h("li", null, h("span", { class: "no" }, i + 1),
        h("span", { class: "yazi" }, t),
        h("span", { class: "ara" },
          h("button", { class: "ikon-btn", "aria-label": "Yukarı taşı", disabled: siraKilit || i === 0, onclick: () => kuyrukTasi(i, -1) }, ikon("yukari")),
          h("button", { class: "ikon-btn", "aria-label": "Aşağı taşı", disabled: siraKilit || i === q.length - 1, onclick: () => kuyrukTasi(i, 1) }, ikon("asagi")),
          h("button", { class: "ikon-btn", "aria-label": "Sıradan çıkar", disabled: siraKilit, onclick: () => kuyrukSil(i) }, ikon("sil")))))));
    } else {
      kutu.append(h("div", { class: "bos", style: "margin-bottom:12px" }, "Sıra boş. Otomatik üretim gündemden konu seçer."));
    }
    const yeni = h("input", { class: "alan", id: "yeni-konu", placeholder: "Sıraya konu ekle", maxlength: "300",
      autocomplete: "off", enterkeyhint: "done", oninput: (e) => { S.yeniKonu = e.target.value; } });
    yeni.value = S.yeniKonu;
    kutu.append(h("form", { class: "giris-satir", onsubmit: (e) => {
      e.preventDefault();
      if (kuyrugaEkle(yeni.value)) { S.yeniKonu = ""; ciz(true); const y = $("yeni-konu"); if (y) y.focus(); }
    } }, yeni, h("button", { class: "btn btn-cizgi btn-kucuk", type: "submit", disabled: siraKilit || q.length >= 30 }, ikon("arti"), "Ekle")));
    const bekliyor = siraKilit;
    kutu.append(h("div", { class: "kaydet-cubuk" },
      h("span", { class: "durum" + (kayitli || bekliyor ? "" : " kirli") }, bekliyor ? "Kaydediliyor…" : kayitli ? "Kayıtlı." : "Kaydedilmemiş değişiklik var."),
      kayitli || bekliyor ? null : h("button", { class: "btn btn-cizgi btn-kucuk", onclick: () => {
        S.kuyruk = (S.D.konu_sirasi || []).slice(); S.kuyrukTaban = S.kuyruk.slice(); S.kuyrukKirli = false; ciz(true);
      } }, "Geri al"),
      // kirli bayrağı kayıt sunucuda görülene kadar kalır (izlemeyiDenetle); taban, Python'un üç yollu birleştirmesi için
      dugme("queue_set", "Kaydet", "btn-ana btn-kucuk", () => {
        islem("queue_set", { action: "queue_set", queue: S.kuyruk.slice(),
          queue_base: (S.kuyrukTaban || S.D.konu_sirasi || []).slice() }, "konu sırası");
      }, { disabled: kayitli })));
    sag.append(kutu);
    kap.append(sol, sag);
    return kap;
  }

  function kuyrugaEkle(t) {
    t = String(t || "").split(/\s+/).filter(Boolean).join(" ");
    if (!t || S.bekleyen.has("queue_set")) return false;
    if (uzunluk(t) > 300) { bildir("Konu en fazla 300 karakter olabilir.", true); return false; }
    S.kuyruk = S.kuyruk || [];
    if (S.kuyruk.includes(t)) { bildir("Bu konu zaten sırada."); return false; }
    if (S.kuyruk.length >= 30) { bildir("Sırada en fazla 30 konu olabilir.", true); return false; }
    S.kuyruk.push(t); S.kuyrukKirli = true;
    ciz(true);
    bildir("Sıraya eklendi. Kalıcı olması için 'Kaydet'e bas.");
    return true;
  }
  function kuyrukTasi(i, yon) {
    const q = S.kuyruk, j = i + yon;
    if (j < 0 || j >= q.length || S.bekleyen.has("queue_set")) return;
    [q[i], q[j]] = [q[j], q[i]]; S.kuyrukKirli = true; ciz(true);
  }
  function kuyrukSil(i) { if (S.bekleyen.has("queue_set")) return; S.kuyruk.splice(i, 1); S.kuyrukKirli = true; ciz(true); }

  // ---------------------------------------------------------------- başlat
  const ilk = (location.hash || "").slice(1);
  if (SEKMELER.some(([id]) => id === ilk)) S.sekme = ilk;
  window.addEventListener("hashchange", () => {
    const id = (location.hash || "").slice(1);
    if (SEKMELER.some(([x]) => x === id) && id !== S.sekme) { S.sekme = id; ciz(true); }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && Date.now() - S.sonYukleme > 30000) yukle(true);
  });
  setInterval(() => { if (document.visibilityState === "visible" && !zamanlayici) yukle(true); }, 60000);
  setInterval(ustCiz, 15000);
  ciz(true);
  yukle();
}

export const UYGULAMA_JS = `(${uygulama.toString()})(${JSON.stringify({ kuyrukBasi: KUYRUK_BASI, sinir: SINIR })});\n`;
