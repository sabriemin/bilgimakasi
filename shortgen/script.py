"""Konu seçimi ve senaryo üretimi.

Claude'a Claude Code CLI üzerinden, kullanıcının claude.ai aboneliğiyle (CLAUDE_CODE_OAUTH_TOKEN) erişilir.
Yapılandırılmış çıktı için --json-schema kullanılır. Doğrulama adımı web araması yapabilir.
Aylık harcama tavanı: state/claude_usage.json içinde tutulan eşdeğer maliyet CLAUDE_MONTHLY_BUDGET_USD'yi aşarsa üretim durur.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field

MODEL = os.environ.get("CLAUDE_MODEL", "opus")
ROOT = Path(__file__).resolve().parent.parent
USAGE = ROOT / "state" / "claude_usage.json"

CATEGORIES = [
    "bilim", "psikoloji", "tarih", "doğa ve hayvanlar", "uzay", "teknoloji",
    "ekonomi ve markalar", "sanat ve müzik", "spor", "dil ve kültür",
    "icatlar", "insan vücudu", "coğrafya", "az bilinen insan hikâyeleri",
]


# Anlatım kalıpları: aynı şablonun tekrarı "seri üretim" gibi görünmesin diye dönüşümlü kullanılır.
# label: ilk sahnenin üstündeki seri etiketi (ör. "EFSANE Mİ, GERÇEK Mİ? #4"), izleyiciye tanıdık bir format verir.
STRUCTURES = {
    "hikaye": ("BİLİNMEYEN HİKÂYE", "MİNİ HİKÂYE: kanca → çok kısa bağlam (yıl, yer, kişi) → gerilim ya da dönüm noktası → "
               "vurucu sonuç."),
    "efsane": ("EFSANE Mİ, GERÇEK Mİ?", "EFSANE Mİ GERÇEK Mİ: ilk cümlede herkesin doğru sandığı yaygın inanışı ve yanlış "
               "(ya da şaşırtıcı biçimde doğru) olduğunu birlikte söyle → kanıtı ve hikâyesi → doğrusu tek cümlede."),
    "neden": ("NEDEN BÖYLE?", "NEDEN SORUSU: gündelik ya da tanıdık bir şeyin şaşırtıcı nedenini sor ('X neden Y?') → "
              "çoğu kişinin tahmin ettiği yanlış cevabı söyle → gerçek nedeni adım adım aç → sonuç."),
    "sayac": ("3 ŞAŞIRTICI BİLGİ", "3 ŞAŞIRTICI BİLGİ: tek konu hakkında giderek şaşırtıcılaşan 3 bilgi; en şaşırtıcısı en "
              "sonda. Kuru sayım ('Birincisi, ikincisi') YAPMA; bilgiler akıcı bir anlatıyla bağlansın ('Üstelik...', "
              "'Ama asıl tuhaf olan...') ve izleyici üç ayrı bilgiyi rahatça seçebilsin. Kanca en tuhaf bilgiye merak uyandırsın."),
}


class Scene(BaseModel):
    narration: str = Field(description=(
        "Bu sahnede okunacak metin parçası: bir cümle ya da uzun bir cümlenin bir bölümü. Tüm sahnelerin narration'ları "
        "art arda okunduğunda kusursuz, akıcı tek bir belgesel metni oluşturmalı."))
    kicker: str = Field(description="Üstte küçük daktilo etiketi, BÜYÜK HARF, 1-5 kelime. Boş olabilir.")
    headline: List[str] = Field(description="Ekranda büyük yazılacak 1-3 satır, BÜYÜK HARF, satır başı 1-3 kelime.")
    highlight_line: int = Field(description="Sarı kutuda gösterilecek headline satır indeksi, yoksa -1.")
    strike: List[str] = Field(description="Üstü kırmızıyla çizilecek ek satırlar (BÜYÜK HARF). Çoğu sahnede boş.")
    theme: Literal["red", "yellow", "black", "paper"]
    image_mode: Literal["full", "framed", "none"]
    image_query: str = Field(default="", description="(Eski alan) Tek arama sorgusu. Yeni senaryolarda image_queries kullan.")
    image_queries: List[str] = Field(default_factory=list, description=(
        "Wikimedia Commons / Openverse'te aranacak 2-3 İngilizce sorgu, en özelden en genele. "
        "Özel isimleri (kişi, yer, olay) içersin. image_mode none ise boş liste."))
    icon: Literal["none", "question", "arrow", "door", "letter", "record"]
    illustration: str = Field(default="", description=(
        "Bu sahnede gösterilecek ÇİZİMİN İngilizce tarifi (tek nesne veya küçük sahne, anlamı tam versin; ör. "
        "'a towering dark-brown wave of sticky molasses with drips, sweeping forward'). Animasyonlu sahnelerde zorunlu; "
        "fotoğraflı sahnelerde fotoğraf bulunamazsa yedek olarak kullanılır. Saf sayı/istatistik sahnelerinde boş."))
    motion: Literal["none", "fly_up", "fly_right", "fly_left", "drop_in", "zoom_in", "float", "spin", "shake", "orbit", "pulse", "rise"] = "none"
    trail: bool = Field(default=False, description="Hareket eden nesnenin arkasında duman/iz olsun mu (roket, uçak için true; dalga, hayvan için false).")
    anim_query: str = Field(default="", description="(Eski alan) Kullanma.")
    # Yalnız "kart" şablonu kullanır; diğer şablonlar yok sayar. Eski senaryolar için hepsi isteğe bağlı.
    card: Literal["auto", "photo", "drawing", "counter", "compare", "quote", "interstitial", "cta"] = Field(
        default="auto", description="Kart şablonunda bu sahnenin kartı; çoğu sahnede auto.")
    card_value: str = Field(default="", description="counter kartı: sayılacak sayı, ör. '3.300' ya da '%90'.")
    card_label: str = Field(default="", description="counter: sayının etiketi (ör. 'YIL ÖNCE'); quote: alıntının kendisi.")
    card_myth: str = Field(default="", description="compare: yaygın inanış, en fazla 6 kelime.")
    card_fact: str = Field(default="", description="compare: doğrusu, en fazla 6 kelime.")
    card_note: str = Field(default="", description="Kartın küçük notu ya da kaynağı (ör. 'NASA arşivi · 1999'), en fazla 32 karakter.")
    mascot: Literal["auto", "normal", "surprised", "thinking", "happy"] = Field(
        default="auto", description="Kart şablonunda maskot Makas'ın ifadesi; çoğu sahnede auto.")


class ShortScript(BaseModel):
    topic: str
    category: Literal[tuple(CATEGORIES)] = Field(description="Konunun kategorisi.")  # type: ignore[valid-type]
    template: str = Field(default="", description="Önerilen görsel şablon adı (listeden) veya boş.")
    title: str = Field(description="Platform başlığı, en fazla 70 karakter, merak uyandıran.")
    description: str = Field(description=(
        "Kısa platform açıklaması: en fazla 2 kısa cümle (toplam ~200 karakter). İlk cümle merak uyandıran kanca, "
        "konunun aranan anahtar kelimelerini doğal biçimde içerir; ikinci cümle izleyiciye yorum yaptıran bir soru. "
        "Kaynak, link, emoji yığını veya etiket YAZMA."))
    hashtags: List[str] = Field(description=(
        "Tam 5 etiket, # olmadan, Türkçe karakterli olabilir; yalnız harf ve rakam (boşluk, kesme işareti, noktalama yok). "
        "Sıra: 1) search_phrase'in bitişik yazılmış hâli (ör. 'titaniknedenbattı'), "
        "2-4) konuya özel ve aranan 3 etiket (kişi/olay/yer/takım adı, alan: 'tarih', 'futbol', 'uzay'), 5) 'bilgimakasi'. "
        "'keşfet', 'fyp', 'viral' gibi genel etiketler ve konuyla ilgisi olmayan trend etiketleri KULLANMA: video yanlış "
        "kitleye test edilir. Instagram en fazla 5 etiket kabul ettiği için 5'i geçme."))
    scenes: List[Scene]
    sources: List[str] = Field(description="İddiaları destekleyen güvenilir kaynak başlıkları veya URL'leri.")
    search_phrase: str = Field(default="", description=(
        "Bu konuyu merak eden birinin TikTok/YouTube/Instagram aramasına yazacağı 2-5 kelimelik Türkçe ifade "
        "(ör. 'Titanik neden battı', 'Galatasaray UEFA Kupası', 'GTA nasıl doğdu')."))
    structure: Literal[tuple(STRUCTURES)] = Field(default="hikaye", description="Seçilen anlatım kalıbı.")  # type: ignore[valid-type]
    series_part: int = Field(default=0, description="0 = tek video, 1 = iki bölümlük serinin 1. bölümü, 2 = 2. bölümü.")
    next_part_brief: str = Field(default="", description=(
        "Yalnız series_part=1 ise: 2. bölümde anlatılacak, doğrulanmış ve 1. bölümde HİÇ söylenmemiş bilgiler "
        "(olaylar, sayılar, isimler, final/çözüm) ve 2. bölümün kancası. Diğer durumlarda boş."))


SYSTEM = """Sen Türkçe kısa video (YouTube Shorts / Reels / TikTok) senaristisin.
Biçim: 30-35 saniye. Seslendirme yavaş ve tane tane olduğu için toplam dış ses 65-75 kelime olsun, 78'i GEÇMESİN.
9-12 sahne, her sahne 2-4 saniye. Kısa videolar sonuna kadar izlenip tekrar izlendiği için daha çok dağıtılır; her saniye hak
edilmeli, dolgu cümle ve gereksiz bağlam yok. Hikâye bu süreye sığmıyorsa en ilginç tek açıyı anlat.
Yapı (seçilen anlatım kalıbının gövdesiyle birlikte):
1) KANCA (ilk sahne, ilk 3-4 saniye, en önemli kısım; izleyicilerin yarıdan fazlası kaydırıp geçme kararını ilk saniyede
   verir): En şaşırtıcı sonucu ya da çelişkiyi İLK CÜMLEDE söyle. Dönüşü ikinci cümleye bırakan kurulum cümlesiyle açma
   (kötü: "Manchester United Avrupa'da evinde 40 yıl yenilmedi. Ta ki..."; iyi: "Manchester United'ın Avrupa'daki
   40 yıllık serisini bir Türk takımı bitirdi."). Efsane kalıbında ilk cümle inanışı ve yanlış (ya da şaşırtıcı biçimde doğru) olduğunu birlikte
   söylesin ("Boğalar kırmızıya kızmaz; kırmızıyı ayırt edemezler bile."); neden kalıbında ilk cümle sorunun kendisi olabilir
   ("Uçaklar neden neredeyse hep beyaz?"); sayaç kalıbında ilk cümle en tuhaf bilgiyi ele vermeden ona işaret eden somut
   bir iddia olsun, en tuhaf bilgi yine en sonda gelsin. Serinin 2. bölümünde (series_part 2) ilk cümle 1. bölümün
   kaldığı yeri hatırlatan cümle olarak kalsın; kalıba özel ilk cümle kuralları uygulanmaz. Giriş, selam, "biliyor
   muydunuz" veya bağlam cümlesi YOK. İlk cümle en fazla 10 kelime olsun; ilk cümleyi bölme, tamamı ilk sahnede olsun.
   İlk sahnenin headline'ı tek başına okunduğunda kim/ne ve ne olduğunu söyleyen, merak uyandıran 2-3 satırlık güçlü bir
   iddia olsun; öznesiz bırakma (kötü: "AVRUPA'DA / 40 YIL / YENİLMEDİ"; iyi: "40 YILLIK SERİSİNİ / BİR TÜRK TAKIMI / BİTİRDİ"; neden kalıbında headline sorunun kendisi olabilir).
   Videonun kapağı ve önizlemesi bu karedir. Konuda Türkiye bağlantısı varsa ilk cümlede ve ilk headline'da geçsin.
   İlk sahne asla boş bir arka planla açılmasın: güçlü, yakın plan bir fotoğraf (image_mode full) ya da büyük bir çizim
   kullan; çizimse motion zoom_in, pulse, float ya da none olsun (nesne ilk karede görünmeli, fly_* kullanma).
   Örnek: "Bir mahalleyi tsunami değil, melas yuttu." / "1904 Olimpiyat maratonunda ilk gelen adam 17 kilometreyi arabayla gitti."
2) GÖVDE: seçilen anlatım kalıbına uy (bağlam en fazla 1-2 sahne). Videonun yaklaşık yarısında izleyiciyi tutan ikinci bir
   merak anı olsun: somut yeni bir bilgi ya da beklenmedik dönüş (kalıp cümle değil).
