// 维护台。负责人：A（GUI）。
// 只展示数据和发起操作；补货是否合法、能否退款等规则由后端判断，前端只把后端的提示显示出来。

import * as api from './api.js';
import { $, h, yuan, label, humanize, formatTime, store } from './ui.js';

const REFRESH_MS = 4000;
const FAULTS = ['CUP_JAM', 'OUT_OF_CUPS', 'WATER_TEMP_LOW', 'PUMP_ERROR'];
const SUGAR_ORDER = ['NONE', 'LIGHT', 'HALF', 'FULL'];

const state = {
  config: { demo: false, machine_id: '' },
  stock: [],
  names: {},               // 菜单项 ID → 名称
  range: 'today',
  scope: 'machine',
};

// ------------------------------------------------------------------ 工具

function operator() {
  const name = $('operator').value.trim();
  if (!name) {
    $('operator').focus();
    return null;
  }
  store.set('drink.operator', name);
  return name;
}

function message(target, text, ok) {
  const el = $(target);
  el.textContent = text;
  el.className = `form-msg ${ok ? 'ok' : 'bad'}`;
}

const errText = err => (err.code === 'NETWORK_ERROR' ? '网络连接中断' : err.message);

function startOfToday() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

function rangeSince(range) {
  if (range === 'today') return startOfToday();
  if (range === '7d') return startOfToday() - 6 * 86400000;
  return undefined;
}

function recipeText(r) {
  const names = [state.names[r.base_id] ?? r.base_id, ...r.addon_ids.map(id => state.names[id] ?? id)];
  return `${names.join(' + ')} · ${label(r.size)}/${label(r.temperature)}/${label(r.sugar)}`;
}

function statusTag(status) {
  const kind = { COMPLETED: 'ok', PRODUCTION_FAILED: 'bad', REFUNDED: 'muted', CANCELLED: 'muted', EXPIRED: 'muted',
                 AWAITING_PAYMENT: 'warn', PAID: 'warn', MAKING: 'warn' }[status] ?? '';
  return h('span', { class: `tag ${kind}` }, label(status));
}

// ------------------------------------------------------------------ 机器

function renderMachine(m) {
  const pill = $('machine-pill');
  const dot = $('machine-dot');
  if (!m) {
    pill.className = 'pill bad';
    pill.lastChild.textContent = '连接中断';
    $('machine-text').textContent = '无法连接';
    $('machine-sub').textContent = '请确认程序仍在运行';
    dot.className = 'machine-dot bad';
    dot.textContent = '?';
    return;
  }
  const text = !m.online ? '故障停机' : m.busy ? '正在制作' : '空闲待命';
  pill.className = `pill ${!m.online ? 'bad' : m.busy ? 'busy' : ''}`;
  pill.lastChild.textContent = text;
  $('machine-text').textContent = text;
  $('machine-sub').textContent = m.online ? '可以接单' : '点单页显示“暂停服务”，排除故障后自动恢复';
  $('machine-id').textContent = `机器 ${m.machine_id}`;
  dot.className = `machine-dot ${!m.online ? 'bad' : m.busy ? 'busy' : ''}`;
  dot.textContent = !m.online ? '!' : m.busy ? '…' : '✓';

  $('fault-list').replaceChildren(...m.faults.map(code => h('div', { class: 'fault' },
    h('span', {}, label(code)),
    h('button', { type: 'button', class: 'btn danger small', onclick: () => clearFault(code) }, '已排除'))));
  $('clear-all').hidden = m.faults.length < 2;
}

async function clearFault(code) {
  try {
    renderMachine(await api.clearFault(code));
  } catch (err) {
    alertBox(errText(err));
  }
}

async function injectFault(code) {
  try {
    renderMachine(await api.devFault(code));
  } catch (err) {
    alertBox(errText(err));
  }
}

function alertBox(text) {
  $('updated-at').textContent = `操作失败：${text}`;
}

// ------------------------------------------------------------------ 库存与补货

