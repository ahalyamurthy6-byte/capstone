from __future__ import annotations

from common.rag import search_wording


queries = [
    "pre-existing condition",
    "cosmetic surgery",
    "documents required for claim",
    "policy expired",
]


for query in queries:
    hits = search_wording(query, k=3)
    print(f"QUERY: {query}")
    for hit in hits:
        print(f"{hit.clause_id}: {hit.title} (score={hit.score:.4f})")
    print()
