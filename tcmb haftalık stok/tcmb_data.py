"""
TCMB EVDS API - Yurt Disi/Ici Yerlesikler Menkul Kiymet Portfoyu
Haftalik otomatik calisma icin tasarlanmistir.

Ciktilar:
  1. Son 5 hafta net degisim tablosu (PNG)
  2. Haftalik net degisim histogrami (bar chart, PNG)
  3. Yil basinda 0'dan baslayan kumulatif time series (2024/2025/2026 + diger yillar ort.)
"""

import sys
import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

# --- Ayarlar ---
os.environ.setdefault("TCMB_API_KEY", os.environ.get("EVDS_API_KEY", ""))
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

SERIES = {
    # HEPSI YURT DISI YERLESIKLER'in Turkiye menkul kiymet yatirimidir.
    # M1/M2 = STOK (Duzey/portfoy seviyesi), M7/M8 = HAFTALIK NET DEGISIM (akim).
    "TP.MKNETHAR.M1":  "Hisse Stok",
    "TP.MKNETHAR.M2":  "DIBS Stok",
    "TP.MKNETHAR.M7":  "Hisse Degisim",
    "TP.MKNETHAR.M8":  "DIBS Degisim",
}

# Haftalik NET YABANCI HAREKETI bilesenleri (hepsi akim, Milyon USD).
# hareket.xlsx'e yazilir; dashboard'daki 5 grafigin kaynagi budur.
FLOW_SERIES = {
    "TP.MKNETHAR.M7":  "hisse",                  # 2.1.1 Hisse Senedi
    "TP.MKNETHAR.M8":  "dibs_kesin",             # 2.1.2 DIBS (Kesin Alim)
    "TP.MKNETHAR.M9":  "dibs_tersrepo",          # 4.1 DIBS (Ters Repo)
    "TP.MKNETHAR.M10": "dibs_teminat",           # 4.2 DIBS (Teminat Alim)
    "TP.MKNETHAR.M11": "dibs_odunc",             # 4.3 DIBS (Odunc Alim)
    "TP.MKNETHAR.M12": "ost",                    # 2.1.3 Genel Yonetim Disi Borclanma Senetleri
    "TP.MKNETHAR.M23": "euro_genel_yonetim",     # 2.2.1 Genel Yonetim Ihraclari (Eurobond)
    "TP.MKNETHAR.M24": "euro_finansal_olmayan",  # 2.2.2 Finansal Olmayan Kurulus Ihraclari
    "TP.MKNETHAR.M25": "euro_banka",             # 2.2.3 Banka Ihraclari
    "TP.MKNETHAR.M26": "euro_diger_finansal",    # 2.2.4 Diger Finansal Kurulus Ihraclari
}

ALL_CODES = list(dict.fromkeys(list(SERIES) + list(FLOW_SERIES)))

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False


# ── Veri Cekme ──────────────────────────────────────────────

