from unittest.mock import MagicMock

from infrastructure.database.migrations.assistant_behaviour import downgrade, upgrade


def test_assistant_behaviour_migration_defines_backfill_ownership_and_immutability() -> None:
    cursor = MagicMock()
    upgrade(cursor)
    sql = "\n".join(str(call.args[0]) for call in cursor.execute.call_args_list)
    assert "assistant_behaviour_revisions" in sql
    assert "assistant_behaviour_states" in sql
    assert "FOREIGN KEY (assistant_id, draft_revision)" in sql
    assert "FOREIGN KEY (assistant_id, published_revision)" in sql
    assert "SELECT id,1" in sql
    assert "assistant_behaviour_revisions_immutable" in sql


def test_assistant_behaviour_migration_has_forward_cleanup_for_test_databases() -> None:
    cursor = MagicMock()
    downgrade(cursor)
    sql = "\n".join(str(call.args[0]) for call in cursor.execute.call_args_list)
    assert sql.index("assistant_behaviour_states") < sql.index("assistant_behaviour_revisions")
