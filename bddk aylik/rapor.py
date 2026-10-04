#!/usr/bin/env python3
"""Bankacılık Monitörü — aylık PDF rapor (ekordion.com.tr tasarımı).
Kullanım: python rapor.py <çıktı.pdf>   (önce fetch_bddk.py ve gorunum.py; veri calc.py'den gelir)
Sayfa seti: kapak, ayın görünümü, özet tablo, grup karnesi, kârlılık (8), bilanço (5), krediler (8),
aktif kalitesi, menkul kıymetler (2), fonlama (4), bilanço rasyoları, sermaye, şube-personel, metodoloji.
Kompozisyon ve pazar payı sayfaları zaman serili %100 yığılmış alan grafikleridir (son 25 ay)."""
import warnings; warnings.filterwarnings('ignore')
import json, sys, textwrap
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from calc import *  # noqa: E402,F401  (D, LAST, GROUPS, DEPG, GSHORT, GNAME, at, series, yoy)
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

plt.rcParams['font.family'] = 'DejaVu Sans'
PW, PH = 15.6, 8.0
LACI, KIRMIZI, GRI, METIN, ACIK = '#1C3044', '#D40031', '#9AA4B2', '#1A2233', '#F4F6F9'
GC = {'S': '#1C3044', 'M': '#5E8BC5', 'KA': '#D40031', 'YO': '#2E7D5B', 'YA': '#B99464', 'KB': '#E07B00', 'KY': '#7A5C9E'}
GLEG = [(g, GSHORT[g]) for g in GROUPS]
PREV = pd.Timestamp(LAST.year - 1, LAST.month, 1) + pd.offsets.MonthEnd(0)
ONCEKI = LAST - pd.offsets.MonthEnd(1)
AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
AYK = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']
DON = f"{AYLAR[LAST.month - 1]} {LAST.year}"
BRAND = 'ekordion.com.tr'
SRC = 'Kaynak: BDDK Aylık Bülten · ekordion.com.tr Bankacılık Monitörü'
GORUNUM = json.loads((HERE / 'gorunum.json').read_text(encoding='utf-8')) if (HERE / 'gorunum.json').exists() else None
SAYFA = [0]
BAS = (LAST - pd.DateOffset(months=24)).strftime('%Y-%m-%d')   # kompozisyon grafiklerinin başlangıcı (25 ay)


def tr(x, d=1, pct=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return '-'
    s = f"{x:,.{d}f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('%' + s) if pct else s


def trp(x, d=1):
    if x is None or np.isnan(x):
        return '-'
    return ('-' if x < 0 else '') + '%' + tr(abs(x), d)


def header(fig, title, sub=None):
    ax = fig.add_axes([0, 0.875, 1, 0.125]); ax.axis('off')
    ax.add_patch(Rectangle((0, 0), 1, 1, color=LACI, transform=ax.transAxes))
    ax.add_patch(Rectangle((0, 0), 1, 0.045, color=KIRMIZI, transform=ax.transAxes))
    ax.text(0.03, 0.62 if sub else 0.52, title, ha='left', va='center', fontsize=21, color='white', fontweight='bold')
    if sub:
        ax.text(0.03, 0.25, sub, ha='left', va='center', fontsize=9.5, color='#C9D3E0')
    ax.text(0.97, 0.64, 'Bankacılık Monitörü', ha='right', va='center', fontsize=12, color='white', fontweight='bold')
    ax.text(0.97, 0.28, DON, ha='right', va='center', fontsize=10.5, color='#C9D3E0')
    SAYFA[0] += 1
    fig.text(0.03, 0.013, SRC, fontsize=7.5, color='#666')
    fig.text(0.97, 0.013, str(SAYFA[0]), fontsize=7.5, color='#666', ha='right')
    fig.text(0.985, 0.003, 'bacanli', fontsize=2.5, color='#bbbbbb', ha='right', va='bottom')


def legend_bottom(fig, items, y=0.045, fs=8.5):
    hs = [Line2D([0], [0], marker='o', color='w', markerfacecolor=c, markersize=7) for c, _ in items]
    fig.legend(hs, [t for _, t in items], loc='lower center', bbox_to_anchor=(0.5, y - 0.02), ncol=len(items),
               frameon=False, fontsize=fs, handletextpad=0.2, columnspacing=1.2)


def style(ax):
    ax.grid(True, axis='y', ls='-', color='#E3E7EE', lw=0.7); ax.set_axisbelow(True)
    for sp in ['top', 'right']:
        ax.spines[sp].set_visible(False)
    ax.spines['left'].set_color('#C9CED6'); ax.spines['bottom'].set_color('#C9CED6')
    ax.tick_params(labelsize=7.5, colors='#444')


def line_end_labels(ax, ends, fs=7.5):
    ymin, ymax = ax.get_ylim(); span = ymax - ymin; gap = span * 0.055
    items = sorted([(v, c, l) for v, c, l in ends if not np.isnan(v)], key=lambda t: t[0])
    pos = [v for v, _, _ in items]
    for i in range(1, len(pos)):
        if pos[i] - pos[i - 1] < gap:
            pos[i] = pos[i - 1] + gap
    over = pos[-1] - ymax if pos else 0
    if over > 0:
        pos = [p - over for p in pos]
    for i in range(len(pos) - 2, -1, -1):
        if pos[i + 1] - pos[i] < gap:
            pos[i] = pos[i + 1] - gap
    x1 = ax.get_xlim()[1]
    for (v, c, l), p in zip(items, pos):
        ax.text(x1, p, ' ' + l, color=c, fontsize=fs, fontweight='bold', va='center', ha='left', clip_on=False)


def ay_ekseni(ax, yr_only=False):
    if yr_only:
        ax.xaxis.set_major_locator(mdates.YearLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda t, p: f"{AYK[mdates.num2date(t).month - 1]} {mdates.num2date(t).year}"))


def line_panel(ax, col, title, start, fmt='pct', groups=GROUPS, yfmt=None, d=1, yr_only=False):
    ends = []
    for g in groups:
        s = series(g, col, start).dropna()
        if len(s) == 0:
            continue
        ax.plot(s.index, s.values, color=GC[g], lw=2.1 if g == 'S' else 1.5)
        v = s.iloc[-1]; ends.append((v, GC[g], trp(v, d) if fmt == 'pct' else tr(v, d)))
    ax.set_title(title, fontsize=10.5, pad=6, color=METIN)
    style(ax); ay_ekseni(ax, yr_only)
    if yfmt == 'pct':
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: '%' + tr(v, 0 if abs(v) >= 10 else 1)))
    else:
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: tr(v, d if d <= 1 else 1)))
    ax.set_xlim(right=ax.get_xlim()[1] + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.02)
    line_end_labels(ax, ends)


def grid_axes(fig, layout, top=0.82, bottom=0.085):
    axes = []; nrows = len(layout); h = (top - bottom) / nrows
    for r, row in enumerate(layout):
        y1 = top - r * h; y0 = y1 - h
        left, right = 0.03, 0.965; tot = sum(row); x = left
        for w in row:
            wid = (right - left) * w / tot
            ax = fig.add_axes([x + 0.028, y0 + 0.1 * h, wid - 0.058, h * 0.74]); axes.append(ax); x += wid
    return axes


def line_page(pdf, title, panels, layout, start_default='2024-07-31', sub=None, legend=True):
    fig = plt.figure(figsize=(PW, PH)); header(fig, title, sub)
    for ax, p in zip(grid_axes(fig, layout), panels):
        line_panel(ax, p['col'], p['title'], p.get('start', start_default), p.get('fmt', 'pct'),
                   p.get('groups', GROUPS), p.get('yfmt'), p.get('d', 1), p.get('yr_only', False))
    if legend:
        legend_bottom(fig, [(GC[g], t) for g, t in GLEG])
    pdf.savefig(fig); plt.close(fig)


