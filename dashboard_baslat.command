#!/bin/bash
# Ekonomik Veriler Dashboard - Çift tıkla ve aç!
cd "$(dirname "$0")"
echo "🚀 Dashboard başlatılıyor..."
echo "Tarayıcıda açılacak: http://localhost:8501"
echo ""
/opt/anaconda3/bin/streamlit run dashboard.py
