#!/usr/bin/env python3
"""BDDK haftalık veri durumu — hangi hafta bekleniyor, hangisi yayında?

BDDK haftalık bülteni bir hafta gecikmeyle çıkar: Cuma biten haftanın verisi bir sonraki Perşembe akşamı ile
Cuma öğleden sonrası arasında (saat değişken) yayımlanır. Beklenen hafta = bugünden en az 7 gün önceki son Cuma.

  python3 bddk_hafta.py --durum         GUNCEL|EKSIK beklenen=YYYY-MM-DD yayinda=YYYY-MM-DD   (bddk_data/ içeriği)
  python3 bddk_hafta.py --hazir         bugün indirilen TL+USD dosyaları beklenen haftayı içeriyorsa çıkış 0, değilse 1
  python3 bddk_hafta.py --dosya X.xlsx  dosyadaki son hafta
"""
import argparse, datetime as dt, re, sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "bddk veri çekme"
DST = ROOT / "bddk_data"


def son_hafta(path):
    """Dosyanın ilk sütunundaki (Tarih) en büyük gün."""
    try:
        df = pd.read_excel(path, header=None, usecols=[0], nrows=600)
    except Exception:
        return None
    ds = []
    for v in df.iloc[:, 0].astype(str):
        m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", v.strip())   # BDDK günü sıfırsız yazabiliyor: 2.10.2026
        if m:
            ds.append(dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
    return max(ds) if ds else None


def beklenen_hafta(bugun=None):
    d = (bugun or dt.date.today()) - dt.timedelta(days=7)
    return d - dt.timedelta(days=(d.weekday() - 4) % 7)   # d'den geriye ilk Cuma


def en_yeni(klasor, pb):
    files = sorted(klasor.glob(f"bddk_krediler_{pb}_*.xls*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--durum", action="store_true"); ap.add_argument("--hazir", action="store_true"); ap.add_argument("--dosya")
    a = ap.parse_args()
    bek = beklenen_hafta()
    if a.dosya:
        print(son_hafta(a.dosya)); return
    if a.durum:
        haftalar = [son_hafta(en_yeni(DST, pb)) for pb in ("TL", "USD") if en_yeni(DST, pb)]
        yay = min(haftalar) if len(haftalar) == 2 else None
        print(f"{'GUNCEL' if yay and yay >= bek else 'EKSIK'} beklenen={bek} yayinda={yay}"); return
    if a.hazir:
        bugun = dt.date.today().strftime("%Y%m%d"); eksik = []
        for pb in ("TL", "USD"):
            f = sorted(SRC.glob(f"bddk_krediler_{pb}_{bugun}_*.xls*"), key=lambda p: p.stat().st_mtime)
            h = son_hafta(f[-1]) if f else None
            if h is None or h < bek:
                eksik.append(f"{pb}: {'dosya yok' if not f else f'son hafta {h}'}")
        if eksik:
            print(f"HAZIR DEGIL (beklenen {bek}) — " + "; ".join(eksik)); sys.exit(1)
        print(f"HAZIR: TL ve USD dosyaları {bek} haftasını içeriyor"); return
    ap.print_help()


if __name__ == "__main__":
    main()
