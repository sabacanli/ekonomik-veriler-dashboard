#!/usr/bin/env python3
"""Bankacılık Monitörü — aylık PDF rapor (ekordion.com.tr tasarımı).
Kullanım: python rapor.py <çıktı.pdf>   (önce fetch_bddk.py ve gorunum.py; veri calc.py'den gelir)
Akış (ekordion çerçevesi): Görünüm → Büyüme ve ivme → Bilanço ve kredi yapısı → Kârlılık → Aktif kalitesi →
Fonlama ve dolarizasyon → Sermaye → Ekler. Kendi analizlerimiz: kredi ivme haritası, segment ivmesi, reel büyüme,
pazar payı değişimi, hacim–marj ayrıştırması, kârlılık kalitesi, NPL oluşum hızı, sermaye tamponu, haftalık köprü.
Kompozisyon sayfaları zaman serili %100 yığılmış alan grafikleridir (son 25 ay)."""
import warnings; warnings.filterwarnings('ignore')
import json, sys, textwrap
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from calc import *  # noqa: E402,F401  (D, LAST, GROUPS, DEPG, GSHORT, GNAME, at, series, yoy)
from analiz import *  # noqa: E402,F401  (ek göstergeler, hacim_marj, pay_degisim, haftalik_kopru, SEGMENTLER, PAY_KOL, ENF_SON)
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
    for i, row in enumerate(rows):
        lab, vals = row[0], row[1]; dec = row[2] if len(row) > 2 else 1
        y = 1 - (i + 2) * rh; x = 0; bg = ACIK if i % 2 else 'white'
        if vals is None:   # bölüm başlığı
            ax.add_patch(Rectangle((0, y), 1, rh, facecolor='#E6EAF0', edgecolor='#D9DEE6', lw=0.5, transform=ax.transAxes))
            ax.text(0.008, y + rh / 2, lab, ha='left', va='center', fontsize=8.5, color=LACI, fontweight='bold', transform=ax.transAxes)
            continue
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
                    ax.text(x + cw[j] / 2, y + rh / 2, tr(v, dec), ha='center', va='center', fontsize=9.2, color=METIN,
                            fontweight='bold' if colgroups[j - 1] == 'S' else 'normal', transform=ax.transAxes)
            x += cw[j]
    if note:
        fig.text(0.03, 0.05, note, fontsize=8, color='#333')
    pdf.savefig(fig); plt.close(fig)


OZET_SATIRLAR = [('BÜYÜME (yıllık %)', None, 1), ('Toplam aktif', 'g_aktif', 1), ('TP canlı krediler', 'g_canliTP', 1),
                 ('TP canlı krediler, 3 aylık yıllıklandırılmış', 'g3_canliTP', 1), ('Reel TP canlı krediler (TÜFE arındırılmış)', 'gr_canliTP', 1),
                 ('TP toplanan fonlar', 'g_mvTP', 1), ('YP toplanan fonlar (USD)', 'g_mvYP_usd', 1),
                 ('KÂRLILIK (12 aylık yıllıklandırılmış, %)', None, 1), ('Aktif kârlılığı (ROA)', 'roa', 2), ('Özkaynak kârlılığı (ROE)', 'roe', 1),
                 ('Net faiz marjı', 'nim', 2), ('Çekirdek kârlılık / ortalama aktif', 'cekirdekAktif', 2), ('Gider / gelir', 'giderGelir', 1),
                 ('AKTİF KALİTESİ (%)', None, 1), ('NPL oranı', 'npl', 2), ('NPL oluşum hızı, 3 aylık ortalama (yıllıklandırılmış)', 'nplOlusum3', 2),
                 ('Özel karşılık oranı', 'ozelKarsOran', 1), ('Risk maliyeti (karşılık / ortalama canlı kredi)', 'riskMaliyeti', 2),
                 ('FONLAMA VE SERMAYE', None, 1), ('Toplanan fon TP ağırlığı (%)', 'fonTPag', 1), ('TL kredi / TL mevduat (%)', 'tlKrediMev', 1),
                 ('Standart SYR (%)', 'syr', 1), ('Fazla sermaye, %12 hedefe göre (milyar ₺)', 'fazlaSermaye', 0)]