def fetch_all_series(start: str = "01-01-2010") -> dict[str, pd.DataFrame]:
    """EVDS3 API'sinden requests ile çeker. (Eskiden 'tcmb' paketi kullanılıyordu
    ama asılı kalabiliyordu; artık tüm seriler tek istekte, timeout'lu çekiliyor.)"""
    import requests
    key = os.environ.get("TCMB_API_KEY") or os.environ.get("EVDS_API_KEY", "")
    end = datetime.now().strftime("%d-%m-%Y")
    url = (f"https://evds3.tcmb.gov.tr/igmevdsms-dis/series={'-'.join(ALL_CODES)}"
           f"&startDate={start}&endDate={end}&type=json")
    headers = {"key": key, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    all_data = {}
    try:
        r = requests.get(url, headers=headers, timeout=45)
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception as e:
        print(f"  EVDS HATA: {e}")
        return all_data
    for code in ALL_CODES:
        name = SERIES.get(code) or FLOW_SERIES.get(code)
        k = code.replace(".", "_")
        rows = []
        for it in items:
            v = it.get(k)
            if v in (None, ""):
                continue
            t = pd.to_datetime(it.get("Tarih"), format="%d-%m-%Y", errors="coerce")
            if pd.notna(t):
                try:
                    rows.append((t, float(str(v).replace(",", "."))))
                except (ValueError, TypeError):
                    pass
        if not rows:
            print(f"  {name}: bos")
            continue
        df = (pd.DataFrame(rows, columns=["date", "value"])
              .drop_duplicates("date").sort_values("date").reset_index(drop=True))
        df["change"] = df["value"].diff()
        all_data[code] = df
        print(f"  {name}: {len(df)} satir")
    return all_data


# ── 1) Son 5 Hafta Net Degisim Tablosu ─────────────────────

def make_recent_table(all_data: dict[str, pd.DataFrame], n_weeks: int = 5):
    """Son n hafta net degisim tablosu - PNG olarak kaydeder."""

    # Her seri icin son n haftayi al
    rows = {}
    date_cols = []
    for code, df in all_data.items():
        recent = df.tail(n_weeks)
        name = SERIES[code]
        for _, row in recent.iterrows():
            d = row["date"].strftime("%d/%m")
            if d not in date_cols:
                date_cols.append(d)
            if name not in rows:
                rows[name] = {}
            rows[name][d] = row["value"]  # net degisim degil, EVDS Duzey (seviye)

    if not rows:
        return

    # DataFrame olustur
    tbl = pd.DataFrame(rows).T
    tbl = tbl[date_cols]  # tarih sirasiyla

    # Tablo gorseli
    fig, ax = plt.subplots(figsize=(max(8, len(date_cols) * 1.8), len(rows) * 0.55 + 1.5))
    ax.axis("off")

    cell_text = []
    cell_colors = []
    for idx, row_name in enumerate(tbl.index):
        row_vals = []
        row_colors = []
        for col in tbl.columns:
            val = tbl.loc[row_name, col]
            if pd.isna(val):
                row_vals.append("-")
                row_colors.append("#FFFFFF")
            else:
                row_vals.append(f"{val:,.0f}")
                # Seviye tablosu: negatif pozisyon kirmizi, digerleri notr
                row_colors.append("#FFCDD2" if val < 0 else "#FFFFFF")
        cell_text.append(row_vals)
        cell_colors.append(row_colors)

    table = ax.table(
        cellText=cell_text,
        rowLabels=list(tbl.index),
        colLabels=list(tbl.columns),
        cellColours=cell_colors,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.6)

    # Header renkleri
    for j in range(len(tbl.columns)):
        table[0, j].set_facecolor("#37474F")
        table[0, j].set_text_props(color="white", fontweight="bold")
    for i in range(len(tbl.index)):
        table[i + 1, -1].set_text_props(fontweight="bold")

    ax.set_title(f"Yurt Disi Yerlesikler - Son {n_weeks} Hafta Stok ve Haftalik Net Akim (Milyon USD)", fontsize=12, fontweight="bold", pad=20)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "tablo_son_haftalar.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  tablo_son_haftalar.png")


# ── 2) Haftalik Net Degisim Histogrami ──────────────────────

