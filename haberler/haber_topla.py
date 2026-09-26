#!/usr/bin/env python3
"""Gündem — günlük finans haberleri toplayıcısı.

Türkçe ekonomi/finans RSS akışlarından son N saatin haberlerini toplar, aynı haberin farklı
sitelerdeki kopyalarını kümeler, finansla ilgisiz olanları eler, kategorilere ayırır ve
site/data/haber/ altına günlük arşiv + index yazar (site/gundem.html ve ana sayfa bunları okur).

İki seçki modu:
  ai       — ANTHROPIC_API_KEY (veya `ant auth login` profili) ve `anthropic` paketi varsa:
             Claude ilgiyi, kategoriyi, önemi belirler; her habere tek cümlelik özgün özet ve
             "günün öne çıkanları" maddelerini yazar.
  anahtar  — aksi halde: anahtar kelime puanlamasıyla aynı yapı (özet cümlesi yok).
Yapay zekâ çağrısı herhangi bir nedenle başarısız olursa akış bozulmaz, anahtar moduna düşer.

Telif: haber metni kopyalanmaz — yalnız başlık, kaynağa bağlantı ve kısa özgün özet yayımlanır.

Kullanım:  python haberler/haber_topla.py [--saat 24] [--zorla]
"""
import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
OUT_DIR = BASE / "site" / "data" / "haber"
GUNDEM_HTML = BASE / "site" / "gundem.html"
HOME_JSON = BASE / "site" / "data" / "home.json"        # modül özet kartları (site_export üretir)
DURUM_JSON = OUT_DIR / "veri_durum.json"                 # son bültende görülen kart imzaları
TAKVIM_JSON = BASE / "site" / "data" / "takvim.json"     # ekonomik takvim (takvim/takvim_uret.py)
PIYASA_JSON = BASE / "site" / "data" / "piyasa.json"     # günün rakamları (piyasa/piyasa_fetch.py)
TR = dt.timezone(dt.timedelta(hours=3))
ARSIV_GUN = 60
MODEL = os.environ.get("HABER_MODEL", "claude-opus-5")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*"}

# (ad, url, finans odaklı mı) — sıra aynı zamanda küme temsilcisi seçiminde kaynak önceliğidir
KAYNAKLAR = [
    ("AA Ekonomi", "https://www.aa.com.tr/tr/rss/default?cat=ekonomi", True),
    ("CNBC-e", "https://www.cnbce.com/rss", True),
    ("Ekonomim", "https://www.ekonomim.com/rss", True),
    ("Dünya", "https://www.dunya.com/rss", True),
    ("Ekonomist", "https://www.ekonomist.com.tr/rss", True),
    ("Borsa Gündem", "https://www.borsagundem.com.tr/rss", True),
    ("Investing TR", "https://tr.investing.com/rss/news.rss", True),
    ("Habertürk Ekonomi", "https://www.haberturk.com/rss/ekonomi.xml", True),
    ("TRT Haber Ekonomi", "https://www.trthaber.com/ekonomi_articles.rss", True),
    ("Sabah Ekonomi", "https://www.sabah.com.tr/rss/ekonomi.xml", True),
    ("Milliyet Ekonomi", "https://www.milliyet.com.tr/rss/rssnew/ekonomirss.xml", True),
    ("Sözcü Ekonomi", "https://www.sozcu.com.tr/feeds-rss-category-ekonomi", True),
    ("Hürriyet Ekonomi", "https://www.hurriyet.com.tr/rss/ekonomi", True),
    ("Euronews Ekonomi", "https://tr.euronews.com/rss?level=vertical&name=business", True),
    ("Cumhuriyet", "https://www.cumhuriyet.com.tr/rss/6", False),
    ("BBC Türkçe", "https://feeds.bbci.co.uk/turkce/rss.xml", False),
    ("DW Türkçe", "https://rss.dw.com/rdf/rss-tur-all", False),
]

