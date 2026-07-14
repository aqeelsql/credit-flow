CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE SCHEMA IF NOT EXISTS ai_generation;

CREATE TABLE IF NOT EXISTS ai_generation.generation_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id varchar(128) NOT NULL,
    user_id varchar(128) NOT NULL,
    request_id varchar(128),
    channel varchar(255) NOT NULL UNIQUE,
    model varchar(255) NOT NULL,
    prompt text NOT NULL,
    response_text text NOT NULL DEFAULT '',
    status varchar(24) NOT NULL DEFAULT 'queued',
    prompt_tokens integer,
    completion_tokens integer,
    total_tokens integer,
    cost numeric(18, 8),
    error_reason text,
    cancellation_requested boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS ai_generation.prompt_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_job_id uuid NOT NULL UNIQUE REFERENCES ai_generation.generation_jobs(id) ON DELETE CASCADE,
    account_id varchar(128) NOT NULL,
    user_id varchar(128) NOT NULL,
    model varchar(255) NOT NULL,
    prompt text NOT NULL,
    response_text text NOT NULL,
    prompt_tokens integer,
    completion_tokens integer,
    total_tokens integer,
    cost numeric(18, 8),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_generation.image_generation_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id varchar(128) NOT NULL,
    user_id varchar(128) NOT NULL,
    source_generation_job_id uuid REFERENCES ai_generation.generation_jobs(id) ON DELETE SET NULL,
    provider varchar(64) NOT NULL,
    model varchar(255) NOT NULL,
    prompt text NOT NULL,
    source_text text NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'queued',
    image_url text,
    width integer,
    height integer,
    seed integer,
    error_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS ix_generation_jobs_account_created
    ON ai_generation.generation_jobs (account_id, created_at);
CREATE INDEX IF NOT EXISTS ix_generation_jobs_status_created
    ON ai_generation.generation_jobs (status, created_at);
CREATE INDEX IF NOT EXISTS ix_prompt_history_account_created
    ON ai_generation.prompt_history (account_id, created_at);
CREATE INDEX IF NOT EXISTS ix_image_generation_jobs_account_created
    ON ai_generation.image_generation_jobs (account_id, created_at);
