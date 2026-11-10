"""参考实现：全部接口的内存版本。

用途：
1. 证明契约测试本身是对的（参考实现必须 100% 通过）；
2. 队友的模块还没写完时，用参考实现顶上，让整个程序先跑起来（python run.py 默认就用它）；
3. 遇到“这个接口到底该怎么表现”的疑问时，可以读这里的代码。

正式实现不要 import 这个文件。正式实现和这里的区别：数据要存进 SQLite（经由 Repository），
重启不丢；机器模拟器要更像真机；支付可接支付宝沙箱。
"""
from __future__ import annotations

import dataclasses
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone

from drink.maintenance.interfaces import InventoryService, MachineDriver, StatsService
from drink.model import (ComboCount, DrinkError, ErrorCode, FaultCode, ItemKind, JobState,
                         JobStatus, MachineState, Menu, MenuEntry, Order, OrderLine,
                         OrderStatus, PaymentStatus, Quote, Recipe, RestockRecord,
                         SalesSummary, Size, StockLevel, Sugar, Temperature)
from drink.model import seed
from drink.model.repository import Repository
from drink.sales.interfaces import IngredientService, OrderService


# ====================================================================== 数据结构（D）

class MemoryRepository(Repository):

    def __init__(self):
        self._lock = threading.RLock()
        self._materials = {}
        self._menu = {}
        self._stock = {}
        self._orders = {}
        self._restocks = []

    def initialize(self, materials, menu_items, initial_stock):
        with self._lock:
            if self._materials:
                return
            self._materials = {m.id: m for m in materials}
            self._menu = {i.id: i for i in menu_items}
            self._stock = {m: int(initial_stock.get(m, 0)) for m in self._materials}

    def list_materials(self):
        return list(self._materials.values())

    def list_menu_items(self):
        return list(self._menu.values())

    def get_menu_item(self, item_id):
        return self._menu.get(item_id)

    def list_stock(self):
        with self._lock:
            return [StockLevel(m, self._stock[m.id]) for m in self._materials.values()]

    def get_stock(self, material_id):
        with self._lock:
            if material_id not in self._materials:
                raise DrinkError(ErrorCode.NOT_FOUND, f"没有原料 {material_id}")
            return StockLevel(self._materials[material_id], self._stock[material_id])

    def apply_stock_changes(self, deltas):
        with self._lock:
            unknown = sorted(k for k in deltas if k not in self._materials)
            if unknown:
                raise DrinkError(ErrorCode.NOT_FOUND, f"没有原料 {', '.join(unknown)}")
            missing = sorted(k for k, d in deltas.items() if self._stock[k] + d < 0)
            if missing:
                raise DrinkError(ErrorCode.OUT_OF_STOCK, "库存不足", missing=missing)
            for k, d in deltas.items():
                self._stock[k] += d

    def save_order(self, order):
        with self._lock:
            self._orders[order.order_id] = order

    def get_order(self, order_id):
        return self._orders.get(order_id)

    def list_orders(self, *, machine_id=None, statuses=None, since_ms=None, until_ms=None,
                    limit=None):
        statuses = set(statuses) if statuses is not None else None
        with self._lock:
            result = [o for o in self._orders.values()
                      if (machine_id is None or o.machine_id == machine_id)
                      and (statuses is None or o.status in statuses)
                      and (since_ms is None or o.created_at >= since_ms)
                      and (until_ms is None or o.created_at < until_ms)]
        result.sort(key=lambda o: o.created_at, reverse=True)
        return result[:limit] if limit is not None else result

    def add_restock(self, material_id, quantity, operator, created_at):
        with self._lock:
            record = RestockRecord(len(self._restocks) + 1, material_id, quantity, operator,
                                   created_at)
            self._restocks.append(record)
            return record

    def list_restocks(self, limit=50):
        with self._lock:
            ordered = sorted(self._restocks, key=lambda r: (r.created_at, r.record_id),
                             reverse=True)
        return ordered[:limit]


# ====================================================================== 数据维护（C）

