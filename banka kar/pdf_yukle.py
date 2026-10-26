#!/usr/bin/env python3
"""PDF_YUKLE kutusunu (alt klasörler dahil) tarar; SOLO finansal rapor PDF'lerini uygulamanın ayrıştırıcısıyla
veritabanına yükler (uygulamadaki bootstrap.py ile aynı kayıt mantığı).

  - Konsolide raporlar yüklenmez; PDF_ISLENDI/_konsolide/<klasör>/ altına taşınır.
  - Okunamayan / banka-dönemi tespit edilemeyen dosyalar (sunumlar vb.) PDF_ISLENDI/_okunamayan/<klasör>/ altına taşınır.
  - Klasör adı dönem ipucudur (2025-3 → 2025Q3): PDF'ten tespit edilen dönem uyuşmazsa dosya yüklenmez,
    PDF_ISLENDI/_donem_uyusmazligi/<klasör>/ altına taşınır (elle bakılmalı).
  - Yüklenenler PDF_ISLENDI/<klasör>/ altına taşınır; rapor PDF_ISLENDI/yukleme_raporu_<zaman>.txt'ye yazılır.

  python3 "banka kar/pdf_yukle.py" [--klasor 2026-2] [--isci 4] [--kuru]
  banka_kar_export.pdf_isle() de her site güncellemesinde yukle() çağırır (kaynak uygulama yoksa sessizce atlar).
"""
from __future__ import annotations
import argparse, datetime as dt, logging, os, re, shutil, sys, time, warnings
from pathlib import Path
warnings.filterwarnings("ignore"); logging.getLogger("pdfminer").setLevel(logging.ERROR)
HERE = Path(__file__).resolve().parent


def klasor_donem(ad):
    m = re.fullmatch(r"(20\d\d)[-_ ]?[QÇq]?([1-4])", ad.strip())
    return f"{m.group(1)}Q{m.group(2)}" if m else None


def _parse(arg):
    """Alt süreçte çalışır: (yol, rapor | None, hata). arg = (uygulama klasörü, pdf yolu)."""
    app, path = arg
    warnings.filterwarnings("ignore"); logging.getLogger("pdfminer").setLevel(logging.ERROR)
    import io, contextlib
    if app not in sys.path:
        sys.path.insert(0, app)
    try:
        from core.parser import parse_pdf
        with contextlib.redirect_stderr(io.StringIO()):
            rep = parse_pdf(path, os.path.basename(path))
        return path, rep, None
    except Exception as e:
        return path, None, f"{type(e).__name__}: {str(e)[:120]}"


def _birim_duzelt(db, rep):
    """Sayfada birim ifadesi yoksa ve toplam aktif bankanın bir önceki dönemine göre 1/100'ün altındaysa rapor milyon TL
    sayılır: tüm değerler ×1000 (Akbank 2026Ç2 gibi)."""
    a = rep.metrics.get("toplam_aktif")
    if not a:
        return False
    with db.connect() as con:
        row = con.execute("SELECT value FROM metrics WHERE bank=? AND metric='toplam_aktif' AND period<? AND value>0 ORDER BY period DESC LIMIT 1", (rep.bank, rep.period)).fetchone()
    if not row or a / row[0] >= 0.01:
        return False
    k = 1000.0
    rep.metrics = {m: (None if v is None else v * k) for m, v in rep.metrics.items()}
    rep.prev_metrics = {m: (None if v is None else v * k) for m, v in (rep.prev_metrics or {}).items()}
    if rep.rows is not None and not rep.rows.empty:
        for c in ("tp", "yp", "total", "tp_prev", "yp_prev", "total_prev"):
            if c in rep.rows:
                rep.rows[c] = rep.rows[c] * k
    if rep.segments is not None and not rep.segments.empty:
        import pandas as pd
        say = [c for c in rep.segments.columns if c != "block" and pd.api.types.is_numeric_dtype(rep.segments[c])]
        mx = max((abs(rep.segments[c]).max() for c in say), default=0) or 0
        if mx and mx < rep.metrics["toplam_aktif"] / 100:   # bölüm tablosu parser tarafından zaten ölçeklenmediyse
            for c in say:
                rep.segments[c] = rep.segments[c] * k
    rep.notes.append("birim: milyon TL varsayıldı (önceki döneme oranla)")
    return True