# ---------- kompozisyon: zaman serili %100 yığılmış alan ----------
def comp_frame(g, parts, start):
    sub = D[(D.g == g) & (D.d >= start)].sort_values('d')
    return pd.DataFrame({lab: [f(r) for _, r in sub.iterrows()] for lab, f, _ in parts}, index=sub.d)


def area_page(pdf, title, sub, parts, groups=GROUPS, unit_div=1e6, unit='trilyon ₺', totfmt=1):
    fig = plt.figure(figsize=(PW, PH)); header(fig, title, sub)
    layout = [[1] * 4, [1] * 3] if len(groups) == 7 else [[1] * 3, [1] * 3]
    for ax, g in zip(grid_axes(fig, layout, top=0.83, bottom=0.09), groups):
        F = comp_frame(g, parts, BAS); T = F.sum(axis=1)
        if len(F) == 0 or T.iloc[-1] == 0:
            ax.axis('off'); continue
        sh = F.div(T, axis=0) * 100
        ax.stackplot(sh.index, [sh[c].values for c in sh.columns], colors=[c for _, _, c in parts], alpha=0.93, lw=0)
        ax.set_ylim(0, 100); ax.set_xlim(sh.index[0], sh.index[-1])
        base = 0
        for c, (lab, _, col) in zip(sh.columns, parts):
            v = sh[c].iloc[-1]
            if v >= 4:
                ax.text(sh.index[-1], base + v / 2, ' ' + tr(v, 1) + '%', fontsize=6.6, color=col, va='center', ha='left', fontweight='bold', clip_on=False)
            base += v
        yoy_ = (T.iloc[-1] / T.iloc[-13] - 1) * 100 if len(T) >= 13 else np.nan
        ax.set_title(f"{GSHORT[g]}\n{tr(T.iloc[-1] / unit_div, totfmt)} {unit} · yıllık {trp(yoy_)}", fontsize=9, pad=4, color=METIN)
        style(ax); ax.grid(False)
        ax.set_yticks([0, 25, 50, 75, 100]); ax.set_yticklabels(['0', '25', '50', '75', '100%'], fontsize=6.5)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda t, p: f"{AYK[mdates.num2date(t).month - 1]} {str(mdates.num2date(t).year)[2:]}"))
        ax.tick_params(labelsize=6.5)
    legend_bottom(fig, [(c, lab) for lab, _, c in parts], y=0.05, fs=8)
    pdf.savefig(fig); plt.close(fig)


def share_page(pdf, title, cats, groups=('KA', 'YO', 'YA', 'KB'), sub='Sektör içindeki paylar, son 25 ay; panel başlığı: sektör toplamı ve yıllık büyüme'):
    fig = plt.figure(figsize=(PW, PH)); header(fig, title, sub)
    n = len(cats); layout = [[1] * n] if n <= 4 else [[1] * 3, [1] * (n - 3)]
    for ax, (ttl, col, fmt) in zip(grid_axes(fig, layout, top=0.83, bottom=0.09), cats):
        S = series('S', col, BAS)
        shares = {g: (series(g, col, BAS) / S * 100).reindex(S.index) for g in groups}
        kalan = 100 - sum(shares.values())
        kalan[kalan < 0] = 0
        cols = [GC[g] for g in groups] + ['#C9CED6']
        ax.stackplot(S.index, [shares[g].fillna(0).values for g in groups] + [kalan.fillna(0).values], colors=cols, alpha=0.93, lw=0)
        ax.set_ylim(0, 100); ax.set_xlim(S.index[0], S.index[-1])
        base = 0
        for g in groups:
            v = shares[g].iloc[-1]
            if v >= 4:
                ax.text(S.index[-1], base + v / 2, ' ' + tr(v, 1) + '%', fontsize=6.8, color=GC[g], va='center', ha='left', fontweight='bold', clip_on=False)
            base += v
        yoy_ = (S.iloc[-1] / S.iloc[-13] - 1) * 100 if len(S) >= 13 else np.nan
        ax.set_title(f"{ttl}\n{tr(S.iloc[-1] / 1e6, fmt)} trilyon ₺ · yıllık {trp(yoy_)}", fontsize=9.5, pad=4, color=METIN)
        style(ax); ax.grid(False)
        ax.set_yticks([0, 25, 50, 75, 100]); ax.set_yticklabels(['0', '25', '50', '75', '100%'], fontsize=6.5)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda t, p: f"{AYK[mdates.num2date(t).month - 1]} {str(mdates.num2date(t).year)[2:]}"))
        ax.tick_params(labelsize=6.5)
    legend_bottom(fig, [(GC[g], GSHORT[g]) for g in groups] + [('#C9CED6', 'Diğer')], y=0.05, fs=8)
    pdf.savefig(fig); plt.close(fig)


# kompozisyon tanımları (satır → değer)
AKTIF = [('TP Krediler', lambda r: r.krediTP, LACI), ('YP Krediler', lambda r: r.krediYP, '#5E8BC5'),
         ('TP Menkul Kıymetler', lambda r: r.mkTP, KIRMIZI), ('YP Menkul Kıymetler', lambda r: r.mkYP, '#E8A0AE'),
         ('TP Nakit ve Benzerleri', lambda r: r.nakTP, '#2E7D5B'), ('YP Nakit ve Benzerleri', lambda r: r.nakYP, '#8FCBB0'),
         ('Diğer Aktifler', lambda r: r.aktif - r.krediTP - r.krediYP - r.mkTP - r.mkYP - r.nakTP - r.nakYP, '#C9CED6')]
PASIF = [('TP Toplanan Fon', lambda r: r.mvTP, LACI), ('YP Toplanan Fon', lambda r: r.mvYP - r.kmTot, '#5E8BC5'),
         ('Kıymetli Madenler', lambda r: r.kmTot, '#B99464'), ('Toptan Fonlama', lambda r: r.topTP + r.topYP, KIRMIZI),
         ('Sermaye Benzeri Borçlanma', lambda r: r.sermBz, '#E8A0AE'), ('Özkaynaklar', lambda r: r.ozk, '#2E7D5B'),
         ('Diğer Pasifler', lambda r: r.aktif - r.mvTP - r.mvYP - r.topTP - r.topYP - r.sermBz - r.ozk, '#C9CED6')]
CANLI = [('Tüketici Kredileri ve KK', lambda r: r.tukKK, LACI), ('TP KOBİ', lambda r: r.kobiTP, KIRMIZI),
         ('YP KOBİ', lambda r: r.kobiYP, '#E8A0AE'), ('TP Ticari/Kurumsal', lambda r: r.ticKurTP, '#2E7D5B'),
         ('YP Ticari/Kurumsal', lambda r: r.ticKurYP, '#8FCBB0'), ('Finansal Kiralama', lambda r: r.fk, '#B99464')]
TUK = [('Konut', lambda r: r.konut, LACI), ('Taşıt', lambda r: r.tasit, '#5E8BC5'),
       ('İhtiyaç (dövize endeksli dahil)', lambda r: r.tuk - r.konut - r.tasit, KIRMIZI), ('Bireysel Kredi Kartları', lambda r: r.kk, '#B99464')]
