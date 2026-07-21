from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Старые ORM-модели
from app.database.models import *  # noqa: E402,F403

# Новые ORM-модели
from app.models import *  # noqa: E402,F403  # noqa: E402,F403
