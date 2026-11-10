// 点单页。负责人：A（GUI）。
// 只负责展示和收集操作：价格、能否售卖、订单状态全部以后端返回为准（见 docs/04-接口契约.md）。
//
// 界面状态（view）：
//   loading → editing ⇄ submitting → paying → making → done
//                                      │         └──→ failed
//                                      └──→ closed（取消 / 超时）
//   machine 离线且没有进行中的订单时，叠加“暂停服务”遮罩。

import * as api from './api.js';
import { $, h, yuan, label, humanize, SIZE_ML, fakeQr } from './ui.js';

const POLL_MS = 1000;
const MENU_REFRESH_MS = 20000;
const MACHINE_REFRESH_MS = 4000;
const DONE_RESET_MS = 20000;
const MAX_ADDONS = 3;

const state = {
  config: { demo: false, machine_id: '', payment_method: 'mock' },
  menu: null,
  machine: null,
  recipe: null,
  recs: [],
  quote: null,
  quoteError: null,
  view: 'loading',
  order: null,
  progress: null,
  error: null,          // 最近一次操作失败的提示 { title, message }
  payDeadline: 0,       // 本地时间的付款截止时刻
  payTotalMs: 1,
};

let quoteSeq = 0;
let pollTimer = null;
let doneTimer = null;

const ACTIVE = ['AWAITING_PAYMENT', 'PAID', 'MAKING'];

// ------------------------------------------------------------------ 工具

const item = id => [...(state.menu?.bases ?? []), ...(state.menu?.addons ?? [])].find(e => e.item.id === id);
const itemName = id => item(id)?.item.name ?? id;
const isEditing = () => state.view === 'editing';

function friendly(err) {
  if (!err) return '';
  if (err.code === 'NETWORK_ERROR') return '网络连接中断，请稍后再试。';
  return err.message || '出了点问题，请稍后再试。';
}

function setView(view) {
  state.view = view;
  render();
}

// ------------------------------------------------------------------ 配方

function normalizeRecipe() {
  const r = state.recipe;
  const base = item(r.base_id)?.item;
  if (!base) return;
  if (r.temperature === 'HOT' && !base.hot_allowed) r.temperature = base.iced_allowed ? 'ICED' : 'NORMAL';
  if (r.temperature === 'ICED' && !base.iced_allowed) r.temperature = 'NORMAL';
}

function chooseInitialRecipe() {
  const recipe = structuredClone(state.menu.default_recipe);
  if (!item(recipe.base_id)?.available) {
    const first = state.menu.bases.find(e => e.available);
    if (first) recipe.base_id = first.item.id;
  }
  recipe.addon_ids = recipe.addon_ids.filter(id => item(id)?.available);
  state.recipe = recipe;
  normalizeRecipe();
}

function unavailableParts() {
  const r = state.recipe;
  return [r.base_id, ...r.addon_ids].filter(id => !item(id)?.available).map(itemName);
}

function updateRecipe(change) {
  if (!isEditing()) return;
  change(state.recipe);
  normalizeRecipe();
  state.error = null;
  renderChoices();
  refreshQuote();
}

async function refreshQuote() {
  const seq = ++quoteSeq;
  state.quote = null;
  renderOrderCard();
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
  renderOrderCard();
}

// ------------------------------------------------------------------ 渲染：左侧选择区

