"""Görsel denetimi: bulunan fotoğraf sahnenin anlattığı şeyi gerçekten gösteriyor mu?

Wikimedia/Openverse aramaları başlık ve etiketle eşleşir; bu yüzden ör. kedi belgeselinde 'göz açılması' sorgusu insan
bebeği fotoğrafı getirebiliyordu. Her videoda bütün fotoğraflar küçük önizlemeler hâlinde tek bir Claude çağrısıyla
gözle denetlenir. Uygun olmayan fotoğraf atılır, o sahne çizimle (illustrate) anlatılır.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List

from PIL import Image
from pydantic import BaseModel, Field

from .script import ask_claude

SYSTEM = """Sen bir belgesel görsel editörüsün. Her sahne için bir fotoğraf önizlemesi verilir. Read aracıyla her dosyaya BAK
ve fotoğrafın o sahnenin anlattığı şeyi gösterip göstermediğine karar ver.
UYGUN DEĞİL say:
- Konunun ana öznesi yanlışsa (ör. kedi videosunda insan, köpek ya da başka hayvan; kan videosunda alakasız bir nesne).
- Hayvan/doğa konusunda fotoğrafta insan öne çıkıyorsa ya da hayvan hiç görünmüyorsa.
- Harita, şema, logo, arma, metin sayfası, pul ya da afiş ise (sahne bunu açıkça istemiyorsa).
- Sahnedeki evreyle bariz çelişiyorsa (ör. 'yeni doğmuş yavru' sahnesinde yaşlı yetişkin hayvan).
- Bulanık, çok küçük, ekran görüntüsü ya da üzerinde büyük yazı/filigran varsa.
UYGUN say: konu öznesini açıkça gösteren, sahneyle çelişmeyen fotoğrafları (birebir aynı an olmak zorunda değil).
Emin değilsen UYGUN DEĞİL de: yerine çizim yapılır, yanlış fotoğraf göstermekten iyidir."""


class Karar(BaseModel):
    scene: int = Field(description="Sahne numarası")
    uygun: bool = Field(description="Fotoğraf sahneyi doğru gösteriyor mu")
    gorulen: str = Field(description="Fotoğrafta ne görüldüğü, 3-8 kelime")


class Kararlar(BaseModel):
    items: List[Karar]


def acik() -> bool:
    return os.environ.get("GORSEL_DENETIM", "1") != "0"


def denetle(adaylar: dict[int, tuple[Path, str]], topic: str, calisma: Path) -> dict[int, str]:
    """adaylar: {sahne: (fotoğraf, sahnenin anlattığı)}. Uygun OLMAYAN sahneleri {sahne: görülen} döndürür.
    Claude'a ulaşılamazsa hiçbir fotoğraf atılmaz (üretim durmaz)."""
    if not adaylar or not acik():
        return {}
    calisma.mkdir(parents=True, exist_ok=True)
    satirlar = []
    for i, (p, ne) in sorted(adaylar.items()):
        kucuk = calisma / f"sahne_{i:02d}.jpg"
        try:
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((448, 448))
                im.save(kucuk, quality=80)
        except Exception as e:  # noqa: BLE001
            print(f"Görsel denetimi: sahne {i} açılamadı ({e}); atılıyor")
            continue
        satirlar.append(f"- Sahne {i}: dosya {kucuk} | anlatılan: {ne}")
    if not satirlar:
        return {i: "açılamadı" for i in adaylar}
    prompt = (f"Video konusu: {topic}\n\nHer sahnenin önizlemesine Read ile bak ve 'items' listesinde karar ver:\n"
              + "\n".join(satirlar))
    try:
        res = ask_claude(prompt, Kararlar, SYSTEM, tools=["Read"])
    except Exception as e:  # noqa: BLE001
        print(f"::warning::Görsel denetimi yapılamadı ({str(e)[:120]}); fotoğraflar olduğu gibi kullanılıyor")
        return {}
    kotu = {k.scene: k.gorulen for k in res.items if k.scene in adaylar and not k.uygun}
    acilamayan = {i: "açılamadı" for i in adaylar if not (calisma / f"sahne_{i:02d}.jpg").exists()}
    kotu.update(acilamayan)
    for i, g in sorted(kotu.items()):
        print(f"Görsel denetimi: sahne {i} fotoğrafı konuya uymuyor ({g}); çizim yapılacak")
    shutil.rmtree(calisma, ignore_errors=True)
    return kotu
