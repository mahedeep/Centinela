#!/usr/bin/env bash
# Smoke test de Centinela: salud + los tres veredictos de transacción +
# validación de un documento + bandeja + métricas.
#
#   bash scripts/smoke_test.sh [URL_BASE]
#
# Requiere la API corriendo:
#   uvicorn centinela.main:app --app-dir src

set -uo pipefail

BASE="${1:-http://localhost:8000}"
API="$BASE/api/v1"
SAMPLES="$(cd "$(dirname "$0")/.." && pwd)/data/samples"
PASS=0
FAIL=0

c_ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; PASS=$((PASS + 1)); }
c_fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=$((FAIL + 1)); }
title()  { printf '\n\033[1m%s\033[0m\n' "$1"; }

json_get() {  # json_get <json> <clave>  → valor simple, sin dependencias externas
  printf '%s' "$1" | sed -n "s/.*\"$2\":[[:space:]]*\"\{0,1\}\([^,\"}]*\)\"\{0,1\}.*/\1/p" | head -1
}

tx_payload() {  # tx_payload <monto> <nuevo_benef> <nuevo_disp> <pais_ip> <vpn> <km> <fallidos> <sesion>
  cat <<JSON
{"transaction_id":"TX-SMOKE-$RANDOM","timestamp":"2026-09-08T14:32:10-03:00",
 "amount":$1,"currency":"CLP","channel":"app_movil","type":"transferencia",
 "origin_account":{"id":"ACC-1001","age_days":1450,"avg_monthly_amount":900000,"country":"CL"},
 "destination_account":{"id":"ACC-77$RANDOM","bank":"OtroBanco","is_new_beneficiary":$2,"country":"CL"},
 "device":{"id":"DEV-55","is_new_device":$3,"os":"Android","ip_country":"$4","vpn":$5},
 "geo":{"lat":-33.45,"lon":-70.66,"distance_from_home_km":$6},
 "behavior":{"tx_last_hour":1,"tx_last_24h":4,"failed_logins_24h":$7,"session_seconds":$8},
 "customer_profile":{"segment":"persona_natural","risk_tier":"medio"}}
JSON
}

# El cuerpo de la última respuesta queda en LAST_BODY: así los mensajes de
# estado van a stdout sin mezclarse con el JSON.
LAST_BODY=""

check_verdict() {  # check_verdict <nombre> <payload> <veredicto esperado>
  local verdict
  LAST_BODY=$(curl -s -X POST "$API/transactions/evaluate" \
                   -H 'Content-Type: application/json' -d "$2")
  verdict=$(json_get "$LAST_BODY" verdict)
  if [ "$verdict" = "$3" ]; then
    c_ok "$1 → $verdict (score $(json_get "$LAST_BODY" score))"
  else
    c_fail "$1 → se esperaba '$3' y se obtuvo '${verdict:-sin respuesta}'"
    printf '    %s\n' "$(printf '%s' "$LAST_BODY" | head -c 300)"
  fi
}

title "Centinela · smoke test contra $BASE"

# --- salud --------------------------------------------------------------------
title "1. Salud"
HEALTH=$(curl -s --max-time 10 "$API/health")
if [ -z "$HEALTH" ]; then
  c_fail "La API no responde en $API/health. ¿Está corriendo uvicorn?"
  exit 1
fi
[ "$(json_get "$HEALTH" status)" = "ok" ] \
  && c_ok "status=ok · mock_mode=$(json_get "$HEALTH" mock_mode)" \
  || c_fail "health devolvió: $HEALTH"

# --- transacciones ------------------------------------------------------------
title "2. Transacciones · los tres veredictos"
check_verdict "legítima"    "$(tx_payload 85000   false false CL false 2.1  0 180)" "aprobar"
check_verdict "dudosa"      "$(tx_payload 1250000 true  false CL false 3.2  1 95)"  "validacion_adicional"
check_verdict "fraudulenta" "$(tx_payload 3900000 true  true  BR true  640  5 22)"  "bloquear"
TRACE_ID=$(json_get "$LAST_BODY" trace_id)

# --- documentos ---------------------------------------------------------------
title "3. Documentos"
if [ -f "$SAMPLES/cedula_ok.png" ]; then
  DOC=$(curl -s -X POST "$API/documents/validate" -F "file=@$SAMPLES/cedula_ok.png")
  DOC_VERDICT=$(json_get "$DOC" verdict)
  DOC_TRACE=$(json_get "$DOC" trace_id)
  [ "$DOC_VERDICT" = "autentico" ] \
    && c_ok "cedula_ok.png → autentico" \
    || c_fail "cedula_ok.png → '$DOC_VERDICT' (se esperaba autentico)"

  if [ -f "$SAMPLES/cedula_alterada_fecha.png" ]; then
    ALT=$(curl -s -X POST "$API/documents/validate" -F "file=@$SAMPLES/cedula_alterada_fecha.png")
    ALT_VERDICT=$(json_get "$ALT" verdict)
    case "$ALT_VERDICT" in
      sospechoso|falso) c_ok "cedula_alterada_fecha.png → $ALT_VERDICT" ;;
      *) c_fail "cedula_alterada_fecha.png → '$ALT_VERDICT' (se esperaba sospechoso o falso)" ;;
    esac
  fi

  if [ -n "${DOC_TRACE:-}" ]; then
    EV=$(curl -s "$API/documents/$DOC_TRACE/evidence")
    [ -n "$(json_get "$EV" trace_id)" ] \
      && c_ok "evidencia con regiones disponible para el front" \
      || c_fail "el endpoint de evidencia no respondió"
  fi
else
  c_fail "No hay documentos de prueba. Corre: python scripts/make_sample_documents.py"
fi

# --- trazabilidad -------------------------------------------------------------
title "4. Trazabilidad y feedback"
if [ -n "${TRACE_ID:-}" ]; then
  DETAIL=$(curl -s "$API/cases/$TRACE_ID")
  [ -n "$(json_get "$DETAIL" prompt_version)" ] \
    && c_ok "la traza guarda el prompt_version ($(json_get "$DETAIL" prompt_version))" \
    || c_fail "la traza no expone prompt_version"

  FB=$(curl -s -X POST "$API/feedback" -H 'Content-Type: application/json' \
       -d "{\"trace_id\":\"$TRACE_ID\",\"label\":\"fraude_confirmado\",\"analyst\":\"smoke.test\",\"comment\":\"Smoke test\"}")
  [ "$(json_get "$FB" trace_id)" = "$TRACE_ID" ] \
    && c_ok "feedback registrado (indexado: $(json_get "$FB" indexed))" \
    || c_fail "el feedback no se registró"
else
  c_fail "Sin trace_id del caso bloqueado; se omite la verificación de traza"
fi

# --- bandeja y métricas -------------------------------------------------------
title "5. Bandeja y métricas"
CASES=$(curl -s "$API/cases?requires_human_review=true&limit=5")
printf '%s' "$CASES" | grep -q 'trace_id' \
  && c_ok "la bandeja del analista devuelve casos para revisar" \
  || c_fail "la bandeja no devolvió casos"

METRICS=$(curl -s "$API/metrics")
printf '%s' "$METRICS" | grep -q 'total_volume' \
  && c_ok "métricas: volumen $(json_get "$METRICS" total_volume) · costo USD $(json_get "$METRICS" total_cost_usd)" \
  || c_fail "las métricas no respondieron"

# --- resumen ------------------------------------------------------------------
printf '\n\033[1mResultado: %d correctas, %d fallidas\033[0m\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
