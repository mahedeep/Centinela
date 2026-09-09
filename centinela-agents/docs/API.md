# Contrato de la API

Base: `{{API_BASE_URL}}` · versión `/api/v1` · todas las respuestas en JSON UTF-8.

Este documento describe los endpoints con ejemplos **capturados de la API real**
en modo mock. El contrato formal, con todos los esquemas, está en `openapi.json`
en la raíz del repositorio; se exporta en cada arranque.

## Índice

| Método | Ruta | Sección |
|---|---|---|
| `GET` | `/api/v1/health` | [Salud](#salud) |
| `POST` | `/api/v1/transactions/evaluate` | [Evaluar una transacción](#evaluar-una-transacción) |
| `POST` | `/api/v1/transactions/evaluate/batch` | [Lote de transacciones](#lote-de-transacciones) |
| `GET` | `/api/v1/transactions/rules` | [Catálogo de reglas](#catálogo-de-reglas) |
| `POST` | `/api/v1/documents/validate` | [Validar un documento](#validar-un-documento) |
| `POST` | `/api/v1/documents/references` | [Registrar una referencia](#registrar-una-referencia) |
| `GET` | `/api/v1/documents/{trace_id}/evidence` | [Regiones de los hallazgos](#regiones-de-los-hallazgos) |
| `GET` | `/api/v1/documents/{trace_id}/page/{n}` | [Imagen procesada](#imagen-procesada) |
| `GET` | `/api/v1/cases` | [Bandeja del analista](#bandeja-del-analista) |
| `GET` | `/api/v1/cases/{trace_id}` | [Detalle de un caso](#detalle-de-un-caso) |
| `POST` | `/api/v1/feedback` | [Feedback del analista](#feedback-del-analista) |
| `GET` | `/api/v1/metrics` | [Métricas](#métricas) |
| `GET` | `/api/v1/settings` | [Ajustes visibles](#ajustes-visibles) |

---

## Reglas de consumo

**Lo que el rol Cliente jamás debe ver.** `score`, `confidence`, `evidence`,
`checks`, `findings`, `reasons`, `explanation_analyst`, `model`, `tokens_*`,
`cost_usd`, `weights`, `prompts`. El único texto apto para el cliente es
`explanation_customer`.

**`trace_id` es el identificador universal.** Enlaza cualquier resultado con su
detalle. El prefijo indica el proceso: `tx-` o `doc-`.

**Códigos de error.**

| Código | Cuándo |
|---|---|
| `400` | Petición mal formada |
| `404` | `trace_id` inexistente, o página/imagen ya purgada por retención |
| `413` | Archivo sobre `MAX_UPLOAD_MB`, o lote sobre 200 transacciones |
| `415` | Formato de documento no soportado (solo JPG, PNG, PDF) |
| `422` | Validación de esquema, o etiqueta de feedback que no corresponde al proceso |
| `500` | Error inesperado del agente. El detalle va en `detail` |

Cuerpo de error:

```json
{ "detail": "El archivo supera el máximo de 10 MB.", "code": "error" }
```

---

## Salud

```bash
curl -s http://localhost:8000/api/v1/health
```

```json
{
  "status": "ok",
  "mock_mode": true,
  "shadow_mode": false,
  "version": "0.1.0",
  "openai_configured": false,
  "models": {
    "chat": "gpt-5.6-luna",
    "vision": "gpt-5.6-luna",
    "embedding": "text-embedding-3-small",
    "ocr_engine": "vision"
  }
}
```

Si `health` falla o no responde, el front debe mostrar un aviso persistente y
ofrecer activar el modo demo.

---

## Evaluar una transacción

`POST /api/v1/transactions/evaluate` → `Decision`

Los tres ejemplos siguientes producen los tres veredictos posibles.

### Ejemplo 1 · `aprobar`

Monto muy por debajo del promedio, beneficiario y dispositivo conocidos, sesión normal: ninguna regla se activa.

**Request**

```json
{
  "transaction_id": "TX-000101",
  "timestamp": "2026-09-08T14:32:10-03:00",
  "currency": "CLP",
  "origin_account": {
    "id": "ACC-1001",
    "age_days": 1450,
    "avg_monthly_amount": 900000,
    "country": "CL"
  },
  "customer_profile": {
    "segment": "persona_natural",
    "risk_tier": "medio"
  },
  "amount": 85000,
  "type": "pago",
  "channel": "app_movil",
  "destination_account": {
    "id": "ACC-7001",
    "bank": "OtroBanco",
    "is_new_beneficiary": false,
    "country": "CL"
  },
  "device": {
    "id": "DEV-12",
    "is_new_device": false,
    "os": "iOS",
    "ip_country": "CL",
    "vpn": false
  },
  "geo": {
    "lat": -33.45,
    "lon": -70.66,
    "distance_from_home_km": 2.1
  },
  "behavior": {
    "tx_last_hour": 0,
    "tx_last_24h": 1,
    "failed_logins_24h": 0,
    "session_seconds": 180
  }
}
```

**Response `200`**

```json
{
  "trace_id": "tx-0cf664e2bf3a455e",
  "process": "transaction",
  "verdict": "aprobar",
  "score": 0.0,
  "confidence": 0.55,
  "reasons": [
    "Sin señales de riesgo relevantes en esta operación"
  ],
  "evidence": [
    {
      "type": "similarity",
      "name": "similar_reviewed_legitimate",
      "value": [
        "98f3fa0a7542b0f7",
        "44570a2f42d591e7",
        "2eed692e70bb3ebf",
        "3100f573f881b049",
        "4aa65e8d096e532d"
      ],
      "weight": 0.05,
      "detail": "Patrón similar a 5 operación(es) revisada(s) y marcada(s) como legítimas (similitud 0.97)"
    }
  ],
  "requires_human_review": false,
  "shadow": false,
  "explanation_customer": "Tu operación se realizó correctamente.",
  "explanation_analyst": "Veredicto aprobar · score 0.00 (reglas 0.00 · similitud 0.00 · modelo 0.00).\nEvidencias por peso:\n  · [similarity] similar_reviewed_legitimate (0.05) — Patrón similar a 5 operación(es) revisada(s) y marcada(s) como legítimas (similitud 0.97)\nLectura del modelo: Evidencias consideradas: Sin señales de riesgo relevantes en esta operación",
  "model": "mock",
  "tokens_in": 661,
  "tokens_out": 75,
  "cost_usd": 0.0,
  "latency_ms": 24,
  "created_at": "2026-09-09T23:20:15.261745Z"
}
```

### Ejemplo 2 · `validacion_adicional`

Beneficiario nuevo con monto 1,4× el promedio mensual. Suficiente para pedir autenticación reforzada, insuficiente para bloquear.

**Request**

```json
{
  "transaction_id": "TX-000123",
  "timestamp": "2026-09-08T14:32:10-03:00",
  "currency": "CLP",
  "origin_account": {
    "id": "ACC-1001",
    "age_days": 1450,
    "avg_monthly_amount": 900000,
    "country": "CL"
  },
  "customer_profile": {
    "segment": "persona_natural",
    "risk_tier": "medio"
  },
  "amount": 1250000,
  "type": "transferencia",
  "channel": "app_movil",
  "destination_account": {
    "id": "ACC-7781",
    "bank": "OtroBanco",
    "is_new_beneficiary": true,
    "country": "CL"
  },
  "device": {
    "id": "DEV-55",
    "is_new_device": false,
    "os": "Android",
    "ip_country": "CL",
    "vpn": false
  },
  "geo": {
    "lat": -33.45,
    "lon": -70.66,
    "distance_from_home_km": 3.2
  },
  "behavior": {
    "tx_last_hour": 1,
    "tx_last_24h": 4,
    "failed_logins_24h": 1,
    "session_seconds": 95
  }
}
```

**Response `200`**

```json
{
  "trace_id": "tx-971103cd46ac4689",
  "process": "transaction",
  "verdict": "validacion_adicional",
  "score": 0.3841,
  "confidence": 0.7617,
  "reasons": [
    "Beneficiario nuevo recibiendo 1.3889× el promedio mensual del cliente",
    "Primera transferencia hacia esta cuenta de destino"
  ],
  "evidence": [
    {
      "type": "rule",
      "name": "new_beneficiary_amount_above_average",
      "value": true,
      "weight": 0.45,
      "detail": "Beneficiario nuevo recibiendo 1.3889× el promedio mensual del cliente"
    },
    {
      "type": "similarity",
      "name": "similar_confirmed_fraud",
      "value": [
        "f3a9eafad34b703c",
        "e6d839283b7b051b"
      ],
      "weight": 0.2912,
      "detail": "Patrón similar a 2 fraude(s) confirmado(s) (similitud máxima 0.97)"
    },
    {
      "type": "rule",
      "name": "new_beneficiary",
      "value": true,
      "weight": 0.1,
      "detail": "Primera transferencia hacia esta cuenta de destino"
    }
  ],
  "requires_human_review": false,
  "shadow": false,
  "explanation_customer": "Para confirmar que eres tú, vamos a pedirte un código de verificación antes de completar la operación.",
  "explanation_analyst": "Veredicto validacion_adicional · score 0.38 (reglas 0.37 · similitud 0.41 · modelo 0.38).\nEvidencias por peso:\n  · [rule] new_beneficiary_amount_above_average (0.45) — Beneficiario nuevo recibiendo 1.3889× el promedio mensual del cliente\n  · [similarity] similar_confirmed_fraud (0.29) — Patrón similar a 2 fraude(s) confirmado(s) (similitud máxima 0.97)\n  · [rule] new_beneficiary (0.10) — Primera transferencia hacia esta cuenta de destino\nLectura del modelo: Evidencias consideradas: Beneficiario nuevo recibiendo 1.3889× el promedio mensual del cliente; Primera transferencia hacia esta cuenta de destino",
  "model": "mock",
  "tokens_in": 705,
  "tokens_out": 132,
  "cost_usd": 0.0,
  "latency_ms": 5,
  "created_at": "2026-09-09T23:20:15.273146Z"
}
```

### Ejemplo 3 · `bloquear`

Dispositivo y beneficiario nuevos, IP extranjera con VPN, cinco intentos fallidos, sesión de 22 segundos y monto 4,3× el promedio: patrón de toma de cuenta.

**Request**

```json
{
  "transaction_id": "TX-000777",
  "timestamp": "2026-09-08T14:32:10-03:00",
  "currency": "CLP",
  "origin_account": {
    "id": "ACC-1001",
    "age_days": 1450,
    "avg_monthly_amount": 900000,
    "country": "CL"
  },
  "customer_profile": {
    "segment": "persona_natural",
    "risk_tier": "medio"
  },
  "amount": 3900000,
  "type": "transferencia",
  "channel": "web",
  "destination_account": {
    "id": "ACC-9091",
    "bank": "OtroBanco",
    "is_new_beneficiary": true,
    "country": "CL"
  },
  "device": {
    "id": "DEV-903",
    "is_new_device": true,
    "os": "Android",
    "ip_country": "BR",
    "vpn": true
  },
  "geo": {
    "lat": -23.55,
    "lon": -46.63,
    "distance_from_home_km": 640
  },
  "behavior": {
    "tx_last_hour": 3,
    "tx_last_24h": 7,
    "failed_logins_24h": 5,
    "session_seconds": 22
  }
}
```

**Response `200`**

```json
{
  "trace_id": "tx-23005b2f47cc4c10",
  "process": "transaction",
  "verdict": "bloquear",
  "score": 0.9216,
  "confidence": 1.0,
  "reasons": [
    "Beneficiario nuevo recibiendo 4.3333× el promedio mensual del cliente",
    "Dispositivo nuevo y beneficiario nuevo en la misma sesión: combinación típica de toma de cuenta",
    "Monto 4.3333× el promedio mensual de la cuenta",
    "La conexión proviene de un país distinto al de la cuenta",
    "Patrón similar a 5 caso(s) de fraude confirmado (similitud 1.00)"
  ],
  "evidence": [
    {
      "type": "rule",
      "name": "new_beneficiary_amount_above_average",
      "value": true,
      "weight": 0.45,
      "detail": "Beneficiario nuevo recibiendo 4.3333× el promedio mensual del cliente"
    },
    {
      "type": "rule",
      "name": "new_device_and_new_beneficiary",
      "value": true,
      "weight": 0.3,
      "detail": "Dispositivo nuevo y beneficiario nuevo en la misma sesión: combinación típica de toma de cuenta"
    },
    {
      "type": "similarity",
      "name": "similar_confirmed_fraud",
      "value": [
        "e818f296958e7a2c",
        "83c4e3629e22a669",
        "0047c7c264afbc31",
        "25a96858180c134d",
        "8d7d9dede166adea"
      ],
      "weight": 0.2913,
      "detail": "Patrón similar a 5 fraude(s) confirmado(s) (similitud máxima 0.97)"
    },
    {
      "type": "rule",
      "name": "amount_over_3x_average",
      "value": true,
      "weight": 0.25,
      "detail": "Monto 4.3333× el promedio mensual de la cuenta"
    },
    {
      "type": "rule",
      "name": "ip_country_mismatch",
      "value": true,
      "weight": 0.22,
      "detail": "La conexión proviene de un país distinto al de la cuenta"
    },
    {
      "type": "rule",
      "name": "failed_logins_3_or_more",
      "value": true,
      "weight": 0.18,
      "detail": "5 intentos de acceso fallidos en 24 horas"
    },
    {
      "type": "rule",
      "name": "vpn_with_high_amount",
      "value": true,
      "weight": 0.16,
      "detail": "VPN activa en una operación de monto alto"
    },
    {
      "type": "rule",
      "name": "new_beneficiary",
      "value": true,
      "weight": 0.1,
      "detail": "Primera transferencia hacia esta cuenta de destino"
    }
  ],
  "requires_human_review": true,
  "shadow": false,
  "explanation_customer": "Por seguridad dejamos esta operación en pausa mientras la revisamos. Un ejecutivo puede confirmarla contigo cuando quieras.",
  "explanation_analyst": "Veredicto bloquear · score 0.92 (reglas 0.85 · similitud 1.00 · modelo 0.97).\nEvidencias por peso:\n  · [rule] new_beneficiary_amount_above_average (0.45) — Beneficiario nuevo recibiendo 4.3333× el promedio mensual del cliente\n  · [rule] new_device_and_new_beneficiary (0.30) — Dispositivo nuevo y beneficiario nuevo en la misma sesión: combinación típica de toma de cuenta\n  · [similarity] similar_confirmed_fraud (0.29) — Patrón similar a 5 fraude(s) confirmado(s) (similitud máxima 0.97)\n  · [rule] amount_over_3x_average (0.25) — Monto 4.3333× el promedio mensual de la cuenta\n  · [rule] ip_country_mismatch (0.22) — La conexión proviene de un país distinto al de la cuenta\n  · [rule] failed_logins_3_or_more (0.18) — 5 intentos de acceso fallidos en 24 horas\n  · [rule] vpn_with_high_amount (0.16) — VPN activa en una operación de monto alto\n  · [rule] new_beneficiary (0.10) — Primera transferencia hacia esta cuenta de destino\nLectura del modelo: Evidencias consideradas: Beneficiario nuevo recibiendo 4.3333× el promedio mensual del cliente; Dispositivo nuevo y beneficiario nuevo en la misma sesión: combinación típica de toma de cuenta; Monto 4.3333× el promedio mensual de la cuenta; La conexión proviene de un país distinto al de la cuenta; Patrón similar a 5 caso(s) de fraude confirmado (similitud 1.00)",
  "model": "mock",
  "tokens_in": 821,
  "tokens_out": 243,
  "cost_usd": 0.0,
  "latency_ms": 5,
  "created_at": "2026-09-09T23:20:15.282119Z"
}
```

> Nota sobre el ejemplo 3: `requires_human_review` es `true`. Ningún bloqueo se
> emite sin derivación a una persona.

### Lote de transacciones

`POST /api/v1/transactions/evaluate/batch` → `Decision[]`

Máximo 200 por llamada. Útil para replay histórico y para correr el piloto en
modo sombra sobre tráfico real.

```json
{ "transactions": [ { "transaction_id": "TX-000101", "…": "…" } ] }
```

### Catálogo de reglas

`GET /api/v1/transactions/rules` — reglas y pesos vigentes, solo lectura. La
pantalla de Ajustes del Supervisor la muestra sin permitir editarla.

```json
{ "rules": [ { "name": "new_beneficiary_amount_above_average", "weight": 0.45, "description": "…" } ] }
```

---

## Validar un documento

`POST /api/v1/documents/validate` (multipart) → `DocumentDecision`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|:-:|---|
| `file` | archivo | Sí | JPG, PNG o PDF. Máximo 10 MB, 5 páginas |
| `document_type` | texto | No | `cedula`, `comprobante_domicilio`, `contrato`, `poder`, `liquidacion`, `firma`, `otro`. Si falta, el agente clasifica |
| `reference_id` | texto | No | Firma o plantilla registrada previamente, para comparar |
| `expected_fields` | JSON | No | Campo → valor declarado en el onboarding, para cruzar |

```bash
curl -s -X POST http://localhost:8000/api/v1/documents/validate \
  -F "file=@data/samples/cedula_ok.png" \
  -F "document_type=cedula" \
  -F 'expected_fields={"rut":"12.345.678-5"}'
```

### Ejemplo 1 · `autentico`

Todos los checks aplicables en `pass`, sin hallazgos forenses, calidad suficiente. (`cedula_ok.png`)

```json
{
  "trace_id": "doc-6a9fb6fa7af04f79",
  "process": "document",
  "verdict": "autentico",
  "score": 0.0269,
  "confidence": 0.786,
  "reasons": [
    "Campos extraídos consistentes y sin señales de alteración visibles"
  ],
  "evidence": [],
  "requires_human_review": false,
  "shadow": false,
  "explanation_customer": "Tu documento fue validado correctamente. No necesitas hacer nada más.",
  "explanation_analyst": "Veredicto autentico · score 0.03 (forense 0.05 · checks 0.00 · modelo 0.03).\nTipo detectado: cedula. Páginas: 1. Calidad: 0.96. Motor de extracción: mock.\nVerificaciones:\n  · PASS rut_modulo_11 — RUT 12.345.678-5 válido por módulo 11.\n  · PASS date_consistency — Las fechas extraídas son coherentes entre sí y con la fecha actual.\n  · PENDING arithmetic_consistency — No aplica a este tipo de documento.\n  · PENDING expected_fields_match — No se entregaron campos esperados para cruzar.\n  · PASS format_by_type — 2 campo(s) con el formato esperado para 'cedula'.\n  · PASS metadata_coherence — Los metadatos del archivo no muestran señales de edición.\n  · PENDING signature_match — No se entregó una firma de referencia para comparar.\nHallazgos forenses: ninguno.\nLectura del modelo: Checks en falla: ninguno. Hallazgos: ninguno. Calidad de imagen: 0.96.",
  "model": "mock",
  "tokens_in": 1588,
  "tokens_out": 89,
  "cost_usd": 0.0,
  "latency_ms": 58,
  "created_at": "2026-09-09T23:20:15.343828Z",
  "document_type_detected": "cedula",
  "fields": {
    "nombre": {
      "value": "MARÍA FICTICIA PÉREZ DE PRUEBA",
      "confidence": 0.95,
      "source": "vision"
    },
    "rut": {
      "value": "12.345.678-5",
      "confidence": 0.94,
      "source": "vision"
    },
    "fecha_nacimiento": {
      "value": "12/03/1988",
      "confidence": 0.93,
      "source": "vision"
    },
    "fecha_emision": {
      "value": "05/01/2022",
      "confidence": 0.92,
      "source": "vision"
    },
    "fecha_vencimiento": {
      "value": "05/01/2032",
      "confidence": 0.9,
      "source": "vision"
    },
    "numero_serie": {
      "value": "A123456789",
      "confidence": 0.88,
      "source": "vision"
    }
  },
  "checks": [
    {
      "name": "rut_modulo_11",
      "status": "pass",
      "detail": "RUT 12.345.678-5 válido por módulo 11.",
      "critical": true
    },
    {
      "name": "date_consistency",
      "status": "pass",
      "detail": "Las fechas extraídas son coherentes entre sí y con la fecha actual.",
      "critical": true
    },
    {
      "name": "arithmetic_consistency",
      "status": "pending",
      "detail": "No aplica a este tipo de documento.",
      "critical": true
    },
    {
      "name": "expected_fields_match",
      "status": "pending",
      "detail": "No se entregaron campos esperados para cruzar.",
      "critical": true
    },
    {
      "name": "format_by_type",
      "status": "pass",
      "detail": "2 campo(s) con el formato esperado para 'cedula'.",
      "critical": false
    },
    {
      "name": "metadata_coherence",
      "status": "pass",
      "detail": "Los metadatos del archivo no muestran señales de edición.",
      "critical": false
    },
    {
      "name": "signature_match",
      "status": "pending",
      "detail": "No se entregó una firma de referencia para comparar.",
      "critical": true
    }
  ],
  "findings": [],
  "pages_analyzed": 1,
  "image_quality": 0.96
}
```

### Ejemplo 2 · `sospechoso`

Los metadatos declaran software de edición de imagen. Es `warn`, no `fail`: basta para pedir el documento original y derivar a una persona, no para declararlo falso. (`comprobante_metadatos_editor.png`)

```json
{
  "trace_id": "doc-1bb64ea3ca244480",
  "process": "document",
  "verdict": "sospechoso",
  "score": 0.1194,
  "confidence": 0.786,
  "reasons": [
    "Campos extraídos consistentes y sin señales de alteración visibles",
    "metadatos con señales de edición: solicitar el documento original"
  ],
  "evidence": [
    {
      "type": "metadata",
      "name": "metadata_coherence",
      "value": "warn",
      "weight": 0.15,
      "detail": "Metadatos con señales de edición: los metadatos declaran software de edición de imagen (Adobe Photoshop 26.0 (Macintosh)); la fecha de modificación del archivo es posterior a la emisión."
    }
  ],
  "requires_human_review": true,
  "shadow": false,
  "explanation_customer": "Tu documento fue validado correctamente. No necesitas hacer nada más.",
  "explanation_analyst": "Veredicto sospechoso · score 0.12 (forense 0.05 · checks 0.20 · modelo 0.12).\nTipo detectado: comprobante_domicilio. Páginas: 1. Calidad: 0.96. Motor de extracción: mock.\nVerificaciones:\n  · PENDING rut_modulo_11 — No se extrajo un RUT del documento.\n  · PASS date_consistency — Las fechas extraídas son coherentes entre sí y con la fecha actual.\n  · PENDING arithmetic_consistency — No aplica a este tipo de documento.\n  · PENDING expected_fields_match — No se entregaron campos esperados para cruzar.\n  · PASS format_by_type — 1 campo(s) con el formato esperado para 'comprobante_domicilio'.\n  · WARN metadata_coherence — Metadatos con señales de edición: los metadatos declaran software de edición de imagen (Adobe Photoshop 26.0 (Macintosh)); la fecha de modificación del archivo es posterior a la emisión.\n  · PENDING signature_match — No se entregó una firma de referencia para comparar.\nHallazgos forenses: ninguno.\nCompuertas aplicadas: metadatos con señales de edición: solicitar el documento original.\nLectura del modelo: Checks en falla: ninguno. Hallazgos: ninguno. Calidad de imagen: 0.96.",
  "model": "mock",
  "tokens_in": 1610,
  "tokens_out": 89,
  "cost_usd": 0.0,
  "latency_ms": 53,
  "created_at": "2026-09-09T23:20:15.401055Z",
  "document_type_detected": "comprobante_domicilio",
  "fields": {
    "nombre": {
      "value": "MARÍA FICTICIA PÉREZ DE PRUEBA",
      "confidence": 0.93,
      "source": "vision"
    },
    "direccion": {
      "value": "Calle Inventada 1234, Comuna Ejemplo",
      "confidence": 0.91,
      "source": "vision"
    },
    "emisor": {
      "value": "Luz del Valle S.A.",
      "confidence": 0.95,
      "source": "vision"
    },
    "fecha_emision": {
      "value": "03/08/2026",
      "confidence": 0.92,
      "source": "vision"
    },
    "monto": {
      "value": "$ 38.450",
      "confidence": 0.9,
      "source": "vision"
    }
  },
  "checks": [
    {
      "name": "rut_modulo_11",
      "status": "pending",
      "detail": "No se extrajo un RUT del documento.",
      "critical": true
    },
    {
      "name": "date_consistency",
      "status": "pass",
      "detail": "Las fechas extraídas son coherentes entre sí y con la fecha actual.",
      "critical": true
    },
    {
      "name": "arithmetic_consistency",
      "status": "pending",
      "detail": "No aplica a este tipo de documento.",
      "critical": true
    },
    {
      "name": "expected_fields_match",
      "status": "pending",
      "detail": "No se entregaron campos esperados para cruzar.",
      "critical": true
    },
    {
      "name": "format_by_type",
      "status": "pass",
      "detail": "1 campo(s) con el formato esperado para 'comprobante_domicilio'.",
      "critical": false
    },
    {
      "name": "metadata_coherence",
      "status": "warn",
      "detail": "Metadatos con señales de edición: los metadatos declaran software de edición de imagen (Adobe Photoshop 26.0 (Macintosh)); la fecha de modificación del archivo es posterior a la emisión.",
      "critical": false
    },
    {
      "name": "signature_match",
      "status": "pending",
      "detail": "No se entregó una firma de referencia para comparar.",
      "critical": true
    }
  ],
  "findings": [],
  "pages_analyzed": 1,
  "image_quality": 0.96
}
```

### Ejemplo 3 · `falso`

El líquido a pagar no cuadra con bruto menos descuentos, y el forense detecta compresión distinta en los dígitos del monto. (`liquidacion_montos_editados.png`)

```json
{
  "trace_id": "doc-ca30c2470b354319",
  "process": "document",
  "verdict": "falso",
  "score": 0.8602,
  "confidence": 0.8527,
  "reasons": [
    "Verificación en falla: arithmetic_consistency",
    "Hallazgo forense: digit_retouch",
    "verificación crítica en falla (arithmetic_consistency)"
  ],
  "evidence": [
    {
      "type": "vision",
      "name": "digit_retouch",
      "value": {
        "page": 1,
        "x": 0.58,
        "y": 0.6,
        "width": 0.28,
        "height": 0.08
      },
      "weight": 0.74,
      "detail": "Los dígitos del monto líquido presentan compresión distinta al resto de la tabla."
    },
    {
      "type": "consistency",
      "name": "arithmetic_consistency",
      "value": "fail",
      "weight": 0.35,
      "detail": "La suma no cuadra: bruto 1,850,000 − descuentos 370,000 = 1,480,000, pero el documento declara 1,780,000."
    }
  ],
  "requires_human_review": true,
  "shadow": false,
  "explanation_customer": "No pudimos validar este documento en línea. Un ejecutivo te contactará para revisarlo contigo.",
  "explanation_analyst": "Veredicto falso · score 0.86 (forense 0.74 · checks 1.00 · modelo 0.86).\nTipo detectado: liquidacion. Páginas: 1. Calidad: 0.96. Motor de extracción: mock.\nVerificaciones:\n  · PASS rut_modulo_11 — RUT 12.345.678-5 válido por módulo 11.\n  · PASS date_consistency — Las fechas extraídas son coherentes entre sí y con la fecha actual.\n  · FAIL [CRÍTICO] arithmetic_consistency — La suma no cuadra: bruto 1,850,000 − descuentos 370,000 = 1,480,000, pero el documento declara 1,780,000.\n  · PENDING expected_fields_match — No se entregaron campos esperados para cruzar.\n  · PASS format_by_type — 1 campo(s) con el formato esperado para 'liquidacion'.\n  · PASS metadata_coherence — Los metadatos del archivo no muestran señales de edición.\n  · PENDING signature_match — No se entregó una firma de referencia para comparar.\nHallazgos forenses:\n  · digit_retouch (confianza 0.74) · región p1 (0.58, 0.60) — Los dígitos del monto líquido presentan compresión distinta al resto de la tabla.\nCompuertas aplicadas: verificación crítica en falla (arithmetic_consistency).\nLectura del modelo: Checks en falla: arithmetic_consistency. Hallazgos: digit_retouch. Calidad de imagen: 0.96.",
  "model": "mock",
  "tokens_in": 1639,
  "tokens_out": 157,
  "cost_usd": 0.0,
  "latency_ms": 68,
  "created_at": "2026-09-09T23:20:15.471503Z",
  "document_type_detected": "liquidacion",
  "fields": {
    "nombre": {
      "value": "MARÍA FICTICIA PÉREZ DE PRUEBA",
      "confidence": 0.94,
      "source": "vision"
    },
    "rut": {
      "value": "12.345.678-5",
      "confidence": 0.93,
      "source": "vision"
    },
    "periodo": {
      "value": "Agosto 2026",
      "confidence": 0.92,
      "source": "vision"
    },
    "monto_bruto": {
      "value": "$ 1.850.000",
      "confidence": 0.91,
      "source": "vision"
    },
    "monto_descuentos": {
      "value": "$ 370.000",
      "confidence": 0.9,
      "source": "vision"
    },
    "monto_liquido": {
      "value": "$ 1.780.000",
      "confidence": 0.89,
      "source": "vision"
    },
    "fecha_emision": {
      "value": "31/08/2026",
      "confidence": 0.92,
      "source": "vision"
    }
  },
  "checks": [
    {
      "name": "rut_modulo_11",
      "status": "pass",
      "detail": "RUT 12.345.678-5 válido por módulo 11.",
      "critical": true
    },
    {
      "name": "date_consistency",
      "status": "pass",
      "detail": "Las fechas extraídas son coherentes entre sí y con la fecha actual.",
      "critical": true
    },
    {
      "name": "arithmetic_consistency",
      "status": "fail",
      "detail": "La suma no cuadra: bruto 1,850,000 − descuentos 370,000 = 1,480,000, pero el documento declara 1,780,000.",
      "critical": true
    },
    {
      "name": "expected_fields_match",
      "status": "pending",
      "detail": "No se entregaron campos esperados para cruzar.",
      "critical": true
    },
    {
      "name": "format_by_type",
      "status": "pass",
      "detail": "1 campo(s) con el formato esperado para 'liquidacion'.",
      "critical": false
    },
    {
      "name": "metadata_coherence",
      "status": "pass",
      "detail": "Los metadatos del archivo no muestran señales de edición.",
      "critical": false
    },
    {
      "name": "signature_match",
      "status": "pending",
      "detail": "No se entregó una firma de referencia para comparar.",
      "critical": true
    }
  ],
  "findings": [
    {
      "name": "digit_retouch",
      "detail": "Los dígitos del monto líquido presentan compresión distinta al resto de la tabla.",
      "confidence": 0.74,
      "region": {
        "page": 1,
        "x": 0.58,
        "y": 0.6,
        "width": 0.28,
        "height": 0.08
      }
    }
  ],
  "pages_analyzed": 1,
  "image_quality": 0.96
}
```

### Registrar una referencia

`POST /api/v1/documents/references` (multipart) → `ReferenceResponse`

Registra una firma o plantilla contra la cual comparar después.

```bash
curl -s -X POST http://localhost:8000/api/v1/documents/references \
  -F "file=@data/samples/firma_referencia.png" -F "document_type=firma"
```

```json
{
  "reference_id": "REF-a1b2c3d4e5f6",
  "document_type": "firma",
  "stored_at": "2026-09-09T23:11:04.512Z",
  "message": "Referencia registrada. Úsala en `reference_id` al validar un documento."
}
```

### Regiones de los hallazgos

`GET /api/v1/documents/{trace_id}/evidence` → `EvidenceRegionsResponse`

Coordenadas **normalizadas** (0 a 1), donde `x,y` es la esquina superior
izquierda. El front las multiplica por el tamaño renderizado de la imagen.

```json
{
  "trace_id": "doc-9f2a1c8b4e6d0a35",
  "pages_analyzed": 1,
  "image_quality": 0.96,
  "artifacts_available": true,
  "findings": [
    {
      "name": "digit_retouch",
      "detail": "Los dígitos del monto líquido presentan compresión distinta al resto de la tabla.",
      "confidence": 0.74,
      "region": { "page": 1, "x": 0.58, "y": 0.6, "width": 0.28, "height": 0.08 }
    }
  ]
}
```

`artifacts_available: false` significa que la retención ya borró las imágenes:
el front debe mostrar los hallazgos como lista, sin el visor.

### Imagen procesada

`GET /api/v1/documents/{trace_id}/page/{n}` → `image/png`

La página tal como la vio el agente, para dibujar los recuadros encima. Devuelve
`404` cuando venció la retención (`TRACE_RETENTION_DAYS`, 7 días por defecto).
Solo para los roles Analista y Supervisor.

---

## Bandeja del analista

`GET /api/v1/cases` → `CaseSummary[]`

| Parámetro | Valores | Por defecto |
|---|---|---|
| `process` | `transaction`, `document` | todos |
| `verdict` | cualquiera de los seis | todos |
| `requires_human_review` | `true`, `false` | todos |
| `date_from`, `date_to` | ISO 8601 | sin límite |
| `order_by` | `score`, `created_at` | `score` (descendente) |
| `limit`, `offset` | 1–500, ≥ 0 | 100, 0 |

```bash
curl -s "http://localhost:8000/api/v1/cases?requires_human_review=true&order_by=score&limit=20"
```

```json
[
  {
    "trace_id": "tx-4c1e9a77b2d05f38",
    "process": "transaction",
    "verdict": "bloquear",
    "score": 0.9216,
    "confidence": 0.9,
    "requires_human_review": true,
    "shadow": false,
    "created_at": "2026-09-09T23:07:12.884Z",
    "cost_usd": 0.0,
    "latency_ms": 4,
    "feedback_label": null,
    "age_seconds": 182.4
  }
]
```

`age_seconds` alimenta el indicador de SLA de la bandeja.

## Detalle de un caso

`GET /api/v1/cases/{trace_id}` → `CaseDetail`

Devuelve la decisión más la traza interna: entradas, **prompts usados**,
`prompt_version`, pesos efectivos, vecinos recuperados y el feedback registrado.

**Solo para Analista y Supervisor.** Los prompts jamás deben llegar al cliente.

```json
{
  "decision": { "…": "el objeto Decision completo" },
  "inputs": { "transaction_id": "TX-000777", "amount": 3900000, "…": "…" },
  "prompts": { "system": "Eres un analista senior antifraude…", "user": "## Perfil de la operación…", "version": "tx-2026.09.09-v1" },
  "prompt_version": "tx-2026.09.09-v1",
  "weights": {
    "rules": 0.45, "similarity": 0.25, "model": 0.3,
    "score_rules": 0.8712, "score_similarity": null, "score_model": 0.9512
  },
  "neighbors": [ { "id": "a1b2c3d4e5f60718", "label": "fraude", "similarity": 0.61, "meta": { "patron": "account_takeover" } } ],
  "feedback": []
}
```

`score_similarity: null` significa que esa fuente no tenía casos comparables y su
peso se repartió entre las otras dos.

## Feedback del analista

`POST /api/v1/feedback` → `FeedbackAck`

Cierra el ciclo de aprendizaje: la etiqueta se guarda con el `trace_id` y el caso
se indexa en el vector store, de modo que la similitud mejora con cada revisión.

| Proceso | Etiquetas válidas |
|---|---|
| `transaction` | `fraude_confirmado`, `legitimo` |
| `document` | `documento_falso`, `documento_autentico` |

Una etiqueta del otro proceso devuelve `422`.

```json
{
  "trace_id": "tx-4c1e9a77b2d05f38",
  "label": "fraude_confirmado",
  "analyst": "ana.perez",
  "comment": "Cliente confirmó que no reconoce la operación."
}
```

```json
{
  "trace_id": "tx-4c1e9a77b2d05f38",
  "label": "fraude_confirmado",
  "indexed": true,
  "message": "Feedback registrado e indexado en la memoria de casos."
}
```

## Métricas

`GET /api/v1/metrics` → `MetricsResponse`

Acepta `date_from` y `date_to`. Alimenta el dashboard del Supervisor.

```json
{
  "generated_at": "2026-09-09T23:20:00Z",
  "total_volume": 312,
  "total_cost_usd": 0.041233,
  "cost_per_event_usd": 0.00013215,
  "feedback_count": 14,
  "estimated_accuracy": 0.857,
  "shadow_would_block": 0,
  "shadow_approved": 0,
  "by_process": [
    {
      "process": "transaction",
      "volume": 300,
      "block_rate": 0.06,
      "human_review_rate": 0.06,
      "latency_p50_ms": 4.0,
      "latency_p95_ms": 5.0,
      "cost_usd": 0.039,
      "cost_per_event_usd": 0.00013,
      "verdicts": [ { "verdict": "aprobar", "count": 273 }, { "verdict": "bloquear", "count": 18 } ]
    }
  ],
  "by_model": [ { "model": "mock", "events": 312, "tokens_in": 208431, "tokens_out": 27110, "cost_usd": 0.0 } ],
  "top_evidence": [ { "name": "new_beneficiary", "count": 41 } ],
  "timeseries": [ { "date": "2026-09-09", "verdict": "aprobar", "count": 273 } ]
}
```

`shadow_would_block` frente a `shadow_approved` alimenta la tarjeta «Piloto en
modo sombra»: cuántos casos *se habrían* bloqueado sin afectar a ningún cliente.

## Ajustes visibles

`GET /api/v1/settings` — umbrales, pesos, límites de documentos y precios.
Solo lectura, sin secretos. Pensado para la pantalla de Ajustes del Supervisor.

---

## Esquemas

### `Decision`

| Campo | Tipo | Descripción |
|---|---|---|
| `trace_id` | string | Identificador universal. Prefijo `tx-` o `doc-` |
| `process` | `transaction` \| `document` | Proceso que produjo la decisión |
| `verdict` | enum | `aprobar` \| `validacion_adicional` \| `bloquear` \| `autentico` \| `sospechoso` \| `falso` |
| `score` | 0–1 | Probabilidad de fraude o falsificación |
| `confidence` | 0–1 | Qué tan concluyentes son las evidencias |
| `reasons` | string[] | Frases cortas, máximo 5, ancladas a evidencias |
| `evidence` | `Evidence[]` | Ordenadas por peso descendente |
| `requires_human_review` | bool | `true` obliga a derivar a un analista |
| `shadow` | bool | `true` si `SHADOW_MODE` forzó el veredicto a `aprobar` |
| `explanation_customer` | string | **Único texto apto para el cliente** |
| `explanation_analyst` | string | Texto técnico, con evidencias y checks |
| `model` | string | Modelos que participaron |
| `tokens_in` / `tokens_out` | int | Consumo **de esta evaluación** |
| `cost_usd` | float | Costo estimado de esta evaluación |
| `latency_ms` | int | Tiempo total del ciclo |
| `created_at` | ISO 8601 | Momento de la decisión |

### `Evidence`

| Campo | Tipo | Descripción |
|---|---|---|
| `type` | enum | `rule` \| `similarity` \| `vision` \| `metadata` \| `consistency` |
| `name` | string | Identificador estable, en inglés |
| `value` | cualquiera | Valor observado |
| `weight` | 0–1 | Peso relativo dentro de su fuente |
| `detail` | string | Explicación en una frase, en español |

### `Check`

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | string | `rut_modulo_11`, `date_consistency`, `arithmetic_consistency`, `expected_fields_match`, `format_by_type`, `metadata_coherence`, `signature_match` |
| `status` | enum | `pass` \| `fail` \| `warn` \| `pending` |
| `detail` | string | Qué se verificó y con qué resultado |
| `critical` | bool | Si falla, el veredicto mínimo es `sospechoso` |

### `DocumentDecision`

Extiende `Decision` con `document_type_detected`, `fields` (campo → valor +
confianza), `checks`, `findings`, `pages_analyzed` e `image_quality`.

### `Finding`

`name`, `detail`, `confidence` (0–1) y `region` opcional
(`page`, `x`, `y`, `width`, `height`, normalizados a 0–1).
