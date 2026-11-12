-- Feedback loop store (Neon project "outbound-feedback"). Already applied; kept here so it can be recreated.
-- One row per draft the operator changed or rejected: before, after, and the context
-- needed to retrieve it for a similar email later. No contact names or email addresses.
CREATE TABLE corrections (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  operator text NOT NULL,          -- whose correction (never pooled across people); a hash, not an email
  domain text NOT NULL,
  contact_role text,
  role_tier smallint,              -- position on the role priority list
  company_stage text,
  sector text,
  company_trigger text,
  subject_before text NOT NULL,
  body_before text NOT NULL,
  subject_after text NOT NULL,
  body_after text NOT NULL,
  reason text,                     -- optional: why he changed it, in his words
  disagreement real NOT NULL CHECK (disagreement BETWEEN 0 AND 1),  -- share of the draft that changed
  rejected boolean NOT NULL DEFAULT false
);
CREATE INDEX corrections_lookup ON corrections (operator, role_tier, created_at DESC);
