-- Serves OrderRepository.list_due_for_fanout after switching the ordering to
-- `ORDER BY amount DESC, created_at ASC`. The index columns/directions match the
-- ORDER BY exactly, so rows come back presorted (no sort node) and the LIMIT can
-- short-circuit. The partial predicate matches the query's inlined
-- `status IN ('pending','offering')`, keeping the index tiny regardless of how
-- large the historical orders table grows.
--
-- On a large live table, consider building this with CREATE INDEX CONCURRENTLY
-- (outside a transaction) to avoid blocking writes.
CREATE INDEX IF NOT EXISTS orders_active_fanout_amount_idx
    ON orders (amount DESC, created_at ASC)
    WHERE status IN ('pending', 'offering');