class RefInventoryService(InventoryService):

    def __init__(self, repo, clock):
        self.repo = repo
        self.clock = clock

    def list_stock(self):
        return self.repo.list_stock()

    def check(self, consumption):
        stock = {s.material.id: s.quantity for s in self.repo.list_stock()}
        return sorted(k for k, need in consumption.items() if stock.get(k, 0) < need)

    def consume(self, consumption, order_id):
        self.repo.apply_stock_changes({k: -v for k, v in consumption.items() if v})

    def restock(self, material_id, quantity, operator):
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise DrinkError(ErrorCode.INVALID_ARGUMENT, "补货数量必须是正整数")
        if not operator or not operator.strip():
            raise DrinkError(ErrorCode.INVALID_ARGUMENT, "请填写操作人")
        current = self.repo.get_stock(material_id)
        if current.quantity + quantity > current.material.capacity:
            room = current.material.capacity - current.quantity
            raise DrinkError(ErrorCode.INVALID_ARGUMENT,
                             f"超过料仓容量，最多还能补 {room}{current.material.unit}")
        self.repo.apply_stock_changes({material_id: quantity})
        self.repo.add_restock(material_id, quantity, operator.strip(), self.clock.now_ms())
        return self.repo.get_stock(material_id)

    def list_restocks(self, limit=50):
        return self.repo.list_restocks(limit)


class RefStatsService(StatsService):

    def __init__(self, repo, clock):
        self.repo = repo
        self.clock = clock

    def _combos(self, orders):
        names = {i.id: i.name for i in self.repo.list_menu_items()}
        counter = Counter((o.recipe.base_id, tuple(sorted(o.recipe.addon_ids))) for o in orders)
        combos = []
        for (base, addons), n in counter.items():
            label = " + ".join([names.get(base, base)] + [names.get(a, a) for a in addons])
            combos.append(ComboCount(label, Recipe(base, addons), n))
        combos.sort(key=lambda c: (-c.count, c.label))
        return combos

    def summary(self, machine_id=None, since_ms=None, until_ms=None):
        orders = self.repo.list_orders(machine_id=machine_id,
                                       statuses=[OrderStatus.COMPLETED],
                                       since_ms=since_ms, until_ms=until_ms)
        tz = timezone(timedelta(hours=seed.TZ_OFFSET_HOURS))
        by_hour = Counter(datetime.fromtimestamp(o.created_at / 1000, tz).hour for o in orders)
        by_sugar = Counter(o.recipe.sugar.value for o in orders)
        return SalesSummary(
            machine_id=machine_id,
            since_ms=since_ms if since_ms is not None else 0,
            until_ms=until_ms if until_ms is not None else self.clock.now_ms(),
            order_count=len(orders),
            revenue_fen=sum(o.total_fen for o in orders),
            top_combos=tuple(self._combos(orders)[:5]),
            by_hour=dict(sorted(by_hour.items())),
            by_sugar=dict(sorted(by_sugar.items())),
        )

    def top_recipes(self, limit=3):
        orders = self.repo.list_orders(statuses=[OrderStatus.COMPLETED])
        return self._combos(orders)[:limit]


# ====================================================================== 机器维护（C）

