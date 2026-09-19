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
  python haberler/bulten_gonder.py --mod evet      # tüm listeye
  python haberler/bulten_gonder.py --kuru out.html # göndermeden HTML önizleme yaz
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
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
         "Kasım", "Aralık"]
KATEGORI_BASINA = 6       # e-postada kategori başına en çok haber; tamamı sitede

esc = lambda s: html.escape(str(s or ""), quote=True)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", choices=["test", "evet"], default="test")
    ap.add_argument("--gun", default=dt.datetime.now(TR).strftime("%Y-%m-%d"))
    ap.add_argument("--kuru", metavar="DOSYA", help="göndermeden HTML önizlemeyi bu dosyaya yaz")
    a = ap.parse_args()

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
    alicilar = [x.strip() for x in re.split(r"[,;\s]+", os.environ.get("BULTEN_ALICILAR", "")) if "@" in x]
    alicilar = list(dict.fromkeys(alicilar))
    if not anahtar or not alicilar:
        print("Bülten atlandı: RESEND_API_KEY ve/veya BULTEN_ALICILAR tanımlı değil.")
        return
    if a.mod == "test":
        alicilar = alicilar[:1]
    gonderen = os.environ.get("BULTEN_GONDEREN", "").strip() or "Ekordion Gündem <bulten@ekordion.com.tr>"
    yanit = os.environ.get("BULTEN_YANIT", "").strip()

    print(f"Bülten gönderiliyor — mod: {a.mod} · alıcı sayısı: {len(alicilar)} · konu: {konu}")
    tamam = atlanan = hata = 0
    for i, alici in enumerate(alicilar, 1):
        yuk = {"from": gonderen, "to": [alici], "subject": konu, "html": govde, "text": duz}
        if yanit:
            yuk["reply_to"] = yanit
        iz = hashlib.sha256(f"{a.gun}|{a.mod}|{alici.lower()}".encode()).hexdigest()[:32]
        try:
            r = requests.post("https://api.resend.com/emails", json=yuk, timeout=30,
                              headers={"Authorization": f"Bearer {anahtar}",
                                       "Idempotency-Key": f"gundem-{a.gun}-{iz}"})
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
