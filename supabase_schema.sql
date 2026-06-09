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
  client_request_id text,
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

create table if not exists public.calls (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid references public.conversations(id) on delete set null,
  direction text not null default 'outbound' check (direction in ('outbound', 'inbound')),
  call_type text not null check (call_type in ('conversation_call', 'manual_outbound', 'inbound')),
  customer_phone text not null,
  employee_phone text,
  twilio_call_sid text,
  status text not null default 'initiated',
  outcome text check (
    outcome is null
    or outcome in ('connected', 'voicemail', 'no_answer', 'follow_up_needed', 'wrong_number', 'cancelled')
  ),
  notes text,
  follow_up_status text not null default 'none' check (follow_up_status in ('none', 'needed', 'scheduled', 'done')),
  recap text,
  transcription text,
  recording_sid text,
  recording_url text,
  recording_status text,
  recording_duration_seconds integer,
  recording_channels integer,
  started_at timestamptz not null default now(),
  answered_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.call_events (
  id uuid primary key default gen_random_uuid(),
  call_id uuid references public.calls(id) on delete set null,
  twilio_call_sid text,
  event_type text not null,
  call_status text,
  payload jsonb not null default '{}'::jsonb,
  received_at timestamptz not null default now()
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

create unique index if not exists messages_client_request_idx
  on public.messages (conversation_id, client_request_id)
  where client_request_id is not null;

create index if not exists message_attachments_message_idx
  on public.message_attachments (message_id, created_at);

create unique index if not exists calls_twilio_call_sid_idx
  on public.calls (twilio_call_sid)
  where twilio_call_sid is not null;

create index if not exists calls_recording_sid_idx
  on public.calls (recording_sid)
  where recording_sid is not null;

create index if not exists calls_conversation_started_idx
  on public.calls (conversation_id, started_at desc);

create index if not exists calls_customer_started_idx
  on public.calls (customer_phone, started_at desc);

create index if not exists call_events_call_received_idx
  on public.call_events (call_id, received_at desc);

create index if not exists call_events_twilio_sid_received_idx
  on public.call_events (twilio_call_sid, received_at desc)
  where twilio_call_sid is not null;

alter table public.messages
  add column if not exists num_media integer not null default 0,
  add column if not exists media_urls jsonb not null default '[]'::jsonb,
  add column if not exists media_content_types jsonb not null default '[]'::jsonb,
  add column if not exists client_request_id text;

alter table public.contacts
  add column if not exists display_name text,
  add column if not exists lookup_name text,
  add column if not exists lookup_checked_at timestamptz;

alter table public.conversations
  add column if not exists conversation_code text,
  add column if not exists customer_channel text not null default 'sms';

alter table public.calls
  add column if not exists follow_up_status text not null default 'none',
  add column if not exists recap text,
  add column if not exists transcription text,
  add column if not exists recording_sid text,
  add column if not exists recording_url text,
  add column if not exists recording_status text,
  add column if not exists recording_duration_seconds integer,
  add column if not exists recording_channels integer;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'calls_follow_up_status_check'
  ) then
    alter table public.calls
      add constraint calls_follow_up_status_check
      check (follow_up_status in ('none', 'needed', 'scheduled', 'done'));
  end if;
end $$;

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

drop trigger if exists calls_set_updated_at on public.calls;

create trigger calls_set_updated_at
before update on public.calls
for each row
execute function public.set_updated_at();

alter table public.contacts enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.calls enable row level security;
alter table public.call_events enable row level security;

grant all on public.contacts to service_role;
grant all on public.conversations to service_role;
grant all on public.messages to service_role;
grant all on public.message_attachments to service_role;
grant all on public.calls to service_role;
grant all on public.call_events to service_role;
grant usage on schema public to service_role;
grant all on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;

revoke execute on function public.rls_auto_enable() from public;
revoke execute on function public.rls_auto_enable() from anon;
revoke execute on function public.rls_auto_enable() from authenticated;

notify pgrst, 'reload schema';

-- The backend uses SUPABASE_SERVICE_ROLE_KEY only on the server.
-- Do not grant anon/authenticated access until there is a real user-facing client.
