"""组装：决定每个组件用正式实现还是参考实现。负责人：D（与全组共同维护）。

    build(real={"inventory", "stats"})   # 只有库存、统计用正式实现，其余用参考实现

每个人都可以“只把自己的模块换成正式实现”，在完整程序里看效果。
"""
from __future__ import annotations

from dataclasses import dataclass

from drink.maintenance.interfaces import InventoryService, MachineDriver, StatsService
from drink.model import Clock, Repository, SystemClock, seed
from drink.sales.interfaces import IngredientService, OrderService, PaymentGateway

COMPONENTS = ("repository", "ingredient", "order", "inventory", "stats", "machine")
OWNERS = {
    "repository": "D 数据结构",
    "ingredient": "B 销售+食材",
    "order": "B 销售+食材",
    "inventory": "C 数据+机器维护",
    "stats": "C 数据+机器维护",
    "machine": "C 数据+机器维护",
}


@dataclass
class System:
    clock: Clock
    repo: Repository
    inventory: InventoryService
    stats: StatsService
    machine: MachineDriver
    payment: PaymentGateway
    ingredient: IngredientService
    orders: OrderService
    real: frozenset[str]


def build(real=frozenset(), *, db_path: str = "drink.db", clock: Clock | None = None,
          payment: PaymentGateway | None = None, machine_job_ms: int | None = None) -> System:
    from drink.maintenance.inventory_service import InventoryServiceImpl
    from drink.maintenance.machine_simulator import MachineSimulator
    from drink.maintenance.stats_service import StatsServiceImpl
    from drink.model.repository import SqliteRepository
    from drink.sales.ingredient_service import IngredientServiceImpl
    from drink.sales.order_service import OrderServiceImpl
    from drink.sales.payment_mock import MockPayment
    from drink.testing import reference as ref

    real = frozenset(real)
    unknown = real - set(COMPONENTS)
    if unknown:
        raise ValueError(f"未知组件：{', '.join(sorted(unknown))}；可选 {', '.join(COMPONENTS)}")

    clock = clock or SystemClock()
    payment = payment or MockPayment()
    mid = seed.MACHINE_ID

    repo = SqliteRepository(db_path) if "repository" in real else ref.MemoryRepository()
    repo.initialize(seed.MATERIALS, seed.MENU_ITEMS, seed.INITIAL_STOCK)

    inventory = (InventoryServiceImpl if "inventory" in real else ref.RefInventoryService)(repo, clock)
    stats = (StatsServiceImpl if "stats" in real else ref.RefStatsService)(repo, clock)
    machine_kwargs = {"job_ms": machine_job_ms} if machine_job_ms is not None else {}
    machine = (MachineSimulator if "machine" in real else ref.RefMachine)(mid, clock, **machine_kwargs)
    ingredient = (IngredientServiceImpl if "ingredient" in real else ref.RefIngredientService)(
        repo, inventory, stats)
    orders = (OrderServiceImpl if "order" in real else ref.RefOrderService)(
        mid, repo, ingredient, inventory, machine, payment, clock)
    return System(clock, repo, inventory, stats, machine, payment, ingredient, orders, real)
