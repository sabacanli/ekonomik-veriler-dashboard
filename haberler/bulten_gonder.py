#!/usr/bin/env python3
"""Finans Gündemi e-posta bülteni — günün seçkisini (site/data/haber/<gün>.json) e-postaya çevirip gönderir.

Gönderim Resend API'si üzerinden yapılır. Ortam değişkenleri (GitHub Actions secret/variable):
  RESEND_API_KEY   — Resend API anahtarı (secret)
  BULTEN_ALICILAR  — alıcılar; virgül, noktalı virgül veya satır sonuyla ayrılmış (secret)
  BULTEN_YANIT     — isteğe bağlı yanıt adresi; alan adında posta kutusu olmadığından önerilir (secret)
  BULTEN_GONDEREN  — gönderen; varsayılan "Ekordion Gündem <bulten@ekordion.com.tr>"

GİZLİLİK: depo ve Actions logları herkese açıktır — bu script alıcı adreslerini ASLA yazdırmaz;
hata çıktıları da adres içerebileceğinden yalnız durum kodu ve hata türü loglanır.
Her alıcıya ayrı e-posta gider (alıcılar birbirini görmez). Idempotency-Key = gün + alıcı özeti:
aynı gün ikinci koşuda Resend aynı alıcıya ikinci kez göndermez.

Kullanım:
  python haberler/bulten_gonder.py --mod test      # yalnız listedeki İLK alıcıya
  python haberler/bulten_gonder.py --tur haftalik  # Pazar "Haftaya Bakış" bülteni (hafta_ozeti.py çıktısı)
  python haberler/bulten_gonder.py --mod evet      # tüm listeye
  python haberler/bulten_gonder.py --kuru out.html # göndermeden HTML önizleme yaz
  python haberler/bulten_gonder.py --denetle       # göndermeden alıcı listesini denetle (adres yazdırmaz)
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
HABER_DIR = BASE / "site" / "data" / "haber"
TR = dt.timezone(dt.timedelta(hours=3))
SITE = "https://ekordion.com.tr/gundem.html"
KOK = "https://ekordion.com.tr/"
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
         "Kasım", "Aralık"]
KATEGORI_BASINA = 6       # e-postada kategori başına en çok haber; tamamı sitede

esc = lambda s: html.escape(str(s or ""), quote=True)
GUN_KISA = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


def trn(v, ond=2, isaret=False):
    """Türkçe sayı biçimi: 1.234,56 (isaret=True → +/−)."""
    if v is None:
        return "—"
    s = f"{v:+,.{ond}f}" if isaret else f"{v:,.{ond}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def gun_kisa(t):
    d = dt.date.fromisoformat(t)
    return f"{GUN_KISA[d.weekday()]} {d.day:02d}.{d.month:02d}"


def takvim_satir_html(o, tarihli=False):
    on = (gun_kisa(o["tarih"]) + " ") if tarihli else ""
    saat = o.get("saat") or "—"
    b = esc(o["baslik"])
    if o.get("onem", 1) >= 3:
        b = f"<b>{b}</b>"
    donem = f' <span style="color:#8A93A6;">— {esc(o["donem"])}</span>' if o.get("donem") else ""
    return (f'<div style="padding:6px 0;border-bottom:1px solid #EEF1F6;font-size:13.5px;line-height:1.5;color:#1A2233;">'
            f'<span style="color:#8A93A6;font-size:12.5px;">{esc(on)}{esc(saat)} · {esc(o["kurum"])}</span> · {b}{donem}</div>')


def guvenli_link(u):
    return esc(u) if re.match(r"^https?://", u or "", re.I) else SITE


def tarih_yazi(gun):
    d = dt.date.fromisoformat(gun)
    return f"{d.day} {AYLAR[d.month - 1]} {d.year} {GUNLER[d.weekday()]}"


def html_yap(D):
    gun_yazi = tarih_yazi(D["tarih"])
    toplam = D["sayilar"]["secilen"]
    on_baslik = esc((D.get("ozet") or ["Günün finans gündemi"])[0])[:140]
    P = []
    P.append(f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Finans Gündemi</title></head>
<body style="margin:0;padding:0;background:#F3F5F9;">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;color:#F3F5F9;">{on_baslik}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F3F5F9;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:100%;max-width:640px;background:#FFFFFF;border-radius:10px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;">
<tr><td style="background:#0B0E14;padding:22px 28px;">
  <div style="color:#FF9E1B;font-size:20px;font-weight:700;letter-spacing:.2px;">Ekordion · Finans Gündemi</div>
  <div style="color:#9AA4B2;font-size:13px;margin-top:5px;">{esc(gun_yazi)} · son {D['pencere_saat']} saat · {D['sayilar']['kaynak']} kaynaktan {toplam} haber</div>
</td></tr>
<tr><td style="padding:24px 28px 8px;">""")
    if D.get("ozet"):
        P.append('<div style="font-size:16px;font-weight:700;color:#1A2233;margin:0 0 10px;">Günün Öne Çıkanları</div>'
                 '<ol style="margin:0 0 6px;padding-left:20px;color:#1A2233;font-size:14.5px;line-height:1.6;">')
        P += [f'<li style="margin-bottom:8px;">{esc(m)}</li>' for m in D["ozet"]]
        P.append("</ol>")
    PZ = D.get("piyasa")
    if PZ and PZ.get("satirlar"):
        P.append('<div style="font-size:16px;font-weight:700;color:#1A2233;margin:18px 0 6px;">Günün Rakamları</div>'
                 '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13.5px;">')
        for s in PZ["satirlar"]:
            if s.get("tur") == "faiz":
                dg = "—" if s.get("degisim") is None else trn(s["degisim"], 2, True) + " puan"
                yon = s.get("degisim")
            else:
                dg = "—" if s.get("degisim_pct") is None else trn(s["degisim_pct"], 2, True) + "%"
                yon = s.get("degisim_pct")
            renk = "#8A93A6" if not yon else ("#2E7D5B" if yon > 0 else "#C0392B")
            birim = f' <span style="color:#8A93A6;font-size:12px;">{esc(s["birim"])}</span>' if s.get("birim") else ""
            P.append(f'<tr><td style="padding:6px 0;border-bottom:1px solid #EEF1F6;color:#1A2233;">{esc(s["ad"])}</td>'
                     f'<td align="right" style="padding:6px 0;border-bottom:1px solid #EEF1F6;color:#1A2233;font-weight:700;white-space:nowrap;">{trn(s["deger"], s.get("ondalik", 2))}{birim}</td>'
                     f'<td align="right" style="padding:6px 0 6px 14px;border-bottom:1px solid #EEF1F6;color:{renk};white-space:nowrap;width:84px;">{dg}</td></tr>')
        P.append('</table><div style="font-size:11.5px;color:#8A93A6;margin:6px 0 0;">Sabah itibarıyla son değerler; tahvil faizleri önceki gün kapanışı, değişim bir önceki kapanışa göre. '
                 'Kaynak: TradingView, TCMB EVDS, Yahoo Finance.</div>')
    T = D.get("takvim")
    if T is not None:
        P.append('<div style="font-size:16px;font-weight:700;color:#1A2233;margin:18px 0 6px;">Bugün Takvimde</div>')
        if T.get("bugun"):
            P += [takvim_satir_html(o) for o in T["bugun"]]
        else:
            P.append('<div style="font-size:13.5px;color:#8A93A6;padding:4px 0;">Bugün takvimde önemli bir veri açıklaması yok.</div>')
        if dt.date.fromisoformat(D["tarih"]).weekday() == 0 and T.get("hafta"):
            P.append('<div style="font-size:13px;font-weight:700;color:#55627A;margin:12px 0 2px;">Haftanın kalanı</div>')
            P += [takvim_satir_html(o, tarihli=True) for o in T["hafta"]]
    if D.get("veriler"):
        P.append('<div style="font-size:16px;font-weight:700;color:#1A2233;margin:18px 0 2px;">Yeni Açıklanan Veriler</div>'
                 '<div style="font-size:12.5px;color:#8A93A6;margin:0 0 6px;">Son bültenden bu yana güncellenen Ekordion serileri — rakamlar sitedeki grafiklerle aynı</div>')
        for v in D["veriler"]:
            P.append(
                f'<div style="padding:8px 0;border-bottom:1px solid #EEF1F6;">'
                f'<a href="{KOK}{esc(v["link"])}" style="color:#1A2233;font-size:14.5px;font-weight:700;text-decoration:none;">'
                f'{esc(v.get("ikon", ""))} {esc(v["baslik"])}</a>'
                f'<div style="color:#55627A;font-size:13.5px;line-height:1.55;margin-top:3px;">{esc(v["ozet"])}</div></div>')
    for k in D["kategoriler"]:
        P.append(f'<div style="font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;'
                 f'color:#B86E00;border-bottom:2px solid #F1E3CC;padding:18px 0 6px;margin-bottom:4px;">'
                 f'{esc(k["ad"])}</div>')
        for h in k["haberler"][:KATEGORI_BASINA]:
            nokta = '<span style="color:#FF9E1B;">●</span> ' if h.get("onem", 0) >= 4 else ""
            diger = f' · +{len(h["diger"])} kaynak' if h.get("diger") else ""
            P.append(
                f'<div style="padding:10px 0;border-bottom:1px solid #EEF1F6;">'
                f'<a href="{guvenli_link(h["link"])}" style="color:#1A2233;font-size:15px;font-weight:700;'
                f'line-height:1.4;text-decoration:none;">{nokta}{esc(h["baslik"])}</a>'
                + (f'<div style="color:#55627A;font-size:13.5px;line-height:1.55;margin-top:4px;">{esc(h["ozet"])}</div>'
                   if h.get("ozet") else "")
                + f'<div style="color:#8A93A6;font-size:12px;margin-top:4px;">{esc(h["kaynak"])} · {esc(h["zaman"])}{diger}</div>'
                  f'</div>')
        kalan = len(k["haberler"]) - KATEGORI_BASINA
        if kalan > 0:
            P.append(f'<div style="font-size:12.5px;color:#8A93A6;padding:8px 0 0;">+{kalan} haber daha — '
                     f'<a href="{SITE}" style="color:#B86E00;">sitede</a></div>')
    P.append(f"""</td></tr>
<tr><td align="center" style="padding:20px 28px 26px;">
  <a href="{SITE}" style="display:inline-block;background:#FF9E1B;color:#0B0E14;font-size:14px;font-weight:700;text-decoration:none;padding:11px 22px;border-radius:7px;">Tüm gündemi sitede aç →</a>
</td></tr>
<tr><td style="background:#F8F9FC;padding:16px 28px;color:#8A93A6;font-size:11.5px;line-height:1.6;">
  Başlıklar ilgili yayıncılara aittir; bağlantılar haberin kaynağına gider. Seçki ve kısa özetler otomatik
  üretilir — yatırım tavsiyesi değildir. Veriler ve grafikler: <a href="https://ekordion.com.tr" style="color:#8A93A6;">ekordion.com.tr</a><br>
  Bu bülteni almak istemiyorsanız bu e-postayı yanıtlayarak bildirmeniz yeterli.
</td></tr>
</table></td></tr></table></body></html>""")
    return "".join(P)


