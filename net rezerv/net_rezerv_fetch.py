#!/usr/bin/env python3
"""TCMB Rezervleri — EVDS3'ten çeker (analitik bilanço + resmî haftalık rezerv tablosu).

Günlük (iş günü, analitik bilanço, Bin TL → günün USD kuruyla milyon USD):
  TP.AB.A02  A.1 Dış Varlıklar               — brüt rezerv (ALTIN DAHİL; resmî rezerv varlıklarına yakın)
  TP.AB.A11  P.1a Dış Yükümlülükler
  TP.AB.A13  P.1ba Kamu ve Diğer Döviz Mevduatı
  TP.AB.A14  P.1bb Bankalar Döviz Mevduatı
  → Net rezerv (analitik bilanço) = A02 − A11 − A13 − A14   (dış varlıklar swap dövizini içerir → "swap dahil")
Haftalık (Cuma, resmî "Merkez Bankası Rezervleri" tablosu, milyon USD):
  TP.AB.C1 Altın · TP.AB.C2 Döviz · TP.AB.TOPLAM Toplam
Yardımcı: TP.DK.USD.A.YTL kur; TP.SWAPTEKTAR.* tek taraflı swap ihale stoku (eski hesap kolonları için).

DİKKAT (23.09.2026 düzeltmesi): A18 = "Bankalar Mevduatı", A20 = "Serbest Mevduat" — TL yükümlülük
kalemleridir; daha önce yanlışlıkla altın ve net rezerv sanılmıştı. Altın artık resmî haftalık
tablodan (günlük çerçeveye ileri doldurulur), net rezerv analitik bilanço formülünden gelir.

Çıktı: net_rezerv.xlsx — sayfa 1 günlük, sayfa "Haftalik" resmî rezerv tablosu. Birim: milyon USD.
"""
import os
import sys
from pathlib import Path

import pandas as pd
import requests

API_KEY = os.environ.get("EVDS_API_KEY", "") or os.environ.get("TCMB_API_KEY", "")
BASE = "https://evds3.tcmb.gov.tr/igmevdsms-dis"
GUNLUK = {
    "TP.AB.A02": "dis_varliklar_tl",
    "TP.AB.A11": "dis_yukumlulukler_tl",
    "TP.AB.A13": "kamu_mevduati_tl",
    "TP.AB.A14": "banka_mevduati_tl",
    "TP.DK.USD.A.YTL": "usdtry",
    "TP.SWAPTEKTAR.TOTALSTOKALIMYONLU": "swap_alim",
    "TP.SWAPTEKTAR.TOTALSTOKSATIMYONLU": "swap_satim",
}
HAFTALIK = {"TP.AB.C1": "altin_resmi", "TP.AB.C2": "doviz_resmi", "TP.AB.TOPLAM": "toplam_resmi"}


def fetch(codes, start, end):
    url = f"{BASE}/series={'-'.join(codes)}&startDate={start}&endDate={end}&type=json"
    for d in range(3):
        try:
            r = requests.get(url, headers={"key": API_KEY, "User-Agent": "Mozilla/5.0"}, timeout=60)
            r.raise_for_status()
            return r.json().get("items", [])
        except Exception as e:
            if d == 2:
                raise
            print(f"  EVDS deneme {d + 1} hatası ({type(e).__name__}) — yeniden")
    return []


def tablo(items, eslem):
    rows = []
    for it in items:
        row = {"tarih": it.get("Tarih")}
        for code, ad in eslem.items():
            v = it.get(code.replace(".", "_"))
            row[ad] = None if v in (None, "", "ND") else float(str(v).replace(",", "."))
        rows.append(row)
    df = pd.DataFrame(rows)
    df["tarih"] = pd.to_datetime(df["tarih"], format="%d-%m-%Y", errors="coerce")
    return (df.dropna(subset=["tarih"]).drop_duplicates(subset=["tarih"], keep="last")
              .sort_values("tarih").reset_index(drop=True))


