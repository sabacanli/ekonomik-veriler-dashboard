"""
Site veri dışa aktarımı — mevcut modül verilerinden site/data/*.json üretir.
==========================================================================
Statik web sitesi (site/) bu JSON'ları okur; sunucu hesabı gerekmez.
Her veri güncellemesinden sonra çalıştırılır:  python3 site_export.py

Kaynaklar (hepsi mevcut modül çıktıları — yeniden veri ÇEKMEZ):
  enflasyon/enflasyon.xlsx            tcmb haftalık stok/output/*
  butce/butce.xlsx                    yabanci para hareketi/dth.xlsx
  hazine nakit/nakit.xlsx             net rezerv/net_rezerv.xlsx
  kredi mevduat/kredi_mevduat.xlsx    cari acik/cari_acik_son.xlsx
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent
DATA = BASE / "site" / "data"
DATA.mkdir(parents=True, exist_ok=True)

AY = {1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
      7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"}


def ht(v, d=1, sign=False):
    """Türkçe sayı biçimi (1.234,5)."""
    if v is None or pd.isna(v):
        return "—"
    fmt = f"{{:+,.{d}f}}" if sign else f"{{:,.{d}f}}"
    return fmt.format(float(v)).replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def mtime(path):
    p = Path(path)
    if not p.exists():
        return None
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%d.%m.%Y %H:%M")


def dump(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ {name}")


def col(df, c, r=None):
    """Kolonu JSON'a uygun listeye çevirir (NaN -> None)."""
    s = df[c]
    if r is not None:
        s = s.round(r)
    return [None if pd.isna(x) else (float(x) if not isinstance(x, str) else x) for x in s]


# ──────────────────────────────────────────────────────────────
# Modül veri paketleri
# ──────────────────────────────────────────────────────────────

def build_tcmb_stok():
    out_dir = BASE / "tcmb haftalık stok" / "output"

    def _last_csv(name):
        fp = out_dir / f"raw_{name}.csv"
        if not fp.exists():
            return None, None
        d = pd.read_csv(fp)
        return (float(d.iloc[-1]["value"]), d.iloc[-1]["date"]) if len(d) else (None, None)

    hs, dt1 = _last_csv("Hisse_Stok")
    ds, _ = _last_csv("DIBS_Stok")
    hd, _ = _last_csv("Hisse_Degisim")
    dd, _ = _last_csv("DIBS_Degisim")

    hx = pd.read_excel(out_dir / "hareket.xlsx", sheet_name="Haftalik")
    hx["tarih"] = pd.to_datetime(hx["tarih"])
    hx = hx.sort_values("tarih").reset_index(drop=True)
    hx["dibs_toplam"] = hx[["dibs_kesin", "dibs_dolayli"]].sum(axis=1, min_count=1)
    hx["toplam_4h"] = hx["toplam"].rolling(4).sum()
    hx["menkul_4h"] = hx["menkul_toplam"].rolling(4).sum()
    L = hx.iloc[-1]

    stok = (hs or 0) + (ds or 0)
    yon = "giriş" if L["toplam"] >= 0 else "çıkış"
    ozet = (f"Yurt dışı yerleşiklerin Türkiye menkul kıymet stoku {dt1} itibarıyla toplam "
            f"<b>{ht(stok, 0)} milyon USD</b> (Hisse {ht(hs, 0)}, DİBS {ht(ds, 0)} milyon USD). "
            f"<b>{L['tarih'].strftime('%d.%m.%Y')}</b> haftasında toplam net yabancı hareketi "
            f"<b>{ht(L['toplam'] / 1000, 1, True)} milyar USD {yon}</b>: Hisse {ht(L['hisse'], 0, True)}, "
            f"DİBS {ht(L['dibs_toplam'], 0, True)} (kesin {ht(L['dibs_kesin'], 0, True)}, "
            f"dolaylı {ht(L['dibs_dolayli'], 0, True)}), ÖST {ht(L['ost'], 0, True)}, "
            f"Eurobond {ht(L['eurobond'], 0, True)} milyon USD. "
            f"Son 4 haftada kümülatif <b>{ht(L['toplam_4h'] / 1000, 1, True)} milyar USD</b>.")

    hx52 = hx.tail(156)  # site paketi: son 3 yıl haftalık
    hareket = {
        "tarih": [t.strftime("%Y-%m-%d") for t in hx52["tarih"]],
        **{c: col(hx52, c, 1) for c in ["hisse", "dibs_kesin", "dibs_dolayli", "ost",
                                        "eurobond", "menkul_toplam", "toplam",
                                        "toplam_4h", "menkul_4h"]},
    }

    hy = hx.copy()
    hy["yil"] = hy["tarih"].dt.year
    yc = hy.groupby("yil")[["dibs_kesin", "eurobond", "hisse", "dibs_dolayli", "ost"]].sum().tail(3)
    yillik = {"yil": [str(int(y)) for y in yc.index],
              **{c: [round(float(v) / 1000, 1) for v in yc[c]] for c in yc.columns}}

    dump("tcmb_stok.json", {
        "updated": mtime(out_dir / "hareket.xlsx"),
        "ozet_html": ozet,
        "stok": {"tarih": dt1, "hisse": hs, "dibs": ds, "toplam": stok,
                 "hisse_deg": hd, "dibs_deg": dd, "akim": (hd or 0) + (dd or 0)},
        "hafta": {"toplam": float(L["toplam"]), "toplam_4h": float(L["toplam_4h"])},
        "hareket": hareket,
        "yillik": yillik,
    })


def build_dth():
    fp = BASE / "yabanci para hareketi" / "dth.xlsx"
    d = pd.read_excel(fp, sheet_name="Haftalik")
    d["tarih"] = pd.to_datetime(d["tarih"])
    d = d.sort_values("tarih").reset_index(drop=True)
    L = d.iloc[-1]
    s4 = float(d["yerlesik_toplam"].tail(4).sum())
    ytd = float(d[d["tarih"].dt.year == int(L["tarih"].year)]["yerlesik_toplam"].sum())
    yon = "arttı" if L["yerlesik_toplam"] >= 0 else "azaldı"
    yon4 = "artış" if s4 >= 0 else "azalış"
    yon_ytd = "artış (dolarizasyon)" if ytd >= 0 else "azalış (de-dolarizasyon)"
    ozet = (f"<b>{L['tarih'].strftime('%d.%m.%Y')}</b> haftasında yurt içi yerleşiklerin yabancı para "
            f"mevduatı (altın ve parite etkileri düzeltilmiş) "
            f"<b>{ht(abs(L['yerlesik_toplam']) / 1000)} milyar USD {yon}</b>: "
            f"tüzel kişiler <b>{ht(L['tuzel_kisiler'] / 1000, 1, True)}</b>, "
            f"gerçek kişiler <b>{ht(L['gercek_kisiler'] / 1000, 1, True)} milyar USD</b> "
            f"(altın {ht(L['gk_altin'] / 1000, 1, True)}, döviz {ht(L['gk_doviz'] / 1000, 1, True)}). "
            f"Son 4 haftada kümülatif {ht(abs(s4) / 1000)} milyar USD {yon4}; "
            f"yılbaşından beri <b>{ht(abs(ytd) / 1000)} milyar USD {yon_ytd}</b>.")

    dp = d.tail(156)
    dump("dth.json", {
        "updated": mtime(fp),
        "ozet_html": ozet,
        "hafta": {"toplam": float(L["yerlesik_toplam"]), "gercek": float(L["gercek_kisiler"]),
                  "tuzel": float(L["tuzel_kisiler"]), "ytd": ytd},
        "haftalik": {
            "tarih": [t.strftime("%Y-%m-%d") for t in dp["tarih"]],
            "toplam": col(dp, "yerlesik_toplam", 1),
            "gercek": col(dp, "gercek_kisiler", 1),
            "tuzel": col(dp, "tuzel_kisiler", 1),
            "altin": col(dp, "gk_altin", 1),
            "doviz": col(dp, "gk_doviz", 1),
        },
    })


