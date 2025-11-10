# backend/database.py
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class UserRequest(Base):
    __tablename__ = 'user_requests'
    id = Column(Integer, primary_key=True)
    user_id = Column(String)
    action = Column(String)  # 'translate', 'analyze', 'transcribe'
    file_type = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String)  # 'pending', 'completed', 'failed'