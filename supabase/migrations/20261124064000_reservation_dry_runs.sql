-- The activation boundary keeps already expired reservations terminal on upgrade.
alter table cherrypulse_private.reservations add column dry_run_enabled boolean not null default true;
update cherrypulse_private.reservations set dry_run_enabled=false where execute_at<=statement_timestamp();
create index reservations_due_queue on cherrypulse_private.reservations(execute_at)
 where not cancelled and dry_run_enabled;

create table cherrypulse_private.reservation_dry_runs (
 owner_id uuid not null,
 reservation_id uuid not null,
 reservation_version integer not null,
 scheduled_at timestamptz not null,
 processed_at timestamptz not null,
 result text not null check(result in ('DRY_RUN','ERROR')),
 error_code text,
 primary key(owner_id,reservation_id),
 foreign key(owner_id,reservation_id) references cherrypulse_private.reservations(owner_id,id),
 check((result='ERROR')=(error_code is not null))
);
alter table cherrypulse_private.reservation_dry_runs enable row level security;
revoke all on cherrypulse_private.reservation_dry_runs from public,anon,authenticated;
create policy no_direct_access on cherrypulse_private.reservation_dry_runs
 as restrictive for all to public using(false) with check(false);

create function cherrypulse_private.krx_reservation_day(day date) returns boolean
 language sql immutable strict set search_path='' as $$
 select day between date '2026-01-01' and date '2026-12-31' and extract(isodow from day)<=5
 and day not in ('2026-01-01','2026-02-16','2026-02-17','2026-02-18','2026-03-02',
 '2026-05-01','2026-05-05','2026-05-25','2026-06-03','2026-07-17','2026-08-17',
 '2026-09-24','2026-09-25','2026-10-05','2026-10-09','2026-12-25','2026-12-31');
$$;

-- Each tick is one transaction. Rollback releases the lock and leaves work eligible.
create function cherrypulse_private.run_reservation_dry_tick(tick timestamptz default statement_timestamp()) returns integer
 language plpgsql security invoker set search_path='' as $$
declare
 processed integer;
begin
 if not pg_try_advisory_xact_lock(72461124,1) then return 0; end if;
 with due as (
   select r.*,r.execute_at at time zone 'Asia/Seoul' as local_time
   from cherrypulse_private.reservations r
   where r.dry_run_enabled and not r.cancelled and r.execute_at<=tick
     and r.execute_at>tick-interval '2 minutes'
     and cherrypulse_private.krx_reservation_day((r.execute_at at time zone 'Asia/Seoul')::date)
     and not exists(select from cherrypulse_private.reservation_dry_runs d
       where d.owner_id=r.owner_id and d.reservation_id=r.id)
   for update of r skip locked
 ), checked as (
   select due.*,case when details->>'date' is distinct from to_char(local_time,'YYYY-MM-DD')
     or details->>'time' is distinct from to_char(local_time,'HH24:MI') then 'SCHEDULE_MISMATCH'
     when (details->>'type'='지정가' and (details->>'qty')::numeric*(details->>'price')::numeric > 9007199254740991)
     then 'AMOUNT_OUT_OF_RANGE' end as problem from due
 )
 insert into cherrypulse_private.reservation_dry_runs
 (owner_id,reservation_id,reservation_version,scheduled_at,processed_at,result,error_code)
 select owner_id,id,version,execute_at,clock_timestamp(),
   case when problem is null then 'DRY_RUN' else 'ERROR' end,problem from checked
 on conflict(owner_id,reservation_id) do nothing;
 get diagnostics processed=row_count;
 return processed;
end; $$;
revoke all on function cherrypulse_private.run_reservation_dry_tick(timestamptz),
 cherrypulse_private.krx_reservation_day(date) from public,anon,authenticated;

create function cherrypulse_private.list_reservation_runs(p_session text) returns jsonb
 language plpgsql security definer set search_path='' as $$
declare owner uuid:=cherrypulse_private.pin_owner(p_session); rows jsonb;
begin
 if owner is null then return '{"status":401}'; end if;
 select coalesce(jsonb_agg(jsonb_build_object('id',r.id,'details',r.details,'version',r.version,
 'executeAt',r.execute_at,'processedAt',d.processed_at,'errorCode',d.error_code,
 'status',case when r.cancelled then 'cancelled' when d.result='DRY_RUN' then 'dry_run'
   when d.result='ERROR' then 'error' when not r.dry_run_enabled or
     not cherrypulse_private.krx_reservation_day((r.execute_at at time zone 'Asia/Seoul')::date)
     or r.execute_at<=statement_timestamp()-interval '2 minutes' then 'expired'
   when r.execute_at<=statement_timestamp() then 'due' else 'scheduled' end)
 order by r.execute_at desc,r.id),'[]'::jsonb) into rows
 from cherrypulse_private.reservations r left join cherrypulse_private.reservation_dry_runs d
 on d.owner_id=r.owner_id and d.reservation_id=r.id where r.owner_id=owner;
 return jsonb_build_object('rows',rows);
end; $$;
revoke all on function cherrypulse_private.list_reservation_runs(text) from public;
grant execute on function cherrypulse_private.list_reservation_runs(text) to anon,authenticated;
create or replace function public.cp_reservations(p_session text,p_action text,p_id uuid,p_version integer,p_details jsonb)
 returns jsonb language sql security invoker set search_path='' as $$
 select case when p_action='list' then cherrypulse_private.list_reservation_runs(p_session)
 else cherrypulse_private.manage_reservations(p_session,p_action,p_id,p_version,p_details) end;
$$;