function renderChoices() {
  const menu = state.menu;
  if (!menu || !state.recipe) return;
  const r = state.recipe;

  $('base-options').replaceChildren(...menu.bases.map(({ item: it, available }) => h('label', { class: `base-option${available ? '' : ' sold'}` },
    h('input', { type: 'radio', name: 'base', value: it.id, checked: r.base_id === it.id, disabled: !available,
                 onchange: () => updateRecipe(x => { x.base_id = it.id; }) }),
    h('span', { class: 'mini-drink', style: { '--swatch': it.color }, 'aria-hidden': 'true' }, it.name.slice(-2, -1)),
    h('span', { class: 'base-copy' },
      h('strong', {}, it.name), h('small', {}, it.description), h('b', {}, yuan(it.price_fen))),
    available ? null : h('span', { class: 'tag bad' }, '售罄'),
  )));

  const full = r.addon_ids.length >= MAX_ADDONS;
  $('addon-options').replaceChildren(...menu.addons.map(({ item: it, available }) => {
    const checked = r.addon_ids.includes(it.id);
    const blocked = !available ? ' sold' : full && !checked ? ' full' : '';
    return h('label', { class: `addon-option${blocked}` },
      h('input', { type: 'checkbox', value: it.id, checked, disabled: !available || (full && !checked),
                   onchange: e => updateRecipe(x => {
                     x.addon_ids = e.target.checked ? [...x.addon_ids, it.id] : x.addon_ids.filter(a => a !== it.id);
                   }) }),
      h('span', {}, it.name),
      h('small', {}, available ? `+${yuan(it.price_fen)}` : '售罄'));
  }));
  $('addon-hint').textContent = full ? `最多选 ${MAX_ADDONS} 种` : '可多选，也可以不加';

  const base = item(r.base_id)?.item;
  segments('size-options', 'size', menu.sizes, v => [label(v), `${SIZE_ML[v] ?? ''} mL${menu.size_extra_fen[v] ? ` · +${yuan(menu.size_extra_fen[v])}` : ''}`]);
  segments('temperature-options', 'temperature', menu.temperatures, v => [label(v)],
           v => (v === 'HOT' && base && !base.hot_allowed) || (v === 'ICED' && base && !base.iced_allowed));
  segments('sugar-options', 'sugar', menu.sugars, v => [label(v)]);
  $('temperature-hint').textContent = base && !base.hot_allowed ? `${base.name}只做冷饮` : '';

  $('recommendations').replaceChildren(...(state.recs.length ? state.recs.map(rec => h('button', {
    type: 'button', class: 'rec',
    onclick: () => updateRecipe(x => Object.assign(x, structuredClone(rec))),
  }, [itemName(rec.base_id), ...rec.addon_ids.map(itemName)].join(' + '),
     h('small', {}, `${label(rec.size)} · ${label(rec.temperature)} · ${label(rec.sugar)}`))) : [h('small', {}, '暂无推荐')]));
}

function segments(target, key, values, text, disabled = () => false) {
  $(target).replaceChildren(...values.map(v => {
    const [main, sub] = text(v);
    const blocked = disabled(v);
    return h('label', { class: `segment${blocked ? ' blocked' : ''}` },
      h('input', { type: 'radio', name: key, value: v, checked: state.recipe[key] === v, disabled: blocked,
                   onchange: () => updateRecipe(x => { x[key] = v; }) }),
      h('span', {}, main, sub ? h('small', {}, sub) : null));
  }));
}

// ------------------------------------------------------------------ 渲染：订单卡

function renderCup(recipe, fill) {
  const base = item(recipe.base_id)?.item;
  $('liquid').style.setProperty('--drink', base?.color ?? '#cda56c');
  $('cup').style.setProperty('--fill', fill);
  $('cup').classList.toggle('large', recipe.size === 'L');
  $('ice').hidden = recipe.temperature !== 'ICED' || fill < 0.3;
  $('steam').hidden = recipe.temperature !== 'HOT' || fill < 0.3;
  const marks = { pearl: ['pearl', '● ● ● ●'], pudding: ['pudding', '▬ ▬'], coconut: ['coconut', '■ ■ ■'] };
  $('toppings').replaceChildren(...recipe.addon_ids.filter(id => marks[id]).map(id => h('div', { class: marks[id][0] }, marks[id][1])));
  $('stage-caption').textContent = `FRESHLY MIXED / ${SIZE_ML[recipe.size] ?? ''} mL`;
}

function status(title, message, kind = '', busy = false) {
  $('status-box').className = `status-box${kind ? ` ${kind}` : ''}`;
  $('status-title').replaceChildren(...(busy ? [h('span', { class: 'spinner' })] : []), title);
  $('status-message').textContent = message;
}

function lines(list) {
  $('line-items').replaceChildren(...list.map(l => h('div', { class: 'line-item' }, h('span', {}, l.label), h('span', {}, yuan(l.price_fen)))));
}

function primary(text, onClick, disabled = false) {
  const btn = $('primary');
  btn.hidden = !text;
  btn.textContent = text || '';
  btn.disabled = disabled;
  btn.onclick = onClick || null;
}

function secondary(text, onClick) {
  const btn = $('secondary');
  btn.hidden = !text;
  btn.textContent = text || '';
  btn.onclick = onClick || null;
}