GELIR_SATIRLAR = [('Faiz gelirleri', 'faizGel'), ('Faiz giderleri', 'faizGid'), ('Net faiz geliri', 'netFaiz'),
                  ('Ücret ve Komisyon Gelirleri', 'ucrGel'), ('Ücret ve Komisyon Giderleri', 'ucrGid'), ('Net Ücret ve Komisyon Geliri', 'netUcret'),
                  ('Ticari Kâr / Zarar', 'ticari'), ('Diğer Faaliyet Gelirleri', 'digGel'), ('Brüt Faaliyet Kârı', 'brutKar'),
                  ('Personel Giderleri', 'personel'), ('Diğer İşletme Giderleri', 'digIsl'), ('Faaliyet Giderleri (Op-Ex)', 'opex'),
                  ('Karşılık Giderleri', 'karsilik'), ('Vergi Öncesi Kâr', 'vergiOncesi'), ('Vergi Karşılıkları', 'vergi'), ('Net Kâr', 'netKar')]
GIDER_KALEMLERI = ['faizGid', 'ucrGid', 'personel', 'digIsl', 'opex', 'karsilik', 'vergi']


def karne_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Grup Karnesi', f'{DON} itibarıyla; hücre rengi grup sıralamasını gösterir (koyu yeşil = en iyi). Sektör sütunu referanstır.')
    metrics = [('TP canlı kredi büyümesi, 12 aylık (%)', 'g_canliTP', 1, 1), ('TP canlı kredi, 3 aylık yıllıklandırılmış (%)', 'g3_canliTP', 1, 1),
               ('Reel TP canlı kredi büyümesi (%)', 'gr_canliTP', 1, 1), ('TP mevduat büyümesi (%)', 'g_mvTP', 1, 1),
               ('NPL oranı (%)', 'npl', 2, -1), ('NPL oluşum hızı, 3 aylık (%)', 'nplOlusum3', 2, -1), ('Özel karşılık oranı (%)', 'ozelKarsOran', 1, 1),
               ('Risk maliyeti (%)', 'riskMaliyeti', 2, -1), ('Çekirdek kârlılık / aktif (%)', 'cekirdekAktif', 2, 1), ('ROE (%)', 'roe', 1, 1),
               ('Net faiz marjı (%)', 'nim', 2, 1), ('Gider / gelir (%)', 'giderGelir', 1, -1), ('Standart SYR (%)', 'syr', 1, 1),
               ('Fazla sermaye, %12 hedefe göre (milyar ₺)', 'fazlaSermaye', 0, 1), ('Toplanan fon TP ağırlığı (%)', 'fonTPag', 1, 1)]
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


ROA_ITEMS = [('roaNetFaiz', 'Net faiz geliri', LACI, 1), ('roaUcret', 'Net Ücret ve Komisyon', '#5E8BC5', 1), ('roaTicari', 'Ticari Kâr/Zarar', '#B99464', 1),
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
    ax = fig.add_axes([0.16, 0.12, 0.32, 0.62]); ax.set_title('Net faiz marjı bileşenleri', fontsize=10.5, color=METIN)
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
    ax3 = fig.add_axes([0.55, 0.11, 0.41, 0.28]); line_panel(ax3, 'nim', 'Net faiz marjı (%)', '2024-07-31', 'pct')
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
        "• Kompozisyon sayfaları son 25 ayın %100 yığılmış alan grafikleridir; sağ uçtaki etiketler son ayın paylarıdır. Aylık net kâr yıl içi kümülatiften türetilir (Ocak = o ayın YTD değeri).",
        "• İvme: 3 aylık yıllıklandırılmış büyüme ((X(t)/X(t−3))^4 − 1); reel büyümeler TÜFE yıllık enflasyonla arındırılır ((1+g)/(1+π) − 1). NPL oluşum hızı = takipteki alacak bakiyesindeki aylık net artış / önceki ay canlı krediler × 12 (satış ve silme sonrası net).",
        "• Hacim–marj ayrıştırması: ΔNFG = (Δortalama aktif × önceki yıl NIM) + (ΔNIM × bu yıl ortalama aktif); çekirdek kârlılık = (net faiz + net komisyon − faaliyet gideri) / ortalama aktif; risk maliyeti = 12 aylık karşılık gideri / ortalama canlı kredi.",
        "• Fazla sermaye = yasal özkaynak − %12 × risk ağırlıklı aktifler (BDDK hedef rasyosu); RAK yoğunluğu = RAK / aktif. Haftalık köprü sayfası sitedeki haftalık BDDK verisinden ay sonu sonrasını özetler.",
        "• Grup karnesinde sıralama Sektör hariç altı grup arasında yapılır; 'Ayın Görünümü' sayfasındaki yorum verilerden otomatik üretilir ve hata içerebilir. Faiz kalemleri katılım bankaları için kâr payını kapsar.",
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


# ---------- ekordion analiz sayfaları ----------
def multi_panel(ax, items, title, start, fmt='pct', d=1, yfmt=None):
    """items: [(g, col, etiket, renk)] — farklı serileri aynı panelde çizer."""
    ends = []
    for g, col, lab, color in items:
        sr = series(g, col, start).dropna()
        if len(sr) == 0:
            continue
        ax.plot(sr.index, sr.values, color=color, lw=1.9)
        v = sr.iloc[-1]; ends.append((v, color, (trp(v, d) if fmt == 'pct' else tr(v, d)) + ' ' + lab))
    ax.set_title(title, fontsize=10.5, pad=6, color=METIN); style(ax); ay_ekseni(ax)
    if yfmt == 'pct':
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: '%' + tr(v, 0 if abs(v) >= 10 else 1)))
    ax.set_xlim(right=ax.get_xlim()[1] + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.02)
    line_end_labels(ax, ends, fs=7)


