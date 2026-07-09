"""
SQLAlchemy Declarative Base

所有 ORM 模型都继承自此类。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 Declarative Base 类"""
