"""HTTP 接口契约测试。负责人：A（GUI）。

后端全部用参考实现，只检查“URL、请求格式、响应格式、错误映射”是否符合 docs/04-接口契约.md。
前端代码按这里的格式写，就不怕后端换实现。
"""
import pytest

from conftest import JOB_MS
from drink.web.api import create_app
from drink.wiring import build

OWNER = "A GUI"
TEA = {"base_id": "milk_tea", "addon_ids": ["pearl"], "size": "M", "temperature": "ICED",
       "sugar": "HALF"}


@pytest.fixture
def system(clock):
    return build(clock=clock, machine_job_ms=JOB_MS)


@pytest.fixture
def client(system):
    return create_app(system).test_client()


def error_code(resp):
    return resp.get_json()["error"]["code"]


class TestCustomer:
    def test_pages(self, client):
        assert client.get("/").status_code == 200
        assert client.get("/admin").status_code == 200

    def test_menu(self, client):
        m = client.get("/api/menu").get_json()
        assert m["bases"][0]["item"]["id"] == "milk_tea"
        assert m["bases"][0]["item"]["kind"] == "BASE"
        assert m["bases"][0]["available"] is True
        assert m["addons"][2] == {"item": m["addons"][2]["item"], "available": False}
        assert m["sizes"] == ["M", "L"] and m["sugars"][0] == "NONE"
        assert m["size_extra_fen"] == {"M": 0, "L": 300}
        assert m["default_recipe"] == {"base_id": "milk_tea", "addon_ids": [], "size": "M",
                                       "temperature": "ICED", "sugar": "HALF"}

    def test_recommendations(self, client):
        recs = client.get("/api/recommendations?limit=2").get_json()
        assert len(recs) == 2 and set(recs[0]) == {"base_id", "addon_ids", "size",
                                                   "temperature", "sugar"}

    def test_quote(self, client):
        q = client.post("/api/quotes", json=TEA).get_json()
        assert q == {"lines": [{"label": "经典奶茶", "price_fen": 1200},
                               {"label": "黑糖珍珠", "price_fen": 200}], "total_fen": 1400}

    def test_quote_defaults(self, client):
        assert client.post("/api/quotes", json={"base_id": "jasmine"}).get_json()["total_fen"] == 800

    def test_full_order_flow(self, client, clock):
        r = client.post("/api/orders", json=TEA)
        assert r.status_code == 201
        o = r.get_json()
        assert o["status"] == "AWAITING_PAYMENT" and o["total_fen"] == 1400
        assert o["payment"]["qr_content"] and o["payment"]["status"] == "WAITING"
        oid = o["order_id"]

        assert client.get(f"/api/orders/{oid}").get_json()["status"] == "AWAITING_PAYMENT"
        assert client.post(f"/api/dev/payments/{oid}/succeed").get_json()["status"] == "MAKING"
        p = client.get(f"/api/orders/{oid}/progress").get_json()
        assert p["state"] == "RUNNING" and 0 <= p["progress"] <= 100 and p["step"]
        clock.advance(JOB_MS)
        assert client.get(f"/api/orders/{oid}").get_json()["status"] == "COMPLETED"
        assert client.get(f"/api/orders/{oid}/progress").get_json()["progress"] == 100

    def test_cancel(self, client):
        oid = client.post("/api/orders", json=TEA).get_json()["order_id"]
        assert client.post(f"/api/orders/{oid}/cancel").get_json()["status"] == "CANCELLED"
        r = client.post(f"/api/orders/{oid}/cancel")
        assert (r.status_code, error_code(r)) == (409, "INVALID_STATE")

    def test_config(self, client, system):
        assert client.get("/api/config").get_json() == {
            "demo": True, "machine_id": "M001", "payment_method": "mock",
            "pay_base_url": "http://localhost"}
        assert create_app(system, demo=False).test_client().get("/api/config").get_json()["demo"] is False

    def test_config_public_url(self, system):
        client = create_app(system, public_url="http://192.168.1.5:3000").test_client()
        assert client.get("/api/config").get_json()["pay_base_url"] == "http://192.168.1.5:3000"

    def test_qr_svg(self, client):
        r = client.get("/api/qr.svg?text=http://192.168.1.5:3000/pay/M001-1")
        assert r.status_code == 200 and r.mimetype == "image/svg+xml" and b"<svg" in r.data
        assert error_code(client.get("/api/qr.svg")) == "INVALID_ARGUMENT"

    def test_demo_cashier_page(self, client):
        assert client.get("/pay/M001-1").status_code == 200

    def test_machine(self, client):
        assert client.get("/api/machine").get_json() == {
            "machine_id": "M001", "online": True, "busy": False, "faults": []}


