-- Migration: users.share_consent_given_at — one-time public-share disclosure consent
-- Description: #79 opt-in loop. When a user flips their first session public
--   (via dashboard button or `yoru share`), we show a disclosure modal. That
--   acceptance was previously stored per-device (localStorage + a local file).
--   This migration moves it to the user row so the consent travels with the
--   account — confirm once, any browser/machine.
-- Author: backend-dev
-- Date: 2026-04-24

-- Receipt v0 (SQLite, receipt.db) creates the `users` table from the
-- SQLModel in apps/api/api/routers/receipt/models.py via init_db()'s
-- create_all() — no SQL needed at boot once the column lives on the model.
-- This file documents the equivalent shape for the Supabase-managed table
-- so the same column lands on production.

-- Postgres / Supabase
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS share_consent_given_at TIMESTAMPTZ;

-- SQLite (Receipt v0) — equivalent statement, in case create_all is skipped
-- on an existing receipt.db with the legacy schema.
-- ALTER TABLE users ADD COLUMN share_consent_given_at TIMESTAMP;