# kod -> (başlık, anahtar kelime kökleri). Kısa kökler (≤4 harf) tam sözcük, uzunlar önek eşleşir.
KATEGORILER = {
    "para": ("Para Politikası & TCMB", [
        "tcmb", "merkez bankası", "merkez bankasi", "politika faizi", "faiz karar", "para politikası",
        "ppk", "karahan", "rezerv", "swap", "zorunlu karşılık", "makroihtiyati", "kur korumalı", "kkm",
        "sıkılaşma", "faiz indirim", "faiz artır"]),
    "maliye": ("Hazine, Bütçe & Maliye", [
        "hazine", "bütçe", "maliye", "vergi", "şimşek", "borçlanma", "eurobond", "kira sertifikası",
        "ötv", "kdv", "kamu borç", "orta vadeli program", "ovp", "teşvik", "stopaj", "gelir idaresi"]),
    "banka": ("Bankacılık & Kredi", [
        "bddk", "banka", "kredi", "mevduat", "takipteki", "sermaye yeterlili", "katılım banka", "tmsf",
        "kredi kartı", "konut kredisi", "ihtiyaç kredisi"]),
    "piyasa": ("Piyasalar", [
        "borsa", "bist", "dolar", "euro", "altın", "ons", "tahvil", "getiri", "cds", "döviz", "kuru",
        "hisse", "endeks", "petrol", "brent", "bitcoin", "kripto", "viop", "gümüş", "emtia", "parite"]),
    "makro": ("Makro Veriler", [
        "enflasyon", "tüfe", "üfe", "büyüme", "gsyh", "işsizlik", "istihdam", "cari açık", "cari denge",
        "cari işlemler", "dış ticaret", "ihracat", "ithalat", "sanayi üretim", "pmi", "tüik",
        "güven endeksi", "konut satış", "kapasite kullanım", "perakende satış", "asgari ücret"]),
    "kuresel": ("Küresel Ekonomi", [
        "fed", "powell", "ecb", "avrupa merkez", "lagarde", "boj", "boe", "imf", "dünya bankası", "opec",
        "tarife", "gümrük vergisi", "resesyon", "moody", "fitch", "s&p", "kredi notu", "derecelendirme",
        "euro bölgesi", "wall street", "nasdaq", "ticaret savaş"]),
    "sirket": ("Şirketler & Sektörler", [
        "halka arz", "bedelli", "bedelsiz", "temettü", "kap", "spk", "birleşme", "satın al", "konkordato",
        "iflas", "yatırım", "otomotiv", "enerji", "turizm", "havayolu", "sanayi", "kâr açıkla", "bilanço"]),
}
KATEGORI_SIRA = list(KATEGORILER)
# Yalnız kategori belirlemede kullanılır (ilgi puanına girmez): yurt dışı işaretleri ve yerel işaretler
YURTDISI = ["trump", "abd", "çin", "japonya", "almanya", "rusya", "avrupa", "ingiltere", "küresel",
            "yaptırım", "fed", "ecb", "powell", "lagarde"]
YEREL = ["tcmb", "türkiye", "hazine", "bddk", "bist", "borsa istanbul", "şimşek", "karahan", "tüik",
         "lira", "tl", "ankara", "istanbul"]
# Finans dışı / tıklama tuzağı kalıpları (başlıkta) — güçlü eksi puan
EKSI = ["burç", "astroloji", "maç", "magazin", "dizi", "hava durumu", "deprem", "trafik", "kpss", "dgs",
        "yks", "öğretmen", "sınav", "tarif", "sağlık", "ünlü", "cinayet", "kaza", "yangın", "sergi",
        "konser", "festival", "nasıl yapılır", "sorgulama", "ne zaman", "kimdir", "nerede", "şans topu",
        "çılgın sayısal", "piyango", "loto", "süper loto", "on numara"]
DURAK = {"ve", "ile", "için", "bir", "bu", "da", "de", "mi", "mı", "mu", "mü", "ne", "en", "o", "şu", "ki",
         "ya", "veya", "ama", "gibi", "kadar", "daha", "çok", "son", "yeni", "oldu", "olan", "olarak",
         "göre", "sonra", "önce", "ise", "the", "a", "an", "of", "in", "to"}