3) MAKAS'IN YORUMU: sonda kanalın kendi sesiyle tek kısa cümlelik bir çıkarım ya da bugüne bağlantı
   (ör. "Yani bazen bir yazılım hatası, bir efsanenin ta kendisidir."); vaaz ve klişe yok.
4) KAPANIŞ VE DÖNGÜ: Son sahnede izleyiciye kısa, açık uçlu bir soru sor ve "Yorumlara yaz." gibi
   en fazla 3 kelimelik bir çağrı ekle. Son cümle, video başa sardığında ilk cümleyle anlamlı biçimde birleşebilecek şekilde
   kurulursa izleyici fark etmeden ikinci kez izler; uygun düşüyorsa böyle bitir. "Takip et", "beğen" gibi istekler YAZMA.
ARAMA (izlenmenin önemli kısmı aramadan gelir): search_phrase alanına insanların arama kutusuna yazacağı 2-5 kelimelik
Türkçe ifadeyi yaz. Bu ifade (ya da çok yakın hâli) dış sesin ilk iki cümlesinde doğal biçimde söylensin, başlıkta geçsin,
açıklamanın ilk cümlesinde geçsin ve ilk etiket bu ifadenin boşluksuz hâli olsun. Başlık tıklama tuzağı değil, merak + arama
kelimesi olsun.
PAYLAŞILABİLİRLİK: En güçlü sinyal izleyicinin videoyu bir arkadaşına göndermesidir. Bunu bilen kişiyi "ilginç" gösteren,
sohbet açtıran bilgiyi öne çıkar. Konuda Türkiye bağlantısı varsa (Türk kişi, takım, yer, marka, kelime kökeni, Türkiye'deki
yansıması) mutlaka kullan; hedef kitle Türkiye'deki 15-34 yaş.
DİL VE ANLATIM (en önemli kural): Metin bir TÜRK BELGESEL ANLATICISININ ağzından, doğal ve kusursuz Türkçeyle yazılsın.
- Önce dış sesi baştan sona TEK BİR AKICI METİN olarak düşün, sonra sahnelere böl. Bir cümle iki üç sahneye yayılabilir;
  sahneleri art arda okuyunca metin hiç kesilmeden akmalı.
