from __future__ import annotations

from typing import Any

import numpy as np

from common.db import get_conn
from common.llm import get_embeddings
from common.models import WordingHit


def search_wording(query: str, product: str | None = None, k: int = 4) -> list[WordingHit]:
    embedding = np.asarray(get_embeddings().embed_query(query), dtype="float32")
    if product is None:
        sql = """
            SELECT clause_id, title, text, 1 - (embedding <=> %s) AS score
            FROM policy_wording_chunks
            ORDER BY embedding <=> %s
            LIMIT %s
        """
        params: tuple[Any, ...] = (embedding, embedding, k)
    else:
        sql = """
            SELECT clause_id, title, text, 1 - (embedding <=> %s) AS score
            FROM policy_wording_chunks
            WHERE product = %s
            ORDER BY embedding <=> %s
            LIMIT %s
        """
        params = (embedding, product, embedding, k)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        WordingHit(
            clause_id=row["clause_id"],
            title=row["title"],
            text=row["text"],
            score=float(row["score"]),
        )
        for row in rows
    ]
