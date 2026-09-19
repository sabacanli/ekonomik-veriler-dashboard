"""
Merkezi Yönetim Bütçe Dengesi ve Finansmanı — HMB'den çeker ve ayrıştırır.
=========================================================================
Kaynak: HMB Kamu Finansmanı İstatistikleri sayfası (WordPress API). Dosya adı
kökü sabit ("Merkezi-Yonetim-Butce-Dengesi-ve-Finansmani-...") olduğundan
güncel URL otomatik bulunur (her ay yeni klasör/hash'te yayınlanır).

Excel yapısı: yıl başına bir sheet; satırlar bütçe kalemleri, sütunlar aylar
(Oca..Ara) + TOPLAM. Değerler Milyon TL.

HMB bu dosyayı aylık sonuçlar açıklandıktan günler-haftalar sonra yeniler. Aradaki
boşlukta eksik son ay(lar), sonuçların açıklandığı gün güncellenen Muhasebat Genel
Müdürlüğü "Konsolide Bütçe Denge Tablosu"ndan (cari yıl, Bin TL) tamamlanır. O tabloda
dolaysız/dolaylı vergi kırılımı yoktur; bu iki kolon HMB dosyası yenilenene dek boş kalır.

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


MUH_PAGE_API = "https://muhasebat.hmb.gov.tr/portal/v2/pages?slug=merkezi-yonetim-butce-istatistikleri"
MUH_FILES_API = "https://muhasebat.hmb.gov.tr/portal/v2/files"
MUH_STEM = "Merkezi-Yonetim-Konsolide-Butce-Denge-Tablosu-"
MONTHS_TAM = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6,
              "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}
# Muhasebat denge tablosu satır etiketi -> iç sütun adı
MUH_ROWS = {
    "Gelirler": "gelir",
    "Vergi Gelirleri": "vergi",
    "Harcamalar": "gider",
    "1-Faiz Hariç Harcama": "faiz_haric_gider",
    "2-Faiz Harcamaları": "faiz_gideri",
    "Faiz Dışı Denge": "faiz_disi_denge",
    "Bütçe Dengesi": "denge",
}
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def muhasebat_url(year):
    """İstatistik ağacındaki '<yıl> Merkezi Yönetim… → Bütçe Dengesi' düğümünün denge tablosu URL'si."""
    agac = requests.get(MUH_PAGE_API, headers=UA, timeout=30).json()[0]["content"]["rendered"]
    m = re.search(rf'data-name="{year} Merkezi Yönetim[^"]*".*?data-name="Bütçe Dengesi" data-id="(\d+)"',
                  agac, re.S)
    if not m:
        return None
    liste = requests.get(MUH_FILES_API, params={"name": "Bütçe Dengesi", "id": m.group(1)},
                         headers=UA, timeout=30).json()["content"]
    for u in re.findall(r'href="(https://ms\.hmb\.gov\.tr/uploads/[^"]+?\.xlsx?)"', liste):
        ad = u.rsplit("/", 1)[-1]
        if ad.startswith(MUH_STEM) and "Onceki-Yilla" not in ad:
            return u
    return None


def muhasebat_aylar(year):
    """Muhasebat'ın cari yıl denge tablosu → {ay: {kalem: Milyon TL}} (yalnız yayımlanmış aylar)."""
    import xlrd
    import xlrd.biffh
    url = muhasebat_url(year)
    if not url:
        return {}
    content = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60).content
    # Dosyadaki bozuk sayı-biçimi dizgileri xlrd'yi düşürüyor; hücre değerlerini etkilemez
    xlrd.biffh.unicode = lambda b, enc: b.decode(enc, errors="replace")
    df = pd.read_excel(xlrd.open_workbook(file_contents=content), engine="xlrd",
                       sheet_name=0, header=None)
    hrow = next((i for i in range(min(12, len(df)))
                 if any(str(v).strip() == "Ocak" for v in df.iloc[i].tolist())), None)
    if hrow is None:
        return {}
    col_month = {c: MONTHS_TAM[str(df.iloc[hrow, c]).strip()] for c in range(df.shape[1])
                 if str(df.iloc[hrow, c]).strip() in MONTHS_TAM}
    recs = {}
    for i in range(df.shape[0]):
        lab = df.iloc[i, 1]
        lab = lab.strip() if isinstance(lab, str) else ""
        if lab in MUH_ROWS:
            for c, m in col_month.items():
                v = df.iloc[i, c]
                if isinstance(v, (int, float)) and pd.notna(v):
                    recs.setdefault(m, {})[MUH_ROWS[lab]] = float(v) / 1000.0   # Bin TL → Milyon TL
    return {m: d for m, d in recs.items() if d.get("gelir")}


def muhasebat_tamamla(out):
    """HMB dosyasında henüz olmayan ayları Muhasebat tablosundan ekler; ortak aylarda dengeyi çapraz denetler."""
    eklenen = []
    for year in sorted({int(out["yil"].max()), pd.Timestamp.today().year}):
        mevcut = set(out.loc[out["yil"] == year, "ay"])
        for m, d in sorted(muhasebat_aylar(year).items()):
            if m in mevcut:
                ref = out[(out["yil"] == year) & (out["ay"] == m)].iloc[0]
                if "denge" in d and abs(ref["denge"] - d["denge"]) > 1:
                    print(f"  UYARI: {m:02d}.{year} denge HMB {ref['denge']:,.0f} ≠ Muhasebat {d['denge']:,.0f}")
                continue
            out = pd.concat([out, pd.DataFrame([{"yil": year, "ay": m, **d}])], ignore_index=True)
            eklenen.append(f"{m:02d}.{year}")
    if eklenen:
        print(f"  + Muhasebat'tan tamamlanan ay(lar): {', '.join(eklenen)} "
              f"(vergi kırılımı HMB dosyası yenilenince dolar)")
    return out


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
    try:
        out = muhasebat_tamamla(out)
    except Exception as e:
        print(f"  UYARI: Muhasebat tamamlama atlandı ({e}) — HMB dosyasındaki son ayla devam")
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
