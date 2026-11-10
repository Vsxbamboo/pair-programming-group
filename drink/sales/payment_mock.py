"""模拟支付（已完成，可直接使用）。负责人：B。

二维码内容是 mock-pay://...，界面显示后，用维护页或 POST /api/dev/payments/<id>/succeed
模拟“顾客扫码付款成功”。
"""
from __future__ import annotations

import threading

from drink.model import DrinkError, ErrorCode, PaymentInfo, PaymentStatus

from .interfaces import PaymentGateway


class MockPayment(PaymentGateway):
    method = "mock"

    def __init__(self):
        self._lock = threading.Lock()
        self._payments: dict[str, dict] = {}

    def _get(self, order_id: str) -> dict:
        p = self._payments.get(order_id)
        if p is None:
            raise DrinkError(ErrorCode.NOT_FOUND, f"没有订单 {order_id} 的支付记录")
        return p

    def create(self, order_id, amount_fen, subject):
        if amount_fen <= 0:
            raise DrinkError(ErrorCode.INVALID_ARGUMENT, "金额必须大于 0")
        with self._lock:
            p = self._payments.setdefault(order_id, {
                "amount": amount_fen, "subject": subject, "status": PaymentStatus.WAITING})
            return PaymentInfo(self.method, f"mock-pay://{order_id}?amount_fen={p['amount']}",
                               p["status"])

    def query(self, order_id):
        with self._lock:
            return self._get(order_id)["status"]

    def close(self, order_id):
        with self._lock:
            p = self._get(order_id)
            if p["status"] == PaymentStatus.WAITING:
                p["status"] = PaymentStatus.CLOSED

    def refund(self, order_id, amount_fen):
        with self._lock:
            p = self._get(order_id)
            if p["status"] != PaymentStatus.SUCCESS:
                raise DrinkError(ErrorCode.INVALID_STATE, "只有已付款的订单可以退款")
            if amount_fen != p["amount"]:
                raise DrinkError(ErrorCode.INVALID_ARGUMENT, "只支持全额退款")
            p["status"] = PaymentStatus.REFUNDED

    # ----- 仅模拟支付有：演示用 -----
    def simulate_success(self, order_id: str) -> None:
        with self._lock:
            p = self._get(order_id)
            if p["status"] != PaymentStatus.WAITING:
                raise DrinkError(ErrorCode.INVALID_STATE, "该支付不在等待付款状态")
            p["status"] = PaymentStatus.SUCCESS

    def simulate_close(self, order_id: str) -> None:
        """模拟顾客支付失败 / 支付渠道关闭了交易。"""
        self.close(order_id)
