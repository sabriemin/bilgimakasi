"""Konu seçimi ve senaryo üretimi.

Claude'a Claude Code CLI üzerinden erişilir: önce ANTHROPIC_API_KEY (aboneliğin aylık API kredisi), yoksa
CLAUDE_CODE_OAUTH_TOKEN (abonelik). Yapılandırılmış çıktı için --json-schema kullanılır. Doğrulama adımı web araması yapabilir.
Harcama tavanı: state/claude_usage.json içinde dönem başına tutulan maliyet CLAUDE_MONTHLY_BUDGET_USD'yi (varsayılan 90 $)
aşarsa üretim durur. Dönem, API kredisinin yenilendiği gün (CLAUDE_BUDGET_RESET_DAY, varsayılan 24) başlar.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
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


# Rakamlı serilerin (Ya sen olsaydın?) güncel yılı: rakamlar bu yılın Türkiye verileriyle araştırılır.
YIL = dt.date.today().year

# Nasıl yapılır? içecek tarifleri. False: alkollü içecek tarifi önerilmez ve yazılmaz (kokteyller alkolsüz). True:
# alkollü tarif yazılabilir; senaryo 'alkollu' alanını işaretler ve açıklamaya publish.ALKOL_UYARI satırı ("18 yaş altı
# için uygun değildir; sorumlu tüketin.") kendiliğinden eklenir. Değer bu dosyada değiştirilir: öneri, senaryo ve
# doğrulama yönergeleri modül yüklenirken buna göre kurulur.
ALKOLLU_ICECEK = False


def nasil_alanlari(alkol: bool = ALKOLLU_ICECEK) -> list[str]:
    """Nasıl yapılır? serisinin konu alanları (öneri yönergesi: 3 önerinin her biri farklı bir alandan)."""
    return [
        "ev işleri ve temizlik",
        "alet kullanımı: temel el aletleri ve ev tipi aletler (tornavida, matkapla dübel takma, su terazisi, metre, "
        "silikon tabancası, pense)",
        "yemek ve mutfak: kısa tarifler, mutfak teknikleri, Türk mutfağı",
        ("kokteyl ve içecekler: alkolsüz kokteyl (mocktail), limonata, şerbet, ev yapımı soğuk kahve; alkollü kokteyl "
         "de olabilir" if alkol else
         "alkolsüz kokteyl ve içecekler: mocktail, limonata, şerbet, ev yapımı soğuk kahve"),
        "öğrenciler için: ders çalışma, not tutma, yurt ya da küçük oda düzeni, az malzemeyle hızlı yemek",
        "evi çekip çevirenler ve ev hanımları için pratikler: çamaşır, ütü, leke çıkarma, dolap ve mutfak düzeni",
    ]


def nasil_yasak(alkol: bool = ALKOLLU_ICECEK) -> str:
    """Nasıl yapılır? serisinde önerilmeyecek ve senaryoda bulunmayacak alanlar (öneri, senaryo ve doğrulama aynı
    listeyi kullanır). Olağan tarif adımları, tek başına kullanılan tek bir temizlik ürünü ya da mutfak malzemesi ve
    temel el aletleri serbesttir; alkollü içecek tarifi yalnız ALKOLLU_ICECEK True iken."""
    return ("tıbbi ya da sağlık tedavisi, ilaç, tehlikeli ya da yasa dışı işler, finansal/yatırım ya da hukuki tavsiye, "
            "uzmanlık gerektiren işler; temizlik ürünlerini ya da kimyasalları (çamaşır suyu, tuz ruhu, kireç çözücü, "
            "amonyak) birbiriyle ya da herhangi bir şeyle (sirke ve limon dahil) karıştırma (tek bir ürünü etiketindeki "
            "talimatla tek başına kullanmak ya da sirke, karbonat, limon gibi mutfak malzemeleriyle temizlik serbest); "
            "gıda güvenliği iddiaları (bozulmuş yiyeceği kurtarma, pişmiş yemeği saklama ya da yeniden ısıtma, son "
            "kullanma tarihi); kızgın yağ, alev ya da açık ateşle ilgili püf noktaları (ocakta ya da fırında olağan "
            "pişirme, olağan kızartma ve su kaynatma hariç); elektrik tesisatı (priz, sigorta, kablo bağlama), gaz "
            "tesisatı ya da tüp, pil, yüksekte çalışma, ağır elektrikli aletler (taşlama, motorlu testere); çocuk ya da "
            "evcil hayvan bakımı; başkasının konumunu, mesajlarını ya da hesabını izleme ve güvenlik önlemlerini aşma; "
            + ("alkolü özendiren ya da aşırı tüketimi öven anlatım" if alkol else
               "alkollü içecek tarifi (kokteyl ve içecekler alkolsüz)"))


NASIL_YASAK = nasil_yasak()
# alet ve tarif adımlarının ortak kuralı (kalıp tanımı ve Adım kartları düzeni aynı cümleyi kullanır)
NASIL_GUVENLIK = ("Alet kullanılan işte kısa bir güvenlik notu bir adımın dış sesinde (narration) söylensin (ör. "
                  "koruyucu gözlük; duvarı delmeden önce kablo ve boru kontrolü); Adım kartlarında ayrıca callout "
                  "olarak da yazılabilir ama yalnız callout'ta kalmasın. Tariflerde miktar, sıcaklık ve süreler kesin "
                  "ve doğrulanmış olsun.")
# senaryonun 'alkollu' alanı: açıklamadaki yaş uyarısı bu alana bağlı (ALKOLLU_ICECEK kapalıyken alan hep false)
NASIL_ALKOL = (" Tarif alkollü bir içecekse 'alkollu' alanını true yap; açıklamaya yaş uyarısı kendiliğinden eklenir."
               if ALKOLLU_ICECEK else "")

# Nasıl üretiliyor? serisinde önerilmeyecek ve senaryoda bulunmayacak alanlar (öneri, senaryo ve doğrulama aynı listeyi
# kullanır)
URETIM_YASAK = ("silah, mühimmat ve patlayıcılar, uyuşturucu, alkol ve tütün ürünleri, tehlikeli kimyasalların evde "
                "yapımı, hayvan kesiminin ayrıntısı, izleyiciyi endüstriyel bir süreci evde denemeye teşvik etme, bir "
                "markanın gizli tarifini ya da formülünü kesin bilgi gibi sunma")

# Ya sen olsaydın? serisinde önerilmeyecek ve senaryoda bulunmayacak alanlar (öneri, senaryo ve doğrulama aynı listeyi
# kullanır)
OLSAYDIN_YASAK = ("yasa dışı ya da ruhsatsız işler, kumar ve bahis siteleri, alkol ya da tütün satışına dayanan işler, "
                  "kripto para, borsa, forex ve her tür yatırım ürünü, saadet zinciri ve ağ pazarlaması (MLM), kredi "
                  "çekme tavsiyesi, vergi kaçırma ya da kayıt dışı kazanç, gerçek bir kişinin ya da işletmenin gelirini "
                  "ifşa etme, garanti kazanç iddiası, sağlık ve tıbbi senaryolar, siyasi kutuplaştırıcı açılar")

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
    "nasil": ("NASIL YAPILIR?", "NASIL YAPILIR: ilk sahne kanca: ilk cümlede ulaşılacak sonucu ya da çözülen sorunu söyle "
              "('Muzları bir hafta taze tutmanın sırrı sapında.') → 3-5 numaralı, somut adım; her adım TEK sahne olsun "
              "(step alanı 1, 2, 3...; headline'ın ilk satırı 'ADIM 1', 'ADIM 2' diye adım numarası, sonraki satır(lar) "
              "adımın kendisi, ör. 'ADIM 1' / 'SAPI SAR') → son sahne özet: yöntemin neden işe yaradığını (şaşırtıcı ya da "
              "bilimsel nedenini) tek cümlede söyle. Adımlar evde, güvenle ve özel beceri gerektirmeden yapılabilsin. "
              + NASIL_GUVENLIK + NASIL_ALKOL + " Şu alanlara giren adım YOK: " + NASIL_YASAK + "."),
    "uretim": ("NASIL ÜRETİLİYOR?", "NASIL ÜRETİLİYOR: tek bir gündelik ürünün hammaddeden bitmiş ürüne yolculuğu "
               "(belgesellerdeki 'nasıl yapılmış' tarzı). İlk sahne kanca: ilk cümlede ürünle ilgili şaşırtıcı bir gerçek "
               "ya da soru ('Kurşun kalemin içinde tek gram kurşun yok.') → 3-5 üretim aşaması, gerçek sırasıyla; her "
               "aşama TEK sahne olsun (step alanı 1, 2, 3...; headline'ın ilk satırı 'AŞAMA 1', 'AŞAMA 2' diye aşama "
               "numarası, sonraki satır(lar) aşamanın kendisi, ör. 'AŞAMA 2' / 'GRAFİT PİŞİRİLİR'); aşamalar geniş "
               "zaman edilgen çatıyla anlatılır ('Grafit kille karıştırılıp fırında pişirilir.') → son sahne ölçek: "
               "ürünün yılda kaç tane üretildiği ya da Türkiye'nin üretimi, ardından kısa bir soru. Sıcaklık, süre ve "
               "miktarlar doğrulanmış olsun; süreç izleyicinin evde deneyeceği bir şey gibi anlatılmasın. Şu alanlara "
               "giren konu ve ayrıntı YOK: " + URETIM_YASAK + "."),
    "olsaydin": ("YA SEN OLSAYDIN?", "YA SEN OLSAYDIN: izleyiciyi ikinci tekil şahısla somut bir duruma koy: bir meslek "
                 "ya da iş ('Kuyumcu olsaydın'), bir para ya da hayat olayı ('Piyango sana çıksaydı') ya da bir hayat "
                 "durumu ('Yurt dışına taşınsaydın'); konu yalnız para değil, 'Elektrikçi olsaydın günün nasıl geçerdi' gibi bir "
                 "gün de olabilir. İlk cümle izleyiciyi duruma koyup çarpıcı bir rakam ya da an versin → 3-4 durak: para "
                 f"konusunda her biri {YIL} Türkiye'sine ait somut bir rakamla (işe nasıl girilir ya da ilk adım, bir gün ya "
                 "da ilk ay, gelir ve giderler ya da paranın neye yettiği, olasılık), gün akışında her biri günün bir "
                 "saatinde gerçekçi bir an → içeriden bilinen ya da şaşırtıcı "
                 "bir ayrıntı → son sahne 'Sen olsan ne yapardın? Yorumlara yaz.' ile bitsin. Rakamlar yuvarlanmış ve "
                 "resmî ya da güvenilir kaynaktan olsun; tahminse 'yaklaşık' ya da 'tahmini' de. Şu alanlara giren konu ve "
                 "açı YOK: " + OLSAYDIN_YASAK + "."),
}
# Yalnız açıkça istendiğinde (öneriden üretim: --structure) kullanılan kalıplar: otomatik dönüşüme girmez.
FORCED_ONLY = {"nasil", "uretim", "olsaydin"}
# Senaryosu web aramasıyla araştırılarak yazılan kalıplar (süreç bilgileri ve güncel rakamlar)
WEB_KALIPLARI = {"uretim", "olsaydin"}
# Adım kartlarıyla (nasil kurgu modülü) çizilen kalıplar ve başlıktaki numaranın kelimesi ('ADIM 2' / 'AŞAMA 2')
ADIM_KELIMESI = {"nasil": "ADIM", "uretim": "AŞAMA"}


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
    card: Literal["auto", "photo", "drawing", "counter", "compare", "quote", "interstitial", "cta", "receipt"] = Field(
        default="auto", description="Kart şablonunda bu sahnenin kartı; çoğu sahnede auto.")
    card_value: str = Field(default="", description=(
        "counter kartı: sayılacak sayı, ör. '3.300' ya da '%90' (olsaydin kalıbında birimiyle, ör. '1,2 MİLYON ₺')."))
    card_label: str = Field(default="", description="counter: sayının etiketi (ör. 'YIL ÖNCE'); quote: alıntının kendisi.")
    card_myth: str = Field(default="", description="compare: yaygın inanış, en fazla 6 kelime.")
    card_fact: str = Field(default="", description="compare: doğrusu, en fazla 6 kelime.")
    card_note: str = Field(default="", description="Kartın küçük notu ya da kaynağı (ör. 'NASA arşivi · 1999'), en fazla 32 karakter.")
    card_lines: List[str] = Field(default_factory=list, description=(
        "Yalnız olsaydin kalıbının hesap fişi (receipt) kartı: 2-5 satır, her biri 'KALEM|TUTAR' (ör. "
        "'KİRA + DEPOZİTO|135.000 ₺'); toplam card_value'da (ör. '420.000 ₺'), etiketi card_label'da ('TOPLAM'), "
        "kaynak ya da tarih card_note'ta ('Tahmini · Kasım 2026'). Diğer kalıplarda ve diğer kartlarda boş."))
    mascot: Literal["auto", "normal", "surprised", "thinking", "happy"] = Field(
        default="auto", description="Kart şablonunda maskot Makas'ın ifadesi; çoğu sahnede auto.")
    # Yalnız 'nasil' kalıbı (Nasıl yapılır? / "nasil" şablonu) kullanır; eski senaryolar için isteğe bağlı.
    step: int = Field(default=0, ge=0, description=(
        "Yalnız nasil kalıbı: bu sahnenin adım numarası (1, 2, 3...); kanca ve özet sahnelerinde 0. Diğer kalıplarda 0."))
    callouts: List[str] = Field(default_factory=list, description=(
        "Yalnız nasil kalıbının adım sahneleri: çizimin üstüne konacak en fazla 2 küçük not etiketi, her biri en fazla "
        "3 kelime/18 karakter, BÜYÜK HARF (ör. 'TAŞMA SINIRI', '12-15 DK'). Çoğu sahnede boş."))
    # --- dosya şablonu ---
    delil: int = Field(default=0, ge=0, description=(
        "Yalnız Dava Dosyası şablonu (efsane kalıbı): bu sahnenin delil numarası (1, 2, 3...); aynı delilin devam "
        "sahnesi aynı numarayı alır. Kanca, iddia, ara ve hüküm sahnelerinde 0. Diğer şablonlarda 0."))


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
    alkollu: bool = Field(default=False, description=(
        "Yalnız nasil kalıbı: tarif alkollü bir içecek içeriyorsa true (açıklamaya yaş uyarısı eklenir). Diğer "
        "durumlarda false."))
    # --- dosya şablonu ---
    hukum: Literal["", "EFSANE", "GERÇEK", "KISMEN DOĞRU"] = Field(default="", description=(
        "Yalnız efsane kalıbı (Dava Dosyası şablonu): inanışın hükmü; inanış yanlışsa EFSANE, doğruysa GERÇEK, bir "
        "kısmı doğruysa KISMEN DOĞRU. Diğer kalıplarda boş."))


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
   bir iddia olsun, en tuhaf bilgi yine en sonda gelsin; nasıl yapılır kalıbında ilk cümle sonucu ya da sorunu ve
   şaşırtıcı çözüme işaret eden ipucunu söylesin ("Muzları bir hafta taze tutmanın sırrı sapında."). Serinin 2.
   bölümünde (series_part 2) ilk cümle 1. bölümün kaldığı yeri hatırlatan cümle olarak kalsın; kalıba özel ilk cümle
   kuralları uygulanmaz. Giriş, selam, "biliyor muydunuz" veya bağlam cümlesi YOK. İlk cümle en fazla 10 kelime olsun;
   ilk cümleyi bölme, tamamı ilk sahnede olsun.
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
headline kelimeleri narration içinde geçen en vurucu kelimeler olsun (nasıl yapılır kalıbının 'ADIM 1' gibi adım
numaraları hariç). Temaları çeşitlendir, art arda aynı temayı en fazla iki kez kullan. icon sadece gerçekten anlam katıyorsa."""


