#!/usr/bin/env python3
"""
SGarden API test suite
Usage: python test_api.py [base_url]
Default: http://localhost:4000
"""
import json
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4000").rstrip("/")

_pass = 0
_fail = 0
_cleanup_products: list[str] = []
_cleanup_orders: list[str] = []


# ── HTTP ──────────────────────────────────────────────────────────────────────

def req(method, path, body=None, token=None, **qs):
    url = BASE_URL + path
    if qs:
        url += "?" + urlencode({k: v for k, v in qs.items() if v is not None})
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


# ── Assertions ────────────────────────────────────────────────────────────────

def check(name, condition, info=""):
    global _pass, _fail
    mark = "✓" if condition else "✗"
    note = f"  ← {info}" if info and not condition else ""
    print(f"  {mark} {name}{note}")
    if condition:
        _pass += 1
    else:
        _fail += 1


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── Auth ──────────────────────────────────────────────────────────────────────

def login(username, password):
    _, d = req("POST", "/api/auth/login", {"username": username, "password": password})
    return d.get("token")


# ── Test groups ───────────────────────────────────────────────────────────────

def test_product_search(token):
    section("Product Search")

    status, data = req("GET", "/api/products/search", q="mouse")
    check("GET /search?q=mouse returns 200", status == 200)
    check("Result is an array", isinstance(data, list))
    if isinstance(data, list) and data:
        hits = [p for p in data if
                "mouse" in (p.get("name") or "").lower() or
                "mouse" in (p.get("description") or "").lower()]
        check("All results contain 'mouse' in name or description",
              len(hits) == len(data), f"{len(hits)}/{len(data)}")

    status, data = req("GET", "/api/products/search", category="Electronics")
    check("GET /search?category=Electronics returns 200", status == 200)
    if isinstance(data, list) and data:
        wrong = [p for p in data if p.get("category") != "Electronics"]
        check("All results have category Electronics", not wrong, f"{len(wrong)} wrong")

    status, data = req("GET", "/api/products/search", minPrice=50)
    check("GET /search?minPrice=50 returns 200", status == 200)
    if isinstance(data, list) and data:
        cheap = [p for p in data if (p.get("price") or 0) < 50]
        check("All results have price >= 50", not cheap, f"{len(cheap)} below 50")

    status, data = req("GET", "/api/products/search", maxPrice=20)
    check("GET /search?maxPrice=20 returns 200", status == 200)
    if isinstance(data, list) and data:
        expensive = [p for p in data if (p.get("price") or 0) > 20]
        check("All results have price <= 20", not expensive, f"{len(expensive)} above 20")

    # USB-C Hub ($45.99) and USB Flash Drive ($12.99) both match
    status, data = req("GET", "/api/products/search", q="USB", minPrice=10, maxPrice=50)
    check("GET /search?q=USB&minPrice=10&maxPrice=50 returns 200", status == 200)
    if isinstance(data, list):
        wrong = [p for p in data if not (10 <= (p.get("price") or 0) <= 50)]
        check("Combined filter: all results within price range", not wrong, f"{len(wrong)} out of range")

    status, data = req("GET", "/api/products/search", q="nonexistentxyz")
    check("GET /search?q=nonexistentxyz returns empty array", status == 200 and data == [])


def test_product_stats(token):
    section("Product Stats")

    status, data = req("GET", "/api/products/stats")
    check("GET /api/products/stats returns 200", status == 200)
    check("totalCount is a number > 0",
          isinstance(data.get("totalCount"), (int, float)) and data.get("totalCount", 0) > 0)
    check("averagePrice is a positive number",
          isinstance(data.get("averagePrice"), (int, float)) and data.get("averagePrice", 0) > 0)

    mn, mx = data.get("minPrice"), data.get("maxPrice")
    check("minPrice and maxPrice are present", mn is not None and mx is not None)
    check("maxPrice >= minPrice", mx is not None and mn is not None and mx >= mn)

    cat = data.get("categoryCount")
    check("categoryCount is an object", isinstance(cat, dict))
    if isinstance(cat, dict):
        check("Sum of categoryCount equals totalCount",
              sum(cat.values()) == data.get("totalCount", -1),
              f"{sum(cat.values())} != {data.get('totalCount')}")


