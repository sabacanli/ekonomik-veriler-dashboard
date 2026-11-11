#!/usr/bin/env python3
"""Banka Kârlılık Analizi — site/data/banka_kar.json üretir.

Kaynak: yerel "Banka Analiz Dashboard'u" (Streamlit) uygulamasının SQLite veritabanı (banka.db): bankaların
solo (konsolide olmayan) BDDK formatlı finansal tablolarından okunan metrikler, faaliyet bölümleri ve MDC faiz tipi.
Veri bakımı (PDF yükleme, manuel giriş) yerel uygulamada yapılır; bu betik yalnız sonuçları siteye aktarır.

  BANKA_DB=/yol/banka.db  → kaynak veritabanı (varsayılan: ~/cowork/*/banka_dashboard/data/banka.db içinde en yenisi)
  PDF kutusu: proje klasöründeki PDF_YUKLE/ içine bırakılan solo finansal tablo PDF'leri her çalıştırmada uygulamanın
  bootstrap.py'si ile veritabanına işlenir; okunanlar PDF_ISLENDI/ klasörüne taşınır, okunamayanlar PDF_YUKLE'de kalır.
  Kaynak bulunursa 'banka kar/banka.db' kopyası tazelenir (git'e girmez); bulunamazsa kopya kullanılır;
  o da yoksa hiçbir şey yazılmaz (sitedeki JSON korunur) — bulut iş akışında durum budur.

Hesaplar uygulamanın core/metrics.py tanımlarıyla birebir: rasyolar YTD akımla yıllıklandırılır (×4/çeyrek);
'çeyreklik' görünümde Qn = YTD(Qn) − YTD(Qn−1) ve rasyolar yıllıklandırılmaz.
"""
from __future__ import annotations
import datetime as dt, glob, json, os, re, shutil, sqlite3, sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
LOCAL_DB = HERE / "banka.db"
OUT = BASE / "site" / "data" / "banka_kar.json"

