"""支付宝沙箱当面付（加分项）。负责人：B。

流程：create → alipay.trade.precreate，返回的 qr_code 作为 qr_content；
query → alipay.trade.query，把 trade_status 映射为 PaymentStatus：
    WAIT_BUYER_PAY → WAITING；TRADE_SUCCESS / TRADE_FINISHED → SUCCESS；TRADE_CLOSED → CLOSED
    （交易不存在：刚预下单、顾客还没扫码时会出现，也视为 WAITING）
close → alipay.trade.close；refund → alipay.trade.refund。

不使用支付宝异步通知（notify_url 需要公网地址），付款结果全靠前端轮询 → OrderService.get_order → query。
网络或签名错误统一抛 DrinkError(PAYMENT_ERROR)。

需要额外依赖（如官方 alipay-sdk-python），写进 requirements-alipay.txt，不要放进主 requirements.txt，
保证不接支付宝的同学也能零配置运行。密钥从环境变量读取，不要提交到 git：
    ALIPAY_APP_ID, ALIPAY_PRIVATE_KEY_PATH, ALIPAY_PUBLIC_KEY_PATH, ALIPAY_GATEWAY
"""
from __future__ import annotations

from .interfaces import PaymentGateway


class AlipaySandboxPayment(PaymentGateway):
    method = "alipay"

    def __init__(self, app_id: str, private_key_path: str, alipay_public_key_path: str,
                 gateway: str):
        self.app_id = app_id
        self.private_key_path = private_key_path
        self.alipay_public_key_path = alipay_public_key_path
        self.gateway = gateway

    def create(self, order_id, amount_fen, subject):
        raise NotImplementedError

    def query(self, order_id):
        raise NotImplementedError

    def close(self, order_id):
        raise NotImplementedError

    def refund(self, order_id, amount_fen):
        raise NotImplementedError
