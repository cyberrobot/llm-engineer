from enum import Enum


class IngestionStatus(str, Enum):
    queued = "queued"
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
