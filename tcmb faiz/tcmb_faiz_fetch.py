#!/usr/bin/env python3
"""Para Politikası & Beklentiler — EVDS'den çeker (TCMB sunumundaki temel göstergeler).

Sayfalar (tcmb_faiz.xlsx):
  Gunluk  : politika faizi (BIS aylık serisi iş günlerine taşınır), AOFM, TLREF, BIST gecelik repo,
            TCMB net fonlama (Milyar TL), USD/TL
  Aylik   : 12 ay sonrası enflasyon beklentileri (piyasa / reel sektör / hanehalkı), REDK (TÜFE bazlı)
  Haftalik: TCMB haftalık bankacılık tabloları — kredi toplamları (TL/YP) ve mevduat (TL / YP-USD);
            kur etkisinden arındırılmış 13 haftalık yıllıklandırılmış kredi büyümesi ve TL mevduat payı
            burada değil site_export'ta hesaplanır (ham seriler saklanır)
  Ceyrek  : GSYH ve harcama bileşenleri (zincirlenmiş hacim) — yıllık % değişim export'ta

Anahtar: EVDS_API_KEY ortam değişkeni. EVDS tek istekte ~1000 satır verdiğinden günlük seriler
yıl yıl pencereyle çekilir.
"""
import os
import sys
import datetime as dt
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis"
KEY = os.environ.get("EVDS_API_KEY") or os.environ.get("TCMB_API_KEY")
SCRIPT_DIR = Path(__file__).parent
OUT = SCRIPT_DIR / "tcmb_faiz.xlsx"

GUNLUK = {"TP.BISTTLREF.ORAN": "tlref", "TP.APIFON4": "aofm", "TP.AOFOBAP": "on_repo",
          "TP.APIFON3": "net_fonlama", "TP.DK.USD.A": "usd"}
AYLIK = {"TP.BISPOLFAIZ.TUR": "politika", "TP.ENFBEK.PKA12ENF": "bek_piyasa",
         "TP.ENFBEK.IYA12ENF": "bek_reel", "TP.ENFBEK.HBA12ENF": "bek_hane", "TP.RK.T1.Y": "redk"}
# Haftalık bankacılık: krediler (Bin TL) — TL ve YP parçaları ayrı toplanır; mevduat TL (Bin TL) / YP (Milyon USD)
HAFTALIK = {
    "TP.HPBITABLO6.1": "kredi_toplam", "TP.HPBITABLO6.2": "kredi_tuketici", "TP.HPBITABLO6.16": "kredi_kart",
    "TP.HPBITABLO6.21": "ticari_tl", "TP.HPBITABLO6.26": "ticari_yp",
    "TP.HPBITABLO6.31": "diger_tl", "TP.HPBITABLO6.32": "diger_yp",
    "TP.HPBITABLO6.34": "kkart_tl", "TP.HPBITABLO6.35": "kkart_yp",
    "TP.HPBITABLO6.17": "bkart_tl", "TP.HPBITABLO6.18": "bkart_yp",
    "TP.HPBITABLO6.38": "fin_banka_tl", "TP.HPBITABLO6.39": "fin_banka_yp",
    "TP.HPBITABLO6.41": "fin_diger_tl", "TP.HPBITABLO6.42": "fin_diger_yp",
    "TP.HPBITABLO3.1": "mevduat_tl", "TP.HPBITABLO4.1": "mevduat_yp_usd",
}
CEYREK = {"TP.GSYIH20.CY.B1GQ": "gsyh", "TP.GSYIH20.CY.P311": "hane", "TP.GSYIH20.CY.P312": "hhkak",
          "TP.GSYIH20.CY.P32": "devlet", "TP.GSYIH20.CY.P51G": "yatirim"}


def fetch(codes, start, end):
    url = f"{BASE_URL}/series={'-'.join(codes)}&startDate={start}&endDate={end}&type=json"
    for deneme in range(3):
        try:
            r = requests.get(url, headers={"key": KEY, "User-Agent": "Mozilla/5.0"}, timeout=60)
            r.raise_for_status()
            return r.json().get("items", [])
        except Exception as e:
            if deneme == 2:
                raise
            print(f"  EVDS deneme {deneme + 1} hatası ({type(e).__name__}) — yeniden")
    return []


