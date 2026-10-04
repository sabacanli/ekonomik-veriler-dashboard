#!/usr/bin/env python3
"""Bankacılık Monitörü site verisi → site/data/bankacilik.json (site/bankacilik.html, ana sayfa kartı, e-posta).
Kullanım: python export_web.py [--pdf raporlar/x.pdf] [--xlsx raporlar/x.xlsx]"""
import warnings; warnings.filterwarnings('ignore')
import argparse, datetime as dt, json, re, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from calc import D, LAST, GROUPS, DEPG, GSHORT, GNAME, at  # noqa: E402

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
}
KARNE = [('Aktif büyümesi', 'g_aktif', 1, 1), ('Aktif TP ağırlığı', 'aktifTPag', 1, 0), ('TP canlı kredi büyümesi', 'g_canliTP', 1, 1),
         ('YP canlı kredi büyümesi (USD)', 'g_canliYP_usd', 1, 1), ('Tüketici kredileri / canlı krediler', 'tukCanli', 1, 0),
         ('NPL oranı', 'npl', 2, -1), ('Özel karşılık oranı', 'ozelKarsOran', 1, 1), ('TP toplanan fon büyümesi', 'g_mvTP', 1, 1),
         ('YP toplanan fon büyümesi (USD)', 'g_mvYP_usd', 1, 1), ('Toplanan fon TP ağırlığı', 'fonTPag', 1, 0),
         ('Standart SYR', 'syr', 1, 1), ('Çekirdek SYR', 'cekSyr', 1, 1), ('ROA', 'roa', 1, 1), ('ROE', 'roe', 1, 1), ('Net faiz marjı', 'nim', 1, 1),
         ('Brüt faaliyet kârı artışı', 'gy_brutKar', 1, 1), ('Net kâr artışı', 'gy_netKar', 1, 1), ('Gider / gelir oranı', 'giderGelir', 1, -1),
         ('Op-Ex / aktifler', 'opexAktif', 1, -1), ('Kaldıraç (x)', 'kaldirac', 1, -1)]
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
        kpi[g] = {'aktif': f(s.aktif / 1e6, 2), 'g_aktif': f(s.g_aktif, 1), 'canli': f(s.canli / 1e6, 2), 'g_canliTP': f(s.g_canliTP, 1), 'g_canliTP_onceki': f(p.g_canliTP, 1),
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
        'updated': dt.datetime.now().strftime('%d.%m.%Y %H:%M'), 'donem': donem, 'donem_ad': donem_ad, 'pdf': pdf, 'xlsx': xlsx,
        'ozet_html': ozet, 'gorunum': gor, 'gruplar': [{'kod': g, 'ad': GNAME[g], 'kisa': GSHORT[g]} for g in GROUPS], 'mevduat_gruplari': DEPG,
        'kpi': kpi, 'karne': karne, 'seri': seri, 'kompozisyon': komp, 'arsiv': arsiv,
    }, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f"site/data/bankacilik.json yazıldı · dönem {donem_ad} · seri {len(tarihler)} ay · arşiv {len(arsiv)} rapor · {OUT.stat().st_size // 1024} KB")


if __name__ == '__main__':
    main()
