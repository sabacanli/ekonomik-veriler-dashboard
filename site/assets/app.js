/* Ekonomik Veriler — ortak yardımcılar */

/* ── Tema: "acik" (TCMB sunum dili — varsayılan) / "koyu" (Bloomberg) ──
   Tercih localStorage'da; sayfa <head>'indeki küçük betik koyu temayı boyamadan önce uygular. */
const TEMA_AD = (function () {
  try { const t = localStorage.getItem("ekordion-tema"); if (t === "koyu" || t === "acik") return t; } catch (e) {}
  return "acik";
})();
if (TEMA_AD === "koyu") document.documentElement.setAttribute("data-theme", "koyu");
else document.documentElement.removeAttribute("data-theme");
const ACIK_TEMA = TEMA_AD === "acik";
function temaDegistir() {
  try { localStorage.setItem("ekordion-tema", ACIK_TEMA ? "koyu" : "acik"); } catch (e) {}
  location.reload();
}

const NAV = [
  { href: "index.html", label: "Ana Sayfa" },
  { href: "gundem.html", label: "Finans Gündemi" },
  { href: "tcmb-stok.html", label: "TCMB Haftalık Stok" },
  { href: "dth.html", label: "Yabancı Para Hareketi" },
  { href: "enflasyon.html", label: "TÜFE Enflasyon" },
  { href: "tcmb-faiz.html", label: "Para Politikası & Beklentiler" },
  { href: "net-rezerv.html", label: "TCMB Rezervleri" },
  { href: "cari.html", label: "Cari Denge" },
  { href: "kredi.html", label: "Kredi Faizleri" },
  { href: "mevduat.html", label: "Mevduat Faizleri" },
  { href: "butce.html", label: "Bütçe Dengesi" },
  { href: "nakit.html", label: "Hazine Nakit Gerçekleşmeleri" },
  { href: "hazine.html", label: "Hazine İhale Verileri" },
  { href: "tcmb-alim.html", label: "TCMB Doğrudan Alım" },
  { group: "Banka Bilanço Analizi", items: [      // katlanır grup: içindeki sayfadaysa açık, yoksa kullanıcının son tercihi
    { href: "bddk.html", label: "BDDK Haftalık Veriler" },
    { href: "bankacilik.html", label: "Bankacılık Monitörü" },
    { href: "banka-kar.html", label: "Banka Kârlılık Analizi", items: [   // sayfa içi sekmeler (hash)
      { hash: "#genel", label: "Genel Bakış" }, { hash: "#rasyolar", label: "Rasyolar" }, { hash: "#karsilastirma", label: "Banka Karşılaştırma" },
      { hash: "#zaman", label: "Zaman Serisi" }, { hash: "#odak", label: "Banka Odak" }, { hash: "#bolumler", label: "Faaliyet Bölümleri" },
      { hash: "#portfoy", label: "Menkul Kıymet Portföyü" },
    ] },
  ] },
  { group: "Finansal Hesaplar", items: [
    { href: "hesap-kredi.html", label: "Kredi Hesaplama" },
    { href: "hesap-mevduat.html", label: "Mevduat / Stopaj" },
  ] },
];

/* Seri renkleri — temaya göre. Açık tema TCMB paleti: kırmızı ana seri, lacivert ikinci seri,
   açık mavi / bej / gri yardımcı; yeşil yalnız "fazla/artış" anlamı için. */
