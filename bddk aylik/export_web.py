#!/usr/bin/env python3
"""Bankacılık Monitörü site verisi → site/data/bankacilik.json (site/bankacilik.html, ana sayfa kartı, e-posta).
Kullanım: python export_web.py [--pdf raporlar/x.pdf] [--xlsx raporlar/x.xlsx]"""
import warnings; warnings.filterwarnings('ignore')
from zoneinfo import ZoneInfo
import argparse, datetime as dt, json, re, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from calc import D, LAST, GROUPS, DEPG, GSHORT, GNAME, at  # noqa: E402
from analiz import hacim_marj, hacim_marj_seri, pay_degisim, haftalik_kopru, reel_sektor_fx, basabas, SEGMENTLER, PAY_KOL, ENF_SON  # noqa: E402

BASE = HERE.parent
OUT = BASE / 'site' / 'data' / 'bankacilik.json'
RAPOR_DIR = BASE / 'site' / 'raporlar'
AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
ONCEKI = LAST - __import__('pandas').offsets.MonthEnd(1)

# siteye giden seriler (2023-01'den): kolon → (etiket, birim)
SERILER = {
    'g_aktif': 'Toplam aktif büyümesi (yıllık %)', 'g_akTP': 'TP aktif büyümesi (yıllık %)', 'g_akYP_usd': 'YP aktif büyümesi (USD, yıllık %)',
    'g_canliTP': 'TP canlı kredi büyümesi (yıllık %)', 'g_canliYP_usd': 'YP canlı kredi büyümesi (USD, yıllık %)', 'g3_canliTP': 'TP canlı kredi, 3 aylık yıllıklandırılmış (%)',
    'g1_canliTP': 'TP canlı kredi, aylık (%)', 'g_tukKK': 'Tüketici kredileri + KK büyümesi (yıllık %)', 'g_tuzel': 'Tüzel kredi büyümesi (yıllık %)', 'g_kobi': 'KOBİ kredi büyümesi (yıllık %)',
    'g_mvTP': 'TP mevduat büyümesi (yıllık %)', 'g_mvYP_usd': 'YP mevduat büyümesi (USD, yıllık %)', 'g3_mvTP': 'TP mevduat, 3 aylık yıllıklandırılmış (%)', 'fonTPag': 'Toplanan fon TP ağırlığı (%)',
    'aktifTPag': 'Aktif TP ağırlığı (%)', 'npl': 'NPL oranı (%)', 'nplTuk': 'Tüketici NPL (%)', 'nplKobi': 'KOBİ NPL (%)', 'ozelKarsOran': 'Özel karşılık oranı (%)',
    'syr': 'Standart SYR (%)', 'cekSyr': 'Çekirdek SYR (%)', 'roa': 'ROA (%)', 'roe': 'ROE (%)', 'nim': 'Net faiz marjı (%)', 'giderGelir': 'Gider / gelir (%)',
    'krediGetiri': 'Kredi getirisi (%)', 'fonMaliyet': 'Fon maliyeti (%)', 'kaldirac': 'Kaldıraç (x)', 'netKar_m': 'Aylık net kâr (milyon ₺)', 'aktifPay': 'Aktif pazar payı (%)',
    'tlKrediMev': 'TL kredi / mevduat (%)', 'krediMev': 'Kredi / mevduat (%)',
    'g3_tukKK': 'Tüketici + KK, 3 aylık yıllıklandırılmış (%)', 'g3_kobi': 'KOBİ, 3 aylık yıllıklandırılmış (%)', 'g3_ticKur': 'Ticari/kurumsal, 3 aylık yıllıklandırılmış (%)',
    'gr_canliTP': 'Reel TP canlı kredi büyümesi (%)', 'gr_mvTP': 'Reel TP mevduat büyümesi (%)', 'gr_akTP': 'Reel TP aktif büyümesi (%)', 'tufe': 'TÜFE yıllık (%)',
    'cekirdekAktif': 'Çekirdek kârlılık / aktif (%)', 'oynakPay': 'Oynak gelir payı (%)', 'riskMaliyeti': 'Risk maliyeti (%)', 'efVergi': 'Efektif vergi oranı (%)',
    'nplOlusum': 'NPL oluşum hızı, aylık yıllıklandırılmış (%)', 'nplOlusum3': 'NPL oluşum hızı, 3 aylık ortalama (%)', 'nplMakas': 'NPL makası tüketici − ticari (puan)',
    'fazlaSermaye': 'Fazla sermaye, %12 hedefe göre (milyar ₺)', 'rakYogunluk': 'RAK / aktif (%)', 'buyumeKapasite': 'RAK büyüme kapasitesi (%)',
    'kmPay': 'Kıymetli maden payı (%)', 'ypMevPay': 'YP mevduat payı (%)', 'ypGap': 'YP açığı / aktif (%)',
    'cor': 'Risk maliyeti, kredi karşılıkları (%)', 'corNet': 'Net risk maliyeti (%)', 'karsilikPPI': 'Karşılık / karşılık öncesi kâr (%)',
    'ecl1Oran': '1. aşama karşılık / canlı (%)', 'ecl2Oran': '2. aşama karşılık / canlı (%)', 'eclToplam': 'Toplam karşılık / brüt kredi (%)',
    'teminatsizPay': 'Teminatsız bireysel payı (%)', 'kobiPay': 'KOBİ payı (%)', 'ypKrediPay': 'YP kredi payı (%)',
    'nplKK': 'Kredi kartı NPL (%)', 'nplIhtiyac': 'İhtiyaç NPL (%)', 'nplKonut': 'Konut NPL (%)', 'nplTasit': 'Taşıt NPL (%)', 'nplTic': 'Ticari/kurumsal NPL (%)',
    'nplTP': 'TP kredi NPL (%)', 'nplYP': 'YP kredi NPL (%)', 'nimSwap': 'Swap etkisi dahil marj (%)',
}
KARNE = [('TP canlı kredi büyümesi, 12 aylık (%)', 'g_canliTP', 1, 1), ('TP canlı kredi, 3 aylık yıllıklandırılmış (%)', 'g3_canliTP', 1, 1),
         ('Reel TP canlı kredi büyümesi (%)', 'gr_canliTP', 1, 1), ('TP mevduat büyümesi (%)', 'g_mvTP', 1, 1), ('YP mevduat büyümesi, USD (%)', 'g_mvYP_usd', 1, 1),
         ('NPL oranı (%)', 'npl', 2, -1), ('NPL oluşum hızı, 3 aylık (%)', 'nplOlusum3', 2, -1), ('Özel karşılık oranı (%)', 'ozelKarsOran', 1, 1),
         ('Risk maliyeti, kredi karşılıkları (%)', 'cor', 2, -1), ('2. aşama karşılık / canlı kredi (%)', 'ecl2Oran', 2, -1), ('Teminatsız bireysel payı (%)', 'teminatsizPay', 1, -1),
         ('Çekirdek kârlılık / aktif (%)', 'cekirdekAktif', 2, 1), ('ROA (%)', 'roa', 2, 1), ('ROE (%)', 'roe', 1, 1),
         ('Net faiz marjı (%)', 'nim', 2, 1), ('Swap etkisi dahil marj (%)', 'nimSwap', 2, 1), ('Gider / gelir (%)', 'giderGelir', 1, -1), ('Standart SYR (%)', 'syr', 1, 1),
         ('Fazla sermaye, %12 hedefe göre (milyar ₺)', 'fazlaSermaye', 0, 1), ('RAK / aktif (%)', 'rakYogunluk', 1, 0), ('Toplanan fon TP ağırlığı (%)', 'fonTPag', 1, 1)]
