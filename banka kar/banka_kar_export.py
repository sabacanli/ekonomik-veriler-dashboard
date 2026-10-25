#!/usr/bin/env python3
"""Banka Kârlılık Analizi — site/data/banka_kar.json üretir.

Kaynak: yerel "Banka Analiz Dashboard'u" (Streamlit) uygulamasının SQLite veritabanı (banka.db): bankaların
solo (konsolide olmayan) BDDK formatlı finansal tablolarından okunan metrikler, faaliyet bölümleri ve MDC faiz tipi.
Veri bakımı (PDF yükleme, manuel giriş) yerel uygulamada yapılır; bu betik yalnız sonuçları siteye aktarır.

  BANKA_DB=/yol/banka.db  → kaynak veritabanı (varsayılan: ~/cowork/*/banka_dashboard/data/banka.db içinde en yenisi)
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
    "Garanti Bankası": ("Garanti", "Yabancı"), "QNB": ("QNB", "Yabancı"), "DenizBank": ("Deniz", "Yabancı"), "TEB": ("TEB", "Yabancı"),
    "BurganBank": ("Burgan", "Yabancı"), "Odeabank": ("Odea", "Yabancı"), "Fibabank": ("Fiba", "Yabancı"), "ING": ("ING", "Yabancı"),
    "HSBC": ("HSBC", "Yabancı"), "ICBC": ("ICBC", "Yabancı"), "Alternatifbank": ("ABank", "Yabancı"),
    "Şekerbank": ("Şeker", "Özel"), "Anadolubank": ("Anadolu", "Özel"),
    "TSKB": ("TSKB", "Kalkınma/Yatırım"), "Aktifbank": ("Aktif", "Kalkınma/Yatırım"), "TKYB": ("TKYB", "Kalkınma/Yatırım"),
}
BIG7 = ["Ziraat", "VakıfBank", "Halkbank", "İşbankası", "Akbank", "YapıKredi", "Garanti Bankası"]
SEGMENT_CATEGORIES = [
    ("Hazine / Yatırım", ["hazine", "aktif pasif", "yatırım bankacılığı", "sermaye piyasa"]),
    ("Bireysel / Perakende", ["bireysel", "perakende", "özel bankacılık", "dijital"]),
    ("Kurumsal / Ticari / KOBİ", ["kurumsal", "ticari", "kobi", "toptan", "tarım"]),
    ("Toplam", ["toplam", "banka'nın", "bankanın", "banka toplamı"]),
    ("Diğer / Dağıtılamayan", ["diğer", "dağıtılamayan", "genel müdürlük", "merkez"]),
]
SEG_ITEM_PRIORITY = {
    "net_kar": [r"^donem net kar", r"^net donem kar", r"^vergi sonrasi kar", r"^net kar", r"net kari?/zarar", r"surdurulen faaliyetler net"],
    "vergi_oncesi": [r"^vergi oncesi"], "vergi": [r"^vergi gideri", r"^vergi karsiligi", r"^vergi$"],
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


def build(out=OUT):
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
                r = {k: r1(v, 1) for k, v in vals.items() if k in dict((m[0], 1) for m in METRICS)}
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
    banks = [{"ad": b, "kisa": BANKS.get(b, (b, "Diğer"))[0], "grup": BANKS.get(b, (b, "Diğer"))[1]} for b in sorted(banks_set, key=lambda b: -son_aktif(b))]
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
            "ham": {"kalemler": items, "segmentler": [s.replace("\n", " ") for s in segs],
                    "deger": [[None if val.get((s, it)) is None else round(val[(s, it)]) for s in segs] for it in items]},
        }
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
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(kayit, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  banka_kar.json: {len(periods)} dönem · {len(banks)} banka · bölüm verisi {len(segments)} banka · {out.stat().st_size // 1024} KB · son tam dönem {plabel}")
    return True


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