def metin_yap(D):
    S = [f"EKORDION · FİNANS GÜNDEMİ — {tarih_yazi(D['tarih'])}", ""]
    if D.get("ozet"):
        S.append("GÜNÜN ÖNE ÇIKANLARI")
        S += [f"  {i}. {m}" for i, m in enumerate(D["ozet"], 1)]
        S.append("")
    PZ = D.get("piyasa")
    if PZ and PZ.get("satirlar"):
        S.append("GÜNÜN RAKAMLARI")
        for s in PZ["satirlar"]:
            dg = (trn(s["degisim"], 2, True) + " puan") if s.get("tur") == "faiz" and s.get("degisim") is not None else \
                 (trn(s["degisim_pct"], 2, True) + "%" if s.get("degisim_pct") is not None else "—")
            S.append(f"  {s['ad']}: {trn(s['deger'], s.get('ondalik', 2))} {s.get('birim', '')} ({dg})".rstrip())
        S.append("")
    T = D.get("takvim")
    if T is not None:
        S.append("BUGÜN TAKVİMDE")
        S += [f"  {o.get('saat') or '—'} · {o['kurum']} · {o['baslik']}" + (f" — {o['donem']}" if o.get("donem") else "")
              for o in T.get("bugun", [])] or ["  Bugün takvimde önemli bir veri açıklaması yok."]
        if dt.date.fromisoformat(D["tarih"]).weekday() == 0 and T.get("hafta"):
            S.append("  Haftanın kalanı:")
            S += [f"    {gun_kisa(o['tarih'])} {o.get('saat') or ''} · {o['kurum']} · {o['baslik']}" for o in T["hafta"]]
        S.append("")
    if D.get("veriler"):
        S.append("YENİ AÇIKLANAN VERİLER (Ekordion)")
        for v in D["veriler"]:
            S.append(f"  • {v['baslik']}: {v['ozet']}")
            S.append(f"    {KOK}{v['link']}")
        S.append("")
    for k in D["kategoriler"]:
        S.append(k["ad"].upper())
        for h in k["haberler"][:KATEGORI_BASINA]:
            S.append(f"  • {h['baslik']} ({h['kaynak']})")
            if h.get("ozet"):
                S.append(f"    {h['ozet']}")
            S.append(f"    {h['link']}")
        S.append("")
    S += [f"Tüm gündem: {SITE}", "",
          "Seçki ve özetler otomatik üretilir — yatırım tavsiyesi değildir.",
          "Bu bülteni almak istemiyorsanız bu e-postayı yanıtlayarak bildirmeniz yeterli."]
    return "\n".join(S)


