-- A committed attempt survives a lost HTTP response and process restarts.
create table cherrypulse_private.reservation_paper_orders (
  owner_id uuid not null, reservation_id uuid not null, trade_day date not null,
  state text not null default 'unknown' check (state in ('unknown','accepted','unfilled','partial','filled','rejected')),
  started_at timestamptz not null, sent_at timestamptz, received_at timestamptz,
  accepted_at timestamptz, broker_number text, response_code integer, executed bigint, remaining bigint,
  primary key (owner_id,reservation_id),
  foreign key (owner_id,reservation_id) references cherrypulse_private.reservations(owner_id,id),
  unique(owner_id,trade_day,broker_number)
);
alter table cherrypulse_private.reservation_paper_orders enable row level security;
revoke all on cherrypulse_private.reservation_paper_orders from public,anon,authenticated;

create function public.cp_reservation_paper(p_session text,p_auth text,p_id uuid,p_version integer,p_action text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare owner uuid:=cherrypulse_private.pin_owner(p_session);
  r cherrypulse_private.reservations; a cherrypulse_private.reservation_paper_orders;
  n text:=p_data->>'number'; s text:=p_data->>'state'; q bigint; e bigint; rem bigint;
begin
  if owner is null or p_auth is null or encode(sha256(convert_to(p_auth,'UTF8')),'hex') <>
     '78d2fd4acb568ead49c941a3f15e0232a0a62b226e53aeddca937041aa58bf29' then return '{"status":403}'; end if;
  select * into r from cherrypulse_private.reservations where owner_id=owner and id=p_id for update;
  if not found then return '{"status":404}'; end if;
  if r.version is distinct from p_version or r.cancelled then return '{"status":409}'; end if;
  select * into a from cherrypulse_private.reservation_paper_orders where owner_id=owner and reservation_id=p_id;
  if p_action in ('preview','claim') then
    if a.reservation_id is not null or not r.dry_run_enabled or r.details->>'type'<>'지정가'
      or r.execute_at>clock_timestamp() or r.execute_at<=clock_timestamp()-interval '2 minutes'
      or not cherrypulse_private.krx_reservation_day((r.execute_at at time zone 'Asia/Seoul')::date)
      or exists(select from cherrypulse_private.reservation_dry_runs d where d.owner_id=owner and d.reservation_id=p_id and d.result='ERROR')
      then return '{"status":409}'; end if;
    if p_action='claim' then
      if r.details->>'side'='매수' and public.cp_claim_manual_paper_buy(p_session,p_auth,r.details->>'code',
        (r.details->>'qty')::bigint,(r.details->>'price')::bigint)<>201 then return '{"status":409}'; end if;
      insert into cherrypulse_private.reservation_paper_orders(owner_id,reservation_id,trade_day,started_at)
        values(owner,p_id,(r.execute_at at time zone 'Asia/Seoul')::date,(p_data->>'startedAt')::timestamptz);
    end if;
    return jsonb_build_object('details',r.details);
  end if;
  if a.reservation_id is null then return '{"status":404}'; end if;
  if p_action='inspect' then return jsonb_build_object('details',r.details,'number',a.broker_number,'startedAt',a.started_at,'state',a.state); end if;
  if p_action='dispatch' then
    update cherrypulse_private.reservation_paper_orders set sent_at=coalesce(sent_at,(p_data->>'sentAt')::timestamptz)
      where owner_id=owner and reservation_id=p_id;
  elsif p_action='response' then
    if a.received_at is not null or (a.broker_number is not null and n is not null and n<>a.broker_number)
      or s is null or s not in ('accepted','unknown','rejected') or
      (s='accepted' and (n is null or n !~ '^[0-9]+$' or n !~ '[1-9]')) then return '{"status":409}'; end if;
    update cherrypulse_private.reservation_paper_orders set
      sent_at=coalesce(sent_at,(p_data->>'sentAt')::timestamptz),received_at=(p_data->>'receivedAt')::timestamptz,
      state=case when a.state='unknown' then s else a.state end, broker_number=coalesce(a.broker_number,n),
      response_code=(p_data->>'responseCode')::integer where owner_id=owner and reservation_id=p_id;
  elsif p_action='observe' then
    q:=(r.details->>'qty')::bigint; e:=(p_data->>'executed')::bigint; rem:=(p_data->>'remaining')::bigint;
    if n is null or n !~ '^[0-9]+$' or n !~ '[1-9]' or (a.broker_number is not null and a.broker_number<>n)
      or s is null or s not in ('accepted','unfilled','partial','filled','rejected') then return '{"status":409}'; end if;
    if s in ('unfilled','partial','filled') and (e is null or rem is null or e<0 or rem<0 or e+rem<>q
      or (s='unfilled' and e<>0) or (s='partial' and (e=0 or rem=0)) or (s='filled' and rem<>0))
      then return '{"status":422}'; end if;
    if a.state in ('filled','rejected') or (a.executed is not null and coalesce(e,-1)<a.executed)
      or (a.state in ('unfilled','partial') and s='accepted') then return '{"ok":true}'; end if;
    update cherrypulse_private.reservation_paper_orders set broker_number=n,state=s,executed=e,remaining=rem,
      accepted_at=coalesce(accepted_at,(p_data->>'acceptedAt')::timestamptz) where owner_id=owner and reservation_id=p_id;
  else return '{"status":422}'; end if;
  return '{"ok":true}';
exception when unique_violation then return '{"status":409}';
end; $$;
revoke all on function public.cp_reservation_paper(text,text,uuid,integer,text,jsonb) from public;
grant execute on function public.cp_reservation_paper(text,text,uuid,integer,text,jsonb) to anon;
create or replace function cherrypulse_private.list_reservation_runs(p_session text) returns jsonb
 language plpgsql security definer set search_path='' as $$
declare owner uuid:=cherrypulse_private.pin_owner(p_session); rows jsonb;
begin
 if owner is null then return '{"status":401}'; end if;
 select coalesce(jsonb_agg(jsonb_build_object('id',r.id,'details',r.details,'version',r.version,
 'paperOrder',case when a.reservation_id is not null then jsonb_build_object('state',a.state,'startedAt',a.started_at,'sentAt',a.sent_at,'receivedAt',a.received_at,'acceptedAt',a.accepted_at,'number',a.broker_number,'executed',a.executed,'remaining',a.remaining) end,
 'executeAt',r.execute_at,'processedAt',d.processed_at,'errorCode',d.error_code,
 'status',case when r.cancelled then 'cancelled' when d.result='DRY_RUN' then 'dry_run'
   when d.result='ERROR' then 'error' when not r.dry_run_enabled or
     not cherrypulse_private.krx_reservation_day((r.execute_at at time zone 'Asia/Seoul')::date)
     or r.execute_at<=statement_timestamp()-interval '2 minutes' then 'expired'
   when r.execute_at<=statement_timestamp() then 'due' else 'scheduled' end)
 order by r.execute_at desc,r.id),'[]'::jsonb) into rows
 from cherrypulse_private.reservations r left join cherrypulse_private.reservation_dry_runs d
 on d.owner_id=r.owner_id and d.reservation_id=r.id left join cherrypulse_private.reservation_paper_orders a on a.owner_id=r.owner_id and a.reservation_id=r.id where r.owner_id=owner;
 return jsonb_build_object('rows',rows);
end; $$;
