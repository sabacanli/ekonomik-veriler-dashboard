#!/usr/bin/env python3
"""Haftaya Bakış — Pazar akşamı haftalık bülteni: geçen haftaya bakış + gelecek hafta neler bekliyor.

Girdiler (hepsi depoda hazır):
  site/data/haber/<gün>.json   haftanın günlük seçkileri (günün özeti maddeleri + öne çıkan haberler)
  site/data/home.json          modül özet kartları → "bu hafta açıklanan veriler" (haftalık durum dosyasıyla)
  site/data/piyasa.json        günün rakamları + haftalık / aylık / yılbaşı değişimler (piyasa_fetch.py)
  site/data/takvim.json        gelecek haftanın olayları (takvim_uret.py)
Çıktı: site/data/haber/hafta-YYYY-Www.json + index.json "haftalik" listesi; e-posta: bulten_gonder.py --tur haftalik.

Claude (ANTHROPIC_API_KEY varsa) haftanın özetini, piyasa yorumunu ve gelecek hafta yorumunu yazar;
yoksa günlük özetlerden derleme yapılır (mod: "derleme"). Yapay zekâ hatası akışı bozmaz.

Kullanım: python haberler/hafta_ozeti.py [--hafta 2026-W39] [--bulten]
  --bulten: bülten koşusu — "bu hafta açıklanan veriler" durum dosyası bu koşuda ilerletilir.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import haber_topla as ht  # noqa: E402  (ortak yardımcılar: veri_bolumu, TR, MODEL, OUT_DIR)

BASE = ht.BASE
OUT_DIR = ht.OUT_DIR
DURUM_HAFTA = OUT_DIR / "veri_durum_hafta.json"
TR = ht.TR
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
HAFTA_ARSIV = 26


def aralik_yazi(bas, son):
    if bas.month == son.month:
        return f"{bas.day}–{son.day} {AYLAR[son.month - 1]} {son.year}"
    return f"{bas.day} {AYLAR[bas.month - 1]} – {son.day} {AYLAR[son.month - 1]} {son.year}"


def hafta_gunleri(hafta_id):
    yil, w = hafta_id.split("-W")
    pzt = dt.date.fromisocalendar(int(yil), int(w), 1)
    return [pzt + dt.timedelta(days=i) for i in range(7)]


def gunluk_topla(gunler):
    """Haftanın günlük dosyaları → (gün → özet maddeleri), öne çıkan haberler (önem ≥ 4)."""
    ozetler, haberler = {}, []
    for g in gunler:
        fp = OUT_DIR / f"{g.isoformat()}.json"
        if not fp.exists():
            continue
        D = json.loads(fp.read_text(encoding="utf-8"))
        if D.get("ozet"):
            ozetler[g.isoformat()] = D["ozet"]
        for k in D.get("kategoriler", []):
            for h in k["haberler"]:
                if int(h.get("onem") or 0) >= 4:
                    haberler.append({"gun": g.isoformat(), "kategori": k["ad"], "baslik": h["baslik"], "link": h["link"],
                                     "kaynak": h["kaynak"], "ozet": h.get("ozet"), "onem": int(h["onem"]),
                                     "kaynak_sayisi": 1 + len(h.get("diger") or [])})
    haberler.sort(key=lambda h: (-h["onem"], -h["kaynak_sayisi"], h["gun"]))
    return ozetler, haberler


def gelecek_hafta(gunler_sonraki):
    try:
        ol = json.loads(ht.TAKVIM_JSON.read_text(encoding="utf-8"))["olaylar"]
    except Exception:
        return []
    bas, son = gunler_sonraki[0].isoformat(), gunler_sonraki[-1].isoformat()
    return [o for o in ol if bas <= o["tarih"] <= son]


SISTEM = """Türkiye'de bir bankanın sabit getirili menkul kıymetler masası için Pazar akşamı yayımlanan haftalık \
finans bülteninin editörüsün. Sana geçen haftanın günlük özetleri ve öne çıkan haberleri, hafta içinde açıklanan \
verilerin Ekordion özetleri, piyasa tablosu (haftalık/aylık/yılbaşı değişimler) ve gelecek haftanın takvimi verilecek.