# Yalnız kart şablonu açıkken (ya da elle seçildiğinde) sisteme eklenir: kapalıyken üretim yönergesi değişmez.
KART_RULES = """KART ALANLARI (yalnız "kart" şablonu kullanır, diğer şablonlar yok sayar; emin değilsen card "auto", diğerleri boş):
- card "counter": tek büyük sayının sahnesi (card_value yalnız sayı, ör. "3.300"; card_label 1-3 kelimelik birim/etiket).
- card "compare": efsane kalıbında inanışın çürütüldüğü sahne (card_myth inanış, card_fact doğrusu).
- card "interstitial": videonun ortasındaki ikinci merak anı (headline o anın kendi vurucu kelimeleri; kalıp cümle değil).
- card "quote": doğrulanmış kısa bir alıntı (card_label alıntı, card_note kim · yıl). card "cta": son soru sahnesi.
- card_note kartın küçük notu ya da kaynağıdır. mascot çoğunlukla auto.
- nasil kalıbında adım sahnelerinin card'ı auto (fotoğraf/çizim) kalsın; adım numarasını counter kartına koyma.
Kart alanları görsel alanların yerine geçmez; her sahnede fotoğraf/çizim kuralı aynen geçerli.
Kartlardaki sayı, inanış ve alıntılar da doğrulanmış bilgi olmalı."""


