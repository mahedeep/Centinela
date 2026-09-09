# Centinela

Plataforma antifraude multimodal para banca. Dos procesos, dos agentes, una web
app con tres roles y un contrato de salida único, explicable y trazable.

Proyecto del curso *Advanced Prompt Engineering 4 Generative AI*, Universidad
Adolfo Ibáñez. **Todos los datos son sintéticos.**

---

## Los dos procesos

| | Entrada | Veredictos | Cómo decide |
|---|---|---|---|
| **A · Transacciones** | Monto, canal, dispositivo, geo, comportamiento | `aprobar` · `validacion_adicional` · `bloquear` | `0,45 · reglas+difuso + 0,25 · similitud + 0,30 · modelo` |
| **B · Documentos** | JPG, PNG o PDF (≤ 10 MB, ≤ 5 páginas) | `autentico` · `sospechoso` · `falso` | `0,40 · forense + 0,35 · checks + 0,25 · modelo` |

Ambos recorren el mismo ciclo —**percibir → enriquecer → razonar → decidir →
explicar → registrar**— y devuelven `Decision`: score, confianza, evidencias con
peso, dos explicaciones (cliente y analista), modelo, tokens, costo y latencia,
todo bajo un `trace_id`.

Toda decisión de bloqueo o documento falso pasa por una persona.

## Los dos repositorios

| Carpeta | Qué es |
|---|---|
| [`centinela-agents/`](centinela-agents/) | API de agentes. FastAPI + Pydantic + OpenAI (chat, visión, embeddings). Publica `openapi.json`, que es el contrato |
| [`centinela-web/`](centinela-web/) | Web app. React + TypeScript + Tailwind + Recharts. Tres roles: Cliente, Analista, Supervisor |
| `_insumos/` | Prompts del kit, ficha de producto y datos de prueba originales |

## Arrancar todo

```bash
# 1. API de agentes
cd centinela-agents
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env                       # MOCK_MODE=true funciona sin clave
python scripts/seed_synthetic.py           # memoria de casos + 1.000 transacciones
python scripts/make_sample_documents.py    # 12 documentos sintéticos
uvicorn centinela.main:app --reload --app-dir src

# 2. Web app, en otra terminal
cd centinela-web
npm install
cp .env.example .env                       # VITE_API_BASE_URL=http://localhost:8000
npm run dev                                # http://localhost:5173
```

La web queda en <http://localhost:5173> y la documentación interactiva de la API
en <http://localhost:8000/docs>.

### Con la clave de OpenAI

En `centinela-agents/.env`:

```bash
OPENAI_API_KEY=sk-...
MOCK_MODE=false
```

Los modelos por defecto son los que fija el kit (`gpt-5.6-luna`). Si tu cuenta
no los tiene, el cliente reintenta con el modelo de respaldo y lo anota en la
traza. El cliente también **adapta los parámetros** que cada familia de modelos
acepta (`max_tokens` frente a `max_completion_tokens`, temperatura fija o
configurable) y recuerda por modelo la combinación que funcionó.

## Verificar

```bash
cd centinela-agents
pytest                                      # 182 tests, sin red
bash scripts/smoke_test.sh                  # health + los seis veredictos + traza
python scripts/evaluate_transactions.py     # → reports/transactions_eval.md
python scripts/evaluate_documents.py        # → reports/documents_eval.md
```

Resultados sobre los datos del kit, en modo mock:

| Métrica | Resultado | Objetivo del MVP |
|---|---|---|
| Recall (transacciones, 300 casos etiquetados) | **0,96** | ≥ 0,80 |
| Falsos positivos | **0,015** | ≤ 0,05 |
| Precisión | 0,857 | — |
| Documentos con veredicto correcto | **12 / 12** | ≥ 10 / 12 con clave |

Contra OpenAI real, los tres documentos verificados (auténtico, fecha alterada,
montos editados) también dieron el veredicto esperado, con la visión extrayendo
los campos y detectando `typography_mismatch` y `background_patch` solo en los
alterados.

## Modos de operación

- **`MOCK_MODE=true`** — respuestas deterministas, sin red y sin costo. Es el
  modo por defecto y el que usan los tests y la demo.
- **`SHADOW_MODE=true`** — el agente calcula y registra todo, pero devuelve
  siempre `aprobar` con `shadow=true`. Permite pilotar sin bloquear a nadie; el
  dashboard muestra cuántos casos *se habrían* bloqueado.
- **Modo demo del front** — la web usa respuestas precargadas, sin backend.
  Se activa desde Ajustes o con `VITE_DEMO_MODE=true`.

## Qué se puede enchufar

- **El motor de OCR.** `OcrEngine` tiene tres implementaciones —visión
  multimodal (por defecto), Tesseract local y mock determinista— y agregar una
  cuarta (Document AI, Textract, Azure DI) es implementar un método. Los checks,
  el forense y el razonamiento consumen `OcrResult`, no el motor.
- **El vector store.** SQLite + NumPy detrás de la interfaz `VectorStore`;
  migrar a pgvector es cambiar una clase.
- **Los pesos y umbrales.** Todos por variable de entorno.

## Documentación

| Documento | Qué contiene |
|---|---|
| [`centinela-agents/README.md`](centinela-agents/README.md) | Instalación, endpoints, scripts, resolución de problemas |
| [`centinela-agents/docs/API.md`](centinela-agents/docs/API.md) | Contrato con ejemplos capturados de la API real |
| [`centinela-agents/docs/ARQUITECTURA.md`](centinela-agents/docs/ARQUITECTURA.md) | Diagramas del sistema, del ciclo y del aprendizaje |
| [`centinela-agents/docs/REGLAS.md`](centinela-agents/docs/REGLAS.md) | Cada regla, cada peso y cada función de pertenencia, justificados |
| [`centinela-agents/docs/DECISIONES.md`](centinela-agents/docs/DECISIONES.md) | Once decisiones de diseño con su alternativa descartada |
| [`centinela-web/README.md`](centinela-web/README.md) | Rutas, componentes, Supabase, accesibilidad, despliegue |

## Constantes del caso

- La revisión humana se mantiene en los casos complejos: es parte del diseño,
  no una excepción.
- Cero pasos, demoras o costos adicionales para el cliente.
- Toda decisión es explicable y trazable.
- Los flujos normativos (SP, CMF) permanecen intactos.
- Datos sintéticos; datos reales solo bajo gobierno y consentimiento.
