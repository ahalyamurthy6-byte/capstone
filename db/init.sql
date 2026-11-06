CREATE TABLE IF NOT EXISTS customers (
    customer_id text PRIMARY KEY,
    name text,
    email text,
    dob date
);

CREATE TABLE IF NOT EXISTS policies (
    policy_number text PRIMARY KEY,
    customer_id text REFERENCES customers(customer_id),
    product text,
    start_date date,
    end_date date,
    sum_insured numeric,
    exclusions jsonb DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS policy_wording_chunks (
    id serial PRIMARY KEY,
    product text,
    clause_id text,
    title text,
    text text,
    embedding vector(768),
    UNIQUE (product, clause_id)
);

CREATE TABLE IF NOT EXISTS staff (
    staff_id text PRIMARY KEY,
    name text,
    email text,
    role text CHECK (role IN ('adjuster', 'approver', 'supervisor')),
    approval_limit numeric DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cases (
    case_id text PRIMARY KEY,
    policy_number text REFERENCES policies(policy_number),
    claimant_name text,
    claimant_email text,
    incident_date date,
    claim_type text,
    amount numeric,
    description text,
    status text DEFAULT 'NEW',
    duplicate_of text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id text PRIMARY KEY,
    case_id text REFERENCES cases(case_id),
    file_path text,
    doc_type text,
    ocr_text text,
    ocr_confidence real,
    injection_flag bool DEFAULT false,
    fields jsonb,
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS summaries (
    case_id text PRIMARY KEY REFERENCES cases(case_id),
    summary jsonb,
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS assignments (
    case_id text PRIMARY KEY REFERENCES cases(case_id),
    adjuster_id text,
    approver_id text,
    assigned_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approvals (
    id serial PRIMARY KEY,
    case_id text REFERENCES cases(case_id),
    approver_id text,
    status text CHECK (status IN ('pending', 'approved', 'rejected', 'more_info')),
    rationale text,
    requested_at timestamptz DEFAULT now(),
    decided_at timestamptz
);

CREATE TABLE IF NOT EXISTS sla_timers (
    id serial PRIMARY KEY,
    case_id text REFERENCES cases(case_id),
    kind text,
    due_at timestamptz,
    breached bool DEFAULT false
);

CREATE TABLE IF NOT EXISTS notifications (
    id serial PRIMARY KEY,
    case_id text,
    to_addr text,
    subject text,
    body text,
    sent_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id bigserial PRIMARY KEY,
    case_id text,
    actor text,
    action text,
    before jsonb,
    after jsonb,
    checkpoint_id text,
    ts timestamptz DEFAULT now()
);

CREATE OR REPLACE FUNCTION audit_log_block()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log;
CREATE TRIGGER audit_log_append_only
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW
EXECUTE FUNCTION audit_log_block();

CREATE INDEX IF NOT EXISTS idx_cases_status ON cases (status);
CREATE INDEX IF NOT EXISTS idx_documents_case_id ON documents (case_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_case_ts ON audit_log (case_id, ts);
CREATE INDEX IF NOT EXISTS idx_cases_claimant_name_trgm ON cases USING gin (claimant_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_policy_wording_chunks_embedding_hnsw ON policy_wording_chunks USING hnsw (embedding vector_cosine_ops);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'checkpoints'
    ) THEN
        CREATE OR REPLACE VIEW audit_with_checkpoint AS
        SELECT a.*, c.checkpoint_id AS linked_checkpoint_id
        FROM audit_log a
        LEFT JOIN LATERAL (
            SELECT c.checkpoint_id, c.checkpoint
            FROM checkpoints c
            WHERE c.thread_id = a.case_id
              AND (c.checkpoint->>'ts')::timestamptz <= a.ts
            ORDER BY (c.checkpoint->>'ts')::timestamptz DESC
            LIMIT 1
        ) c ON TRUE;
    END IF;
END $$;