def test_product_pagination(token):
    section("Product Pagination & Sorting")

    status, data = req("GET", "/api/products", page=1, limit=5)
    check("GET /products?page=1&limit=5 returns 200", status == 200)
    check("Response has data, page, limit, total",
          all(k in data for k in ("data", "page", "limit", "total")))
    check("page=1 echoed in response", data.get("page") == 1)
    check("limit=5 echoed in response", data.get("limit") == 5)
    check("total > len(data) when limit is small",
          data.get("total", 0) > len(data.get("data", [])))

    _, p1 = req("GET", "/api/products", page=1, limit=5)
    _, p2 = req("GET", "/api/products", page=2, limit=5)
    ids1 = {p["id"] for p in p1.get("data", [])}
    ids2 = {p["id"] for p in p2.get("data", [])}
    check("Page 1 and page 2 return non-overlapping IDs",
          ids1.isdisjoint(ids2), f"overlap: {ids1 & ids2}")

    _, data = req("GET", "/api/products", page=1, limit=20, sort="price", order="asc")
    prices = [p["price"] for p in data.get("data", []) if p.get("price") is not None]
    check("Sort price asc: non-decreasing", prices == sorted(prices), str(prices[:5]))

    _, data = req("GET", "/api/products", page=1, limit=20, sort="price", order="desc")
    prices = [p["price"] for p in data.get("data", []) if p.get("price") is not None]
    check("Sort price desc: non-increasing", prices == sorted(prices, reverse=True), str(prices[:5]))

    _, data = req("GET", "/api/products", page=1, limit=20, sort="name", order="asc")
    names = [p["name"] for p in data.get("data", []) if p.get("name")]
    check("Sort name asc: lexicographic order", names == sorted(names), str(names[:3]))

    status, data = req("GET", "/api/products", page=999, limit=10)
    check("page=999 returns 200 with empty data array", status == 200 and data.get("data") == [])


def test_product_validation(token):
    section("Product Validation")

    status, data = req("POST", "/api/products", {"price": 10.0}, token=token)
    check("POST without name returns 400", status == 400)
    errors = (data.get("detail") or {}).get("errors", {})
    check("errors.name present", "name" in errors)

    status, data = req("POST", "/api/products", {"name": "X", "price": -5}, token=token)
    check("POST with negative price returns 400", status == 400)
    errors = (data.get("detail") or {}).get("errors", {})
    check("errors.price present for negative", "price" in errors)

    status, data = req("POST", "/api/products", {"name": "X", "price": 0}, token=token)
    check("POST with price=0 returns 400", status == 400)
    errors = (data.get("detail") or {}).get("errors", {})
    check("errors.price present for zero", "price" in errors)

    status, data = req("POST", "/api/products",
                       {"name": "X", "price": 10, "category": "Widgets"}, token=token)
    check("POST with invalid category returns 400", status == 400)
    errors = (data.get("detail") or {}).get("errors", {})
    check("errors.category present", "category" in errors)

    status, data = req("POST", "/api/products",
                       {"name": "__test_valid__", "price": 19.99,
                        "category": "Electronics", "stock": 5}, token=token)
    check("POST with all valid fields returns 201", status == 201)
    if status == 201 and data.get("id"):
        _cleanup_products.append(data["id"])

    # Use the first seed product for PUT validation
    _, listing = req("GET", "/api/products", page=1, limit=1)
    pid = (listing.get("data") or [{}])[0].get("id")
    if pid:
        status, data = req("PUT", f"/api/products/{pid}", {"price": -1}, token=token)
        check("PUT with negative price returns 400", status == 400)
        errors = (data.get("detail") or {}).get("errors", {})
        check("errors object has string values",
              isinstance(errors, dict) and all(isinstance(v, str) for v in errors.values()))

    status, _ = req("PUT", "/api/products/000000000000000000000000",
                    {"name": "X"}, token=token)
    check("PUT /products/000...000 returns 404", status == 404)