def build_enflasyon():
    fp = BASE / "enflasyon" / "enflasyon.xlsx"
    g = pd.read_excel(fp, sheet_name="Genel")
    g["tarih"] = pd.to_datetime(g["tarih"])
    g = g.sort_values("tarih").reset_index(drop=True)
    L, P = g.iloc[-1], g.iloc[-2]
    d_yil = float(L["yillik"] - P["yillik"])
    yon = "geriledi" if d_yil < 0 else "yükseldi"
    trend = "dezenflasyon sürüyor" if d_yil < 0 else "enflasyon yeniden hızlandı"
    avg3 = float(g["aylik"].tail(3).mean())
    ozet = (f"<b>{AY[L['tarih'].month]} {L['tarih'].year}</b> itibarıyla yıllık enflasyon "
            f"<b>%{ht(L['yillik'], 2)}</b>, aylık <b>%{ht(L['aylik'], 2)}</b>; "
            f"yılbaşından beri %{ht(L['ytd'], 2)}. Yıllık oran önceki aya göre "
            f"<b>{ht(abs(d_yil), 2)} puan {yon}</b> — {trend}; "
            f"son 3 ayın ortalama aylık artışı %{ht(avg3, 2)}.")

    # ── Alt kalemler (COICOP ana grupları) — son 24 ay ──
    KISA = {
        "01. Gıda Ve Alkolsüz İçecekler": "Gıda ve Alkolsüz İçecekler",
        "02. Alkollü İçecekler, Tütün Ve Tütün Ürünleri": "Alkollü İçecek ve Tütün",
        "03. Giyim Ve Ayakkabı": "Giyim ve Ayakkabı",
        "04. Konut, Su, Elektrik, Gaz Ve Diğer Yakıtlar": "Konut ve Enerji",
        "05. Mobilya, Mefruşat Ve Evde Kullanılan Ekipmanlar İle Rutin Ev Bakım Ve Onarımı": "Ev Eşyası",
        "06. Sağlık": "Sağlık",
        "07. Ulaştırma": "Ulaştırma",
        "08. Bilgi Ve İletişim": "Bilgi ve İletişim",
        "09. Eğlence, Dinlence, Spor Ve Kültür": "Eğlence ve Kültür",
        "10. Eğitim Hizmetleri": "Eğitim",
        "11. Lokantalar Ve Konaklama Hizmetleri": "Lokanta ve Otel",
        "12. Sigorta Ve Finansal Hizmetler": "Sigorta ve Finans",
        "13. Kişisel Bakım, Sosyal Koruma Ve Çeşitli Mal Ve Hizmetler": "Kişisel Bakım ve Diğer",
    }
    ende = pd.read_excel(fp, sheet_name="AltKalem_Endeks")
    yill = pd.read_excel(fp, sheet_name="AltKalem_Yillik")
    for _df in (ende, yill):
        _df["tarih"] = pd.to_datetime(_df["tarih"])
        _df.sort_values("tarih", inplace=True)
    kalemler = [c for c in ende.columns if c != "tarih"]

    # Aylık %: endeksten; YTD %: önceki yıl Aralık endeksine göre
    ayl = ende.set_index("tarih")[kalemler].pct_change() * 100
    e_idx = ende.set_index("tarih")[kalemler]
    aralik = e_idx[e_idx.index.month == 12]
    ytd_m = pd.DataFrame(index=e_idx.index, columns=kalemler, dtype=float)
    for t in e_idx.index:
        onceki = aralik[aralik.index < t]
        if len(onceki):
            ytd_m.loc[t] = (e_idx.loc[t] / onceki.iloc[-1] - 1) * 100

    son24 = ende["tarih"].tail(24).tolist()
    y_idx = yill.set_index("tarih")[kalemler]

    def matris(kaynak):
        out = []
        for t in son24:
            satir = kaynak.loc[t]
            out.append([None if pd.isna(v) else round(float(v), 2) for v in satir])
        return out

    g_idx = g.set_index("tarih")
    alt = {
        "kalemler": [KISA.get(k, k) for k in kalemler],
        "aylar": [t.strftime("%Y-%m") for t in son24],
        "ay_adlari": [f"{AY[t.month]} {t.year}" for t in son24],
        "yillik": matris(y_idx),
        "aylik": matris(ayl),
        "ytd": matris(ytd_m),
        "genel": {
            "yillik": [round(float(g_idx.loc[t, "yillik"]), 2) for t in son24],
            "aylik": [round(float(g_idx.loc[t, "aylik"]), 2) for t in son24],
            "ytd": [round(float(g_idx.loc[t, "ytd"]), 2) for t in son24],
        },
    }

    gp = g.tail(72)  # son 6 yıl aylık
    dump("enflasyon.json", {
        "updated": mtime(fp),
        "ozet_html": ozet,
        "son": {"donem": f"{AY[L['tarih'].month]} {L['tarih'].year}",
                "yillik": float(L["yillik"]), "aylik": float(L["aylik"]),
                "ytd": float(L["ytd"]), "d_yillik": d_yil},
        "genel": {
            "tarih": [t.strftime("%Y-%m-%d") for t in gp["tarih"]],
            "yillik": col(gp, "yillik", 2),
            "aylik": col(gp, "aylik", 2),
            "ytd": col(gp, "ytd", 2),
        },
        "alt": alt,
    })


def _kumulatif_yillar(df, val_col, n_yil=5):
    """Son n yıl için yılbaşından kümülatif seri (Milyar TL) — yıl karşılaştırma grafiği."""
    cy = int(df["yil"].max())
    out = []
    for y in sorted(df["yil"].unique()):
        y = int(y)
        if y < cy - n_yil + 1:
            continue
        yd = df[df["yil"] == y].sort_values("ay")
        out.append({"yil": str(y),
                    "ay": [int(a) for a in yd["ay"]],
                    "kum": [round(float(v) / 1000, 1) for v in yd[val_col].cumsum()]})
    return out


def build_butce():
    fp = BASE / "butce" / "butce.xlsx"
    b = pd.read_excel(fp, sheet_name="Aylik")
    b["tarih"] = pd.to_datetime(b["tarih"])
    b = b.sort_values("tarih").reset_index(drop=True)
    L = b.iloc[-1]
    cy, cm = int(L["yil"]), int(L["ay"])
    ytd = float(b[(b.yil == cy) & (b.ay <= cm)]["denge"].sum())
    ytd_prev = float(b[(b.yil == cy - 1) & (b.ay <= cm)]["denge"].sum())
    yon = "açık" if L["denge"] < 0 else "fazla"
    ozet = (f"<b>{AY[cm]} {cy}</b> ayında merkezi yönetim bütçesi "
            f"<b>{ht(abs(L['denge']) / 1000)} milyar TL {yon}</b> verdi "
            f"(gelir {ht(L['gelir'] / 1000)}, gider {ht(L['gider'] / 1000)} milyar TL). "
            f"Faiz dışı denge <b>{ht(L['faiz_disi_denge'] / 1000)} milyar TL</b>, "
            f"faiz gideri {ht(L['faiz_gideri'] / 1000)} milyar TL. "
            f"Yılbaşından beri kümülatif bütçe açığı <b>{ht(abs(ytd) / 1000)} milyar TL</b> — "
            f"geçen yıl aynı dönemde {ht(abs(ytd_prev) / 1000)} milyar TL idi.")
    dump("butce.json", {
        "updated": mtime(fp),
        "ozet_html": ozet,
        "son": {"donem": f"{AY[cm]} {cy}", "denge": float(L["denge"]), "gelir": float(L["gelir"]),
                "gider": float(L["gider"]), "faiz_disi": float(L["faiz_disi_denge"]),
                "faiz": float(L["faiz_gideri"]), "ytd": ytd, "ytd_prev": ytd_prev},
        "aylik": {
            "tarih": [t.strftime("%Y-%m-%d") for t in b["tarih"]],
            "denge": col(b, "denge", 0), "gelir": col(b, "gelir", 0), "gider": col(b, "gider", 0),
            "dolaysiz": col(b, "dolaysiz_vergi", 0), "dolayli": col(b, "dolayli_vergi", 0),
        },
        "kumulatif": _kumulatif_yillar(b, "denge"),
    })


