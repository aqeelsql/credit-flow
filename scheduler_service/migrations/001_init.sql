CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE SCHEMA IF NOT EXISTS scheduler;

CREATE TABLE IF NOT EXISTS scheduler.scheduled_posts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id varchar(128) NOT NULL,
    created_by_user_id varchar(128) NOT NULL,
    content_id uuid NOT NULL,
    content_title varchar(255) NOT NULL,
    publish_at timestamptz NOT NULL,
    timezone varchar(128) NOT NULL DEFAULT 'UTC',
    recurrence varchar(24) NOT NULL DEFAULT 'none',
    status varchar(24) NOT NULL DEFAULT 'scheduled',
    dispatch_attempts integer NOT NULL DEFAULT 0,
    last_error text,
    locked_at timestamptz,
    dispatched_at timestamptz,
    cancelled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_scheduled_posts_account_publish ON scheduler.scheduled_posts (account_id, publish_at);
CREATE INDEX IF NOT EXISTS ix_scheduled_posts_due ON scheduler.scheduled_posts (status, publish_at);
CREATE INDEX IF NOT EXISTS ix_scheduled_posts_content ON scheduler.scheduled_posts (account_id, content_id);
