"""数据库连接和会话管理 — PostgreSQL (Railway) / SQLite (本地开发)"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Railway 自动注入 DATABASE_URL，本地开发无此变量则用 SQLite
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # PostgreSQL (Railway)
    # Railway 给的 URL 前缀是 "postgres://"，SQLAlchemy 需要 "postgresql://"
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL, echo=False)
else:
    # SQLite (本地开发)
    DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'shaoshan.db')}"
    engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

    # SQLite 默认关闭外键约束，需手动启用
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """依赖注入: 获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库表 (首次运行时自动创建)"""
    Base.metadata.create_all(bind=engine)
