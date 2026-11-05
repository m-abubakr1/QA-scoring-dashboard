"""The language model behind a small interface, so tests can use a fake one."""
from functools import lru_cache
from typing import Protocol

import openai
from openai import AsyncOpenAI

from .config import settings


class LLMError(Exception):
    """The model service failed or timed out."""


class LLM(Protocol):
    model: str

    async def complete(self, system: str, user: str, json_mode: bool = False) -> str: ...


class OpenAILLM:
    def __init__(self, api_key: str, model: str, timeout: float):
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout)

    async def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0,
                **extra,
            )
        except openai.OpenAIError as exc:
            raise LLMError(str(exc)) from exc
        return (resp.choices[0].message.content or "").strip()


@lru_cache
def get_llm() -> LLM:
    if not settings.openai_api_key:
        raise LLMError("OPENAI_API_KEY is not set")
    return OpenAILLM(settings.openai_api_key, settings.model, settings.timeout_seconds)
