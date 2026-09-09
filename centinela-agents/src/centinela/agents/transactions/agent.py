"""`TransactionAgent`: proceso A del producto.

Combina cuatro fuentes en una sola decisión explicable:

    score_final = W_RULES · (reglas + fuzzy) + W_SIM · similitud + W_MODEL · modelo

El modelo de lenguaje razona sobre evidencias ya calculadas; jamás decide solo
ni ve datos personales.
"""

from __future__ import annotations

import json
from typing import Any

from centinela.agents.base import AgentContext, BaseAgent
from centinela.agents.transactions import prompts as tx_prompts
from centinela.agents.transactions.features import canonical_text, derive_features
from centinela.agents.transactions.rules_config import build_engine
from centinela.agents.transactions.schemas import TransactionInput
from centinela.core import graph
from centinela.core.mock import mock_transaction_reasoning
from centinela.core.redaction import sanitize_customer_text
from centinela.core.vector_store import (
    NS_TRANSACTIONS,
    Neighbor,
    get_vector_store,
    stable_id,
)
from centinela.schemas import Decision, Evidence

NEIGHBOR_K = 5
# Similitud mínima para que un vecino cuente como señal. Por debajo, el coseno
# refleja ruido de la plantilla común más que un patrón compartido.
SIMILARITY_FLOOR = 0.55

VERDICTS = ("aprobar", "validacion_adicional", "bloquear")


