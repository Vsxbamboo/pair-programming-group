// 点单页（售货机触摸屏）。负责人：A（GUI）。
// 只负责展示和收集操作：价格、能否售卖、订单状态全部以后端返回为准（见 docs/04-接口契约.md）。
//
// 界面状态（view）：
//   loading → menu → custom ⇄ submitting → paying → making → done
//                                            │         └──→ failed
//                                            └──→ closed（取消 / 超时）
//   机器离线且没有进行中的订单时，盖上“暂停服务”。

import * as api from './api.js';
import { $, h, yuan, label, humanize, SIZE_ML } from './ui.js';

const POLL_MS = 1000;
const MENU_REFRESH_MS = 20000;
const MACHINE_REFRESH_MS = 4000;
const DONE_RESET_MS = 15000;
const IDLE_RESET_MS = 90000;
const MAX_ADDONS = 3;
const ACTIVE = ['AWAITING_PAYMENT', 'PAID', 'MAKING'];

const state = {
  config: { demo: false, machine_id: '', payment_method: 'mock', pay_base_url: location.origin },
  menu: null,
  machine: null,
  recipe: null,
  recs: [],
  quote: null,
  quoteError: null,
  view: 'loading',
  order: null,
  progress: null,
  message: '',          // 底部操作栏的错误提示
  payDeadline: 0,
  payTotalMs: 1,
};

let quoteSeq = 0;
let pollTimer = null;
let resetTimer = null;
let idleTimer = null;

// ------------------------------------------------------------------ 工具

const entry = id => [...(state.menu?.bases ?? []), ...(state.menu?.addons ?? [])].find(e => e.item.id === id);
const itemName = id => entry(id)?.item.name ?? id;
const friendly = err => (err?.code === 'NETWORK_ERROR' ? '网络连接中断，请稍后再试。' : err?.message || '出了点问题，请稍后再试。');

function recipeDetail(r) {
  return [label(r.size), label(r.temperature), label(r.sugar),
    r.addon_ids.length ? r.addon_ids.map(itemName).join('+') : '不加料'].join(' · ');
}

function setView(view) {
  state.view = view;
  armIdleTimer();
  render();
}

function armIdleTimer() {
  clearTimeout(idleTimer);
  if (state.view === 'custom') idleTimer = setTimeout(() => goMenu(), IDLE_RESET_MS);
}

// ------------------------------------------------------------------ 配方

function normalizeRecipe() {
  const r = state.recipe;
  const base = entry(r.base_id)?.item;
  if (!base) return;
  if (r.temperature === 'HOT' && !base.hot_allowed) r.temperature = base.iced_allowed ? 'ICED' : 'NORMAL';
  if (r.temperature === 'ICED' && !base.iced_allowed) r.temperature = 'NORMAL';
}

function freshRecipe(baseId) {
  const recipe = structuredClone(state.menu.default_recipe);
  if (baseId) recipe.base_id = baseId;
  recipe.addon_ids = recipe.addon_ids.filter(id => entry(id)?.available);
  return recipe;
}

function unavailableParts() {
  const r = state.recipe;
  return [r.base_id, ...r.addon_ids].filter(id => !entry(id)?.available).map(itemName);
}

function updateRecipe(change) {
  if (state.view !== 'custom') return;
  change(state.recipe);
  normalizeRecipe();
  state.message = '';
  armIdleTimer();
  renderCustom();
  refreshQuote();
}

async function refreshQuote() {
  const seq = ++quoteSeq;
  state.quote = null;
  renderBar();
  try {
    const q = await api.quote(state.recipe);
    if (seq !== quoteSeq) return;
    state.quote = q;
    state.quoteError = null;
  } catch (err) {
    if (seq !== quoteSeq) return;
    state.quote = null;
    state.quoteError = err;
  }
  renderBar();
}

// ------------------------------------------------------------------ 渲染：各屏

