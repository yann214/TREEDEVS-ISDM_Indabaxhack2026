/* ═══════════════════════════════════════════════════
   CONFIG
═══════════════════════════════════════════════════ */
const API  = "http://localhost:5004";
const T    = 10000000;               // timeout ms
let   MAP  = null;
let   MAP_MARKERS = {};
let   CHARTS = {};
let   STATE = {
  dash: null,
  alerts: [],
  cities: [],
  selectedCity: "Douala",
  selectedYear: new Date().getFullYear(),   // ← année courante réelle
};


/* ═══════════════════════════════════════════════════
   GLOBAL LOADER
═══════════════════════════════════════════════════ */
let LOADING_COUNT = 0;

function showLoader(text="Chargement...") {
  LOADING_COUNT++;
  const el = document.getElementById("global-loader");
  if (!el) return;
  el.querySelector(".loader-text").textContent = text;
  el.classList.remove("hidden");
}

function hideLoader() {
  LOADING_COUNT = Math.max(0, LOADING_COUNT - 1);
  if (LOADING_COUNT === 0) {
    document.getElementById("global-loader")?.classList.add("hidden");
  }
}

/* ═══ FETCH HELPERS ═════════════════════════════════ */
async function get(path) {
  showLoader();
  try {
    const r = await fetch(API+path, {signal: AbortSignal.timeout(T)});
    if (!r.ok) throw new Error("HTTP "+r.status);
    return await r.json();
  } finally {
    hideLoader();
  }
}

async function post(path, body) {
  showLoader();
  try {
    const r = await fetch(API+path, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body),
      signal: AbortSignal.timeout(T),
    });
    if (!r.ok) throw new Error("HTTP "+r.status);
    return await r.json();
  } finally {
    hideLoader();
  }
}


/* ═══ IQA HELPERS ═══════════════════════════════════ */
function iqaColor(v) {
  if (v <= 50)  return {color:"#22c55e",bg:"#dcfce7",label:"Bon",tag:"Bonne"};
  if (v <= 100) return {color:"#f97316",bg:"#ffedd5",label:"Modéré",tag:"Modérée"};
  if (v <= 150) return {color:"#ef4444",bg:"#fee2e2",label:"Mauvais",tag:"Mauvaise"};
  if (v <= 200) return {color:"#dc2626",bg:"#fee2e2",label:"Très mauvais",tag:"Très mauvaise"};
  return             {color:"#7f1d1d",bg:"#fee2e2",label:"Dangereux",tag:"Dangereuse"};
}

function barColor(v) {
  if (v < 50)  return "#22c55e";
  if (v < 100) return "#f97316";
  return "#ef4444";
}

function destroyChart(id) {
  if (CHARTS[id]) { try { CHARTS[id].destroy(); } catch(_){} delete CHARTS[id]; }
}

const CHART_DEFAULTS = {
  tick: { color:"#94a3b8", font: {family:"Plus Jakarta Sans",size:11} },
  grid: "rgba(0,0,0,0.05)",
  tooltip: { backgroundColor:"#1e293b", titleColor:"#f8fafc", bodyColor:"#94a3b8",
             padding:10, cornerRadius:8, borderColor:"rgba(255,255,255,0.08)", borderWidth:1 },
};

/* ═══ NAVIGATION ════════════════════════════════════ */
const PAGES = {
  dashboard: "Tableau de bord",
  time:      "Données & Corrélations",
  xai:       "IA & Prédictions",
  map:       "Carte Pollution",
  alerts:    "Alertes Santé",
  regions:   "Par région",
  predict:   "Rechercher ville",
};

function goTo(page) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
  document.getElementById("page-"+page)?.classList.add("active");
  document.querySelector(`[onclick="goTo('${page}')"]`)?.classList.add("active");
  document.getElementById("topbar-title").textContent = PAGES[page] || page;
  if (page==="time")    { populatePageCitySelects(); buildTimeCharts(); }
  if (page==="xai")     { populatePageCitySelects(); buildXAI(); }
  if (page==="map")     buildMap();
  if (page==="alerts")  buildAlertsPage();
  if (page==="regions") buildRegionsPage();
  if (page==="predict") populatePageCitySelects();
}

function onCityChange() {
  STATE.selectedCity = document.getElementById("global-city-select").value;
  loadDashboard();
}

/* ═══ POPULATE SELECTS ══════════════════════════════ */
// Peuple un seul select par son id
function _populateSelect(id, cities, selectedVal) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = cities.map(c =>
    `<option value="${c}"${c === selectedVal ? " selected" : ""}>${c}</option>`
  ).join("");
}

// Peuple les selects des pages secondaires (time, xai, predict) — appelé à l'ouverture de chaque page
function populatePageCitySelects() {
  ["time-city-select", "xai-city-select", "pred-city"].forEach(id => {
    _populateSelect(id, STATE.cities, STATE.selectedCity);
  });
}

