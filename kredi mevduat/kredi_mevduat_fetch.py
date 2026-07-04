"""
TCMB Kredi & Mevduat Faiz Oranları — EVDS3 API'sinden çeker.
============================================================
Seriler proje kökündeki "kredi ve mevduat verileri.xlsx" dosyasından okunur
(4 sayfa: kredi akım, mevduat akım, krediler stok, mevduat stok).

  - Akım  = yeni açılan kredi / yeni açılan mevduata uygulanan faiz — HAFTALIK
  - Stok  = mevcut kredi / mevduat portföyünün faizi              — AYLIK

Tüm seriler faiz oranı (%). Çıktı: kredi_mevduat.xlsx
  Sayfalar: Kredi_Akim, Kredi_Stok, Mevduat_Akim, Mevduat_Stok, Meta
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

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
SRC_EXCEL = ROOT_DIR / "kredi ve mevduat verileri.xlsx"


def clean_label(name):
    """'İhtiyaç Kredisi (TL, Akım, %) - Düzey' -> 'İhtiyaç Kredisi'.
    'KMH Dahil', 'Vadesiz Hariç' gibi anlamlı parantezler korunur; döviz eklenir."""
    s = re.sub(r"\s*-\s*Düzey\s*$", "", str(name)).strip()
    low = s.lower()
    cur = " (EUR)" if "euro" in low else (" (USD)" if "abd doları" in low else "")
    # yalnızca boilerplate parantezi (Akım/Stok/% içeren) kaldır
    s = re.sub(r"\s*\([^)]*(?:Ak[ıi]m|Stok|%)[^)]*\)", "", s).strip()
    return s + cur


def read_series_defs():
    """Excel'in 4 sayfasından (bölüm, frekans, kod, etiket) tanımlarını okur."""
    xl = pd.ExcelFile(SRC_EXCEL)
    groups = {}  # (section, freq) -> list of (code, label)
    for sn in xl.sheet_names:
        low = sn.lower()
        section = "Kredi" if "kredi" in low else "Mevduat"
        freq = "Akim" if ("akım" in low or "akim" in low) else "Stok"
        col = pd.read_excel(SRC_EXCEL, sheet_name=sn, header=None)[0].astype(str).tolist()
        items = []
        for i, v in enumerate(col):
            v = v.strip()
            if re.match(r"^TP\.", v):
                nm = col[i + 1].strip() if i + 1 < len(col) else v
                items.append((v, clean_label(nm)))
        groups[(section, freq)] = items
    return groups


def fetch(codes, weekly, retries=3):
    """Kodları tek istekte çeker. weekly=True ise haftalık (Akım), değilse aylık (Stok)."""
    end = datetime.now().strftime("%d-%m-%Y")
    start = "01-01-2015"
    url = f"{BASE_URL}/series={'-'.join(codes)}&startDate={start}&endDate={end}&type=json"
    headers = {"key": API_KEY, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            print(f"  EVDS ({'haftalık' if weekly else 'aylık'}) deneme {attempt}...")
            r = requests.get(url, headers=headers, timeout=45)
            r.raise_for_status()
            data = r.json()
            if "items" not in data:
                raise ValueError(f"Beklenmeyen yanıt: {str(data)[:200]}")
            return data["items"]
        except Exception as e:
            last_err = e
            print(f"    başarısız: {e}")
    raise RuntimeError(f"EVDS çekilemedi: {last_err}")


def parse(items, code_to_label, weekly):
    rows = []
    for it in items:
        row = {"tarih": it.get("Tarih")}
        for code, label in code_to_label.items():
            key = code.replace(".", "_")
            v = it.get(key)
            row[label] = None if v in (None, "") else float(str(v).replace(",", "."))
        rows.append(row)
    df = pd.DataFrame(rows)
    fmt = "%d-%m-%Y" if weekly else "%Y-%m"
    df["tarih"] = pd.to_datetime(df["tarih"], format=fmt, errors="coerce")
    df = df.dropna(subset=["tarih"]).sort_values("tarih").reset_index(drop=True)
    # tümüyle boş satırları at
    val_cols = [c for c in df.columns if c != "tarih"]
    return df.dropna(how="all", subset=val_cols).reset_index(drop=True)


def main():
    print("TCMB Kredi & Mevduat faiz oranları çekiliyor (EVDS3)...")
    groups = read_series_defs()

    out_sheets = {}
    meta_rows = []
    for (section, freq), items in groups.items():
        if not items:
            continue
        weekly = (freq == "Akim")
        # aynı etiket iki kez gelirse ayrıştır
        code_to_label, seen = {}, {}
        for code, label in items:
            lab = label
            if lab in seen:
                seen[lab] += 1
                lab = f"{label} ({seen[label]})"
            else:
                seen[lab] = 1
            code_to_label[code] = lab
            meta_rows.append({"Bölüm": section, "Tür": freq, "Kod": code, "Kalem": lab})
        raw = fetch(list(code_to_label.keys()), weekly)
        df = parse(raw, code_to_label, weekly)
        out_sheets[f"{section}_{freq}"] = df
        print(f"  {section}_{freq}: {len(df)} kayıt | {df['tarih'].min().date()} → {df['tarih'].max().date()} | {len(code_to_label)} seri")

    out = SCRIPT_DIR / "kredi_mevduat.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for name, df in out_sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
        pd.DataFrame(meta_rows).to_excel(w, sheet_name="Meta", index=False)

    # Özet çıktı
    for name, df in out_sheets.items():
        last = df.iloc[-1]
        print(f"\n  {name} (son: {last['tarih'].date()}):")
        for c in [c for c in df.columns if c != "tarih"]:
            if pd.notna(last[c]):
                print(f"    {c:34s} %{last[c]:.2f}")
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
