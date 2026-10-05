#!/usr/bin/env python3
"""Makro ek veriler (EVDS) → makro.json: reel sektör döviz pozisyonu (TCMB "Finansal Kesim Dışındaki Firmaların Döviz
Varlık ve Yükümlülükleri", aylık, ~2,5 ay gecikmeli) ve TL mevduat kur başabaş girdileri (3 aya kadar TL/USD mevduat
faizleri — akım, aylık ortalama; Piyasa Katılımcıları Anketi 12 ay sonrası USD/TL beklentisi; aylık ortalama kur).
EVDS_API_KEY yoksa ya da çekim başarısız olursa mevcut makro.json kullanılır (önbellek)."""
import datetime as dt, json, os, sys
from pathlib import Path
import requests
HERE = Path(__file__).resolve().parent
OUT = HERE / "makro.json"
KEY = os.environ.get("EVDS_API_KEY", "") or os.environ.get("TCMB_API_KEY", "")
H = {"key": KEY, "User-Agent": "Mozilla/5.0"}
BASE = "https://evds3.tcmb.gov.tr/igmevdsms-dis"
MEVF = {"TP.TRY.MT02": "tl3", "TP.TRY.MT06": "tl_top", "TP.USD.MT02": "usd3", "TP.USD.MT04": "usd12"}
PKA = {"TP.BEK.S05.C.A": "pka12"}          # 12 ay sonrasının USD/TL beklentisi (aritmetik ortalama)
SPOT = {"TP.DK.USD.A": "spot"}
FDVY = {"TP.FDVY01": "varlik", "TP.FDVY12": "yukumluluk", "TP.FDVY37": "net", "TP.FDVY40": "net_kisa",
        "TP.FDVY13": "nakdi_kredi", "TP.FDVY14": "yurtici_kredi", "TP.FDVY27": "yurtdisi_kredi", "TP.FDVY02": "mevduat"}


def seri(codes, bas, son, extra=""):
    url = f"{BASE}/series={'-'.join(codes)}&startDate={bas}&endDate={son}&type=json{extra}"
    r = requests.get(url, headers=H, timeout=60); r.raise_for_status()
    out = []
    for it in r.json().get("items", []):
        row = {"tarih": it.get("Tarih")}
        for c, n in codes.items():
            v = it.get(c.replace(".", "_")); row[n] = None if v in (None, "", "ND") else float(str(v).replace(",", "."))
        out.append(row)
    return out


def ay(rows):
    """EVDS aylık tarih 'YYYY-M' → {'YYYY-MM': satır}"""
    out = {}
    for r in rows:
        y, m = r["tarih"].split("-"); out[f"{y}-{int(m):02d}"] = r
    return out


def basabas_cek(son):
    D = ay(seri(MEVF, "01-01-2013", son, "&frequency=5&aggregationTypes=avg-avg-avg-avg"))
    P = ay(seri(PKA, "01-01-2013", son)); S = ay(seri(SPOT, "01-01-2013", son, "&frequency=5&aggregationTypes=avg"))
    rows = []
    for t in sorted(set(D) & set(P) & set(S)):
        d, e12, sp = D[t], P[t].get("pka12"), S[t].get("spot")
        if None in (d.get("tl3"), d.get("usd3"), e12, sp):
            continue
        tl3, usd3, k = d["tl3"], d["usd3"], e12 / sp
        rows.append({"tarih": t, "tl3": round(tl3, 2), "tl_top": None if d.get("tl_top") is None else round(d["tl_top"], 2),
                     "usd3": round(usd3, 2), "usd12": None if d.get("usd12") is None else round(d["usd12"], 2),
                     "pka12": round(e12, 2), "spot": round(sp, 4),
                     "bek_dep": round((k - 1) * 100, 1),                                   # PKA: beklenen 12 aylık kur artışı
                     "basabas_dep": round(((1 + tl3 / 100) / (1 + usd3 / 100) - 1) * 100, 1),  # faiz farkının karşıladığı kur artışı
                     "basabas_tl": round(((1 + usd3 / 100) * k - 1) * 100, 1),            # USD mevduata denk gelen TL faizi
                     "usd_getiri": round(((1 + tl3 / 100) / k - 1) * 100, 1)})            # TL mevduatın beklenen USD getirisi
    return rows


def main():
    if not KEY:
        print("  ~ EVDS_API_KEY yok — makro.json önbelleği kullanılacak"); return
    try:
        kayit = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    except Exception:
        kayit = {}
    son = dt.date.today().strftime("%d-%m-%Y"); ok = False
    try:
        rows = seri(FDVY, "01-01-2008", son)
        rows = [r for r in rows if r.get("net") is not None]
        for r in rows:   # EVDS aylık tarih 'YYYY-M' → 'YYYY-MM'
            y, m = r["tarih"].split("-"); r["tarih"] = f"{y}-{int(m):02d}"
        kayit["reel_sektor_fx"] = rows; ok = True
        L = rows[-1]
        print(f"  reel sektör döviz pozisyonu: {len(rows)} ay, son {L['tarih']}: net {L['net']/1e3:.1f} milyar USD (varlık {L['varlik']/1e3:.1f}, yükümlülük {L['yukumluluk']/1e3:.1f})")
    except Exception as e:
        print(f"  ~ reel sektör çekimi başarısız ({type(e).__name__}: {str(e)[:60]}) — önbellek kullanılacak")
    try:
        rows = basabas_cek(son)
        if rows:
            kayit["basabas"] = rows; ok = True
            L = rows[-1]
            print(f"  TL mevduat başabaş: {len(rows)} ay, son {L['tarih']}: TL 3 ay %{L['tl3']:.1f}, USD %{L['usd3']:.2f}, PKA 12 ay {L['pka12']:.2f} / kur {L['spot']:.2f} → beklenen artış %{L['bek_dep']:.1f}, başabaş artış %{L['basabas_dep']:.1f}, beklenen USD getiri %{L['usd_getiri']:.1f}")
    except Exception as e:
        print(f"  ~ başabaş çekimi başarısız ({type(e).__name__}: {str(e)[:60]}) — önbellek kullanılacak")
    if ok:
        kayit["updated"] = dt.datetime.now().strftime("%d.%m.%Y %H:%M")
        OUT.write_text(json.dumps(kayit, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
