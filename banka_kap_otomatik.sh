#!/bin/zsh
# Günlük otomatik KAP kontrolü — launchd her gün 09:20, 14:20 ve 17:40'ta çalıştırır
# (~/Library/LaunchAgents/com.ekordion.kap.plist; log: ~/Library/Logs/ekordion-kap.log).
#
# Bankaların yeni yayımlanan solo finansal raporlarını KAP'tan indirir, doğrular, veritabanına yükler ve
# siteyi yayımlar (banka kar/kap_otomatik.py). Yeni rapor yoksa hiçbir şey değişmez; doğrulamadan geçemeyen
# rapor veritabanına yazılmaz, bildirim gönderilir. Eksik ya da şüpheli veriyle asla yayın yapılmaz.
#
# Kapatmak için:  launchctl bootout gui/$(id -u)/com.ekordion.kap
set -u
REPO="/Users/sadettin/cowork/ekonomik veriler dashboard"
PY="/opt/anaconda3/bin/python3"

log() { echo "[$(date '+%d.%m.%Y %H:%M:%S')] $1"; }

cd "$REPO" || { log "HATA: repo klasörü bulunamadı"; exit 1; }

# Aynı anda iki koşu olmasın (2 saatten eski kilit bayat sayılır)
KILIT="/tmp/ekordion-kap.kilit"
if [ -d "$KILIT" ] && [ -n "$(find "$KILIT" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then rmdir "$KILIT" 2>/dev/null; fi
if ! mkdir "$KILIT" 2>/dev/null; then log "Başka bir koşu sürüyor — atlandı"; exit 0; fi
trap 'rmdir "$KILIT" 2>/dev/null' EXIT

# Mac uykudan yeni uyandıysa ağ henüz bağlanmamış olabilir (en fazla ~4 dk beklenir)
i=0
until curl -sm 5 -o /dev/null "https://www.gstatic.com/generate_204" 2>/dev/null || [ $i -ge 16 ]; do
  i=$((i + 1)); sleep 15
done
[ $i -ge 16 ] && log "UYARI: ağ 4 dakikada gelmedi — yine de deneniyor"

# Süre sınırı: 40 dakikada bitmeyen koşu sonlandırılır
"$PY" - <<'PYEOF'
import subprocess, sys
try:
    r = subprocess.run([sys.executable, "banka kar/kap_otomatik.py"], timeout=2400)
    sys.exit(r.returncode)
except subprocess.TimeoutExpired:
    print("SURE ASIMI: 40 dakikada bitmedi, sonlandirildi", flush=True)
    sys.exit(124)
PYEOF
KOD=$?
[ $KOD -ne 0 ] && log "UYARI: koşu çıkış kodu $KOD"
exit 0