def _kaydet(db, rep, no_prev=False):
    if _birim_duzelt(db, rep):
        pass
    """bootstrap.py ile aynı kayıt mantığı; fark: önceki yıl sütunu yalnız o dönem için hiç kayıt yoksa yazılır
    (uygulamadaki force=False eşit öncelikli 'pdf' kaydın üzerine yazıyordu; 2025+ raporlarda önceki yıl sütunu
    enflasyon muhasebesiyle yeniden ifade edilmiş olabilir, doğrudan rapor esastır)."""
    n = db.upsert_metrics(rep.bank, rep.period, rep.metrics, "pdf", force=True)
    db.save_fin_rows(rep.bank, rep.period, rep.rows)
    if not no_prev and rep.prev_period:
        with db.connect() as con:
            var = con.execute("SELECT 1 FROM metrics WHERE bank=? AND period=? LIMIT 1", (rep.bank, rep.prev_period)).fetchone()
        if not var:
            db.upsert_metrics(rep.bank, rep.prev_period, rep.prev_metrics, "pdf", force=False)
    segmsg = "bölüm yok"
    if not rep.segments.empty:
        nc = rep.segment_meta["ncols"]
        names = db.get_segment_names(rep.bank, nc) or [f"Bölüm {i+1}" for i in range(nc - 1)] + ["Toplam"]
        for blk, per in ((0, rep.period), (1, rep.prev_period)):
            t = rep.segments[rep.segments["block"] == blk].drop(columns=["block"])
            if t.empty or not per:
                continue
            if blk == 1 and not db.load_segments(rep.bank).query("period == @per").empty:
                continue
            db.save_segments(rep.bank, per, t, names, "pdf")
        segmsg = f"bölümler {nc} sütun ({'hatırlanan adlar' if db.get_segment_names(rep.bank, nc) else 'genel adlar'})"
    fails = [c[0] for c in rep.checks if not c[1]]
    db.log_upload(rep.file_name, rep.bank, rep.period, rep.basis, not fails, "; ".join(rep.notes))
    return n, segmsg, fails


def _tasi(p, hedef_klasor):
    hedef_klasor.mkdir(parents=True, exist_ok=True)
    hedef = hedef_klasor / p.name
    if hedef.exists():
        hedef = hedef_klasor / f"{p.stem}_{dt.datetime.now():%Y%m%d%H%M%S}{p.suffix}"
    shutil.move(str(p), str(hedef))


