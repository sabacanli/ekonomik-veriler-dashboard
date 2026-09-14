#!/usr/bin/env python3
"""HMB "İç Borçlanma Stratejisi" PDF'lerini (aylık yayımlanan 3 aylık program) ayrıştırır.

pdf/ klasöründeki her baskıdan:
  Sayfa 1 — İç Borç Ödemeleri: ay bazında Piyasa / Kamu / Toplam (Milyon TL)
  Sayfa 2 — Hazine Finansman Programı tablosu (Milyar TL): İç Borç Servisi (anapara/faiz),
            İç Borçlanma, Piyasadan İhale Yoluyla İç Borçlanma, Doğrudan Satışlar, Kamuya Satışlar

Her ay 3 ardışık baskıda görünür (ilk ay = kesinleşmiş program, 2./3. ay = öngörü).
Ay bazında en yakın ufuklu baskı esas alınır; kesin baskısı olmayan aylar "ufuk" > 1 ile
öngörü olarak işaretli kalır. Çıktı: program.json (tüm tutarlar Milyar TL).

Kullanım: yeni baskıyı pdf/ klasörüne at, bu scripti çalıştır, site_export'u koştur.
"""
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

HERE = Path(__file__).resolve().parent
PDF_DIR = HERE / "pdf"
OUT = HERE / "program.json"

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
AY_NO = {a: i + 1 for i, a in enumerate(AYLAR)}
NUM = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$")

# Sayfa 2 satır etiketleri (dipnot numaraları temizlendikten sonra tam eşleşme)
SATIRLAR = {
    "odemeler": "Ödemeler",
    "ic_servis": "İç Borç Servisi",
    "dis_servis": "Dış Borç Servisi",
    "borclanma_disi": "Borçlanma Dışı Kaynaklar",
    "borclanma": "Borçlanma",
    "ic_borclanma": "İç Borçlanma",
    "ihale": "Piyasadan İhale Yoluyla İç Borçlanma",
    "dogrudan": "Doğrudan Satışlar",
    "kamuya": "Kamuya Satışlar",
}


def satirlar(page):
    """Sayfadaki metin satırları (x0, y0, x-merkez, metin).

    Bitişik hücreler PyMuPDF'te tek satıra kaynayabiliyor ('216.805 8.617 225.422');
    salt sayı dizisi olan satırlar karakter konumuna göre orantılı x ile hücrelere ayrılır.
    """
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if not t:
                continue
            x0, y0, x1, _ = l["bbox"]
            parcalar = t.split()
            if len(parcalar) > 1 and all(NUM.match(p) for p in parcalar):
                for m in re.finditer(r"\S+", t):
                    a, z = m.start() / len(t), m.end() / len(t)
                    out.append({"x0": x0 + (x1 - x0) * a, "y0": y0,
                                "xc": x0 + (x1 - x0) * (a + z) / 2, "t": m.group(0)})
            else:
                out.append({"x0": x0, "y0": y0, "xc": (x0 + x1) / 2, "t": t})
    return out


def basliklar_bul(page):
    """Sayfa 2 ay başlıkları ('Şubat 2025 (1)') → [(x-merkez, 'YYYY-MM')] soldan sağa.

    Uzun ay adlarında bitişik başlıklar tek span'a kaynayabildiğinden ('Haziran 2025 (1)
    Temmuz 2025 (1)') span içinde tüm eşleşmeler aranır, x konumu karakter oranıyla kestirilir.
    """
    pat = re.compile(r"(\S+) (\d{4})(?: \(\d\))?")
    # Tablo, giriş paragrafının uzunluğuna göre dikeyde kayabiliyor (Tr12/2025'te ~46 pt):
    # başlık şeridi "HAZİNE FİNANSMAN PROGRAMI" satırına göre aranır (onun 12–40 pt altı).
    # Üstteki düz metin ("Ocak - Mart 2025 dönemi…") x<280'de kaldığından ayrıca dışlanır.
    baslik_y = next((l["y0"] for l in satirlar(page) if l["t"].startswith("HAZİNE FİNANSMAN")), 102.0)
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            if not (baslik_y + 12 <= l["bbox"][1] <= baslik_y + 40) or l["bbox"][0] < 280:
                continue
            for s in l["spans"]:
                t, x0, x1 = s["text"], s["bbox"][0], s["bbox"][2]
                for m in pat.finditer(t):
                    if m.group(1) not in AY_NO or not t:
                        continue
                    a, z = m.start() / len(t), m.end() / len(t)
                    out.append((x0 + (x1 - x0) * (a + z) / 2,
                                f"{int(m.group(2))}-{AY_NO[m.group(1)]:02d}"))
    out.sort()
    return out


def sayi(t):
    return float(t.replace(".", "").replace(",", "."))


def temiz(t):
    return re.sub(r"\s*\(\d\)", "", t).strip()