def compute(df, haftalik):
    bs = ["dis_varliklar_tl", "dis_yukumlulukler_tl", "kamu_mevduati_tl", "banka_mevduati_tl"]
    aux = ["usdtry", "swap_alim", "swap_satim"]
    # Kur + swap stoku ileri doldurulur; bilanço kalemleri DOLDURULMAZ (her bilanço günü kendi kuruyla)
    df[aux] = df[aux].ffill()
    df = df.dropna(subset=bs + aux).reset_index(drop=True)
    for tl, usd in [("dis_varliklar_tl", "dis_varliklar"), ("dis_yukumlulukler_tl", "dis_yukumlulukler"),
                    ("kamu_mevduati_tl", "kamu_mevduati"), ("banka_mevduati_tl", "banka_mevduati")]:
        df[usd] = df[tl] / df["usdtry"] / 1000.0
    df["net_swap"] = df["swap_alim"] - df["swap_satim"]
    df["net_rezerv_swap_dahil"] = (df["dis_varliklar"] - df["dis_yukumlulukler"]
                                   - df["kamu_mevduati"] - df["banka_mevduati"])
    df["net_rezerv_swap_haric"] = df["net_rezerv_swap_dahil"] - df["net_swap"]
    df["net_ur"] = df["net_rezerv_swap_dahil"]          # analitik bilanço net rezervi
    df["brut_toplam"] = df["dis_varliklar"]             # altın dahil (çift sayım yok)
    # Resmî haftalık altın günlük çerçeveye: o güne kadar açıklanmış son Cuma değeri
    h = haftalik[["tarih", "altin_resmi"]].dropna().rename(columns={"altin_resmi": "altin"})
    df = pd.merge_asof(df.sort_values("tarih"), h.sort_values("tarih"), on="tarih", direction="backward")
    return df


def main():
    if not API_KEY:
        print("HATA: EVDS_API_KEY tanımlı değil", file=sys.stderr); sys.exit(1)
    print("TCMB rezerv verisi çekiliyor (EVDS3)...")
    bugun = pd.Timestamp.today().strftime("%d-%m-%Y")
    items = []
    for bas, son in [("01-01-2022", "31-12-2023"), ("01-01-2024", bugun)]:   # ~1000 satır sınırı
        parca = fetch(list(GUNLUK), bas, son)
        print(f"  günlük {bas} → {son}: {len(parca)} ham kayıt")
        items.extend(parca)
    gunluk = tablo(items, GUNLUK)
    haftalik = tablo(fetch(list(HAFTALIK), "01-01-2022", bugun), HAFTALIK)
    print(f"  resmî haftalık rezerv tablosu: {len(haftalik)} hafta (son {haftalik['tarih'].max().date()})")
    df = compute(gunluk, haftalik)
    print(f"  Hesaplandı: {len(df)} gün | {df['tarih'].min().date()} → {df['tarih'].max().date()}")

    out = Path(__file__).parent / "net_rezerv.xlsx"
    cols = ["tarih", "usdtry", "dis_varliklar", "altin", "brut_toplam", "net_ur",
            "dis_yukumlulukler", "kamu_mevduati", "banka_mevduati",
            "swap_alim", "swap_satim", "net_swap", "net_rezerv_swap_dahil", "net_rezerv_swap_haric",
            "dis_varliklar_tl", "dis_yukumlulukler_tl", "kamu_mevduati_tl", "banka_mevduati_tl"]
    with pd.ExcelWriter(out) as w:
        df[cols].to_excel(w, sheet_name="Gunluk", index=False)
        haftalik.to_excel(w, sheet_name="Haftalik", index=False)
    L, H = df.iloc[-1], haftalik.iloc[-1]
    print(f"  {L['tarih'].date()}: brüt (dış varlıklar, altın dahil) {L['dis_varliklar']/1000:,.1f} · "
          f"net rezerv {L['net_ur']/1000:,.1f} milyar USD")
    print(f"  resmî {H['tarih'].date()}: altın {H['altin_resmi']/1000:,.1f} + döviz {H['doviz_resmi']/1000:,.1f} "
          f"= {H['toplam_resmi']/1000:,.1f} milyar USD")
    print(f"Kaydedildi: {out.name}")
    print("BAŞARILI")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"HATA: {e}", file=sys.stderr); sys.exit(1)
