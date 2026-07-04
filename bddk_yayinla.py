"""
BDDK verilerini buluta yayınlar.
================================
'bddk veri çekme' klasöründeki en güncel TL ve USD Excel'lerini repodaki
'bddk_data/' klasörüne kopyalar, ardından git commit + push yapar.
Böylece Streamlit Cloud sürümü (iş arkadaşları) en güncel BDDK verisini görür.

YALNIZCA YERELDE çalıştırılır (git kimliği + push erişimi gerekir).
Scraping'in kendisi burada YAPILMAZ; önce dashboard'daki 'TL/USD Çek'
butonlarıyla (Selenium) veri çekilmiş olmalı.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "bddk veri çekme"
DST = ROOT / "bddk_data"
KEEP = 6  # her para biriminden repoda tutulacak en güncel dosya sayısı


def latest(pattern, n):
    files = sorted(SRC.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)
    return files[:n]


def main():
    if not SRC.exists():
        print("HATA: 'bddk veri çekme' klasörü bulunamadı.", file=sys.stderr)
        sys.exit(1)

    picked = latest("bddk_krediler_TL_*.xls*", KEEP) + latest("bddk_krediler_USD_*.xls*", KEEP)
    if not picked:
        print("HATA: Yayınlanacak BDDK Excel'i yok. Önce 'TL/USD Çek' ile veri çekin.",
              file=sys.stderr)
        sys.exit(1)

    DST.mkdir(exist_ok=True)
    # Eski yayınları temizle (rolling window)
    for old in DST.glob("bddk_*.xls*"):
        old.unlink()
    for f in picked:
        shutil.copy2(f, DST / f.name)
        print(f"  kopyalandı: {f.name}")
    print(f"{len(picked)} dosya bddk_data/ klasörüne yayınlandı.")

    # git add + commit + push
    def git(*args, check=True):
        return subprocess.run(["git", *args], cwd=ROOT, check=check)

    git("add", "bddk_data")
    commit = subprocess.run(
        ["git", "commit", "-m", "BDDK verisi guncellendi (buluta yayin)"],
        cwd=ROOT,
    )
    if commit.returncode != 0:
        print("Not: yeni değişiklik yok (veri zaten güncel).")
    push = subprocess.run(["git", "push", "origin", "main"], cwd=ROOT)
    if push.returncode != 0:
        print("HATA: git push başarısız. Elle 'git push' gerekebilir.", file=sys.stderr)
        sys.exit(1)
    print("BAŞARILI: BDDK verileri buluta yayınlandı.")


if __name__ == "__main__":
    main()
