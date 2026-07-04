"""
TCMB Ödemeler Dengesi Gelişmeleri tablosunu EVDS'den çeker.

PDF bültenindeki "Tablo 1. Cari İşlemler Dengesi" formatını yeniden üretir:
  - Aylık (son ay vs önceki yıl aynı ay)
  - İlk N Ay Birikimli (yıl başından son aya kadar)
  - 12 Aylık Birikimli (son 12 ay vs önceki 12 ay)

Kaynak: bie_odeayrsunum6 grubundan aylık seriler.
"""
import os
import sys
import json
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

API_KEY = os.environ.get("EVDS_API_KEY", "")
BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis"

# PDF tablosundaki kalemler ile EVDS seri kodları eşleşmesi
SERIES_MAP = {
    "Q1":  "Cari İşlemler Dengesi",
    "Q4":  "Dış Ticaret Dengesi",
    "Q5":  "Toplam Mal İhracatı",
    "Q6":  "Toplam Mal İthalatı",
    "Q17": "Parasal Olmayan Altın (net)",
    "Q18": "Altın İhracatı",
    "Q19": "Altın İthalatı",
    "Q20": "Hizmetler Dengesi",
    "Q21": "Hizmet Gelirleri",
    "Q22": "Hizmet Giderleri",
    "Q30": "Taşımacılık - Gelir",
    "Q31": "Taşımacılık - Gider",
    "Q42": "Seyahat - Gelir",
    "Q43": "Seyahat - Gider",
    "Q68": "Birincil Gelir Dengesi",
    "Q92": "İkincil Gelir Dengesi",
}