def buyume_page(pdf):
    line_page(pdf, 'Büyüme | Bilanço', [dict(col='g_akTP', title='TP aktif'), dict(col='g_akYP_usd', title='YP aktif (USD)', yfmt='pct'),
                                        dict(col='g_canliTP', title='TP canlı krediler'), dict(col='g_canliYP_usd', title='YP canlı krediler (USD)', yfmt='pct'),
                                        dict(col='g_mvTP', title='TP toplanan fonlar', groups=DEPG), dict(col='g_mvYP_usd', title='YP toplanan fonlar (USD)', yfmt='pct', groups=DEPG)],
              [[1, 1, 1], [1, 1, 1]], sub='Yıllık büyüme (%); YP kalemler örtük USD/TL kuruyla dolar bazında')


def ivme_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Büyüme | Kredi İvme Haritası', 'Sol: yatay eksen 12 aylık, dikey eksen 3 aylık yıllıklandırılmış TP canlı kredi büyümesi; köşegenin üstü hızlanma · Sağ: sektör segmentleri')
    ax = fig.add_axes([0.06, 0.14, 0.40, 0.64]); S = at('S'); xs, ys = [], []
    for g in GROUPS:
        a = at(g); x, y = a.g_canliTP, a.g3_canliTP
        if np.isnan(x) or np.isnan(y):
            continue
        ax.scatter(x, y, s=170 if g == 'S' else 110, color=GC[g], zorder=3, edgecolor='white', lw=1)
        ax.annotate(GSHORT[g], (x, y), xytext=(7, 6), textcoords='offset points', fontsize=8.5, color=GC[g], fontweight='bold')
        xs.append(x); ys.append(y)
    lo, hi = min(xs + ys) - 6, max(xs + ys) + 6
    ax.plot([lo, hi], [lo, hi], color='#999', lw=0.9, ls='--'); ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
    ax.axvline(S.g_canliTP, color=GRI, lw=0.6, ls=':'); ax.axhline(S.g3_canliTP, color=GRI, lw=0.6, ls=':')
    ax.text(hi - 1, lo + 1.5, 'yavaşlıyor', ha='right', fontsize=8.5, color='#888'); ax.text(lo + 1, hi - 2.5, 'hızlanıyor', ha='left', fontsize=8.5, color='#888')
    ax.set_xlabel('12 aylık büyüme (%)', fontsize=8.5, color='#444'); ax.set_ylabel('3 aylık yıllıklandırılmış büyüme (%)', fontsize=8.5, color='#444')
    style(ax); ax.grid(True, axis='both', ls='-', color='#E3E7EE', lw=0.7)
    ax2 = fig.add_axes([0.58, 0.14, 0.37, 0.64])
    y = np.arange(len(SEGMENTLER))[::-1]
    g12 = [S['g_' + c] for c, _ in SEGMENTLER]; g3 = [S['g3_' + c] for c, _ in SEGMENTLER]
    ax2.barh(y + 0.18, g12, height=0.34, color=GRI, label='12 aylık'); ax2.barh(y - 0.18, g3, height=0.34, color=KIRMIZI, label='3 aylık yıllıklandırılmış')
    for yi, a_, b_ in zip(y, g12, g3):
        ax2.text(max(a_, b_) + 1, yi, trp(b_ - a_), va='center', fontsize=8, color=('#2E7D5B' if b_ >= a_ else KIRMIZI), fontweight='bold')
    ax2.set_yticks(y); ax2.set_yticklabels([ad for _, ad in SEGMENTLER], fontsize=8.5); style(ax2); ax2.grid(True, axis='x', ls='-', color='#E3E7EE', lw=0.7); ax2.grid(False, axis='y')
    ax2.set_xlim(0, max(g12 + g3) * 1.22)
    ax2.set_title('Sektör segmentleri (%); sağdaki rakam ivme farkı (3 aylık − 12 aylık)', fontsize=9.5, color=METIN)
    ax2.legend(loc='upper right', fontsize=8, frameon=False)
    pdf.savefig(fig); plt.close(fig)


