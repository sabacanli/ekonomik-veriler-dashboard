#!/usr/bin/env python3
"""KAP'tan (Kamuyu Aydınlatma Platformu, kap.org.tr) eksik SOLO finansal rapor PDF'lerini indirir.

Bankaların "Finansal Rapor" bildirimlerinin ekindeki bağımsız denetim raporu PDF'i, PDF_YUKLE kutusuna elle bırakılan
dosyayla aynıdır; indirilenler `pdf_yukle.py --kaynak <klasör>` ile veritabanına yüklenir.

  python3 "banka kar/kap_cek.py" --uyeler                 # bankaların KAP üye kimliklerini bulur → kap_uyeler.json
  python3 "banka kar/kap_cek.py" --liste                  # veritabanında eksik olup KAP'ta bulunan dönemleri listeler
  python3 "banka kar/kap_cek.py" --indir [--banka Anadolubank Odeabank] [--bas 2022Q1] [--son 2026Q3] [--en-cok 40]

"Eksik" = o banka-dönem için veritabanında bilanço satırı (PDF hiç yüklenmemiş) ya da nazım hesap satırı yok.
KAP uçları (site, Next.js uygulamasının kullandığı JSON servisleri):
  POST /tr/api/search/combined {keyword}                       → üye kimliği (mkkMemberOid)
  POST /tr/api/disclosure/members/byCriteria {...}             → bildirim listesi (disclosureClass "FR")
  GET  /tr/api/notification/attachment-detail/<bildirim no>    → ftNiteligi (NC = konsolide olmayan, CS = konsolide) + ekler
  GET  /tr/api/file/download/<objId>                           → ek dosya; Java serileştirilmiş byte[] olarak gelir (27 baytlık başlık atılır)
İstekler sıralı ve aralıklıdır (siteyi yormamak için); anahtar ya da oturum gerekmez.
"""
from __future__ import annotations
import argparse, datetime as dt, glob, json, os, re, sqlite3, sys, time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
KOK = "https://www.kap.org.tr/tr/api"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
UYE_DOSYA = HERE / "kap_uyeler.json"
BEKLE = 2.0          # istekler arası bekleme (sn) — sık istekte KAP HTTP 429 (hız sınırı) döndürüyor
# kanonik banka adı → (arama sözcüğü, KAP unvanında aranan desen — sadeleştirilmiş küçük harf)
ARAMA = {
    "Ziraat": ("ziraat bankası", r"^t ?c ?ziraat bankasi"), "VakıfBank": ("vakıflar bankası", r"^turkiye vakiflar bankasi"),
    "Halkbank": ("halk bankası", r"^turkiye halk bankasi"), "İşbankası": ("iş bankası", r"^turkiye is bankasi"),
    "Akbank": ("akbank", r"^akbank"), "YapıKredi": ("yapı ve kredi", r"^yapi ve kredi bankasi"),
    "Garanti Bankası": ("garanti bankası", r"^turkiye garanti bankasi"), "QNB": ("qnb", r"^qnb (finansbank|bank)"),
    "DenizBank": ("denizbank", r"^denizbank"), "TEB": ("türk ekonomi bankası", r"^turk ekonomi bankasi"),
    "BurganBank": ("burgan bank", r"^burgan bank"), "Odeabank": ("odea bank", r"^odea ?bank"), "Fibabank": ("fibabanka", r"^fibabanka"),
    "ING": ("ING BANK", r"^ing bank"), "HSBC": ("hsbc", r"^hsbc bank"), "ICBC": ("ICBC", r"^icbc turkey bank"),   # arama büyük/küçük I'ya duyarlı
    "Alternatifbank": ("alternatifbank", r"^alternatif ?bank"), "Şekerbank": ("şekerbank", r"^sekerbank"),
    "Anadolubank": ("anadolubank", r"^anadolubank"), "TSKB": ("sınai kalkınma", r"^turkiye sinai kalkinma bankasi"),
    "Aktifbank": ("aktif yatırım", r"^aktif yatirim bankasi"), "Nurolbank": ("nurol yatırım", r"^nurol yatirim bankasi"),
    "Misyonbank": ("misyon yatırım", r"^misyon yatirim bankasi"), "DYatirim": ("d yatırım", r"^d yatirim bankasi"),
    "ZiraatKatilim": ("ziraat katılım", r"^ziraat katilim bankasi"), "Albaraka": ("albaraka", r"^albaraka turk"),
    "ZiraatDinamik": ("ziraat dinamik", r"^ziraat dinamik"),
}
CEYREK = {"3 Aylık": 1, "6 Aylık": 2, "9 Aylık": 3, "Yıllık": 4}


