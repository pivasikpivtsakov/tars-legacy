-- Speeds up OrderRepository.list_due_for_fanout: a partial index over only the
-- active (pending/offering) orders. The predicate keeps the index tiny regardless
-- of how large the historical orders table grows, and indexing created_at also
-- serves the query's ORDER BY created_at ASC (no extra sort).
--
-- The predicate must match the query's inlined `status IN ('pending','offering')`
-- for the planner to use it. On a large live table, consider building this with
-- CREATE INDEX CONCURRENTLY (outside a transaction) to avoid blocking writes.
CREATE INDEX IF NOT EXISTS orders_active_fanout_idx
    ON orders (created_at)
    WHERE status IN ('pending', 'offering');