# Yalnız 'nasil' kalıbında sisteme eklenir (Nasıl yapılır? serisi); diğer kalıpların yönergesi değişmez.
NASIL_RULES = """NASIL YAPILIR? DÜZENİ (yalnız 'nasil' kalıbı; video "Adım kartları" ekranlarıyla kurulur, her sahne bir ekrandır):
- Sahne sayısı = adım sayısı + 2 (5-7 sahne); genel kuraldaki 9-12 sahne bu kalıpta geçerli değil. Her sahnenin
  narration'ı tam cümle(ler)le başlayıp biter; genel kuraldaki gibi bir cümleyi sahneler arasında BÖLME (her ekran
  kendi cümlesini yazar). Sıra:
  1) KANCA (ilk sahne, step 0): narration'ın ilk cümlesi sonucu ya da sorunu ve çözüme işaret eden ipucunu söyler (en
     fazla 10 kelime, ör. "Muzları bir hafta taze tutmanın sırrı sapında."). headline ekranda büyük yazılan SORUDUR
     (2-3 satır, satır başı 1-3 kelime, ör. "MUZ NASIL" / "BİR HAFTA" / "TAZE KALIR?"; bu başlığın kelimeleri dış seste
     geçmeyebilir; adım sayısını yazma, "4 ADIM" ekranda kendiliğinden çıkar), highlight_line en vurucu satır.
     illustration sonucu ya da sorunu gösteren tek, net çizim.
  2) ADIMLAR (3-5 sahne, her adım TEK sahne, doğru sırada): step 1, 2, 3...; headline'ın ilk satırı 'ADIM n', sonraki
     1-2 satır adımın kendisi, emir kipinde 2-5 kelime (ör. "ADIM 2" / "SAPI STREÇLE"). narration 1-2 kısa cümle
     (8-14 kelime): adımı ve kısa püf noktasını ya da nedenini söyler; "Önce", "Ardından", "Son olarak" gibi
     bağlaçlarla akar. Bu metin Makas'ın konuşma balonunda kelime kelime yazılır: kısa ve sade olsun.
     illustration: adımın nesnesini ya da hareketini gösteren yalın, düz bir çizim (ör. "a bunch of bananas whose stems
     are wrapped in plastic film"); çizimde yazı olmaz. callouts: çizimin üstündeki en fazla 2 küçük not (ölçü, süre,
     sınır; ör. "TAŞMA SINIRI", "12-15 DK"), gerekmiyorsa boş; başlıkta yazanı tekrarlamasın, her biri en fazla 3
     kelime. image_mode none, image_queries boş: bu şablon fotoğraf değil çizim kullanır. card auto.
  3) ÖZET (son sahne, step 0): narration önce yöntemin neden işe yaradığını tek cümlede söyler (şaşırtıcı ya da
     bilimsel neden; adımlardaki bir püf noktasına bağlansın), sonra kısa bir soru sorar ve "Yorumlara yaz." ile biter.
     Bu "neden" cümlesi Makas'ın yorumunun yerine geçer; ayrıca yorum cümlesi ekleme. headline işin 1-3 kelimelik
     kısa adı (ör. "MUZ SAKLAMA"; "ADIM" ya da adım sayısı yazma). Adımların listesi ekranda kendiliğinden çıkar;
     illustration boş kalabilir.
- Toplam dış ses genel kuraldaki gibi 65-75 kelime (78'i geçmesin): kanca ~10, her adım 8-14, özet 14-20 kelime.
- Sayı, süre ve miktarlar doğrulanmış olsun; adımlar evde güvenle uygulanabilsin. """ + NASIL_GUVENLIK + NASIL_ALKOL + \
    " Şu alanlara giren adım YOK: " + NASIL_YASAK + "."


# Yalnız 'uretim' kalıbı Adım kartlarıyla çizilecekse sisteme eklenir (Nasıl üretiliyor? serisi; NASIL_RULES'un
# aşamalı karşılığı). Diğer kalıpların yönergesi değişmez.
URETIM_RULES = """NASIL ÜRETİLİYOR? DÜZENİ (yalnız 'uretim' kalıbı; video "Adım kartları" ekranlarıyla kurulur, her sahne bir
ekrandır, adımların yerinde ürünün üretim AŞAMALARI vardır):
- Sahne sayısı = aşama sayısı + 2 (5-7 sahne); genel kuraldaki 9-12 sahne bu kalıpta geçerli değil. Her sahnenin
  narration'ı tam cümle(ler)le başlayıp biter; genel kuraldaki gibi bir cümleyi sahneler arasında BÖLME (her ekran
  kendi cümlesini yazar). Sıra:
  1) KANCA (ilk sahne, step 0): narration'ın ilk cümlesi ürünle ilgili şaşırtıcı bir gerçek ya da soru (en fazla 10
     kelime, ör. "Kurşun kalemin içinde tek gram kurşun yok."). headline ekranda büyük yazılan SORUDUR (2-3 satır,
     satır başı 1-3 kelime, ör. "KURŞUN KALEM" / "NASIL" / "ÜRETİLİYOR?"; bu başlığın kelimeleri dış seste geçmeyebilir;
     aşama sayısını yazma, "4 AŞAMA" ekranda kendiliğinden çıkar), highlight_line en vurucu satır. illustration ürünün
     kendisini gösteren tek, net çizim.
  2) AŞAMALAR (3-5 sahne, her aşama TEK sahne, üretimdeki gerçek sırayla): step 1, 2, 3...; headline'ın ilk satırı
     'AŞAMA n', sonraki 1-2 satır aşamanın kendisi, 2-5 kelime (ör. "AŞAMA 2" / "GRAFİT PİŞİRİLİR"). narration 1-2 kısa
     cümle (8-14 kelime), geniş zaman edilgen çatıyla ("Grafit kille karıştırılıp fırında pişirilir."); "Önce",
     "Ardından", "Son olarak" gibi bağlaçlarla akar. Bu metin Makas'ın konuşma balonunda kelime kelime yazılır: kısa ve
     sade olsun. illustration: aşamadaki makineyi ya da malzemeyi gösteren yalın, düz bir çizim (ör. "graphite and clay
     rods sliding into a glowing industrial kiln"); çizimde yazı olmaz. callouts: çizimin üstündeki en fazla 2 küçük
     not (sıcaklık, süre, miktar; ör. "1.000°C", "72 SAAT"), gerekmiyorsa boş; başlıkta yazanı tekrarlamasın, her biri
     en fazla 3 kelime. image_mode none, image_queries boş: bu şablon fotoğraf değil çizim kullanır. card auto.
  3) ÖLÇEK (son sahne, step 0): narration önce ölçeği tek cümlede söyler (dünyada yılda kaç tane üretildiği ya da
     Türkiye'nin üretimi), sonra kısa bir soru sorar ve "Yorumlara yaz." ile biter. Bu ölçek cümlesi Makas'ın yorumunun
     yerine geçer; ayrıca yorum cümlesi ekleme. headline ürünün 1-3 kelimelik kısa adı (ör. "KURŞUN KALEM"; "AŞAMA" ya
     da aşama sayısı yazma). Aşamaların listesi ekranda kendiliğinden çıkar; illustration boş kalabilir.
- Toplam dış ses genel kuraldaki gibi 65-75 kelime (78'i geçmesin): kanca ~10, her aşama 8-14, ölçek 14-20 kelime.
- Türkiye bağlantılı ürünler öncelikli (çay, fındık, lokum, cam, porselen, halı, bakır cezve, çini, nazar boncuğu, beyaz
  eşya); gündelik küresel ürünler de olur.
- Aşamaların sırası, süreç bilgileri (sıcaklık, süre, malzeme) ve ölçek sayıları üreticilerin ya da güvenilir
  kaynakların anlatımıyla doğrulanmış olsun; bir markanın tarifi kesin bilgi gibi sunulmasın. Şu alanlara giren ayrıntı
  YOK: """ + URETIM_YASAK + "."