- Tam ve bağlantılı cümleler kur: "ise, oysa, üstelik, ne var ki, tam da bu sırada, bu yüzden" gibi bağlaçlarla olayları birbirine bağla.
  Telgraf üslubu yok: "İçinde 8,7 milyon litre melas." veya "Saatte 56 kilometre hızla." gibi yüklemsiz parçalar KULLANMA.
- Çeviri kokan kalıplardan kaçın ("Yerliler ... anlatır", "Peki ... neden ...?" tekrarı, "Ama gerçek başkaydı" gibi klişeler,
  İngilizce söz dizimi). Türkçede doğal duran fiil ve deyimleri seç; zamanlar tutarlı olsun (anlatı için -di'li/-miş'li geçmiş).
- Ton: sakin, ağırbaşlı, merak uyandıran; abartısız ama canlı. Sayıları okunduğu gibi yaz (sekiz virgül yedi milyon değil, "8,7 milyon").
- İyi örnek (gövde dili, kanca değil): "15 Ocak 1919'da Boston'ın North End mahallesi sıradan bir kış gününe uyanmıştı. Limanın hemen yanında, içinde 8,7 milyon
  litre melas bulunan dev bir tank yükseliyordu. Tank ilk günden beri sızdırıyordu; şirket ise sorunu gidermek yerine tankı kahverengiye boyatmayı seçti."
