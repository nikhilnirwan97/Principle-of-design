// ── State ─────────────────────────────────────────────────────────────────
let currentStation = 3;
let liveInterval = null;
let map = null;
let mapMarkers = [];
let chartBOD = null, chartDO = null;

// ── Navigation ────────────────────────────────────────────────────────────
function showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(a => a.classList.remove('active'));
  document.getElementById('page-' + id).classList.add('active');
  document.querySelector(`[data-page="${id}"]`).classList.add('active');
  document.getElementById('sidebar').classList.remove('open');

  if (id === 'dashboard') startLive();
  else stopLive();

  if (id === 'map') initMap();
  if (id === 'analytics') loadCharts(document.getElementById('chart-station').value);
  if (id === 'reports') loadReports('ALL', document.querySelector('#report-filters .active'));
  if (id === 'alerts') loadAlerts();
}

// ── Live Dashboard ─────────────────────────────────────────────────────────
function changeStation(sid) {
  currentStation = parseInt(sid);
  fetchLive();
}

function startLive() {
  fetchLive();
  loadStationTable();
  if (liveInterval) clearInterval(liveInterval);
  liveInterval = setInterval(() => { fetchLive(); loadStationTable(); }, 10000);
}

function stopLive() {
  if (liveInterval) { clearInterval(liveInterval); liveInterval = null; }
}

async function fetchLive() {
  try {
    const res = await fetch(`/api/live?station=${currentStation}`);
    const d = await res.json();
    renderLive(d);
  } catch(e) { console.error('Live fetch error', e); }
}

function renderLive(d) {
  // Score banner
  const scoreEl = document.getElementById('score-num');
  animateNumber(scoreEl, parseInt(scoreEl.textContent) || 0, d.score, 800);
  document.getElementById('score-status').textContent = d.label;
  document.getElementById('score-status').style.color = levelColor(d.label);
  document.getElementById('score-marker').style.left = `${d.score}%`;
  document.getElementById('station-name-badge').textContent = `Station: ${d.station}`;
  document.getElementById('live-timestamp').textContent = `Updated: ${d.timestamp}`;

  // BOD
  setMetric('bod', d.bod, d.bod > 50 ? 'CRITICAL' : d.bod > 20 ? 'HIGH' : d.bod > 5 ? 'MODERATE' : 'GOOD',
    Math.min(100, d.bod / 120 * 100), `${d.bod}`, 'mc-bod');

  // DO
  setMetric('do', d.do, d.do < 2 ? 'CRITICAL' : d.do < 4 ? 'HIGH' : d.do < 6 ? 'MODERATE' : 'GOOD',
    Math.min(100, d.do / 9 * 100), `${d.do}`, 'mc-do');

  // pH
  const phStatus = (d.ph < 6.5 || d.ph > 8.5) ? 'HIGH' : (d.ph < 7 || d.ph > 8) ? 'MODERATE' : 'GOOD';
  setMetric('ph', d.ph, phStatus, Math.abs(d.ph - 7) / 3 * 100, `${d.ph}`, 'mc-ph');

  // Turbidity
  setMetric('turb', d.turbidity,
    d.turbidity > 100 ? 'CRITICAL' : d.turbidity > 50 ? 'HIGH' : d.turbidity > 20 ? 'MODERATE' : 'GOOD',
    Math.min(100, d.turbidity / 200 * 100), `${d.turbidity}`, 'mc-turb');

  // Nitrates
  setMetric('nit', d.nitrates,
    d.nitrates > 30 ? 'HIGH' : d.nitrates > 10 ? 'MODERATE' : 'GOOD',
    Math.min(100, d.nitrates / 50 * 100), `${d.nitrates}`, 'mc-nit');

  // Coliform
  const colLevel = d.coliform === 'CRITICAL' ? 'CRITICAL' :
                   d.coliform === 'VERY HIGH' ? 'HIGH' :
                   d.coliform === 'HIGH' ? 'HIGH' :
                   d.coliform === 'MODERATE' ? 'MODERATE' : 'LOW';
  document.getElementById('v-col').textContent = d.coliform;
  document.getElementById('v-col').style.color = levelColor(colLevel);
  setBadge('b-col', colLevel);
}

function setMetric(key, raw, status, pct, display, cardId) {
  document.getElementById(`v-${key}`).textContent = display;
  document.getElementById(`v-${key}`).style.color = levelColor(status);
  setBadge(`b-${key}`, status);
  const bar = document.getElementById(`bar-${key}`);
  bar.style.width = pct + '%';
  bar.style.background = levelColor(status);
  const card = document.getElementById(cardId);
  card.className = 'metric-card ' + status.toLowerCase();
}

