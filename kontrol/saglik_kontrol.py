#!/usr/bin/env python3
"""ekordion sağlık kontrolü — otomasyonlar çalıştı mı, site güncel mi?

Sabah kontrolcüsü (Claude zamanlanmış görevi "ekordion-sabah-kontrol") her hafta içi sabah bu betiği çalıştırır; elle de
çalıştırılabilir. Hiçbir şeyi DEĞİŞTİRMEZ (yalnız okur; tek yazdığı dosya kendi durum kaydı kontrol/durum.json).

Neden var: Kasım 2026'da bir haftada dört arıza sessizce oldu — bülten iki gün gitmedi (site yayın adımı düşünce e-posta
atlanıyordu), KAP zamanlayıcısı hiç tetiklenmedi (launchd "Month" tuzağı), KAP kontrolü rapor yükleyip üç gün yayımlayamadı
(home.json çakışması), site yayını iki kez düştü. Hepsi ancak biri bakınca fark edildi.

Baktıkları (pencere = son kontrolden bugüne; ilk çalıştırmada 26 saat, Pazartesi 74 saat):
  1. GitHub Actions koşuları (anahtarsız, herkese açık API): başarısız koşular; her hafta içi sabah bülteni ve Pazar akşamı
     "Haftaya Bakış" koşusu başlamış mı, e-posta adımı başarılı mı; haftalık veri güncellemesi çalışıyor mu.
  2. Canlı site: erişilebilir mi; depodaki son sürümle aynı mı (yayın düşmüşse geride kalır); bugünkü gündem sayfası var mı.
  3. Yerel depo: gönderilmemiş eski commit, yarım kalmış rebase/birleştirme, günlerdir bekleyen değişiklik.
  4. Yerel zamanlanmış işler (launchd): yüklü mü; KAP kontrolü (rapor aylarında) bugün çalıştı mı, günlüğünde uyarı var mı,
     yayın bekleyen ya da doğrulamadan geçemeyen rapor var mı; BDDK haftalık verisi beklenen haftada mı.

Kullanım:
  python3 kontrol/saglik_kontrol.py              # denetle, raporu yaz, durum kaydını ilerlet
  python3 kontrol/saglik_kontrol.py --kuru       # durum kaydını ilerletme (deneme)
  python3 kontrol/saglik_kontrol.py --geri 168   # pencereyi elle ver (saat) — ör. son bir haftayı yeniden tara
  python3 kontrol/saglik_kontrol.py --json       # makinece okunur çıktı
  python3 kontrol/saglik_kontrol.py --bildir     # sorun varsa masaüstü bildirimi de göster (sabah kontrolcüsü böyle çağırır)
Çıkış kodu: 0 = sorun yok (uyarı olabilir) · 1 = sorun var.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
TR = ZoneInfo("Europe/Istanbul")
API = "https://api.github.com/repos/sabacanli/ekonomik-veriler-dashboard"
SITE = "https://ekordion.com.tr"
DURUM = REPO / "kontrol" / "durum.json"
LOG_KAP = Path.home() / "Library" / "Logs" / "ekordion-kap.log"
LOG_BDDK = Path.home() / "Library" / "Logs" / "ekordion-bddk.log"
LAUNCHD = ["com.ekordion.kap", "com.ekordion.bddk"]
KAP_AYLARI = (2, 5, 8, 11)            # banka_kap_otomatik.sh yalnız bu aylarda çalışır
YAYINLAYANLAR = ("Site Yayınla", "Finans Gündemi", "Haftalık Veri Güncelleme", "Bankacılık Monitörü")
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

bulgular = []   # {"duzey": "sorun" | "uyari" | "bilgi", "baslik": …, "ayrinti": …, "oneri": …}


def ekle(duzey, baslik, ayrinti="", oneri=""):
    bulgular.append({"duzey": duzey, "baslik": baslik, "ayrinti": ayrinti, "oneri": oneri})


def simdi():
    return dt.datetime.now(TR)


def tr_saat(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TR)


def al(url, zaman=30):
    ek = ("&" if "?" in url else "?") + f"x={int(time.time() * 1000)}" if url.startswith(SITE) else ""
    istek = urllib.request.Request(url + ek, headers={"User-Agent": "ekordion-kontrol", "Accept": "application/vnd.github+json",
                                                      "Cache-Control": "no-cache"})
    with urllib.request.urlopen(istek, timeout=zaman) as r:
        return r.read().decode("utf-8")


def gh(yol):
    return json.loads(al(API + yol))


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def log_satirlari(yol, t0):
    """Günlükteki '[GG.AA.YYYY SS:DD:SS] …' satırlarından t0'dan yeni olanlar: [(zaman, metin)]."""
    out = []
    try:
        metin = yol.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for s in metin.splitlines():
        m = re.match(r"^\[(\d{2})\.(\d{2})\.(\d{4}) (\d{2}):(\d{2}):(\d{2})\] (.*)$", s)
        if not m:
            continue
        g, a, y, sa, dk, sn = (int(x) for x in m.groups()[:6])
        z = dt.datetime(y, a, g, sa, dk, sn, tzinfo=TR)
        if z >= t0:
            out.append((z, m.group(7)))
    return out


