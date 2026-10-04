#!/usr/bin/env python3
"""Ayın Görünümü — rapor, site ve e-posta için kısa yorum (manşet + 5-7 madde).

Girdi: calc.D (son ay, önceki ay, 12 ay önce) → özet metin. ANTHROPIC_API_KEY varsa Claude yazar
(JSON şema), yoksa/arıza olursa veriden kural tabanlı maddeler üretilir. Çıktı: gorunum.json
{"baslik", "maddeler", "mod": "ai"|"kural", "donem"}  — rapor.py ve export_web.py okur.
Kullanım: python gorunum.py
"""
import json, os, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calc import D, LAST, GROUPS, GSHORT, at  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "gorunum.json"
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
MODEL = os.environ.get("HABER_MODEL", "claude-opus-5")


def tr(x, d=1):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def onceki_ay(d):
    import pandas as pd
    return (pd.Timestamp(d) - pd.offsets.MonthEnd(1))


def ozet_metni():
    import pandas as pd
    S = at("S"); P = at("S", onceki_ay(LAST))
    don = f"{AYLAR[LAST.month - 1]} {LAST.year}"
    L = [f"DÖNEM: {don} (BDDK Aylık Bülten)", "",
         "SEKTÖR (yıllık % büyüme; parantez içinde bir önceki aydaki yıllık büyüme):",
         f"- Toplam aktif {tr(S.aktif/1e6)} trilyon TL, yıllık %{tr(S.g_aktif)} (önceki ay %{tr(P.g_aktif)}); TP aktif %{tr(S.g_akTP)}, YP aktif (USD) %{tr(S.g_akYP_usd)}",
         f"- Canlı krediler {tr(S.canli/1e6)} trilyon; TP canlı kredi yıllık %{tr(S.g_canliTP)} (önceki ay %{tr(P.g_canliTP)}), 3 aylık yıllıklandırılmış %{tr(S.g3_canliTP)}, aylık %{tr(S.g1_canliTP)}; YP canlı kredi (USD) %{tr(S.g_canliYP_usd)}",
         f"- Tüketici kredileri+KK yıllık %{tr(S.g_tukKK)} (konut %{tr(S.g_konut)}, taşıt %{tr(S.g_tasit)}, ihtiyaç %{tr(S.g_ihtiyac)}, kredi kartı %{tr(S.g_kk)}); tüzel krediler %{tr(S.g_tuzel)} (KOBİ %{tr(S.g_kobi)}, ticari/kurumsal %{tr(S.g_ticKur)})",
         f"- Toplanan fonlar {tr(S.mevduat/1e6)} trilyon; TP mevduat yıllık %{tr(S.g_mvTP)} (önceki ay %{tr(P.g_mvTP)}), YP mevduat (USD) %{tr(S.g_mvYP_usd)}; TP ağırlığı %{tr(S.fonTPag)} (önceki ay %{tr(P.fonTPag)})",
         f"- NPL %{tr(S.npl, 2)} (önceki ay %{tr(P.npl, 2)}); tüketici NPL %{tr(S.nplTuk, 2)}, KOBİ NPL %{tr(S.nplKobi, 2)}; özel karşılık oranı %{tr(S.ozelKarsOran)}",
         f"- Net kâr yıl içi {tr(S.netKar/1e3)} milyar TL, yıllık %{tr(S.gy_netKar)}; aylık net kâr {tr(S.netKar_m/1e3)} milyar (önceki ay {tr(P.netKar_m/1e3)}); ROA %{tr(S.roa)}, ROE %{tr(S.roe)}, NIM %{tr(S.nim)} (önceki ay NIM %{tr(P.nim)}); gider/gelir %{tr(S.giderGelir)}",
         f"- Kredi getirisi %{tr(S.krediGetiri)}, fon maliyeti %{tr(S.fonMaliyet)}; SYR %{tr(S.syr)} (önceki ay %{tr(P.syr)}), çekirdek SYR %{tr(S.cekSyr)}; kaldıraç {tr(S.kaldirac)}x",
         "", "GRUPLAR (aktif büyümesi / TP canlı kredi büyümesi / NPL / ROE / SYR / aylık net kâr milyar TL):"]
    for g in GROUPS:
        if g == "S":
            continue
        a = at(g)
        L.append(f"- {GSHORT[g]}: %{tr(a.g_aktif)} / %{tr(a.g_canliTP)} / %{tr(a.npl, 2)} / %{tr(a.roe)} / %{tr(a.syr)} / {tr(a.netKar_m/1e3)}")
    return "\n".join(L), don


SISTEM = """Türkiye bankacılık sektörünü izleyen bir analistsin; ekordion.com.tr'nin aylık "Bankacılık Monitörü" \
raporunun "Ayın Görünümü" sayfasını yazıyorsun. Okuyucu bankacı ve sabit getirili masası çalışanı; sade ve \
rakamlı yaz. Sana BDDK Aylık Bülten verisinden türetilmiş özet rakamlar verilecek.

Görev: "baslik": ayın manşeti (tek satır, en çok 12 kelime, rakam içerebilir). "maddeler": 5-7 madde; her biri \
tek cümle (en çok 35 kelime), önem sırasıyla: kredi ivmesi (3 aylık yıllıklandırılmış ile 12 aylık farkı), \
fonlama ve TP ağırlığı/dolarizasyon, kârlılık (aylık net kâr, NIM, ROE yönü), aktif kalitesi (NPL yönü), sermaye, \
gruplar arası ayrışma (en hızlı/yavaş büyüyen, kârlılıkta öne çıkan). Verilmeyen bilgiyi uydurma, tahmin/yatırım \
tavsiyesi verme; "arttı/geriledi" ifadelerini verilen önceki ay karşılaştırmasına dayandır."""

