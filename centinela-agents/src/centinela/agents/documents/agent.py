"""`DocumentAgent`: proceso B del producto.

    score_final = W_VISION · forense + W_CHECKS · checks + W_MODEL · modelo

Dos compuertas duras, previas a los umbrales:
- calidad de imagen por debajo de `MIN_IMAGE_QUALITY` → `sospechoso`;
- cualquier check crítico en `fail` → mínimo `sospechoso`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from centinela.agents.base import AgentContext, BaseAgent
from centinela.agents.documents import checks as dchecks
from centinela.agents.documents import prompts as doc_prompts
from centinela.agents.documents.ocr import OcrEngine, OcrResult, build_ocr_engine
from centinela.agents.documents.preprocess import PreparedDocument, prepare
from centinela.agents.documents.schemas import DocumentDecision, FieldValue
from centinela.core.redaction import sanitize_customer_text
from centinela.core.mock import (
    mock_document_reasoning,
    mock_signature_comparison,
    mock_vision_forensics,
)
from centinela.core.vector_store import (
    NS_DOCUMENTS,
    NS_TEMPLATES,
    get_vector_store,
    stable_id,
)
from centinela.schemas import Check, Evidence, Finding, Region

VERDICTS = ("autentico", "sospechoso", "falso")
NEIGHBOR_K = 5
SIMILARITY_FLOOR = 0.55

# --- Compuertas forenses -----------------------------------------------------
# La media ponderada del caso (0,40 forense + 0,35 checks + 0,25 modelo) tiene un
# límite estructural: con todos los checks en `pass` el score no puede superar
# 0,65, de modo que la evidencia forense por sí sola jamás alcanzaría el umbral
# de 0,70. Eso es incorrecto para el negocio: una alteración física confirmada es
# decisiva aunque la aritmética del documento cuadre. Estas compuertas corrigen
# ese límite con reglas explícitas y auditables, en vez de deformar los pesos.
FORENSIC_SUSPICIOUS_CONFIDENCE = 0.75  # un hallazgo así ⇒ mínimo sospechoso
FORENSIC_FAKE_CONFIDENCE = 0.80  # un hallazgo así ⇒ falso
FORENSIC_FAKE_COUNT_CONFIDENCE = 0.70  # dos hallazgos así ⇒ falso
FORENSIC_FAKE_COUNT = 2


@dataclass
class DocumentInput:
    """Entrada del proceso B, ya leída desde el multipart."""

    content: bytes
    filename: str = ""
    document_type: str | None = None
    reference_id: str | None = None
    expected_fields: dict[str, str] = field(default_factory=dict)


class DocumentAgent(BaseAgent[DocumentInput]):
    process = "document"
    prompt_version = doc_prompts.PROMPT_VERSION

    def __init__(self, *args: Any, ocr_engine: OcrEngine | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.store = get_vector_store()
        self.ocr: OcrEngine = ocr_engine or build_ocr_engine(self.llm, self.settings)

    # -- 1. perceive ---------------------------------------------------------
    def perceive(self, payload: DocumentInput, ctx: AgentContext) -> None:
        prepared: PreparedDocument = prepare(payload.content, payload.filename)
        ctx.normalized = {"prepared": prepared, "input": payload}
        ctx.raw_input = {
            "filename": payload.filename,
            "document_type_declared": payload.document_type,
            "reference_id": payload.reference_id,
            "expected_fields": payload.expected_fields,
            "size_bytes": len(payload.content),
        }
        ctx.features = {
            "image_quality": prepared.image_quality,
            "quality_detail": prepared.quality_detail,
            "pages_analyzed": prepared.pages_analyzed,
            "metadata": prepared.metadata,
        }
        ctx.artifacts_dir = str(self._persist_artifacts(prepared, ctx.trace_id))

    def _persist_artifacts(self, prepared: PreparedDocument, trace_id: str) -> Path:
        """Guarda las páginas en `data/traces/{trace_id}/`. Nada fuera de ahí."""
        directory = self.settings.traces_path / trace_id
        directory.mkdir(parents=True, exist_ok=True)
        for index, page in enumerate(prepared.pages, start=1):
            (directory / f"page-{index}.png").write_bytes(page)
        return directory

    # -- 2. enrich -----------------------------------------------------------
    def enrich(self, ctx: AgentContext) -> None:
        prepared: PreparedDocument = ctx.normalized["prepared"]
        payload: DocumentInput = ctx.normalized["input"]

        hint = {
            "source_name": payload.filename,
            "document_type_declared": payload.document_type,
            "image_quality": prepared.image_quality,
        }

        # 2.1 Extracción (llamada 1 de 2 al modelo con la imagen).
        ocr: OcrResult = self.ocr.extract(prepared.pages, hint)
        detected = ocr.document_type or payload.document_type or "otro"
        ctx.extra["ocr_engine"] = ocr.engine
        ctx.extra["document_type_detected"] = detected
        ctx.extra["fields"] = ocr.fields
        ctx.extra["layout"] = ocr.layout
        if payload.document_type and payload.document_type != detected:
            ctx.add_evidence(
                Evidence(
                    type="consistency",
                    name="declared_type_mismatch",
                    value=f"{payload.document_type} → {detected}",
                    weight=0.20,
                    detail=(
                        f"El documento se declaró como '{payload.document_type}' pero se "
                        f"clasificó como '{detected}'."
                    ),
                )
            )

        # 2.2 Forense (llamada 2 de 2).
        forensics = self._forensics(prepared, hint, ctx)
        findings = forensics["findings"]
        ctx.extra["findings"] = findings
        ctx.extra["unverifiable"] = forensics.get("unverifiable", [])
        ctx.signals["vision"] = float(forensics.get("manipulation_score", 0.0))
        for finding in findings[:6]:
            ctx.add_evidence(
                Evidence(
                    type="vision",
                    name=finding["name"],
                    value=finding.get("region"),
                    weight=round(min(1.0, float(finding.get("confidence", 0.0))), 4),
                    detail=finding.get("detail", ""),
                )
            )

        # 2.3 Firma contra referencia.
        signature_probability = self._compare_signature(prepared, payload, detected, hint, ctx)

        # 2.4 Checks deterministas.
        results = dchecks.run_all(
            ocr.fields,
            detected,
            prepared.metadata,
            payload.expected_fields or None,
            signature_probability,
            today=date.today(),
        )
        ctx.extra["checks"] = [c.model_dump() for c in results]
        ctx.signals["checks"] = dchecks.checks_score(results)
        for check in results:
            if check.status in ("fail", "warn"):
                ctx.add_evidence(
                    Evidence(
                        type="metadata" if check.name == "metadata_coherence" else "consistency",
                        name=check.name,
                        value=check.status,
                        weight=0.35 if (check.status == "fail" and check.critical) else 0.15,
                        detail=check.detail,
                    )
                )

        # 2.5 Similitud con plantillas y falsos confirmados.
        self._similarity(detected, ocr, ctx)

    def _forensics(
        self, prepared: PreparedDocument, hint: dict[str, Any], ctx: AgentContext
    ) -> dict[str, Any]:
        try:
            payload = self.llm.describe_image(
                prepared.pages[:1],
                doc_prompts.FORENSICS_PROMPT,
                doc_prompts.FORENSICS_SCHEMA,
                system=doc_prompts.FORENSICS_SYSTEM,
                schema_name="analisis_forense",
                mock_fn=mock_vision_forensics,
                mock_hint=hint,
            )
        except Exception as exc:  # noqa: BLE001 - se degrada, no se cae
            ctx.extra["forensics_error"] = str(exc)
            return {"findings": [], "manipulation_score": 0.0, "unverifiable": []}
        payload.setdefault("findings", [])
        payload.setdefault("unverifiable", [])
        return payload

    def _compare_signature(
        self,
        prepared: PreparedDocument,
        payload: DocumentInput,
        detected: str,
        hint: dict[str, Any],
        ctx: AgentContext,
    ) -> float | None:
        """Compara con la firma de referencia. None si no hay con qué comparar."""
        if not payload.reference_id:
            return None
        reference_path = self.settings.data_path / "references" / f"{payload.reference_id}.png"
        if not reference_path.exists():
            ctx.extra["signature_error"] = (
                f"La referencia '{payload.reference_id}' no está registrada."
            )
            return None
        if detected != "firma" and "firma" not in (ctx.extra.get("layout") or "").lower():
            ctx.extra["signature_note"] = (
                "El documento no declara firma visible; la comparación se ejecuta igual "
                "porque se entregó una referencia."
            )
        try:
            result = self.llm.describe_image(
                [prepared.pages[0], reference_path.read_bytes()],
                doc_prompts.SIGNATURE_PROMPT,
                doc_prompts.SIGNATURE_SCHEMA,
                system=doc_prompts.SIGNATURE_SYSTEM,
                schema_name="comparacion_firma",
                mock_fn=mock_signature_comparison,
                mock_hint=hint,
            )
        except Exception as exc:  # noqa: BLE001
            ctx.extra["signature_error"] = str(exc)
            return None

        probability = float(result.get("match_probability", 0.0))
        ctx.extra["signature"] = result
        if result.get("differences"):
            ctx.add_evidence(
                Evidence(
                    type="vision",
                    name="signature_differences",
                    value=result["differences"],
                    weight=round(min(0.35, 0.35 * (1.0 - probability)), 4),
                    detail="Diferencias con la firma de referencia: "
                    + "; ".join(str(d) for d in result["differences"][:3]),
                )
            )
        return probability

    def _similarity(self, detected: str, ocr: OcrResult, ctx: AgentContext) -> None:
        canonical = self._canonical_text(detected, ocr)
        ctx.extra["canonical_text"] = canonical
        try:
            vector = self.llm.embed([canonical])[0]
        except Exception as exc:  # noqa: BLE001
            ctx.extra["similarity_error"] = str(exc)
            return

        neighbors = self.store.search(NS_DOCUMENTS, vector, k=NEIGHBOR_K)
        templates = self.store.search(NS_TEMPLATES, vector, k=2)
        ctx.neighbors = [n.as_dict() for n in neighbors] + [n.as_dict() for n in templates]

        fakes = [n for n in neighbors if n.label == "falso" and n.similarity >= SIMILARITY_FLOOR]
        if fakes:
            top = max(n.similarity for n in fakes)
            ctx.add_evidence(
                Evidence(
                    type="similarity",
                    name="similar_confirmed_fake",
                    value=[n.id for n in fakes],
                    weight=round(min(0.25, 0.25 * top), 4),
                    detail=(
                        f"Estructura similar a {len(fakes)} documento(s) falso(s) "
                        f"confirmado(s) (similitud {top:.2f})"
                    ),
                )
            )
        matching_template = [n for n in templates if n.similarity >= SIMILARITY_FLOOR]
        if matching_template:
            top = max(n.similarity for n in matching_template)
            ctx.add_evidence(
                Evidence(
                    type="similarity",
                    name="matches_reference_template",
                    value=[n.id for n in matching_template],
                    weight=0.08,
                    detail=f"El layout coincide con una plantilla registrada (similitud {top:.2f})",
                )
            )

    @staticmethod
    def _canonical_text(detected: str, ocr: OcrResult) -> str:
        """Texto canónico: tipo + nombres de campo + layout. Sin valores personales."""
        names = ", ".join(sorted(ocr.fields.keys())) or "sin campos"
        return f"documento tipo {detected}; campos presentes: {names}; layout: {ocr.layout}"

    # -- 3. reason -----------------------------------------------------------
    def reason(self, ctx: AgentContext) -> None:
        user_prompt = doc_prompts.build_reasoning_prompt(
            ctx.extra.get("document_type_detected", "otro"),
            ctx.extra.get("fields", {}),
            ctx.extra.get("checks", []),
            ctx.extra.get("findings", []),
            ctx.neighbors,
            float(ctx.features.get("image_quality", 1.0)),
            ctx.extra.get("unverifiable", []),
        )
        messages = [
            {"role": "system", "content": doc_prompts.REASONING_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        ctx.prompts = {
            "system": doc_prompts.REASONING_SYSTEM,
            "user": user_prompt,
            "forensics_system": doc_prompts.FORENSICS_SYSTEM,
            "version": doc_prompts.PROMPT_VERSION,
        }

        checks_list = [Check.model_validate(c) for c in ctx.extra.get("checks", [])]
        hint = {
            "vision_score": ctx.signals.get("vision", 0.0),
            "checks_score": ctx.signals.get("checks", 0.0),
            "failed_checks": dchecks.failed_names(checks_list),
            "finding_names": [f["name"] for f in ctx.extra.get("findings", [])],
            "image_quality": ctx.features.get("image_quality", 1.0),
        }
        try:
            result = self.llm.chat_structured(
                doc_prompts.REASONING_SCHEMA,
                messages,
                schema_name="evaluacion_documento",
                mock_fn=mock_document_reasoning,
                mock_hint=hint,
            )
        except Exception as exc:  # noqa: BLE001
            ctx.extra["model_error"] = str(exc)
            result = mock_document_reasoning(hint)
            result["degraded"] = True

        ctx.reasoning = result
        ctx.signals["model"] = float(result.get("score", 0.0))

    # -- 4. decide -----------------------------------------------------------
    def decide(self, ctx: AgentContext) -> DocumentDecision:  # type: ignore[override]
        w_vision, w_checks, w_model = self.settings.doc_weights()
        score = (
            w_vision * ctx.signals.get("vision", 0.0)
            + w_checks * ctx.signals.get("checks", 0.0)
            + w_model * ctx.signals.get("model", 0.0)
        )
        score = round(max(0.0, min(1.0, score)), 4)

        checks_list = [Check.model_validate(c) for c in ctx.extra.get("checks", [])]
        quality = float(ctx.features.get("image_quality", 1.0))
        verdict = self.classify(score, VERDICTS)
        gate_reasons: list[str] = []
        rank = {"autentico": 0, "sospechoso": 1, "falso": 2}

        def escalate(target: str, reason: str) -> None:
            """Las compuertas solo pueden agravar el veredicto, nunca suavizarlo."""
            nonlocal verdict
            if rank[target] > rank[verdict]:
                verdict = target
            if reason not in gate_reasons:
                gate_reasons.append(reason)

        # Compuerta 1: calidad insuficiente. No se puede declarar auténtico algo
        # que no se pudo leer.
        if quality < self.settings.min_image_quality:
            escalate("sospechoso", "calidad insuficiente, solicitar nueva captura")

        # Compuerta 2: check crítico en falla (RUT inválido, fecha imposible,
        # aritmética que no cuadra, firma sin coincidencia).
        if dchecks.has_critical_failure(checks_list):
            failed = ", ".join(
                c.name for c in checks_list if c.status == "fail" and c.critical
            )
            escalate("sospechoso", f"verificación crítica en falla ({failed})")

        # Compuerta 3: evidencia forense concluyente.
        confidences = sorted(
            (float(f.get("confidence", 0.0)) for f in ctx.extra.get("findings", [])),
            reverse=True,
        )
        if confidences:
            strong = [c for c in confidences if c >= FORENSIC_FAKE_COUNT_CONFIDENCE]
            if confidences[0] >= FORENSIC_FAKE_CONFIDENCE:
                escalate(
                    "falso",
                    f"hallazgo forense concluyente (confianza {confidences[0]:.2f})",
                )
            elif len(strong) >= FORENSIC_FAKE_COUNT:
                escalate(
                    "falso",
                    f"{len(strong)} hallazgos forenses concordantes",
                )
            elif confidences[0] >= FORENSIC_SUSPICIOUS_CONFIDENCE:
                escalate(
                    "sospechoso",
                    f"hallazgo forense relevante (confianza {confidences[0]:.2f})",
                )

        # Compuerta 4: metadatos con señales de edición. Es `warn`, no `fail`: un
        # escaneo legítimo puede pasar por un editor. Basta para pedir el original
        # y derivar a una persona, jamás para declarar el documento falso.
        # Se puede desactivar con METADATA_WARN_GATE=false.
        if self.settings.metadata_warn_gate:
            metadata_warn = any(
                c.name == "metadata_coherence" and c.status == "warn" for c in checks_list
            )
            if metadata_warn:
                escalate(
                    "sospechoso",
                    "metadatos con señales de edición: solicitar el documento original",
                )

        requires_review = verdict in ("sospechoso", "falso")
        if ctx.reasoning.get("degraded"):
            requires_review = True

        ctx.extra["weights"] = {
            "vision": w_vision,
            "checks": w_checks,
            "model": w_model,
            "score_vision": ctx.signals.get("vision", 0.0),
            "score_checks": ctx.signals.get("checks", 0.0),
            "score_model": ctx.signals.get("model", 0.0),
        }
        ctx.extra["gate_reasons"] = gate_reasons

        reasons = [str(r) for r in ctx.reasoning.get("reasons", [])][:5]
        for gate in gate_reasons:
            if gate not in reasons:
                reasons.append(gate)

        findings = [
            Finding(
                name=f["name"],
                detail=f.get("detail", ""),
                confidence=float(f.get("confidence", 0.0)),
                region=Region.model_validate(f["region"]) if f.get("region") else None,
            )
            for f in ctx.extra.get("findings", [])
        ]
        fields = {
            name: FieldValue(
                value=str(entry.get("value", "")),
                confidence=float(entry.get("confidence", 0.0)),
                source=entry.get("source", "vision"),
            )
            for name, entry in (ctx.extra.get("fields") or {}).items()
        }

        return DocumentDecision(
            trace_id=ctx.trace_id,
            process="document",
            verdict=verdict,  # type: ignore[arg-type]
            score=score,
            confidence=round(float(ctx.reasoning.get("confidence", 0.5)), 4),
            reasons=reasons[:6],
            requires_human_review=requires_review,
            document_type_detected=ctx.extra.get("document_type_detected", "otro"),  # type: ignore[arg-type]
            fields=fields,
            checks=checks_list,
            findings=findings,
            pages_analyzed=int(ctx.features.get("pages_analyzed", 1)),
            image_quality=quality,
        )

    # -- 5. explain ----------------------------------------------------------
    def explain(self, decision: DocumentDecision, ctx: AgentContext) -> DocumentDecision:  # type: ignore[override]
        quality = float(ctx.features.get("image_quality", 1.0))

        if quality < self.settings.min_image_quality:
            # La compuerta de calidad manda sobre el texto del modelo: la acción
            # que el cliente debe ejecutar es tomar otra foto, no esperar.
            customer = (
                "Necesitamos una foto más nítida del documento. Tómala con buena luz, "
                "sin reflejos y con el documento completo dentro del cuadro."
            )
        else:
            # El prompt le prohíbe al modelo nombrar la señal forense detectada,
            # pero un prompt no es una garantía: se verifica antes de devolverlo.
            customer, leaks = sanitize_customer_text(
                str(ctx.reasoning.get("explanation_customer", "")), decision.verdict
            )
            if leaks:
                ctx.extra["customer_text_redacted"] = {
                    "terms": leaks,
                    "original": str(ctx.reasoning.get("explanation_customer", "")),
                }

        lines = [
            f"Veredicto {decision.verdict} · score {decision.score:.2f} "
            f"(forense {ctx.signals.get('vision', 0):.2f} · "
            f"checks {ctx.signals.get('checks', 0):.2f} · "
            f"modelo {ctx.signals.get('model', 0):.2f}).",
            f"Tipo detectado: {decision.document_type_detected}. "
            f"Páginas: {decision.pages_analyzed}. Calidad: {quality:.2f}. "
            f"Motor de extracción: {ctx.extra.get('ocr_engine', 'n/d')}.",
            "Verificaciones:",
        ]
        for check in decision.checks:
            marker = " [CRÍTICO]" if check.critical and check.status == "fail" else ""
            lines.append(f"  · {check.status.upper()}{marker} {check.name} — {check.detail}")

        if decision.findings:
            lines.append("Hallazgos forenses:")
            for finding in decision.findings:
                region = finding.region
                where = (
                    f" · región p{region.page} ({region.x:.2f}, {region.y:.2f})"
                    if region
                    else ""
                )
                lines.append(
                    f"  · {finding.name} (confianza {finding.confidence:.2f}){where} — "
                    f"{finding.detail}"
                )
        else:
            lines.append("Hallazgos forenses: ninguno.")

        if ctx.extra.get("gate_reasons"):
            lines.append("Compuertas aplicadas: " + "; ".join(ctx.extra["gate_reasons"]) + ".")
        if ctx.extra.get("unverifiable"):
            lines.append(
                "Pendiente por calidad de imagen: " + "; ".join(ctx.extra["unverifiable"][:3]) + "."
            )
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
                "Decisión degradada a checks + forense; se derivó a revisión humana."
            )

        decision.explanation_customer = customer
        decision.explanation_analyst = "\n".join(lines)
        return decision


# --- Aprendizaje y referencias ------------------------------------------------


def index_document_from_feedback(trace_id: str, label: str, llm: Any = None) -> bool:
    """Indexa un documento etiquetado por el analista en el vector store."""
    from centinela.core.llm import LLMClient
    from centinela.core.tracing import get_trace_store

    detail = get_trace_store().get_case(trace_id)
    if detail is None:
        return False
    canonical = (detail.extra or {}).get("canonical_text")
    if not canonical:
        return False

    mapped = {"documento_falso": "falso", "documento_autentico": "autentico"}.get(label)
    if mapped is None:
        return False

    client = llm or LLMClient()
    vector = client.embed([canonical])[0]
    get_vector_store().upsert(
        NS_DOCUMENTS,
        stable_id(trace_id),
        canonical,
        vector,
        label=mapped,
        meta={"source": "analyst_feedback", "trace_id": trace_id},
    )
    return True