function renderMenu() {
  if (!state.menu) return;
  $('base-options').replaceChildren(...state.menu.bases.map(({ item, available }) => h('button', {
    type: 'button', class: 'base-card', disabled: !available, onclick: () => chooseBase(item.id),
  }, h('span', { class: 'base-inner' },
    h('span', { class: 'swatch', style: { '--swatch': item.color }, 'aria-hidden': 'true' }, item.name.slice(-2, -1)),
    h('strong', {}, item.name),
    h('small', {}, item.description),
    h('b', {}, `${yuan(item.price_fen)} 起`),
    available ? null : h('span', { class: 'tag bad' }, '售罄')))));

  $('recommendations').replaceChildren(...(state.recs.length ? state.recs.map(rec => h('button', {
    type: 'button', class: 'rec', onclick: () => chooseRecipe(rec),
  }, [itemName(rec.base_id), ...rec.addon_ids.map(itemName)].join(' + '),
     h('small', {}, `${label(rec.size)} · ${label(rec.temperature)} · ${label(rec.sugar)}`))) : [h('p', { class: 'note' }, '暂无推荐')]));
}

function optionButtons(target, key, values, text, blocked = () => false) {
  $(target).replaceChildren(...values.map(v => {
    const [main, sub] = text(v);
    const no = blocked(v);
    return h('button', {
      type: 'button', class: `opt${no ? ' blocked' : ''}`, disabled: no,
      'aria-pressed': String(state.recipe[key] === v),
      onclick: () => updateRecipe(x => { x[key] = v; }),
    }, main, sub ? h('small', {}, sub) : null);
  }));
}

function renderCustom() {
  const menu = state.menu;
  const r = state.recipe;
  if (!menu || !r) return;
  const base = entry(r.base_id)?.item;
  $('custom-swatch').style.setProperty('--swatch', base?.color ?? '#cda56c');
  $('custom-swatch').textContent = base ? base.name.slice(-2, -1) : '';
  $('custom-name').textContent = base?.name ?? '';
  $('custom-desc').textContent = base?.description ?? '';

  optionButtons('size-options', 'size', menu.sizes,
    v => [`${label(v)} ${SIZE_ML[v] ?? ''}mL`, menu.size_extra_fen[v] ? `+${yuan(menu.size_extra_fen[v])}` : '标准']);
  optionButtons('temperature-options', 'temperature', menu.temperatures, v => [label(v)],
    v => (v === 'HOT' && base && !base.hot_allowed) || (v === 'ICED' && base && !base.iced_allowed));
  optionButtons('sugar-options', 'sugar', menu.sugars, v => [label(v)]);
  $('temperature-hint').textContent = base && !base.hot_allowed ? `${base.name}只做冷饮` : '';

  const full = r.addon_ids.length >= MAX_ADDONS;
  $('addon-hint').textContent = full ? `最多 ${MAX_ADDONS} 种` : '可多选，也可以不加';
  $('addon-options').replaceChildren(...menu.addons.map(({ item, available }) => {
    const on = r.addon_ids.includes(item.id);
    return h('button', {
      type: 'button', class: 'opt', disabled: !available || (full && !on), 'aria-pressed': String(on),
      onclick: () => updateRecipe(x => {
        x.addon_ids = on ? x.addon_ids.filter(a => a !== item.id) : [...x.addon_ids, item.id];
      }),
    }, item.name, h('small', {}, available ? `+${yuan(item.price_fen)}` : '售罄'));
  }));
}