TUZEL = [('Ticari / Kurumsal', lambda r: r.ticKur, LACI), ('KOBİ', lambda r: r.kobi, KIRMIZI), ('Finansal Kiralama', lambda r: r.fk, '#B99464')]
MENKUL = [('TP Alım-Satım + Satılmaya Hazır', lambda r: r.mkTP - r.htmTP, LACI), ('TP Vadeye Kadar Elde Tutulacak', lambda r: r.htmTP, '#5E8BC5'),
          ('YP Alım-Satım + Satılmaya Hazır', lambda r: r.mkYP - r.htmYP, KIRMIZI), ('YP Vadeye Kadar Elde Tutulacak', lambda r: r.htmYP, '#E8A0AE')]
FON = [('TP Vadesiz', lambda r: r.vdsTP, LACI), ('TP Vadeli', lambda r: r.vadeliTP, '#5E8BC5'),
       ('YP Vadesiz', lambda r: r.ypVds_exKM, KIRMIZI), ('YP Vadeli', lambda r: r.ypVdl_exKM, '#E8A0AE'),
       ('Kıymetli Maden Vadesiz', lambda r: r.kmVds, '#B99464'), ('Kıymetli Maden Vadeli', lambda r: r.kmVdl, '#E3C9A0')]


# ---------- tablolar ----------
def table_page(pdf, title, sub, rows, colgroups=GROUPS, note=None):
    fig = plt.figure(figsize=(PW, PH)); header(fig, title, sub)
    ax = fig.add_axes([0.03, 0.085, 0.94, 0.76]); ax.axis('off')
    n = len(rows); hdr = ['Kalem'] + [GSHORT[g] for g in colgroups]
    cw = [0.30] + [0.70 / len(colgroups)] * len(colgroups); rh = 1 / (n + 1); x = 0
    for j, h in enumerate(hdr):
        ax.add_patch(Rectangle((x, 1 - rh), cw[j], rh, color=LACI, transform=ax.transAxes))
        ax.text(x + cw[j] / 2, 1 - rh / 2, h, ha='center', va='center', color='white', fontsize=9.5, fontweight='bold', transform=ax.transAxes); x += cw[j]
    for i, (lab, vals) in enumerate(rows):
        y = 1 - (i + 2) * rh; x = 0; bg = ACIK if i % 2 else 'white'
        for j in range(len(hdr)):
            ax.add_patch(Rectangle((x, y), cw[j], rh, facecolor=bg, edgecolor='#D9DEE6', lw=0.5, transform=ax.transAxes))
            if j == 0:
                ax.text(x + 0.008, y + rh / 2, lab, ha='left', va='center', fontsize=9.2, color=METIN, transform=ax.transAxes)
            else:
                v = vals[j - 1]
                if isinstance(v, tuple):
                    g, amt = v
                    ax.text(x + 0.012, y + rh / 2, trp(g, 1) if not np.isnan(g) else '-', ha='left', va='center', fontsize=7.5,
                            color='#2E7D5B' if (not np.isnan(g) and g >= 0) else KIRMIZI, fontweight='bold', transform=ax.transAxes)
                    ax.text(x + cw[j] - 0.008, y + rh / 2, tr(amt, 0), ha='right', va='center', fontsize=9, color=METIN, transform=ax.transAxes)
                else:
                    ax.text(x + cw[j] / 2, y + rh / 2, tr(v, 1), ha='center', va='center', fontsize=9.2, color=METIN,
                            fontweight='bold' if colgroups[j - 1] == 'S' else 'normal', transform=ax.transAxes)
            x += cw[j]
    if note:
        fig.text(0.03, 0.05, note, fontsize=8, color='#333')
    pdf.savefig(fig); plt.close(fig)


OZET_SATIRLAR = [('Aktif Büyümesi', 'g_aktif'), ('Aktif TP Ağırlığı', 'aktifTPag'), ('TP Canlı Kredi Büyümesi', 'g_canliTP'),
                 ('YP Canlı Kredi Büyümesi (USD)', 'g_canliYP_usd'), ('Tüketici Kredileri / Canlı Krediler', 'tukCanli'),
                 ('NPL Oranı', 'npl'), ('Özel Karşılık Oranı', 'ozelKarsOran'), ('TP Toplanan Fon Büyümesi', 'g_mvTP'),
                 ('YP Toplanan Fon Büyümesi (USD)', 'g_mvYP_usd'), ('Toplanan Fon TP Ağırlığı', 'fonTPag'),
                 ('Standart SYR', 'syr'), ('Çekirdek SYR', 'cekSyr'), ('Aktif Kârlılığı (ROA)', 'roa'), ('Özkaynak Kârlılığı (ROE)', 'roe'),
                 ('Brüt Faaliyet Kârı Artışı', 'gy_brutKar'), ('Net Kâr Artışı', 'gy_netKar'), ('Gider / Gelir Oranı', 'giderGelir'),
                 ('Op-Ex / Aktifler', 'opexAktif')]
GELIR_SATIRLAR = [('Faiz / Kâr Payı Gelirleri', 'faizGel'), ('Faiz / Kâr Payı Giderleri', 'faizGid'), ('Net Faiz / Kâr Payı Geliri', 'netFaiz'),
                  ('Ücret ve Komisyon Gelirleri', 'ucrGel'), ('Ücret ve Komisyon Giderleri', 'ucrGid'), ('Net Ücret ve Komisyon Geliri', 'netUcret'),
                  ('Ticari Kâr / Zarar', 'ticari'), ('Diğer Faaliyet Gelirleri', 'digGel'), ('Brüt Faaliyet Kârı', 'brutKar'),
                  ('Personel Giderleri', 'personel'), ('Diğer İşletme Giderleri', 'digIsl'), ('Faaliyet Giderleri (Op-Ex)', 'opex'),
                  ('Karşılık Giderleri', 'karsilik'), ('Vergi Öncesi Kâr', 'vergiOncesi'), ('Vergi Karşılıkları', 'vergi'), ('Net Kâr', 'netKar')]
GIDER_KALEMLERI = ['faizGid', 'ucrGid', 'personel', 'digIsl', 'opex', 'karsilik', 'vergi']


