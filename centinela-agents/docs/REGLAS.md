# Reglas, lógica difusa y checks

Este documento justifica cada regla, cada peso y cada función de pertenencia.
Los valores son **iniciales**: exigen calibración con línea base y piloto en
modo sombra antes de bloquear a nadie.

---

## Proceso A · Transacciones

### Cómo se combinan las reglas

No se suman. Se combinan con una **OR ruidosa**:

```
score_reglas = 1 − Π (1 − wᵢ)     para cada regla i que se activó
```

Tres motivos para no usar una suma:

1. El resultado queda acotado en `[0, 1]` sin normalizaciones arbitrarias.
2. Es monótona: agregar una regla nunca baja el score.
3. Agregar una regla débil no diluye a las fuertes. Con una suma normalizada,
   incorporar una regla nueva de peso bajo *reduciría* el score de casos que ya
   estaban bien clasificados, y habría que recalibrar todo el catálogo cada vez.

El score que consume el agente mezcla la OR ruidosa con el score difuso:

```
score_fuente_reglas = 0,60 · OR_ruidosa + 0,40 · score_difuso
```

Las reglas aportan conocimiento discreto y auditable; la lógica difusa evita que
un corte duro decida el caso por sí solo (un monto de 2,99× el promedio no es
materialmente distinto de uno de 3,01×).

### Catálogo de reglas

| Peso | Regla | Se activa cuando | Por qué ese peso |
|---:|---|---|---|
| 0,45 | `new_beneficiary_amount_above_average` | Beneficiario nuevo y monto > 1,2× el promedio mensual | Patrón de pago único de la ingeniería social (falso ejecutivo, arriendo o compra inexistente): el dinero sale una vez, a alguien a quien el cliente nunca transfirió, por sobre lo que mueve al mes. Peso alto a propósito: por sí sola debe alcanzar el umbral de validación adicional —el negocio quiere resolver este caso con un código, no con una llamada— pero jamás el de bloqueo. |
| 0,30 | `new_device_and_new_beneficiary` | Dispositivo nuevo **y** beneficiario nuevo en la misma sesión | Firma de toma de cuenta. Por separado ambas señales son comunes y benignas; juntas, en la misma sesión, casi nunca lo son. |
| 0,30 | `structuring_pattern` | ≥ 4 operaciones en una hora, monto < 0,5× el promedio, beneficiario nuevo | Fraccionamiento: el defraudador parte el monto para quedar bajo el control de monto. Cada operación aislada parece inofensiva; la firma es la combinación velocidad + beneficiario nuevo + monto bajo. |
| 0,25 | `amount_over_3x_average` | Monto > 3× el promedio mensual | Desviación fuerte del comportamiento propio del cliente. No es concluyente por sí sola (un pie de auto es legítimo), por eso no llega a bloquear sola. |
| 0,22 | `ip_country_mismatch` | País de la IP ≠ país de la cuenta | Señal potente, pero con falsos positivos reales: clientes de viaje. Peso alto sin llegar a decisivo. |
| 0,20 | `velocity_over_5_per_hour` | > 5 transacciones en la última hora | Vaciado de cuenta o automatización. Se acota a la hora porque el día completo diluye la señal. |
| 0,18 | `failed_logins_3_or_more` | ≥ 3 intentos de acceso fallidos en 24 h | Indica intento de acceso por terceros. Se pone en 3 y no en 1 porque olvidar la clave es cotidiano. |
| 0,16 | `vpn_with_high_amount` | VPN activa **y** monto ≥ 1.000.000 CLP | La VPN sola es común y legítima; combinada con monto alto, encubre ubicación en el momento que más importa. |
| 0,15 | `account_age_under_30_days` | Cuenta de origen con < 30 días | Cuentas recién abiertas concentran el uso como cuenta puente. |
| 0,14 | `cross_border_new_beneficiary` | Beneficiario nuevo en otro país | Dificulta la recuperación de los fondos, lo que sube el costo esperado del error. |
| 0,12 | `session_under_20_seconds` | Sesión de < 20 s antes de operar | Un humano legítimo mira saldo, escribe y confirma. Una sesión de segundos sugiere guion automatizado o instrucción dictada por teléfono. |
| 0,12 | `night_hours_with_geo_anomaly` | 00:00–06:00 **y** ≥ 150 km del domicilio | Ninguna de las dos condiciones sola dice mucho; juntas describen el patrón nocturno desde ubicación inusual. |
| 0,10 | `new_beneficiary` | Primera transferencia a esa cuenta | Señal débil: la mayoría de los beneficiarios nuevos son legítimos. Suma poco, pero acompaña a las combinaciones peligrosas. |