def _sade(s):
    s = (s or "").replace("İ", "i").replace("I", "ı").lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("ç", "c"), ("â", "a")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def pkey(p):
    return (int(p[:4]), int(p[-1]))


def istek(yol, veri=None, ham=False, deneme=4, zaman=180):
    """KAP JSON servisine istek; ham=True ise bayt döner. Geçici hatalarda aralıklı yeniden dener."""
    url = f"{KOK}/{yol}"
    bas = {"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Referer": "https://www.kap.org.tr/tr/bildirim-sorgu", "Origin": "https://www.kap.org.tr"}
    for i in range(deneme):
        try:
            r = requests.post(url, json=veri, headers=bas, timeout=zaman) if veri is not None else requests.get(url, headers=bas, timeout=zaman)
            if r.status_code == 200:
                time.sleep(BEKLE)
                return r.content if ham else r.json()
            hata = f"HTTP {r.status_code}"
            if r.status_code == 429:       # hız sınırı: uzun bekle
                time.sleep(45 * (i + 1)); continue
        except Exception as e:
            hata = f"{type(e).__name__}: {str(e)[:80]}"
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"KAP isteği başarısız ({yol}): {hata}")


def uyeleri_bul(bankalar=None):
    """ARAMA'daki bankaların KAP üye kimliklerini arama servisinden bulur ve kap_uyeler.json'a yazar."""
    kayit = json.loads(UYE_DOSYA.read_text(encoding="utf-8")) if UYE_DOSYA.exists() else {}
    for b, (soz, desen) in ARAMA.items():
        if bankalar and b not in bankalar:
            continue
        if b in kayit:
            continue
        try:
            sonuc = istek("search/combined", {"keyword": soz})
        except Exception as e:
            print(f"  ~ {b}: arama hatası ({e})"); continue
        aday = [x for g in sonuc if g.get("category") == "companyOrFunds" for x in g.get("results", []) if x.get("searchType") == "C"]
        uyan = [x for x in aday if re.search(desen, _sade(x["searchValue"]))]
        if len(uyan) == 1:
            kayit[b] = {"oid": uyan[0]["memberOrFundOid"], "unvan": uyan[0]["searchValue"], "kod": uyan[0].get("cmpOrFundCode")}
            print(f"  {b:16s} → {uyan[0]['searchValue']} ({uyan[0].get('cmpOrFundCode')})")
        else:
            print(f"  ! {b}: {len(uyan)} eşleşme — adaylar: {[x['searchValue'] for x in aday][:6]}")
    UYE_DOSYA.write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
    return kayit


def bildirimler(oid, bas_tarih, son_tarih, uye_turu=""):
    """Üyenin finansal rapor sınıfındaki bildirimleri (yıl yıl sorgulanır). uye_turu: "" = tür ayırmadan; "IGS" işlem görenler, "DDK" diğer üyeler."""
    out, y0, y1 = [], int(bas_tarih[:4]), int(son_tarih[:4])
    for y in range(y0, y1 + 1):
        fd, td = max(bas_tarih, f"{y}-01-01"), min(son_tarih, f"{y}-12-31")
        govde = {"fromDate": fd, "toDate": td, "memberType": uye_turu, "mkkMemberOidList": [oid], "inactiveMkkMemberOidList": [], "disclosureClass": "FR",
                 "subjectList": [], "isLate": "", "mainSector": "", "sector": "", "subSector": "", "marketOid": "", "index": "", "bdkReview": "",
                 "bdkMemberOidList": [], "year": "", "term": "", "ruleType": "", "period": "", "fromSrc": False, "srcCategory": "", "discIndex": []}
        out += istek("disclosure/members/byCriteria", govde) or []
    return out


