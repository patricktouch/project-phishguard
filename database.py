from sqlalchemy import (create_engine, Column, Integer,
                        String, Float, DateTime, Text)
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./phishing_log.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

class EmailLog(Base):
    __tablename__ = "email_log"

    id                = Column(Integer, primary_key=True, index=True)
    received_at       = Column(DateTime, default=datetime.utcnow)
    source            = Column(String)   # "forwarded" or "manual"
    sender            = Column(String)
    subject           = Column(String)
    body_preview      = Column(Text)     # first 300 chars
    bert_phishing_pct = Column(Float)
    lr_phishing_pct   = Column(Float)
    verdict           = Column(String)   # PHISHING or LEGITIMATE
    confidence        = Column(String)   # High, Medium, Low

# Create the table if it doesn't exist
Base.metadata.create_all(bind=engine)
print("✅ Database ready — phishing_log.db created")
