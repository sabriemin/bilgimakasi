# shortgen: otomatik short video üretici

Örnek videodaki kolaj/fanzin tarzında, 9:16, 60-75 saniyelik Türkçe short videolar üretir.

## Akış
1. **Senaryo** (`shortgen/script.py`): Claude, çeşitli kategorilerden (bilim, uzay, psikoloji, tarih, doğa, ekonomi...) daha önce işlenmemiş bir konu seçer ve sahne sahne senaryo yazar. İkinci bir geçiş bilgileri kontrol edip düzeltir. İşlenen konular `history.jsonl` dosyasında tutulur ve tekrar edilmez.
2. **Görseller** (`shortgen/images.py`): Wikimedia Commons'tan yalnızca kamu malı, CC0, CC BY veya CC BY-SA lisanslı fotoğraflar alınır. Lisans atıfları açıklamaya otomatik eklenir. Uygun görsel bulunamazsa sahne tipografik olur.
3. **Ses** (`shortgen/voice.py`): ElevenLabs ile Türkçe dış ses ve kelime kelime zamanlama.
4. **Kurgu** (`shortgen/render.py`): Duotone fotoğraflar, yırtık kâğıt dokusu, etiket kutulu başlıklar, kelime vurgulu altyazı, 1080x1920 30 fps H.264. Müzik verilirse konuşma altında otomatik kısılır.
5. **Yayın paketi**: Her video `output/<tarih>_<konu>/` klasörüne `video.mp4`, `metadata.json` (başlık, açıklama, etiketler, kaynaklar, görsel atıfları) ve `script.json` olarak çıkar. Durumu `onay_bekliyor` olarak işaretlenir.

## Kurulum
Gereken: Python 3.10+, FFmpeg, Node.js ve Claude Code (`npm install -g @anthropic-ai/claude-code`).
Claude, claude.ai aboneliğiyle kullanılır. Aylık eşdeğer harcama `CLAUDE_MONTHLY_BUDGET_USD` (varsayılan 100 $) aşılırsa üretim durur.

    pip install -r requirements.txt
    cp .env.example .env   # anahtarları doldurun

## Çalıştırma

    python -m shortgen.pipeline                      # yeni konu seç, üret
    python -m shortgen.pipeline --topic "ahtapotların zekâsı"
    python -m shortgen.pipeline --script demo/demo_script.json --no-voice   # anahtarsız deneme

Günde 2 video için zamanlayıcıya (cron, Windows Görev Zamanlayıcı veya GitHub Actions) günde iki çalıştırma eklenir.

## Onay ve otomatik paylaşım
Her video Telegram'a gelir. **Onayla** denince saat seçilir (Şimdi / Bugün 19:00 / Yarın 12:00 / Yarın 19:00); saati gelince
`shortgen/publish.py` videoyu YouTube Shorts, Instagram Reels ve TikTok'a yükler ve linkleri Telegram'a yazar.
Hata olan platform için "Hatalıları tekrar dene" düğmesi çıkar. Platform bağlantıları: `docs/PAYLASIM_KURULUM.md`.