def test_orders_crud(token):
    section("Orders CRUD")

    # Dedicated product so stock is predictable
    _, product = req("POST", "/api/products",
                     {"name": "__test_orders__", "price": 20.00,
                      "category": "Electronics", "stock": 50}, token=token)
    pid = product.get("id")
    if pid:
        _cleanup_products.append(pid)
    price = product.get("price", 20.00)

    status, order = req("POST", "/api/orders",
                        {"items": [{"productId": pid, "quantity": 2}]}, token=token)
    check("POST /api/orders returns 201", status == 201)
    check("Order has id and items", "id" in order and "items" in order)
    oid = order.get("id")
    check(f"Order total = {price} × 2 = {round(price * 2, 2)}",
          round(order.get("total", 0), 2) == round(price * 2, 2))
    if oid:
        _cleanup_orders.append(oid)

    status, data = req("GET", "/api/orders", token=token)
    check("GET /api/orders returns 200 with array", status == 200 and isinstance(data, list))

    status, data = req("GET", f"/api/orders/{oid}", token=token)
    check("GET /api/orders/:id returns matching order", status == 200 and data.get("id") == oid)
    check("Order has items and total", "items" in data and "total" in data)

    status, data = req("PUT", f"/api/orders/{oid}",
                       {"items": [{"productId": pid, "quantity": 3}]}, token=token)
    check("PUT /api/orders/:id recalculates total",
          status == 200 and round(data.get("total", 0), 2) == round(price * 3, 2))

    status, _ = req("GET", "/api/orders/000000000000000000000000", token=token)
    check("GET /orders/000...000 returns 404", status == 404)

    status, _ = req("DELETE", f"/api/orders/{oid}", token=token)
    check("DELETE /api/orders/:id returns 200", status == 200)
    status, _ = req("GET", f"/api/orders/{oid}", token=token)
    check("Subsequent GET after DELETE returns 404", status == 404)
    if oid in _cleanup_orders:
        _cleanup_orders.remove(oid)

    status, _ = req("POST", "/api/orders", {"items": [{"productId": pid, "quantity": 1}]})
    check("POST /api/orders without auth returns 401/403", status in (401, 403))


def test_stock_management(token):
    section("Stock Management")

    status, product = req("POST", "/api/products",
                          {"name": "__test_stock__", "price": 10.00,
                           "category": "Accessories", "stock": 100}, token=token)
    check("POST /api/products with stock field returns 201", status == 201)
    check("Created product has stock=100", product.get("stock") == 100)
    pid = product.get("id")
    if pid:
        _cleanup_products.append(pid)

    _, p = req("GET", f"/api/products/{pid}")
    check("GET /api/products/:id includes stock as number",
          isinstance(p.get("stock"), (int, float)))

    status, data = req("PATCH", f"/api/products/{pid}/stock", {"stock": 75}, token=token)
    check("PATCH /:id/stock { stock: 75 } returns 200", status == 200)
    check("Stock updated to 75", data.get("stock") == 75)

    status, _ = req("PATCH", f"/api/products/{pid}/stock", {"stock": -10}, token=token)
    check("PATCH /:id/stock { stock: -10 } returns 400", status == 400)

    status, _ = req("PATCH", f"/api/products/{pid}/stock", {"stock": 50})
    check("PATCH /:id/stock without auth returns 401/403", status in (401, 403))

    _, p_before = req("GET", f"/api/products/{pid}")
    stock_before = p_before.get("stock")  # 75
    status, order = req("POST", "/api/orders",
                        {"items": [{"productId": pid, "quantity": 5}]}, token=token)
    check("Order placement returns 201", status == 201)
    oid = order.get("id")
    if oid:
        _cleanup_orders.append(oid)
    _, p_after = req("GET", f"/api/products/{pid}")
    check("Order reduces stock by ordered quantity",
          p_after.get("stock") == stock_before - 5,
          f"{p_after.get('stock')} != {stock_before - 5}")

    stock_now = p_after.get("stock", 0)
    status, _ = req("POST", "/api/orders",
                    {"items": [{"productId": pid, "quantity": stock_now + 999}]}, token=token)
    check("Order with quantity > stock returns 400", status == 400)
    _, p_check = req("GET", f"/api/products/{pid}")
    check("Stock unchanged after rejected order",
          p_check.get("stock") == stock_now, f"{p_check.get('stock')} != {stock_now}")


