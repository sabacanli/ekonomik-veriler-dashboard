#!/usr/bin/env python3
"""Ekonomik takvim → site/data/takvim.json (bültenin "Bugün takvimde" ve Pazar "gelecek hafta" bölümleri).

Kaynaklar:
  1) takvim/sabit_takvim.json — elle derlenen yıllık takvim: TCMB PPK kararı/özeti, Enflasyon ve Finansal
     İstikrar Raporları, Fed FOMC, ECB, ABD TÜFE / istihdam / PCE / GSYH. Yıl sonunda resmî takvimlerden
     yenilenir (kaynak adresleri dosyanın başında). Saatler kendi dilimindedir, burada TR saatine çevrilir.
  2) TÜİK Ulusal Veri Yayımlama Takvimi — tüm kurumların (TÜİK, TCMB, HMB, BDDK, SPK…) resmî istatistik
     yayın tarih ve saatleri. Uç nokta: /Kurumsal/GetYillikHaberBulteniListesi?yil=YYYY&kurum=TUIK
     (kurum parametresi olmadan 500 döner). Başarılı çekim takvim/ulusal_<yıl>.json önbelleğine yazılır;
     ağ/uç nokta hatasında önbellek kullanılır. SECIM listesindeki bültenler alınır, gerisi elenir.
  3) Hazine iç borç ihraç takvimi — "hazine ihale /borclanma programi/program.json" içindeki "ihale_takvimi"
     (program_parse.py, aylık strateji PDF'lerinden; Ekim/Kasım takvimleri geçici olup sonraki baskıda kesinleşir).

Çıktı olay kaydı: {tarih, saat, kurum, baslik, donem, kategori (veri|karar|rapor|ihale|kuresel), onem 1-3, link}
Kullanım: python takvim/takvim_uret.py
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
OUT = BASE / "site" / "data" / "takvim.json"
PROGRAM = BASE / "hazine ihale " / "borclanma programi" / "program.json"
TR = ZoneInfo("Europe/Istanbul")
ULUSAL_URL = "https://www.tuik.gov.tr/Kurumsal/GetYillikHaberBulteniListesi?yil={yil}&kurum=TUIK"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
      "Accept": "application/json", "Referer": "https://www.tuik.gov.tr/Kurumsal/Veri_Takvimi"}

# Ulusal takvimden alınacak bültenler: (kurum, ad deseni, kısa başlık, önem, birleştirme grubu)
# Aynı gün+saat+grup olan kayıtlar tek olayda birleşir (TCMB'nin Perşembe 14:30 haftalık seti gibi).
SECIM = [
    ("TÜİK", r"^Tüketici Fiyat Endeksi", "Enflasyon (TÜFE)", 3, "tufe"),
    ("TÜİK", r"^Yurt İçi Üretici Fiyat", "Yurt içi ÜFE", 2, "tufe"),
    ("TÜİK", r"^Dış Ticaret İstatistikleri", "Dış ticaret", 2, None),
    ("TÜİK", r"^İşgücü İstatistikleri", "İşgücü (işsizlik)", 2, None),
    ("TÜİK", r"^Sanayi Üretim Endeksi", "Sanayi üretimi", 2, None),
    ("TÜİK", r"Gayrisafi Yurt ?İçi Hasıla", "GSYH (büyüme)", 3, None),
    ("TÜİK", r"^Ekonomik Güven", "Ekonomik güven endeksi", 1, None),
    ("TÜİK", r"^Tüketici Güven", "Tüketici güven endeksi", 1, None),
    ("TÜİK", r"^Ticaret Satış Hacim", "Perakende satış hacmi", 1, None),
    ("TÜİK", r"^Konut ve İş Yeri Satış|^Konut Satış", "Konut satışları", 1, None),
    ("TÜİK", r"^Finansal Yatırım Araçlarının Reel", "Finansal araçların reel getirisi", 1, None),
    ("TÜİK", r"^Hizmet, Perakende Ticaret ve İnşaat Güven", "Sektörel güven endeksleri", 1, None),
    ("TCMB", r"^Haftalık Para ve Banka", "Haftalık para-banka istatistikleri, rezervler", 2, "tcmb-hafta"),
    ("TCMB", r"^\s*Menkul Kıymet İstatistikleri", "yurt dışı yerleşik menkul kıymet", 2, "tcmb-hafta"),
    ("TCMB", r"^Kredi Faiz Oranları", "Haftalık kredi faizleri", 1, "tcmb-faiz"),
    ("TCMB", r"^Mevduat Faiz Oranları", "mevduat faizleri", 1, "tcmb-faiz"),
    ("TCMB", r"^Ödemeler Dengesi", "Ödemeler dengesi (cari denge)", 3, None),
    ("TCMB", r"^Uluslararası Rezervler ve Döviz Likiditesi", "Uluslararası rezervler ve döviz likiditesi (aylık)", 2, None),
    ("TCMB", r"İktisadi Yönelim|Reel Kesim Güven", "Reel kesim güveni", 1, "tcmb-rkge"),
    ("TCMB", r"^İmalat Sanayi Kapasite", "kapasite kullanım oranı", 1, "tcmb-rkge"),
    ("TCMB", r"^Konut Fiyat Endeksi", "Konut fiyat endeksi", 1, None),
    ("TCMB", r"^Finansal Hizmetler", "Finansal hizmetler güven endeksi", 1, None),
    ("TCMB", r"^Kısa Vadeli Dış Borç", "Kısa vadeli dış borç", 1, None),
    ("TCMB", r"^Reel Efektif Döviz Kuru", "Reel efektif döviz kuru", 1, None),
    ("TCMB", r"^Aylık Para ve Banka", "Aylık para-banka istatistikleri", 1, None),
    ("TCMB", r"^Uluslararası Yatırım Pozisyonu", "Uluslararası yatırım pozisyonu", 1, None),
    ("TCMB", r"^Finansal Hesaplar", "Finansal hesaplar", 1, None),
    ("TCMB", r"^Türkiye Dış Borç", "Dış borç istatistikleri", 1, None),
    ("TCMB", r"Sektörel Enflasyon Beklentileri", "Sektörel enflasyon beklentileri", 2, None),
    ("TCMB", r"Piyasa Katılımcıları Anketi", "Piyasa Katılımcıları Anketi", 2, None),
    ("HMB", r"^Merkezi Yönetim Bütçe Denge", "Merkezi yönetim bütçe gerçekleşmeleri", 3, None),
    ("HMB", r"^Hazine Nakit Gerçekleşmeleri", "Hazine nakit gerçekleşmeleri", 2, None),
    ("HMB", r"^Merkezi Yönetim Borç Stoku", "Merkezi yönetim borç stoku", 2, None),
    ("HMB", r"^Merkezi Yönetim İç Borç İstatistikleri \(Merkezi Yönetim İç Borç Ödemeleri", "İç borç ödeme ve ihale istatistikleri", 1, "hmb-icborc"),
    ("HMB", r"^Merkezi Yönetim İç Borç İstatistikleri", "iç borç istatistikleri", 1, "hmb-icborc"),
    ("HMB", r"^Kamu Net Borç Stoku", "Kamu net borç stoku", 1, None),
    ("HMB", r"^Avrupa Birliği Tanımlı", "AB tanımlı genel yönetim borç stoku", 1, None),
    ("BDDK", r"^Bankacılık Sektörü (Kredi Bilgileri|Mevduat|Menkul Değerler|Takipteki|Yabancı Para|Bilanço)", "", 2, "bddk"),
    ("BDDK", r"^Bankacılık Sektörü (Kar-Zarar|Sermaye Yeterliliği|Likidite|KOBİ|Sektörel Kredi|Kredi Dağılımı)", "", 1, "bddk"),
]
# Birleştirme gruplarının sabit başlıkları (kayıt sırasından bağımsız); bddk döneme göre haftalık/aylık
GRUP_BASLIK = {
    "tufe": "Enflasyon: TÜFE ve Yİ-ÜFE",
    "tcmb-hafta": "Haftalık para-banka istatistikleri, rezervler, yurt dışı yerleşik menkul kıymet",
    "tcmb-faiz": "Haftalık kredi ve mevduat faizleri",
    "tcmb-rkge": "Reel kesim güveni ve kapasite kullanım oranı",
    "hmb-icborc": "İç borç istatistikleri (ödemeler, ihaleler, stok)",
}
SECIM_DESEN = [(k, re.compile(d), b, o, g) for k, d, b, o, g in SECIM]
KURUM_LINK = {"TÜİK": "https://data.tuik.gov.tr", "TCMB": "https://evds3.tcmb.gov.tr", "HMB": "https://www.hmb.gov.tr",
              "BDDK": "https://www.bddk.org.tr"}


def ulusal_takvim(yil):
    """Ulusal Veri Yayımlama Takvimi kayıtları (önbellekli). Dönüş: [kayıt] veya []."""
    cache = HERE / f"ulusal_{yil}.json"
    kayit = None
    try:
        r = requests.get(ULUSAL_URL.format(yil=yil), headers=UA, timeout=45)
        r.raise_for_status()
        d = r.json()
        kayit = [x for k, v in d.items() if isinstance(v, list) for x in v]
        if kayit:
            # önbelleğe yalnız gerekli alanları (ve seçili kurumları) yaz — depo şişmesin
            kucuk = [{k2: x.get(k2) for k2 in ("sorumluKisaAd", "adi", "gTarih", "donemi", "link")}
                     for x in kayit if x.get("sorumluKisaAd") in ("TÜİK", "TCMB", "HMB", "BDDK")]
            kucuk.sort(key=lambda x: (x.get("gTarih") or "", x.get("sorumluKisaAd") or "", x.get("adi") or ""))  # kararlı sıra: gereksiz diff olmasın
            cache.write_text(json.dumps(kucuk, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"  ulusal takvim {yil}: {len(kayit)} kayıt (uç nokta) → önbellek {len(kucuk)}")
            return kucuk
    except Exception as e:
        print(f"  ~ ulusal takvim {yil} çekilemedi ({type(e).__name__}: {str(e)[:60]})")
    if cache.exists():
        kayit = json.loads(cache.read_text(encoding="utf-8"))
        print(f"  ulusal takvim {yil}: {len(kayit)} kayıt (önbellek)")
        return kayit
    return []


def ulusal_olaylar(kayitlar):
    ham = []
    for x in kayitlar:
        kurum, ad = x.get("sorumluKisaAd"), (x.get("adi") or "").strip()
        for k, desen, baslik, onem, grup in SECIM_DESEN:
            if k == kurum and desen.search(ad):
                t = dt.datetime.fromisoformat(x["gTarih"])
                ham.append({"tarih": t.strftime("%Y-%m-%d"), "saat": t.strftime("%H:%M"), "kurum": kurum,
                            "baslik": baslik, "donem": (x.get("donemi") or "").strip() or None,
                            "kategori": "veri", "onem": onem, "link": x.get("link") or KURUM_LINK.get(kurum),
                            "_grup": grup})
                break
    # Aynı gün+saat+grup → tek olay; başlık grubun sabit başlığıdır, önem en yükseği
    birlesik, out = {}, []
    for o in ham:
        if o["_grup"]:
            anahtar = (o["tarih"], o["saat"], o["_grup"])
            if anahtar in birlesik:
                birlesik[anahtar]["onem"] = max(birlesik[anahtar]["onem"], o["onem"])
                continue
            birlesik[anahtar] = o
        out.append(o)
    for o in out:
        g = o.pop("_grup", None)
        if g == "bddk":
            haftalik = "Hafta" in (o["donem"] or "")
            o["baslik"] = ("Haftalık bankacılık verileri (kredi, mevduat, YP pozisyonu)" if haftalik
                           else "Aylık bankacılık sektörü verileri (bilanço, kâr-zarar, sermaye yeterliliği)")
            o["onem"] = 2 if haftalik else 1
        elif g:
            o["baslik"] = GRUP_BASLIK[g]
    return out


def sabit_olaylar():
    d = json.loads((HERE / "sabit_takvim.json").read_text(encoding="utf-8"))
    out = []
    for o in d["olaylar"]:
        yerel = dt.datetime.fromisoformat(f"{o['tarih']}T{o['saat']}").replace(tzinfo=ZoneInfo(o["dilim"]))
        t = yerel.astimezone(TR)
        out.append({"tarih": t.strftime("%Y-%m-%d"), "saat": t.strftime("%H:%M"), "kurum": o["kurum"],
                    "baslik": o["baslik"], "donem": None, "kategori": o["kategori"], "onem": o["onem"],
                    "link": o.get("link")})
    return out


def hazine_olaylar():
    if not PROGRAM.exists():
        return []
    rows = json.loads(PROGRAM.read_text(encoding="utf-8")).get("ihale_takvimi", [])
    # Aynı gün birden çok ihraç → tek olay, senetler listelenir
    gunler = {}
    for r in rows:
        gunler.setdefault(r["ihale"], []).append(r)
    out = []
    for gun, rs in sorted(gunler.items()):
        parca = []
        for r in rs:
            senet = r["senet"].split(",")[0].strip()
            vade = r["vade"].split("/")[0].strip()
            yontem = "doğrudan satış" if "Doğrudan" in r["yontem"] else ("ilk ihraç" if "İlk" in r["yontem"] else "yeniden ihraç")
            parca.append(f"{vade} {senet} ({yontem})")
        out.append({"tarih": gun, "saat": None, "kurum": "Hazine",
                    "baslik": "Hazine ihracı: " + "; ".join(parca),
                    "donem": f"valör {dt.date.fromisoformat(rs[0]['valor']).strftime('%d.%m.%Y')}",
                    "kategori": "ihale", "onem": 3 if any("ihraç" in p for p in parca) else 2,
                    "link": "https://ekordion.com.tr/hazine.html"})
    return out


def main():
    bugun = dt.datetime.now(TR).date()
    print("Ekonomik takvim üretiliyor...")
    olaylar = sabit_olaylar()
    print(f"  sabit takvim: {len(olaylar)} olay")
    for yil in (bugun.year, bugun.year + 1):
        k = ulusal_takvim(yil)
        if k:
            u = ulusal_olaylar(k)
            print(f"  ulusal takvim {yil}: {len(u)} seçili olay")
            olaylar += u
    h = hazine_olaylar()
    print(f"  Hazine ihraç takvimi: {len(h)} gün")
    olaylar += h
    # pencere: 45 gün geri → 400 gün ileri; sıralama tarih, saat (saatsizler günün başına), önem
    bas, son = bugun - dt.timedelta(days=45), bugun + dt.timedelta(days=400)
    olaylar = [o for o in olaylar if bas.isoformat() <= o["tarih"] <= son.isoformat()]
    olaylar.sort(key=lambda o: (o["tarih"], o["saat"] or "00:00", -o["onem"], o["kurum"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updated": dt.datetime.now(TR).strftime("%d.%m.%Y %H:%M"), "olaylar": olaylar},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    yakin = [o for o in olaylar if bugun.isoformat() <= o["tarih"] <= (bugun + dt.timedelta(days=10)).isoformat()]
    print(f"  toplam {len(olaylar)} olay → {OUT.relative_to(BASE)} · önümüzdeki 10 gün:")
    for o in yakin:
        print(f"    {o['tarih']} {o['saat'] or '--:--'}  {o['kurum']:6s} {'★' * o['onem']:3s} {o['baslik'][:80]}" + (f"  [{o['donem']}]" if o["donem"] else ""))
    print("BAŞARILI")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"HATA: {e}", file=sys.stderr); sys.exit(1)
