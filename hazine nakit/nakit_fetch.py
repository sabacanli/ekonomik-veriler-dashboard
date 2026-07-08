"""
Hazine Nakit Gerçekleşmeleri — HMB'den çeker ve ayrıştırır.
============================================================
Kaynak: HMB Kamu Finansmanı İstatistikleri sayfası (WordPress API). Dosya adı
kökü sabit ("Hazine-Nakit-Gerceklesmeleri-...") olduğundan güncel URL otomatik
bulunur (her ay yeni klasör/hash'te yayınlanır).

Excel yapısı: yıl başına bir sheet; satırlar nakit kalemleri, sütunlar aylar
(Ocak..Aralık) + TOPLAM. Değerler Milyon TL. Satır etiketlerinde dipnot/formül
parantezleri vardır ("1. GELİRLER (2)", "5. NAKİT DENGESİ (1+4-2)") — normalize
edilerek eşleştirilir.

Not: Nakit Dengesi = Gelirler + Özelleştirme/Fon − Giderler. Negatif = nakit açığı.

Çıktı: nakit.xlsx  (Aylik sheet — tarih bazlı anahtar kalemler).
"""
import sys
import re
import requests
import pandas as pd
from pathlib import Path

HMB_PAGE_API = "https://www.hmb.gov.tr/portal/v2/pages?slug=kamu-finansmani-istatistikleri"
FILE_STEM = "Hazine-Nakit-Gerceklesmeleri"
SCRIPT_DIR = Path(__file__).parent

MONTHS = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6,
          "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}

# Normalize edilmiş satır etiketi -> iç sütun adı.
ROWS = {
    "GELİRLER": "gelir",
    "GİDERLER": "gider",
    "FAİZ DIŞI GİDERLER": "faiz_disi_gider",
    "FAİZ ÖDEMELERİ": "faiz_odemesi",
    "FAİZ DIŞI DENGE": "faiz_disi_denge",
    "ÖZELLEŞTİRME ve FON GELİRLERİ": "ozellestirme",
    "NAKİT DENGESİ": "nakit_denge",
    "FİNANSMAN": "finansman",
    "BORÇLANMA": "borclanma_net",
    "DIŞ BORÇLANMA": "dis_borclanma_net",
    "İÇ BORÇLANMA": "ic_borclanma_net",
}


def norm(lab):
    """Dipnot/formül parantezlerini ve baştaki 'N.' numarasını atarak sadeleştir."""
    if not isinstance(lab, str):
        return ""
    s = re.sub(r"\([^)]*\)", "", lab)       # (2), (1+4-2), (NET) ...
    s = re.sub(r"^\s*\d+\.\s*", "", s)       # baştaki "1. " "2. " ...
    s = re.sub(r"\s+", " ", s).strip()
    return s


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


def parse_sheet(df):
    # Ay başlık satırını bul (içinde 'Ocak' geçen)
    hrow = None
    for i in range(min(12, len(df))):
        if any(str(v).strip() == "Ocak" for v in df.iloc[i].tolist()):
            hrow = i
            break
    if hrow is None:
        return {}
    col_month = {c: MONTHS[str(df.iloc[hrow, c]).strip()]
                 for c in range(df.shape[1])
                 if str(df.iloc[hrow, c]).strip() in MONTHS}
    # ay -> {clean: value}. İlk eşleşen satır kazanır (alt tekrarlara karşı koruma).
    recs = {}
    seen = set()
    for i in range(df.shape[0]):
        key = norm(df.iloc[i, 1])
        if key in ROWS and key not in seen:
            seen.add(key)
            clean = ROWS[key]
            for c, m in col_month.items():
                v = df.iloc[i, c]
                if isinstance(v, (int, float)) and pd.notna(v):
                    recs.setdefault(m, {})[clean] = float(v)
    return recs


def main():
    print("Hazine Nakit Gerçekleşmeleri çekiliyor (HMB)...")
    url = discover_url()
    print(f"  URL: {url.rsplit('/', 1)[-1]}")
    content = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60).content
    raw = SCRIPT_DIR / "nakit_kaynak.xls"
    raw.write_bytes(content)

    xls = pd.ExcelFile(raw, engine="xlrd")
    rows = []
    for sn in xls.sheet_names:
        try:
            year = int(str(sn).strip())
        except ValueError:
            continue
        df = pd.read_excel(xls, sheet_name=sn, header=None)
        recs = parse_sheet(df)
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
    cols = ["tarih", "yil", "ay", "gelir", "gider", "faiz_disi_gider", "faiz_odemesi",
            "faiz_disi_denge", "ozellestirme", "nakit_denge", "finansman",
            "borclanma_net", "ic_borclanma_net", "dis_borclanma_net"]
    out = out[[c for c in cols if c in out.columns]]

    out_path = SCRIPT_DIR / "nakit.xlsx"
    out.to_excel(out_path, sheet_name="Aylik", index=False)

    last = out.iloc[-1]
    print(f"  {len(out)} ay | {out['tarih'].min().date()} → {out['tarih'].max().date()}")
    print(f"  Son ay ({last['tarih'].strftime('%m.%Y')}), Milyon TL:")
    for c in ["gelir", "gider", "faiz_odemesi", "faiz_disi_denge", "nakit_denge", "borclanma_net"]:
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
