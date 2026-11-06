"""ElevenLabs seslendirme + kelime zamanlaması.

Tek sesli yol (synthesize): bütün dış ses anlatıcının sesiyle (ELEVENLABS_VOICE_ID) tek istekte seslendirilir.
Çok sesli yol (parcala + synthesize_parcali): şablon bir ses haritası verirse ("sesler": {karakter kimliği: ses
kimliği}) dış ses anlatıcı ve karakter parçalarına bölünür; konuşma balonundaki söz (dış seste tırnak içinde) o
karakterin sesiyle, geri kalanı anlatıcıyla seslendirilir. Parçaların sesi uç uca eklenir, kelime zamanları
parçanın başladığı ana kaydırılarak birleşir. Karakter sesi hata verirse o parça anlatıcının sesiyle seslendirilir
(üretim durmaz). Sahne araları (duraklat) ses ve kelime zamanlarına aynı anda eklenir."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass
class Word:
    text: str
    start: float
    end: float


def _words_from_alignment(al: dict) -> list[Word]:
    chars, starts, ends = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, s, e = [], "", None, None
    for ch, cs, ce in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append(Word(cur, s, e))
            cur, s = "", None
            continue
        if s is None:
            s = cs
        cur += ch
        e = ce
    if cur:
        words.append(Word(cur, s, e))
    return words


# VOICE_TEMPO'nun varsayılanı ve bu tempoda ölçülen ortalama konuşma hızı (kelime/sn; SPEC 6.1). Sessiz denemede
# şablon kendi temposunu verirse süre tahmini buna göre ölçeklenir (tahmin).
VARSAYILAN_TEMPO = 1.08
SES_HIZI = 2.15
SES_HATA_KODLARI = (401, 402, 403, 429)   # anahtar/kredi/plan sorunu: başka ses de denense fayda etmez


def _tempo(tempo: float | None) -> float:
    return float(tempo) if tempo is not None else float(os.environ.get("VOICE_TEMPO", str(VARSAYILAN_TEMPO)))


def synthesize(text: str, out_mp3: Path, tempo: float | None = None) -> list[Word]:
    """Metni seslendirir, mp3 yazar ve kelime zamanlarını döndürür (tempo ve baştaki sessizlik ayarı uygulanmış).
    tempo: verilmezse VOICE_TEMPO (varsayılan 1.08); şablon kendi temposunu verebilir (ör. cizgi: daha yavaş)."""
    words, aligned = _synthesize(text, out_mp3)
    return _tighten(words, out_mp3, trim=aligned, tempo=tempo)


def _tighten(words: list[Word], mp3: Path, trim: bool = True, tempo: float | None = None) -> list[Word]:
    """Kısa videoda her saniye önemli: baştaki sessizliği kırpar ve sesi perdesini bozmadan hızlandırır.
    VOICE_TEMPO=1 ile kapatılır (varsayılan 1.08); tempo verilirse ortam değişkeninin yerine geçer."""
    import subprocess
    tempo = _tempo(tempo)
    # baş kırpma yalnız kelime zamanları gerçekten ölçüldüyse (tahmini zamanla ilk kelimenin başı kesilebilir)
    cut = max(0.0, words[0].start - 0.05) if (trim and words) else 0.0
    if abs(tempo - 1.0) < 0.01 and cut < 0.1:
        return words
    tmp = mp3.with_name(mp3.stem + "_ham.mp3")
    mp3.replace(tmp)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{cut:.3f}", "-i", str(tmp),
                        "-filter:a", f"atempo={tempo}", "-b:a", "128k", str(mp3)], capture_output=True, text=True)
    if r.returncode != 0:  # ayar başarısızsa ham sesi kullan
        print("Ses hızlandırılamadı:", r.stderr[:300])
        tmp.replace(mp3)
        return words
    tmp.unlink(missing_ok=True)
    print(f"Ses: baştan {cut:.2f} sn kırpıldı, tempo x{tempo}")
    return [Word(w.text, max(0.0, (w.start - cut) / tempo), max(0.0, (w.end - cut) / tempo)) for w in words]


class SesHatasi(RuntimeError):
    """ElevenLabs seslendirmesi başarısız; kod: son yanıtın HTTP kodu (anahtar/kredi sorununu ayırmak için)."""

    def __init__(self, mesaj: str, kod: int = 0):
        super().__init__(mesaj)
        self.kod = kod


def _synthesize(text: str, out_mp3: Path, voice_id: str | None = None) -> tuple[list[Word], bool]:
    """voice_id: verilmezse anlatıcının sesi (ELEVENLABS_VOICE_ID); çok sesli yolda karakterin sesi."""
    key = os.environ["ELEVENLABS_API_KEY"]
    voice = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "")
    if not voice:
        raise RuntimeError("ELEVENLABS_VOICE_ID tanımlı değil (.env dosyasına ekleyin).")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"
    model = os.environ.get("ELEVENLABS_MODEL", "eleven_v3")
    body = {
        "text": text, "model_id": model, "language_code": "tr",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.15, "speed": 1.0},
    }
    if model == "eleven_v3":  # v3 yalnızca 0.0 / 0.5 / 1.0 stability kabul eder, style/speed desteklemez
        body["voice_settings"] = {"stability": 0.5, "similarity_boost": 0.8}
    attempts = [body, {"text": text, "model_id": model}]
    if model != "eleven_multilingual_v2":  # son çare: zaman damgası kesin destekli model
        attempts.append({"text": text, "model_id": "eleven_multilingual_v2", "language_code": "tr"})
    errors = []
    for b in attempts:
        r = requests.post(url, params={"output_format": "mp3_44100_128"},
                          headers={"xi-api-key": key, "Content-Type": "application/json"}, json=b, timeout=300)
        if r.ok:
            if b["model_id"] != model:
                print(f"UYARI: {model} reddetti, {b['model_id']} ile seslendirildi.")
            break
        errors.append(f"{b['model_id']} -> {r.status_code}: {r.text[:500]}")
        print("ElevenLabs hatası:", errors[-1])
        if r.status_code in SES_HATA_KODLARI:  # anahtar/kredi/plan sorunu: başka deneme fayda etmez
            break
    else:
        raise SesHatasi("ElevenLabs seslendirme başarısız:\n" + "\n".join(errors), r.status_code)
    if not r.ok:
        raise SesHatasi("ElevenLabs seslendirme başarısız:\n" + "\n".join(errors), r.status_code)
    data = r.json()
    out_mp3.write_bytes(base64.b64decode(data["audio_base64"]))
    al = data.get("normalized_alignment") or data.get("alignment")
    if al and al.get("characters"):
        return _words_from_alignment(al), True
    # Zamanlama dönmezse (bazı modeller): kelimeleri gerçek ses süresine göre dağıt
    return fit_to_duration(estimate(text), _duration(out_mp3)), False


def _duration(path: Path) -> float:
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def fit_to_duration(words: list[Word], total: float) -> list[Word]:
    k = (total - 0.2) / max(0.1, words[-1].end)
    return [Word(w.text, w.start * k, w.end * k) for w in words]


def estimate(text: str, wps: float = 2.6) -> list[Word]:
    """Ses yokken (deneme modu) kelime sürelerini tahmin eder."""
    words, t = [], 0.4
    for w in text.split():
        d = max(0.18, len(w) / (wps * 5.2))
        words.append(Word(w, t, t + d))
        t += d + (0.35 if w[-1] in ".?!" else 0.12 if w[-1] in ",;:" else 0.04)
    return words


def tahmin(text: str, tempo: float | None = None) -> list[Word]:
    """Sessiz deneme için kelime süreleri: tempo verilmezse estimate ile aynı. Şablon kendi temposunu verirse süre
    gerçek seslendirmenin hızına (SES_HIZI, VARSAYILAN_TEMPO'da) göre ölçeklenir: daha yavaş anlatıcı, daha uzun video."""
    words = estimate(text)
    if tempo is None or not words:
        return words
    hedef = 0.4 + len(words) / (SES_HIZI * float(tempo) / VARSAYILAN_TEMPO)
    k = hedef / max(0.1, words[-1].end)
    return [Word(w.text, w.start * k, w.end * k) for w in words]


# ---------------------------------------------------------------- çok sesli seslendirme
TIRNAK = "\"“”«»"
_NOKTALAMA = ".,!?;:…"


@dataclass
class Parca:
    """Seslendirilecek bir parça: art arda aynı sesle okunan kelimeler. konusan boşsa anlatıcı."""
    text: str
    konusan: str = ""

    @property
    def kelime(self) -> int:
        return len(self.text.split())


def tirnak_ici(texts: list[str]) -> list[bool]:
    """Her kelimenin tırnak içinde olup olmadığı (tırnak işareti kelimeye bitişik yazılır)."""
    out, ic = [], False
    for t in texts:
        acar = bool(t) and t[0] in TIRNAK
        if acar and not ic:
            ic = True
            kapar = len(t) > 1 and t.rstrip(_NOKTALAMA)[-1:] in TIRNAK
            out.append(True)
            if kapar:
                ic = False
            continue
        out.append(ic)
        if ic and t.rstrip(_NOKTALAMA)[-1:] in TIRNAK:
            ic = False
    return out


def _sade(t: str) -> str:
    return t.strip(TIRNAK + _NOKTALAMA + "'’").replace("İ", "i").replace("I", "ı").lower()


def soz_kelimeleri(tokens: list[str], soz: str = "") -> list[bool]:
    """Sahnenin dış sesinde karakterin söylediği kelimeler: tırnak içi; tırnak yoksa balon metninin dış seste aynen
    geçtiği yer (noktalama ve büyük harf yok sayılır). Bulunamazsa hiçbiri (sahne anlatıcıda kalır)."""
    ic = tirnak_ici(tokens)
    if any(ic):
        return ic
    hedef = [_sade(x) for x in soz.split() if _sade(x)]
    if not hedef:
        return [False] * len(tokens)
    sade = [_sade(x) for x in tokens]
    for i in range(len(tokens) - len(hedef) + 1):
        if sade[i:i + len(hedef)] == hedef:
            return [i <= k < i + len(hedef) for k in range(len(tokens))]
    return [False] * len(tokens)


def parcala(sahneler: list[tuple[str, str, str]], sesler: dict[str, str]) -> list[Parca]:
    """Dış sesi anlatıcı ve karakter parçalarına böler. sahneler: her sahne için (dış ses, konuşan kimliği, balon
    metni); konuşan boşsa ya da ses haritasında yoksa sahnenin tamamı anlatıcıda kalır. Aynı sesin art arda gelen
    kelimeleri (sahne sınırını geçse de) tek parçadır: istek sayısı balon sayısıyla sınırlı kalır. Kelimeler ve
    sıraları değişmez (parçaların kelimeleri uç uca eklenince dış sesin kelimeleri çıkar)."""
    out: list[Parca] = []
    for metin, konusan, soz in sahneler:
        tokens = metin.split()
        bayrak = soz_kelimeleri(tokens, soz) if (konusan and sesler.get(konusan)) else [False] * len(tokens)
        for tok, b in zip(tokens, bayrak):
            k = konusan if b else ""
            if out and out[-1].konusan == k:
                out[-1].text += " " + tok
            else:
                out.append(Parca(tok, k))
    return out


def _metne_esle(words: list[Word], text: str) -> list[Word]:
    """Hizalamanın kelimeleri metnin kelimeleriyle aynı sayıdaysa yazılışı metinden alır (tırnaklar korunur: kurgu
    tırnak içini balona yazar)."""
    tokens = text.split()
    if len(tokens) != len(words):
        return words
    return [Word(t, w.start, w.end) for t, w in zip(tokens, words)]


def _wav(mp3: Path) -> tuple[Path, float]:
    """Parçayı tek kanallı 44.1 kHz WAV'a açar; süre örnek sayısından (mp3 dolgusu kaymaya yol açmasın)."""
    import subprocess
    import wave
    wav = mp3.with_suffix(".wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le",
                    str(wav)], check=True, capture_output=True, text=True)
    with wave.open(str(wav), "rb") as w:
        return wav, w.getnframes() / w.getframerate()