SEMA = {"type": "object", "properties": {"baslik": {"type": "string"}, "maddeler": {"type": "array", "items": {"type": "string"}}},
        "required": ["baslik", "maddeler"], "additionalProperties": False}


def ai_yaz(metin):
    import anthropic
    client = anthropic.Anthropic()
    istek = dict(model=MODEL, max_tokens=2500, system=SISTEM, messages=[{"role": "user", "content": metin}],
                 output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SEMA}})
    try:
        r = client.beta.messages.create(betas=["server-side-fallback-2026-06-01"], fallbacks=[{"model": "claude-opus-4-8"}], **istek)
    except anthropic.BadRequestError:
        r = client.messages.create(**istek)
    if r.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"yanıt tamamlanmadı ({r.stop_reason})")
    v = json.loads(next(b.text for b in r.content if b.type == "text"))
    print(f"  Claude ({r.model}): {len(v['maddeler'])} madde · girdi {r.usage.input_tokens} / çıktı {r.usage.output_tokens} token")
    return v


def kural_tabanli():
    S = at("S"); P = at("S", onceki_ay(LAST))
    yon = lambda a, b, d=1: "yükseldi" if round(a - b, d) > 0 else ("geriledi" if round(a - b, d) < 0 else "yatay kaldı")
    ivme = "hızlanıyor" if S.g3_canliTP > S.g_canliTP else "yavaşlıyor"
    gr = [(g, at(g).g_aktif) for g in GROUPS if g != "S"]
    hizli, yavas = max(gr, key=lambda x: x[1]), min(gr, key=lambda x: x[1])
    roe = [(g, at(g).roe) for g in GROUPS if g != "S"]
    en_karli = max(roe, key=lambda x: x[1])
    m = [
        f"Sektör aktifleri yıllık %{tr(S.g_aktif)} büyüdü; TP canlı krediler yıllık %{tr(S.g_canliTP)}, 3 aylık yıllıklandırılmış %{tr(S.g3_canliTP)} ile kredi ivmesi {ivme}.",
        f"TP mevduat yıllık %{tr(S.g_mvTP)}, YP mevduat dolar bazında %{tr(S.g_mvYP_usd)} büyüdü; toplanan fonlarda TP ağırlığı %{tr(S.fonTPag)} ile önceki aya göre {yon(S.fonTPag, P.fonTPag)}.",
        f"Aylık net kâr {tr(S.netKar_m/1e3)} milyar TL (önceki ay {tr(P.netKar_m/1e3)}); yıl içi net kâr {tr(S.netKar/1e3)} milyar TL ile yıllık %{tr(S.gy_netKar)}; ROE %{tr(S.roe)}, NIM %{tr(S.nim)} ile önceki aya göre {yon(S.nim, P.nim, 2)}.",
        f"NPL oranı %{tr(S.npl, 2)} ile önceki aya göre {yon(S.npl, P.npl, 2)}; tüketici NPL %{tr(S.nplTuk, 2)}, KOBİ NPL %{tr(S.nplKobi, 2)}; özel karşılık oranı %{tr(S.ozelKarsOran)}.",
        f"Standart SYR %{tr(S.syr)} (çekirdek %{tr(S.cekSyr)}) ile önceki aya göre {yon(S.syr, P.syr)}; kaldıraç {tr(S.kaldirac)} kat.",
        f"Gruplar arasında aktif büyümesinde {GSHORT[hizli[0]]} %{tr(hizli[1])} ile önde, {GSHORT[yavas[0]]} %{tr(yavas[1])} ile geride; özkaynak kârlılığında {GSHORT[en_karli[0]]} %{tr(en_karli[1])} ile ilk sırada.",
    ]
    baslik = f"Krediler %{tr(S.g_canliTP, 0)} büyüdü, NPL %{tr(S.npl, 2)}, ROE %{tr(S.roe, 0)}"
    return {"baslik": baslik, "maddeler": m}


def main():
    metin, don = ozet_metni()
    mod, v = "kural", None
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        try:
            v = ai_yaz(metin); mod = "ai"
        except Exception as e:
            print(f"  ~ Claude başarısız ({type(e).__name__}: {str(e)[:80]}) — kural tabanlı yoruma düşülüyor")
    if v is None:
        v = kural_tabanli()
    kayit = {"donem": LAST.strftime("%Y-%m"), "donem_ad": don, "mod": mod, "baslik": v["baslik"].strip(),
             "maddeler": [x.strip() for x in v["maddeler"] if x.strip()][:7]}
    OUT.write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Ayın Görünümü ({mod}): {kayit['baslik']}")
    for x in kayit["maddeler"]:
        print("  •", x)


if __name__ == "__main__":
    main()