/* ═══════════════════════════════════════════════════
   DASHBOARD LOAD
═══════════════════════════════════════════════════ */
async function loadDashboard() {
  try {
    const [dash, top, regions, weather, alerts] = await Promise.all([
      get("/dashboard?city="+encodeURIComponent(STATE.selectedCity)),
      get("/top-cities?n=5"),
      get("/regions-iqa"),
      get("/weather?city="+encodeURIComponent(STATE.selectedCity)),
      get("/alerts"),
    ]);

    STATE.dash   = dash;
    STATE.alerts = alerts.alerts || [];

    // ── KPIs ──────────────────────────────────────
    const pred = dash.current;
    const lvl  = iqaColor(pred.iqa_global);

    document.getElementById("kpi-iqa").textContent      = pred.iqa_global.toFixed(0);
    document.getElementById("kpi-iqa").style.color      = lvl.color;
    document.getElementById("kpi-city-name").textContent= pred.city;
    document.getElementById("kpi-tag-iqa").textContent  = lvl.tag;
    document.getElementById("kpi-tag-iqa").style.cssText=
      `background:${lvl.bg};color:${lvl.color};font-size:10px;font-weight:700;padding:3px 8px;border-radius:20px`;
    document.getElementById("kpi-icon-iqa").style.background = lvl.bg;

    // Variation IQA vs mois dernier — calculée par l'API (/dashboard → iqa_change)
    const chg   = dash.iqa_change ?? null;
    const chgEl = document.getElementById("kpi-iqa-change");
    if (chg !== null) {
      chgEl.textContent = `${chg > 0 ? "↑ +" : "↓ "}${Math.abs(chg).toFixed(1)} vs mois dernier`;
      chgEl.className   = "kpi-change " + (chg > 0 ? "up" : "down");
    } else {
      chgEl.textContent = "Variation non disponible";
      chgEl.className   = "kpi-change";
    }

    // ── O3 ── données réelles uniquement
    const o3El        = document.getElementById("kpi-o3");
    const o3ChangeEl  = document.getElementById("kpi-o3-change");
    if (pred.o3 != null) {
      o3El.textContent = pred.o3.toFixed(1) + " µg/m³";
      // Variation O3 vs semaine précédente via timeseries (7 derniers jours)
      _computePollutantWeeklyChange("o3_mean", pred.city).then(delta => {
        if (delta !== null) {
          o3ChangeEl.textContent =
            `${delta > 0 ? "↑ +" : "↘ "}${Math.abs(delta).toFixed(1)} µg/m³ vs semaine`;
          o3ChangeEl.className = "kpi-sub " + (delta > 0 ? "up" : "down");
        } else {
          o3ChangeEl.textContent = "Variation non disponible";
        }
      });
    } else {
      o3El.textContent      = "— µg/m³";
      o3ChangeEl.textContent = "Données O₃ indisponibles";
    }

    // ── NO2 ── seuil OMS réel : 40 µg/m³ annuel / 25 µg/m³ journalier (OMS 2021 : 25)
    const no2El       = document.getElementById("kpi-no2");
    const no2ChangeEl = document.getElementById("kpi-no2-change");
    const OMS_NO2_DAILY = 25; // µg/m³ — seuil OMS 2021 journalier
    if (pred.no2 != null) {
      no2El.textContent = pred.no2.toFixed(1) + " µg/m³";
      if (pred.no2 > 0) {
        const ratio = (OMS_NO2_DAILY / pred.no2).toFixed(1);
        if (pred.no2 <= OMS_NO2_DAILY) {
          no2ChangeEl.textContent = `✓ En dessous du seuil OMS (${OMS_NO2_DAILY} µg/m³)`;
          no2ChangeEl.className   = "kpi-sub down";
        } else {
          no2ChangeEl.textContent =
            `⚠ ${(pred.no2 / OMS_NO2_DAILY).toFixed(1)}× le seuil OMS (${OMS_NO2_DAILY} µg/m³)`;
          no2ChangeEl.className = "kpi-sub up";
        }
      } else {
        no2ChangeEl.textContent = `Seuil OMS : ${OMS_NO2_DAILY} µg/m³`;
      }
    } else {
      no2El.textContent      = "— µg/m³";
      no2ChangeEl.textContent = "Données NO₂ indisponibles";
    }

    // ── PM2.5 ── seuil OMS 2021 journalier : 15 µg/m³
    const pm25El       = document.getElementById("kpi-pm25");
    const pm25ChangeEl = document.getElementById("kpi-pm25-change");
    const OMS_PM25_DAILY = 35; // µg/m³ — seuil OMS 2021 journalier
    if (pred.pm25 != null) {
      pm25El.textContent = pred.pm25.toFixed(1) + " µg/m³";
      if (pred.pm25 > 0) {
        if (pred.pm25 <= OMS_PM25_DAILY) {
          pm25ChangeEl.textContent = `✓ En dessous du seuil OMS (${OMS_PM25_DAILY} µg/m³)`;
          pm25ChangeEl.className   = "kpi-sub down";
        } else {
          pm25ChangeEl.textContent =
            `⚠ ${(pred.pm25 / OMS_PM25_DAILY).toFixed(1)}× le seuil OMS (${OMS_PM25_DAILY} µg/m³)`;
          pm25ChangeEl.className = "kpi-sub up";
        }
      } else {
        pm25ChangeEl.textContent = `Seuil OMS : ${OMS_PM25_DAILY} µg/m³`;
      }
      // Variation PM2.5 vs semaine précédente
      _computePollutantWeeklyChange("pm25", pred.city).then(delta => {
        if (delta !== null && pm25ChangeEl) {
          // On n'écrase le texte que si la variation est disponible et utile
          const sign = delta > 0 ? "↑ +" : "↘ ";
          pm25ChangeEl.textContent =
            `${sign}${Math.abs(delta).toFixed(1)} µg/m³ vs semaine · OMS ${OMS_PM25_DAILY} µg/m³`;
          pm25ChangeEl.className = "kpi-sub " + (delta > 0 ? "up" : "down");
        }
      });
    } else {
      if (pm25El)       pm25El.textContent       = "— µg/m³";
      if (pm25ChangeEl) pm25ChangeEl.textContent  = "Données PM₂.₅ indisponibles";
    }

    // Counts
    const s = dash.summary;
    document.getElementById("kpi-total-cities").textContent = s.total_cities;
    document.getElementById("kpi-cities-sub").textContent   = s.total_cities + " villes disponibles";
    document.getElementById("stat-good").textContent  = s.count_good      ?? 0;
    document.getElementById("stat-mod").textContent   = s.count_moderate  ?? 0;
    document.getElementById("stat-bad").textContent   = s.count_bad       ?? 0;
    document.getElementById("stat-vbad").textContent  = s.count_very_bad  ?? 0;

    // Meta
    document.getElementById("db-meta").innerHTML =
      `Qualité de l'air · <span id="db-cities-count">${s.total_cities}</span> villes · `
      + `Données au <span id="db-date">${new Date().toLocaleDateString("fr",{day:"numeric",month:"long",year:"numeric"})}</span>`;
    document.getElementById("db-alert-pill").textContent  = `⚠ ${s.active_alerts} villes en alerte`;
    document.getElementById("db-season-pill").textContent = `🌿 ${s.saison || pred.saison}`;

    // Notifs
    const ac = s.active_alerts ?? 0;
    document.getElementById("notif-badge").textContent     = ac;
    document.getElementById("nav-alert-badge").textContent = ac;

    // ── Top 5 ──────────────────────────────────────
    renderTop5("top5-polluted", top.polluted, true);
    renderTop5("top5-clean",    top.clean,    false);

    // ── Régions ───────────────────────────────────
    renderRegions("region-list", regions.regions, 6);

    // ── Météo ─────────────────────────────────────
    const lastUpdate = pred.timestamp
      ? new Date(pred.timestamp).toLocaleDateString("fr", {month:"long",year:"numeric"})
      : new Date().toLocaleDateString("fr", {month:"long",year:"numeric"});
    document.getElementById("weather-meta").textContent =
      `${pred.city} · ${lastUpdate}${weather.source === "openmeteo" ? " · Open-Meteo" : ""}`;
    document.getElementById("w-temp").textContent  = weather.temperature  ?? "—";
    document.getElementById("w-wind").textContent  = weather.wind_speed   ?? "—";
    document.getElementById("w-rain").textContent  = weather.precipitation ?? "—";
    document.getElementById("w-sun").textContent   = weather.sunshine      ?? "—";
    document.getElementById("w-saison").textContent =
      weather.saison + (weather.saison_desc ? " · " + weather.saison_desc : "");

    // ── Alertes panel ─────────────────────────────
    renderAlertsPanel(STATE.alerts.slice(0, 4));

    // ── Chart mensuel ─────────────────────────────
    await loadMonthlyChart(STATE.selectedCity, STATE.selectedYear);

  } catch(e) {
    console.warn("Dashboard error:", e.message);
  }
}