def build_nakit():
    fp = BASE / "hazine nakit" / "nakit.xlsx"
    n = pd.read_excel(fp, sheet_name="Aylik")
    n["tarih"] = pd.to_datetime(n["tarih"])
    n = n.sort_values("tarih").reset_index(drop=True)
    L = n.iloc[-1]
    cy, cm = int(L["yil"]), int(L["ay"])
    ytd = float(n[(n.yil == cy) & (n.ay <= cm)]["nakit_denge"].sum())
    ytd_prev = float(n[(n.yil == cy - 1) & (n.ay <= cm)]["nakit_denge"].sum())
    yon = "açık" if L["nakit_denge"] < 0 else "fazla"
    yon_ytd = "açığı" if ytd < 0 else "fazlası"
    yon_prev = "açık" if ytd_prev < 0 else "fazla"
    ozet = (f"<b>{AY[cm]} {cy}</b> ayında Hazine nakit dengesi "
            f"<b>{ht(abs(L['nakit_denge']) / 1000)} milyar TL {yon}</b> verdi "
            f"(gelir {ht(L['gelir'] / 1000)}, gider {ht(L['gider'] / 1000)} milyar TL). "
            f"Faiz dışı denge <b>{ht(L['faiz_disi_denge'] / 1000)} milyar TL</b>, "
            f"faiz ödemesi {ht(L['faiz_odemesi'] / 1000)} milyar TL. "
            f"Yılbaşından beri kümülatif nakit {yon_ytd} <b>{ht(abs(ytd) / 1000)} milyar TL</b> — "
            f"geçen yıl aynı dönemde {ht(abs(ytd_prev) / 1000)} milyar TL {yon_prev} idi.")
    dump("nakit.json", {
        "updated": mtime(fp),
        "ozet_html": ozet,
        "son": {"donem": f"{AY[cm]} {cy}", "denge": float(L["nakit_denge"]), "gelir": float(L["gelir"]),
                "gider": float(L["gider"]), "faiz_disi": float(L["faiz_disi_denge"]),
                "faiz": float(L["faiz_odemesi"]), "ytd": ytd, "ytd_prev": ytd_prev},
        "aylik": {
            "tarih": [t.strftime("%Y-%m-%d") for t in n["tarih"]],
            "denge": col(n, "nakit_denge", 0), "gelir": col(n, "gelir", 0), "gider": col(n, "gider", 0),
            "ic_borc": col(n, "ic_borclanma_net", 0), "dis_borc": col(n, "dis_borclanma_net", 0),
        },
        "kumulatif": _kumulatif_yillar(n, "nakit_denge"),
    })


def build_rezerv():
    fp = BASE / "net rezerv" / "net_rezerv.xlsx"
    r = pd.read_excel(fp)
    r["tarih"] = pd.to_datetime(r["tarih"])
    r = r.sort_values("tarih").reset_index(drop=True)
    L = r.iloc[-1]
    nrc = "net_rezerv_swap_haric"
    cur = float(L[nrc])
    m1 = r[r["tarih"] <= L["tarih"] - pd.Timedelta(days=30)]
    ys = r[r["tarih"] >= pd.Timestamp(L["tarih"].year, 1, 1)]
    d1 = (cur - float(m1.iloc[-1][nrc])) / 1000 if len(m1) else None
    dy = (cur - float(ys.iloc[0][nrc])) / 1000 if len(ys) else None
    ek = ""
    if d1 is not None and dy is not None:
        w1 = "arttı" if d1 >= 0 else "azaldı"
        wy = "artış" if dy >= 0 else "azalış"
        ek = (f" Son bir ayda <b>{ht(abs(d1))} milyar USD {w1}</b>; "
              f"yıl başından beri {ht(abs(dy))} milyar USD {wy}.")
    ozet = (f"<b>{L['tarih'].strftime('%d.%m.%Y')}</b> itibarıyla net rezerv (swap hariç) "
            f"<b>{ht(cur / 1000)} milyar USD</b>, swap dahil {ht(L['net_rezerv_swap_dahil'] / 1000)} milyar USD; "
            f"brüt dış varlıklar {ht(L['dis_varliklar'] / 1000)} milyar USD.{ek}")
    dump("rezerv.json", {
        "updated": mtime(fp),
        "ozet_html": ozet,
        "son": {"tarih": L["tarih"].strftime("%d.%m.%Y"), "haric": cur,
                "dahil": float(L["net_rezerv_swap_dahil"]), "brut": float(L["dis_varliklar"]),
                "net_swap": float(L["net_swap"]), "d1ay": d1, "dytd": dy},
        "seri": {
            "tarih": [t.strftime("%Y-%m-%d") for t in r["tarih"]],
            "haric": col(r, "net_rezerv_swap_haric", 0),
            "dahil": col(r, "net_rezerv_swap_dahil", 0),
            "brut": col(r, "dis_varliklar", 0),
            "net_swap": col(r, "net_swap", 0),
        },
    })


def build_kredi():
    fp = BASE / "kredi mevduat" / "kredi_mevduat.xlsx"
    ka = pd.read_excel(fp, sheet_name="Kredi_Akim")
    ka["tarih"] = pd.to_datetime(ka["tarih"])
    ka = ka.sort_values("tarih").reset_index(drop=True)
    L, P = ka.iloc[-1], ka.iloc[-5]
    d4 = {k: float(L[c] - P[c]) for k, c in
          [("ihtiyac", "İhtiyaç Kredisi"), ("tasit", "Taşıt Kredisi"),
           ("konut", "Konut Kredisi"), ("ticari", "Ticari Krediler")]}
    wi = "geriledi" if d4["ihtiyac"] < 0 else "yükseldi"
    wk = "yükseldi" if d4["konut"] > 0 else "geriledi"
    ozet = (f"<b>{L['tarih'].strftime('%d.%m.%Y')}</b> haftası yeni kredi faizleri (akım, yıllık bileşik): "
            f"İhtiyaç <b>%{ht(L['İhtiyaç Kredisi'], 2)}</b>, Konut %{ht(L['Konut Kredisi'], 2)}, "
            f"Taşıt %{ht(L['Taşıt Kredisi'], 2)}, Ticari %{ht(L['Ticari Krediler'], 2)}. "
            f"Son 4 haftada ihtiyaç kredisi faizi <b>{ht(abs(d4['ihtiyac']), 2)} puan {wi}</b>, "
            f"konut {ht(abs(d4['konut']), 2)} puan {wk}.")
    dump("kredi.json", {
        "updated": mtime(fp),
        "ozet_html": ozet,
        "son": {"tarih": L["tarih"].strftime("%d.%m.%Y"),
                "ihtiyac": float(L["İhtiyaç Kredisi"]), "tasit": float(L["Taşıt Kredisi"]),
                "konut": float(L["Konut Kredisi"]), "ticari": float(L["Ticari Krediler"]), "d4": d4},
        "seri": {
            "tarih": [t.strftime("%Y-%m-%d") for t in ka["tarih"]],
            "ihtiyac": col(ka, "İhtiyaç Kredisi", 2), "tasit": col(ka, "Taşıt Kredisi", 2),
            "konut": col(ka, "Konut Kredisi", 2), "ticari": col(ka, "Ticari Krediler", 2),
            "ticari_usd": col(ka, "Ticari Krediler (USD)", 2),
            "ticari_eur": col(ka, "Ticari Krediler (EUR)", 2),
        },
    })