def kucuk(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


def _desen(kok):
    k = re.escape(kucuk(kok))
    # kısa kökler tam sözcük ("fed" ≠ "federasyon"); uzun kökler sözcük başından önek (çekim eklerine izin)
    return re.compile(r"(?<![a-zçğıöşü0-9])" + k + (r"(?![a-zçğıöşü])" if len(kok) <= 4 else ""))


KAT_DESEN = {kod: [_desen(k) for k in kokler] for kod, (_, kokler) in KATEGORILER.items()}
EKSI_DESEN = [_desen(k) for k in EKSI]
YURTDISI_DESEN = [_desen(k) for k in YURTDISI]
YEREL_DESEN = [_desen(k) for k in YEREL]


def tarih_coz(s, simdi):
    """RFC822 / ISO / saat dilimsiz ('2026-09-19 11:58:06' → UTC varsayılır). Gelecek tarih şimdiye kırpılır."""
    if not s:
        return None
    s = s.strip()
    w = None
    try:
        w = email.utils.parsedate_to_datetime(s)
    except Exception:
        try:
            w = dt.datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
        except Exception:
            return None
    if w.tzinfo is None:
        w = w.replace(tzinfo=dt.timezone.utc)
    return min(w, simdi)


def duz_metin(s, n=240):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    s = re.sub(r"\s+", " ", html.unescape(s)).strip()
    return (s[: n - 1].rsplit(" ", 1)[0] + "…") if len(s) > n else s


def akis_oku(ad, url, simdi):
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    try:
        kok = ET.fromstring(r.content)
    except ET.ParseError:
        # tanımsız HTML varlıkları (&nbsp; vb.) bazı akışları bozuyor — yumuşatıp yeniden dene
        kok = ET.fromstring(re.sub(rb"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", b"&amp;", r.content))
    ogeler = [e for e in kok.iter() if e.tag.split("}")[-1] in ("item", "entry")]
    out = []
    for it in ogeler:
        v = {"baslik": "", "link": "", "tarih": None, "snippet": ""}
        for ch in it:
            tag = ch.tag.split("}")[-1]
            txt = (ch.text or "").strip()
            if tag == "title" and not v["baslik"]:
                v["baslik"] = duz_metin(txt, 300)
            elif tag == "link" and not v["link"]:
                v["link"] = txt or ch.attrib.get("href", "")
            elif tag in ("pubDate", "published", "updated", "date") and v["tarih"] is None:
                v["tarih"] = tarih_coz(txt, simdi)
            elif tag in ("description", "summary") and not v["snippet"]:
                v["snippet"] = duz_metin(txt)
        if v["baslik"] and v["link"].startswith("http") and v["tarih"]:
            v["kaynak"] = ad
            out.append(v)
    return out


def belirtecler(baslik):
    t = re.sub(r"[^a-zçğıöşü0-9 ]", " ", kucuk(baslik))
    return {w[:6] for w in t.split() if w not in DURAK and len(w) > 1}


def kumele(haberler):
    """Aynı haberin farklı sitelerdeki kopyalarını birleştirir (başlık belirteç benzerliği)."""
    kumeler = []
    for h in haberler:
        b = belirtecler(h["baslik"])
        h["_b"] = b
        yer = None
        for k in kumeler:
            # kümenin HERHANGİ bir üyesine yeterince benzeyen başlık o kümeye girer
            for u in k["uyeler"]:
                ortak = len(b & u["_b"])
                if ortak < 3:
                    continue
                jac = ortak / len(b | u["_b"])
                kapsama = ortak / max(1, min(len(b), len(u["_b"])))
                if jac >= 0.45 or (kapsama >= 0.7 and ortak >= 4):
                    yer = k
                    break
            if yer:
                break
        if yer:
            yer["uyeler"].append(h)
        else:
            kumeler.append({"uyeler": [h]})
    oncelik = {ad: i for i, (ad, _, _) in enumerate(KAYNAKLAR)}
    out = []
    for k in kumeler:
        uy = sorted(k["uyeler"], key=lambda h: (oncelik.get(h["kaynak"], 99), h["tarih"]))
        tem = uy[0]
        gorulen, diger = {tem["kaynak"]}, []
        for h in uy[1:]:
            if h["kaynak"] not in gorulen:
                gorulen.add(h["kaynak"])
                diger.append({"kaynak": h["kaynak"], "link": h["link"]})
        out.append({"baslik": tem["baslik"], "link": tem["link"], "kaynak": tem["kaynak"],
                    "tarih": min(h["tarih"] for h in uy), "diger": diger,
                    "snippet": next((h["snippet"] for h in uy if h["snippet"]), "")})
    return out


def puanla(k, finans_kaynak):
    """Anahtar kelime puanı → (toplam puan, kategori kodu)."""
    bas, snip = kucuk(k["baslik"]), kucuk(k["snippet"])
    kat_puan = {}
    for kod, desenler in KAT_DESEN.items():
        p = sum(2 for d in desenler if d.search(bas)) + sum(1 for d in desenler if d.search(snip))
        if p:
            kat_puan[kod] = p
    toplam = sum(kat_puan.values()) + (1 if finans_kaynak.get(k["kaynak"]) else 0)
    toplam -= 4 * sum(1 for d in EKSI_DESEN if d.search(bas))
    if bas.rstrip().endswith("?"):
        toplam -= 2
    kat = max(kat_puan, key=lambda c: (kat_puan[c], -KATEGORI_SIRA.index(c))) if kat_puan else "sirket"
    # "vergi/faiz" gibi genel kelimeler yurt dışı haberlerini yerel kategorilere çekmesin
    if kat in ("para", "maliye", "makro", "banka") and any(d.search(bas) for d in YURTDISI_DESEN) \
            and not any(d.search(bas) for d in YEREL_DESEN):
        kat = "kuresel"
    return toplam, kat


SISTEM = """Türkiye'de bir bankanın sabit getirili menkul kıymetler masası için günlük finans bülteni \
editörüsün. Sana son 24 saatin haber başlıkları (kaynak ve varsa kısa açıklamayla) numaralı liste olarak verilecek.

Görevin:
1. Masanın işine yarayan haberleri seç: para politikası ve TCMB, Hazine/bütçe/vergi, bankacılık düzenlemeleri \
ve kredi-mevduat, tahvil-döviz-altın-borsa piyasaları, makro veri açıklamaları, Fed/ECB ve küresel ekonomi, \
piyasayı etkileyen büyük şirket/sektör gelişmeleri. Finansla ilgisiz haberleri, magazin/spor/asayiş \
haberlerini, "ne zaman/nasıl yapılır" türü tıklama içeriklerini ve reklam niteliğindeki duyuruları alma.
2. Seçtiğin her haber için kategori, 1-5 arası önem (5 = piyasayı bugün fiilen etkileyen gelişme) ve haberin \
ne söylediğini kendi cümlenle anlatan tek cümlelik (en çok 25 kelime) Türkçe özet yaz. Başlığı kopyalama; \
bilgi başlık ve açıklamada yoksa uydurma, elindekiyle sınırlı kal.
3. "gunun_ozeti" alanına günün en önemli 3-5 gelişmesini, her biri tek cümle olacak şekilde yaz. Birden \
çok haber aynı gelişmeyi anlatıyorsa tek maddede birleştir. Rakam varsa koru.

Kategoriler: para (Para Politikası & TCMB), maliye (Hazine, Bütçe & Maliye), banka (Bankacılık & Kredi), \
piyasa (Piyasalar), makro (Makro Veriler), kuresel (Küresel Ekonomi), sirket (Şirketler & Sektörler)."""

SEMA = {
    "type": "object",
    "properties": {
        "gunun_ozeti": {"type": "array", "items": {"type": "string"}},
        "secilenler": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "kategori": {"type": "string", "enum": KATEGORI_SIRA},
                    "onem": {"type": "integer"},
                    "ozet": {"type": "string"},
                },
                "required": ["id", "kategori", "onem", "ozet"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["gunun_ozeti", "secilenler"],
    "additionalProperties": False,
}


def ai_sec(kumeler):
    """Claude ile seçki. Dönüş: {'gunun_ozeti': [...], 'secilenler': [{id,kategori,onem,ozet}]}."""
    import anthropic

    client = anthropic.Anthropic()
    liste = "\n".join(
        f"[{i}] ({k['kaynak']}" + (f", +{len(k['diger'])} kaynak" if k["diger"] else "") + f") {k['baslik']}"
        + (f" — {k['snippet']}" if k["snippet"] else "")
        for i, k in enumerate(kumeler))
    istek = dict(
        model=MODEL,
        max_tokens=16000,
        system=SISTEM,
        messages=[{"role": "user", "content": "Haber listesi:\n\n" + liste}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SEMA}},
    )
    try:
        # Ret (refusal) durumunda aynı çağrı içinde yedek modele geçilir
        r = client.beta.messages.create(betas=["server-side-fallback-2026-06-01"],
                                        fallbacks=[{"model": "claude-opus-4-8"}], **istek)
    except anthropic.BadRequestError as e:
        print(f"  ~ yedekli çağrı reddedildi ({e.message}) — yedeksiz deneniyor")
        r = client.messages.create(**istek)
    if r.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"yanıt tamamlanmadı (stop_reason={r.stop_reason})")
    veri = json.loads(next(b.text for b in r.content if b.type == "text"))
    print(f"  Claude ({r.model}): {len(veri['secilenler'])} haber seçildi · "
          f"girdi {r.usage.input_tokens} / çıktı {r.usage.output_tokens} token")
    return veri