Sadece doğrulanabilir bilgiler kullan; emin olmadığın tarih, sayı veya alıntıyı kullanma. Tartışmalı siyasi, dinî, sağlıkla ilgili
iddialardan, yaşayan özel kişileri hedef alan içerikten kaçın.
Görsel kuralı: HİÇBİR sahne boş kalmasın. Her sahnede ya gerçek fotoğraf ya çizim olsun; yalnızca büyük bir sayı/istatistik
gösteren sahneler (en fazla 3 tane) saf tipografik olabilir.
- Fotoğraf: Sahnelerin yaklaşık yarısında (image_mode full veya framed). image_queries'e 2-3 sorgu yaz, en özelden en genele
  (ör. ["Boston Molasses Disaster 1919", "Great Molasses Flood wreckage", "North End Boston 1919"]). Sorgular Wikimedia Commons'ta
  kamu malı/özgür lisanslı karşılığı bulunabilecek şeyleri tarif etsin (tarihî kişi, yer, olay, nesne, hayvan, tablo).
  Yakın dönem ünlü fotoğrafları, film/dizi kareleri, logolar isteme. Fotoğraflı sahnelere de yedek 'illustration' tarifi yaz.
- Çizim: Diğer sahnelerde image_mode none ve 'illustration' alanına anlamı tam veren bir çizim tarifi yaz. Kelimeyi değil anlamı
  tarif et: 'melas dalgası' için deniz dalgası değil, koyu kahverengi yapışkan bir melas dalgası.