def build_mevduat():
    fp = BASE / "kredi mevduat" / "kredi_mevduat.xlsx"
    ma = pd.read_excel(fp, sheet_name="Mevduat_Akim")
    ma["tarih"] = pd.to_datetime(ma["tarih"])
    ma = ma.sort_values("tarih").reset_index(drop=True)
    L = ma.iloc[-1]
    dt_ = float(L["Toplam"] - ma.iloc[-5]["Toplam"])
    if abs(dt_) < 0.10:
        ek = "Son 4 haftada büyük ölçüde <b>yatay</b> seyretti."
    else:
        w = "yükseldi" if dt_ > 0 else "geriledi"
        ek = f"Son 4 haftada toplam mevduat faizi <b>{ht(abs(dt_), 2)} puan {w}</b>."
    ozet = (f"<b>{L['tarih'].strftime('%d.%m.%Y')}</b> haftası TL mevduat faizi toplam "
            f"<b>%{ht(L['Toplam'], 2)}</b>; 1 aya kadar %{ht(L['1 Aya Kadar Vadeli'], 2)}, "
            f"3 aya kadar %{ht(L['3 Aya Kadar Vadeli'], 2)}, 1 yıla kadar %{ht(L['1 Yıla Kadar Vadeli'], 2)}. {ek}")
    dump("mevduat.json", {
        "updated": mtime(fp),
        "ozet_html": ozet,
        "son": {"tarih": L["tarih"].strftime("%d.%m.%Y"), "toplam": float(L["Toplam"]),
                "v1ay": float(L["1 Aya Kadar Vadeli"]), "v3ay": float(L["3 Aya Kadar Vadeli"]),
                "v1yil": float(L["1 Yıla Kadar Vadeli"]), "d4": dt_},
        "seri": {
            "tarih": [t.strftime("%Y-%m-%d") for t in ma["tarih"]],
            "v1ay": col(ma, "1 Aya Kadar Vadeli", 2), "v3ay": col(ma, "3 Aya Kadar Vadeli", 2),
            "v6ay": col(ma, "6 Aya Kadar Vadeli", 2), "v1yil": col(ma, "1 Yıla Kadar Vadeli", 2),
            "uzun": col(ma, "1 Yıl ve Daha Uzun Vadeli", 2), "toplam": col(ma, "Toplam", 2),
            "toplam_usd": col(ma, "Toplam (USD)", 2), "toplam_eur": col(ma, "Toplam (EUR)", 2),
        },
    })


def build_cari():
    fp = BASE / "cari acik" / "cari_acik_son.xlsx"
    c = pd.read_excel(fp)
    ccol = [x for x in c.columns if "Cari" in str(x)][0]
    fcol = [x for x in c.columns if "Finans" in str(x)][0]
    ncol = [x for x in c.columns if "Hata" in str(x)][0]
    c["cari_4c"] = c[ccol].rolling(4).sum()
    L = c.iloc[-1]
    last4 = float(L["cari_4c"])
    prev4 = float(c[ccol].iloc[-8:-4].sum()) if len(c) >= 8 else None
    kel = "açık" if last4 < 0 else "fazla"
    ek = ""
    if prev4 is not None:
        yon2 = "genişledi" if abs(last4) > abs(prev4) else "daraldı"
        ek = f"; bir yıl öncesine göre {yon2}"
    ozet = (f"Son dönem (<b>{L['Tarih']}</b>) cari işlemler dengesi <b>{ht(L[ccol], 0)} milyon USD</b>. "
            f"Son dört çeyreğin (12 aylık) toplamı <b>{ht(abs(last4) / 1000)} milyar USD {kel}</b>{ek}. "
            f"Finans hesabı {ht(L[fcol], 0)}, net hata &amp; noksan {ht(L[ncol], 0)} milyon USD.")
    # Ödemeler dengesi kırılım tablosu (aylık; hiyerarşik satırlar)
    odm = None
    try:
        ofp = BASE / "cari acik" / "odemeler_dengesi_tablo.xlsx"
        od = pd.read_excel(ofp, sheet_name=0)
        deger_kolonlari = [x for x in od.columns if x not in ("Kalem", "_level")]
        odm = {
            "updated": mtime(ofp),
            "cols": [str(x) for x in deger_kolonlari],
            "rows": [{"k": str(r["Kalem"]),
                      "lv": int(r["_level"]) if pd.notna(r["_level"]) else 0,
                      "v": [None if pd.isna(r[c]) else float(r[c]) for c in deger_kolonlari]}
                     for _, r in od.iterrows()],
        }
    except Exception:
        pass

    dump("cari.json", {
        "updated": mtime(fp),
        "ozet_html": ozet,
        "son": {"donem": str(L["Tarih"]), "cari": float(L[ccol]), "finans": float(L[fcol]),
                "nhn": float(L[ncol]), "yillik": last4},
        "seri": {
            "ceyrek": [str(x) for x in c["Tarih"]],
            "cari": col(c, ccol, 0), "finans": col(c, fcol, 0), "nhn": col(c, ncol, 0),
            "cari_4c": col(c, "cari_4c", 0),
        },
        "odm": odm,
    })


def _wavg(vals, weights):
    """Ağırlıklı ortalama (NaN'ler atlanır)."""
    m = vals.notna() & weights.notna() & (weights > 0)
    if not m.any():
        return None
    return float((vals[m] * weights[m]).sum() / weights[m].sum())


def _hazine_tarih(col):
    """Hazine Excel'indeki karışık tarih kolonu: bir kısmı 'GG.AA.YYYY' metni,
    bir kısmı Excel seri numarası (float). İkisini de çözer."""
    s_metin = pd.to_datetime(col.where(col.map(lambda x: isinstance(x, str))),
                             format="%d.%m.%Y", errors="coerce")
    s_seri = pd.to_datetime(pd.to_numeric(col, errors="coerce"),
                            unit="D", origin="1899-12-30", errors="coerce")
    return s_metin.fillna(s_seri)