function renderBar() {
  const { view, order } = state;
  const bar = $('action-bar');
  bar.hidden = !['custom', 'submitting', 'paying'].includes(view);
  if (bar.hidden) return;
  const recipe = order?.recipe ?? state.recipe;
  $('sum-name').textContent = itemName(recipe.base_id);
  $('sum-detail').textContent = recipeDetail(recipe);

  const btn = $('primary');
  if (view === 'paying') {
    $('sum-label').textContent = '应付';
    $('sum-total').textContent = yuan(order.total_fen);
    btn.textContent = '取消订单';
    btn.className = 'btn big ghost primary';
    btn.disabled = false;
    btn.onclick = cancelOrder;
    $('bar-message').textContent = state.message;
    return;
  }
  btn.className = 'btn big primary';
  $('sum-label').textContent = '合计';
  $('sum-total').textContent = state.quote ? yuan(state.quote.total_fen) : '—';
  const sold = unavailableParts();
  const offline = state.machine && !state.machine.online;
  let message = state.message;
  if (!message && sold.length) message = `${sold.join('、')}刚刚售罄了，请换一种。`;
  if (!message && state.quoteError) message = friendly(state.quoteError);
  $('bar-message').textContent = message;
  btn.textContent = view === 'submitting' ? '正在下单…' : '去付款 ›';
  btn.disabled = view === 'submitting' || !state.quote || sold.length > 0 || !!state.quoteError || offline;
  btn.onclick = submitOrder;
}

function renderPay() {
  const order = state.order;
  const mock = order.payment?.method === 'mock';
  const url = mock ? `${state.config.pay_base_url}/pay/${encodeURIComponent(order.order_id)}` : order.payment?.qr_content ?? '';
  const src = `/api/qr.svg?text=${encodeURIComponent(url)}`;
  if ($('qr').getAttribute('src') !== src) $('qr').src = src;
  $('pay-amount').textContent = yuan(order.total_fen);
  $('pay-lines').replaceChildren(...order.lines.map(l => h('div', {}, h('span', {}, l.label), h('span', {}, yuan(l.price_fen)))));
  const local = /\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(state.config.pay_base_url);
  $('pay-hint').textContent = mock ? '用手机扫码，在“一杯 · 演示收银台”里确认付款。' : '请打开支付宝（沙箱版）扫一扫付款。';
  $('pay-note').textContent = mock && local ? '提示：手机扫码需要用 python run.py --lan 启动，并和电脑连同一个 Wi-Fi。' : '';
  $('demo-pay').hidden = !(state.config.demo && mock);
}

function renderMaking() {
  const recipe = state.order.recipe;
  const base = entry(recipe.base_id)?.item;
  const p = state.progress?.progress ?? 0;
  const cup = $('cup');
  cup.style.setProperty('--drink', base?.color ?? '#cda56c');
  cup.style.setProperty('--fill', Math.max(0.04, p / 100));
  cup.classList.toggle('large', recipe.size === 'L');
  $('ice').hidden = recipe.temperature !== 'ICED' || p < 40;
  $('steam').hidden = recipe.temperature !== 'HOT' || p < 40;
  const marks = { pearl: '● ● ● ●', pudding: '▬ ▬', coconut: '■ ■ ■' };
  $('toppings').replaceChildren(...recipe.addon_ids.filter(id => marks[id] && p >= 60).map(id => h('div', { class: id }, marks[id])));
  $('making-step').textContent = `${itemName(recipe.base_id)} · ${recipeDetail(recipe)}　${state.progress?.step || '准备中'}`;
  $('progress-bar').style.width = `${p}%`;
  $('making-pct').textContent = `${p}%`;
}

function renderResult() {
  const { view, order } = state;
  const icon = $('result-icon');
  const second = $('result-secondary');
  second.hidden = true;
  $('result-order').textContent = order ? `订单号 ${order.order_id}` : '';
  if (view === 'done') {
    icon.className = 'result-icon';
    icon.textContent = '✓';
    $('result-title').textContent = '做好了，请取杯！';
    $('result-text').textContent = `${itemName(order.recipe.base_id)}已经放在取杯口，${order.recipe.temperature === 'HOT' ? '小心烫口' : '趁冰享用'}。`;
    $('result-primary').textContent = '再来一杯';
    $('result-primary').onclick = goMenu;
  } else if (view === 'failed') {
    icon.className = 'result-icon bad';
    icon.textContent = '!';
    $('result-title').textContent = '抱歉，这杯没能做好';
    $('result-text').textContent = `${humanize(order.failure_reason) || '机器故障'}。你已付款，请记下订单号并联系工作人员处理退款，不要重复付款。`;
    $('result-primary').textContent = '返回首页';
    $('result-primary').onclick = goMenu;
  } else {
    icon.className = 'result-icon bad';
    icon.textContent = '×';
    $('result-title').textContent = order.status === 'EXPIRED' ? '付款超时，订单已关闭' : '订单已取消';
    $('result-text').textContent = '没有产生扣款。';
    $('result-primary').textContent = '按原配方重新下单';
    $('result-primary').onclick = backToCustom;
    second.hidden = false;
    second.textContent = '返回首页';
    second.onclick = goMenu;
  }
}