# Yalnız 'olsaydin' kalıbında sisteme eklenir (Ya sen olsaydın? serisi, kart şablonu: sayaç kartları ve hesap fişi).
# Hesap fişi yönergesi yalnız burada: diğer kart videolarının yönergesi (KART_RULES) değişmez.
OLSAYDIN_RULES = f"""YA SEN OLSAYDIN? DÜZENİ (yalnız 'olsaydin' kalıbı; video kart şablonuyla kurulur):
- Konu her zaman para hesabı değildir. Üç türden biridir: (a) bir meslek ya da iş ('Kuyumcu olsaydın': işe nasıl
  girilir, bir iş günü, aylık gelir ve giderler, içeriden bir ayrıntı; ya da 'Elektrikçi olsaydın günün nasıl geçerdi':
  sabahtan akşama bir iş günü, işin zor ve güzel yanları, kimsenin bilmediği ayrıntılar); (b) bir para ya da hayat olayı ('Piyango sana çıksaydı': vergiden sonra eline geçen
  net tutar, o paranın neye yettiği, kazanma olasılığı, kazananların genelde ne yaptığı); (c) bir hayat durumu ('Yurt
  dışına taşınsaydın ilk ay kaç lira harcardın', 'Bir köyde yaşamaya başlasaydın').
- Dış ses izleyiciyle ikinci tekil şahısla ve şart kipiyle konuşur ('olsaydın', 'kazanırdın', 'öderdin'); belgesel
  ağırbaşlılığı sürer, abartı ve vaaz yok.
- KANCA: ilk cümle izleyiciyi duruma koyar ve çarpıcı bir rakam ya da çarpıcı bir an verir (en fazla 10 kelime).
  İlk headline durumu ve rakamı ya da anı söyler.
- GÜN AKIŞI ("günün nasıl geçerdi" konuları): 3-5 durak, her biri günün bir saati. kicker saat olur (ör. "07:30"),
  headline o saatte olan somut iş ya da an (ör. "İLK ARIZA", "ÇATIDA ÖĞLE"); dış ses o anı gerçekçi bir ayrıntıyla
  anlatır (kullanılan alet, tipik iş, iş güvenliği kuralı, müşteriyle bir an, yorgunluk ya da keyif). Para yalnız
  konunun parçasıysa geçer (ör. günün sonunda eline kalan); geçiyorsa aşağıdaki rakam kuralları geçerlidir.
- DURAKLAR (para konuları: gelir, gider, ikramiye, maliyet): 3-4 durak, her biri somut bir rakama dayanır. Rakamın sahnesi card "counter" olur: card_value rakamın
  kendisi birimiyle (ör. "1,2 MİLYON ₺", "%25", "18 AY"), card_label 1-3 kelimelik etiket (ör. "AYLIK KİRA"). Bu kalıpta
  bu kural KART ALANLARI'ndaki genel counter kuralının yerine geçer: birim card_value'da kalır, card_label'a yazılmaz.
- HESAP FİŞİ (para konuları; gün akışı konusunda para geçmiyorsa fiş yok): en az bir sahne card "receipt" olur. card_lines 2-5 satır, her satır "KALEM|TUTAR" (ör. "KİRA +
  DEPOZİTO|135.000 ₺"; kalem BÜYÜK HARF, en fazla 22 karakter; düşülen tutar eksiyle, ör. "VERGİ|-200.000 ₺").
  Satırların toplamı card_value'ya tam eşit olur (ör. "420.000 ₺"); card_label "TOPLAM" ya da benzeri ("AYLIK GİDER",
  "ELİNE KALAN"); card_note kaynak ve tarih (ör. "Tahmini · Kasım {YIL}"). Fişin sahnesinde dış ses toplamı söyler.
- Videonun ortasında içeriden bilinen ya da şaşırtıcı bir ayrıntı olur (ikinci merak anı; card "interstitial" olabilir).
- KAPANIŞ: Makas'ın yorumu tek kısa cümle; son sahne "Sen olsan ne yapardın? Yorumlara yaz." ile biter (card "cta").
- GERÇEKLİK: gün akışındaki işler, saatler ve kurallar da gerçektir (meslek odaları, MEB meslek tanımları, iş
  güvenliği mevzuatı, meslek sahiplerinin anlatımları); uydurma ayrıntı ya da abartılı tehlike yok.
- RAKAMLAR: hepsi {YIL} Türkiye'sine aittir ve web aramasıyla bulunur; yuvarlanır (ör. "yaklaşık 48 bin lira"), tahminse
  "yaklaşık" ya da "tahmini" denir; şehre göre değişiyorsa şehir adı söylenir. Kaynaklar resmî ya da saygın olur:
  Resmî Gazete, ÇSGB ve SGK (asgari ücret, işveren maliyeti), TÜİK, Milli Piyango'nun resmî ikramiye ve olasılık
  tabloları, meslek odaları, ilan sitelerinin ortalamaları; hepsi sources alanına yazılır. Gelir anlatılıyorsa giderler
  de anlatılır ve "eline kalan" gelir eksi gidere eşit olur; dış sesteki rakamlar kartlardakilerle aynıdır.
- Şans oyunu konularında kazanma olasılığı açıkça söylenir; oynamaya özendiren ya da "sen de dene" diyen cümle yok.
- Yatırım, kredi ya da vergi tavsiyesi verilmez. Açıklamaya rakamların yaklaşık olduğunu ve yatırım tavsiyesi
  olmadığını söyleyen satır kendiliğinden eklenir: description alanına yazma.
- Şu alanlara giren konu, açı ve ayrıntı YOK: """ + OLSAYDIN_YASAK + "."


def kalip_kurallari(yapi: str | None, adim_kartlari: bool) -> str:
    """Kalıba özel ek yönerge (sistem istemine eklenir): nasil ve uretim yalnız Adım kartlarıyla çizilecekse ekran
    düzenini (NASIL_RULES / URETIM_RULES), olsaydin her zaman kendi düzenini (OLSAYDIN_RULES) ister. Diğer kalıplarda
    boş: yönergeleri değişmez."""
    if yapi == "olsaydin":
        return "\n" + OLSAYDIN_RULES
    if adim_kartlari and yapi == "nasil":
        return "\n" + NASIL_RULES
    if adim_kartlari and yapi == "uretim":
        return "\n" + URETIM_RULES
    return ""


