CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE SCHEMA IF NOT EXISTS content;

CREATE TABLE IF NOT EXISTS content.content (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id varchar(128) NOT NULL,
    created_by_user_id varchar(128) NOT NULL,
    title varchar(255) NOT NULL,
    body text NOT NULL,
    prompt text,
    status varchar(24) NOT NULL DEFAULT 'draft',
    source_generation_job_id uuid,
    image_url text,
    image_asset_ref text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    approved_at timestamptz,
    published_at timestamptz,
    deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS content.content_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    content_id uuid NOT NULL REFERENCES content.content(id) ON DELETE CASCADE,
    version_number integer NOT NULL,
    title varchar(255) NOT NULL,
    body text NOT NULL,
    prompt text,
    image_url text,
    image_asset_ref text,
    status varchar(24) NOT NULL,
    created_by_user_id varchar(128) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (content_id, version_number)
);

CREATE INDEX IF NOT EXISTS ix_content_account_status_updated ON content.content (account_id, status, updated_at);
CREATE INDEX IF NOT EXISTS ix_content_generation_job ON content.content (source_generation_job_id);
