from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_ollama import OllamaEmbeddings
from pydantic import BaseModel

from common.config import get_settings

settings = get_settings()


@lru_cache(maxsize=3)
def get_model(tier: Literal["small", "mid", "judge"]):
    model_map = {
        "small": settings.SMALL_MODEL,
        "mid": settings.MID_MODEL,
        "judge": settings.JUDGE_MODEL,
    }
    return init_chat_model(model_map[tier], base_url=settings.OLLAMA_BASE_URL, temperature=0)


def structured(tier: Literal["small", "mid", "judge"], schema: type[BaseModel]):
    return get_model(tier).with_structured_output(schema)


@lru_cache(maxsize=1)
def get_embeddings():
    return OllamaEmbeddings(model=settings.EMBED_MODEL, base_url=settings.OLLAMA_BASE_URL)