# Başlıktaki adım (uretim'de aşama) işareti: 'ADIM 2', 'ADIM 2:', '2. ADIM', 'AŞAMA 2', '2. AŞAMA'. Ters biçimde sıra
# noktası şart: '4 ADIM' / '4 AŞAMA' adım sayısıdır (kanca ya da özet başlığı), adım işareti değil.
ADIM_RE = re.compile(r"^\s*(?:(?:ADIM|AŞAMA)\s*(\d+)|(\d+)\s*\.\s*(?:ADIM|AŞAMA))\b[\s:.,\-–—]*")


def _tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def adim_isaretleri(steps: list[int], first_lines: list[str]) -> list[int]:
    """Sahnelerin ham adım işaretleri (0: adımsız). step alanı her sahnede geçerlidir; yoksa başlığın ilk satırındaki
    'ADIM n' (uretim'de 'AŞAMA n') okunur, ama 3+ sahnelik senaryoda ilk (kanca) ve son (özet) sahnede okunmaz:
    kancanın ya da özetin başlığı adımı sanılıp düzen kaymasın."""
    n = len(steps)
    out = []
    for i, (st, line) in enumerate(zip(steps, first_lines)):
        if st and st > 0:
            out.append(int(st))
            continue
        m = ADIM_RE.match(_tr_upper((line or "").strip())) if (n < 3 or 0 < i < n - 1) else None
        out.append(int(m.group(1) or m.group(2)) if m else 0)
    return out


def adim_gruplari(raw: list[int]) -> tuple[list[int], list[tuple[int, list[int]]], list[int]]:
    """Ham adım işaretlerinden (kanca sahneleri, [(adım sırası, sahneler)], özet sahneleri). İlk adımdan önceki sahneler
    kanca; aynı adımın art arda sahneleri ve iki adım arasındaki adımsız sahne o adımın devamı; son adımdan sonraki
    adımsız sahneler de son adımın devamıdır, yalnız en son sahne özettir. Adım işareti yoksa adım listesi boştur."""
    marked = [i for i, r in enumerate(raw) if r]
    if not marked:
        return list(range(len(raw))), [], []
    first, last = marked[0], marked[-1]
    end = max(last, len(raw) - 2)          # özet yalnız en son sahne (adım son sahnede bitmiyorsa)
    groups: list[tuple[int, list[int]]] = []
    prev = None
    for i in range(first, end + 1):
        if raw[i] and raw[i] != prev:
            groups.append((len(groups) + 1, [i]))
            prev = raw[i]
        else:
            groups[-1][1].append(i)
    return list(range(first)), groups, list(range(end + 1, len(raw)))


def normalize_nasil(script: ShortScript) -> ShortScript:
    """Adım kartlı kalıpların (nasil: Nasıl yapılır?, uretim: Nasıl üretiliyor?) adım düzenini sağlamlaştırır (yerinde;
    başka kalıba dokunmaz): adım numarası step alanından, yoksa başlığın ilk satırındaki 'ADIM n' / 'AŞAMA n'den okunur
    (adim_isaretleri) ve 1'den sırayla yeniden verilir; sahneler adim_gruplari ile kanca / adım / özet olarak ayrılır
    (adımsız ara sahneler adımın devamıdır). Her adımın ilk sahnesinin başlığı kalıbın kelimesiyle ('ADIM n', uretim'de
    'AŞAMA n') başlar (kart şablonu sağ üstte adım numarasını bu satırdan okur)."""
    kelime = ADIM_KELIMESI.get(script.structure)
    if not kelime:
        return script
    raw = adim_isaretleri([sc.step for sc in script.scenes], [(sc.headline or [""])[0] for sc in script.scenes])
    hook, groups, recap = adim_gruplari(raw)
    if not groups:
        return script
    for n, idx in groups:
        for i in idx:
            _adim_basligi(script.scenes[i], n, new=(i == idx[0]), kelime=kelime)
    for i in hook + recap:
        script.scenes[i].step = 0
    return script


def _adim_basligi(sc: Scene, n: int, new: bool, kelime: str = "ADIM") -> None:
    """Sahnenin adım numarasını ve başlığındaki 'ADIM n' (ya da 'AŞAMA n') satırını n'e çeker; adımın ilk sahnesi bu
    satırla başlar. Başlıkta öteki kelime yazılmışsa ('ADIM 2' yerine 'AŞAMA 2') kalıbın kelimesine çevrilir."""
    sc.step = n
    head = list(sc.headline or [])
    m = ADIM_RE.match(_tr_upper(head[0].strip())) if head else None
    if m:
        rest = head[0].strip()[m.end():].strip()
        head[0:1] = [f"{kelime} {n}"] + ([_tr_upper(rest)] if rest else [])
        if rest and sc.highlight_line >= 0:
            sc.highlight_line += 1
    elif new:
        head.insert(0, f"{kelime} {n}")
        if sc.highlight_line >= 0:
            sc.highlight_line += 1
    sc.headline = head


def _history(path: Path) -> list[str]:
    if path.exists():
        return [json.loads(l)["topic"] for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return []


class BudgetExceeded(RuntimeError):
    pass


def _period(today: dt.date | None = None) -> str:
    """Kredi dönemi anahtarı: dönemin başladığı gün (ör. 24 Kasım-23 Aralık için '2026-11-24').
    Gün 1 ise eski takvim ayı biçimi ('2026-11') kullanılır."""
    today = today or dt.date.today()
    day = min(max(int(os.environ.get("CLAUDE_BUDGET_RESET_DAY", "24") or 1), 1), 28)
    if day == 1:
        return today.strftime("%Y-%m")
    start = today.replace(day=day)
    if today.day < day:
        start = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=day)
    return start.isoformat()


def _month_usage() -> tuple[dict, str]:
    u = json.loads(USAGE.read_text(encoding="utf-8")) if USAGE.exists() else {}
    return u, _period()


def _check_budget() -> float:
    limit = float(os.environ.get("CLAUDE_MONTHLY_BUDGET_USD", "90"))
    u, m = _month_usage()
    left = limit - u.get(m, 0.0)
    if left <= 0:
        raise BudgetExceeded(f"Bu dönemin Claude bütçesi ({limit:.0f} $, {m} başlangıçlı) doldu, üretim durduruldu.")
    return left


def _record(cost: float) -> None:
    u, m = _month_usage()
    u[m] = round(u.get(m, 0.0) + cost, 4)
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    USAGE.write_text(json.dumps(u, indent=2), encoding="utf-8")


_AUTH_ERR = re.compile(r"invalid api key|invalid x-api-key|authentication_error|credit balance", re.I)
_api_key_ok = True  # anahtar bir kez reddedilirse bu çalışmanın geri kalanı abonelik jetonuyla sürer


def _claude_env() -> dict:
    """Claude Code'un ortamı: API anahtarı (boşlukları temizlenmiş) varsa ve reddedilmediyse önce o kullanılır."""
    env = dict(os.environ)
    key = env.pop("ANTHROPIC_API_KEY", "").strip()
    if key and _api_key_ok:
        env["ANTHROPIC_API_KEY"] = key
    return env


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
    global _api_key_ok
    last_err = ""
    tries = 0
    while tries < 2:
        tries += 1
        env = _claude_env()
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, cwd=ROOT, env=env)
        try:
            data = json.loads(out.stdout)
        except json.JSONDecodeError:
            data, last_err = None, (out.stderr or out.stdout)[-2000:]
        if data is not None:
            _record(float(data.get("total_cost_usd") or 0))
            if not data.get("is_error") and data.get("structured_output") is not None:
                return schema.model_validate(data["structured_output"])
            last_err = str(data.get("result"))[-2000:]
        if _AUTH_ERR.search(last_err) and "ANTHROPIC_API_KEY" in env and os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            # anahtar geçersiz ya da kredisi bitti: üretim durmasın, bu çalışma abonelik jetonuyla sürer
            _api_key_ok = False
            tries -= 1
            print("::warning::ANTHROPIC_API_KEY kullanılamadı (" + last_err[:80].replace("\n", " ")
                  + "); abonelik jetonuna geçildi.", file=sys.stderr)
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
    """Son kullanılan kalıp tekrar edilmez; 'hikaye' son 3 videonun 2'sinde kullanıldıysa o da dışarıda kalır.
    FORCED_ONLY kalıpları (nasil) hiçbir zaman dönüşüme girmez."""
    last = recent_structures(history_file)
    keys = [k for k in STRUCTURES if k not in FORCED_ONLY]
    out = [k for k in keys if not (last and k == last[-1])]
    if last.count("hikaye") >= 2:
        out = [k for k in out if k != "hikaye"]
    return out or keys


