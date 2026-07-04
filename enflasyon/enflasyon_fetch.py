"""
Türkiye TÜFE (Tüketici Fiyat Endeksi) — EVDS3 API'sinden çeker ve analiz eder.
==============================================================================
Ana endeks:
  TP.TUKFIY2025.GENEL   Genel TÜFE (2025=100), aylık

Alt kalemler (COICOP ana grupları) proje kökündeki
"enflasyon alt kalemleri.xlsx" dosyasından okunur:
  TP.TUKFIY2025.01 ... TP.TUKFIY2025.13

Hesaplanan analizler (hem genel hem her alt kalem için):
  - Aylık enflasyon  = endeks[t]  / endeks[t-1]  − 1
  - Yıllık enflasyon = endeks[t]  / endeks[t-12] − 1
  - Yılbaşından beri = endeks[t]  / endeks[Aralık(önceki yıl)] − 1

Çıktı: enflasyon.xlsx (Genel, AltKalem_Endeks, AltKalem_Yillik, AltKalem_Ozet).
"""
import os
import re
import sys
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

API_KEY = os.environ.get("EVDS_API_KEY", "")
BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis"
GENEL_CODE = "TP.TUKFIY2025.GENEL"

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
ALT_EXCEL = ROOT_DIR / "enflasyon alt kalemleri.xlsx"

# Excel okunamazsa yedek liste (COICOP ana grupları)
FALLBACK_ALT = [
    ("TP.TUKFIY2025.01", "01", "Gıda ve Alkolsüz İçecekler"),
    ("TP.TUKFIY2025.02", "02", "Alkollü İçecekler ve Tütün"),
    ("TP.TUKFIY2025.03", "03", "Giyim ve Ayakkabı"),
    ("TP.TUKFIY2025.04", "04", "Konut, Su, Elektrik, Gaz"),
    ("TP.TUKFIY2025.05", "05", "Mobilya, Ev Eşyası ve Bakımı"),
    ("TP.TUKFIY2025.06", "06", "Sağlık"),
    ("TP.TUKFIY2025.07", "07", "Ulaştırma"),
    ("TP.TUKFIY2025.08", "08", "Bilgi ve İletişim"),
    ("TP.TUKFIY2025.09", "09", "Eğlence, Dinlence ve Kültür"),
    ("TP.TUKFIY2025.10", "10", "Eğitim Hizmetleri"),
    ("TP.TUKFIY2025.11", "11", "Lokanta ve Konaklama"),
    ("TP.TUKFIY2025.12", "12", "Sigorta ve Finansal Hizmetler"),
    ("TP.TUKFIY2025.13", "13", "Kişisel Bakım ve Çeşitli"),
]


def load_alt_kalemler():
    """Alt kalem serilerini (code, no, ad) olarak Excel'den okur; olmazsa yedeği kullanır."""
    try:
        df = pd.read_excel(ALT_EXCEL, sheet_name=0, header=None)
        col = df[0].astype(str).tolist()
        out = []
        for i, v in enumerate(col):
            v = v.strip()
            if re.match(r"TP\.TUKFIY2025\.\d", v):
                raw = col[i + 1].strip() if i + 1 < len(col) else v
                m = re.match(r"(\d+)\.\s*(.*?)\s*-\s*Düzey\s*$", raw)
                if m:
                    no, ad = m.group(1), m.group(2)
                else:
                    no, ad = "", re.sub(r"\s*-\s*Düzey\s*$", "", raw)
                out.append((v, no, ad))
        if out:
            print(f"  Alt kalemler Excel'den okundu: {len(out)} kalem")
            return out
    except Exception as e:
        print(f"  UYARI: Excel okunamadı ({e}); yedek liste kullanılıyor.")
    return FALLBACK_ALT


def fetch(codes, start_date="01-01-2005", end_date=None, retries=3):
    if end_date is None:
        end_date = datetime.now().strftime("%d-%m-%Y")
    url = f"{BASE_URL}/series={'-'.join(codes)}&startDate={start_date}&endDate={end_date}&type=json"
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


def parse(items, code_to_col):
    rows = []
    for it in items:
        row = {"tarih": it.get("Tarih")}
        for code, col in code_to_col.items():
            key = code.replace(".", "_")
            v = it.get(key)
            row[col] = None if v in (None, "") else float(str(v).replace(",", "."))
        rows.append(row)
    df = pd.DataFrame(rows)
    df["tarih_dt"] = pd.to_datetime(df["tarih"], format="%Y-%m", errors="coerce")
    return df.dropna(subset=["tarih_dt"]).sort_values("tarih_dt").reset_index(drop=True)