/* ══ VARIATION POLLUANT SEMAINE ═════════════════════
   Calcule la différence entre la valeur actuelle et
   la moyenne de la semaine N-2 à N-1 (données CSV).
═════════════════════════════════════════════════════ */
async function _computePollutantWeeklyChange(pollutantField, city) {
  try {
    const data = await get(`/timeseries?city=${encodeURIComponent(city)}&days=14`);
    const series = data.series || [];
    if (series.length < 7) return null;
    // Semaine courante (7 derniers jours)
    const currWeek = series.slice(-7).map(d => d[pollutantField]).filter(v => v != null);
    // Semaine précédente
    const prevWeek = series.slice(-14, -7).map(d => d[pollutantField]).filter(v => v != null);
    if (!currWeek.length || !prevWeek.length) return null;
    const avg = arr => arr.reduce((a, b) => a + b, 0) / arr.length;
    return parseFloat((avg(currWeek) - avg(prevWeek)).toFixed(2));
  } catch(_) {
    return null;
  }
}

/* ══ RENDER HELPERS ════════════════════════════════ */
function renderTop5(containerId, items, showTag) {
  const el = document.getElementById(containerId);
  if (!el || !items?.length) return;
  const maxIqa = Math.max(...items.map(x => x.iqa));
  el.innerHTML = items.map((item, i) => {
    const c = iqaColor(item.iqa);
    const w = (item.iqa / maxIqa * 100).toFixed(0);
    return `<div class="top5-item">
      <span class="top5-rank">${i+1}</span>
      <span class="top5-city">${item.city}</span>
      ${showTag
        ? `<div class="top5-bar-wrap"><div class="top5-bar" style="width:${w}%;background:${c.color}"></div></div>
           <span class="top5-iqa">${item.iqa.toFixed(0)}</span>
           <span class="top5-tag" style="background:${c.bg};color:${c.color}">${item.label||c.label}</span>`
        : `<div class="top5-bar-wrap"><div class="top5-bar" style="width:${w}%;background:${c.color}"></div></div>
           <span class="top5-iqa" style="color:${c.color}">${item.iqa.toFixed(0)}</span>`
      }
    </div>`;
  }).join("");
}

