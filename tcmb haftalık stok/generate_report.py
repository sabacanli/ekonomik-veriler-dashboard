"""
TCMB Menkul Kiymet Portfoyu - Ust Yonetim Raporu (PDF)
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
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

sys.stdout.reconfigure(line_buffering=True)

os.environ.setdefault("TCMB_API_KEY", os.environ.get("EVDS_API_KEY", ""))
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Turkce font kaydi ──
FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"
pdfmetrics.registerFont(TTFont("ArialUnicode", FONT_PATH))
FONT = "ArialUnicode"

# Renkler
DARK_BLUE = HexColor("#1A237E")
MID_BLUE = HexColor("#1976D2")
LIGHT_BLUE = HexColor("#E3F2FD")
DARK_GRAY = HexColor("#37474F")
LIGHT_GRAY = HexColor("#F5F5F5")
GREEN = HexColor("#2E7D32")
RED = HexColor("#C62828")
ORANGE = HexColor("#FF8F00")

SERIES = {
    "TP.MKNETHAR.M7":  "Yurt \u0130\u00e7i Hisse",
    "TP.MKNETHAR.M8":  "Yurt \u0130\u00e7i D\u0130BS",
    "TP.MKNETHAR.M23": "Yurt \u0130\u00e7i Gen.Y\u00f6n.",
    "TP.MKNETHAR.M25": "Yurt \u0130\u00e7i Banka",
    "TP.MKNETHAR.M1":  "Yurt D\u0131\u015f\u0131 Hisse",
    "TP.MKNETHAR.M2":  "Yurt D\u0131\u015f\u0131 D\u0130BS",
    "TP.MKNETHAR.M16": "Yurt D\u0131\u015f\u0131 Gen.Y\u00f6n.",
    "TP.MKNETHAR.M18": "Yurt D\u0131\u015f\u0131 Banka",
}

YURT_DISI = ["TP.MKNETHAR.M1", "TP.MKNETHAR.M2", "TP.MKNETHAR.M16", "TP.MKNETHAR.M18"]
YURT_ICI = ["TP.MKNETHAR.M7", "TP.MKNETHAR.M8", "TP.MKNETHAR.M23", "TP.MKNETHAR.M25"]


# ══════════════════════════════════════════════════════════════
#  VER\u0130 \u00c7EKME
# ══════════════════════════════════════════════════════════════

def fetch_all() -> dict[str, pd.DataFrame]:
    end = datetime.now().strftime("%d-%m-%Y")
    data = {}
    for code, name in SERIES.items():
        print(f"  {name}...", end=" ")
        try:
            df = tcmb.read(code, start="01-01-2010", end=end)
            if df.empty:
                print("bos"); continue
            col = df.columns[0]
            df = df.rename(columns={col: "value"}).reset_index()
            df.columns = ["date", "value"]
            df["date"] = pd.to_datetime(df["date"])
            df = df.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
            df["change"] = df["value"].diff()
            data[code] = df
            print(f"{len(df)} sat\u0131r")
        except Exception as e:
            print(f"HATA: {e}")
    return data


# ══════════════════════════════════════════════════════════════
#  GRAF\u0130K \u00dcRET\u0130M\u0130 (PNG -> BytesIO)
# ══════════════════════════════════════════════════════════════

def _fig_to_bytes(fig) -> BytesIO:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_histogram(data: dict, n_weeks=20) -> BytesIO:
    frames = []
    for code, df in data.items():
        recent = df.tail(n_weeks).copy()
        recent["group"] = "Yurt D\u0131\u015f\u0131" if code in YURT_DISI else "Yurt \u0130\u00e7i"
        frames.append(recent)
    combined = pd.concat(frames)
    pivot = combined.groupby(["date", "group"])["change"].sum().unstack(fill_value=0)

    fig, ax = plt.subplots(figsize=(13, 5))
    x = range(len(pivot))
    w = 0.35
    if "Yurt D\u0131\u015f\u0131" in pivot.columns:
        ax.bar([i - w/2 for i in x], pivot["Yurt D\u0131\u015f\u0131"], w,
               label="Yurt D\u0131\u015f\u0131", color="#1976D2", alpha=0.85)
    if "Yurt \u0130\u00e7i" in pivot.columns:
        ax.bar([i + w/2 for i in x], pivot["Yurt \u0130\u00e7i"], w,
               label="Yurt \u0130\u00e7i", color="#FF8F00", alpha=0.85)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([d.strftime("%d/%m") for d in pivot.index], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Milyon USD")
    ax.set_title("Haftal\u0131k Net De\u011fi\u015fim - Yurt \u0130\u00e7i vs Yurt D\u0131\u015f\u0131", fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    plt.tight_layout()
    return _fig_to_bytes(fig)


def chart_cumulative(data: dict, code: str) -> BytesIO:
    df = data[code].copy()
    name = SERIES[code]
    df["year"] = df["date"].dt.year
    df["week"] = df["date"].dt.isocalendar().week.astype(int)

    highlight = [2024, 2025, 2026]
    clrs = {2024: "#2196F3", 2025: "#FF5722", 2026: "#4CAF50", "Ort.": "#9E9E9E"}

    fig, ax = plt.subplots(figsize=(13, 5))
    for y in highlight:
        ydf = df[df["year"] == y].copy()
        if ydf.empty: continue
        ydf["cum"] = ydf["value"] - ydf["value"].iloc[0]
        ax.plot(ydf["week"], ydf["cum"], label=str(y), color=clrs[y], lw=2.2)

    other = df[~df["year"].isin(highlight)]
    if not other.empty:
        cfs = []
        for y, ydf in other.groupby("year"):
            ydf = ydf.copy()
            ydf["cum"] = ydf["value"] - ydf["value"].iloc[0]
            cfs.append(ydf[["week", "cum"]])
        if cfs:
            avg = pd.concat(cfs).groupby("week")["cum"].mean().reset_index()
            ax.plot(avg["week"], avg["cum"], label="Di\u011fer Y\u0131llar Ort.",
                    color=clrs["Ort."], lw=1.8, ls="--")

    ax.axhline(0, color="black", lw=0.8, alpha=0.5)
    ax.set_title(f"{name} \u2013 Y\u0131l Ba\u015f\u0131ndan K\u00fcm\u00fclatif De\u011fi\u015fim (Mn USD)", fontweight="bold")
    ax.set_xlabel("Hafta")
    ax.set_ylabel("K\u00fcm\u00fclatif De\u011fi\u015fim (Mn USD)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    plt.tight_layout()
    return _fig_to_bytes(fig)


def chart_ytd_bar(data: dict) -> BytesIO:
    current_year = datetime.now().year
    ytd = {}
    for code, df in data.items():
        ydf = df[df["date"].dt.year == current_year]
        if not ydf.empty:
            ytd[SERIES[code]] = ydf["change"].sum()

    if not ytd:
        return None

    names = list(ytd.keys())
    vals = list(ytd.values())
    bar_colors = ["#2E7D32" if v >= 0 else "#C62828" for v in vals]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(names, vals, color=bar_colors, alpha=0.85, height=0.6)

    for bar, val in zip(bars, vals):
        x_pos = bar.get_width()
        offset = 80 if val >= 0 else -80
        ax.annotate(f"{val:,.0f}", xy=(x_pos, bar.get_y() + bar.get_height()/2),
                    xytext=(offset, 0), textcoords="offset points",
                    ha="left" if val >= 0 else "right", va="center", fontsize=9, fontweight="bold")

    ax.axvline(0, color="black", lw=0.8)
    ax.set_title(f"{current_year} Y\u0131l Ba\u015f\u0131ndan Bug\u00fcne Toplam Net Ak\u0131m (Mn USD)", fontweight="bold")
    ax.set_xlabel("Milyon USD")
    ax.grid(axis="x", alpha=0.3)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    plt.tight_layout()
    return _fig_to_bytes(fig)


# ══════════════════════════════════════════════════════════════
#  \u0130STAT\u0130ST\u0130K HESAPLAMA
# ══════════════════════════════════════════════════════════════

def calc_stats(data: dict) -> dict:
    now = datetime.now()
    current_year = now.year
    stats = {}

    last_week = {}
    for code, df in data.items():
        if len(df) >= 2:
            last_week[SERIES[code]] = df["change"].iloc[-1]
    stats["last_week"] = last_week

    ytd = {}
    for code, df in data.items():
        ydf = df[df["date"].dt.year == current_year]
        if not ydf.empty:
            ytd[SERIES[code]] = ydf["change"].sum()
    stats["ytd"] = ytd

    yd_total = sum(ytd.get(SERIES[c], 0) for c in YURT_DISI)
    yi_total = sum(ytd.get(SERIES[c], 0) for c in YURT_ICI)
    stats["ytd_yd_total"] = yd_total
    stats["ytd_yi_total"] = yi_total

    avg_4w = {}
    for code, df in data.items():
        if len(df) >= 4:
            avg_4w[SERIES[code]] = df["change"].tail(4).mean()
    stats["avg_4w"] = avg_4w

    current = {}
    for code, df in data.items():
        if not df.empty:
            current[SERIES[code]] = df["value"].iloc[-1]
    stats["current"] = current

    all_dates = [df["date"].iloc[-1] for df in data.values() if not df.empty]
    stats["last_date"] = max(all_dates) if all_dates else now

    # Son hafta yurt disi / ici toplam
    lw_yd = sum(last_week.get(SERIES[c], 0) for c in YURT_DISI)
    lw_yi = sum(last_week.get(SERIES[c], 0) for c in YURT_ICI)
    stats["lw_yd_total"] = lw_yd
    stats["lw_yi_total"] = lw_yi

    return stats


# ══════════════════════════════════════════════════════════════
#  PDF OLU\u015eTURMA
# ══════════════════════════════════════════════════════════════

def build_pdf(data: dict, stats: dict):
    pdf_path = OUTPUT_DIR / "TCMB_Menkul_Kiymet_Raporu.pdf"
    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()

    # ── T\u00fcrk\u00e7e destekli stiller ──
    styles.add(ParagraphStyle("ReportTitle", parent=styles["Title"],
                              fontName=FONT, fontSize=22, textColor=DARK_BLUE, spaceAfter=6))
    styles.add(ParagraphStyle("ReportSubtitle", parent=styles["Normal"],
                              fontName=FONT, fontSize=12, textColor=DARK_GRAY,
                              alignment=TA_CENTER, spaceAfter=20))
    styles.add(ParagraphStyle("SectionHead", parent=styles["Heading1"],
                              fontName=FONT, fontSize=14, textColor=DARK_BLUE,
                              spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle("Caption", parent=styles["Normal"],
                              fontName=FONT, fontSize=9, textColor=DARK_GRAY,
                              alignment=TA_LEFT, spaceBefore=4, spaceAfter=14, leading=12))
    styles.add(ParagraphStyle("BodyText2", parent=styles["Normal"],
                              fontName=FONT, fontSize=10, leading=14, alignment=TA_JUSTIFY))
    styles.add(ParagraphStyle("KPI_Big", parent=styles["Normal"],
                              fontName=FONT, fontSize=28, alignment=TA_CENTER, leading=34))
    styles.add(ParagraphStyle("KPI_Title", parent=styles["Normal"],
                              fontName=FONT, fontSize=10, textColor=DARK_BLUE,
                              alignment=TA_CENTER, leading=13))
    styles.add(ParagraphStyle("KPI_Sub", parent=styles["Normal"],
                              fontName=FONT, fontSize=8, textColor=DARK_GRAY,
                              alignment=TA_CENTER, leading=10))

    story = []
    now = datetime.now()
    last_date = stats["last_date"].strftime("%d.%m.%Y")
    current_year = now.year

    # ── KAPAK ──
    story.append(Spacer(1, 2.5*cm))
    story.append(Paragraph("MENKUL KIYMET PORTF\u00d6Y\u00dc", styles["ReportTitle"]))
    story.append(Paragraph("HAFTALIK RAPOR", styles["ReportTitle"]))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        f"Yurt \u0130\u00e7i ve Yurt D\u0131\u015f\u0131 Yerle\u015fikler Menkul K\u0131ymet \u0130\u015flemleri<br/>"
        f"Son Veri Tarihi: {last_date} &nbsp;|&nbsp; Rapor Tarihi: {now.strftime('%d.%m.%Y')}",
        styles["ReportSubtitle"]))
    story.append(Spacer(1, 1.2*cm))

    # ── KPI KUTULARI (daha aciklayici) ──
    yd_total = stats["ytd_yd_total"]
    yi_total = stats["ytd_yi_total"]
    genel_total = yd_total + yi_total
    lw_yd = stats["lw_yd_total"]
    lw_yi = stats["lw_yi_total"]
    lw_genel = lw_yd + lw_yi

    def _color_hex(val):
        return "#2E7D32" if val >= 0 else "#C62828"

    def _arrow(val):
        return "\u25b2" if val >= 0 else "\u25bc"

    kpi_data = [
        # Basliklar
        [Paragraph("<b>Yurt D\u0131\u015f\u0131 Yerle\u015fikler</b>", styles["KPI_Title"]),
         Paragraph("<b>Yurt \u0130\u00e7i Yerle\u015fikler</b>", styles["KPI_Title"]),
         Paragraph("<b>Genel Toplam</b>", styles["KPI_Title"])],
        # YTD buyuk rakam
        [Paragraph(f"<font color='{_color_hex(yd_total)}'><b>{_arrow(yd_total)} {yd_total:+,.0f}</b></font>",
                   styles["KPI_Big"]),
         Paragraph(f"<font color='{_color_hex(yi_total)}'><b>{_arrow(yi_total)} {yi_total:+,.0f}</b></font>",
                   styles["KPI_Big"]),
         Paragraph(f"<font color='{_color_hex(genel_total)}'><b>{_arrow(genel_total)} {genel_total:+,.0f}</b></font>",
                   styles["KPI_Big"])],
        # YTD aciklama
        [Paragraph(f"Yabanc\u0131 yat\u0131r\u0131mc\u0131lar\u0131n<br/>{current_year} YTD net al\u0131m\u0131 (Mn USD)", styles["KPI_Sub"]),
         Paragraph(f"Yerli yat\u0131r\u0131mc\u0131lar\u0131n<br/>{current_year} YTD net al\u0131m\u0131 (Mn USD)", styles["KPI_Sub"]),
         Paragraph(f"T\u00fcm yerle\u015fiklerin<br/>{current_year} YTD net ak\u0131m\u0131 (Mn USD)", styles["KPI_Sub"])],
        # Bos ayirici
        [Spacer(1, 0.3*cm), Spacer(1, 0.3*cm), Spacer(1, 0.3*cm)],
        # Son hafta
        [Paragraph(f"Son Hafta: <font color='{_color_hex(lw_yd)}'><b>{lw_yd:+,.0f}</b></font> Mn",
                   ParagraphStyle("x", parent=styles["Normal"], fontName=FONT, fontSize=11, alignment=TA_CENTER)),
         Paragraph(f"Son Hafta: <font color='{_color_hex(lw_yi)}'><b>{lw_yi:+,.0f}</b></font> Mn",
                   ParagraphStyle("x2", parent=styles["Normal"], fontName=FONT, fontSize=11, alignment=TA_CENTER)),
         Paragraph(f"Son Hafta: <font color='{_color_hex(lw_genel)}'><b>{lw_genel:+,.0f}</b></font> Mn",
                   ParagraphStyle("x3", parent=styles["Normal"], fontName=FONT, fontSize=11, alignment=TA_CENTER))],
    ]

    kpi_table = Table(kpi_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("BACKGROUND", (0, 1), (-1, 2), LIGHT_BLUE),
        ("BACKGROUND", (0, 4), (-1, 4), LIGHT_GRAY),
        ("BOX", (0, 0), (0, -1), 1.5, MID_BLUE),
        ("BOX", (1, 0), (1, -1), 1.5, MID_BLUE),
        ("BOX", (2, 0), (2, -1), 1.5, MID_BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 1), (-1, 1), 10),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
    ]))
    story.append(kpi_table)
    story.append(PageBreak())

    # ── SAYFA 2: MEVCUT PORTF\u00d6Y B\u00dcY\u00dcKL\u00dc\u011e\u00dc ──
    story.append(Paragraph("1. Mevcut Portf\u00f6y B\u00fcy\u00fckl\u00fc\u011f\u00fc", styles["SectionHead"]))
    story.append(Paragraph(
        f"{last_date} itibar\u0131yla her bir kalem i\u00e7in mevcut portf\u00f6y b\u00fcy\u00fckl\u00fc\u011f\u00fc (d\u00fczey) "
        f"ve {current_year} y\u0131l ba\u015f\u0131ndan itibaren toplam net de\u011fi\u015fim a\u015fa\u011f\u0131da yer almaktad\u0131r.",
        styles["BodyText2"]))
    story.append(Spacer(1, 0.3*cm))

    header = ["Kalem", "Portf\u00f6y (Mn USD)", f"YTD {current_year} (Mn USD)", "YTD %"]
    rows = [header]
    for code in YURT_DISI + YURT_ICI:
        if code not in data: continue
        name = SERIES[code]
        cur = stats["current"].get(name, 0)
        ytd_val = stats["ytd"].get(name, 0)
        ydf = data[code][data[code]["date"].dt.year == current_year]
        if not ydf.empty and ydf["value"].iloc[0] != 0:
            ytd_pct = (ytd_val / ydf["value"].iloc[0]) * 100
        else:
            ytd_pct = 0
        rows.append([name, f"{cur:,.0f}", f"{ytd_val:+,.0f}", f"{ytd_pct:+.1f}%"])

    yd_cur = sum(stats["current"].get(SERIES[c], 0) for c in YURT_DISI)
    yi_cur = sum(stats["current"].get(SERIES[c], 0) for c in YURT_ICI)
    yd_ytd = stats["ytd_yd_total"]
    yi_ytd = stats["ytd_yi_total"]

    rows.insert(5, ["YURT DI\u015eI TOPLAM", f"{yd_cur:,.0f}", f"{yd_ytd:+,.0f}", ""])
    rows.append(["YURT \u0130\u00c7\u0130 TOPLAM", f"{yi_cur:,.0f}", f"{yi_ytd:+,.0f}", ""])
    rows.append(["GENEL TOPLAM", f"{yd_cur+yi_cur:,.0f}", f"{yd_ytd+yi_ytd:+,.0f}", ""])

    col_widths = [5*cm, 4*cm, 4*cm, 3*cm]
    tbl = Table(rows, colWidths=col_widths)
    tbl_style = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GRAY]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i, row in enumerate(rows):
        if "TOPLAM" in str(row[0]):
            tbl_style.append(("FONTNAME", (0, i), (-1, i), FONT))
            tbl_style.append(("BACKGROUND", (0, i), (-1, i), LIGHT_BLUE))
    tbl.setStyle(TableStyle(tbl_style))
    story.append(tbl)
    story.append(Paragraph(
        f"Kaynak: TCMB EVDS. Veriler haftal\u0131k frekansta olup {last_date} tarihli son a\u00e7\u0131klamay\u0131 i\u00e7erir.",
        styles["Caption"]))

    # ── SON 5 HAFTA NET DE\u011e\u0130\u015e\u0130M TABLOSU ──
    story.append(Paragraph("2. Son 5 Hafta Net De\u011fi\u015fim", styles["SectionHead"]))
    story.append(Paragraph(
        "Son 5 haftal\u0131k d\u00f6nemde her bir kalemdeki haftal\u0131k net de\u011fi\u015fimler (milyon USD). "
        "Ye\u015fil h\u00fccre giri\u015f, k\u0131rm\u0131z\u0131 h\u00fccre \u00e7\u0131k\u0131\u015f ifade eder.",
        styles["BodyText2"]))
    story.append(Spacer(1, 0.3*cm))

    n_weeks = 5
    date_cols = []
    tbl_rows = {}
    for code in YURT_DISI + YURT_ICI:
        if code not in data: continue
        df = data[code]
        recent = df.tail(n_weeks)
        name = SERIES[code]
        tbl_rows[name] = {}
        for _, row in recent.iterrows():
            d = row["date"].strftime("%d/%m")
            if d not in date_cols:
                date_cols.append(d)
            tbl_rows[name][d] = row["change"]

    header2 = ["Kalem"] + date_cols
    rows2 = [header2]
    for name in tbl_rows:
        row = [name]
        for d in date_cols:
            v = tbl_rows[name].get(d)
            row.append(f"{v:+,.0f}" if pd.notna(v) else "-")
        rows2.append(row)

    n_cols = len(header2)
    cw = [4.5*cm] + [2.5*cm] * (n_cols - 1)
    tbl2 = Table(rows2, colWidths=cw)
    tbl2_style = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(rows2)):
        for j in range(1, n_cols):
            val_str = rows2[i][j]
            if val_str != "-":
                val = float(val_str.replace(",", "").replace("+", ""))
                if val > 0:
                    tbl2_style.append(("BACKGROUND", (j, i), (j, i), HexColor("#C8E6C9")))
                elif val < 0:
                    tbl2_style.append(("BACKGROUND", (j, i), (j, i), HexColor("#FFCDD2")))
    tbl2.setStyle(TableStyle(tbl2_style))
    story.append(tbl2)
    story.append(Paragraph(
        "Ye\u015fil: net giri\u015f | K\u0131rm\u0131z\u0131: net \u00e7\u0131k\u0131\u015f. De\u011ferler milyon USD cinsindendir.",
        styles["Caption"]))

    # ── KISA VADEL\u0130 MOMENTUM ──
    story.append(Paragraph("3. K\u0131sa Vadeli Momentum", styles["SectionHead"]))
    story.append(Paragraph(
        "Son 4 haftal\u0131k ortalama de\u011fi\u015fim, mevcut trendlerin g\u00fcc\u00fcn\u00fc g\u00f6stermektedir. "
        "Pozitif de\u011ferler s\u00fcrekli giri\u015f, negatif de\u011ferler s\u00fcrekli \u00e7\u0131k\u0131\u015f anlam\u0131na gelir.",
        styles["BodyText2"]))
    story.append(Spacer(1, 0.3*cm))

    header3 = ["Kalem", "Son Hafta (Mn)", "4H Ort. (Mn)", "Trend"]
    rows3 = [header3]
    for code in YURT_DISI + YURT_ICI:
        if code not in data: continue
        name = SERIES[code]
        lw_val = stats["last_week"].get(name, 0)
        avg4 = stats["avg_4w"].get(name, 0)
        if avg4 > 100:
            trend = "\u25b2 G\u00fc\u00e7l\u00fc Giri\u015f"
        elif avg4 > 0:
            trend = "\u25b2 Giri\u015f"
        elif avg4 > -100:
            trend = "\u25bc \u00c7\u0131k\u0131\u015f"
        else:
            trend = "\u25bc G\u00fc\u00e7l\u00fc \u00c7\u0131k\u0131\u015f"
        rows3.append([name, f"{lw_val:+,.0f}", f"{avg4:+,.0f}", trend])

    tbl3 = Table(rows3, colWidths=[4.5*cm, 3.5*cm, 3.5*cm, 3.5*cm])
    tbl3_style = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GRAY]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(rows3)):
        trend_val = rows3[i][3]
        if "G\u00fc\u00e7l\u00fc Giri\u015f" in trend_val:
            tbl3_style.append(("TEXTCOLOR", (3, i), (3, i), GREEN))
        elif "Giri\u015f" in trend_val:
            tbl3_style.append(("TEXTCOLOR", (3, i), (3, i), GREEN))
        elif "G\u00fc\u00e7l\u00fc \u00c7\u0131k\u0131\u015f" in trend_val:
            tbl3_style.append(("TEXTCOLOR", (3, i), (3, i), RED))
        elif "\u00c7\u0131k\u0131\u015f" in trend_val:
            tbl3_style.append(("TEXTCOLOR", (3, i), (3, i), RED))
    tbl3.setStyle(TableStyle(tbl3_style))
    story.append(tbl3)
    story.append(Paragraph(
        "4H Ort.: Son 4 haftan\u0131n ortalama net de\u011fi\u015fimi. "
        "Trend: |ort| > 100 Mn ise 'G\u00fc\u00e7l\u00fc', aksi halde normal.",
        styles["Caption"]))
    story.append(PageBreak())

    # ── YTD BAR CHART ──
    story.append(Paragraph(f"4. {current_year} YTD Toplam Net Ak\u0131m", styles["SectionHead"]))
    ytd_buf = chart_ytd_bar(data)
    if ytd_buf:
        story.append(Image(ytd_buf, width=16*cm, height=8*cm))
        story.append(Paragraph(
            f"{current_year} y\u0131l ba\u015f\u0131ndan {last_date} tarihine kadar her bir kalemdeki "
            f"toplam net portf\u00f6y de\u011fi\u015fimi. Ye\u015fil: net giri\u015f, K\u0131rm\u0131z\u0131: net \u00e7\u0131k\u0131\u015f.",
            styles["Caption"]))

    # ── H\u0130STOGRAM ──
    story.append(Paragraph("5. Haftal\u0131k Net De\u011fi\u015fim Trendi", styles["SectionHead"]))
    hist_buf = chart_histogram(data, n_weeks=20)
    story.append(Image(hist_buf, width=16*cm, height=7*cm))
    story.append(Paragraph(
        "Son 20 haftada Yurt \u0130\u00e7i ve Yurt D\u0131\u015f\u0131 yerle\u015fiklerin toplam haftal\u0131k net "
        "menkul k\u0131ymet i\u015flem hacimleri. Mavi: Yurt D\u0131\u015f\u0131, Turuncu: Yurt \u0130\u00e7i.",
        styles["Caption"]))
    story.append(PageBreak())

    # ── K\u00dcM\u00dcLAT\u0130F TIME SERIES ──
    story.append(Paragraph("6. Y\u0131ll\u0131k K\u00fcm\u00fclatif De\u011fi\u015fim Kar\u015f\u0131la\u015ft\u0131rmas\u0131", styles["SectionHead"]))
    story.append(Paragraph(
        "Her seri i\u00e7in y\u0131l ba\u015f\u0131ndaki de\u011fere g\u00f6re s\u0131f\u0131rlanm\u0131\u015f k\u00fcm\u00fclatif de\u011fi\u015fim grafikleri. "
        "2024, 2025 ve 2026 y\u0131llar\u0131 ayr\u0131 \u00e7izgilerle, di\u011fer y\u0131llar ortalamas\u0131 kesikli \u00e7izgiyle g\u00f6sterilmi\u015ftir. "
        "Bu grafikler y\u0131llar aras\u0131 mevsimsel kal\u0131plar\u0131 ve sapmalar\u0131 ortaya koyar.",
        styles["BodyText2"]))
    story.append(Spacer(1, 0.3*cm))

    for label, codes in [("Yurt D\u0131\u015f\u0131 Yerle\u015fikler", YURT_DISI),
                         ("Yurt \u0130\u00e7i Yerle\u015fikler", YURT_ICI)]:
        story.append(Paragraph(f"6.{1 if 'D\u0131\u015f\u0131' in label else 2}. {label}", styles["SectionHead"]))
        for code in codes:
            if code not in data: continue
            buf = chart_cumulative(data, code)
            story.append(Image(buf, width=16*cm, height=6.5*cm))
            story.append(Paragraph(
                f"{SERIES[code]}: Y\u0131l ba\u015f\u0131ndan itibaren k\u00fcm\u00fclatif net de\u011fi\u015fim (Milyon USD). "
                f"Her y\u0131l 0'dan ba\u015flar.",
                styles["Caption"]))

    # ── FOOTER ──
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        f"<b>Kaynak:</b> TCMB Elektronik Veri Da\u011f\u0131t\u0131m Sistemi (EVDS). "
        f"Bu rapor otomatik olarak olu\u015fturulmu\u015ftur. "
        f"Rapor tarihi: {now.strftime('%d.%m.%Y %H:%M')}",
        ParagraphStyle("Footer", parent=styles["Normal"],
                       fontName=FONT, fontSize=8, textColor=DARK_GRAY, spaceBefore=20)))

    doc.build(story)
    print(f"\n  PDF: {pdf_path}")
    return pdf_path


# ══════════════════════════════════════════════════════════════

def run():
    print("=" * 50)
    print("TCMB Haftal\u0131k Rapor Olu\u015fturucu")
    print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    print("\n[1/3] Veriler \u00e7ekiliyor...")
    data = fetch_all()
    if not data:
        print("Veri yok!"); return

    print("\n[2/3] \u0130statistikler hesaplan\u0131yor...")
    stats = calc_stats(data)

    print("\n[3/3] PDF olu\u015fturuluyor...")
    build_pdf(data, stats)

    print("\nTamamland\u0131!")


if __name__ == "__main__":
    run()