def forced_ask(key: str) -> str:
    """Kalıp öneriden geliyorsa (ör. Efsane mi, gerçek mi? serisi) yalnız o kalıp sunulur."""
    return (f"\nANLATIM KALIBI (SABİT): Bu video '{STRUCTURES[key][0]}' serisinden; 'structure' alanına '{key}' yaz ve "
            f"gövdeyi bu kalıba göre kur (kanca, Makas'ın yorumu ve kapanış kuralları geçerli):\n- {key}: {STRUCTURES[key][1]}")


def structure_ask(keys: list[str]) -> str:
    return ("\nANLATIM KALIBI: Şu kalıplardan konuya en uygun olanını seç, 'structure' alanına anahtarını yaz ve gövdeyi "
            "ona göre kur (kanca, Makas'ın yorumu ve kapanış kuralları her kalıpta geçerli):\n"
            + "\n".join(f"- {k}: {STRUCTURES[k][1]}" for k in keys))


def generate_script(history_file: Path, topic_hint: str | None = None,
                    templates: dict[str, str] | None = None, series_prev: dict | None = None,
                    allow_series: bool = False, kart: bool = False, structure: str | None = None,
                    adim_kartlari: bool = False, sablon_kurali: str = "") -> ShortScript:
    """structure verilirse (öneriden üretim) kalıp sabittir: yalnız o sunulur, doğrulama ve dil düzeltmesi değiştiremez.
    adim_kartlari: video "Adım kartları" (renderer'ı nasil olan şablon: nasil, uretim) ile çizilecek; nasil ve uretim
    kalıplarında ekran düzeni (NASIL_RULES / URETIM_RULES) yalnız o zaman istenir. Kart şablonuna giden nasil
    senaryoları genel sahne kurallarıyla yazılır. olsaydin kalıbı her zaman kendi düzenini (OLSAYDIN_RULES) ister;
    uretim ve olsaydin senaryoları yazılırken de web araması yapılır (WEB_KALIPLARI).
    sablon_kurali: videoyu çizecek şablonun kendi ek yönergesi (şablon dosyasındaki "istem"; ör. ek sahne alanları)."""
    if structure and structure not in STRUCTURES:
        raise ValueError(f"bilinmeyen anlatım kalıbı: {structure}")
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
        ask += forced_ask(structure) if structure else structure_ask(allowed_structures(history_file))
        if allow_series:
            ask += SERIES_START
    if templates:
        ask += "\nGörsel şablonlardan konuya en uygun olanını 'template' alanına yaz:\n" + "\n".join(
            f"- {k}: {v}" for k, v in templates.items())
    if used and not series_prev:
        ask += "\nDaha önce işlenen konuları tekrar etme:\n- " + "\n- ".join(used)
    yapi = (series_prev or {}).get("structure", structure)
    nasil = adim_kartlari and yapi in ADIM_KELIMESI  # Adım kartları düzeni (nasil: adımlar, uretim: aşamalar)
    web = yapi in WEB_KALIPLARI
    if web:
        ask += arastirma_ask(yapi)
    script = ask_claude(ask, ShortScript, SYSTEM + ("\n" + KART_RULES if kart else "") + kalip_kurallari(yapi, nasil)
                        + ("\n" + sablon_kurali.strip() if sablon_kurali.strip() else ""), web=web)
    forced = None if series_prev else structure
    serbest = not series_prev and not structure  # kalıp dönüşümden seçilir: FORCED_ONLY (nasil, uretim, olsaydin) seçilemez
    if forced:
        script.structure = forced
    elif serbest and script.structure in FORCED_ONLY:  # şema bunlara izin verir; sunulmadığı hâlde seçildiyse dönüşüme dön
        script.structure = allowed_structures(history_file)[0]
    part, brief = (2, "") if series_prev else (script.series_part if allow_series else 0, script.next_part_brief)
    phrase = script.search_phrase
    checked = verify_script(script, keep_structure=bool(forced), adim_kartlari=nasil)
    # doğrulayıcı kalıbı gerekçeyle değiştirebilir: etiket son metne uysun diye doğrulanmış hâlin kalıbı kullanılır
    # (sabit kalıpta değiştiremez: seri etiketi ve şablon kalıba bağlı)
    structure = series_prev.get("structure", checked.structure) if series_prev else (forced or checked.structure)
    if serbest and structure in FORCED_ONLY:  # doğrulayıcı da serbest kalıpta nasil'e (uretim, olsaydin) geçemez
        structure = script.structure  # (seri etiketi, kart şablonu ve #NasılYapılır bu kalıba bağlı)
    checked.structure = structure
    out = polish_script(checked, adim_kartlari=nasil)
    out.series_part, out.next_part_brief = part, (brief if part == 1 else "")
    out.structure, out.search_phrase = structure, out.search_phrase or phrase
    out.hashtags = [t for t in (re.sub(r"\W", "", h) for h in out.hashtags) if t]
    # yaş uyarısı (publish.ALKOL_UYARI) bu alana bağlı: yalnız nasil kalıbında anlamlı; tarif kapalıyken yayına gitmez
    out.alkollu = bool(out.alkollu) and structure == "nasil"
    if out.alkollu and not ALKOLLU_ICECEK:
        raise RuntimeError("Senaryo alkollü içecek tarifi içeriyor ama ALKOLLU_ICECEK kapalı: senaryo kullanılmadı.")
    if structure == "olsaydin":
        for p in fis_sorunlari(out):  # doğrulayıcı düzeltemediyse günlükte görünsün (onaydan önce bakılır)
            print("UYARI hesap fişi:", p)
    return normalize_nasil(out)


def arastirma_ask(yapi: str) -> str:
    """Senaryosu web aramasıyla yazılan kalıpların (WEB_KALIPLARI) araştırma yönergesi."""
    bugun = dt.date.today().strftime("%d.%m.%Y")
    if yapi == "olsaydin":
        return (f"\nBugünün tarihi: {bugun}. Yazmadan önce bütün rakamları ve prosedürleri web aramasıyla {YIL} Türkiye "
                "verilerinden araştır (Resmî Gazete, ÇSGB ve SGK, TÜİK, Milli Piyango'nun resmî tabloları, meslek odaları, "
                "ilan sitelerinin ortalamaları); kullandığın kaynakları 'sources' alanına URL olarak yaz.")
    return (f"\nBugünün tarihi: {bugun}. Yazmadan önce ürünün üretim sürecini web aramasıyla araştır (üreticilerin "
            "anlatımları, sektör kuruluşları, güvenilir belgeseller ve ansiklopediler): aşamaların sırası, sıcaklık, süre, "
            "malzeme ve ölçek sayıları bu kaynaklara dayansın; kaynakları 'sources' alanına URL olarak yaz.")


# Hesap fişi (card "receipt") tutarları: '135.000 ₺', '-200.000 ₺', '1,2 MİLYON ₺', '48 BİN ₺'
_TUTAR_RE = re.compile(r"([-−–])?\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?\s*(MİLYAR|MİLYON|BİN)?")


def tutar(metin: str) -> tuple[float, float] | None:
    """Fiş tutarını (değer, yuvarlama payı) olarak okur; '1,2 MİLYON ₺' -> (1200000, 50000). Okunamazsa None."""
    m = _TUTAR_RE.search(_tr_upper(str(metin or "")))
    if not m:
        return None
    kat = {"BİN": 1e3, "MİLYON": 1e6, "MİLYAR": 1e9}.get(m.group(4) or "", 1.0)
    ondalik = m.group(3) or ""
    deger = float(m.group(2).replace(".", "") + ("." + ondalik if ondalik else "")) * kat
    return (-deger if m.group(1) else deger), kat * 10 ** -len(ondalik) / 2


