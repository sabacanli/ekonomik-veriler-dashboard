#!/bin/zsh
# Toplu yerel veri güncelleme — bulut workflow'unun (veri-guncelle.yml) yerel eşi.
# 13 veri script'ini çalıştırır, site paketlerini üretir, commit + push eder
# (push, sitenin yeniden yayınını da tetikler). BDDK hariç (bddk_otomatik.sh).
#
# Kullanım:  zsh veri_guncelle_yerel.sh
# Detay log: ~/Library/Logs/ekordion-veri-detay.log
set -u
REPO="/Users/sadettin/cowork/ekonomik veriler dashboard"
PY="/opt/anaconda3/bin/python3"
LOG="$HOME/Library/Logs/ekordion-veri-detay.log"
: > "$LOG"

cd "$REPO" || exit 1
export EVDS_API_KEY=$("$PY" -c "import tomllib;print(tomllib.load(open('.streamlit/secrets.toml','rb'))['EVDS_API_KEY'])")
export TCMB_API_KEY="$EVDS_API_KEY"

echo "[$(date '+%d.%m.%Y %H:%M:%S')] Toplu güncelleme başladı"
FAILS=""
calistir() {
  if "$PY" "$2" >> "$LOG" 2>&1; then
    echo "OK: $1"
  else
    echo "FAIL: $1"
    FAILS="$FAILS | $1"
  fi
}

calistir "TCMB Haftalık Stok"      "tcmb haftalık stok/tcmb_data.py"
calistir "Net Rezerv"              "net rezerv/net_rezerv_fetch.py"
calistir "Rezerv Likidite (URDL)"  "net rezerv/likidite_fetch.py"
calistir "Enflasyon"               "enflasyon/enflasyon_fetch.py"
calistir "Kredi/Mevduat"           "kredi mevduat/kredi_mevduat_fetch.py"
calistir "Yabancı Para (DTH)"      "yabanci para hareketi/dth_fetch.py"
calistir "Cari Denge"              "cari acik/evds_fetch.py"
calistir "Ödemeler Dengesi"        "cari acik/odemeler_dengesi_fetch.py"
calistir "Bütçe"                   "butce/butce_fetch.py"
calistir "Hazine Nakit"            "hazine nakit/nakit_fetch.py"
calistir "Hazine İhale — çek"      "hazine ihale /hazine_ihale_cek.py"
calistir "Hazine İhale — analiz"   "hazine ihale /hazine_analiz.py"
calistir "Hazine İhale — ödeme"    "hazine ihale /hazine_odeme.py"
calistir "TCMB Doğrudan Alım"      "tcmb dogrudan alım/guncelle.py"

"$PY" site_export.py >> "$LOG" 2>&1 && echo "OK: site_export" || echo "FAIL: site_export"

git add "tcmb haftalık stok/output" "net rezerv" "enflasyon" "kredi mevduat" \
        "yabanci para hareketi" "cari acik" "butce" "hazine nakit" \
        "hazine ihale " "tcmb dogrudan alım" site/data 2>> "$LOG"
if git diff --cached --quiet; then
  echo "Yeni veri yok — commit atlandı."
else
  git commit -q -m "Toplu veri güncelleme (yerel, $(date '+%d.%m.%Y %H:%M'))" >> "$LOG" 2>&1
  git pull --rebase -q origin main >> "$LOG" 2>&1
  GIT_TERMINAL_PROMPT=0 git push -q origin main >> "$LOG" 2>&1 && echo "PUSH: tamam" || echo "PUSH: BAŞARISIZ"
fi
echo "[$(date '+%d.%m.%Y %H:%M:%S')] SONUC — başarısız:${FAILS:- (yok)}"