def segment_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Büyüme | Segment İvmesi', '3 aylık yıllıklandırılmış büyüme (%); 12 aylık seriden önce dönen eğilimi gösterir')
    axes = grid_axes(fig, [[1, 1], [1, 1]])
    multi_panel(axes[0], [('S', 'g3_tukKK', 'Tüketici + KK', LACI), ('S', 'g3_kobi', 'KOBİ', KIRMIZI), ('S', 'g3_ticKur', 'Ticari / kurumsal', '#2E7D5B'), ('S', 'g3_mvTP', 'TP mevduat', '#B99464')],
                'Sektör: segmentler', '2024-07-31')
    line_panel(axes[1], 'g3_tukKK', 'Tüketici + KK, gruplar', '2024-07-31', 'pct', DEPG)
    line_panel(axes[2], 'g3_kobi', 'KOBİ, gruplar', '2024-07-31', 'pct')
    line_panel(axes[3], 'g3_ticKur', 'Ticari / kurumsal, gruplar', '2024-07-31', 'pct')
    legend_bottom(fig, [(GC[g], t) for g, t in GLEG])
    pdf.savefig(fig); plt.close(fig)


def reel_page(pdf):
    alt = f"TÜFE yıllık enflasyonla arındırılmış ((1+g)/(1+π) − 1); TÜFE serisi {ENF_SON.strftime('%m.%Y') if ENF_SON is not None else '—'} dahil"
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Büyüme | Reel Büyüme', alt)
    axes = grid_axes(fig, [[1, 1], [1, 1]])
    multi_panel(axes[0], [('S', 'g_canliTP', 'nominal', GRI), ('S', 'gr_canliTP', 'reel', LACI), ('S', 'tufe', 'TÜFE', KIRMIZI)], 'Sektör: TP canlı krediler, nominal ve reel (%)', '2023-01-31')
    line_panel(axes[1], 'gr_canliTP', 'Reel TP canlı kredi büyümesi, gruplar (%)', '2023-01-31', 'pct')
    line_panel(axes[2], 'gr_mvTP', 'Reel TP mevduat büyümesi, gruplar (%)', '2023-01-31', 'pct', DEPG)
    line_panel(axes[3], 'gr_akTP', 'Reel TP aktif büyümesi, gruplar (%)', '2023-01-31', 'pct')
    legend_bottom(fig, [(GC[g], t) for g, t in GLEG])
    pdf.savefig(fig); plt.close(fig)


def pay_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Büyüme | Pazar Payı Değişimi', f'Grupların sektör içindeki payının 12 aylık değişimi (puan); çubuk ucundaki rakam {DON} payı (%)')
    P = pay_degisim(); gs = GROUPS[1:]
    KISA = {'KB': 'Katılım', 'M': 'Mevduat', 'KA': 'Kamu', 'YO': 'Yerli Özel', 'YA': 'Yabancı', 'KY': 'Kalk.-Yat.'}
    for ax, (col, ad) in zip(grid_axes(fig, [[1, 1, 1, 1], [1, 1, 1]], top=0.83, bottom=0.09), PAY_KOL):
        y = np.arange(len(gs))[::-1]
        vals = [P[g][col]['degisim'] if P[g][col] else np.nan for g in gs]
        ax.barh(y, [0 if np.isnan(v) else v for v in vals], color=[GC[g] for g in gs], height=0.62)
        for yi, g, v in zip(y, gs, vals):
            if np.isnan(v):
                ax.text(0, yi, ' —', va='center', fontsize=7.5, color='#888'); continue
            ax.text(v + (0.05 if v >= 0 else -0.05), yi, f"{trp(v, 2).replace('%', '')}  (pay %{tr(P[g][col]['pay'], 1)})", va='center', ha='left' if v >= 0 else 'right', fontsize=6.5, color=METIN)
        ax.set_yticks(y); ax.set_yticklabels([KISA[g] for g in gs], fontsize=7.5); ax.axvline(0, color='#666', lw=0.8)
        m = max(abs(v) for v in vals if not np.isnan(v)) if any(not np.isnan(v) for v in vals) else 1
        ax.set_xlim(-m * 2.6, m * 2.6); ax.set_title(ad, fontsize=10, color=METIN); style(ax); ax.grid(True, axis='x', ls='-', color='#E3E7EE', lw=0.7); ax.grid(False, axis='y')
        ax.tick_params(labelsize=7)
    pdf.savefig(fig); plt.close(fig)