const C = ACIK_TEMA ? {
  toplam: "#1C3044", hisse: "#D40031", kesin: "#5E8BC5", dolayli: "#A7C0E0",
  ost: "#9AA4B2", euro: "#B99464", line: "#9AA4B2",
  altin: "#B99464", doviz: "#1C3044", tuzel: "#5E8BC5", gercek: "#D40031",
  amber: "#D40031", green: "#2E7D5B", red: "#D40031",
} : {
  toplam: "#4C9AFF", hisse: "#ED7D31", kesin: "#3D7BE0", dolayli: "#6FD1FF",
  ost: "#9AA4B2", euro: "#4CAF7D", line: "#9AA4B2",
  altin: "#FF9E1B", doviz: "#26C281", tuzel: "#4FC3F7", gercek: "#E64980",
  amber: "#FF9E1B", green: "#26C281", red: "#FF5A5F",
};
/* Sayfalarda ad verilerek kullanılan ek kategorik renkler (tür/yöntem kırılımları) */
const PAL = ACIK_TEMA ? {
  mavi: "#1C3044", mor: "#5E8BC5", cyan: "#A7C0E0", yesil: "#2E7D5B", turuncu: "#B99464",
  sari: "#C9A227", pembe: "#D40031", lacivert: "#1C3044", gri: "#9AA4B2", kirmizi: "#D40031", amber: "#D40031",
} : {
  mavi: "#4C9AFF", mor: "#B98AFF", cyan: "#6FD1FF", yesil: "#4CAF7D", turuncu: "#ED7D31",
  sari: "#E8C468", pembe: "#FF7A80", lacivert: "#3D7BE0", gri: "#9AA4B2", kirmizi: "#FF5A5F", amber: "#FF9E1B",
};
/* Etiket yazı tipi: açık temada Open Sans kalın (TCMB değer etiketleri), koyuda Plex Mono */
const ANN_FONT = ACIK_TEMA ? { family: "'Open Sans', sans-serif", weight: 700 } : { family: "'IBM Plex Mono', monospace" };

/* ── Kenar çubuğu ── */
function renderShell() {
  const here = (location.pathname.split("/").pop() || "index.html");
  const side = document.getElementById("sidebar");
  if (!side) return;
  side.innerHTML =
    '<a class="brand" href="index.html">Ekonomik Veriler</a>' +
    '<div class="brand-sub">Piyasa analiz platformu</div>' +
    '<nav class="nav">' +
    NAV.map(function (n) {
      if (n.head) return '<span class="nav-head">' + n.head + "</span>";
      if (n.group) {
        const icinde = n.items.some(function (i) { return i.href === here; });
        // Site açıldığında gruplar kapalı gelir (kullanıcı isteği); aynı sekme oturumunda açılan grup açık kalır
        let acik = false;
        try { acik = sessionStorage.getItem("ekordion-nav-" + n.group) === "1"; } catch (e) {}
        return '<div class="nav-grp' + (acik ? " open" : "") + (icinde ? " has-active" : "") + '" data-grp="' + n.group + '">' +
          '<button type="button" class="nav-grp-btn" aria-expanded="' + (acik ? "true" : "false") + '"><span>' + n.group + '</span><span class="chev"></span></button>' +
          '<div class="nav-sub">' + n.items.map(function (i) {
            const act = i.href === here;
            if (i.items) {   // üçüncü düzey: aynı sayfanın hash sekmeleri; ok düğmesiyle açılır/kapanır (o sayfadayken varsayılan açık)
              let acik2 = false;
              try { acik2 = sessionStorage.getItem("ekordion-nav-item-" + i.href) === "1"; } catch (e) {}
              return '<div class="nav-item' + (acik2 ? " open" : "") + '" data-item="' + i.href + '"><div class="nav-item-row"><a class="' + (act ? "active" : "") + '" href="' + i.href + '">' + i.label + "</a>" +
                '<button type="button" class="nav-item-btn" aria-expanded="' + (acik2 ? "true" : "false") + '" aria-label="Alt sekmeleri aç/kapat"><span class="chev"></span></button></div>' +
                '<div class="nav-sub nav-sub2">' + i.items.map(function (t) { return '<a data-hash="' + t.hash + '" href="' + i.href + t.hash + '">' + t.label + "</a>"; }).join("") + "</div></div>";
            }
            return '<a class="' + (act ? "active" : "") + '" href="' + i.href + '">' + i.label + "</a>";
          }).join("") + "</div></div>";
      }
      if (n.href) {
        const act = n.href === here ? " active" : "";
        return '<a class="' + act.trim() + '" href="' + n.href + '">' + n.label + "</a>";
      }
      return '<span class="soon">' + n.label + "</span>";
    }).join("") +
    "</nav>" +
    '<button class="tema-btn" type="button" id="temaBtn">' + (ACIK_TEMA ? "● Koyu tema" : "○ Açık tema") + "</button>" +
    '<div class="side-foot">v3.0 · statik site</div>';
  const tb = document.getElementById("temaBtn");
  if (tb) tb.onclick = temaDegistir;
  // Sayfa içi sekme bağlantıları: etkin olanı hash'e göre işaretle; mobilde menüyü kapat
  function hashIsaretle() {   // yalnız o sayfadayken etkin sekme işaretlenir
    const h = location.hash || "#genel";
    side.querySelectorAll(".nav-item").forEach(function (it) {
      const burada = it.dataset.item === here;
      it.querySelectorAll(".nav-sub2 a").forEach(function (a) { a.classList.toggle("active", burada && a.dataset.hash === h); });
    });
  }
  hashIsaretle();
  window.addEventListener("hashchange", hashIsaretle);
  side.querySelectorAll(".nav-sub2 a").forEach(function (a) {
    a.addEventListener("click", function () { side.classList.remove("open"); const o = document.getElementById("overlay"); if (o) o.classList.remove("show"); });
  });
  side.querySelectorAll(".nav-item-btn").forEach(function (b) {
    b.onclick = function () {
      const it = b.closest(".nav-item"), acik = !it.classList.contains("open");
      it.classList.toggle("open", acik); b.setAttribute("aria-expanded", acik ? "true" : "false");
      try { sessionStorage.setItem("ekordion-nav-item-" + it.dataset.item, acik ? "1" : "0"); } catch (e) {}
    };
  });
  side.querySelectorAll(".nav-grp-btn").forEach(function (b) {
    b.onclick = function () {
      const g = b.parentElement, acik = !g.classList.contains("open");
      g.classList.toggle("open", acik); b.setAttribute("aria-expanded", acik ? "true" : "false");
      try { sessionStorage.setItem("ekordion-nav-" + g.dataset.grp, acik ? "1" : "0"); } catch (e) {}
    };
  });

  const btn = document.getElementById("menuBtn");
  const ovl = document.getElementById("overlay");
  if (btn) btn.onclick = function () { side.classList.toggle("open"); if (ovl) ovl.classList.toggle("show"); };
  if (ovl) ovl.onclick = function () { side.classList.remove("open"); ovl.classList.remove("show"); };
}
renderShell();

