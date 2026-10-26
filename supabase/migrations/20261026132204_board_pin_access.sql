-- Single-owner board authentication. PIN hashes and bearer hashes are never exposed.
create table cherrypulse_private.pin_access (
  singleton boolean primary key default true check(singleton),
  owner_id uuid not null references auth.users(id),
  pin_hash text,
  failed_attempts integer not null default 0,
  locked_until timestamptz
);
create table cherrypulse_private.pin_sessions (
  token_hash text primary key,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);
alter table cherrypulse_private.pin_access enable row level security;
alter table cherrypulse_private.pin_sessions enable row level security;
revoke all on cherrypulse_private.pin_access, cherrypulse_private.pin_sessions from public, anon, authenticated;
-- One owner was verified before applying this migration. Keep the existing draft owner.
insert into cherrypulse_private.pin_access(singleton,owner_id)
  select true,id from auth.users order by created_at,id limit 1;

create function cherrypulse_private.pin_owner(p_session text) returns uuid
language sql security invoker set search_path='' as $$
  select a.owner_id from cherrypulse_private.pin_access a
  where p_session ~ '^[a-f0-9]{64}$' and exists (
    select 1 from cherrypulse_private.pin_sessions s
    where s.token_hash=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_session,'UTF8')),'hex')
      and s.expires_at>now()
  );
$$;
revoke all on function cherrypulse_private.pin_owner(text) from public,anon,authenticated;

create function public.cp_pin_login(p_pin text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare
  access cherrypulse_private.pin_access%rowtype;
  session_token text;
  failures integer;
begin
  if p_pin is null or p_pin !~ '^[0-9]{4}$' then
    return jsonb_build_object('status',422,'code','PIN_FORMAT_INVALID');
  end if;
  select * into access from cherrypulse_private.pin_access where singleton for update;
  if not found or access.pin_hash is null then
    return jsonb_build_object('status',503,'code','PIN_NOT_CONFIGURED');
  end if;
  if access.locked_until>now() then
    return jsonb_build_object('status',429,'code','PIN_LOCKED');
  end if;
  if access.locked_until is not null then access.failed_attempts:=0; end if;
  if extensions.crypt(p_pin,access.pin_hash)<>access.pin_hash then
    failures:=access.failed_attempts+1;
    update cherrypulse_private.pin_access set failed_attempts=failures,
      locked_until=case when failures>=5 then now()+interval '15 minutes' else null end
      where singleton;
    return jsonb_build_object('status',case when failures>=5 then 429 else 401 end,
      'code',case when failures>=5 then 'PIN_LOCKED' else 'PIN_INCORRECT' end);
  end if;
  update cherrypulse_private.pin_access set failed_attempts=0,locked_until=null where singleton;
  delete from cherrypulse_private.pin_sessions where expires_at<=now();
  -- Bound session growth; newer logins replace the oldest beyond 20 active sessions.
  delete from cherrypulse_private.pin_sessions where token_hash in (
    select token_hash from cherrypulse_private.pin_sessions order by created_at desc offset 19
  );
  session_token:=pg_catalog.encode(extensions.gen_random_bytes(32),'hex');
  insert into cherrypulse_private.pin_sessions(token_hash,expires_at)
    values(pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(session_token,'UTF8')),'hex'),now()+interval '12 hours');
  return jsonb_build_object('sessionToken',session_token,'expiresIn',43200);
end; $$;

create function public.cp_pin_load_board(p_session text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare owner uuid; result jsonb;
begin
  owner:=cherrypulse_private.pin_owner(p_session);
  if owner is null then return jsonb_build_object('status',401,'code','UNAUTHENTICATED'); end if;
  select jsonb_build_object('revision',revision,'snapshot',snapshot,'updatedAt',updated_at)
    into result from cherrypulse_private.board_snapshots where owner_id=owner;
  return coalesce(result,jsonb_build_object('revision',0,'snapshot',null,'updatedAt',null));
end; $$;

create function public.cp_pin_logout(p_session text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
  delete from cherrypulse_private.pin_sessions where token_hash=
    pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_session,'UTF8')),'hex');
  return jsonb_build_object('ok',true);
end; $$;

create function public.cp_pin_save_board(p_session text, p_snapshot jsonb, p_expected_revision integer, p_request_key uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  owner uuid;
  current_revision integer;
  request_digest text;
  receipt cherrypulse_private.save_receipts%rowtype;
  result jsonb;
begin
  owner:=cherrypulse_private.pin_owner(p_session);
  if owner is null then
    return jsonb_build_object('status',401,'code','UNAUTHENTICATED');
  end if;
  if p_request_key is null or p_expected_revision is null or p_expected_revision<0 or
     p_snapshot is null or jsonb_typeof(p_snapshot)<>'object' or
     octet_length(p_snapshot::text)>1048576 or
     p_snapshot->>'format' is distinct from 'cherrypulse-board-draft' or
     p_snapshot->'schemaVersion' is distinct from '1'::jsonb or
     jsonb_typeof(p_snapshot->'symbols') is distinct from 'array' or
     jsonb_typeof(p_snapshot->'patterns') is distinct from 'array' or
     p_snapshot - array['format','schemaVersion','symbols','patterns'] <> '{}'::jsonb then
    return jsonb_build_object('status',422,'code','VALIDATION_FAILED');
  end if;
  -- One transaction per owner serializes creation as well as update/replay races.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('cherrypulse:'||owner::text,0));
  delete from cherrypulse_private.save_receipts where owner_id=owner and created_at<now()-interval '24 hours';
  request_digest := pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_snapshot::text,'UTF8')),'hex');
  select * into receipt from cherrypulse_private.save_receipts where owner_id=owner and request_key=p_request_key;
  if found then
    if receipt.request_digest<>request_digest or receipt.expected_revision<>p_expected_revision then
      return jsonb_build_object('status',409,'code','IDEMPOTENCY_MISMATCH');
    end if;
    return receipt.result;
  end if;
  select revision into current_revision from cherrypulse_private.board_snapshots where owner_id=owner;
  current_revision := coalesce(current_revision,0);
  if p_expected_revision<>current_revision then
    return jsonb_build_object('status',412,'code','VERSION_CONFLICT');
  end if;
  if (select count(*) from cherrypulse_private.save_receipts where owner_id=owner)>=1000 then
    return jsonb_build_object('status',429,'code','RATE_LIMITED');
  end if;
  insert into cherrypulse_private.board_snapshots(owner_id,revision,snapshot,updated_at)
    values(owner,current_revision+1,p_snapshot,now())
    on conflict(owner_id) do update set revision=excluded.revision,snapshot=excluded.snapshot,updated_at=excluded.updated_at;
  result := jsonb_build_object('revision',current_revision+1,'updatedAt',now());
  insert into cherrypulse_private.save_receipts(owner_id,request_key,request_digest,expected_revision,result)
    values(owner,p_request_key,request_digest,p_expected_revision,result);
  return result;
end; $$;

revoke all on function public.cp_pin_login(text) from public;
revoke all on function public.cp_pin_load_board(text) from public;
revoke all on function public.cp_pin_logout(text) from public;
revoke all on function public.cp_pin_save_board(text,jsonb,integer,uuid) from public;
grant execute on function public.cp_pin_login(text) to anon,authenticated;
grant execute on function public.cp_pin_load_board(text) to anon,authenticated;
grant execute on function public.cp_pin_logout(text) to anon,authenticated;
grant execute on function public.cp_pin_save_board(text,jsonb,integer,uuid) to anon,authenticated;
