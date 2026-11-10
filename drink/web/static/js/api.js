// 前端调用后端的唯一入口。负责人：A（GUI）。
// 每个函数对应 docs/04-接口契约.md 第 3 节的一个接口；失败时抛 ApiError。

export class ApiError extends Error {
  constructor(status, { code = 'NETWORK_ERROR', message = '网络错误', details = {} } = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function call(method, path, body) {
  let resp;
  try {
    resp = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0);
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(resp.status, data.error);
  return data;
}

const q = params => {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''));
  return s.toString() ? `?${s}` : '';
};

// ---- 顾客 ----
export const getMenu = () => call('GET', '/menu');
export const getRecommendations = (limit = 3) => call('GET', `/recommendations${q({ limit })}`);
export const quote = recipe => call('POST', '/quotes', recipe);
export const createOrder = recipe => call('POST', '/orders', recipe);
export const getOrder = id => call('GET', `/orders/${encodeURIComponent(id)}`);
export const getProgress = id => call('GET', `/orders/${encodeURIComponent(id)}/progress`);
export const cancelOrder = id => call('POST', `/orders/${encodeURIComponent(id)}/cancel`);
export const getMachine = () => call('GET', '/machine');

// ---- 维护人员 ----
export const getStock = () => call('GET', '/admin/stock');
export const restock = (material_id, quantity, operator) => call('POST', '/admin/restock', { material_id, quantity, operator });
export const getRestocks = (limit = 50) => call('GET', `/admin/restocks${q({ limit })}`);
export const getOrders = (status, limit = 50) => call('GET', `/admin/orders${q({ status, limit })}`);
export const refund = (id, operator) => call('POST', `/admin/orders/${encodeURIComponent(id)}/refund`, { operator });
export const clearFault = code => call('POST', '/admin/machine/clear-fault', code ? { code } : {});
export const getStats = ({ machine_id, since_ms, until_ms } = {}) => call('GET', `/admin/stats${q({ machine_id, since_ms, until_ms })}`);

// ---- 演示 ----
export const devPay = id => call('POST', `/dev/payments/${encodeURIComponent(id)}/succeed`);
export const devClosePayment = id => call('POST', `/dev/payments/${encodeURIComponent(id)}/close`);
export const devFault = code => call('POST', '/dev/machine/faults', { code });

// ---- 显示用 ----
export const yuan = fen => `¥${(fen / 100).toFixed(2)}`;
export const LABELS = {
  M: '中杯', L: '大杯', ICED: '冰', NORMAL: '常温', HOT: '热',
  NONE: '无糖', LIGHT: '三分糖', HALF: '半糖', FULL: '全糖',
  AWAITING_PAYMENT: '待付款', PAID: '已付款', MAKING: '制作中', COMPLETED: '已完成',
  PRODUCTION_FAILED: '制作失败', REFUNDED: '已退款', CANCELLED: '已取消', EXPIRED: '已超时',
  OK: '正常', LOW: '偏低', EMPTY: '缺货',
  CUP_JAM: '落杯卡住', OUT_OF_CUPS: '杯子用完', WATER_TEMP_LOW: '水温不足', PUMP_ERROR: '水泵故障',
};