- Animasyon: Anlatılan şey doğal olarak hareket ediyorsa çizime 'motion' ver: roket/mekik fırlatılıyorsa fly_up (trail true),
  uçak/kuş/tren geçiyorsa fly_right veya fly_left, sel/dalga/akıntı ilerliyorsa fly_right veya rise (trail false),
  bir şey düşüyorsa drop_in, ortaya çıkış/keşif anında zoom_in, gezegen için spin veya orbit, kalp/beyin için pulse,
  patlama/deprem/yarılma için shake, balon/astronot/su altı için float. Hareketsiz çizimlerde motion none.
headline kelimeleri narration içinde geçen en vurucu kelimeler olsun. Temaları çeşitlendir, art arda aynı temayı
en fazla iki kez kullan. icon sadece gerçekten anlam katıyorsa.
KART ALANLARI (yalnız "kart" şablonu kullanır, diğer şablonlar yok sayar; emin değilsen card "auto", diğerleri boş):
- card "counter": tek büyük sayının sahnesi (card_value yalnız sayı, ör. "3.300"; card_label 1-3 kelimelik birim/etiket).
- card "compare": efsane kalıbında inanışın çürütüldüğü sahne (card_myth inanış, card_fact doğrusu).
- card "interstitial": videonun ortasındaki ikinci merak anı (headline o anın kendi vurucu kelimeleri; kalıp cümle değil).
- card "quote": doğrulanmış kısa bir alıntı (card_label alıntı, card_note kim · yıl). card "cta": son soru sahnesi.
- card_note kartın küçük notu ya da kaynağıdır. mascot çoğunlukla auto.
Kart alanları görsel alanların yerine geçmez; her sahnede fotoğraf/çizim kuralı aynen geçerli.
Kartlardaki sayı, inanış ve alıntılar da doğrulanmış bilgi olmalı."""


def _history(path: Path) -> list[str]:
    if path.exists():
        return [json.loads(l)["topic"] for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return []


class BudgetExceeded(RuntimeError):
    pass


def _month_usage() -> tuple[dict, str]:
    u = json.loads(USAGE.read_text(encoding="utf-8")) if USAGE.exists() else {}
    return u, dt.date.today().strftime("%Y-%m")


def _check_budget() -> float:
    limit = float(os.environ.get("CLAUDE_MONTHLY_BUDGET_USD", "100"))
    u, m = _month_usage()
    left = limit - u.get(m, 0.0)
    if left <= 0:
        raise BudgetExceeded(f"Bu ayın Claude bütçesi ({limit:.0f} $) doldu, üretim durduruldu.")
    return left


def _record(cost: float) -> None:
    u, m = _month_usage()
    u[m] = round(u.get(m, 0.0) + cost, 4)
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    USAGE.write_text(json.dumps(u, indent=2), encoding="utf-8")


def ask_claude(prompt: str, schema: type[BaseModel], system: str, web: bool = False) -> BaseModel:
    """Claude Code'u başsız (-p) çalıştırır, şemaya uygun JSON döndürür."""
    left = _check_budget()
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "json",
           "--json-schema", json.dumps(schema.model_json_schema()),
           "--append-system-prompt", system, "--max-budget-usd", f"{min(left, 3.0):.2f}",
           "--effort", "high"]
    if web:
        cmd += ["--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch", "WebFetch"]
    else:
        cmd += ["--tools", ""]
    last_err = ""
    for _ in range(2):
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, cwd=ROOT)
        try:
            data = json.loads(out.stdout)
        except json.JSONDecodeError:
            last_err = (out.stderr or out.stdout)[-2000:]
            continue
        _record(float(data.get("total_cost_usd") or 0))
        if data.get("is_error") or data.get("structured_output") is None:
            last_err = str(data.get("result"))[-2000:]
            continue
        return schema.model_validate(data["structured_output"])
    raise RuntimeError(f"Claude yanıtı alınamadı: {last_err}")


