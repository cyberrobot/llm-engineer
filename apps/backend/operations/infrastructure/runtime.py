from collections.abc import Callable
from typing import Any

import psycopg

from infrastructure.database.connection import get_connection
from operations.domain.administration import (
    MaintenanceState,
    OperationsDependencyUnavailable,
)


class PostgresRuntimeStateStore:
    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def get_maintenance(self) -> MaintenanceState:
        try:
            with self._connection_factory() as connection:
                row = connection.execute(
                    """SELECT maintenance_enabled,maintenance_message,updated_at,updated_by
                       FROM operations_runtime_state WHERE singleton=TRUE"""
                ).fetchone()
            if row is None:
                raise OperationsDependencyUnavailable("Runtime operations state is unavailable.")
            return MaintenanceState(bool(row[0]), row[1], row[2], row[3])
        except psycopg.Error as exc:
            raise OperationsDependencyUnavailable(
                "Runtime operations state lookup failed."
            ) from exc

    def set_maintenance(self, state: MaintenanceState) -> MaintenanceState:
        try:
            with self._connection_factory() as connection:
                connection.execute(
                    """UPDATE operations_runtime_state
                       SET maintenance_enabled=%s,maintenance_message=%s,updated_at=%s,updated_by=%s
                       WHERE singleton=TRUE""",
                    (state.enabled, state.message, state.updated_at, state.updated_by),
                )
            return state
        except psycopg.Error as exc:
            raise OperationsDependencyUnavailable(
                "Runtime operations state update failed."
            ) from exc
