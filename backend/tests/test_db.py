from sqlalchemy import text

from icereach.db import get_db


def test_get_db_yields_working_session():
    gen = get_db()
    db = next(gen)
    try:
        assert db.execute(text("select 1")).scalar() == 1
    finally:
        gen.close()