# ───────────────────────────── 1. GitHub Actions ─────────────────────────────
def adimlar(run_id):
    """Koşunun ilk işinin adımları ve hata iletileri: ({adım adı: sonuç}, [ileti])."""
    try:
        isler = gh(f"/actions/runs/{run_id}/jobs")["jobs"]
    except Exception:
        return {}, []
    if not isler:
        return {}, []
    ad = {s["name"]: s["conclusion"] for s in isler[0].get("steps", [])}
    iletiler = []
    try:
        for a in gh(f"/check-runs/{isler[0]['id']}/annotations"):
            if a.get("annotation_level") == "failure":
                iletiler.append((a.get("message") or "").split("\n")[0][:220])
    except Exception:
        pass
    return ad, list(dict.fromkeys(iletiler))[:2]


def kontrol_github(t0, n):
    try:
        kosular = gh("/actions/runs?per_page=100")["workflow_runs"]
    except urllib.error.HTTPError as e:
        ekle("uyari", "GitHub koşuları denetlenemedi", f"GitHub API HTTP {e.code} (saatlik anahtarsız sınır dolmuş olabilir)",
             "Bir saat sonra yeniden çalıştırın.")
        return
    except Exception as e:
        ekle("uyari", "GitHub koşuları denetlenemedi", f"{type(e).__name__}: {str(e)[:120]}", "Ağ bağlantısını kontrol edin.")
        return
    for x in kosular:
        x["_t"] = tr_saat(x["created_at"])
    basarili_yayin = [x["_t"] for x in kosular if x["conclusion"] == "success" and x["name"].startswith(YAYINLAYANLAR)]

    # 1a. bülten beklentileri: hafta içi 07:50 günlük, Pazar 19:00 haftalık (Cloudflare tetiği → workflow_dispatch)
    bulten_tamam = set()   # e-postası gittiği doğrulanan koşu kimlikleri
    gun = max(t0.date(), n.date() - dt.timedelta(days=6))
    while gun <= n.date():
        if gun.weekday() <= 4:
            tur, bas, son, vade = "Günlük bülten", dt.time(7, 30), dt.time(9, 30), dt.time(8, 25)
        elif gun.weekday() == 6:
            tur, bas, son, vade = "Haftaya Bakış bülteni", dt.time(18, 30), dt.time(20, 30), dt.time(19, 35)
        else:
            gun += dt.timedelta(days=1); continue
        vade_z = dt.datetime.combine(gun, vade, tzinfo=TR)
        if vade_z < t0 or vade_z > n:      # önceki kontrolde bakıldı ya da henüz vakti gelmedi
            gun += dt.timedelta(days=1); continue
        ad = f"{gun:%d.%m.%Y} {GUNLER[gun.weekday()]} · {tur}"
        aday = [x for x in kosular if x["name"].startswith("Finans Gündemi") and x["event"] == "workflow_dispatch"
                and x["_t"].date() == gun and bas <= x["_t"].time() <= son]
        if not aday:
            ekle("sorun", f"{ad}: koşu hiç başlamadı",
                 "Cloudflare tetiği GitHub'da koşu başlatmamış (07:50 / Pazar 19:00). Olası neden: Cloudflare Worker durmuş ya da "
                 "GitHub erişim anahtarının (ekordion-gundem-tetik) süresi dolmuş.",
                 "Bülten gönderilmedi. GitHub → Actions → Finans Gündemi (günlük) → Run workflow ile elle başlatılabilir.")
        else:
            x = max(aday, key=lambda k: k["_t"])
            if x["status"] != "completed":
                ekle("bilgi", f"{ad}: koşu sürüyor ({x['_t']:%H:%M} başladı)")
            else:
                ad_son, iletiler = adimlar(x["id"])
                eposta = next((v for k, v in ad_son.items() if "E-posta" in k), None)
                if eposta == "success" and x["conclusion"] == "success":
                    bulten_tamam.add(x["id"])
                    ekle("bilgi", f"{ad}: gönderildi ({x['_t']:%H:%M} koşusu)")
                elif eposta == "success":
                    bulten_tamam.add(x["id"])
                    ekle("uyari", f"{ad}: e-posta gitti ama koşu başarısız bitti",
                         "Başarısız adım: " + ", ".join(k for k, v in ad_son.items() if v == "failure") + (" · " + iletiler[0] if iletiler else ""),
                         "Site yayını düşmüş olabilir; aşağıdaki site denetimine bakın.")
                else:
                    ekle("sorun", f"{ad}: e-posta GÖNDERİLMEDİ",
                         f"Koşu sonucu: {x['conclusion']} · e-posta adımı: {eposta or 'yok'} · başarısız adım: "
                         + (", ".join(k for k, v in ad_son.items() if v == "failure") or "—") + (" · " + iletiler[0] if iletiler else ""),
                         "İstenirse aynı gün: Actions → Finans Gündemi (günlük) → Run workflow → tür gunluk/haftalik, bülten evet, "
                         "gündemi yeniden üret hayir. Kullanıcı istemeden gönderilmez.")
        gun += dt.timedelta(days=1)

    # 1b. penceredeki başarısız koşular (bülten koşuları yukarıda ele alındı)
    sayac = 0
    for x in sorted(kosular, key=lambda k: k["_t"]):
        if x["_t"] < t0 or x["conclusion"] not in ("failure", "timed_out", "startup_failure"):
            continue
        if x["id"] in bulten_tamam:
            continue
        if x["name"].startswith("Finans Gündemi") and x["event"] == "workflow_dispatch":
            continue   # 1a'da raporlandı
        sonra_duzeldi = any(t > x["_t"] for t in basarili_yayin) if x["name"].startswith(YAYINLAYANLAR) else False
        ad_son, iletiler = adimlar(x["id"]) if sayac < 4 else ({}, [])
        sayac += 1
        ayr = (f"Başarısız adım: {', '.join(k for k, v in ad_son.items() if v == 'failure') or '—'}"
               + (" · " + iletiler[0] if iletiler else ""))
        if x["name"].startswith("Site Yayınla") and sonra_duzeldi:
            ekle("bilgi", f"{x['_t']:%d.%m %H:%M} Site Yayınla koşusu düştü, sonraki yayın başarılı", ayr)
        elif x["name"].startswith("Finans Gündemi") and x["event"] == "schedule" and sonra_duzeldi:
            ekle("bilgi", f"{x['_t']:%d.%m %H:%M} Finans Gündemi yedek koşusu düştü, sonraki yayın başarılı", ayr)
        else:
            ekle("sorun", f"{x['_t']:%d.%m %H:%M} {x['name']} koşusu başarısız ({x['conclusion']})", ayr,
                 "Sonraki koşu da düşerse nedenine bakılmalı; ayrıntı: GitHub → Actions.")

    # 1c. haftalık veri güncellemesi (Perşembe + Cuma 14:45; GitHub saatlerce geciktirebilir)
    hv = [x for x in kosular if x["name"].startswith("Haftalık Veri Güncelleme")]
    if hv:
        son = max(hv, key=lambda k: k["_t"])
        yas = (n - son["_t"]).total_seconds() / 86400
        if yas > 8.5:
            ekle("uyari", f"Haftalık veri güncellemesi {yas:.0f} gündür çalışmadı", f"Son koşu {son['_t']:%d.%m.%Y %H:%M}",
                 "GitHub zamanlayıcısı durmuş olabilir (60 gün hareketsiz depoda kapanır); Actions sekmesinden elle çalıştırılabilir.")
        elif son["conclusion"] == "success":
            ekle("bilgi", f"Haftalık veri güncellemesi: son koşu {son['_t']:%d.%m %H:%M} başarılı")


