"""PaymentGateway 契约测试。负责人：B（销售端）。

这里测 MockPayment；支付宝沙箱实现的离线测试在 test_alipay.py。
"""
import pytest

from drink.model import DrinkError, ErrorCode, PaymentStatus
from drink.sales.payment_mock import MockPayment

OWNER = "B 销售+食材"


@pytest.fixture(params=["mock"])
def impl(request):
    return request.param


@pytest.fixture
def pay(impl):
    return MockPayment()


def err(fn, *args):
    with pytest.raises(DrinkError) as e:
        fn(*args)
    return e.value.code


def test_create_is_idempotent(pay):
    a = pay.create("O1", 1400, "经典奶茶")
    b = pay.create("O1", 1400, "经典奶茶")
    assert a == b and a.qr_content and a.status == PaymentStatus.WAITING
    assert pay.query("O1") == PaymentStatus.WAITING


def test_unknown(pay):
    assert err(pay.query, "nope") == ErrorCode.NOT_FOUND


def test_success_then_refund(pay):
    pay.create("O1", 1400, "x")
    pay.simulate_success("O1")
    pay.close("O1")                      # 已付款的支付关不掉，也不报错
    assert pay.query("O1") == PaymentStatus.SUCCESS
    pay.refund("O1", 1400)
    assert pay.query("O1") == PaymentStatus.REFUNDED


def test_close(pay):
    pay.create("O1", 1400, "x")
    pay.close("O1")
    assert pay.query("O1") == PaymentStatus.CLOSED
    assert err(pay.simulate_success, "O1") == ErrorCode.INVALID_STATE


def test_refund_requires_success(pay):
    pay.create("O1", 1400, "x")
    assert err(pay.refund, "O1", 1400) == ErrorCode.INVALID_STATE

