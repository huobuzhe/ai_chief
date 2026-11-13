-- scripts/migrate_stage4.sql
-- 阶段 4 数据库结构补丁：给阶段 3 已有的 users 表补 default_tenant_id 列
-- 原因：SQLAlchemy create_all() 不会给已存在的表加新列，手动 ALTER TABLE 兜底
-- 执行对象：v3.0 数据库（ai_chief_pgvector / localhost:5433）

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS default_tenant_id INTEGER;

CREATE INDEX IF NOT EXISTS ix_users_default_tenant_id
    ON users(default_tenant_id);
