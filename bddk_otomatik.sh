#!/bin/zsh
# BDDK haftalık otomatik güncelleme — launchd birden çok denemede çalıştırır:
# Cuma 09:30 / 13:30 / 17:30, Cumartesi 10:30, Pazartesi 09:30 (~/Library/LaunchAgents/com.ekordion.bddk.plist).
# BDDK, Cuma biten haftanın bültenini bir hafta sonra ve değişken saatte yayımlıyor (Perşembe akşamı ile Cuma
# öğleden sonrası arası; 09.10.2026'da 10:51'de henüz yoktu) — bu yüzden tek bir sabah koşusu yetmiyor.
#
# Adımlar: bddk_hafta.py --durum (beklenen hafta zaten yayındaysa hiçbir şey yapma) -> TL scrape -> USD scrape
# (Selenium; Chrome penceresi açılır ve kendi kendine gezinir; dosya üretilmediyse yeniden dener) ->
# bddk_hafta.py --hazir (iki dosya da beklenen haftayı içeriyor mu?) -> bddk_yayinla.py (bddk_data'ya kopya +
# site paketleri + git push -> Streamlit ve ekordion.com.tr kendini yeniler).
#
# BDDK beklenen haftayı henüz yayımlamamışsa yayın atlanır ve sonraki planlı deneme bekler; eksik/eski
# dosyayla asla yayın yapılmaz — sistem asla bozulmaz.
set -u
REPO="/Users/sadettin/cowork/ekonomik veriler dashboard"
PY="/opt/anaconda3/bin/python3"

log() { echo "[$(date '+%d.%m.%Y %H:%M:%S')] $1"; }

log "BDDK otomatik güncelleme başladı"
cd "$REPO" || { log "HATA: repo klasörü bulunamadı"; exit 1; }

# Beklenen hafta (bugünden en az 7 gün önceki son Cuma) zaten bddk_data'da yayındaysa çekim gereksiz
DURUM=$("$PY" bddk_hafta.py --durum 2>/dev/null)
log "Durum: ${DURUM:-bilinmiyor}"
case "$DURUM" in GUNCEL*) log "Beklenen hafta zaten yayında — çekim atlandı"; log "Bitti"; exit 0;; esac

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
BUGUN=$(date +%Y%m%d)
cek() {   # $1 = etiket (TL/USD), $2 = script — başarı ölçütü: bugünün damgasını taşıyan dosya gerçekten var
  for deneme in 1 2; do
    "$PY" - "$2" <<'PYEOF2'
import subprocess, sys
try:
    r = subprocess.run([sys.executable, sys.argv[1]], timeout=900)
    sys.exit(r.returncode)
except subprocess.TimeoutExpired:
    print("SURE ASIMI: 15 dakikada bitmedi, sonlandirildi", flush=True)
    sys.exit(124)
PYEOF2
    KOD=$?
    if ls "bddk veri çekme"/bddk_krediler_$1_${BUGUN}_*.xlsx >/dev/null 2>&1; then
      log "$1 verisi çekildi (deneme $deneme, çıkış $KOD)"
      return 0
    fi
    log "UYARI: $1 dosyası inmedi (deneme $deneme, çıkış $KOD)"
    pkill -f chromedriver 2>/dev/null
    sleep 10
  done
  log "UYARI: $1 scrape iki denemede de dosya üretmedi"
  return 1
}

cek "TL"  "bddk veri çekme/enhanced_manual_scraper.py"
cek "USD" "bddk veri çekme/enhanced_manual_scraperUSD.py"

# İki dosya da beklenen haftayı içeriyorsa yayınla; aksi halde (BDDK henüz yayımlamamış ya da indirme eksik)
# yayın atlanır — sonraki planlı deneme (13:30 / 17:30 / Cumartesi / Pazartesi) tekrar dener.
if HAZIR=$("$PY" bddk_hafta.py --hazir 2>&1); then
  log "$HAZIR"
  if "$PY" bddk_yayinla.py; then
    log "Buluta yayınlandı (Streamlit + site)"
  else
    log "UYARI: yayın adımı başarısız"
  fi
else
  log "Yayın atlandı — $HAZIR"
fi

log "Bitti"
