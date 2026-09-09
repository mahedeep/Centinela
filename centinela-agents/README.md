# Centinela · API de agentes antifraude

Plataforma antifraude multimodal para banca. Dos procesos, dos agentes, un solo
contrato de salida explicable y trazable.

| Proceso | Entrada | Veredictos |
|---|---|---|
| **A · Transacciones** | Una transacción (monto, canal, dispositivo, comportamiento) | `aprobar` · `validacion_adicional` · `bloquear` |
| **B · Documentos** | JPG, PNG o PDF (≤ 10 MB, ≤ 5 páginas) | `autentico` · `sospechoso` · `falso` |

Ambos agentes recorren el mismo ciclo —**percibir → enriquecer → razonar →
decidir → explicar → registrar**— y devuelven `Decision`: score, confianza,
evidencias con peso, dos explicaciones (cliente y analista), modelo, tokens,
costo y latencia, todo bajo un `trace_id`.

> **Datos sintéticos.** Proyecto académico (*Advanced Prompt Engineering 4
> Generative AI*, Universidad Adolfo Ibáñez). Ningún dato de ejemplo corresponde
> a una persona real. No procesar datos reales de clientes sin gobierno y
> consentimiento.

---

## Puesta en marcha en menos de 10 minutos

```bash
# 1. Entorno (Python 3.11+)
uv venv --python 3.11 .venv          # o: python3.11 -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"           # o: pip install -e ".[dev]"

# 2. Configuración
cp .env.example .env                 # MOCK_MODE=true funciona sin clave de OpenAI

# 3. Datos sintéticos y documentos de prueba
python scripts/seed_synthetic.py
python scripts/make_sample_documents.py

# 4. Arrancar
uvicorn centinela.main:app --reload --app-dir src

# 5. Verificar
curl -s localhost:8000/api/v1/health          # {"status":"ok","mock_mode":true,...}
bash scripts/smoke_test.sh
pytest
```

Documentación interactiva en <http://localhost:8000/docs>. El contrato
`openapi.json` se exporta a la raíz del repositorio en cada arranque.

### Con clave de OpenAI

```bash
# en .env
OPENAI_API_KEY=sk-...
MOCK_MODE=false
```

Los modelos por defecto son los que fija el kit del curso (`gpt-5.6-luna`). Si
ese identificador no existe en tu cuenta, el cliente **reintenta una vez con el
modelo de respaldo** (`OPENAI_CHAT_FALLBACK_MODEL`, por defecto `gpt-4o-mini`) y
lo deja anotado en la traza. Para evitar el reintento, fija directamente los
modelos que sí tienes habilitados:

```bash
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_VISION_MODEL=gpt-4o
```

---

## Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| `GET` | `/api/v1/health` | Estado, modo mock, modo sombra, modelos |
| `POST` | `/api/v1/transactions/evaluate` | Evalúa una transacción → `Decision` |
| `POST` | `/api/v1/transactions/evaluate/batch` | Lote de ≤ 200 (replay y modo sombra) |
| `GET` | `/api/v1/transactions/rules` | Catálogo de reglas y pesos vigentes |
| `POST` | `/api/v1/documents/validate` | Valida un documento (multipart) → `DocumentDecision` |
| `POST` | `/api/v1/documents/references` | Registra firma o plantilla → `reference_id` |
| `GET` | `/api/v1/documents/{trace_id}/evidence` | Regiones de los hallazgos, para dibujar |
| `GET` | `/api/v1/documents/{trace_id}/page/{n}` | Imagen procesada (sujeta a retención) |
| `GET` | `/api/v1/cases` | Bandeja del analista, filtrable |
| `GET` | `/api/v1/cases/{trace_id}` | Detalle con la traza completa |
| `POST` | `/api/v1/feedback` | Etiqueta del analista; indexa el caso |
| `GET` | `/api/v1/metrics` | KPIs, costo acumulado, modo sombra |
| `GET` | `/api/v1/settings` | Umbrales y pesos (solo lectura) |

Ejemplos completos de request y response en [`docs/API.md`](docs/API.md).

---

## Cómo decide

**Transacciones** — `score = 0,45 · reglas+fuzzy + 0,25 · similitud + 0,30 · modelo`

**Documentos** — `score = 0,40 · forense + 0,35 · checks + 0,25 · modelo`

Umbrales comunes: `< 0,35` → verde · `0,35–0,70` → ámbar · `≥ 0,70` → rojo con
revisión humana obligatoria. Dos compuertas duras en documentos: calidad de
imagen bajo `MIN_IMAGE_QUALITY` y check crítico en `fail` fuerzan como mínimo
`sospechoso`.

`explanation_customer` es el único texto apto para el cliente, y **se verifica
antes de devolverlo**: si el modelo revela un control —«dispositivo nuevo»,
«VPN», «tipografía distinta»— el texto se reemplaza por la redacción segura del
veredicto y el original queda en la traza.

