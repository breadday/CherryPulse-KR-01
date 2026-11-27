-- Transaction-only local fixture. Force an open test date so CI also works on holidays.
begin;
create or replace function cherrypulse_private.krx_reservation_day(day date) returns boolean
language sql immutable as $$ select true $$;
update cherrypulse_private.pin_access set pin_hash=extensions.crypt('0123',extensions.gen_salt('bf',4)),failed_attempts=0,locked_until=null;
do $$
declare
  fn regprocedure; t text:=public.cp_pin_login('0123')->>'sessionToken';
  owner uuid:=cherrypulse_private.pin_owner(t); id uuid:=gen_random_uuid();
  auth text:='isolated-paper-fixture'; r jsonb; details jsonb;
begin
  foreach fn in array array['public.cp_reservation_paper(text,text,uuid,integer,text,jsonb)'::regprocedure,
    'public.cp_claim_manual_paper_buy(text,text,text,bigint,bigint)'::regprocedure] loop
    execute replace(pg_get_functiondef(fn),'78d2fd4acb568ead49c941a3f15e0232a0a62b226e53aeddca937041aa58bf29',
      encode(sha256(convert_to(auth,'UTF8')),'hex'));
  end loop;
  details:=jsonb_build_object('code','023160','side','매수','type','지정가','qty',3,'price',18080,'name','테스트',
    'date',to_char(now() at time zone 'Asia/Seoul','YYYY-MM-DD'),'time',to_char(now() at time zone 'Asia/Seoul','HH24:MI'));
  insert into cherrypulse_private.reservations(owner_id,id,details,original_details,execute_at)
    values(owner,id,details,details,now()-interval '1 second');
  assert public.cp_reservation_paper(t,'wrong',id,1,'claim','{}')->>'status'='403';
  assert public.cp_reservation_paper(t,auth,id,1,'preview','{}')->'details'=details;
  assert (public.cp_reservations(t,'list',null,null,null)->'rows'->0->'paperOrder')='null'::jsonb;
  assert public.cp_reservation_paper(t,auth,id,1,'claim',jsonb_build_object('startedAt',now()))->'details'=details;
  assert public.cp_reservation_paper(t,auth,id,1,'claim','{}')->>'status'='409','no resend after restart';
  assert public.cp_reservation_paper(t,auth,id,1,'inspect','{}')->>'state'='unknown';
  assert public.cp_reservation_paper(t,auth,id,1,'response',jsonb_build_object('state','accepted','number','000123',
    'sentAt',now(),'receivedAt',now(),'responseCode',0))->>'ok'='true';
  assert public.cp_reservation_paper(t,auth,id,1,'observe','{"state":"unfilled","number":"000123","executed":0,"remaining":3}')->>'ok'='true';
  assert public.cp_reservation_paper(t,auth,id,1,'observe','{"state":"partial","number":"000123","executed":1,"remaining":2}')->>'ok'='true';
  assert public.cp_reservation_paper(t,auth,id,1,'observe','{"state":"filled","number":"000123","executed":3,"remaining":0}')->>'ok'='true';
  perform public.cp_reservation_paper(t,auth,id,1,'observe','{"state":"unfilled","number":"000123","executed":0,"remaining":3}');
  r:=public.cp_reservations(t,'list',null,null,null)->'rows'->0->'paperOrder';
  assert r->>'state'='filled' and r->>'remaining'='0' and r->>'number'='000123';
end $$;
rollback;