# ───────────────────────────── 2. Canlı site ─────────────────────────────
def kontrol_site(n):
    cek = git("fetch", "-q", "origin", "main")
    if cek.returncode != 0:
        ekle("uyari", "Depo güncellenemedi (git fetch)", (cek.stderr or cek.stdout).strip()[:160])
    try:
        canli = json.loads(al(f"{SITE}/data/home.json"))
    except Exception as e:
        ekle("sorun", "Canlı siteye erişilemiyor", f"{SITE}/data/home.json → {type(e).__name__}: {str(e)[:100]}",
             "Birkaç dakika sonra yeniden denenmeli; sürerse GitHub Pages / Cloudflare durumu kontrol edilmeli.")
        return
    depo = git("show", "origin/main:site/data/home.json")
    try:
        depo_j = json.loads(depo.stdout)
    except Exception:
        depo_j = None
    if depo_j is not None and depo_j != canli:
        son_commit = git("log", "-1", "--format=%ct|%s", "origin/main", "--", "site").stdout.strip()
        ct, _, konu = son_commit.partition("|")
        yas_dk = (time.time() - int(ct)) / 60 if ct.isdigit() else 0
        if yas_dk > 25:
            ekle("sorun", "Canlı site depodaki son sürümün gerisinde",
                 f"Depodaki son site değişikliği {yas_dk / 60:.1f} saat önce ({konu[:70]}), canlı sitede yok — yayın adımı düşmüş olabilir.",
                 "Bir sonraki yayın (herhangi bir push ya da sabah bülteni) siteyi günceller; hemen gerekiyorsa Actions → Site Yayınla → Run workflow.")
        else:
            ekle("bilgi", f"Site yayını sürüyor olabilir (son değişiklik {yas_dk:.0f} dk önce)")
    else:
        ekle("bilgi", "Canlı site depodaki son sürümle aynı")
    if n.weekday() <= 4 and n.time() >= dt.time(8, 25):
        try:
            g = json.loads(al(f"{SITE}/data/haber/{n:%Y-%m-%d}.json"))
            if g.get("mod") != "ai":
                ekle("uyari", "Bugünkü gündem Claude seçkisi olmadan üretilmiş", f"mod = {g.get('mod')!r} (anahtar kelime süzgeci)",
                     "ANTHROPIC_API_KEY secret'ı ya da model adı (HABER_MODEL) kontrol edilmeli.")
        except urllib.error.HTTPError as e:
            ekle("sorun", "Bugünkü gündem sayfası canlı sitede yok", f"{SITE}/data/haber/{n:%Y-%m-%d}.json → HTTP {e.code}",
                 "Sabah koşusu gündemi üretememiş ya da site yayını düşmüş; yukarıdaki bülten satırına bakın.")
        except Exception as e:
            ekle("uyari", "Bugünkü gündem sayfası okunamadı", f"{type(e).__name__}: {str(e)[:100]}")