def tablo(items, eslem, tarih_cozucu):
    rows = []
    for it in items:
        t = tarih_cozucu(it.get("Tarih"))
        if t is None:
            continue
        row = {"tarih": t}
        for code, ad in eslem.items():
            v = it.get(code.replace(".", "_"))
            row[ad] = float(v) if v not in (None, "", "ND") else None
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("tarih").drop_duplicates("tarih").reset_index(drop=True)


def t_gun(s):
    try:
        return pd.Timestamp(dt.datetime.strptime(s, "%d-%m-%Y"))
    except Exception:
        return None


def t_ay(s):
    try:
        y, m = s.split("-")
        return pd.Timestamp(int(y), int(m), 1)
    except Exception:
        return None


def t_ceyrek(s):
    try:
        y, q = s.split("-Q")
        return pd.Timestamp(int(y), 3 * int(q) - 2, 1)
    except Exception:
        return None


def main():
    if not KEY:
        print("HATA: EVDS_API_KEY tanımlı değil", file=sys.stderr)
        sys.exit(1)
    bugun = dt.date.today()
    son = bugun.strftime("%d-%m-%Y")
    print("Para politikası verileri çekiliyor (EVDS)...")

    # Günlük — yıl pencereleri (2022'den bugüne)
    parcalar = []
    for yil in range(2022, bugun.year + 1):
        s = f"01-01-{yil}"
        e = son if yil == bugun.year else f"31-12-{yil}"
        parcalar.append(tablo(fetch(list(GUNLUK), s, e), GUNLUK, t_gun))
        print(f"  günlük {yil}: {len(parcalar[-1])} gün")
    gunluk = pd.concat(parcalar, ignore_index=True).sort_values("tarih").reset_index(drop=True)
    gunluk["net_fonlama"] = gunluk["net_fonlama"] / 1000.0          # Milyon TL → Milyar TL
    gunluk = gunluk.dropna(subset=["tlref", "aofm", "on_repo", "net_fonlama"], how="all")

    aylik = tablo(fetch(list(AYLIK), "01-01-2015", son), AYLIK, t_ay)
    print(f"  aylık: {len(aylik)} ay ({aylik['tarih'].min().date()} → {aylik['tarih'].max().date()})")
    # politika faizi: iş günlerine taşı (aylık BIS serisi; ay içi değişimler bir sonraki ay görünür)
    pol = aylik[["tarih", "politika"]].dropna().set_index("tarih")["politika"]
    gunluk["politika"] = gunluk["tarih"].map(lambda t: pol[pol.index <= t].iloc[-1] if (pol.index <= t).any() else None)

    haftalik = tablo(fetch(list(HAFTALIK), "01-01-2022", son), HAFTALIK, t_gun)
    print(f"  haftalık: {len(haftalik)} hafta (son {haftalik['tarih'].max().date()})")
    ceyrek = tablo(fetch(list(CEYREK), "01-01-2015", son), CEYREK, t_ceyrek)
    print(f"  çeyrek: {len(ceyrek)} dönem (son {ceyrek['tarih'].max().date()})")

    with pd.ExcelWriter(OUT) as w:
        gunluk.to_excel(w, sheet_name="Gunluk", index=False)
        aylik.to_excel(w, sheet_name="Aylik", index=False)
        haftalik.to_excel(w, sheet_name="Haftalik", index=False)
        ceyrek.to_excel(w, sheet_name="Ceyrek", index=False)
    g = gunluk.iloc[-1]
    print(f"  Son gün {g['tarih'].date()}: politika {g['politika']} · AOFM {g['aofm']} · TLREF {g['tlref']} · net fonlama {g['net_fonlama']:.0f} mlr")
    print(f"Kaydedildi: {OUT.name}")
    print("BAŞARILI")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)
