#!/bin/zsh
# Sabah kontrolcüsünün tek komutu (Claude zamanlanmış görevi "ekordion-sabah-kontrol" her hafta içi sabah bunu çalıştırır).
# Yalnız okur; sorun bulursa masaüstü bildirimi gösterir. Ayrıntı: kontrol/saglik_kontrol.py
cd "/Users/sadettin/cowork/ekonomik veriler dashboard" || { echo "HATA: proje klasörü bulunamadı"; exit 1; }
exec /opt/anaconda3/bin/python3 kontrol/saglik_kontrol.py --bildir "$@"
