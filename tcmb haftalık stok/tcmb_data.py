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
import tcmb
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
    # Yurt Ici Yerlesikler — yalnizca Hisse Senedi + DIBS (Kesin Alim)
    "TP.MKNETHAR.M7":  "Yurt Ici Hisse",
    "TP.MKNETHAR.M8":  "Yurt Ici DIBS",
    # Yurt Disi Yerlesikler — yalnizca Hisse Senedi + DIBS (Kesin Alim)
    "TP.MKNETHAR.M1":  "Yurt Disi Hisse",
    "TP.MKNETHAR.M2":  "Yurt Disi DIBS",
}

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False


# ── Veri Cekme ──────────────────────────────────────────────

def fetch_all_series(start: str = "01-01-2010") -> dict[str, pd.DataFrame]:
    """EVDS3 API'sinden requests ile çeker. (Eskiden 'tcmb' paketi kullanılıyordu
    ama asılı kalabiliyordu; artık tüm seriler tek istekte, timeout'lu çekiliyor.)"""
    import requests
    key = os.environ.get("TCMB_API_KEY") or os.environ.get("EVDS_API_KEY", "")
    end = datetime.now().strftime("%d-%m-%Y")
    url = (f"https://evds3.tcmb.gov.tr/igmevdsms-dis/series={'-'.join(SERIES.keys())}"
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
    for code, name in SERIES.items():
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

    ax.set_title(f"Son {n_weeks} Hafta Duzey / Seviye - EVDS (Milyon USD)", fontsize=13, fontweight="bold", pad=20)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "tablo_son_haftalar.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  tablo_son_haftalar.png")


# ── 2) Haftalik Net Degisim Histogrami ──────────────────────

def make_histogram(all_data: dict[str, pd.DataFrame], n_weeks: int = 20):
    """Son n hafta haftalik net degisim bar chart."""

    # Son n haftayi al - en son tarihi referans al
    ref_dates = []
    for code, df in all_data.items():
        ref_dates.extend(df["date"].tail(n_weeks).tolist())
    if not ref_dates:
        return

    # Tum serilerin son n haftasini birlestir
    frames = []
    for code, df in all_data.items():
        recent = df.tail(n_weeks).copy()
        recent["series"] = SERIES[code]
        frames.append(recent)

    combined = pd.concat(frames, ignore_index=True)

    # Yurt Ici ve Yurt Disi toplam
    combined["group"] = combined["series"].apply(lambda x: "Yurt Ici" if "Ici" in x else "Yurt Disi")
    pivot = combined.groupby(["date", "group"])["change"].sum().unstack(fill_value=0)

    fig, ax = plt.subplots(figsize=(14, 6))
    dates = pivot.index
    x = range(len(dates))
    width = 0.35

    if "Yurt Disi" in pivot.columns:
        bars1 = ax.bar([i - width/2 for i in x], pivot["Yurt Disi"], width,
                       label="Yurt Disi Toplam", color="#1976D2", alpha=0.85)
    if "Yurt Ici" in pivot.columns:
        bars2 = ax.bar([i + width/2 for i in x], pivot["Yurt Ici"], width,
                       label="Yurt Ici Toplam", color="#FF8F00", alpha=0.85)

    ax.axhline(y=0, color="black", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([d.strftime("%d/%m") for d in dates], rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Net Degisim (Milyon USD)", fontsize=11)
    ax.set_title("Haftalik Net Degisim - Yurt Ici vs Yurt Disi Toplam", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "histogram_haftalik.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  histogram_haftalik.png")


# ── 3) Kumulatif Time Series (yil basi = 0) ────────────────

def make_cumulative_ts(all_data: dict[str, pd.DataFrame]):
    """
    Her seri icin: yil basinda 0'dan baslayan kumulatif degisim.
    2024, 2025, 2026 ayri cizgiler + diger yillar ortalama.
    Yurt Ici ve Yurt Disi ayri ayri 2 grafik.
    """
    groups = {
        "Yurt Disi": ["TP.MKNETHAR.M1", "TP.MKNETHAR.M2"],
        "Yurt Ici":  ["TP.MKNETHAR.M7", "TP.MKNETHAR.M8"],
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


# ── Ana Calisma ─────────────────────────────────────────────

def run():
    print("=" * 60)
    print("TCMB Menkul Kiymet Portfoyu Veri Analizi")
    print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Veri cek
    print("\n[1/4] Veriler cekiliyor...")
    all_data = fetch_all_series()
    if not all_data:
        print("Hic veri cekilemedi!")
        return

    # Ham veri kaydet
    for code, df in all_data.items():
        name = SERIES[code].replace(" ", "_")
        df.to_csv(OUTPUT_DIR / f"raw_{name}.csv", index=False)

    # Grafikler
    print("\n[2/4] Son hafta tablosu...")
    make_recent_table(all_data, n_weeks=5)

    print("\n[3/4] Histogram...")
    make_histogram(all_data, n_weeks=20)

    print("\n[4/4] Kumulatif time series...")
    make_cumulative_ts(all_data)

    print(f"\n{'=' * 60}")
    print(f"Tamamlandi! -> {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run()