def fetch_monthly_data(start_date="01-01-2010"):
    """Tüm gerekli serileri AYLIK frekansta çeker."""
    end_date = datetime.now().strftime("%d-%m-%Y")
    series_codes = [f"TP.ODEAYRSUNUM6.{k}" for k in SERIES_MAP.keys()]
    series_str = "-".join(series_codes)

    url = (
        f"{BASE_URL}/series={series_str}"
        f"&startDate={start_date}&endDate={end_date}"
        f"&type=json&frequency=5"  # 5 = aylık
    )
    headers = {"key": API_KEY, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    print(f"EVDS aylık veri çekiliyor: {start_date} → {end_date}")
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()

    if "items" not in data:
        raise ValueError(f"Beklenmeyen yanıt: {data}")

    items = data["items"]
    print(f"Toplam {len(items)} aylık kayıt alındı")
    return items


def to_dataframe(items):
    """JSON kayıtları DataFrame'e çevirir."""
    rows = []
    for item in items:
        row = {"Tarih": item.get("Tarih")}
        for q_code, label in SERIES_MAP.items():
            full_code = f"TP_ODEAYRSUNUM6_{q_code}"
            v = item.get(full_code)
            if v is None or v == "":
                row[label] = None
            else:
                try:
                    row[label] = float(str(v).replace(",", "."))
                except (ValueError, TypeError):
                    row[label] = None
        rows.append(row)

    df = pd.DataFrame(rows)
    # Tarih: "2026-2" → datetime
    df["Tarih_dt"] = pd.to_datetime(df["Tarih"], format="%Y-%m", errors="coerce")
    df = df.sort_values("Tarih_dt").reset_index(drop=True)
    return df


def build_pdf_table(df):
    """PDF bülten tablosunu birebir formatta üretir."""
    # Son ay
    son = df.iloc[-1]
    son_dt = son["Tarih_dt"]
    son_yil = son_dt.year
    son_ay = son_dt.month

    # Önceki yıl aynı ay
    onc_dt = son_dt.replace(year=son_yil - 1)
    onc = df[df["Tarih_dt"] == onc_dt].iloc[0] if not df[df["Tarih_dt"] == onc_dt].empty else None

    # Birikimli (Yıl başından son aya kadar)
    bir_son = df[(df["Tarih_dt"].dt.year == son_yil) &
                  (df["Tarih_dt"].dt.month <= son_ay)]
    bir_onc = df[(df["Tarih_dt"].dt.year == son_yil - 1) &
                  (df["Tarih_dt"].dt.month <= son_ay)]

    # 12 aylık (son ay dahil son 12 ay)
    son12 = df.tail(12)
    onc12 = df.iloc[-24:-12] if len(df) >= 24 else None

    def s(row, col):
        """Tek değer al, None ise 0."""
        if row is None:
            return None
        v = row[col] if isinstance(row, pd.Series) else row[col].iloc[0]
        return float(v) if pd.notna(v) else 0.0

    def total(rows, col):
        if rows is None or rows.empty:
            return None
        return float(rows[col].sum())

    # Tablo satırları (PDF sırasına göre) - HAM sayılar olarak sakla
    rows = []

    def add(label, fn, level=0):
        try:
            ay_son = fn(son, mode="ay")
            ay_onc = fn(onc, mode="ay") if onc is not None else None
            bir_s = fn(bir_son, mode="bir")
            bir_o = fn(bir_onc, mode="bir") if bir_onc is not None and not bir_onc.empty else None
            y12_s = fn(son12, mode="bir")
            y12_o = fn(onc12, mode="bir") if onc12 is not None else None
        except Exception:
            ay_son = ay_onc = bir_s = bir_o = y12_s = y12_o = None

        def to_int(v):
            return None if v is None else int(round(v))

        rows.append({
            "Kalem": label,
            "_level": level,
            "Aylık (Cari)": to_int(ay_son),
            "Aylık (Önceki Yıl)": to_int(ay_onc),
            f"İlk {son_ay} Ay (Cari)": to_int(bir_s),
            f"İlk {son_ay} Ay (Önceki Yıl)": to_int(bir_o),
            "12 Aylık (Cari)": to_int(y12_s),
            "12 Aylık (Önceki Yıl)": to_int(y12_o),
        })

    # Helper
    def get(row_or_df, col, mode):
        if mode == "ay":
            return s(row_or_df, col)
        return total(row_or_df, col)

    # Cari İşlemler Dengesi
    add("Cari İşlemler Dengesi", lambda x, mode: get(x, "Cari İşlemler Dengesi", mode))
    add("Dış Ticaret Dengesi", lambda x, mode: get(x, "Dış Ticaret Dengesi", mode), 1)
    add("İhracat", lambda x, mode: get(x, "Toplam Mal İhracatı", mode), 2)
    add("Altın", lambda x, mode: get(x, "Altın İhracatı", mode), 3)
    add("Altın hariç",
        lambda x, mode: (get(x, "Toplam Mal İhracatı", mode) or 0) - (get(x, "Altın İhracatı", mode) or 0), 3)
    add("İthalat", lambda x, mode: get(x, "Toplam Mal İthalatı", mode), 2)
    add("Altın", lambda x, mode: get(x, "Altın İthalatı", mode), 3)
    add("Hizmetler Dengesi", lambda x, mode: get(x, "Hizmetler Dengesi", mode), 1)
    add("Hizmet Gelirleri", lambda x, mode: get(x, "Hizmet Gelirleri", mode), 2)
    add("Taşımacılık", lambda x, mode: get(x, "Taşımacılık - Gelir", mode), 3)
    add("Seyahat", lambda x, mode: get(x, "Seyahat - Gelir", mode), 3)
    add("Diğer",
        lambda x, mode: ((get(x, "Hizmet Gelirleri", mode) or 0)
                         - (get(x, "Taşımacılık - Gelir", mode) or 0)
                         - (get(x, "Seyahat - Gelir", mode) or 0)), 3)
    add("Hizmet Giderleri", lambda x, mode: get(x, "Hizmet Giderleri", mode), 2)
    add("Taşımacılık", lambda x, mode: get(x, "Taşımacılık - Gider", mode), 3)
    add("Seyahat", lambda x, mode: get(x, "Seyahat - Gider", mode), 3)
    add("Diğer",
        lambda x, mode: ((get(x, "Hizmet Giderleri", mode) or 0)
                         - (get(x, "Taşımacılık - Gider", mode) or 0)
                         - (get(x, "Seyahat - Gider", mode) or 0)), 3)
    add("Gelir Dengesi**",
        lambda x, mode: ((get(x, "Birincil Gelir Dengesi", mode) or 0)
                         + (get(x, "İkincil Gelir Dengesi", mode) or 0)), 1)
    # Cari İşlemler Dengesi (Altın hariç) = CİD - net altın (Q17)
    add("Cari İşlemler Dengesi (Altın hariç)",
        lambda x, mode: ((get(x, "Cari İşlemler Dengesi", mode) or 0)
                         - (get(x, "Parasal Olmayan Altın (net)", mode) or 0)))

    table_df = pd.DataFrame(rows)
    return table_df, son_dt


def save_outputs(raw_df, table_df, son_dt):
    out_dir = Path(__file__).parent
    raw_df.to_excel(out_dir / "odemeler_dengesi_raw.xlsx", index=False)
    # _level kolonu dashboard'da girinti için kullanılır, sakla
    table_df.to_excel(out_dir / "odemeler_dengesi_tablo.xlsx", index=False)
    print(f"Kaydedildi: odemeler_dengesi_raw.xlsx + odemeler_dengesi_tablo.xlsx")
    print(f"Son ay: {son_dt.strftime('%B %Y')}")


def main():
    items = fetch_monthly_data()
    df = to_dataframe(items)
    print(f"DataFrame: {df.shape}")
    table_df, son_dt = build_pdf_table(df)
    print("\n=== Tablo (son ay):", son_dt.strftime("%b %Y"), "===")
    print(table_df.drop(columns=["_level"]).to_string(index=False))
    save_outputs(df, table_df, son_dt)
    print("BAŞARILI")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)
