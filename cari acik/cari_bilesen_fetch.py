#!/usr/bin/env python3
"""Cari denge bileşenleri — altın, enerji ve diğer (Moody's "credit effects" görünümü).

EVDS 'bie_hariccariacik' (aylık, Milyon USD): cari işlemler hesabı, parasal olmayan altın net, enerji
(27. fasıl) net, altın ve enerji hariç cari denge. GSYH'ye oran için: cari fiyatlarla çeyreklik GSYH
(Bin TL) çeyrek ortalama USD/TL kuruyla dolara çevrilir, son 4 çeyrek toplanır (yıllıklandırılmış GSYH).
Her ay: 12 aylık hareketli toplam bileşenler ÷ o ay itibarıyla bilinen son 4 çeyrek GSYH (USD).

Çıktı: cari_bilesen.xlsx  (Aylik: tutarlar Milyar USD ve GSYH oranları %; Ceyrek: GSYH USD)
Anahtar: EVDS_API_KEY.
"""
import os
import sys
import datetime as dt
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis"
KEY = os.environ.get("EVDS_API_KEY") or os.environ.get("TCMB_API_KEY")
OUT = Path(__file__).parent / "cari_bilesen.xlsx"
AYLIK = {"TP.HARICCARIACIK.K1": "cari", "TP.HARICCARIACIK.K4": "altin", "TP.HARICCARIACIK.K7": "enerji",
         "TP.HARICCARIACIK.K10": "diger"}


def fetch(codes, start, end):
    url = f"{BASE_URL}/series={'-'.join(codes)}&startDate={start}&endDate={end}&type=json"
    for d in range(3):
        try:
            r = requests.get(url, headers={"key": KEY, "User-Agent": "Mozilla/5.0"}, timeout=60)
            r.raise_for_status()
            return r.json().get("items", [])
        except Exception as e:
            if d == 2:
                raise
            print(f"  EVDS deneme {d + 1} hatası ({type(e).__name__}) — yeniden")


def main():
    if not KEY:
        print("HATA: EVDS_API_KEY tanımlı değil", file=sys.stderr); sys.exit(1)
    bugun = dt.date.today(); son = bugun.strftime("%d-%m-%Y")
    print("Cari denge bileşenleri çekiliyor (EVDS)...")

    rows = []
    for it in fetch(list(AYLIK), "01-01-2008", son):
        try:
            y, m = it["Tarih"].split("-"); t = pd.Timestamp(int(y), int(m), 1)
        except Exception:
            continue
        row = {"tarih": t}
        for k, ad in AYLIK.items():
            v = it.get(k.replace(".", "_")); row[ad] = float(v) / 1000 if v not in (None, "", "ND") else None
        rows.append(row)
    a = pd.DataFrame(rows).sort_values("tarih").reset_index(drop=True)      # Milyar USD
    a = a.dropna(subset=["cari"])
    print(f"  aylık: {len(a)} ay → {a['tarih'].max().date()}")

    # USD/TL günlük → çeyrek ortalaması (yıl pencereleriyle)
    kur = []
    for yil in range(2008, bugun.year + 1):
        e = son if yil == bugun.year else f"31-12-{yil}"
        for it in fetch(["TP.DK.USD.A"], f"01-01-{yil}", e):
            v = it.get("TP_DK_USD_A")
            if v not in (None, "", "ND"):
                kur.append((pd.Timestamp(dt.datetime.strptime(it["Tarih"], "%d-%m-%Y")), float(v)))
    kur = pd.DataFrame(kur, columns=["tarih", "usd"])
    kur["ceyrek"] = kur["tarih"].dt.to_period("Q")
    kur_c = kur.groupby("ceyrek")["usd"].mean()

    q = []
    for it in fetch(["TP.GSYIH20.BY.B1GQ"], "01-01-2008", son):
        v = it.get("TP_GSYIH20_BY_B1GQ")
        if v in (None, "", "ND"):
            continue
        y, qq = it["Tarih"].split("-Q")
        q.append({"ceyrek": pd.Period(f"{y}Q{qq}"), "gsyh_tl": float(v) / 1e6})   # Bin TL → Milyar TL
    c = pd.DataFrame(q).sort_values("ceyrek").reset_index(drop=True)
    c["usd_ort"] = c["ceyrek"].map(kur_c)
    c["gsyh_usd"] = c["gsyh_tl"] / c["usd_ort"]                  # Milyar USD
    c["gsyh_4c_usd"] = c["gsyh_usd"].rolling(4).sum()
    c["tarih"] = c["ceyrek"].dt.to_timestamp(how="end").dt.normalize()   # çeyreğin son günü
    print(f"  GSYH: {len(c)} çeyrek → {c['ceyrek'].max()} · son 4 çeyrek {c['gsyh_4c_usd'].iloc[-1]:,.0f} milyar USD")

    for kol in ["cari", "altin", "enerji", "diger"]:
        a[kol + "_12"] = a[kol].rolling(12).sum()
    # aya kadar açıklanmış son 4 çeyrek GSYH (çeyrek sonu ≤ ay sonu)
    a["ay_sonu"] = a["tarih"] + pd.offsets.MonthEnd(0)
    g = c.dropna(subset=["gsyh_4c_usd"])[["tarih", "gsyh_4c_usd"]].rename(columns={"tarih": "gsyh_tarih"})
    a = pd.merge_asof(a.sort_values("ay_sonu"), g.sort_values("gsyh_tarih"), left_on="ay_sonu", right_on="gsyh_tarih", direction="backward")
    for kol in ["cari", "altin", "enerji", "diger"]:
        a[kol + "_gsyh"] = a[kol + "_12"] / a["gsyh_4c_usd"] * 100
    a = a.drop(columns=["ay_sonu"])

    with pd.ExcelWriter(OUT) as w:
        a.to_excel(w, sheet_name="Aylik", index=False)
        c.drop(columns=["ceyrek"]).to_excel(w, sheet_name="Ceyrek", index=False)
    L = a.iloc[-1]
    print(f"  Son ay {L['tarih'].strftime('%m.%Y')}: 12 aylık cari {L['cari_12']:.1f} mlr USD = GSYH %{L['cari_gsyh']:.1f} "
          f"(altın {L['altin_gsyh']:.1f} · enerji {L['enerji_gsyh']:.1f} · diğer {L['diger_gsyh']:+.1f})")
    print(f"Kaydedildi: {OUT.name}")
    print("BAŞARILI")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"HATA: {e}", file=sys.stderr); sys.exit(1)
