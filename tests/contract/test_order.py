"""OrderService 契约测试。负责人：B（销售端）。

付款用 MockPayment：system.payment.simulate_success(order_id) 相当于顾客扫码付款。
"""
import pytest

from conftest import JOB_MS
from drink.model import (DrinkError, ErrorCode, FaultCode, OrderLine, OrderStatus, PaymentStatus,
                         Recipe, seed)

COMPONENT = "order"
TEA = Recipe("milk_tea", ("pearl",))
TEA_USE = {"black_tea": 200, "milk": 150, "syrup": 15, "ice": 80, "pearl": 40, "cup": 1}


@pytest.fixture
def svc(system):
    return system.orders


def err(fn, *args):
    with pytest.raises(DrinkError) as e:
        fn(*args)
    return e.value


def stock(system):
    return {s.material.id: s.quantity for s in system.repo.list_stock()}


def paid_and_making(system, svc):
    o = svc.create_order(TEA)
    system.payment.simulate_success(o.order_id)
    assert svc.get_order(o.order_id).status == OrderStatus.MAKING
    return o


class TestCreate:
    def test_awaiting_payment(self, system, svc, clock):
        o = svc.create_order(TEA)
        assert o.status == OrderStatus.AWAITING_PAYMENT
        assert (o.machine_id, o.recipe) == ("M001", TEA)
        assert o.lines == (OrderLine("经典奶茶", 1200), OrderLine("黑糖珍珠", 200))
        assert o.total_fen == 1400
        assert o.created_at == o.updated_at == clock.now_ms()
        assert o.expires_at == clock.now_ms() + seed.PAYMENT_TIMEOUT_MS
        assert o.payment.method == "mock" and o.payment.qr_content
        assert o.payment.status == PaymentStatus.WAITING
        assert system.repo.get_order(o.order_id) == o
        assert system.payment.query(o.order_id) == PaymentStatus.WAITING

    def test_ids_are_unique(self, svc):
        ids = {svc.create_order(TEA).order_id for _ in range(5)}
        assert len(ids) == 5

    def test_does_not_touch_stock(self, system, svc):
        before = stock(system)
        svc.create_order(TEA)
        assert stock(system) == before

    def test_invalid_recipe(self, system, svc):
        assert err(svc.create_order, Recipe("cola")).code == ErrorCode.INVALID_RECIPE
        assert system.repo.list_orders() == []

    def test_out_of_stock(self, system, svc):
        e = err(svc.create_order, Recipe("milk_tea", ("coconut",)))
        assert e.code == ErrorCode.OUT_OF_STOCK
        assert e.details["missing"] == ["coconut"]
        assert system.repo.list_orders() == []

    def test_machine_fault(self, system, svc):
        system.machine.inject_fault(FaultCode.PUMP_ERROR)
        assert err(svc.create_order, TEA).code == ErrorCode.MACHINE_UNAVAILABLE

    def test_new_customer_replaces_unpaid_order(self, system, svc):
        first = svc.create_order(TEA)
        second = svc.create_order(Recipe("jasmine"))
        assert svc.get_order(first.order_id).status == OrderStatus.CANCELLED
        assert system.payment.query(first.order_id) == PaymentStatus.CLOSED
        assert svc.get_order(second.order_id).status == OrderStatus.AWAITING_PAYMENT

    def test_cannot_order_while_making(self, system, svc):
        paid_and_making(system, svc)
        assert err(svc.create_order, TEA).code == ErrorCode.MACHINE_UNAVAILABLE

    def test_can_order_after_previous_cup_done(self, system, svc, clock):
        o = paid_and_making(system, svc)
        clock.advance(JOB_MS)
        svc.create_order(TEA)
        assert svc.get_order(o.order_id).status == OrderStatus.COMPLETED