# ---- uygulamadaki tanımlar (core/metrics.py, core/banks.py) ----
METRICS = [
    ("faiz_geliri", "Faiz Geliri", "IS"), ("krediden_faiz", "Krediden Faiz", "IS"), ("mdc_faiz", "MDC Faiz", "IS"),
    ("faiz_gideri", "Faiz Gideri", "IS"), ("mevduata_faiz", "Mevduata Faiz", "IS"), ("net_faiz", "Net Faiz Geliri", "IS"),
    ("net_ucret", "Net Ücret/Komisyon", "IS"), ("temettu", "Temettü Geliri", "IS"), ("ticari_kz", "Ticari K/Z", "IS"),
    ("diger_gelir", "Diğer Faaliyet Gelirleri", "IS"), ("karsilik", "Beklenen Zarar Karşılığı", "IS"),
    ("personel", "Personel Gideri", "IS"), ("diger_gider", "Diğer Faaliyet Giderleri", "IS"),
    ("vergi_oncesi", "Vergi Öncesi Kâr", "IS"), ("vergi", "Vergi Karşılığı", "IS"), ("net_kar", "Net Kâr", "IS"),
    ("kapsamli_gelir", "Toplam Kapsamlı Gelir", "IS"),
    ("toplam_aktif", "Toplam Aktif", "BS"), ("kredi_tl", "Kredi TL", "BS"), ("kredi_yp", "Kredi YP", "BS"), ("kredi", "Kredi Toplam", "BS"),
    ("mevduat_tl", "Mevduat TL", "BS"), ("mevduat_yp", "Mevduat YP", "BS"), ("mevduat", "Mevduat Toplam", "BS"),
    ("mdc_tl", "MDC TL", "BS"), ("mdc_yp", "MDC YP", "BS"), ("mdc", "MDC Toplam", "BS"), ("ozkaynak", "Özkaynak", "BS"),
    ("alinan_kredi", "Alınan Krediler", "BS"), ("ihrac_mk", "İhraç Edilen MK", "BS"), ("nakit", "Nakit ve Benzerleri", "BS"),
]
FLOW = {k for k, _, s in METRICS if s == "IS"}
RATIOS = [
    ("roe", "ROE (Net Kâr / Özkaynak)", "ROE", "pct", "high"), ("roa", "ROA (Net Kâr / Toplam Aktif)", "ROA", "pct", "high"),
    ("nim", "NFG / Toplam Aktif", "NFG/Aktif", "pct", "high"), ("nfg_fg", "NFG / Faiz Geliri", "NFG/Faiz Gel.", "pct", "high"),
    ("kredi_mevduat", "Kredi / Mevduat", "Kredi/Mevd.", "pct", None), ("yp_kredi", "YP Kredi Payı", "YP Kredi %", "pct", None),
    ("yp_mevduat", "YP Mevduat Payı", "YP Mevd. %", "pct", None), ("mevduat_aktif", "Mevduat / Aktif", "Mevd./Aktif", "pct", None),
    ("kredi_aktif", "Kredi / Aktif", "Kredi/Aktif", "pct", None), ("mdc_aktif", "MDC / Aktif", "MDC/Aktif", "pct", None),
    ("ucret_opgelir", "Komisyon / Op. Gelir", "Kom./Op.Gel.", "pct", "high"), ("per_opgelir", "Personel Gid. / Op. Gelir", "Pers./Op.Gel.", "pct", "low"),
    ("maliyet_gelir", "Maliyet / Gelir (Per.+Diğer Gid.)", "Maliyet/Gelir", "pct", "low"), ("kaldirac", "Kaldıraç (Aktif / Özkaynak)", "Kaldıraç", "x", None),
    ("op_gelir", "Op. Gelir (NFG+Kom.+Ticari)", "Op. Gelir", "mn", "high"),
]
BANKS = {  # kanonik ad: (kısa ad, grup)
    "Ziraat": ("Ziraat", "Kamu"), "VakıfBank": ("Vakıf", "Kamu"), "Halkbank": ("Halk", "Kamu"),
    "İşbankası": ("İş", "Özel"), "Akbank": ("Akbank", "Özel"), "YapıKredi": ("YKB", "Özel"),
    "Garanti Bankası": ("Garanti", "Yabancı"), "QNB": ("QNB", "Yabancı"), "DenizBank": ("Deniz", "Yabancı"), "TEB": ("TEB", "Özel"),
    "BurganBank": ("Burgan", "Yabancı"), "Odeabank": ("Odea", "Yabancı"), "Fibabank": ("Fiba", "Özel"), "ING": ("ING", "Yabancı"),
    "HSBC": ("HSBC", "Yabancı"), "ICBC": ("ICBC", "Yabancı"), "Alternatifbank": ("ABank", "Yabancı"),
    "Şekerbank": ("Şeker", "Özel"), "Anadolubank": ("Anadolu", "Özel"),
    "TSKB": ("TSKB", "Kalkınma/Yatırım"), "Aktifbank": ("Aktif", "Kalkınma/Yatırım"), "TKYB": ("TKYB", "Kalkınma/Yatırım"),
    "Nurolbank": ("Nurol", "Kalkınma/Yatırım"), "Misyonbank": ("Misyon", "Kalkınma/Yatırım"), "DYatirim": ("D Yatırım", "Kalkınma/Yatırım"),
    "ZiraatKatilim": ("Z.Katılım", "Katılım"), "Albaraka": ("Albaraka", "Katılım"), "ZiraatDinamik": ("Z.Dinamik", "Kamu"),
}
BIG7 = ["Ziraat", "VakıfBank", "Halkbank", "İşbankası", "Akbank", "YapıKredi", "Garanti Bankası"]
TAM_AD = {  # özet tablo / Excel için unvanlar (kullanıcının "Sektör Sonuçları" tablosundaki gibi)
    "Ziraat": "Türkiye Cumhuriyeti Ziraat Bankası A.Ş.", "VakıfBank": "Türkiye Vakıflar Bankası T.A.O.", "Halkbank": "Türkiye Halk Bankası A.Ş.",
    "İşbankası": "Türkiye İş Bankası A.Ş.", "Akbank": "Akbank T.A.Ş.", "YapıKredi": "Yapı ve Kredi Bankası A.Ş.", "Garanti Bankası": "Türkiye Garanti Bankası A.Ş.",
    "QNB": "QNB Bank A.Ş.", "DenizBank": "Denizbank A.Ş.", "TEB": "Türk Ekonomi Bankası A.Ş.", "BurganBank": "Burgan Bank A.Ş.", "Odeabank": "Odea Bank A.Ş.",
    "Fibabank": "Fibabanka A.Ş.", "ING": "ING Bank A.Ş.", "HSBC": "HSBC Bank A.Ş.", "ICBC": "ICBC Turkey Bank A.Ş.", "Alternatifbank": "Alternatifbank A.Ş.",
    "Şekerbank": "Şekerbank T.A.Ş.", "Anadolubank": "Anadolubank A.Ş.", "TSKB": "Türkiye Sınai Kalkınma Bankası A.Ş.", "Aktifbank": "Aktif Yatırım Bankası A.Ş.",
    "TKYB": "Türkiye Kalkınma ve Yatırım Bankası A.Ş.", "Nurolbank": "Nurol Yatırım Bankası A.Ş.", "Misyonbank": "Misyon Yatırım Bankası A.Ş.", "DYatirim": "D Yatırım Bankası A.Ş.",
    "ZiraatKatilim": "Ziraat Katılım Bankası A.Ş.", "Albaraka": "Albaraka Türk Katılım Bankası A.Ş.", "ZiraatDinamik": "Ziraat Dinamik Banka A.Ş.",
}
DONEM_SONU = {"1": "31.03", "2": "30.06", "3": "30.09", "4": "31.12"}
SEGMENT_CATEGORIES = [
    ("Hazine / Yatırım", ["hazine", "aktif pasif", "yatırım bankacılığı", "sermaye piyasa"]),
    ("Bireysel / Perakende", ["bireysel", "perakende", "özel bankacılık", "dijital"]),
    ("Kurumsal / Ticari / KOBİ", ["kurumsal", "ticari", "kobi", "toptan", "tarım"]),
    ("Toplam", ["toplam", "banka'nın", "bankanın", "banka toplamı"]),
    ("Diğer / Dağıtılamayan", ["diğer", "dağıtılamayan", "genel müdürlük", "merkez"]),
]
SEG_ITEM_PRIORITY = {
    "net_kar": [r"^donem net kar", r"^net donem kar", r"^vergi sonrasi kar", r"^net kar", r"net kari?/zarar", r"surdurulen faaliyetler net"],
    "vergi_oncesi": [r"^vergi oncesi", r"^net faaliyet kar"], "vergi": [r"^vergi gideri", r"^vergi karsiligi", r"^vergi$", r"^vergi karsilig"],
    "varlik": [r"^bolum varliklari", r"^bolum aktif"],
    "nfg": [r"^net faiz"], "komisyon": [r"^net ucret"], "ticari": [r"^ticari"],
    "diger_gelir": [r"^diger faaliyet gelir", r"^diger gelir"],
}
BUCKETS = ["TRY Sabit", "TRY TÜFE", "TRY TLREF/Değişken", "YP Sabit", "YP Değişken"]


