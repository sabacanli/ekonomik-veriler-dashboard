"""
BDDK haftalık analiz tabloları — TL/USD Excel'lerinden iki özet tablo üretir.
=============================================================================
Kaynak: 'bddk veri çekme' scraper'ının ürettiği bddk_krediler_TL_*.xlsx ve
bddk_krediler_USD_*.xlsx. Her dosya 5 BLOK içerir (ayraç satırlarıyla):
  1) Sektör (toplam)          [dosya başı]
  2) "Mevduat - Kamu"         → Kamu
  3) "Mevduat - Yabancı"      → Yabancı Özel
  4) "Mevduat - Yerli Özel"   → Yerli Özel
  5) "Katılım"                → Katılım
Her blok ~53 haftalık zaman serisidir; kalem başına TP/YP/TOPLAM kolonları.

Üretilen tablolar (kullanıcının Excel şablonunun birebir karşılığı):
  Tablo 1: Menkul Değerler + Krediler + Bankalardan Alacaklar
  Tablo 2: Mevduat + Diğer Bilanço Kalemleri
Kolonlar: Toplam · Haftalık % · YtD % · Yıllık %  |  Sektör kırılımı
(Kamu / Yerli Özel / Yabancı Özel / Katılım — haftalık % değişim).

dashboard.py ve site_export.py tarafından ortak kullanılır.
"""
import pandas as pd
from pathlib import Path

# Excel'deki kalem sırası (Tarih=0. kolon; her kalem 3 kolon: TP, YP, TOPLAM)
ITEMS = ["menkul_toplam", "devlet_tahvil", "bank_alacak", "bank_alacak_yd",
         "kredi_toplam", "tuketici_bkk", "konut", "tasit", "ihtiyac", "bkk",
         "ticari", "kkart_kurumsal", "mevduat", "mevduat_gk", "mevduat_tk",
         "bank_borc", "bank_borc_yd", "repo", "ihrac", "kkm"]

TP, YP, TOPLAM = 0, 1, 2

# Ayraç satırı -> grup anahtarı
GRUP_AYRAC = {"Mevduat - Kamu": "kamu", "Mevduat - Yabancı": "yabanci",
              "Mevduat - Yerli Özel": "yerli", "Katılım": "katilim"}
GRUP_SIRA = ["kamu", "yerli", "yabanci", "katilim"]  # tablo kolon sırası


def _col(item, part):
    return 1 + 3 * ITEMS.index(item) + part


# (etiket, kaynak 'TL'|'USD', kalem, kolon, girinti, bölüm başı mı)
TABLO1 = [
    ("Toplam Menkul Değerler",             "TL",  "menkul_toplam",  TOPLAM, 0, True),
    ("TL Menkul Değerler",                 "TL",  "menkul_toplam",  TP,     1, False),
    ("Devlet Tahvilleri",                  "TL",  "devlet_tahvil",  TP,     2, False),
    ("YP Menkul Değerler (USD)",           "USD", "menkul_toplam",  YP,     1, False),
    ("Devlet Tahvilleri (USD)",            "USD", "devlet_tahvil",  YP,     2, False),
    ("Toplam Krediler (TL)",               "TL",  "kredi_toplam",   TOPLAM, 0, True),
    ("TL Krediler",                        "TL",  "kredi_toplam",   TP,     1, False),
    ("Ticari ve Diğer Krediler (TL)",      "TL",  "ticari",         TP,     1, False),
    ("Tüketici Kredileri ve B.K.K. (TL)",  "TL",  "tuketici_bkk",   TP,     1, False),
    ("Konut",                              "TL",  "konut",          TP,     2, False),
    ("Taşıt",                              "TL",  "tasit",          TP,     2, False),
    ("İhtiyaç",                            "TL",  "ihtiyac",        TP,     2, False),
    ("Bireysel Kredi Kartları (TL)",       "TL",  "bkk",            TP,     1, False),
    ("Kurumsal Kredi Kartları (TL)",       "TL",  "kkart_kurumsal", TP,     1, False),
    ("YP Krediler (USD)",                  "USD", "kredi_toplam",   YP,     1, False),
    ("Bankalardan Alacaklar — Toplam (TL)","TL",  "bank_alacak",    TOPLAM, 0, True),
    ("TL",                                 "TL",  "bank_alacak",    TP,     1, False),
    ("YP (USD)",                           "USD", "bank_alacak",    YP,     1, False),
    ("Yurt dışı Bankalar (USD)",           "USD", "bank_alacak_yd", YP,     2, False),
]

TABLO2 = [
    ("Toplam Mevduat (TL Cinsi)",                    "TL",  "mevduat",      TOPLAM, 0, True),
    ("TL Mevduat",                                   "TL",  "mevduat",      TP,     1, False),
    ("Gerçek Kişiler",                               "TL",  "mevduat_gk",   TP,     2, False),
    ("Ticari Kuruluşlar",                            "TL",  "mevduat_tk",   TP,     2, False),
    ("Kur Korumalı Mevduat (KKM)",                   "TL",  "kkm",          TP,     2, False),
    ("YP Mevduat (USD)",                             "USD", "mevduat",      YP,     1, False),
    ("Gerçek Kişiler (USD)",                         "USD", "mevduat_gk",   YP,     2, False),
    ("Ticari Kuruluşlar (USD)",                      "USD", "mevduat_tk",   YP,     2, False),
    ("Bankalara Borçlar — Toplam (TL)",              "TL",  "bank_borc",    TOPLAM, 0, True),
    ("TL",                                           "TL",  "bank_borc",    TP,     1, False),
    ("Yurtdışı Bankalar (TL)",                       "TL",  "bank_borc_yd", TP,     2, False),
    ("YP (USD)",                                     "USD", "bank_borc",    YP,     1, False),
    ("Yurtdışı Bankalar (USD)",                      "USD", "bank_borc_yd", YP,     2, False),
    ("Repo İşl. Sağlanan Fonlar — Toplam (TL)",      "TL",  "repo",         TOPLAM, 0, True),
    ("TL",                                           "TL",  "repo",         TP,     1, False),
    ("YP (USD)",                                     "USD", "repo",         YP,     1, False),
    ("İhraç Edilen Menkul Kıymetler — Toplam (TL)",  "TL",  "ihrac",        TOPLAM, 0, True),
    ("TL",                                           "TL",  "ihrac",        TP,     1, False),
    ("YP (USD)",                                     "USD", "ihrac",        YP,     1, False),
]