def kaynak_db():
    env = os.environ.get("BANKA_DB", "").strip()
    if env and Path(env).exists():
        return Path(env)
    aday = [Path(p) for p in glob.glob(str(Path.home() / "cowork" / "*" / "banka_dashboard" / "data" / "banka.db"))]
    return max(aday, key=lambda p: p.stat().st_mtime) if aday else None


def eksikler(db, bankalar, bas, son):
    """{banka: [dönem]} — bilanço ya da nazım satırı olmayan banka-dönemler (bas..son aralığında)."""
    con = sqlite3.connect(db)
    bs = set(con.execute("SELECT DISTINCT bank, period FROM fin_rows WHERE stmt='BS'"))
    obs = set(con.execute("SELECT DISTINCT bank, period FROM fin_rows WHERE stmt='OBS'"))
    donemler = [f"{y}Q{q}" for y in range(int(bas[:4]), int(son[:4]) + 1) for q in range(1, 5)]
    donemler = [p for p in donemler if pkey(bas) <= pkey(p) <= pkey(son)]
    return {b: [p for p in donemler if (b, p) not in bs or (b, p) not in obs] for b in bankalar}


def solo_raporlar(b, oid, istenen, gunluk=print, detay=True):
    """İstenen dönemler için KAP'taki solo finansal rapor bildirimi: {dönem: {index, tarih, ekler}}.
    detay=False: bildirim ayrıntısı çekilmez (yalnız o dönemde finansal rapor bildirimi var mı: {dönem: {"aday": n}})."""
    if not istenen:
        return {}
    ilk = min(istenen, key=pkey)
    bas_tarih = f"{ilk[:4]}-01-01"
    liste = bildirimler(oid, bas_tarih, dt.date.today().isoformat())
    zaman = lambda x: dt.datetime.strptime(x["publishDate"], "%d.%m.%Y %H:%M:%S")
    aday, solo_beyan = {}, {}
    for d in liste:
        if d.get("ruleType") not in CEYREK or not d.get("year"):
            continue
        p = f"{d['year']}Q{CEYREK[d['ruleType']]}"
        konu = _sade(d.get("subject"))
        if konu == "finansal rapor" and p in istenen:
            aday.setdefault(p, []).append(d)
        elif konu.startswith("sorumluluk beyani") and "konsolide olmayan" in konu:
            solo_beyan.setdefault(p, []).append(zaman(d))
    if not detay:
        return {p: {"aday": len(v)} for p, v in aday.items()}
    out = {}
    for p in sorted(aday, key=pkey):
        # Bildirim ayrıntısı ~1 MB (tabloların tamamı) → önce solo olması en olası aday denenir: "Sorumluluk Beyanı (Konsolide
        # Olmayan)" bildirimine zamanca en yakın finansal rapor; eşitlikte / beyan yoksa en yeni yayın (düzeltme varsa o alınır)
        yakin = lambda x: min((abs((zaman(x) - t).total_seconds()) for t in solo_beyan.get(p, [])), default=9e9)
        for d in sorted(aday[p], key=lambda x: (yakin(x) > 1800, -zaman(x).timestamp())):
            try:
                det = istek(f"notification/attachment-detail/{d['disclosureIndex']}")[0]
            except Exception as e:
                gunluk(f"  ~ {b} {p}: bildirim {d['disclosureIndex']} okunamadı ({e})"); continue
            if (det["disclosure"]["disclosureDetail"] or {}).get("ftNiteligi") != "NC":
                continue
            pdfler = [a for a in det.get("attachments") or [] if (a.get("fileExtension") or "").lower() == "pdf"]
            if not pdfler:
                gunluk(f"  ~ {b} {p}: solo bildirimde ({d['disclosureIndex']}) PDF eki yok"); continue
            out[p] = {"index": d["disclosureIndex"], "tarih": d["publishDate"], "ekler": pdfler}
            break
    return out