class TestErrors:
    @pytest.mark.parametrize("payload, status, code", [
        (None, 400, "INVALID_ARGUMENT"),
        ({"addon_ids": []}, 400, "INVALID_ARGUMENT"),
        ({"base_id": "milk_tea", "size": "XL"}, 400, "INVALID_ARGUMENT"),
        ({"base_id": "milk_tea", "addon_ids": "pearl"}, 400, "INVALID_ARGUMENT"),
        ({"base_id": "cola"}, 400, "INVALID_RECIPE"),
        ({"base_id": "milk_tea", "addon_ids": ["coconut"]}, 409, "OUT_OF_STOCK"),
    ])
    def test_create_order_errors(self, client, payload, status, code):
        r = client.post("/api/orders", json=payload) if payload is not None else \
            client.post("/api/orders", data="not json", content_type="application/json")
        assert (r.status_code, error_code(r)) == (status, code)
        assert r.get_json()["error"]["message"]

    def test_out_of_stock_details(self, client):
        r = client.post("/api/orders", json={"base_id": "milk_tea", "addon_ids": ["coconut"]})
        assert r.get_json()["error"]["details"] == {"missing": ["coconut"]}

    def test_unknown_order(self, client):
        r = client.get("/api/orders/nope")
        assert (r.status_code, error_code(r)) == (404, "NOT_FOUND")

    def test_unknown_url(self, client):
        assert error_code(client.get("/api/nothing")) == "NOT_FOUND"

    def test_machine_down(self, client):
        client.post("/api/dev/machine/faults", json={"code": "PUMP_ERROR"})
        r = client.post("/api/orders", json=TEA)
        assert (r.status_code, error_code(r)) == (503, "MACHINE_UNAVAILABLE")

    def test_bad_query_param(self, client):
        assert error_code(client.get("/api/admin/stats?since_ms=abc")) == "INVALID_ARGUMENT"


class TestAdmin:
    def test_stock(self, client):
        rows = client.get("/api/admin/stock").get_json()
        pudding = next(r for r in rows if r["material"]["id"] == "pudding")
        assert pudding == {"material": pudding["material"], "quantity": 150, "status": "LOW"}
        assert pudding["material"]["unit"] == "g"

    def test_restock(self, client):
        r = client.post("/api/admin/restock",
                        json={"material_id": "coconut", "quantity": 500, "operator": "小王"})
        assert r.get_json()["quantity"] == 500 and r.get_json()["status"] == "OK"
        [rec] = client.get("/api/admin/restocks").get_json()
        assert (rec["material_id"], rec["quantity"], rec["operator"]) == ("coconut", 500, "小王")

    def test_restock_errors(self, client):
        r = client.post("/api/admin/restock", json={"material_id": "coconut", "quantity": 99999,
                                                    "operator": "小王"})
        assert (r.status_code, error_code(r)) == (400, "INVALID_ARGUMENT")
        r = client.post("/api/admin/restock", json={"material_id": "gold", "quantity": 1,
                                                    "operator": "小王"})
        assert (r.status_code, error_code(r)) == (404, "NOT_FOUND")

    def test_failed_order_refund_and_clear_fault(self, client):
        oid = client.post("/api/orders", json=TEA).get_json()["order_id"]
        client.post(f"/api/dev/payments/{oid}/succeed")
        assert client.post("/api/dev/machine/faults", json={"code": "CUP_JAM"}).get_json()["online"] is False
        failed = client.get("/api/admin/orders?status=PRODUCTION_FAILED").get_json()
        assert [o["order_id"] for o in failed] == [oid]
        assert "CUP_JAM" in failed[0]["failure_reason"]
        r = client.post(f"/api/admin/orders/{oid}/refund", json={"operator": "小王"})
        assert r.get_json()["status"] == "REFUNDED"
        s = client.post("/api/admin/machine/clear-fault", json={}).get_json()
        assert s["online"] is True and s["faults"] == []

    def test_bad_status_filter(self, client):
        assert error_code(client.get("/api/admin/orders?status=WHATEVER")) == "INVALID_ARGUMENT"

    def test_stats(self, client, clock):
        oid = client.post("/api/orders", json=TEA).get_json()["order_id"]
        client.post(f"/api/dev/payments/{oid}/succeed")
        clock.advance(JOB_MS)
        client.get(f"/api/orders/{oid}")
        s = client.get("/api/admin/stats?machine_id=M001").get_json()
        assert (s["order_count"], s["revenue_fen"], s["machine_id"]) == (1, 1400, "M001")
        assert s["top_combos"][0]["label"] == "经典奶茶 + 黑糖珍珠"
        assert set(s) >= {"by_hour", "by_sugar", "since_ms", "until_ms"}


def test_demo_endpoints_can_be_disabled(system):
    client = create_app(system, demo=False).test_client()
    assert client.post("/api/dev/machine/faults", json={"code": "CUP_JAM"}).status_code == 404
