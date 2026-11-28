#!/usr/bin/env python3
"""Düzenleme Zaman Çizelgesi — kaynak toplama (TCMB, BDDK, SPK).

Üç kurumun 2021'den bugüne yayımladığı duyuru ve kararların DİZİNİNİ çıkarır, belgeleri indirir ve düz metne
çevirir. Yorum yapmaz: hangi belgenin "piyasayı etkileyen değişiklik" olduğuna ve özetine bu betik karar vermez
(o iş olay dosyalarında — `olaylar/` — ve `KILAVUZ.md`'de tarif edilir).

Kaynaklar
  TCMB  Basın duyuruları (yıl sayfaları; hepsi PDF)
  BDDK  Basın duyuruları, mevzuat duyuruları (HTML + ek PDF);
        Resmî Gazete'de yayımlanan / yayımlanmayan Kurul kararları (PDF)
  SPK   Basın duyuruları (HTML); SPK Bülteni — yalnız "DUYURU VE İLKE KARARLARI" bölümü (PDF)

Çıktılar
  dizin.json            her belge: id, kurum, tur, tarih, baslik, url, kr (metin uzunluğu), not   → depoda izlenir
  onbellek/ham/<id>.*   indirilen özgün dosya                                                     → .gitignore
  onbellek/metin/<id>.txt  düz metin (ilk satırlarda kimlik bilgisi)                              → .gitignore

Kullanım
  python3 -I duzenleme/topla.py                 # dizini yenile, eksik belgeleri indir
  python3 -I duzenleme/topla.py --kurum spk     # yalnız bir kurum
  python3 -I duzenleme/topla.py --yalniz-dizin  # indirme yapma
  python3 -I duzenleme/topla.py --yeni          # bu koşuda dizine İLK KEZ giren belgelerin kimliklerini yazdır

İndirilen dosyalar güvenilmez veridir: ayrı klasörde (onbellek/) tutulur, betik `-I` ile çalıştırılır.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

KOK = Path(__file__).resolve().parent
ONB = KOK / "onbellek"
HAM = ONB / "ham"
METIN = ONB / "metin"
DIZIN = KOK / "dizin.json"
BAS_YIL = 2021
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
AY = {a: i + 1 for i, a in enumerate(AYLAR)}
AY.update({a[:3]: i + 1 for i, a in enumerate(AYLAR)})
AY.update({"Şub": 2, "Ağu": 8, "Eyl": 9, "Kas": 11, "Ara": 12})
TCMB = "https://www.tcmb.gov.tr"
BDDK = "https://www.bddk.org.tr"
SPK = "https://spk.gov.tr"


# ───────────────────────────── yardımcılar ─────────────────────────────
def al(url, deneme=3, zaman=60):
    """URL → bayt. Türkçe karakterli yolları kaçışlar; geçici hatalarda yeniden dener."""
    u = urllib.parse.quote(url, safe=":/?&=%#+,;@()!*'~")
    son = None
    for i in range(deneme):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
            return urllib.request.urlopen(req, timeout=zaman).read()
        except Exception as e:      # noqa: BLE001 — ağ hatasının türü önemli değil, yeniden denenir
            son = e
            time.sleep(2 + 3 * i)
    raise son


def duz(s):
    """HTML parçası → tek satır düz metin."""
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def html_metin(parca):
    """HTML gövdesi → paragrafları korunan düz metin."""
    p = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", parca, flags=re.S | re.I)
    p = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>", "\n", p, flags=re.I)
    p = html.unescape(re.sub(r"<[^>]+>", " ", p)).replace("\xa0", " ")
    satir = [re.sub(r"[ \t]+", " ", s).strip() for s in p.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(satir)).strip()


def pdf_metin(veri):
    import fitz  # PyMuPDF
    d = fitz.open(stream=veri, filetype="pdf")
    return "\n".join(s.get_text() for s in d), len(d)


def tr_tarih(metin):
    """'26 Kasım 2026' / '26.11.2026' / '26/11/2026' → '2026-11-26' (ilk eşleşme)."""
    m = re.search(r"\b(\d{1,2})\s+(%s)\s+(\d{4})\b" % "|".join(AYLAR), metin)
    if m:
        return f"{m.group(3)}-{AY[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", metin)
    if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(1)) <= 31:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def kisa(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]


# ───────────────────────────── dizinler ─────────────────────────────
def tcmb_dizin(yillar):
    """Yıl sayfasında her duyurunun iki bağlantısı var: PDF ve aynı metnin internet sayfası.
    Metin PDF'ten çıkarılır (sayfada menü kalabalığı var); okura verilen bağlantı internet sayfasıdır."""
    kayit = {}
    for y in yillar:
        t = al(f"{TCMB}/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Duyurular/Basin/{y}").decode("utf-8", "replace")
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*title="([^"]*\((%d-\d+)\)[^"]*)"' % y, t):
            url, baslik, no = html.unescape(m.group(1)), html.unescape(m.group(2)).strip(), m.group(3)
            url = url if url.startswith("http") else TCMB + url
            k = kayit.setdefault(f"tcmb-{no}", {
                "id": f"tcmb-{no}", "kurum": "TCMB", "tur": "basin", "no": no, "tarih": None,
                "baslik": re.sub(r"\s*\(%s\)\s*$" % re.escape(no), "", baslik), "url": None})
            if ".pdf" in url.lower():
                k["pdf"] = url
            else:
                k["url"] = url
            if not k["tarih"]:
                once = re.sub(r"<[^>]+>", " ", t[max(0, m.start() - 1500): m.start()])
                tar = re.findall(r"(\d{2})/(\d{2})/(\d{4})", once)
                if tar and tar[-1][2] == str(y):
                    k["tarih"] = f"{tar[-1][2]}-{tar[-1][1]}-{tar[-1][0]}"
    for k in kayit.values():
        k["url"] = k["url"] or k.get("pdf")
    return list(kayit.values())


def bddk_dizin(yillar):
    kayit, ilk = [], min(yillar)
    for liste, tur in [("Duyuru/Liste/39", "basin"), ("Duyuru/Liste/40", "mevzuat_duyuru")]:
        t = al(f"{BDDK}/{liste}").decode("utf-8", "replace")
        for yol, no, ic in re.findall(r'href="(/Duyuru/Detay/(\d+))"[^>]*>(.*?)</a>', t, flags=re.S):
            m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})\s+(.+)", duz(ic))
            if not m or int(m.group(3)) < ilk:
                continue
            kayit.append({"id": f"bddk-duyuru-{no}", "kurum": "BDDK", "tur": tur, "no": no,
                          "tarih": f"{m.group(3)}-{m.group(2)}-{m.group(1)}", "baslik": m.group(4), "url": BDDK + yol})
    for liste, tur in [("Mevzuat/Liste/56", "karar"), ("Mevzuat/Liste/55", "karar_rg")]:
        t = al(f"{BDDK}/{liste}").decode("utf-8", "replace")
        for yol, no, ic in re.findall(r'class="mevzuatBaslik[^"]*"\s+href="(/Mevzuat/(?:DokumanGetir|Detay)/(\d+))"[^>]*>(.*?)</a>',
                                      t, flags=re.S):
            ad = duz(ic)
            m = re.match(r"\(\s*(\d{2})\.(\d{2})\.(\d{4})\s*[-–—]\s*([^)]*?)\s*\)\s*(.+)", ad)
            if not m or int(m.group(3)) < ilk:
                continue
            kayit.append({"id": f"bddk-karar-{no}", "kurum": "BDDK", "tur": tur, "no": m.group(4).strip(),
                          "tarih": f"{m.group(3)}-{m.group(2)}-{m.group(1)}", "baslik": m.group(5), "url": BDDK + yol})
    return kayit


