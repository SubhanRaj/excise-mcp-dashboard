"""Ollama async client: structured-output loop (one retry) and plain text
generation. MCP_ENGINES.md §Structured-output loop.
"""

from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.schemas import LLMStructuredOutputError, OllamaUnreachableError

T = TypeVar("T", bound=BaseModel)


class OllamaClient:
    def __init__(self, base_url: str, http_client: httpx.AsyncClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http_client

    async def generate_structured(
        self, *, model: str, prompt: str, response_model: type[T], stage: str
    ) -> T:
        current_prompt = prompt
        last_error = ""
        for attempt in (1, 2):
            raw = await self._generate(
                model=model, prompt=current_prompt, format_schema=response_model.model_json_schema()
            )
            try:
                return response_model.model_validate_json(raw)
            except ValidationError as e:
                last_error = str(e)
                if attempt == 2:
                    raise LLMStructuredOutputError(
                        response_model.__name__, stage, last_error
                    ) from e
                current_prompt = (
                    f"{prompt}\n\nThe previous reply failed validation:\n{last_error}\n"
                    "Return only valid JSON matching the schema."
                )
        raise AssertionError("unreachable")  # loop always returns or raises

    async def generate_text(self, *, model: str, prompt: str) -> str:
        return await self._generate(model=model, prompt=prompt, format_schema=None)

    async def _generate(
        self, *, model: str, prompt: str, format_schema: dict[str, object] | None
    ) -> str:
        payload: dict[str, object] = {"model": model, "prompt": prompt, "stream": False}
        if format_schema is not None:
            payload["format"] = format_schema
        try:
            resp = await self.http.post(
                f"{self.base_url}/api/generate", json=payload, timeout=120.0
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaUnreachableError(str(e)) from e
        response_text = resp.json().get("response", "")
        return str(response_text)

    async def pulled_models(self) -> set[str]:
        try:
            resp = await self.http.get(f"{self.base_url}/api/tags", timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPError:
            return set()
        data = resp.json()
        return {m["name"] for m in data.get("models", [])}
