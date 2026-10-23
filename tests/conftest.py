import hashlib
import os
import random
from pathlib import Path

import pytest
from dotenv import load_dotenv

from app import db
from app.embeddings import EMBEDDING_DIM
from app.seed import build

load_dotenv()
# Keep test traces out of the project that holds real runs and evals.
os.environ["LANGSMITH_PROJECT"] = "triage-tests"


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Offline stand-in for embed(): a fixed pseudo-random vector per text."""
    vectors = []
    for text in texts:
        rng = random.Random(hashlib.sha256(text.encode()).digest())
        vectors.append([rng.uniform(-1, 1) for _ in range(EMBEDDING_DIM)])
    return vectors


@pytest.fixture(scope="session")
def fake_embed():
    return _fake_embed


@pytest.fixture(scope="session")
def offline_db(tmp_path_factory) -> Path:
    """Seeded template database with fake vectors, for tests that don't need real search."""
    path = tmp_path_factory.mktemp("offline") / "harbour.db"
    build(path, embed_fn=_fake_embed)
    return path


@pytest.fixture(scope="session")
def openai_db(tmp_path_factory) -> Path:
    """Seeded template database with real OpenAI vectors. Skips without a key."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not set")
    path = tmp_path_factory.mktemp("openai") / "harbour.db"
    build(path)
    return path


@pytest.fixture
def conn(offline_db):
    conn = db.connect(offline_db)
    yield conn
    conn.close()