/* ── Sayı biçimi (Türkçe) ── */
function trNum(v, d, sign) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  d = d === undefined ? 1 : d;
  const s = Math.abs(v).toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
  return (v < 0 ? "-" : (sign ? "+" : "")) + s;
}

/* ── JSON yükleme ── */
async function getJSON(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(path + " yüklenemedi (" + r.status + ")");
  return r.json();
}

/* ── Plotly varsayılanları ── */
function deepMerge(base, over) {
  const out = Object.assign({}, base);
  for (const k in over) {
    if (over[k] && typeof over[k] === "object" && !Array.isArray(over[k]) && base[k] && typeof base[k] === "object" && !Array.isArray(base[k])) {
      out[k] = deepMerge(base[k], over[k]);
    } else {
      out[k] = over[k];
    }
  }
  return out;
}

/* Sağ altta ince imza — kopyalanan/paylaşılan görsellerde üretici belli olur */
function imzaAnn(acik) {
  return { text: "bacanlı", xref: "paper", yref: "paper", x: 1, y: 0,
    xanchor: "right", yanchor: "bottom", xshift: -6, yshift: 5, showarrow: false,
    font: { size: 10, color: acik ? "#C3CBD9" : "#39445A", family: acik ? "'Open Sans', sans-serif" : "'IBM Plex Mono', monospace" } };
}

