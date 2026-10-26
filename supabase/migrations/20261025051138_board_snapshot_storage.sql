-- Account-scoped draft snapshots only. No broker credentials or trading state.
create schema cherrypulse_private;
revoke all on schema cherrypulse_private from public, anon;
grant usage on schema cherrypulse_private to authenticated;

create table cherrypulse_private.board_snapshots (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  revision integer not null check (revision > 0),
  snapshot jsonb not null check (
    octet_length(snapshot::text) <= 1048576
    and jsonb_typeof(snapshot) = 'object'
    and snapshot->>'format' = 'cherrypulse-board-draft'
    and snapshot->'schemaVersion' = '1'::jsonb
    and jsonb_typeof(snapshot->'symbols') = 'array'
    and jsonb_typeof(snapshot->'patterns') = 'array'
    and snapshot ?& array['format','schemaVersion','symbols','patterns']
    and snapshot - array['format','schemaVersion','symbols','patterns'] = '{}'::jsonb
  ),
  updated_at timestamptz not null default now()
);
create table cherrypulse_private.save_receipts (
  owner_id uuid not null references auth.users(id) on delete cascade,
  request_key uuid not null,
  request_digest text not null,
  expected_revision integer not null,
  result jsonb not null,
  created_at timestamptz not null default now(),
  primary key (owner_id, request_key)
);
alter table cherrypulse_private.board_snapshots enable row level security;
alter table cherrypulse_private.save_receipts enable row level security;
create policy snapshots_owner on cherrypulse_private.board_snapshots to authenticated
  using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy receipts_owner on cherrypulse_private.save_receipts to authenticated
  using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
revoke all on cherrypulse_private.board_snapshots, cherrypulse_private.save_receipts from public, anon;
grant select, insert, update on cherrypulse_private.board_snapshots to authenticated;
grant select, insert, delete on cherrypulse_private.save_receipts to authenticated;

create function public.cp_load_board() returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare result jsonb;
begin
  if auth.uid() is null or coalesce((auth.jwt()->>'is_anonymous')::boolean, false) then
    return jsonb_build_object('status',401,'code','UNAUTHENTICATED');
  end if;
  select jsonb_build_object('revision',revision,'snapshot',snapshot,'updatedAt',updated_at)
    into result from cherrypulse_private.board_snapshots where owner_id=auth.uid();
  return coalesce(result,jsonb_build_object('revision',0,'snapshot',null,'updatedAt',null));
end; $$;

create function public.cp_save_board(p_snapshot jsonb, p_expected_revision integer, p_request_key uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  current_revision integer;
  request_digest text;
  receipt cherrypulse_private.save_receipts%rowtype;
  result jsonb;
begin
  if auth.uid() is null or coalesce((auth.jwt()->>'is_anonymous')::boolean, false) then
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
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('cherrypulse:'||auth.uid()::text,0));
  delete from cherrypulse_private.save_receipts where owner_id=auth.uid() and created_at<now()-interval '24 hours';
  request_digest := pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_snapshot::text,'UTF8')),'hex');
  select * into receipt from cherrypulse_private.save_receipts where owner_id=auth.uid() and request_key=p_request_key;
  if found then
    if receipt.request_digest<>request_digest or receipt.expected_revision<>p_expected_revision then
      return jsonb_build_object('status',409,'code','IDEMPOTENCY_MISMATCH');
    end if;
    return receipt.result;
  end if;
  select revision into current_revision from cherrypulse_private.board_snapshots where owner_id=auth.uid();
  current_revision := coalesce(current_revision,0);
  if p_expected_revision<>current_revision then
    return jsonb_build_object('status',412,'code','VERSION_CONFLICT');
  end if;
  if (select count(*) from cherrypulse_private.save_receipts where owner_id=auth.uid())>=1000 then
    return jsonb_build_object('status',429,'code','RATE_LIMITED');
  end if;
  insert into cherrypulse_private.board_snapshots(owner_id,revision,snapshot,updated_at)
    values(auth.uid(),current_revision+1,p_snapshot,now())
    on conflict(owner_id) do update set revision=excluded.revision,snapshot=excluded.snapshot,updated_at=excluded.updated_at;
  result := jsonb_build_object('revision',current_revision+1,'updatedAt',now());
  insert into cherrypulse_private.save_receipts(owner_id,request_key,request_digest,expected_revision,result)
    values(auth.uid(),p_request_key,request_digest,p_expected_revision,result);
  return result;
end; $$;
revoke all on function public.cp_load_board() from public,anon;
revoke all on function public.cp_save_board(jsonb,integer,uuid) from public,anon;
grant execute on function public.cp_load_board() to authenticated;
grant execute on function public.cp_save_board(jsonb,integer,uuid) to authenticated;