def _n(s):
    s = str(s).lower()
    for a, b in (("â", "a"), ("î", "i"), ("û", "u"), ("ı", "i"), ("i̇", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("ç", "c")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def segment_category(name):
    low = str(name).lower().replace("\n", " ")
    for cat, keys in SEGMENT_CATEGORIES:
        if any(k in low for k in keys):
            return cat
    return "Diğer / Dağıtılamayan"


def kaynak_db():
    """Kaynak veritabanı: BANKA_DB → ~/cowork/*/banka_dashboard/data/banka.db (en yeni)."""
    env = os.environ.get("BANKA_DB", "").strip()
    if env and Path(env).exists():
        return Path(env)
    adaylar = glob.glob(str(Path.home() / "cowork" / "*" / "banka_dashboard" / "data" / "banka.db"))
    adaylar = [Path(p) for p in adaylar if Path(p).exists()]
    return max(adaylar, key=lambda p: p.stat().st_mtime) if adaylar else None


def pdf_isle():
    """PDF_YUKLE/ kutusundaki solo rapor PDF'lerini (alt klasörler dahil) pdf_yukle.yukle() ile veritabanına işler."""
    if kaynak_db() is None:
        return
    sys.path.insert(0, str(HERE))
    import pdf_yukle
    r = pdf_yukle.yukle(isci=4)
    if r and (r["ok"] or r["atlandi"] or r["kons"] or r["uyusmaz"]):
        print(f"  PDF kutusu: yüklenen {r['ok']} · konsolide ayrıldı {r['kons']} · okunamayan {r['atlandi']} · dönem uyuşmazlığı {r['uyusmaz']}" + (f" · rapor {r['rapor']}" if r.get('rapor') else ""))


def sync_db():
    src = kaynak_db()
    if src and src.resolve() != LOCAL_DB.resolve():
        if not LOCAL_DB.exists() or src.stat().st_mtime > LOCAL_DB.stat().st_mtime or src.stat().st_size != LOCAL_DB.stat().st_size:
            shutil.copy2(src, LOCAL_DB)
            print(f"  banka.db kopyalandı ← {src}")
    return LOCAL_DB if LOCAL_DB.exists() else None


def r1(v, d=1):
    return None if v is None else round(float(v), d)


def period_key(p):
    return (int(p[:4]), int(p[-1]))


def safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def ratios(row, ann):
    """core/metrics.add_ratios ile aynı tanımlar; ann = 4/çeyrek (YTD) ya da 1 (çeyreklik)."""
    g = row.get
    nf, nu, tk = g("net_faiz"), g("net_ucret"), g("ticari_kz")
    op = None if (nf is None and nu is None and tk is None) else (nf or 0) + (nu or 0) + (tk or 0)
    out = {"op_gelir": op}
    nk, oz, ta = g("net_kar"), g("ozkaynak"), g("toplam_aktif")
    out["roe"] = safe_div(None if nk is None else nk * ann, oz)
    out["roa"] = safe_div(None if nk is None else nk * ann, ta)
    out["nim"] = safe_div(None if nf is None else nf * ann, ta)
    out["nfg_fg"] = safe_div(nf, g("faiz_geliri"))
    out["kredi_mevduat"] = safe_div(g("kredi"), g("mevduat"))
    out["yp_kredi"] = safe_div(g("kredi_yp"), g("kredi"))
    out["yp_mevduat"] = safe_div(g("mevduat_yp"), g("mevduat"))
    out["mevduat_aktif"] = safe_div(g("mevduat"), ta)
    out["kredi_aktif"] = safe_div(g("kredi"), ta)
    out["mdc_aktif"] = safe_div(g("mdc"), ta)
    out["ucret_opgelir"] = safe_div(nu, op)
    out["per_opgelir"] = safe_div(g("personel"), op)
    per = g("personel")
    out["maliyet_gelir"] = None if per is None or op is None else safe_div(per + (g("diger_gider") or 0), op + (g("diger_gelir") or 0))
    out["kaldirac"] = safe_div(ta, oz)
    return out


def seg_item(items, kind):
    """Bölüm tablosundaki kalem adlarından (sıralı liste) tür için eşleşen kalemi seçer (net kâr: son, diğerleri: ilk)."""
    norm = [(it, _n(it)) for it in items]
    for rx in SEG_ITEM_PRIORITY.get(kind, []):
        hits = [it for it, n in norm if re.search(rx, n)]
        if hits:
            return hits[-1] if kind == "net_kar" else hits[0]
    return None


# ---- Menkul değerler cüzdanı kırılımı: BDDK bilançosundaki sınıflandırma satırları ETİKETLE bulunur (kod numarası bankadan
# bankaya kayar: Garanti'de itfa satırı 2.3, Akbank'ta 2.4); DİBS = satırın "Devlet Borçlanma Senetleri" alt satırı, DİĞER = kalan.
MDC_SINIF = {"asa": r"^gercege uygun deger farki kar ?/? ?zarara yansitilan finansal( varliklar)?$",
             "sh": r"^gercege uygun deger farki diger kapsamli gelire yansitilan finansal( varliklar)?$",
             "vket": r"^itfa edilmis maliyeti ile olculen (diger )?finansal varliklar$"}


def mdc_kirilim(con):
    """{period: {bank: {dibs/diger/toplam: {asa/sh/vket: [tp, yp]}, total}}} (mn TL); PDF'in önceki yıl sütunu da kullanılır."""
    rows = con.execute("SELECT bank, period, code, label, tp, yp, total, tp_prev, yp_prev, total_prev FROM fin_rows "
                       "WHERE stmt='BS' AND section='A' AND code IS NOT NULL ORDER BY bank, period, ord").fetchall()
    grup = {}
    for r in rows:
        grup.setdefault((r[0], r[1]), []).append(r)
    by = {}   # (bank, period) -> {sinif: {"ana": (tp, yp, tot), "dibs": (tp, yp, tot)}}
    for (b, p), lst in grup.items():
        y, q = period_key(p); pp = f"{y-1}Q{q}"
        cur, prv = {}, {}
        for sinif, rx in MDC_SINIF.items():
            ana = next((r for r in lst if re.search(rx, _n(r[3]))), None)
            if ana is None:
                continue
            kod = str(ana[2])
            dibs = next((r for r in lst if str(r[2]).startswith(kod + ".") and re.search(r"^devlet borclanma", _n(r[3]))), None)
            cur[sinif] = {"ana": ana[4:7], "dibs": dibs[4:7] if dibs else None}
            prv[sinif] = {"ana": ana[7:10], "dibs": dibs[7:10] if dibs else None}
        if cur:
            by[(b, p)] = cur
        if prv and any(v["ana"][0] is not None or v["ana"][1] is not None for v in prv.values()):
            by.setdefault((b, pp), prv)   # doğrudan PDF yoksa önceki yıl sütunundan
    out = {}
    for (b, p), c in by.items():
        def g(sinif, key, i):
            v = c.get(sinif, {}).get(key); return None if v is None or v[i] is None else v[i] / 1000
        rec = {"dibs": {}, "diger": {}, "toplam": {}}
        for k in MDC_SINIF:
            rec["toplam"][k] = [r1(g(k, "ana", 0)), r1(g(k, "ana", 1))]
            rec["dibs"][k] = [r1(g(k, "dibs", 0)), r1(g(k, "dibs", 1))]
            rec["diger"][k] = [None if g(k, "ana", i) is None else r1(g(k, "ana", i) - (g(k, "dibs", i) or 0)) for i in (0, 1)]
        tots = [g(k, "ana", 2) for k in MDC_SINIF]
        rec["total"] = None if all(t is None for t in tots) else r1(sum(t or 0 for t in tots))
        if rec["total"] is None:
            continue
        out.setdefault(p, {})[b] = rec
    return out


def mdc_excel(mdc, banks, path):
    """Kullanıcının MDC tablosu düzeninde Excel: banka · dönem · DİBS/DİĞER/TOPLAM × ASA/SH/VKET × TRY/YP · TOTAL (mn TL)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook(); ws = wb.active; ws.title = "MDC"
    periods = sorted(mdc, key=period_key)
    LACI, MAVI, ACIK, BEYAZ = "1C3044", "5E8BC5", "C9D6EA", "FFFFFF"
    fill = lambda hex_: PatternFill("solid", fgColor=hex_)
    ince = Side(style="thin", color="B8C2D1"); kenar = Border(left=ince, right=ince, top=ince, bottom=ince)
    ort = Alignment(horizontal="center", vertical="center")
    ws["A1"] = "MDC"; ws["A2"] = "Menkul Değerler Cüzdanı — bin TL değil, milyon TL · son dönem " + (f"{periods[-1][:4]} Ç{periods[-1][-1]}" if periods else "")
    ws["A1"].font = Font(bold=True, color=BEYAZ); ws["A1"].fill = fill(LACI); ws["A2"].font = Font(italic=True, size=9, color="55627A")
    ws.merge_cells("A1:U1"); ws.merge_cells("A2:U2")
    # başlık satırları 3-5
    ws.cell(3, 1, "Banka"); ws.cell(3, 2, "Dönem"); ws.merge_cells(start_row=3, start_column=1, end_row=5, end_column=1); ws.merge_cells(start_row=3, start_column=2, end_row=5, end_column=2)
    gruplar = [("DİBS", "dibs"), ("DİĞER", "diger"), ("TOPLAM", "toplam")]
    col = 3
    for ad, _ in gruplar:
        ws.cell(3, col, ad); ws.merge_cells(start_row=3, start_column=col, end_row=3, end_column=col + 5)
        for j, sinif in enumerate(("ASA", "SH", "VKET")):
            ws.cell(4, col + 2 * j, sinif); ws.merge_cells(start_row=4, start_column=col + 2 * j, end_row=4, end_column=col + 2 * j + 1)
            ws.cell(5, col + 2 * j, "TRY"); ws.cell(5, col + 2 * j + 1, "YP")
        col += 6
    ws.cell(3, col, "TOTAL"); ws.merge_cells(start_row=3, start_column=col, end_row=5, end_column=col)
    for r in (3, 4, 5):
        for c in range(1, col + 1):
            cell = ws.cell(r, c); cell.alignment = ort; cell.border = kenar
            cell.fill = fill(LACI if r == 3 else MAVI if r == 4 else ACIK); cell.font = Font(bold=True, color=BEYAZ if r < 5 else LACI, size=10)
    # veri satırları: banka (aktif büyüklüğü sırası) × dönem (artan)
    BANT = ["F4F6F9", "FFFFFF"]
    r = 6
    for bi, b in enumerate([x["ad"] for x in banks] + sorted({bb for p in mdc for bb in mdc[p]} - {x["ad"] for x in banks})):
        ps = [p for p in periods if b in mdc[p]]
        if not ps:
            continue
        for p in ps:
            rec = mdc[p][b]
            ws.cell(r, 1, BANKS.get(b, (b, ""))[0] or b).font = Font(bold=True, color=LACI)
            ws.cell(r, 2, f"{p[:4]} Ç{p[-1]}")
            c = 3
            for _, key in gruplar:
                for sinif in ("asa", "sh", "vket"):
                    for v in rec[key][sinif]:
                        cell = ws.cell(r, c, None if v is None else round(v)); cell.number_format = "#,##0"; c += 1
            cell = ws.cell(r, c, None if rec["total"] is None else round(rec["total"])); cell.number_format = "#,##0"; cell.font = Font(bold=True)
            for cc in range(1, c + 1):
                ws.cell(r, cc).fill = fill(BANT[bi % 2]); ws.cell(r, cc).border = kenar
            r += 1
    ws.freeze_panes = "C6"
    ws.column_dimensions["A"].width = 14; ws.column_dimensions["B"].width = 9
    for c in range(3, col + 1):
        ws.column_dimensions[get_column_letter(c)].width = 11
    ws.cell(r + 1, 1, "Kaynak: bankaların solo BDDK formatlı bilançoları. ASA = GUD farkı kâr/zarara yansıtılan (1.2), SH = GUD farkı diğer kapsamlı gelire yansıtılan (1.3), VKET = itfa edilmiş maliyetle ölçülen diğer finansal varlıklar (2.4); DİBS = devlet borçlanma senetleri alt satırı, DİĞER = kalan. Yalnız PDF'i yüklenmiş banka-dönemler yer alır.").font = Font(italic=True, size=9, color="55627A")
    path.parent.mkdir(parents=True, exist_ok=True); wb.save(path)
    return r - 6


OZET_KOL = [  # (anahtar, başlık, tür)  — kullanıcının "Sektör Sonuçları" özet tablosu düzeni
    ("aktif", "Toplam Aktifler", "mn"), ("kredi", "Toplam Krediler", "mn"), ("ozkaynak", "Toplam Özkaynaklar", "mn"),
    ("net_kar", "Net Dönem Kâr/Zararı", "mn"), ("kapsamli", "Toplam Kapsamlı Gelir", "mn"), ("net_faiz", "Net Faiz Gelirleri", "mn"),
    ("net_ucret", "Net Ücret ve Komisyonlar", "mn"), ("ozk_yontemi", "Özk. Yönt. Uyg. Ortaklık K/Z", "mn"),
    ("cost_income", "Cost / Income", "pct"), ("syr", "SYR", "pct100"), ("roaa", "ROAA", "pct"), ("roae", "ROAE", "pct"),
    ("roaa_x", "ROAA (Özk. Yönt. Ort. Hariç)", "pct"), ("roae_x", "ROAE (Özk. Yönt. Ort. Hariç)", "pct"),
    ("zk_faiz", "Zorunlu Karş. Alınan Faiz", "mn"), ("zk_oran", "Zor. Karş. Faizi / Toplam Faiz Geliri", "pct"),
    ("spk", "Sermaye Piyasası İşlem K/Z (net)", "mn"), ("turev", "Türev İşlem K/Z (net)", "mn"), ("kambiyo", "Kambiyo K/Z (net)", "mn"), ("ticari", "Ticari K/Z Toplam", "mn"),
]
OZET_NOT = ("ROAA/ROAE = yıllıklandırılmış net kâr / (dönem sonu + önceki yıl sonu) ortalaması; 'Özk. Yönt. Ort. Hariç' sütunlarında özkaynak yöntemi "
            "uygulanan ortaklıklardan kâr/zarar net kârdan düşülür. Cost/Income = (personel + diğer faaliyet giderleri) / (net faiz + net ücret + ticari + "
            "diğer faaliyet gelirleri). SYR ve toplam kapsamlı gelir finansal tablo dipnotlarından; ticari K/Z kalemleri gelir tablosundaki net tutarlar. Katılım bankalarında faiz kalemleri kâr payı gelir/giderlerine, mevduat toplanan fonlara karşılık gelir. "
            "NPL oranı ve serbest karşılık dipnot verisi olduğundan tabloda yer almaz. Kaynak: bankaların solo BDDK formatlı finansal tabloları (KAP).")


def ozet_tablo(con, wide):
    """{period: [satır]} — PDF'i yüklenmiş (fin_rows'u olan) bankalar, aktif büyüklüğüne göre sıralı; tutarlar mn TL, oranlar kesir."""
    rows = con.execute("SELECT bank, period, stmt, section, code, label, total, total_prev FROM fin_rows ORDER BY bank, period, ord").fetchall()
    grp = {}
    for r in rows:
        grp.setdefault((r[0], r[1]), []).append(r)
    def bul(lst, stmt, rx, sec=None):
        return next((r for r in lst if r[2] == stmt and (sec is None or r[3] == sec) and re.search(rx, _n(r[5]))), None)
    tot = lambda r: None if r is None or r[6] is None else r[6] / 1000
    prv = lambda r: None if r is None or r[7] is None else r[7] / 1000
    ort = lambda c, pv: None if c is None else ((c + pv) / 2 if pv is not None else c)
    out = {}
    for (b, p), lst in grp.items():
        m = wide.get(p, {}).get(b, {})
        if not m.get("toplam_aktif"):
            continue
        y, q = period_key(p); ann = 4 / q; g = m.get
        aktif, aktif_p = g("toplam_aktif"), prv(bul(lst, "BS", r"^(varliklar|aktif) toplami", "A"))
        ozkay, ozkay_p = g("ozkaynak"), prv(bul(lst, "BS", r"^ozkaynaklar$", "L"))
        ozky = tot(bul(lst, "IS", r"^ozkaynak yontemi uygulanan ortakliklardan"))
        zk = tot(bul(lst, "IS", r"^zorunlu karsiliklardan alinan (faiz|gelir)"))
        # kredilere ilişkin beklenen zarar karşılığı stoku (bilanço aktif II. bölüm; kod bankadan bankaya kayar: Akbank 2.5, Garanti 2.4)
        bzk_aday = [r for r in lst if r[2] == "BS" and r[3] == "A" and re.search(r"^beklenen zarar karsiliklari", _n(r[5]))]
        bzk_r = next((r for r in bzk_aday if str(r[4]).startswith("2.")), None) or (max(bzk_aday, key=lambda r: r[6] or 0) if bzk_aday else None)
        nk = g("net_kar"); nk_x = None if nk is None else nk - (ozky or 0)
        yil = lambda v: None if v is None else v * ann
        out.setdefault(p, []).append({
            "ad": b, "aktif": r1(aktif, 1), "kredi": r1(g("kredi"), 1), "ozkaynak": r1(ozkay, 1), "net_kar": r1(nk, 1),
            "kapsamli": r1(g("kapsamli_gelir"), 1), "net_faiz": r1(g("net_faiz"), 1), "net_ucret": r1(g("net_ucret"), 1), "ozk_yontemi": r1(ozky, 1),
            "cost_income": r1(ratios(m, ann)["maliyet_gelir"], 4), "syr": r1(g("syr"), 2),
            "roaa": r1(safe_div(yil(nk), ort(aktif, aktif_p)), 4), "roae": r1(safe_div(yil(nk), ort(ozkay, ozkay_p)), 4),
            "roaa_x": r1(safe_div(yil(nk_x), ort(aktif, aktif_p)), 4), "roae_x": r1(safe_div(yil(nk_x), ort(ozkay, ozkay_p)), 4),
            "zk_faiz": r1(zk, 1), "zk_oran": r1(safe_div(zk, g("faiz_geliri")), 4),
            "spk": r1(tot(bul(lst, "IS", r"^sermaye piyasasi islemleri kar")), 1), "turev": r1(tot(bul(lst, "IS", r"^turev finansal islemlerden kar")), 1),
            "kambiyo": r1(tot(bul(lst, "IS", r"^kambiyo islemleri kar")), 1), "ticari": r1(g("ticari_kz"), 1),
            "bzk_stok": r1(tot(bzk_r), 1),   # çeyrek raporu: karşılık stoku / krediler
        })
    for p in out:
        out[p].sort(key=lambda r: -(r["aktif"] or 0))
    return out


def ozet_excel(ozet, path):
    """Dönem başına bir sayfa: kullanıcının özet tablo düzeni (mn TL / %)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook(); wb.remove(wb.active)
    LACI, ACIK, BEYAZ = "1C3044", "C9D6EA", "FFFFFF"
    fill = lambda hex_: PatternFill("solid", fgColor=hex_)
    ince = Side(style="thin", color="B8C2D1"); kenar = Border(left=ince, right=ince, top=ince, bottom=ince)
    n = 0
    for p in sorted(ozet, key=period_key, reverse=True):
        ws = wb.create_sheet(f"{p[:4]} Ç{p[-1]}")
        ws["A1"] = f"{DONEM_SONU[p[-1]]}.{p[:4]} Bankalar Özet Verileri (Solo) · {len(ozet[p])} banka · mn TL"
        ws["A1"].font = Font(bold=True, color=BEYAZ); ws["A1"].fill = fill(LACI); ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2 + len(OZET_KOL))
        ws.cell(2, 1, "Sıra No"); ws.cell(2, 2, "Banka (Mio TL)")
        for j, (k, ad, t) in enumerate(OZET_KOL):
            ws.cell(2, 3 + j, ad)
        for c in range(1, 3 + len(OZET_KOL)):
            cell = ws.cell(2, c); cell.font = Font(bold=True, color=LACI, size=9); cell.fill = fill(ACIK); cell.border = kenar
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[2].height = 48
        for i, r in enumerate(ozet[p]):
            ws.cell(3 + i, 1, i + 1); ws.cell(3 + i, 2, TAM_AD.get(r["ad"], r["ad"])).font = Font(bold=True, color=LACI)
            for j, (k, ad, t) in enumerate(OZET_KOL):
                v = r.get(k); cell = ws.cell(3 + i, 3 + j, None if v is None else (round(v) if t == "mn" else (v / 100 if t == "pct100" else v)))
                cell.number_format = "#,##0" if t == "mn" else "0.0%"; cell.border = kenar
            n += 1
        ws.cell(4 + len(ozet[p]), 1, OZET_NOT).font = Font(italic=True, size=8, color="55627A")
        ws.freeze_panes = "C3"; ws.column_dimensions["A"].width = 6; ws.column_dimensions["B"].width = 38
        for c in range(3, 3 + len(OZET_KOL)):
            ws.column_dimensions[get_column_letter(c)].width = 12
    path.parent.mkdir(parents=True, exist_ok=True); wb.save(path)
    return n


