import logging
import time

import httpx

from elenchos.providers.base import Completion, GenerationParams, Message

logger = logging.getLogger(__name__)


class OpenAICompatProvider:
    """OpenAI-compatible chat completions client (Ollama /v1, LM Studio, OpenRouter)."""

    def __init__(
        self,
        name: str,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/models",
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("data") or []
            return [item["id"] for item in items]

    def complete(
        self,
        model: str,
        messages: list[Message],
        params: GenerationParams,
    ) -> Completion:
        payload: dict = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "temperature": params.temperature,
            "top_p": params.top_p,
        }
        if params.max_tokens is not None:
            payload["max_tokens"] = params.max_tokens
        if params.seed is not None:
            payload["seed"] = params.seed
        if params.stop is not None:
            payload["stop"] = params.stop
        if params.reasoning_effort is not None:
            payload["reasoning_effort"] = params.reasoning_effort

        logger.debug("POST %s/chat/completions model=%s", self.base_url, model)
        logger.debug("request payload: %s", payload)

        started = time.perf_counter()
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            if response.status_code == 404:
                detail = response.text
                raise RuntimeError(
                    f"Model {model!r} not found on {self.name}. "
                    f"Pull it first (e.g. ollama pull {model}). {detail}"
                ) from None
            if response.is_error:
                logger.error(
                    "%s chat/completions failed: status=%s model=%s body=%s",
                    self.name,
                    response.status_code,
                    model,
                    response.text[:500],
                )
            response.raise_for_status()
            raw = response.json()

        latency_ms = (time.perf_counter() - started) * 1000
        usage = raw.get("usage") or {}
        logger.info(
            "%s completion ok: model=%s latency_ms=%.0f tokens=%s",
            self.name,
            model,
            latency_ms,
            usage.get("total_tokens", "?"),
        )
        logger.debug("response (%0.0f ms): %s", latency_ms, raw)

        choice = raw["choices"][0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or None

        return Completion(
            text=content,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
            raw=raw,
            finish_reason=choice.get("finish_reason"),
            reasoning=reasoning,
        )