SERIES_START = """
SERİ KURALI: Konu tek videoya sığmayacak kadar zengin ve merak uyandıran bir devamı varsa (gizem, dönüm noktası, beklenmedik final)
bunu İKİ BÖLÜMLÜK seri yap: series_part=1, başlığın sonuna " (1. Bölüm)" ekle, hikâyeyi en heyecanlı yerde kes ve son sahnede
çözümü SÖYLEME; son cümle merak bırakan bir soru ya da yarım kalan bir an olsun, ardından "Devamı ikinci bölümde." de
(bu bölümde yorum çağrısı yerine bu cümleyi kullan). next_part_brief alanına 2. bölümün içeriğini yaz.
Konu tek videoda doyurucu biçimde bitiyorsa series_part=0 bırak; seriyi zorlama."""


def series_ask(prev: dict) -> str:
    return (f"Bu video iki bölümlük serinin 2. BÖLÜMÜ. 1. bölümün başlığı: {prev['title']}\n"
            f"1. bölümün konusu: {prev['topic']}\n1. bölümün dış sesi: {prev.get('narration', '')}\n"
            f"2. bölümde anlatılacaklar: {prev['brief']}\n"
            "Kurallar: series_part=2, başlığın sonuna \" (2. Bölüm)\" ekle. İlk cümle 1. bölümün kaldığı yeri tek bir vurucu "
            "cümleyle hatırlatsın (ör. 'Tank patladığında asıl felaket daha yeni başlıyordu.'), 1. bölümü yeniden anlatma; "
            "videonun çoğu yeni bilgi ve final olsun. Sonda normal yorum çağrısı yap. Kategori, şablon ve anlatım kalıbı 1. "
            f"bölümle aynı kalsın: category={prev.get('category', '')}, template={prev.get('template', '')}, "
            f"structure={prev.get('structure', 'hikaye')}.")


def recent_structures(history_file: Path, n: int = 3) -> list[str]:
    out = []
    if history_file.exists():
        for line in history_file.read_text(encoding="utf-8").splitlines():
            try:
                st = json.loads(line).get("structure")
            except Exception:  # noqa: BLE001
                continue
            out.append(st or "hikaye")  # eski videolar kalıp kaydı yokken hep hikâye anlatımıydı
    return out[-n:]