def build_hazine():
    fp = BASE / "hazine ihale " / "hazine_ihale_verileri.xlsx"
    df = pd.read_excel(fp, sheet_name="Tüm İhaleler", header=[0, 1])
    df.columns = [" / ".join(str(x) for x in c) for c in df.columns]
    C_VAL = "Genel Bilgiler / Valör Tarihi"
    C_TUR = "Genel Bilgiler / Senet Türü"
    C_NET = "Toplam Satış / Net (Bin TL)"
    C_NOM = "Toplam Satış / Nominal (Bin TL)"
    C_FAIZ = "Kabul Edilen Faiz (%) / Ort. Yıllık Bileşik"
    C_TEKLIF = "Teklif Edilen Tutar / Nominal (Bin TL)"
    C_KABUL = "İhale Kabul Edilen Tutar / Nominal (Bin TL)"
    df[C_VAL] = _hazine_tarih(df[C_VAL])
    df = df.dropna(subset=[C_VAL]).sort_values(C_VAL).reset_index(drop=True)

    L_t = df[C_VAL].max()
    cy = int(L_t.year)
    ytd = df[df[C_VAL].dt.year == cy]
    ytd_satis = float(ytd[C_NET].sum()) / 1e6          # Bin TL -> Milyar TL
    son3ay = df[df[C_VAL] >= L_t - pd.DateOffset(months=3)]
    faiz3 = _wavg(son3ay[C_FAIZ], son3ay[C_NOM])
    ozet = (f"<b>{L_t.strftime('%d.%m.%Y')}</b> itibarıyla {cy} yılında Hazine iç borçlanma "
            f"ihalelerinde toplam <b>{ht(ytd_satis)} milyar TL</b> (net) satış yapıldı "
            f"({len(ytd)} ihale). Son 3 ayın satış ağırlıklı ortalama yıllık bileşik faizi "
            f"<b>%{ht(faiz3, 2)}</b>.")

    # Aylık seriler
    ayg = df.groupby(df[C_VAL].dt.to_period("M"))
    aylik = pd.DataFrame({
        "satis": ayg[C_NET].sum() / 1e6,
        "teklif": ayg[C_TEKLIF].sum(),
        "kabul": ayg[C_KABUL].sum(),
    })
    aylik["faiz"] = ayg.apply(lambda g: _wavg(g[C_FAIZ], g[C_NOM]))
    aylik["bid_cover"] = (aylik["teklif"] / aylik["kabul"]).where(aylik["kabul"] > 0)
    aylik.index = aylik.index.to_timestamp()

    # Yıllık senet türü dağılımı (son 6 yıl, Milyar TL)
    KISA = {"TLREF Endeksli Senetler": "TLREF",
            "TL Cinsi Kira Sertifikalari": "Kira Sertifikası",
            "TL Cinsi Kuponsuz Senetler": "Kuponsuz",
            "TL Cinsi TUFE Endeksli Senetler": "TÜFE Endeksli",
            "TL Cinsi Sabit Faizli Kuponlu Senetler": "Sabit Kuponlu",
            "TL Cinsi Degisken Faizli Kuponlu Senetler": "Değişken Kuponlu"}
    yt = df.copy()
    yt["yil"] = yt[C_VAL].dt.year
    yt["tur"] = yt[C_TUR].map(KISA).fillna(yt[C_TUR])
    piv = (yt.pivot_table(index="yil", columns="tur", values=C_NET, aggfunc="sum")
           .fillna(0.0) / 1e6).tail(6)

    # İhale bazlı kayıtlar (sayfadaki filtreli analizlerin ham verisi).
    # Birimler: tutarlar Bin TL, faiz %, vade gün.
    C_ITFA = "Genel Bilgiler / İtfa Tarihi"
    C_VG = "Genel Bilgiler / Vade (Gün)"
    C_ISIN = "Genel Bilgiler / ISIN Kodu"
    itfa = _hazine_tarih(df[C_ITFA])

    def num(s, r=0):
        return [None if pd.isna(v) else round(float(v), r) for v in s]

    ihaleler = {
        "t": [d.strftime("%Y-%m-%d") for d in df[C_VAL]],
        "tur": [KISA.get(x, str(x)) for x in df[C_TUR]],
        "itfa": [None if pd.isna(d) else d.strftime("%Y-%m-%d") for d in itfa],
        "vg": num(df[C_VG]),
        "net": num(df[C_NET]),
        "nom": num(df[C_NOM]),
        "teklif": num(df[C_TEKLIF]),
        "kabul": num(df[C_KABUL]),
        "faiz": num(df[C_FAIZ], 2),
        "isin": [None if pd.isna(x) else str(x) for x in df[C_ISIN]],
    }

    dump("hazine.json", {
        "updated": mtime(fp),
        "ozet_html": ozet,
        "son": {"tarih": L_t.strftime("%d.%m.%Y"), "ytd_satis": ytd_satis,
                "ytd_ihale": int(len(ytd)), "faiz3": faiz3, "yil": cy},
        "aylik": {
            "ay": [t.strftime("%Y-%m-%d") for t in aylik.index],
            "satis": [round(float(v), 2) for v in aylik["satis"]],
            "faiz": [None if pd.isna(v) else round(float(v), 2) for v in aylik["faiz"]],
            "bid_cover": [None if pd.isna(v) else round(float(v), 2) for v in aylik["bid_cover"]],
        },
        "yillik_tur": {
            "yil": [str(int(y)) for y in piv.index],
            "turler": [{"ad": c, "deger": [round(float(v), 1) for v in piv[c]]} for c in piv.columns],
        },
        "ihaleler": ihaleler,
    })


def build_tcmb_alim():
    fp = BASE / "tcmb dogrudan alım" / "tcmb_dogrudan_alim.xlsx"
    d = pd.read_excel(fp, sheet_name="Doğrudan Alım İşlemleri")
    d["İşlem Tarihi"] = pd.to_datetime(d["İşlem Tarihi"], errors="coerce")
    d["Valör"] = pd.to_datetime(d["Valör"], errors="coerce")
    d["Vade"] = pd.to_datetime(d["Vade"], errors="coerce")
    d = d.dropna(subset=["İşlem Tarihi"]).sort_values("İşlem Tarihi").reset_index(drop=True)

    L_t = d["İşlem Tarihi"].max()
    cy = int(L_t.year)
    ytd = d[d["İşlem Tarihi"].dt.year == cy]
    ytd_alim = float(ytd["Kazanan Tutar (Nominal)"].sum()) / 1e6   # Bin TL -> Milyar TL
    son3ay = d[d["İşlem Tarihi"] >= L_t - pd.DateOffset(months=3)]
    faiz3 = _wavg(son3ay["Ortalama Bileşik Faiz"], son3ay["Kazanan Tutar (Nominal)"])
    ozet = (f"<b>{L_t.strftime('%d.%m.%Y')}</b> itibarıyla {cy} yılında doğrudan alım "
            f"ihalelerinde toplam <b>{ht(ytd_alim)} milyar TL</b> (nominal) işlem yapıldı "
            f"({len(ytd)} işlem). Son 3 ayın tutar ağırlıklı ortalama bileşik faizi "
            f"<b>%{ht(faiz3, 2)}</b>.")

    ayg = d.groupby(d["İşlem Tarihi"].dt.to_period("M"))
    aylik = pd.DataFrame({
        "alim": ayg["Kazanan Tutar (Nominal)"].sum() / 1e6,
        "islem": ayg["İhale No"].count(),
    })
    aylik["faiz"] = ayg.apply(lambda g: _wavg(g["Ortalama Bileşik Faiz"], g["Kazanan Tutar (Nominal)"]))
    aylik.index = aylik.index.to_timestamp()

    # Yıllık borçlanma (işlem yılı) vs itfa (vade yılı)
    borc = d.groupby(d["İşlem Tarihi"].dt.year)["Kazanan Tutar (Nominal)"].sum() / 1e6
    itfa = d.dropna(subset=["Vade"]).groupby(d["Vade"].dt.year)["Kazanan Tutar (Nominal)"].sum() / 1e6
    yillar = sorted(set(borc.index.astype(int)) | set(itfa.index.astype(int)))

    dump("tcmb_alim.json", {
        "updated": mtime(fp),
        "ozet_html": ozet,
        "son": {"tarih": L_t.strftime("%d.%m.%Y"), "ytd_alim": ytd_alim,
                "ytd_islem": int(len(ytd)), "faiz3": faiz3, "yil": cy},
        "aylik": {
            "ay": [t.strftime("%Y-%m-%d") for t in aylik.index],
            "alim": [round(float(v), 2) for v in aylik["alim"]],
            "faiz": [None if pd.isna(v) else round(float(v), 2) for v in aylik["faiz"]],
            "islem": [int(v) for v in aylik["islem"]],
        },
        "yillik": {
            "yil": [str(y) for y in yillar],
            "borclanma": [round(float(borc.get(y, 0.0)), 1) for y in yillar],
            "itfa": [round(float(itfa.get(y, 0.0)), 1) for y in yillar],
        },
        # İşlem bazlı kayıtlar (sayfadaki filtreli analizlerin ham verisi).
        # Birimler: tutarlar Bin TL, faiz %, vade gün (valörden itfaya).
        "islemler": _alim_islemler(d),
    })


