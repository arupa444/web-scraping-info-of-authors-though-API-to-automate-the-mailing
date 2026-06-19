"""Shared test fixtures: throwaway SQLite DB + fresh schema per test."""

import os
import tempfile

# Point the app at a throwaway DB BEFORE importing any app module (engine binds at import).
_TMPDIR = tempfile.mkdtemp(prefix="icereach-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMPDIR}/test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("GEMINI_API_KEY", "")  # AI disabled by default in tests
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")  # disabled in tests (one test opts in)

import pytest  # noqa: E402

from icereach.db import Base, SessionLocal, engine  # noqa: E402
import icereach.models  # noqa: E402,F401  (populate metadata)


@pytest.fixture(autouse=True)
def _fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
