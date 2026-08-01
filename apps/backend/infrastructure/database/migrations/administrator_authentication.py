from typing import Any


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS administrators (
            id UUID PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('administrator')),
            status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
            failed_login_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
            locked_until TIMESTAMPTZ,
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT administrators_normalized_email_check
                CHECK (email = lower(btrim(email)) AND length(email) <= 254),
            CONSTRAINT administrators_timestamps_check CHECK (updated_at >= created_at)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS administrator_sessions (
            id UUID PRIMARY KEY,
            administrator_id UUID NOT NULL REFERENCES administrators(id) ON DELETE RESTRICT,
            token_hash TEXT NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL,
            last_seen_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            CONSTRAINT administrator_sessions_timestamps_check CHECK (
                last_seen_at >= created_at AND expires_at > created_at
                AND (revoked_at IS NULL OR revoked_at >= created_at)
            )
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS administrator_sessions_administrator_id_idx
        ON administrator_sessions(administrator_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS administrator_sessions_expires_at_idx
        ON administrator_sessions(expires_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS administrator_sessions_active_expiry_idx
        ON administrator_sessions(expires_at) WHERE revoked_at IS NULL
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP TABLE IF EXISTS administrator_sessions")
    cursor.execute("DROP TABLE IF EXISTS administrators")