KOMP = {
    'aktif': ('Aktif yapısı', [('TP Krediler', lambda r: r.krediTP), ('YP Krediler', lambda r: r.krediYP), ('TP Menkul', lambda r: r.mkTP), ('YP Menkul', lambda r: r.mkYP),
                               ('TP Nakit', lambda r: r.nakTP), ('YP Nakit', lambda r: r.nakYP), ('Diğer', lambda r: r.aktif - r.krediTP - r.krediYP - r.mkTP - r.mkYP - r.nakTP - r.nakYP)]),
    'pasif': ('Pasif yapısı', [('TP Toplanan Fon', lambda r: r.mvTP), ('YP Toplanan Fon', lambda r: r.mvYP - r.kmTot), ('Kıymetli Madenler', lambda r: r.kmTot), ('Toptan Fonlama', lambda r: r.topTP + r.topYP),
                               ('Sermaye Benzeri', lambda r: r.sermBz), ('Özkaynaklar', lambda r: r.ozk), ('Diğer', lambda r: r.aktif - r.mvTP - r.mvYP - r.topTP - r.topYP - r.sermBz - r.ozk)]),
    'canli': ('Canlı kredi yapısı', [('Tüketici + KK', lambda r: r.tukKK), ('TP KOBİ', lambda r: r.kobiTP), ('YP KOBİ', lambda r: r.kobiYP), ('TP Ticari/Kurumsal', lambda r: r.ticKurTP),
                                     ('YP Ticari/Kurumsal', lambda r: r.ticKurYP), ('Finansal Kiralama', lambda r: r.fk)]),
    'fon': ('Toplanan fon yapısı', [('TP Vadesiz', lambda r: r.vdsTP), ('TP Vadeli', lambda r: r.vadeliTP), ('YP Vadesiz', lambda r: r.ypVds_exKM), ('YP Vadeli', lambda r: r.ypVdl_exKM),
                                    ('KM Vadesiz', lambda r: r.kmVds), ('KM Vadeli', lambda r: r.kmVdl)]),
}


