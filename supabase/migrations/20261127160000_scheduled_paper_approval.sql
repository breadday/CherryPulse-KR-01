-- Approval applies only to the exact version saved from a registered device.
alter table cherrypulse_private.reservations
  add column paper_approved_version integer,
  add column paper_worker_key uuid unique;

create function public.cp_save_scheduled_paper(p_session text,p_auth text,p_action text,p_id uuid,p_version integer,p_details jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare owner uuid:=cherrypulse_private.pin_owner(p_session); saved jsonb; r cherrypulse_private.reservations;
begin
  if owner is null or p_auth is null or encode(sha256(convert_to(p_auth,'UTF8')),'hex')<>
    '78d2fd4acb568ead49c941a3f15e0232a0a62b226e53aeddca937041aa58bf29' then return '{"status":403}'; end if;
  if p_action not in ('create','update') or p_details->>'type' is distinct from '지정가' then return '{"status":422}'; end if;
  select * into r from cherrypulse_private.reservations where owner_id=owner and id=p_id for update;
  if found and p_action='create' then
    if r.version=1 and r.paper_approved_version=1 and r.details=p_details and not r.cancelled then
      return jsonb_build_object('id',r.id,'version',r.version);
    end if;
    return '{"status":409}';
  end if;
  saved:=cherrypulse_private.manage_reservations(p_session,p_action,p_id,p_version,p_details);
  if saved ? 'status' then return saved; end if;
  update cherrypulse_private.reservations set paper_approved_version=version,paper_worker_key=gen_random_uuid()
    where owner_id=owner and id=p_id and details=p_details and version=(saved->>'version')::integer
    and not cancelled and execute_at>clock_timestamp() and cherrypulse_private.krx_reservation_day((execute_at at time zone 'Asia/Seoul')::date);
  if not found then raise exception 'Reservation cannot be approved'; end if;
  return saved;
end; $$;
revoke all on function public.cp_save_scheduled_paper(text,text,text,uuid,integer,jsonb) from public,authenticated;
grant execute on function public.cp_save_scheduled_paper(text,text,text,uuid,integer,jsonb) to anon;

create function public.cp_scheduled_paper_worker(p_key uuid,p_auth text,p_action text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r cherrypulse_private.reservations; day date; n text:=p_data->>'number';
begin
  if p_auth is null or encode(sha256(convert_to(p_auth,'UTF8')),'hex')<>
    '78d2fd4acb568ead49c941a3f15e0232a0a62b226e53aeddca937041aa58bf29' then return '{"status":403}'; end if;
  select * into r from cherrypulse_private.reservations where paper_worker_key=p_key and paper_approved_version=version and not cancelled for update;
  if not found then return '{"status":404}'; end if;
  day:=(r.execute_at at time zone 'Asia/Seoul')::date;
  if p_action='response' then
    update cherrypulse_private.reservation_paper_orders set sent_at=(p_data->>'sentAt')::timestamptz,
      received_at=(p_data->>'receivedAt')::timestamptz,response_code=(p_data->>'responseCode')::integer,
      state=case when state='unknown' then p_data->>'state' else state end,broker_number=coalesce(broker_number,n)
      where owner_id=r.owner_id and reservation_id=r.id and sent_at is null and (broker_number is null or n is null or broker_number=n);
    if not found then return '{"status":409}'; end if;
    return '{"ok":true}';
  end if;
  if p_action not in ('preview','claim') or r.execute_at>clock_timestamp() or r.execute_at+interval '2 minutes'<=clock_timestamp()
    or not cherrypulse_private.krx_reservation_day(day) or not exists(select from cherrypulse_private.reservation_dry_runs d
      where d.owner_id=r.owner_id and d.reservation_id=r.id and d.reservation_version=r.version and d.result='DRY_RUN')
    or exists(select from cherrypulse_private.reservation_paper_orders a where a.owner_id=r.owner_id and a.reservation_id=r.id)
    then return '{"status":409}'; end if;
  if p_action='claim' then
    if r.details->>'side'='매수' then
      insert into cherrypulse_private.manual_paper_buys(owner_id,trade_day,symbol,qty,price)
        values(r.owner_id,day,r.details->>'code',(r.details->>'qty')::bigint,(r.details->>'price')::bigint);
    end if;
    insert into cherrypulse_private.reservation_paper_orders(owner_id,reservation_id,trade_day,started_at)
      values(r.owner_id,r.id,day,clock_timestamp());
  end if;
  return jsonb_build_object('details',r.details,'deadline',r.execute_at+interval '2 minutes');
exception when unique_violation then return '{"status":409}';
end; $$;
revoke all on function public.cp_scheduled_paper_worker(uuid,text,text,jsonb) from public,authenticated;
grant execute on function public.cp_scheduled_paper_worker(uuid,text,text,jsonb) to anon;

create or replace function cherrypulse_private.list_reservation_runs(p_session text) returns jsonb
 language plpgsql security definer set search_path='' as $$
declare owner uuid:=cherrypulse_private.pin_owner(p_session); rows jsonb;
begin
 if owner is null then return '{"status":401}'; end if;
 select coalesce(jsonb_agg(jsonb_build_object('id',r.id,'details',r.details,'version',r.version,
 'autoApproved',coalesce(r.paper_approved_version=r.version,false),'paperOrder',case when a.reservation_id is not null then jsonb_build_object('state',a.state,'startedAt',a.started_at,'sentAt',a.sent_at,'receivedAt',a.received_at,'acceptedAt',a.accepted_at,'number',a.broker_number,'executed',a.executed,'remaining',a.remaining) end,
 'executeAt',r.execute_at,'processedAt',d.processed_at,'errorCode',d.error_code,
 'status',case when r.cancelled then 'cancelled' when d.result='DRY_RUN' then 'dry_run'
   when d.result='ERROR' then 'error' when not r.dry_run_enabled or
     not cherrypulse_private.krx_reservation_day((r.execute_at at time zone 'Asia/Seoul')::date)
     or r.execute_at<=statement_timestamp()-interval '2 minutes' then 'expired'
   when r.execute_at<=statement_timestamp() then 'due' else 'scheduled' end)
 order by r.execute_at desc,r.id),'[]'::jsonb) into rows
 from cherrypulse_private.reservations r left join cherrypulse_private.reservation_dry_runs d
 on d.owner_id=r.owner_id and d.reservation_id=r.id left join cherrypulse_private.reservation_paper_orders a on a.owner_id=r.owner_id and a.reservation_id=r.id where r.owner_id=owner;
 return jsonb_build_object('rows',rows,'scheduledPaperAvailable',to_regprocedure('cherrypulse_private.dispatch_approved_paper()') is not null);
end; $$;