def make_histogram(all_data: dict[str, pd.DataFrame], n_weeks: int = 20):
    """Son n hafta haftalik NET AKIM (yurt disi yerlesiklerin Hisse & DIBS'e girisi).
    M7/M8 serilerinin 'value' degeri zaten haftalik net akimdir."""
    akim = {"TP.MKNETHAR.M7": "Hisse", "TP.MKNETHAR.M8": "DİBS"}
    frames = []
    for code, lbl in akim.items():
        if code in all_data:
            r = all_data[code].tail(n_weeks).copy()
            r["enstruman"] = lbl
            frames.append(r[["date", "value", "enstruman"]])
    if not frames:
        return
    combined = pd.concat(frames, ignore_index=True)
    pivot = combined.pivot_table(index="date", columns="enstruman", values="value", fill_value=0).sort_index()

    fig, ax = plt.subplots(figsize=(14, 6))
    x = range(len(pivot.index))
    width = 0.38
    if "Hisse" in pivot.columns:
        ax.bar([i - width / 2 for i in x], pivot["Hisse"], width, label="Hisse Senedi", color="#4CAF50", alpha=0.85)
    if "DİBS" in pivot.columns:
        ax.bar([i + width / 2 for i in x], pivot["DİBS"], width, label="DİBS", color="#1976D2", alpha=0.85)
    ax.axhline(y=0, color="black", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([d.strftime("%d/%m") for d in pivot.index], rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Net Akim (Milyon USD)", fontsize=11)
    ax.set_title("Yurt Disi Yerlesikler - Haftalik Net Akim (Milyon USD)", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "histogram_haftalik.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  histogram_haftalik.png")


# ── 3) Kumulatif Time Series (yil basi = 0) ────────────────

def make_cumulative_ts(all_data: dict[str, pd.DataFrame]):
    """
    Yalnizca STOK serileri (Hisse Stok, DIBS Stok) icin: yil basindan
    kumulatif seviye degisimi. 2024/2025/2026 + diger yillar ort.
    (Degisim/akim serileri M7/M8 zaten haftalik akim oldugu icin kumulatif alinmaz.)
    """
    groups = {
        "Stok": ["TP.MKNETHAR.M1", "TP.MKNETHAR.M2"],
    }

    for group_name, codes in groups.items():
        for code in codes:
            if code not in all_data:
                continue
            df = all_data[code].copy()
            name = SERIES[code]

            df["year"] = df["date"].dt.year
            df["week"] = df["date"].dt.isocalendar().week.astype(int)

            highlight_years = [2024, 2025, 2026]
            colors = {2024: "#2196F3", 2025: "#FF5722", 2026: "#4CAF50", "Diger Yillar Ort.": "#9E9E9E"}
            linestyles = {2024: "-", 2025: "-", 2026: "-", "Diger Yillar Ort.": "--"}

            fig, ax = plt.subplots(figsize=(14, 6))

            for y in highlight_years:
                ydf = df[df["year"] == y].copy()
                if ydf.empty:
                    continue
                # Yil basindaki degere gore 0'la
                base = ydf["value"].iloc[0]
                ydf["cumulative"] = ydf["value"] - base
                ax.plot(ydf["week"], ydf["cumulative"], label=str(y),
                        color=colors[y], linewidth=2.2, alpha=0.9)

            # Diger yillar ortalama
            other = df[~df["year"].isin(highlight_years)].copy()
            if not other.empty:
                # Her yil icin kumulatif hesapla, sonra hafta bazinda ortalama al
                cum_frames = []
                for y, ydf in other.groupby("year"):
                    base = ydf["value"].iloc[0]
                    ydf = ydf.copy()
                    ydf["cumulative"] = ydf["value"] - base
                    cum_frames.append(ydf[["week", "cumulative"]])
                if cum_frames:
                    all_cum = pd.concat(cum_frames)
                    avg_cum = all_cum.groupby("week")["cumulative"].mean().reset_index()
                    ax.plot(avg_cum["week"], avg_cum["cumulative"], label="Diger Yillar Ort.",
                            color=colors["Diger Yillar Ort."], linewidth=1.8, linestyle="--", alpha=0.8)

            ax.axhline(y=0, color="black", linewidth=0.8, alpha=0.5)
            ax.set_title(f"{name}\nYil Basindan Kumulatif Degisim (Milyon USD)", fontsize=13, fontweight="bold")
            ax.set_xlabel("Hafta", fontsize=11)
            ax.set_ylabel("Kumulatif Degisim (Milyon USD)", fontsize=11)
            ax.legend(fontsize=10)
            ax.grid(True, alpha=0.3)
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
            plt.tight_layout()

            safe = name.replace(" ", "_").replace(".", "")
            plt.savefig(OUTPUT_DIR / f"kumulatif_{safe}.png", dpi=150, bbox_inches="tight")
            plt.close()
            print(f"  kumulatif_{safe}.png")


# ── 4) Net Yabanci Hareketi (hareket.xlsx) ──────────────────

def make_hareket(all_data: dict[str, pd.DataFrame]):
    """Akim serilerini tek tabloda birlestirir ve turetilmis kolonlari ekler:
    dibs_dolayli = ters repo + teminat + odunc
    eurobond     = genel yonetim + finansal olmayan + banka + diger finansal
    menkul_toplam= hisse + dibs_kesin + dibs_dolayli + ost   (Eurobond haric)
    toplam       = menkul_toplam + eurobond
    """
    cols = {}
    for code, name in FLOW_SERIES.items():
        if code in all_data:
            cols[name] = all_data[code].set_index("date")["value"]
    if not cols:
        print("  hareket: akim verisi yok")
        return
    h = pd.DataFrame(cols).sort_index()
    h = h.dropna(subset=["hisse", "dibs_kesin"], how="all")
    h["dibs_dolayli"] = h[["dibs_tersrepo", "dibs_teminat", "dibs_odunc"]].sum(axis=1, min_count=1)
    h["eurobond"] = h[["euro_genel_yonetim", "euro_finansal_olmayan",
                       "euro_banka", "euro_diger_finansal"]].sum(axis=1, min_count=1)
    h["menkul_toplam"] = h[["hisse", "dibs_kesin", "dibs_dolayli", "ost"]].sum(axis=1, min_count=1)
    h["toplam"] = h[["menkul_toplam", "eurobond"]].sum(axis=1, min_count=1)
    out = h.reset_index().rename(columns={"date": "tarih"})
    order = ["tarih", "hisse", "dibs_kesin", "dibs_dolayli", "ost", "eurobond",
             "menkul_toplam", "toplam", "dibs_tersrepo", "dibs_teminat", "dibs_odunc",
             "euro_genel_yonetim", "euro_finansal_olmayan", "euro_banka", "euro_diger_finansal"]
    out = out[[c for c in order if c in out.columns]]
    out.to_excel(OUTPUT_DIR / "hareket.xlsx", sheet_name="Haftalik", index=False)
    L = out.iloc[-1]
    print(f"  hareket.xlsx: {len(out)} hafta | son {L['tarih'].date()}")
    print(f"    hisse={L['hisse']:,.0f}  dibs_kesin={L['dibs_kesin']:,.0f}  "
          f"dibs_dolayli={L['dibs_dolayli']:,.0f}  ost={L['ost']:,.0f}  "
          f"eurobond={L['eurobond']:,.0f}  TOPLAM={L['toplam']:,.0f}")


# ── Ana Calisma ─────────────────────────────────────────────

def run():
    print("=" * 60)
    print("TCMB Menkul Kiymet Portfoyu Veri Analizi")
    print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Veri cek
    print("\n[1/5] Veriler cekiliyor...")
    all_data = fetch_all_series()
    if not all_data:
        print("Hic veri cekilemedi!")
        return

    # Ham veri kaydet (yalnizca cekirdek stok/akim serileri)
    for code in SERIES:
        if code in all_data:
            name = SERIES[code].replace(" ", "_")
            all_data[code].to_csv(OUTPUT_DIR / f"raw_{name}.csv", index=False)

    core = {c: d for c, d in all_data.items() if c in SERIES}

    # Grafikler
    print("\n[2/5] Son hafta tablosu...")
    make_recent_table(core, n_weeks=5)

    print("\n[3/5] Histogram...")
    make_histogram(core, n_weeks=20)

    print("\n[4/5] Kumulatif time series...")
    make_cumulative_ts(core)

    print("\n[5/5] Net yabanci hareketi (hareket.xlsx)...")
    make_hareket(all_data)

    print(f"\n{'=' * 60}")
    print(f"Tamamlandi! -> {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run()
