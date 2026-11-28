#!/usr/bin/env python3
"""Düzenleme Zaman Çizelgesi — olay dosyası doğrulaması.

  python3 -I duzenleme/dogrula.py                      # tüm olay dosyaları
  python3 -I duzenleme/dogrula.py olaylar/tcmb_2026.json
  python3 -I duzenleme/dogrula.py --kapsam             # dizindeki her belge karara bağlanmış mı?
  python3 -I duzenleme/dogrula.py --paket tcmb 2026    # bir paketin (kurum, yıl) kapsamı

HATA (çıkış kodu 1): biçim, eksik alan, bilinmeyen kaynak, yinelenen kimlik, eksik kapsam.
UYARI: `alinti` kaynak metinde bulunamadı; özetteki bir sayı kaynak metinde yok (yanlış okuma ya da uydurma
olabilir — elle bakılır). Uyarılar yayını durdurmaz ama her biri gözden geçirilmelidir.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ortak as O  # noqa: E402

ZORUNLU = ("id", "kaynak", "tarih", "kurum", "konu", "onem", "baslik", "ozet", "detay", "alinti")
TARIH = re.compile(r"^\d{4}-\d{2}-\d{2}$")
AYLAR = "Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık"

# ── Türkçe sayı sözcükleri: "yüzde yirmisi" → 20, "iki yüz bin" → 200000 ──
BIRLER = {"sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9}
ONLAR = {"on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80, "doksan": 90}
CARPAN = {"yüz": 100, "bin": 1000, "milyon": 10 ** 6, "milyar": 10 ** 9, "trilyon": 10 ** 12}
_EKLER = ("", "i", "ı", "u", "ü", "si", "sı", "su", "sü", "e", "a", "ye", "ya", "in", "ın", "un", "ün", "nin", "nın",
          "inci", "ıncı", "uncu", "üncü", "nci", "ncı", "ncu", "ncü", "er", "ar", "şer", "şar", "de", "da", "den", "dan",
          "te", "ta", "ini", "ını", "unu", "ünü", "sini", "sını", "sine", "sına", "lik", "lık", "luk", "lük", "ü", "dür",
          "yi", "yı", "yu", "yü", "ni", "nı", "nu", "nü", "ne", "na", "nde", "nda", "nden", "ndan", "sinin", "sının",
          "sunun", "sünün", "inin", "ının", "unun", "ünün", "sinden", "sından", "ine", "ına", "una", "üne")
_SOZLUK = {**BIRLER, **ONLAR, **CARPAN}
_SIRALI = sorted(_SOZLUK, key=len, reverse=True)


def _parcala(tok):
    """Sayı sözcüğü mü? 'yirmisi' → ['yirmi'] · 'yüzyirmibin' → ['yüz','yirmi','bin'] (resmî metinler sayıyı
    bitişik yazar) · sayı değilse None. Sondaki çekim eki (_EKLER) yok sayılır."""
    t = tok.replace("İ", "i").replace("I", "ı").lower().replace("i̇", "i").strip("’'`.,;:()")
    t = re.split(r"[’']", t)[0]
    if t.startswith("dörd"):            # dört + ünlü: "dördü", "dörde"
        t = "dört" + t[4:]
    cikti, i = [], 0
    while i < len(t):
        for soz in _SIRALI:
            if t.startswith(soz, i):
                cikti.append(soz)
                i += len(soz)
                break
        else:
            return cikti if cikti and t[i:] in _EKLER else None
    return cikti or None


def sozcuk_sayilari(metin):
    """Metindeki sayı sözcüğü dizilerinin değerleri (küme)."""
    bulunan, dizi = set(), []

    def bitir():
        if not dizi:
            return
        toplam, parca = 0, 0
        for s in dizi:
            if s in BIRLER or s in ONLAR:
                parca += _SOZLUK[s]
            elif s == "yüz":
                parca = (parca or 1) * 100
            else:
                toplam += (parca or 1) * CARPAN[s]
                parca = 0
        bulunan.add(float(toplam + parca))
        for s in dizi:                  # tek tek sözcük değerleri de (dizinin parçası başka bir sayıya ait olabilir)
            bulunan.add(float(_SOZLUK[s]))
        dizi.clear()

    for tok in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşüâîû’']+", metin):
        if tok.lower() in ("yüzde", "binde", "onbinde"):     # oran belirteci: sayının parçası değil, diziyi böler
            bitir()
            continue
        p = _parcala(tok)
        if p is None:
            bitir()
        else:
            dizi.extend(p)
    bitir()
    return bulunan


SAYI = re.compile(r"(?<![\w/])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)")
CARP = {"bin": 1e3, "milyon": 1e6, "milyar": 1e9, "trilyon": 1e12}


def _oku(s):
    """'1.250,5' → 1250.5 · '37,5' → 37.5 · '0.25' → 0.25 · '500.000' → 500000"""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        return float(s.replace(".", "").replace(",", "."))
    return float(s.replace(",", "."))


def rakam_sayilari(metin, tarihleri_at=False):
    """Metindeki rakamla yazılmış sayılar; 'bin/milyon/milyar' çarpanlı karşılıkları da eklenir."""
    if tarihleri_at:
        metin = re.sub(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b", " ", metin)
        metin = re.sub(r"\b\d{1,2}\s+(%s)(\s+\d{4})?\b" % AYLAR, " ", metin)
        metin = re.sub(r"\b(%s)\s+\d{4}\b" % AYLAR, " ", metin)
        metin = re.sub(r"\b(19|20)\d{2}\b", " ", metin)                # tek başına yıllar
    cikti = []
    for m in SAYI.finditer(metin):
        try:
            v = _oku(m.group(1))
        except ValueError:
            continue
        ard = metin[m.end(): m.end() + 40].lower()
        ard = re.sub(r"^(\s*[/–-]\s*%?\d+(?:[.,]\d+)?)+", "", ard).strip()      # "10 / 40 / 80 milyon" → çarpan hepsine
        carpan = next((c for ad, c in CARP.items() if ard.startswith(ad)), None)
        cikti.append((v, v * carpan if carpan else None, m.group(1)))
    return cikti


def norm(s):
    s = s.replace("İ", "i").replace("I", "ı").lower()
    s = re.sub(r"[’‘`´']", "'", s)
    s = re.sub(r"[“”«»\"]", '"', s)
    s = re.sub(r"[‐‑–—-]\s*\n\s*", "", s)     # satır sonu tirelemesi
    return re.sub(r"\s+", " ", s).strip()


def olay_denetle(o, dizin, hata, uyari, dosya):
    kim = f"{dosya}:{o.get('id', '?')}"
    for a in ZORUNLU:
        if a not in o:
            hata.append(f"{kim}: '{a}' alanı yok")
            return
    if o["kurum"] not in O.KURUMLAR:
        hata.append(f"{kim}: kurum '{o['kurum']}' geçersiz")
    if o["konu"] not in O.KONULAR:
        hata.append(f"{kim}: konu '{o['konu']}' listede yok")
    if o["onem"] not in (1, 2, 3):
        hata.append(f"{kim}: önem 1-3 olmalı")
    for a in ("tarih", "yururluk"):
        v = o.get(a)
        if a == "yururluk" and v in (None, ""):
            continue
        if not isinstance(v, str) or not TARIH.match(v):
            hata.append(f"{kim}: {a} 'YYYY-AA-GG' değil ({v!r})")
    if isinstance(o.get("yururluk"), str) and isinstance(o.get("tarih"), str) and TARIH.match(o["yururluk"]) and o["yururluk"] < o["tarih"]:
        uyari.append(f"{kim}: yürürlük ({o['yururluk']}) duyuru tarihinden ({o['tarih']}) önce — null bırakılıp detayda yazılmalı")
    if not isinstance(o["baslik"], str) or not 12 <= len(o["baslik"]) <= 120:
        hata.append(f"{kim}: başlık uzunluğu {len(str(o['baslik']))} (12–120)")
    if re.search(r"(Basın Duyurusu|Basın Açıklaması|Kurul Kararı|Hk\.)\s*$", str(o["baslik"])):
        uyari.append(f"{kim}: başlık belge adı gibi — ne değiştiğini söylemeli: {o['baslik']!r}")
    if not isinstance(o["ozet"], str) or not 30 <= len(o["ozet"]) <= 400:
        hata.append(f"{kim}: özet uzunluğu {len(str(o['ozet']))} (30–400)")
    if not isinstance(o["detay"], list) or not 1 <= len(o["detay"]) <= 7 or not all(isinstance(d, str) and d.strip() for d in o["detay"]):
        hata.append(f"{kim}: detay 1–7 metin maddesi olmalı")
    elif any(len(d) > 300 for d in o["detay"]):
        hata.append(f"{kim}: detay maddesi 300 karakteri aşıyor")
    if not isinstance(o["kaynak"], list) or not o["kaynak"]:
        hata.append(f"{kim}: kaynak listesi boş")
        return
    kaynak_metni = ""
    for kid in o["kaynak"]:
        k = dizin.get(kid)
        if not k:
            hata.append(f"{kim}: kaynak '{kid}' dizinde yok")
            continue
        if k["kurum"] != o["kurum"]:
            uyari.append(f"{kim}: kaynak {kid} başka kurumun ({k['kurum']})")
        kaynak_metni += "\n" + (k.get("baslik") or "") + "\n" + O.metin_oku(kid)
        if k.get("tarih") and isinstance(o.get("tarih"), str) and TARIH.match(o["tarih"]):
            from datetime import date
            fark = abs((date.fromisoformat(o["tarih"]) - date.fromisoformat(k["tarih"])).days)
            if fark > 45:
                uyari.append(f"{kim}: olay tarihi {o['tarih']} ile belge tarihi {k['tarih']} arasında {fark} gün var")
    if len(kaynak_metni.strip()) < 100:
        uyari.append(f"{kim}: kaynak metni önbellekte yok — alıntı/sayı denetimi yapılamadı")
        return
    # alıntı kaynağa dayanıyor mu?
    nk, na = norm(kaynak_metni), norm(str(o["alinti"]))
    if not 40 <= len(na) <= 260:
        uyari.append(f"{kim}: alıntı uzunluğu {len(na)} (60–220 beklenir)")
    if na and na not in nk and re.sub(r"[\s\-‐‑–—]", "", na) not in re.sub(r"[\s\-‐‑–—]", "", nk):
        uyari.append(f"{kim}: ALINTI kaynakta bulunamadı: {o['alinti'][:90]!r}")
    # sayılar kaynağa dayanıyor mu?
    kaynak_sayi = set()
    for v, c, _ in rakam_sayilari(kaynak_metni):
        kaynak_sayi.add(round(v, 6))
        if c:
            kaynak_sayi.add(round(c, 6))
    kaynak_sayi |= {round(v, 6) for v in sozcuk_sayilari(kaynak_metni)}
    yazi = " ".join([o["baslik"], o["ozet"]] + [d for d in o["detay"] if isinstance(d, str)])
    eksik = []
    for v, c, ham in rakam_sayilari(yazi, tarihleri_at=True):
        aday = {round(v, 6)} | ({round(c, 6)} if c else set())
        # "500 bin" ↔ kaynakta 500.000; "%0,5" ↔ kaynakta "yarım"; binde/onbinde gösterimleri kapsam dışı
        if aday & kaynak_sayi:
            continue
        eksik.append(ham)
    if eksik:
        uyari.append(f"{kim}: SAYI kaynakta yok → {', '.join(dict.fromkeys(eksik))}  | {o['baslik'][:70]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dosya", nargs="*")
    ap.add_argument("--kapsam", action="store_true", help="dizindeki tüm belgeler karara bağlanmış mı")
    ap.add_argument("--paket", nargs=2, metavar=("KURUM", "YIL"), help="yalnız bu kurum-yıl için kapsam")
    ap.add_argument("--sessiz", action="store_true", help="uyarı ayrıntılarını yazma, yalnız sayılar")
    a = ap.parse_args()
    dizin = {k["id"]: k for k in O.dizin_oku()}
    dosyalar = [Path(d) if Path(d).exists() else O.KOK / d for d in a.dosya] or O.olay_dosyalari()
    hata, uyari, gorulen, karar = [], [], {}, {}
    n_olay = 0
    for f in dosyalar:
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:      # noqa: BLE001
            hata.append(f"{f.name}: JSON okunamadı — {e}")
            continue
        if not isinstance(v, dict) or not isinstance(v.get("olaylar"), list):
            hata.append(f"{f.name}: kökte 'olaylar' listesi yok")
            continue
        for o in v["olaylar"]:
            n_olay += 1
            if o.get("id") in gorulen:
                hata.append(f"{f.name}: kimlik yineleniyor: {o.get('id')} (ayrıca {gorulen[o.get('id')]})")
            gorulen[o.get("id")] = f.name
            olay_denetle(o, dizin, hata, uyari, f.name)
            for kid in o.get("kaynak") or []:
                karar[kid] = "olay"
        for e in v.get("elenen") or []:
            if not isinstance(e, dict) or "id" not in e or not e.get("neden"):
                hata.append(f"{f.name}: 'elenen' kaydı {{id, neden}} olmalı: {e!r}")
                continue
            if e["id"] not in dizin:
                hata.append(f"{f.name}: elenen '{e['id']}' dizinde yok")
            karar.setdefault(e["id"], "elendi")
    if a.kapsam or a.paket:
        eksik = []
        for k in dizin.values():
            if a.paket and (k["kurum"].lower() != a.paket[0].lower() or (k.get("tarih") or "")[:4] != a.paket[1]):
                continue
            if k["id"] in karar or O.baslik_eler_mi(k):
                continue
            eksik.append(k)
        if eksik:
            hata.append(f"KAPSAM: {len(eksik)} belge karara bağlanmamış")
            for k in eksik[:40]:
                hata.append(f"   eksik: {k['id']} · {k.get('tarih')} · {k['baslik'][:80]}")
    print(f"{len(dosyalar)} dosya · {n_olay} olay · {sum(1 for v in karar.values() if v == 'elendi')} elenen belge · "
          f"{len(hata)} hata · {len(uyari)} uyarı")
    for h in hata:
        print("HATA :", h)
    if not a.sessiz:
        for u in uyari:
            print("UYARI:", u)
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
