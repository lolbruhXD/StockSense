# StockSense

StockSense is an inventory management app with separate company workspaces. It tracks products across warehouses and locations, turns receipts, deliveries, transfers, and physical counts into stock movements, and keeps a searchable ledger of every validated change.

The interface follows the supplied StockSense PDF and workflow sketch. The implementation uses Python's standard library, SQLite, and plain browser JavaScript. There is no build step or package installation.

## Run it

Use Python 3.10 or newer:

```bash
python3 -m stocksense.server
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), create an account, then add a warehouse and products. The database is created in `data/stocksense.sqlite3`. Set `STOCKSENSE_DB` to choose another path. The `data/` directory is ignored by Git.

Each new signup creates a company workspace. To add a colleague to that workspace, open **My profile**, create an invitation for their email address, and share the generated link. Invitations expire after seven days and can only be used once by the named email address. Existing databases are migrated on startup; their current accounts and stock stay together in one workspace.

## How stock moves

1. **Receipt:** save products and destination; mark ready; validate to add stock.
2. **Delivery:** save products and source; submit, pick, pack, mark ready, then validate to remove stock.
3. **Transfer:** choose different source and destination locations; validate to move stock without changing the company total.
4. **Adjustment:** enter a physical count for a product at a location; validate to replace the recorded quantity.

Draft and waiting operations can be edited. Canceled operations never change stock. A validation updates balances and writes ledger entries in the same SQLite transaction. If any line fails, the entire validation rolls back. Quantity precision is three decimal places. Opening stock entered when creating a product becomes a completed adjustment, so it is visible in history too.

The **All operations** view filters by document type, status, warehouse, and category. Stock and products have SKU/name search; the move ledger has reference/SKU search and warehouse/product filters.

Products, stock locations, operations, and move history load 100 rows at a time; use **Load more** to browse older records. Products, operations, and move history use cursor paging. Product pickers search the catalog as you type. The stock view shows locations with a recorded balance, including balances adjusted to zero. Products without any stock movement remain in the product catalog.

## Password reset

One-time reset codes are valid for ten minutes and accept at most five attempts. To send them by email, configure SMTP before starting the server:

```bash
export STOCKSENSE_SMTP_HOST=smtp.example.com
export STOCKSENSE_SMTP_PORT=587
export STOCKSENSE_SMTP_USER=your-smtp-user
export STOCKSENSE_SMTP_PASSWORD=your-smtp-password
export STOCKSENSE_MAIL_FROM=inventory@example.com
python3 -m stocksense.server
```

For a local demo without email, set `STOCKSENSE_DEV_RESET_CODES=1`. The reset code is then shown in the browser only while the server is bound to loopback. Do not use that setting on a shared machine.

## Scope and deployment

The default server listens only on `127.0.0.1`. Company IDs are checked on inventory reads and writes, and the database uses company-aware foreign keys. The included SQLite database and Python HTTP server are still for local demos and small private installations. They have not been load tested for hundreds of companies and thousands of users. A production deployment at that scale needs PostgreSQL, a multiworker application server, HTTPS, backups, monitoring, and load tests before launch.
