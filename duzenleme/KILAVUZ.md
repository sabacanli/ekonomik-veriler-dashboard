# Düzenleme Zaman Çizelgesi — yazım kılavuzu

Bu kılavuz, TCMB / BDDK / SPK belgelerinden **olay kaydı** çıkaran herkes (insan, Claude oturumu, otomatik koşu)
içindir. Okur finans profesyonelidir: çizelgeyi tarayıp "o tarihte ne değişmişti?" sorusuna saniyeler içinde yanıt
arar, ayrıntı için olaya tıklar. Bu yüzden her kayıt **somut, sayısal ve kaynağa sadık** olmalıdır.

## 1. Ne olaydır, ne değildir

**Olay:** finansal piyasaları, bankaları, yatırım kuruluşlarını ya da bunların müşterilerini bağlayan veya
fiyatlamayı etkileyen bir **karar, kural, parametre ya da uygulama değişikliği**. Örnekler: faiz kararı, zorunlu
karşılık oranı, kredi büyüme sınırı, kredi vadesi/taksit sınırı, risk ağırlığı, KKM kuralı, ihracat bedeli satış
oranı, açığa satış yasağı, devre kesici, halka arz ve fon kuralları, sermaye yeterliliği esnekliği, enflasyon
muhasebesi kararı, swap anlaşması, döviz müdahalesi, kripto varlık düzenlemesi, banka kuruluş/faaliyet izni ya da
iptali, TMSF'ye devir.

**Olay değildir (elenir):** toplantı, konferans, ziyaret, tören duyuruları; rapor yayım/bilgilendirme toplantısı
tarihleri; PPK toplantı özetleri (karar ayrı duyurudadır); hükûmete açık mektuplar; genel kurul; banknot tedavülü;
sınav, personel, başsağlığı; internet sitesi/sertifika duyuruları; dolandırıcılık uyarıları ve yalanlamalar; veri
yayımı ve istatistik yöntemi duyuruları; **tek bir şirketi** ilgilendiren izin, yaptırım ve başvurular
(istisna: banka kuruluş/faaliyet izinleri, banka faaliyet izni iptali, TMSF'ye devir ve piyasanın genelini
etkileyen toplu işlemler — bunlar olaydır). Faktoring, finansman, varlık yönetim, değerleme, bağımsız denetim ve
ödeme kuruluşu izinleri elenir. Düzenleme **taslakları** (görüşe açılan metinler) önem 1 olarak alınır.

Kararsız kalınan belge **elenmez**, önem 1 olarak yazılır.

## 2. Bir belge = kaç olay?

- Varsayılan: **bir belge → bir olay.** Aynı konuda birden çok parametre değişmişse hepsi tek olayın `detay`
  maddeleridir.
- Belge birbirinden bağımsız, **farklı konu başlıklarına** giren kararlar içeriyorsa en çok üç olaya bölünür
  (kimlikler `-b`, `-c` ekiyle).
- Aynı kararı anlatan birden çok belge (ör. BDDK basın açıklaması + Kurul kararı; SPK basın duyurusu + bülten
  duyurusu) **tek olayda** birleştirilir; `kaynak` listesine hepsi yazılır.
- Düzenli yinelenen kararlar (ör. açığa satış yasağının iki haftada bir uzatılması) her seferinde ayrı olaydır,
  önem 1.

## 3. Alanlar

| alan | kural |
|---|---|
| `id` | İlk kaynak belgenin kimliği; aynı belgeden ikinci/üçüncü olay için `-b`, `-c`. |
| `kaynak` | Dizindeki belge kimlikleri (en az bir). |
| `tarih` | Kararın **duyurulduğu** gün, `YYYY-AA-GG`. Kurul karar tarihi ile bülten tarihi farklıysa karar tarihi. |
| `yururluk` | Belgede açıkça yazıyorsa yürürlük/uygulama başlangıcı, yoksa `null`. Tahmin edilmez. Tarih duyurudan önceyse (ör. geçmiş bir yükümlülük dönemi) `null` bırakılır, ayrıntı detayda yazılır. |
| `kurum` | `TCMB`, `BDDK` ya da `SPK`. |
| `konu` | Aşağıdaki listeden tek değer. |
| `onem` | 1, 2 ya da 3 (aşağıda). |
| `baslik` | En çok 110 karakter. **Ne değişti**, sayıyla: "Politika faizi %50'den %47,5'e indirildi". Kurum adı yazılmaz (rozet olarak gösterilir). Edilgen geçmiş zaman: yükseltildi / indirildi / getirildi / kaldırıldı / uzatıldı / sabit tutuldu. Belge adı başlık olmaz ("…'ne İlişkin Basın Duyurusu" yazılmaz). |
| `ozet` | 1–3 cümle, en çok 350 karakter: ne, kimin için, ne zamandan itibaren. Başlığı yinelemez, onu tamamlar. |
| `detay` | 1–6 madde. Her madde tek bir kural/parametre; mümkünse **eski → yeni**; kapsam, istisna, süre. Her madde en çok 260 karakter. |
| `alinti` | Kaynak metinden **birebir** kopyalanan, olayın özünü taşıyan 60–220 karakterlik parça (satır sonları boşluğa çevrilebilir). Doğrulama içindir, sayfada gösterilmez. |

