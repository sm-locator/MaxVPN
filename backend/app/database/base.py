from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Импортируем модели после объявления Base,
# чтобы Alembic видел их через Base.metadata.
from app.models import *  # noqa: E402,F403