def pdf_indir(obj_id, hedef):
    """Ek dosyayı indirir; Java serileştirme başlığını atar. PDF değilse False."""
    ham = istek(f"file/download/{obj_id}", ham=True)
    i = ham.find(b"%PDF")
    if i < 0 or i > 64:
        return False
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_bytes(ham[i:])
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uyeler", action="store_true"); ap.add_argument("--liste", action="store_true"); ap.add_argument("--indir", action="store_true")
    ap.add_argument("--banka", nargs="*"); ap.add_argument("--bas", default="2022Q1"); ap.add_argument("--son")
    ap.add_argument("--en-cok", type=int, default=400, help="bu çalıştırmada indirilecek en çok dosya")
    ap.add_argument("--hedef", help="indirme klasörü (varsayılan: <uygulama kökü>/PDF_ISLENDI/kap/_yeni)")
    ap.add_argument("--donemler", nargs="*", help="eksik olup olmadığına bakmadan bu dönemleri indir (yeniden ayrıştırma için; --banka ile)")
    a = ap.parse_args()
    uye = uyeleri_bul(a.banka) if (a.uyeler or not UYE_DOSYA.exists()) else json.loads(UYE_DOSYA.read_text(encoding="utf-8"))
    if a.uyeler and not (a.liste or a.indir):
        return 0
    db = kaynak_db()
    if db is None:
        print("banka.db bulunamadı"); return 1
    bugun = dt.date.today(); q = (bugun.month - 1) // 3          # yıl içinde tamamlanan çeyrek sayısı
    son = a.son or (f"{bugun.year}Q{q}" if q else f"{bugun.year - 1}Q4")
    bankalar = [b for b in (a.banka or list(uye)) if b in uye]
    eks = {b: list(a.donemler) for b in bankalar} if a.donemler else eksikler(db, bankalar, a.bas, son)
    kok = Path(a.hedef) if a.hedef else db.parent.parent.parent / "PDF_ISLENDI" / "kap" / "_yeni"
    indeks_yol = kok.parent / "indeks.json" if not a.hedef else kok / "indeks.json"
    indeks = json.loads(indeks_yol.read_text(encoding="utf-8")) if indeks_yol.exists() else {}
    n_indir = n_var = 0
    for b in bankalar:
        if not eks[b]:
            continue
        try:
            bulunan = solo_raporlar(b, uye[b]["oid"], set(eks[b]), detay=a.indir)
        except Exception as e:
            print(f"  ~ {b}: KAP sorgusu başarısız ({e})"); continue
        yok = [p for p in eks[b] if p not in bulunan]
        print(f"{b:16s} eksik {len(eks[b]):2d} · KAP'ta {len(bulunan):2d}" + (f" · KAP'ta yok: {' '.join(yok)}" if yok else "") + (f" · var: {' '.join(sorted(bulunan, key=pkey))}" if not a.indir else ""))
        if not a.indir:
            continue
        for p in sorted(bulunan, key=pkey):
            anahtar = f"{b}|{p}"
            if anahtar in indeks and all((kok / d).exists() for d in indeks[anahtar].get("dosya", [])):
                n_var += 1; continue
            if n_indir >= a.en_cok:
                break
            r = bulunan[p]
            # birden çok PDF varsa İngilizce sürüm elenir; kalanların hepsi indirilir (yükleyici solo olanı seçer)
            ekler = [e for e in r["ekler"] if not re.search(r"\b(eng|english|ing|ingilizce)\b", _sade(e.get("fileName")))] or r["ekler"]
            dosyalar = []
            for j, e in enumerate(ekler):
                ad = f"{b}_{p}_KAP{r['index']}" + (f"_{j + 1}" if len(ekler) > 1 else "") + ".pdf"
                try:
                    if pdf_indir(e["objId"], kok / ad):
                        dosyalar.append(ad)
                except Exception as ex:
                    print(f"  ~ {b} {p}: indirilemedi ({ex})")
            if dosyalar:
                indeks[anahtar] = {"index": r["index"], "tarih": r["tarih"], "dosya": dosyalar, "ek": [e.get("fileName") for e in ekler]}
                indeks_yol.parent.mkdir(parents=True, exist_ok=True)
                indeks_yol.write_text(json.dumps(indeks, ensure_ascii=False, indent=1), encoding="utf-8")
                n_indir += 1
                print(f"  ↓ {b} {p}: {', '.join(dosyalar)} ({sum((kok / d).stat().st_size for d in dosyalar) / 1e6:.1f} MB)")
    if a.indir:
        print(f"indirilen {n_indir} banka-dönem · önceden indirilmiş {n_var} · klasör {kok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