class TransactionAgent(BaseAgent[TransactionInput]):
    process = "transaction"
    prompt_version = tx_prompts.PROMPT_VERSION

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.engine = build_engine()
        self.store = get_vector_store()

    # -- 1. perceive ---------------------------------------------------------
    def perceive(self, payload: TransactionInput, ctx: AgentContext) -> None:
        tx = (
            payload
            if isinstance(payload, TransactionInput)
            else TransactionInput.model_validate(payload)
        )
        ctx.raw_input = json.loads(tx.model_dump_json())
        ctx.normalized = {"transaction": tx}
        ctx.features = derive_features(tx)
        ctx.extra["transaction_id"] = tx.transaction_id

    # -- 2. enrich -----------------------------------------------------------
    def enrich(self, ctx: AgentContext) -> None:
        features = ctx.features
        tx: TransactionInput = ctx.normalized["transaction"]

        # 2.1 Reglas + score fuzzy.
        rules_score, fired, breakdown = self.engine.combined_score(
            features,
            {
                "amount_ratio": features["amount_ratio"],
                "velocity_score": features["velocity_score"],
                "distance_from_home_km": features["distance_from_home_km"],
            },
        )
        ctx.add_evidence(*fired)
        ctx.signals["rules"] = rules_score
        ctx.extra["rules_breakdown"] = breakdown

        # 2.2 Similitud con casos revisados.
        canonical = canonical_text(features)
        ctx.extra["canonical_text"] = canonical
        similarity_score, neighbors = self._similarity(canonical, ctx)
        if similarity_score is not None:
            ctx.signals["similarity"] = similarity_score

        # 2.3 Grafo ligero.
        graph_evidence, graph_notes = graph.analyze(
            tx.origin_account.id, tx.destination_account.id, tx.device.id
        )
        ctx.add_evidence(*graph_evidence)
        ctx.extra["graph_notes"] = graph_notes
        graph.record_edge(
            tx.origin_account.id,
            tx.destination_account.id,
            tx.device.id,
            features["amount_clp"],
            ctx.trace_id,
            tx.timestamp,
        )

    def _similarity(
        self, canonical: str, ctx: AgentContext
    ) -> tuple[float | None, list[Neighbor]]:
        """kNN sobre la memoria de casos confirmados.

        Devuelve `None` cuando no hay ningún caso comparable: una memoria vacía
        no es evidencia de inocencia, así que la fuente se marca como no
        disponible y su peso se reparte entre las otras dos.
        """
        try:
            vector = self.llm.embed([canonical])[0]
        except Exception as exc:  # noqa: BLE001 - la similitud es opcional
            ctx.extra["similarity_error"] = str(exc)
            return None, []

        neighbors = self.store.search(NS_TRANSACTIONS, vector, k=NEIGHBOR_K)
        ctx.neighbors = [n.as_dict() for n in neighbors]
        relevant = [n for n in neighbors if n.similarity >= SIMILARITY_FLOOR]
        fraud = [n for n in relevant if n.label == "fraude"]
        legit = [n for n in relevant if n.label == "legitimo"]

        if not relevant:
            score = None
        else:
            # Voto ponderado por similitud: fraudes empujan hacia 1, legítimos hacia 0.
            weight_fraud = sum(n.similarity for n in fraud)
            weight_total = sum(n.similarity for n in relevant)
            score = round(weight_fraud / weight_total, 4) if weight_total else None

        if fraud:
            top = max(n.similarity for n in fraud)
            ctx.add_evidence(
                Evidence(
                    type="similarity",
                    name="similar_confirmed_fraud",
                    value=[n.id for n in fraud],
                    weight=round(min(0.30, 0.30 * top), 4),
                    detail=(
                        f"Patrón similar a {len(fraud)} fraude(s) confirmado(s) "
                        f"(similitud máxima {top:.2f})"
                    ),
                )
            )
        elif legit:
            top = max(n.similarity for n in legit)
            ctx.add_evidence(
                Evidence(
                    type="similarity",
                    name="similar_reviewed_legitimate",
                    value=[n.id for n in legit],
                    weight=0.05,
                    detail=(
                        f"Patrón similar a {len(legit)} operación(es) revisada(s) y "
                        f"marcada(s) como legítimas (similitud {top:.2f})"
                    ),
                )
            )

        ctx.extra["fraud_neighbors"] = len(fraud)
        return score, neighbors

    # -- 3. reason -----------------------------------------------------------
    def reason(self, ctx: AgentContext) -> None:
        breakdown = ctx.extra.get("rules_breakdown", {})
        fired = [
            {"name": e.name, "weight": e.weight, "detail": e.detail}
            for e in ctx.evidence
            if e.type == "rule"
        ]
        user_prompt = tx_prompts.build_user_prompt(
            ctx.extra.get("canonical_text", ""),
            fired,
            breakdown.get("fuzzy_detail", {}),
            ctx.neighbors,
            ctx.extra.get("graph_notes", []),
        )
        messages = [
            {"role": "system", "content": tx_prompts.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        # Los prompts viven en la traza; jamás en la respuesta al cliente.
        ctx.prompts = {
            "system": tx_prompts.SYSTEM_PROMPT,
            "user": user_prompt,
            "version": tx_prompts.PROMPT_VERSION,
        }

        hint = {
            "rules_score": ctx.signals.get("rules", 0.0),
            "similarity_score": ctx.signals.get("similarity"),
            "fired_rules": [f["name"] for f in fired],
            "rule_details": [f["detail"] for f in fired],
            "neighbor_count": len(ctx.neighbors),
            "fraud_neighbors": ctx.extra.get("fraud_neighbors", 0),
            "graph_flag": (ctx.extra.get("graph_notes") or [None])[0],
        }
        try:
            result = self.llm.chat_structured(
                tx_prompts.REASONING_SCHEMA,
                messages,
                schema_name="evaluacion_transaccion",
                mock_fn=mock_transaction_reasoning,
                mock_hint=hint,
            )
        except Exception as exc:  # noqa: BLE001 - degradación controlada
            # Sin modelo, el sistema sigue decidiendo con reglas y similitud, y
            # marca el caso para revisión humana.
            ctx.extra["model_error"] = str(exc)
            result = mock_transaction_reasoning(hint)
            result["degraded"] = True

        ctx.reasoning = result
        ctx.signals["model"] = float(result.get("score", 0.0))

    # -- 4. decide -----------------------------------------------------------
    def decide(self, ctx: AgentContext) -> Decision:
        w_rules, w_sim, w_model = self.settings.tx_weights()
        score, combination = self.weighted_score(
            {
                "rules": (w_rules, ctx.signals.get("rules")),
                "similarity": (w_sim, ctx.signals.get("similarity")),
                "model": (w_model, ctx.signals.get("model")),
            }
        )
        ctx.extra["combination"] = combination

        verdict = self.classify(score, VERDICTS)
        # Prohibido bloquear sin revisión humana: el bloqueo es una derivación,
        # no una decisión final del sistema.
        requires_review = verdict == "bloquear"
        if ctx.reasoning.get("degraded"):
            requires_review = True

        ctx.extra["weights"] = {
            "rules": w_rules,
            "similarity": w_sim,
            "model": w_model,
            "score_rules": ctx.signals.get("rules", 0.0),
            "score_similarity": ctx.signals.get("similarity"),
            "score_model": ctx.signals.get("model", 0.0),
        }

        return Decision(
            trace_id=ctx.trace_id,
            process="transaction",
            verdict=verdict,  # type: ignore[arg-type]
            score=score,
            confidence=round(float(ctx.reasoning.get("confidence", 0.5)), 4),
            reasons=[str(r) for r in ctx.reasoning.get("reasons", [])][:5],
            requires_human_review=requires_review,
        )

    # -- 5. explain ----------------------------------------------------------
    def explain(self, decision: Decision, ctx: AgentContext) -> Decision:
        # El prompt le prohíbe al modelo revelar controles, pero un prompt no es
        # una garantía: se verifica el texto antes de devolverlo.
        customer, leaks = sanitize_customer_text(
            str(ctx.reasoning.get("explanation_customer", "")), decision.verdict
        )
        if leaks:
            ctx.extra["customer_text_redacted"] = {
                "terms": leaks,
                "original": str(ctx.reasoning.get("explanation_customer", "")),
            }

        ordered = ctx.sorted_evidence()
        similarity_note = (
            f"similitud {ctx.signals['similarity']:.2f}"
            if "similarity" in ctx.signals
            else "similitud sin datos comparables"
        )
        lines = [
            f"Veredicto {decision.verdict} · score {decision.score:.2f} "
            f"(reglas {ctx.signals.get('rules', 0):.2f} · "
            + similarity_note
            + f" · modelo {ctx.signals.get('model', 0):.2f}).",
            "Evidencias por peso:",
        ]
        lines.extend(f"  · [{e.type}] {e.name} ({e.weight:.2f}) — {e.detail}" for e in ordered[:10])
        if not ordered:
            lines.append("  · Sin señales activas.")
        model_note = str(ctx.reasoning.get("explanation_analyst", "")).strip()
        if model_note:
            lines.append(f"Lectura del modelo: {model_note}")
        if ctx.extra.get("customer_text_redacted"):
            lines.append(
                "El texto del modelo para el cliente se reemplazó por la redacción segura: "
                f"revelaba {', '.join(ctx.extra['customer_text_redacted']['terms'])}."
            )
        if ctx.extra.get("model_error"):
            lines.append(
                f"ATENCIÓN: el modelo no respondió ({ctx.extra['model_error']}). "
                "Decisión degradada a reglas + similitud; se derivó a revisión humana."
            )

        decision.explanation_customer = customer
        decision.explanation_analyst = "\n".join(lines)
        return decision


# --- Aprendizaje desde el feedback -------------------------------------------


def index_case_from_feedback(trace_id: str, label: str, llm: Any = None) -> bool:
    """Indexa un caso etiquetado por el analista en el vector store.

    Es el ciclo de aprendizaje sin reentrenar modelos: basta con actualizar la
    memoria de casos que alimenta la similitud.
    """
    from centinela.core.llm import LLMClient
    from centinela.core.tracing import get_trace_store

    detail = get_trace_store().get_case(trace_id)
    if detail is None:
        return False
    canonical = (detail.extra or {}).get("canonical_text")
    if not canonical:
        return False

    mapped = {"fraude_confirmado": "fraude", "legitimo": "legitimo"}.get(label)
    if mapped is None:
        return False

    client = llm or LLMClient()
    vector = client.embed([canonical])[0]
    get_vector_store().upsert(
        NS_TRANSACTIONS,
        stable_id(trace_id),
        canonical,
        vector,
        label=mapped,
        meta={"source": "analyst_feedback", "trace_id": trace_id},
    )
    return True
