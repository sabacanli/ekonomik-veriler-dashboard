#!/usr/bin/env python3
"""Peer Grup Türev Analizi — site/data/banka_turev.json üretir (banka_kar_export.build() çağırır).

Kaynak: banka.db `fin_rows` (stmt='OBS'): bankaların solo BDDK formatlı finansal tablolarındaki nazım hesaplar
tablosunun "III. Türev Finansal Araçlar" bölümü. Ürün toplamları kullanıcının tablosundaki gibi alım + satım bacağıdır:

  Forward        = Vadeli döviz alım + satım işlemleri        (3.2.1.1 + 3.2.1.2)
  Para swapı     = Swap para alım + satım işlemleri           (3.2.2.1 + 3.2.2.2)
  Faiz swapı/IRS = Swap faiz alım + satım işlemleri           (3.2.2.3 + 3.2.2.4)
  Opsiyon        = Para alım + para satım opsiyonları         (3.2.3.1 + 3.2.3.2)
  Futures        = Futures para alım + satım işlemleri        (3.2.4.1 + 3.2.4.2)
  Diğer          = kalan alım satım amaçlı türevler (faiz/menkul değer opsiyonları, futures faiz, diğer)
  Riskten kor.   = Riskten korunma amaçlı türev finansal araçlar (3.1)

Satırlar etiketle bulunur (kod numarası bankaya göre kayabilir). Her banka-dönem kod ağacıyla doğrulanır: her ara
toplam alt kalemlerinin toplamına, her satırda TP + YP toplama eşit olmalıdır (cari ve önceki dönem sütunları).
Tutmayan gruplarda PDF metninden kaynaklanan iki bilinen bozulma onarılır — yapışmış sayılar ("63 3.228" →
"633.228") ve düşmüş "-" (sıfır) hücreleri — ve onarım yalnız üst toplamı altı sütunda da tutturuyorsa kabul edilir;
onarılamayan grubun kalemleri boş bırakılır ve not düşülür.

Ek veri: `turev_ek.json` — PDF'i okunamayan banka-dönemler için KAP bildirimlerinden elle derlenen satırlar (bin TL).
Önceki yıl sonu: bir yılın PDF'lerindeki "önceki dönem" sütunu, o bankanın Ç4 verisi yoksa Ç4 olarak kullanılır.
"""
from __future__ import annotations
import datetime as dt, itertools, json, re
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
EK = HERE / "turev_ek.json"
KUR_XLSX = BASE / "tcmb faiz" / "tcmb_faiz.xlsx"

# (anahtar, kısa ad, nazım hesap tanımı, alım bacağı, satım bacağı) — sıra kullanıcının pay tablosundaki gibi
URUNLER = [
    ("fwd", "Forward", "Vadeli döviz alım + satım işlemleri", "fwd_a", "fwd_s"),
    ("ops", "Opsiyon", "Para alım + para satım opsiyonları", "po_a", "po_s"),
    ("fut", "Futures", "Futures para alım + satım işlemleri", "fp_a", "fp_s"),
    ("psw", "Para swapı", "Swap para alım + satım işlemleri", "ps_a", "ps_s"),
    ("irs", "Faiz swapı (IRS)", "Swap faiz alım + satım işlemleri", "fs_a", "fs_s"),
]
ALAN = [a for k, *_ in URUNLER for a in (k + "_a", k + "_s", k)] + ["diger", "hedge", "tur", "aktif"]
# normalize edilmiş (küçük harf, Türkçe karakter ve boşluk/noktalama yok) etiket desenleri
KALEM = {
    "tur": r"^turevfinansalaraclar", "hedge": r"^risktenkorunmaamacliturevfinansalaraclar",
    "ticari": r"^alimsatimamacli(islemler|turevfinansalaraclar)",
    "fwd": r"^vadeli(doviz)?alimsatimislemleri", "fwd_a": r"^vadelidovizalimislemleri", "fwd_s": r"^vadelidovizsatimislemleri",
    "swp": r"^para(vefaiz)?swapislemleri", "ps_a": r"^swapparaalimislemleri", "ps_s": r"^swapparasatimislemleri",
    "fs_a": r"^swapfaizalimislemleri", "fs_s": r"^swapfaizsatimislemleri",
    "opt": r"^parafaizvemenkuldeger(ler)?opsiyonlari", "po_a": r"^paraalimopsiyonlari", "po_s": r"^parasatimopsiyonlari",
    "fut": r"^futuresparaislemleri", "fp_a": r"^futuresparaalimislemleri", "fp_s": r"^futuresparasatimislemleri",
}
UST = {"fwd_a": "fwd", "fwd_s": "fwd", "ps_a": "swp", "ps_s": "swp", "fs_a": "swp", "fs_s": "swp",
       "po_a": "opt", "po_s": "opt", "fp_a": "fut", "fp_s": "fut"}
