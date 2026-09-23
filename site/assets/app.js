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
  { href: "bddk.html", label: "BDDK Bankacılık Verileri" },
  { href: "hazine.html", label: "Hazine İhale Verileri" },
  { href: "tcmb-alim.html", label: "TCMB Doğrudan Alım" },
  { head: "Finansal Hesaplar" },
  { href: "hesap-kredi.html", label: "Kredi Hesaplama" },
  { href: "hesap-mevduat.html", label: "Mevduat / Stopaj" },
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
      if (n.href) {
        const act = n.href === here ? " active" : "";
        return '<a class="' + act.trim() + '" href="' + n.href + '">' + n.label + "</a>";
      }
      return '<span class="soon">' + n.label + "</span>";
    }).join("") +
    "</nav>" +
    '<button class="tema-btn" type="button" id="temaBtn">' + (ACIK_TEMA ? "● Koyu tema" : "○ Açık tema (TCMB)") + "</button>" +
    '<div class="side-foot">v3.0 · statik site</div>';
  const tb = document.getElementById("temaBtn");
  if (tb) tb.onclick = temaDegistir;

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
    annlar.push({ x: s_.x, y: s_.y, text: "%" + trNum(s_.y, 2), showarrow: false,
      xanchor: "left", xshift: 8, yshift: sonShift,
      font: Object.assign({ color: s_.renk }, ANN_MONO) });
  }
  const kenar = function (u) {
    return u.i >= u.n - 2 ? { xanchor: "right", xshift: -6 }
         : u.i <= 1 ? { xanchor: "left", xshift: 6 }
         : { xanchor: "center", xshift: 0 };
  };
  if (gMax) annlar.push(Object.assign({ x: gMax.x, y: gMax.v, text: "▲ %" + trNum(gMax.v, 2),
    showarrow: false, yshift: 15, font: Object.assign({ color: gMax.renk }, ANN_MONO) }, kenar(gMax)));
  if (gMin) annlar.push(Object.assign({ x: gMin.x, y: gMin.v, text: "▼ %" + trNum(gMin.v, 2),
    showarrow: false, yshift: -15, font: Object.assign({ color: gMin.renk }, ANN_MONO) }, kenar(gMin)));
  annlar.push(imzaAnn(gd.layout.paper_bgcolor === "#FFFFFF"));  // imza korunur
  Plotly.relayout(gd, { annotations: annlar });
}

/* Pencereli çok serili çizgi grafiği + görünürlüğe duyarlı etiketler.
   veriler: [[dizi, ad, renk, kalınlık?], ...] */
function cokSerili(id, veriler, tarih, W, yukseklik, acik) {
  const t = tail(tarih, W);
  const izler = veriler.map(function (v) {
    return { type: "scatter", mode: "lines", x: t, y: tail(v[0], W), name: v[1],
      line: { color: v[2], width: v[3] || 2 },
      hovertemplate: "%{x|%d.%m.%Y}<br>%%{y:.2f}<extra>" + v[1] + "</extra>" };
  });
  return draw(id, izler, { height: yukseklik, margin: { l: 54, r: 74, t: 26, b: 44 } }, acik)
    .then(function (gd) {
      annGuncelle(gd);
      gd.on("plotly_restyle", function () { annGuncelle(gd); });  // lejant aç/kapa
      return gd;
    });
}

/* Kart başına "Beyaz zemin (sunum)" + "Resim olarak kopyala" düğmeleri.
   Kural: kart id'si secN, grafik id'si chN. CIZ[secN]() grafiği yeniden çizer (promise döner). */
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
  document.querySelectorAll(".resim-btn").forEach(function (b) {
    b.onclick = async function () {
      const sec = b.dataset.sec;
      b.textContent = "⏳ Hazırlanıyor...";
      try {
        try {
          await navigator.clipboard.write([new ClipboardItem({ "image/png": grafikResmi(sec) })]);
        } catch (e1) {
          const blob = await grafikResmi(sec);
          await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        }
        b.textContent = "✓ Resim kopyalandı — yapıştırabilirsin";
      } catch (e) {
        b.textContent = "Kopyalanamadı — beyaz zemin + ekran görüntüsü kullan";
      }
      setTimeout(function () { b.textContent = "🖼 Resim olarak kopyala"; }, 3000);
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
