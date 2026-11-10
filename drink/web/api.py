"""HTTP 接口层。负责人：A（GUI）。

这一层只做三件事：解析请求 → 调服务 → 把结果转成 JSON。不写业务规则。
接口清单与示例见 docs/04-接口契约.md 第 3 节；验收标准是 tests/api/test_api.py。

错误统一返回：HTTP 状态码 + {"error": {"code": "...", "message": "...", "details": {...}}}
"""
from __future__ import annotations

import io
from pathlib import Path

from flask import Blueprint, Flask, Response, jsonify, request, send_from_directory

from drink.model import DrinkError, ErrorCode, FaultCode, OrderStatus
from drink.model.errors import HTTP_STATUS
from drink.model.serialize import recipe_from_dict, to_jsonable
from drink.wiring import System

STATIC_DIR = Path(__file__).parent / "static"


def ok(obj, status=200):
    return jsonify(to_jsonable(obj)), status


def body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise DrinkError(ErrorCode.INVALID_ARGUMENT, "请求体必须是 JSON 对象")
    return data


def int_arg(name: str, default=None):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise DrinkError(ErrorCode.INVALID_ARGUMENT, f"{name} 必须是整数") from None


def enum_arg(cls, raw, name):
    try:
        return cls(raw)
    except ValueError:
        raise DrinkError(ErrorCode.INVALID_ARGUMENT, f"{name} 取值不正确：{raw}") from None


def create_app(system: System, *, demo: bool = True, public_url: str | None = None) -> Flask:
    """public_url：手机能访问到的本机地址（如 http://192.168.1.5:3000），用于演示收银台二维码。
    不传则用浏览器访问时的地址。"""
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.json.ensure_ascii = False
    app.config["SYSTEM"] = system
    api = Blueprint("api", __name__, url_prefix="/api")
    s = system

    @app.errorhandler(DrinkError)
    def on_drink_error(e: DrinkError):
        return jsonify({"error": e.to_dict()}), HTTP_STATUS[e.code]

    @app.errorhandler(404)
    def on_404(e):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "没有这个地址"}}), 404

    @app.errorhandler(405)
    def on_405(e):
        return jsonify({"error": {"code": "INVALID_ARGUMENT", "message": "请求方法不对"}}), 405

    # ---------------- 页面 ----------------
    @app.get("/")
    def kiosk_page():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/admin")
    def admin_page():
        return send_from_directory(STATIC_DIR, "admin.html")

    @app.get("/pay/<order_id>")
    def demo_cashier_page(order_id):
        """手机扫演示二维码后打开的“演示收银台”。"""
        return send_from_directory(STATIC_DIR, "pay.html")

    # ---------------- 通用 ----------------
    @api.get("/config")
    def config():
        return ok({"demo": demo, "machine_id": s.machine.machine_id,
                   "payment_method": s.payment.method,
                   "pay_base_url": (public_url or request.host_url).rstrip("/")})

    @api.get("/qr.svg")
    def qr_svg():
        import segno

        text = request.args.get("text", "")
        if not text or len(text) > 600:
            raise DrinkError(ErrorCode.INVALID_ARGUMENT, "text 不能为空，且不超过 600 个字符")
        buf = io.BytesIO()
        segno.make(text, error="m").save(buf, kind="svg", scale=8, border=2, dark="#233b34", xmldecl=False)
        return Response(buf.getvalue(), mimetype="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=3600"})

    # ---------------- 顾客 ----------------
    @api.get("/menu")
    def menu():
        return ok(s.ingredient.get_menu())

    @api.get("/recommendations")
    def recommendations():
        return ok(s.ingredient.recommend(int_arg("limit", 3)))

    @api.post("/quotes")
    def quote():
        return ok(s.ingredient.quote(recipe_from_dict(body())))

    @api.post("/orders")
    def create_order():
        return ok(s.orders.create_order(recipe_from_dict(body())), 201)

    @api.get("/orders/<order_id>")
    def get_order(order_id):
        return ok(s.orders.get_order(order_id))

    @api.get("/orders/<order_id>/progress")
    def order_progress(order_id):
        s.orders.get_order(order_id)            # 订单不存在时返回 404
        return ok(s.machine.job_status(order_id))

    @api.post("/orders/<order_id>/cancel")
    def cancel_order(order_id):
        return ok(s.orders.cancel_order(order_id))

    @api.get("/machine")
    def machine_status():
        return ok(s.machine.status())

    # ---------------- 维护人员 ----------------
    @api.get("/admin/stock")
    def stock():
        return ok(s.inventory.list_stock())

    @api.post("/admin/restock")
    def restock():
        data = body()
        return ok(s.inventory.restock(data.get("material_id", ""), data.get("quantity"),
                                      data.get("operator", "")))

    @api.get("/admin/restocks")
    def restocks():
        return ok(s.inventory.list_restocks(int_arg("limit", 50)))

    @api.get("/admin/orders")
    def admin_orders():
        raw = request.args.get("status")
        status = enum_arg(OrderStatus, raw, "status") if raw else None
        return ok(s.orders.list_orders(status, int_arg("limit", 50)))

    @api.post("/admin/orders/<order_id>/refund")
    def refund(order_id):
        return ok(s.orders.refund_order(order_id, body().get("operator", "")))

    @api.post("/admin/machine/clear-fault")
    def clear_fault():
        raw = (request.get_json(silent=True) or {}).get("code")
        return ok(s.machine.clear_fault(enum_arg(FaultCode, raw, "code") if raw else None))

    @api.get("/admin/stats")
    def stats():
        return ok(s.stats.summary(request.args.get("machine_id") or None,
                                  int_arg("since_ms"), int_arg("until_ms")))

    # ---------------- 演示用（demo=False 时不存在） ----------------
    if demo:
        @api.post("/dev/payments/<order_id>/succeed")
        def dev_pay(order_id):
            _need(s.payment, "simulate_success")(order_id)
            return ok(s.orders.get_order(order_id))

        @api.post("/dev/payments/<order_id>/close")
        def dev_close(order_id):
            _need(s.payment, "simulate_close")(order_id)
            return ok(s.orders.get_order(order_id))

        @api.post("/dev/machine/faults")
        def dev_fault():
            code = enum_arg(FaultCode, body().get("code"), "code")
            _need(s.machine, "inject_fault")(code)
            return ok(s.machine.status())

    app.register_blueprint(api)
    return app


def _need(obj, method):
    fn = getattr(obj, method, None)
    if fn is None:
        raise DrinkError(ErrorCode.INVALID_STATE, f"当前实现不支持 {method}（不是模拟实现）")
    return fn
