"""Düzenleme Zaman Çizelgesi — ortak tanımlar: konu/önem listeleri, başlık süzgeci, dosya okuma."""
import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parent
DIZIN = KOK / "dizin.json"
OLAYLAR = KOK / "olaylar"
METIN = KOK / "onbellek" / "metin"

KURUMLAR = ("TCMB", "BDDK", "SPK")
KONULAR = {
    "faiz": "Faiz ve likidite",
    "zk": "Zorunlu karşılık",
    "kredi": "Krediler ve kartlar",
    "mevduat": "Mevduat ve KKM",
    "doviz": "Döviz ve rezerv",
    "sermaye": "Sermaye ve muhasebe",
    "piyasa": "Pay ve borçlanma piyasası",
    "fon": "Fonlar ve yatırım kuruluşları",
    "kripto": "Kripto varlıklar",
    "odeme": "Ödeme sistemleri",
    "kurum": "Kuruluş ve izinler",
    "diger": "Diğer",
}

# Başlığa bakarak GÜVENLE elenebilen belgeler (içerik okunmaz). Kalıplar bilerek dar tutulur: kararsız olan
# her belge okunur. (kurum, tür süzgeci ya da None, başlık kalıbı, neden)
_BASLIK_SUZGEC = [
    ("TCMB", None, r"Para Politikası Kurulu Toplantı Özeti", "PPK toplantı özeti (karar ayrı duyuruda)"),
    ("TCMB", None, r"Enflasyon Raporu.*(Bilgilendirme Toplantısı|Yayım Tarihi)", "rapor toplantısı / yayım tarihi duyurusu"),
    ("TCMB", None, r"Olağan Genel Kurul", "genel kurul duyurusu"),
    ("TCMB", None, r"Sertifika Değişikliği", "internet sitesi duyurusu"),
    ("TCMB", None, r"Banknot", "banknot tedavülü"),
    ("TCMB", None, r"Açık Mektup", "hükûmete açık mektup"),
    ("TCMB", None, r"Forumu Toplantısı|Konferans|Konseyi?\b.*Toplantı|Çalıştay", "toplantı / konferans duyurusu"),
    ("SPK", "basin", r"Sınav|Başsağlığı|Ziyaret|Personel|Yarışma|Lisanslama|Mülakat|Tören|Panel|Konferans|Çalıştay|Zirve|Heyet",
     "etkinlik / personel duyurusu"),
    ("BDDK", "basin", r"Sınav|Personel|Başsağlığı|Faaliyet Raporu", "etkinlik / personel / rapor duyurusu"),
]
# BDDK Kurul kararlarında banka DIŞI tek kuruluşa ilişkin izin/iptal (banka kararları olaydır, elenmez)
_BDDK_TEK_KURULUS = re.compile(
    r"(Değerleme|Bağımsız Denetim|Denetim ve|Derecelendirme|Faktoring|Finansman|Varlık Yönetim|Finansal Kiralama|"
    r"Elektronik Para|Ödeme Hizmetleri|Ödeme Kuruluşu|Müşavirlik|Holding)[^.]*A\.\s?Ş", re.I)
_BANKA = re.compile(r"Bank(ası)?\b|Bank A\.\s?Ş|Katılım", re.I)


def baslik_eler_mi(k):
    """Dizin kaydı başlığından elenebiliyorsa nedeni döndür, değilse None."""
    # kr None = belge henüz indirilemedi (geçici ağ hatası): elenmiş sayma, sonraki koşuda yeniden denenir
    if k.get("tur") == "bulten" and k.get("kr") is not None and k["kr"] < 40:
        return "bültende duyuru / ilke kararı bölümü yok"
    b = k.get("baslik") or ""
    for kurum, tur, kalip, neden in _BASLIK_SUZGEC:
        if k["kurum"] == kurum and (tur is None or k.get("tur") == tur) and re.search(kalip, b, flags=re.I):
            return neden
    if k["kurum"] == "BDDK" and k.get("tur") in ("karar", "karar_rg"):
        if _BDDK_TEK_KURULUS.search(b) and not _BANKA.search(b) and re.search(r"izn|yetki|iptal", b, flags=re.I):
            return "banka dışı tek kuruluşa ilişkin izin / iptal"
        if re.search(r"adet şirket", b, flags=re.I) and re.search(r"değerleme|denetim", b, flags=re.I):
            return "değerleme / denetim şirketi yetkilendirmesi"
    return None


def dizin_oku():
    return json.loads(DIZIN.read_text(encoding="utf-8"))


def metin_oku(kimlik):
    """Önbellekteki belge metni (başlık bloğu hariç gövde). Yoksa boş."""
    f = METIN / f"{kimlik}.txt"
    if not f.exists():
        return ""
    t = f.read_text(encoding="utf-8")
    i = t.find("=" * 60)
    return t[i + 61:] if i >= 0 else t


def olay_dosyalari():
    return sorted(p for p in OLAYLAR.glob("*.json") if not p.name.startswith("_"))


def kaynak_etiketi(k):
    """Dizin kaydı → okura gösterilen kaynak adı."""
    tr = f"{k['tarih'][8:10]}.{k['tarih'][5:7]}.{k['tarih'][:4]}" if k.get("tarih") else ""
    if k["kurum"] == "TCMB":
        return f"TCMB Basın Duyurusu {k.get('no', '')}".strip()
    if k["kurum"] == "BDDK":
        if k["tur"] in ("karar", "karar_rg"):
            return f"BDDK Kurul Kararı {k.get('no', '')}".strip() + (f" ({tr})" if tr else "")
        return ("BDDK Mevzuat Duyurusu" if k["tur"] == "mevzuat_duyuru" else "BDDK Basın Açıklaması") + (f" ({tr})" if tr else "")
    if k["tur"] == "bulten":
        return f"SPK Bülteni {k.get('no') or ''}".strip()
    return "SPK Basın Duyurusu" + (f" ({tr})" if tr else "")
