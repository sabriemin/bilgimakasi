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
    """Metni seslendirir, mp3 yazar ve kelime zamanlarını döndürür."""
    key = os.environ["ELEVENLABS_API_KEY"]
    voice = os.environ.get("ELEVENLABS_VOICE_ID", "")
    if not voice:
        raise RuntimeError("ELEVENLABS_VOICE_ID tanımlı değil (.env dosyasına ekleyin).")
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_v3"),
            "language_code": "tr",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.15, "speed": 1.0},
        },
        timeout=300,
    )
    if r.status_code == 400 and "language_code" in r.text:  # bazı modeller language_code kabul etmez
        r = requests.post(r.request.url, headers={"xi-api-key": key}, json={
            "text": text, "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_v3")}, timeout=300)
    r.raise_for_status()
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
