create extension if not exists pgcrypto;

create table if not exists public.contacts (
  id uuid primary key default gen_random_uuid(),
  phone_number text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  customer_phone text not null,
  assigned_employee text not null,
  status text not null default 'open' check (status in ('open', 'closed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  direction text not null check (direction in ('customer_to_employee', 'employee_to_customer', 'system')),
  from_phone text not null,
  to_phone text not null,
  body text not null,
  twilio_message_sid text,
  delivery_status text,
  delivery_error_code text,
  delivery_error_message text,
  created_at timestamptz not null default now()
);

create index if not exists conversations_customer_open_idx
  on public.conversations (customer_phone, assigned_employee, status, updated_at desc);

create index if not exists conversations_employee_open_idx
  on public.conversations (assigned_employee, status, updated_at desc);

create index if not exists messages_conversation_created_idx
  on public.messages (conversation_id, created_at);

create index if not exists messages_twilio_sid_idx
  on public.messages (twilio_message_sid)
  where twilio_message_sid is not null;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists conversations_set_updated_at on public.conversations;

create trigger conversations_set_updated_at
before update on public.conversations
for each row
execute function public.set_updated_at();

alter table public.contacts enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;

grant all on public.contacts to service_role;
grant all on public.conversations to service_role;
grant all on public.messages to service_role;
grant usage on schema public to service_role;
grant all on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;

revoke execute on function public.rls_auto_enable() from public;
revoke execute on function public.rls_auto_enable() from anon;
revoke execute on function public.rls_auto_enable() from authenticated;

notify pgrst, 'reload schema';

-- The backend uses SUPABASE_SERVICE_ROLE_KEY only on the server.
-- Do not grant anon/authenticated access until there is a real user-facing client.