function renderRegions(containerId, regions, limit) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const maxIqa = Math.max(...regions.map(r => r.iqa));
  const items  = limit ? regions.slice(0, limit) : regions;
  el.innerHTML = items.map(r => {
    const c = iqaColor(r.iqa);
    const w = (r.iqa / maxIqa * 100).toFixed(0);
    return `<div class="region-item">
      <span class="region-name">${r.region}</span>
      <div class="region-bar-wrap">
        <div class="region-bar" style="width:${w}%;background:${c.color}"></div>
      </div>
      <span class="region-iqa" style="color:${c.color}">${r.iqa.toFixed(1)}</span>
    </div>`;
  }).join("");
}

function renderAlertsPanel(alerts) {
  const el    = document.getElementById("alerts-panel");
  const badge = document.getElementById("alert-badge-count");
  if (badge) badge.textContent = STATE.alerts.length + " alertes";
  if (!el) return;
  if (!alerts.length) {
    el.innerHTML = `<div class="empty-state"><div class="emoji">✅</div><div class="msg">Aucune alerte active</div></div>`;
    return;
  }
  el.innerHTML = alerts.map(a => {
    const c = iqaColor(a.iqa);
    return `<div class="alert-item">
      <div class="alert-icon" style="background:${c.color}">!</div>
      <div style="flex:1">
        <div class="alert-city">${a.city}</div>
        <div class="alert-region">${a.region}</div>
      </div>
      <div class="alert-right">
        <div class="alert-iqa" style="color:${c.color}">${a.iqa.toFixed(0)}</div>
        <div class="alert-level">${c.label}</div>
      </div>
    </div>`;
  }).join("");
  if (alerts.length) {
    document.getElementById("health-rec-text").textContent =
      alerts[0].recommendation || "Évitez les activités extérieures prolongées.";
  }
}

/* ══ MONTHLY IQA BAR CHART ══════════════════════════ */
async function loadMonthlyChart(city, year) {
  // Année par défaut 2025 si non spécifiée
  if (!year) year = 2025;
  try {
    const data = await get(`/monthly-iqa?city=${encodeURIComponent(city)}&year=${year}`);
    document.getElementById("chart-city-label").textContent = city;
    document.getElementById("chart-year-label").textContent = year;

    const toggle = document.getElementById("year-toggle");
    // Ancre sur 2025 comme demandé : 2025, 2024, 2023
    const baseYear = 2025;
    toggle.innerHTML = [baseYear, baseYear-1, baseYear-2].map(yr =>
      `<button class="yr-btn${yr===year?" active":""}" onclick="changeYear(${yr})">${yr}</button>`
    ).join("");

    const values = data.data[String(year)] || [];
    const colors = values.map(v => v !== null ? barColor(v) : "#e5e7eb");

    destroyChart("monthly-iqa");
    const ctx = document.getElementById("chart-monthly-iqa").getContext("2d");
    CHARTS["monthly-iqa"] = new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.months,
        datasets: [{
          data:            values,
          backgroundColor: colors,
          borderRadius:    4,
          borderSkipped:   false,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            ...CHART_DEFAULTS.tooltip,
            callbacks: {
              label: ctx => ctx.raw !== null
                ? ` IQA : ${ctx.raw}`
                : " Données non disponibles",
            },
          },
          annotation: data.oms_line ? {
            annotations: {
              oms: {
                type: "line",
                yMin: data.oms_line, yMax: data.oms_line,
                borderColor: "#ef4444", borderWidth: 1.5,
                borderDash: [5,4],
                label: { display:true, content:"OMS", color:"#ef4444",
                         font:{size:9,weight:"bold"}, position:"end" },
              }
            }
          } : {}
        },
        scales: {
          x: { ticks: CHART_DEFAULTS.tick, grid: { color: CHART_DEFAULTS.grid } },
          y: { ticks: CHART_DEFAULTS.tick, grid: { color: CHART_DEFAULTS.grid }, min: 0,
               title: { display:true, text:"IQA Global", color:"#94a3b8", font:{size:10} } },
        }
      }
    });
  } catch(e) { console.warn("Monthly chart error:", e); }
}

async function changeYear(yr) {
  STATE.selectedYear = yr;
  await loadMonthlyChart(STATE.selectedCity, yr);
}

