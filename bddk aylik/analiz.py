#!/usr/bin/env python3
"""ekordion analizleri — calc.D üzerine türetilmiş göstergeler (kaynak raporlarda bulunmayan, kendi çerçevemiz).

  İvme      : segment bazında 3 aylık yıllıklandırılmış büyüme (g3_*) ve 12 aylık büyümeyle farkı
  Kalite    : çekirdek kârlılık (net faiz + net komisyon − faaliyet gideri) / ort. aktif, oynak gelir payı,
              risk maliyeti (karşılık / ort. canlı kredi), efektif vergi oranı
  NPL oluşum: takipteki alacak bakiyesindeki aylık net artış / önceki ay canlı krediler, yıllıklandırılmış (%)
  Sermaye   : %12 hedef rasyoya göre fazla sermaye (milyar ₺), RAK yoğunluğu (RAK / aktif), büyüme kapasitesi
  Reel      : TÜFE yıllık enflasyonla arındırılmış büyümeler (enflasyon/enflasyon.xlsx)
  Hacim–marj: net faiz gelirindeki yıllık değişimin hacim (ort. aktif) ve marj (NIM) etkilerine ayrıştırılması
  Pazar payı: grupların sektör içindeki payındaki 12 aylık değişim (puan)
  Köprü     : ay sonundan sonraki haftalık BDDK verisi (bddk_data/) — ay bittikten sonra ne oldu
"""
import warnings; warnings.filterwarnings('ignore')
import sys
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).resolve().parent; BASE = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(BASE))
from calc import D, LAST, GROUPS, DEPG, GSHORT, GNAME, at, series  # noqa: E402,F401

D.sort_values(['g', 'd'], inplace=True)
PREV = pd.Timestamp(LAST.year - 1, LAST.month, 1) + pd.offsets.MonthEnd(0)
_g = lambda col: D.groupby('g')[col]

# ── ivme: segment bazında 3 aylık yıllıklandırılmış büyüme
for c in ['tukKK', 'kobi', 'ticKur', 'tuzel', 'konut', 'ihtiyac', 'kk', 'canli', 'mevduat', 'aktif']:
    D['g3_' + c] = _g(c).transform(lambda x: ((x / x.shift(3)) ** 4 - 1) * 100)
SEGMENTLER = [('canliTP', 'TP canlı krediler'), ('tukKK', 'Tüketici + kredi kartı'), ('konut', 'Konut'), ('ihtiyac', 'İhtiyaç'),
              ('kk', 'Bireysel kredi kartı'), ('kobi', 'KOBİ'), ('ticKur', 'Ticari / kurumsal'), ('mvTP', 'TP mevduat')]

# ── kârlılık kalitesi
D['cekirdekAktif'] = (D.netFaiz_12 + D.netUcret_12 - D.opex_12) / D.avgAktif * 100
D['oynakPay'] = (D.ticari_12 + D.digGel_12) / D.brutKar_12 * 100
D['riskMaliyeti'] = D.karsilik_12 / D.avgCanli * 100
D['efVergi'] = D.vergi_12 / D.vergiOncesi_12 * 100

# ── NPL oluşum hızı
D['nplOlusum'] = _g('takip').diff() / _g('canli').shift(1) * 12 * 100
D['nplOlusum3'] = _g('nplOlusum').transform(lambda x: x.rolling(3).mean())
D['nplOlusum12'] = _g('nplOlusum').transform(lambda x: x.rolling(12).mean())
D['nplMakas'] = D.nplTuk - D.nplTic

# ── sermaye tamponu (%12 hedef rasyo)
D['fazlaSermaye'] = (D.yasalOzk - 0.12 * D.rak) / 1e3
D['rakYogunluk'] = D.rak / D.aktif * 100
D['buyumeKapasite'] = (D.yasalOzk / (0.12 * D.rak) - 1) * 100

# ── dolarizasyon
D['kmPay'] = D.kmTot / D.mevduat * 100
D['ypMevPay'] = D.mvYP / D.mevduat * 100

# ── reel büyüme (TÜFE yıllık)
ENF_SON = None
try:
    _enf = pd.read_excel(BASE / 'enflasyon' / 'enflasyon.xlsx', sheet_name='Genel')[['tarih', 'yillik']]
    _enf['d'] = pd.to_datetime(_enf.tarih) + pd.offsets.MonthEnd(0)
    _pi = D.d.map(dict(zip(_enf.d, _enf.yillik)))
    D['tufe'] = _pi
    for c in ['canliTP', 'mvTP', 'akTP', 'tukKK', 'tuzel', 'canli', 'mevduat']:
        D['gr_' + c] = ((1 + D['g_' + c] / 100) / (1 + _pi / 100) - 1) * 100
    ENF_SON = _enf.d.max()
except Exception as e:
    print(f"  ~ enflasyon serisi okunamadı ({type(e).__name__}); reel büyümeler boş")
    D['tufe'] = np.nan
    for c in ['canliTP', 'mvTP', 'akTP', 'tukKK', 'tuzel', 'canli', 'mevduat']:
        D['gr_' + c] = np.nan


def _at(g, d):
    r = D[(D.g == g) & (D.d == d)]
    return r.iloc[0] if len(r) else None