def _birlestir(wavlar: list[Path], out_mp3: Path) -> None:
    """WAV parçalarını uç uca ekleyip tek mp3 yazar (örnekler birebir: kelime zamanları kaymaz)."""
    import subprocess
    import wave
    birlesik = out_mp3.with_name(out_mp3.stem + "_birlesik.wav")
    with wave.open(str(birlesik), "wb") as o:
        o.setnchannels(1)
        o.setsampwidth(2)
        o.setframerate(44100)
        for f in wavlar:
            with wave.open(str(f), "rb") as w:
                o.writeframes(w.readframes(w.getnframes()))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(birlesik), "-b:a", "128k", str(out_mp3)], check=True,
                   capture_output=True, text=True)
    birlesik.unlink(missing_ok=True)


def synthesize_parcali(parcalar: list[Parca], out_mp3: Path, sesler: dict[str, str],
                       tempo: float | None = None) -> list[Word]:
    """Parçaları kendi sesleriyle seslendirir, sesi uç uca ekler ve kelime zamanlarını kaydırarak birleştirir.
    Yalnız anlatıcıdan oluşan tek parça synthesize ile aynıdır. Karakter sesi reddedilirse (ör. ses kimliği yok)
    o parça günlüğe yazılarak anlatıcının sesiyle seslendirilir; anahtar/kredi hatası (401/402/403/429) olduğu gibi
    yükselir."""
    parcalar = [p for p in parcalar if p.text.strip()]
    if len(parcalar) == 1 and not parcalar[0].konusan:
        return synthesize(parcalar[0].text, out_mp3, tempo=tempo)
    klasor = out_mp3.parent / (out_mp3.stem + "_parcalar")
    klasor.mkdir(parents=True, exist_ok=True)
    words: list[Word] = []
    dosyalar: list[Path] = []
    t = 0.0
    for k, p in enumerate(parcalar):
        f = klasor / f"{k:02d}.mp3"
        ses = sesler.get(p.konusan) if p.konusan else None
        try:
            ws, aligned = _synthesize(p.text, f, voice_id=ses)
        except SesHatasi as e:
            if not ses or e.kod in SES_HATA_KODLARI:
                raise
            print(f"Ses: {p.konusan} için karakter sesi kullanılamadı (HTTP {e.kod}); parça anlatıcının sesiyle "
                  "seslendiriliyor.")
            ws, aligned = _synthesize(p.text, f)
        if ses:
            print(f"Ses: {p.konusan} sesiyle {p.kelime} kelime")
        ws = _metne_esle(_tighten(ws, f, trim=aligned, tempo=tempo), p.text)
        words += [Word(w.text, w.start + t, w.end + t) for w in ws]
        wav, d = _wav(f)
        f.unlink(missing_ok=True)
        dosyalar.append(wav)
        t += d
    _birlestir(dosyalar, out_mp3)
    for f in dosyalar:
        f.unlink(missing_ok=True)
    try:
        klasor.rmdir()
    except OSError:
        pass
    return words


