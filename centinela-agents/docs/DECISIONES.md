# Registro de decisiones (ADR corto)

Una entrada por decisión que costó pensar. Formato: contexto → decisión →
consecuencia.

---

## ADR-001 · Un solo esquema de salida para ambos procesos

**Contexto.** Transacciones y documentos producen veredictos distintos
(`aprobar/validacion_adicional/bloquear` frente a `autentico/sospechoso/falso`)
y evidencias de naturaleza distinta.

**Decisión.** Ambos devuelven `Decision`. El proceso de documentos lo extiende
con `DocumentDecision`, que **agrega** campos sin cambiar los existentes.

**Consecuencia.** El front tiene una sola forma que aprender y la auditoría una
sola tabla que consultar. El costo es que `verdict` es una unión de seis valores
y el consumidor debe saber cuáles corresponden a cada proceso; se documenta en
`API.md` y el campo `process` lo desambigua.

---

## ADR-002 · OR ruidosa en lugar de suma ponderada para las reglas

**Contexto.** Con una suma normalizada, agregar una regla nueva de peso bajo
reduce el score de casos ya bien clasificados, y obliga a recalibrar el catálogo
completo cada vez.

**Decisión.** `score = 1 − Π(1 − wᵢ)` sobre las reglas activadas.

**Consecuencia.** El score queda acotado en `[0, 1]` sin normalización
arbitraria, es monótono y agregar reglas es incremental. El costo es que los
pesos ya no se leen como «porcentaje del total» y hay que explicarlos; se hace en
`REGLAS.md`.

---

## ADR-003 · Renormalizar los pesos sobre las fuentes disponibles

**Contexto.** La similitud pesa 0,25 en transacciones. Con la memoria de casos
vacía —las primeras semanas de operación— su score sería 0 y el máximo alcanzable
quedaría en 0,75, distorsionando la calibración justo cuando el sistema más se
observa.

**Decisión.** Una fuente sin datos vale `None`, no `0`. Su peso se reparte
proporcionalmente entre las que sí aportaron. La traza registra qué fuentes
participaron y con qué peso efectivo.

**Consecuencia.** Los umbrales significan lo mismo con y sin memoria de casos. El
costo es que dos decisiones con el mismo score pueden provenir de combinaciones
distintas; por eso `weights` y `combination` van en la traza.

---

## ADR-004 · Compuertas explícitas en documentos, en vez de deformar los pesos

**Contexto.** Con la media ponderada del caso (0,40 forense + 0,35 checks + 0,25
modelo), un documento con todos los checks en `pass` alcanza como máximo 0,65: por
debajo del umbral de 0,70. Una alteración física evidente en un documento cuya
aritmética cuadra jamás podría declararse falsa.

**Decisión.** Cuatro compuertas que solo pueden **agravar** el veredicto: calidad
insuficiente, check crítico en falla, evidencia forense concluyente (≥ 0,80, o
dos ≥ 0,70) y metadatos con señales de edición.

**Alternativa descartada.** Subir el peso de la visión hasta que el caso encaje.
Se descartó porque deforma la calibración de todos los demás casos para resolver
uno, y porque una compuerta explícita es auditable mientras que un peso inflado
no se puede explicar a un regulador.

**Consecuencia.** El sistema puede condenar un documento por evidencia forense
sola, y la razón queda escrita en `gate_reasons`. La compuerta de metadatos es la
más agresiva —marca como sospechoso un escaneo legítimo procesado con un editor—
y por eso es desactivable con `METADATA_WARN_GATE=false`.

---

## ADR-005 · Capa de OCR detrás de una interfaz

**Contexto.** El caso exige que la extracción principal sea el modelo multimodal,
pero el motor de extracción es exactamente la pieza que más probablemente cambie:
Document AI, Textract, Azure DI o un OCR local, según costo, latencia y
requisitos de residencia de datos.

**Decisión.** `OcrEngine` con un único método, `extract(pages, hint) → OcrResult`.
Tres implementaciones: `VisionOcrEngine` (por defecto), `TesseractOcrEngine`
(local, desactivado) y `MockOcrEngine` (determinista). La fábrica
`build_ocr_engine` fuerza el mock cuando `MOCK_MODE=true`, sea cual sea
`OCR_ENGINE`.

**Consecuencia.** Cambiar de motor no toca los checks, el forense ni el
razonamiento: todos consumen `OcrResult`. El costo es una capa de indirección que
no se paga hasta el segundo motor.

---

## ADR-006 · Los prompts viven en la traza, jamás en la respuesta

**Contexto.** La explicabilidad regulatoria exige poder reconstruir por qué el
sistema decidió lo que decidió en una fecha dada. Al mismo tiempo, exponer los
prompts al cliente revelaría los controles.