def _parse_blocks(fp):
    """Dosyayı grup bloklarına ayırır: {'sektor': df, 'kamu': df, ...}"""
    raw = pd.read_excel(fp, header=None)
    raw = raw.iloc[1:].reset_index(drop=True)  # üst başlık satırı

    # Ayraç satırlarını bul
    sep_idx = []
    for i, v in raw[0].items():
        if isinstance(v, str) and v.strip() in GRUP_AYRAC:
            sep_idx.append((i, GRUP_AYRAC[v.strip()]))

    bounds = [(0, "sektor")] + [(i + 1, g) for i, g in sep_idx]
    ends = [i for i, _ in sep_idx] + [len(raw)]

    out = {}
    for (start, name), end in zip(bounds, ends):
        b = raw.iloc[start:end].copy()
        b[0] = pd.to_datetime(b[0], format="%d.%m.%Y", errors="coerce")
        b = b.dropna(subset=[0]).sort_values(0).reset_index(drop=True)
        for c in b.columns[1:]:
            b[c] = pd.to_numeric(b[c], errors="coerce")
        out[name] = b
    return out


def load_latest(data_dir):
    """En güncel TL ve USD dosyalarını blok yapısıyla yükler.
    Dönüş: (tl_blocks, usd_blocks, dosya_adı) veya (None, None, None)."""
    d = Path(data_dir)
    tl = sorted(d.glob("bddk_krediler_TL_*.xls*"), key=lambda x: x.stat().st_mtime)
    usd = sorted(d.glob("bddk_krediler_USD_*.xls*"), key=lambda x: x.stat().st_mtime)
    if not tl or not usd:
        return None, None, None
    return _parse_blocks(tl[-1]), _parse_blocks(usd[-1]), tl[-1].name


def _pct(last, base):
    if last is None or base is None or pd.isna(last) or pd.isna(base) or base == 0:
        return None
    return float((last / base - 1) * 100)


def hesapla(tl_blocks, usd_blocks):
    """Dönüş: (tablo1, tablo2, son_tarih, onceki_tarih).
    Satır: {label, indent, bold, usd, toplam, hafta, ytd, yillik,
            kamu, yerli, yabanci, katilim}  (grup kolonları: haftalık %)."""

    def rows_for(spec):
        rows = []
        for label, src, item, part, indent, bold in spec:
            blocks = tl_blocks if src == "TL" else usd_blocks
            sek = blocks["sektor"]
            c = _col(item, part)
            s, t = sek[c], sek[0]
            last = s.iloc[-1]
            prev = s.iloc[-2] if len(s) >= 2 else None
            cy = t.iloc[-1].year
            onceki_yil = t[t.dt.year < cy]
            ytd_base = s.loc[onceki_yil.index[-1]] if len(onceki_yil) else None
            hedef = t.iloc[-1] - pd.Timedelta(days=365)
            yil_base = s.loc[(t - hedef).abs().idxmin()]

            row = {"label": label, "indent": indent, "bold": bold, "usd": src == "USD",
                   "toplam": None if pd.isna(last) else float(last),
                   "hafta": _pct(last, prev), "ytd": _pct(last, ytd_base),
                   "yillik": _pct(last, yil_base)}

            # Grup kırılımı: haftalık % değişim
            for g in GRUP_SIRA:
                gv = None
                gb = blocks.get(g)
                if gb is not None and len(gb) >= 2:
                    gs = gb[c]
                    gv = _pct(gs.iloc[-1], gs.iloc[-2])
                row[g] = gv
            rows.append(row)
        return rows

    sek_t = tl_blocks["sektor"][0]
    son = sek_t.iloc[-1]
    onceki = sek_t.iloc[-2] if len(sek_t) >= 2 else None
    return rows_for(TABLO1), rows_for(TABLO2), son, onceki


def renk(v, olcek):
    """Isı haritası rengi: kırmızı (negatif) → sarı (0) → yeşil (pozitif).
    olcek = tam doygunluğa ulaşılan mutlak %. Dönüş: (r, g, b) veya None."""
    if v is None:
        return None
    x = max(-1.0, min(1.0, v / olcek))
    KIRMIZI, SARI, YESIL = (224, 92, 87), (238, 210, 100), (80, 178, 110)
    if x < 0:
        a, b, t = KIRMIZI, SARI, x + 1
    else:
        a, b, t = SARI, YESIL, x
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


# Kolon -> renk ölçeği (± % doygunluk)
OLCEK = {"hafta": 3.0, "ytd": 25.0, "yillik": 50.0,
         "kamu": 3.0, "yerli": 3.0, "yabanci": 3.0, "katilim": 3.0}
