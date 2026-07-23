/* Ekonomik Veriler — ortak yardımcılar */

const NAV = [
  { href: "index.html", label: "Ana Sayfa" },
  { href: "tcmb-stok.html", label: "TCMB Haftalık Stok" },
  { href: "dth.html", label: "Yabancı Para Hareketi" },
  { href: "enflasyon.html", label: "TÜFE Enflasyon" },
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

const C = {
  toplam: "#4C9AFF", hisse: "#ED7D31", kesin: "#3D7BE0", dolayli: "#6FD1FF",
  ost: "#9AA4B2", euro: "#4CAF7D", line: "#9AA4B2",
  altin: "#FF9E1B", doviz: "#26C281", tuzel: "#4FC3F7", gercek: "#E64980",
  amber: "#FF9E1B", green: "#26C281", red: "#FF5A5F",
};

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
    '<div class="side-foot">v3.0 · statik site</div>';

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

function plLayout(over) {
  const base = {
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
  return deepMerge(base, over || {});
}

const PCFG = { displayModeBar: false, responsive: true };

function draw(id, traces, layoutOver) {
  const gd = document.getElementById(id);
  Plotly.newPlot(gd, traces, plLayout(layoutOver), PCFG).then(function () {
    zoomSifirlaKur(gd);
  });
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
    font: { size: 13, color: color, family: "'IBM Plex Mono', monospace" },
  };
}

/* Yığılmış son bar etiketleri — [ [değer, renk], ... ] yığın sırasında */
function annStack(x, items) {
  let pos = 0, neg = 0;
  const out = [];
  for (const it of items) {
    const v = it[0], color = it[1], txt = it[2];
    if (v === null || v === undefined || isNaN(v)) continue;
    let y, shift;
    if (v >= 0) { pos += v; y = pos; shift = 14; }
    else { neg += v; y = neg; shift = -14; }
    out.push({ x: x, y: y, text: txt, showarrow: false, yshift: shift,
               font: { size: 13, color: color, family: "'IBM Plex Mono', monospace" } });
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