# ───────────────────────────── 3. Yerel depo ─────────────────────────────
def kontrol_depo(n):
    dal = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if dal != "main":
        ekle("uyari", f"Yerel depo 'main' dalında değil ({dal})", "", "Otomatik yayınlar main dalını bekler.")
    gitdir = REPO / ".git"
    if any((gitdir / d).exists() for d in ("rebase-merge", "rebase-apply", "MERGE_HEAD")):
        ekle("sorun", "Yerel depoda yarım kalmış rebase / birleştirme var", "Otomatik yayınlar bu durumda çalışamaz.",
             "Bir Claude oturumunda 'depodaki yarım rebase'i temizle' denmeli.")
    ileri = git("rev-list", "--count", "origin/main..HEAD").stdout.strip()
    if ileri.isdigit() and int(ileri) > 0:
        zamanlar = [int(t) for t in git("log", "--format=%ct", "origin/main..HEAD").stdout.split() if t.isdigit()]
        en_eski = (time.time() - min(zamanlar)) / 3600 if zamanlar else 0
        konular = git("log", "--format=%s", "origin/main..HEAD").stdout.strip().splitlines()[:3]
        if en_eski > 2:
            ekle("sorun", f"Yerelde gönderilmemiş {ileri} commit var (en eskisi {en_eski:.0f} saat önce)",
                 " · ".join(k[:70] for k in konular), "Site bu değişiklikleri görmüyor; push edilmeli (çakışma varsa nedenine bakılmalı).")
        else:
            ekle("bilgi", f"Yerelde henüz gönderilmemiş {ileri} yeni commit var (çalışma sürüyor olabilir)")
    degisen = [s[3:].strip().strip('"') for s in git("status", "--porcelain").stdout.splitlines() if s[:2].strip() and not s.startswith("??")]
    eski = []
    for f in degisen:
        try:
            if time.time() - (REPO / f).stat().st_mtime > 86400:
                eski.append(f)
        except OSError:
            pass
    if eski:
        ekle("uyari", f"Depoda bir günden eski, kaydedilmemiş {len(eski)} değişiklik var", ", ".join(eski[:5]),
             "Yarım kalmış bir iş olabilir; bir Claude oturumunda bakılmalı.")