def rakam_tablo_html(satirlar, haftalik):
    """Piyasa tablosu (e-posta): günlük → Son/Değişim; haftalık → Son/Hafta/Ay/Yılbaşı."""
    hucre = 'padding:6px 0 6px 12px;border-bottom:1px solid #EEF1F6;white-space:nowrap;text-align:right;'
    def renkli(v, metin):
        renk = "#8A93A6" if not v else ("#2E7D5B" if v > 0 else "#C0392B")
        return f'<td style="{hucre}color:{renk};">{metin}</td>'
    P = ['<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13.5px;">']
    if haftalik:
        P.append('<tr>' + ''.join(f'<th style="{hucre}color:#8A93A6;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;'
                                  f'{"text-align:left;padding-left:0;" if i == 0 else ""}">{b}</th>'
                                  for i, b in enumerate(["Gösterge", "Son", "Hafta", "Ay", "Yılbaşı"])) + '</tr>')
    for r in satirlar:
        faiz = r.get("tur") == "faiz"
        birim = f' <span style="color:#8A93A6;font-size:12px;">{esc(r["birim"])}</span>' if r.get("birim") else ""
        satir = (f'<tr><td style="padding:6px 0;border-bottom:1px solid #EEF1F6;color:#1A2233;">{esc(r["ad"])}</td>'
                 f'<td style="{hucre}color:#1A2233;font-weight:700;">{trn(r["deger"], r.get("ondalik", 2))}{birim}</td>')
        if haftalik:
            hp = r.get("hafta_puan") if faiz else None
            hafta = ("—" if hp is None else trn(hp, 2, True) + " p") if faiz else ("—" if r.get("hafta_pct") is None else trn(r["hafta_pct"], 2, True) + "%")
            satir += renkli(hp if faiz else r.get("hafta_pct"), hafta)
            satir += renkli(r.get("ay_pct"), "—" if r.get("ay_pct") is None else trn(r["ay_pct"], 1, True) + "%")
            satir += renkli(r.get("ytd_pct"), "—" if r.get("ytd_pct") is None else trn(r["ytd_pct"], 1, True) + "%")
        else:
            v = r.get("degisim") if faiz else r.get("degisim_pct")
            satir += renkli(v, "—" if v is None else (trn(v, 2, True) + (" puan" if faiz else "%")))
        P.append(satir + "</tr>")
    P.append("</table>")
    return "".join(P)


