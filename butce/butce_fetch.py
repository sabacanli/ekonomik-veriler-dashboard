"""
Merkezi Yönetim Bütçe Dengesi ve Finansmanı — HMB'den çeker ve ayrıştırır.
=========================================================================
Kaynak: HMB Kamu Finansmanı İstatistikleri sayfası (WordPress API). Dosya adı
kökü sabit ("Merkezi-Yonetim-Butce-Dengesi-ve-Finansmani-...") olduğundan
güncel URL otomatik bulunur (her ay yeni klasör/hash'te yayınlanır).

Excel yapısı: yıl başına bir sheet; satırlar bütçe kalemleri, sütunlar aylar
(Oca..Ara) + TOPLAM. Değerler Milyon TL.

Çıktı: butce.xlsx  (Aylik sheet — tarih bazlı anahtar kalemler).
"""
import sys
import re
import requests
import pandas as pd
from pathlib import Path

HMB_PAGE_API = "https://www.hmb.gov.tr/portal/v2/pages?slug=kamu-finansmani-istatistikleri"
FILE_STEM = "Merkezi-Yonetim-Butce-Dengesi-ve-Finansmani"
SCRIPT_DIR = Path(__file__).parent

MONTHS = {"Oca": 1, "Şub": 2, "Mar": 3, "Nis": 4, "May": 5, "Haz": 6,
          "Tem": 7, "Ağu": 8, "Eyl": 9, "Eki": 10, "Kas": 11, "Ara": 12}

# Excel'deki satır etiketi (kolon 1) -> iç sütun adı. Tam eşleşme kullanılır.
ROWS = {
    "MERKEZİ YÖNETİM BÜTÇE GELİRLERİ": "gelir",
    "Vergi Gelirleri": "vergi",
    "Dolaysız Vergiler": "dolaysiz_vergi",
    "Dolaylı Vergiler": "dolayli_vergi",
    "MERKEZİ YÖNETİM BÜTÇE HARCAMALARI": "gider",
    "Faiz Hariç Bütçe Giderleri": "faiz_haric_gider",
    "Faiz Giderleri": "faiz_gideri",
    "MERKEZİ YÖNETİM BÜTÇE FAİZ DIŞI DENGESİ": "faiz_disi_denge",
    "MERKEZİ YÖNETİM BÜTÇE DENGESİ": "denge",
}


def discover_url():
    r = requests.get(HMB_PAGE_API, headers={"User-Agent": "Mozilla/5.0",
                     "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    content = r.json()[0]["content"]["rendered"]
    urls = re.findall(r'href="(https://ms\.hmb\.gov\.tr/uploads/\d{4}/\d{2}/[^"]+?\.xlsx?)"', content)
    for u in urls:
        if u.rsplit("/", 1)[-1].startswith(FILE_STEM):
            return u
    raise RuntimeError(f"'{FILE_STEM}' linki HMB sayfasında bulunamadı.")


def parse_sheet(df, year):
    # Ay başlık satırını bul (içinde 'Oca' geçen)
    hrow = None
    for i in range(min(12, len(df))):
        if any(str(v).strip() == "Oca" for v in df.iloc[i].tolist()):
            hrow = i
            break
    if hrow is None:
        return {}
    col_month = {c: MONTHS[str(df.iloc[hrow, c]).strip()]
                 for c in range(df.shape[1])
                 if str(df.iloc[hrow, c]).strip() in MONTHS}
    # ay -> {clean: value}
    recs = {}
    for i in range(df.shape[0]):
        lab = df.iloc[i, 1]
        lab = lab.strip() if isinstance(lab, str) else ""
        if lab in ROWS:
            clean = ROWS[lab]
            for c, m in col_month.items():
                v = df.iloc[i, c]
                if isinstance(v, (int, float)) and pd.notna(v):
                    recs.setdefault(m, {})[clean] = float(v)
    return recs


def main():
    print("Merkezi Yönetim Bütçe Dengesi çekiliyor (HMB)...")
    url = discover_url()
    print(f"  URL: {url.rsplit('/', 1)[-1]}")
    content = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60).content
    raw = SCRIPT_DIR / "butce_kaynak.xls"
    raw.write_bytes(content)

    xls = pd.ExcelFile(raw, engine="xlrd")
    rows = []
    for sn in xls.sheet_names:
        try:
            year = int(str(sn).strip())
        except ValueError:
            continue
        df = pd.read_excel(xls, sheet_name=sn, header=None)
        recs = parse_sheet(df, year)
        for m, d in recs.items():
            # yalnızca gelir DOLU ve sıfırdan farklı aylar (yayımlanmış aylar)
            if not d.get("gelir"):
                continue
            row = {"yil": year, "ay": m}
            row.update(d)
            rows.append(row)

    out = pd.DataFrame(rows)
    out["tarih"] = pd.to_datetime(dict(year=out["yil"], month=out["ay"], day=1))
    out = out.sort_values("tarih").reset_index(drop=True)
    # Kolon sırası
    cols = ["tarih", "yil", "ay", "gelir", "vergi", "dolaysiz_vergi", "dolayli_vergi",
            "gider", "faiz_haric_gider", "faiz_gideri", "faiz_disi_denge", "denge"]
    out = out[[c for c in cols if c in out.columns]]

    out_path = SCRIPT_DIR / "butce.xlsx"
    out.to_excel(out_path, sheet_name="Aylik", index=False)

    last = out.iloc[-1]
    print(f"  {len(out)} ay | {out['tarih'].min().date()} → {out['tarih'].max().date()}")
    print(f"  Son ay ({last['tarih'].strftime('%m.%Y')}), Milyon TL:")
    for c in ["gelir", "gider", "faiz_gideri", "faiz_disi_denge", "denge"]:
        if c in out.columns and pd.notna(last[c]):
            print(f"    {c:18s} {last[c]:>14,.0f}")
    print(f"Kaydedildi: {out_path.name}")
    print("BAŞARILI")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)
