-- Replace the single price_60 (+ packages array) with a per-package price map.
-- Each pack now carries its own user-set price. Backfill preserves prior
-- economics by pricing every previously-selected pack at price_60 * unit_count.

ALTER TABLE user_profiles ADD COLUMN prices JSONB;

UPDATE user_profiles up
   SET prices = sub.prices
  FROM (
      SELECT p.id,
             jsonb_object_agg(u.size::text, p.price_60 * u.units) AS prices
        FROM user_profiles p
        CROSS JOIN LATERAL unnest(p.packages) AS pkg(size)
        JOIN (VALUES
            (60, 1), (325, 5), (660, 10), (1800, 25), (3850, 50), (8100, 100)
        ) AS u(size, units) ON u.size = pkg.size
       WHERE p.price_60 IS NOT NULL
         AND p.packages IS NOT NULL
       GROUP BY p.id
  ) sub
 WHERE up.id = sub.id;

ALTER TABLE user_profiles DROP COLUMN price_60;
ALTER TABLE user_profiles DROP COLUMN packages;
