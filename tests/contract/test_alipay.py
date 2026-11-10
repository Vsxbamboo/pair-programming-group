"""支付宝沙箱当面付的离线测试。负责人：B。

用一个假的“支付宝网关”代替真网关：它会校验我们的 RSA2 签名，并用“支付宝私钥”给响应签名，
所以签名、验签、参数和状态映射都能在本地测到。真沙箱联调见 docs/07-支付宝沙箱配置.md。
"""
import base64
import json
import urllib.parse

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402

from drink.model import DrinkError, ErrorCode, PaymentStatus  # noqa: E402
from drink.sales.payment_alipay import AlipaySandboxPayment, _signing_content  # noqa: E402

OWNER = "B 销售+食材"


def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()).decode()
    public_der = key.public_key().public_bytes(serialization.Encoding.DER,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, private_pem, base64.b64encode(public_der).decode()   # 公钥用“一整行 base64”，和密钥工具一致


APP_KEY, APP_PRIVATE_PEM, APP_PUBLIC_B64 = keypair()
ALI_KEY, _, ALI_PUBLIC_B64 = keypair()


class FakeAlipay:
    """记录交易状态的假网关。trades[out_trade_no] = {"amount": "14.00", "status": ...}"""

    def __init__(self):
        self.trades = {}
        self.calls = []
        self.tamper = False

    def __call__(self, url, body):
        params = dict(urllib.parse.parse_qsl(body.decode()))
        sig = base64.b64decode(params["sign"])
        APP_KEY.public_key().verify(sig, _signing_content(params).encode(), padding.PKCS1v15(), hashes.SHA256())
        method, biz = params["method"], json.loads(params["biz_content"])
        self.calls.append((method, biz))
        trade = self.trades.get(biz["out_trade_no"])
        if method == "alipay.trade.precreate":
            self.trades[biz["out_trade_no"]] = {"amount": biz["total_amount"], "status": None}
            resp = {"code": "10000", "msg": "Success", "out_trade_no": biz["out_trade_no"],
                    "qr_code": f"https://qr.alipay.com/fake{biz['out_trade_no']}"}
        elif trade is None or (method in ("alipay.trade.query", "alipay.trade.close") and trade["status"] is None):
            resp = {"code": "40004", "msg": "Business Failed", "sub_code": "ACQ.TRADE_NOT_EXIST",
                    "sub_msg": "交易不存在"}
        elif method == "alipay.trade.query":
            resp = {"code": "10000", "msg": "Success", "trade_status": trade["status"]}
        elif method == "alipay.trade.close":
            if trade["status"] == "TRADE_SUCCESS":
                resp = {"code": "40004", "sub_code": "ACQ.TRADE_STATUS_ERROR", "sub_msg": "交易状态不合法"}
            else:
                trade["status"] = "TRADE_CLOSED"
                resp = {"code": "10000", "msg": "Success"}
        elif method == "alipay.trade.refund":
            trade["status"] = "TRADE_CLOSED"
            resp = {"code": "10000", "msg": "Success", "fund_change": "Y", "refund_fee": biz["refund_amount"]}
        else:
            resp = {"code": "40004", "sub_code": "UNKNOWN"}
        content = json.dumps(resp, ensure_ascii=False)
        sign = base64.b64encode(ALI_KEY.sign(content.encode(), padding.PKCS1v15(), hashes.SHA256())).decode()
        if self.tamper:
            content = content.replace("10000", "10000 ")
        return f'{{"{method.replace(".", "_")}_response":{content},"sign":"{sign}"}}'

    def scan_and_pay(self, order_id):
        self.trades[order_id]["status"] = "TRADE_SUCCESS"

    def scan_only(self, order_id):
        self.trades[order_id]["status"] = "WAIT_BUYER_PAY"


@pytest.fixture
def gw():
    return FakeAlipay()


@pytest.fixture
def pay(gw):
    return AlipaySandboxPayment("9021000000000000", APP_PRIVATE_PEM, ALI_PUBLIC_B64, transport=gw)


def code_of(fn, *args):
    with pytest.raises(DrinkError) as e:
        fn(*args)
    return e.value.code


def test_create_returns_qr_and_amount_in_yuan(pay, gw):
    info = pay.create("M001-1", 1405, "经典奶茶")
    assert info.method == "alipay" and info.qr_content.startswith("https://qr.alipay.com/")
    assert info.status == PaymentStatus.WAITING
    assert gw.calls[0] == ("alipay.trade.precreate",
                           {"out_trade_no": "M001-1", "total_amount": "14.05", "subject": "经典奶茶"})


def test_create_is_idempotent(pay, gw):
    assert pay.create("M001-1", 1400, "x") == pay.create("M001-1", 1400, "x")
    assert len(gw.calls) == 1


def test_query_maps_status(pay, gw):
    pay.create("M001-1", 1400, "x")
    assert pay.query("M001-1") == PaymentStatus.WAITING      # 还没扫码：交易不存在
    gw.scan_only("M001-1")
    assert pay.query("M001-1") == PaymentStatus.WAITING      # 扫了还没付
    gw.scan_and_pay("M001-1")
    assert pay.query("M001-1") == PaymentStatus.SUCCESS


def test_close_before_scan_and_after_pay_do_not_raise(pay, gw):
    pay.create("A", 1400, "x")
    pay.close("A")                                            # 交易不存在
    pay.create("B", 1400, "x")
    gw.scan_only("B")
    pay.close("B")
    assert pay.query("B") == PaymentStatus.CLOSED
    pay.create("C", 1400, "x")
    gw.scan_and_pay("C")
    pay.close("C")                                            # 已付款关不掉，不报错
    assert pay.query("C") == PaymentStatus.SUCCESS


def test_refund(pay, gw):
    pay.create("A", 1400, "x")
    assert code_of(pay.refund, "A", 1400) == ErrorCode.INVALID_STATE
    gw.scan_and_pay("A")
    assert code_of(pay.refund, "A", 1000) == ErrorCode.INVALID_ARGUMENT
    pay.refund("A", 1400)
    assert pay.query("A") == PaymentStatus.REFUNDED
    assert gw.calls[-1][0] == "alipay.trade.refund" or gw.calls[-2][0] == "alipay.trade.refund"


def test_bad_response_signature_is_rejected(pay, gw):
    gw.tamper = True
    assert code_of(pay.create, "A", 1400, "x") == ErrorCode.PAYMENT_ERROR


def test_network_error_becomes_payment_error():
    def broken(url, body):
        raise OSError("connection refused")
    pay = AlipaySandboxPayment("1", APP_PRIVATE_PEM, ALI_PUBLIC_B64, transport=broken)
    assert code_of(pay.create, "A", 1400, "x") == ErrorCode.PAYMENT_ERROR


def test_works_with_order_service(gw, clock):
    """接到完整下单流程里：扫码付款后订单进入制作。"""
    from drink.model import OrderStatus, Recipe
    from drink.wiring import build
    pay = AlipaySandboxPayment("1", APP_PRIVATE_PEM, ALI_PUBLIC_B64, transport=gw)
    s = build(clock=clock, payment=pay, machine_job_ms=5000)
    order = s.orders.create_order(Recipe("milk_tea", ("pearl",)))
    assert order.payment.qr_content.startswith("https://qr.alipay.com/")
    assert s.orders.get_order(order.order_id).status == OrderStatus.AWAITING_PAYMENT
    gw.scan_and_pay(order.order_id)
    assert s.orders.get_order(order.order_id).status == OrderStatus.MAKING
