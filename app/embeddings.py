"""Text embeddings via OpenAI, through langchain-openai."""

import os

from langchain_openai import OpenAIEmbeddings

from app.models import Clause

EMBEDDING_DIM = 1536
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts with EMBEDDING_MODEL, one vector of EMBEDDING_DIM floats per text."""
    model = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    vectors = OpenAIEmbeddings(model=model).embed_documents(texts)
    for vector in vectors:
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(
                f"{model} returned {len(vector)} dimensions, expected {EMBEDDING_DIM}"
            )
    return vectors


def clause_text(clause: Clause) -> str:
    """The text we embed for a clause: its heading, a newline, then its body."""
    return f"{clause.heading}\n{clause.text}"