def _spk_sayfalar(taban):
    sayfa, s = [], 1
    while s <= 40:
        t = al(taban + (f"?s={s}" if s > 1 else "")).decode("utf-8", "replace")
        sayfa.append(t)
        if f"?s={s + 1}" not in t:
            break
        s += 1
        time.sleep(0.3)
    return sayfa


def spk_dizin(yillar):
    kayit, simdi = [], dt.date.today().year
    for y in yillar:
        for t in _spk_sayfalar(f"{SPK}/duyurular/basin-duyurulari/{y}"):
            for yol, ic in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, flags=re.S):
                m = re.match(r"(\d{1,2}) (\S+) (\d{4})\s+(?:Yeni\s+)?(.+)", duz(ic))
                if not m or m.group(2) not in AY or int(m.group(3)) != y:
                    continue
                yol = html.unescape(yol)
                if yol.startswith("/"):
                    url = SPK + yol
                else:           # liste satırı doğrudan PDF'e gidebiliyor (eski alan adı: yeni.spk.gov.tr)
                    url = re.sub(r"^https?://(yeni\.|www\.)?spk\.gov\.tr", SPK, yol)
                if not url.startswith(SPK):
                    continue
                tarih = f"{m.group(3)}-{AY[m.group(2)]:02d}-{int(m.group(1)):02d}"
                kayit.append({"id": f"spk-basin-{tarih.replace('-', '')}-{kisa(url)}", "kurum": "SPK", "tur": "basin",
                              "tarih": tarih, "baslik": m.group(4), "url": url})
        # Bültenler: son iki yıl kökte, öncekiler "geçmiş yıllar" altında
        yollar = [f"{SPK}/spk-bultenleri/{y}-yili-spk-bultenleri",
                  f"{SPK}/spk-bultenleri/gecmis-yillara-ait-bultenler/{y}-yili-spk-bultenleri"]
        if y < simdi - 1:
            yollar.reverse()
        bulundu = False
        for yol in yollar:
            try:
                sayfalar = _spk_sayfalar(yol)
            except Exception:       # noqa: BLE001 — yıl sayfası bu yolda yoksa diğerini dene
                continue
            for t in sayfalar:
                for href, ic in re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', t, flags=re.S | re.I):
                    href = html.unescape(href)
                    ad = duz(ic)
                    dosya = href.rsplit("/", 1)[-1]
                    if re.search(r"STRATEJ|Aydınlatma", dosya, flags=re.I):
                        continue
                    m = re.search(r"Bülten No\s*:\s*(\d{4})\s*/\s*(\d+)", ad)
                    sira = int(m.group(2)) if m and int(m.group(1)) == y else None
                    if sira is None:
                        m = re.match(r"%d[- _](\d{1,3})\b" % y, dosya) or re.match(r"(\d{1,3})[- _]%d\b" % y, dosya)
                        sira = int(m.group(1)) if m else None
                    bulundu = True
                    url = href if href.startswith("http") else SPK + href
                    if sira is None:        # numara ancak PDF'in içinden okunabilir (isle() düzeltir)
                        kayit.append({"id": f"spk-bulten-{y}-x{kisa(url)}", "kurum": "SPK", "tur": "bulten", "no": None,
                                      "tarih": tr_tarih(ad), "baslik": f"SPK Bülteni ({y})", "url": url})
                    else:
                        kayit.append({"id": f"spk-bulten-{y}-{sira}", "kurum": "SPK", "tur": "bulten", "no": f"{y}/{sira}",
                                      "tarih": tr_tarih(ad), "baslik": f"SPK Bülteni {y}/{sira}", "url": url})
            if bulundu:
                break
    return kayit