def karne_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Grup Karnesi', f'{DON} itibarıyla; hücre rengi grup sıralamasını gösterir (koyu yeşil = en iyi). Sektör sütunu referanstır.')
    metrics = [('Aktif Büyümesi (%)', 'g_aktif', 1, 1), ('TP Canlı Kredi Büyümesi (%)', 'g_canliTP', 1, 1), ('NPL Oranı (%)', 'npl', 2, -1),
               ('Tüketici NPL (%)', 'nplTuk', 2, -1), ('Özel Karşılık Oranı (%)', 'ozelKarsOran', 1, 1), ('Standart SYR (%)', 'syr', 1, 1),
               ('ROA (%)', 'roa', 1, 1), ('ROE (%)', 'roe', 1, 1), ('Net Faiz Marjı (%)', 'nim', 1, 1), ('Gider / Gelir (%)', 'giderGelir', 1, -1),
               ('Op-Ex / Aktifler (%)', 'opexAktif', 1, -1), ('Kaldıraç (Aktif/Özkaynak, x)', 'kaldirac', 1, -1)]
    ax = fig.add_axes([0.03, 0.085, 0.94, 0.76]); ax.axis('off')
    cg = GROUPS; n = len(metrics); hdr = ['Gösterge'] + [GSHORT[g] for g in cg]
    cw = [0.24] + [0.76 / len(cg)] * len(cg); rh = 1 / (n + 1); x = 0
    for j, h in enumerate(hdr):
        ax.add_patch(Rectangle((x, 1 - rh), cw[j], rh, color=LACI, transform=ax.transAxes))
        ax.text(x + cw[j] / 2, 1 - rh / 2, h, ha='center', va='center', color='white', fontsize=9.5, fontweight='bold', transform=ax.transAxes); x += cw[j]
    import matplotlib.colors as mcolors
    cmap = mcolors.LinearSegmentedColormap.from_list('isi', ['#E05C57', '#EED264', '#50B26E'])
    for i, (lab, col, d, sgn) in enumerate(metrics):
        vals = [at(g)[col] for g in cg]
        sub = [v for g, v in zip(cg, vals) if g != 'S' and not np.isnan(v)]
        order = sorted(sub, reverse=(sgn > 0))
        y = 1 - (i + 2) * rh; x = 0
        for j in range(len(hdr)):
            if j == 0:
                ax.add_patch(Rectangle((x, y), cw[j], rh, facecolor='white', edgecolor='#D9DEE6', lw=0.5, transform=ax.transAxes))
                ax.text(x + 0.006, y + rh / 2, lab, ha='left', va='center', fontsize=9, color=METIN, transform=ax.transAxes)
            else:
                g = cg[j - 1]; v = vals[j - 1]
                if g == 'S' or np.isnan(v):
                    fc = '#F0F2F5'
                else:
                    r = order.index(v) / max(len(order) - 1, 1); fc = mcolors.to_hex(cmap(1 - r))
                ax.add_patch(Rectangle((x, y), cw[j], rh, facecolor=fc, edgecolor='#D9DEE6', lw=0.5, transform=ax.transAxes))
                ax.text(x + cw[j] / 2, y + rh / 2, tr(v, d), ha='center', va='center', fontsize=9, color=METIN,
                        fontweight='bold' if g == 'S' else 'normal', transform=ax.transAxes)
            x += cw[j]
    fig.text(0.03, 0.05, 'Mevduata dayalı göstergeler Kalkınma-Yatırım grubu için tanımsızdır.', fontsize=8, color='#333')
    pdf.savefig(fig); plt.close(fig)


# ---------- özel sayfalar ----------
def cover(pdf):
    fig = plt.figure(figsize=(PW, PH)); ax = fig.add_axes([0, 0, 1, 1]); ax.axis('off')
    ax.add_patch(Rectangle((0, 0), 1, 1, color=LACI, transform=ax.transAxes))
    ax.add_patch(Rectangle((0, 0), 0.012, 1, color=KIRMIZI, transform=ax.transAxes))
    ax.text(0.06, 0.74, 'Bankacılık', fontsize=46, color='white', fontweight='bold', ha='left', va='center')
    ax.text(0.06, 0.62, 'Monitörü', fontsize=46, color='white', fontweight='bold', ha='left', va='center')
    ax.text(0.06, 0.50, DON, fontsize=24, color='#FFB3C1', ha='left', va='center', fontweight='bold')
    ax.text(0.06, 0.43, 'BDDK Aylık Bülten verileriyle yedi banka grubu için bilanço, kredi,', fontsize=11, color='#C9D3E0', ha='left', va='center')
    ax.text(0.06, 0.395, 'aktif kalitesi, fonlama, sermaye ve kârlılık görünümü', fontsize=11, color='#C9D3E0', ha='left', va='center')
    ax.text(0.06, 0.09, BRAND, fontsize=16, color='white', fontweight='bold', ha='left', va='center')
    ax.text(0.06, 0.055, 'Her ay BDDK açıklamasını takiben güncellenir · bilgilendirme amaçlıdır, yatırım tavsiyesi değildir', fontsize=8, color='#8FA0B8', ha='left', va='center')
    a = at('S')
    kp = [('Toplam Aktif', tr(a.aktif / 1e6, 1) + ' trilyon ₺', trp(a.g_aktif)), ('Canlı Krediler', tr(a.canli / 1e6, 1) + ' trilyon ₺', trp(a.g_canli)),
          ('Toplanan Fonlar', tr(a.mevduat / 1e6, 1) + ' trilyon ₺', trp(a.g_mevduat)), ('Net Kâr (yıl içi)', tr(a.netKar / 1e3, 1) + ' milyar ₺', trp(a.gy_netKar)),
          ('NPL / SYR', tr(a.npl, 2) + '%  /  ' + tr(a.syr, 1) + '%', ''), ('ROA / ROE', tr(a.roa, 1) + '%  /  ' + tr(a.roe, 1) + '%', '')]
    for i, (k, v, g) in enumerate(kp):
        y = 0.86 - i * 0.125
        ax.add_patch(Rectangle((0.58, y - 0.045), 0.37, 0.1, color='white', transform=ax.transAxes))
        ax.add_patch(Rectangle((0.58, y - 0.045), 0.006, 0.1, color=KIRMIZI, transform=ax.transAxes))
        ax.text(0.60, y + 0.022, k, fontsize=9.5, color='#666', va='center')
        ax.text(0.60, y - 0.018, v, fontsize=15, color=METIN, fontweight='bold', va='center')
        ax.text(0.935, y - 0.018, g, fontsize=13, color=KIRMIZI, fontweight='bold', va='center', ha='right')
    ax.text(0.765, 0.085, 'Sektör toplamı; yüzdeler yıllık değişim', fontsize=8.5, color='#C9D3E0', ha='center')
    fig.text(0.985, 0.003, 'bacanli', fontsize=2.5, color='#2B3F57', ha='right', va='bottom')
    pdf.savefig(fig); plt.close(fig)


def gorunum_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Ayın Görünümü', 'Verilerden üretilen kısa yorum; sağda sektör göstergelerinin bir önceki aya göre değişimi')
    G = GORUNUM or {'baslik': DON, 'maddeler': [], 'mod': 'yok'}
    y = 0.80
    for line in textwrap.wrap(G['baslik'], 62):
        fig.text(0.04, y, line, fontsize=16, fontweight='bold', color=METIN, va='top'); y -= 0.055
    y -= 0.02
    for m in G['maddeler']:
        lines = textwrap.wrap(m, 92)
        fig.add_artist(plt.Circle((0.047, y - 0.012), 0.004, color=KIRMIZI, transform=fig.transFigure))
        for k, line in enumerate(lines):
            fig.text(0.06, y, line, fontsize=10.2, color=METIN, va='top'); y -= 0.034
        y -= 0.016
    S = at('S'); P = at('S', ONCEKI)
    kp = [('Toplam aktif, yıllık', trp(S.g_aktif), f"önceki ay {trp(P.g_aktif)}"), ('TP canlı kredi, yıllık', trp(S.g_canliTP), f"3 aylık yıllıklandırılmış {trp(S.g3_canliTP)}"),
          ('Toplanan fon TP ağırlığı', trp(S.fonTPag), f"önceki ay {trp(P.fonTPag)}"), ('Aylık net kâr', tr(S.netKar_m / 1e3, 1) + ' milyar ₺', f"önceki ay {tr(P.netKar_m / 1e3, 1)} milyar ₺"),
          ('NPL oranı', trp(S.npl, 2), f"önceki ay {trp(P.npl, 2)}"), ('Standart SYR', trp(S.syr), f"önceki ay {trp(P.syr)}")]
    for i, (k, v, alt) in enumerate(kp):
        yy = 0.78 - i * 0.118
        fig.add_artist(Rectangle((0.70, yy - 0.05), 0.27, 0.095, facecolor=ACIK, edgecolor='#D9DEE6', lw=0.6, transform=fig.transFigure))
        fig.add_artist(Rectangle((0.70, yy - 0.05), 0.005, 0.095, color=LACI, transform=fig.transFigure))
        fig.text(0.715, yy + 0.022, k, fontsize=8.5, color='#666', va='center')
        fig.text(0.715, yy - 0.012, v, fontsize=14, color=METIN, fontweight='bold', va='center')
        fig.text(0.715, yy - 0.036, alt, fontsize=7.5, color='#777', va='center')
    fig.text(0.04, 0.05, 'Yorum ' + ('Claude ile verilerden üretildi' if G.get('mod') == 'ai' else 'verilerden kural tabanlı üretildi') + '; bilgilendirme amaçlıdır.', fontsize=8, color='#555')
    pdf.savefig(fig); plt.close(fig)