El desglose de reglas, pesos y funciones de pertenencia está en
[`docs/REGLAS.md`](docs/REGLAS.md); la arquitectura, en
[`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md); las decisiones de diseño, en
[`docs/DECISIONES.md`](docs/DECISIONES.md).

### Modos de operación

- **`MOCK_MODE=true`** — respuestas deterministas, sin red y sin costo. Es el
  modo por defecto y el que usan los tests y la demo.
- **`SHADOW_MODE=true`** — el agente calcula y registra todo, pero devuelve
  siempre `aprobar` con `shadow=true`. Permite pilotar sin bloquear a nadie; el
  dashboard muestra cuántos casos *se habrían* bloqueado.

---

## Estructura

```
centinela-agents/
├── src/centinela/
│   ├── config.py            Settings (pydantic-settings)
│   ├── main.py              FastAPI, CORS, export de openapi.json
│   ├── schemas/             Decision, Evidence, Check, Feedback, métricas
│   ├── core/
│   │   ├── llm.py           chat estructurado · visión · embeddings · costo
│   │   ├── vector_store.py  interfaz + SQLite/NumPy (coseno)
│   │   ├── rules.py         motor de reglas + lógica difusa
│   │   ├── graph.py         grafo ligero cuenta ↔ destino ↔ dispositivo
│   │   ├── tracing.py       trazas, métricas, retención
│   │   ├── mock.py          respuestas deterministas
│   │   └── db.py            SQLAlchemy 2.0
│   ├── agents/
│   │   ├── base.py          BaseAgent: el ciclo común
│   │   ├── transactions/    features · reglas · prompts · agente
│   │   └── documents/       preproceso · ocr · checks · prompts · agente
│   └── api/                 routers
├── scripts/                 seed, muestras, evaluación, smoke test
├── tests/                   pytest, sin red
└── docs/                    API · ARQUITECTURA · REGLAS · DECISIONES
```

---

## La capa de OCR es enchufable

`src/centinela/agents/documents/ocr.py` define un contrato único, `OcrEngine`,
con tres implementaciones:

| Motor | `OCR_ENGINE` | Qué hace |
|---|---|---|
| `VisionOcrEngine` | `vision` *(por defecto)* | Modelo multimodal de OpenAI: clasifica, extrae campos con confianza y describe el layout en una llamada |
| `TesseractOcrEngine` | `tesseract` | OCR local, solo texto plano. Contingencia offline. Requiere `pip install -e ".[ocr-local]"` y el binario `tesseract` |
| `MockOcrEngine` | `mock` | Determinista, sin red. Lee las fichas `data/samples/*.fields.json` |

En `MOCK_MODE=true` siempre se usa el mock, sea cual sea `OCR_ENGINE`: ningún
motor toca la red durante tests o demos.

**Para agregar un motor nuevo** (Google Document AI, AWS Textract, Azure
Document Intelligence) basta con implementar `OcrEngine.extract` y registrarlo
en `build_ocr_engine`. Nada más del pipeline cambia: los checks, el forense y el
razonamiento consumen `OcrResult`, no el motor.

---

## Scripts

```bash
python scripts/seed_synthetic.py         # 1.000 transacciones + 20 casos confirmados
python scripts/load_xlsx.py <ruta.xlsx>  # carga el set de prueba del kit
python scripts/make_sample_documents.py  # 12 documentos sintéticos en data/samples/
python scripts/evaluate_transactions.py  # → reports/transactions_eval.md
python scripts/evaluate_documents.py     # → reports/documents_eval.md
bash scripts/smoke_test.sh               # health + los tres veredictos con curl
```

## Docker

```bash
docker compose up --build     # API en http://localhost:8000
```

## Variables de entorno

Todas están documentadas una por una en [`.env.example`](.env.example). Las que
más se tocan:

| Variable | Por defecto | Para qué |
|---|---|---|
| `OPENAI_API_KEY` | — | Clave de OpenAI. Sin ella solo funciona `MOCK_MODE=true` |
| `MOCK_MODE` | `true` | Respuestas deterministas sin red ni costo |
| `SHADOW_MODE` | `false` | Piloto sin bloquear: registra todo, devuelve `aprobar` |
| `THRESHOLD_REVIEW` / `THRESHOLD_BLOCK` | `0.35` / `0.70` | Umbrales de los tres veredictos |
| `OCR_ENGINE` | `vision` | Motor de extracción documental |
| `MIN_IMAGE_QUALITY` | `0.40` | Bajo este valor el veredicto mínimo es `sospechoso` |
| `TRACE_RETENTION_DAYS` | `7` | Días antes de borrar las imágenes procesadas |
| `ALLOWED_ORIGINS` | `localhost:5173,...` | CORS para la web app |

## Si algo no arranca

**`ModuleNotFoundError: No module named 'centinela'`**

En macOS, `uv` crea los archivos `.pth` del *editable install* con el flag
`UF_HIDDEN`, y `site.py` de Python **salta los `.pth` ocultos** sin avisar. El
resultado es un paquete instalado que no se puede importar. Dos salidas:

```bash
# a) quitar el flag
chflags nohidden .venv/lib/python3.11/site-packages/*.pth

# b) no depender del editable install
PYTHONPATH=src python scripts/seed_synthetic.py
PYTHONPATH=src python -m pytest
uvicorn centinela.main:app --app-dir src
```

Nada del repositorio depende del editable install: `pytest` usa
`pythonpath = ["src"]` de `pyproject.toml`, los scripts ajustan `sys.path` con
`scripts/_bootstrap.py`, y `uvicorn` acepta `--app-dir src`.

**El modelo devuelve 404.** `gpt-5.6-luna` es el identificador que fija el kit
del curso. Si tu cuenta no lo tiene, el cliente reintenta una vez con
`OPENAI_CHAT_FALLBACK_MODEL` y lo anota en la traza. Para evitar el reintento,
fija en `.env` los modelos que sí tengas habilitados.

**`pypdfium2` no instala.** Trae binarios precompilados para macOS, Linux y
Windows; si tu plataforma no está cubierta, el resto del sistema funciona igual
y solo se pierde la conversión de PDF a imagen (los JPG y PNG siguen andando).

**El front no puede llamar a la API.** Agrega su origen a `ALLOWED_ORIGINS`.
Cualquier puerto de `localhost` y los subdominios de Lovable ya están permitidos
por expresión regular en `main.py`.

---

## Licencia

MIT. Proyecto académico con datos sintéticos.
