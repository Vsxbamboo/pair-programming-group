"""统一错误。负责人：D（数据结构）。

所有模块只抛 DrinkError，web 层按 code 转成 HTTP 状态码和 JSON。
"""
from enum import Enum


class ErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"        # 参数格式不对（缺字段、数量为负……）
    INVALID_RECIPE = "INVALID_RECIPE"            # 配方不合法（不存在的食材、违反搭配规则）
    NOT_FOUND = "NOT_FOUND"
    OUT_OF_STOCK = "OUT_OF_STOCK"                # 库存不足，details["missing"] 为缺少的原料 ID
    INVALID_STATE = "INVALID_STATE"              # 当前状态不允许该操作（如取消已付款订单）
    MACHINE_UNAVAILABLE = "MACHINE_UNAVAILABLE"  # 机器故障或忙
    PAYMENT_ERROR = "PAYMENT_ERROR"              # 支付渠道调用失败（网络、签名……）


HTTP_STATUS = {
    ErrorCode.INVALID_ARGUMENT: 400,
    ErrorCode.INVALID_RECIPE: 400,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.OUT_OF_STOCK: 409,
    ErrorCode.INVALID_STATE: 409,
    ErrorCode.MACHINE_UNAVAILABLE: 503,
    ErrorCode.PAYMENT_ERROR: 502,
}


class DrinkError(Exception):
    def __init__(self, code: ErrorCode, message: str, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        body = {"code": self.code.value, "message": self.message}
        if self.details:
            body["details"] = self.details
        return body

    def __repr__(self) -> str:
        return f"DrinkError({self.code.value}, {self.message!r})"
