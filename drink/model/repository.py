"""数据访问接口。负责人：D（数据结构）。

其他模块不直接写 SQL，只通过 Repository 读写数据。
Repository 只负责“存取”，不做业务判断（例如补货是否超过容量由库存模块判断）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from .entities import (Consumption, Material, MenuItem, Order, RestockRecord,
                       StockLevel)
from .enums import OrderStatus


class Repository(ABC):

    # ----- 初始化 -----
    @abstractmethod
    def initialize(self, materials: Iterable[Material], menu_items: Iterable[MenuItem],
                   initial_stock: dict[str, int]) -> None:
        """建表；若还没有任何原料数据，则写入给定的初始数据。可重复调用（幂等）。"""

    # ----- 原料与菜单 -----
    @abstractmethod
    def list_materials(self) -> list[Material]:
        """按初始化时的顺序返回。"""

    @abstractmethod
    def list_menu_items(self) -> list[MenuItem]:
        """按初始化时的顺序返回。"""

    @abstractmethod
    def get_menu_item(self, item_id: str) -> MenuItem | None: ...

    # ----- 库存 -----
    @abstractmethod
    def list_stock(self) -> list[StockLevel]:
        """按原料初始化顺序返回。"""

    @abstractmethod
    def get_stock(self, material_id: str) -> StockLevel:
        """原料不存在 → DrinkError(NOT_FOUND)。"""

    @abstractmethod
    def apply_stock_changes(self, deltas: Consumption) -> None:
        """原子地修改库存，delta 为正表示增加、为负表示扣减。

        - 任一原料不存在 → NOT_FOUND，且不修改任何库存；
        - 任一原料结果 < 0 → OUT_OF_STOCK（details["missing"] 为这些原料 ID，按 ID 排序），
          且不修改任何库存。
        """

    # ----- 订单 -----
    @abstractmethod
    def save_order(self, order: Order) -> None:
        """按 order_id 插入或覆盖。"""

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None: ...

    @abstractmethod
    def list_orders(self, *, machine_id: str | None = None,
                    statuses: Iterable[OrderStatus] | None = None,
                    since_ms: int | None = None, until_ms: int | None = None,
                    limit: int | None = None) -> list[Order]:
        """按 created_at 降序（最新在前）。since_ms 含、until_ms 不含。None 表示不过滤。"""

    # ----- 补货记录 -----
    @abstractmethod
    def add_restock(self, material_id: str, quantity: int, operator: str,
                    created_at: int) -> RestockRecord:
        """只记录，不修改库存。record_id 从 1 开始自增。"""

    @abstractmethod
    def list_restocks(self, limit: int = 50) -> list[RestockRecord]:
        """按 created_at 降序；时间相同按 record_id 降序。"""


class SqliteRepository(Repository):
    """正式实现：SQLite。负责人：D。建表语句见 schema.sql。

    TODO(D)：实现全部方法。提示：
    - 用标准库 sqlite3；check_same_thread=False，并用一把 threading.Lock 保护写操作（Flask 多线程）。
    - consumption、recipe、lines、payment 这类嵌套字段可以存 JSON 字符串（见 serialize.py）。
    - apply_stock_changes 用一个事务完成“先检查、再全部更新”。
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def initialize(self, materials, menu_items, initial_stock):
        raise NotImplementedError

    def list_materials(self):
        raise NotImplementedError

    def list_menu_items(self):
        raise NotImplementedError

    def get_menu_item(self, item_id):
        raise NotImplementedError

    def list_stock(self):
        raise NotImplementedError

    def get_stock(self, material_id):
        raise NotImplementedError

    def apply_stock_changes(self, deltas):
        raise NotImplementedError

    def save_order(self, order):
        raise NotImplementedError

    def get_order(self, order_id):
        raise NotImplementedError

    def list_orders(self, *, machine_id=None, statuses=None, since_ms=None, until_ms=None,
                    limit=None):
        raise NotImplementedError

    def add_restock(self, material_id, quantity, operator, created_at):
        raise NotImplementedError

    def list_restocks(self, limit=50):
        raise NotImplementedError
