#!/usr/bin/env python3
"""Bankacılık Monitörü — aylık güncelleme (GitHub Actions ve yerel).

  python update.py --otomatik          BDDK'daki son yayımlanmış ayı bulur; sitede zaten varsa hiçbir şey yapmaz
  python update.py --donem 2026-08     belirli dönem için üretir
  --zorla: aynı dönem olsa da yeniden üret · --cekme: veri çekmeyi atla (raw/ mevcut)

Adımlar: fetch_bddk.py (2022-01 → dönem) → gorunum.py (Ayın Görünümü; ANTHROPIC_API_KEY varsa Claude) →
rapor.py → site/raporlar/bankacilik-monitoru-YYYY-MM.pdf → build_xlsx.py → ...-veri.xlsx → export_web.py → site/data/bankacilik.json
GITHUB_OUTPUT varsa 'yeni=true|false' ve 'donem=YYYY-MM' yazar (iş akışı e-posta ve commit adımlarını buna göre atlar)."""
import argparse, json, os, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; BASE = HERE.parent
sys.path.insert(0, str(HERE))
PY = sys.executable
AY = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']


def cikti(ad, deger):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f"{ad}={deger}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--donem'); ap.add_argument('--otomatik', action='store_true'); ap.add_argument('--zorla', action='store_true'); ap.add_argument('--cekme', action='store_true')
    a = ap.parse_args()
    import fetch_bddk as F
    donem = a.donem or F.latest_available()
    y, m = map(int, donem.split('-'))
    mevcut = None
    js = BASE / 'site' / 'data' / 'bankacilik.json'
    if js.exists():
        try:
            mevcut = json.loads(js.read_text(encoding='utf-8')).get('donem')
        except Exception:
            pass
    print(f"BDDK son dönem: {donem} · sitede: {mevcut or '—'}")
    if a.otomatik and mevcut == donem and not a.zorla:
        print("Yeni ay yok — güncelleme atlandı."); cikti('yeni', 'false'); cikti('donem', donem); return
    if not a.cekme:
        subprocess.check_call([PY, str(HERE / 'fetch_bddk.py'), '--start', '2022-01', '--end', donem], cwd=HERE)
    subprocess.call([PY, str(HERE / 'makro.py')], cwd=HERE)        # EVDS ek verileri (anahtar yoksa önbellek)
    subprocess.check_call([PY, str(HERE / 'gorunum.py')], cwd=HERE)
    rdir = BASE / 'site' / 'raporlar'; rdir.mkdir(parents=True, exist_ok=True)
    pdf = rdir / f"bankacilik-monitoru-{donem}.pdf"; xlsx = rdir / f"bankacilik-monitoru-{donem}-veri.xlsx"
    subprocess.check_call([PY, str(HERE / 'rapor.py'), str(pdf)], cwd=HERE)
    subprocess.check_call([PY, str(HERE / 'build_xlsx.py'), str(xlsx)], cwd=HERE)
    subprocess.check_call([PY, str(HERE / 'export_web.py'), '--pdf', f"raporlar/{pdf.name}", '--xlsx', f"raporlar/{xlsx.name}"], cwd=HERE)
    print(f"Hazır: {pdf.relative_to(BASE)} ({pdf.stat().st_size // 1024} KB) · {xlsx.name} · dönem {AY[m - 1]} {y}")
    cikti('yeni', 'true'); cikti('donem', donem); cikti('donem_ad', f"{AY[m - 1]} {y}")
    print('BAŞARILI')


if __name__ == '__main__':
    main()