function setBadge(id, status) {
  const el = document.getElementById(id);
  el.textContent = status;
  el.className = 'mc-badge ' + status.toLowerCase();
}

function levelColor(s) {
  const map = { CRITICAL: '#e63946', HIGH: '#f4a261', MODERATE: '#f9c74f', GOOD: '#2a9d8f', POOR: '#f4a261', LOW: '#94a3b8' };
  return map[s] || '#94a3b8';
}

async function loadStationTable() {
  try {
    const res = await fetch('/api/stations');
    const stations = await res.json();
    const tbody = document.getElementById('station-tbody');
    tbody.innerHTML = stations.map(s => `
      <tr>
        <td><strong>${s.name}</strong></td>
        <td style="color:var(--text2)">${s.stretch}</td>
        <td><strong>${s.score}</strong></td>
        <td style="color:${s.bod > 50 ? 'var(--critical)' : 'inherit'}">${s.bod}</td>
        <td style="color:${s.do < 3 ? 'var(--critical)' : 'inherit'}">${s.do}</td>
        <td>${s.ph}</td>
        <td><span class="status-pill ${s.label}">${s.label}</span></td>
      </tr>
    `).join('');
  } catch(e) { console.error(e); }
}

// ── Map ────────────────────────────────────────────────────────────────────
function initMap() {
  if (map) return;
  map = L.map('leaflet-map').setView([28.65, 77.23], 11);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap',
    maxZoom: 18
  }).addTo(map);

  // Monitoring stations
  const stationDots = [
    { lat: 28.877, lng: 77.175, name: 'Palla',      color: '#2a9d8f', label: 'GOOD' },
    { lat: 28.739, lng: 77.218, name: 'Wazirabad',  color: '#f4a261', label: 'POOR' },
    { lat: 28.610, lng: 77.248, name: 'Nizamuddin', color: '#e63946', label: 'CRITICAL' },
    { lat: 28.535, lng: 77.272, name: 'Okhla',      color: '#e63946', label: 'CRITICAL' },
    { lat: 28.430, lng: 77.300, name: 'Agra Canal', color: '#f4a261', label: 'POOR' },
  ];

  stationDots.forEach(s => {
    L.circleMarker([s.lat, s.lng], { radius: 12, color: '#fff', weight: 2, fillColor: s.color, fillOpacity: 0.9 })
      .addTo(map)
      .bindPopup(`<b>${s.name}</b><br>Status: <b style="color:${s.color}">${s.label}</b>`);
  });

  // Incident reports
  loadMapReports();
}

async function loadMapReports() {
  try {
    const res = await fetch('/api/reports');
    const reports = await res.json();
    mapMarkers.forEach(m => map.removeLayer(m));
    mapMarkers = [];

    reports.forEach(r => {
      const lat = parseFloat(r.lat) || 28.65 + (Math.random() - 0.5) * 0.3;
      const lng = parseFloat(r.lng) || 77.23 + (Math.random() - 0.5) * 0.2;
      const color = r.severity === 'CRITICAL' ? '#e63946' : r.severity === 'HIGH' ? '#f4a261' : '#f9c74f';
      const m = L.marker([lat, lng], {
        icon: L.divIcon({
          className: '',
          html: `<div style="background:${color};width:14px;height:14px;border-radius:50%;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.4)"></div>`,
          iconSize: [14, 14],
          iconAnchor: [7, 7]
        })
      }).addTo(map).bindPopup(`
        <b>${r.type}</b><br>${r.location}<br>
        <span style="color:${color}">${r.severity}</span> · ${r.status}
      `);
      mapMarkers.push(m);
    });
  } catch(e) { console.error(e); }
}

function filterMap(type, el) {
  document.querySelectorAll('.map-controls-bar .filter-pill').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
}