def ai_kullanilabilir():
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or (Path.home() / ".config" / "anthropic").exists())


def sec(kumeler, finans_kaynak):
    """→ (mod, gunun_ozeti, [(kume, kategori, onem, ozet)])"""
    puanli = [(k, *puanla(k, finans_kaynak)) for k in kumeler]
    if ai_kullanilabilir():
        import anthropic
        # bariz ilgisizleri gönderme; kalanları Claude değerlendirir (en çok 260 küme)
        aday = [k for k, p, _ in sorted(puanli, key=lambda x: -x[1]) if p > -2][:260]
        try:
            v = ai_sec(aday)
            secim = [(aday[s["id"]], s["kategori"], max(1, min(5, s["onem"])), s["ozet"].strip())
                     for s in v["secilenler"] if 0 <= s["id"] < len(aday)]
            if secim:
                return "ai", [m.strip() for m in v["gunun_ozeti"] if m.strip()][:5], secim
            print("  ~ Claude hiçbir haber seçmedi — anahtar kelime moduna düşülüyor")
        except anthropic.RateLimitError as e:
            print(f"  ~ Claude oran sınırı ({e.message}) — anahtar kelime moduna düşülüyor")
        except anthropic.APIStatusError as e:
            print(f"  ~ Claude API hatası {e.status_code} ({e.message}) — anahtar kelime moduna düşülüyor")
        except anthropic.APIConnectionError as e:
            print(f"  ~ Claude bağlantı hatası ({e}) — anahtar kelime moduna düşülüyor")
        except Exception as e:
            print(f"  ~ Claude seçkisi başarısız ({type(e).__name__}: {e}) — anahtar kelime moduna düşülüyor")
    secim = []
    for k, p, kat in puanli:
        if p >= 3:
            onem = max(1, min(5, 1 + len(k["diger"]) + (p - 3) // 3))
            secim.append((k, kat, onem, ""))
    return "anahtar", [], secim


def veri_bolumu(bulten):
    """'Yeni açıklanan veriler': ana sayfa kartlarından (home.json) son bültenden bu yana metni değişen
    modüller — yeni veri açıklanınca site_export kart cümlesini yeniler, imzası (metin özeti) değişir.
    Durum dosyası yalnız bülten koşusunda (--bulten) güncellenir; böylece Pazartesi bülteni Cuma ve hafta
    sonu açıklanan verileri de kapsar, yerel/hafta sonu koşuları listeyi tüketmez. İlk koşuda (durum
    dosyası yokken) liste boş döner, yalnız imzalar kaydedilir."""
    try:
        kartlar = json.loads(HOME_JSON.read_text(encoding="utf-8")).get("cards", [])
    except Exception:
        return []
    try:
        eski = json.loads(DURUM_JSON.read_text(encoding="utf-8")).get("imza", {})
    except Exception:
        eski = None
    yeni, degisen = {}, []
    for k in kartlar:
        link = k.get("link") or ""
        metin = re.sub(r"<[^>]+>", "", k.get("html") or "").strip()
        if not link or link.startswith("gundem") or not metin:
            continue
        imza = hashlib.sha1(metin.encode("utf-8")).hexdigest()[:12]
        yeni[link] = imza
        if eski is not None and eski.get(link) != imza:
            degisen.append({"ikon": k.get("icon") or "", "baslik": k.get("title") or "", "ozet": metin, "link": link})
    if bulten or eski is None:
        DURUM_JSON.write_text(json.dumps({"imza": yeni, "guncelleme": dt.datetime.now(TR).strftime("%d.%m.%Y %H:%M")},
                                         ensure_ascii=False, indent=0), encoding="utf-8")
    return degisen


def takvim_bolumu(simdi):
    """Bugünün olayları + haftanın kalanındaki önemli (önem ≥ 2) olaylar (Pazar'a kadar)."""
    try:
        ol = json.loads(TAKVIM_JSON.read_text(encoding="utf-8"))["olaylar"]
    except Exception:
        return None
    bugun = simdi.date()
    hafta_son = bugun + dt.timedelta(days=6 - bugun.weekday())
    return {"bugun": [o for o in ol if o["tarih"] == bugun.isoformat()],
            "hafta": [o for o in ol if bugun.isoformat() < o["tarih"] <= hafta_son.isoformat() and o["onem"] >= 2]}


def piyasa_bolumu():
    try:
        return json.loads(PIYASA_JSON.read_text(encoding="utf-8"))
    except Exception:
        return None


def yaz(gun, simdi, saat, mod, ozet, secim, sayilar, ek=None):
    kats = []
    for kod in KATEGORI_SIRA:
        hs = sorted((s for s in secim if s[1] == kod), key=lambda s: (-s[2], -s[0]["tarih"].timestamp()))
        if hs:
            kats.append({"kod": kod, "ad": KATEGORILER[kod][0], "haberler": [
                {"baslik": k["baslik"], "link": k["link"], "kaynak": k["kaynak"],
                 "zaman": k["tarih"].astimezone(TR).strftime("%d.%m %H:%M"),
                 "ozet": oz or None, "onem": onem, "diger": k["diger"]} for k, _, onem, oz in hs]})
    one_cikan = [{"baslik": k["baslik"], "link": k["link"], "kaynak": k["kaynak"]}
                 for k, _, _, _ in sorted(secim, key=lambda s: (-s[2], -len(s[0]["diger"]),
                                                                -s[0]["tarih"].timestamp()))[:5]]
    if not ozet:
        ozet = [o["baslik"] for o in one_cikan]
    gun_tr = simdi.strftime("%d.%m.%Y")
    ozet_html = (f"<b>{gun_tr}</b> finans gündemi — son {saat} saatte {sayilar['kaynak']} kaynaktan "
                 f"{sayilar['secilen']} haber: " + " · ".join(ozet))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{gun}.json").write_text(json.dumps({
        "tarih": gun, "updated": simdi.strftime("%d.%m.%Y %H:%M"), "pencere_saat": saat, "mod": mod,
        "ozet": ozet, "ozet_html": ozet_html, "kategoriler": kats, "sayilar": sayilar, **(ek or {}),
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    gunler = sorted((p.stem for p in OUT_DIR.glob("20??-??-??.json")), reverse=True)
    for eski in gunler[ARSIV_GUN:]:
        (OUT_DIR / f"{eski}.json").unlink()
    (OUT_DIR / "index.json").write_text(json.dumps({
        "son": gunler[0], "gunler": gunler[:ARSIV_GUN], "updated": simdi.strftime("%d.%m.%Y %H:%M"),
        "mod": mod, "ozet": ozet, "ozet_html": ozet_html, "one_cikan": one_cikan, "sayilar": sayilar,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # Arama motorları JS beklemeden taze içerik görsün: özeti sayfaya düz metin olarak göm
    if GUNDEM_HTML.exists():
        s = GUNDEM_HTML.read_text(encoding="utf-8")
        duz = html.escape(re.sub(r"<[^>]+>", "", ozet_html), quote=False)
        yeni, n = re.subn(r'(<div class="info-box" id="ozet">).*?(</div>)',
                          lambda m: m.group(1) + "📰 " + duz + m.group(2), s, count=1, flags=re.S)
        if n == 1 and yeni != s:
            GUNDEM_HTML.write_text(yeni, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saat", type=int, default=24, help="geriye dönük pencere (saat)")
    ap.add_argument("--zorla", action="store_true", help="bugünün yapay zekâ seçkisini anahtar moduyla ez")
    ap.add_argument("--bulten", action="store_true",
                    help="bülten koşusu: 'yeni açıklanan veriler' durum dosyasını bu koşuda ilerlet")
    a = ap.parse_args()

    simdi = dt.datetime.now(TR)
    gun = simdi.strftime("%Y-%m-%d")
    esik = simdi - dt.timedelta(hours=a.saat)
    print(f"Gündem toplanıyor — son {a.saat} saat ({esik.strftime('%d.%m %H:%M')} → {simdi.strftime('%d.%m %H:%M')})")

    hepsi, calisan = [], 0
    for ad, url, _ in KAYNAKLAR:
        try:
            ogeler = akis_oku(ad, url, simdi)
            taze = [o for o in ogeler if o["tarih"] >= esik]
            hepsi += taze
            calisan += 1
            print(f"  ✓ {ad:18s} {len(ogeler):3d} öğe · pencerede {len(taze):3d}")
        except Exception as e:
            print(f"  ✗ {ad:18s} {type(e).__name__}: {str(e)[:70]}")
    if not hepsi:
        print("HATA: hiçbir kaynaktan pencere içinde haber gelmedi", file=sys.stderr)
        sys.exit(1)

    hepsi.sort(key=lambda h: h["tarih"])
    kumeler = kumele(hepsi)
    finans_kaynak = {ad: f for ad, _, f in KAYNAKLAR}
    mod, ozet, secim = sec(kumeler, finans_kaynak)

    hedef = OUT_DIR / f"{gun}.json"
    if mod == "anahtar" and hedef.exists() and not a.zorla:
        try:
            if json.loads(hedef.read_text(encoding="utf-8")).get("mod") == "ai":
                print("Bugünün yapay zekâ seçkisi zaten var — anahtar kelime moduyla ezilmedi (--zorla ile ezilir).")
                return
        except Exception:
            pass

    sayilar = {"kaynak": calisan, "pencere": len(hepsi), "kume": len(kumeler), "secilen": len(secim)}
    veriler = veri_bolumu(a.bulten)
    print(f"  yeni açıklanan veri: {len(veriler)} modül" + (" (durum ilerletildi)" if a.bulten else ""))
    takvim, piyasa = takvim_bolumu(simdi), piyasa_bolumu()
    print(f"  takvim: {'yok' if takvim is None else str(len(takvim['bugun'])) + ' olay bugün'} · "
          f"piyasa: {'yok' if piyasa is None else str(len(piyasa['satirlar'])) + ' satır'}")
    yaz(gun, simdi, a.saat, mod, ozet, secim, sayilar, ek={"veriler": veriler, "takvim": takvim, "piyasa": piyasa})
    print(f"  {len(hepsi)} haber → {len(kumeler)} küme → {len(secim)} seçildi · mod: {mod}")
    print(f"Kaydedildi: site/data/haber/{gun}.json + index.json")
    print("BAŞARILI")


if __name__ == "__main__":
    main()
