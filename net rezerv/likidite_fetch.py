"""
TCMB Uluslararası Rezervler ve Döviz Likiditesi (URDL) — haftalık şablon.
=========================================================================
Kaynak: TCMB "Veri (Tablolar) - Haftalık" sayfasındaki URDL_*.zip (IMF rezerv
şablonu; her hafta yeni dosya/UUID ile yayınlanır — link otomatik bulunur).

Çekilen kalemler (Milyon USD):
  I.A    Resmi rezerv varlıkları (altın dahil brüt)
  I.A.1  Döviz varlıkları
  I.A.4  Altın
  II.2   Yurt içi para karşılığı forward/future (swap forward bacağı) — negatif
  II.3   Diğer (repo/ters repo vb.) — işaretli
  swap_toplam = II.2 + II.3   →  "swap hariç net rezerv" = Net UR + swap_toplam

Dosyada yalnız son 3 kolon (önceki ay sonu + son 2 Cuma) bulunur; script her
koşuda mevcut likidite.xlsx ile BİRLEŞTİRİR (tarih bazlı upsert) — zamanla
tarihsel seri birikir.

Çıktı: likidite.xlsx
"""
import io
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

SAYFA = ("https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/"
         "Istatistikler/Odemeler+Dengesi+ve+Ilgili+Istatistikler/"
         "Uluslararasi+Rezervler+ve+Doviz+Likiditesi/Veri+%28Tablolar%29+-+Haftalik")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
SCRIPT_DIR = Path(__file__).parent
OUT = SCRIPT_DIR / "likidite.xlsx"

AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
         "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}

# Satır etiketi (başlangıç eşleşmesi) -> kolon adı
SATIRLAR = [
    ("I.A. Resmi rezerv", "resmi_rezerv"),
    ("I.A.1 Döviz varlıkları", "doviz"),
    ("I.A.4 Altın", "altin"),
    ("II.2. Yurt içi para karşılığında", "swap_forward"),
    ("II.3. Diğer", "diger"),
]


def zip_url_bul():
    r = requests.get(SAYFA, headers=UA, timeout=30)
    r.raise_for_status()
    m = re.search(r'href="(/wps/wcm/connect/[^"]*URDL_\d+\.zip\?MOD=AJPERES[^"]*)"', r.text)
    if not m:
        raise RuntimeError("URDL zip linki sayfada bulunamadı.")
    return "https://www.tcmb.gov.tr" + m.group(1).replace("&amp;", "&")


def kolon_tarihi(v):
    """Kolon başlığını tarihe çevirir: datetime, '13.05.2022' ya da 'Haziran 2026' (ay sonu)."""
    if isinstance(v, datetime):
        return pd.Timestamp(v).normalize()
    s = str(v).strip().lower()
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:  # eski şablonlarda tarihler metin
        return pd.Timestamp(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    for ad, no in AYLAR.items():
        if s.startswith(ad):
            yil = int(re.search(r"(\d{4})", s).group(1))
            return pd.Timestamp(yil, no, 1) + pd.offsets.MonthEnd(0)
    return None


def main():
    print("URDL (rezerv/likidite şablonu) çekiliyor...")
    url = zip_url_bul()
    print(f"  URL: ...{url.split('/')[-1][:40]}")
    z = zipfile.ZipFile(io.BytesIO(requests.get(url, headers=UA, timeout=60).content))
    xlsx_adi = next(n for n in z.namelist() if n.lower().endswith(".xlsx"))
    df = pd.read_excel(io.BytesIO(z.read(xlsx_adi)), header=None)

    # Başlık satırı: '(Milyon ABD Doları)' içeren satır; sonraki kolonlar tarihler
    hrow = next(i for i in range(len(df))
                if any("Milyon ABD" in str(v) for v in df.iloc[i].tolist()))
    tarihler = {}  # kolon indeksi -> tarih
    for c in range(1, df.shape[1]):
        t = kolon_tarihi(df.iloc[hrow, c])
        if t is not None:
            tarihler[c] = t
    if not tarihler:
        raise RuntimeError("Tarih kolonları çözülemedi.")

    kayitlar = {t: {} for t in tarihler.values()}
    for i in range(len(df)):
        # Etiket ilk dolu metin hücresinde (genelde 1. kolon; 0. kolon boş)
        etiket = ""
        for c in range(min(3, df.shape[1])):
            v = df.iloc[i, c]
            if isinstance(v, str) and v.strip():
                etiket = v.strip()
                break
        for onek, ad in SATIRLAR:
            if etiket.startswith(onek):
                for c, t in tarihler.items():
                    v = df.iloc[i, c]
                    if pd.notna(v) and isinstance(v, (int, float)):
                        kayitlar[t][ad] = float(v)
                break

    yeni = pd.DataFrame([{"tarih": t, **d} for t, d in kayitlar.items() if d])
    yeni["swap_toplam"] = yeni[["swap_forward", "diger"]].sum(axis=1, min_count=1)

    # Mevcutla birleştir (tarih upsert — yeni değerler eskiyi günceller)
    if OUT.exists():
        eski = pd.read_excel(OUT)
        eski["tarih"] = pd.to_datetime(eski["tarih"])
        birlesik = pd.concat([eski[~eski["tarih"].isin(yeni["tarih"])], yeni])
    else:
        birlesik = yeni
    birlesik = birlesik.sort_values("tarih").reset_index(drop=True)
    birlesik.to_excel(OUT, index=False)

    print(f"  {len(yeni)} dönem işlendi; dosyada toplam {len(birlesik)} kayıt.")
    for _, r in yeni.sort_values("tarih").iterrows():
        print(f"  {r['tarih'].date()}  resmi={r.get('resmi_rezerv', float('nan')):>9,.0f}  "
              f"altın={r.get('altin', float('nan')):>8,.0f}  "
              f"swap_toplam={r.get('swap_toplam', float('nan')):>9,.0f} mn USD")
    print(f"Kaydedildi: {OUT.name}")
    print("BAŞARILI")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)
