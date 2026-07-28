from assistant.infrastructure.audit import get_audit_logs as load_audit_logs


def get_audit_logs(limit: int):
    return load_audit_logs(limit)
