-- Single-owner sessions are resolved inside the same transaction as every operation.
create table cherrypulse_private.reservations (
 owner_id uuid not null references auth.users(id),
 id uuid not null,
 version integer not null default 1,
 details jsonb not null,
 original_details jsonb not null,
 execute_at timestamptz not null,
 cancelled boolean not null default false,
 primary key(owner_id,id)
);
alter table cherrypulse_private.reservations enable row level security;
revoke all on cherrypulse_private.reservations from public,anon,authenticated;
create unique index reservations_active_order on cherrypulse_private.reservations
 (owner_id, (details - 'name')) where not cancelled;

create function cherrypulse_private.manage_reservations(
 p_session text,p_action text,p_id uuid,p_version integer,p_details jsonb
) returns jsonb language plpgsql security definer set search_path='' as $$
declare
 owner uuid := cherrypulse_private.pin_owner(p_session);
 item cherrypulse_private.reservations%rowtype;
 target timestamptz;
 day date;
 rows jsonb;
begin
 if owner is null then return '{"status":401}'; end if;
 if p_action='list' then
   select coalesce(jsonb_agg(jsonb_build_object('id',r.id,'version',r.version,'details',r.details,
    'status',case when r.cancelled then 'cancelled' when r.execute_at<=clock_timestamp() then 'expired' else 'scheduled' end)
    order by r.execute_at desc,r.id),'[]'::jsonb) into rows
   from cherrypulse_private.reservations r where r.owner_id=owner;
   return jsonb_build_object('rows',rows);
 end if;
 if p_id is null or p_action is null or p_action not in ('create','update','cancel') then return '{"status":422}'; end if;
 if p_action in ('create','update') then
   if p_details is null or jsonb_typeof(p_details)<>'object' then return '{"status":422}'; end if;
   if not (p_details ?& array['code','name','side','type','price','qty','date','time'])
      or p_details - array['code','name','side','type','price','qty','date','time'] <> '{}'
      or not coalesce(jsonb_typeof(p_details->'code')='string' and p_details->>'code' ~ '^[0-9]{6}$'
       and jsonb_typeof(p_details->'name')='string' and length(trim(p_details->>'name')) between 1 and 100
       and p_details->>'side' in ('매수','매도') and p_details->>'type' in ('지정가','시장가')
       and jsonb_typeof(p_details->'qty')='number' and p_details->>'qty' ~ '^[1-9][0-9]{0,14}$'
       and ((p_details->>'type'='시장가' and p_details->'price'='null'::jsonb) or
         (p_details->>'type'='지정가' and jsonb_typeof(p_details->'price')='number' and p_details->>'price' ~ '^[1-9][0-9]{0,14}$'))
       and p_details->>'date' ~ '^2026-[0-9]{2}-[0-9]{2}$'
       and p_details->>'time' ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$',false)
     then return '{"status":422}'; end if;
   day := (p_details->>'date')::date;
   target := (day + (p_details->>'time')::time) at time zone 'Asia/Seoul';
   if extract(isodow from day)>5 or to_char(day,'MM-DD')=any(array[
     '01-01','02-16','02-17','02-18','03-02','05-01','05-05','05-25','06-03','07-17',
     '08-17','09-24','09-25','10-05','10-09','12-25','12-31']) then return '{"status":422}'; end if;
 end if;
 if p_action='create' then
   select * into item from cherrypulse_private.reservations where owner_id=owner and id=p_id;
   if found then
     if item.original_details=p_details then return jsonb_build_object('id',item.id,'version',item.version); end if;
     return '{"status":409}';
   end if;
   if target<=clock_timestamp() then return '{"status":422}'; end if;
   insert into cherrypulse_private.reservations(owner_id,id,details,original_details,execute_at)
    values(owner,p_id,p_details,p_details,target) returning * into item;
 else
   select * into item from cherrypulse_private.reservations where owner_id=owner and id=p_id for update;
   if not found then return '{"status":404}'; end if;
   if item.cancelled or item.execute_at<=clock_timestamp() or item.version is distinct from p_version then return '{"status":409}'; end if;
   if target<=clock_timestamp() then return '{"status":422}'; end if;
   update cherrypulse_private.reservations set version=version+1,cancelled=p_action='cancel',
    details=coalesce(case when p_action='update' then p_details end,details),execute_at=coalesce(target,execute_at)
    where owner_id=owner and id=p_id returning * into item;
 end if;
 return jsonb_build_object('id',item.id,'version',item.version);
exception when unique_violation then return '{"status":409}';
 when invalid_datetime_format or datetime_field_overflow then return '{"status":422}';
end; $$;
create function public.cp_reservations(p_session text,p_action text,p_id uuid,p_version integer,p_details jsonb)
 returns jsonb language sql security invoker set search_path='' as $$
 select cherrypulse_private.manage_reservations(p_session,p_action,p_id,p_version,p_details);
$$;
revoke all on function cherrypulse_private.manage_reservations(text,text,uuid,integer,jsonb),
 public.cp_reservations(text,text,uuid,integer,jsonb) from public;
grant execute on function cherrypulse_private.manage_reservations(text,text,uuid,integer,jsonb),
 public.cp_reservations(text,text,uuid,integer,jsonb) to anon,authenticated;
