"""
Yabancı Para Hareketi (DTH) — EVDS3'ten haftalık, parite etkisinden arındırılmış değişim.
=========================================================================================
Kaynak: TCMB Haftalık Para ve Banka İstatistikleri, Tablo 5 (TP.HPBITABLO5).
Seriler yurt içi yerleşiklerin DTH (döviz tevdiat) + kıymetli maden hesaplarındaki
HAFTALIK DEĞİŞİMİ verir; parite ve kıymetli maden fiyat etkilerinden arındırılmıştır.

  TP.HPBITABLO5.1  Yurt içi yerleşikler toplam değişim
  TP.HPBITABLO5.2  ├─ Gerçek kişiler
  TP.HPBITABLO5.7  └─ Tüzel kişiler
  TP.HPBITABLO5.3  Gerçek kişiler: ABD doları mevduat
  TP.HPBITABLO5.4  Gerçek kişiler: Euro mevduat
  TP.HPBITABLO5.5  Gerçek kişiler: Diğer para mevduat
  TP.HPBITABLO5.6  Gerçek kişiler: Kıymetli maden depo hesapları (altın)

Türetilen: gk_doviz = USD + EUR + Diğer (gerçek kişiler döviz kısmı).
Birim: Milyon USD. Çıktı: dth.xlsx (Haftalik sheet).
"""
import os
import sys
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

API_KEY = os.environ.get("EVDS_API_KEY", "")
BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis"

SERIES = {
    "TP.HPBITABLO5.1": "yerlesik_toplam",
    "TP.HPBITABLO5.2": "gercek_kisiler",
    "TP.HPBITABLO5.7": "tuzel_kisiler",
    "TP.HPBITABLO5.3": "gk_usd",
    "TP.HPBITABLO5.4": "gk_eur",
    "TP.HPBITABLO5.5": "gk_diger",
    "TP.HPBITABLO5.6": "gk_altin",
}


def fetch_items(start_date="01-01-2015", end_date=None, retries=3):
    if end_date is None:
        end_date = datetime.now().strftime("%d-%m-%Y")
    series_str = "-".join(SERIES.keys())
    url = (f"{BASE_URL}/series={series_str}"
           f"&startDate={start_date}&endDate={end_date}&type=json")
    headers = {"key": API_KEY, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            print(f"  EVDS isteği (deneme {attempt})...")
            r = requests.get(url, headers=headers, timeout=45)
            r.raise_for_status()
            data = r.json()
            if "items" not in data:
                raise ValueError(f"Beklenmeyen yanıt: {str(data)[:200]}")
            return data["items"]
        except Exception as e:
            last_err = e
            print(f"    başarısız: {e}")
    raise RuntimeError(f"EVDS verisi çekilemedi: {last_err}")


def to_dataframe(items):
    rows = []
    for it in items:
        row = {"tarih": it.get("Tarih")}
        for code, name in SERIES.items():
            v = it.get(code.replace(".", "_"))
            row[name] = None if v in (None, "") else float(str(v).replace(",", "."))
        rows.append(row)
    df = pd.DataFrame(rows)
    df["tarih"] = pd.to_datetime(df["tarih"], format="%d-%m-%Y", errors="coerce")
    return df.dropna(subset=["tarih"]).sort_values("tarih").reset_index(drop=True)


def main():
    print("Yabancı Para Hareketi (DTH, Tablo 5) çekiliyor (EVDS3)...")
    items = fetch_items()
    print(f"  {len(items)} ham kayıt alındı")
    df = to_dataframe(items)
    # Ana seri boş olan satırları at (yayımlanmamış hafta vb.)
    df = df.dropna(subset=["yerlesik_toplam"]).reset_index(drop=True)
    # Gerçek kişiler döviz kısmı = USD + EUR + Diğer
    df["gk_doviz"] = df[["gk_usd", "gk_eur", "gk_diger"]].sum(axis=1, min_count=1)

    cols = ["tarih", "yerlesik_toplam", "gercek_kisiler", "tuzel_kisiler",
            "gk_altin", "gk_doviz", "gk_usd", "gk_eur", "gk_diger"]
    df = df[cols]

    out = Path(__file__).parent / "dth.xlsx"
    df.to_excel(out, sheet_name="Haftalik", index=False)

    print(f"  {len(df)} hafta | {df['tarih'].min().date()} → {df['tarih'].max().date()}")
    print("\n  Son 3 hafta (Milyon USD):")
    for _, r in df.tail(3).iterrows():
        print(f"    {r['tarih'].date()}  toplam={r['yerlesik_toplam']:>9,.0f}  "
              f"gerçek={r['gercek_kisiler']:>8,.0f}  tüzel={r['tuzel_kisiler']:>9,.0f}  "
              f"altın={r['gk_altin']:>8,.0f}  döviz={r['gk_doviz']:>8,.0f}")
    # Tutarlılık kontrolü (toplam ≈ gerçek + tüzel)
    L = df.iloc[-1]
    fark = abs(L["yerlesik_toplam"] - (L["gercek_kisiler"] + L["tuzel_kisiler"]))
    print(f"\n  Kontrol: |toplam − (gerçek+tüzel)| = {fark:,.0f} mn USD")
    print(f"Kaydedildi: {out.name}")
    print("BAŞARILI")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)