/* ══ TIME SERIES PAGE ════════════════════════════════ */
async function buildTimeCharts() {
  const city = document.getElementById("time-city-select")?.value || STATE.selectedCity;
  try {
    const data = await get(`/timeseries?city=${encodeURIComponent(city)}&days=90&predicted=true`);
    const s    = data.series || [];
    destroyChart("ts");
    CHARTS["ts"] = new Chart(document.getElementById("chart-time-series").getContext("2d"), {
      type: "line",
      data: {
        labels: s.map(d => d.date),
        datasets: [
          { label:"IQA réel", data:s.map(d => d.iqa), borderColor:"#22c55e",
            backgroundColor:"rgba(34,197,94,0.08)", fill:true, tension:0.35,
            pointRadius:2, pointBackgroundColor:"#22c55e" },
          ...(s[0]?.iqa_predicted != null ? [{
            label:"IQA prédit (RF)", data:s.map(d => d.iqa_predicted),
            borderColor:"#f97316", fill:false, tension:0.35, pointRadius:0,
            borderDash:[4,3], backgroundColor:"transparent",
          }] : []),
        ]
      },
      options: {
        responsive:true, maintainAspectRatio:false,
        interaction:{mode:"index",intersect:false},
        plugins:{
          legend:{labels:{color:"#64748b",font:{family:"Plus Jakarta Sans",size:11},boxWidth:10}},
          tooltip:CHART_DEFAULTS.tooltip,
        },
        scales:{
          x:{ticks:CHART_DEFAULTS.tick,grid:{color:CHART_DEFAULTS.grid}},
          y:{ticks:CHART_DEFAULTS.tick,grid:{color:CHART_DEFAULTS.grid},min:0},
        }
      }
    });
  } catch(e) { console.warn(e); }

  // Compare cities — données réelles du dashboard
  if (STATE.dash) {
    const all = Object.values(STATE.dash.predictions || {})
      .sort((a, b) => b.iqa_global - a.iqa_global)
      .slice(0, 8);
    destroyChart("cmp");
    CHARTS["cmp"] = new Chart(document.getElementById("chart-compare-cities").getContext("2d"), {
      type: "bar",
      data: {
        labels: all.map(c => c.city),
        datasets: [{
          label: "IQA",
          data:  all.map(c => c.iqa_global.toFixed(1)),
          backgroundColor: all.map(c => iqaColor(c.iqa_global).color + "aa"),
          borderColor:     all.map(c => iqaColor(c.iqa_global).color),
          borderWidth: 1, borderRadius: 4,
        }],
      },
      options: {
        responsive:true, maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:CHART_DEFAULTS.tooltip},
        scales:{
          x:{ticks:CHART_DEFAULTS.tick,grid:{color:CHART_DEFAULTS.grid}},
          y:{ticks:CHART_DEFAULTS.tick,grid:{color:CHART_DEFAULTS.grid},min:0},
        }
      }
    });
  }

  // Saisons — regroupement depuis les données CSV (/timeseries 365j)
  try {
    const full    = await get(`/timeseries?city=${encodeURIComponent(city)}&days=365`);
    const bySaison = {};
    (full.series || []).forEach(d => {
      const s = d.saison || "Inconnu";
      if (!bySaison[s]) bySaison[s] = [];
      bySaison[s].push(d.iqa);
    });
    const labels = Object.keys(bySaison);
    const avgs   = labels.map(s => {
      const v = bySaison[s];
      return v.reduce((a, b) => a + b, 0) / v.length;
    });
    destroyChart("seas");
    CHARTS["seas"] = new Chart(document.getElementById("chart-seasons").getContext("2d"), {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "IQA moyen",
          data:  avgs.map(v => v.toFixed(1)),
          backgroundColor: avgs.map(v => iqaColor(v).color + "aa"),
          borderColor:     avgs.map(v => iqaColor(v).color),
          borderWidth: 1, borderRadius: 6,
        }],
      },
      options: {
        responsive:true, maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:CHART_DEFAULTS.tooltip},
        scales:{
          x:{ticks:CHART_DEFAULTS.tick,grid:{color:CHART_DEFAULTS.grid}},
          y:{ticks:CHART_DEFAULTS.tick,grid:{color:CHART_DEFAULTS.grid},min:0},
        }
      }
    });
  } catch(e) { console.warn(e); }
}

function toggleSidebar() {
  let cpt = parseInt(document.getElementById("menu-toggle").dataset.cpt || "1");
  const sidebar = document.querySelector("#sidebar");
  const btn     = document.getElementById("menu-toggle");
  if (cpt % 2 === 0) {
    sidebar.style.display = "none";
    btn.style.color       = "black";
    btn.innerHTML         = "☰";
  } else {
    sidebar.style.display = "block";
    btn.style.color       = "red";
    btn.innerHTML         = "X";
  }
  btn.dataset.cpt = cpt + 1;
}

