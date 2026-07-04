"""
TCMB EVDS API'sinden cari aclk verilerini ceker.

Seriler:
  TP.ODEAYRSUNUM6.Q1   - Cari Islemler Hesabi
  TP.ODEAYRSUNUM6.Q101 - Finans Hesabi
  TP.ODEAYRSUNUM6.Q210 - Net Hata ve Noksan

Frekans: Ceyreklik (Q)
"""
import os
import sys
import json
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

API_KEY = os.environ.get("EVDS_API_KEY", "")

SERIES = {
    "TP.ODEAYRSUNUM6.Q1":   "Cari Islemler Hesabi",
    "TP.ODEAYRSUNUM6.Q101": "Finans Hesabi",
    "TP.ODEAYRSUNUM6.Q210": "Net Hata ve Noksan",
}


def fetch_evds(start_date="01-01-2010", end_date=None):
    """EVDS API'den ceyreklik veriyi ceker."""
    if end_date is None:
        end_date = datetime.now().strftime("%d-%m-%Y")

    series_str = "-".join(SERIES.keys())
    # EVDS3 (Ocak 2026'da gecildi) yeni endpoint:
    url = (
        f"https://evds3.tcmb.gov.tr/igmevdsms-dis/"
        f"series={series_str}"
        f"&startDate={start_date}"
        f"&endDate={end_date}"
        f"&type=json"
        f"&frequency=6"
    )
    headers = {
        "key": API_KEY,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    print(f"EVDS'den veri cekiliyor: {start_date} -> {end_date}")
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()

    if "items" not in data:
        raise ValueError(f"Beklenmeyen yanit: {data}")

    items = data["items"]
    print(f"Toplam {len(items)} kayit alindi")
    return items


def to_dataframe(items):
    """JSON kayitlari DataFrame'e cevirir."""
    rows = []
    for item in items:
        row = {"Tarih": item.get("Tarih")}
        for code, label in SERIES.items():
            # Nokta seri kodunda olabilir - EVDS bazen _ olarak donduruyor
            key_alt = code.replace(".", "_")
            val = item.get(code) or item.get(key_alt)
            if val is None or val == "":
                val = None
            else:
                try:
                    val = float(str(val).replace(",", "."))
                except (ValueError, TypeError):
                    val = None
            row[label] = val
        rows.append(row)

    df = pd.DataFrame(rows)
    # Tarih: "2010-Q1", "2024-Q3" formatinda
    df["Tarih_Sira"] = df["Tarih"].apply(_parse_quarter)
    df = df.sort_values("Tarih_Sira").reset_index(drop=True)
    df = df.drop(columns=["Tarih_Sira"])
    return df


def _parse_quarter(s):
    """'2010-Q1' -> 2010.0, 2010.25, 2010.5, 2010.75 (sıralama icin)"""
    if not s or "Q" not in s:
        return 0
    try:
        year, q = s.split("-Q")
        return int(year) + (int(q) - 1) * 0.25
    except Exception:
        return 0


def save_data(df):
    """Veriyi xlsx ve csv olarak kaydeder."""
    out_dir = Path(__file__).parent
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    xlsx_path = out_dir / "cari_acik_son.xlsx"
    csv_path = out_dir / "cari_acik_son.csv"

    df.to_excel(xlsx_path, index=False, engine="openpyxl")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # Tarih damgalı yedek
    backup_path = out_dir / f"cari_acik_{timestamp}.xlsx"
    df.to_excel(backup_path, index=False, engine="openpyxl")

    print(f"Kaydedildi: {xlsx_path}")
    print(f"Yedek:      {backup_path}")
    return xlsx_path


def main():
    # Son 15 yil
    yil = datetime.now().year - 15
    start = f"01-01-{yil}"

    items = fetch_evds(start_date=start)
    df = to_dataframe(items)
    print(f"DataFrame: {df.shape}")
    print(df.tail(8))

    out_path = save_data(df)
    print(f"BASARILI: {out_path.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)