function renderStock() {
  const low = state.stock.filter(s => s.status !== 'OK').length;
  $('kpi-stock').textContent = low;
  $('kpi-stock-box').className = `kpi ${low ? 'warn' : ''}`;

  $('stock').replaceChildren(...state.stock.map(s => {
    const m = s.material;
    const pct = Math.min(100, (s.quantity / m.capacity) * 100);
    const warnPct = Math.min(100, (m.warn_threshold / m.capacity) * 100);
    return h('tr', {},
      h('td', {}, m.name),
      h('td', { class: 'num' }, `${s.quantity} ${m.unit}`),
      h('td', { class: 'num' }, `${m.capacity}`),
      h('td', {}, h('div', { class: `meter ${s.status.toLowerCase()}`, title: `预警线 ${m.warn_threshold} ${m.unit}` },
        h('i', { style: { width: `${pct}%` } }), h('s', { style: { left: `${warnPct}%` } }))),
      h('td', {}, h('span', { class: `tag ${{ OK: 'ok', LOW: 'warn', EMPTY: 'bad' }[s.status]}` }, label(s.status))),
      h('td', {}, s.quantity < m.capacity
        ? h('button', { type: 'button', class: 'link-btn', onclick: () => pickMaterial(m.id, true) }, '补货')
        : null));
  }));

  const select = $('material');
  const current = select.value;
  select.replaceChildren(...state.stock.map(s => h('option', { value: s.material.id },
    `${s.material.name}（${s.quantity}/${s.material.capacity} ${s.material.unit}）`)));
  if (current) select.value = current;
  updateRoom();
}

function room() {
  const s = state.stock.find(x => x.material.id === $('material').value);
  return s ? { left: s.material.capacity - s.quantity, unit: s.material.unit } : { left: 0, unit: '' };
}

function updateRoom() {
  const { left, unit } = room();
  $('room').textContent = left > 0 ? `最多还能补 ${left} ${unit}` : '已经是满仓';
}

function pickMaterial(id, fill) {
  $('material').value = id;
  updateRoom();
  if (fill) $('qty').value = room().left;
  $('qty').focus();
}

async function submitRestock(e) {
  e.preventDefault();
  const name = operator();
  if (!name) return message('restock-msg', '请先在右上角填写操作人', false);
  const qty = Number($('qty').value);
  try {
    const level = await api.restock($('material').value, Number.isInteger(qty) ? qty : $('qty').value, name);
    message('restock-msg', `已补货：${level.material.name} 现有 ${level.quantity} ${level.material.unit}`, true);
    $('qty').value = '';
    await refresh();
  } catch (err) {
    message('restock-msg', errText(err), false);
  }
}

function renderRestocks(records) {
  const names = Object.fromEntries(state.stock.map(s => [s.material.id, s.material]));
  $('restocks').replaceChildren(...(records.length ? records.map(r => h('li', {},
    h('span', {}, h('b', {}, names[r.material_id]?.name ?? r.material_id), ` +${r.quantity} ${names[r.material_id]?.unit ?? ''}`),
    h('span', {}, `${r.operator} · ${formatTime(r.created_at)}`))) : [h('li', {}, '还没有补货记录')]));
}

// ------------------------------------------------------------------ 订单

function renderFailed(orders) {
  $('kpi-failed').textContent = orders.length;
  $('kpi-failed-box').className = `kpi ${orders.length ? 'bad' : ''}`;
  $('failed-orders').replaceChildren(...(orders.length ? orders.map(o => h('div', { class: 'order-row' },
    h('div', {}, h('div', {}, recipeText(o.recipe)), h('div', { class: 'meta' }, `${o.order_id} · ${formatTime(o.created_at)}`)),
    h('div', { class: 'right' }, h('b', {}, yuan(o.total_fen)),
      h('button', { type: 'button', class: 'btn danger small', onclick: () => refund(o) }, '退款')),
    h('div', { class: 'reason' }, humanize(o.failure_reason)))) : [h('p', { class: 'empty' }, '没有待处理的订单')]));
}

async function refund(order) {
  const name = operator();
  if (!name) return message('refund-msg', '请先在右上角填写操作人', false);
  if (!window.confirm(`确认给订单 ${order.order_id} 退款 ${yuan(order.total_fen)}？`)) return;
  try {
    await api.refund(order.order_id, name);
    message('refund-msg', `已退款 ${yuan(order.total_fen)}`, true);
    await refresh();
  } catch (err) {
    message('refund-msg', errText(err), false);
  }
}

function renderRecent(orders) {
  $('recent-orders').replaceChildren(...(orders.length ? orders.map(o => h('div', { class: 'order-row' },
    h('div', {}, h('div', {}, recipeText(o.recipe)), h('div', { class: 'meta' }, `${formatTime(o.created_at)} · ${o.order_id}`)),
    h('div', { class: 'right' }, h('span', {}, yuan(o.total_fen)), statusTag(o.status)))) : [h('p', { class: 'empty' }, '还没有订单')]));
}

// ------------------------------------------------------------------ 统计