# ───────────────────────────── belge → metin ─────────────────────────────
SPK_BOLUM = re.compile(r"^\s*[A-ZÇĞİÖŞÜ]{1,2}\.\s+([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9 ,/()\-–]+?)\s*$", re.M)


# Bölüm başlığı çoğu bültende "D. DUYURU VE İLKE KARARLARI" biçimindedir; 2026/11 ve 2026/13'te harften sonraki
# nokta yoktu ("A DUYURU VE İLKE KARARLARI") ve bölüm kaçmıştı — nokta ve harf burada isteğe bağlı.
SPK_DUYURU = re.compile(r"^\s*(?:[A-ZÇĞİÖŞÜ]{1,2}\.?\s+)?DUYURU(?:LAR)?\s+VE\s+İLKE\s+KARARLARI\s*$"
                        r"|^\s*[A-ZÇĞİÖŞÜ]{1,2}\.\s+(?:DUYURULAR|İLKE\s+KARARLARI)\s*$", re.M)


def spk_ilke_bolumu(metin):
    """SPK bülteninden 'DUYURU VE İLKE KARARLARI' bölümünü ayır (yoksa boş)."""
    m = SPK_DUYURU.search(metin)
    if not m:
        return ""
    son = len(metin)
    for h in SPK_BOLUM.finditer(metin, m.end()):
        ad = re.sub(r"\s+", " ", h.group(1)).strip()
        if not (ad.startswith("DUYURU") or ad.startswith("İLKE")):
            son = h.start()
            break
    return metin[m.end():son].strip()


