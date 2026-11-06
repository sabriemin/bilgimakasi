"""Konu önerileri: dokuz seride (Popüler, Konular, Efsane mi gerçek mi?, Nasıl yapılır?, Nasıl üretiliyor?, Ya sen
olsaydın?, Bir Kitap Bir Dakika, Mini Belgesel, Kelimenin kökeni) short fikri önerir.

Claude tek bir web aramalı çağrıyla güncel gündemi (Google Trends TR, haber manşetleri, sosyal medya gündemi,
YouTube'da yükselen konular) tarar; her seriden 3 öneri döndürür. Popüler gündeme bağlı "az bilinen bilgi" açısıdır,
Bir Kitap Bir Dakika gündeme bağlanabilir (yıl dönümü, uyarlama, ödül); diğer seriler gündemden bağımsızdır.

    python -m shortgen.trends notify   # 24 öneriyi seri seri Telegram'a butonlarla gönderir (en çok üç serilik mesajlar)
    python -m shortgen.trends best     # en iyi öneriyi yazdırır (otomatik üretim için; yalnız OTOMATIK_SERILER)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field

from .script import (CATEGORIES, KAMU_MALI_FARK, KITAP_YASAK, NASIL_YASAK, OLSAYDIN_YASAK, URETIM_YASAK, YIL,
                     _history, allowed_structures, ask_claude, nasil_alanlari)

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "oneriler.json"

# Nasıl yapılır? önerilerinin alanları, numaralı: "(1) ev işleri ve temizlik; (2) alet kullanımı: ..."
NASIL_ALANLARI = "; ".join(f"({i}) {a}" for i, a in enumerate(nasil_alanlari(), 1))
# Seriler (kayıt sırası = Telegram ve paneldeki sıra). "seri" alanı olmayan eski öneriler Popüler sayılır.
SERILER = {"populer": "Popüler", "konu": "Konular", "efsane": "Efsane mi, gerçek mi?", "nasil": "Nasıl yapılır?",
           "uretim": "Nasıl üretiliyor?", "olsaydin": "Ya sen olsaydın?", "kitap": "Bir Kitap Bir Dakika",
           "belgesel": "Mini Belgesel", "koken": "Kelimenin kökeni"}
# simgeler ayrı olsun: Konular 📚, Bir Kitap Bir Dakika 📖, Mini Belgesel 🎞
SERI_IKON = {"populer": "🔥", "konu": "📚", "efsane": "🧐", "nasil": "🛠", "uretim": "🏭", "olsaydin": "💭",
             "kitap": "📖", "belgesel": "🎞", "koken": "🔤"}
# öneriden üretimde zorunlu anlatım kalıbı (script.STRUCTURES); listede olmayan seriler normal dönüşümü kullanır
SERI_KALIP = {"efsane": "efsane", "nasil": "nasil", "uretim": "uretim", "olsaydin": "olsaydin", "kitap": "kitap",
              "belgesel": "belgesel", "koken": "koken"}
# otomatik üretimin seçebileceği seriler: Nasıl yapılır?, Nasıl üretiliyor?, Ya sen olsaydın?, Bir Kitap Bir Dakika ve
# Mini Belgesel yalnız elle seçilir
OTOMATIK_SERILER = ("populer", "konu", "efsane")
SERI_BASI = 10  # her seriden öneri sayısı (Sabri 6 Kasım: her seride en az 10 öneri)
OTOMATIK_BASI = 3  # otomatik üretimin (best) seri başına istediği öneri
YENILE_ESIK = 3  # bir serinin üretilmemiş önerisi bu sayıya inince yalnız o seri yeniden doldurulur
CAGRI_SERI = 3  # tek Claude çağrısında istenen seri sayısı (10'ar öneriyle yanıt uzun olmasın)
TG_SINIR = 4096  # Telegram mesaj sınırı (UTF-16 birimi)
# /oneri mesajı başına seri: 24 öneri ayrıntısıyla tek mesaja sığmaz. Seriler kayıt sırasıyla üçerli mesajlara bölünür
# (Popüler, Konular, Efsane | Nasıl yapılır, Nasıl üretiliyor, Ya sen olsaydın | Bir Kitap Bir Dakika, Mini Belgesel);
# bir serinin yeri hep aynı mesajdır. Seri başına 10 öneriyle her seri kendi mesajındadır.
MESAJ_SERI = 1
DUGME_SATIR = 5  # bir düğme satırında en çok bu kadar düğme (Telegram satır başına 8'e izin verir)

SYSTEM = f"""Sen Türkçe bilgi/merak kanalı "Bilgi Makası" için konu editörüsün. Görevin, short videolar için
DOKUZ SERİDE konu önermek. Hedef kitle Türkiye'deki 15-34 yaş; en güçlü büyüme sinyali videonun bir arkadaşa gönderilmesi,
bu yüzden "bunu görünce birine atarım" dedirten açıları seç. Her önerinin 'seri' alanını doldur.
SERİLER:
- populer (Popüler): BUGÜN Türkiye'de ve dünyada çok konuşulan, aranan bir konuya bağlı şaşırtıcı, doğrulanabilir bir açı.
  Web araması yap: Google Trends Türkiye günlük aramaları, Türkiye ve dünya haber manşetleri, X/Twitter Türkiye gündemi,
  YouTube'da yükselen konular, yaklaşan önemli günler/yıl dönümleri, vizyondaki film/dizi/oyunlar, spor olayları.
  Konunun kendisini haber gibi anlatma; ona bağlı az bilinen bir bilgi, tarihçe, bilim veya ilginç bağlantı bul.
  Ör. gündem 'Dünya Kupası elemeleri' ise açı: 'Bir maçta kalecinin attığı 3 golün hikâyesi'.
  trend: bağlı olduğu gündem ve neden şu an popüler.