def syr_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Sermaye Yeterliliği', 'Sermaye yapısı (milyon ₺) ve SYR serileri')
    legend_bottom(fig, [(LACI, 'Çekirdek Sermaye'), ('#5E8BC5', 'İlave Ana Sermaye'), ('#E8A0AE', 'Katkı Sermaye')], y=0.80, fs=8)
    for i, g in enumerate(GROUPS):
        a = at(g); ax = fig.add_axes([0.055 + i * 0.134, 0.5, 0.08, 0.2]); ax.axis('off')
        parts = [(a.cekirdek, LACI), (a.anaSerm - a.cekirdek, '#5E8BC5'), (a.katkiSerm, '#E8A0AE')]
        base = 0; T = a.anaSerm + a.katkiSerm
        for v, c in parts:
            p = v / T * 100; ax.bar(0, p, bottom=base, color=c, width=1)
            if p > 3:
                ax.text(0, base + p / 2, f"{p:.0f}%", ha='center', va='center', color='white', fontsize=8)
            base += p
        ax.set_ylim(0, 100); ax.set_xlim(-0.5, 0.5)
        ax.text(0, 104, tr(T, 0), ha='center', fontsize=10, fontweight='bold', color=METIN)
        ax.text(0, -8, GSHORT[g], ha='center', va='top', fontsize=8.5, color='#444')
    axes = [fig.add_axes([0.05, 0.11, 0.27, 0.31]), fig.add_axes([0.37, 0.11, 0.27, 0.31]), fig.add_axes([0.69, 0.11, 0.27, 0.31])]
    for ax, (col, t) in zip(axes, [('syr', 'Standart SYR'), ('cekSyr', 'Çekirdek SYR'), ('anaSyr', 'Ana SYR')]):
        line_panel(ax, col, t, '2024-07-31', 'pct')
    legend_bottom(fig, [(GC[g], t) for g, t in GLEG], y=0.045)
    pdf.savefig(fig); plt.close(fig)


ROA_ITEMS = [('roaNetFaiz', 'Net Faiz / Kâr Payı Geliri', LACI, 1), ('roaUcret', 'Net Ücret ve Komisyon', '#5E8BC5', 1), ('roaTicari', 'Ticari Kâr/Zarar', '#B99464', 1),
             ('roaDiger', 'Diğer Faaliyet Gelirleri', '#E3C9A0', 1), ('roaOpex', 'Faaliyet Giderleri', KIRMIZI, -1), ('roaKars', 'Karşılık Giderleri', '#E8A0AE', -1), ('roaVergi', 'Vergi', '#C9CED6', -1)]


def roa_comp_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Kârlılık | ROA Ayrıştırması', '12 aylık gelir tablosu kalemleri / 13 aylık ortalama aktifler (%); çubuk üstü: ROA')
    ax = fig.add_axes([0.06, 0.15, 0.9, 0.62])
    for i, g in enumerate(GROUPS):
        a = at(g); pb = 0; nb = 0
        for col, lab, c, sg in ROA_ITEMS:
            v = a[col] * sg
            if v >= 0:
                ax.bar(i, v, bottom=pb, color=c, width=0.5)
                if abs(v) > 0.35:
                    ax.text(i, pb + v / 2, tr(v, 1), ha='center', va='center', color='white', fontsize=8)
                pb += v
            else:
                ax.bar(i, v, bottom=nb, color=c, width=0.5)
                if abs(v) > 0.35:
                    ax.text(i, nb + v / 2, tr(v, 1), ha='center', va='center', color='white', fontsize=8)
                nb += v
        ax.text(i, pb + 0.3, tr(a.roa, 1), ha='center', fontsize=11, fontweight='bold', color=METIN)
    ax.set_xticks(range(len(GROUPS))); ax.set_xticklabels([GSHORT[g].replace(' ', '\n') for g in GROUPS], fontsize=8.5, color='#444')
    ax.axhline(0, color='#666', lw=0.8); style(ax)
    legend_bottom(fig, [(c, l) for _, l, c, _ in ROA_ITEMS], y=0.05, fs=8)
    pdf.savefig(fig); plt.close(fig)


def marj_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Kârlılık | Marj', '12 aylık yıllıklandırılmış; marj bileşenleri 13 aylık ortalama aktiflere oranla (%)')
    ax = fig.add_axes([0.16, 0.12, 0.32, 0.62]); ax.set_title('Net faiz / kâr payı marjı bileşenleri', fontsize=10.5, color=METIN)
    items = [('mKredi', 'Kredilerden alınan', LACI, 1), ('mMenkul', 'Menkul kıymetlerden alınan', '#5E8BC5', 1), ('mDigGel', 'Diğer kalemlerden alınan', '#B99464', 1),
             ('mFon', 'Toplanan fonlara verilen', KIRMIZI, -1), ('mToptan', 'Toptan fonlamaya verilen', '#E8A0AE', -1), ('mDigGid', 'Diğer kalemlere verilen', '#C9CED6', -1)]
    for i, g in enumerate(GROUPS):
        a = at(g); pb = 0; nb = 0
        for col, lab, c, sg in items:
            v = a[col] * sg
            b = pb if v >= 0 else nb
            ax.bar(i, v, bottom=b, color=c, width=0.6)
            if abs(v) > 0.9:
                ax.text(i, b + v / 2, tr(v, 1), ha='center', va='center', color='white', fontsize=8)
            if v >= 0:
                pb += v
            else:
                nb += v
        ax.text(i, pb + 0.5, tr(a.nim, 1), ha='center', fontsize=10, fontweight='bold', color=METIN)
    ax.set_xticks(range(len(GROUPS))); ax.set_xticklabels([GSHORT[g].replace(' ', '\n') for g in GROUPS], fontsize=7, color='#444')
    ax.axhline(0, color='#666', lw=0.8); style(ax)
    for k, (col, lab, c, sg) in enumerate(items):
        fig.add_artist(plt.Circle((0.03, 0.55 - k * 0.03), 0.004, color=c, transform=fig.transFigure))
        fig.text(0.038, 0.55 - k * 0.03, lab, fontsize=8, va='center')
    ax2 = fig.add_axes([0.55, 0.49, 0.41, 0.24]); ax2.set_title('Kredi getirisi − fon maliyeti (%)', fontsize=10.5, loc='left', color=METIN)
    ax2.set_ylim(-26, 40)
    for i, g in enumerate(GROUPS):
        a = at(g); ax2.bar(i, a.krediGetiri, color=LACI, width=0.6); ax2.bar(i, -a.fonMaliyet, color=KIRMIZI, width=0.6)
        ax2.text(i, a.krediGetiri / 2, tr(a.krediGetiri, 1), ha='center', va='center', color='white', fontsize=8)
        if not np.isnan(a.fonMaliyet):
            ax2.text(i, -a.fonMaliyet / 2, tr(-a.fonMaliyet, 1), ha='center', va='center', color='white', fontsize=8)
        ax2.text(i, a.krediGetiri + 1.5, tr(a.krediGetiri - a.fonMaliyet, 1) if not np.isnan(a.fonMaliyet) else '', ha='center', fontsize=9, fontweight='bold', color='#555')
    ax2.set_xticks(range(len(GROUPS))); ax2.set_xticklabels([GSHORT[g].replace(' ', '\n') for g in GROUPS], fontsize=6.5, color='#444'); ax2.axhline(0, color='#666', lw=0.8)
    style(ax2)
    fig.text(0.79, 0.75, '● Kredi getirisi', fontsize=8, color=LACI); fig.text(0.88, 0.75, '● Fon maliyeti', fontsize=8, color=KIRMIZI)
    ax3 = fig.add_axes([0.55, 0.11, 0.41, 0.28]); line_panel(ax3, 'nim', 'Net faiz / kâr payı marjı (%)', '2024-07-31', 'pct')
    legend_bottom(fig, [(GC[g], t) for g, t in GLEG], y=0.05)
    pdf.savefig(fig); plt.close(fig)