function renderOrderCard() {
  const { view, order } = state;
  const recipe = order?.recipe ?? state.recipe;
  if (!recipe) return;

  $('drink-name').textContent = itemName(recipe.base_id);
  $('recipe-text').textContent = [label(recipe.size), label(recipe.temperature), label(recipe.sugar),
    recipe.addon_ids.length ? recipe.addon_ids.map(itemName).join(' + ') : '不加料'].join(' / ');

  const fill = view === 'making' ? Math.max(0.05, (state.progress?.progress ?? 0) / 100)
    : view === 'paying' ? 0.15 : 1;
  renderCup(recipe, fill);

  if (order) {
    lines(order.lines);
    $('price-label').textContent = '实付';
    $('total').textContent = yuan(order.total_fen);
    $('order-id').textContent = `订单号 ${order.order_id}`;
  } else {
    lines(state.quote?.lines ?? []);
    $('price-label').textContent = '合计';
    $('total').textContent = state.quote ? yuan(state.quote.total_fen) : '—';
    $('order-id').textContent = '';
  }

  $('pay-panel').hidden = view !== 'paying';
  $('progress-panel').hidden = view !== 'making';
  $('payment-note').textContent = '';
  secondary(null);

  switch (view) {
    case 'loading':
      status('正在载入菜单…', '', '', true);
      primary('请稍候', null, true);
      break;

    case 'editing': {
      const sold = unavailableParts();
      const offline = state.machine && !state.machine.online;
      if (state.error) status(state.error.title, state.error.message, 'error');
      else if (sold.length) status('有选项刚刚售罄', `${sold.join('、')}暂时没货了，请换一种。`, 'error');
      else if (state.quoteError) status('这样搭配做不了', friendly(state.quoteError), 'error');
      else if (!state.quote) status('正在计算价格…', '', '', true);
      else status('选好了吗？', '确认后生成付款码，2 分钟内付款有效。');
      const ready = state.quote && !sold.length && !state.quoteError && !offline;
      primary(state.quote ? `确认下单 · ${yuan(state.quote.total_fen)} →` : '确认下单 →', submitOrder, !ready);
      secondary('恢复默认配方', () => updateRecipe(x => Object.assign(x, structuredClone(state.menu.default_recipe))));
      $('payment-note').textContent = state.config.demo ? '演示模式 · 不产生真实付款' : '支持支付宝扫码付款';
      break;
    }

    case 'submitting':
      status('正在下单', '正在确认价格和库存…', '', true);
      primary('正在下单…', null, true);
      break;

    case 'paying': {
      const mock = order.payment?.method === 'mock';
      status('请扫码付款', mock ? '这是演示付款码，可点下方按钮模拟顾客付款。' : '请使用支付宝扫描二维码完成付款。');
      $('qr-note').textContent = mock ? '演示付款码（不可真实扫码）' : order.payment?.qr_content ?? '';
      $('demo-pay').hidden = !(state.config.demo && mock);
      primary(null);
      secondary('取消订单', cancelOrder);
      break;
    }

    case 'making': {
      const p = state.progress?.progress ?? 0;
      status('付款成功，正在为你现调', state.progress?.step || '准备中', '', true);
      $('progress-bar').style.width = `${p}%`;
      $('progress-step').textContent = state.progress?.step || '准备中';
      $('progress-num').textContent = `${p}%`;
      primary('制作中，请稍候…', null, true);
      break;
    }

    case 'done':
      status('做好了，请取杯！', '小心烫口 / 冰爽，享用这一杯。20 秒后自动回到首页。', 'success');
      primary('再来一杯 →', startOver);
      break;

    case 'failed':
      status('抱歉，这杯没能做好',
        `${humanize(order.failure_reason) || '机器故障'}。你已付款，请记下订单号并联系工作人员处理退款，不要重复付款。`, 'error');
      primary('返回首页', startOver);
      break;

    case 'closed':
      status(order.status === 'EXPIRED' ? '付款超时，订单已关闭' : '订单已取消',
        '没有产生扣款。配方已保留，可以直接重新下单。');
      primary('重新下单 →', backToEditing);
      break;
  }
}

function renderSteps() {
  const current = { paying: 1, making: 2, done: 2, failed: 2 }[state.view] ?? 0;
  document.querySelectorAll('[data-step]').forEach(li => {
    const n = Number(li.dataset.step);
    li.classList.toggle('active', n === current);
    li.classList.toggle('done', n < current);
    if (n === current) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
  });
}

function renderMachine() {
  const m = state.machine;
  const pill = $('machine-pill');
  if (!m) {
    pill.className = 'pill bad';
    pill.lastChild.textContent = '连接中断';
  } else if (!m.online) {
    pill.className = 'pill bad';
    pill.lastChild.textContent = '暂停服务';
  } else if (m.busy) {
    pill.className = 'pill busy';
    pill.lastChild.textContent = '制作中';
  } else {
    pill.className = 'pill';
    pill.lastChild.textContent = '可以点单';
  }
  const hasActiveOrder = state.order && ACTIVE.includes(state.order.status);
  const paused = (!m || !m.online) && !hasActiveOrder && ['editing', 'closed', 'loading'].includes(state.view);
  $('paused').hidden = !paused;
  $('paused-reason').textContent = !m ? '与机器的连接中断，正在重试…'
    : `${m.faults.map(label).join('、') || '机器维护中'}。请稍后再来，或联系工作人员。`;
}

