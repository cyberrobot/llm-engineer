from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from infrastructure.database.connection import get_connection
from operations.domain.administration import (
    AuditEntry,
    AuditFilters,
    AuditPage,
    AuditResult,
    OperationsDependencyUnavailable,
)


class PostgresOperationsAuditStore:
    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def add(self, entry: AuditEntry) -> AuditEntry:
        try:
            with self._connection_factory() as connection:
                connection.execute(
                    """INSERT INTO operations_audit_logs
                       (id,timestamp,actor,action,resource,result,request_id,correlation_id,
                        duration_ms,metadata)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        entry.id,
                        entry.timestamp,
                        entry.actor,
                        entry.action,
                        entry.resource,
                        entry.result.value,
                        entry.request_id,
                        entry.correlation_id,
                        entry.duration_ms,
                        Jsonb(entry.metadata),
                    ),
                )
            return entry
        except psycopg.Error as exc:
            raise OperationsDependencyUnavailable("Administrative audit recording failed.") from exc

    def update(self, entry: AuditEntry) -> AuditEntry:
        try:
            with self._connection_factory() as connection:
                result = connection.execute(
                    """UPDATE operations_audit_logs
                       SET result=%s,duration_ms=%s,metadata=%s WHERE id=%s""",
                    (
                        entry.result.value,
                        entry.duration_ms,
                        Jsonb(entry.metadata),
                        entry.id,
                    ),
                )
                if result.rowcount != 1:
                    raise OperationsDependencyUnavailable(
                        "Administrative audit entry is unavailable."
                    )
            return entry
        except OperationsDependencyUnavailable:
            raise
        except psycopg.Error as exc:
            raise OperationsDependencyUnavailable("Administrative audit update failed.") from exc

    def list(self, filters: AuditFilters, *, limit: int, offset: int) -> AuditPage:
        where, parameters = self._where(filters)
        try:
            with self._connection_factory() as connection:
                total = connection.execute(
                    f"SELECT count(*) FROM operations_audit_logs {where}", parameters
                ).fetchone()[0]
                rows = connection.execute(
                    f"""SELECT id,timestamp,actor,action,resource,result,request_id,
                               correlation_id,duration_ms,metadata
                        FROM operations_audit_logs {where}
                        ORDER BY timestamp DESC,id DESC LIMIT %s OFFSET %s""",
                    (*parameters, limit, offset),
                ).fetchall()
            return AuditPage(tuple(self._entry(row) for row in rows), total, limit, offset)
        except psycopg.Error as exc:
            raise OperationsDependencyUnavailable("Administrative audit query failed.") from exc

    def get(self, entry_id: UUID) -> AuditEntry | None:
        try:
            with self._connection_factory() as connection:
                row = connection.execute(
                    """SELECT id,timestamp,actor,action,resource,result,request_id,
                              correlation_id,duration_ms,metadata
                       FROM operations_audit_logs WHERE id=%s""",
                    (entry_id,),
                ).fetchone()
            return self._entry(row) if row else None
        except psycopg.Error as exc:
            raise OperationsDependencyUnavailable("Administrative audit query failed.") from exc

    def count_since(self, timestamp: datetime) -> int:
        try:
            with self._connection_factory() as connection:
                return connection.execute(
                    "SELECT count(*) FROM operations_audit_logs WHERE timestamp >= %s",
                    (timestamp,),
                ).fetchone()[0]
        except psycopg.Error as exc:
            raise OperationsDependencyUnavailable("Administrative audit query failed.") from exc

    @staticmethod
    def _where(filters: AuditFilters) -> tuple[str, tuple[Any, ...]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        for column, value in (
            ("actor", filters.user),
            ("action", filters.action),
            ("resource", filters.resource),
            ("result", filters.result.value if filters.result else None),
            ("timestamp >=", filters.date_from),
            ("timestamp <=", filters.date_to),
        ):
            if value is None:
                continue
            operator = "" if " " in column else " ="
            clauses.append(f"{column}{operator} %s")
            parameters.append(value)
        return ("WHERE " + " AND ".join(clauses) if clauses else "", tuple(parameters))

    @staticmethod
    def _entry(row) -> AuditEntry:
        return AuditEntry(
            id=UUID(str(row[0])),
            timestamp=row[1],
            actor=row[2],
            action=row[3],
            resource=row[4],
            result=AuditResult(row[5]),
            request_id=row[6],
            correlation_id=row[7],
            duration_ms=row[8],
            metadata=dict(row[9]),
        )
