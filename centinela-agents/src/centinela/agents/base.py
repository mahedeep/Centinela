"""`BaseAgent`: el ciclo común de ambos procesos.

    perceive → enrich → reason → decide → explain → log

Cada agente concreto completa los métodos abstractos; la orquestación, la
trazabilidad, el modo sombra y la contabilidad de costo viven aquí y no se
duplican.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from centinela.config import Settings, get_settings
from centinela.core.llm import LLMClient, UsageAccumulator
from centinela.core.tracing import TraceStore, get_trace_store, new_trace_id
from centinela.schemas import Decision, Evidence, utcnow

InputT = TypeVar("InputT")


@dataclass
class AgentContext:
    """Estado mutable que atraviesa el ciclo. Es lo que se guarda en la traza."""

    trace_id: str
    process: str
    raw_input: dict[str, Any] = field(default_factory=dict)
    normalized: dict[str, Any] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    signals: dict[str, float] = field(default_factory=dict)
    neighbors: list[dict[str, Any]] = field(default_factory=list)
    prompts: dict[str, Any] = field(default_factory=dict)
    reasoning: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    artifacts_dir: str = ""

    def add_evidence(self, *items: Evidence) -> None:
        self.evidence.extend(items)

    def sorted_evidence(self) -> list[Evidence]:
        """Las evidencias que ve el analista van ordenadas por peso descendente."""
        return sorted(self.evidence, key=lambda e: e.weight, reverse=True)


class BaseAgent(ABC, Generic[InputT]):
    """Orquestador del ciclo. No decide nada por su cuenta: delega en el agente."""

    process: str = "transaction"
    prompt_version: str = "v0"

    def __init__(
        self,
        settings: Settings | None = None,
        llm: LLMClient | None = None,
        trace_store: TraceStore | None = None,
    ):
        self.settings = settings or get_settings()
        self.usage = UsageAccumulator()
        self.llm = llm or LLMClient(self.settings, usage=self.usage)
        # Si nos inyectan un cliente, compartimos su acumulador para no perder costo.
        self.usage = self.llm.usage
        self.traces = trace_store or get_trace_store()

    # -- ciclo (a implementar por cada agente) --------------------------------
    @abstractmethod
    def perceive(self, payload: InputT, ctx: AgentContext) -> None:
        """Valida la entrada, normaliza y deriva features."""

    @abstractmethod
    def enrich(self, ctx: AgentContext) -> None:
        """Agrega señales: reglas, similitud, visión, consistencia."""

    @abstractmethod
    def reason(self, ctx: AgentContext) -> None:
        """Llama al modelo con salida estructurada y guarda el resultado."""

    @abstractmethod
    def decide(self, ctx: AgentContext) -> Decision:
        """Combina scores, aplica umbrales y la política de revisión humana."""

    @abstractmethod
    def explain(self, decision: Decision, ctx: AgentContext) -> Decision:
        """Produce las dos explicaciones (cliente y analista)."""

    # -- utilidades compartidas ----------------------------------------------
    def classify(self, score: float, labels: tuple[str, str, str]) -> str:
        """Aplica los dos umbrales configurables a un score y devuelve la etiqueta."""
        low, mid, high = labels
        if score >= self.settings.threshold_block:
            return high
        if score >= self.settings.threshold_review:
            return mid
        return low

    @staticmethod
    def weighted_score(
        parts: dict[str, tuple[float, float | None]]
    ) -> tuple[float, dict[str, Any]]:
        """Combina fuentes ponderadas, **renormalizando sobre las disponibles**.

        Una fuente sin datos (`None`) no vale cero: vale nada. Si la memoria de
        casos está vacía, la similitud no debe arrastrar el score hacia abajo y
        volver imposible alcanzar el umbral de bloqueo; su peso se reparte entre
        las fuentes que sí tienen algo que decir.

        `parts` mapea nombre → (peso, score o None si la fuente no aportó).
        """
        available = {k: (w, s) for k, (w, s) in parts.items() if s is not None}
        total_weight = sum(w for w, _ in available.values())
        if total_weight <= 0:
            return 0.0, {"available": [], "renormalized": False}

        score = sum(w * s for w, s in available.values()) / total_weight
        breakdown: dict[str, Any] = {
            "available": sorted(available),
            "unavailable": sorted(set(parts) - set(available)),
            "renormalized": len(available) != len(parts),
            "effective_weights": {
                k: round(w / total_weight, 4) for k, (w, _) in available.items()
            },
        }
        return round(max(0.0, min(1.0, score)), 4), breakdown

    def apply_shadow(self, decision: Decision) -> Decision:
        """SHADOW_MODE: se registra todo, pero al consumidor se le devuelve `aprobar`.

        Permite pilotar sin bloquear a nadie. El veredicto real queda en la traza
        (`extra.real_verdict`), que es lo que lee el dashboard del supervisor.
        """
        if not self.settings.shadow_mode:
            return decision
        decision.shadow = True
        decision.requires_human_review = False
        decision.verdict = "aprobar"
        decision.explanation_customer = "Tu operación se realizó correctamente."
        return decision

    def log(self, decision: Decision, ctx: AgentContext) -> None:
        ctx.extra.setdefault("usage", self.usage.as_dict())
        self.traces.save(
            decision,
            inputs=ctx.raw_input,
            prompts=ctx.prompts,
            extra=ctx.extra,
            prompt_version=self.prompt_version,
            artifacts_dir=ctx.artifacts_dir,
        )

    # -- entrada pública ------------------------------------------------------
    def run(self, payload: InputT, trace_id: str | None = None) -> Decision:
        started = time.perf_counter()
        # El acumulador es por evaluación, no por agente: un mismo agente se
        # reutiliza en el endpoint batch y en los scripts de evaluación, y cada
        # decisión debe reportar solo sus propios tokens y su propio costo.
        self.usage = UsageAccumulator()
        self.llm.usage = self.usage
        ctx = AgentContext(
            trace_id=trace_id or new_trace_id(self.process), process=self.process
        )

        self.perceive(payload, ctx)
        self.enrich(ctx)
        self.reason(ctx)
        decision = self.decide(ctx)
        decision = self.explain(decision, ctx)

        real_verdict = decision.verdict
        real_review = decision.requires_human_review
        decision = self.apply_shadow(decision)
        if decision.shadow:
            ctx.extra["real_verdict"] = real_verdict
            ctx.extra["real_requires_human_review"] = real_review

        decision.trace_id = ctx.trace_id
        decision.process = self.process  # type: ignore[assignment]
        decision.model = self.usage.model_label
        decision.tokens_in = self.usage.tokens_in
        decision.tokens_out = self.usage.tokens_out
        decision.cost_usd = self.usage.cost_usd
        decision.latency_ms = int((time.perf_counter() - started) * 1000)
        decision.created_at = utcnow()
        decision.evidence = ctx.sorted_evidence()

        ctx.extra["neighbors"] = ctx.neighbors
        ctx.extra["signals"] = ctx.signals
        ctx.extra["features"] = ctx.features
        self.log(decision, ctx)
        return decision