VARSAYILAN = ["Aktifbank", "Fibabank", "BurganBank", "Odeabank", "Anadolubank"]   # orta ölçekli grup (sayfa açılışı)
GORUNEN = {"YapıKredi": "Yapı Kredi", "İşbankası": "İş Bankası", "Garanti Bankası": "Garanti", "Fibabank": "Fibabanka", "BurganBank": "Burgan Bank",
           "Aktifbank": "Aktif Bank", "Nurolbank": "Nurol Bank", "Misyonbank": "Misyon Bank", "DYatirim": "D Yatırım Bankası",
           "ZiraatKatilim": "Ziraat Katılım", "ZiraatDinamik": "Ziraat Dinamik", "Albaraka": "Albaraka Türk"}


def _tn(s):
    s = (s or "").replace("İ", "i").replace("I", "ı").lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("ç", "c"), ("â", "a"), ("î", "i"), ("û", "u")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "", s)


def pkey(p):
    return (int(p[:4]), int(p[-1]))


def _bolum3(rows):
    """Nazım tablo satırlarından III. bölüm: {kod: {"lab", "v": [tp, yp, toplam, tp_ö, yp_ö, toplam_ö]}} (sıra korunur)."""
    out, basla = {}, False
    for code, label, *v in rows:
        code, lab = (code or "").strip(), _tn(label)
        if not basla:
            if re.search(KALEM["tur"], lab):
                basla, code = True, "III"
            else:
                continue
        elif code in ("IV", "B") or lab.startswith("bemanet") or lab.startswith("emanetkiymetler"):
            break
        if code and code not in out:
            out[code] = {"lab": lab, "v": [float(x or 0) for x in v]}
    return out


def _cocuk(agac, kod):
    on = "3" if kod == "III" else kod
    return [k for k in agac if re.fullmatch(re.escape(on) + r"\.\d+", k)]


def _aday(v, olcek, tol):
    """Bozuk satır için olası altılılar: baştaki dolgu sıfırları atılır, yapışmış sayılar bölünür, düşmüş '-' için 0 eklenir."""
    t = [int(round(x / olcek)) for x in v]
    bas = 0
    while bas < 6 and t[bas] == 0:
        bas += 1
    bulunan = set()

    def uret(seq, kalan):
        if kalan == 0:
            if abs(seq[0] + seq[1] - seq[2]) <= tol and abs(seq[3] + seq[4] - seq[5]) <= tol:
                bulunan.add(tuple(seq))
            return
        for i in range(len(seq) + 1):
            uret(seq[:i] + [0] + seq[i:], kalan - 1)
        for i, x in enumerate(seq):
            s = str(x)
            for j in range(1, len(s)):
                if s[j] == "0":          # ikinci parça "0…" ile başlayamaz (sayı böyle yazılmaz)
                    continue
                uret(seq[:i] + [int(s[:j]), int(s[j:])] + seq[i + 1:], kalan - 1)

    for k in range(0, bas + 1):
        tok = t[k:]
        if 0 < 6 - len(tok) <= 3:
            uret(tok, 6 - len(tok))
    return [[x * olcek for x in c] for c in bulunan]