// ── Charts ─────────────────────────────────────────────────────────────────
async function loadCharts(sid) {
  try {
    const res = await fetch(`/api/history?station=${sid}`);
    const d = await res.json();

    if (chartBOD) chartBOD.destroy();
    if (chartDO) chartDO.destroy();

    const bodCtx = document.getElementById('chart-bod').getContext('2d');
    chartBOD = new Chart(bodCtx, {
      type: 'line',
      data: {
        labels: d.labels,
        datasets: [{
          label: 'BOD (mg/L)',
          data: d.bod,
          borderColor: '#e63946',
          backgroundColor: 'rgba(230,57,70,0.1)',
          fill: true,
          tension: 0.4,
          pointRadius: 3
        }]
      },
      options: chartOptions('#e63946')
    });

    const doCtx = document.getElementById('chart-do').getContext('2d');
    chartDO = new Chart(doCtx, {
      type: 'line',
      data: {
        labels: d.labels,
        datasets: [{
          label: 'DO (mg/L)',
          data: d.do,
          borderColor: '#2a9d8f',
          backgroundColor: 'rgba(42,157,143,0.1)',
          fill: true,
          tension: 0.4,
          pointRadius: 3
        }]
      },
      options: chartOptions('#2a9d8f')
    });
  } catch(e) { console.error(e); }
}

function chartOptions(color) {
  return {
    responsive: true,
    plugins: { legend: { labels: { color: '#94a3b8', font: { size: 12 } } } },
    scales: {
      x: { ticks: { color: '#94a3b8', font: { size: 11 } }, grid: { color: '#2d3748' } },
      y: { ticks: { color: '#94a3b8' }, grid: { color: '#2d3748' } }
    }
  };
}

// ── Report Form ─────────────────────────────────────────────────────────────
function updateCounter(el) {
  document.getElementById('desc-counter').textContent = `${el.value.length}/500`;
}

function getGPS() {
  if (!navigator.geolocation) return showToast('GPS not supported');
  navigator.geolocation.getCurrentPosition(pos => {
    document.getElementById('form-lat').value = pos.coords.latitude;
    document.getElementById('form-lng').value = pos.coords.longitude;
    showToast(`📍 GPS set: ${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)}`);
  }, () => showToast('Could not get location'));
}

function previewPhoto(input) {
  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = e => {
      const img = document.getElementById('photo-preview');
      img.src = e.target.result;
      img.style.display = 'block';
    };
    reader.readAsDataURL(input.files[0]);
  }
}

function dropFile(e) {
  e.preventDefault();
  const input = document.getElementById('photo-input');
  input.files = e.dataTransfer.files;
  previewPhoto(input);
}

async function submitReport(e) {
  e.preventDefault();
  const btn = document.getElementById('submit-btn');
  btn.textContent = 'Submitting…';
  btn.disabled = true;

  const formData = new FormData(e.target);

  try {
    const res = await fetch('/api/reports', { method: 'POST', body: formData });
    const d = await res.json();
    if (d.success) {
      showMsg('success', `✅ Report #${d.id} submitted successfully!`);
      e.target.reset();
      document.getElementById('photo-preview').style.display = 'none';
      document.getElementById('desc-counter').textContent = '0/500';
    } else {
      showMsg('error', '❌ Submission failed. Please try again.');
    }
  } catch(err) {
    showMsg('error', '❌ Network error. Please try again.');
  }

  btn.textContent = 'Submit Report';
  btn.disabled = false;
}

function showMsg(type, text) {
  const el = document.getElementById('form-msg');
  el.className = 'form-msg ' + type;
  el.textContent = text;
  el.style.display = 'block';
  setTimeout(() => el.style.display = 'none', 5000);
}

// ── All Reports ─────────────────────────────────────────────────────────────
async function loadReports(status, el) {
  if (el) {
    document.querySelectorAll('#report-filters .filter-pill').forEach(p => p.classList.remove('active'));
    el.classList.add('active');
  }
  try {
    const res = await fetch(`/api/reports?status=${status}`);
    const reports = await res.json();
    const container = document.getElementById('reports-list');

    if (!reports.length) {
      container.innerHTML = '<div style="color:var(--text2);padding:40px;text-align:center">No reports found</div>';
      return;
    }

    container.innerHTML = reports.map(r => {
      const imgSrc = r.photo_url || '';
      const imgHTML = imgSrc
        ? `<img src="${imgSrc}" alt="photo" class="report-card-img" onerror="this.style.display='none'">`
        : `<div class="report-card-img" style="display:flex;align-items:center;justify-content:center;font-size:28px">📍</div>`;
      return `
        <div class="report-card" id="rc-${r.id}">
          ${imgHTML}
          <div class="report-card-body">
            <div class="report-card-title">${r.type}</div>
            <span class="status-pill ${r.severity}">${r.severity}</span>
            &nbsp;<span class="status-pill ${r.status}">${r.status}</span>
            <div class="report-card-meta">
              <span>📍 ${r.location}</span>
              <span>🏭 ${r.station}</span>
              <span>🕐 ${r.created_at}</span>
            </div>
            ${r.description ? `<p style="margin-top:10px;color:var(--text2);font-size:13px">${r.description}</p>` : ''}
            <div class="report-card-actions">
              <button class="btn-sm" onclick="updateReportStatus(${r.id},'ASSIGNED')">Assign</button>
              <button class="btn-sm" onclick="updateReportStatus(${r.id},'RESOLVED')">Resolve</button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch(e) { console.error(e); }
}

async function updateReportStatus(id, status) {
  await fetch(`/api/reports/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status })
  });
  showToast(`Report #${id} marked as ${status}`);
  loadReports('ALL', null);
}