### Funciones de pertenencia

Tres conjuntos difusos por variable (bajo / medio / alto). Los dos primeros son
trapezoidales `(a, b, c, d)`: valen 0 antes de `a`, suben hasta 1 en `[b, c]` y
bajan a 0 en `d`. El conjunto «alto» es una rampa creciente `(a, b)`.

La defuzzificación es un centroide sobre riesgos `{bajo: 0, medio: 0,5, alto: 1}`.

| Variable | Peso | Bajo | Medio | Alto (rampa) | Por qué esos cortes |
|---|---:|---|---|---|---|
| `amount_ratio` | 0,40 | (−1; 0; 0,8; 1,5) | (0,8; 1,5; 2,5; 3,5) | (2,5 → 4,0) | Gastar menos que el promedio mensual es lo normal. La zona 1,5–3,5× es donde conviven el pie de un auto y el fraude, y por eso es «media». Sobre 4× el promedio, el riesgo satura. |
| `velocity_score` | 0,35 | (−1; 0; 0,20; 0,40) | (0,20; 0,40; 0,60; 0,80) | (0,55 → 0,85) | `velocity_score` mezcla 70 % de la actividad de la última hora y 30 % de las 24 h: lo inmediato pesa más que lo acumulado. |
| `distance_from_home_km` | 0,25 | (−1; 0; 20; 60) | (20; 60; 150; 300) | (150 → 500) | 20 km es el radio de la vida cotidiana; sobre 150 km ya no se explica por un desplazamiento normal. |

### Score final

```
score = 0,45 · reglas+difuso + 0,25 · similitud + 0,30 · modelo
```

**Renormalización sobre fuentes disponibles.** Si una fuente no aportó datos
—típicamente la similitud, cuando la memoria de casos aún está vacía— su peso se
reparte entre las que sí. Una memoria vacía no es evidencia de inocencia: si su
score contara como 0, el máximo alcanzable sería 0,75 y la calibración de los
umbrales quedaría distorsionada durante las primeras semanas de operación, que
es justo cuando el sistema más se observa.

### Umbrales

| Score | Veredicto | Revisión humana |
|---|---|---|
| < 0,35 | `aprobar` | No |
| 0,35 – 0,70 | `validacion_adicional` | No |
| ≥ 0,70 | `bloquear` | **Sí, obligatoria** |

Ningún bloqueo se emite sin `requires_human_review=true`. El bloqueo es una
derivación a una persona, no una decisión final del sistema.

---

## Proceso B · Documentos

### Checks deterministas

Se ejecutan en Python, sin modelo: son reproducibles y explicables sin apelar a
una red neuronal. Ninguno se omite; si no aplica, queda en `pending`.

| Check | Crítico | Qué verifica | Cuándo falla |
|---|:-:|---|---|
| `rut_modulo_11` | Sí | Dígito verificador por módulo 11 | El dígito no corresponde al cuerpo del RUT |
| `date_consistency` | Sí | Emisión < vencimiento, emisión ≤ hoy, edad coherente | Vencimiento anterior a la emisión, fecha futura, edad > 120 años |
| `arithmetic_consistency` | Sí | Liquidaciones: bruto − descuentos = líquido (tolerancia 0,5 %) | La suma no cuadra |
| `expected_fields_match` | Sí | Cruce contra lo declarado en el onboarding | El valor leído difiere del declarado |
| `signature_match` | Sí | Comparación con la firma de referencia | Probabilidad de coincidencia < 0,60 |
| `format_by_type` | No | Regex por campo según el tipo de documento | El formato no corresponde al tipo |
| `metadata_coherence` | No | EXIF / metadatos PDF | Software de edición, o modificación posterior a la emisión |