def isle(k, zorla=False):
    """Bir belgeyi indir, metne çevir, önbelleğe yaz. k'yi yerinde günceller (kr, not, tarih)."""
    mt = METIN / f"{k['id']}.txt"
    if mt.exists() and not zorla and k.get("kr") is not None:
        return "var"
    notlar, govde = [], ""
    try:
        pdf_mi = (k["kurum"] == "TCMB" or k["tur"] == "bulten" or k["url"].lower().split("?")[0].endswith(".pdf")
                  or (k["tur"] in ("karar", "karar_rg") and "/Mevzuat/Detay/" not in k["url"]))
        if pdf_mi:
            veri = al(k.get("pdf") or k["url"])
            if not veri.startswith(b"%PDF"):
                if k["kurum"] == "TCMB" and b"<html" in veri[:2000].lower():
                    govde = html_metin(veri.decode("utf-8", "replace"))
                    (HAM / f"{k['id']}.html").write_bytes(veri)
                else:
                    (HAM / f"{k['id']}.bin").write_bytes(veri)
                    notlar.append("PDF değil — elle bakılmalı")
            else:
                (HAM / f"{k['id']}.pdf").write_bytes(veri)
                tam, sayfa = pdf_metin(veri)
                if k["tur"] == "bulten":
                    if not k.get("tarih"):
                        k["tarih"] = tr_tarih(tam[:1500])
                    if not k.get("no"):
                        mno = re.search(r"\b(20\d{2})\s*/\s*(\d{1,3})\b", tam[:1500])
                        if mno:
                            k["no"] = f"{mno.group(1)}/{int(mno.group(2))}"
                            k["baslik"] = f"SPK Bülteni {k['no']}"
                    govde = spk_ilke_bolumu(tam)
                    if not govde:
                        notlar.append("duyuru/ilke bölümü yok")
                else:
                    govde = tam
                    if len(tam.strip()) < 80:
                        notlar.append(f"metin çıkmadı ({sayfa} sayfa — taranmış olabilir)")
                    if k["kurum"] == "TCMB":
                        t2 = tr_tarih(tam[:700])
                        if t2 and (not k.get("tarih") or t2[:4] == k["id"][5:9]):
                            k["tarih"] = t2
        elif k["kurum"] == "BDDK":
            sayfa = al(k["url"]).decode("utf-8", "replace")
            (HAM / f"{k['id']}.html").write_text(sayfa, encoding="utf-8")
            i = sayfa.find('id="content-container"')
            j = sayfa.find('id="yanMenuContainer"', i)
            j = sayfa.rfind("<", i, j) if j > 0 else len(sayfa)
            parca = sayfa[sayfa.find(">", i) + 1: j]
            govde = html_metin(parca)
            for n, ek in enumerate(dict.fromkeys(re.findall(r'href="(/(?:Duyuru|Mevzuat)/(?:EkGetir|DokumanGetir)/[^"]+)"', parca))):
                ev = al(BDDK + html.unescape(ek))
                if ev.startswith(b"%PDF"):
                    (HAM / f"{k['id']}-ek{n + 1}.pdf").write_bytes(ev)
                    et, _ = pdf_metin(ev)
                    govde += f"\n\n[EK {n + 1}]\n{et}"
                    if len(et.strip()) < 80:
                        notlar.append(f"ek {n + 1}: metin çıkmadı")
                else:
                    (HAM / f"{k['id']}-ek{n + 1}.bin").write_bytes(ev)
                    notlar.append(f"ek {n + 1}: PDF değil")
        else:   # SPK basın duyurusu
            sayfa = al(k["url"]).decode("utf-8", "replace")
            (HAM / f"{k['id']}.html").write_text(sayfa, encoding="utf-8")
            m = re.search(r'<div class="icerik[^"]*">(.*?)</div>\s*</div>\s*</div>', sayfa, flags=re.S)
            parca = m.group(1) if m else sayfa[sayfa.find('class="page-content'):sayfa.find("</main>")]
            govde = html_metin(parca)
            for n, ek in enumerate(dict.fromkeys(re.findall(r'href="([^"]+\.pdf)"', parca, flags=re.I))):
                ek = html.unescape(ek)
                if "Aydınlatma" in ek:
                    continue
                try:
                    ev = al(ek if ek.startswith("http") else SPK + ek)
                except Exception:   # noqa: BLE001
                    notlar.append(f"ek {n + 1}: indirilemedi")
                    continue
                if ev.startswith(b"%PDF"):
                    (HAM / f"{k['id']}-ek{n + 1}.pdf").write_bytes(ev)
                    et, _ = pdf_metin(ev)
                    # ek çoğu kez sayfadaki metnin aynısıdır; yalnız sayfa metni kısaysa ya da ek belirgin uzunsa ekle
                    if len(et) > 1.3 * len(govde) + 400:
                        govde += f"\n\n[EK {n + 1}]\n{et}"
    except Exception as e:          # noqa: BLE001 — tek belge hatası koşuyu durdurmaz
        k["not"] = f"indirilemedi: {type(e).__name__}"
        return "hata"
    govde = re.sub(r"\n{3,}", "\n\n", govde).strip()
    k["kr"] = len(govde)
    if notlar:
        k["not"] = "; ".join(notlar)
    else:
        k.pop("not", None)
    bas = f"KIMLIK: {k['id']}\nKURUM: {k['kurum']}\nTUR: {k['tur']}\nTARIH: {k.get('tarih')}\nBASLIK: {k['baslik']}\nURL: {k['url']}\n"
    mt.write_text(bas + "=" * 60 + "\n" + govde + "\n", encoding="utf-8")
    time.sleep(0.25)
    return "indi"