def allowed_structures(history_file: Path) -> list[str]:
    """Son kullanılan kalıp tekrar edilmez; 'hikaye' son 3 videonun 2'sinde kullanıldıysa o da dışarıda kalır."""
    last = recent_structures(history_file)
    out = [k for k in STRUCTURES if not (last and k == last[-1])]
    if last.count("hikaye") >= 2:
        out = [k for k in out if k != "hikaye"]
    return out or list(STRUCTURES)


def structure_ask(keys: list[str]) -> str:
    return ("\nANLATIM KALIBI: Şu kalıplardan konuya en uygun olanını seç, 'structure' alanına anahtarını yaz ve gövdeyi "
            "ona göre kur (kanca, Makas'ın yorumu ve kapanış kuralları her kalıpta geçerli):\n"
            + "\n".join(f"- {k}: {STRUCTURES[k][1]}" for k in keys))


def generate_script(history_file: Path, topic_hint: str | None = None,
                    templates: dict[str, str] | None = None, series_prev: dict | None = None,
                    allow_series: bool = False) -> ShortScript:
    used = _history(history_file)[-200:]
    if series_prev:
        ask = series_ask(series_prev)
    else:
        ask = (
            f"Bugün için yeni bir short senaryosu yaz. Konu önerisi: {topic_hint}." if topic_hint else
            "Bugün için yeni bir short senaryosu yaz. Şu kategorilerden birini seç ve az bilinen, şaşırtıcı, "
            f"doğrulanabilir bir hikâye bul: {', '.join(CATEGORIES)}. Konuların yaklaşık yarısı Türkiye bağlantılı olmalı; "
            "izleyicinin arkadaşına göndereceği türden bir konu seç (efsane-gerçek, futbol, gündelik hayattan şaşırtıcı nedenler)."
        )
        ask += structure_ask(allowed_structures(history_file))
        if allow_series:
            ask += SERIES_START
    if templates:
        ask += "\nGörsel şablonlardan konuya en uygun olanını 'template' alanına yaz:\n" + "\n".join(
            f"- {k}: {v}" for k, v in templates.items())
    if used and not series_prev:
        ask += "\nDaha önce işlenen konuları tekrar etme:\n- " + "\n- ".join(used)
    script = ask_claude(ask, ShortScript, SYSTEM)
    part, brief = (2, "") if series_prev else (script.series_part if allow_series else 0, script.next_part_brief)
    phrase = script.search_phrase
    checked = verify_script(script)
    # doğrulayıcı kalıbı gerekçeyle değiştirebilir: etiket son metne uysun diye doğrulanmış hâlin kalıbı kullanılır
    structure = series_prev.get("structure", checked.structure) if series_prev else checked.structure
    out = polish_script(checked)
    out.series_part, out.next_part_brief = part, (brief if part == 1 else "")
    out.structure, out.search_phrase = structure, out.search_phrase or phrase
    out.hashtags = [t for t in (re.sub(r"\W", "", h) for h in out.hashtags) if t]
    return out


class Review(BaseModel):
    ok: bool
    problems: List[str]
    fixed: ShortScript


def verify_script(script: ShortScript) -> ShortScript:
    """İkinci geçiş: bilgileri web aramasıyla doğrular, hataları düzeltir veya çıkarır."""
    review = ask_claude(
        "Aşağıdaki senaryodaki her olgusal iddiayı (tarih, sayı, isim, alıntı) web aramasıyla kontrol et. "
        "Yanlış ya da doğrulanamayan her bilgiyi düzelt veya çıkar, biçim kurallarına uymayan yerleri düzelt "
        "(özellikle toplam dış ses 78 kelimeyi geçmesin, ilk cümle en fazla 10 kelimelik doğrudan bir kanca olsun, search_phrase "
        "ilk iki cümlede ve başlıkta geçsin; boş sahne kalmasın). Seçilen anlatım kalıbını (structure) koru; yalnız konu o "
        "kalıba gerçekten uymuyorsa değiştir ve structure alanını da buna göre güncelle. "
        "Kullandığın güvenilir kaynakları 'sources' alanına URL olarak yaz. Düzeltilmiş tam senaryoyu 'fixed' "
        "alanında döndür.\n\n" + script.model_dump_json(indent=1),
        Review, SYSTEM + "\n\nŞimdi editör ve doğruluk kontrolcüsüsün.", web=True)
    if review.problems:
        print("Doğrulama notları:", *review.problems, sep="\n - ")
    return review.fixed


