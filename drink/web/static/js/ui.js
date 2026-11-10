// 页面共用的小工具。负责人：A（GUI）。
// 约定：服务端返回的文字一律用 textContent 写入（h() 内部就是这么做的），不拼 HTML。

export const $ = id => document.getElementById(id);

/** 创建元素：h('div', {class: 'x', onclick: fn, disabled: true}, '文字', 子元素...) */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'style' && typeof value === 'object') {
      for (const [prop, v] of Object.entries(value)) {
        if (prop.startsWith('--')) el.style.setProperty(prop, v); else el.style[prop] = v;
      }
    }
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
    else if (key in el && typeof value !== 'string') el[key] = value;
    else el.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === undefined || child === null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export const yuan = fen => `¥${(fen / 100).toFixed(2)}`;

export const LABELS = {
  M: '中杯', L: '大杯', ICED: '冰', NORMAL: '常温', HOT: '热',
  NONE: '无糖', LIGHT: '三分糖', HALF: '半糖', FULL: '全糖',
  AWAITING_PAYMENT: '待付款', PAID: '已付款', MAKING: '制作中', COMPLETED: '已完成',
  PRODUCTION_FAILED: '制作失败', REFUNDED: '已退款', CANCELLED: '已取消', EXPIRED: '已超时',
  OK: '正常', LOW: '偏低', EMPTY: '缺货',
  CUP_JAM: '落杯卡住', OUT_OF_CUPS: '杯子用完', WATER_TEMP_LOW: '水温不足', PUMP_ERROR: '水泵故障',
};

export const SIZE_ML = { M: 500, L: 700 };

export function label(code) {
  return LABELS[code] ?? code;
}

/** 把一段文字里出现的英文代码（如 CUP_JAM）换成中文名称。 */
export function humanize(text) {
  return String(text ?? '').replace(/\b[A-Z][A-Z_]{2,}\b/g, code => LABELS[code] ?? code);
}

/** 安全读写 localStorage（某些环境会抛异常）。 */
export const store = {
  get(key, fallback = '') {
    try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, value); } catch { /* 忽略 */ }
  },
};

export function formatTime(ms) {
  const d = new Date(ms);
  const pad = n => String(n).padStart(2, '0');
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