def hacim_marj(g, d=None):
    """Net faiz gelirindeki (12 aylık) yıllık değişim = hacim etkisi + marj etkisi. Dönüş: milyon ₺ ve % (önceki NII'ye oranla)."""
    d = d or LAST; p = pd.Timestamp(pd.Timestamp(d) - pd.DateOffset(years=1)) + pd.offsets.MonthEnd(0)
    a, b = _at(g, d), _at(g, p)
    if a is None or b is None or pd.isna(a.netFaiz_12) or pd.isna(b.netFaiz_12) or not b.netFaiz_12:
        return None
    hacim = (a.avgAktif - b.avgAktif) * b.nim / 100
    marj = (a.nim - b.nim) / 100 * a.avgAktif
    return {'nii': a.netFaiz_12, 'nii_onceki': b.netFaiz_12, 'degisim': a.netFaiz_12 - b.netFaiz_12, 'hacim': hacim, 'marj': marj,
            'hacim_pct': hacim / b.netFaiz_12 * 100, 'marj_pct': marj / b.netFaiz_12 * 100, 'toplam_pct': (a.netFaiz_12 / b.netFaiz_12 - 1) * 100}


def hacim_marj_seri(g, ay=24):
    out = []
    tarihler = sorted(D[D.g == g].d.unique())[-ay:]
    for d in tarihler:
        h = hacim_marj(g, pd.Timestamp(d))
        if h:
            out.append((pd.Timestamp(d), h['hacim_pct'], h['marj_pct'], h['toplam_pct']))
    return out


PAY_KOL = [('canli', 'Canlı krediler'), ('tukKK', 'Tüketici + KK'), ('kobi', 'KOBİ'), ('ticKur', 'Ticari / kurumsal'),
           ('mevduat', 'Toplanan fonlar'), ('mvTP', 'TP mevduat'), ('mvYP', 'YP mevduat')]


def pay_degisim():
    """Grupların sektör payı (%) ve 12 aylık değişimi (puan)."""
    S, Sp = at('S'), at('S', PREV)
    out = {}
    for g in GROUPS[1:]:
        a, b = at(g), at(g, PREV)
        out[g] = {}
        for col, ad in PAY_KOL:
            if g == 'KY' and col in ('mevduat', 'mvTP', 'mvYP'):
                out[g][col] = None; continue
            pay, payp = a[col] / S[col] * 100, b[col] / Sp[col] * 100
            out[g][col] = {'pay': float(pay), 'degisim': float(pay - payp)}
    return out


def haftalik_kopru():
    """Ay sonundan sonraki haftalık BDDK verisi (sitedeki haftalık modül). Dönüş: None ya da
    {baz, son, hafta, gruplar: {g: {kredi, tuketici, ticari, mevduat, ypMevduatUsd}}, seri: {tarih, kredi, mevduat}}"""
    try:
        import bddk_analiz as ba
        tl, usd, ad = ba.load_latest(BASE / 'bddk_data')
    except Exception:
        return None
    if tl is None:
        return None
    esle = {'sektor': 'S', 'kamu': 'KA', 'yerli': 'YO', 'yabanci': 'YA', 'katilim': 'KB'}
    ay_sonu = pd.Timestamp(LAST)
    sek = tl['sektor']
    son = sek[0].max()
    if son <= ay_sonu:
        return None
    baz_t = sek[sek[0] <= ay_sonu][0].max()
    hafta = int(((son - baz_t).days + 3) // 7)
    gruplar = {}
    for blok, g in esle.items():
        s = tl.get(blok); u = usd.get(blok) if usd else None
        if s is None:
            continue
        def pct(frame, item, part):
            c = ba._col(item, part)
            b = frame[frame[0] == baz_t]; e = frame[frame[0] == son]
            if not len(b) or not len(e) or not b[c].iloc[0]:
                return None
            return float((e[c].iloc[0] / b[c].iloc[0] - 1) * 100)
        gruplar[g] = {'kredi': pct(s, 'kredi_toplam', ba.TOPLAM), 'tuketici': pct(s, 'tuketici_bkk', ba.TOPLAM),
                      'ticari': pct(s, 'ticari', ba.TOPLAM), 'mevduat': pct(s, 'mevduat', ba.TOPLAM),
                      'mevduatTP': pct(s, 'mevduat', ba.TP),
                      'ypMevduatUsd': pct(u, 'mevduat', ba.YP) if u is not None else None}
    son13 = sek[sek[0] >= baz_t - pd.Timedelta(days=70)]
    kc, mc = ba._col('kredi_toplam', ba.TOPLAM), ba._col('mevduat', ba.TOPLAM)
    baz_k = sek[sek[0] == baz_t][kc].iloc[0]; baz_m = sek[sek[0] == baz_t][mc].iloc[0]
    return {'baz': baz_t.strftime('%Y-%m-%d'), 'son': son.strftime('%Y-%m-%d'), 'hafta': hafta, 'dosya': ad, 'gruplar': gruplar,
            'seri': {'tarih': [t.strftime('%Y-%m-%d') for t in son13[0]],
                     'kredi': [float(v / baz_k * 100) for v in son13[kc]], 'mevduat': [float(v / baz_m * 100) for v in son13[mc]]}}


if __name__ == '__main__':
    S = at('S')
    print(f"dönem {LAST.date()} · TÜFE {S.tufe:.1f} · reel TP kredi {S.gr_canliTP:.1f} · çekirdek kârlılık {S.cekirdekAktif:.2f} · NPL oluşum(3a) {S.nplOlusum3:.2f} · fazla sermaye {S.fazlaSermaye:,.0f} mlr · RAK/aktif {S.rakYogunluk:.1f}")
    print("hacim-marj S:", {k: round(v, 1) for k, v in hacim_marj('S').items()})
    print("pay değişimi KB:", {k: (None if v is None else round(v['degisim'], 2)) for k, v in pay_degisim()['KB'].items()})
    k = haftalik_kopru(); print("köprü:", None if not k else (k['baz'], k['son'], k['hafta'], {g: round(v['kredi'], 2) for g, v in k['gruplar'].items()}))
    for s, ad in SEGMENTLER:
        print(f"  {ad:24s} 12a {S['g_'+s]:6.1f}  3a {S['g3_'+s]:6.1f}")