def dogrula_onar(agac):
    """Kod ağacını kökten yaprağa doğrular; tutmayan grupları onarmayı dener. → (onarım notları, güvenilmez kodlar)"""
    if "III" not in agac:
        return [], set(agac)
    deger = [x for n in agac.values() for x in n["v"]]
    olcek = 1000.0 if deger and all(abs(x) % 1000 == 0 for x in deger) and any(deger) else 1.0   # 2026: milyon TL tablolar
    tol = 2 * olcek
    satir_ok = lambda v: abs(v[0] + v[1] - v[2]) <= tol and abs(v[3] + v[4] - v[5]) <= tol
    T = (2, 5)                               # toplam sütunları (cari, önceki) — dışa aktarılan yalnız bunlar
    notlar, kotu = [], set()
    kuyruk = ["III"]
    while kuyruk:
        ust = kuyruk.pop(0)
        cocuk = _cocuk(agac, ust)
        if not cocuk:
            continue
        kuyruk += cocuk
        if ust in kotu:                      # üst toplam güvenilmezse altı doğrulanamaz
            kotu.update(cocuk)
            continue
        hedef, gtol = agac[ust]["v"], tol * max(1, len(cocuk) / 2)
        if all(abs(hedef[i] - sum(agac[c]["v"][i] for c in cocuk)) <= gtol for i in T):
            continue                         # toplamlar tutuyor (yalnız TP/YP dağılımı kaymış olabilir: tek "-" düşmüş satır; kullanılmıyor)
        bozuk = [c for c in cocuk if not satir_ok(agac[c]["v"])]
        if len(bozuk) == 1:                  # tek bozuk satır: üst toplam − diğerleri
            c = bozuk[0]
            yeni = [hedef[i] - sum(agac[x]["v"][i] for x in cocuk if x != c) for i in range(6)]
            if all(yeni[i] >= -gtol for i in T):
                if not satir_ok(yeni) or min(yeni) < -gtol:      # TP/YP dağılımı bilinmiyor: toplam TP'ye yazılır (alt kalemi yoksa önemsiz)
                    yeni = [yeni[2], 0.0, yeni[2], yeni[5], 0.0, yeni[5]]
                agac[c]["v"] = [max(0.0, x) for x in yeni]
                notlar.append(f"{c} üst toplamdan türetildi")
                continue
        elif 2 <= len(bozuk) <= 3:           # birden çok bozuk satır: aday altılılardan üst toplamı tutturan TEK birleşim
            adaylar = [_aday(agac[c]["v"], olcek, 2) for c in bozuk]
            if all(adaylar):
                sabit = [sum(agac[x]["v"][i] for x in cocuk if x not in bozuk) for i in range(6)]
                def sec(kolonlar):           # toplamları aynı olan birleşimler tek çözüm sayılır
                    return list({tuple((a[2], a[5]) for a in k): k for k in itertools.product(*adaylar)
                                 if all(abs(hedef[i] - sabit[i] - sum(a[i] for a in k)) <= gtol for i in kolonlar)}.values())
                uyan = sec(range(6))
                if len(uyan) != 1:
                    uyan = sec(T)
                if len(uyan) == 1:
                    for c, a in zip(bozuk, uyan[0]):
                        agac[c]["v"] = list(a)
                    notlar.append(f"{', '.join(bozuk)} yeniden ayrıştırıldı")
                    continue
        kotu.update(cocuk)
        notlar.append(f"{ust} altındaki kalemler toplamı tutmuyor")
    return notlar, kotu


def kalemler(rows, ondeki=False):
    """Bir banka-dönemin nazım satırları → ({alan: bin TL}, notlar). ondeki=True: önceki dönem (yıl sonu) sütunu."""
    agac = _bolum3(rows)
    if "III" not in agac:
        return None, ["türev bölümü bulunamadı"]
    notlar, kotu = dogrula_onar(agac)
    j = 5 if ondeki else 2
    kod = {}
    for c, n in agac.items():
        for k, pat in KALEM.items():
            if k not in kod and re.search(pat, n["lab"]):
                kod[k] = c
                break
    def al(k):
        """Kalem değeri: satır yoksa ve üst grubu doğrulanmışsa 0 (o banka raporlamıyor); güvenilmezse None."""
        if k in kod:
            return None if kod[k] in kotu else agac[kod[k]]["v"][j]
        ust = UST.get(k)
        if ust is None or ust not in kod or kod[ust] not in kotu:
            return 0.0
        return None
    out = {}
    for k, _ad, _tanim, ka, ks in URUNLER:
        a, s = al(ka), al(ks)
        out[k + "_a"], out[k + "_s"] = a, s
        out[k] = a + s if a is not None and s is not None else None
    for k in ("fwd", "fut"):                 # iki bacağı okunamayan üründe toplam, üst satırdan (yalnız bu iki üründe üst = alım + satım)
        if out[k] is None and k in kod and kod[k] not in kotu:
            out[k] = agac[kod[k]]["v"][j]
    out["tur"] = agac["III"]["v"][j]
    out["hedge"] = al("hedge")
    bes = [out[k] for k, *_ in URUNLER]
    out["diger"] = None if out["hedge"] is None or any(x is None for x in bes) else max(0.0, out["tur"] - out["hedge"] - sum(bes))
    if not any(out[k] for k in out if out[k] is not None):
        return None, notlar                  # tümü sıfır: sütun boş (ör. önceki dönem sütunu verilmemiş)
    return out, notlar