function renderSteps() {
  const current = { menu: 0, custom: 1, submitting: 1, paying: 2, making: 3, done: 3, failed: 3, closed: 2 }[state.view] ?? 0;
  document.querySelectorAll('[data-step]').forEach(li => {
    const n = Number(li.dataset.step);
    li.classList.toggle('active', n === current);
    li.classList.toggle('done', n < current);
  });
}

function renderMachine() {
  const m = state.machine;
  const pill = $('machine-pill');
  const [cls, text] = !m ? ['pill bad', '连接中断'] : !m.online ? ['pill bad', '暂停服务'] : m.busy ? ['pill busy', '制作中'] : ['pill', '可以点单'];
  pill.className = cls;
  pill.lastChild.textContent = text;
  const active = state.order && ACTIVE.includes(state.order.status);
  const paused = (!m || !m.online) && !active && ['menu', 'custom', 'closed'].includes(state.view);
  $('paused').hidden = !paused;
  $('paused-reason').textContent = !m ? '与机器的连接中断，正在重试…'
    : `${m.faults.map(label).join('、') || '机器维护中'}。请稍后再来，或联系工作人员。`;
}

function render() {
  const screen = { menu: 'menu', custom: 'custom', submitting: 'custom', paying: 'pay', making: 'making',
                   done: 'result', failed: 'result', closed: 'result' }[state.view] ?? 'loading';
  for (const id of ['menu', 'custom', 'pay', 'making', 'result', 'loading']) $(`screen-${id}`).hidden = id !== screen;
  if (screen === 'menu') renderMenu();
  if (screen === 'custom') renderCustom();
  if (screen === 'pay') renderPay();
  if (screen === 'making') renderMaking();
  if (screen === 'result') renderResult();
  renderBar();
  renderSteps();
  renderMachine();
}

// ------------------------------------------------------------------ 动作

function chooseBase(baseId) {
  state.recipe = freshRecipe(baseId);
  normalizeRecipe();
  state.message = '';
  setView('custom');
  refreshQuote();
}

function chooseRecipe(rec) {
  state.recipe = structuredClone(rec);
  normalizeRecipe();
  state.message = '';
  setView('custom');
  refreshQuote();
}

function goMenu() {
  clearTimeout(resetTimer);
  clearTimeout(pollTimer);
  state.order = null;
  state.progress = null;
  state.message = '';
  setView('menu');
  loadMenu();
}

function backToCustom() {
  state.order = null;
  state.message = '';
  setView('custom');
  loadMenu();
  refreshQuote();
}

async function submitOrder() {
  if (state.view !== 'custom') return;
  state.message = '';
  setView('submitting');
  try {
    const order = await api.createOrder(state.recipe);
    state.order = order;
    state.payTotalMs = Math.max(1, order.expires_at - order.created_at);
    state.payDeadline = Date.now() + state.payTotalMs;
    setView('paying');
    tickCountdown();
    schedulePoll(0);
  } catch (err) {
    state.order = null;
    if (err.code === 'OUT_OF_STOCK') {
      state.message = '有原料刚刚用完，已更新可选项，请换一种。';
      await loadMenu();
    } else if (err.code === 'MACHINE_UNAVAILABLE') {
      state.message = friendly(err);
      await loadMachine();
    } else {
      state.message = friendly(err);
    }
    setView('custom');
  }
}

