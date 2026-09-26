"""Small HTTP API and static file server; no package installation required."""

import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import smtplib
import sqlite3
import traceback
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .database import connect, initialize
from . import inventory

STATIC = Path(__file__).resolve().parent.parent / "static"
SESSION_DAYS = 7


def now():
    return datetime.now(timezone.utc)


def stamp(dt):
    return dt.isoformat()


def password_digest(password, salt):
    return hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1
    ).hex()


def public_user(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def mail_reset_code(email, code):
    host = os.environ.get("STOCKSENSE_SMTP_HOST")
    sender = os.environ.get("STOCKSENSE_MAIL_FROM")
    if not host or not sender:
        return False
    message = EmailMessage()
    message["Subject"] = "Your StockSense password reset code"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"Your StockSense reset code is {code}. It expires in 10 minutes.\n"
    )
    port = int(os.environ.get("STOCKSENSE_SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.starttls()
        username = os.environ.get("STOCKSENSE_SMTP_USER")
        if username:
            smtp.login(username, os.environ.get("STOCKSENSE_SMTP_PASSWORD", ""))
        smtp.send_message(message)
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "StockSense/1.0"

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")

    def json_response(self, data, status=HTTPStatus.OK, cookie=None):
        body = json.dumps(data, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 1_000_000:
            raise inventory.InventoryError("Request body is empty or too large")
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise inventory.InventoryError("Send valid JSON") from None
        if not isinstance(data, dict):
            raise inventory.InventoryError("Send a JSON object")
        return data

    def session(self, db):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
            token = cookies["stocksense_session"].value
        except Exception:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        row = db.execute(
            """SELECT s.*, u.name, u.email FROM sessions s
            JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?""",
            (token_hash, stamp(now())),
        ).fetchone()
        return row

    def new_session(self, db, user_id):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        db.execute("DELETE FROM sessions WHERE expires_at<=?", (stamp(now()),))
        db.execute(
            "INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES (?,?,?,?)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                user_id,
                csrf,
                stamp(now() + timedelta(days=SESSION_DAYS)),
            ),
        )
        cookie = f"stocksense_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_DAYS * 86400}"
        return csrf, cookie

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def do_PUT(self):
        self.handle_request("PUT")

    def do_PATCH(self):
        self.handle_request("PATCH")

    def handle_request(self, method):
        parsed = urlsplit(self.path)
        if not parsed.path.startswith("/api/"):
            if method == "GET":
                return self.serve_static(parsed.path)
            return self.json_response({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        try:
            origin = self.headers.get("Origin")
            if origin and origin not in (
                f"http://{self.headers.get('Host')}",
                f"https://{self.headers.get('Host')}",
            ):
                return self.json_response(
                    {"error": "Request origin not allowed"}, HTTPStatus.FORBIDDEN
                )
            with closing(connect(self.server.db_path)) as db:
                self.route(db, method, parsed.path, parse_qs(parsed.query))
        except inventory.InventoryError as error:
            self.json_response({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except (ValueError, TypeError):
            self.json_response(
                {"error": "Check the submitted values"}, HTTPStatus.BAD_REQUEST
            )
        except sqlite3.IntegrityError as error:
            self.json_response(
                {"error": str(inventory.friendly_integrity_error(error))},
                HTTPStatus.CONFLICT,
            )
        except Exception:
            traceback.print_exc()
            self.json_response(
                {"error": "Something went wrong. Please try again."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def route(self, db, method, path, query):
        if path == "/api/session" and method == "GET":
            session = self.session(db)
            if not session:
                return self.json_response({"user": None})
            return self.json_response(
                {
                    "user": public_user(
                        {
                            "id": session["user_id"],
                            "name": session["name"],
                            "email": session["email"],
                        }
                    ),
                    "csrf": session["csrf_token"],
                }
            )

        if path == "/api/signup" and method == "POST":
            data = self.read_json()
            name = inventory.required(data, "name")
            email = inventory.required(data, "email").lower()
            password = str(data.get("password", ""))
            if "@" not in email or len(password) < 10:
                raise inventory.InventoryError(
                    "Use a valid email and a password of at least 10 characters"
                )
            salt = secrets.token_hex(16)
            cursor = db.execute(
                "INSERT INTO users(name,email,password_hash,salt) VALUES (?,?,?,?)",
                (name, email, password_digest(password, salt), salt),
            )
            csrf, cookie = self.new_session(db, cursor.lastrowid)
            return self.json_response(
                {
                    "user": {"id": cursor.lastrowid, "name": name, "email": email},
                    "csrf": csrf,
                },
                HTTPStatus.CREATED,
                cookie,
            )

        if path == "/api/login" and method == "POST":
            data = self.read_json()
            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not user or not hmac.compare_digest(
                password_digest(password, user["salt"]), user["password_hash"]
            ):
                raise inventory.InventoryError("Email or password is incorrect")
            csrf, cookie = self.new_session(db, user["id"])
            return self.json_response(
                {"user": public_user(user), "csrf": csrf}, cookie=cookie
            )

        if path == "/api/password-reset/request" and method == "POST":
            data = self.read_json()
            email = str(data.get("email", "")).strip().lower()
            user = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            response = {
                "message": "If that account exists, a reset code has been sent."
            }
            if user:
                code = f"{secrets.randbelow(1_000_000):06d}"
                if not mail_reset_code(email, code):
                    if os.environ.get(
                        "STOCKSENSE_DEV_RESET_CODES"
                    ) == "1" and self.server.server_address[0] in (
                        "127.0.0.1",
                        "localhost",
                    ):
                        response["development_code"] = code
                    else:
                        raise inventory.InventoryError(
                            "Email delivery is not configured. Ask the administrator to set up SMTP."
                        )
                digest = hashlib.sha256(f"{user['id']}:{code}".encode()).hexdigest()
                db.execute(
                    """INSERT INTO password_resets(user_id,code_hash,expires_at,attempts)
                    VALUES (?,?,?,0) ON CONFLICT(user_id) DO UPDATE SET
                    code_hash=excluded.code_hash, expires_at=excluded.expires_at, attempts=0""",
                    (user["id"], digest, stamp(now() + timedelta(minutes=10))),
                )
            return self.json_response(response)

        if path == "/api/password-reset/confirm" and method == "POST":
            data = self.read_json()
            email = str(data.get("email", "")).strip().lower()
            code = str(data.get("code", "")).strip()
            password = str(data.get("password", ""))
            if len(password) < 10:
                raise inventory.InventoryError(
                    "Password must be at least 10 characters"
                )
            user = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            reset = (
                db.execute(
                    "SELECT * FROM password_resets WHERE user_id=?", (user["id"],)
                ).fetchone()
                if user
                else None
            )
            if (
                not reset
                or reset["expires_at"] <= stamp(now())
                or reset["attempts"] >= 5
            ):
                raise inventory.InventoryError("Reset code is invalid or expired")
            db.execute(
                "UPDATE password_resets SET attempts=attempts+1 WHERE user_id=?",
                (user["id"],),
            )
            expected = hashlib.sha256(f"{user['id']}:{code}".encode()).hexdigest()
            if not hmac.compare_digest(expected, reset["code_hash"]):
                raise inventory.InventoryError("Reset code is invalid or expired")
            salt = secrets.token_hex(16)
            db.execute(
                "UPDATE users SET password_hash=?, salt=? WHERE id=?",
                (password_digest(password, salt), salt, user["id"]),
            )
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            db.execute("DELETE FROM password_resets WHERE user_id=?", (user["id"],))
            return self.json_response(
                {"message": "Password updated. Sign in with your new password."}
            )

        session = self.session(db)
        if not session:
            return self.json_response(
                {"error": "Sign in to continue"}, HTTPStatus.UNAUTHORIZED
            )
        if method != "GET" and not hmac.compare_digest(
            self.headers.get("X-CSRF-Token", ""), session["csrf_token"]
        ):
            return self.json_response(
                {"error": "Session expired. Refresh and try again."},
                HTTPStatus.FORBIDDEN,
            )
        if path == "/api/logout" and method == "POST":
            db.execute(
                "DELETE FROM sessions WHERE token_hash=?", (session["token_hash"],)
            )
            return self.json_response(
                {"ok": True},
                cookie="stocksense_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0",
            )
        if path == "/api/profile" and method == "PATCH":
            name = inventory.required(self.read_json(), "name")
            db.execute("UPDATE users SET name=? WHERE id=?", (name, session["user_id"]))
            return self.json_response({"name": name})

        if path == "/api/bootstrap" and method == "GET":
            return self.json_response(
                {
                    "warehouses": [
                        dict(r)
                        for r in db.execute("SELECT * FROM warehouses ORDER BY name")
                    ],
                    "locations": [
                        dict(r)
                        for r in db.execute(
                            """SELECT l.*, w.name warehouse FROM locations l
                    JOIN warehouses w ON w.id=l.warehouse_id ORDER BY w.name,l.name"""
                        )
                    ],
                    "categories": [
                        dict(r)
                        for r in db.execute("SELECT * FROM categories ORDER BY name")
                    ],
                    "products": inventory.list_products(db),
                }
            )
        if path == "/api/dashboard" and method == "GET":
            return self.json_response(inventory.dashboard(db))
        if path == "/api/products" and method == "GET":
            return self.json_response(
                inventory.list_products(
                    db, self.param(query, "search"), self.param(query, "category_id")
                )
            )
        if path == "/api/products" and method == "POST":
            return self.json_response(
                {"id": inventory.create_product(db, self.read_json())},
                HTTPStatus.CREATED,
            )
        if path.startswith("/api/products/") and method == "PUT":
            inventory.update_product(db, int(path.rsplit("/", 1)[1]), self.read_json())
            return self.json_response({"ok": True})
        if path == "/api/categories" and method == "POST":
            return self.json_response(
                {"id": inventory.create_category(db, self.read_json())},
                HTTPStatus.CREATED,
            )
        if path == "/api/warehouses" and method == "POST":
            return self.json_response(
                {"id": inventory.create_warehouse(db, self.read_json())},
                HTTPStatus.CREATED,
            )
        if path.startswith("/api/warehouses/") and method == "PUT":
            inventory.update_warehouse(
                db, int(path.rsplit("/", 1)[1]), self.read_json()
            )
            return self.json_response({"ok": True})
        if path == "/api/locations" and method == "POST":
            return self.json_response(
                {"id": inventory.create_location(db, self.read_json())},
                HTTPStatus.CREATED,
            )
        if path.startswith("/api/locations/") and method == "PUT":
            inventory.update_location(db, int(path.rsplit("/", 1)[1]), self.read_json())
            return self.json_response({"ok": True})
        if path == "/api/stock" and method == "GET":
            return self.json_response(
                inventory.stock(
                    db,
                    self.param(query, "search"),
                    self.param(query, "warehouse_id"),
                    self.param(query, "category_id"),
                )
            )
        if path == "/api/operations" and method == "GET":
            return self.json_response(
                inventory.list_operations(
                    db,
                    self.param(query, "type"),
                    self.param(query, "status"),
                    self.param(query, "search"),
                    self.param(query, "warehouse_id"),
                    self.param(query, "category_id"),
                )
            )
        if path == "/api/operations" and method == "POST":
            return self.json_response(
                {
                    "id": inventory.create_operation(
                        db, self.read_json(), session["user_id"]
                    )
                },
                HTTPStatus.CREATED,
            )
        if path.startswith("/api/operations/"):
            parts = path.strip("/").split("/")
            if len(parts) in (3, 4):
                operation_id = int(parts[2])
                if len(parts) == 3 and method == "GET":
                    return self.json_response(
                        inventory.operation_detail(db, operation_id)
                    )
                if len(parts) == 3 and method == "PUT":
                    inventory.update_operation(db, operation_id, self.read_json())
                    return self.json_response({"ok": True})
                if len(parts) == 4 and method == "POST" and parts[3] == "validate":
                    inventory.validate_operation(db, operation_id)
                    return self.json_response({"ok": True})
                if len(parts) == 4 and method == "POST" and parts[3] == "action":
                    inventory.set_status(
                        db, operation_id, inventory.required(self.read_json(), "action")
                    )
                    return self.json_response({"ok": True})
        if path == "/api/history" and method == "GET":
            return self.json_response(
                inventory.history(
                    db,
                    self.param(query, "search"),
                    self.param(query, "warehouse_id"),
                    self.param(query, "product_id"),
                    min(max(int(self.param(query, "limit") or 100), 1), 200),
                    max(int(self.param(query, "offset") or 0), 0),
                )
            )
        return self.json_response({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    @staticmethod
    def param(query, key):
        return query.get(key, [""])[0]

    def serve_static(self, path):
        requested = (STATIC / path.lstrip("/")).resolve()
        if path == "/" or path == "":
            requested = STATIC / "index.html"
        if not requested.is_relative_to(STATIC) or not requested.is_file():
            return self.json_response({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        body = requested.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            mimetypes.guess_type(requested)[0] or "application/octet-stream",
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)


def run():
    import argparse

    parser = argparse.ArgumentParser(description="Run StockSense")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    initialize()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.db_path = None
    print(f"StockSense is ready at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