# Yerel günlük kur dosyası 03.01.2022'de başlar; öncesi için EVDS ay sonu değerleri (TP.DK.USD.A.YTL, 12.11.2026'da doğrulandı)
KUR_ESKI = {"2020Q4": 7.3405, "2021Q1": 8.3260, "2021Q2": 8.7052, "2021Q3": 8.8433, "2021Q4": 12.9775}


def kur_donem_sonu(periods):
    """Dönem sonu USD/TL (TCMB döviz alış; dönem sonundaki ya da öncesindeki son gözlem). Dosya yoksa yalnız KUR_ESKI."""
    try:
        import pandas as pd
        g = pd.read_excel(KUR_XLSX, sheet_name="Gunluk")[["tarih", "usd"]].dropna()
        g["tarih"] = pd.to_datetime(g["tarih"]); g = g.sort_values("tarih")
    except Exception:
        return {p: KUR_ESKI[p] for p in periods if p in KUR_ESKI}
    out = {}
    for p in periods:
        if p in KUR_ESKI:
            out[p] = KUR_ESKI[p]; continue
        y, q = pkey(p)
        son = pd.Timestamp(year=y, month=q * 3, day=1) + pd.offsets.MonthEnd(0)
        once = g[g["tarih"] <= son]
        if len(once) and (son - once["tarih"].iloc[-1]).days <= 10:
            out[p] = round(float(once["usd"].iloc[-1]), 4)
        else:                                # seri başından önceki dönem sonu: izleyen ilk gözlem (en çok 10 gün)
            sonra = g[g["tarih"] > son]
            if len(sonra) and (sonra["tarih"].iloc[0] - son).days <= 10:
                out[p] = round(float(sonra["usd"].iloc[0]), 4)
    return out