def ytd(series, dates):
    """Yılbaşından beri (kümülatif): endeks[t] / endeks[önceki yıl Aralık] − 1."""
    out = []
    s = series.reset_index(drop=True)
    d = dates.reset_index(drop=True)
    for i in range(len(s)):
        yr = d[i].year
        # önceki yıl Aralık endeksi
        mask = (d.dt.year == yr - 1) & (d.dt.month == 12)
        base = s[mask]
        out.append((s[i] / base.iloc[0] - 1) * 100 if len(base) and pd.notna(base.iloc[0]) else None)
    return out


def main():
    print("Türkiye TÜFE verisi çekiliyor (EVDS3)...")
    alt = load_alt_kalemler()  # [(code, no, ad), ...]

    code_to_col = {GENEL_CODE: "genel"}
    col_to_ad = {"genel": "Genel TÜFE"}
    for code, no, ad in alt:
        col = f"k{no}" if no else code.split(".")[-1]
        code_to_col[code] = col
        col_to_ad[col] = f"{no}. {ad}" if no else ad

    items = fetch(list(code_to_col.keys()))
    print(f"  {len(items)} ham kayıt alındı")
    df = parse(items, code_to_col)
    print(f"  {len(df)} ay | {df['tarih_dt'].min().date()} → {df['tarih_dt'].max().date()}")

    value_cols = [c for c in code_to_col.values()]

    # ── Genel TÜFE analizleri ──
    genel = pd.DataFrame({"tarih": df["tarih_dt"]})
    genel["endeks"] = df["genel"]
    genel["aylik"] = df["genel"].pct_change() * 100
    genel["yillik"] = df["genel"].pct_change(12) * 100
    genel["ytd"] = ytd(df["genel"], df["tarih_dt"])

    # ── Alt kalem endeks & yıllık matrisleri (sütun adı = temiz ad) ──
    endeks_df = pd.DataFrame({"tarih": df["tarih_dt"]})
    yillik_df = pd.DataFrame({"tarih": df["tarih_dt"]})
    for col in value_cols:
        if col == "genel":
            continue
        endeks_df[col_to_ad[col]] = df[col]
        yillik_df[col_to_ad[col]] = df[col].pct_change(12) * 100

    # ── Alt kalem özet (son ay) ──
    last_i = len(df) - 1
    prev_i = last_i - 1
    y12_i = last_i - 12
    ozet_rows = []
    for code, no, ad in alt:
        col = code_to_col[code]
        endeks = df[col].iloc[last_i]
        aylik = (df[col].iloc[last_i] / df[col].iloc[prev_i] - 1) * 100 if prev_i >= 0 else None
        yillik = (df[col].iloc[last_i] / df[col].iloc[y12_i] - 1) * 100 if y12_i >= 0 else None
        _ytd = ytd(df[col], df["tarih_dt"])[last_i]
        ozet_rows.append({
            "No": no, "Kalem": ad, "Endeks": endeks,
            "Aylık %": aylik, "Yıllık %": yillik, "Yılbaşından %": _ytd,
        })
    ozet = pd.DataFrame(ozet_rows)

    out = SCRIPT_DIR / "enflasyon.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        genel.to_excel(w, sheet_name="Genel", index=False)
        endeks_df.to_excel(w, sheet_name="AltKalem_Endeks", index=False)
        yillik_df.to_excel(w, sheet_name="AltKalem_Yillik", index=False)
        ozet.to_excel(w, sheet_name="AltKalem_Ozet", index=False)

    g = genel.iloc[-1]
    print(f"\n  Son ay: {g['tarih'].strftime('%m.%Y')} | Endeks {g['endeks']:.2f}")
    print(f"  Aylık enflasyon : {g['aylik']:+.2f}%")
    print(f"  Yıllık enflasyon: {g['yillik']:+.2f}%")
    print(f"  Yılbaşından beri: {g['ytd']:+.2f}%")
    print("\n  Alt kalemler — yıllık enflasyon (yüksekten düşüğe):")
    for _, r in ozet.sort_values("Yıllık %", ascending=False).iterrows():
        print(f"    {r['No']}. {r['Kalem'][:34]:34s} {r['Yıllık %']:+6.1f}%  (aylık {r['Aylık %']:+.1f}%)")
    print(f"\nKaydedildi: {out.name}")
    print("BAŞARILI")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)
