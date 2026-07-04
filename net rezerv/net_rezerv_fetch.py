"""
TCMB Net Rezerv Hesaplama — EVDS3 API'sinden çeker.
=====================================================
Seriler (günlük / iş günü):
  TP.AB.A02                          Dış Varlıklar            (Bin TL)
  TP.AB.A11                          Dış Yükümlülükler        (Bin TL)
  TP.AB.A13                          Kamu Mevduatı            (Bin TL)
  TP.AB.A14                          Bankalar Mevduatı        (Bin TL)
  TP.DK.USD.A.YTL                    USD/TRY alış kuru
  TP.SWAPTEKTAR.TOTALSTOKALIMYONLU   Swap (alım yönlü)        (mn USD)
  TP.SWAPTEKTAR.TOTALSTOKSATIMYONLU  Swap (satım yönlü)       (mn USD)

Hesap mantığı:
  - TL kalemleri USD'ye çevrilir:  USD_mn = BinTL / USDTRY / 1000
  - Net Swap = Swap Alım − Swap Satım            (kullanıcı tercihi)
  - Net Rezerv (Swap Dahil) = Varlıklar − Yükümlülükler − Kamu Mev. − Banka Mev.
        (Dış Varlıklar swap kaynaklı dövizi zaten içerir → "swap dahil".)
  - Net Rezerv (Swap Hariç) = (Swap Dahil) − Net Swap
        (Net swap etkisi çıkarılır → asıl aranan "swap hariç net rezerv".)

Birim: milyon USD.
"""
import os
import sys
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

API_KEY = os.environ.get("EVDS_API_KEY", "")
BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis"

# EVDS seri kodu -> iç (düz) sütun adı
SERIES = {
    "TP.AB.A02": "dis_varliklar_tl",
    "TP.AB.A11": "dis_yukumlulukler_tl",
    "TP.AB.A13": "kamu_mevduati_tl",
    "TP.AB.A14": "banka_mevduati_tl",
    "TP.DK.USD.A.YTL": "usdtry",
    "TP.SWAPTEKTAR.TOTALSTOKALIMYONLU": "swap_alim",
    "TP.SWAPTEKTAR.TOTALSTOKSATIMYONLU": "swap_satim",
}


def fetch_items(start_date="01-01-2020", end_date=None, retries=3):
    """Tüm serileri tek istekte (tarih hizalı) çeker. EVDS3 en yeni ~1000 satırı döner."""
    if end_date is None:
        end_date = datetime.now().strftime("%d-%m-%Y")
    series_str = "-".join(SERIES.keys())
    url = (f"{BASE_URL}/series={series_str}"
           f"&startDate={start_date}&endDate={end_date}&type=json")
    headers = {"key": API_KEY, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            print(f"  EVDS isteği (deneme {attempt})...")
            r = requests.get(url, headers=headers, timeout=45)
            r.raise_for_status()
            data = r.json()
            if "items" not in data:
                raise ValueError(f"Beklenmeyen yanıt: {str(data)[:200]}")
            return data["items"]
        except Exception as e:
            last_err = e
            print(f"    başarısız: {e}")
    raise RuntimeError(f"EVDS verisi çekilemedi: {last_err}")


def to_dataframe(items):
    rows = []
    for it in items:
        row = {"tarih": it.get("Tarih")}
        for code, name in SERIES.items():
            key = code.replace(".", "_")
            v = it.get(key)
            row[name] = None if v in (None, "") else float(str(v).replace(",", "."))
        rows.append(row)
    df = pd.DataFrame(rows)
    df["tarih"] = pd.to_datetime(df["tarih"], format="%d-%m-%Y", errors="coerce")
    return df.dropna(subset=["tarih"]).sort_values("tarih").reset_index(drop=True)


def compute(df):
    bs_cols = ["dis_varliklar_tl", "dis_yukumlulukler_tl",
               "kamu_mevduati_tl", "banka_mevduati_tl"]
    aux_cols = ["usdtry", "swap_alim", "swap_satim"]
    # Yardımcı serileri (kur + swap stoku) ileri-doldur; bilanço kalemlerini DOLDURMA.
    # Böylece her bilanço tarihi KENDİ günün kuruyla USD'ye çevrilir (kur/tarih uyumsuzluğu
    # ve henüz yayımlanmamış bilançodan kaynaklı sahte son satır önlenir).
    df[aux_cols] = df[aux_cols].ffill()
    df = df.dropna(subset=bs_cols + aux_cols).reset_index(drop=True)

    # TL kalemleri -> milyon USD
    for tl, usd in [("dis_varliklar_tl", "dis_varliklar"),
                    ("dis_yukumlulukler_tl", "dis_yukumlulukler"),
                    ("kamu_mevduati_tl", "kamu_mevduati"),
                    ("banka_mevduati_tl", "banka_mevduati")]:
        df[usd] = df[tl] / df["usdtry"] / 1000.0

    df["net_swap"] = df["swap_alim"] - df["swap_satim"]
    df["net_rezerv_swap_dahil"] = (df["dis_varliklar"] - df["dis_yukumlulukler"]
                                   - df["kamu_mevduati"] - df["banka_mevduati"])
    df["net_rezerv_swap_haric"] = df["net_rezerv_swap_dahil"] - df["net_swap"]
    return df


def main():
    print("TCMB Net Rezerv verisi çekiliyor (EVDS3)...")
    items = fetch_items()
    print(f"  {len(items)} ham kayıt alındı")
    df = to_dataframe(items)
    df = compute(df)
    print(f"  Hesaplandı: {len(df)} tam kayıt | "
          f"{df['tarih'].min().date()} → {df['tarih'].max().date()}")

    out = Path(__file__).parent / "net_rezerv.xlsx"
    cols = ["tarih", "usdtry",
            "dis_varliklar", "dis_yukumlulukler", "kamu_mevduati", "banka_mevduati",
            "swap_alim", "swap_satim", "net_swap",
            "net_rezerv_swap_dahil", "net_rezerv_swap_haric",
            "dis_varliklar_tl", "dis_yukumlulukler_tl", "kamu_mevduati_tl", "banka_mevduati_tl"]
    df[cols].to_excel(out, index=False)

    last = df.iloc[-1]
    print(f"\n  Son tarih: {last['tarih'].date()} | USDTRY={last['usdtry']:.4f}")
    print(f"  Dış Varlıklar         : {last['dis_varliklar']:>12,.0f} mn USD")
    print(f"  Dış Yükümlülükler     : {last['dis_yukumlulukler']:>12,.0f} mn USD")
    print(f"  Kamu Mevduatı         : {last['kamu_mevduati']:>12,.0f} mn USD")
    print(f"  Banka Mevduatı        : {last['banka_mevduati']:>12,.0f} mn USD")
    print(f"  Net Swap (Alım−Satım) : {last['net_swap']:>12,.0f} mn USD")
    print(f"  → Net Rezerv (Swap Dahil) : {last['net_rezerv_swap_dahil']:>12,.0f} mn USD")
    print(f"  → Net Rezerv (Swap Hariç) : {last['net_rezerv_swap_haric']:>12,.0f} mn USD")
    print(f"\nKaydedildi: {out.name}")
    print("BAŞARILI")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)