class TestLifecycle:
    def test_unknown(self, svc):
        assert err(svc.get_order, "nope").code == ErrorCode.NOT_FOUND

    def test_waiting(self, svc, clock):
        o = svc.create_order(TEA)
        clock.advance(seed.PAYMENT_TIMEOUT_MS - 1)
        assert svc.get_order(o.order_id).status == OrderStatus.AWAITING_PAYMENT

    def test_paid_starts_making_and_consumes_stock(self, system, svc):
        before = stock(system)
        o = paid_and_making(system, svc)
        after = stock(system)
        assert {k: before[k] - after[k] for k in before if before[k] != after[k]} == TEA_USE
        assert system.machine.status().busy
        assert svc.get_order(o.order_id).payment.status == PaymentStatus.SUCCESS

    def test_completes(self, system, svc, clock):
        o = paid_and_making(system, svc)
        clock.advance(JOB_MS)
        done = svc.get_order(o.order_id)
        assert done.status == OrderStatus.COMPLETED
        assert done.updated_at == clock.now_ms()

    def test_polling_after_completion_is_harmless(self, system, svc, clock):
        o = paid_and_making(system, svc)
        clock.advance(JOB_MS)
        for _ in range(3):
            svc.get_order(o.order_id)
        assert stock(system)["milk"] == 5000 - 150

    def test_expires(self, system, svc, clock):
        o = svc.create_order(TEA)
        clock.advance(seed.PAYMENT_TIMEOUT_MS)
        assert svc.get_order(o.order_id).status == OrderStatus.EXPIRED
        assert system.payment.query(o.order_id) == PaymentStatus.CLOSED

    def test_payment_closed_by_channel(self, system, svc):
        o = svc.create_order(TEA)
        system.payment.simulate_close(o.order_id)
        assert svc.get_order(o.order_id).status == OrderStatus.CANCELLED

    def test_fault_while_making(self, system, svc, clock):
        o = paid_and_making(system, svc)
        clock.advance(1000)
        system.machine.inject_fault(FaultCode.CUP_JAM)
        failed = svc.get_order(o.order_id)
        assert failed.status == OrderStatus.PRODUCTION_FAILED
        assert "CUP_JAM" in failed.failure_reason

    def test_paid_but_machine_broke_before_start(self, system, svc):
        o = svc.create_order(TEA)
        before = stock(system)
        system.machine.inject_fault(FaultCode.WATER_TEMP_LOW)
        system.payment.simulate_success(o.order_id)
        failed = svc.get_order(o.order_id)
        assert failed.status == OrderStatus.PRODUCTION_FAILED and failed.failure_reason
        assert stock(system) == before


class TestCancel:
    def test_cancel_unpaid(self, system, svc):
        o = svc.create_order(TEA)
        c = svc.cancel_order(o.order_id)
        assert c.status == OrderStatus.CANCELLED
        assert system.payment.query(o.order_id) == PaymentStatus.CLOSED

    def test_cannot_cancel_after_paying(self, system, svc):
        o = svc.create_order(TEA)
        system.payment.simulate_success(o.order_id)   # 顾客已付款，但界面还没轮询到
        assert err(svc.cancel_order, o.order_id).code == ErrorCode.INVALID_STATE
        assert svc.get_order(o.order_id).status == OrderStatus.MAKING

    def test_unknown(self, svc):
        assert err(svc.cancel_order, "nope").code == ErrorCode.NOT_FOUND


class TestRefundAndList:
    def failed_order(self, system, svc, clock):
        o = paid_and_making(system, svc)
        system.machine.inject_fault(FaultCode.CUP_JAM)
        return svc.get_order(o.order_id)

    def test_refund_failed_order(self, system, svc, clock):
        o = self.failed_order(system, svc, clock)
        r = svc.refund_order(o.order_id, "小王")
        assert r.status == OrderStatus.REFUNDED
        assert r.payment.status == PaymentStatus.REFUNDED
        assert system.payment.query(o.order_id) == PaymentStatus.REFUNDED

    def test_refund_requires_operator(self, system, svc, clock):
        o = self.failed_order(system, svc, clock)
        assert err(svc.refund_order, o.order_id, " ").code == ErrorCode.INVALID_ARGUMENT

    def test_cannot_refund_completed(self, system, svc, clock):
        o = paid_and_making(system, svc)
        clock.advance(JOB_MS)
        svc.get_order(o.order_id)
        assert err(svc.refund_order, o.order_id, "小王").code == ErrorCode.INVALID_STATE

    def test_list(self, system, svc, clock):
        a = svc.create_order(TEA)
        clock.advance(10)
        b = svc.create_order(TEA)               # a 被取消
        assert [o.order_id for o in svc.list_orders()] == [b.order_id, a.order_id]
        assert [o.order_id for o in svc.list_orders(OrderStatus.CANCELLED)] == [a.order_id]
        assert len(svc.list_orders(limit=1)) == 1

    def test_list_advances_active_orders(self, system, svc, clock):
        o = paid_and_making(system, svc)
        clock.advance(JOB_MS)                   # 没有人轮询 get_order
        assert svc.list_orders()[0].status == OrderStatus.COMPLETED
        assert system.repo.get_order(o.order_id).status == OrderStatus.COMPLETED