def veri_html(veriler, baslik, alt):
    P = [f'<div style="font-size:16px;font-weight:700;color:#1A2233;margin:18px 0 2px;">{baslik}</div>'
         f'<div style="font-size:12.5px;color:#8A93A6;margin:0 0 6px;">{alt}</div>']
    for v in veriler:
        P.append(f'<div style="padding:8px 0;border-bottom:1px solid #EEF1F6;">'
                 f'<a href="{KOK}{esc(v["link"])}" style="color:#1A2233;font-size:14.5px;font-weight:700;text-decoration:none;">'
                 f'{esc(v.get("ikon", ""))} {esc(v["baslik"])}</a>'
                 f'<div style="color:#55627A;font-size:13.5px;line-height:1.55;margin-top:3px;">{esc(v["ozet"])}</div></div>')
    return "".join(P)


def html_hafta(H):
    """Pazar 'Haftaya Bakış' e-postası."""
    P = [f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Haftaya Bakış</title></head>
<body style="margin:0;padding:0;background:#F3F5F9;">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;color:#F3F5F9;">{esc(H["baslik"])[:140]}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F3F5F9;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:100%;max-width:640px;background:#FFFFFF;border-radius:10px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;">
<tr><td style="background:#0B0E14;padding:22px 28px;">
  <div style="color:#FF9E1B;font-size:20px;font-weight:700;letter-spacing:.2px;">Ekordion · Haftaya Bakış</div>
  <div style="color:#9AA4B2;font-size:13px;margin-top:5px;">{esc(H["aralik"])} · geçen haftanın özeti ve gelecek hafta neler bekliyor</div>
</td></tr>
<tr><td style="padding:24px 28px 8px;">
<div style="font-size:19px;font-weight:700;color:#1A2233;line-height:1.35;margin:0 0 14px;">{esc(H["baslik"])}</div>
<div style="font-size:16px;font-weight:700;color:#1A2233;margin:0 0 8px;">Haftanın Özeti</div>
<ol style="margin:0 0 6px;padding-left:20px;color:#1A2233;font-size:14.5px;line-height:1.6;">"""]
    P += [f'<li style="margin-bottom:8px;">{esc(m)}</li>' for m in H["hafta_ozeti"]]
    P.append("</ol>")
    PZ = H.get("piyasa")
    if PZ and PZ.get("satirlar"):
        P.append('<div style="font-size:16px;font-weight:700;color:#1A2233;margin:18px 0 6px;">Piyasalarda Hafta</div>')
        P.append(rakam_tablo_html(PZ["satirlar"], True))
        if H.get("piyasa_yorumu"):
            P.append(f'<div style="font-size:13.5px;color:#55627A;line-height:1.55;margin:8px 0 0;">{esc(H["piyasa_yorumu"])}</div>')
        P.append('<div style="font-size:11.5px;color:#8A93A6;margin:6px 0 0;">Cuma kapanışı; faizlerde hafta sütunu puan, diğerleri yüzde değişim. Kaynak: TradingView, TCMB EVDS, Yahoo Finance.</div>')
    if H.get("veriler"):
        P.append(veri_html(H["veriler"], "Bu Hafta Açıklanan Veriler", "Hafta içinde güncellenen Ekordion serileri — rakamlar sitedeki grafiklerle aynı"))
    P.append(f'<div style="font-size:16px;font-weight:700;color:#1A2233;margin:18px 0 2px;">Gelecek Hafta: {esc(H["sonraki_aralik"])}</div>')
    if H.get("gelecek_hafta"):
        P.append('<ul style="margin:6px 0 10px;padding-left:20px;color:#1A2233;font-size:14px;line-height:1.6;">'
                 + "".join(f'<li style="margin-bottom:6px;">{esc(m)}</li>' for m in H["gelecek_hafta"]) + "</ul>")
    gun_onceki = None
    for o in H.get("takvim", []):
        if o["tarih"] != gun_onceki:
            d = dt.date.fromisoformat(o["tarih"])
            P.append(f'<div style="font-size:12.5px;font-weight:700;color:#B86E00;letter-spacing:.5px;text-transform:uppercase;margin:10px 0 2px;">{GUNLER[d.weekday()]} {d.day:02d}.{d.month:02d}</div>')
            gun_onceki = o["tarih"]
        P.append(takvim_satir_html(o))
    if H.get("one_cikan"):
        P.append('<div style="font-size:16px;font-weight:700;color:#1A2233;margin:20px 0 4px;">Haftanın Öne Çıkan Haberleri</div>')
        for h in H["one_cikan"][:8]:
            P.append(f'<div style="padding:8px 0;border-bottom:1px solid #EEF1F6;">'
                     f'<a href="{guvenli_link(h["link"])}" style="color:#1A2233;font-size:14.5px;font-weight:700;line-height:1.4;text-decoration:none;">{esc(h["baslik"])}</a>'
                     + (f'<div style="color:#55627A;font-size:13.5px;line-height:1.55;margin-top:3px;">{esc(h["ozet"])}</div>' if h.get("ozet") else "")
                     + f'<div style="color:#8A93A6;font-size:12px;margin-top:3px;">{esc(h["kaynak"])} · {h["gun"][8:]}.{h["gun"][5:7]} · {esc(h["kategori"])}</div></div>')
    P.append(f"""</td></tr>
<tr><td align="center" style="padding:20px 28px 26px;">
  <a href="{SITE}?hafta={esc(H["hafta"])}" style="display:inline-block;background:#FF9E1B;color:#0B0E14;font-size:14px;font-weight:700;text-decoration:none;padding:11px 22px;border-radius:7px;">Haftaya Bakış'ı sitede aç →</a>
</td></tr>
<tr><td style="background:#F8F9FC;padding:16px 28px;color:#8A93A6;font-size:11.5px;line-height:1.6;">
  Başlıklar ilgili yayıncılara aittir; bağlantılar haberin kaynağına gider. Özet ve yorumlar otomatik
  üretilir — yatırım tavsiyesi değildir. Veriler ve grafikler: <a href="https://ekordion.com.tr" style="color:#8A93A6;">ekordion.com.tr</a><br>
  Bu bülteni almak istemiyorsanız bu e-postayı yanıtlayarak bildirmeniz yeterli.
</td></tr>
</table></td></tr></table></body></html>""")
    return "".join(P)


def metin_hafta(H):
    S = [f"EKORDION · HAFTAYA BAKIŞ — {H['aralik']}", "", H["baslik"], "", "HAFTANIN ÖZETİ"]
    S += [f"  {i}. {m}" for i, m in enumerate(H["hafta_ozeti"], 1)]
    PZ = H.get("piyasa")
    if PZ and PZ.get("satirlar"):
        S += ["", "PİYASALARDA HAFTA (son · hafta · ay · yılbaşı)"]
        for r in PZ["satirlar"]:
            faiz = r.get("tur") == "faiz"
            hafta = (trn(r["hafta_puan"], 2, True) + " p") if faiz and r.get("hafta_puan") is not None else \
                    (trn(r["hafta_pct"], 2, True) + "%" if r.get("hafta_pct") is not None else "—")
            S.append(f"  {r['ad']}: {trn(r['deger'], r.get('ondalik', 2))} {r.get('birim', '')} · {hafta} · "
                     f"{'—' if r.get('ay_pct') is None else trn(r['ay_pct'], 1, True) + '%'} · "
                     f"{'—' if r.get('ytd_pct') is None else trn(r['ytd_pct'], 1, True) + '%'}".replace("  ·", " ·"))
        if H.get("piyasa_yorumu"):
            S += ["", f"  {H['piyasa_yorumu']}"]
    if H.get("veriler"):
        S += ["", "BU HAFTA AÇIKLANAN VERİLER (Ekordion)"]
        for v in H["veriler"]:
            S += [f"  • {v['baslik']}: {v['ozet']}", f"    {KOK}{v['link']}"]
    S += ["", f"GELECEK HAFTA: {H['sonraki_aralik']}"]
    S += [f"  • {m}" for m in H.get("gelecek_hafta", [])]
    gun_onceki = None
    for o in H.get("takvim", []):
        if o["tarih"] != gun_onceki:
            d = dt.date.fromisoformat(o["tarih"]); S.append(f"  {GUNLER[d.weekday()]} {d.day:02d}.{d.month:02d}"); gun_onceki = o["tarih"]
        S.append(f"    {o.get('saat') or '—'} · {o['kurum']} · {o['baslik']}" + (f" — {o['donem']}" if o.get("donem") else ""))
    if H.get("one_cikan"):
        S += ["", "HAFTANIN ÖNE ÇIKAN HABERLERİ"]
        for h in H["one_cikan"][:8]:
            S += [f"  • {h['baslik']} ({h['kaynak']}, {h['gun'][8:]}.{h['gun'][5:7]})", f"    {h['link']}"]
    S += ["", f"Sitede: {SITE}?hafta={H['hafta']}", "",
          "Özet ve yorumlar otomatik üretilir — yatırım tavsiyesi değildir.",
          "Bu bülteni almak istemiyorsanız bu e-postayı yanıtlayarak bildirmeniz yeterli."]
    return "\n".join(S)


def alicilari_oku():
    ham = [x.strip() for x in re.split(r"[,;\s]+", os.environ.get("BULTEN_ALICILAR", "")) if x.strip()]
    return ham


ADRES_DESENI = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")


def denetle():
    """Secret'lardaki alıcı listesini göndermeden denetler. Adresler ASLA yazdırılmaz — yalnız sıra
    numarası ve sayılar. Sonuç ayrıca GitHub 'notice' ek açıklaması olarak da verilir."""
    ham = alicilari_oku()
    gecerli = [x for x in ham if ADRES_DESENI.match(x)]
    hatali = [i for i, x in enumerate(ham, 1) if not ADRES_DESENI.match(x)]
    yinelenen = len(gecerli) - len({x.lower() for x in gecerli})
    yanit = os.environ.get("BULTEN_YANIT", "").strip()
    satirlar = [
        f"alıcı listesi: {len(ham)} öğe · biçimce geçerli {len(gecerli)} · hatalı {len(hatali)}"
        + (f" (sıra: {', '.join(map(str, hatali))})" if hatali else "") + f" · yinelenen {yinelenen}",
        "yanıt adresi (BULTEN_YANIT): " + ("tanımlı, biçimi geçerli" if ADRES_DESENI.match(yanit)
                                          else "tanımlı ama biçimi HATALI" if yanit else "tanımlı değil"),
        "Resend anahtarı (RESEND_API_KEY): " + ("tanımlı" if os.environ.get("RESEND_API_KEY", "").strip() else "TANIMLI DEĞİL"),
    ]
    for t in satirlar:
        print(t)
    print("::notice title=Bülten listesi::" + " | ".join(satirlar))
    if hatali or not gecerli:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", choices=["test", "evet"], default="test")
    ap.add_argument("--tur", choices=["gunluk", "haftalik"], default="gunluk", help="günlük gündem veya Pazar 'Haftaya Bakış'")
    ap.add_argument("--hafta", help="haftalık bülten için ISO hafta (ör. 2026-W39); varsayılan: içinde bulunulan hafta")
    ap.add_argument("--gun", default=dt.datetime.now(TR).strftime("%Y-%m-%d"))
    ap.add_argument("--kuru", metavar="DOSYA", help="göndermeden HTML önizlemeyi bu dosyaya yaz")
    ap.add_argument("--denetle", action="store_true", help="göndermeden alıcı listesini denetle")
    a = ap.parse_args()
    if a.denetle:
        denetle()
        return

    if a.tur == "haftalik":
        yil, w, _ = dt.datetime.now(TR).date().isocalendar()
        kimlik = a.hafta or f"{yil}-W{w:02d}"
        fp = HABER_DIR / f"hafta-{kimlik}.json"
        if not fp.exists():
            print(f"Bülten atlandı: {kimlik} için Haftaya Bakış verisi yok (hafta_ozeti.py çalışmamış).")
            return
        H = json.loads(fp.read_text(encoding="utf-8"))
        govde, duz = html_hafta(H), metin_hafta(H)
        konu = f"Haftaya Bakış · {H['aralik']}"
    else:
        kimlik = a.gun
        fp = HABER_DIR / f"{a.gun}.json"
        if not fp.exists():
            print(f"Bülten atlandı: {a.gun} için gündem verisi yok.")
            return
        D = json.loads(fp.read_text(encoding="utf-8"))
        govde, duz = html_yap(D), metin_yap(D)
        konu = f"Finans Gündemi · {tarih_yazi(a.gun)}"

    if a.kuru:
        Path(a.kuru).write_text(govde, encoding="utf-8")
        print(f"Önizleme yazıldı: {a.kuru} ({len(govde) // 1024} KB) · konu: {konu}")
        return

    anahtar = os.environ.get("RESEND_API_KEY", "").strip()
    alicilar = list(dict.fromkeys(x for x in alicilari_oku() if ADRES_DESENI.match(x)))
    if not anahtar or not alicilar:
        print("Bülten atlandı: RESEND_API_KEY ve/veya BULTEN_ALICILAR tanımlı değil.")
        return
    toplam = len(alicilar)
    if a.mod == "test":
        alicilar = alicilar[:1]
    gonderen = os.environ.get("BULTEN_GONDEREN", "").strip() or "Ekordion Gündem <bulten@ekordion.com.tr>"
    yanit = os.environ.get("BULTEN_YANIT", "").strip()

    print(f"Bülten gönderiliyor — mod: {a.mod} · gönderilecek alıcı: {len(alicilar)} (listede {toplam}) · konu: {konu}")
    tamam = atlanan = hata = 0
    for i, alici in enumerate(alicilar, 1):
        yuk = {"from": gonderen, "to": [alici], "subject": konu, "html": govde, "text": duz}
        if yanit:
            yuk["reply_to"] = yanit
        iz = hashlib.sha256(f"{kimlik}|{a.mod}|{alici.lower()}".encode()).hexdigest()[:32]
        try:
            r = requests.post("https://api.resend.com/emails", json=yuk, timeout=30,
                              headers={"Authorization": f"Bearer {anahtar}",
                                       "Idempotency-Key": f"gundem-{kimlik}-{iz}"})
            if r.status_code in (200, 201):
                tamam += 1
                print(f"  ✓ alıcı {i}: gönderildi")
            elif r.status_code == 409:
                atlanan += 1
                print(f"  ~ alıcı {i}: bugün zaten gönderilmiş (yinelenen istek atlandı)")
            else:
                hata += 1
                try:
                    tur = r.json().get("name") or r.json().get("error") or ""
                except Exception:
                    tur = ""
                print(f"  ✗ alıcı {i}: HTTP {r.status_code} {str(tur)[:60]}")   # yanıt gövdesi adres içerebilir: yazdırma
        except requests.RequestException as e:
            hata += 1
            print(f"  ✗ alıcı {i}: bağlantı hatası ({type(e).__name__})")
        time.sleep(0.6)   # Resend oran sınırı (saniyede ~2 istek)
    print(f"Bitti: {tamam} gönderildi · {atlanan} yinelenen atlandı · {hata} hata")
    if hata and not tamam and not atlanan:
        sys.exit(1)


if __name__ == "__main__":
    main()