async function cancelOrder() {
  $('primary').disabled = true;
  try {
    state.order = await api.cancelOrder(state.order.order_id);
  } catch (err) {
    if (err.code !== 'INVALID_STATE') state.message = `取消失败：${friendly(err)}`;
  }
  await poll();
}

async function demoPay(ok) {
  try {
    await (ok ? api.devPay(state.order.order_id) : api.devClosePayment(state.order.order_id));
  } catch (err) {
    state.message = friendly(err);
  }
  await poll();
}

// ------------------------------------------------------------------ 轮询

function schedulePoll(delay = POLL_MS) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(poll, delay);
}

async function poll() {
  clearTimeout(pollTimer);
  if (!state.order) return;
  try {
    state.order = await api.getOrder(state.order.order_id);
  } catch (err) {
    state.message = `网络异常，正在重试…（${friendly(err)}）`;
    renderBar();
    schedulePoll();
    return;
  }
  const s = state.order.status;
  if (s === 'AWAITING_PAYMENT') {
    if (state.view !== 'paying') setView('paying'); else renderBar();
    schedulePoll();
  } else if (s === 'PAID' || s === 'MAKING') {
    state.progress = await api.getProgress(state.order.order_id).catch(() => state.progress);
    if (state.view !== 'making') setView('making'); else renderMaking();
    schedulePoll();
  } else if (s === 'COMPLETED') {
    state.progress = { progress: 100, step: '已完成' };
    setView('done');
    clearTimeout(resetTimer);
    resetTimer = setTimeout(() => { if (state.view === 'done') goMenu(); }, DONE_RESET_MS);
  } else if (s === 'PRODUCTION_FAILED' || s === 'REFUNDED') {
    setView('failed');
  } else {
    setView('closed');
  }
  loadMachine();
}

function tickCountdown() {
  if (state.view !== 'paying') return;
  const left = Math.max(0, state.payDeadline - Date.now());
  const sec = Math.ceil(left / 1000);
  $('countdown-sec').textContent = sec;
  $('countdown').classList.toggle('urgent', sec <= 20);
  $('countdown-bar').style.width = `${(left / state.payTotalMs) * 100}%`;
  setTimeout(tickCountdown, 250);
}

// ------------------------------------------------------------------ 载入

async function loadMenu() {
  try {
    state.menu = await api.getMenu();
    state.recs = await api.getRecommendations(3).catch(() => state.recs);
    if (state.view === 'menu') renderMenu();
    if (state.view === 'custom') { renderCustom(); renderBar(); }
  } catch {
    /* 下次再试 */
  }
}

async function loadMachine() {
  try {
    state.machine = await api.getMachine();
  } catch {
    state.machine = null;
  }
  renderMachine();
  if (state.view === 'custom') renderBar();
}

async function init() {
  $('demo-pay-ok').onclick = () => demoPay(true);
  $('demo-pay-fail').onclick = () => demoPay(false);
  $('back').onclick = goMenu;
  document.addEventListener('pointerdown', armIdleTimer, { passive: true });

  try {
    state.config = { ...state.config, ...(await api.getConfig()) };
  } catch {
    /* 用默认配置 */
  }
  $('mode-pill').hidden = !state.config.demo;
  $('admin-link').hidden = !state.config.demo;

  await Promise.all([loadMenu(), loadMachine()]);
  if (!state.menu) {
    $('loading-title').textContent = '菜单载入失败';
    $('loading-text').textContent = '请检查程序是否已启动，页面会自动重试。';
    setTimeout(init, 3000);
    return;
  }
  setView('menu');
  setInterval(loadMachine, MACHINE_REFRESH_MS);
  setInterval(() => { if (['menu', 'custom'].includes(state.view)) loadMenu(); }, MENU_REFRESH_MS);
}

init();
