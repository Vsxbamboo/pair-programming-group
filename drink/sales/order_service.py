"""销售端正式实现。负责人：B。

构造参数是约定的一部分（wiring.py 按此创建），不要改。
行为约定见 interfaces.OrderService 的文档字符串和 docs/03-详细设计.md 的状态图；
验收标准是 tests/contract/test_order.py。
"""
from __future__ import annotations

from dataclasses import replace
from threading import Lock
from uuid import uuid4

from drink.maintenance.interfaces import InventoryService, MachineDriver
from drink.model import (Clock, Consumption, DrinkError, ErrorCode, JobState, Order,
                         OrderStatus, PaymentStatus, Recipe, Repository, seed)

from .interfaces import IngredientService, OrderService, PaymentGateway


class OrderServiceImpl(OrderService):

    def __init__(self, machine_id: str, repo: Repository, ingredient: IngredientService,
                 inventory: InventoryService, machine: MachineDriver, payment: PaymentGateway,
                 clock: Clock):
        self.machine_id = machine_id
        self.repo = repo
        self.ingredient = ingredient
        self.inventory = inventory
        self.machine = machine
        self.payment = payment
        self.clock = clock
        self._lock = Lock()
        self._pending_save: Order | None = None

    def _flush_pending_save(self) -> None:
        if self._pending_save is not None:
            self.repo.save_order(self._pending_save)
            self._pending_save = None

    def _save(self, order: Order) -> Order:
        # 保存失败后先重试写入状态，避免下一次查询再次扣库存。
        self._pending_save = order
        self._flush_pending_save()
        return order

    def _active_orders(self) -> list[Order]:
        self._flush_pending_save()
        statuses = [status for status in OrderStatus if status.is_active]
        return self.repo.list_orders(machine_id=self.machine_id, statuses=statuses)

    def _load(self, order_id: str) -> Order:
        self._flush_pending_save()
        order = self.repo.get_order(order_id)
        if order is None or order.machine_id != self.machine_id:
            raise DrinkError(ErrorCode.NOT_FOUND, f"没有订单 {order_id}")
        return order

    def _transition(self, order: Order, status: OrderStatus, *,
                    payment_status: PaymentStatus | None = None,
                    failure_reason: str | None = None) -> Order:
        payment = order.payment
        if payment is not None and payment_status is not None:
            payment = replace(payment, status=payment_status)
        updated = replace(order, status=status, payment=payment,
                          updated_at=self.clock.now_ms(),
                          failure_reason=failure_reason or order.failure_reason)
        return self._save(updated)

    def _check_stock(self, amounts: Consumption) -> None:
        missing = self.inventory.check(amounts)
        if missing:
            message = "原料不足：" + "、".join(missing)
            raise DrinkError(ErrorCode.OUT_OF_STOCK, message, missing=missing)

    def create_order(self, recipe: Recipe) -> Order:
        with self._lock:
            self.ingredient.validate(recipe)
            if not self.machine.status().online:
                raise DrinkError(ErrorCode.MACHINE_UNAVAILABLE, "机器故障，暂停服务")
            for previous in self._active_orders():
                previous = self._advance(previous)
                if previous.status == OrderStatus.AWAITING_PAYMENT:
                    previous = self._advance(self._close_unpaid(previous, OrderStatus.CANCELLED))
                if previous.status.is_active:
                    raise DrinkError(ErrorCode.MACHINE_UNAVAILABLE, "上一杯还在制作，请稍候")
            if self.machine.status().busy:
                raise DrinkError(ErrorCode.MACHINE_UNAVAILABLE, "上一杯还在制作，请稍候")

            self._check_stock(self.ingredient.consumption_of(recipe))
            quote = self.ingredient.quote(recipe)
            order_id = uuid4().hex
            payment = self.payment.create(order_id, quote.total_fen, quote.lines[0].label)
            now = self.clock.now_ms()
            order = Order(
                order_id=order_id, machine_id=self.machine_id, recipe=recipe,
                lines=quote.lines, total_fen=quote.total_fen,
                status=OrderStatus.AWAITING_PAYMENT, payment=payment,
                created_at=now, updated_at=now, expires_at=now + seed.PAYMENT_TIMEOUT_MS,
            )
            return self._save(order)

    def _close_unpaid(self, order: Order, status: OrderStatus) -> Order:
        self.payment.close(order.order_id)
        # 付款可能在上次查询之后、关单之前到账。
        if self.payment.query(order.order_id) == PaymentStatus.SUCCESS:
            return self._transition(order, OrderStatus.PAID, payment_status=PaymentStatus.SUCCESS)
        return self._transition(order, status, payment_status=PaymentStatus.CLOSED)

    def _advance_payment(self, order: Order) -> Order:
        try:
            status = self.payment.query(order.order_id)
        except DrinkError as error:
            if (error.code != ErrorCode.NOT_FOUND or order.payment is None
                    or order.payment.method != "mock"):
                raise
            # 模拟支付在进程重启后会丢失尚未付款的记录。
            status = PaymentStatus.CLOSED
        if status == PaymentStatus.SUCCESS:
            return self._transition(order, OrderStatus.PAID, payment_status=status)
        if status == PaymentStatus.CLOSED:
            return self._transition(order, OrderStatus.CANCELLED, payment_status=status)
        if self.clock.now_ms() >= order.expires_at:
            return self._close_unpaid(order, OrderStatus.EXPIRED)
        return order

    def _start_production(self, order: Order) -> Order:
        try:
            amounts = self.ingredient.consumption_of(order.recipe)
            self._check_stock(amounts)
            self.machine.start_job(order.order_id, amounts)
            self.inventory.consume(amounts, order.order_id)
        except DrinkError as error:
            return self._transition(order, OrderStatus.PRODUCTION_FAILED,
                                    failure_reason=error.message)
        return self._transition(order, OrderStatus.MAKING)

    def _advance_production(self, order: Order) -> Order:
        try:
            job = self.machine.job_status(order.order_id)
        except DrinkError as error:
            if error.code != ErrorCode.NOT_FOUND:
                raise
            return self._transition(order, OrderStatus.PRODUCTION_FAILED,
                                    failure_reason="机器已重启，制作状态丢失")
        if job.state == JobState.DONE:
            return self._transition(order, OrderStatus.COMPLETED)
        if job.state == JobState.FAILED:
            reason = f"制作故障：{job.fault.value}" if job.fault else "制作故障"
            return self._transition(order, OrderStatus.PRODUCTION_FAILED, failure_reason=reason)
        return order

    def _advance(self, order: Order) -> Order:
        if order.status == OrderStatus.AWAITING_PAYMENT:
            order = self._advance_payment(order)
        if order.status == OrderStatus.PAID:
            order = self._start_production(order)
        if order.status == OrderStatus.MAKING:
            order = self._advance_production(order)
        return order

    def get_order(self, order_id: str) -> Order:
        with self._lock:
            return self._advance(self._load(order_id))

    def cancel_order(self, order_id: str) -> Order:
        with self._lock:
            order = self._advance(self._load(order_id))
            if order.status == OrderStatus.AWAITING_PAYMENT:
                order = self._advance(self._close_unpaid(order, OrderStatus.CANCELLED))
                if order.status == OrderStatus.CANCELLED:
                    return order
            raise DrinkError(ErrorCode.INVALID_STATE, "订单已付款或已结束，不能取消")

    def list_orders(self, status: OrderStatus | None = None, limit: int = 50) -> list[Order]:
        with self._lock:
            for order in self._active_orders():
                self._advance(order)
            statuses = [status] if status is not None else None
            return self.repo.list_orders(machine_id=self.machine_id, statuses=statuses, limit=limit)

    def refund_order(self, order_id: str, operator: str) -> Order:
        with self._lock:
            order = self._load(order_id)
            if order.status != OrderStatus.PRODUCTION_FAILED:
                raise DrinkError(ErrorCode.INVALID_STATE, "只有制作失败的订单可以退款")
            if not operator or not operator.strip():
                raise DrinkError(ErrorCode.INVALID_ARGUMENT, "请填写操作人")
            try:
                self.payment.refund(order_id, order.total_fen)
            except DrinkError as error:
                if (error.code != ErrorCode.INVALID_STATE
                        or self.payment.query(order_id) != PaymentStatus.REFUNDED):
                    raise
            return self._transition(order, OrderStatus.REFUNDED, payment_status=PaymentStatus.REFUNDED)
