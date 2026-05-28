-- aiogram FSM state moved to Redis; the Postgres-backed table is no longer used.
DROP TABLE IF EXISTS aiogram_fsm;
