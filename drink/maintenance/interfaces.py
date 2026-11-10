"""数据维护 + 机器维护的接口。负责人：C。

改动任何方法签名或行为约定，必须先在组里讨论，并同步修改 docs/04-接口契约.md 和契约测试。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from drink.model import (ComboCount, Consumption, FaultCode, JobStatus, MachineState,
                         RestockRecord, SalesSummary, StockLevel)


class InventoryService(ABC):
    """数据维护：库存。"""

    @abstractmethod
    def list_stock(self) -> list[StockLevel]: ...

    @abstractmethod
    def check(self, consumption: Consumption) -> list[str]:
        """返回库存不足的原料 ID（按 ID 排序）；空列表表示够用。不存在的原料视为不足。"""

    @abstractmethod
    def consume(self, consumption: Consumption, order_id: str) -> None:
        """按配方扣减库存，全部成功或全部不扣。不足 → OUT_OF_STOCK。"""

    @abstractmethod
    def restock(self, material_id: str, quantity: int, operator: str) -> StockLevel:
        """补货并记录。quantity 必须是正整数，补完不能超过容量，operator 不能为空，
        否则 INVALID_ARGUMENT；原料不存在 → NOT_FOUND。返回补货后的库存。
        """

    @abstractmethod
    def list_restocks(self, limit: int = 50) -> list[RestockRecord]:
        """补货记录，最新在前。"""


class StatsService(ABC):
    """数据维护：销售数据分析（“用户分析”）。只统计 COMPLETED 订单。"""

    @abstractmethod
    def summary(self, machine_id: str | None = None, since_ms: int | None = None,
                until_ms: int | None = None) -> SalesSummary:
        """machine_id 为 None 表示全部机器；since 含、until 不含；None 表示不限。
        返回的 since_ms / until_ms：传了就原样返回，没传分别为 0 和“当前时间”。
        by_hour 按 TZ_OFFSET_HOURS 时区计算。
        top_combos：按（基底, 加料集合）分组，次数降序，同次数按 label 升序，最多 5 个；
        label 形如“经典奶茶 + 黑糖珍珠”（加料按 ID 排序）；recipe 只保证 base_id 与 addon_ids
        有意义（addon_ids 按 ID 排序），其余字段取默认值。
        """

    @abstractmethod
    def top_recipes(self, limit: int = 3) -> list[ComboCount]:
        """全部时间、全部机器的 top_combos 前 limit 个。"""


class MachineDriver(ABC):
    """机器维护：机器硬件抽象。正式实现是 MachineSimulator（没有真机）。"""

    @property
    @abstractmethod
    def machine_id(self) -> str: ...

    @abstractmethod
    def status(self) -> MachineState:
        """online = 没有故障；busy = 有正在制作的任务。"""

    @abstractmethod
    def start_job(self, order_id: str, consumption: Consumption) -> None:
        """开始制作，立即返回（异步）。有故障或忙 → MACHINE_UNAVAILABLE。
        同一 order_id 重复调用：若该任务已存在则忽略（幂等）。
        """

    @abstractmethod
    def job_status(self, order_id: str) -> JobStatus:
        """未知 order_id → NOT_FOUND。制作中出现故障 → FAILED，fault 为故障码。"""

    @abstractmethod
    def clear_fault(self, code: FaultCode | None = None) -> MachineState:
        """维护人员排除故障；code 为 None 表示清除全部。"""
