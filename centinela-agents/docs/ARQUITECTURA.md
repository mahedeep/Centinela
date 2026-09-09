# Arquitectura

## Vista de componentes

```mermaid
flowchart TB
    subgraph front["Web app · React + TypeScript"]
        C[Cliente<br/>simular transacción · subir documento]
        A[Analista<br/>bandeja de revisión]
        S[Supervisor<br/>KPIs y costo]
    end

    subgraph api["API de agentes · FastAPI"]
        R[/Routers<br/>transactions · documents · cases · metrics · health/]
        BA[BaseAgent<br/>percibir → enriquecer → razonar → decidir → explicar → registrar]
        TA[TransactionAgent]
        DA[DocumentAgent]
    end

    subgraph core["Núcleo compartido"]
        LLM[llm.py<br/>chat estructurado · visión · embeddings · costo]
        RUL[rules.py<br/>reglas + lógica difusa]
        VS[vector_store.py<br/>coseno sobre SQLite]
        GR[graph.py<br/>cuenta ↔ destino ↔ dispositivo]
        TR[tracing.py<br/>trazas · métricas · retención]
        MK[mock.py<br/>respuestas deterministas]
    end

    subgraph ext["Externo"]
        OA[(OpenAI<br/>chat · visión · embeddings)]
        DB[(SQLite<br/>traces · feedback · vectors · graph_edges)]
        FS[(data/traces/<br/>imágenes con retención de 7 días)]
    end

    C & A & S -->|HTTPS · openapi.json| R
    R --> BA
    BA --> TA & DA
    TA --> RUL & VS & GR
    DA --> VS
    TA & DA --> LLM & TR
    LLM -->|MOCK_MODE=false| OA
    LLM -.->|MOCK_MODE=true| MK
    VS & TR & GR --> DB
    DA --> FS
```

## El ciclo del agente

Ambos procesos recorren el mismo ciclo. Lo que cambia son las señales que
enriquecen la decisión y los umbrales de negocio.

```mermaid
sequenceDiagram
    participant Cl as Consumidor (web app)
    participant Ag as Agente
    participant Se as Señales
    participant Mo as Modelo (OpenAI)
    participant Tr as Traza

    Cl->>Ag: entrada (transacción o documento)
    Ag->>Ag: perceive · validar, normalizar, derivar features
    Ag->>Se: enrich · reglas, difuso, similitud, grafo / visión, checks
    Se-->>Ag: evidencias con peso
    Ag->>Mo: reason · evidencias + JSON Schema estricto, temperatura 0
    Mo-->>Ag: score, confianza, razones, dos explicaciones
    Ag->>Ag: decide · pesos, umbrales, compuertas, revisión humana
    Ag->>Ag: explain · texto de cliente y texto de analista
    Ag->>Tr: log · entradas, prompts, modelo, tokens, costo, latencia
    Ag-->>Cl: Decision con trace_id
```

El modelo **no decide**: razona sobre evidencias ya calculadas y devuelve un JSON
validado. Los umbrales, los pesos y las compuertas viven en código, no en el
prompt. Esto es lo que hace la decisión auditable.

## Flujo de las dos señales de visión

```mermaid
flowchart LR
    F[Archivo<br/>JPG · PNG · PDF] --> P[preprocess.py<br/>PDF→imagen · orientación<br/>calidad · metadatos]
    P --> O[Capa OCR enchufable<br/>OcrEngine]
    O -->|vision| V1[Llamada 1<br/>clasificar + extraer + layout]
    O -->|tesseract| TL[OCR local<br/>texto plano]
    O -->|mock| MO[Ficha sintética]
    P --> V2[Llamada 2<br/>análisis forense]
    V1 & TL & MO --> CK[checks.py<br/>7 verificaciones deterministas]
    V2 --> FI[Hallazgos con región<br/>y confianza]
    CK & FI --> D[decide<br/>pesos + 4 compuertas]
    D --> R[DocumentDecision]
```

Nunca se envía el documento al modelo más de **dos veces** por evaluación: la
extracción y el forense. La comparación de firma es una tercera llamada solo
cuando se entrega un `reference_id`, y usa la página ya procesada.

## Ciclo de aprendizaje

```mermaid
flowchart LR
    D[Decisión con<br/>requires_human_review] --> B[Bandeja del analista]
    B --> E[Etiqueta:<br/>fraude confirmado · legítimo<br/>documento falso · auténtico]
    E -->|POST /feedback| G[Se guarda con el trace_id]
    G --> I[Se indexa el texto canónico<br/>en el vector store]
    I --> S[La similitud del<br/>siguiente caso mejora]
    S --> D
```

No se reentrena ningún modelo: basta con actualizar la memoria de casos que
alimenta la búsqueda por coseno. Es el ciclo «fraude → investigación →
etiquetado → evaluación» implementado con el costo de un embedding.

## Decisiones estructurales

| Decisión | Por qué |
|---|---|
| Un solo esquema de salida (`Decision`) para ambos procesos | Simplifica el front y la auditoría: una sola forma que aprender, una sola tabla que consultar |
| El front nunca llama a OpenAI | Toda la inteligencia y todo el costo quedan trazados en un solo lugar |
| `MOCK_MODE` en el cliente LLM, no en los agentes | El pipeline es idéntico con y sin red; lo único que cambia es de dónde viene la respuesta |
| Vector store detrás de una interfaz | SQLite + NumPy alcanza hasta ~10⁴ vectores; migrar a pgvector es cambiar una clase |
| Persistencia de imágenes solo en `data/traces/` con retención | Un único lugar que auditar y purgar |
| Modo sombra en `BaseAgent`, no en cada agente | Un piloto sin bloqueos no debe depender de que cada agente recuerde implementarlo |

## Límites conocidos

- Un embedding de texto captura **patrones descritos**, no la firma exacta de un
  fraude nuevo. La similitud ayuda a reconocer lo ya visto, no a anticipar lo
  inédito.
- La visión detecta señales **visibles**. Falla ante fotos de pantalla,
  hologramas y documentos de muy baja calidad; por eso existe la compuerta de
  calidad.
- El «grafo» son dos consultas de ventana móvil sobre una tabla de aristas, no un
  motor de grafos. Detecta cuenta recolectora y dispositivo compartido; no
  detecta anillos ni caminos largos.
- Los pesos y umbrales son valores iniciales. Exigen calibración con línea base y
  piloto en modo sombra antes de bloquear a nadie.