def test_alerts(token):
    section("Alerts")

    status, data = req("PUT", "/api/alerts/threshold", {"threshold": 25}, token=token)
    check("PUT /api/alerts/threshold { threshold: 25 } returns 200", status == 200)
    check("Response has threshold=25", data.get("threshold") == 25)

    status, alerts = req("GET", "/api/alerts", token=token)
    check("GET /api/alerts returns 200 with array",
          status == 200 and isinstance(alerts, list))

    if isinstance(alerts, list):
        check("Alerts list is non-empty (seed has low-stock items)", len(alerts) > 0)

        bad_sev = [a for a in alerts if a.get("severity") not in {"critical", "warning", "info"}]
        check("Each alert severity is critical/warning/info", not bad_sev,
              f"{len(bad_sev)} invalid")

        missing = [a for a in alerts if not a.get("productName") or "stock" not in a]
        check("Each alert has productName and stock", not missing)

        above = [a for a in alerts if (a.get("stock") or 0) >= 25]
        check("No alert has stock >= threshold (25)", not above, f"{len(above)} above threshold")

    status, _ = req("GET", "/api/alerts")
    check("GET /api/alerts without auth returns 401/403", status in (401, 403))


def test_order_status(token):
    section("Order Status Workflow")

    _, product = req("POST", "/api/products",
                     {"name": "__test_status__", "price": 5.00,
                      "category": "Accessories", "stock": 20}, token=token)
    pid = product.get("id")
    if pid:
        _cleanup_products.append(pid)

    def new_order():
        _, o = req("POST", "/api/orders",
                   {"items": [{"productId": pid, "quantity": 1}]}, token=token)
        oid = o.get("id")
        if oid:
            _cleanup_orders.append(oid)
        return oid

    def patch_status(oid, new_status):
        return req("PATCH", f"/api/orders/{oid}/status", {"status": new_status}, token=token)

    oid = new_order()
    _, order = req("GET", f"/api/orders/{oid}", token=token)
    check("New order has status 'pending'", order.get("status") == "pending")

    status, data = patch_status(oid, "confirmed")
    check("pending -> confirmed returns 200", status == 200)
    check("Status is now 'confirmed'", data.get("status") == "confirmed")

    status, _ = patch_status(oid, "delivered")
    check("pending -> shipped (skipping confirmed) returns 400", status == 400)

    status, _ = patch_status(oid, "shipped")
    check("confirmed -> shipped returns 200", status == 200)

    status, data = patch_status(oid, "delivered")
    check("shipped -> delivered returns 200", status == 200)
    check("Full workflow: final status is 'delivered'", data.get("status") == "delivered")

    status, _ = patch_status(oid, "pending")
    check("Delivered order status change returns 400", status == 400)

    oid2 = new_order()
    status, data = patch_status(oid2, "cancelled")
    check("Cancelling pending order returns 200", status == 200)
    check("Status is 'cancelled'", data.get("status") == "cancelled")

    oid3 = new_order()
    patch_status(oid3, "confirmed")
    patch_status(oid3, "shipped")
    status, _ = patch_status(oid3, "cancelled")
    check("Cancelling shipped order returns 400", status == 400)

    _, pending_orders = req("GET", "/api/orders", token=token, status="pending")
    wrong = [o for o in pending_orders if o.get("status") != "pending"]
    check("GET /api/orders?status=pending returns only pending",
          not wrong, f"{len(wrong)} non-pending")


