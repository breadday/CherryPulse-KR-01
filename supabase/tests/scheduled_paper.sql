begin;
create or replace function cherrypulse_private.krx_reservation_day(day date) returns boolean language sql immutable as $$select true$$;
update cherrypulse_private.pin_access set pin_hash=extensions.crypt('0123',extensions.gen_salt('bf',4)),failed_attempts=0,locked_until=null;
do $$
declare fn regprocedure; session text:=public.cp_pin_login('0123')->>'sessionToken';
  auth text:='worker-fixture'; rid uuid:=gen_random_uuid(); k uuid; old_key uuid; owner uuid:=cherrypulse_private.pin_owner(session);
  details jsonb:='{"code":"023160","name":"테스트","side":"매수","type":"지정가","qty":1,"price":19590,"date":"2099-01-05","time":"09:05"}';
begin
  -- Keep this fixture valid after the supported 2026 calendar expires.
  execute replace(pg_get_functiondef('cherrypulse_private.manage_reservations(text,text,uuid,integer,jsonb)'::regprocedure),'^2026-','^2099-');
  foreach fn in array array['public.cp_save_scheduled_paper(text,text,text,uuid,integer,jsonb)'::regprocedure,
    'public.cp_scheduled_paper_worker(uuid,text,text,jsonb)'::regprocedure] loop
    execute replace(pg_get_functiondef(fn),'78d2fd4acb568ead49c941a3f15e0232a0a62b226e53aeddca937041aa58bf29',encode(sha256(convert_to(auth,'UTF8')),'hex'));
  end loop;
  assert public.cp_save_scheduled_paper(session,'bad','create',rid,null,details)->>'status'='403';
  assert public.cp_save_scheduled_paper(session,auth,'create',rid,null,details)->>'version'='1';
  select paper_worker_key into strict old_key from cherrypulse_private.reservations where id=rid;
  assert public.cp_scheduled_paper_worker(old_key,auth,'preview','{}')->>'status'='409';
  assert public.cp_reservations(session,'update',rid,1,details)->>'version'='2';
  assert public.cp_scheduled_paper_worker(old_key,auth,'preview','{}')->>'status'='404';
  assert public.cp_save_scheduled_paper(session,auth,'update',rid,2,details)->>'version'='3';
  select paper_worker_key into strict k from cherrypulse_private.reservations where id=rid;
  update cherrypulse_private.reservations set execute_at=now()-interval '1 second' where id=rid;
  assert public.cp_scheduled_paper_worker(k,auth,'claim','{}')->>'status'='409';
  insert into cherrypulse_private.reservation_dry_runs values(owner,rid,3,now(),now(),'DRY_RUN',null);
  assert public.cp_scheduled_paper_worker(k,auth,'preview','{}')->'details'=details;
  assert public.cp_scheduled_paper_worker(k,auth,'claim','{}')->'details'=details;
  assert public.cp_scheduled_paper_worker(k,auth,'claim','{}')->>'status'='409';
  assert public.cp_scheduled_paper_worker(k,auth,'response',jsonb_build_object('sentAt',now(),'receivedAt',now(),'state','accepted','number','000123'))->>'ok'='true';
  assert exists(select from cherrypulse_private.reservation_paper_orders where reservation_id=rid and state='accepted' and broker_number='000123');
end $$;
rollback;
