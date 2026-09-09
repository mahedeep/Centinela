# Centinela · web app

Interfaz de la plataforma antifraude **Centinela**, con tres experiencias sobre
una misma API de agentes.

| Rol | Qué hace | Qué jamás ve |
|---|---|---|
| **Cliente** | Simula una transacción y sube documentos | Score, reglas, evidencias, checks, similitudes, modelos, costos |
| **Analista** | Revisa por excepción, con evidencias por peso y hallazgos dibujados sobre la imagen | — |
| **Supervisor** | KPIs, latencia, costo por evento y piloto en modo sombra | — |

React 18 + TypeScript + Tailwind + Recharts. La inteligencia vive en la API
(`centinela-agents`): **el front nunca llama a OpenAI**.

---

## Puesta en marcha

```bash
npm install
cp .env.example .env     # ajusta VITE_API_BASE_URL
npm run dev              # http://localhost:5173
```

Con la API de agentes corriendo en `http://localhost:8000`, la app funciona sin
más configuración.

```bash
npm run build            # compila TypeScript y genera dist/
npm run preview          # sirve dist/ localmente
npm run lint             # solo chequeo de tipos
```

## Variables de entorno

| Variable | Por defecto | Para qué |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | URL base de la API de agentes |
| `VITE_DEMO_MODE` | `false` | `true` arranca en modo demo, sin API |
| `VITE_SUPABASE_URL` | vacío | Opcional. Habilita el acceso con cuenta |
| `VITE_SUPABASE_ANON_KEY` | vacío | Opcional. Clave pública de Supabase |

La URL de la API y el modo demo también se cambian en caliente desde
**Ajustes** (rol Supervisor); el valor queda guardado en ese navegador y tiene
prioridad sobre la variable de entorno.

## Modo demo

El interruptor de **modo demo** hace que la app use respuestas precargadas
(`src/lib/demo.ts`) en lugar de llamar a la API. Sirve para presentar sin
backend y sin gastar tokens.

Los tres escenarios de transacción y tres documentos de ejemplo recorren su
flujo completo en modo demo. Cuando la API no responde, la app muestra un aviso
persistente con un botón para activarlo.

## Rutas

| Ruta | Rol | Pantalla |
|---|---|---|
| `/` | — | Portada y acceso por rol |
| `/cliente/transaccion` | Cliente | Formulario de transacción con tres escenarios precargados |
| `/cliente/documento` | Cliente | Carga por arrastre, vista previa y progreso en tres etapas |
| `/analista` | Analista, Supervisor | Bandeja filtrable, ordenada por score, con indicador de SLA |
| `/casos/:traceId` | Analista, Supervisor | Detalle: score, evidencias, checks, visor con recuadros, decisión humana |
| `/supervisor` | Supervisor | KPIs, series por veredicto, evidencias frecuentes, costo por modelo |
| `/ajustes` | Supervisor | URL de la API, modo demo, umbrales y pesos (solo lectura) |

Las rutas se protegen por rol en `src/App.tsx`. Un rol sin permiso se redirige a
la portada.

## Componentes

| Componente | Para qué |
|---|---|
| `VerdictBadge` | Semáforo del veredicto. Nunca color solo: siempre ícono + texto |
| `ScoreMeter` | Medidor con los dos umbrales marcados. Solo Analista y Supervisor |
| `EvidenceTable` | Evidencias ordenadas por peso, con su tipo |
| `ChecksTable` | Verificaciones deterministas, con lo que exige atención primero |
| `DocumentViewer` | Imagen del documento con los hallazgos como recuadros seleccionables |
| `CaseTimeline` | Decisión, derivación, modo sombra y etiquetas del analista |
| `KpiTile` | Tarjeta de KPI del dashboard |
| `Layout` | Navegación por rol y aviso de estado de la API |
| `states.tsx` | Estados vacíos, de carga y de error, con mensajes accionables |

## Estructura

```
src/
├── lib/
│   ├── types.ts     Tipos derivados de openapi.json
│   ├── api.ts       Cliente HTTP + conmutación a modo demo
│   ├── demo.ts      Respuestas precargadas
│   └── format.ts    Formateadores es-CL y etiquetas en español
├── hooks/
│   ├── useAuth.tsx     Sesión y rol (Supabase opcional)
│   └── useApiStatus.ts Estado de la API, para el aviso persistente
├── components/      Componentes reutilizables
├── pages/           Una por pantalla
└── App.tsx          Rutas y protección por rol
```

## Supabase (opcional)

Sin `VITE_SUPABASE_URL` la app usa **acceso por rol local**: eliges el rol en la
portada y queda guardado en el navegador. Es lo suficiente para la demo.

Con Supabase configurado aparece además el formulario de correo y contraseña, y
el rol se lee de la tabla `profiles`. El esquema completo con sus políticas RLS
está en [`supabase/schema.sql`](supabase/schema.sql):

| Tabla | Para qué | RLS |
|---|---|---|
| `profiles` | Rol de cada usuario | Cada uno ve su perfil; el supervisor ve todos. Nadie puede cambiarse el rol a sí mismo |
| `analyst_actions` | Copia de auditoría del feedback enviado | El analista inserta y lee lo suyo; el supervisor lee todo. Sin update ni delete |
| `settings` | URL de la API y modo demo | Lectura autenticada; solo el supervisor escribe |

Las decisiones, trazas y métricas **no** se guardan en Supabase: viven en la API
de agentes, que es la única fuente de verdad.

## Accesibilidad

- Navegación completa por teclado, con foco visible y enlace «saltar al contenido».
- Contraste AA en texto y controles.
- Todos los campos con `<label>` asociado; tablas con `<caption>` y encabezados con `scope`.
- Objetivos táctiles de 44 px de alto mínimo.
- El semáforo nunca comunica solo por color: siempre acompaña ícono y texto.
- Los resultados se anuncian con `aria-live` para lectores de pantalla.

## Responsive

El flujo del Cliente está pensado para móvil primero; la bandeja del Analista y
el dashboard del Supervisor, para escritorio, con tablas que hacen scroll
horizontal dentro de su contenedor.

## Despliegue

Cualquier hosting de estáticos sirve (Vercel, Netlify, Cloudflare Pages):

```bash
npm run build     # genera dist/
```

Dos cosas que configurar en el hosting:

1. **`VITE_API_BASE_URL`** apuntando a la API desplegada, en las variables de
   entorno del build.
2. **Reescritura a `index.html`** para todas las rutas, porque la app usa
   `BrowserRouter`. En Netlify, `_redirects` con `/* /index.html 200`; en Vercel,
   un `rewrites` equivalente.

Y en la API de agentes, agregar el dominio del front a `ALLOWED_ORIGINS`.

---

Proyecto académico de *Advanced Prompt Engineering 4 Generative AI*, Universidad
Adolfo Ibáñez. Todos los datos son sintéticos.
