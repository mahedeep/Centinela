-- ============================================================================
-- Centinela · esquema de Supabase
--
-- Tres tablas y sus políticas RLS. Supabase es OPCIONAL: sin él la app usa
-- acceso por rol guardado en el navegador, suficiente para la demo del curso.
--
-- Ejecuta este archivo en el editor SQL de Supabase.
--
-- Nota de alcance: las decisiones, trazas y métricas viven en la API de
-- agentes, no aquí. Supabase solo guarda quién es quién (`profiles`), una copia
-- de auditoría de lo que el analista envió (`analyst_actions`) y la
-- configuración de la app (`settings`).
-- ============================================================================

-- --- 1. profiles ------------------------------------------------------------
-- Un perfil por usuario de auth. El rol determina qué pantallas ve.

create type public.user_role as enum ('cliente', 'analista', 'supervisor');

create table public.profiles (
  id           uuid primary key references auth.users on delete cascade,
  role         public.user_role not null default 'cliente',
  display_name text not null default '',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

comment on table public.profiles is
  'Rol de cada usuario. El front lo lee al iniciar sesión.';

alter table public.profiles enable row level security;

-- Cada usuario ve y edita su propio perfil…
create policy "perfil propio · lectura"
  on public.profiles for select
  using (auth.uid() = id);

create policy "perfil propio · actualización"
  on public.profiles for update
  using (auth.uid() = id)
  -- …pero no puede ascenderse solo: el rol se cambia desde el panel de
  -- Supabase o con la service key, jamás desde el front.
  with check (auth.uid() = id and role = (select role from public.profiles where id = auth.uid()));

-- Los supervisores ven todos los perfiles, para saber quién revisó qué.
create policy "supervisor · lectura de todos los perfiles"
  on public.profiles for select
  using (
    exists (
      select 1 from public.profiles p
      where p.id = auth.uid() and p.role = 'supervisor'
    )
  );

-- Al crearse un usuario, se le crea el perfil con rol `cliente`.
create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', new.email));
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();


-- --- 2. analyst_actions -----------------------------------------------------
-- Copia local de cada feedback enviado a la API, para auditoría interna.
-- La fuente de verdad sigue siendo la traza de la API.

create table public.analyst_actions (
  id          bigint generated always as identity primary key,
  analyst_id  uuid not null references auth.users on delete cascade,
  trace_id    text not null,
  process     text not null check (process in ('transaction', 'document')),
  label       text not null check (
                label in ('fraude_confirmado', 'legitimo',
                          'documento_falso', 'documento_autentico')
              ),
  comment     text not null default '',
  api_ack     jsonb,
  created_at  timestamptz not null default now()
);

create index analyst_actions_trace_idx on public.analyst_actions (trace_id);
create index analyst_actions_analyst_idx on public.analyst_actions (analyst_id, created_at desc);

comment on table public.analyst_actions is
  'Auditoría local de las etiquetas que el analista envió a la API de agentes.';

alter table public.analyst_actions enable row level security;

-- Analistas y supervisores pueden registrar acciones; el registro queda a su
-- nombre y no puede falsificarse.
create policy "analista · registra sus propias acciones"
  on public.analyst_actions for insert
  with check (
    auth.uid() = analyst_id
    and exists (
      select 1 from public.profiles p
      where p.id = auth.uid() and p.role in ('analista', 'supervisor')
    )
  );

create policy "analista · lee sus propias acciones"
  on public.analyst_actions for select
  using (auth.uid() = analyst_id);

create policy "supervisor · lee todas las acciones"
  on public.analyst_actions for select
  using (
    exists (
      select 1 from public.profiles p
      where p.id = auth.uid() and p.role = 'supervisor'
    )
  );

-- Nadie borra ni edita: es un registro de auditoría (no se declara ninguna
-- política de update ni de delete, así que RLS las niega por defecto).


-- --- 3. settings ------------------------------------------------------------
-- Configuración compartida de la app. Una sola fila.

create table public.settings (
  id             int primary key default 1 check (id = 1),
  api_base_url   text not null default 'http://localhost:8000',
  demo_mode      boolean not null default false,
  agents_repo_url text not null default '',
  updated_by     uuid references auth.users on delete set null,
  updated_at     timestamptz not null default now()
);

insert into public.settings (id) values (1) on conflict do nothing;

comment on table public.settings is
  'URL de la API y modo demo. Solo el supervisor puede cambiarlos.';

alter table public.settings enable row level security;

-- Todos los usuarios autenticados leen la configuración…
create policy "settings · lectura autenticada"
  on public.settings for select
  using (auth.uid() is not null);

-- …solo el supervisor la modifica.
create policy "settings · escritura del supervisor"
  on public.settings for update
  using (
    exists (
      select 1 from public.profiles p
      where p.id = auth.uid() and p.role = 'supervisor'
    )
  );


-- ============================================================================
-- Usuarios de demo
--
-- Crea los tres usuarios desde Authentication → Users en el panel de Supabase
-- y después ajusta su rol aquí. Los correos son ficticios.
--
--   update public.profiles set role = 'analista',   display_name = 'Ana Analista'
--     where id = (select id from auth.users where email = 'analista@ejemplo.cl');
--
--   update public.profiles set role = 'supervisor', display_name = 'Sofía Supervisora'
--     where id = (select id from auth.users where email = 'supervisor@ejemplo.cl');
--
--   update public.profiles set role = 'cliente',    display_name = 'Carlos Cliente'
--     where id = (select id from auth.users where email = 'cliente@ejemplo.cl');
-- ============================================================================