- konu (Konular): bugünün gündemine bağlı OLMAYAN, her zaman ilgi çeken şaşırtıcı bir konu. Şu kategorilerden birinden
  seç: {', '.join(CATEGORIES)}. Ör. gündelik bir şeyin şaşırtıcı nedeni, şehirlerin ve kelimelerin bilinmeyen hikâyeleri,
  az bilinen bir icat ya da insan hikâyesi. trend: konunun neden ilgi çekeceği (kalıcı merak, mevsim, yaklaşan bir gün).
- efsane (Efsane mi, gerçek mi?): Türkiye'de yaygın olarak doğru sanılan ama yanlış olan (ya da şaşırtıcı biçimde doğru
  çıkan) bir inanış. topic inanışı ve doğrusunu birlikte söylesin. Bilim kurumu, ansiklopedi, resmî kurum gibi güvenilir
  kaynaklarla doğrulanabilsin; sağlık, tedavi ve beslenme inanışlarını seçme. trend: inanışın ne kadar yaygın olduğu ya
  da neden şimdi konuşulduğu.
- nasil (Nasıl yapılır?): 3-5 somut adımla 30-35 saniyede gösterilebilen pratik, güvenli ve doğrulanabilir bir "nasıl
  yapılır"; şaşırtıcı bir püf noktası ya da nedeni olsun ve Türkiye'de günlük hayatta işe yarasın. Yalnız şu alanlardan:
  {NASIL_ALANLARI}. 3 önerinin her biri farklı bir alandan olsun. topic sonucu ve yöntemi net söylesin (ör. 'Muzları
  bir hafta taze tutmak: sapı sarıp diğer meyvelerden ayırmak, çünkü etilen gazı sapından çıkar'). Şu alanlarda
  ÖNERME: {NASIL_YASAK}.
  trend: yöntemin neden işe yaradığı ya da kimin işine yarayacağı.
- uretim (Nasıl üretiliyor?): tanıdık, gündelik bir ürünün hammaddeden bitmiş ürüne 3-5 aşamada nasıl üretildiği
  (belgesellerdeki 'nasıl yapılmış' tarzı); süreçte şaşırtıcı bir aşama ya da gerçek olsun. Türkiye bağlantılı ürünler
  öncelikli (çay, fındık, lokum, cam, porselen, halı, bakır cezve, çini, nazar boncuğu, beyaz eşya); gündelik küresel
  ürünler de olur. topic ürünü ve şaşırtıcı yanını söylesin (ör. 'Kurşun kalem nasıl üretilir: içindeki "kurşun"
  aslında kille pişirilmiş grafit'). Süreç üreticilerin ya da güvenilir kaynakların anlatımıyla doğrulanabilsin. Şu
  alanlarda ÖNERME: {URETIM_YASAK}. trend: ürünün neden ilgi çekeceği.
- olsaydin (Ya sen olsaydın?): izleyiciyi ikinci tekil şahısla somut bir duruma koyan, {YIL} Türkiye'sinin gerçek
  rakamları ve prosedürleriyle anlatılan bir "olsaydın"; her zaman para hesabı değildir. Üç tür: (a) bir meslek ya da
  iş (ör. 'Kuyumcu olsaydın: Kapalıçarşı'da bir kuyumcunun bir günü ve ayda kalan para' ya da 'Elektrikçi olsaydın
  günün nasıl geçerdi: sabahtan akşama bir iş günü'); (b) bir para ya da hayat olayı (ör. 'Piyango sana
  çıksaydı: vergiden sonra eline geçen para, neye yettiği ve kazanma olasılığı'); (c) bir hayat durumu (ör. 'Yurt
  dışına taşınsaydın ilk ay kaç lira harcardın', 'Bir köyde yaşamaya başlasaydın'). 3 öneri bu türlere karışık
  dağılsın; topic somut durumu adıyla söylesin. Rakamlar resmî ya da güvenilir kaynaklarla (Resmî Gazete, SGK, TÜİK,
  Milli Piyango, meslek odaları, ilan ortalamaları) doğrulanabilsin. Şu alanlarda ÖNERME: {OLSAYDIN_YASAK}.
  trend: durumun neden merak edildiği.
- kitap (Bir Kitap Bir Dakika): tek bir kitabın konusunu ve ana fikrini sürprizini ele vermeden anlatan, kitap ya da
  yazarı hakkında şaşırtıcı ve doğrulanabilir bir bilgi içeren 30-38 saniyelik tanıtım. Mümkünse gündeme bağlansın;
  web aramasıyla yakın tarihleri bul: yayımının, yazarının doğumunun ya da ölümünün yıl dönümü, vizyondaki ya da yeni
  duyurulan film/dizi uyarlaması, edebiyat ödülü (Nobel, Booker, Orhan Kemal, Sait Faik...), okul okuma listeleri ve
  sınav dönemi. Türk edebiyatından ve dünya klasiklerinden karışık öner; 3 öneriden en az biri Türk edebiyatından
  olsun. topic kitabın adını, yazarını ve açıyı söylesin (ör. 'Franz Kafka, Dönüşüm: bir sabah dev bir böceğe
  dönüşen pazarlamacı; Kafka yayıncısından kapağa böceğin çizilmemesini istedi'). Telif: yazarı {YIL - KAMU_MALI_FARK}
  ya da daha önce ölmüş kitaplar kamu malıdır ve ilk cümlesi kendi çevirimizle ekrana yazılabilir; diğer kitaplar da
  önerilebilir ama videoda alıntı olmaz, kitap yalnız anlatılır. 3 öneriden en az biri kamu malı olsun. Kitabın sonunu
  ya da büyük sürprizini ele veren topic ve hook yazma. Şu alanlarda ÖNERME: {KITAP_YASAK}.
  trend: bağlandığı gündem (yıl dönümü, uyarlama, ödül, okuma listesi) ya da kitabın neden şimdi ilgi çekeceği.
- belgesel (Mini Belgesel): iki bölümlük (her biri ~90 saniye) belgesel; konu 4-6 net evreden ya da duraktan geçen bir
  yolculuk olsun. Yalnız şu alanlardan: doğa (bir doğa olayının, ekosistemin ya da mevsimin evreleri), hayvan (bir
  hayvanın yaşam döngüsü ya da göçü), insan (insanlığın bir dönüm noktası, bir şehrin ya da yapının hikâyesi), vücut
  (bir maddenin vücuttaki yolculuğu, bir organın işi). 3 öneri bu alanlardan en az ikisine dağılsın. topic yolculuğu
  ve evreleri net söylesin (ör. 'Kedinin yaşam döngüsü: doğumdan yaşlılığa 6 evre', 'Kanın temizlenmesi: kalpten
  böbreğe 6 durak'). Ansiklopedi, üniversite ve bilim kurumu kaynaklarıyla doğrulanabilsin; hastalık, tedavi ve
  beslenme iddiası, kan ve yaralanma ayrıntısı, avlanma sahnesi içermesin. trend: konunun neden merak edildiği.
- koken (Kelimenin kökeni): Türkçede her gün kullanılan tek bir kelimenin ya da deyimin şaşırtıcı kökeni; en iyi
  çalışan örnek 'Benzin kelimesinin kökeni: depodaki yakıt bir tütsünün adını taşıyor'. Gündelik eşya, yiyecek, şehir,
  meslek, marka ve deyimlerden seç; kelime herkesin tanıdığı bir şey olsun, kökeni ise 'bunu bilmiyordum' dedirtsin.
  topic kelimeyi ve şaşırtıcı kökenini birlikte söylesin. TDK, Nişanyan Sözlük ve etimoloji sözlükleriyle
  doğrulanabilsin; halk etimolojisi önerme; siyasi, dinî tartışma yaratan ve hakaret içeren kelime seçme.
  trend: kelimenin neden merak edileceği.
Ortak kurallar:
- Siyasi kutuplaştırıcı, trajik (ölüm, afet, suç mağdurları), sağlık iddiası ve magazin dedikodusu konularını ÖNERME.
- Doğrulanabilir olmalı; güvenilir kaynakta geçmeli.
- Daha önce işlenen konuları tekrar etme.
- Çeşitlilik: önerilerin en az yarısı ve her seriden en az biri Türkiye bağlantılı olsun (Türk kişi, takım, şehir,
  marka, kelime kökeni, Türkiye'deki yansıması); küresel konuda da Türkiye bağlantısı varsa onu öne çıkar.
- Son işlenen konulara bakıp aynı alanı (ör. art arda futbol) üst üste önerme; seriler arasında da aynı konuyu ya da
  alanı tekrarlama.
- POPÜLER BAŞLIKLAR: her öneri geniş kitlenin tanıdığı bir şeye bağlansın: herkesin bildiği kişi, takım, marka, ürün,
  kelime, film/dizi/oyun, şehir ya da gündelik nesne. Kanalın verisi: Türk takımlı futbol hikâyeleri (Fenerbahçe,
  Galatasaray, Beşiktaş, Milli Takım, Avrupa geceleri) ve gündelik bir şeyin şaşırtıcı kökeni en çok izlenenler; antik
  tarih, yabancı ve uzak konular en az izlenenler. Niş, akademik, uzak konular ÖNERME. 'Bunu kim bilmez ki' denen bir
  konunun 'bunu bilmiyordum' dedirten açısını bul. Puanı 7'nin altında kalacak öneriyi yazma, yerine daha bilinen bir
  konu bul."""


class Suggestion(BaseModel):
    topic: str = Field(description="Video konusu, tek cümle, üretim için yeterince net (ör. 'Halley kuyruklu yıldızının 1910'da yarattığı panik')")
    hook: str = Field(description="Videonun açılış kancası, en fazla 12 kelime, merak uyandıran")
    trend: str = Field(description="populer: bağlı olduğu gündem ve neden şu an popüler; diğer seriler: seri tanımındaki "
                                   "kısa gerekçe. En fazla 15 kelime")
    scope: Literal["TR", "Global"]
    category: str = Field(description=f"Şunlardan biri: {', '.join(CATEGORIES)}")
    score: int = Field(description="Tahmini izlenme potansiyeli 1-10 (populer'de gündem sıcaklığı x merak x arkadaşa "
                                   "gönderilme ihtimali x Türkiye bağlantısı x görsel zenginlik)")
    seri: Literal["populer", "konu", "efsane", "nasil", "uretim", "olsaydin", "kitap", "belgesel", "koken"] = Field(
        description="Önerinin serisi (sistem yönergesindeki tanımlar)")


class Suggestions(BaseModel):
    items: List[Suggestion]


def _alan(it, ad: str, varsayilan=None):
    """Öneri sözlük (kayıt) ya da Suggestion olabilir."""
    return it.get(ad, varsayilan) if isinstance(it, dict) else getattr(it, ad, varsayilan)


def seri_of(it) -> str:
    """Önerinin serisi; alanı olmayan ya da tanınmayan eski öneriler Popüler sayılır."""
    s = _alan(it, "seri")
    return s if s in SERILER else "populer"


def kalip_of(it) -> str:
    """Öneriden üretimde zorunlu anlatım kalıbı ('' = normal dönüşüm)."""
    return SERI_KALIP.get(seri_of(it), "")


# Elle yazılan konunun serisi (Telegram /uret, panel "Şimdi üret", panel konu sırası). Başta "seri:" öneki varsa o
# seri kullanılır (ör. "olsaydin: Piyango sana çıksaydı"; "genel:" serbest kalıp demektir). Önek yoksa yalnız açık
# işaretlerden tahmin edilir; emin olunmayan konu serbest kalıpta kalır. Bir Kitap Bir Dakika (kitap) yalnız önekle
# seçilir ("kitap: Kürk Mantolu Madonna"): kitap adı tek başına tahmin edilmez.
_SERI_ONEK = {"genel": "", "serbest": "", "efsane": "efsane", "efsane mi gercek mi": "efsane", "nasil": "nasil",
              "nasil yapilir": "nasil", "uretim": "uretim", "nasil uretiliyor": "uretim", "olsaydin": "olsaydin",
              "ya sen olsaydin": "olsaydin", "kitap": "kitap", "bir kitap bir dakika": "kitap",
              "belgesel": "belgesel", "mini belgesel": "belgesel",
              "koken": "koken", "kelimenin koken": "koken", "kelimenin kokeni": "koken"}
_NASIL_FIIL = ("yapılır|hazırlanır|demlenir|pişirilir|temizlenir|yıkanır|ütülenir|katlanır|dikilir|takılır|sökülür|"
               "değiştirilir|kullanılır|bağlanır|kurulur|saklanır|çıkarılır|onarılır|giderilir|ayıklanır|doğranır|"
               "soyulur|haşlanır|kızartılır|kaynatılır|boyanır|asılır|sıkılır|ayarlanır|açılır|tamir edilir")
_SERI_IZ = (
    ("uretim", re.compile(r"\bnasıl (üretil|imal edil)|fabrikada nasıl|üretim (süreci|aşamaları)")),
    ("olsaydin", re.compile(r"\w(saydın|seydin)\b")),
    ("nasil", re.compile(rf"\bnasıl (\w+ )?({_NASIL_FIIL})\b")),
    ("efsane", re.compile(r"\befsane mi\b|\b(gerçek|doğru) mu\s*\??\s*$")),
    ("koken", re.compile(r"kelimesinin (kökeni|hikâyesi|hikayesi)|kelimesi nereden gel|\betimolojisi\b")),
)


def _sade(s: str) -> str:
    s = s.replace("I", "ı").replace("İ", "i").lower()
    return s.translate(str.maketrans("ıçğöşü", "icgosu")).strip(" ?!.")


def seri_tahmini(konu: str) -> tuple[str, str]:
    """(kalıp, konu): elle yazılan konunun anlatım kalıbı ('' = serbest) ve öneki atılmış konu."""
    konu = " ".join(str(konu or "").split())
    if ":" in konu:
        on, kalan = konu.split(":", 1)
        if _sade(on) in _SERI_ONEK and kalan.strip():
            return _SERI_ONEK[_sade(on)], kalan.strip()
    k = konu.replace("I", "ı").replace("İ", "i").lower()
    for kalip, iz in _SERI_IZ:
        if kalip == "olsaydin":
            # ikinci tekil şart ("kuyumcu olsaydın") ya da "sen/sana" ile şart ("piyango sana çıksaydı");
            # "Titanik batmasaydı" gibi genel "ya olsaydı" konuları serbest kalır
            if iz.search(k) or (re.search(r"\b(sen|sana|seni|senin)\b", k) and re.search(r"\w(saydı|seydi)\b", k)):
                return kalip, konu
        elif iz.search(k):
            return kalip, konu
    return "", konu


def seri_adi(kalip: str) -> str:
    """Kalıbın seri adı (ör. olsaydin -> 'Ya sen olsaydın?'); serbest kalıp için ''."""
    return next((SERILER[s] for s, k in SERI_KALIP.items() if k == kalip), "")


def uretim_konusu(it) -> str:
    """Üretime (uret.yml topic) giden konu metni. Popüler önerinin gerekçesi gündemdir, diğer serilerinki değil."""
    etiket = "gündem" if seri_of(it) == "populer" else "neden ilgi çeker"
    return f"{_alan(it, 'topic')} (kanca: {_alan(it, 'hook')}; {etiket}: {_alan(it, 'trend')})"


def sirala(items: list, adet: int = SERI_BASI) -> list:
    """Seri sırasıyla (SERILER: Popüler ... Bir Kitap Bir Dakika), her seride puana göre; seri başına en çok SERI_BASI."""
    out = []
    for s in SERILER:
        grup = sorted((x for x in items if seri_of(x) == s), key=lambda x: -(_alan(x, "score") or 0))
        out += grup[:adet]
    return out


def _iste(seriler: tuple, adet: int, used: list[str]) -> list:
    today = dt.date.today().strftime("%d %B %Y")
    prompt = (f"Bugünün tarihi: {today}. Gündemi araştır ve şu serilerin her birinden tam {adet} short konusu öner "
              f"(toplam {adet * len(seriler)}): {', '.join(seriler)}. Her serinin içinde en yüksek puanlı önce gelsin.")
    if used:
        prompt += "\nDaha önce işlenen ya da listede duran konular (tekrar etme):\n- " + "\n- ".join(used)
    res = ask_claude(prompt, Suggestions, SYSTEM, web=True)
    return [x for x in res.items if seri_of(x) in seriler]


def suggest(kaydet: bool = True, seriler: tuple = tuple(SERILER), adet: int = SERI_BASI) -> list[Suggestion]:
    """Web aramalı Claude çağrıları (en çok CAGRI_SERI seri bir çağrıda): istenen her seriden `adet` öneri.
    kaydet: sonuç state/oneriler.json'a seri sırasıyla yazılır (Telegram düğmesi ve panel öneriyi bu sıradaki
    numarasıyla seçer). Yalnız bazı seriler istenirse (seri yenileme) kayıtlı listenin diğer serileri olduğu gibi kalır;
    istenen serilerin eski önerileri yenileriyle değişir."""
    used = _history(ROOT / "history.jsonl")[-150:]
    eski = load_saved() if kaydet and set(seriler) != set(SERILER) else []
    kalan = [x for x in eski if seri_of(x) not in seriler]
    used += [str(_alan(x, "topic")) for x in kalan if not uretildi_mi(x)][:60]
    gelen: list = []
    for i in range(0, len(seriler), CAGRI_SERI):
        parca = seriler[i:i + CAGRI_SERI]
        try:
            gelen += _iste(parca, adet, used)
        except Exception as e:  # noqa: BLE001  bir grup düşerse diğerleri yine kaydedilir
            print("öneri alınamadı:", parca, e, file=sys.stderr)
    items = sirala(gelen, adet)
    if kaydet and items:
        tum = [*kalan, *(s.model_dump() for s in items)]
        tum = [x for s in SERILER for x in tum if seri_of(x) == s]
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"date": str(dt.date.today()), "items": tum}, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return items


def best() -> Suggestion:
    """Otomatik üretimin konusu: OTOMATIK_SERILER'in (Popüler, Konular, Efsane) en yüksek puanlı önerisi (eşitlikte
    seri sırası); Nasıl yapılır?, Nasıl üretiliyor?, Ya sen olsaydın? ve Bir Kitap Bir Dakika hiç istenmez.
    Liste kaydedilmez: sahibin Telegram'da ve panelde seçtiği öneriler değişmesin. Kalıbı şu an dönüşümde olmayan seri
    seçilmez (ör. son video efsane kalıbındaysa Efsane önerisi): aynı kalıp art arda gelmesin."""
    izinli = allowed_structures(ROOT / "history.jsonl")
    adaylar = [s for s in suggest(kaydet=False, seriler=OTOMATIK_SERILER, adet=OTOMATIK_BASI)
               if seri_of(s) in OTOMATIK_SERILER and (not kalip_of(s) or kalip_of(s) in izinli)]
    if not adaylar:
        raise RuntimeError("otomatik üretime uygun öneri çıkmadı")
    return max(adaylar, key=lambda s: _alan(s, "score") or 0)


def load_saved() -> list[dict]:
    """Son önerileri okur. Dinleme oturumu öneriden önce başlamış olabileceği için önce GitHub'daki güncel kopyaya bakar."""
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if repo and token:
        try:
            import requests
            r = requests.get(f"https://api.github.com/repos/{repo}/contents/state/oneriler.json",
                             headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json"},
                             timeout=20)
            if r.ok:
                return r.json().get("items", [])
        except Exception:  # noqa: BLE001
            pass
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8")).get("items", [])
    return []


# ---- Telegram mesajı ----
def _kisa(t: str, n: int | None) -> str:
    """Metni kelime sınırında n karaktere kısaltır (n None ise aynen)."""
    t = " ".join(str(t or "").split())
    if n is None or len(t) <= n:
        return t
    k = t[:n - 1]
    return (k[:k.rfind(" ")] if k.rfind(" ") > n * 0.6 else k).rstrip(" ,;:") + "…"


def uretildi_mi(it) -> bool:
    """Öneri daha önce üretildi mi (telegram_bot._produce_suggestion işaretler)."""
    return bool(_alan(it, "uretildi"))


def uretildi_isaretle(topic: str) -> str | None:
    """Kayıtlı listede bu konulu öneriyi üretildi diye işaretler (sıra ve damga değişmez: düğmeler doğru kalır).
    İşaretlenen önerinin serisinde üretilmemiş öneri YENILE_ESIK'e indiyse o serinin adını döndürür (yalnız o seri
    yeniden doldurulur)."""
    if not STATE.exists():
        return None
    d = json.loads(STATE.read_text(encoding="utf-8"))
    items = d.get("items") or []
    hedef = next((it for it in items if it.get("topic") == topic), None)
    if hedef is None:
        return None
    hedef["uretildi"] = dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).isoformat(timespec="minutes")
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    seri = seri_of(hedef)
    grup = [x for x in items if seri_of(x) == seri]
    kalan = sum(1 for x in grup if not uretildi_mi(x))
    # seri boşaldıysa ya da (en az YENILE_ESIK'ten fazla öneriyle başlamış) seri YENILE_ESIK'e indiyse yenilenir
    return seri if kalan == 0 or (len(grup) > YENILE_ESIK >= kalan) else None


def gruplar(items: list[dict]) -> list[tuple[str, list[tuple[int, dict]]]]:
    """Önerileri seri sırasıyla gruplar (boş seri yok); her öğe kayıttaki sırasını taşır (düğme numarası,
    tp:<damga>:<sıra>). Üretilmiş öneriler gösterilmez."""
    out = []
    for s in SERILER:
        g = [(i, it) for i, it in enumerate(items) if seri_of(it) == s and not uretildi_mi(it)]
        if g:
            out.append((s, g))
    return out


def _mesaj_metni(gr: list, n: int | None, ayrinti: bool, baslik: str = "🗂 Bugünün konu önerileri") -> str:
    lines = [baslik]
    for s, g in gr:
        lines.append(f"\n{SERI_IKON[s]} {SERILER[s]}")
        for i, it in g:
            flag = "🇹🇷" if _alan(it, "scope") == "TR" else "🌍"
            lines.append(f"{i + 1}. {flag} {_kisa(_alan(it, 'topic'), n)}")
            puan = f"(puan {_alan(it, 'score')}/10)"
            if ayrinti:
                ikon = "📈" if s == "populer" else "💡"
                lines.append(f"   🎣 {_kisa(_alan(it, 'hook'), n)}\n   {ikon} {_kisa(_alan(it, 'trend'), n)} {puan}")
            else:
                lines.append(f"   🎣 {_kisa(_alan(it, 'hook'), n)} {puan}")
    lines.append("\nÜretmek istediğin konunun numarasına bas.")
    return "\n".join(lines)


def damga(items: list) -> str:
    """Öneri listesinin kısa damgası. Telegram düğmesi (tp:<damga>:<sıra>) liste yenilendikten sonra eski mesajdan
    basılırsa aynı numara başka konuyu gösterir; damga tutmazsa üretim başlamaz."""
    konular = "\n".join(str(_alan(x, "topic") or "") for x in items)
    return hashlib.sha256(konular.encode("utf-8")).hexdigest()[:8]


def load_saved_local() -> list[dict]:
    return json.loads(STATE.read_text(encoding="utf-8")).get("items", []) if STATE.exists() else []


def mesajlar(items: list[dict], seriler: tuple = tuple(SERILER)) -> list[tuple[str, list[list[tuple[str, str]]]]]:
    """/oneri mesajları ve klavyeleri: seriler kayıt sırasıyla MESAJ_SERI'lik gruplara bölünür (her serinin mesajı
    sabit: SERILER'deki sırası // MESAJ_SERI); birden çok mesajda başlık "(1/2)" diye numaralanır. Numaralar mesajlar
    boyunca 1'den kesintisiz; her seri kendi mesajında bir düğme satırı (tp:<damga>:<kayıttaki sıra>). Bir mesaj
    Telegram sınırına (TG_SINIR) sığmazsa önce uzun metinler kısalır, sonra gerekçe satırları düşer."""
    from .telegram_bot import _cut16
    gr, d = gruplar(items), damga(items)
    sira = list(SERILER)
    parcalar: dict[int, list] = {}
    for s, g in gr:
        if s not in seriler:
            continue
        parcalar.setdefault(sira.index(s) // MESAJ_SERI, []).append((s, g))
    out = []
    for no, pr in enumerate(parcalar.values(), 1):
        rows = [[(f"🎬 {i + 1}", f"tp:{d}:{i}") for i, _ in g[k:k + DUGME_SATIR]]
                for _, g in pr for k in range(0, len(g), DUGME_SATIR)]
        baslik = "🗂 Bugünün konu önerileri" + (f" ({no}/{len(parcalar)})" if len(parcalar) > 1 else "")
        metin = ""
        for n, ayrinti in ((None, True), (220, True), (150, True), (110, False), (80, False), (50, False)):
            metin = _mesaj_metni(pr, n, ayrinti, baslik)
            if len(metin.encode("utf-16-le")) // 2 <= TG_SINIR:
                break
        out.append((_cut16(metin, TG_SINIR), rows))
    return out


def notify(seriler: tuple = tuple(SERILER)) -> None:
    """Öneri ister, kaydeder ve Telegram'a gönderir. Yalnız bazı seriler yenilendiyse yalnız onların mesajı gider."""
    from .telegram_bot import _kb, api
    yeni = suggest(seriler=seriler)
    chat = os.environ["TELEGRAM_CHAT_ID"]
    if not yeni:
        api("sendMessage", data={"chat_id": chat, "text": "Bugün öneri çıkmadı; /oneri ile yeniden dene."})
        return
    items = load_saved_local()
    for text, rows in mesajlar(items, seriler):  # seriler en çok üçerli mesajlarda; her mesaj kendi serilerinin düğmeleriyle
        api("sendMessage", data={"chat_id": chat, "text": text, "reply_markup": _kb(rows),
                                 "disable_web_page_preview": "true"})


if __name__ == "__main__":
    from .pipeline import load_env
    load_env(ROOT / ".env")
    if sys.argv[1] == "notify":
        secili = tuple(x for x in (sys.argv[2] if len(sys.argv) > 2 else "").replace(",", " ").split() if x in SERILER)
        notify(secili or tuple(SERILER))
    elif sys.argv[1] == "best":
        s = best()
        print(uretim_konusu(s))