function closeSidebar() {
  const sidebar = document.querySelector("#sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  sidebar.classList.remove("active");
  overlay.classList.remove("active");
}


/* ══ XAI PAGE ════════════════════════════════════════ */
async function buildXAI() {
  const fi      = STATE.dash?.feature_importances || {};
  const entries = Object.entries(fi).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const PALETTE = ["#22c55e","#f97316","#ef4444","#3b82f6","#a855f7",
                   "#f59e0b","#14b8a6","#ec4899","#84cc16","#06b6d4"];

  // Barres d'importance
  document.getElementById("fi-bars").innerHTML = entries.length
    ? entries.map(([name, val], i) => {
        const pct  = (val * 100).toFixed(1);
        const maxV = entries[0][1];
        const col  = PALETTE[i];
        return `<div class="fi-item">
          <div class="fi-meta"><span class="fi-name">${name}</span><span class="fi-val">${pct}%</span></div>
          <div class="fi-track"><div class="fi-fill" style="width:${(val/maxV*100).toFixed(1)}%;background:${col}"></div></div>
        </div>`;
      }).join("")
    : `<div style="color:var(--text-muted);font-size:12px">Démarrez Flask pour voir les importances</div>`;

  // Donut
  if (entries.length) {
    destroyChart("fi-donut");
    CHARTS["fi-donut"] = new Chart(document.getElementById("chart-fi-donut").getContext("2d"), {
      type: "doughnut",
      data: {
        labels: entries.map(([k]) => k),
        datasets: [{
          data:            entries.map(([, v]) => (v * 100).toFixed(2)),
          backgroundColor: PALETTE.map(c => c + "cc"),
          borderColor:     PALETTE,
          borderWidth:     1,
        }],
      },
      options: {
        responsive:true, maintainAspectRatio:false,
        plugins:{legend:{position:"right",labels:{color:"#64748b",font:{family:"Plus Jakarta Sans",size:10},boxWidth:10,padding:8}}},
      }
    });
  }

  // Scatter réel vs prédit
  const city = document.getElementById("xai-city-select")?.value || "Douala";
  try {
    const data = await get(`/timeseries?city=${encodeURIComponent(city)}&days=180&predicted=true`);
    const pts  = (data.series || []).filter(d => d.iqa_predicted != null);
    if (pts.length) {
      const allV = [...pts.map(d => d.iqa), ...pts.map(d => d.iqa_predicted)];
      const mn   = Math.max(0, Math.min(...allV) - 10);
      const mx   = Math.max(...allV) + 10;
      destroyChart("scatter");
      CHARTS["scatter"] = new Chart(document.getElementById("chart-scatter").getContext("2d"), {
        type: "scatter",
        data: {
          datasets: [
            { label:"Réel vs Prédit", data:pts.map(d => ({x:d.iqa, y:d.iqa_predicted})),
              backgroundColor:"#22c55e88", pointRadius:3 },
            { label:"Parfait", data:[{x:mn,y:mn},{x:mx,y:mx}], type:"line",
              borderColor:"#94a3b8", borderDash:[4,4], pointRadius:0, fill:false },
          ],
        },
        options: {
          responsive:true, maintainAspectRatio:false,
          plugins:{
            legend:{labels:{color:"#64748b",font:{family:"Plus Jakarta Sans",size:10}}},
            tooltip:CHART_DEFAULTS.tooltip,
          },
          scales:{
            x:{title:{display:true,text:"IQA réel",color:"#94a3b8"},ticks:CHART_DEFAULTS.tick,grid:{color:CHART_DEFAULTS.grid},min:mn,max:mx},
            y:{title:{display:true,text:"IQA prédit",color:"#94a3b8"},ticks:CHART_DEFAULTS.tick,grid:{color:CHART_DEFAULTS.grid},min:mn,max:mx},
          }
        }
      });

      // ── SHAP text — basé sur feature_importances réelles ──
      // feature_importances = importances RF (toutes positives, somme ≈ 1)
      // On classe par importance décroissante et on signale les top facteurs
      const r       = STATE.dash?.current;
      const contribs = r?.feature_contributions || {};
      const ranked   = Object.entries(contribs).sort((a, b) => b[1] - a[1]);
      const top3     = ranked.slice(0, 3);
      const bottom3  = ranked.slice(-3).reverse();  // features les moins influentes

      document.getElementById("shap-text").innerHTML = `
        <strong style="color:${iqaColor(r?.iqa_global || 70).color}">${iqaColor(r?.iqa_global || 70).label} à ${city}</strong>
        — IQA prédit : <strong>${r?.iqa_global != null ? r.iqa_global.toFixed(1) : "—"}</strong><br><br>
        <span style="color:#64748b">Facteurs <span style="color:#ef4444">les plus influents</span> :</span>
        ${top3.map(([k,v]) =>
          `<span style="color:#f97316;margin-left:6px">${k} (${(v*100).toFixed(1)}%)</span>`
        ).join("") || " —"}<br>
        <span style="color:#64748b">Facteurs <span style="color:#22c55e">les moins influents</span> :</span>
        ${bottom3.map(([k,v]) =>
          `<span style="color:#94a3b8;margin-left:6px">${k} (${(v*100).toFixed(1)}%)</span>`
        ).join("") || " —"}
        <br><br>
        <span style="color:#94a3b8;font-size:11px">
          Importances RandomForest — ${ranked.length} features · modèle : ${r?.model || "RF"}
        </span>
      `;
    }
  } catch(e) { console.warn(e); }
}


/* ══ MAP ════════════════════════════════════════════ */
async function buildMap() {
  if (!MAP) {
    MAP = L.map("map", {center:[5.5,12.0], zoom:6});
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {attribution:"© OSM", maxZoom:18}).addTo(MAP);
    const s = document.createElement("style");
    s.textContent = `.lp .leaflet-popup-content-wrapper{background:#fff;border:1px solid #e2e8f0;border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,0.12)}.lp .leaflet-popup-tip-container{display:none}`;
    document.head.appendChild(s);
  }
  Object.values(MAP_MARKERS).forEach(m => m.remove());
  MAP_MARKERS = {};

  // Toujours récupérer les coordonnées fraîches depuis /cities (source : CSV)
  // puis croiser avec les prédictions pour l'IQA
  let citiesGeo = {};
  try {
    const citiesData = await get("/cities");
    citiesGeo = citiesData.data || {};  // { CityName: { lat, lon, region, ... } }
  } catch(e) { console.warn("Map: cities fetch failed", e); }

  // Les prédictions sont dans STATE.dash si disponibles, sinon on fetch /risk-score
  let preds = STATE.dash?.predictions ? Object.values(STATE.dash.predictions) : [];
  if (!preds.length) {
    try {
      const rs = await get("/risk-score");
      preds = rs.cities || [];
    } catch(e) { console.warn("Map: risk-score fetch failed", e); }
  }

  preds.forEach(p => {
    // Coordonnées : priorité aux données CSV via /cities (source de vérité)
    const geo = citiesGeo[p.city];
    const lat = (geo?.lat != null) ? geo.lat : p.lat;
    const lon = (geo?.lon != null) ? geo.lon : p.lon;

    if (lat == null || lon == null || (lat === 0 && lon === 0)) {
      console.warn(`Map: coordonnées manquantes pour ${p.city}`);
      return;
    }

    const c      = iqaColor(p.iqa_global);
    const radius = Math.max(14, Math.min(36, p.iqa_global / 4));
    const circle = L.circleMarker([lat, lon], {
      radius, fillColor:c.color, color:c.color, weight:2, opacity:0.9, fillOpacity:0.5,
    }).addTo(MAP);

    circle.bindPopup(`
      <div style="font-family:'Plus Jakarta Sans',sans-serif;padding:4px;min-width:160px">
        <div style="font-weight:800;font-size:14px;margin-bottom:2px">${p.city}</div>
        <div style="font-size:11px;color:#64748b;margin-bottom:6px">${p.region}</div>
        <div style="font-size:26px;font-weight:800;color:${c.color};line-height:1">${p.iqa_global.toFixed(0)}</div>
        <div style="font-size:11px;color:${c.color};margin-bottom:4px">${c.label}</div>
        ${p.polluant_directeur
          ? `<div style="font-size:10px;color:#94a3b8">Polluant directeur : ${p.polluant_directeur}</div>`
          : ""}
        <div style="font-size:9px;color:#cbd5e1;margin-top:4px">${lat.toFixed(4)}, ${lon.toFixed(4)}</div>
      </div>`, {className:"lp"});

    L.marker([lat, lon], {
      icon: L.divIcon({
        className: "",
        html: `<div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:10px;font-weight:600;color:#1e293b;white-space:nowrap;text-shadow:0 1px 2px rgba(255,255,255,0.8)">${p.city}</div>`,
        iconAnchor: [-14, 4],
      })
    }).addTo(MAP);
    MAP_MARKERS[p.city] = circle;
  });
}