EDITOR = """Sen deneyimli bir Türk belgesel metin yazarı ve dil editörüsün. Görevin, sana verilen kısa video senaryosunun dış sesini
(narration alanları) Türkçe dil ve akış açısından kusursuz hâle getirmek.
- Sahnelerin narration'larını art arda okuyunca TEK, akıcı bir belgesel metni çıkmalı. Kopuk, yüklemsiz, telgraf üslubu
  parçaları tam cümlelere çevir; cümleleri bağlaçlarla birbirine bağla; çeviri kokan ifadeleri doğal Türkçeyle değiştir.
- Yazım, noktalama, ek ve zaman uyumunu düzelt. Anlatı zamanı tutarlı olsun.
- YENİ BİLGİ EKLEME, hiçbir olguyu (tarih, sayı, isim) değiştirme ya da çıkarma. Sahne sayısını ve sırasını koru.
- Toplam dış ses 65-75 kelime arasında kalsın (78'i geçmesin).
- search_phrase ifadesi ilk iki cümlede geçiyorsa koru, çıkarma.
- İlk cümle (kanca) en fazla 10 kelime, doğrudan ve şaşırtıcı kalsın; dönüş ilk cümlede kalsın, önüne giriş cümlesi ekleme.
- İlk sahnenin headline'ı özneyi ve dönüşü birlikte söylesin (kim/ne + ne oldu); öznesiz bırakma.
- Senaryonun structure alanına göre: neden ise ilk cümle ve ilk headline soru olarak kalabilir, cevabı öne taşıma;
  sayac ise en tuhaf bilgiyi öne taşıma (sonda kalsın); efsane ise ilk cümle inanışı ve yanlış (ya da şaşırtıcı biçimde
  doğru) olduğunu birlikte söylesin, doğrulanmış sonucu tersine çevirme.
- series_part 2 ise ilk cümle 1. bölümün kaldığı yeri hatırlatan cümle olarak kalsın; kalıba özel ilk cümle kuralını
  uygulama, 1. bölümü yeniden anlatma.
- headline satırları, değişen narration'da geçen kelimelerden oluşsun (BÜYÜK HARF, satır başı 1-3 kelime).
- Görsel alanlarına (theme, image_mode, image_queries, illustration, motion, trail, icon) DOKUNMA.
Düzeltilmiş tam senaryoyu döndür."""


class Polished(BaseModel):
    notes: List[str] = Field(description="Yapılan önemli dil düzeltmeleri, kısa")
    fixed: ShortScript


def polish_script(script: ShortScript) -> ShortScript:
    """Üçüncü geçiş: belgesel dili ve akış için Türkçe editör (web araması yok)."""
    res = ask_claude("Bu senaryonun dış sesini düzelt:\n\n" + script.model_dump_json(indent=1), Polished, EDITOR)
    if res.notes:
        print("Dil düzeltmeleri:", *res.notes[:12], sep="\n - ")
    fixed = res.fixed
    if len(fixed.scenes) != len(script.scenes):  # güvenlik: sahne yapısı bozulduysa yalnız metinleri al
        return script
    for a, b in zip(script.scenes, fixed.scenes):  # görsel alanları kesin olarak koru
        for f in ("theme", "image_mode", "image_query", "image_queries", "illustration", "motion", "trail", "icon", "anim_query",
                  "card", "card_value", "card_label", "card_myth", "card_fact", "card_note", "mascot"):
            setattr(b, f, getattr(a, f))
    fixed.sources, fixed.category = script.sources, script.category
    fixed.search_phrase, fixed.structure = script.search_phrase, script.structure
    return fixed


def load_script(path: Path) -> ShortScript:
    return ShortScript.model_validate_json(path.read_text(encoding="utf-8"))