def yukle(klasor=None, isci=4, kuru=False, sessiz=False, kaynak=None):
    """Kutudaki PDF'leri yükler; özet sözlüğü döndürür (kaynak uygulama yoksa None).
    kaynak: PDF_YUKLE yerine taranacak kök klasör (ör. PDF_ISLENDI ile yeniden yükleme); bu durumda dosya taşınmaz."""
    sys.path.insert(0, str(HERE))
    import banka_kar_export as bk
    src = bk.kaynak_db()
    if src is None:
        return None
    app = src.parent.parent; proje = app.parent
    gelen, islendi = (Path(kaynak) if kaynak else proje / "PDF_YUKLE"), proje / "PDF_ISLENDI"
    tasi = not kaynak
    gelen.mkdir(exist_ok=True); islendi.mkdir(exist_ok=True)
    klasorler = sorted([d for d in gelen.iterdir() if d.is_dir() and not d.name.startswith("_") and d.name != "talep"] + [gelen], key=lambda d: (klasor_donem(d.name) or "9999", d.name))
    if klasor:
        klasorler = [d for d in klasorler if d.name == klasor]
    isler = [(kl, sorted(p for p in kl.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")) for kl in klasorler]
    isler = [(kl, pdfs) for kl, pdfs in isler if pdfs]
    if not isler:
        return {"ok": 0, "kons": 0, "atlandi": 0, "uyusmaz": 0, "kontrol": 0, "genel_ad": 0, "rapor": None}
    if str(app) not in sys.path:
        sys.path.insert(0, str(app))
    from core import db
    from concurrent.futures import ProcessPoolExecutor
    log = lambda s: (None if sessiz else print(s[:170], flush=True))
    rapor = [f"Yükleme raporu {dt.datetime.now():%d.%m.%Y %H:%M}"]
    T = {"ok": 0, "kons": 0, "atlandi": 0, "uyusmaz": 0, "kontrol": 0, "genel_ad": 0}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=isci) as ex:
        for kl, pdfs in isler:
            kd = klasor_donem(kl.name) if kl != gelen else None
            rapor.append(f"\n== {kl.name if kl != gelen else '(kök)'} — {len(pdfs)} PDF" + (f" · beklenen dönem {kd}" if kd else "")); log(rapor[-1])
            for path, rep, hata in ex.map(_parse, [(str(app), str(p)) for p in pdfs], chunksize=1):
                p = Path(path)
                if rep is None or not rep.bank or not rep.period or not rep.metrics:
                    T["atlandi"] += 1; rapor.append(f"  ATLANDI  {p.name}: " + (hata or f"banka={rep.bank if rep else '?'} dönem={rep.period if rep else '?'} notlar={(rep.notes[:2] if rep else [])}")); log(rapor[-1])
                    if not kuru and tasi: _tasi(p, islendi / "_okunamayan" / kl.name)
                    continue
                if rep.basis != "solo":
                    T["kons"] += 1; rapor.append(f"  KONSOLİDE {p.name}: {rep.bank} {rep.period} — yüklenmedi")
                    if not kuru and tasi: _tasi(p, islendi / "_konsolide" / kl.name)
                    continue
                if kd and rep.period != kd:
                    T["uyusmaz"] += 1; rapor.append(f"  UYUŞMAZ  {p.name}: PDF dönemi {rep.period} ≠ klasör {kd} ({rep.bank}) — yüklenmedi, elle bakın"); log(rapor[-1])
                    if not kuru and tasi: _tasi(p, islendi / "_donem_uyusmazligi" / kl.name)
                    continue
                if kuru:
                    T["ok"] += 1; rapor.append(f"  OK(kuru) {rep.bank:16} {rep.period} {len(rep.metrics)} metrik"); continue
                n, segmsg, fails = _kaydet(db, rep)
                T["ok"] += 1; T["kontrol"] += bool(fails); T["genel_ad"] += ("genel adlar" in segmsg)
                birim = "  BİRİM×1000" if any("milyon TL varsayıldı" in x for x in rep.notes) else ""
                rapor.append(f"  OK  {rep.bank:16} {rep.period} {n} metrik, {segmsg}{birim}" + (f"  KONTROL: {fails}" if fails else "") + f"  [{p.name}]"); log(rapor[-1])
                if tasi: _tasi(p, islendi / (kl.name if kl != gelen else "diger"))
    ozet = (f"\nTOPLAM: yüklenen {T['ok']} · konsolide (atlandı) {T['kons']} · okunamayan {T['atlandi']} · dönem uyuşmazlığı {T['uyusmaz']}"
            f" · tutarlılık uyarılı {T['kontrol']} · genel bölüm adlı {T['genel_ad']} · süre {(time.time() - t0) / 60:.1f} dk")
    rapor.append(ozet); log(ozet)
    rp = islendi / f"yukleme_raporu_{dt.datetime.now():%Y%m%d_%H%M}.txt"
    rp.write_text("\n".join(rapor), encoding="utf-8"); log("rapor: " + str(rp))
    T["rapor"] = str(rp)
    return T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--klasor", help="yalnız bu alt klasör (ör. 2026-2)")
    ap.add_argument("--isci", type=int, default=4); ap.add_argument("--kuru", action="store_true", help="kaydetme/taşıma yapma")
    ap.add_argument("--kaynak", help="PDF_YUKLE yerine taranacak kök klasör (dosyalar taşınmaz)")
    a = ap.parse_args()
    r = yukle(a.klasor, a.isci, a.kuru, kaynak=a.kaynak)
    if r is None:
        print("Kaynak uygulama (banka_dashboard) bulunamadı."); sys.exit(1)


if __name__ == "__main__":
    main()