/* ══ ALERTS PAGE ════════════════════════════════════ */
async function buildAlertsPage() {
  try {
    const data = await get("/alerts");
    STATE.alerts = data.alerts || [];
  } catch(e) {}
  const alerts = STATE.alerts;
  const crit   = alerts.filter(a => a.iqa > 200).length;
  const high   = alerts.filter(a => a.iqa > 150 && a.iqa <= 200).length;
  const mod    = alerts.filter(a => a.iqa > 120 && a.iqa <= 150).length;
  ["al-crit","al-high","al-mod","al-total"].forEach((id, i) => {
    const el = document.getElementById(id);
    if (el) el.textContent = [crit, high, mod, alerts.length][i];
  });
  const el = document.getElementById("alerts-full-list");
  if (!el) return;
  el.innerHTML = alerts.length ? alerts.map(a => {
    const c = iqaColor(a.iqa);
    return `<div class="card" style="margin-bottom:12px">
      <div class="card-body" style="display:flex;align-items:center;gap:16px">
        <div style="width:48px;height:48px;background:${c.bg};border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0">⚠</div>
        <div style="flex:1">
          <div style="font-size:15px;font-weight:700">${a.message}</div>
          <div style="font-size:12px;color:#64748b;margin-top:2px">
            IQA : <strong style="color:${c.color}">${a.iqa.toFixed(1)}</strong> · ${a.region}
          </div>
          <div style="font-size:11px;margin-top:6px;padding:6px 10px;background:var(--bg);border-radius:6px;color:#475569">${a.recommendation}</div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div style="font-size:22px;font-weight:800;color:${c.color}">${a.iqa.toFixed(0)}</div>
          <div style="font-size:10px;font-weight:700;padding:2px 8px;background:${c.bg};color:${c.color};border-radius:20px">${a.severity || c.label}</div>
        </div>
      </div>
    </div>`;
  }).join("")
  : `<div class="empty-state"><div class="emoji">✅</div><div class="msg">Aucune alerte active</div></div>`;
}