def build(con, wide, banks_meta, out, buyuk=()):
    """banks_meta: {ad: (kısa, grup, tam)}; wide: {dönem: {banka: {metrik: mn TL}}}; buyuk: hazır "büyük bankalar" grubu.
    JSON'u yazar, özet sözlüğünü döndürür."""
    grp = {}
    for b, p, *r in con.execute("SELECT bank, period, code, label, tp, yp, total, tp_prev, yp_prev, total_prev FROM fin_rows "
                                "WHERE stmt='OBS' ORDER BY bank, period, ord"):
        grp.setdefault((b, p), []).append(r)
    veri, notlar, onarim = {}, {}, {}        # notlar: sayfada gösterilen kaynak notu; onarim: ayrıştırma onarımları (tanı için)
    def yaz(p, b, k, kaynak_not=None, nl=None):
        veri.setdefault(p, {})[b] = k
        if kaynak_not:
            notlar.setdefault(p, {})[b] = kaynak_not
        if nl:
            onarim.setdefault(p, {})[b] = "; ".join(nl)
    for (b, p), rows in sorted(grp.items(), key=lambda kv: (kv[0][0], pkey(kv[0][1]))):
        k, nl = kalemler(rows)
        if k:
            yaz(p, b, k, None, nl)
    # önceki yıl sonu sütunu → eksik Ç4 (yılın en erken PDF'i esas)
    for (b, p), rows in sorted(grp.items(), key=lambda kv: (kv[0][0], pkey(kv[0][1]))):
        y, q = pkey(p); p4 = f"{y - 1}Q4"
        if b in veri.get(p4, {}):
            continue
        k, nl = kalemler(rows, ondeki=True)
        if k:
            yaz(p4, b, k, f"{p[:4]} Ç{p[-1]} tablosunun önceki dönem sütunundan", nl)
    # elle derlenen ek veri (KAP bildirimleri) — yalnız veritabanında olmayan banka-dönemler
    if EK.exists():
        try:
            ek = json.loads(EK.read_text(encoding="utf-8"))
            for p, bb in ek.get("veri", {}).items():
                for b, e in bb.items():
                    if b in veri.get(p, {}):
                        continue
                    k = {}
                    for u, _ad, _t, ka, ks in URUNLER:
                        k[u + "_a"], k[u + "_s"] = float(e.get(ka, 0)), float(e.get(ks, 0)); k[u] = k[u + "_a"] + k[u + "_s"]
                    k["tur"], k["hedge"] = float(e["tur"]), float(e.get("hedge", 0))
                    k["diger"] = max(0.0, k["tur"] - k["hedge"] - sum(k[u] for u, *_ in URUNLER))
                    yaz(p, b, k, e.get("kaynak") or ek.get("kaynak"))
        except Exception as ex:
            print(f"  ~ turev_ek.json okunamadı ({type(ex).__name__}: {str(ex)[:80]})")
    periods = sorted(veri, key=pkey)
    r1 = lambda v: None if v is None else round(v / 1000, 1)        # bin TL → mn TL
    paket = {}
    for p in periods:
        for b, k in veri[p].items():
            aktif = wide.get(p, {}).get(b, {}).get("toplam_aktif")
            paket.setdefault(p, {})[b] = [r1(k.get(a)) for a in ALAN[:-1]] + [None if aktif is None else round(aktif, 1)]
    def son_aktif(b):
        for p in sorted(wide, key=pkey, reverse=True):
            v = wide[p].get(b, {}).get("toplam_aktif")
            if v:
                return v
        return 0
    adlar = sorted({b for p in veri for b in veri[p]}, key=lambda b: -son_aktif(b))
    meta = lambda b: banks_meta.get(b, (b, "Diğer", b))
    banks = [{"ad": b, "kisa": meta(b)[0], "grup": meta(b)[1], "tam": meta(b)[2], "gorunen": GORUNEN.get(b, b)} for b in adlar]
    # özet: en yeni, en az 5 bankalı dönem
    tam = [p for p in periods if len(veri[p]) >= 5] or periods
    son = tam[-1]
    top = {u: sum((veri[son][b].get(u) or 0) for b in veri[son]) for u, *_ in URUNLER}
    tur_top = sum(veri[son][b]["tur"] for b in veri[son])
    ht = lambda v, d=1: f"{v:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    sirali = sorted(URUNLER, key=lambda u: -top[u[0]])
    ozet = (f"<b>{son[:4]} Ç{son[-1]}</b> nazım hesapları, {len(veri[son])} banka: türev finansal araçların toplam sözleşme tutarı "
            f"<b>{ht(tur_top / 1e9, 2)} trilyon TL</b>. Ürün dağılımı: "
            + ", ".join(f"{u[1].lower().replace('(irs)', '(IRS)')} %{ht(top[u[0]] / tur_top * 100)}" for u in sirali)
            + ". Sayfa orta ölçekli banka grubuyla açılır; banka seçimi değiştirilebilir.")
    kayit = {
        "updated": dt.datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M"),
        "periods": periods, "kapsam": {p: len(veri[p]) for p in periods}, "son": son, "banks": banks,
        "urunler": [list(u[:3]) for u in URUNLER], "alan": ALAN, "veri": paket, "kur": kur_donem_sonu(periods),
        "varsayilan": [b for b in VARSAYILAN if b in adlar], "buyuk": [b for b in buyuk if b in adlar],
        "notlar": notlar, "onarim": onarim, "ozet_html": ozet,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(kayit, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = sum(len(v) for v in veri.values())
    eksik = [(p, b) for p in periods for b, k in veri[p].items() if any(k.get(a) is None for a in ALAN[:-1])]
    print(f"  banka_turev.json: {len(periods)} dönem · {len(banks)} banka · {n} banka-dönem · onarılan {sum(len(v) for v in onarim.values())}"
          f" · eksik kalemli {len(eksik)} · {out.stat().st_size // 1024} KB · son dönem {son[:4]} Ç{son[-1]} ({len(veri[son])} banka)")
    for p, b in eksik:
        print(f"    ! {b} {p}: {onarim.get(p, {}).get(b, 'kalem okunamadı')}")
    return {"veri": veri, "notlar": notlar, "onarim": onarim, "periods": periods}