def hacim_marj_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Kârlılık | Hacim–Marj Ayrıştırması', 'Net faiz gelirindeki (12 aylık) yıllık değişimin kaynağı: bilanço büyümesi (hacim) ve marj değişimi; önceki yılın net faiz gelirine oranla (%)')
    ax = fig.add_axes([0.06, 0.13, 0.40, 0.64])
    for i, g in enumerate(GROUPS):
        h = hacim_marj(g)
        if not h:
            continue
        pb = nb = 0
        for v, c in [(h['hacim_pct'], LACI), (h['marj_pct'], KIRMIZI)]:
            if v >= 0:
                ax.bar(i, v, bottom=pb, color=c, width=0.55); pb += v
            else:
                ax.bar(i, v, bottom=nb, color=c, width=0.55); nb += v
        ax.plot(i, h['toplam_pct'], marker='D', color='#222', ms=6, zorder=4)
        ax.text(i, max(pb, h['toplam_pct']) + 2.5, trp(h['toplam_pct'], 0), ha='center', fontsize=8.5, fontweight='bold', color=METIN)
    ax.set_xticks(range(len(GROUPS))); ax.set_xticklabels([GSHORT[g].replace(' ', '\n') for g in GROUPS], fontsize=7.5, color='#444')
    ax.axhline(0, color='#666', lw=0.8); style(ax); ax.set_title(f'{DON}: gruplar (lacivert hacim, kırmızı marj, elmas toplam)', fontsize=10, color=METIN)
    ax2 = fig.add_axes([0.54, 0.13, 0.42, 0.64])
    ser = hacim_marj_seri('S', 24)
    if ser:
        xs = [t for t, _, _, _ in ser]; h_ = [a for _, a, _, _ in ser]; m_ = [b for _, _, b, _ in ser]; t_ = [c for _, _, _, c in ser]
        ax2.bar(xs, h_, width=20, color=LACI, label='Hacim etkisi')
        ax2.bar(xs, m_, width=20, bottom=[x if x > 0 and y > 0 or x < 0 and y < 0 else 0 for x, y in zip(h_, m_)], color=KIRMIZI, label='Marj etkisi')
        ax2.plot(xs, t_, color='#222', lw=1.8, marker='o', ms=3, label='Net faiz geliri değişimi')
        ax2.axhline(0, color='#666', lw=0.8); style(ax2); ax2.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7])); ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m.%y'))
        ax2.set_title('Sektör: son 24 ay (%)', fontsize=10, color=METIN); ax2.legend(fontsize=8, frameon=False, loc='upper left')
    pdf.savefig(fig); plt.close(fig)


def kalite_page(pdf):
    line_page(pdf, 'Kârlılık | Kârlılık Kalitesi', [dict(col='cekirdekAktif', title='Çekirdek kârlılık / ortalama aktif (%)', fmt='num', d=2, start='2023-07-31'),
                                                     dict(col='oynakPay', title='Oynak gelir payı: (ticari + diğer) / brüt faaliyet kârı (%)', fmt='num', start='2023-07-31'),
                                                     dict(col='riskMaliyeti', title='Risk maliyeti: karşılık gideri / ortalama canlı kredi (%)', fmt='num', d=2, start='2023-07-31'),
                                                     dict(col='efVergi', title='Efektif vergi oranı (%)', fmt='num', start='2023-07-31')],
              [[1, 1], [1, 1]], sub='Çekirdek kârlılık = net faiz + net komisyon − faaliyet gideri; 12 aylık yıllıklandırılmış')


def rasyolar_page(pdf):
    line_page(pdf, 'Kârlılık | Rasyolar', [dict(col='roa', title='Aktif kârlılığı (ROA)', yfmt='pct'), dict(col='roe', title='Özkaynak kârlılığı (ROE)'), dict(col='nim', title='Net faiz marjı'),
                                           dict(col='giderGelir', title='Gider / gelir (%)', start='2023-01-31', fmt='num'), dict(col='opexAktif', title='Faaliyet gideri / aktif (%)', start='2023-07-31', fmt='num'),
                                           dict(col='g_opex_12', title='Faaliyet gideri artışı, 12 aylık (%)', fmt='num')],
              [[1, 1, 1], [1, 1, 1]], sub='12 aylık yıllıklandırılmış')