def _alim_islemler(d):
    YONTEM = {"GELENEKSEL": "Geleneksel", "PYGELENEKSEL": "PY Geleneksel",
              "MIKTAR": "Miktar", "PY MIKTAR": "PY Miktar"}
    vg = (d["Vade"] - d["Valör"]).dt.days

    def num(s, r=0):
        return [None if pd.isna(v) else round(float(v), r) for v in s]

    return {
        "t": [x.strftime("%Y-%m-%d") for x in d["İşlem Tarihi"]],
        "itfa": [None if pd.isna(x) else x.strftime("%Y-%m-%d") for x in d["Vade"]],
        "vg": num(vg),
        "nom": num(d["Kazanan Tutar (Nominal)"]),
        "net": num(d["Kazanan Tutar (Net)"]),
        "teklif": num(d["Teklif Tutarı (Nominal)"]),
        "faiz": num(d["Ortalama Bileşik Faiz"], 2),
        "isin": [None if pd.isna(x) else str(x) for x in d["Tanım (ISIN)"]],
        "yontem": [YONTEM.get(str(x).strip(), str(x)) for x in d["Yöntem"]],
    }


def build_bddk():
    import bddk_analiz as ba
    tl_b, usd_b, kaynak = ba.load_latest(BASE / "bddk_data")
    if tl_b is None:
        raise RuntimeError("bddk_data içinde TL/USD Excel yok")
    t1, t2, son, onceki = ba.hesapla(tl_b, usd_b)

    def g(rows, lbl):
        return next((r for r in rows if r["label"] == lbl), {})

    def pp(v):
        return "—" if v is None else f"{v:+.1f}%".replace(".", ",")

    kr, mv = g(t1, "Toplam Krediler (TL)"), g(t2, "Toplam Mevduat (TL Cinsi)")
    mk = g(t1, "Toplam Menkul Değerler")
    ozet = (f"<b>{son.strftime('%d.%m.%Y')}</b> haftası: Toplam krediler (TL) haftalık "
            f"<b>{pp(kr.get('hafta'))}</b> (YtD {pp(kr.get('ytd'))}, yıllık {pp(kr.get('yillik'))}); "
            f"toplam mevduat <b>{pp(mv.get('hafta'))}</b> (YtD {pp(mv.get('ytd'))}, "
            f"yıllık {pp(mv.get('yillik'))}); menkul değerler {pp(mk.get('hafta'))}.")

    dump("bddk.json", {
        "updated": mtime(BASE / "bddk_data" / kaynak),
        "son": son.strftime("%d.%m.%Y"),
        "onceki": onceki.strftime("%d.%m.%Y") if onceki is not None else "",
        "ozet_html": ozet,
        "tablo1": t1,
        "tablo2": t2,
        "olcek": ba.OLCEK,
    })


# ──────────────────────────────────────────────────────────────
# Ana sayfa kartları (dashboard.py home_summaries ile aynı mantık)
# ──────────────────────────────────────────────────────────────

