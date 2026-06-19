from sqlalchemy import Column, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import UUIDBase


class AuditLog(UUIDBase):
    __tablename__ = "audit_logs"

    action = Column(String(100), nullable=False)  # create | update | delete
    entity_type = Column(String(100), nullable=False)  # budget | expense | event | vendor
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    performed_by = Column(String(100), nullable=True)