function hbars(target, rows) {
  const max = Math.max(1, ...rows.map(r => r.value));
  $(target).replaceChildren(...(rows.length ? rows.map(r => h('div', { class: 'hbar' },
    h('span', {}, r.label), h('b', {}, r.value),
    h('div', { class: 'track' }, h('i', { style: { width: `${(r.value / max) * 100}%` } })))) : [h('p', { class: 'empty' }, '暂无数据')]));
}

function renderStats(s) {
  const avg = s.order_count ? yuan(Math.round(s.revenue_fen / s.order_count)) : '—';
  const rangeText = { today: '今天', '7d': '近 7 天', all: '全部时间' }[state.range];
  $('stats-summary').textContent =
    `${rangeText} · ${s.machine_id ? `机器 ${s.machine_id}` : '全部机器'}：完成 ${s.order_count} 杯，收入 ${yuan(s.revenue_fen)}，客单价 ${avg}`;

  const byHour = s.by_hour ?? {};
  const max = Math.max(1, ...Object.values(byHour));
  $('hour-chart').replaceChildren(...Array.from({ length: 24 }, (_, hr) => {
    const n = byHour[String(hr)] ?? 0;
    return h('div', { class: `bar ${n ? 'has' : ''}`, style: { height: `${(n / max) * 100}%` }, title: `${hr} 点：${n} 杯` });
  }));
  $('hour-axis').replaceChildren(...Array.from({ length: 24 }, (_, hr) => h('span', {}, hr % 3 === 0 ? hr : '')));

  hbars('combos', s.top_combos.map(c => ({ label: c.label, value: c.count })));
  hbars('sugars', SUGAR_ORDER.filter(k => s.by_sugar[k]).map(k => ({ label: label(k), value: s.by_sugar[k] })));
}

async function loadStats() {
  try {
    const machine_id = state.scope === 'machine' ? state.config.machine_id : undefined;
    renderStats(await api.getStats({ machine_id, since_ms: rangeSince(state.range) }));
  } catch {
    /* 下次刷新再试 */
  }
}

async function loadToday() {
  try {
    const s = await api.getStats({ machine_id: state.config.machine_id, since_ms: startOfToday() });
    $('kpi-cups').textContent = s.order_count;
    $('kpi-revenue').textContent = yuan(s.revenue_fen);
    $('kpi-avg').textContent = s.order_count ? yuan(Math.round(s.revenue_fen / s.order_count)) : '—';
  } catch {
    /* 下次刷新再试 */
  }
}

function bindTabs(id, key, attr) {
  $(id).addEventListener('click', e => {
    const btn = e.target.closest('button');
    if (!btn) return;
    state[key] = btn.dataset[attr];
    $(id).querySelectorAll('button').forEach(b => b.classList.toggle('on', b === btn));
    loadStats();
  });
}

// ------------------------------------------------------------------ 刷新

async function refresh() {
  const results = await Promise.allSettled([
    api.getMachine(), api.getStock(), api.getOrders('PRODUCTION_FAILED'), api.getOrders(undefined, 12), api.getRestocks(6),
  ]);
  const [machine, stock, failed, recent, restocks] = results.map(r => (r.status === 'fulfilled' ? r.value : null));
  renderMachine(machine);
  if (stock) { state.stock = stock; renderStock(); }
  if (failed) renderFailed(failed);
  if (recent) renderRecent(recent);
  if (restocks) renderRestocks(restocks);
  await Promise.all([loadToday(), loadStats()]);
  $('updated-at').textContent = machine ? `更新于 ${formatTime(Date.now()).slice(6)}` : '连接中断，正在重试…';
}

async function init() {
  $('operator').value = store.get('drink.operator');
  $('operator').addEventListener('change', () => store.set('drink.operator', $('operator').value.trim()));
  $('restock-form').addEventListener('submit', submitRestock);
  $('material').addEventListener('change', updateRoom);
  $('fill').addEventListener('click', () => { $('qty').value = room().left || ''; });
  $('clear-all').addEventListener('click', () => clearFault());
  bindTabs('range-tabs', 'range', 'range');
  bindTabs('scope-tabs', 'scope', 'scope');

  try {
    state.config = await api.getConfig();
  } catch {
    /* 用默认配置 */
  }
  $('demo-box').hidden = !state.config.demo;
  $('demo-faults').replaceChildren(...FAULTS.map(code =>
    h('button', { type: 'button', class: 'btn ghost small', onclick: () => injectFault(code) }, label(code))));

  try {
    const menu = await api.getMenu();
    state.names = Object.fromEntries([...menu.bases, ...menu.addons].map(e => [e.item.id, e.item.name]));
  } catch {
    /* 订单里显示 ID */
  }
  await refresh();
  setInterval(refresh, REFRESH_MS);
}

init();
