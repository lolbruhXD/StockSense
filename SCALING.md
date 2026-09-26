# Scaling StockSense

The target is hundreds of companies and thousands of users. The current app is a useful local preview, but its SQLite database and Python standard-library HTTP server are not the production setup for that target.

## What is in place

- Every inventory record belongs to a company. Queries use the signed-in user's company ID, and company-aware foreign keys reject references to another company's records.
- Stock validation updates balances and movement history in one transaction. Outbound stock uses a conditional update, so two requests cannot both spend the same units.
- Stock, operations, and movement history load in pages. Operations and history use their last seen ID, so browsing older records does not scan through every earlier page. The dashboard aggregates counts in SQL instead of loading the whole catalog.
- Existing SQLite files migrate in place. New signups get separate workspaces; invited teammates join the same workspace.

## Production architecture

1. Move inventory and auth data to PostgreSQL. Use company IDs in every primary lookup and foreign key, and add row-level security as a second boundary. Migrate the existing SQLite data with a checked, reversible import.
2. Run stateless API workers behind an HTTPS reverse proxy. Use a bounded PostgreSQL connection pool, health checks, and graceful shutdown. Session state stays in the database so requests can reach any worker.
3. Replace full product-catalog downloads with paged product search and selection. Index searches to match the actual product count and query patterns.
4. Add automated backups with restore drills, request and database metrics, and load tests using representative company sizes and daily stock movements. Size the worker and database tiers from measured latency and contention, then scale them independently.

The SQLite preview can keep serving demos while this production path is built. Do not place the SQLite file on a network filesystem or run multiple app hosts against it. A quick synthetic query run is not evidence that the app can serve the target workload; that needs load testing after the PostgreSQL deployment exists.