# ───────────────────────────── ana akış ─────────────────────────────
def calistir(kurumlar=None, yillar=None, yalniz_dizin=False, zorla=False, sessiz=False):
    """Dizini yenile, eksik belgeleri indir. Döner: {"yeni": [kimlik…], "hata": [metin…], "dizin": [kayıt…]}.
    Günlük güncelleme (guncelle.py) de bunu çağırır."""
    kurumlar = kurumlar or ["tcmb", "bddk", "spk"]
    yillar = yillar or list(range(BAS_YIL, dt.date.today().year + 1))
    for d in (HAM, METIN):
        d.mkdir(parents=True, exist_ok=True)
    eski = {k["id"]: k for k in json.loads(DIZIN.read_text(encoding="utf-8"))} if DIZIN.exists() else {}

    yeni_liste, hata = [], []
    for ad, f in [("tcmb", tcmb_dizin), ("bddk", bddk_dizin), ("spk", spk_dizin)]:
        if ad not in kurumlar:
            continue
        try:
            yeni_liste += f(yillar)
        except Exception as e:      # noqa: BLE001 — bir kurumun sitesi yanıt vermezse diğerleri sürsün
            hata.append(f"{ad.upper()} dizini okunamadı: {type(e).__name__}: {str(e)[:80]}")
    gor = dict(eski)
    ilk_kez = []
    for k in yeni_liste:
        if k["id"] in gor:
            for alan in ("baslik", "url", "pdf"):
                if k.get(alan):
                    gor[k["id"]][alan] = k[alan]
            if k.get("tarih") and not gor[k["id"]].get("tarih"):
                gor[k["id"]]["tarih"] = k["tarih"]
        else:
            gor[k["id"]] = k
            ilk_kez.append(k["id"])
    if not yalniz_dizin:
        # önbellek depoda tutulmaz: bulutta yalnız YENİ belgeler indirilir (eskilerin kr değeri dizinde kayıtlı)
        hedef = [k for k in gor.values() if k["kurum"].lower() in kurumlar
                 and (zorla or k.get("kr") is None or k["id"] in ilk_kez)]
        with ThreadPoolExecutor(4) as ex:
            son = list(ex.map(lambda k: isle(k, zorla), hedef))
        if not sessiz:
            print(f"belgeler: {son.count('indi')} indirildi · {son.count('var')} önbellekte · {son.count('hata')} hata")
        hata += [f"{k['id']}: {k.get('not')}" for k, s in zip(hedef, son) if s == "hata"]
    sirali = sorted(gor.values(), key=lambda k: (k.get("tarih") or "0000", k["id"]))
    DIZIN.write_text(json.dumps(sirali, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"yeni": ilk_kez, "hata": hata, "dizin": sirali}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kurum", choices=["tcmb", "bddk", "spk"], action="append")
    ap.add_argument("--yalniz-dizin", action="store_true")
    ap.add_argument("--yeni", action="store_true", help="yeni belgelerin kimliklerini 'YENI: <id>' satırlarıyla yazdır")
    ap.add_argument("--zorla", action="store_true", help="önbellekte olsa da yeniden indir")
    ap.add_argument("--yil", type=int, help="yalnız bu yılın listeleri (günlük koşuda hız için)")
    a = ap.parse_args()
    r = calistir(a.kurum, [a.yil] if a.yil else None, a.yalniz_dizin, a.zorla)
    from collections import Counter
    say = Counter((k["kurum"], k["tur"]) for k in r["dizin"])
    print("dizin:", len(r["dizin"]), "belge ·", ", ".join(f"{ku} {tu} {n}" for (ku, tu), n in sorted(say.items())))
    for h in r["hata"]:
        print("UYARI:", h)
    if a.yeni:
        for i in r["yeni"]:
            print("YENI:", i)
    print(f"yeni belge: {len(r['yeni'])}")
    return 1 if r["hata"] else 0


if __name__ == "__main__":
    sys.exit(main())