def build_home():
    cards = []

    def add(icon, title, html, link=None):
        cards.append({"icon": icon, "title": title, "html": html, "link": link})

    try:
        g = pd.read_excel(BASE / "enflasyon" / "enflasyon.xlsx", sheet_name="Genel")
        g["tarih"] = pd.to_datetime(g["tarih"]); L = g.iloc[-1]
        d_yil = float(L["yillik"] - g.iloc[-2]["yillik"])
        yon = "geriledi" if d_yil < 0 else "yükseldi"
        trend = "dezenflasyon sürüyor" if d_yil < 0 else "enflasyon yeniden hızlandı"
        avg3 = float(g["aylik"].tail(3).mean())
        add("📈", "TÜFE Enflasyon",
            f"{AY[L['tarih'].month]} {L['tarih'].year} itibarıyla yıllık enflasyon <b>%{ht(L['yillik'], 2)}</b>, "
            f"aylık <b>%{ht(L['aylik'], 2)}</b>; yılbaşından beri %{ht(L['ytd'], 2)}. "
            f"Yıllık oran önceki aya göre <b>{ht(abs(d_yil), 2)} puan {yon}</b> — {trend}; "
            f"son 3 ayın ortalama aylık artışı %{ht(avg3, 2)}.", "enflasyon.html")
    except Exception:
        pass
    try:
        b = pd.read_excel(BASE / "butce" / "butce.xlsx", sheet_name="Aylik")
        b["tarih"] = pd.to_datetime(b["tarih"]); b = b.sort_values("tarih"); L = b.iloc[-1]
        cy, cm = int(L["yil"]), int(L["ay"])
        ytd = b[(b.yil == cy) & (b.ay <= cm)]["denge"].sum()
        ytd_prev = b[(b.yil == cy - 1) & (b.ay <= cm)]["denge"].sum()
        yon = "açık" if L["denge"] < 0 else "fazla"
        yon_ytd = "açık" if ytd < 0 else "fazla"
        ek = ""
        if ytd_prev:
            pct = (abs(ytd) - abs(ytd_prev)) / abs(ytd_prev) * 100
            yon2 = "genişledi" if abs(ytd) > abs(ytd_prev) else "daraldı"
            ek = (f" Açık geçen yılın aynı dönemine ({ht(abs(ytd_prev) / 1000)} milyar TL) göre "
                  f"<b>%{ht(abs(pct), 0)} {yon2}</b>.")
        add("🏛️", "Bütçe Dengesi",
            f"{AY[cm]} {cy} ayında merkezi yönetim bütçesi <b>{ht(abs(L['denge']) / 1000)} milyar TL {yon}</b> verdi; "
            f"yılbaşından beri kümülatif {yon_ytd} <b>{ht(abs(ytd) / 1000)} milyar TL</b>.{ek}", "butce.html")
    except Exception:
        pass
    try:
        nk = pd.read_excel(BASE / "hazine nakit" / "nakit.xlsx", sheet_name="Aylik")
        nk["tarih"] = pd.to_datetime(nk["tarih"]); nk = nk.sort_values("tarih"); L = nk.iloc[-1]
        cy, cm = int(L["yil"]), int(L["ay"])
        ytd = nk[(nk.yil == cy) & (nk.ay <= cm)]["nakit_denge"].sum()
        ytd_prev = nk[(nk.yil == cy - 1) & (nk.ay <= cm)]["nakit_denge"].sum()
        ib = nk[(nk.yil == cy) & (nk.ay <= cm)]["ic_borclanma_net"].sum()
        yon = "açık" if L["nakit_denge"] < 0 else "fazla"
        yon_ytd = "açık" if ytd < 0 else "fazla"
        ek = ""
        if ytd_prev:
            pct = (abs(ytd) - abs(ytd_prev)) / abs(ytd_prev) * 100
            yon2 = "daha yüksek" if abs(ytd) > abs(ytd_prev) else "daha düşük"
            ek = (f" Bu açık geçen yılın aynı dönemine ({ht(abs(ytd_prev) / 1000)} milyar TL) göre "
                  f"<b>%{ht(abs(pct), 0)} {yon2}</b>; ağırlıkla iç borçlanmayla finanse edildi "
                  f"(net {ht(ib / 1000)} milyar TL).")
        add("🪙", "Hazine Nakit Gerçekleşmeleri",
            f"{AY[cm]} {cy} ayında Hazine nakit dengesi <b>{ht(abs(L['nakit_denge']) / 1000)} milyar TL {yon}</b> verdi; "
            f"yılbaşından beri kümülatif {yon_ytd} <b>{ht(abs(ytd) / 1000)} milyar TL</b>.{ek}", "nakit.html")
    except Exception:
        pass
    try:
        dh = pd.read_excel(BASE / "yabanci para hareketi" / "dth.xlsx", sheet_name="Haftalik")
        dh["tarih"] = pd.to_datetime(dh["tarih"]); dh = dh.sort_values("tarih"); L = dh.iloc[-1]
        yon = "arttı" if L["yerlesik_toplam"] >= 0 else "azaldı"
        s4 = float(dh["yerlesik_toplam"].tail(4).sum())
        yflow = float(dh[dh["tarih"].dt.year == int(L["tarih"].year)]["yerlesik_toplam"].sum())
        w4 = "artış" if s4 >= 0 else "azalış"
        wy = "artış (dolarizasyon)" if yflow >= 0 else "azalış (de-dolarizasyon)"
        add("💱", "Yabancı Para Hareketi",
            f"{L['tarih'].strftime('%d.%m.%Y')} haftasında yerleşiklerin YP mevduatı (parite düzeltilmiş) "
            f"<b>{ht(abs(L['yerlesik_toplam']) / 1000)} milyar USD</b> {yon} "
            f"(tüzel {ht(L['tuzel_kisiler'] / 1000, 1, True)}, gerçek {ht(L['gercek_kisiler'] / 1000, 1, True)} milyar). "
            f"Son 4 haftada kümülatif <b>{ht(abs(s4) / 1000)} milyar USD {w4}</b>; "
            f"yılbaşından beri {ht(abs(yflow) / 1000)} milyar USD {wy}.", "dth.html")
    except Exception:
        pass
    try:
        r = pd.read_excel(BASE / "net rezerv" / "net_rezerv.xlsx")
        r["tarih"] = pd.to_datetime(r["tarih"]); r = r.sort_values("tarih"); L = r.iloc[-1]
        nrc = "net_rezerv_swap_haric"
        cur = float(L[nrc])
        m1 = r[r["tarih"] <= L["tarih"] - pd.Timedelta(days=30)]
        ys = r[r["tarih"] >= pd.Timestamp(L["tarih"].year, 1, 1)]
        ek = ""
        if len(m1) and len(ys):
            d1 = (cur - float(m1.iloc[-1][nrc])) / 1000
            dy = (cur - float(ys.iloc[0][nrc])) / 1000
            w1 = "arttı" if d1 >= 0 else "azaldı"
            wy = "artış" if dy >= 0 else "azalış"
            ek = f" Son bir ayda <b>{ht(abs(d1))} milyar USD {w1}</b>; yıl başından beri {ht(abs(dy))} milyar USD {wy}."
        add("💵", "TCMB Net Rezerv",
            f"{L['tarih'].strftime('%d.%m.%Y')} itibarıyla net rezerv (swap hariç) "
            f"<b>{ht(cur / 1000)} milyar USD</b>, brüt dış varlıklar {ht(L['dis_varliklar'] / 1000)} milyar USD.{ek}", "net-rezerv.html")
    except Exception:
        pass
    try:
        c = pd.read_excel(BASE / "cari acik" / "cari_acik_son.xlsx")
        ccol = [x for x in c.columns if "Cari" in str(x)][0]
        L = c.iloc[-1]
        ek = ""
        vals = c[ccol].astype(float).tolist()
        if len(vals) >= 8:
            last4, prev4 = sum(vals[-4:]), sum(vals[-8:-4])
            kel = "açık" if last4 < 0 else "fazla"
            yon2 = "genişledi" if abs(last4) > abs(prev4) else "daraldı"
            ek = (f" Son dört çeyreğin (12 aylık) toplamı <b>{ht(abs(last4) / 1000)} milyar USD {kel}</b>; "
                  f"bir yıl öncesine göre {yon2}.")
        add("🌍", "Cari Denge",
            f"Son dönem ({L['Tarih']}) cari işlemler dengesi <b>{ht(L[ccol], 0)} milyon USD</b>.{ek}", "cari.html")
    except Exception:
        pass
    try:
        ka = pd.read_excel(BASE / "kredi mevduat" / "kredi_mevduat.xlsx", sheet_name="Kredi_Akim")
        ka["tarih"] = pd.to_datetime(ka["tarih"]); ka = ka.sort_values("tarih"); L = ka.iloc[-1]
        ek = ""
        if len(ka) >= 5:
            P = ka.iloc[-5]
            di = float(L["İhtiyaç Kredisi"] - P["İhtiyaç Kredisi"])
            dk = float(L["Konut Kredisi"] - P["Konut Kredisi"])
            wi = "geriledi" if di < 0 else "yükseldi"
            wk = "yükseldi" if dk > 0 else "geriledi"
            ek = (f" Son 4 haftada ihtiyaç kredisi faizi <b>{ht(abs(di), 2)} puan {wi}</b>, "
                  f"konut {ht(abs(dk), 2)} puan {wk}.")
        add("🏦", "Kredi Faizleri",
            f"Yeni kredi faizleri ({L['tarih'].strftime('%d.%m.%Y')}): İhtiyaç <b>%{ht(L.get('İhtiyaç Kredisi'), 2)}</b>, "
            f"Konut %{ht(L.get('Konut Kredisi'), 2)}, Ticari %{ht(L.get('Ticari Krediler'), 2)}.{ek}", "kredi.html")
    except Exception:
        pass
    try:
        ma = pd.read_excel(BASE / "kredi mevduat" / "kredi_mevduat.xlsx", sheet_name="Mevduat_Akim")
        ma["tarih"] = pd.to_datetime(ma["tarih"]); ma = ma.sort_values("tarih"); L = ma.iloc[-1]
        ek = ""
        if len(ma) >= 5:
            dt_ = float(L["Toplam"] - ma.iloc[-5]["Toplam"])
            if abs(dt_) < 0.10:
                ek = " Son 4 haftada büyük ölçüde <b>yatay</b> seyretti."
            else:
                w = "yükseldi" if dt_ > 0 else "geriledi"
                ek = f" Son 4 haftada toplam mevduat faizi <b>{ht(abs(dt_), 2)} puan {w}</b>."
        add("💰", "Mevduat Faizleri",
            f"TL mevduat faizi toplam <b>%{ht(L.get('Toplam'), 2)}</b>; 3 ay %{ht(L.get('3 Aya Kadar Vadeli'), 2)}, "
            f"1 yıl %{ht(L.get('1 Yıla Kadar Vadeli'), 2)} ({L['tarih'].strftime('%d.%m.%Y')}).{ek}", "mevduat.html")
    except Exception:
        pass
    try:
        import bddk_analiz as ba
        tl_b, usd_b, _ = ba.load_latest(BASE / "bddk_data")
        if tl_b is not None:
            t1, t2, son, _ = ba.hesapla(tl_b, usd_b)

            def g(rows, lbl):
                return next((r for r in rows if r["label"] == lbl), {})

            def pp(v):
                return "—" if v is None else f"{v:+.1f}%".replace(".", ",")

            kr, mv = g(t1, "Toplam Krediler (TL)"), g(t2, "Toplam Mevduat (TL Cinsi)")
            tlm, ypm = g(t2, "TL Mevduat"), g(t2, "YP Mevduat (USD)")
            add("📑", "BDDK Bankacılık",
                f"{son.strftime('%d.%m.%Y')} haftası: toplam krediler (TL) haftalık <b>{pp(kr.get('hafta'))}</b> "
                f"(yıllık {pp(kr.get('yillik'))}), toplam mevduat <b>{pp(mv.get('hafta'))}</b> "
                f"(yıllık {pp(mv.get('yillik'))}). TL mevduat {pp(tlm.get('hafta'))}, "
                f"YP mevduat (USD) {pp(ypm.get('hafta'))}.", "bddk.html")
    except Exception:
        pass
    try:
        fp = BASE / "hazine ihale " / "hazine_ihale_verileri.xlsx"
        hz = pd.read_excel(fp, sheet_name="Tüm İhaleler", header=[0, 1])
        hz.columns = [" / ".join(str(x) for x in c) for c in hz.columns]
        cv = "Genel Bilgiler / Valör Tarihi"
        hz[cv] = _hazine_tarih(hz[cv])
        hz = hz.dropna(subset=[cv])
        L_t = hz[cv].max(); cy = int(L_t.year)
        ytd = hz[hz[cv].dt.year == cy]
        satis = float(ytd["Toplam Satış / Net (Bin TL)"].sum()) / 1e6
        s3 = hz[hz[cv] >= L_t - pd.DateOffset(months=3)]
        f3 = _wavg(s3["Kabul Edilen Faiz (%) / Ort. Yıllık Bileşik"], s3["Toplam Satış / Nominal (Bin TL)"])
        add("🏦", "Hazine İhaleleri",
            f"{cy} yılında iç borçlanma ihalelerinde toplam <b>{ht(satis)} milyar TL</b> (net) satış "
            f"({len(ytd)} ihale, son: {L_t.strftime('%d.%m.%Y')}). Son 3 ayın satış ağırlıklı "
            f"ortalama bileşik faizi <b>%{ht(f3, 2)}</b>.", "hazine.html")
    except Exception:
        pass
    try:
        fp = BASE / "tcmb dogrudan alım" / "tcmb_dogrudan_alim.xlsx"
        ta = pd.read_excel(fp, sheet_name="Doğrudan Alım İşlemleri")
        ta["İşlem Tarihi"] = pd.to_datetime(ta["İşlem Tarihi"], errors="coerce")
        ta = ta.dropna(subset=["İşlem Tarihi"])
        L_t = ta["İşlem Tarihi"].max(); cy = int(L_t.year)
        ytd = ta[ta["İşlem Tarihi"].dt.year == cy]
        alim = float(ytd["Kazanan Tutar (Nominal)"].sum()) / 1e6
        s3 = ta[ta["İşlem Tarihi"] >= L_t - pd.DateOffset(months=3)]
        f3 = _wavg(s3["Ortalama Bileşik Faiz"], s3["Kazanan Tutar (Nominal)"])
        add("🎯", "TCMB Doğrudan Alım",
            f"{cy} yılında doğrudan alım ihalelerinde toplam <b>{ht(alim)} milyar TL</b> (nominal) "
            f"işlem ({len(ytd)} işlem, son: {L_t.strftime('%d.%m.%Y')}). Son 3 ayın ortalama "
            f"bileşik faizi <b>%{ht(f3, 2)}</b>.", "tcmb-alim.html")
    except Exception:
        pass
    try:
        td = BASE / "tcmb haftalık stok" / "output"

        def lv(n):
            fp = td / f"raw_{n}.csv"
            if not fp.exists():
                return None, None
            d = pd.read_csv(fp)
            return (float(d.iloc[-1]["value"]), d.iloc[-1]["date"]) if len(d) else (None, None)

        hs, ld = lv("Hisse_Stok"); ds, _ = lv("DIBS_Stok")
        if hs is not None or ds is not None:
            stok = (hs or 0) + (ds or 0)
            base = (f"{ld} itibarıyla yurt dışı yerleşiklerin Türkiye menkul kıymet stoku "
                    f"<b>{ht(stok / 1000)} milyar USD</b> (Hisse {ht((hs or 0) / 1000)}, DİBS {ht((ds or 0) / 1000)} milyar).")
            ek = ""
            try:
                hx = pd.read_excel(td / "hareket.xlsx", sheet_name="Haftalik")
                hx["tarih"] = pd.to_datetime(hx["tarih"]); hx = hx.sort_values("tarih")
                hL = hx.iloc[-1]
                s4h = float(hx["toplam"].tail(4).sum())
                hy = hx[hx["tarih"].dt.year == int(hL["tarih"].year)]
                yflow = float(hy["toplam"].sum())
                isim = {"hisse": "Hisse", "dibs_kesin": "DİBS kesin", "dibs_dolayli": "DİBS dolaylı",
                        "ost": "ÖST", "eurobond": "Eurobond"}
                ycomp = {k: float(hy[k].sum()) for k in isim}
                lider = max(ycomp, key=lambda k: ycomp[k])
                dibs_hafta = float(hL[["dibs_kesin", "dibs_dolayli"]].sum())
                ek = (f" Bu hafta toplam net yabancı hareketi <b>{ht(hL['toplam'] / 1000, 1, True)} milyar USD</b> "
                      f"(Hisse {ht(hL['hisse'], 0, True)}, DİBS {ht(dibs_hafta, 0, True)}, "
                      f"ÖST {ht(hL['ost'], 0, True)}, Eurobond {ht(hL['eurobond'], 0, True)} milyon); "
                      f"son 4 haftada <b>{ht(s4h / 1000, 1, True)} milyar USD</b>. "
                      f"Yılbaşından beri {ht(yflow / 1000, 1, True)} milyar USD giriş — en büyük katkı "
                      f"<b>{isim[lider]} ({ht(ycomp[lider] / 1000, 1, True)} milyar)</b>.")
            except Exception:
                pass
            add("📊", "Yabancı Menkul Kıymet Yatırımı", base + ek, "tcmb-stok.html")
    except Exception:
        pass

    dump("home.json", {
        "updated": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "cards": cards,
    })


def main():
    print("Site verileri dışa aktarılıyor -> site/data/")
    ok, fail = 0, 0
    for name, fn in [("home", build_home), ("tcmb_stok", build_tcmb_stok),
                     ("dth", build_dth), ("enflasyon", build_enflasyon),
                     ("butce", build_butce), ("nakit", build_nakit),
                     ("rezerv", build_rezerv), ("kredi", build_kredi),
                     ("mevduat", build_mevduat), ("cari", build_cari),
                     ("bddk", build_bddk), ("hazine", build_hazine),
                     ("tcmb_alim", build_tcmb_alim)]:
        try:
            fn()
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ✗ {name}: {e}")
    print(f"Bitti: {ok} paket yazıldı" + (f", {fail} hata" if fail else ""))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