def f(v, d=2):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), d)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pdf'); ap.add_argument('--xlsx'); a = ap.parse_args()
    donem = LAST.strftime('%Y-%m'); donem_ad = f"{AYLAR[LAST.month - 1]} {LAST.year}"
    D['aktifPay'] = D.aktif / D.groupby('d').aktif.transform(lambda x: x[D.loc[x.index, 'g'] == 'S'].iloc[0]) * 100
    gor = json.loads((HERE / 'gorunum.json').read_text(encoding='utf-8')) if (HERE / 'gorunum.json').exists() else None
    if gor and gor.get('donem') != donem:
        gor = None

    kpi = {}
    for g in GROUPS:
        s, p = at(g), at(g, ONCEKI)
        kpi[g] = {'gr_canliTP': f(s.gr_canliTP, 1), 'cekirdekAktif': f(s.cekirdekAktif, 2), 'nplOlusum3': f(s.nplOlusum3, 2), 'fazlaSermaye': f(s.fazlaSermaye, 0),
                  'cor': f(s.cor, 2), 'teminatsizPay': f(s.teminatsizPay, 1), 'nimSwap': f(s.nimSwap, 2), 'ecl2Oran': f(s.ecl2Oran, 2),
                  'aktif': f(s.aktif / 1e6, 2), 'g_aktif': f(s.g_aktif, 1), 'canli': f(s.canli / 1e6, 2), 'g_canliTP': f(s.g_canliTP, 1), 'g_canliTP_onceki': f(p.g_canliTP, 1),
                  'g3_canliTP': f(s.g3_canliTP, 1), 'mevduat': f(s.mevduat / 1e6, 2), 'g_mvTP': f(s.g_mvTP, 1), 'fonTPag': f(s.fonTPag, 1), 'fonTPag_onceki': f(p.fonTPag, 1),
                  'netKar': f(s.netKar / 1e3, 1), 'gy_netKar': f(s.gy_netKar, 1), 'netKar_m': f(s.netKar_m / 1e3, 1), 'netKar_m_onceki': f(p.netKar_m / 1e3, 1),
                  'npl': f(s.npl, 2), 'npl_onceki': f(p.npl, 2), 'syr': f(s.syr, 1), 'syr_onceki': f(p.syr, 1), 'roa': f(s.roa, 2), 'roe': f(s.roe, 1), 'nim': f(s.nim, 2), 'nim_onceki': f(p.nim, 2)}

    karne = []
    for ad, col, d, yon in KARNE:
        karne.append({'ad': ad, 'kol': col, 'ondalik': d, 'yon': yon, 'deger': {g: f(at(g)[col], d) for g in GROUPS}})

    bas = '2023-01-31'
    sub = D[D.d >= bas].sort_values('d')
    tarihler = sorted({t.strftime('%Y-%m') for t in sub.d})
    seri = {'tarih': tarihler, 'etiket': SERILER}
    for g in GROUPS:
        sg = sub[sub.g == g].set_index(sub[sub.g == g].d.dt.strftime('%Y-%m'))
        seri[g] = {col: [f(sg[col].get(t), 2) if col != 'netKar_m' else f(sg[col].get(t), 0) for t in tarihler] for col in SERILER}

    komp = {}
    kbas = (LAST - __import__('pandas').DateOffset(months=24))
    for key, (ad, parts) in KOMP.items():
        grp = DEPG if key == 'fon' else GROUPS
        ksub = D[D.d >= kbas].sort_values('d')
        kt = sorted({t.strftime('%Y-%m') for t in ksub.d})
        komp[key] = {'ad': ad, 'etiketler': [p[0] for p in parts], 'tarih': kt, 'gruplar': {}}
        for g in grp:
            rows = ksub[ksub.g == g]
            degerler = [[f(fn(r) / 1e3, 0) for _, r in rows.iterrows()] for _, fn in parts]   # milyar ₺
            komp[key]['gruplar'][g] = degerler

    arsiv = []
    for p in sorted(RAPOR_DIR.glob('bankacilik-monitoru-20??-??.pdf'), reverse=True):
        m = re.search(r'(\d{4})-(\d{2})', p.name)
        if m:
            x = RAPOR_DIR / p.name.replace('.pdf', '-veri.xlsx')
            arsiv.append({'donem': f"{m.group(1)}-{m.group(2)}", 'ad': f"{AYLAR[int(m.group(2)) - 1]} {m.group(1)}", 'pdf': f"raporlar/{p.name}",
                          'xlsx': f"raporlar/{x.name}" if x.exists() else None, 'boyut_kb': p.stat().st_size // 1024})
    # ekordion analizleri (anlık görüntü)
    analiz = {
        'ivme': {'gruplar': {g: {'g12': f(at(g).g_canliTP, 1), 'g3': f(at(g).g3_canliTP, 1)} for g in GROUPS},
                 'segmentler': [{'ad': ad, 'kol': c, 'g12': f(at('S')['g_' + c], 1), 'g3': f(at('S')['g3_' + c], 1)} for c, ad in SEGMENTLER]},
        'hacim_marj': {'gruplar': {g: ({k: f(v, 1) for k, v in hacim_marj(g).items()} if hacim_marj(g) else None) for g in GROUPS},
                       'seri': [{'tarih': t.strftime('%Y-%m'), 'hacim': f(h, 1), 'marj': f(m, 1), 'toplam': f(tt, 1)} for t, h, m, tt in hacim_marj_seri('S', 24)]},
        'pay': {'kategoriler': [{'kol': c, 'ad': ad} for c, ad in PAY_KOL], 'gruplar': {g: {c: (None if v is None else {'pay': f(v['pay'], 2), 'degisim': f(v['degisim'], 2)}) for c, v in d_.items()} for g, d_ in pay_degisim().items()}},
        'sermaye': {g: {'fazla': f(at(g).fazlaSermaye, 0), 'kapasite': f(at(g).buyumeKapasite, 0), 'rak': f(at(g).rakYogunluk, 1), 'syr': f(at(g).syr, 1)} for g in GROUPS},
        'npl_olusum12': {g: f(at(g).nplOlusum12, 2) for g in GROUPS},
        'kopru': haftalik_kopru(),
        'reel_fx': [{k: (None if v is None else (round(v / 1e3, 1) if k != 'tarih' else v)) for k, v in r.items() if k in ('tarih', 'varlik', 'yukumluluk', 'net', 'net_kisa')} for r in reel_sektor_fx()],
        'basabas': [{k: r.get(k) for k in ('tarih', 'tl3', 'usd3', 'pka12', 'spot', 'bek_dep', 'basabas_dep', 'basabas_tl', 'usd_getiri')} for r in basabas() if r['tarih'] >= '2015-01'],
        'tufe_son': ENF_SON.strftime('%Y-%m') if ENF_SON is not None else None,
    }
    pdf = a.pdf or (arsiv[0]['pdf'] if arsiv else None)
    xlsx = a.xlsx or (arsiv[0]['xlsx'] if arsiv else None)

    S = kpi['S']
    ozet = (f"<b>{donem_ad}</b> BDDK verileri: sektör aktifleri {str(S['aktif']).replace('.', ',')} trilyon TL (yıllık %{str(S['g_aktif']).replace('.', ',')}), "
            f"TP canlı krediler yıllık %{str(S['g_canliTP']).replace('.', ',')} büyüdü; NPL %{str(S['npl']).replace('.', ',')}, SYR %{str(S['syr']).replace('.', ',')}, "
            f"ROE %{str(S['roe']).replace('.', ',')}. Aylık net kâr {str(S['netKar_m']).replace('.', ',')} milyar TL.")
    if gor:
        ozet += ' ' + gor['baslik'] + '.'

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        'updated': dt.datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M'), 'donem': donem, 'donem_ad': donem_ad, 'pdf': pdf, 'xlsx': xlsx,
        'ozet_html': ozet, 'gorunum': gor, 'gruplar': [{'kod': g, 'ad': GNAME[g], 'kisa': GSHORT[g]} for g in GROUPS], 'mevduat_gruplari': DEPG,
        'kpi': kpi, 'karne': karne, 'seri': seri, 'kompozisyon': komp, 'arsiv': arsiv, 'analiz': analiz,
    }, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f"site/data/bankacilik.json yazıldı · dönem {donem_ad} · seri {len(tarihler)} ay · arşiv {len(arsiv)} rapor · {OUT.stat().st_size // 1024} KB")


if __name__ == '__main__':
    main()