def parse_odemeler(page):
    """Sayfa 1 → {'2025-01': {'piyasa','kamu','toplam'}} (Milyar TL)."""
    L = satirlar(page)
    out = {}
    basliklar = [l for l in L if re.match(r"^(\d{4}) Yılı (\S+) Ayı", l["t"])]
    toplamlar = [l for l in L if l["t"] == "TOPLAM"]
    for b in basliklar:
        m = re.match(r"^(\d{4}) Yılı (\S+) Ayı", b["t"])
        ay = f"{int(m.group(1))}-{AY_NO[m.group(2)]:02d}"
        tl = min((t for t in toplamlar if t["y0"] > b["y0"]), key=lambda t: t["y0"], default=None)
        if tl is None:
            continue
        nums = sorted((l for l in L if abs(l["y0"] - tl["y0"]) < 3 and NUM.match(l["t"])),
                      key=lambda l: l["x0"])
        if len(nums) < 2:
            continue
        p, k = sayi(nums[0]["t"]) / 1000, sayi(nums[1]["t"]) / 1000
        tp = sayi(nums[2]["t"]) / 1000 if len(nums) > 2 else p + k
        out[ay] = {"piyasa": round(p, 3), "kamu": round(k, 3), "toplam": round(tp, 3)}
    return out


def parse_program(page):
    """Sayfa 2 → ({'2025-01': {...satırlar...}}, [aylar sırayla])."""
    L = satirlar(page)
    basliklar = basliklar_bul(page)
    aylar = [a for _, a in basliklar]
    out = {a: {} for a in aylar}
    if not basliklar:
        return out, aylar

    def sutun(xc):
        return min(basliklar, key=lambda b: abs(b[0] - xc))[1]

    etiketler = {}
    for l in L:
        for anahtar, ad in SATIRLAR.items():
            if temiz(l["t"]) == ad and l["x0"] < 300:
                etiketler[anahtar] = l
    # İç borç servisinin anapara/faiz alt satırları: İç ve Dış servis etiketleri arasında
    if "ic_servis" in etiketler and "dis_servis" in etiketler:
        y1, y2 = etiketler["ic_servis"]["y0"], etiketler["dis_servis"]["y0"]
        for l in L:
            if y1 < l["y0"] < y2 and l["x0"] < 300 and temiz(l["t"]) in ("Anapara", "Faiz"):
                etiketler["ic_" + ("anapara" if "Anapara" in l["t"] else "faiz")] = l

    for anahtar, et in etiketler.items():
        for l in L:
            if l["x0"] > 300 and abs(l["y0"] - et["y0"]) <= 5 and NUM.match(l["t"]):
                out[sutun(l["xc"])][anahtar] = sayi(l["t"])
    return out, aylar


def yayin_tarihi(page):
    for l in satirlar(page):
        m = re.match(r"^(\d{1,2}) (\S+) (\d{4})$", l["t"])
        if m and m.group(2) in AY_NO:
            return f"{int(m.group(3))}-{AY_NO[m.group(2)]:02d}-{int(m.group(1)):02d}"
    return None


def main():
    baskilar = []
    for f in sorted(PDF_DIR.glob("*.pdf")):
        doc = fitz.open(f)
        od = parse_odemeler(doc[0])
        pr, aylar = parse_program(doc[1])
        if len(aylar) != 3:
            print(f"UYARI: {f.name}: {len(aylar)} ay başlığı bulundu, atlandı", file=sys.stderr)
            continue
        # Tutarlılık: sayfa 1 toplam ödeme ≈ sayfa 2 iç borç servisi
        for a in aylar:
            s1, s2 = od.get(a, {}).get("toplam"), pr.get(a, {}).get("ic_servis")
            if s1 is not None and s2 is not None and abs(s1 - s2) > 0.15:
                print(f"UYARI: {f.name} {a}: sayfa1 toplam {s1:.1f} ≠ sayfa2 servis {s2:.1f}",
                      file=sys.stderr)
        baskilar.append({"dosya": f.name, "yayin": yayin_tarihi(doc[0]),
                         "aylar": aylar, "odeme": od, "program": pr})

    aylik, revizyon = {}, {}
    for b in baskilar:
        for ufuk, ay in enumerate(b["aylar"], start=1):
            kayit = {"ufuk": ufuk, "kaynak": b["dosya"], "yayin": b["yayin"],
                     "odeme": b["odeme"].get(ay), "program": b["program"].get(ay)}
            revizyon.setdefault(ay, []).append(
                {"ufuk": ufuk, "yayin": b["yayin"],
                 "ihale": kayit["program"].get("ihale") if kayit["program"] else None})
            if ay not in aylik or ufuk < aylik[ay]["ufuk"]:
                aylik[ay] = kayit
    for ay in revizyon:
        revizyon[ay].sort(key=lambda r: -r["ufuk"])   # en eski öngörüden kesine

    OUT.write_text(json.dumps({
        "aylar": dict(sorted(aylik.items())),
        "revizyon": dict(sorted(revizyon.items())),
        "baski_sayisi": len(baskilar),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(baskilar)} baskı → {len(aylik)} ay · {OUT.name}")
    for ay, r in sorted(aylik.items()):
        p, o = r["program"] or {}, r["odeme"] or {}
        print(f"  {ay}  ufuk={r['ufuk']}  ihale={p.get('ihale', '—'):>6}  servis={p.get('ic_servis', '—'):>6}"
              f"  ödeme(piyasa/kamu)={o.get('piyasa', '—')}/{o.get('kamu', '—')}  ← {r['kaynak'][:24]}")


if __name__ == "__main__":
    main()
