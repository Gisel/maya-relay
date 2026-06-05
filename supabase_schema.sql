create extension if not exists pgcrypto;

create table if not exists public.contacts (
  id uuid primary key default gen_random_uuid(),
  phone_number text not null unique,
  display_name text,
  lookup_name text,
  lookup_checked_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  customer_phone text not null,
  assigned_employee text not null,
  customer_channel text not null default 'sms' check (customer_channel in ('sms', 'whatsapp')),
  conversation_code text unique,
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
  num_media integer not null default 0,
  media_urls jsonb not null default '[]'::jsonb,
  media_content_types jsonb not null default '[]'::jsonb,
  delivery_status text,
  delivery_error_code text,
  delivery_error_message text,
  created_at timestamptz not null default now()
);

create table if not exists public.message_attachments (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.messages(id) on delete cascade,
  bucket text not null default 'attachments',
  object_path text not null,
  public_url text not null,
  source_url text not null,
  content_type text not null,
  size_bytes integer,
  created_at timestamptz not null default now()
);

create index if not exists conversations_customer_open_idx
  on public.conversations (customer_phone, assigned_employee, status, updated_at desc);

create index if not exists conversations_channel_customer_open_idx
  on public.conversations (customer_phone, assigned_employee, customer_channel, status, updated_at desc);

create index if not exists conversations_employee_open_idx
  on public.conversations (assigned_employee, status, updated_at desc);

create index if not exists messages_conversation_created_idx
  on public.messages (conversation_id, created_at);

create index if not exists messages_twilio_sid_idx
  on public.messages (twilio_message_sid)
  where twilio_message_sid is not null;

create index if not exists message_attachments_message_idx
  on public.message_attachments (message_id, created_at);

alter table public.messages
  add column if not exists num_media integer not null default 0,
  add column if not exists media_urls jsonb not null default '[]'::jsonb,
  add column if not exists media_content_types jsonb not null default '[]'::jsonb;

alter table public.contacts
  add column if not exists display_name text,
  add column if not exists lookup_name text,
  add column if not exists lookup_checked_at timestamptz;

alter table public.conversations
  add column if not exists conversation_code text,
  add column if not exists customer_channel text not null default 'sms';

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'conversations_customer_channel_check'
  ) then
    alter table public.conversations
      add constraint conversations_customer_channel_check
      check (customer_channel in ('sms', 'whatsapp'));
  end if;
end $$;

update public.conversations
set conversation_code = upper(substr(replace(id::text, '-', ''), 1, 8))
where conversation_code is null;

create unique index if not exists conversations_code_idx
  on public.conversations (conversation_code)
  where conversation_code is not null;

alter table public.message_attachments enable row level security;

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
grant all on public.message_attachments to service_role;
grant usage on schema public to service_role;
grant all on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;

revoke execute on function public.rls_auto_enable() from public;
revoke execute on function public.rls_auto_enable() from anon;
revoke execute on function public.rls_auto_enable() from authenticated;

notify pgrst, 'reload schema';

-- The backend uses SUPABASE_SERVICE_ROLE_KEY only on the server.
-- Do not grant anon/authenticated access until there is a real user-facing client.