# ───────────────────────────── 4. Yerel zamanlanmış işler ─────────────────────────────
def kontrol_launchd():
    uid = os.getuid()
    for etiket in LAUNCHD:
        r = subprocess.run(["launchctl", "print", f"gui/{uid}/{etiket}"], capture_output=True, text=True)
        if r.returncode != 0:
            ekle("sorun", f"Zamanlayıcı yüklü değil: {etiket}", "launchd bu işi tanımıyor; zamanında çalışmaz.",
                 f"launchctl bootstrap gui/{uid} ~/Library/LaunchAgents/{etiket}.plist")


def kap_kok():
    adaylar = glob.glob(str(Path.home() / "cowork" / "*" / "PDF_ISLENDI" / "kap"))
    return Path(adaylar[0]) if adaylar else None


def kontrol_kap(t0, n):
    satirlar = log_satirlari(LOG_KAP, t0)
    if n.month in KAP_AYLARI and n.time() >= dt.time(9, 20):
        bugun_var = lambda: any(z.date() == n.date() for z, _ in log_satirlari(LOG_KAP, dt.datetime.combine(n.date(), dt.time(0), tzinfo=TR)))
        bekle = 0
        while not bugun_var() and Path("/tmp/ekordion-kap.kilit").exists() and bekle < 240:   # koşu şu an sürüyor olabilir
            time.sleep(15); bekle += 15
        if not bugun_var():
            ekle("sorun", "KAP otomatik kontrolü bugün çalışmadı",
                 f"Rapor ayındayız ({n:%m}. ay); günlükte bugüne ait satır yok ({LOG_KAP}).",
                 "Elle başlatma: launchctl kickstart gui/$(id -u)/com.ekordion.kap · zamanlayıcı ayarı kontrol edilmeli.")
        else:
            satirlar = log_satirlari(LOG_KAP, t0)
    for z, m in satirlar:
        if m.startswith("YÜKLENDİ"):
            ekle("bilgi", f"KAP: yeni rapor yüklendi — {m[10:].split(' · ')[0]} ({z:%d.%m %H:%M})")
    uyarilar = [(z, m) for z, m in satirlar if re.search(r"UYARI|HATA|SORUNLU|SURE ASIMI|Traceback|Error", m)]
    kok = kap_kok()
    bekliyor = bool(kok and (kok / ".yayin_bekliyor").exists())
    if bekliyor:
        ekle("sorun", "KAP: yüklenen rapor siteye gönderilemedi (yayın bekliyor)",
             "; ".join(f"{z:%d.%m %H:%M} {m[:110]}" for z, m in uyarilar[-2:]) or "kap/.yayin_bekliyor işareti duruyor",
             "Yeniden deneme: zsh banka_kap_otomatik.sh (rapor ayı dışında KAP_ZORLA=1 ile). Yine olmazsa yayın adımına bakılmalı.")
    elif uyarilar:
        ekle("uyari", f"KAP günlüğünde {len(uyarilar)} uyarı satırı", "; ".join(f"{z:%d.%m %H:%M} {m[:110]}" for z, m in uyarilar[-3:]))
    if kok and (kok / "durum.json").exists():
        try:
            sorunlu = json.loads((kok / "durum.json").read_text(encoding="utf-8")).get("sorunlu", {})
        except Exception:
            sorunlu = {}
        if sorunlu:
            ekle("uyari", f"KAP: doğrulamadan geçemeyen {len(sorunlu)} rapor bekliyor",
                 "; ".join(f"{k.replace('|', ' ')} — {str(v.get('neden', ''))[:70]} ({v.get('tarih', '')})" for k, v in list(sorunlu.items())[:4]),
                 "Bu raporlar veritabanına yazılmadı; okuyucunun rapor düzenine uyarlanması gerekir (bir Claude oturumunda).")