function plLayout(over, acik) {
  const base = acik ? {
    // Açık tema — TCMB sunum dili: beyaz zemin, x'te kılavuz yok, y'de çok açık kılavuz,
    // ince lacivert eksen çizgileri, lejant grafiğin üstünde ortada
    paper_bgcolor: "#FFFFFF",
    plot_bgcolor: "#FFFFFF",
    font: { family: "'Open Sans', 'IBM Plex Sans', sans-serif", color: "#1C3044", size: 13 },
    separators: ",.",
    margin: { l: 54, r: 18, t: 10, b: 44 },
    xaxis: { showgrid: false, zeroline: false, showline: true, linecolor: "#1C3044", linewidth: 1.2,
             ticks: "outside", tickcolor: "#1C3044", ticklen: 4, tickfont: { color: "#1C3044" } },
    yaxis: { gridcolor: "#EDEFF3", zerolinecolor: "#1C3044", zerolinewidth: 1.2, showline: true,
             linecolor: "#1C3044", linewidth: 1.2, tickfont: { color: "#1C3044" } },
    legend: { orientation: "h", x: 0.5, xanchor: "center", y: 1.02, yanchor: "bottom", font: { size: 12.5 } },
    hoverlabel: { bgcolor: "#FFFFFF", bordercolor: "#1C3044", font: { color: "#1C3044", family: "'Open Sans', sans-serif" } },
    bargap: 0.3,
    height: 380,
  } : {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "'IBM Plex Sans', sans-serif", color: "#E6EAF2", size: 13 },
    separators: ",.",
    margin: { l: 54, r: 18, t: 10, b: 44 },
    xaxis: { gridcolor: "#1C2230", zerolinecolor: "#2A3245", linecolor: "#1C2230" },
    yaxis: { gridcolor: "#1C2230", zerolinecolor: "#2A3245", linecolor: "#1C2230" },
    legend: { orientation: "h", y: -0.22, font: { size: 12 } },
    hoverlabel: { bgcolor: "#151B29", bordercolor: "#1C2230", font: { color: "#E6EAF2", family: "'IBM Plex Sans', sans-serif" } },
    bargap: 0.25,
    height: 380,
  };
  const out = deepMerge(base, over || {});
  // Açık temada lejant veri alanının ÜSTÜNDE durur (TCMB düzeni); üst kenar boşluğu ona yer açar
  if (acik && out.showlegend !== false) out.margin = Object.assign({}, out.margin, { t: Math.max(out.margin.t || 0, 42) });
  out.annotations = (out.annotations || []).concat([imzaAnn(!!acik)]);
  return out;
}

const PCFG = { displayModeBar: false, responsive: true };

function draw(id, traces, layoutOver, acik) {
  const gd = document.getElementById(id);
  return Plotly.newPlot(gd, traces, plLayout(layoutOver, acik || ACIK_TEMA), PCFG).then(function () {
    zoomSifirlaKur(gd);
    return gd;
  });
}

/* ── Faiz/oran grafikleri için ortak takım ──
   Etiketler grafiğin O ANKİ görünür serilerinden hesaplanır (lejant aç/kapa dahil):
   sağ kenarda seri başına son değer, ▲/▼ pencere uçları (kenardaysa içeri bakar). */
const ANN_MONO = Object.assign({ size: 12.5 }, ANN_FONT);

function annGuncelle(gd) {
  const fmt = gd.__fmt || function (v) { return "%" + trNum(v, 2); };   // varsayılan: yüzde
  const gorunur = gd.data.filter(function (tr) { return tr.visible === undefined || tr.visible === true; });
  const annlar = [];
  let gMax = null, gMin = null;
  const sonlar = [];
  for (const tr of gorunur) {
    const y = tr.y, x = tr.x, renk = tr.line.color, n = y.length;
    let iSon = -1;
    for (let i = n - 1; i >= 0; i--) if (y[i] !== null && y[i] !== undefined) { iSon = i; break; }
    if (iSon < 0) continue;
    sonlar.push({ x: x[iSon], y: y[iSon], renk: renk });
    for (let i = 0; i < n; i++) {
      const v = y[i];
      if (v === null || v === undefined) continue;
      if (!gMax || v > gMax.v) gMax = { v: v, x: x[i], renk: renk, i: i, n: n };
      if (!gMin || v < gMin.v) gMin = { v: v, x: x[i], renk: renk, i: i, n: n };
    }
  }
  // Son değerler çizgi ucunun sağına (kenar boşluğu); yakın olanlar dikeyde kademelenir
  const aralik = gMax && gMin ? Math.max(gMax.v - gMin.v, 0.01) : 1;
  sonlar.sort(function (a, b) { return b.y - a.y; });
  let sonShift = 0, oncekiY = null;
  for (const s_ of sonlar) {
    sonShift = (oncekiY !== null && (oncekiY - s_.y) < aralik * 0.05) ? sonShift - 16 : 0;
    oncekiY = s_.y;
    annlar.push({ x: s_.x, y: s_.y, text: fmt(s_.y), showarrow: false,
      xanchor: "left", xshift: 8, yshift: sonShift,
      font: Object.assign({ color: s_.renk }, ANN_MONO) });
  }
  const kenar = function (u) {
    return u.i >= u.n - 2 ? { xanchor: "right", xshift: -6 }
         : u.i <= 1 ? { xanchor: "left", xshift: 6 }
         : { xanchor: "center", xshift: 0 };
  };
  if (gMax) annlar.push(Object.assign({ x: gMax.x, y: gMax.v, text: "▲ " + fmt(gMax.v),
    showarrow: false, yshift: 15, font: Object.assign({ color: gMax.renk }, ANN_MONO) }, kenar(gMax)));
  if (gMin) annlar.push(Object.assign({ x: gMin.x, y: gMin.v, text: "▼ " + fmt(gMin.v),
    showarrow: false, yshift: -15, font: Object.assign({ color: gMin.renk }, ANN_MONO) }, kenar(gMin)));
  annlar.push(imzaAnn(gd.layout.paper_bgcolor === "#FFFFFF"));  // imza korunur
  Plotly.relayout(gd, { annotations: annlar });
}