def test_analytics(token):
    section("Sales Analytics")

    status, data = req("GET", "/api/analytics/sales", token=token)
    check("GET /api/analytics/sales returns 200", status == 200)
    check("totalRevenue is a number > 0",
          isinstance(data.get("totalRevenue"), (int, float)) and data.get("totalRevenue", 0) > 0)
    check("totalOrders is a number > 0",
          isinstance(data.get("totalOrders"), (int, float)) and data.get("totalOrders", 0) > 0)

    tp = data.get("topProducts")
    check("topProducts is an array", isinstance(tp, list))
    if isinstance(tp, list) and tp:
        item = tp[0]
        check("topProducts items have productId and productName",
              "productId" in item and "productName" in item)
        check("topProducts items have totalQuantity and totalRevenue",
              "totalQuantity" in item and "totalRevenue" in item)

    rbp = data.get("revenueByPeriod")
    check("revenueByPeriod is an array or object", isinstance(rbp, (list, dict)))

    status, data = req("GET", "/api/analytics/sales", token=token,
                       startDate="2024-01-01", endDate="2024-12-31")
    check("Date range filter returns 200", status == 200)
    check("Response includes totalRevenue field", "totalRevenue" in data)

    status, data = req("GET", "/api/analytics/sales", token=token,
                       startDate="2099-01-01", endDate="2099-12-31")
    check("Future date range returns totalRevenue=0 and totalOrders=0",
          status == 200 and data.get("totalRevenue") == 0 and data.get("totalOrders") == 0)

    status, _ = req("GET", "/api/analytics/sales")
    check("GET /analytics/sales without auth returns 401/403", status in (401, 403))


# ── Cleanup ───────────────────────────────────────────────────────────────────

def cleanup(token):
    for oid in list(_cleanup_orders):
        req("DELETE", f"/api/orders/{oid}", token=token)
    for pid in list(_cleanup_products):
        req("DELETE", f"/api/products/{pid}", token=token)


def pre_cleanup(token):
    """Remove any __test_* products left over from previous runs."""
    page = 1
    while True:
        _, data = req("GET", "/api/products", page=page, limit=100)
        products = data.get("data", [])
        if not products:
            break
        for p in products:
            if (p.get("name") or "").startswith("__test_"):
                req("DELETE", f"/api/products/{p['id']}", token=token)
        if len(products) < 100:
            break
        page += 1


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'═' * 60}")
    print(f"  SGarden API Test Suite")
    print(f"  Target: {BASE_URL}")
    print(f"{'═' * 60}")

    try:
        status, _ = req("GET", "/api/health")
        if status != 200:
            print("✗ Server health check failed")
            sys.exit(1)
        print("\n  ✓ Server reachable")
    except Exception as e:
        print(f"✗ Cannot connect to {BASE_URL}: {e}")
        sys.exit(1)

    token = login("admin", "admin123")
    if not token:
        print("✗ Could not log in as admin")
        sys.exit(1)
    print("  ✓ Auth tokens acquired")
    pre_cleanup(token)
    print("  ✓ Pre-test cleanup done")

    try:
        test_product_search(token)
        test_product_stats(token)
        test_product_pagination(token)
        test_product_validation(token)
        test_orders_crud(token)
        test_stock_management(token)
        test_alerts(token)
        test_order_status(token)
        test_analytics(token)
    finally:
        cleanup(token)

    total = _pass + _fail
    print(f"\n{'═' * 60}")
    if _fail == 0:
        print(f"  ✓ All {total} tests passed")
    else:
        print(f"  {_pass}/{total} passed  ({_fail} failed)")
    print(f"{'═' * 60}\n")
    sys.exit(0 if _fail == 0 else 1)


if __name__ == "__main__":
    main()