class RefMachine(MachineDriver):
    """最简单的模拟器：一个步骤，按时间线性推进。"""

    def __init__(self, machine_id, clock, job_ms=3000):
        self._machine_id = machine_id
        self.clock = clock
        self.job_ms = job_ms
        self._lock = threading.Lock()
        self._jobs = {}          # order_id -> {"start": ms, "state": JobState, "fault": ...}
        self._faults = []

    @property
    def machine_id(self):
        return self._machine_id

    def _refresh(self):
        now = self.clock.now_ms()
        for job in self._jobs.values():
            if job["state"] == JobState.RUNNING and now - job["start"] >= self.job_ms:
                job["state"] = JobState.DONE

    def _running(self):
        return [j for j in self._jobs.values() if j["state"] == JobState.RUNNING]

    def status(self):
        with self._lock:
            self._refresh()
            return MachineState(self._machine_id, not self._faults, bool(self._running()),
                                tuple(self._faults))

    def start_job(self, order_id, consumption):
        with self._lock:
            self._refresh()
            if order_id in self._jobs:
                return
            if self._faults:
                raise DrinkError(ErrorCode.MACHINE_UNAVAILABLE, "机器故障，暂停服务")
            if self._running():
                raise DrinkError(ErrorCode.MACHINE_UNAVAILABLE, "机器正在制作上一杯")
            self._jobs[order_id] = {"start": self.clock.now_ms(), "state": JobState.RUNNING,
                                    "fault": None}

    def job_status(self, order_id):
        with self._lock:
            self._refresh()
            job = self._jobs.get(order_id)
            if job is None:
                raise DrinkError(ErrorCode.NOT_FOUND, f"没有订单 {order_id} 的制作任务")
            if job["state"] == JobState.DONE:
                return JobStatus(order_id, JobState.DONE, 100, "已完成")
            if job["state"] == JobState.FAILED:
                return JobStatus(order_id, JobState.FAILED, job["progress"], "故障停止",
                                 job["fault"])
            elapsed = self.clock.now_ms() - job["start"]
            progress = min(99, elapsed * 100 // self.job_ms)
            return JobStatus(order_id, JobState.RUNNING, progress, "制作中")

    def clear_fault(self, code=None):
        with self._lock:
            self._faults = [] if code is None else [f for f in self._faults if f != code]
        return self.status()

    def inject_fault(self, code: FaultCode) -> None:
        with self._lock:
            self._refresh()
            if code not in self._faults:
                self._faults.append(code)
            now = self.clock.now_ms()
            for job in self._running():
                job["state"] = JobState.FAILED
                job["fault"] = code
                job["progress"] = min(99, (now - job["start"]) * 100 // self.job_ms)


# ====================================================================== 食材端（B）

class RefIngredientService(IngredientService):

    def __init__(self, repo, inventory, stats):
        self.repo = repo
        self.inventory = inventory
        self.stats = stats

    def _item(self, item_id, kind):
        item = self.repo.get_menu_item(item_id)
        if item is None or item.kind != kind:
            what = "基底" if kind == ItemKind.BASE else "加料"
            raise DrinkError(ErrorCode.INVALID_RECIPE, f"没有这种{what}：{item_id}")
        return item

    def validate(self, recipe):
        base = self._item(recipe.base_id, ItemKind.BASE)
        if len(set(recipe.addon_ids)) != len(recipe.addon_ids):
            raise DrinkError(ErrorCode.INVALID_RECIPE, "同一种加料不能重复选择")
        if len(recipe.addon_ids) > seed.MAX_ADDONS:
            raise DrinkError(ErrorCode.INVALID_RECIPE, f"加料最多 {seed.MAX_ADDONS} 种")
        for a in recipe.addon_ids:
            self._item(a, ItemKind.ADDON)
        if recipe.temperature == Temperature.HOT and not base.hot_allowed:
            raise DrinkError(ErrorCode.INVALID_RECIPE, f"{base.name}不能做热饮")
        if recipe.temperature == Temperature.ICED and not base.iced_allowed:
            raise DrinkError(ErrorCode.INVALID_RECIPE, f"{base.name}不能加冰")

    def quote(self, recipe):
        self.validate(recipe)
        base = self.repo.get_menu_item(recipe.base_id)
        lines = [OrderLine(base.name, base.price_fen)]
        for a in recipe.addon_ids:
            item = self.repo.get_menu_item(a)
            lines.append(OrderLine(item.name, item.price_fen))
        extra = seed.SIZE_EXTRA_FEN[recipe.size]
        if extra:
            lines.append(OrderLine("大杯", extra))
        return Quote(tuple(lines), sum(line.price_fen for line in lines))

    def consumption_of(self, recipe):
        self.validate(recipe)
        factor = seed.SIZE_FACTOR[recipe.size]
        result = Counter()
        for k, v in self.repo.get_menu_item(recipe.base_id).consumption.items():
            result[k] += round(v * factor)
        result["syrup"] += round(seed.SUGAR_SYRUP_ML[recipe.sugar] * factor)
        result["ice"] += round(seed.ICE_G[recipe.temperature] * factor)
        for a in recipe.addon_ids:
            for k, v in self.repo.get_menu_item(a).consumption.items():
                result[k] += v
        result["cup"] += 1
        return {k: v for k, v in result.items() if v > 0}

    def get_menu(self):
        bases, addons = [], []
        for item in self.repo.list_menu_items():
            if item.kind == ItemKind.BASE:
                need = {k: round(v * seed.SIZE_FACTOR[Size.L]) for k, v in item.consumption.items()}
                need["cup"] = need.get("cup", 0) + 1
                bases.append(MenuEntry(item, not self.inventory.check(need)))
            else:
                addons.append(MenuEntry(item, not self.inventory.check(dict(item.consumption))))
        return Menu(tuple(bases), tuple(addons), tuple(Size), tuple(Temperature), tuple(Sugar),
                    {s.value: f for s, f in seed.SIZE_EXTRA_FEN.items()}, seed.DEFAULT_RECIPE)

    def _usable(self, recipe):
        try:
            return not self.inventory.check(self.consumption_of(recipe))
        except DrinkError:
            return False

    def recommend(self, limit=3):
        candidates = [c.recipe for c in self.stats.top_recipes(limit * 2)]
        candidates += list(seed.PRESET_RECOMMENDATIONS)
        result, seen = [], set()
        for r in candidates:
            key = (r.base_id, frozenset(r.addon_ids))
            if key in seen or not self._usable(r):
                continue
            seen.add(key)
            result.append(r)
            if len(result) == limit:
                break
        return result


# ====================================================================== 销售端（B）

class RefOrderService(OrderService):

    def __init__(self, machine_id, repo, ingredient, inventory, machine, payment, clock):
        self.machine_id = machine_id
        self.repo = repo
        self.ingredient = ingredient
        self.inventory = inventory
        self.machine = machine
        self.payment = payment
        self.clock = clock
        self._lock = threading.RLock()
        self._seq = 0

    def _new_id(self):
        self._seq += 1
        return f"{self.machine_id}-{self.clock.now_ms()}-{self._seq}"

    def _save(self, order, **changes):
        updated = dataclasses.replace(order, updated_at=self.clock.now_ms(), **changes)
        self.repo.save_order(updated)
        return updated

    def _with_payment_status(self, order, status):
        return dataclasses.replace(order.payment, status=status) if order.payment else None

    def create_order(self, recipe):
        with self._lock:
            self.ingredient.validate(recipe)
            state = self.machine.status()
            if not state.online:
                raise DrinkError(ErrorCode.MACHINE_UNAVAILABLE, "机器故障，暂停服务")
            active = self.repo.list_orders(
                machine_id=self.machine_id,
                statuses=[s for s in OrderStatus if s.is_active])
            for old in active:
                old = self._advance(old)
                if old.status in (OrderStatus.PAID, OrderStatus.MAKING):
                    raise DrinkError(ErrorCode.MACHINE_UNAVAILABLE, "上一杯还在制作，请稍候")
                if old.status == OrderStatus.AWAITING_PAYMENT:
                    self.payment.close(old.order_id)
                    self._save(old, status=OrderStatus.CANCELLED,
                               payment=self._with_payment_status(old, PaymentStatus.CLOSED))
            missing = self.inventory.check(self.ingredient.consumption_of(recipe))
            if missing:
                raise DrinkError(ErrorCode.OUT_OF_STOCK, "部分原料不足，请换一种配方",
                                 missing=missing)
            quote = self.ingredient.quote(recipe)
            order_id = self._new_id()
            subject = quote.lines[0].label
            payment = self.payment.create(order_id, quote.total_fen, subject)
            now = self.clock.now_ms()
            order = Order(order_id, self.machine_id, recipe, quote.lines, quote.total_fen,
                          OrderStatus.AWAITING_PAYMENT, now, now,
                          now + seed.PAYMENT_TIMEOUT_MS, payment)
            self.repo.save_order(order)
            return order

    def _advance(self, order):
        if order.status == OrderStatus.AWAITING_PAYMENT:
            ps = self.payment.query(order.order_id)
            if ps == PaymentStatus.SUCCESS:
                order = self._save(order, status=OrderStatus.PAID,
                                   payment=self._with_payment_status(order, ps))
            elif ps == PaymentStatus.CLOSED:
                return self._save(order, status=OrderStatus.CANCELLED,
                                  payment=self._with_payment_status(order, ps))
            elif self.clock.now_ms() >= order.expires_at:
                self.payment.close(order.order_id)
                return self._save(order, status=OrderStatus.EXPIRED,
                                  payment=self._with_payment_status(order, PaymentStatus.CLOSED))
            else:
                return order
        if order.status == OrderStatus.PAID:
            consumption = self.ingredient.consumption_of(order.recipe)
            try:
                missing = self.inventory.check(consumption)
                if missing:
                    raise DrinkError(ErrorCode.OUT_OF_STOCK, "原料不足：" + "、".join(missing))
                self.machine.start_job(order.order_id, consumption)
                self.inventory.consume(consumption, order.order_id)
            except DrinkError as e:
                return self._save(order, status=OrderStatus.PRODUCTION_FAILED,
                                  failure_reason=e.message)
            order = self._save(order, status=OrderStatus.MAKING)
        if order.status == OrderStatus.MAKING:
            try:
                job = self.machine.job_status(order.order_id)
            except DrinkError as e:
                if e.code != ErrorCode.NOT_FOUND:
                    raise
                return self._save(order, status=OrderStatus.PRODUCTION_FAILED,
                                  failure_reason="机器已重启，制作状态丢失")
            if job.state == JobState.DONE:
                return self._save(order, status=OrderStatus.COMPLETED)
            if job.state == JobState.FAILED:
                reason = f"制作故障：{job.fault.value}" if job.fault else "制作故障"
                return self._save(order, status=OrderStatus.PRODUCTION_FAILED,
                                  failure_reason=reason)
        return order

    def _load(self, order_id):
        order = self.repo.get_order(order_id)
        if order is None:
            raise DrinkError(ErrorCode.NOT_FOUND, f"没有订单 {order_id}")
        return order

    def get_order(self, order_id):
        with self._lock:
            return self._advance(self._load(order_id))

    def cancel_order(self, order_id):
        with self._lock:
            order = self._advance(self._load(order_id))
            if order.status != OrderStatus.AWAITING_PAYMENT:
                raise DrinkError(ErrorCode.INVALID_STATE, "订单已付款或已结束，不能取消")
            self.payment.close(order_id)
            return self._save(order, status=OrderStatus.CANCELLED,
                              payment=self._with_payment_status(order, PaymentStatus.CLOSED))

    def list_orders(self, status=None, limit=50):
        with self._lock:
            for order in self.repo.list_orders(machine_id=self.machine_id,
                                               statuses=[s for s in OrderStatus if s.is_active]):
                self._advance(order)
        statuses = [status] if status is not None else None
        return self.repo.list_orders(machine_id=self.machine_id, statuses=statuses, limit=limit)

    def refund_order(self, order_id, operator):
        with self._lock:
            order = self._load(order_id)
            if order.status != OrderStatus.PRODUCTION_FAILED:
                raise DrinkError(ErrorCode.INVALID_STATE, "只有制作失败的订单可以退款")
            if not operator or not operator.strip():
                raise DrinkError(ErrorCode.INVALID_ARGUMENT, "请填写操作人")
            self.payment.refund(order_id, order.total_fen)
            return self._save(order, status=OrderStatus.REFUNDED,
                              payment=self._with_payment_status(order, PaymentStatus.REFUNDED))