def build(out=OUT):
    try:
        pdf_isle()
    except Exception as e:
        print(f"  ~ PDF kutusu işlenemedi ({type(e).__name__}: {str(e)[:80]})")
    db = sync_db()
    if db is None:
        print("  ~ banka.db yok (kaynak uygulama bu makinede değil) — banka_kar.json korunuyor")
        return False
    con = sqlite3.connect(db)
    rows = con.execute("SELECT bank, period, metric, value FROM metrics").fetchall()
    wide = {}
    for b, p, m, v in rows:
        if v is None:
            continue
        wide.setdefault(p, {}).setdefault(b, {})[m] = float(v)
    periods = sorted(wide, key=period_key)
    banks_set = sorted({b for p in wide for b in wide[p]})
    # çeyreklik akım
    ceyrek = {}
    for p in periods:
        y, q = period_key(p)
        prev = f"{y}Q{q-1}" if q > 1 else None
        for b, vals in wide[p].items():
            row = dict(vals)
            if q > 1:
                pv = wide.get(prev, {}).get(b)
                for k in list(row):
                    if k in FLOW:
                        row[k] = (row[k] - pv[k]) if (pv and k in pv) else None
            ceyrek.setdefault(p, {})[b] = row
    def paket(src, annualize):
        out_ = {}
        for p in periods:
            y, q = period_key(p)
            for b, vals in src.get(p, {}).items():
                ann = (4 / q) if annualize else 1
                r = {k: r1(v, 1) for k, v in vals.items() if k in dict((m[0], 1) for m in METRICS) and (annualize or k in FLOW)}
                for k, v in ratios(vals, ann).items():
                    r[k] = r1(v, 1) if k == "op_gelir" else r1(v, 4)
                out_.setdefault(p, {})[b] = r
        return out_
    ytd = paket(wide, True)
    cey = paket(ceyrek, False)
    # banka listesi: son dönemdeki aktife göre sıralı
    def son_aktif(b):
        for p in reversed(periods):
            v = wide.get(p, {}).get(b, {}).get("toplam_aktif")
            if v:
                return v
        return 0
    banks = [{"ad": b, "kisa": BANKS.get(b, (b, "Diğer"))[0], "grup": BANKS.get(b, (b, "Diğer"))[1], "tam": TAM_AD.get(b, b)} for b in sorted(banks_set, key=lambda b: -son_aktif(b))]
    kapsam = {p: len(wide[p]) for p in periods}
    # faaliyet bölümleri
    seg_rows = con.execute("SELECT bank, period, segment, item, value, seg_order, item_order FROM segments ORDER BY bank, period, seg_order, item_order").fetchall()
    segments = {}
    tmp = {}
    for b, p, s, it, v, so, io in seg_rows:
        tmp.setdefault((b, p), []).append((s, it, v, so, io))
    for (b, p), lst in tmp.items():
        segs = []
        for s, it, v, so, io in lst:
            if s not in segs:
                segs.append(s)
        items = []
        for s, it, v, so, io in lst:
            if it not in items:
                items.append(it)
        val = {(s, it): v for s, it, v, so, io in lst}
        toplam_ad = next((s for s in segs if segment_category(s) == "Toplam"), None)
        bolumler = [s for s in segs if segment_category(s) != "Toplam"]
        kalem = {k: seg_item(items, k) for k in SEG_ITEM_PRIORITY}
        def deg(s, k):
            it = kalem.get(k)
            v = val.get((s, it)) if it else None
            return None if v is None else r1(v / 1000, 1)   # bin TL → mn TL
        nk_it = kalem["net_kar"]; turetilmis = False
        if nk_it is None and kalem.get("vergi_oncesi"):   # Akbank 2025Ç4 gibi: net kâr satırı yok → vergi öncesi kâr + vergi (tabloda işaretli)
            turetilmis = True
            vo, vg = kalem["vergi_oncesi"], kalem.get("vergi")
            for s in segs:
                a = val.get((s, vo)); t = val.get((s, vg)) if vg else 0
                val[(s, "__net_kar__")] = None if a is None else a + ((t or 0) if (t or 0) <= 0 else -(t or 0))
            kalem["net_kar"] = nk_it = "__net_kar__"
        toplam_nk = deg(toplam_ad, "net_kar") if toplam_ad else (r1(sum(val.get((s, nk_it)) or 0 for s in bolumler) / 1000, 1) if nk_it else None)
        segments.setdefault(b, {})[p] = {
            "toplam_ad": toplam_ad, "toplam_net_kar": toplam_nk, "net_kar_turetilmis": turetilmis,
            "bolumler": [{"ad": s.replace("\n", " "), "kat": segment_category(s), "net_kar": deg(s, "net_kar"), "varlik": deg(s, "varlik"),
                          "nfg": deg(s, "nfg"), "komisyon": deg(s, "komisyon"), "ticari": deg(s, "ticari"), "diger_gelir": deg(s, "diger_gelir")} for s in bolumler],
        }
    # Menkul değerler cüzdanı kırılımı (+ Excel)
    mdc = mdc_kirilim(con)
    try:
        n_mdc = mdc_excel(mdc, banks, out.parent / "banka-mdc-kirilimi.xlsx")
    except Exception as e:
        n_mdc = 0; print(f"  ~ MDC Excel yazılamadı ({type(e).__name__}: {str(e)[:80]})")
    # Özet tablo (sektör sonuçları düzeni) + Excel
    ozet_t = ozet_tablo(con, wide)
    try:
        n_ozet = ozet_excel(ozet_t, out.parent / "banka-ozet-tablo.xlsx")
    except Exception as e:
        n_ozet = 0; print(f"  ~ Özet tablo Excel yazılamadı ({type(e).__name__}: {str(e)[:80]})")
    # Peer Grup Türev Analizi (nazım hesaplar tablosu, III. bölüm) — ayrı JSON: banka_turev.json
    try:
        import turev_export
        meta = {b: (BANKS.get(b, (b, "Diğer"))[0], BANKS.get(b, (b, "Diğer"))[1], TAM_AD.get(b, b)) for b in set(banks_set) | set(BANKS)}
        turev_export.build(con, wide, meta, out.parent / "banka_turev.json", buyuk=BIG7)
    except Exception as e:
        print(f"  ~ banka_turev.json yazılamadı ({type(e).__name__}: {str(e)[:120]})")
    # MDC faiz tipi
    faiz = {}
    for b, p, bucket, v in con.execute("SELECT bank, period, bucket, value FROM faiz_tipi"):
        faiz.setdefault(p, {}).setdefault(b, {})[bucket] = r1(v, 1)
    # özet (son tam dönem: ≥5 banka)
    tam = [p for p in periods if kapsam[p] >= 5] or periods
    son = tam[-1]; y, q = period_key(son); onceki = f"{y-1}Q{q}"
    cur = ytd[son]; prv = ytd.get(onceki, {})
    ortak = [b for b in cur if b in prv and cur[b].get("net_kar") is not None and prv[b].get("net_kar") is not None]
    nk_top = sum(cur[b]["net_kar"] for b in cur if cur[b].get("net_kar") is not None)
    yoy = (sum(cur[b]["net_kar"] for b in ortak) / sum(prv[b]["net_kar"] for b in ortak) - 1) * 100 if ortak and sum(prv[b]["net_kar"] for b in ortak) > 0 else None
    def med(k):
        v = sorted(x[k] for x in cur.values() if x.get(k) is not None)
        return None if not v else (v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2)
    def ht(v, d=1, sign=False):
        if v is None:
            return "—"
        s = f"{v:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")
        return ("+" if sign and v > 0 else "") + s
    sirali = sorted([b for b in cur if cur[b].get("net_kar") is not None], key=lambda b: -cur[b]["net_kar"])[:3]
    kisa = lambda b: BANKS.get(b, (b, ""))[0]
    plabel = f"{son[:4]} Ç{son[-1]}"
    ozet = (f"<b>{plabel}</b> solo finansal tablolar, {kapsam[son]} banka: toplam net kâr <b>{ht(nk_top / 1000)} milyar TL</b>"
            + (f" (yıllık {ht(yoy, 1, True)}%, aynı banka seti)" if yoy is not None else "")
            + f"; medyan ROE %{ht((med('roe') or 0) * 100)}, ROA %{ht((med('roa') or 0) * 100, 2)}. En yüksek net kâr: "
            + ", ".join(f"{kisa(b)} {ht(cur[b]['net_kar'] / 1000)} mlr" for b in sirali) + ".")
    kayit = {
        "updated": dt.datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M"),
        "veri_tarihi": dt.datetime.fromtimestamp(db.stat().st_mtime, ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M"),
        "kaynak": "Bankaların solo (konsolide olmayan) BDDK formatlı finansal tabloları (KAP); faaliyet bölümleri finansal tablo dipnotları; MDC faiz tipi yatırımcı sunumları",
        "periods": periods, "kapsam": kapsam, "son_tam": son, "banks": banks, "big7": [b for b in BIG7 if b in banks_set],
        "metrics": [{"key": k, "label": l, "stmt": s, "flow": s == "IS"} for k, l, s in METRICS],
        "ratios": [{"key": k, "label": l, "short": sh, "fmt": f, "good": g} for k, l, sh, f, g in RATIOS],
        "ytd": ytd, "ceyrek": cey, "segments": segments, "faiz_tipi": faiz, "buckets": BUCKETS, "ozet_html": ozet,
        "mdc": mdc, "mdc_xlsx": "data/banka-mdc-kirilimi.xlsx" if n_mdc else None,
        "ozet_tablo": ozet_t, "ozet_xlsx": "data/banka-ozet-tablo.xlsx" if n_ozet else None, "ozet_kol": [list(k) for k in OZET_KOL], "ozet_not": OZET_NOT,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(kayit, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  banka_kar.json: {len(periods)} dönem · {len(banks)} banka · bölüm verisi {len(segments)} banka · MDC kırılımı {n_mdc} satır · özet tablo {n_ozet} satır · {out.stat().st_size // 1024} KB · son tam dönem {plabel}")
    return True


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