def npl_olusum_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Aktif Kalitesi | NPL Oluşumu ve Karşılıklar', 'NPL oluşum hızı = takipteki alacak bakiyesindeki aylık net artış / önceki ay canlı krediler, yıllıklandırılmış (%)')
    axes = grid_axes(fig, [[1, 1], [1, 1]])
    s = series('S', 'nplOlusum', '2024-07-31'); s3 = series('S', 'nplOlusum3', '2024-07-31')
    axes[0].bar(s.index, s.values, width=20, color=LACI, alpha=0.85); axes[0].plot(s3.index, s3.values, color=KIRMIZI, lw=1.8)
    axes[0].set_title('Sektör: aylık (çubuk) ve 3 aylık ortalama (çizgi), %', fontsize=10.5, color=METIN); style(axes[0]); ay_ekseni(axes[0]); axes[0].axhline(0, color='#666', lw=0.6)
    ax = axes[1]; vals = [at(g).nplOlusum12 for g in GROUPS]
    ax.bar(range(len(GROUPS)), vals, color=[GC[g] for g in GROUPS], width=0.6)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.05, tr(v, 2), ha='center', fontsize=8, color=METIN)
    ax.set_xticks(range(len(GROUPS))); ax.set_xticklabels([GSHORT[g].replace(' ', '\n') for g in GROUPS], fontsize=7, color='#444'); style(ax); ax.set_title('Son 12 ayın ortalama NPL oluşum hızı, gruplar (%)', fontsize=10.5, color=METIN)
    line_panel(axes[2], 'ozelKarsOran', 'Özel karşılık oranı (%)', '2023-07-31', 'num', d=1)
    line_panel(axes[3], 'nplMakas', 'NPL makası: tüketici − ticari/kurumsal (puan)', '2023-07-31', 'num', DEPG, d=2)
    legend_bottom(fig, [(GC[g], t) for g, t in GLEG])
    pdf.savefig(fig); plt.close(fig)


def dolarizasyon_page(pdf):
    line_page(pdf, 'Fonlama | Dolarizasyon ve Likidite', [dict(col='fonTPag', title='Toplanan fonlarda TP ağırlığı (%)', start='2023-01-31', groups=DEPG), dict(col='ypMevPay', title='YP mevduat payı, kıymetli maden dahil (%)', start='2023-01-31', groups=DEPG),
                                                           dict(col='kmPay', title='Kıymetli maden hesaplarının payı (%)', start='2023-01-31', groups=DEPG, fmt='num', d=1), dict(col='g_mvYP_usd', title='YP mevduat büyümesi, USD (%)', yfmt='pct', groups=DEPG),
                                                           dict(col='tlKrediMev', title='TL kredi / TL mevduat (%)', start='2023-01-31', groups=DEPG), dict(col='ypGap', title='Bilanço içi YP açığı: (YP kredi − YP fon) / aktif (%)', start='2023-01-31', fmt='num', d=1, groups=DEPG)],
              [[1, 1, 1], [1, 1, 1]], sub='Mevduat kabul eden gruplar')


def sermaye_page(pdf):
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Sermaye | Yeterlilik ve Tampon', 'Fazla sermaye = yasal özkaynak − %12 × risk ağırlıklı aktifler (BDDK hedef rasyosu); kapasite = aynı rasyoyla RAK\'ın büyüyebileceği oran')
    ax = fig.add_axes([0.06, 0.50, 0.90, 0.29])
    vals = [at(g).fazlaSermaye for g in GROUPS]
    ax.bar(range(len(GROUPS)), vals, color=[GC[g] for g in GROUPS], width=0.6)
    for i, g in enumerate(GROUPS):
        a = at(g); ax.text(i, a.fazlaSermaye + max(vals) * 0.02, f"{tr(a.fazlaSermaye, 0)} mlr ₺\nkapasite %{tr(a.buyumeKapasite, 0)}", ha='center', fontsize=8, color=METIN)
    ax.set_xticks(range(len(GROUPS))); ax.set_xticklabels([GSHORT[g] for g in GROUPS], fontsize=8.5, color='#444'); style(ax); ax.set_ylim(0, max(vals) * 1.3)
    ax.set_title(f'{DON}: %12 hedef rasyoya göre fazla sermaye (milyar ₺) ve RAK büyüme kapasitesi', fontsize=10.5, color=METIN)
    axes = [fig.add_axes([0.05, 0.11, 0.27, 0.29]), fig.add_axes([0.37, 0.11, 0.27, 0.29]), fig.add_axes([0.69, 0.11, 0.27, 0.29])]
    for ax_, (col, t, fm) in zip(axes, [('syr', 'Standart SYR (%)', 'pct'), ('cekSyr', 'Çekirdek SYR (%)', 'pct'), ('rakYogunluk', 'RAK yoğunluğu: RAK / aktif (%)', 'num')]):
        line_panel(ax_, col, t, '2024-01-31', fm)
    legend_bottom(fig, [(GC[g], t) for g, t in GLEG], y=0.045)
    pdf.savefig(fig); plt.close(fig)


