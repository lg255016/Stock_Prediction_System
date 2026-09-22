-- Migration 001: Baseline — 建立 schema_version 表
-- From: v0 (no migration tracking)
-- To:   v1
-- 規格來源：doc/upgrade/contracts/DB_MIGRATION_PLAN.md §4.1（Gate 0 已核准）

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at  TIMESTAMP DEFAULT NOW(),
    checksum    TEXT
);

INSERT INTO schema_version (version, description)
VALUES (1, 'Baseline: create schema_version table')
ON CONFLICT (version) DO NOTHING;
