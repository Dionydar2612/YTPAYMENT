-- Reference schema, matching app/models.py.
-- The app creates these tables automatically on startup via
-- SQLAlchemy's Base.metadata.create_all(), so running this file manually
-- is optional — useful if you prefer to provision the schema yourself
-- (e.g. via a DBA-managed migration pipeline) before first boot.

CREATE TABLE IF NOT EXISTS users (
    id              VARCHAR(36) PRIMARY KEY,
    username        VARCHAR(64) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(128),
    role            VARCHAR(16) NOT NULL DEFAULT 'member',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);

CREATE TABLE IF NOT EXISTS expenses (
    id                  VARCHAR(36) PRIMARY KEY,
    month               VARCHAR(7) NOT NULL,
    description         VARCHAR(255) NOT NULL,
    total_amount        NUMERIC(12,2) NOT NULL,
    participants_count  INTEGER NOT NULL,
    per_person_amount   NUMERIC(12,2) NOT NULL,
    created_by          VARCHAR(36) REFERENCES users(id),
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_expenses_month ON expenses (month);

CREATE TABLE IF NOT EXISTS expense_participants (
    id          VARCHAR(36) PRIMARY KEY,
    expense_id  VARCHAR(36) NOT NULL REFERENCES expenses(id),
    user_id     VARCHAR(36) NOT NULL REFERENCES users(id),
    amount      NUMERIC(12,2) NOT NULL,
    UNIQUE (expense_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_expense_participants_user ON expense_participants (user_id);

CREATE TABLE IF NOT EXISTS monthly_balances (
    id                   VARCHAR(36) PRIMARY KEY,
    user_id              VARCHAR(36) NOT NULL REFERENCES users(id),
    month                VARCHAR(7) NOT NULL,
    base_amount          NUMERIC(12,2) NOT NULL DEFAULT 0,
    old_balance_carried  NUMERIC(12,2) NOT NULL DEFAULT 0,
    credit_used          NUMERIC(12,2) NOT NULL DEFAULT 0,
    credit_source_month  VARCHAR(7),
    total_due            NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_paid           NUMERIC(12,2) NOT NULL DEFAULT 0,
    outstanding          NUMERIC(12,2) NOT NULL DEFAULT 0,
    credit_new           NUMERIC(12,2) NOT NULL DEFAULT 0,
    status               VARCHAR(16) NOT NULL DEFAULT 'unpaid',
    created_at           TIMESTAMP DEFAULT NOW(),
    updated_at           TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, month)
);
CREATE INDEX IF NOT EXISTS ix_monthly_balances_month ON monthly_balances (month);

CREATE TABLE IF NOT EXISTS payment_slips (
    id              VARCHAR(36) PRIMARY KEY,
    user_id         VARCHAR(36) NOT NULL REFERENCES users(id),
    month           VARCHAR(7) NOT NULL,
    amount_claimed  NUMERIC(12,2) NOT NULL,
    file_path       VARCHAR(500) NOT NULL,
    transferred_at  TIMESTAMP,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    reviewed_by     VARCHAR(36) REFERENCES users(id),
    reviewed_at     TIMESTAMP,
    reject_reason   TEXT,
    uploaded_at     TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_payment_slips_month ON payment_slips (month);

CREATE TABLE IF NOT EXISTS payments (
    id          VARCHAR(36) PRIMARY KEY,
    user_id     VARCHAR(36) NOT NULL REFERENCES users(id),
    month       VARCHAR(7) NOT NULL,
    amount      NUMERIC(12,2) NOT NULL,
    slip_id     VARCHAR(36) REFERENCES payment_slips(id),
    note        VARCHAR(255),
    created_at  TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_payments_user_month ON payments (user_id, month);

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
CREATE INDEX IF NOT EXISTS ix_credit_alloc_source ON credit_allocations (source_user_id, source_month);
CREATE INDEX IF NOT EXISTS ix_credit_alloc_target ON credit_allocations (target_user_id, target_month);
