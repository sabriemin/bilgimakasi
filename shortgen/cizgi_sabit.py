"""Çizgi Roman şablonunun ("Karar Senin" hikâye serisi) sabit listeleri: karakterler, pozlar, ifadeler, mekânlar,
panel düzenleri ve özel kartlar. Yalnız standart kitaplık; senaryo modeli (script.py) bu listeleri Literal tür olarak
kullanır, çizim modülleri (cizgi.py, cizgi_karakter.py, cizgi_mekan.py) her anahtarın çizimini sağlar.

Görünümler sabittir: Sabri pilotu onayladıktan sonra karakterlerin görünüşü değişmez (kilitlenir). Yeni karakter ya da
mekân eklemek için anahtarı buraya, çizimini ilgili modüle eklemek yeterlidir (testler her anahtarın çizildiğini
denetler).
"""
from __future__ import annotations

# ---------------------------------------------------------------- karakterler (kimlik -> kısa Türkçe tanım)
# Tanım, yazara (istem) giden tek görünüm metnidir: resimle söz ayrışmasın diye görünüm yalnız cizgi_karakter.KADRO'da
# tanımlanır, buradaki metin onun özetidir.
KARAKTERLER = {
    "kuzey": "Kuzey, 15 yaşında solak golcü, Sinoplu balıkçı oğlu: kısa koyu kahve dalgalı saç, açık zeytin ten, "
             "lacivert antrenman üstü (kulüp forması yok)",
    "hasan": "Hasan Reis, 48 yaşında balıkçı, Kuzey'in babası: kır sakal, lacivert örgü bere, kalın lacivert kazak",
    "nermin": "Nermin, 44 yaşında, okul kantininde çalışıyor, Kuzey'in annesi: topuz koyu saç, hardal hırka",
    "selim": "Selim Bey, 50 yaşında Galatasaray gözcüsü: gözlük, gri ceket, sarı-kırmızı atkı, not defteri",
    "orhan": "Orhan Bey, 45 yaşında Samsunspor gözcüsü: kırmızı-beyaz eşofman üstü, kasket",
    "golge": "Yüzü gölgede, not alan adam (kimliği henüz belli olmayan gözcü)",
}

# ---------------------------------------------------------------- pozlar (kollar ve eldeki nesne)
POZLAR = {
    "dur": "kollar yanda, ayakta",
    "kartvizit": "elinde iki kartvizit, bakıyor",
    "ag": "iki eliyle ağ topluyor ya da katlıyor",
    "top": "topu kolunun altında tutuyor",
    "sut": "sol ayakla şut atıyor (boydan çizilir)",
    "sevinc": "iki kolu havada, gol sevinci",
    "not": "elinde defter ve kalem, not alıyor",
    "telefon": "telefonla konuşuyor (telefon kulağında)",
    "isaret": "eliyle ileriyi gösteriyor",
    "cene": "eli çenesinde, düşünüyor",
    "kollar": "kollarını kavuşturmuş",
}

# ---------------------------------------------------------------- yüz ifadeleri
IFADELER = {
    "normal": "sakin",
    "gulumse": "hafif gülümsüyor",
    "mutlu": "gülüyor",
    "saskin": "şaşkın",
    "endiseli": "endişeli",
    "dusunceli": "düşünceli",
    "kararli": "kararlı",
}

# ---------------------------------------------------------------- mekânlar (panel arka planı)
MEKANLAR = {
    "bos": "düz renkli zemin ve tram noktaları (yalnız karakter)",
    "iskele_gece": "gece, ahşap iskele, ay ve deniz",
    "liman": "Sinop limanı, mavi-beyaz balıkçı teknesi, gündüz",
    "tekne_sabah": "sabah, tekne güvertesi, ufukta güneş",
    "saha_aksam": "akşam, ışıklı küçük futbol sahası",
    "harita_fener": "Türkiye'nin kuzey kıyısı haritası ve İnceburun feneri",
    "saha_gol": "kale, file ve skor tabelası",
    "tribun": "tribün basamakları, akşam ışığı",
    "brosur": "masada üç kanatlı broşür: yatakhane, okul, ışıklı saha",
    "soyunma": "soyunma odası, askıda sıra sıra aynı formalar",
    "yol_tabelasi": "sahil yolu ve iki yönlü yol tabelası",
    "mutfak": "ev mutfağı, masada okul çantası",
    "telefon_defter": "otel odası masası, açık defter",
    "saat_bilet": "gece, duvar saati ve masada otobüs bileti",
    "istanbul": "İstanbul silueti (A seçeneğinin paneli)",
    "samsun": "Karadeniz kıyısı ve stadyum ışıkları (B seçeneğinin paneli)",
}

# ---------------------------------------------------------------- panel düzenleri
DUZENLER = {
    "tek": "tek büyük panel",
    "ust_alt": "üstte geniş, altta geniş iki panel",
    "yan_yana": "yan yana iki dikey panel",
    "uc": "üstte geniş bir, altta yan yana iki panel",
}

# ---------------------------------------------------------------- özel kartlar
KARTLAR = {
    "gercek": "GERÇEK BİLGİ kartı: bölümün tek gerçek bilgisi (metin) ve kaynağı",
    "ipucu": "izleyicinin bildiği, karakterin bilmediği şey (başlık, ör. 'SEN BİLİYORSUN, KUZEY BİLMİYOR')",
    "ab": "son sahne: ekran makasla kırmızı A ve camgöbeği B paneline bölünür; a ve b seçenekleri",
}

KONUMLAR = ("sol", "orta", "sag")
CERCEVELER = ("bust", "boy")
BALON_TURLERI = ("konus", "dusun", "bagir")

SERI_ADI = "KARAR SENİN"
KURGU_ETIKETI = "KURGU"
AB_CAGRI = "YORUMLARA A YA DA B YAZ"
AB_ALT = "Oylama 24 saat açık · Kurgusal hikâye"
AB_SONRAKI = "En çok oy alan yol {sonraki}. bölüm olur."
AB_SONRAKI_NUMARASIZ = "En çok oy alan yol sonraki bölüm olur."
GERCEK_BASLIK = "GERÇEK BİLGİ"
