#!/usr/bin/env python3
"""Otomatik KAP kontrolü: yeni yayımlanan solo finansal raporları indirir, doğrular, veritabanına yükler ve siteyi yayımlar.

launchd rapor aylarında (Şubat, Mayıs, Ağustos, Kasım) her gün 09:00'da çalıştırır
(~/Library/LaunchAgents/com.ekordion.kap.plist → banka_kap_otomatik.sh → bu betik).

  python3 "banka kar/kap_otomatik.py"            # normal koşu
  python3 "banka kar/kap_otomatik.py" --kuru --dene TSKB 2026Q3   # sınama: indir + doğrula, kaydetme / yayımlama

Akış:
  1. Son iki tamamlanmış çeyrek için veritabanında eksik banka-dönemler bulunur (kap_cek.eksikler); okunamadığı bilinenler
     (kap_cek.OKUNAMAYAN) ve daha önce doğrulamadan geçemeyenler (kap/durum.json → "sorunlu") atlanır.
  2. KAP'ta solo raporu yayımlanmış olanların PDF'i indirilir (kap/_yeni/).
  3. Her rapor ayrıştırılır ve DOĞRULANIR; geçemezse veritabanına YAZILMAZ, PDF kap/_sorunlu/'ya alınır, "sorunlu" diye işaretlenir
     (her gün yeniden denenmez) ve bildirim gönderilir — elle bakılmalıdır. Doğrulama: banka ve dönem beklenenle aynı, solo,
     en az 30 metrik, temel tutarlılık kontrolleri (aktif = pasif, NFG, dönem kârı), nazım tablosu ve türev kalemleri okunmuş,
     toplam aktif önceki döneme göre makul (0,5–2,5 kat).
  4. Geçenler yüklenir (önce veritabanı yedeği), PDF kap/yuklenen/'e taşınır; site verisi üretilir, commit + push edilir.
     Yayın başarısız olursa kap/.yayin_bekliyor işareti kalır ve sonraki koşu yeniden dener.
Yeni rapor yoksa hiçbir şey değişmez. Eksik ya da şüpheli veriyle asla yayın yapılmaz.
"""
from __future__ import annotations
import argparse, datetime as dt, glob, json, os, shutil, sqlite3, subprocess, sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO))
import kap_cek

KRITIK = ("Aktif toplamı = Pasif toplamı", "NFG = Faiz Geliri − Faiz Gideri", "Bilanço dönem kârı = GT net kâr")
YAYIN_DOSYA = ["site/data/banka_kar.json", "site/data/banka_turev.json", "site/data/home.json", "site/data/banka-mdc-kirilimi.xlsx",
               "site/data/banka-ozet-tablo.xlsx", "site/sitemap.xml", "site/banka-kar.html", "site/banka-turev.html"]


def log(s):
    print(f"[{dt.datetime.now():%d.%m.%Y %H:%M:%S}] {s}", flush=True)


def bildir(metin):
    """macOS bildirimi (başarısız olursa sessizce geçilir)."""
    try:
        subprocess.run(["osascript", "-e", f'display notification "{metin.replace(chr(34), "")[:230]}" with title "Ekordion · KAP"'], timeout=15, capture_output=True)
    except Exception:
        pass


def son_ceyrekler(n=2):
    """Bugün itibarıyla tamamlanmış son n çeyrek (eskiden yeniye)."""
    b = dt.date.today(); y, q = b.year, (b.month - 1) // 3
    if q == 0:
        y, q = y - 1, 4
    out = []
    for _ in range(n):
        out.append(f"{y}Q{q}")
        y, q = (y, q - 1) if q > 1 else (y - 1, 4)
    return out[::-1]