Görevin (Türkçe, sade, rakamları koru, başlık kopyalama, verilmeyen bilgiyi uydurma):
1. "baslik": haftanın manşeti — tek satır, en çok 12 kelime.
2. "hafta_ozeti": geçen haftanın en önemli 5-7 gelişmesi; her madde tek cümle, önem sırasıyla (kronoloji değil). \
Aynı gelişmeyi anlatan haberleri tek maddede birleştir.
3. "piyasa_yorumu": 2-3 cümle; tablodaki HAFTALIK değişimlere dayanarak kur, faiz eğrisi (2-10 yıl), BIST ve \
küresel (DXY, ABD 10 yıllık, petrol, altın) için haftanın resmini çiz.
4. "gelecek_hafta": takvimdeki olaylardan masayı en çok ilgilendiren 3-5 tanesi için birer madde: gün adıyla \
başla, ne açıklanacağını ve neden önemli olduğunu tek cümlede söyle. Takvimde olmayan olay ekleme."""

SEMA = {
    "type": "object",
    "properties": {
        "baslik": {"type": "string"},
        "hafta_ozeti": {"type": "array", "items": {"type": "string"}},
        "piyasa_yorumu": {"type": "string"},
        "gelecek_hafta": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["baslik", "hafta_ozeti", "piyasa_yorumu", "gelecek_hafta"],
    "additionalProperties": False,
}


def ai_yaz(girdi):
    import anthropic
    client = anthropic.Anthropic()
    istek = dict(model=ht.MODEL, max_tokens=6000, system=SISTEM,
                 messages=[{"role": "user", "content": girdi}],
                 output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SEMA}})
    try:
        r = client.beta.messages.create(betas=["server-side-fallback-2026-06-01"],
                                        fallbacks=[{"model": "claude-opus-4-8"}], **istek)
    except anthropic.BadRequestError as e:
        print(f"  ~ yedekli çağrı reddedildi ({e.message}) — yedeksiz deneniyor")
        r = client.messages.create(**istek)
    if r.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"yanıt tamamlanmadı (stop_reason={r.stop_reason})")
    v = json.loads(next(b.text for b in r.content if b.type == "text"))
    print(f"  Claude ({r.model}): {len(v['hafta_ozeti'])} özet · {len(v['gelecek_hafta'])} gelecek hafta maddesi · "
          f"girdi {r.usage.input_tokens} / çıktı {r.usage.output_tokens} token")
    return v


def girdi_metni(gunler, ozetler, haberler, veriler, piyasa, takvim):
    S = [f"HAFTA: {aralik_yazi(gunler[0], gunler[-1])}", "", "GÜNLÜK ÖZETLER:"]
    for g, maddeler in ozetler.items():
        d = dt.date.fromisoformat(g)
        S.append(f"[{GUNLER[d.weekday()]} {d.day:02d}.{d.month:02d}]")
        S += [f"  - {m}" for m in maddeler]
    S += ["", "ÖNE ÇIKAN HABERLER (önem 4-5):"]
    S += [f"  - ({h['gun'][8:]}.{h['gun'][5:7]}, {h['kategori']}) {h['baslik']}" + (f" — {h['ozet']}" if h.get("ozet") else "")
          for h in haberler[:30]]
    S += ["", "BU HAFTA AÇIKLANAN VERİLER (Ekordion özetleri):"]
    S += [f"  - {v['baslik']}: {v['ozet']}" for v in veriler] or ["  (yok)"]
    S += ["", "PİYASA TABLOSU (son değer; günlük / haftalık / aylık / yılbaşından beri % değişim; faizlerde haftalık puan):"]
    for s in (piyasa or {}).get("satirlar", []):
        S.append(f"  - {s['ad']}: {s['deger']} {s.get('birim', '')} | gün {s.get('degisim_pct')}% | hafta {s.get('hafta_pct')}%"
                 + (f" ({s.get('hafta_puan')} puan)" if s.get("hafta_puan") is not None else "")
                 + f" | ay {s.get('ay_pct')}% | yılbaşı {s.get('ytd_pct')}%")
    S += ["", "GELECEK HAFTANIN TAKVİMİ:"]
    for o in takvim:
        d = dt.date.fromisoformat(o["tarih"])
        S.append(f"  - {GUNLER[d.weekday()]} {d.day:02d}.{d.month:02d} {o.get('saat') or ''} · {o['kurum']} · {o['baslik']}"
                 + (f" ({o['donem']})" if o.get("donem") else "") + f" · önem {o['onem']}")
    return "\n".join(S)


def derleme(ozetler, haberler, takvim):
    """Yapay zekâ yoksa: günlük özetlerin ilk iki maddesi + takvimin önemli olayları."""
    hafta_ozeti = [m for maddeler in ozetler.values() for m in maddeler[:2]][:7]
    gelecek = []
    for o in takvim:
        if o["onem"] >= 3 or o["kurum"] == "Hazine":
            d = dt.date.fromisoformat(o["tarih"])
            gelecek.append(f"{GUNLER[d.weekday()]}: {o['baslik']}" + (f" ({o['donem']})" if o.get("donem") else ""))
    baslik = (re.split(r"[:;]", hafta_ozeti[0])[0].strip()[:100] if hafta_ozeti else "Haftaya bakış")
    return {"baslik": baslik, "hafta_ozeti": hafta_ozeti, "piyasa_yorumu": "", "gelecek_hafta": gelecek[:5]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hafta", help="ISO hafta, ör. 2026-W39 (varsayılan: içinde bulunulan hafta)")
    ap.add_argument("--bulten", action="store_true", help="bülten koşusu: haftalık veri durumunu ilerlet")
    a = ap.parse_args()
    simdi = dt.datetime.now(TR)
    yil, w, _ = simdi.date().isocalendar()
    hafta_id = a.hafta or f"{yil}-W{w:02d}"
    gunler = hafta_gunleri(hafta_id)
    sonraki = [g + dt.timedelta(days=7) for g in gunler]
    print(f"Haftaya Bakış — {hafta_id}: {aralik_yazi(gunler[0], gunler[-1])} → gelecek hafta {aralik_yazi(sonraki[0], sonraki[-1])}")

    ozetler, haberler = gunluk_topla(gunler)
    veriler = ht.veri_bolumu(a.bulten, DURUM_HAFTA)
    piyasa = ht.piyasa_bolumu()
    takvim = gelecek_hafta(sonraki)
    print(f"  günlük özet: {len(ozetler)} gün · öne çıkan haber: {len(haberler)} · veri: {len(veriler)} modül · "
          f"piyasa: {len((piyasa or {}).get('satirlar', []))} satır · gelecek hafta: {len(takvim)} olay")
    if not ozetler and not haberler:
        print("HATA: bu haftaya ait günlük gündem dosyası yok", file=sys.stderr)
        sys.exit(1)

    mod, yazi = "derleme", None
    if ht.ai_kullanilabilir():
        try:
            yazi = ai_yaz(girdi_metni(gunler, ozetler, haberler, veriler, piyasa, takvim))
            mod = "ai"
        except Exception as e:
            print(f"  ~ Claude başarısız ({type(e).__name__}: {str(e)[:80]}) — derleme moduna düşülüyor")
    if yazi is None:
        yazi = derleme(ozetler, haberler, takvim)

    kayit = {
        "hafta": hafta_id, "baslangic": gunler[0].isoformat(), "bitis": gunler[-1].isoformat(),
        "aralik": aralik_yazi(gunler[0], gunler[-1]), "sonraki_aralik": aralik_yazi(sonraki[0], sonraki[-1]),
        "updated": simdi.strftime("%d.%m.%Y %H:%M"), "mod": mod,
        "baslik": yazi["baslik"].strip(), "hafta_ozeti": [m.strip() for m in yazi["hafta_ozeti"] if m.strip()][:7],
        "piyasa_yorumu": yazi.get("piyasa_yorumu", "").strip(),
        "gelecek_hafta": [m.strip() for m in yazi["gelecek_hafta"] if m.strip()][:5],
        "one_cikan": haberler[:12], "veriler": veriler, "piyasa": piyasa, "takvim": takvim,
        "gunluk_ozetler": ozetler,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"hafta-{hafta_id}.json").write_text(json.dumps(kayit, ensure_ascii=False, separators=(",", ":")),
                                                    encoding="utf-8")
    # index.json: haftalık liste (yeniden eskiye), eski haftalar temizlenir
    haftalar = sorted((p.stem[6:] for p in OUT_DIR.glob("hafta-20??-W??.json")), reverse=True)
    for eski in haftalar[HAFTA_ARSIV:]:
        (OUT_DIR / f"hafta-{eski}.json").unlink()
    liste = []
    for hid in haftalar[:HAFTA_ARSIV]:
        try:
            d = json.loads((OUT_DIR / f"hafta-{hid}.json").read_text(encoding="utf-8"))
            liste.append({"id": hid, "aralik": d["aralik"], "baslik": d["baslik"]})
        except Exception:
            pass
    idx_fp = OUT_DIR / "index.json"
    idx = json.loads(idx_fp.read_text(encoding="utf-8")) if idx_fp.exists() else {}
    idx["haftalik"] = liste
    idx_fp.write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  manşet: {kayit['baslik']}")
    print(f"Kaydedildi: site/data/haber/hafta-{hafta_id}.json (mod: {mod}) + index.json")
    print("BAŞARILI")


if __name__ == "__main__":
    main()
