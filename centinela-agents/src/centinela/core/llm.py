"""Cliente OpenAI: chat estructurado, visión, embeddings, tokens y costo.

Tres funciones públicas, todas con reintentos, timeout y contabilidad de uso:

- `chat_structured(schema, messages, ...)` → dict validado contra un JSON Schema.
- `describe_image(images, prompt, schema, ...)` → dict (visión multimodal).
- `embed(texts)` → lista de vectores.

Con `MOCK_MODE=true` ninguna de las tres toca la red.

Nota sobre modelos: el kit fija `gpt-5.6-luna`. Si ese identificador no existe
en la cuenta, el cliente reintenta una sola vez con el modelo de respaldo y lo
deja registrado en la traza (`model_fallback_used`), en lugar de fallar la
evaluación completa.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from centinela.config import Settings, get_settings
from centinela.core import mock as mockmod
from centinela.schemas import Usage

logger = logging.getLogger(__name__)

# Errores de OpenAI que justifican reintentar tal cual (transitorios).
_RETRYABLE_FRAGMENTS = ("rate limit", "timeout", "temporarily", "overloaded", "503", "502", "529")
# Errores que indican "ese modelo no existe / no está habilitado" → probar respaldo.
_MODEL_MISSING_FRAGMENTS = ("does not exist", "model_not_found", "404", "do not have access")

# La API de OpenAI ha ido cambiando qué parámetros acepta cada familia de
# modelos: los más nuevos exigen `max_completion_tokens` en vez de `max_tokens`
# y algunos solo admiten la temperatura por defecto. En vez de fijar una
# combinación y esperar que dure, el cliente prueba, aprende del error y
# recuerda por modelo lo que funcionó.
_PARAM_ADAPTATIONS: tuple[tuple[str, str], ...] = (
    ("max_tokens", "max_completion_tokens"),
    ("max_completion_tokens", "max_tokens"),
)


def estimate_tokens(text: str) -> int:
    """Estimación barata (~4 caracteres por token). Se usa solo si la API no
    devuelve `usage`, por ejemplo en modo mock."""
    return max(1, len(text) // 4)


@dataclass
class UsageAccumulator:
    """Acumula consumo a lo largo de una evaluación (varias llamadas)."""

    chat: Usage = field(default_factory=Usage)
    embedding: Usage = field(default_factory=Usage)
    models_used: list[str] = field(default_factory=list)
    fallback_used: bool = False

    def add_chat(self, tokens_in: int, tokens_out: int, cost: float, model: str) -> None:
        self.chat.tokens_in += tokens_in
        self.chat.tokens_out += tokens_out
        self.chat.cost_usd += cost
        self.chat.calls += 1
        if model and model not in self.models_used:
            self.models_used.append(model)

    def add_embedding(self, tokens_in: int, cost: float, model: str) -> None:
        self.embedding.tokens_in += tokens_in
        self.embedding.cost_usd += cost
        self.embedding.calls += 1
        if model and model not in self.models_used:
            self.models_used.append(model)

    @property
    def tokens_in(self) -> int:
        return self.chat.tokens_in + self.embedding.tokens_in

    @property
    def tokens_out(self) -> int:
        return self.chat.tokens_out

    @property
    def cost_usd(self) -> float:
        return round(self.chat.cost_usd + self.embedding.cost_usd, 8)

    @property
    def model_label(self) -> str:
        return "+".join(self.models_used) if self.models_used else "mock"

    def as_dict(self) -> dict[str, Any]:
        return {
            "chat": self.chat.model_dump(),
            "embedding": self.embedding.model_dump(),
            "models_used": self.models_used,
            "model_fallback_used": self.fallback_used,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
        }


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Fachada sobre el SDK de OpenAI, con modo mock y contabilidad de costo."""

    def __init__(self, settings: Settings | None = None, usage: UsageAccumulator | None = None):
        self.settings = settings or get_settings()
        self.usage = usage or UsageAccumulator()
        self._client: Any = None

    # -- infraestructura ----------------------------------------------------
    @property
    def mock(self) -> bool:
        return self.settings.mock_mode or not self.settings.has_openai

    def _sdk(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # import diferido: los tests no lo necesitan

            self._client = OpenAI(
                api_key=self.settings.openai_api_key,
                timeout=self.settings.openai_timeout_seconds,
                max_retries=0,  # los reintentos los gestionamos aquí, con backoff propio
            )
        return self._client

    def _cost_chat(self, tokens_in: int, tokens_out: int) -> float:
        s = self.settings
        return (
            tokens_in / 1_000_000 * s.price_chat_input_per_1m
            + tokens_out / 1_000_000 * s.price_chat_output_per_1m
        )

    def _cost_embedding(self, tokens_in: int) -> float:
        return tokens_in / 1_000_000 * self.settings.price_embedding_input_per_1m

    def _call_with_retries(self, fn, primary: str, fallback: str) -> tuple[Any, str]:
        """Ejecuta `fn(model)` con backoff exponencial.

        Solo se pasa al modelo de respaldo cuando el error dice que el modelo
        principal no existe o no está habilitado. Cualquier otro error (clave
        inválida, cuota agotada) se propaga sin gastar una segunda llamada.
        """
        candidates: list[str] = []
        for model in (primary, fallback):
            if model and model not in candidates:
                candidates.append(model)

        last: Exception | None = None
        for index, model in enumerate(candidates):
            for attempt in range(max(1, self.settings.openai_max_retries)):
                try:
                    result = fn(model)
                    if index > 0:
                        self.usage.fallback_used = True
                    return result, model
                except Exception as exc:  # noqa: BLE001 - se reclasifica aquí
                    last = exc
                    message = str(exc).lower()
                    if any(f in message for f in _MODEL_MISSING_FRAGMENTS):
                        logger.warning(
                            "Modelo '%s' no disponible en esta cuenta; se intenta el respaldo.",
                            model,
                        )
                        break  # sin reintentos: probar el siguiente candidato
                    if not any(f in message for f in _RETRYABLE_FRAGMENTS):
                        raise LLMError(f"Llamada a OpenAI fallida: {exc}") from exc
                    if attempt == self.settings.openai_max_retries - 1:
                        raise LLMError(
                            f"Llamada a OpenAI fallida tras "
                            f"{self.settings.openai_max_retries} intentos: {exc}"
                        ) from exc
                    time.sleep(0.5 * (2**attempt))

        raise LLMError(
            f"Ningún modelo disponible entre {candidates}. Último error: {last}"
        ) from last

    # Combinación de parámetros que funcionó para cada modelo, para no pagar el
    # reintento de descubrimiento en cada llamada.
    _param_profile: dict[str, dict[str, Any]] = {}

    def _create_chat(
        self,
        model: str,
        messages: Sequence[dict[str, Any]],
        response_format: dict[str, Any],
        max_output_tokens: int,
        temperature: float,
    ) -> Any:
        """Crea una completion adaptando los parámetros que el modelo acepte.

        Prueba la combinación conocida para ese modelo; si la API rechaza un
        parámetro, aplica la corrección que el propio mensaje de error indica y
        la memoriza. Así el mismo código sirve para familias de modelos con
        contratos distintos sin fijar una lista de nombres en duro.
        """
        profile = dict(
            self._param_profile.get(
                model, {"token_param": "max_completion_tokens", "temperature": True}
            )
        )

        for _ in range(4):  # cada intento corrige a lo sumo un parámetro
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": list(messages),
                "response_format": response_format,
                profile["token_param"]: max_output_tokens,
            }
            if profile["temperature"]:
                kwargs["temperature"] = temperature
            try:
                result = self._sdk().chat.completions.create(**kwargs)
                self._param_profile[model] = profile
                return result
            except Exception as exc:  # noqa: BLE001 - se reclasifica
                message = str(exc).lower()
                if "temperature" in message and profile["temperature"]:
                    logger.info("El modelo '%s' no admite `temperature`; se omite.", model)
                    profile["temperature"] = False
                    continue
                swapped = next(
                    (
                        new
                        for old, new in _PARAM_ADAPTATIONS
                        if old == profile["token_param"] and f"'{old}'" in message
                    ),
                    None,
                )
                if swapped:
                    logger.info(
                        "El modelo '%s' usa `%s` en vez de `%s`.",
                        model,
                        swapped,
                        profile["token_param"],
                    )
                    profile["token_param"] = swapped
                    continue
                raise

        raise LLMError(f"No se encontró una combinación de parámetros válida para '{model}'.")

    # -- capacidades --------------------------------------------------------
    def chat_structured(
        self,
        schema: dict[str, Any],
        messages: Sequence[dict[str, Any]],
        *,
        schema_name: str = "respuesta",
        mock_fn=None,
        mock_hint: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_output_tokens: int = 900,
    ) -> dict[str, Any]:
        """Chat con salida estructurada estricta (JSON Schema), temperatura 0."""
        if self.mock:
            payload = mock_fn(mock_hint or {}) if mock_fn else {}
            rendered = json.dumps(payload, ensure_ascii=False)
            prompt_text = json.dumps(list(messages), ensure_ascii=False)
            t_in, t_out = estimate_tokens(prompt_text), estimate_tokens(rendered)
            self.usage.add_chat(t_in, t_out, 0.0, "mock")
            return payload

        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        }

        def _do(model: str) -> Any:
            return self._create_chat(
                model, messages, response_format, max_output_tokens, temperature
            )

        resp, model_used = self._call_with_retries(
            _do, self.settings.openai_chat_model, self.settings.openai_chat_fallback_model
        )
        content = resp.choices[0].message.content or "{}"
        usage = getattr(resp, "usage", None)
        t_in = getattr(usage, "prompt_tokens", None) or estimate_tokens(str(messages))
        t_out = getattr(usage, "completion_tokens", None) or estimate_tokens(content)
        self.usage.add_chat(t_in, t_out, self._cost_chat(t_in, t_out), model_used)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"El modelo devolvió JSON inválido: {content[:200]}") from exc

    def describe_image(
        self,
        images: Sequence[bytes],
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str = "",
        schema_name: str = "analisis_visual",
        mock_fn=None,
        mock_hint: dict[str, Any] | None = None,
        mime: str = "image/png",
        detail: str = "high",
        max_output_tokens: int = 900,
    ) -> dict[str, Any]:
        """Visión multimodal con salida estructurada. Acepta 1..n imágenes."""
        if self.mock:
            payload = mock_fn(mock_hint or {}) if mock_fn else {}
            rendered = json.dumps(payload, ensure_ascii=False)
            t_in = estimate_tokens(prompt) + 800 * len(images)  # coste fijo aprox. por imagen
            t_out = estimate_tokens(rendered)
            self.usage.add_chat(t_in, t_out, 0.0, "mock")
            return payload

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for raw in images:
            b64 = base64.b64encode(raw).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}", "detail": detail},
                }
            )
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})

        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        }

        def _do(model: str) -> Any:
            return self._create_chat(model, messages, response_format, max_output_tokens, 0.0)

        resp, model_used = self._call_with_retries(
            _do, self.settings.openai_vision_model, self.settings.openai_vision_fallback_model
        )
        text = resp.choices[0].message.content or "{}"
        usage = getattr(resp, "usage", None)
        t_in = getattr(usage, "prompt_tokens", None) or estimate_tokens(prompt)
        t_out = getattr(usage, "completion_tokens", None) or estimate_tokens(text)
        self.usage.add_chat(t_in, t_out, self._cost_chat(t_in, t_out), model_used)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"El modelo de visión devolvió JSON inválido: {text[:200]}") from exc

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        """Embeddings para la similitud con casos confirmados."""
        items = list(texts)
        if not items:
            return []
        if self.mock:
            total = sum(estimate_tokens(t) for t in items)
            self.usage.add_embedding(total, 0.0, "mock")
            return [mockmod.deterministic_embedding(t) for t in items]

        def _do(model: str) -> Any:
            return self._sdk().embeddings.create(model=model, input=items)

        resp, model_used = self._call_with_retries(
            _do,
            self.settings.openai_embedding_model,
            self.settings.openai_embedding_fallback_model,
        )
        usage = getattr(resp, "usage", None)
        t_in = getattr(usage, "prompt_tokens", None) or sum(estimate_tokens(t) for t in items)
        self.usage.add_embedding(t_in, self._cost_embedding(t_in), model_used)
        return [d.embedding for d in resp.data]