def kopru_page(pdf):
    K = haftalik_kopru()
    if not K:
        return
    baz = pd.Timestamp(K['baz']); son = pd.Timestamp(K['son'])
    fig = plt.figure(figsize=(PW, PH)); header(fig, 'Ek | Ay Sonrası Haftalık Köprü', f"BDDK haftalık bülteninden: {baz.strftime('%d.%m.%Y')} → {son.strftime('%d.%m.%Y')} ({K['hafta']} hafta) birikimli değişim (%); kaynak ekordion haftalık BDDK modülü")
    gs = [g for g in ['S', 'KA', 'YO', 'YA', 'KB'] if g in K['gruplar']]
    satirlar = [('Toplam krediler (TL + YP)', 'kredi'), ('Tüketici kredileri ve kredi kartları', 'tuketici'), ('Ticari ve diğer krediler', 'ticari'),
                ('Toplam mevduat (TL karşılığı)', 'mevduat'), ('TL mevduat', 'mevduatTP'), ('YP mevduat (USD)', 'ypMevduatUsd')]
    ax = fig.add_axes([0.04, 0.47, 0.92, 0.33]); ax.axis('off')
    hdr = ['Kalem'] + [GSHORT[g] for g in gs]; cw = [0.34] + [0.66 / len(gs)] * len(gs); rh = 1 / (len(satirlar) + 1); x = 0
    for j, h in enumerate(hdr):
        ax.add_patch(Rectangle((x, 1 - rh), cw[j], rh, color=LACI, transform=ax.transAxes))
        ax.text(x + cw[j] / 2, 1 - rh / 2, h, ha='center', va='center', color='white', fontsize=9, fontweight='bold', transform=ax.transAxes); x += cw[j]
    for i, (lab, key) in enumerate(satirlar):
        y = 1 - (i + 2) * rh; x = 0
        for j in range(len(hdr)):
            ax.add_patch(Rectangle((x, y), cw[j], rh, facecolor=ACIK if i % 2 else 'white', edgecolor='#D9DEE6', lw=0.5, transform=ax.transAxes))
            if j == 0:
                ax.text(x + 0.008, y + rh / 2, lab, ha='left', va='center', fontsize=9, color=METIN, transform=ax.transAxes)
            else:
                v = K['gruplar'][gs[j - 1]].get(key)
                ax.text(x + cw[j] / 2, y + rh / 2, '—' if v is None else trp(v, 2), ha='center', va='center', fontsize=9, color=('#2E7D5B' if (v or 0) >= 0 else KIRMIZI), fontweight='bold' if gs[j - 1] == 'S' else 'normal', transform=ax.transAxes)
            x += cw[j]
    sr = K['seri']; xs = [pd.Timestamp(t) for t in sr['tarih']]
    ax2 = fig.add_axes([0.06, 0.10, 0.40, 0.30]); ax2.plot(xs, sr['kredi'], color=LACI, lw=2, marker='o', ms=3); ax2.axhline(100, color='#999', lw=0.7, ls='--'); ax2.axvline(baz, color=KIRMIZI, lw=0.8, ls=':')
    ax2.set_title('Sektör toplam krediler, ay sonu = 100', fontsize=10, color=METIN); style(ax2); ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
    ax3 = fig.add_axes([0.55, 0.10, 0.40, 0.30]); ax3.plot(xs, sr['mevduat'], color=KIRMIZI, lw=2, marker='o', ms=3); ax3.axhline(100, color='#999', lw=0.7, ls='--'); ax3.axvline(baz, color=KIRMIZI, lw=0.8, ls=':')
    ax3.set_title('Sektör toplam mevduat, ay sonu = 100', fontsize=10, color=METIN); style(ax3); ax3.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
    fig.text(0.04, 0.045, 'Haftalık bülten grupları: Sektör, Kamu, Yerli Özel, Yabancı, Katılım. Haftalık veri aylık bültenle tanım farkları içerir; yön ve büyüklük için kullanılır.', fontsize=8, color='#555')
    pdf.savefig(fig); plt.close(fig)