/* Pencereli çok serili çizgi grafiği + görünürlüğe duyarlı etiketler.
   veriler: [[dizi, ad, renk, kalınlık?], ...] */
function cokSerili(id, veriler, tarih, W, yukseklik, acik, secenek) {
  secenek = secenek || {};
  const t = tail(tarih, W);
  const hoverBirim = secenek.hoverBirim || "%%{y:.2f}";
  const izler = veriler.map(function (v) {
    const iz = { type: "scatter", mode: "lines", x: v[5] ? tail(v[5], W) : t, y: tail(v[0], W), name: v[1],
      line: { color: v[2], width: v[3] || 2 }, connectgaps: true,
      hovertemplate: "%{x|%d.%m.%Y}<br>" + hoverBirim + "<extra>" + v[1] + "</extra>" };
    return v[4] ? Object.assign(iz, v[4]) : iz;
  });
  return draw(id, izler, Object.assign({ height: yukseklik, margin: { l: 54, r: 74, t: 26, b: 44 } }, secenek.layout || {}), acik)
    .then(function (gd) {
      if (secenek.fmt) gd.__fmt = secenek.fmt;
      annGuncelle(gd);
      gd.on("plotly_restyle", function () { annGuncelle(gd); });  // lejant aç/kapa
      return gd;
    });
}

/* Kart başına "Beyaz zemin (sunum)" + "Resim olarak kopyala" düğmeleri.
   Kural: kart id'si secN, grafik id'si chN. CIZ[secN]() grafiği yeniden çizer (promise döner). */
/* html2canvas yalnız gerektiğinde (ilk "resim olarak kopyala" tıklamasında) yüklenir */
function html2canvasYukle() {
  if (window.html2canvas) return Promise.resolve();
  return new Promise(function (res, rej) {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js";
    s.onload = res; s.onerror = function () { rej(new Error("html2canvas yüklenemedi")); };
    document.head.appendChild(s);
  });
}

