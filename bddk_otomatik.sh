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

# Scraper'lar süre sınırıyla çalışır: 02.10.2026'da uykudan uyanırken chromedriver indirmesi takıldı ve
# süreç 6 saat askıda kaldı (çıkış kodu hiç gelmedi). 15 dk'da bitmeyen çekim sonlandırılır, bir kez yinelenir.
cek() {   # $1 = etiket, $2 = script
  for deneme in 1 2; do
    if "$PY" - "$2" <<'PYEOF2'
import subprocess, sys
try:
    r = subprocess.run([sys.executable, sys.argv[1]], timeout=900)
    sys.exit(r.returncode)
except subprocess.TimeoutExpired:
    print("SURE ASIMI: 15 dakikada bitmedi, sonlandirildi", flush=True)
    sys.exit(124)
PYEOF2
    then
      log "$1 verisi çekildi (deneme $deneme)"
      return 0
    fi
    log "UYARI: $1 scrape başarısız (deneme $deneme)"
    pkill -f chromedriver 2>/dev/null
    sleep 10
  done
  log "UYARI: $1 scrape iki denemede de başarısız (mevcut veriyle devam)"
  return 1
}

cek "TL"  "bddk veri çekme/enhanced_manual_scraper.py"
cek "USD" "bddk veri çekme/enhanced_manual_scraperUSD.py"

# Scraper exit 0 dese de indirme başarısız olabiliyor (14.08'de yaşandı):
# bugünün damgasını taşıyan dosyalar gerçekten var mı doğrula
BUGUN=$(date +%Y%m%d)
for PB in TL USD; do
  if ! ls "bddk veri çekme"/bddk_krediler_${PB}_${BUGUN}_*.xlsx >/dev/null 2>&1; then
    log "UYARI: bugünün ${PB} dosyası İNMEMİŞ — yayın eski dosyalarla yapılacak"
  fi
done

if "$PY" bddk_yayinla.py; then
  log "Buluta yayınlandı (Streamlit + site)"
else
  log "UYARI: yayın adımı başarısız"
fi

log "Bitti"
