# Otomatik paylaşım kurulumu

Telegram'da **Onayla** dedikten sonra saat seçersin (Şimdi / Bugün 19:00 / Yarın 12:00 / Yarın 19:00).
Saati gelince video bağlı olan platformlara otomatik yüklenir ve sonuç linkleriyle birlikte Telegram'a yazılır.
Kontrol 10 dakikada bir yapıldığı için paylaşım seçilen saatten birkaç dakika sonra gerçekleşebilir.

Her platform ayrı bağlanır. Bağlı olmayan platform atlanır, diğerleri çalışmaya devam eder.
Tüm anahtarlar yalnızca **GitHub → depo → Settings → Secrets and variables → Actions → New repository secret** alanına girilir. Sohbete veya dosyalara yazılmaz.

---

## 1. YouTube

1. https://console.cloud.google.com adresinde yeni bir proje aç (ör. "Bilgi Makasi").
2. **APIs & Services → Library** bölümünden **YouTube Data API v3**'ü etkinleştir.
3. **OAuth consent screen** sayfasında:
   - User type: **External**.
   - Uygulama adı ve e-posta alanlarını doldur.
   - Kapsam olarak `https://www.googleapis.com/auth/youtube.upload` ekle.
   - **Test users** listesine kendi Google hesabını ekle.
   - Ardından **Publish app** ile durumu **In production** yap. "Testing" durumunda kalırsa oturum 7 günde bir düşer.
4. **Credentials → Create credentials → OAuth client ID** adımında:
   - Tür olarak **Web application** seç.
   - Authorized redirect URI alanına `https://developers.google.com/oauthplayground` yaz.
   - Client ID ve Client secret değerlerini not al.
5. https://developers.google.com/oauthplayground adresine git:
   - Sağ üstteki dişliye tıkla, **Use your own OAuth credentials** kutusunu işaretle, Client ID ve secret'ı gir.
   - Soldaki kutuya `https://www.googleapis.com/auth/youtube.upload` yaz ve **Authorize APIs** de.
   - Kanalın bağlı olduğu Google hesabıyla giriş yap. "Doğrulanmamış uygulama" uyarısında **Gelişmiş → devam et** de.
   - **Exchange authorization code for tokens** de ve **Refresh token** değerini kopyala.
6. GitHub Secrets'a şu üç değeri ekle: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

**Not:** Google, denetimden geçmemiş uygulamalarla yüklenen videoları **gizli** olarak kilitler.
Herkese açık paylaşım için Google Cloud'da **YouTube API Services Audit** formu doldurulur. Onay birkaç gün ile birkaç hafta sürebilir.
O zamana kadar videolar YouTube'a gizli olarak yüklenir. YouTube Studio'dan tek tıkla herkese açık yapılabilir.

## 2. Instagram

Hesap **Profesyonel** olmalı (İşletme veya İçerik üreticisi). Bu yöntemde Facebook sayfası gerekmez.

1. https://developers.facebook.com adresinde **My Apps → Create app** adımına git. Kullanım alanı olarak **Instagram API** seçeneğini seç.
2. Uygulamada **Instagram → API setup with Instagram login** bölümüne gir:
   - **Add account** ile @bilgimakasi hesabını bağla.
   - **Generate token** de.
   - Çıkan uzun anahtarı ve hesabın kullanıcı numarasını (Instagram user ID) not al.
3. GitHub Secrets'a şu iki değeri ekle: `IG_ACCESS_TOKEN`, `IG_USER_ID`.

Meta'nın yeni "Birleşik giriş" (Unified login) ekranında üretilen anahtar `EAA` ile başlar; kod bunu da tanır (graph.facebook.com üzerinden çalışır).
Bu ekranda işletme portföyü seçmek zorunludur. Anahtar **Generate token** linkiyle üretilir ve yalnızca bir kez gösterilir.
`IG` ile başlayan anahtar 60 gün geçerlidir ve her paylaşımda yenilenir.
Yenilenen anahtarın GitHub'a otomatik kaydedilmesi için aşağıdaki **GH_SECRETS_PAT** adımını da yap. Yapmazsan 60 günde bir 2. adımı tekrarlaman gerekir.

## 3. TikTok

1. https://developers.tiktok.com adresinde bir geliştirici hesabı ve uygulama oluştur.
2. Uygulamaya şu ürünleri ekle:
   - **Login Kit**
   - **Content Posting API**: **Direct Post** seçeneğini aç.
3. İzin olarak `video.publish` ve `user.info.basic` ekle.
4. Redirect URI olarak `https://github.com/sabriemin/bilgimakasi` yaz. Giriş sonrası adres çubuğunda çıkan kodu kopyalamak için kullanılır.
5. Bağlantı adımı için bana haber ver, birlikte yapacağız: giriş linkini hazırlayıp kodu anahtara çevireceğiz.
6. GitHub Secrets'a şu üç değeri ekle: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`.

**Not:** TikTok, uygulama incelemesinden geçene kadar API ile yüklenen videoları yalnızca **"Yalnızca ben"** gizliliğiyle kabul eder.
İnceleme başvurusu geliştirici panelinden yapılır.
Başvuruda gizlilik politikası ve kullanım koşulları sayfası istenir. Bu sayfaları biz hazırlayabiliriz.

## 4. (Önerilen) Anahtarların kendiliğinden yenilenmesi: GH_SECRETS_PAT

1. GitHub'da **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token** adımına git.
2. Ayarları şöyle yap:
   - Repository access: **Only select repositories → bilgimakasi**
   - Permissions: **Secrets: Read and write**
3. Çıkan anahtarı `GH_SECRETS_PAT` adıyla Secrets'a ekle.

## 5. Telegram kapısı ve yönetim paneli: KAPI_PAT

Telegram kapısı (Cloudflare Worker) internete açıktır; bu yüzden `GH_SECRETS_PAT` yerine ayrı ve dar yetkili bir anahtar kullanır.

1. **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Ayarlar:
   - Repository access: **Only select repositories → bilgimakasi** (site deposu seçilmez)
   - Permissions: **Actions: Read and write**, **Contents: Read-only** (Metadata: Read-only kendiliğinden gelir)
3. Çıkan anahtarı `KAPI_PAT` adıyla Secrets'a ekle.
4. Actions'ta **Telegram kapısını kur** işini çalıştır. `KAPI_PAT` yoksa iş geçici olarak `GH_SECRETS_PAT` kullanır ve uyarı yazar.

Panel: Telegram'da `/panel` yaz. Gelen bağlantı 10 dakika geçerli ve tek kullanımlıktır. Her girişte sohbete bildirim gelir.
Oturum o tarayıcıda 30 gün açık kalır; paneldeki **Çıkış yap** yalnız o tarayıcıyı kapatır.
**Telegram kapısını kur** işi her çalıştığında imza anahtarı yenilenir ve bütün panel oturumları kapanır.

## İsteğe bağlı ayarlar (Variables sekmesi)

- `YT_PRIVACY`: `public` (varsayılan), `unlisted` veya `private`.
- `TIKTOK_PRIVACY`: `PUBLIC_TO_EVERYONE` (varsayılan). İzin yoksa kendiliğinden `SELF_ONLY` olur.
- `TIKTOK_HANDLE`: TikTok kullanıcı adı (link için, varsayılan `bilgimakasi`).

## Yapay zekâ etiketi

- YouTube'da "değiştirilmiş veya yapay içerik" bilgisi işaretlenir.
- TikTok'ta "AI-generated content" etiketi açılır.
- Açıklamada seslendirmenin yapay zekâ ile yapıldığı yazar.