`metadata_coherence` es `warn` y no `fail` a propósito: un escaneo legítimo puede
pasar por un editor de imagen. Basta para pedir el documento original, no para
declararlo falso.

### Score de los checks

También OR ruidosa, con pesos por severidad:

| Estado | Crítico | Peso |
|---|:-:|---:|
| `fail` | Sí | 1,00 |
| `fail` | No | 0,45 |
| `warn` | Sí | 0,25 |
| `warn` | No | 0,20 |
| `pass` / `pending` | — | 0,00 |

Un `fail` crítico satura el score; varios `warn` no.

### Score final y compuertas

```
score = 0,40 · forense + 0,35 · checks + 0,25 · modelo
```

Los umbrales son los mismos que en transacciones (0,35 / 0,70), pero antes se
aplican cuatro compuertas que **solo pueden agravar** el veredicto:

| # | Compuerta | Efecto |
|---|---|---|
| 1 | Calidad de imagen < `MIN_IMAGE_QUALITY` (0,40) | Mínimo `sospechoso` · «solicitar nueva captura» |
| 2 | Cualquier check crítico en `fail` | Mínimo `sospechoso` |
| 3 | Hallazgo forense con confianza ≥ 0,80, o dos ≥ 0,70 | `falso`. Uno ≥ 0,75 ⇒ mínimo `sospechoso` |
| 4 | `metadata_coherence` en `warn` | Mínimo `sospechoso` · «pedir el documento original» (desactivable con `METADATA_WARN_GATE=false`) |

**Por qué existe la compuerta 3.** La media ponderada tiene un límite
estructural: con todos los checks en `pass`, el score máximo alcanzable es
`0,40 · 1 + 0,25 · 1 = 0,65`, por debajo del umbral de 0,70. Sin esta compuerta,
un documento con una alteración física evidente pero cuya aritmética cuadra
jamás podría declararse falso. Para el negocio eso es incorrecto: una alteración
confirmada es decisiva. Se corrige con una regla explícita y auditable en lugar
de deformar los pesos hasta que el caso encaje.

### Calidad de imagen

```
calidad = 0,45 · nitidez + 0,35 · contraste + 0,20 · resolución
```

- **Nitidez**: varianza del laplaciano (diferencias finitas con NumPy), escalada
  contra 0,004, valor bajo el cual el texto pequeño deja de ser legible.
- **Contraste**: desviación estándar de la luminancia, escalada contra 0,22.
- **Resolución**: lado menor contra 800 px, mínimo razonable para leer un RUT.

Se toma la **mejor** página del documento: si una está nítida, el documento es
legible aunque otra haya salido movida.

---

## Lo que el cliente puede leer

`explanation_customer` es el único campo apto para el cliente, y se verifica
antes de devolverlo (`core/redaction.py`). Si el texto del modelo contiene
alguno de estos términos, se descarta completo y se sustituye por la redacción
segura del veredicto:

| Familia | Términos |
|---|---|
| Mecánica de la decisión | score, puntaje, umbral, regla, modelo, algoritmo, similitud, evidencia, peso, prompt, inteligencia artificial |
| Señales de transacción | vpn, dispositivo, beneficiario, geolocaliza·, dirección ip, intentos fallidos |
| Señales documentales | forense, tipografía, metadato, recorte, compresión, píxel, módulo 11, dígito verificador |
| Acusaciones | fraude, fraudulent·, falsific·, adulterad· |

La comparación ignora tildes y mayúsculas, y cubre plurales y derivados
(«reglas», «dispositivos», «metadatos»). El texto original y los términos
detectados quedan en la traza, para poder ajustar el prompt con evidencia.

Justificación en [`DECISIONES.md`](DECISIONES.md), ADR-011.
