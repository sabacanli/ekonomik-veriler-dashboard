#!/usr/bin/env python3
"""Günün rakamları → site/data/piyasa.json (bültenin "Günün Rakamları" tablosu ve gündem sayfası).

Kaynak: TradingView tarayıcı uç noktası (tek POST, gecikmeli/kapanış verisi; anahtar gerektirmez):
  kur (USD/TRY, EUR/TRY), BIST 100, Türkiye 2-5-10 yıllık gösterge tahvil faizleri, ABD 10 yıllık,
  dolar endeksi (DXY), Brent, altın (ons). Yedek: yfinance (tahvil faizleri hariç).
TLREF: EVDS (TP.BISTTLREF.ORAN) — EVDS_API_KEY varsa eklenir.
Her satır: {ad, deger, degisim (mutlak), degisim_pct, hafta_pct, ay_pct, ytd_pct, birim, tur ('fiyat'|'faiz'), zaman}
Faiz satırlarında ayrıca hafta_puan (haftalık mutlak değişim, puan) — haftalık bülten tablosu için.
Sabah koşusunda değerler bir önceki günün kapanışıdır; 'zaman' TR saatiyle son bar zamanıdır.
Kullanım: python piyasa/piyasa_fetch.py
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "site" / "data" / "piyasa.json"
TR = dt.timezone(dt.timedelta(hours=3))
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}

# (ad, TradingView sembolü, yfinance sembolü, ondalık, tür, birim)
SATIRLAR = [
    ("USD/TRY", "FX_IDC:USDTRY", "USDTRY=X", 4, "fiyat", ""),
    ("EUR/TRY", "FX_IDC:EURTRY", "EURTRY=X", 4, "fiyat", ""),
    ("BIST 100", "BIST:XU100", "XU100.IS", 0, "fiyat", "puan"),
    ("2 yıllık gösterge tahvil", "TVC:TR02Y", None, 2, "faiz", "%"),
    ("5 yıllık tahvil", "TVC:TR05Y", None, 2, "faiz", "%"),
    ("10 yıllık tahvil", "TVC:TR10Y", None, 2, "faiz", "%"),
    ("ABD 10 yıllık tahvil", "TVC:US10Y", "^TNX", 3, "faiz", "%"),
    ("Dolar endeksi (DXY)", "TVC:DXY", "DX-Y.NYB", 2, "fiyat", ""),
    ("Brent petrol", "FX:UKOIL", "BZ=F", 2, "fiyat", "USD/varil"),
    ("Altın", "OANDA:XAUUSD", "GC=F", 1, "fiyat", "USD/ons"),
]


def tradingview():
    r = requests.post("https://scanner.tradingview.com/global/scan", headers={**UA, "Content-Type": "application/json"},
                      json={"symbols": {"tickers": [s[1] for s in SATIRLAR]},
                            "columns": ["close", "change", "change_abs", "time", "Perf.W", "Perf.1M", "Perf.YTD"]}, timeout=30)
    r.raise_for_status()
    veri = {x["s"]: x["d"] for x in r.json().get("data", [])}
    out = {}
    for ad, tv, _, ond, tur, birim in SATIRLAR:
        d = veri.get(tv)
        if not d or d[0] is None:
            continue
        zaman = dt.datetime.fromtimestamp(d[3], TR).strftime("%d.%m %H:%M") if d[3] else None
        pct = lambda v: None if v is None else round(float(v), 2)
        son = float(d[0])
        out[ad] = {"deger": round(son, ond), "degisim": None if d[2] is None else round(float(d[2]), ond),
                   "degisim_pct": pct(d[1]), "hafta_pct": pct(d[4]), "ay_pct": pct(d[5]), "ytd_pct": pct(d[6]),
                   "zaman": zaman, "kaynak": "TradingView"}
        if tur == "faiz" and d[4] is not None:
            out[ad]["hafta_puan"] = round(son - son / (1 + float(d[4]) / 100), ond)
    return out


def yfinance_yedek(eksik):
    import warnings
    warnings.filterwarnings("ignore")
    import yfinance as yf
    out = {}
    for ad, _, ys, ond, tur, birim in SATIRLAR:
        if ad not in eksik or not ys:
            continue
        try:
            h = yf.Ticker(ys).history(period="10d", interval="1d").dropna(subset=["Close"])
            if len(h) < 2:
                continue
            son, onceki = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
            uzun = yf.Ticker(ys).history(period="1y", interval="1d").dropna(subset=["Close"])["Close"]
            def perf(n_gun=None, yilbasi=False):
                try:
                    if yilbasi:
                        ge = uzun[uzun.index.year < uzun.index[-1].year]
                        taban = float(ge.iloc[-1]) if len(ge) else None
                    else:
                        taban = float(uzun.iloc[-1 - n_gun]) if len(uzun) > n_gun else None
                    return None if not taban else round((son / taban - 1) * 100, 2)
                except Exception:
                    return None
            out[ad] = {"deger": round(son, ond), "degisim": round(son - onceki, ond),
                       "degisim_pct": round((son / onceki - 1) * 100, 2),
                       "hafta_pct": perf(5), "ay_pct": perf(21), "ytd_pct": perf(yilbasi=True),
                       "zaman": h.index[-1].strftime("%d.%m") + " kapanış", "kaynak": "Yahoo Finance"}
            if tur == "faiz" and out[ad]["hafta_pct"] is not None:
                out[ad]["hafta_puan"] = round(son - son / (1 + out[ad]["hafta_pct"] / 100), ond)
        except Exception as e:
            print(f"  ~ yfinance {ad}: {type(e).__name__}")
    return out


def tlref():
    key = os.environ.get("EVDS_API_KEY", "") or os.environ.get("TCMB_API_KEY", "")
    if not key:
        return None
    bas = (dt.datetime.now(TR) - dt.timedelta(days=400)).strftime("%d-%m-%Y")
    son = dt.datetime.now(TR).strftime("%d-%m-%Y")
    r = requests.get(f"https://evds3.tcmb.gov.tr/igmevdsms-dis/series=TP.BISTTLREF.ORAN&startDate={bas}&endDate={son}&type=json",
                     headers={"key": key, **UA}, timeout=30)
    r.raise_for_status()
    items = [(it["Tarih"], float(it["TP_BISTTLREF_ORAN"])) for it in r.json().get("items", [])
             if it.get("TP_BISTTLREF_ORAN") not in (None, "", "ND")]
    if len(items) < 2:
        return None
    (t1, v1), (t0, v0) = items[-1], items[-2]
    def geri(n):
        return items[-1 - n][1] if len(items) > n else None
    yil = t1[-4:]
    onceki_yil = [v for t, v in items if t[-4:] < yil]
    hafta = geri(5)
    return {"deger": round(v1, 2), "degisim": round(v1 - v0, 2), "degisim_pct": None,
            "hafta_pct": None if not hafta else round((v1 / hafta - 1) * 100, 2),
            "hafta_puan": None if not hafta else round(v1 - hafta, 2),
            "ay_pct": None if not geri(21) else round((v1 / geri(21) - 1) * 100, 2),
            "ytd_pct": None if not onceki_yil else round((v1 / onceki_yil[-1] - 1) * 100, 2),
            "zaman": t1[:5], "kaynak": "TCMB EVDS"}


def main():
    print("Günün rakamları çekiliyor...")
    veri = {}
    try:
        veri = tradingview()
        print(f"  TradingView: {len(veri)}/{len(SATIRLAR)} satır")
    except Exception as e:
        print(f"  ~ TradingView başarısız ({type(e).__name__}: {str(e)[:60]})")
    eksik = [s[0] for s in SATIRLAR if s[0] not in veri]
    if eksik:
        try:
            y = yfinance_yedek(eksik)
            print(f"  yfinance yedek: {len(y)} satır ({', '.join(eksik)})")
            veri.update(y)
        except Exception as e:
            print(f"  ~ yfinance kullanılamadı ({type(e).__name__})")
    satirlar = []
    for ad, _, _, ond, tur, birim in SATIRLAR:
        if ad in veri:
            satirlar.append({"ad": ad, "tur": tur, "birim": birim, "ondalik": ond, **veri[ad]})
    try:
        t = tlref()
        if t:
            satirlar.insert(3, {"ad": "TLREF (gecelik)", "tur": "faiz", "birim": "%", "ondalik": 2, **t})
            print("  TLREF: eklendi")
    except Exception as e:
        print(f"  ~ TLREF alınamadı ({type(e).__name__})")
    if not satirlar:
        print("HATA: hiçbir piyasa verisi alınamadı", file=sys.stderr)
        sys.exit(1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updated": dt.datetime.now(TR).strftime("%d.%m.%Y %H:%M"), "satirlar": satirlar},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for s in satirlar:
        dg = "" if s["degisim"] is None else f" ({s['degisim']:+.{s['ondalik']}f}" + (f" · {s['degisim_pct']:+.2f}%)" if s["degisim_pct"] is not None else ")")
        print(f"  {s['ad']:26s} {s['deger']:>12,.{s['ondalik']}f} {s['birim']:9s}{dg}  {s['zaman']}  [{s['kaynak']}]")
    print(f"Kaydedildi: {OUT.relative_to(BASE)}")
    print("BAŞARILI")


if __name__ == "__main__":
    main()
