"""Add immutable Assistant behaviour revisions and publication state (PR 11G)."""

import json
from typing import Any

from assistant.domain.assistant_behaviour import (
    DEFAULT_ASSISTANT_INSTRUCTIONS,
    DEFAULT_INPUT_PLACEHOLDER,
    DEFAULT_SUGGESTED_QUESTIONS,
    DEFAULT_WELCOME_MESSAGE,
    MAX_BEHAVIOUR_INSTRUCTIONS_LENGTH,
    MAX_INPUT_PLACEHOLDER_LENGTH,
    MAX_SUGGESTED_QUESTION_LENGTH,
    MAX_SUGGESTED_QUESTIONS,
    MAX_WELCOME_MESSAGE_LENGTH,
)

MIGRATION_ID = "20260811_11g_assistant_behaviour"


def upgrade(cursor: Any) -> None:
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS assistant_behaviour_revisions (
            assistant_id TEXT NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
            revision INTEGER NOT NULL CHECK (revision > 0),
            instructions TEXT NOT NULL CHECK (
                length(trim(instructions)) > 0
                AND length(instructions) <= {MAX_BEHAVIOUR_INSTRUCTIONS_LENGTH}
            ),
            welcome_message TEXT NOT NULL CHECK (
                length(welcome_message) <= {MAX_WELCOME_MESSAGE_LENGTH}
            ),
            input_placeholder TEXT NOT NULL CHECK (
                length(trim(input_placeholder)) > 0
                AND length(input_placeholder) <= {MAX_INPUT_PLACEHOLDER_LENGTH}
                AND input_placeholder !~ '[\\n\\r]'
            ),
            suggested_questions JSONB NOT NULL CHECK (
                jsonb_typeof(suggested_questions) = 'array'
                AND jsonb_array_length(suggested_questions) <= {MAX_SUGGESTED_QUESTIONS}
            ),
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (assistant_id, revision)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assistant_behaviour_states (
            assistant_id TEXT PRIMARY KEY REFERENCES assistants(id) ON DELETE CASCADE,
            draft_revision INTEGER NOT NULL,
            published_revision INTEGER,
            published_at TIMESTAMPTZ,
            version INTEGER NOT NULL CHECK (version > 0),
            updated_at TIMESTAMPTZ NOT NULL,
            CHECK ((published_revision IS NULL) = (published_at IS NULL)),
            CONSTRAINT assistant_behaviour_draft_fkey
                FOREIGN KEY (assistant_id, draft_revision)
                REFERENCES assistant_behaviour_revisions(assistant_id, revision),
            CONSTRAINT assistant_behaviour_published_fkey
                FOREIGN KEY (assistant_id, published_revision)
                REFERENCES assistant_behaviour_revisions(assistant_id, revision)
        )
    """)
    cursor.execute(
        """INSERT INTO assistant_behaviour_revisions
           (assistant_id,revision,instructions,welcome_message,input_placeholder,
            suggested_questions,created_at)
           SELECT id,1,%s,%s,%s,%s::jsonb,created_at FROM assistants
           ON CONFLICT (assistant_id,revision) DO NOTHING""",
        (
            DEFAULT_ASSISTANT_INSTRUCTIONS,
            DEFAULT_WELCOME_MESSAGE,
            DEFAULT_INPUT_PLACEHOLDER,
            json.dumps(DEFAULT_SUGGESTED_QUESTIONS),
        ),
    )
    cursor.execute("""
        INSERT INTO assistant_behaviour_states
            (assistant_id,draft_revision,published_revision,published_at,version,updated_at)
        SELECT id,1,1,created_at,1,created_at FROM assistants
        ON CONFLICT (assistant_id) DO NOTHING
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS assistant_behaviour_revisions_lookup_idx
        ON assistant_behaviour_revisions(assistant_id, revision DESC)
    """)
    cursor.execute(f"""
        CREATE OR REPLACE FUNCTION validate_assistant_behaviour_revision()
        RETURNS trigger AS $$
        DECLARE item JSONB;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'assistant behaviour revisions are immutable';
            END IF;
            IF translate(NEW.instructions, E'\\n\\t', '') ~ '[[:cntrl:]]'
               OR translate(NEW.welcome_message, E'\\n\\t', '') ~ '[[:cntrl:]]'
               OR NEW.input_placeholder ~ '[[:cntrl:]]' THEN
                RAISE EXCEPTION 'assistant behaviour contains unsafe control characters';
            END IF;
            FOR item IN SELECT value FROM jsonb_array_elements(NEW.suggested_questions)
            LOOP
                IF jsonb_typeof(item) <> 'string'
                   OR length(trim(item #>> '{{}}')) = 0
                   OR length(item #>> '{{}}') > {MAX_SUGGESTED_QUESTION_LENGTH}
                   OR (item #>> '{{}}') ~ '[[:cntrl:]]' THEN
                    RAISE EXCEPTION 'invalid suggested question';
                END IF;
            END LOOP;
            RETURN NEW;
        END $$ LANGUAGE plpgsql
    """)
    cursor.execute("""
        DROP TRIGGER IF EXISTS assistant_behaviour_revisions_immutable
            ON assistant_behaviour_revisions;
        CREATE TRIGGER assistant_behaviour_revisions_immutable
        BEFORE INSERT OR UPDATE ON assistant_behaviour_revisions
        FOR EACH ROW EXECUTE FUNCTION validate_assistant_behaviour_revision()
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP TABLE IF EXISTS assistant_behaviour_states")
    cursor.execute("DROP TABLE IF EXISTS assistant_behaviour_revisions")
    cursor.execute("DROP FUNCTION IF EXISTS validate_assistant_behaviour_revision()")
