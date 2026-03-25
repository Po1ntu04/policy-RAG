-- Postgres schema for the Gov RAG platform (3NF-oriented core tables).
-- Focus: RBAC, policy docs, indicators, audits, and traceability.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Users and RBAC
CREATE TABLE IF NOT EXISTS app_users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    email TEXT,
    phone TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS roles (
    role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS permissions (
    perm_code TEXT PRIMARY KEY,
    perm_desc TEXT
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_by UUID REFERENCES app_users(user_id) ON DELETE SET NULL,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id UUID NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    perm_code TEXT NOT NULL REFERENCES permissions(perm_code) ON DELETE CASCADE,
    PRIMARY KEY (role_id, perm_code)
);

-- Organizations (units/offices)
CREATE TABLE IF NOT EXISTS orgs (
    org_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_name TEXT NOT NULL,
    org_type TEXT NOT NULL
        CHECK (org_type IN ('unit', 'office', 'other')),
    parent_org_id UUID REFERENCES orgs(org_id) ON DELETE SET NULL,
    UNIQUE (org_name, org_type)
);

-- Policy categories and documents (file-level metadata)
CREATE TABLE IF NOT EXISTS policy_categories (
    category_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_name TEXT NOT NULL,
    parent_category_id UUID REFERENCES policy_categories(category_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS policy_documents (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    publish_date DATE,
    last_update_date DATE,
    publisher_org_id UUID REFERENCES orgs(org_id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'retired')),
    file_name TEXT,
    file_uri TEXT,
    category_id UUID REFERENCES policy_categories(category_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (file_name)
);

-- Mapping between ingested doc_id (RAG) and policy document
CREATE TABLE IF NOT EXISTS policy_doc_refs (
    doc_id TEXT PRIMARY KEY,
    policy_id UUID NOT NULL REFERENCES policy_documents(policy_id) ON DELETE CASCADE,
    page_label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Document chunks for RAG traceability (optional)
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id UUID NOT NULL REFERENCES policy_documents(policy_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text_uri TEXT,
    chunk_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vector_index (
    vector_item_id TEXT PRIMARY KEY,
    chunk_id UUID NOT NULL REFERENCES document_chunks(chunk_id) ON DELETE CASCADE,
    embedding_model TEXT NOT NULL,
    embedded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indicators (core KPI table)
CREATE TABLE IF NOT EXISTS indicators (
    indicator_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id UUID REFERENCES policy_documents(policy_id) ON DELETE SET NULL,
    year INTEGER NOT NULL,
    primary_category TEXT NOT NULL,
    secondary_indicator TEXT NOT NULL,
    scoring_rules TEXT,
    score NUMERIC(10, 2),
    target_source TEXT,
    deadline DATE,
    completion_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (completion_status IN (
            'pending', 'in_progress', 'completed', 'partial', 'not_completed', 'unknown'
        )),
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('high', 'medium', 'low', 'manual')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS indicator_responsibilities (
    indicator_id UUID NOT NULL REFERENCES indicators(indicator_id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES orgs(org_id) ON DELETE CASCADE,
    duty_type TEXT NOT NULL
        CHECK (duty_type IN ('responsible_unit', 'responsible_office', 'collaborator')),
    PRIMARY KEY (indicator_id, org_id, duty_type)
);

CREATE TABLE IF NOT EXISTS indicator_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_id UUID NOT NULL REFERENCES indicators(indicator_id) ON DELETE CASCADE,
    doc_id TEXT,
    doc_name TEXT,
    page_number INTEGER,
    text_snippet TEXT,
    chunk_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit records
CREATE TABLE IF NOT EXISTS audit_records (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_id UUID NOT NULL REFERENCES indicators(indicator_id) ON DELETE CASCADE,
    reviewer_user_id UUID REFERENCES app_users(user_id) ON DELETE SET NULL,
    review_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    judgment TEXT NOT NULL,
    reason TEXT,
    confidence TEXT NOT NULL DEFAULT 'low'
        CHECK (confidence IN ('high', 'medium', 'low')),
    suggestions TEXT
);

CREATE TABLE IF NOT EXISTS audit_evidence (
    audit_evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id UUID NOT NULL REFERENCES audit_records(audit_id) ON DELETE CASCADE,
    doc_id TEXT,
    doc_name TEXT,
    page_number INTEGER,
    quote TEXT
);

-- Comments and behavior logs
CREATE TABLE IF NOT EXISTS comments (
    comment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    policy_id UUID NOT NULL REFERENCES policy_documents(policy_id) ON DELETE CASCADE,
    parent_comment_id UUID REFERENCES comments(comment_id) ON DELETE CASCADE,
    comment_type TEXT NOT NULL DEFAULT 'comment'
        CHECK (comment_type IN ('comment', 'question', 'answer')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    moderation_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (moderation_status IN ('pending', 'approved', 'rejected'))
);

ALTER TABLE comments
    ADD COLUMN IF NOT EXISTS moderation_reason TEXT,
    ADD COLUMN IF NOT EXISTS moderated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS parent_comment_id UUID REFERENCES comments(comment_id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS comment_type TEXT NOT NULL DEFAULT 'comment'
        CHECK (comment_type IN ('comment', 'question', 'answer'));

CREATE TABLE IF NOT EXISTS policy_likes (
    policy_id UUID NOT NULL REFERENCES policy_documents(policy_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (policy_id, user_id)
);

CREATE TABLE IF NOT EXISTS policy_follows (
    policy_id UUID NOT NULL REFERENCES policy_documents(policy_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (policy_id, user_id)
);

CREATE TABLE IF NOT EXISTS user_behavior_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES app_users(user_id) ON DELETE SET NULL,
    policy_id UUID REFERENCES policy_documents(policy_id) ON DELETE SET NULL,
    behavior_type TEXT NOT NULL
        CHECK (behavior_type IN ('click', 'search', 'favorite', 'comment', 'download', 'favorite_add', 'favorite_remove')),
    happened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id TEXT
);

ALTER TABLE user_behavior_logs
    DROP CONSTRAINT IF EXISTS user_behavior_logs_behavior_type_check;
ALTER TABLE user_behavior_logs
    ADD CONSTRAINT user_behavior_logs_behavior_type_check
    CHECK (behavior_type IN ('click', 'search', 'favorite', 'comment', 'download', 'favorite_add', 'favorite_remove'));

-- Indexes for common filters/statistics
CREATE INDEX IF NOT EXISTS idx_indicators_year ON indicators(year);
CREATE INDEX IF NOT EXISTS idx_indicators_status ON indicators(completion_status);
CREATE INDEX IF NOT EXISTS idx_indicators_primary ON indicators(primary_category);
CREATE INDEX IF NOT EXISTS idx_indicators_policy ON indicators(policy_id);

CREATE INDEX IF NOT EXISTS idx_indicator_resp_org ON indicator_responsibilities(org_id);
CREATE INDEX IF NOT EXISTS idx_policy_publish_date ON policy_documents(publish_date);
CREATE INDEX IF NOT EXISTS idx_audit_review_at ON audit_records(review_at);
CREATE INDEX IF NOT EXISTS idx_comments_policy ON comments(policy_id);
CREATE INDEX IF NOT EXISTS idx_comments_parent ON comments(parent_comment_id);
CREATE INDEX IF NOT EXISTS idx_comments_user ON comments(user_id);
CREATE INDEX IF NOT EXISTS idx_comments_type ON comments(comment_type);
