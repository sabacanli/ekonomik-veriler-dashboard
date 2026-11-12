#!/usr/bin/env python3
"""TCMB analitik bilanço aktif toplamı — EVDS'den çeker (APİ portföyünün bilançoya oranı için).

  TP.AB.A01  A. AKTİF (analitik bilanço toplamı), günlük, Bin TL

Çıktı: analitik_aktif.csv (tarih, aktif_bin_tl) — 2016'dan bugüne iş günleri. Her çalıştırmada son iki yıl yeniden çekilir
(EVDS tek istekte ~1000 gözlem verir; geçmiş yıllar dosyada durur), dosya yoksa tamamı çekilir.
Anahtar: EVDS_API_KEY ortam değişkeni.
"""
import datetime as dt
import os
import sys
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis"
KEY = os.environ.get("EVDS_API_KEY") or os.environ.get("TCMB_API_KEY")
OUT = Path(__file__).parent / "analitik_aktif.csv"
KOD = "TP.AB.A01"
ILK_YIL = 2016


def fetch(start, end):
    url = f"{BASE_URL}/series={KOD}&startDate={start}&endDate={end}&type=json"
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


def main():
    if not KEY:
        print("EVDS_API_KEY yok — analitik_aktif.csv güncellenmedi")
        return 1
    eski = pd.read_csv(OUT, parse_dates=["tarih"]) if OUT.exists() else pd.DataFrame(columns=["tarih", "aktif_bin_tl"])
    bugun = dt.date.today()
    ilk = ILK_YIL if eski.empty else max(ILK_YIL, bugun.year - 1)
    rows = []
    for y in range(ilk, bugun.year + 1):
        for it in fetch(f"01-01-{y}", f"31-12-{y}"):
            v = it.get(KOD.replace(".", "_"))
            if v in (None, "", "ND"):
                continue
            rows.append({"tarih": it.get("Tarih"), "aktif_bin_tl": float(str(v).replace(",", "."))})
    yeni = pd.DataFrame(rows)
    if yeni.empty:
        print("EVDS boş döndü — dosya korunuyor")
        return 1
    yeni["tarih"] = pd.to_datetime(yeni["tarih"], format="%d-%m-%Y", errors="coerce")
    yeni = yeni.dropna(subset=["tarih"])
    onceki = eski[eski["tarih"] < pd.Timestamp(ilk, 1, 1)]
    df = (yeni if onceki.empty else pd.concat([onceki, yeni])).drop_duplicates(subset=["tarih"], keep="last").sort_values("tarih").reset_index(drop=True)
    df.to_csv(OUT, index=False, date_format="%Y-%m-%d")
    print(f"analitik_aktif.csv: {len(df)} gözlem · {df['tarih'].min():%d.%m.%Y} – {df['tarih'].max():%d.%m.%Y} · son {df['aktif_bin_tl'].iloc[-1] / 1e9:,.2f} trilyon TL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