/* ══ REGIONS PAGE ════════════════════════════════════ */
async function buildRegionsPage() {
  try {
    const data    = await get("/regions-iqa");
    const regions = data.regions || [];
    renderRegions("region-full-list", regions, 0);
    destroyChart("regions-bar");
    CHARTS["regions-bar"] = new Chart(document.getElementById("chart-regions-bar").getContext("2d"), {
      type: "bar",
      data: {
        labels: regions.map(r => r.region),
        datasets: [{
          label: "IQA moyen",
          data:  regions.map(r => r.iqa.toFixed(1)),
          backgroundColor: regions.map(r => iqaColor(r.iqa).color + "aa"),
          borderColor:     regions.map(r => iqaColor(r.iqa).color),
          borderWidth: 1, borderRadius: 6,
        }],
      },
      options: {
        indexAxis: "y", responsive:true, maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:CHART_DEFAULTS.tooltip},
        scales:{
          x:{ticks:CHART_DEFAULTS.tick,grid:{color:CHART_DEFAULTS.grid},min:0},
          y:{ticks:{...CHART_DEFAULTS.tick,font:{family:"Plus Jakarta Sans",size:11,weight:"600"}},grid:{display:false}},
        }
      }
    });
  } catch(e) { console.warn(e); }
}

/* ══ PREDICTION ═════════════════════════════════════ */
async function runPrediction() {
  const city = document.getElementById("pred-city").value;
  const btn  = document.getElementById("pred-btn");
  btn.innerHTML = '<span class="spinner"></span> Calcul...';
  btn.disabled  = true;
  try {
    const r = await post("/predict", {city, features: {
      temperature_2m_max: parseFloat(document.getElementById("pred-temp").value),
      wind_speed_10m_max: parseFloat(document.getElementById("pred-wind").value),
      precipitation_sum:  parseFloat(document.getElementById("pred-rain").value),
      iqa_global_lag_1:   parseFloat(document.getElementById("pred-lag1").value),
    }});
    const c   = iqaColor(r.iqa_global);
    const res = document.getElementById("pred-result");
    res.classList.add("show");
    document.getElementById("pr-iqa").textContent   = r.iqa_global.toFixed(1);
    document.getElementById("pr-iqa").style.color   = c.color;
    document.getElementById("pr-level").textContent = r.level;
    document.getElementById("pr-level").style.color = c.color;
    document.getElementById("pr-desc").textContent  = r.recommendation;
    document.getElementById("pr-risk").textContent  = (r.risk_score ?? 0).toFixed(0) + "%";
    const g = document.getElementById("pr-gauge");
    g.style.width      = Math.min(100, r.risk_score ?? 0) + "%";
    g.style.background = `linear-gradient(to right,#22c55e,${c.color})`;

    // Contributions de features (importances RF)
    const feats = r.feature_contributions || {};
    const maxA  = Math.max(...Object.values(feats).map(Math.abs), 0.001);
    document.getElementById("pr-features").innerHTML =
      Object.entries(feats).sort((a, b) => b[1] - a[1]).map(([k, v]) => {
        const pct = (v / maxA * 100).toFixed(1);
        const col = "#f97316";
        return `<div class="fi-item">
          <div class="fi-meta"><span class="fi-name">${k}</span><span class="fi-val">${(v*100).toFixed(2)}%</span></div>
          <div class="fi-track"><div class="fi-fill" style="width:${pct}%;background:${col}"></div></div>
        </div>`;
      }).join("") || "<div style='color:var(--text-muted);font-size:12px'>Contributions non disponibles</div>";

    // Source des données affichée
    if (r.source) {
      const sourceLabel = r.source === "csv_exact"
        ? "✅ Données CSV exactes"
        : r.source === "openmeteo"
          ? "🌦 Météo Open-Meteo"
          : r.source;
      const sourceEl = document.getElementById("pr-source");
      if (sourceEl) sourceEl.textContent = sourceLabel;
    }
  } catch(e) {
    const res = document.getElementById("pred-result");
    res.classList.add("show");
    res.innerHTML = `<div style="color:var(--red);padding:16px">⚠️ API non joignable — vérifiez que Flask tourne sur le port 5004</div>`;
  }
  btn.innerHTML = "⚡ Prédire l'IQA";
  btn.disabled  = false;
}

/* ═══ INIT ═══════════════════════════════════════════ */
async function init() {
  try {
    showLoader("Chargement des villes...");
    const citiesData = await get("/cities");
    STATE.cities = citiesData.cities || [];

    // Ville par défaut : "Douala" si présente dans la liste, sinon première du CSV
    const defaultCity = STATE.cities.find(c => c.toLowerCase() === "douala") || STATE.cities[0] || "Douala";
    STATE.selectedCity = defaultCity;

    // Année par défaut : 2025 (comme demandé)
    STATE.selectedYear = 2025;

    // Peupler uniquement le select du tableau de bord (global-city-select)
    // Les autres pages (time, xai, pred) ont leurs propres selects peuplés à la demande
    _populateSelect("global-city-select", STATE.cities, STATE.selectedCity);

  } catch(e) {
    console.warn("Cities fetch failed:", e.message);
  } finally {
    hideLoader();
  }

  await loadDashboard();
}

window.addEventListener("load", init);