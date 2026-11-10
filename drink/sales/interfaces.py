"""销售端 + 食材端的接口。负责人：B。

改动任何方法签名或行为约定，必须先在组里讨论，并同步修改 docs/04-接口契约.md 和契约测试。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from drink.model import (Consumption, Menu, Order, OrderStatus, PaymentInfo, PaymentStatus,
                         Quote, Recipe)


class IngredientService(ABC):
    """食材端：菜单、配方校验、计价、原料换算、搭配推荐。"""

    @abstractmethod
    def get_menu(self) -> Menu:
        """菜单 + 每一项当前能否售卖。

        available 规则：
        - 基底：库存足够做一杯“大杯、常温、无糖、不加料”（含 1 个杯子）；
        - 加料：库存 ≥ 该加料一份的用量。
        """

    @abstractmethod
    def validate(self, recipe: Recipe) -> None:
        """不合法时抛 INVALID_RECIPE，message 写清楚原因。规则：
        1. base_id 存在且是 BASE；
        2. 每个 addon_id 存在且是 ADDON，不重复，最多 MAX_ADDONS 个；
        3. 温度被该基底允许（hot_allowed / iced_allowed）。
        不检查库存。
        """

    @abstractmethod
    def quote(self, recipe: Recipe) -> Quote:
        """先 validate。明细顺序：基底、各加料（按选择顺序）、杯型加价（仅当 > 0）。"""

    @abstractmethod
    def consumption_of(self, recipe: Recipe) -> Consumption:
        """先 validate。换算规则（数值见 seed.py）：
        - 基底用量 × SIZE_FACTOR[size]，四舍五入为整数；
        - 糖浆 SUGAR_SYRUP_ML[sugar] × SIZE_FACTOR[size]；冰 ICE_G[temperature] × SIZE_FACTOR[size]；
        - 每个加料按其用量（不随杯型变化）；
        - 杯子 1 个；
        - 用量为 0 的原料不出现在结果里。
        """

    @abstractmethod
    def recommend(self, limit: int = 3) -> list[Recipe]:
        """推荐配方，最多 limit 个，都必须当前可售且合法。
        先取历史销量最高的组合（StatsService.top_recipes），不足用 PRESET_RECOMMENDATIONS 补齐；
        按（基底, 加料集合）去重。
        """


class PaymentGateway(ABC):
    """支付渠道。正式实现有两个：MockPayment（演示）和 AlipaySandboxPayment（加分项）。"""

    method: str = "abstract"

    @abstractmethod
    def create(self, order_id: str, amount_fen: int, subject: str) -> PaymentInfo:
        """生成付款二维码。同一 order_id 重复调用返回同一笔支付（幂等）。"""

    @abstractmethod
    def query(self, order_id: str) -> PaymentStatus:
        """查询付款结果。未知 order_id → NOT_FOUND。"""

    @abstractmethod
    def close(self, order_id: str) -> None:
        """关闭未付款的支付；已成功的支付不受影响（不报错）。"""

    @abstractmethod
    def refund(self, order_id: str, amount_fen: int) -> None:
        """全额退款；只有 SUCCESS 状态可退，否则 INVALID_STATE。"""


class OrderService(ABC):
    """销售端：订单生命周期。状态图见 docs/03-详细设计.md。"""

    @abstractmethod
    def create_order(self, recipe: Recipe) -> Order:
        """下单并生成付款二维码，返回 AWAITING_PAYMENT 订单。依次检查：
        1. 配方合法（INVALID_RECIPE）；
        2. 机器在线（MACHINE_UNAVAILABLE）；
        3. 若本机已有 PAID / MAKING 订单 → MACHINE_UNAVAILABLE；
           若有 AWAITING_PAYMENT 订单 → 先把它取消（换人点单）；
        4. 库存足够（OUT_OF_STOCK，details["missing"]）。
        expires_at = now + PAYMENT_TIMEOUT_MS。
        """

    @abstractmethod
    def get_order(self, order_id: str) -> Order:
        """查询订单，并顺带推进状态（前端每 1–2 秒轮询一次）：
        - AWAITING_PAYMENT：支付成功 → PAID；支付关闭 → CANCELLED；超时 → 关闭支付并 EXPIRED；
        - PAID：启动制作并扣库存 → MAKING；启动失败 → PRODUCTION_FAILED；
        - MAKING：制作完成 → COMPLETED；失败 → PRODUCTION_FAILED（failure_reason 写故障）；
          机器查不到该任务（程序重启过）→ PRODUCTION_FAILED。
        一次调用内可以连续推进多步（例如 AWAITING_PAYMENT → PAID → MAKING）。
        未知 order_id → NOT_FOUND。
        """

    @abstractmethod
    def cancel_order(self, order_id: str) -> Order:
        """顾客取消。先按 get_order 推进状态；只有 AWAITING_PAYMENT 能取消，否则 INVALID_STATE。"""

    @abstractmethod
    def list_orders(self, status: OrderStatus | None = None, limit: int = 50) -> list[Order]:
        """本机订单，最新在前。供维护页“异常订单”使用。
        返回前先像 get_order 一样推进本机所有活动订单（AWAITING_PAYMENT / PAID / MAKING），
        这样即使点单页没在轮询，维护页看到的状态也是最新的。
        """

    @abstractmethod
    def refund_order(self, order_id: str, operator: str) -> Order:
        """维护人员给制作失败的订单退款。只有 PRODUCTION_FAILED 可退 → REFUNDED，否则 INVALID_STATE。"""
