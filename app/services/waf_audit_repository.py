import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import get_settings


@dataclass(frozen=True)
class WafAuditTaskRecord:
    task_id: str
    status: str
    created_at: str
    updated_at: str
    report_upload_path: str | None
    log_archive_path: str | None
    preprocessing_id: str | None
    workdir_path: str | None
    audit_opinion_path: str | None
    error_code: str | None
    error_message: str | None
    error_details: str | None


def create_waf_audit_task_record(
    *,
    task_id: str,
    status: str,
    report_upload_path: str | None,
    log_archive_path: str | None,
    workdir_path: str | None,
    preprocessing_id: str | None = None,
    audit_opinion_path: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    error_details: str | None = None,
) -> WafAuditTaskRecord:
    timestamp = _utc_now_iso()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO waf_audit_tasks (
                task_id,
                status,
                created_at,
                updated_at,
                report_upload_path,
                log_archive_path,
                preprocessing_id,
                workdir_path,
                audit_opinion_path,
                error_code,
                error_message,
                error_details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                status,
                timestamp,
                timestamp,
                report_upload_path,
                log_archive_path,
                preprocessing_id,
                workdir_path,
                audit_opinion_path,
                error_code,
                error_message,
                error_details,
            ),
        )
    return get_waf_audit_task_record(task_id)  # pragma: no cover


def update_waf_audit_task_record(task_id: str, **fields: str | None) -> WafAuditTaskRecord | None:
    if not fields:
        return get_waf_audit_task_record(task_id)

    existing = get_waf_audit_task_record(task_id)
    if existing is None:
        return None

    column_names = list(fields.keys()) + ["updated_at"]
    values = [fields[name] for name in fields] + [_utc_now_iso(), task_id]
    assignments = ", ".join(f"{column_name} = ?" for column_name in column_names)
    with _connect() as connection:
        connection.execute(
            f"UPDATE waf_audit_tasks SET {assignments} WHERE task_id = ?",
            values,
        )
    return get_waf_audit_task_record(task_id)


def get_waf_audit_task_record(task_id: str) -> WafAuditTaskRecord | None:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                task_id,
                status,
                created_at,
                updated_at,
                report_upload_path,
                log_archive_path,
                preprocessing_id,
                workdir_path,
                audit_opinion_path,
                error_code,
                error_message,
                error_details
            FROM waf_audit_tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()

    if row is None:
        return None
    return _row_to_record(row)


def list_waf_audit_task_records() -> list[WafAuditTaskRecord]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                task_id,
                status,
                created_at,
                updated_at,
                report_upload_path,
                log_archive_path,
                preprocessing_id,
                workdir_path,
                audit_opinion_path,
                error_code,
                error_message,
                error_details
            FROM waf_audit_tasks
            ORDER BY created_at DESC, task_id DESC
            """
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    settings.tasks_db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.tasks_db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS waf_audit_tasks (
            task_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            report_upload_path TEXT,
            log_archive_path TEXT,
            preprocessing_id TEXT,
            workdir_path TEXT,
            audit_opinion_path TEXT,
            error_code TEXT,
            error_message TEXT,
            error_details TEXT
        )
        """
    )
    _ensure_column(connection, "waf_audit_tasks", "preprocessing_id", "TEXT")
    return connection


def _row_to_record(row: sqlite3.Row) -> WafAuditTaskRecord:
    return WafAuditTaskRecord(
        task_id=row["task_id"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        report_upload_path=row["report_upload_path"],
        log_archive_path=row["log_archive_path"],
        preprocessing_id=row["preprocessing_id"],
        workdir_path=row["workdir_path"],
        audit_opinion_path=row["audit_opinion_path"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        error_details=row["error_details"],
    )


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
