"""支付宝沙箱当面付。负责人：B（A 先行实现，B 负责维护和联调）。

流程（不需要公网服务器）：
    create → alipay.trade.precreate，返回的 qr_code 作为 qr_content，界面把它画成二维码；
    query  → alipay.trade.query，把 trade_status 映射为 PaymentStatus：
             WAIT_BUYER_PAY → WAITING；TRADE_SUCCESS / TRADE_FINISHED → SUCCESS；TRADE_CLOSED → CLOSED；
             交易不存在（刚预下单、顾客还没扫码）→ WAITING；本实例退过款的 → REFUNDED；
    close  → alipay.trade.close（顾客还没扫码时交易不存在，视为已关闭）；
    refund → alipay.trade.refund。
付款结果靠前端轮询 → OrderService.get_order → query，不使用 notify_url（那需要公网地址）。

签名：RSA2（SHA256withRSA）。请求用“应用私钥”签名；响应用“支付宝公钥”验签，验签失败视为 PAYMENT_ERROR。
网络、签名、业务错误统一抛 DrinkError(PAYMENT_ERROR)。

配置见 docs/07-支付宝沙箱配置.md。额外依赖 cryptography（见 requirements-alipay.txt）。
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from drink.model import DrinkError, ErrorCode, PaymentInfo, PaymentStatus

from .interfaces import PaymentGateway

SANDBOX_GATEWAY = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"

Transport = Callable[[str, bytes], str]
"""(网关地址, 表单字节) → 响应文本。测试时可以换成假网关。"""


def _http_post(url: str, body: bytes) -> str:
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return resp.read().decode("utf-8")


def _pem(key_text: str, kind: str) -> bytes:
    """接受 PEM 或支付宝密钥工具导出的“一整行 base64”。kind: PRIVATE / PUBLIC。"""
    text = key_text.strip()
    if "-----BEGIN" in text:
        return text.encode()
    body = "\n".join(text[i:i + 64] for i in range(0, len(text), 64))
    return f"-----BEGIN {kind} KEY-----\n{body}\n-----END {kind} KEY-----\n".encode()


def _signing_content(params: dict[str, str]) -> str:
    return "&".join(f"{k}={params[k]}" for k in sorted(params) if k != "sign" and params[k] not in ("", None))


def _yuan(fen: int) -> str:
    return f"{fen // 100}.{fen % 100:02d}"


class AlipaySandboxPayment(PaymentGateway):
    method = "alipay"

    def __init__(self, app_id: str, app_private_key: str, alipay_public_key: str,
                 gateway: str = SANDBOX_GATEWAY, transport: Transport | None = None):
        from cryptography.hazmat.primitives import serialization

        self.app_id = app_id
        self.gateway = gateway
        self._transport = transport or _http_post
        self._private_key = serialization.load_pem_private_key(_pem(app_private_key, "PRIVATE"), password=None)
        self._alipay_key = serialization.load_pem_public_key(_pem(alipay_public_key, "PUBLIC"))
        self._lock = threading.Lock()
        self._created: dict[str, dict] = {}     # order_id -> {"amount": fen, "info": PaymentInfo}
        self._refunded: set[str] = set()

    # ------------------------------------------------------------------ 配置

    @classmethod
    def from_config(cls, path: str | os.PathLike = "alipay.json") -> "AlipaySandboxPayment":
        """优先读环境变量，其次读 alipay.json（已在 .gitignore 中）。字段含义见 docs/07。"""
        cfg: dict = {}
        p = Path(path)
        if p.exists():
            cfg = json.loads(p.read_text(encoding="utf-8"))
        base = p.parent

        def value(env, key, default=None):
            return os.environ.get(env) or cfg.get(key) or default

        def key_text(env, key):
            raw = value(env, key)
            if not raw:
                raise DrinkError(ErrorCode.PAYMENT_ERROR, f"缺少支付宝配置 {key}（或环境变量 {env}）")
            f = Path(raw) if Path(raw).is_absolute() else base / raw
            return f.read_text(encoding="utf-8")

        app_id = value("ALIPAY_APP_ID", "app_id")
        if not app_id:
            raise DrinkError(ErrorCode.PAYMENT_ERROR, "缺少支付宝配置 app_id（或环境变量 ALIPAY_APP_ID）")
        return cls(app_id, key_text("ALIPAY_PRIVATE_KEY_PATH", "private_key_path"),
                   key_text("ALIPAY_PUBLIC_KEY_PATH", "alipay_public_key_path"),
                   value("ALIPAY_GATEWAY", "gateway", SANDBOX_GATEWAY))

    # ------------------------------------------------------------------ 底层调用

    def _sign(self, content: str) -> str:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        sig = self._private_key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode()

    def _verify(self, content: str, sign: str) -> bool:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        try:
            self._alipay_key.verify(base64.b64decode(sign), content.encode("utf-8"), padding.PKCS1v15(),
                                    hashes.SHA256())
            return True
        except (InvalidSignature, ValueError):
            return False

    def _call(self, method: str, biz: dict) -> dict:
        params = {
            "app_id": self.app_id, "method": method, "format": "JSON", "charset": "utf-8",
            "sign_type": "RSA2", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "version": "1.0",
            "biz_content": json.dumps(biz, ensure_ascii=False, separators=(",", ":")),
        }
        params["sign"] = self._sign(_signing_content(params))
        try:
            text = self._transport(self.gateway, urllib.parse.urlencode(params).encode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise DrinkError(ErrorCode.PAYMENT_ERROR, f"连接支付宝失败：{e}") from None

        key = method.replace(".", "_") + "_response"
        marker = text.find(f'"{key}"')
        if marker < 0:
            raise DrinkError(ErrorCode.PAYMENT_ERROR, "支付宝返回格式不正确")
        start = text.index(":", marker) + 1
        while text[start] in " \t\r\n":
            start += 1
        body, end = json.JSONDecoder().raw_decode(text, start)
        sign = json.loads(text).get("sign")
        if not sign or not self._verify(text[start:end], sign):
            raise DrinkError(ErrorCode.PAYMENT_ERROR, "支付宝返回验签失败，请检查“支付宝公钥”是否填对")
        return body

    @staticmethod
    def _fail(body: dict, what: str) -> DrinkError:
        detail = body.get("sub_msg") or body.get("msg") or "未知错误"
        return DrinkError(ErrorCode.PAYMENT_ERROR, f"{what}失败：{detail}", sub_code=body.get("sub_code"))

    # ------------------------------------------------------------------ PaymentGateway

    def create(self, order_id, amount_fen, subject):
        if amount_fen <= 0:
            raise DrinkError(ErrorCode.INVALID_ARGUMENT, "金额必须大于 0")
        with self._lock:
            if order_id in self._created:
                return self._created[order_id]["info"]
        body = self._call("alipay.trade.precreate", {
            "out_trade_no": order_id, "total_amount": _yuan(amount_fen), "subject": subject})
        if body.get("code") != "10000" or not body.get("qr_code"):
            raise self._fail(body, "生成付款码")
        info = PaymentInfo(self.method, body["qr_code"], PaymentStatus.WAITING)
        with self._lock:
            self._created[order_id] = {"amount": amount_fen, "info": info}
        return info

    def query(self, order_id):
        if order_id in self._refunded:
            return PaymentStatus.REFUNDED
        body = self._call("alipay.trade.query", {"out_trade_no": order_id})
        if body.get("code") == "10000":
            status = body.get("trade_status")
            if status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
                return PaymentStatus.SUCCESS
            if status == "TRADE_CLOSED":
                return PaymentStatus.CLOSED
            return PaymentStatus.WAITING
        if body.get("sub_code") == "ACQ.TRADE_NOT_EXIST":
            # 预下单后顾客还没扫码时，支付宝查不到这笔交易；程序重启后也无法区分，统一当作“等待付款”，
            # 超时后由 OrderService 关闭订单。
            return PaymentStatus.WAITING
        raise self._fail(body, "查询付款结果")

    def close(self, order_id):
        body = self._call("alipay.trade.close", {"out_trade_no": order_id})
        if body.get("code") == "10000":
            return
        if body.get("sub_code") in ("ACQ.TRADE_NOT_EXIST", "ACQ.TRADE_STATUS_ERROR"):
            return      # 顾客还没扫码（交易不存在）或已付款（关不掉），都按约定不报错
        raise self._fail(body, "关闭交易")

    def refund(self, order_id, amount_fen):
        if self.query(order_id) != PaymentStatus.SUCCESS:
            raise DrinkError(ErrorCode.INVALID_STATE, "只有已付款的订单可以退款")
        created = self._created.get(order_id)
        if created and amount_fen != created["amount"]:
            raise DrinkError(ErrorCode.INVALID_ARGUMENT, "只支持全额退款")
        body = self._call("alipay.trade.refund", {
            "out_trade_no": order_id, "refund_amount": _yuan(amount_fen), "out_request_no": f"{order_id}-R"})
        if body.get("code") != "10000":
            raise self._fail(body, "退款")
        self._refunded.add(order_id)
