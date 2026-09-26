"""Inventory rules. Every posted movement and its stock update share one transaction."""

import sqlite3

from .database import milli, money_cents, quantity, transaction


class InventoryError(ValueError):
    pass


def required(data, key, label=None):
    value = str(data.get(key, "")).strip()
    if not value:
        raise InventoryError(f"{label or key.replace('_', ' ').title()} is required")
    return value


def exists(db, table, item_id):
    # All callers pass a fixed table name, never request data.
    row = db.execute(f"SELECT id FROM {table} WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise InventoryError(f"{table[:-1].title()} not found")
    return item_id


def create_warehouse(db, data):
    name = required(data, "name")
    code = required(data, "code").upper()
    with transaction(db):
        cursor = db.execute(
            "INSERT INTO warehouses(name, code, address) VALUES (?, ?, ?)",
            (name, code, str(data.get("address", "")).strip()),
        )
        db.execute(
            "INSERT INTO locations(warehouse_id, name, code) VALUES (?, 'Main stock', 'MAIN')",
            (cursor.lastrowid,),
        )
    return cursor.lastrowid


def create_location(db, data):
    warehouse_id = exists(db, "warehouses", int(data.get("warehouse_id") or 0))
    with transaction(db):
        cursor = db.execute(
            "INSERT INTO locations(warehouse_id, name, code) VALUES (?, ?, ?)",
            (warehouse_id, required(data, "name"), required(data, "code").upper()),
        )
    return cursor.lastrowid


def update_warehouse(db, warehouse_id, data):
    exists(db, "warehouses", warehouse_id)
    with transaction(db):
        db.execute(
            "UPDATE warehouses SET name=?, code=?, address=? WHERE id=?",
            (
                required(data, "name"),
                required(data, "code").upper(),
                str(data.get("address", "")).strip(),
                warehouse_id,
            ),
        )


def update_location(db, location_id, data):
    exists(db, "locations", location_id)
    with transaction(db):
        db.execute(
            "UPDATE locations SET name=?, code=? WHERE id=?",
            (required(data, "name"), required(data, "code").upper(), location_id),
        )


def create_category(db, data):
    with transaction(db):
        cursor = db.execute(
            "INSERT INTO categories(name) VALUES (?)", (required(data, "name"),)
        )
    return cursor.lastrowid


def create_product(db, data):
    category_id = int(data["category_id"]) if data.get("category_id") else None
    if category_id:
        exists(db, "categories", category_id)
    opening = milli(data.get("initial_stock", 0), allow_zero=True)
    opening_location = (
        _location(db, data.get("initial_location_id")) if opening else None
    )
    with transaction(db):
        cursor = db.execute(
            """INSERT INTO products(sku, name, category_id, uom, unit_cost_cents, reorder_milli)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                required(data, "sku").upper(),
                required(data, "name"),
                category_id,
                required(data, "uom"),
                money_cents(data.get("unit_cost", 0)),
                milli(data.get("reorder_point", 0), allow_zero=True),
            ),
        )
        if opening:
            product_id = cursor.lastrowid
            operation = db.execute(
                """INSERT INTO operations(reference,type,status,from_location_id,note)
                VALUES ('PENDING','adjustment','done',?,'Opening stock')""",
                (opening_location,),
            )
            operation_id = operation.lastrowid
            db.execute(
                "UPDATE operations SET reference=? WHERE id=?",
                (f"ADJ/{operation_id:05d}", operation_id),
            )
            db.execute(
                "INSERT INTO operation_lines(operation_id,product_id,quantity_milli) VALUES (?,?,?)",
                (operation_id, product_id, opening),
            )
            _apply(db, operation_id, product_id, opening_location, opening)
    return cursor.lastrowid


def update_product(db, product_id, data):
    exists(db, "products", product_id)
    category_id = int(data["category_id"]) if data.get("category_id") else None
    if category_id:
        exists(db, "categories", category_id)
    with transaction(db):
        db.execute(
            """UPDATE products SET sku=?, name=?, category_id=?, uom=?,
               unit_cost_cents=?, reorder_milli=?, active=? WHERE id=?""",
            (
                required(data, "sku").upper(),
                required(data, "name"),
                category_id,
                required(data, "uom"),
                money_cents(data.get("unit_cost", 0)),
                milli(data.get("reorder_point", 0), allow_zero=True),
                1 if data.get("active", True) else 0,
                product_id,
            ),
        )


def list_products(db, search="", category_id=None):
    query = """SELECT p.*, c.name category,
        COALESCE(SUM(s.quantity_milli), 0) on_hand_milli
        FROM products p LEFT JOIN categories c ON c.id=p.category_id
        LEFT JOIN stock_levels s ON s.product_id=p.id
        WHERE (p.sku LIKE ? OR p.name LIKE ?)"""
    term = f"%{search.strip()}%"
    params = [term, term]
    if category_id:
        query += " AND p.category_id=?"
        params.append(category_id)
    query += " GROUP BY p.id ORDER BY p.name"
    result = []
    for row in db.execute(query, params):
        item = dict(row)
        item["on_hand"] = quantity(item.pop("on_hand_milli"))
        item["reorder_point"] = quantity(item.pop("reorder_milli"))
        item["unit_cost"] = item.pop("unit_cost_cents") / 100
        item["low_stock"] = item["on_hand"] <= item["reorder_point"]
        result.append(item)
    return result


def stock(db, search="", warehouse_id=None, category_id=None):
    query = """SELECT p.id product_id, p.sku, p.name product, p.uom, p.unit_cost_cents,
        p.reorder_milli, c.name category, w.id warehouse_id, w.name warehouse,
        l.id location_id, l.name location, l.code location_code,
        COALESCE(s.quantity_milli, 0) quantity_milli
        FROM products p CROSS JOIN locations l
        JOIN warehouses w ON w.id=l.warehouse_id
        LEFT JOIN categories c ON c.id=p.category_id
        LEFT JOIN stock_levels s ON s.product_id=p.id AND s.location_id=l.id
        WHERE p.active=1 AND (p.sku LIKE ? OR p.name LIKE ?)"""
    params = [f"%{search.strip()}%"] * 2
    if warehouse_id:
        query += " AND w.id=?"
        params.append(warehouse_id)
    if category_id:
        query += " AND p.category_id=?"
        params.append(category_id)
    query += " ORDER BY p.name, w.name, l.name"
    items = []
    for row in db.execute(query, params):
        item = dict(row)
        item["quantity"] = quantity(item.pop("quantity_milli"))
        item["reorder_point"] = quantity(item.pop("reorder_milli"))
        item["unit_cost"] = item.pop("unit_cost_cents") / 100
        items.append(item)
    return items


def _location(db, value):
    return exists(db, "locations", int(value or 0))


def create_operation(db, data, user_id):
    kind = data.get("type")
    if kind not in ("receipt", "delivery", "transfer", "adjustment"):
        raise InventoryError("Choose a valid operation type")
    source = (
        _location(db, data.get("from_location_id"))
        if kind in ("delivery", "transfer", "adjustment")
        else None
    )
    destination = (
        _location(db, data.get("to_location_id"))
        if kind in ("receipt", "transfer")
        else None
    )
    if kind == "transfer" and source == destination:
        raise InventoryError("Choose two different locations for a transfer")
    lines = data.get("lines")
    if not isinstance(lines, list) or not lines:
        raise InventoryError("Add at least one product")
    parsed = []
    seen = set()
    for line in lines:
        product_id = exists(db, "products", int(line.get("product_id") or 0))
        if product_id in seen:
            raise InventoryError("Add each product only once")
        seen.add(product_id)
        parsed.append(
            (product_id, milli(line.get("quantity"), allow_zero=kind == "adjustment"))
        )
    with transaction(db):
        cursor = db.execute(
            """INSERT INTO operations(reference,type,from_location_id,to_location_id,
               partner,scheduled_date,responsible_id,note)
               VALUES ('PENDING',?,?,?,?,?,?,?)""",
            (
                kind,
                source,
                destination,
                str(data.get("partner", "")).strip(),
                str(data.get("scheduled_date", "")).strip(),
                user_id,
                str(data.get("note", "")).strip(),
            ),
        )
        operation_id = cursor.lastrowid
        prefix = {
            "receipt": "RCV",
            "delivery": "DLV",
            "transfer": "TRF",
            "adjustment": "ADJ",
        }[kind]
        db.execute(
            "UPDATE operations SET reference=? WHERE id=?",
            (f"{prefix}/{operation_id:05d}", operation_id),
        )
        db.executemany(
            "INSERT INTO operation_lines(operation_id,product_id,quantity_milli) VALUES (?,?,?)",
            [(operation_id, product_id, amount) for product_id, amount in parsed],
        )
    return operation_id


def operation_detail(db, operation_id):
    row = db.execute(
        """SELECT o.*, u.name responsible, fl.name from_location, fw.name from_warehouse,
           tl.name to_location, tw.name to_warehouse
           FROM operations o LEFT JOIN users u ON u.id=o.responsible_id
           LEFT JOIN locations fl ON fl.id=o.from_location_id
           LEFT JOIN warehouses fw ON fw.id=fl.warehouse_id
           LEFT JOIN locations tl ON tl.id=o.to_location_id
           LEFT JOIN warehouses tw ON tw.id=tl.warehouse_id
           WHERE o.id=?""",
        (operation_id,),
    ).fetchone()
    if not row:
        raise InventoryError("Operation not found")
    item = dict(row)
    item["lines"] = [
        {
            "id": line["id"],
            "product_id": line["product_id"],
            "sku": line["sku"],
            "product": line["name"],
            "uom": line["uom"],
            "quantity": quantity(line["quantity_milli"]),
        }
        for line in db.execute(
            """SELECT ol.*, p.sku, p.name, p.uom FROM operation_lines ol
            JOIN products p ON p.id=ol.product_id WHERE ol.operation_id=? ORDER BY ol.id""",
            (operation_id,),
        )
    ]
    return item


def list_operations(
    db, kind=None, status=None, search="", warehouse_id=None, category_id=None
):
    query = """SELECT o.id,o.reference,o.type,o.status,o.partner,o.scheduled_date,o.created_at,
        o.from_location_id,o.to_location_id, fl.name from_location, fw.name from_warehouse,
        tl.name to_location, tw.name to_warehouse, u.name responsible,
        COUNT(ol.id) line_count
        FROM operations o LEFT JOIN locations fl ON fl.id=o.from_location_id
        LEFT JOIN warehouses fw ON fw.id=fl.warehouse_id
        LEFT JOIN locations tl ON tl.id=o.to_location_id
        LEFT JOIN warehouses tw ON tw.id=tl.warehouse_id
        LEFT JOIN users u ON u.id=o.responsible_id
        LEFT JOIN operation_lines ol ON ol.operation_id=o.id WHERE 1=1"""
    params = []
    if kind:
        query += " AND o.type=?"
        params.append(kind)
    if status:
        query += " AND o.status=?"
        params.append(status)
    if search:
        query += " AND (o.reference LIKE ? OR o.partner LIKE ?)"
        params.extend([f"%{search}%"] * 2)
    if warehouse_id:
        query += " AND (fw.id=? OR tw.id=?)"
        params.extend([warehouse_id] * 2)
    if category_id:
        query += " AND EXISTS (SELECT 1 FROM operation_lines line JOIN products p ON p.id=line.product_id WHERE line.operation_id=o.id AND p.category_id=?)"
        params.append(category_id)
    query += " GROUP BY o.id ORDER BY o.id DESC"
    return [dict(row) for row in db.execute(query, params)]


def update_operation(db, operation_id, data):
    current = operation_detail(db, operation_id)
    if current["status"] not in ("draft", "waiting"):
        raise InventoryError("Only draft or waiting operations can be edited")
    kind = current["type"]
    source = (
        _location(db, data.get("from_location_id"))
        if kind in ("delivery", "transfer", "adjustment")
        else None
    )
    destination = (
        _location(db, data.get("to_location_id"))
        if kind in ("receipt", "transfer")
        else None
    )
    if kind == "transfer" and source == destination:
        raise InventoryError("Choose two different locations for a transfer")
    lines = data.get("lines")
    if not isinstance(lines, list) or not lines:
        raise InventoryError("Add at least one product")
    parsed = []
    seen = set()
    for line in lines:
        product_id = exists(db, "products", int(line.get("product_id") or 0))
        if product_id in seen:
            raise InventoryError("Add each product only once")
        seen.add(product_id)
        parsed.append(
            (
                operation_id,
                product_id,
                milli(line.get("quantity"), allow_zero=kind == "adjustment"),
            )
        )
    with transaction(db):
        latest = db.execute(
            "SELECT status FROM operations WHERE id=?", (operation_id,)
        ).fetchone()[0]
        if latest not in ("draft", "waiting"):
            raise InventoryError("Only draft or waiting operations can be edited")
        db.execute(
            """UPDATE operations SET from_location_id=?, to_location_id=?, partner=?,
            scheduled_date=?, note=?, updated_at=datetime('now') WHERE id=?""",
            (
                source,
                destination,
                str(data.get("partner", "")).strip(),
                str(data.get("scheduled_date", "")).strip(),
                str(data.get("note", "")).strip(),
                operation_id,
            ),
        )
        db.execute("DELETE FROM operation_lines WHERE operation_id=?", (operation_id,))
        db.executemany(
            "INSERT INTO operation_lines(operation_id,product_id,quantity_milli) VALUES (?,?,?)",
            parsed,
        )


def set_status(db, operation_id, action):
    with transaction(db):
        item = operation_detail(db, operation_id)
        status = item["status"]
        next_status = {
            ("draft", "submit"): "waiting",
            ("waiting", "ready"): "ready",
            ("draft", "ready"): "ready",
            ("draft", "cancel"): "canceled",
            ("waiting", "cancel"): "canceled",
            ("ready", "cancel"): "canceled",
        }.get((status, action))
        if (
            action in ("pick", "pack")
            and item["type"] == "delivery"
            and status in ("waiting", "ready")
        ):
            if action == "pack" and not item["picked"]:
                raise InventoryError("Pick the items before packing")
            db.execute(
                f"UPDATE operations SET {'picked' if action == 'pick' else 'packed'}=1, updated_at=datetime('now') WHERE id=?",
                (operation_id,),
            )
            return
        if not next_status:
            raise InventoryError(f"Cannot {action} an operation in {status} status")
        if next_status == "ready" and item["type"] == "delivery" and not item["packed"]:
            raise InventoryError("Pick and pack the delivery before marking it ready")
        db.execute(
            "UPDATE operations SET status=?, updated_at=datetime('now') WHERE id=?",
            (next_status, operation_id),
        )


def _apply(db, operation_id, product_id, location_id, delta):
    row = db.execute(
        "SELECT quantity_milli FROM stock_levels WHERE product_id=? AND location_id=?",
        (product_id, location_id),
    ).fetchone()
    current = row[0] if row else 0
    balance = current + delta
    if balance < 0:
        product = db.execute(
            "SELECT sku FROM products WHERE id=?", (product_id,)
        ).fetchone()[0]
        raise InventoryError(f"Not enough {product} at the selected location")
    db.execute(
        """INSERT INTO stock_levels(product_id,location_id,quantity_milli)
        VALUES (?,?,?) ON CONFLICT(product_id,location_id)
        DO UPDATE SET quantity_milli=excluded.quantity_milli""",
        (product_id, location_id, balance),
    )
    db.execute(
        """INSERT INTO movements(operation_id,product_id,location_id,delta_milli,balance_milli)
        VALUES (?,?,?,?,?)""",
        (operation_id, product_id, location_id, delta, balance),
    )


def validate_operation(db, operation_id):
    with transaction(db):
        item = operation_detail(db, operation_id)
        if item["status"] != "ready":
            raise InventoryError("Mark the operation ready before validation")
        for line in item["lines"]:
            product_id = line["product_id"]
            amount = milli(line["quantity"], allow_zero=item["type"] == "adjustment")
            if item["type"] == "receipt":
                _apply(db, operation_id, product_id, item["to_location_id"], amount)
            elif item["type"] == "delivery":
                _apply(db, operation_id, product_id, item["from_location_id"], -amount)
            elif item["type"] == "transfer":
                _apply(db, operation_id, product_id, item["from_location_id"], -amount)
                _apply(db, operation_id, product_id, item["to_location_id"], amount)
            else:
                row = db.execute(
                    "SELECT quantity_milli FROM stock_levels WHERE product_id=? AND location_id=?",
                    (product_id, item["from_location_id"]),
                ).fetchone()
                current = row[0] if row else 0
                _apply(
                    db,
                    operation_id,
                    product_id,
                    item["from_location_id"],
                    amount - current,
                )
        db.execute(
            "UPDATE operations SET status='done', updated_at=datetime('now') WHERE id=?",
            (operation_id,),
        )


def history(db, search="", warehouse_id=None, product_id=None, limit=100, offset=0):
    query = """SELECT m.id,m.created_at,m.operation_id,m.delta_milli,m.balance_milli,
        o.reference,o.type,o.status,p.id product_id,p.sku,p.name product,p.uom,
        l.id location_id,l.name location,w.id warehouse_id,w.name warehouse
        FROM movements m JOIN operations o ON o.id=m.operation_id
        JOIN products p ON p.id=m.product_id JOIN locations l ON l.id=m.location_id
        JOIN warehouses w ON w.id=l.warehouse_id WHERE 1=1"""
    params = []
    if search:
        query += " AND (o.reference LIKE ? OR p.sku LIKE ? OR p.name LIKE ?)"
        params.extend([f"%{search}%"] * 3)
    if warehouse_id:
        query += " AND w.id=?"
        params.append(warehouse_id)
    if product_id:
        query += " AND p.id=?"
        params.append(product_id)
    query += " ORDER BY m.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = []
    for row in db.execute(query, params):
        item = dict(row)
        item["delta"] = quantity(item.pop("delta_milli"))
        item["balance"] = quantity(item.pop("balance_milli"))
        rows.append(item)
    return rows


def dashboard(db):
    products = list_products(db)
    counts = {
        row["type"]: row["n"]
        for row in db.execute(
            "SELECT type, COUNT(*) n FROM operations WHERE status NOT IN ('done','canceled') GROUP BY type"
        )
    }
    recent = list_operations(db)[:8]
    return {
        "products_in_stock": sum(product["on_hand"] > 0 for product in products),
        "low_stock": sum(
            product["low_stock"] for product in products if product["active"]
        ),
        "pending_receipts": counts.get("receipt", 0),
        "pending_deliveries": counts.get("delivery", 0),
        "scheduled_transfers": counts.get("transfer", 0),
        "recent_operations": recent,
        "low_stock_products": [p for p in products if p["active"] and p["low_stock"]][
            :6
        ],
    }


def friendly_integrity_error(error):
    message = str(error)
    if "products.sku" in message:
        return InventoryError("That SKU is already in use")
    if (
        "warehouses.code" in message
        or "locations.warehouse_id, locations.code" in message
    ):
        return InventoryError("That code is already in use")
    if "categories.name" in message:
        return InventoryError("That category already exists")
    if "warehouses.name" in message:
        return InventoryError("That warehouse already exists")
    return InventoryError(
        "The record could not be saved because a value is already in use"
    )