def dogrula(rep, banka, donem, con, te):
    """Rapor veritabanına yazılabilir mi? Sorun yoksa None, varsa neden."""
    if rep is None:
        return "ayrıştırılamadı"
    if not rep.metrics or not rep.period:
        return "bilanço sayfaları bulunamadı"
    if rep.bank != banka or rep.period != donem:
        return f"beklenen {banka} {donem}, PDF'te {rep.bank} {rep.period}"
    if rep.basis != "solo":
        return "rapor konsolide"
    dolu = [k for k, v in rep.metrics.items() if v is not None and v == v]
    if len(dolu) < 30:
        return f"yalnız {len(dolu)} metrik okundu"
    kotu = [c[0] for c in (rep.checks or []) if not c[1] and c[0] in KRITIK]
    if kotu:
        return "tutarlılık kontrolü: " + ", ".join(kotu)
    obs = rep.rows[rep.rows["stmt"] == "OBS"] if rep.rows is not None and len(rep.rows) else []
    if len(obs) < 40:
        return "nazım hesaplar tablosu okunamadı"
    tup = [(r["code"], r["label"], r.get("tp"), r.get("yp"), r.get("total"), r.get("tp_prev"), r.get("yp_prev"), r.get("total_prev")) for _, r in obs.iterrows()]
    k, _ = te.kalemler(tup)
    if k is not None and any(v is None for v in k.values()):
        return "türev kalemleri doğrulanamadı"
    onceki = con.execute("SELECT value FROM metrics WHERE bank=? AND metric='toplam_aktif' AND period<? AND value>0 ORDER BY period DESC LIMIT 1", (banka, donem)).fetchone()
    a = rep.metrics.get("toplam_aktif")
    if onceki and a and not (0.5 <= a / onceki[0] <= 2.5):
        return f"toplam aktif önceki dönemin {a / onceki[0]:.2f} katı"
    return None


def git(*args, kontrol=False):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if kontrol and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()[:200]}")
    return r


