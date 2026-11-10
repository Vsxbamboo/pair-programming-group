"""全组共用的数据结构。负责人：D（数据结构）。

约定：
- 金额一律整数“分”（*_fen），界面负责格式化成“元”。
- 时间一律 epoch 毫秒（*_ms 或 *_at）。
- 原料用量：液体 mL、固体 g、杯子 个，单位写在 Material.unit。
- 主键一律稳定的英文 ID（"milk_tea"、"pearl"），不用中文名。
- 实体都是不可变的（frozen），要修改用 dataclasses.replace() 生成新对象。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .enums import (FaultCode, ItemKind, JobState, OrderStatus, PaymentStatus,
                    Size, StockStatus, Sugar, Temperature)

Consumption = dict[str, int]
"""一杯饮料消耗的原料：{material_id: 数量}。"""


# ---------- 原料与菜单（食材端读、数据维护写库存） ----------

@dataclass(frozen=True)
class Material:
    """机器里实际储存的原料，例如红茶液、牛奶、珍珠、杯子。"""
    id: str
    name: str
    unit: str               # "mL" / "g" / "个"
    capacity: int           # 料仓容量
    warn_threshold: int     # 低于此值预警


@dataclass(frozen=True)
class MenuItem:
    """顾客能选的东西：基底或加料。consumption 是中杯（M）的用量，不含糖和冰。"""
    id: str
    name: str
    kind: ItemKind
    price_fen: int
    description: str = ""
    color: str = "#cda56c"  # 界面画杯子用
    consumption: Consumption = field(default_factory=dict)
    hot_allowed: bool = True
    iced_allowed: bool = True


@dataclass(frozen=True)
class Recipe:
    """顾客的选择。addon_ids 按选择顺序，不能重复。"""
    base_id: str
    addon_ids: tuple[str, ...] = ()
    size: Size = Size.M
    temperature: Temperature = Temperature.ICED
    sugar: Sugar = Sugar.HALF


@dataclass(frozen=True)
class MenuEntry:
    """菜单上的一项 = 菜单定义 + 当前是否能卖。"""
    item: MenuItem
    available: bool


@dataclass(frozen=True)
class Menu:
    bases: tuple[MenuEntry, ...]
    addons: tuple[MenuEntry, ...]
    sizes: tuple[Size, ...]
    temperatures: tuple[Temperature, ...]
    sugars: tuple[Sugar, ...]
    size_extra_fen: dict[str, int]      # {"M": 0, "L": 300}
    default_recipe: Recipe


# ---------- 订单与支付（销售端） ----------

@dataclass(frozen=True)
class OrderLine:
    label: str          # "经典奶茶"、"黑糖珍珠"、"大杯"
    price_fen: int


@dataclass(frozen=True)
class Quote:
    lines: tuple[OrderLine, ...]
    total_fen: int


@dataclass(frozen=True)
class PaymentInfo:
    method: str             # "mock" / "alipay"
    qr_content: str         # 二维码里的内容，界面负责画成二维码
    status: PaymentStatus = PaymentStatus.WAITING


@dataclass(frozen=True)
class Order:
    order_id: str
    machine_id: str
    recipe: Recipe
    lines: tuple[OrderLine, ...]
    total_fen: int
    status: OrderStatus
    created_at: int
    updated_at: int
    expires_at: int                     # 付款截止时间
    payment: PaymentInfo | None = None
    failure_reason: str | None = None   # PRODUCTION_FAILED 时说明原因


# ---------- 库存与补货（数据维护） ----------

@dataclass(frozen=True)
class StockLevel:
    material: Material
    quantity: int

    @property
    def status(self) -> StockStatus:
        if self.quantity <= 0:
            return StockStatus.EMPTY
        if self.quantity < self.material.warn_threshold:
            return StockStatus.LOW
        return StockStatus.OK


@dataclass(frozen=True)
class RestockRecord:
    record_id: int
    material_id: str
    quantity: int
    operator: str
    created_at: int


# ---------- 统计（数据维护） ----------

@dataclass(frozen=True)
class ComboCount:
    label: str          # "经典奶茶 + 黑糖珍珠"
    recipe: Recipe
    count: int


@dataclass(frozen=True)
class SalesSummary:
    machine_id: str | None              # None 表示所有机器
    since_ms: int
    until_ms: int
    order_count: int                    # 只统计 COMPLETED
    revenue_fen: int
    top_combos: tuple[ComboCount, ...]  # 按次数降序，最多 5 个（基底 + 加料组合，不区分甜度温度杯型）
    by_hour: dict[int, int]             # {小时 0-23: 杯数}，只含有数据的小时
    by_sugar: dict[str, int]            # {"HALF": 3, ...}


# ---------- 机器（机器维护） ----------

@dataclass(frozen=True)
class MachineState:
    machine_id: str
    online: bool                        # False = 有故障，不能接单
    busy: bool                          # 正在做一杯
    faults: tuple[FaultCode, ...]


@dataclass(frozen=True)
class JobStatus:
    order_id: str
    state: JobState
    progress: int = 0                   # 0–100，DONE 时为 100
    step: str = ""                      # 给界面看的当前步骤，如“落杯”“注入茶底”
    fault: FaultCode | None = None