# 'gider'/'gelir' fiil de olabilir ("ilk arızaya gidersin"), 'kira' da 'kiraz' olabilir: yalnız para anlamındaki ekler
_PARA_RE = re.compile(r"₺|\b(TL|lira\w*|maaş\w*|ücret\w*|ikramiye\w*|kira(?:s[ıi]|y[ıa]|da|dan|lar\w*|c[ıi]\w*)?|"
                      r"maliyet\w*|masraf\w*|harcama\w*|gelir(?:i|in|ler\w*)|gider(?:i|ler\w*)|kazanç\w*|bütçe\w*|"
                      r"borç\w*|kredi\w*)\b", re.IGNORECASE)


def para_var(script) -> bool:
    """Senaryoda para geçiyor mu (dış ses, kart değeri ya da fiş): Ya sen olsaydın? videosunda hesap fişi ve açıklamadaki
    'rakamlar yaklaşık' uyarısı yalnız o zaman gerekir ('Elektrikçi olsaydın günün nasıl geçerdi' parasız olabilir)."""
    for sc in getattr(script, "scenes", None) or []:
        metin = " ".join([str(getattr(sc, "narration", "") or ""), str(getattr(sc, "card_value", "") or ""),
                          str(getattr(sc, "card_label", "") or ""), *map(str, getattr(sc, "card_lines", None) or [])])
        if getattr(sc, "card", "") == "receipt" or _PARA_RE.search(metin):
            return True
    return False


def fis_sorunlari(script) -> list[str]:
    """Ya sen olsaydın? senaryosunun hesap fişi denetimi: en az bir card "receipt" sahnesi, 2-5 'KALEM|TUTAR' satırı ve
    satırların toplamı card_value'ya eşit (card_value yuvarlanmış yazılmışsa yuvarlama payı kadar). Sorunların listesi."""
    out, fis = [], 0
    for i, sc in enumerate(script.scenes, 1):
        if getattr(sc, "card", "") != "receipt":
            continue
        fis += 1
        satirlar = list(getattr(sc, "card_lines", None) or [])
        if not 2 <= len(satirlar) <= 5:
            out.append(f"{i}. sahnenin fişinde {len(satirlar)} satır var (2-5 olmalı)")
        tutarlar = []
        for satir in satirlar:
            kalem, ayrac, deger = str(satir).partition("|")
            t = tutar(deger) if ayrac and kalem.strip() else None
            if t is None:
                out.append(f"{i}. sahnenin fiş satırı 'KALEM|TUTAR' biçiminde değil: {satir}")
            else:
                tutarlar.append(t[0])
        toplam = tutar(getattr(sc, "card_value", ""))
        if toplam is None:
            out.append(f"{i}. sahnenin fişinde toplam (card_value) okunamadı: {getattr(sc, 'card_value', '')!r}")
        elif tutarlar and len(tutarlar) == len(satirlar) and abs(sum(tutarlar) - toplam[0]) > toplam[1] + 1e-6:
            yazili = f"{sum(tutarlar):,.0f}".replace(",", ".")  # binlik ayracı nokta: 405.000
            out.append(f"{i}. sahnenin fişinde satırların toplamı {yazili} ama card_value "
                       f"{getattr(sc, 'card_value', '')}")
    if not fis and para_var(script):
        out.append("hesap fişi (card \"receipt\") yok")
    return out


class Review(BaseModel):
    ok: bool
    problems: List[str]
    fixed: ShortScript


def verify_script(script: ShortScript, keep_structure: bool = False, adim_kartlari: bool = False) -> ShortScript:
    """İkinci geçiş: bilgileri web aramasıyla doğrular, hataları düzeltir veya çıkarır. keep_structure: kalıp seriden
    geldiği için sabit (doğrulayıcı değiştiremez). adim_kartlari: nasil / uretim kalıbının Adım kartları düzeni korunur.
    Seri kalıplarında kalıba özel denetimler eklenir (nasil: güvenlik; uretim: aşama sırası ve süreç bilgileri;
    olsaydin: rakamların güncelliği ve hesap fişinin toplamı)."""
    yapi = script.structure
    duzen = adim_kartlari and yapi in ADIM_KELIMESI
    ozel = ", ".join(f"'{k}'" for k in STRUCTURES if k in FORCED_ONLY)
    kalip = ("Anlatım kalıbı (structure) bu video için SABİT; değiştirme, metni bu kalıba uydur. " if keep_structure else
             "Seçilen anlatım kalıbını (structure) koru; yalnız konu o kalıba gerçekten uymuyorsa değiştir ve structure "
             f"alanını da buna göre güncelle ({ozel} kalıplarına geçme: bunlar yalnız kendi serilerinden gelir). ")
    if yapi == "nasil":  # doğrulanabilir ama güvensiz bir yöntem de elensin
        kalip += "Güvenli olmayan ya da şu alanlara giren adımı çıkar veya güvenli bir adımla değiştir: " + NASIL_YASAK + ". "
        kalip += ("Alet kullanılan işte kısa güvenlik notu (koruyucu gözlük, delmeden önce kablo ve boru kontrolü) bir "
                  "adımın dış sesinde (narration) yoksa ekle (yalnız callout'ta olması yetmez: kart şablonu callout "
                  "çizmez); tarifin miktar, sıcaklık ve sürelerini doğrula. ")
        if ALKOLLU_ICECEK:
            kalip += "Tarif alkollü bir içecekse 'alkollu' alanını true, değilse false yap. "
    elif yapi == "uretim":
        kalip += ("Aşamaların sırasını ve her aşamadaki süreç bilgisini (sıcaklık, süre, malzeme, makine) üreticilerin ya "
                  "da güvenilir kaynakların anlatımıyla karşılaştır; sıra yanlışsa düzelt, doğrulanamayan ayrıntıyı çıkar. "
                  "Son sahnedeki ölçek bilgisini (yıllık üretim, Türkiye'nin üretimi) doğrula. Şu alanlara giren ayrıntıyı "
                  "çıkar: " + URETIM_YASAK + ". ")
    elif yapi == "olsaydin":
        kalip += ("Gün akışı anlatılıyorsa işlerin, saatlerin ve kuralların o meslekte gerçekten böyle olduğunu kontrol "
                  "et; uydurma ya da abartılı ayrıntıyı düzelt. "
                  f"Her rakamı {YIL} Türkiye'si için web aramasıyla yeniden kontrol et (asgari ücret ve işveren maliyeti, "
                  "vergi ve kesinti oranları, kira ve fiyat ortalamaları, ikramiye ve olasılıklar); eskiyse güncelle, "
                  "doğrulanamıyorsa 'yaklaşık' de ya da çıkar. Hesap fişinde (card 'receipt') card_lines satırlarının "
                  "toplamı card_value'ya tam eşit olsun; gelir eksi gider anlatılıyorsa sonuç tutarlı olsun; dış sesteki "
                  "rakamlar kartlardakilerle aynı olsun. Şans oyunu konusunda olasılık söylensin, oynamaya özendirilmesin. "
                  "Şu alanlara giren açıyı çıkar: " + OLSAYDIN_YASAK + ". ")
        sorun = fis_sorunlari(script)
        if sorun:
            kalip += "Hesap fişinde bulunan sorunlar (düzelt): " + "; ".join(sorun) + ". "
    if duzen:
        kalip += (("Kanca, numaralı adım sahneleri (step 1, 2, 3...; başlığın ilk satırı 'ADIM n') ve son özet sahnesi "
                   "düzenini koru; adım çıkarırsan kalanları yeniden numarala. ") if yapi == "nasil" else
                  ("Kanca, numaralı aşama sahneleri (step 1, 2, 3...; başlığın ilk satırı 'AŞAMA n') ve son ölçek "
                   "sahnesi düzenini koru; aşama çıkarırsan kalanları yeniden numarala. "))
    review = ask_claude(
        "Aşağıdaki senaryodaki her olgusal iddiayı (tarih, sayı, isim, alıntı) web aramasıyla kontrol et. "
        "Yanlış ya da doğrulanamayan her bilgiyi düzelt veya çıkar, biçim kurallarına uymayan yerleri düzelt "
        "(özellikle toplam dış ses 78 kelimeyi geçmesin, ilk cümle en fazla 10 kelimelik doğrudan bir kanca olsun, search_phrase "
        "ilk iki cümlede ve başlıkta geçsin; boş sahne kalmasın). " + kalip +
        "Kullandığın güvenilir kaynakları 'sources' alanına URL olarak yaz. Düzeltilmiş tam senaryoyu 'fixed' "
        "alanında döndür.\n\n" + script.model_dump_json(indent=1),
        Review, SYSTEM + kalip_kurallari(yapi, duzen)
        + "\n\nŞimdi editör ve doğruluk kontrolcüsüsün.", web=True)
    if review.problems:
        print("Doğrulama notları:", *review.problems, sep="\n - ")
    if keep_structure:
        review.fixed.structure = script.structure
    # Dava Dosyası alanları: doğrulayıcı boş döndürürse (alanı atladıysa) yazarın değeri kalır; hükmü gerekçeyle
    # değiştirebilir
    if not review.fixed.hukum:
        review.fixed.hukum = script.hukum
    if len(review.fixed.scenes) == len(script.scenes) and not any(sc.delil for sc in review.fixed.scenes):
        for a, b in zip(script.scenes, review.fixed.scenes):
            b.delil = a.delil
    return normalize_nasil(review.fixed)


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
  doğru) olduğunu birlikte söylesin, doğrulanmış sonucu tersine çevirme; nasil ise adımların sayısını ve sırasını koru,
  headline'ların ilk satırındaki 'ADIM 1', 'ADIM 2' numaralarını ve step/callouts alanlarını değiştirme.
