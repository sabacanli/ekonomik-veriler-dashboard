// Cloudflare Worker — Finans Gündemi tetikleyicisi.
//
// GitHub'ın kendi zamanlayıcısı bu depoda saatlerce gecikebildiği için koşuları tam saatinde
// bu Worker başlatır: Cron Trigger → GitHub workflow_dispatch API → gundem.yml.
//
// Kurulum (Cloudflare panosu → Workers & Pages):
//   1. Worker oluştur, bu dosyanın içeriğini yapıştır, Deploy.
//   2. Settings → Variables and Secrets → Secret ekle:  GITHUB_TOKEN
//        = ince ayarlı (fine-grained) kişisel erişim anahtarı; yalnız bu depo,
//          Repository permissions → Actions: Read and write. (Süresi dolunca yenilenmeli.)
//   3. Settings → Triggers → Cron Triggers → İKİ tetik:
//        50 4 * * *   (UTC; her gün 07:50 TR — günlük Finans Gündemi; koşu ~4 dk, bülten ~08:00'de düşer)
//        0 16 * * SUN (UTC; Pazar 19:00 TR — haftalık "Haftaya Bakış": geçen hafta + gelecek hafta)
//        Not: Cloudflare gün alanında 0'ı kabul etmez; Pazar için SUN (veya 1) yazılır.
//
// Günlük bülten hafta içi (TR saatiyle Pzt–Cum) tüm listeye gönderilir; hafta sonu yalnız site güncellenir.
// Haftalık bülten Pazar akşamı tüm listeye gönderilir.
//
// NOT: Worker'daki kod ESKİ sürümse de (tur göndermeyen) sistem çalışır: gundem.yml, tür belirtilmeyen
// Pazar 17:00 TR sonrası tetikleri "haftalik" sayar ve bülteni gönderir. Yani panoda yapılması şart olan
// tek şey ikinci cron tetiğini (0 16 * * SUN) eklemektir; kod güncellemesi isteğe bağlıdır.
// Haftalık tetik cron dizesine değil TR saatine göre tanınır (Pazar 17:00 sonrası) — cron nasıl yazılırsa yazılsın.

const DISPATCH_URL =
  "https://api.github.com/repos/sabacanli/ekonomik-veriler-dashboard/actions/workflows/gundem.yml/dispatches";

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(tetikle(env, event.cron));
  },

  // Worker adresi herkese açık olduğundan HTTP isteği tetikleme YAPMAZ; yalnız ayakta olduğunu söyler.
  async fetch() {
    return new Response("gundem-tetik ayakta — tetikleme yalnız zamanlayıcıyla yapılır.\n");
  },
};

async function tetikle(env, cron) {
  const tr = new Date(Date.now() + 3 * 3600 * 1000);            // Türkiye saati (UTC+3, yaz saati yok)
  const trGun = tr.getUTCDay();                                  // 0 = Pazar … 6 = Cumartesi
  const haftalik = trGun === 0 && tr.getUTCHours() >= 17;        // Pazar 17:00 sonrası → Haftaya Bakış
  const bulten = haftalik ? "evet" : (trGun >= 1 && trGun <= 5 ? "evet" : "hayir");
  const tur = haftalik ? "haftalik" : "gunluk";
  const r = await fetch(DISPATCH_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "ekordion-gundem-tetik",
    },
    body: JSON.stringify({ ref: "main", inputs: { tur, bulten } }),
  });
  if (!r.ok) throw new Error(`GitHub workflow_dispatch başarısız: HTTP ${r.status}`);
  console.log(`gundem.yml tetiklendi (tür: ${tur}, bülten: ${bulten}, cron: ${cron})`);
}
