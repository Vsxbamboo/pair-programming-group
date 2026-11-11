"""销售统计正式实现。负责人：C。

构造参数是约定的一部分（wiring.py 按此创建），不要改。
验收标准是 tests/contract/test_stats.py。

实现要点（见 docs/03-详细设计.md §7）：
- 只读 COMPLETED 订单，按订单的 created_at 过滤（since 含、until 不含）；
- 热门组合按（基底, 加料集合）分组，忽略杯型、温度、甜度；
  次数降序，同次数按名称升序；加料按 ID 排序；
- 按小时分布固定用北京时间（seed.TZ_OFFSET_HOURS），只列有数据的小时。
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from drink.model import Clock, ComboCount, OrderStatus, Recipe, Repository, SalesSummary
from drink.model import seed

from .interfaces import StatsService


class StatsServiceImpl(StatsService):

    def __init__(self, repo: Repository, clock: Clock):
        self.repo = repo
        self.clock = clock

    def _combos(self, orders):
        names = {item.id: item.name for item in self.repo.list_menu_items()}
        counter = Counter(
            (order.recipe.base_id, tuple(sorted(order.recipe.addon_ids)))
            for order in orders
        )
        combos = []
        for (base_id, addon_ids), count in counter.items():
            label = " + ".join([names.get(base_id, base_id)]
                               + [names.get(addon_id, addon_id) for addon_id in addon_ids])
            combos.append(ComboCount(label, Recipe(base_id, addon_ids), count))
        combos.sort(key=lambda combo: (-combo.count, combo.label))
        return combos

    def summary(self, machine_id=None, since_ms=None, until_ms=None):
        # 过滤只在显式传参时生效；返回对象里的默认值用于展示。
        orders = self.repo.list_orders(machine_id=machine_id,
                                       statuses=[OrderStatus.COMPLETED],
                                       since_ms=since_ms, until_ms=until_ms)
        tz = timezone(timedelta(hours=seed.TZ_OFFSET_HOURS))
        by_hour = Counter(datetime.fromtimestamp(order.created_at / 1000, tz).hour
                          for order in orders)
        by_sugar = Counter(order.recipe.sugar.value for order in orders)
        return SalesSummary(
            machine_id=machine_id,
            since_ms=since_ms if since_ms is not None else 0,
            until_ms=until_ms if until_ms is not None else self.clock.now_ms(),
            order_count=len(orders),
            revenue_fen=sum(order.total_fen for order in orders),
            top_combos=tuple(self._combos(orders)[:5]),
            by_hour=dict(sorted(by_hour.items())),
            by_sugar=dict(sorted(by_sugar.items())),
        )

    def top_recipes(self, limit=3):
        orders = self.repo.list_orders(statuses=[OrderStatus.COMPLETED])
        return self._combos(orders)[:limit]