- series_part 2 ise ilk cümle 1. bölümün kaldığı yeri hatırlatan cümle olarak kalsın; kalıba özel ilk cümle kuralını
  uygulama, 1. bölümü yeniden anlatma.
- headline satırları, değişen narration'da geçen kelimelerden oluşsun (BÜYÜK HARF, satır başı 1-3 kelime).
- Görsel alanlarına (theme, image_mode, image_queries, illustration, motion, trail, icon) DOKUNMA.
Düzeltilmiş tam senaryoyu döndür."""


# Yalnız Adım kartları (nasil şablonu) ile çizilecek nasil senaryolarında editöre eklenir.
EDITOR_NASIL = """
ADIM KARTLARI: Bu senaryo "Adım kartları" ekranlarıyla kurulur. headline ve highlight_line alanlarına DOKUNMA: ilk
sahnenin başlığı ekranda büyük yazılan sorudur ve kelimeleri dış seste geçmeyebilir, adım başlıkları kart başlığı, son
sahnenin başlığı işin kısa adıdır (bu senaryoda "headline satırları narration kelimelerinden oluşsun" ve "ilk headline
özneyi ve dönüşü söylesin" kuralları geçerli değil). Her sahnenin narration'ı tam cümleyle başlayıp bitsin; adım
sahnelerinin dış sesi Makas'ın konuşma balonunda yazıldığı için kısa kalsın (8-14 kelime)."""


# Yalnız uretim kalıbında editöre eklenir (Adım kartlarıyla çiziliyorsa EDITOR_NASIL ile birlikte).
EDITOR_URETIM = """
NASIL ÜRETİLİYOR: aşamaların sayısını ve sırasını koru; headline'ların ilk satırındaki 'AŞAMA 1', 'AŞAMA 2'
numaralarını, step/callouts alanlarını ve süreç sayılarını (sıcaklık, süre, miktar, ölçek) değiştirme. Aşamalar geniş
zaman edilgen çatıyla anlatılsın ('pişirilir', 'kesilir'). Adım kartları kuralındaki 'adım' bu videoda 'aşama'dır."""

# Yalnız olsaydin kalıbında editöre eklenir.
EDITOR_OLSAYDIN = """
YA SEN OLSAYDIN: dış ses izleyiciyle ikinci tekil şahısla ve şart kipiyle konuşsun ('olsaydın', 'kazanırdın'). Rakamlara,
tutarlara, yüzdelere, şehir adlarına ve 'yaklaşık'/'tahmini' nitelemelerine DOKUNMA (yazılışlarını da değiştirme: '48 bin'
'48.000' olmasın); dış sesteki rakamlar kartlardakilerle aynı kalsın. Son cümle 'Sen olsan ne yapardın? Yorumlara yaz.'
olarak kalsın."""

# Dil düzeltmesinde rakamları korunan kalıplar: editör bir sahnenin sayılarını değiştirirse o sahnenin metni geri alınır.
SAYI_KORUNAN = {"uretim", "olsaydin"}


def _sayilar(metin: str) -> list[str]:
    return sorted(re.findall(r"\d+(?:[.,]\d+)*", metin or ""))


class Polished(BaseModel):
    notes: List[str] = Field(description="Yapılan önemli dil düzeltmeleri, kısa")
    fixed: ShortScript


def polish_script(script: ShortScript, adim_kartlari: bool = False) -> ShortScript:
    """Üçüncü geçiş: belgesel dili ve akış için Türkçe editör (web araması yok). adim_kartlari: nasil / uretim
    kalıbının Adım kartları düzeninde başlıklar (soru kancası, adım ve özet başlıkları) editörden önceki hâliyle kalır.
    Kart ve adım alanları (hesap fişi satırları dahil) hiç değişmez; uretim ve olsaydin kalıplarında sayıları değişen
    sahnenin metni editörden önceki hâline döner."""
    yapi = script.structure
    duzen = adim_kartlari and yapi in ADIM_KELIMESI
    ek = ((EDITOR_NASIL if duzen else "") + (EDITOR_URETIM if yapi == "uretim" else "")
          + (EDITOR_OLSAYDIN if yapi == "olsaydin" else ""))
    res = ask_claude("Bu senaryonun dış sesini düzelt:\n\n" + script.model_dump_json(indent=1), Polished, EDITOR + ek)
    if res.notes:
        print("Dil düzeltmeleri:", *res.notes[:12], sep="\n - ")
    fixed = res.fixed
    if len(fixed.scenes) != len(script.scenes):  # güvenlik: sahne yapısı bozulduysa yalnız metinleri al
        return script
    korunan = [f for f in ("theme", "image_mode", "image_query", "image_queries", "illustration", "motion", "trail", "icon",
                           "anim_query", "card", "card_value", "card_label", "card_myth", "card_fact", "card_note",
                           "card_lines", "mascot", "step", "callouts", "delil") if f in Scene.model_fields]
    for i, (a, b) in enumerate(zip(script.scenes, fixed.scenes)):  # görsel alanları kesin olarak koru
        for f in korunan:
            setattr(b, f, getattr(a, f))
        if duzen:  # Adım kartlarında başlık ekran metnidir (dış sesin altyazısı değil): editör değiştiremez
            b.headline, b.highlight_line = list(a.headline), a.highlight_line
        if yapi in SAYI_KORUNAN and _sayilar(b.narration) != _sayilar(a.narration):
            print(f"Dil düzeltmesi {i + 1}. sahnenin sayılarını değiştirdi; sahnenin metni geri alındı.")
            b.narration, b.headline, b.highlight_line = a.narration, list(a.headline), a.highlight_line
    fixed.sources, fixed.category = script.sources, script.category
    fixed.search_phrase, fixed.structure = script.search_phrase, script.structure
    fixed.alkollu = script.alkollu
    fixed.hukum = script.hukum  # Dava Dosyası hükmü: dil editörü değiştiremez
    return fixed


def load_script(path: Path) -> ShortScript:
    return ShortScript.model_validate_json(path.read_text(encoding="utf-8"))