function render() {
  $('config-fields').disabled = !isEditing();
  renderMachine();
  renderSteps();
  renderOrderCard();
}

// ------------------------------------------------------------------ 动作

async function submitOrder() {
  if (!isEditing()) return;
  state.error = null;
  setView('submitting');
  try {
    const order = await api.createOrder(state.recipe);
    state.order = order;
    state.payTotalMs = Math.max(1, order.expires_at - order.created_at);
    state.payDeadline = Date.now() + state.payTotalMs;
    $('qr').replaceChildren(fakeQr(order.payment?.qr_content ?? order.order_id));
    setView('paying');
    tickCountdown();
    schedulePoll(0);
  } catch (err) {
    state.order = null;
    if (err.code === 'OUT_OF_STOCK') {
      state.error = { title: '原料不足', message: '所选配方有原料刚刚用完，已为你更新可选项，请换一种。' };
      await loadMenu();
    } else if (err.code === 'MACHINE_UNAVAILABLE') {
      state.error = { title: '机器暂时不能接单', message: friendly(err) };
      await loadMachine();
    } else {
      state.error = { title: '下单没有成功', message: friendly(err) };
    }
    setView('editing');
  }
}

async function cancelOrder() {
  $('secondary').disabled = true;
  try {
    state.order = await api.cancelOrder(state.order.order_id);
  } catch (err) {
    if (err.code !== 'INVALID_STATE') status('取消失败', friendly(err), 'error');
  } finally {
    $('secondary').disabled = false;
  }
  await poll();
}

async function demoPay(ok) {
  const id = state.order.order_id;
  try {
    await (ok ? api.devPay(id) : api.devClosePayment(id));
  } catch (err) {
    status('模拟付款失败', friendly(err), 'error');
  }
  await poll();
}

function backToEditing() {
  state.order = null;
  state.progress = null;
  state.error = null;
  clearTimeout(doneTimer);
  setView('editing');
  loadMenu();
  refreshQuote();
}

function startOver() {
  chooseInitialRecipe();
  backToEditing();
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
    status('网络异常，正在重试…', friendly(err), 'error', true);
    schedulePoll();
    return;
  }
  const s = state.order.status;
  if (s === 'AWAITING_PAYMENT') {
    if (state.view !== 'paying') setView('paying');
    schedulePoll();
  } else if (s === 'PAID' || s === 'MAKING') {
    state.progress = await api.getProgress(state.order.order_id).catch(() => state.progress);
    if (state.view !== 'making') setView('making'); else renderOrderCard();
    schedulePoll();
  } else if (s === 'COMPLETED') {
    state.progress = { progress: 100, step: '已完成' };
    setView('done');
    clearTimeout(doneTimer);
    doneTimer = setTimeout(() => { if (state.view === 'done') startOver(); }, DONE_RESET_MS);
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
    if (!state.recipe) chooseInitialRecipe();
    renderChoices();
    if (isEditing()) renderOrderCard();
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
  if (isEditing()) renderOrderCard();
}

async function init() {
  $('demo-pay-ok').onclick = () => demoPay(true);
  $('demo-pay-fail').onclick = () => demoPay(false);
  render();
  try {
    state.config = await api.getConfig();
  } catch {
    /* 用默认配置 */
  }
  const modePill = $('mode-pill');
  modePill.hidden = !state.config.demo;
  modePill.lastChild.textContent = '演示模式 · 不产生真实付款';
  $('admin-link').hidden = !state.config.demo;
  $('machine-no').textContent = (state.config.machine_id || 'M001').replace(/^\D+/, '').padStart(2, '0').slice(-2);
  $('footer-machine').textContent = state.config.machine_id ? `机器 ${state.config.machine_id}` : '';

  await Promise.all([loadMenu(), loadMachine()]);
  if (!state.menu) {
    status('菜单载入失败', '请检查程序是否已启动，页面会自动重试。', 'error');
    setTimeout(init, 3000);
    return;
  }
  setView('editing');
  refreshQuote();
  setInterval(loadMachine, MACHINE_REFRESH_MS);
  setInterval(() => { if (isEditing()) loadMenu(); }, MENU_REFRESH_MS);
}

init();