def kontrol_bddk(t0, n):
    r = subprocess.run([sys.executable, "bddk_hafta.py", "--durum"], cwd=REPO, capture_output=True, text=True)
    durum = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
    m = re.match(r"(GUNCEL|EKSIK) beklenen=(\S+) yayinda=(\S+)", durum)
    satirlar = log_satirlari(LOG_BDDK, t0)
    if not m:
        ekle("uyari", "BDDK haftalık veri durumu okunamadı", (durum or r.stderr or "")[:160])
        return
    if m.group(1) == "GUNCEL":
        ekle("bilgi", f"BDDK haftalık verisi güncel (hafta {m.group(3)})")
        return
    tum = log_satirlari(LOG_BDDK, n - dt.timedelta(minutes=50))
    suruyor = bool(tum) and any("başladı" in x for _, x in tum) and not any(x.startswith("Bitti") for _, x in tum[-3:])
    ayr = f"Beklenen hafta {m.group(2)}, yayında {m.group(3)}."
    hatalar = [x for _, x in satirlar if re.search(r"HATA|SURE ASIMI", x)]
    if n.weekday() == 4 or (n.weekday() == 5):
        ekle("bilgi", "BDDK haftalık verisi henüz yeni haftada değil (olağan: bülten Perşembe akşamı–Cuma öğleden sonra çıkar; "
                      "denemeler Cuma 09:30/13:30/17:30, Cumartesi 10:30, Pazartesi 09:30)", ayr)
    elif suruyor:
        ekle("bilgi", "BDDK çekimi şu an sürüyor", ayr)
    elif n.weekday() == 0 and n.time() < dt.time(10, 10):
        ekle("bilgi", "BDDK verisi eksik; Pazartesi 09:30 denemesi bekleniyor", ayr)
    else:
        ekle("sorun", "BDDK haftalık verisi beklenen haftayı içermiyor", ayr + (" Günlükte: " + "; ".join(h[:90] for h in hatalar[-2:]) if hatalar else ""),
             "Beş otomatik deneme de tutmamış. Elle: zsh bddk_otomatik.sh (Chrome penceresi açılır). BDDK yayımlamadıysa beklenir.")


def bilgi_banka():
    try:
        D = json.loads((REPO / "site" / "data" / "banka_kar.json").read_text(encoding="utf-8"))
        son = D["periods"][-1]
        var = {r["ad"] for r in D["ozet_tablo"][son]}
        eksik = sorted(b["ad"] for b in D["banks"] if b["ad"] not in var)
        ekle("bilgi", f"Banka verisi: {son[:4]} Ç{son[-1]} · {len(var)} banka" + (f" · raporu bekleyen: {', '.join(eksik[:6])}" if eksik else ""))
    except Exception:
        pass