function sunumAraclariKur(TEMA, CIZ) {
  document.querySelectorAll(".apko-btn").forEach(function (b) {
    b.onclick = function () {
      const sec = b.dataset.sec;
      TEMA[sec] = !TEMA[sec];
      document.getElementById(sec).classList.toggle("apko", TEMA[sec]);
      CIZ[sec]();
      b.textContent = TEMA[sec] ? "🌙 Koyu zemine dön" : "🖨 Beyaz zemin (sunum)";
    };
  });
  function grafikResmi(sec) {
    const onceki = TEMA[sec];
    TEMA[sec] = true;
    return Promise.resolve(CIZ[sec]())
      .then(function (gd) { return Plotly.toImage(gd, { format: "png", scale: 2 }); })
      .then(function (url) { return fetch(url).then(function (r) { return r.blob(); }); })
      .finally(function () { TEMA[sec] = onceki; CIZ[sec](); });
  }
  /* Birden çok grafik ya da tablo içeren kart (ör. Rasyolar): kartın tamamı tek resim olur.
     Başlık, açıklama ve tablolar html2canvas ile yakalanır; Plotly grafikleri PNG olarak yerlerine bindirilir
     (html2canvas SVG grafikleri güvenilir çizemez). Kontroller ve düğmeler yakalama sırasında gizlenir. */
  function kartResmi(sec) {
    const el = document.getElementById(sec);
    const onceki = TEMA[sec], geciciBeyaz = !el.classList.contains("apko");
    TEMA[sec] = true;
    if (geciciBeyaz) el.classList.add("apko");
    el.classList.add("kopya-modu");
    let gds = [];
    return Promise.resolve(CIZ[sec]())
      .then(function () {
        gds = Array.from(el.querySelectorAll(".js-plotly-plot")).filter(function (gd) { return gd._fullLayout; });
        return Promise.all(gds.map(function (gd) { return Promise.all(gd._promises || []); }));
      })
      .then(html2canvasYukle)
      .then(function () { return new Promise(function (r) { setTimeout(r, 80); }); })   // stil/yerleşim otursun (rAF gizli sekmede askıda kalır)
      .then(function () {
        gds.forEach(function (gd) { gd.style.visibility = "hidden"; });
        return html2canvas(el, { scale: 2, backgroundColor: "#FFFFFF", logging: false, width: Math.max(el.offsetWidth, el.scrollWidth) })
          .finally(function () { gds.forEach(function (gd) { gd.style.visibility = ""; }); });
      })
      .then(function (cv) {
        const ctx = cv.getContext("2d"), r0 = el.getBoundingClientRect();
        ctx.setTransform(1, 0, 0, 1, 0, 0);   // html2canvas bağlamı ölçekli bırakır; grafikler piksel koordinatıyla bindirilir
        return Promise.all(gds.map(function (gd) {
          const r = gd.getBoundingClientRect(), w = gd._fullLayout.width, h = gd._fullLayout.height;
          return Plotly.toImage(gd, { format: "png", width: w, height: h, scale: 2 })
            .then(function (url) { return new Promise(function (res, rej) { const im = new Image(); im.onload = function () { res(im); }; im.onerror = rej; im.src = url; }); })
            .then(function (im) { ctx.drawImage(im, (r.left - r0.left) * 2, (r.top - r0.top) * 2, w * 2, h * 2); });
        })).then(function () { return cv; });
      })
      .then(function (cv) { return new Promise(function (r) { cv.toBlob(r, "image/png"); }); })
      .finally(function () { el.classList.remove("kopya-modu"); if (geciciBeyaz) el.classList.remove("apko"); TEMA[sec] = onceki; CIZ[sec](); });
  }
  function tekGrafik(sec) {   // tek Plotly grafiği olan tablosuz kart: yalnız grafik (eski davranış)
    const el = document.getElementById(sec);
    return !!el && el.querySelectorAll(".js-plotly-plot").length === 1 && !el.querySelector("table");
  }
  function resim(sec) { return tekGrafik(sec) ? grafikResmi(sec) : kartResmi(sec); }
  window.ekordionSunum = { resim: resim };   // sınama kancası
  document.querySelectorAll(".resim-btn").forEach(function (b) {
    b.onclick = async function () {
      const sec = b.dataset.sec;
      b.textContent = "⏳ Hazırlanıyor...";
      const blobP = resim(sec);          // resim bir kez üretilir; jest anında başlatılır (Safari)
      blobP.catch(function () {});
      try {
        try {
          await navigator.clipboard.write([new ClipboardItem({ "image/png": blobP })]);
        } catch (e1) {
          const blob = await blobP;      // söz kabul etmeyen eski tarayıcılar
          await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        }
        b.textContent = "✓ Resim kopyalandı — yapıştırabilirsin";
      } catch (e) {
        window.__kopyaHata = String(e && e.name) + ": " + String(e && e.message || e);   // tanı: son hata
        try {   // pano yazma izni yoksa resim dosya olarak indirilir
          const blob = await blobP;
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob); a.download = "ekordion-" + sec.replace(/^sec/, "").toLowerCase() + ".png";
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(function () { URL.revokeObjectURL(a.href); }, 10000);
          b.textContent = "Pano izni yok — resim PNG olarak indirildi";
        } catch (e2) {
          b.textContent = "Kopyalanamadı — beyaz zemin + ekran görüntüsü kullan";
        }
      }
      setTimeout(function () { b.textContent = "🖼 Resim olarak kopyala"; }, 4000);
    };
  });
}