### Konu listesi (`konu`)

| kod | kapsam |
|---|---|
| `faiz` | Politika faizi, faiz koridoru, PPK kararları, likidite yönetimi, TCMB fonlama araçları |
| `zk` | Zorunlu karşılıklar, menkul kıymet tesisi, zorunlu karşılıklara faiz/komisyon |
| `kredi` | Kredi büyüme sınırları, vade/taksit/limit kuralları, kredi değer oranı, risk ağırlıkları, kredi ve kart faiz tavanları, reeskont kredileri, yeniden yapılandırma |
| `mevduat` | Mevduat, kur korumalı mevduat, TL'ye dönüşüm ve TL payı hedefleri, mevduat faizi/stopaj kuralları |
| `doviz` | Döviz ve altın işlemleri, ihracat bedelleri, müdahale ve ihaleler, rezerv, swap anlaşmaları, yurt dışıyla türev işlem sınırları, yabancı para pozisyonu |
| `sermaye` | Sermaye yeterliliği, karşılıklar, likidite oranları, muhasebe ve enflasyon muhasebesi, kâr dağıtımı, bankacılık gözetim kuralları |
| `piyasa` | Pay ve borçlanma aracı piyasaları: açığa satış, devre kesici, kredili işlem, halka arz, geri alım, kamuyu aydınlatma, kurumsal yönetim |
| `fon` | Yatırım fonları, portföy yönetimi, aracı kurumlar, bireysel emeklilik, kira sertifikası ve diğer sermaye piyasası kurumları |
| `kripto` | Kripto varlıklar ve kripto varlık hizmet sağlayıcıları |
| `odeme` | Ödeme sistemleri (FAST, EFT), kartlı ödeme limitleri, dijital bankacılık, uzaktan kimlik tespiti, dijital Türk lirası |
| `kurum` | Banka kuruluş/faaliyet izinleri, iptaller, TMSF'ye devir, birleşme; kurum yapısına ilişkin kararlar |
| `diger` | Yukarıdakilere girmeyenler |

### Önem (`onem`)

- **3 — kritik:** piyasanın genelini doğrudan ve belirgin etkiler. Politika faizinin **değişmesi**; yeni bir
  aracın/rejimin başlaması ya da sona ermesi (KKM'nin başlaması/kapanması, açığa satış yasağı getirilmesi ya da
  kaldırılması, kredi büyüme sınırı getirilmesi); geniş kapsamlı tedbir paketi; doğrudan döviz müdahalesi.
- **2 — önemli:** mevcut bir uygulamanın oranında, limitinde, vadesinde anlamlı değişiklik; belirli bir kesimi
  bağlayan yeni kural; swap anlaşması; banka faaliyet izni iptali ya da TMSF'ye devir.
- **1 — bilgi:** faizin **sabit tutulması**; teknik/operasyonel ayar; süre uzatımı niteliğindeki yinelemeler;
  kuruluş izinleri; taslaklar; etkisi sınırlı duyurular.

## 4. Yazım kuralları

1. **Yalnız belgede yazan** bilgi kullanılır. Önceki değer belgede yoksa "eski → yeni" yazılmaz, uydurulmaz.
   Belgede olmayan yorum, gerekçe tahmini, piyasa etkisi yazılmaz.
2. Sayılar belgeyle birebir aynıdır. Yüzdeler `%37,5` biçiminde (ondalık virgül), tutarlar "500 bin TL",
   "1,5 milyar TL" gibi yazılır. Belgedeki "yüzde yirmi" → `%20`.
3. Hesapla türetilen sayı (ör. "250 baz puan") ancak iki değer de belgede varsa ve fark açıksa yazılır.
4. Kısaltmalar ilk geçtiği yerde açılmaz; sektörde yerleşik olanlar kullanılır: TCMB, PPK, AOFM, KKM, ZK, YP,
   TL, SYR, BIST, TEFAS, KAP. Daha az bilinenler açık yazılır.
5. Dil sade ve nötrdür; övgü, eleştiri, "önemli bir adım" gibi niteleme yok. Madde sonlarında nokta.
6. Aynı batch içinde üslup tutarlı kalır: başlıkta özne + değişiklik + (varsa) eski → yeni değer.

## 5. Dosya biçimi

`duzenleme/olaylar/<kurum>_<yıl>.json` (UTF-8):

