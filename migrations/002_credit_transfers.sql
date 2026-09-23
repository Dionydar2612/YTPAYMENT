-- Credit allocation migration
-- New code uses credit_allocations instead of the old credit_transfers table.
-- Safe to run repeatedly on PostgreSQL.

CREATE TABLE IF NOT EXISTS credit_allocations (
    id              VARCHAR(36) PRIMARY KEY,
    source_user_id  VARCHAR(36) NOT NULL REFERENCES users(id),
    source_month    VARCHAR(7) NOT NULL,
    target_user_id  VARCHAR(36) NOT NULL REFERENCES users(id),
    target_month    VARCHAR(7) NOT NULL,
    amount          NUMERIC(12,2) NOT NULL,
    note            VARCHAR(255),
    created_by      VARCHAR(36) REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_credit_alloc_source
ON credit_allocations(source_user_id, source_month);

CREATE INDEX IF NOT EXISTS ix_credit_alloc_target
ON credit_allocations(target_user_id, target_month);

-- If an older deployment has credit_transfers, copy those records once.
-- Fresh databases do not have that table, so this block safely skips the copy.
DO $$
BEGIN
    IF to_regclass('public.credit_transfers') IS NOT NULL THEN
        INSERT INTO credit_allocations (
            id,
            source_user_id,
            source_month,
            target_user_id,
            target_month,
            amount,
            note,
            created_by,
            created_at
        )
        SELECT
            ct.id,
            ct.from_user_id,
            ct.source_month,
            ct.to_user_id,
            ct.target_month,
            ct.amount,
            ct.note,
            NULL,
            ct.created_at
        FROM credit_transfers ct
        WHERE NOT EXISTS (
            SELECT 1
            FROM credit_allocations ca
            WHERE ca.id = ct.id
        );
    END IF;
END $$;
