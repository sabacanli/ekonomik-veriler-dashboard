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
            f"yılbaşından beri kümülatif {yon_ytd} <b>{ht(abs(ytd) / 1000)} milyar TL</b>.{ek}")
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
            f"yılbaşından beri kümülatif {yon_ytd} <b>{ht(abs(ytd) / 1000)} milyar TL</b>.{ek}")
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
            f"<b>{ht(cur / 1000)} milyar USD</b>, brüt dış varlıklar {ht(L['dis_varliklar'] / 1000)} milyar USD.{ek}")
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
            f"Son dönem ({L['Tarih']}) cari işlemler dengesi <b>{ht(L[ccol], 0)} milyon USD</b>.{ek}")
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
            f"Konut %{ht(L.get('Konut Kredisi'), 2)}, Ticari %{ht(L.get('Ticari Krediler'), 2)}.{ek}")
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
            f"1 yıl %{ht(L.get('1 Yıla Kadar Vadeli'), 2)} ({L['tarih'].strftime('%d.%m.%Y')}).{ek}")
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
                     ("dth", build_dth), ("enflasyon", build_enflasyon)]:
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