def sube_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Şube ve Personel', 'Şube başına personel (bir yıl önce → bugün) ve büyüme serileri')
    for i, g in enumerate(GROUPS):
        a = at(g); b = at(g, PREV); ax = fig.add_axes([0.055 + i * 0.134, 0.5, 0.085, 0.2])
        top = max(b.subePers, a.subePers) * 1.25
        ax.bar([0, 1], [b.subePers, a.subePers], color=[GRI, GC[g]], width=0.6); ax.set_ylim(0, top); ax.set_xlim(-0.6, 1.6); ax.axis('off')
        ax.text(0, b.subePers + top * 0.03, tr(b.subePers, 1), ha='center', fontsize=10, fontweight='bold', color='#666'); ax.text(1, a.subePers + top * 0.03, tr(a.subePers, 1), ha='center', fontsize=10, fontweight='bold', color=METIN)
        ax.text(0, -top * 0.07, f"{AYK[PREV.month - 1]} {PREV.year}", ha='center', va='top', fontsize=7, color='#666'); ax.text(1, -top * 0.07, f"{AYK[LAST.month - 1]} {LAST.year}", ha='center', va='top', fontsize=7, color='#666')
        ax.text(0.5, top * 1.2, trp((a.subePers / b.subePers - 1) * 100, 2), ha='center', fontsize=10, fontweight='bold', color=METIN)
        ax.text(0.5, top * 1.32, GSHORT[g], ha='center', fontsize=8.5, color='#444')
    ax1 = fig.add_axes([0.05, 0.12, 0.42, 0.3]); line_panel(ax1, 'g_sube', 'Şube sayısı, yıllık %', '2024-07-31', 'pct')
    ax2 = fig.add_axes([0.54, 0.12, 0.42, 0.3]); line_panel(ax2, 'g_pers', 'Personel sayısı, yıllık %', '2024-01-31', 'pct')
    legend_bottom(fig, [(GC[g], t) for g, t in GLEG], y=0.045)
    pdf.savefig(fig); plt.close(fig)


def notes_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Metodoloji ve Notlar')
    txt = [
        f"• Veri kaynağı: BDDK Aylık Bülten (Temel Gösterim), dönem {DON}. Gruplar: Sektör, Mevduat, Kamu Mevduat, Yerli Özel Mevduat, Yabancı Mevduat, Katılım, Kalkınma ve Yatırım.",
        "• Kalkınma ve Yatırım Bankaları mevduat kabul etmediğinden fonlama ve mevduat bazlı rasyolarda yer almaz.",
        "• Krediler = Krediler + Takipteki Alacaklar + Finansal Kiralama Alacakları (brüt); Canlı Krediler = Krediler + Finansal Kiralama.",
        "• Tüketici = Tüketici Kredileri (dövize endeksli dahil) + Bireysel Kredi Kartları; Ticari/Kurumsal = Canlı − Tüketici − KOBİ − Finansal Kiralama.",
        "• NPL = Takipteki Alacaklar / (Krediler + Takip + Finansal Kiralama); Özel Karşılık Oranı = Üçüncü Aşama Karşılık / Takipteki Alacaklar.",
        "• Nakit ve Benzerleri = Nakit + TCMB + Para Piyasası + Bankalar + Zorunlu Karşılıklar + MK Ödünç + Ters Repo; Diğer Aktifler = kalan.",
        "• Toptan Fonlama = Bankalara Borçlar + İhraç Edilen Menkul Kıymetler + Para Piyasalarına Borçlar; Sermaye Benzeri = sermaye hesabına dahil borçlanma araçları.",
        "• Toplanan Fonlar = Mevduat (Katılım Fonu); Kıymetli Madenler = KMDH (yurt içi + yurt dışı yerleşik); YP fonlar kıymetli maden hariç gösterilir.",
        "• Faiz/Kâr Payı Gelirleri nakdi kredi komisyonlarını içerir; Ücret ve Komisyon Gelirleri = gayrinakdi kredi komisyonları + bankacılık hizmet gelirleri.",
        "• Ticari Kâr/Zarar = sermaye piyasası + kambiyo + net parasal pozisyon; Karşılık Giderleri = özel provizyon + genel karşılık + değer azalma + diğer provizyonlar.",
        "• 12 aylık kalemler yıl içi kümülatif tablodan türetilir (YTD(t) − YTD(t−12) + YTD(Aralık)); ROA/ROE/NIM/Op-Ex oranları 13 aylık ortalama aktif/özkaynağa bölünür.",
        "• Kredi getirisi = 12 aylık kredi + finansal kiralama gelirleri / 13 aylık ortalama canlı krediler; fon maliyeti = 12 aylık mevduata verilen faiz / 13 aylık ortalama mevduat.",
        "• YP büyümeleri (USD) BDDK USD tablosundan türetilen örtük USD/TL kuruyla hesaplanır; menkul kıymet büyümeleri HTM hariç, MK reeskontları dahil.",
        "• Kompozisyon ve pazar payı sayfaları son 25 ayın %100 yığılmış alan grafikleridir; sağ uçtaki etiketler son ayın paylarıdır. Aylık net kâr yıl içi kümülatiften türetilir (Ocak = o ayın YTD değeri).",
        "• Grup karnesinde sıralama Sektör hariç altı grup arasında yapılır; 'Ayın Görünümü' sayfasındaki yorum verilerden otomatik üretilir ve hata içerebilir.",
        "• Bu rapor BDDK kaynaklı verilerle ekordion.com.tr tarafından bilgilendirme amacıyla hazırlanmıştır; yatırım danışmanlığı niteliği taşımaz."]
    y = 0.80
    for t in txt:
        for k, line in enumerate(textwrap.wrap(t, 150)):
            fig.text(0.04, y, line if k == 0 else '   ' + line, fontsize=9.2, va='top', color=METIN); y -= 0.028
        y -= 0.012
    pdf.savefig(fig); plt.close(fig)


