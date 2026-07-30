#!/bin/zsh
# BDDK haftalık otomatik güncelleme — launchd tarafından her Cuma 09:30'da çalıştırılır.
# (Kurulum: ~/Library/LaunchAgents/com.ekordion.bddk.plist)
#
# Adımlar: TL scrape -> USD scrape (Selenium; Chrome penceresi açılır ve kendi
# kendine gezinir) -> bddk_yayinla.py (bddk_data'ya kopya + site paketleri +
# git push -> Streamlit ve ekordion.com.tr kendini yeniler).
#
# Scrape başarısız olursa yayın adımı mevcut (eski) dosyaları kullanır;
# değişiklik yoksa commit atlanır — sistem asla bozulmaz.
set -u
REPO="/Users/sadettin/cowork/ekonomik veriler dashboard"
PY="/opt/anaconda3/bin/python3"

log() { echo "[$(date '+%d.%m.%Y %H:%M:%S')] $1"; }

log "BDDK otomatik güncelleme başladı"
cd "$REPO" || { log "HATA: repo klasörü bulunamadı"; exit 1; }

# Mac uykudan yeni uyandıysa ağ henüz bağlanmamış olabilir — scrape ve push için
# önce bağlantıyı bekle (en fazla ~4 dk). Sonda adresi curl-dostu olmalı:
# bddk.org.tr bot koruması yüzünden curl'e yanıt vermiyor (30.07 koşusunda 4 dk boşa bekletti).
i=0
until curl -sm 5 -o /dev/null "https://www.gstatic.com/generate_204" 2>/dev/null || [ $i -ge 16 ]; do
  i=$((i + 1))
  log "Ağ bekleniyor... ($i/16)"
  sleep 15
done
if [ $i -ge 16 ]; then
  log "UYARI: ağ 4 dakikada gelmedi — yine de deneniyor"
fi

if "$PY" "bddk veri çekme/enhanced_manual_scraper.py"; then
  log "TL verisi çekildi"
else
  log "UYARI: TL scrape başarısız (mevcut veriyle devam)"
fi

if "$PY" "bddk veri çekme/enhanced_manual_scraperUSD.py"; then
  log "USD verisi çekildi"
else
  log "UYARI: USD scrape başarısız (mevcut veriyle devam)"
fi

if "$PY" bddk_yayinla.py; then
  log "Buluta yayınlandı (Streamlit + site)"
else
  log "UYARI: yayın adımı başarısız"
fi

log "Bitti"