def bildir(metin):
    """Kullanıcının dikkatini çeker: ekranda küçük bir pencere açar (osascript 'display dialog'; bir saat sonra kendiliğinden
    kapanır, betiği bekletmez). 'display notification' bu bilgisayarda görünmüyor (16.11.2026'da denendi: bildirim hiç çıkmadı) —
    yine de denenir, zararı yok."""
    guvenli = metin.replace("\\", " ").replace('"', "'")[:300]
    try:
        subprocess.run(["osascript", "-e", f'display notification "{guvenli}" with title "ekordion sabah kontrolü"'],
                       capture_output=True, timeout=15)
    except Exception:
        pass
    try:
        subprocess.Popen(["osascript", "-e", "tell me to activate", "-e",
                          f'display dialog "{guvenli}" with title "ekordion sabah kontrolü" buttons {{"Tamam"}} '
                          'default button "Tamam" with icon caution giving up after 3600'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass


# ───────────────────────────── çalıştır ─────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bildir", action="store_true", help="sorun varsa masaüstü bildirimi göster")
    ap.add_argument("--bildirim-deneme", action="store_true", help="yalnız bir deneme bildirimi göster ve çık")
    ap.add_argument("--kuru", action="store_true", help="durum kaydını ilerletme")
    ap.add_argument("--geri", type=float, help="pencere (saat); verilmezse son kontrolden bugüne")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.bildirim_deneme:
        bildir("Bildirim denemesi — bir şey yapmanız gerekmiyor."); print("deneme penceresi açıldı"); return
    n = simdi()
    durum = {}
    try:
        durum = json.loads(DURUM.read_text(encoding="utf-8"))
    except Exception:
        pass
    if a.geri:
        t0 = n - dt.timedelta(hours=a.geri)
    elif durum.get("son_kontrol"):
        t0 = max(dt.datetime.fromisoformat(durum["son_kontrol"]), n - dt.timedelta(days=7))
    else:
        t0 = n - dt.timedelta(hours=74 if n.weekday() == 0 else 26)

    for ad, f in (("GitHub", lambda: kontrol_github(t0, n)), ("site", lambda: kontrol_site(n)), ("depo", lambda: kontrol_depo(n)),
                  ("launchd", kontrol_launchd), ("KAP", lambda: kontrol_kap(t0, n)), ("BDDK", lambda: kontrol_bddk(t0, n)),
                  ("banka", bilgi_banka)):
        try:
            f()
        except Exception as e:   # bir denetimin çökmesi diğerlerini durdurmasın; kendisi de bir bulgudur
            ekle("uyari", f"'{ad}' denetimi tamamlanamadı", f"{type(e).__name__}: {str(e)[:160]}")

    sorun = [b for b in bulgular if b["duzey"] == "sorun"]
    uyari = [b for b in bulgular if b["duzey"] == "uyari"]
    bilgi = [b for b in bulgular if b["duzey"] == "bilgi"]
    if not a.kuru:
        DURUM.parent.mkdir(exist_ok=True)
        DURUM.write_text(json.dumps({"son_kontrol": n.isoformat(timespec="seconds"), "sorun": len(sorun), "uyari": len(uyari),
                                     "basliklar": [b["baslik"] for b in sorun + uyari]}, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.bildir and sorun:
        bildir(f"{len(sorun)} sorun: {sorun[0]['baslik'][:120]}" + (" (+%d)" % (len(sorun) - 1) if len(sorun) > 1 else "")
               + " — Claude'da 'Sabah kontrolü' oturumuna bakın.")
    if a.json:
        print(json.dumps({"zaman": n.isoformat(timespec="seconds"), "pencere_baslangic": t0.isoformat(timespec="seconds"),
                          "sonuc": "SORUN VAR" if sorun else "YOLUNDA", "bulgular": bulgular}, ensure_ascii=False, indent=1))
    else:
        print(f"ekordion sağlık kontrolü · {n:%d.%m.%Y %H:%M} {GUNLER[n.weekday()]} · pencere: {t0:%d.%m %H:%M} → şimdi")
        for baslik, liste, im in ((f"SORUN ({len(sorun)})", sorun, "✗"), (f"UYARI ({len(uyari)})", uyari, "!"), ("BİLGİ", bilgi, "·")):
            if not liste:
                continue
            print(f"\n{baslik}")
            for b in liste:
                print(f" {im} {b['baslik']}")
                if b["ayrinti"]:
                    print(f"     {b['ayrinti']}")
                if b["oneri"]:
                    print(f"     öneri: {b['oneri']}")
        print(f"\nSONUÇ: {'SORUN VAR' if sorun else 'YOLUNDA'}" + (f" ({len(uyari)} uyarı)" if uyari and not sorun else ""))
    sys.exit(1 if sorun else 0)


if __name__ == "__main__":
    main()