# ---------------------------------------------------------------- sahne araları
def duraklat(words: list[Word], mp3: Path | None, sinirlar: list[int], sure: float) -> list[Word]:
    """Sahne sınırlarına (yeni sahnenin ilk kelimesinin indeksi) sure saniyelik sessizlik ekler: kesim iki kelimenin
    arasındaki boşluğun ortasından yapılır, sonraki kelimeler kayar. mp3 yoksa (sessiz deneme) yalnız zamanlar kayar."""
    sinirlar = sorted({k for k in sinirlar if 0 < k < len(words)})
    if sure <= 0 or not sinirlar:
        return words
    kesim = [(words[k - 1].end + words[k].start) / 2 for k in sinirlar]
    out, j = [], 0
    for i, w in enumerate(words):
        while j < len(sinirlar) and sinirlar[j] <= i:
            j += 1
        out.append(Word(w.text, w.start + j * sure, w.end + j * sure))
    if mp3 is not None:
        import subprocess
        fmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono"
        parts, adlar, onceki = [], [], 0.0
        for j, c in enumerate(kesim):
            parts.append(f"[0:a]atrim=start={onceki:.3f}:end={c:.3f},asetpts=PTS-STARTPTS,{fmt}[p{j}]")
            parts.append(f"anullsrc=r=44100:cl=mono,atrim=duration={sure:.3f},{fmt}[z{j}]")
            adlar += [f"[p{j}]", f"[z{j}]"]
            onceki = c
        parts.append(f"[0:a]atrim=start={onceki:.3f},asetpts=PTS-STARTPTS,{fmt}[son]")
        adlar.append("[son]")
        filt = ";".join(parts) + ";" + "".join(adlar) + f"concat=n={len(adlar)}:v=0:a=1[a]"
        tmp = mp3.with_name(mp3.stem + "_aralar.mp3")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-filter_complex", filt, "-map", "[a]",
                            "-b:a", "128k", str(tmp)], capture_output=True, text=True)
        if r.returncode != 0:  # ara eklenemezse ses ve zamanlar eskisi gibi kalır
            print("Sahne araları eklenemedi:", r.stderr[:300])
            tmp.unlink(missing_ok=True)
            return words
        tmp.replace(mp3)
        print(f"Ses: {len(kesim)} sahne arasına {sure:.2f} sn duraklama")
    return out