def yayimla(mesaj):
    """Site verisini üretir, yalnız banka veri dosyalarını commit eder ve gönderir. Başarılıysa True."""
    import site_export as s
    s.build_banka_kar(); s.build_home(); s.build_sitemap(); s.ozet_gom()
    for f in ("site/data/banka_kar.json", "site/data/banka_turev.json"):     # bozuk paket yayımlanmasın
        json.loads((REPO / f).read_text(encoding="utf-8"))
    git("add", "--", *YAYIN_DOSYA, kontrol=True)
    if git("diff", "--cached", "--quiet").returncode == 0:
        log("Sitede değişen dosya yok — commit atlandı"); return True
    git("commit", "-q", "-m", mesaj, "--", *YAYIN_DOSYA, kontrol=True)
    for deneme in range(3):
        cek = git("pull", "--rebase", "--autostash", "-q", "origin", "main")
        if cek.returncode != 0:
            git("rebase", "--abort")
        if git("push", "-q", "origin", "main").returncode == 0:
            return True
        import time; time.sleep(20)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true", help="indir + doğrula; veritabanına yazma, yayımlama")
    ap.add_argument("--dene", nargs=2, metavar=("BANKA", "DONEM"), help="eksik olmasa da bu banka-dönemi indirip doğrula (sınama; --kuru ile)")
    a = ap.parse_args()
    db_yol = kap_cek.kaynak_db()
    if db_yol is None:
        log("banka.db bulunamadı — çıkılıyor"); return 1
    app = db_yol.parent.parent; kok = app.parent / "PDF_ISLENDI" / "kap"
    yeni, arsiv, sorunlu_kl = kok / "_yeni", kok / "yuklenen", kok / "_sorunlu"
    durum_yol, bekliyor = kok / "durum.json", kok / ".yayin_bekliyor"
    durum = json.loads(durum_yol.read_text(encoding="utf-8")) if durum_yol.exists() else {"sorunlu": {}}
    uye = json.loads(kap_cek.UYE_DOSYA.read_text(encoding="utf-8"))
    if a.dene:
        eks = {a.dene[0]: [a.dene[1]]}
        yeni = kok / "_deneme"
    else:
        donemler = son_ceyrekler(2)
        eks = kap_cek.eksikler(db_yol, list(uye), donemler[0], donemler[-1])
        eks = {b: [p for p in ps if f"{b}|{p}" not in durum["sorunlu"]] for b, ps in eks.items()}
        eks = {b: ps for b, ps in eks.items() if ps}
        log(f"Kontrol edilen dönemler: {' '.join(donemler)} · eksik: " + (", ".join(f"{b} {' '.join(ps)}" for b, ps in eks.items()) or "yok"))
    # ---- 1-2) KAP'ta yayımlanmış olanları indir
    inen = []   # (banka, dönem, [dosya yolları])
    for b, ps in eks.items():
        if b not in uye:
            continue
        try:
            bulunan = kap_cek.solo_raporlar(b, uye[b]["oid"], set(ps), gunluk=log)
        except Exception as e:
            log(f"UYARI: {b} KAP sorgusu başarısız ({e})"); continue
        for p, r in sorted(bulunan.items()):
            dosyalar = []
            for j, e in enumerate(r["ekler"]):
                hedef = yeni / (f"{b}_{p}_KAP{r['index']}" + (f"_{j + 1}" if len(r["ekler"]) > 1 else "") + ".pdf")
                try:
                    if hedef.exists() or kap_cek.pdf_indir(e["objId"], hedef):
                        dosyalar.append(hedef)
                except Exception as ex:
                    log(f"UYARI: {b} {p} indirilemedi ({ex})")
            if dosyalar:
                inen.append((b, p, dosyalar)); log(f"KAP'ta yeni rapor: {b} {p} ({len(dosyalar)} PDF, yayın {r['tarih']})")
    if not inen and not bekliyor.exists():
        log("Yeni rapor yok"); return 0
    # ---- 3-4) ayrıştır, doğrula, yükle
    import pdf_yukle, turev_export as te
    sys.path.insert(0, str(app))
    from core import db
    con = sqlite3.connect(db_yol)
    yuklenen, hatali, yedeklendi = [], [], False
    for b, p, dosyalar in inen:
        neden, secilen = "PDF okunamadı", None
        for yol in dosyalar:                      # birden çok ek varsa (TR + EN) doğrulamadan geçen ilki
            _, rep, hata = pdf_yukle._parse((str(app), str(yol)))
            if rep is not None and rep.metrics:
                pdf_yukle._birim_duzelt(db, rep)
            n = dogrula(rep, b, p, con, te) if rep is not None else (hata or "ayrıştırılamadı")
            if n is None:
                secilen, neden = (yol, rep), None; break
            neden = n
        if neden is None:
            if a.kuru:
                log(f"SINAMA: {b} {p} doğrulamadan geçti ({len(secilen[1].metrics)} metrik, toplam aktif {secilen[1].metrics.get('toplam_aktif'):,.0f} mn TL) — yazılmadı")
                continue
            if not yedeklendi:
                yedek = db_yol.parent / f"banka.db.yedek_oto_{dt.datetime.now():%Y%m%d_%H%M}"
                shutil.copy2(db_yol, yedek); yedeklendi = True
                for eski in sorted(glob.glob(str(db_yol.parent / "banka.db.yedek_oto_*")))[:-3]:
                    os.remove(eski)
            n_m, segmsg, _ = pdf_yukle._kaydet(db, secilen[1])
            arsiv.mkdir(parents=True, exist_ok=True)
            for yol in dosyalar:
                shutil.move(str(yol), str(arsiv / yol.name))
            yuklenen.append((b, p)); log(f"YÜKLENDİ: {b} {p} · {n_m} metrik · {segmsg}")
        else:
            hatali.append((b, p, neden)); log(f"SORUNLU: {b} {p} — {neden} (veritabanına yazılmadı)")
            if not a.kuru:
                sorunlu_kl.mkdir(parents=True, exist_ok=True)
                for yol in dosyalar:
                    shutil.move(str(yol), str(sorunlu_kl / yol.name))
                durum["sorunlu"][f"{b}|{p}"] = {"neden": neden, "tarih": dt.date.today().isoformat()}
                durum_yol.write_text(json.dumps(durum, ensure_ascii=False, indent=1), encoding="utf-8")
    con.close()
    if a.kuru:
        if a.dene:
            shutil.rmtree(yeni, ignore_errors=True)
        log("Sınama bitti (hiçbir şey yazılmadı)"); return 0
    ad = lambda b, p: f"{uye.get(b, {}).get('unvan', b).split(' A.Ş.')[0].split(' T.A.')[0].title()} {p[:4]} Ç{p[-1]}"
    if hatali:
        bildir("Okunamayan rapor (elle bakılmalı): " + ", ".join(f"{ad(b, p)}" for b, p, _ in hatali))
    if not yuklenen and not bekliyor.exists():
        log("Yüklenecek geçerli rapor yok"); return 0
    # ---- yayın
    bekliyor.write_text(dt.datetime.now().isoformat(), encoding="utf-8")
    liste = ", ".join(ad(b, p) for b, p in yuklenen) or "bekleyen yayın"
    try:
        tamam = yayimla(f"Banka verileri: KAP'tan yeni rapor — {liste} (otomatik, {dt.datetime.now():%d.%m.%Y %H:%M})")
    except Exception as e:
        tamam = False; log(f"UYARI: yayın adımı hata verdi ({type(e).__name__}: {str(e)[:160]})")
    if tamam:
        bekliyor.unlink(missing_ok=True)
        log(f"YAYIMLANDI: {liste}"); bildir(f"Yeni rapor yüklendi ve site güncellendi: {liste}")
    else:
        log("UYARI: yayın başarısız — sonraki koşuda yeniden denenecek"); bildir(f"Rapor yüklendi ama site yayını başarısız (sonraki koşuda denenecek): {liste}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