/* Tablo kartları için sunum araçları: kart içindeki .apko-btn beyaz zemini açıp kapatır,
   .kopya-btn tabloyu Excel/PowerPoint'e renkleriyle yapışacak şekilde panoya yazar,
   .resim-btn tabloyu HER ZAMAN beyaz zeminli PNG olarak kopyalar (sayfada html2canvas gerekir).
   kopyaVerisi() → { html: satır-içi stilli tablo, duz: sekmeyle ayrılmış düz metin } */
function tabloSunumKur(sec, kopyaVerisi) {
  const apko = sec.querySelector(".apko-btn"), kopya = sec.querySelector(".kopya-btn"),
        resim = sec.querySelector(".resim-btn");
  if (apko) apko.onclick = function () {
    const acik = sec.classList.toggle("apko");
    apko.textContent = acik ? "🌙 Koyu zemine dön" : "🖨 Beyaz zemin (sunum)";
  };
  if (kopya) kopya.onclick = async function () {
    const v = kopyaVerisi();
    try {
      await navigator.clipboard.write([new ClipboardItem({
        "text/html": new Blob([v.html], { type: "text/html" }),
        "text/plain": new Blob([v.duz], { type: "text/plain" }),
      })]);
      kopya.textContent = "✓ Kopyalandı — Excel'e yapıştır";
    } catch (e) {
      kopya.textContent = "Kopyalanamadı — beyaz zemin + ekran görüntüsü kullan";
    }
    setTimeout(function () { kopya.textContent = "📋 Panoya kopyala (Excel)"; }, 3000);
  };
  // Dar ekranda kesilmesin diye sarmalayıcı geçici olarak tablo genişliğine açılır
  function tabloResmi() {
    const geciciBeyaz = !sec.classList.contains("apko");
    const wrap = sec.querySelector(".table-wrap"), tbl = sec.querySelector("table.heat");
    const eskiW = wrap.style.width;
    if (geciciBeyaz) sec.classList.add("apko");
    wrap.style.width = tbl.scrollWidth + "px";
    return new Promise(function (r) { requestAnimationFrame(function () { requestAnimationFrame(r); }); })
      .then(function () { return html2canvas(wrap, { scale: 2, backgroundColor: "#FFFFFF", logging: false }); })
      .then(function (cv) { return new Promise(function (r) { cv.toBlob(r, "image/png"); }); })
      .finally(function () { wrap.style.width = eskiW; if (geciciBeyaz) sec.classList.remove("apko"); });
  }
  if (resim) resim.onclick = async function () {
    resim.textContent = "⏳ Hazırlanıyor...";
    try {
      // Safari: blob sözü ClipboardItem'a jest anında verilmeli; eski Chrome için yedek yol
      try {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": tabloResmi() })]);
      } catch (e1) {
        const blob = await tabloResmi();
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      }
      resim.textContent = "✓ Resim kopyalandı — yapıştırabilirsin";
    } catch (e) {
      resim.textContent = "Kopyalanamadı — beyaz zemin + ekran görüntüsü kullan";
    }
    setTimeout(function () { resim.textContent = "🖼 Resim olarak kopyala"; }, 3000);
  };
}

