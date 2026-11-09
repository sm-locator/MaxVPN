const API = '/api/appliance/v1/status';
const state = { status: null };

const $ = (id) => document.getElementById(id);

function formatBytesGiB(valueGiB) {
  const n = Number(valueGiB);
  if (!Number.isFinite(n)) return '—';
  return `${n.toFixed(2)} GiB`;
}

function formatHandshake(text) {
  if (!text) return 'нет данных';
  const m = String(text).match(/latest handshake:\s*([^\n]+)/i);
  return m ? m[1].trim() : 'есть';
}

function parseRuntime(runtime) {
  const text = runtime || '';
  const pick = (re) => {
    const m = text.match(re);
    return m ? m[1].trim() : '—';
  };
  return {
    port: pick(/listening port:\s*([^\n]+)/i),
    endpoint: pick(/endpoint:\s*([^\n]+)/i),
    keepalive: pick(/persistent keepalive:\s*([^\n]+)/i),
    rx: pick(/transfer:\s*([^\n]+)/i).replace(/,.*/, '').replace(/^transfer:\s*/i, ''),
    tx: pick(/transfer:[^\n]*?,\s*([^\n]+)/i),
  };
}

function formatUptime(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d} д ${h} ч`;
  if (h) return `${h} ч ${m} мин`;
  return `${m} мин`;
}

function extractRoutes(text) {
  const lines = String(text || '').split('\n').map((x) => x.trim()).filter(Boolean);
  return {
    all: lines,
    vpn: lines.find((x) => /10\.8\.0\.0\/24/.test(x)) || '—',
    lan: lines.find((x) => /192\.168\.8\.0\/24/.test(x)) || '—',
  };
}

function showToast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => el.classList.remove('show'), 2500);
}

function switchView(view) {
  document.querySelectorAll('.nav-item').forEach((el) => el.classList.toggle('active', el.dataset.view === view));
  document.querySelectorAll('.view').forEach((el) => el.classList.remove('active-view'));
  $(`view-${view}`).classList.add('active-view');
  const title = { dashboard:'Обзор', vpn:'VPN', routing:'Smart Routing', devices:'Устройства', dns:'DNS', system:'Система' }[view] || 'Обзор';
  $('viewTitle').textContent = title;
}

document.querySelectorAll('.nav-item').forEach((el) => el.addEventListener('click', () => switchView(el.dataset.view)));
$('refreshBtn').addEventListener('click', () => loadStatus(true));

async function loadStatus(manual = false) {
  const btn = $('refreshBtn');
  btn.disabled = true;
  try {
    const response = await fetch(API, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.status = data;
    render(data);
    $('lastUpdated').textContent = `Обновлено ${new Date().toLocaleTimeString('ru-RU')}`;
    if (manual) showToast('Состояние обновлено');
  } catch (error) {
    $('heroStatus').textContent = 'ОШИБКА';
    $('sidebarDot').classList.remove('ok');
    $('sidebarState').textContent = 'Нет связи с appliance';
    showToast(`Не удалось получить статус: ${error.message}`);
  } finally {
    btn.disabled = false;
  }
}

function render(data) {
  const runtime = data?.vpn?.runtime || '';
  const parsed = parseRuntime(runtime);
  const routes = extractRoutes(data?.smart_routing?.table_200 || '');
  const board = data?.board || {};
  const release = board.release || {};

  $('heroStatus').textContent = String(data.status || 'RUNNING').toUpperCase();
  $('sidebarState').textContent = 'Соединение активно';
  $('sidebarDot').classList.add('ok');
  $('vpnState').textContent = 'Подключён';
  $('vpnMeta').textContent = data?.vpn?.interface || 'WireGuard';
  $('handshake').textContent = formatHandshake(runtime);
  const transfer = String(runtime).match(/transfer:\s*([^\n]+)/i);
  if (transfer) {
    const parts = transfer[1].split(',').map((x) => x.trim());
    $('rx').textContent = parts[0] || '—';
    $('tx').textContent = parts[1] || '—';
  } else {
    $('rx').textContent = parsed.rx;
    $('tx').textContent = parsed.tx;
  }

  $('vpnInterface').textContent = data?.vpn?.interface || '—';
  $('vpnPort').textContent = parsed.port;
  $('vpnEndpoint').textContent = parsed.endpoint;
  $('vpnKeepalive').textContent = parsed.keepalive;
  $('routingRule').textContent = data?.smart_routing?.ip_rule?.split('\n').find((x) => /fwmark 0x64/.test(x))?.trim() || '—';
  $('routingTable').textContent = `${routes.all.length} маршрутов`;
  $('routingVpn').textContent = routes.vpn;
  $('routingLan').textContent = routes.lan;

  $('vpnRuntime').textContent = runtime || 'Нет данных';
  $('routingRuntime').textContent = data?.smart_routing?.table_200 || 'Нет данных';

  $('systemModel').textContent = board.model || '—';
  $('systemOs').textContent = release.version ? `${release.distribution || 'OpenWrt'} ${release.version}` : '—';
  $('systemKernel').textContent = board.kernel || '—';
  $('systemPython').textContent = data.python || '—';
  $('systemStatus').textContent = data.status || '—';
  $('systemUptime').textContent = formatUptime(data.uptime_seconds);
  $('systemHostname').textContent = board.hostname || '—';
}

loadStatus();
window.setInterval(() => loadStatus(false), 15000);