## Şablonlar
`templates/` klasöründe her şablon bir JSON dosyasıdır: renkler, fontlar, altyazı boyutu ve konumu, başlık ölçeği.
Hazır şablonlar: `kolaj` (örnek videodaki tarz), `gece` (lacivert, camgöbeği, pembe, yıldızlar), `doga` (yeşil, turuncu, krem), `minimal` (beyaz, siyah, mavi, kutusuz), `retro` (70'ler renkleri, tırnaklı harfler), `gazete` (eski gazete sayfası).
Şablon ayarları: `label_style` (box/plain), `rotation`, `text_entry` (pop/slide/wipe/drop), `subtitle_box` (torn/pill/plain), `stars`, `case`.
`"renderer"` alanı olan şablonlar kendi kurgu modülüyle çizilir: `kart` → `shortgen/kart.py`, `nasil` → `shortgen/nasil.py`.

### Nasıl yapılır? şablonu (`nasil`, "Adım kartları")
Sarı noktalı zemin, üstte "NASIL YAPILIR?" etiketi ve ADIM n/N, 1-2-3-4 ilerleme çubuğu (makas bir sonraki düğüme
keser), numaralı adım kartı (kırmızı yırtık numara, başlık, çizim, en çok 2 küçük not) ve kartı gösteren Makas.
Kinetik altyazı yoktur: dış sesin her kelimesi Makas'ın konuşma balonunda (özette NEDEN?/SENCE? kutusunda) okunduğu
anda sarı yazılır, sessiz izleyen de takip eder; sondaki "Yorumlara yaz." kutuya değil, söylendiği anda çıkan YORUMLARA
YAZ çıkartmasına yazılır. Senaryo eşlemesi: ilk sahne kanca (soru başlığı + çizim), `step` alanı 1, 2, 3... olan
sahneler adım kartları (başlığın ilk satırı `ADIM n`, `callouts` küçük notlar; adımsız ara sahneler adımın devamı), en
son sahne özet (adım listesi + "neden" + soru). Bu düzen (`NASIL_RULES`, editörde başlıkların korunması) yalnız video
`nasil` şablonuyla çizilecekse Claude'dan istenir; `yapi_sablon` kart'ı gösterirken nasil senaryoları genel sahne
kurallarıyla yazılır. Adım numaraları her iki yolda `normalize_nasil` ile sağlamlaştırılır. `nasil` şablonu başka
kalıptaki senaryoyla kullanılmaz (pipeline durur). Marka kapanışı kart şablonuyla ortaktır.

    python -m shortgen.pipeline --script demo/nasil/ornek_cay.json --template nasil --no-voice   # anahtarsız deneme
    python -m shortgen.pipeline --topic "çay nasıl demlenir" --template nasil                   # nasil kalıbıyla yazılır

`--template nasil` kalıp verilmemişse senaryoyu `nasil` kalıbıyla yazdırır. Nasıl yapılır? serisinin otomatik olarak
bu şablona gitmesi için `templates/eslesme.json` → `yapi_sablon` içinde `"nasil": "kart"` değerini `"nasil"` yapın
(onaydan önce `kart` kalır). Claude'un şablon önerisi `kart`, `nasil` ve `uretim`'i seçemez (çizicisi `kart` ya da
`nasil` olan şablonlar yalnız kendi kalıbıyla ya da `yapi_sablon` ile seçilir).

## Animasyonlar
Claude, anlatılan şey doğal olarak hareket ediyorsa sahneye bir nesne animasyonu ekler (`shortgen/anim.py`):
`fly_up` (roket, mekik), `fly_right` / `fly_left` (uçak, kuş, tren), `drop_in`, `zoom_in`, `float`, `spin`, `orbit`, `pulse`, `shake`.
Nesne Wikimedia'da önce şeffaf PNG olarak aranır; bulunamazsa fotoğrafın arka planı `rembg` ile silinir. Uçan nesnelerin arkasında duman izi oluşur.
`templates/eslesme.json` hangi kategorinin hangi şablonu kullanacağını belirler. `claude_secsin: true` yapılırsa Claude her konu için şablonu kendisi önerir.
`yapi_sablon` anlatım kalıbına göre şablon seçer ve kategori eşleşmesinden önce gelir (şimdilik `nasil` → `kart`,
`uretim` → `uretim`, `olsaydin` → `kart`).
Elle seçmek için: `python -m shortgen.pipeline --template gece`

## Konu önerileri
`/oneri` (ya da paneldeki "Yeni öneriler iste") tek bir web aramalı Claude çağrısıyla altı seriden üçer, toplam 18
öneri getirir (Telegram'da üçer serilik iki mesaj): 🔥 Popüler (bugünün gündemine bağlı şaşırtıcı açı), 📚 Konular
(gündemden bağımsız şaşırtıcı konu), 🧐 Efsane mi, gerçek mi? (Türkiye'de yaygın yanlış inanış), 🛠 Nasıl yapılır?
(3-5 adımlık güvenli, pratik yöntem), 🏭 Nasıl üretiliyor? (gündelik bir ürünün hammaddeden bitmiş ürüne 3-5 aşamada
üretimi) ve 💭 `olsaydin` serisi (izleyiciyi bir mesleğe, para olayına ya da hayat durumuna koyan, güncel Türkiye
rakamlarıyla "olsaydın ne olurdu" hesabı; serinin adı geçicidir: ekran etiketi `script.STRUCTURES`, liste adı
`trends.SERILER`, panel adı `cloudflare/panel_ui.js` `ONERI_SERILERI`, seri etiketi `publish.SERIES_TAGS` içindedir).
Öneriden üretimde serinin kalıbı sabitlenir: efsane → `efsane`, nasıl yapılır → `nasil`, nasıl üretiliyor → `uretim`,
`olsaydin` → `olsaydin` (`--structure`).
Otomatik üretim yalnız ilk üç seriden seçer (son video efsane kalıbındaysa Efsane önerisini atlar), kendi önerilerini
kaydetmez; `nasil`, `uretim` ve `olsaydin` kalıpları otomatik dönüşüme girmez. Konu sırası yalnız metni tuttuğu için
Efsane, Nasıl yapılır?, Nasıl üretiliyor? ve `olsaydin` önerileri sıraya eklenmez, yalnız "Üret" ile üretilir.
Telegram düğmeleri listenin damgasını taşır: liste yenilendikten sonra eski mesajdan basılan düğme başka bir konuyu
üretmez.

## GitHub Actions ve Telegram
- `uret.yml`: her gün 09:00 ve 18:00'de (Türkiye saati) video üretir, GitHub Releases'a koyar ve Telegram'a Onayla / Reddet düğmeleriyle gönderir.
- `onay.yml`: 10 dakikada bir Telegram'daki düğme basışlarını ve komutları işler. Durumlar `state/videos.json` dosyasında tutulur.
- Bot komutları: `/durum` (bekleyen videolar), `/uret konu` (hemen yeni video).
- `ornek.yml` (elle): yeni bir şablonu denemek için yayınlanmayan, kaydedilmeyen örnek video üretip Telegram'a gönderir.
  Girdiler: `senaryo` (ör. `demo/nasil/ornek_cay.json`) ya da `konu`, `sablon` (ör. `nasil`), isteğe bağlı `kalip`
  (yalnız konuyla üretimde anlatım kalıbını sabitler, ör. `nasil`; küçük harf dışı değer reddedilir) ve `not`.

Depo ayarlarında **Settings → Secrets and variables → Actions** altına şu gizli anahtarları ekleyin:
`CLAUDE_CODE_OAUTH_TOKEN`, `ELEVENLABS_API_KEY`, ``TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## Marka (Bilgi Makası)
`brand.json` ile açılıp kapatılır. Videolara şunlar eklenir:
- Köşeler arasında yer değiştiren yarı saydam filigran (`assets/brand/video_filigran.png`)
- Açılışta ekranı kesen makas ve yerine düşen filigran
- Her 4 sahnede bir makasla kesme geçişi
- Altyazı kutusunun köşesinde @bilgimakasi (altyazıyı kırpmadan silinemez)
- Kapanış kartı varsayılan olarak kapalı (`brand.json` → `outro_seconds: 0`); video son sözden hemen sonra biter ki başa sarınca döngü kopmasın