/* Zoom yapılınca kartın sağ üstünde "sıfırla" düğmesi belirir (çift tıklama da sıfırlar) */
function zoomSifirlaKur(gd) {
  let b = gd.__resetBtn;
  if (!b) {
    const kap = gd.parentElement || gd;
    if (getComputedStyle(kap).position === "static") kap.style.position = "relative";
    b = document.createElement("button");
    b.type = "button";
    b.className = "pl-reset";
    b.textContent = "↺ Zoom'u sıfırla";
    b.style.display = "none";
    b.onclick = function () {
      Plotly.relayout(gd, { "xaxis.autorange": true, "yaxis.autorange": true });
    };
    kap.appendChild(b);
    gd.__resetBtn = b;
  }
  b.style.display = "none";
  gd.on("plotly_relayout", function (e) {
    if (!e) return;
    const sifirlandi = e["xaxis.autorange"] === true || e["yaxis.autorange"] === true;
    const zoomlandi = Object.keys(e).some(function (k) {
      return k.indexOf("range") !== -1 && k.indexOf("autorange") === -1;
    });
    if (sifirlandi) b.style.display = "none";
    else if (zoomlandi) b.style.display = "";
  });
}

/* Son bar etiketi — işarete göre üste/alta */
function annLast(x, y, text, color) {
  return {
    x: x, y: y, text: text, showarrow: false,
    yshift: y >= 0 ? 14 : -14,
    font: Object.assign({ size: 13, color: color }, ANN_FONT),
  };
}

/* Yığılmış son bar etiketleri — [ [değer, renk, metin], ... ] yığın sırasında.
   Etiketler değer konumuna değil, barın ucuna sabit piksel merdiveniyle dizilir:
   pozitifler üstte, negatifler altta alt alta — değerler ne kadar yakın olursa
   olsun üst üste binemezler (renk hangi bileşen olduğunu söyler). */
function annStack(x, items) {
  const gecerli = items.filter(function (it) {
    return it[0] !== null && it[0] !== undefined && !isNaN(it[0]);
  });
  let posT = 0, negT = 0;
  for (const it of gecerli) { if (it[0] >= 0) posT += it[0]; else negT += it[0]; }
  const out = [];
  let pi = 0, ni = 0;
  for (const it of gecerli) {
    const v = it[0], color = it[1], txt = it[2];
    const ust = v >= 0;
    out.push({ x: x, y: ust ? posT : negT, text: txt, showarrow: false,
               yshift: ust ? 14 + 17 * pi++ : -14 - 17 * ni++,
               font: Object.assign({ size: 13, color: color }, ANN_FONT) });
  }
  return out;
}

/* ── Sayfa parçaları ── */
function setUpdated(txt) {
  const el = document.getElementById("updated");
  if (el && txt) el.textContent = "📅 Son veri güncellemesi: " + txt;
}

function setOzet(html) {
  const el = document.getElementById("ozet");
  if (el) el.innerHTML = "📋 " + html;
}

function setMetrics(rows) {
  const el = document.getElementById("metrics");
  if (!el) return;
  el.innerHTML = rows.map(function (r) {
    const dlt = r[2] ? '<div class="dlt ' + (r[3] || "flat") + '">' + r[2] + "</div>" : "";
    return '<div class="metric"><div class="lbl">' + r[0] + '</div><div class="val">' + r[1] + "</div>" + dlt + "</div>";
  }).join("");
}

function rangeCtl(el, options, initial, onChange) {
  if (!el) return;
  el.innerHTML = options.map(function (o) {
    return '<button data-n="' + o[1] + '"' + (o[1] === initial ? ' class="active"' : "") + ">" + o[0] + "</button>";
  }).join("");
  el.querySelectorAll("button").forEach(function (b) {
    b.onclick = function () {
      el.querySelectorAll("button").forEach(function (x) { x.classList.remove("active"); });
      b.classList.add("active");
      onChange(parseInt(b.dataset.n, 10));
    };
  });
}

function tail(arr, n) { return arr.slice(-n); }

/* ── Cloudflare Web Analytics (ziyaretçi ölçümü; yerel önizlemede kapalı) ── */
(function () {
  if (location.hostname === "localhost" || location.hostname === "127.0.0.1") return;
  var s = document.createElement("script");
  s.src = "https://static.cloudflareinsights.com/beacon.min.js";
  s.type = "module";
  s.defer = true;
  s.setAttribute("data-cf-beacon", '{"token": "f251039fc2e04dde870f0912e7ea774a"}');
  document.head.appendChild(s);
})();