```json
{
  "olaylar": [
    {
      "id": "tcmb-2026-52", "kaynak": ["tcmb-2026-52"], "tarih": "2026-11-26", "yururluk": null,
      "kurum": "TCMB", "konu": "zk", "onem": 2,
      "baslik": "TL zorunlu karşılıklara ödenen faiz AOFM'nin %86'sından %90'ına çıkarıldı",
      "ozet": "TL mevduat için tesis edilen zorunlu karşılıklara ödenen faiz ya da telafi ödemesi oranı yükseltildi.",
      "detay": ["TL mevduat zorunlu karşılıklarına ödenen faiz/telafi: TCMB ağırlıklı ortalama fonlama maliyetinin %86'sı → %90'ı."],
      "alinti": "TCMB ağırlıklı ortalama fonlama maliyetinin yüzde 86’sı yerine yüzde 90’ı oranında faiz veya telafi ödemesi yapılmasına karar vermiştir"
    }
  ],
  "elenen": [
    {"id": "tcmb-2026-50", "neden": "konferans duyurusu"}
  ]
}
```

Paketteki **her belge** ya bir olayın `kaynak` listesinde ya da `elenen` listesinde yer almalıdır (eksik belge
kalmaz). Doğrulama: `python3 -I duzenleme/dogrula.py <dosya>`.

## 6. Sık karşılaşılan durumlar

Üslup örneği: `olaylar/tcmb_2026.json` (aynı biçim ve ton).

- **PPK kararı (TCMB "Faiz Oranlarına İlişkin Basın Duyurusu").** Faiz değiştiyse başlık "Politika faizi %38'den
  %37'ye indirildi" (önem 3); değişmediyse "Politika faizi %37'de sabit tutuldu" (önem 1). Detayda politika
  faizi, duyuruda geçiyorsa gecelik borç verme / borçlanma (ve geç likidite) oranları, bir de Kurulun ileriye
  dönük mesajından tek madde. Duyuruda yazmayan oran eklenmez.
- **Belgede parametre verilmemişse** uydurulmaz; "duyuruda oran belirtilmedi", "süre belirtilmedi" denir.
- **Başka belgeye gönderme yapılmaz** ("bkz." yok). Belgenin kendi andığı önceki karar (tarih/sayı) yazılabilir.
- **Farklı `konu`ya giren iki karar aynı belgedeyse bölünür** (ör. kredi büyüme sınırı → `kredi`, zorunlu
  karşılıklara faiz → `zk`). Aynı konudaki birden çok parametre tek olayda kalır.
- **Önem 1 olanlar:** ödeme sistemi limitleri ve hizmet yenilikleri, merkez bankaları arası hesap/iş birliği
  anlaşmaları (swap anlaşması hariç — o önem 2), proje ilerleme duyuruları, taslaklar, yıllık olağan duyurular.
- **Uzun ekler (rehber, tebliğ, yönetmelik metni).** Duyurunun kendi özetlediği değişiklikler yazılır; ek metnin
  tamamı özetlenmez. Paket uzun eklerin ortasını keser — kesik yerde kalan ayrıntı tahmin edilmez.
- **BDDK.** Basın açıklaması ile aynı düzenlemeyi içeren Kurul kararı tek olaydır (iki kaynak). Kurul kararlarında
  `tarih` karar tarihidir. Banka kuruluş / faaliyet izni, izin iptali, TMSF'ye devir `kurum` konusudur
  (kuruluş-faaliyet izni önem 1; iptal ve devir önem 2). Kredi kartı, tüketici kredisi, konut ve taşıt kredisi
  sınırları `kredi`; sermaye yeterliliği, kur sabitleme, karşılık ve muhasebe esneklikleri `sermaye`; yurt
  dışı yerleşiklerle swap/türev sınırları ve yabancı para pozisyonu `doviz`.
- **SPK Bülteni.** Pakete yalnız "Duyuru ve İlke Kararları" bölümü girer ve bir bölümde birden çok duyuru
  olabilir. Her duyuru ayrı değerlendirilir: piyasanın genelini bağlayanlar olaydır (kimlik `spk-bulten-2026-60`,
  ikincisi `…-b`, üçüncüsü `…-c`; gerekirse `-f`'ye kadar); tek bir şirkete, fona ya da kişiye özel olanlar
  olay değildir. Bültenden hiç olay çıkmıyorsa bülten `elenen`e yazılır. `tarih` Kurul karar tarihidir (metinde
  yoksa bülten tarihi). Aynı tedbirin süre uzatımları (ör. açığa satış yasağının uzatılması) her seferinde ayrı
  olaydır, önem 1; tedbirin ilk getirilişi ve kaldırılışı önem 3'tür.
- **SPK basın duyurusu ile bülten duyurusu aynı karar ise** tek olay, iki kaynak.
- **Metni çıkmayan belge** (pakette `# NOT … metin çıkmadı`): `onbellek/ham/<kimlik>-ek1.pdf` dosyası görsel
  olarak okunur; okunamıyorsa belge `elenen`e "metin okunamadı — elle bakılmalı" nedeniyle yazılır.
