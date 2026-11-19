import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def pg_api():
    """Real PostgreSQL sessions in a private schema for this test only."""
    url = os.environ.get("RECONAI_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set RECONAI_TEST_POSTGRES_URL to run PostgreSQL race tests.")
    admin = create_engine(url, connect_args={"connect_timeout": 5})
    assert admin.dialect.name == "postgresql"
    schema = "test_review_" + uuid.uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url,
        connect_args={
            "options": f"-csearch_path={schema} -clock_timeout=10000 -cstatement_timeout=15000",
            "application_name": schema,
        },
    )
    sessions = sessionmaker(bind=engine, autoflush=False)
    previous = app.dependency_overrides.get(get_db)

    def get_test_db():
        with sessions() as db:
            yield db

    try:
        Base.metadata.create_all(engine)
        app.dependency_overrides[get_db] = get_test_db
        with TestClient(app) as client:
            yield client, sessions, schema
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