// ── Alerts ─────────────────────────────────────────────────────────────────
async function loadAlerts() {
  try {
    const res = await fetch('/api/alerts');
    const alerts = await res.json();
    const container = document.getElementById('alerts-list');
    container.innerHTML = alerts.map(a => `
      <div class="alert-card ${a.level}">
        <div>
          <div class="alert-title">⚠️ ${a.parameter} at ${a.station}</div>
          <div class="alert-detail">Measured: <strong>${a.value}</strong> · Threshold: ${a.threshold} · ${a.created_at}</div>
        </div>
        <span class="status-pill ${a.level}">${a.level}</span>
      </div>
    `).join('');
  } catch(e) { console.error(e); }
}

// ── Toast ───────────────────────────────────────────────────────────────────
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}

// ── Util ────────────────────────────────────────────────────────────────────
function animateNumber(el, from, to, duration) {
  const start = performance.now();
  requestAnimationFrame(function step(ts) {
    const progress = Math.min((ts - start) / duration, 1);
    el.textContent = Math.round(from + (to - from) * progress);
    if (progress < 1) requestAnimationFrame(step);
  });
}

// ── Init ────────────────────────────────────────────────────────────────────
showPage('dashboard');

// ── Auth / User ─────────────────────────────────────────────────────────────
async function loadUser() {
  try {
    const res = await fetch('/auth/me');
    const d = await res.json();
    if (!d.logged_in) { window.location.href = '/'; return; }
    // Sidebar
    const initials = d.name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0,2);
    document.getElementById('user-avatar-initials').textContent = initials;
    document.getElementById('sidebar-user-name').textContent = d.name;
    document.getElementById('sidebar-user-role').textContent = d.role;
    // Profile page
    document.getElementById('prof-avatar').textContent = initials;
    document.getElementById('prof-name').textContent = d.name;
    document.getElementById('prof-role').textContent = d.role;
  } catch(e) { console.error(e); }
}

async function doLogout() {
  await fetch('/auth/logout', { method: 'POST' });
  window.location.href = '/';
}

// ── Profile Page ─────────────────────────────────────────────────────────────
async function loadProfile() {
  try {
    const [statsRes, rptRes] = await Promise.all([
      fetch('/api/profile/stats'),
      fetch('/api/reports?mine=1')
    ]);
    const stats = await statsRes.json();
    const reports = await rptRes.json();

    document.getElementById('pstat-total').textContent = stats.total;
    document.getElementById('pstat-pending').textContent = stats.pending;
    document.getElementById('pstat-resolved').textContent = stats.resolved;
    document.getElementById('pstat-impact').textContent = stats.impact + ' pts';

    const container = document.getElementById('my-reports-list');
    if (!reports.length) {
      container.innerHTML = '<div style="color:var(--text2);padding:24px">No reports yet. Go report some pollution!</div>';
      return;
    }
    container.innerHTML = reports.map(r => {
      const imgHTML = r.photo_url
        ? `<img src="${r.photo_url}" alt="photo" class="report-card-img">`
        : `<div class="report-card-img" style="display:flex;align-items:center;justify-content:center;font-size:28px">📍</div>`;
      return `<div class="report-card">
        ${imgHTML}
        <div class="report-card-body">
          <div class="report-card-title">${r.type}</div>
          <span class="status-pill ${r.severity}">${r.severity}</span>
          &nbsp;<span class="status-pill ${r.status}">${r.status}</span>
          <div class="report-card-meta">
            <span>📍 ${r.location}</span>
            <span>🏭 ${r.station}</span>
            <span>🕐 ${r.created_at}</span>
          </div>
        </div>
      </div>`;
    }).join('');
  } catch(e) { console.error(e); }
}

// Patch showPage to load profile
const _origShowPage = showPage;
window.showPage = function(id) {
  _origShowPage(id);
  if (id === 'profile') loadProfile();
};

// Init on load
loadUser();