**Decisión.** `prompts` y `prompt_version` se guardan en `TraceRow` y se exponen
solo en `GET /cases/{trace_id}`, endpoint de analista y supervisor.
`explanation_customer` se valida en tests contra una lista de términos
prohibidos.

**Consecuencia.** La auditoría es posible sin que el cliente vea los controles. El
costo es que cada cambio de prompt exige subir `PROMPT_VERSION`, o la traza deja
de ser reconstruible.

---

## ADR-007 · Degradación controlada cuando el modelo falla

**Contexto.** Si OpenAI no responde, la alternativa a decidir sin modelo es
devolver un 500 y dejar la operación sin evaluar.

**Decisión.** Ante una excepción del modelo, el agente usa el razonamiento mock
sobre las evidencias ya calculadas, marca `degraded=true`, fuerza
`requires_human_review=true` y registra el error en la traza y en
`explanation_analyst`.

**Consecuencia.** El sistema nunca deja una operación sin veredicto, y cuando
opera degradado siempre hay una persona mirando. El costo es que un caso
degradado consume tiempo de analista aunque el score sea bajo.

---

## ADR-008 · El acumulador de consumo es por evaluación, no por agente

**Contexto.** El endpoint batch y los scripts de evaluación reutilizan una misma
instancia de agente. Con un acumulador de vida larga, cada decisión reportaba el
consumo acumulado de todas las anteriores: en una corrida de 300 casos, el
costo por evento salía 150 veces sobrevalorado.

**Decisión.** `BaseAgent.run` crea un `UsageAccumulator` nuevo en cada llamada.

**Consecuencia.** El costo por evento es correcto en batch y en los reportes de
evaluación. Un test lo fija (`test_usage_is_per_evaluation_not_per_agent`).

---

## ADR-009 · Modo sombra en la clase base

**Contexto.** El piloto sin bloqueos es una constante del caso, no una
característica opcional de un agente.

**Decisión.** `apply_shadow` vive en `BaseAgent` y se aplica después de
`explain`. El veredicto real y `requires_human_review` reales quedan en
`extra.real_verdict`, que es lo que lee el dashboard del supervisor.

**Consecuencia.** Un agente nuevo hereda el modo sombra sin escribir una línea.
El costo es que el consumidor ve `aprobar` mientras la traza dice otra cosa; el
campo `shadow=true` lo hace explícito y el dashboard lo separa.

---

## ADR-010 · SQLite y NumPy como vector store del MVP

**Contexto.** El MVP necesita búsqueda por similitud sobre unos pocos miles de
casos. Un motor vectorial dedicado agrega una dependencia de infraestructura que
el proyecto académico no puede sostener.

**Decisión.** Embeddings como JSON en SQLite, coseno exacto con NumPy, detrás de
la interfaz `VectorStore`.

**Consecuencia.** Cero infraestructura extra y búsqueda exacta hasta ~10⁴
vectores. Sobre ese volumen la latencia crece linealmente y hay que migrar a
pgvector; la interfaz existe justamente para eso.

---

## ADR-011 · Verificar el texto del cliente, no confiar en el prompt

**Contexto.** Los prompts del sistema le prohíben al modelo revelar controles en
`explanation_customer`. En la primera prueba contra el modelo real, la respuesta
fue: «Verifica que reconoces el acceso, el dispositivo y el beneficiario». No
menciona reglas ni scores —cumple la letra de la instrucción— pero le dice al
cliente exactamente qué señales se activaron. Un prompt es una petición, no una
garantía, y este es un requisito que el negocio no puede dejar al azar: revelar
el control le enseña al defraudador qué evitar, y a un cliente legítimo le
comunica que se sospecha de él.

**Decisión.** `core/redaction.py` verifica el texto contra una lista de términos
prohibidos —mecánica de la decisión, señales de transacción, señales forenses y
calificaciones acusatorias— comparando sin tildes ni mayúsculas. Si detecta uno
solo, descarta el texto completo y devuelve la redacción segura del veredicto.
El original y los términos detectados quedan en la traza
(`extra.customer_text_redacted`) y se anotan en `explanation_analyst`.

**Por qué descartar el texto completo y no tachar palabras.** Tachar deja frases
rotas y no garantiza que el resto no siga revelando el control por contexto
(«detectamos algo inusual en el equipo desde el que te conectas» no contiene
ningún término prohibido y revela lo mismo). Es preferible un texto genérico
correcto a uno específico parcialmente censurado.

**Consecuencia.** El criterio de aceptación «`explanation_customer` jamás
menciona reglas, umbrales, modelos ni similitudes» pasa de ser una esperanza a
ser verificable, y hay un test por cada término. El costo es que el sistema
pierde la redacción específica que el modelo podría haber escrito bien; la traza
guarda el original para poder ajustar el prompt con evidencia en vez de por
intuición. Tras reforzar los prompts con ejemplos correctos e incorrectos, el
modelo real dejó de activar la barrera.