def netkar_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Kârlılık | Aylık Net Kâr', 'Yıl içi kümülatiften türetilmiş aylık net kâr; milyar ₺ (çizgi: 3 aylık ortalama)')
    ax = fig.add_axes([0.05, 0.47, 0.91, 0.30])
    s = series('S', 'netKar_m', '2024-01-31') / 1e3
    ax.bar(s.index, s.values, width=20, color=LACI, alpha=0.9)
    ma = s.rolling(3).mean(); ax.plot(ma.index, ma.values, color=KIRMIZI, lw=1.8)
    for dt_, v in list(s.items())[-13:]:
        ax.text(dt_, v + 3, tr(v, 0), ha='center', fontsize=7, color='#333')
    ax.set_title('Bankacılık sektörü', fontsize=10.5, color=METIN); style(ax)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10])); ax.xaxis.set_major_formatter(mdates.DateFormatter('%m.%y'))
    gs = [g for g in GROUPS if g != 'S']
    bas13 = (LAST - pd.DateOffset(months=12)).strftime('%Y-%m-%d')
    for i, g in enumerate(gs):
        axg = fig.add_axes([0.05 + i * 0.157, 0.12, 0.12, 0.24])
        sg = series(g, 'netKar_m', bas13) / 1e3
        axg.bar(range(len(sg)), sg.values, color=GC[g], width=0.75)
        axg.set_title(GSHORT[g], fontsize=9, color=METIN)
        axg.set_xticks([0, len(sg) - 1]); axg.set_xticklabels([sg.index[0].strftime('%m.%y'), sg.index[-1].strftime('%m.%y')], fontsize=6.5, color='#555')
        style(axg); axg.tick_params(labelsize=6.5)
        v = sg.iloc[-1]; axg.text(len(sg) - 1, v, tr(v, 1), fontsize=7, fontweight='bold', color=GC[g], ha='center', va='bottom')
    fig.text(0.05, 0.05, 'Alt paneller: son 13 ay, her grup kendi ölçeğinde.', fontsize=8, color='#333')
    pdf.savefig(fig); plt.close(fig)


def kaldirac_page(pdf):
    line_page(pdf, 'Bilanço | Kaldıraç ve YP Dengesi', [
        dict(col='kaldirac', title='Kaldıraç (aktif / özkaynak, x)', start='2023-01-31', fmt='num', d=1),
        dict(col='ozkAktif', title='Özkaynak / aktif (%)', start='2023-01-31', fmt='num', d=1),
        dict(col='g_ozk', title='Özkaynak büyümesi (yıllık %)', start='2024-07-31'),
        dict(col='ypGap', title='Bilanço içi YP açığı: (YP kredi − YP fon) / aktif (%)', start='2023-01-31', fmt='num', d=1, groups=DEPG)],
        [[1, 1], [1, 1]], sub='YP açığı pozitifken YP krediler YP fonları aşar (bilanço dışı hariç)')


def momentum_page(pdf):
    line_page(pdf, 'Krediler | Momentum', [
        dict(col='g3_canliTP', title='TP canlı kredi – 3 aylık yıllıklandırılmış (%)', start='2024-07-31'),
        dict(col='g_canliTP', title='TP canlı kredi – 12 aylık (%)', start='2024-07-31'),
        dict(col='g3_mvTP', title='TP mevduat – 3 aylık yıllıklandırılmış (%)', start='2024-07-31', groups=DEPG),
        dict(col='g1_canliTP', title='TP canlı kredi – aylık (%)', start='2025-01-31', fmt='num', d=1)],
        [[1, 1], [1, 1]], sub='3 aylık yıllıklandırılmış seri, kredi ivmesindeki dönüşleri 12 aylık seriden önce gösterir')