# ---------- kurulum ----------
def build(path):
    SAYFA[0] = 0
    pdf = PdfPages(path)
    cover(pdf)
    gorunum_page(pdf)
    karne_page(pdf)
    table_page(pdf, 'Özet Göstergeler', 'Gruplar itibarıyla; büyümeler yıllık, kârlılık 12 aylık yıllıklandırılmış',
               [(lab, None if col is None else [at(g)[col] for g in GROUPS], dec) for lab, col, dec in OZET_SATIRLAR],
               note='Mevduat göstergeleri Kalkınma-Yatırım grubu için tanımsızdır. Faiz kalemleri katılım bankaları için kâr payını kapsar.')
    # Büyüme ve ivme
    buyume_page(pdf)
    ivme_page(pdf)
    segment_page(pdf)
    reel_page(pdf)
    pay_page(pdf)
    # Bilanço ve kredi yapısı
    area_page(pdf, 'Bilanço | Aktif Yapısı', 'Aktif kalemlerinin payı (%), son 25 ay; panel başlığı: toplam aktif ve yıllık büyüme', AKTIF)
    area_page(pdf, 'Bilanço | Pasif Yapısı', 'Pasif kalemlerinin payı (%), son 25 ay', PASIF)
    kaldirac_page(pdf)
    area_page(pdf, 'Krediler | Canlı Kredi Yapısı', 'Canlı kredi bileşenlerinin payı (%), son 25 ay', CANLI)
    area_page(pdf, 'Krediler | Tüketici Kredisi Yapısı', 'Tüketici kredisi bileşenlerinin payı (%), son 25 ay', TUK, groups=DEPG, totfmt=2)
    line_page(pdf, 'Krediler | Tüketici Büyümesi', [dict(col='g_tukKK', title='Tüketici kredileri ve kredi kartları', start='2023-01-31', groups=DEPG), dict(col='g_konut', title='Konut', groups=DEPG), dict(col='g_tasit', title='Taşıt', groups=DEPG), dict(col='g_ihtiyac', title='İhtiyaç', groups=DEPG), dict(col='g_kk', title='Bireysel kredi kartları', groups=DEPG)], [[2, 1], [1, 1, 1]], sub='Yıllık büyüme (%)')
    area_page(pdf, 'Krediler | Tüzel Kredi Yapısı', 'Tüzel kredi bileşenlerinin payı (%), son 25 ay', TUZEL)
    line_page(pdf, 'Krediler | Tüzel Büyümesi', [dict(col='g_tuzel', title='Tüzel krediler', start='2023-01-31'), dict(col='g_ticKur', title='Ticari / kurumsal'), dict(col='g_kobi', title='KOBİ'), dict(col='g_fk', title='Finansal kiralama', groups=['S', 'KB', 'KY'])], [[1], [1, 1, 1]], sub='Yıllık büyüme (%)')
    # Kârlılık
    netkar_page(pdf)
    hacim_marj_page(pdf)
    kalite_page(pdf)
    marj_page(pdf)
    roa_comp_page(pdf)
    rasyolar_page(pdf)
    # Aktif kalitesi
    line_page(pdf, 'Aktif Kalitesi | Takipteki Alacaklar', [dict(col='npl', title='NPL oranı', start='2023-01-31', fmt='num', d=2), dict(col='nplTuk', title='Tüketici NPL', start='2023-01-31', fmt='num', d=2, groups=DEPG), dict(col='nplKobi', title='KOBİ NPL', start='2023-01-31', fmt='num', d=2), dict(col='nplTic', title='Ticari / kurumsal NPL', start='2023-01-31', fmt='num', d=2)], [[1, 1], [1, 1]], sub='Yüzde')
    npl_olusum_page(pdf)
    # Fonlama
    area_page(pdf, 'Fonlama | Toplanan Fon Yapısı', 'Toplanan fon bileşenlerinin payı (%), son 25 ay', FON, groups=DEPG)
    dolarizasyon_page(pdf)
    share_page(pdf, 'Fonlama | Grup Payları', [('Toplam vadesiz', 'vadesiz', 1), ('Toplam vadeli', 'vadeli', 1), ('TP mevduat', 'mvTP', 1), ('YP mevduat', 'mvYP', 1)])
    # Sermaye
    sermaye_page(pdf)
    # Ekler
    kopru_page(pdf)
    rows = []
    for lab, col in GELIR_SATIRLAR:
        sg = -1 if col in GIDER_KALEMLERI else 1
        rows.append((lab, [(at(g)['gy_' + col], at(g)[col] * sg) for g in GROUPS]))
    table_page(pdf, 'Ek | Gelir Tablosu', 'Milyon ₺, yıl içi kümülatif; renkli rakamlar yıllık yüzde değişim', rows)
    area_page(pdf, 'Ek | Menkul Kıymet Portföyü', 'Menkul kıymet portföyünün sınıflandırma ve para birimine göre payı (%), son 25 ay', MENKUL)
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
