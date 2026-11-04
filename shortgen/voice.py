"""ElevenLabs seslendirme + kelime zamanlaması."""
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


def synthesize(text: str, out_mp3: Path) -> list[Word]:
    """Metni seslendirir, mp3 yazar ve kelime zamanlarını döndürür (tempo ve baştaki sessizlik ayarı uygulanmış)."""
    return _tighten(_synthesize(text, out_mp3), out_mp3)


def _tighten(words: list[Word], mp3: Path) -> list[Word]:
    """Kısa videoda her saniye önemli: baştaki sessizliği kırpar ve sesi perdesini bozmadan hızlandırır.
    VOICE_TEMPO=1 ile kapatılır (varsayılan 1.08)."""
    import subprocess
    tempo = float(os.environ.get("VOICE_TEMPO", "1.08"))
    cut = max(0.0, (words[0].start if words else 0.0) - 0.05)
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


def _synthesize(text: str, out_mp3: Path) -> list[Word]:
    key = os.environ["ELEVENLABS_API_KEY"]
    voice = os.environ.get("ELEVENLABS_VOICE_ID", "")
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
        if r.status_code in (401, 402, 403, 429):  # anahtar/kredi/plan sorunu: başka deneme fayda etmez
            break
    else:
        raise RuntimeError("ElevenLabs seslendirme başarısız:\n" + "\n".join(errors))
    if not r.ok:
        raise RuntimeError("ElevenLabs seslendirme başarısız:\n" + "\n".join(errors))
    data = r.json()
    out_mp3.write_bytes(base64.b64decode(data["audio_base64"]))
    al = data.get("normalized_alignment") or data.get("alignment")
    if al and al.get("characters"):
        return _words_from_alignment(al)
    # Zamanlama dönmezse (bazı modeller): kelimeleri gerçek ses süresine göre dağıt
    return fit_to_duration(estimate(text), _duration(out_mp3))


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
