from sqlalchemy.orm import DeclarativeBase


class SqlAlchemyBase(DeclarativeBase):
    """Collect the ORM schema managed by SQLite setup."""
