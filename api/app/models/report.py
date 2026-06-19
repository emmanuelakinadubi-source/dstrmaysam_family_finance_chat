from sqlalchemy import Column, String, Text, Date, JSON
from app.db.base import UUIDBase


class Report(UUIDBase):
    __tablename__ = "reports"

    report_type = Column(String(50), nullable=False)  # family_monthly | event | vendor_analysis
    title = Column(String(200), nullable=False)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    content_json = Column(JSON, nullable=True)
    file_path = Column(String(500), nullable=True)
    format = Column(String(20), nullable=True)  # pdf | xlsx | csv
