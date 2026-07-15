CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE SCHEMA IF NOT EXISTS social_publishing;

CREATE TABLE IF NOT EXISTS social_publishing.social_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id varchar(128) NOT NULL UNIQUE,
    created_by_user_id varchar(128) NOT NULL,
    provider varchar(32) NOT NULL DEFAULT 'linkedin',
    linkedin_sub varchar(255),
    linkedin_member_urn varchar(255),
    profile_name varchar(255),
    email varchar(255),
    picture text,
    encrypted_access_token text NOT NULL,
    encrypted_refresh_token text,
    scopes text[] NOT NULL DEFAULT ARRAY[]::text[],
    token_expires_at timestamptz,
    refresh_token_expires_at timestamptz,
    status varchar(24) NOT NULL DEFAULT 'connected',
    connected_at timestamptz NOT NULL DEFAULT now(),
    refreshed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS social_publishing.publish_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id varchar(128) NOT NULL,
    scheduled_post_id uuid,
    content_id uuid NOT NULL,
    connection_id uuid REFERENCES social_publishing.social_connections(id),
    status varchar(24) NOT NULL DEFAULT 'queued',
    attempts integer NOT NULL DEFAULT 0,
    last_error text,
    linkedin_post_id text,
    linkedin_post_url text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    published_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(account_id, scheduled_post_id)
);

CREATE TABLE IF NOT EXISTS social_publishing.post_media (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publish_job_id uuid REFERENCES social_publishing.publish_jobs(id) ON DELETE CASCADE,
    content_id uuid NOT NULL,
    source_url text,
    image_asset_ref text,
    linkedin_asset_urn text,
    upload_url text,
    status varchar(24) NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_social_connections_account ON social_publishing.social_connections (account_id);
CREATE INDEX IF NOT EXISTS ix_publish_jobs_account_status ON social_publishing.publish_jobs (account_id, status);
CREATE INDEX IF NOT EXISTS ix_publish_jobs_content ON social_publishing.publish_jobs (content_id);

