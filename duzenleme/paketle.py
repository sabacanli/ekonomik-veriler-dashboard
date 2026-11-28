#!/usr/bin/env python3
"""Düzenleme Zaman Çizelgesi — okuma paketleri.

Bir kurum-yılın belgelerini (başlıktan elenenler hariç) tarih sırasıyla, her biri en çok ~PAKET_KR karakterlik
düz metin dosyalarına böler: onbellek/paket/<kurum>_<yıl>_<n>.txt. Olay çıkaran (insan ya da Claude oturumu)
bu dosyaları sırayla okur. Ayrıca paketin belge listesini ve başlıktan elenenleri yazdırır.

  python3 -I duzenleme/paketle.py tcmb 2026
  python3 -I duzenleme/paketle.py --hepsi        # tüm kurum-yıllar; özet tablo
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ortak as O  # noqa: E402

PAKET = O.KOK / "onbellek" / "paket"
PAKET_KR = 70_000
BELGE_KR = 24_000       # tek belgeden pakete giren en çok karakter (çok uzun belgelerde baş + son)


def paketle(kurum, yil, yaz=True):
    dizin = [k for k in O.dizin_oku() if k["kurum"].lower() == kurum.lower() and (k.get("tarih") or "")[:4] == str(yil)]
    okunacak, elenen = [], []
    for k in dizin:
        n = O.baslik_eler_mi(k)
        (elenen if n else okunacak).append((k, n))
    paketler, simdiki, boy = [], [], 0
    for k, _ in okunacak:
        govde = O.metin_oku(k["id"]).strip()
        if len(govde) > BELGE_KR:
            govde = govde[: BELGE_KR * 2 // 3] + "\n\n[… belge uzun olduğu için ortası kesildi …]\n\n" + govde[-BELGE_KR // 3:]
        blok = (f"\n{'#' * 78}\n# BELGE {k['id']}\n# TARİH {k.get('tarih')} · TÜR {k['tur']}"
                f"{' · NO ' + str(k['no']) if k.get('no') else ''}\n# BAŞLIK {k['baslik']}\n"
                f"{'# NOT ' + k['not'] + chr(10) if k.get('not') else ''}{'#' * 78}\n{govde}\n")
        if simdiki and boy + len(blok) > PAKET_KR:
            paketler.append(simdiki)
            simdiki, boy = [], 0
        simdiki.append(blok)
        boy += len(blok)
    if simdiki:
        paketler.append(simdiki)
    yollar = []
    if yaz:
        PAKET.mkdir(parents=True, exist_ok=True)
        for eski in PAKET.glob(f"{kurum.lower()}_{yil}_*.txt"):
            eski.unlink()
        for i, p in enumerate(paketler, 1):
            f = PAKET / f"{kurum.lower()}_{yil}_{i}.txt"
            f.write_text(f"PAKET {kurum.upper()} {yil} — {i}/{len(paketler)}\n" + "".join(p), encoding="utf-8")
            yollar.append(f)
    return okunacak, elenen, yollar, sum(len(b) for p in paketler for b in p)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--hepsi":
        yillar = sorted({(k.get("tarih") or "????")[:4] for k in O.dizin_oku()})
        print(f"{'':10}" + "".join(f"{y:>16}" for y in yillar))
        for kurum in O.KURUMLAR:
            satir = f"{kurum:10}"
            for y in yillar:
                ok, el, yol, kr = paketle(kurum, y, yaz=("--yaz" in sys.argv))
                satir += f"{len(ok):4d} blg {kr // 1000:4d}k {len(el):3d}e"
            print(satir)
        print("(blg = okunacak belge, k = bin karakter, e = başlıktan elenen)")
        return
    kurum, yil = sys.argv[1], sys.argv[2]
    ok, el, yollar, kr = paketle(kurum, yil)
    print(f"{kurum.upper()} {yil}: {len(ok)} belge okunacak ({kr:,} karakter, {len(yollar)} paket) · {len(el)} belge başlıktan elendi")
    for f in yollar:
        print("  PAKET:", f)
    print("OKUNACAK BELGELER:")
    for k, _ in ok:
        print(f"  {k['id']} · {k.get('tarih')} · {k['baslik'][:90]}")
    print("BAŞLIKTAN ELENENLER (olay dosyasına yazılmaz):")
    for k, n in el:
        print(f"  {k['id']} · {k['baslik'][:70]} → {n}")


if __name__ == "__main__":
    main()
