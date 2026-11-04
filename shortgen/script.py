"""Konu seçimi ve senaryo üretimi.

Claude'a Claude Code CLI üzerinden, kullanıcının claude.ai aboneliğiyle (CLAUDE_CODE_OAUTH_TOKEN) erişilir.
Yapılandırılmış çıktı için --json-schema kullanılır. Doğrulama adımı web araması yapabilir.
Aylık harcama tavanı: state/claude_usage.json içinde tutulan eşdeğer maliyet CLAUDE_MONTHLY_BUDGET_USD'yi aşarsa üretim durur.
"""
from __future__ import annotations

import datetime as dt
import json
import os
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


class Scene(BaseModel):
    narration: str = Field(description="Dış seste okunacak Türkçe cümle(ler). 4-14 kelime.")
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


class ShortScript(BaseModel):
    topic: str
    category: Literal[tuple(CATEGORIES)] = Field(description="Konunun kategorisi.")  # type: ignore[valid-type]
    template: str = Field(default="", description="Önerilen görsel şablon adı (listeden) veya boş.")
    title: str = Field(description="Platform başlığı, en fazla 70 karakter, merak uyandıran.")
    description: str = Field(description="2-3 cümlelik açıklama + soru.")
    hashtags: List[str]
    scenes: List[Scene]
    sources: List[str] = Field(description="İddiaları destekleyen güvenilir kaynak başlıkları veya URL'leri.")


SYSTEM = """Sen Türkçe kısa video (YouTube Shorts / Reels / TikTok) senaristisin.
Biçim: 60-70 saniye. Seslendirme yavaş ve tane tane olduğu için toplam dış ses 120-135 kelimeyi GEÇMESİN.
16-22 sahne, her sahne 2-4 saniye.
Yapı: 1) İlk 2 sahnede güçlü merak kancası (bir fotoğrafa/duruma işaret eden, "Peki neden...?" sorusu),
2) bağlam (yıl, yer, kişi), 3) gerilim veya şaşırtıcı dönüm noktası, 4) vurucu cümle/alıntı,
5) bugüne bağlama, 6) son sahnede izleyiciye açık uçlu soru ve "Yorumlarda buluşalım." çağrısı.
Ton: sakin, hikâye anlatıcısı, kısa cümleler, abartısız. Sadece doğrulanabilir bilgiler kullan;
emin olmadığın tarih, sayı veya alıntıyı kullanma. Tartışmalı siyasi, dinî, sağlıkla ilgili iddialardan,
yaşayan özel kişileri hedef alan içerikten kaçın.
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
en fazla iki kez kullan. icon sadece gerçekten anlam katıyorsa."""


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


def generate_script(history_file: Path, topic_hint: str | None = None,
                    templates: dict[str, str] | None = None) -> ShortScript:
    used = _history(history_file)[-200:]
    ask = (
        f"Bugün için yeni bir short senaryosu yaz. Konu önerisi: {topic_hint}." if topic_hint else
        "Bugün için yeni bir short senaryosu yaz. Şu kategorilerden birini seç ve az bilinen, şaşırtıcı, "
        f"doğrulanabilir bir hikâye bul: {', '.join(CATEGORIES)}."
    )
    if templates:
        ask += "\nGörsel şablonlardan konuya en uygun olanını 'template' alanına yaz:\n" + "\n".join(
            f"- {k}: {v}" for k, v in templates.items())
    if used:
        ask += "\nDaha önce işlenen konuları tekrar etme:\n- " + "\n- ".join(used)
    script = ask_claude(ask, ShortScript, SYSTEM)
    return verify_script(script)


class Review(BaseModel):
    ok: bool
    problems: List[str]
    fixed: ShortScript


def verify_script(script: ShortScript) -> ShortScript:
    """İkinci geçiş: bilgileri web aramasıyla doğrular, hataları düzeltir veya çıkarır."""
    review = ask_claude(
        "Aşağıdaki senaryodaki her olgusal iddiayı (tarih, sayı, isim, alıntı) web aramasıyla kontrol et. "
        "Yanlış ya da doğrulanamayan her bilgiyi düzelt veya çıkar, biçim kurallarına uymayan yerleri düzelt "
        "(özellikle toplam dış ses 135 kelimeyi geçmesin; boş sahne kalmasın). "
        "Kullandığın güvenilir kaynakları 'sources' alanına URL olarak yaz. Düzeltilmiş tam senaryoyu 'fixed' "
        "alanında döndür.\n\n" + script.model_dump_json(indent=1),
        Review, SYSTEM + "\n\nŞimdi editör ve doğruluk kontrolcüsüsün.", web=True)
    if review.problems:
        print("Doğrulama notları:", *review.problems, sep="\n - ")
    return review.fixed


def load_script(path: Path) -> ShortScript:
    return ShortScript.model_validate_json(path.read_text(encoding="utf-8"))
