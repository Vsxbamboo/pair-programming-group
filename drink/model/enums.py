"""全组共用的枚举。负责人：D（数据结构）。

枚举的 value 就是 JSON / 数据库里存的字符串，改名前必须全组同意。
"""
from enum import Enum


class ItemKind(str, Enum):
    BASE = "BASE"      # 基底：奶茶、绿茶、咖啡……必选一款
    ADDON = "ADDON"    # 加料：珍珠、布丁……可多选


class Size(str, Enum):
    M = "M"            # 中杯 500 mL
    L = "L"            # 大杯 700 mL


class Temperature(str, Enum):
    ICED = "ICED"
    NORMAL = "NORMAL"
    HOT = "HOT"


class Sugar(str, Enum):
    NONE = "NONE"
    LIGHT = "LIGHT"    # 三分糖
    HALF = "HALF"
    FULL = "FULL"


class OrderStatus(str, Enum):
    AWAITING_PAYMENT = "AWAITING_PAYMENT"    # 已下单，等顾客扫码
    PAID = "PAID"                            # 已付款，等待机器接单（通常一闪而过）
    MAKING = "MAKING"                        # 机器制作中
    COMPLETED = "COMPLETED"                  # 出杯完成
    PRODUCTION_FAILED = "PRODUCTION_FAILED"  # 已付款但制作失败，等待处理
    REFUNDED = "REFUNDED"                    # 失败订单已退款
    CANCELLED = "CANCELLED"                  # 付款前顾客取消
    EXPIRED = "EXPIRED"                      # 付款超时自动关闭

    @property
    def is_active(self) -> bool:
        """订单仍在占用机器（同一台机器同一时间只能有一个）。"""
        return self in (OrderStatus.AWAITING_PAYMENT, OrderStatus.PAID, OrderStatus.MAKING)

    @property
    def is_final(self) -> bool:
        return self in (OrderStatus.COMPLETED, OrderStatus.REFUNDED,
                        OrderStatus.CANCELLED, OrderStatus.EXPIRED)


class PaymentStatus(str, Enum):
    WAITING = "WAITING"    # 二维码已生成，顾客还没付
    SUCCESS = "SUCCESS"
    CLOSED = "CLOSED"      # 已关闭（超时、取消、支付失败）
    REFUNDED = "REFUNDED"


class JobState(str, Enum):
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class FaultCode(str, Enum):
    CUP_JAM = "CUP_JAM"              # 落杯卡住
    OUT_OF_CUPS = "OUT_OF_CUPS"      # 杯子用完
    WATER_TEMP_LOW = "WATER_TEMP_LOW"
    PUMP_ERROR = "PUMP_ERROR"


class StockStatus(str, Enum):
    OK = "OK"
    LOW = "LOW"        # 低于预警线
    EMPTY = "EMPTY"