# ---------- kurulum ----------
def build(path):
    SAYFA[0] = 0
    pdf = PdfPages(path)
    cover(pdf)
    gorunum_page(pdf)
    table_page(pdf, 'Özet Tablo', 'Yüzde; büyümeler yıllık, kârlılık ve Op-Ex rasyoları 12 aylık yıllıklandırılmış',
               [(lab, [at(g)[col] for g in GROUPS]) for lab, col in OZET_SATIRLAR],
               note='Mevduat göstergeleri Kalkınma-Yatırım grubu için tanımsızdır.')
    karne_page(pdf)
    # Kârlılık
    netkar_page(pdf)
    rows = []
    for lab, col in GELIR_SATIRLAR:
        sg = -1 if col in GIDER_KALEMLERI else 1
        rows.append((lab, [(at(g)['gy_' + col], at(g)[col] * sg) for g in GROUPS]))
    table_page(pdf, 'Kârlılık | Gelir Tablosu', 'Milyon ₺, yıl içi kümülatif; renkli rakamlar yıllık yüzde değişim', rows)
    line_page(pdf, 'Kârlılık | Rasyolar', [dict(col='roa', title='Aktif kârlılığı (ROA)', yfmt='pct'), dict(col='roe', title='Özkaynak kârlılığı (ROE)'), dict(col='nim', title='Net faiz / kâr payı marjı')], [[1, 1, 1]], sub='12 aylık yıllıklandırılmış')
    roa_comp_page(pdf)
    line_page(pdf, 'Kârlılık | ROA Bileşenleri', [dict(col='roaNetFaiz', title='Net faiz / kâr payı geliri (%)', fmt='num'), dict(col='roaUcret', title='Net ücret ve komisyon (%)', fmt='num'), dict(col='roaTicari', title='Ticari kâr / zarar (%)', fmt='num'), dict(col='roaDiger', title='Diğer faaliyet gelirleri (%)', fmt='num'), dict(col='roaOpexN', title='Faaliyet giderleri (%)', fmt='num'), dict(col='roaKarsN', title='Karşılık giderleri (%)', fmt='num'), dict(col='roaVergiN', title='Vergi (%)', fmt='num')], [[1, 1, 1, 1], [1, 1, 1]], sub='12 aylık gelir tablosu kalemi / 13 aylık ortalama aktifler')
    marj_page(pdf)
    line_page(pdf, 'Kârlılık | Gelir Rasyoları', [dict(col='netFaizBrut', title='Net faiz geliri / brüt faaliyet kârı'), dict(col='netFaizOpex', title='Net faiz geliri / Op-Ex'), dict(col='ucrGelAk', title='Ücret, komisyon ve hizmet gelirleri / aktifler'), dict(col='ucrBrut', title='Ücret ve komisyon / brüt faaliyet kârı'), dict(col='ucrOpex', title='Ücret ve komisyon / Op-Ex'), dict(col='giderGelir', title='Gider / gelir oranı', start='2023-01-31', fmt='num')], [[1, 1, 1], [1, 1, 1]], sub='12 aylık yıllıklandırılmış')
    line_page(pdf, 'Kârlılık | Faaliyet Giderleri', [dict(col='opexAktif', title='Op-Ex / aktifler', start='2023-07-31', fmt='num'), dict(col='g_personel_12', title='Personel giderleri artışı (12 aylık, %)', fmt='num'), dict(col='g_digIsl_12', title='Diğer işletme giderleri artışı (12 aylık, %)', fmt='num'), dict(col='g_opex_12', title='Toplam Op-Ex artışı (12 aylık, %)', fmt='num')], [[1, 1], [1, 1]], sub='12 aylık yıllıklandırılmış')
    # Bilanço
    area_page(pdf, 'Bilanço | Aktif Yapısı', 'Aktif kalemlerinin payı (%), son 25 ay; panel başlığı: toplam aktif ve yıllık büyüme', AKTIF)
    line_page(pdf, 'Bilanço | Aktif Büyümesi', [dict(col='aktifTPag', title='Aktif TP ağırlığı', start='2023-01-31'), dict(col='aktifPay', title='Aktif pazar payı', start='2023-07-31', yfmt='pct', groups=['M', 'KA', 'YO', 'YA', 'KB', 'KY']), dict(col='g_akTP', title='TP aktif büyümesi'), dict(col='g_akYP_usd', title='YP aktif büyümesi (USD)', yfmt='pct'), dict(col='g_aktif', title='Toplam aktif büyümesi')], [[1, 1], [1, 1, 1]])
    area_page(pdf, 'Bilanço | Pasif Yapısı', 'Pasif kalemlerinin payı (%), son 25 ay', PASIF)
    line_page(pdf, 'Bilanço | Pasif Büyümesi', [dict(col='pasifTPag', title='Pasif TP ağırlığı', start='2023-01-31'), dict(col='g_pasTP', title='TP pasif büyümesi'), dict(col='g_pasYP_usd', title='YP pasif büyümesi (USD)', yfmt='pct')], [[1, 1, 1]])
    kaldirac_page(pdf)
    # Krediler
    area_page(pdf, 'Krediler | Canlı Kredi Yapısı', 'Canlı kredi bileşenlerinin payı (%), son 25 ay', CANLI)
    momentum_page(pdf)
    line_page(pdf, 'Krediler | Tüketici Büyümesi', [dict(col='g_tukKK', title='Tüketici kredileri ve kredi kartları', start='2023-01-31', groups=DEPG), dict(col='g_konut', title='Konut', groups=DEPG), dict(col='g_tasit', title='Taşıt', groups=DEPG), dict(col='g_ihtiyac', title='İhtiyaç', groups=DEPG), dict(col='g_kk', title='Bireysel kredi kartları', groups=DEPG)], [[2, 1], [1, 1, 1]], sub='Yıllık büyüme (%)')
    area_page(pdf, 'Krediler | Tüketici Kredisi Yapısı', 'Tüketici kredisi bileşenlerinin payı (%), son 25 ay', TUK, groups=DEPG, totfmt=2)
    share_page(pdf, 'Krediler | Tüketici Pazar Payı', [('Tüketici + kredi kartı', 'tukKK', 2), ('Konut', 'konut', 2), ('Taşıt', 'tasit', 2), ('İhtiyaç', 'ihtiyac', 2), ('Bireysel kredi kartları', 'kk', 2)])
    area_page(pdf, 'Krediler | Tüzel Kredi Yapısı', 'Tüzel kredi bileşenlerinin payı (%), son 25 ay', TUZEL)
    share_page(pdf, 'Krediler | Tüzel Pazar Payı', [('Tüzel krediler', 'tuzel', 1), ('Ticari / kurumsal', 'ticKur', 1), ('KOBİ', 'kobi', 1), ('Finansal kiralama', 'fk', 1)], groups=('KA', 'YO', 'YA', 'KB', 'KY'))
    line_page(pdf, 'Krediler | Tüzel Büyümesi', [dict(col='g_tuzel', title='Tüzel krediler', start='2023-01-31'), dict(col='g_ticKur', title='Ticari / kurumsal'), dict(col='g_kobi', title='KOBİ'), dict(col='g_fk', title='Finansal kiralama', groups=['S', 'KB', 'KY'])], [[1], [1, 1, 1]], sub='Yıllık büyüme (%)')
    # Aktif kalitesi
    line_page(pdf, 'Aktif Kalitesi | Takipteki Alacaklar', [dict(col='npl', title='NPL oranı', start='2023-01-31', fmt='num', d=2), dict(col='ozelKarsOran', title='Özel karşılık oranı', start='2023-07-31', fmt='num', d=1), dict(col='nplTuk', title='Tüketici NPL', start='2023-01-31', fmt='num', d=2, yr_only=True, groups=DEPG), dict(col='nplKobi', title='KOBİ NPL', start='2022-07-31', fmt='num', d=2, yr_only=True), dict(col='nplTic', title='Ticari / kurumsal NPL', start='2022-07-31', fmt='num', d=2, yr_only=True)], [[1, 1], [1, 1, 1]], sub='Yüzde')
    # Menkul
    area_page(pdf, 'Menkul Kıymetler | Portföy Yapısı', 'Menkul kıymet portföyünün sınıflandırma ve para birimine göre payı (%), son 25 ay', MENKUL)
    line_page(pdf, 'Menkul Kıymetler | Büyüme ve Pay', [dict(col='g_mkGrTP', title='TP menkul kıymet büyümesi'), dict(col='g_mkGrYP', title='YP menkul kıymet büyümesi (TL)'), dict(col='g_mkGr', title='Toplam menkul kıymet büyümesi'), dict(col='mkTPak', title='TP menkul / TP aktif'), dict(col='mkYPak', title='YP menkul / YP aktif'), dict(col='mkAk', title='Menkul / toplam aktif')], [[1, 1, 1], [1, 1, 1]], sub='Büyümeler HTM hariç, reeskont dahil; yüzde')
    # Fonlama
    area_page(pdf, 'Fonlama | Toplanan Fon Yapısı', 'Toplanan fon bileşenlerinin payı (%), son 25 ay', FON, groups=DEPG)
    share_page(pdf, 'Fonlama | Pazar Payı', [('Toplam vadesiz', 'vadesiz', 1), ('Toplam vadeli', 'vadeli', 1), ('TP vadesiz', 'vdsTP', 1), ('TP vadeli', 'vadeliTP', 1), ('YP vadesiz', 'vdsYP', 1), ('YP vadeli', 'vadeliYP', 1)])
    line_page(pdf, 'Fonlama | Büyüme', [dict(col='g_vadeliTP', title='TP vadeli', groups=DEPG), dict(col='g_vadeliYP', title='YP vadeli (TL)', groups=DEPG), dict(col='g_vadeli', title='Toplam vadeli', groups=DEPG), dict(col='g_vdsTP', title='TP vadesiz', groups=DEPG), dict(col='g_vdsYP', title='YP vadesiz (TL)', groups=DEPG), dict(col='g_vadesiz', title='Toplam vadesiz', groups=DEPG)], [[1, 1, 1], [1, 1, 1]], sub='Yıllık büyüme (%)')
    line_page(pdf, 'Fonlama | Yükümlülük Payları', [dict(col='tlVdlYuk', title='TP vadeli fonlar / toplam yükümlülükler', yfmt='pct', groups=DEPG), dict(col='ypVdlYuk', title='YP vadeli fonlar / toplam yükümlülükler', yfmt='pct', groups=DEPG), dict(col='vdlYuk', title='Toplam vadeli / toplam yükümlülükler', yfmt='pct', groups=DEPG), dict(col='tlVdsYuk', title='TP vadesiz / toplam yükümlülükler', yfmt='pct', groups=DEPG), dict(col='ypVdsYuk', title='YP vadesiz / toplam yükümlülükler', yfmt='pct', groups=DEPG), dict(col='vdsYuk', title='Toplam vadesiz / toplam yükümlülükler', yfmt='pct', groups=DEPG)], [[1, 1, 1], [1, 1, 1]])
    line_page(pdf, 'Bilanço Rasyoları', [dict(col='tlKrediMev', title='TL kredi / TL mevduat', groups=DEPG), dict(col='ypKrediMev', title='YP kredi / YP mevduat', groups=DEPG), dict(col='krediMev', title='Toplam kredi / mevduat', groups=DEPG), dict(col='tlMkMev', title='TL menkul kıymet / TL mevduat', groups=DEPG), dict(col='ypMkMev', title='YP menkul kıymet / YP mevduat', groups=DEPG), dict(col='mkMev', title='Toplam menkul kıymet / mevduat', groups=DEPG)], [[1, 1, 1], [1, 1, 1]], sub='Yüzde; mevduat = toplanan fonlar (katılım fonu dahil)')
    syr_page(pdf)
    sube_page(pdf)
    notes_page(pdf)
    pdf.close()
    return SAYFA[0]


# sayfaların ihtiyaç duyduğu ek türetilmiş kolonlar
D['aktifPay'] = D.aktif / D.groupby('d').aktif.transform(lambda x: x[D.loc[x.index, 'g'] == 'S'].iloc[0]) * 100
D['roaOpexN'] = -D.roaOpex; D['roaKarsN'] = -D.roaKars; D['roaVergiN'] = -D.roaVergi

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'bankacilik_monitoru.pdf'
    n = build(out)
    print(f'PDF hazır: {out} ({n} sayfa)')
