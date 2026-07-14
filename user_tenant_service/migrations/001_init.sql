CREATE SCHEMA IF NOT EXISTS user_tenant;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

SET search_path TO user_tenant, public;

DO $$
BEGIN
    CREATE TYPE account_type AS ENUM ('individual', 'team', 'platform');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE account_role AS ENUM ('Owner', 'TenantAdmin', 'Member');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE member_status AS ENUM ('active', 'invited', 'removed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE invite_status AS ENUM ('pending', 'accepted', 'revoked', 'expired');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(180) NOT NULL,
    type account_type NOT NULL,
    plan VARCHAR(64) NOT NULL DEFAULT 'Starter',
    credits INTEGER NOT NULL DEFAULT 0 CHECK (credits >= 0),
    created_by_user_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_accounts_created_by ON accounts (created_by_user_id);
CREATE INDEX IF NOT EXISTS ix_accounts_type ON accounts (type);

CREATE TABLE IF NOT EXISTS account_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    email VARCHAR(320) NOT NULL,
    role account_role NOT NULL,
    status member_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_account_members_user_status ON account_members (user_id, status);
CREATE INDEX IF NOT EXISTS ix_account_members_account_status ON account_members (account_id, status);

CREATE TABLE IF NOT EXISTS invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    email VARCHAR(320) NOT NULL,
    role account_role NOT NULL DEFAULT 'Member',
    code_hash TEXT NOT NULL UNIQUE,
    status invite_status NOT NULL DEFAULT 'pending',
    created_by_user_id UUID NOT NULL,
    accepted_by_user_id UUID,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_invites_account_status ON invites (account_id, status);
CREATE INDEX IF NOT EXISTS ix_invites_email_status ON invites (email, status);

DO $$
BEGIN
    IF to_regclass('accounts.accounts') IS NOT NULL THEN
        INSERT INTO accounts (id, name, type, plan, credits, created_by_user_id, created_at, updated_at)
        SELECT id, name, type::text::account_type, plan, credits, created_by_user_id, created_at, updated_at
        FROM accounts.accounts
        ON CONFLICT (id) DO NOTHING;
    END IF;

    IF to_regclass('accounts.account_members') IS NOT NULL THEN
        INSERT INTO account_members (id, account_id, user_id, email, role, status, created_at, updated_at)
        SELECT id, account_id, user_id, email, role::text::account_role, status::text::member_status, created_at, updated_at
        FROM accounts.account_members
        ON CONFLICT (account_id, user_id) DO NOTHING;
    ELSIF to_regclass('accounts.memberships') IS NOT NULL THEN
        INSERT INTO account_members (id, account_id, user_id, email, role, status, created_at, updated_at)
        SELECT id, account_id, user_id, email, role::text::account_role, status::text::member_status, created_at, updated_at
        FROM accounts.memberships
        ON CONFLICT (account_id, user_id) DO NOTHING;
    END IF;

    IF to_regclass('accounts.invites') IS NOT NULL THEN
        INSERT INTO invites (
            id,
            account_id,
            email,
            role,
            code_hash,
            status,
            created_by_user_id,
            accepted_by_user_id,
            expires_at,
            created_at,
            accepted_at,
            revoked_at
        )
        SELECT
            id,
            account_id,
            email,
            role::text::account_role,
            code_hash,
            status::text::invite_status,
            created_by_user_id,
            accepted_by_user_id,
            expires_at,
            created_at,
            accepted_at,
            revoked_at
        FROM accounts.invites
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;
