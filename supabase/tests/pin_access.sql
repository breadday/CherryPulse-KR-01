-- Transaction-only PIN probe. The fixture PIN is unrelated to the configured PIN.
begin;
update cherrypulse_private.pin_access set pin_hash=extensions.crypt('0123',extensions.gen_salt('bf',4)),failed_attempts=0,locked_until=null;
set local role anon;
do $$
declare token text; result jsonb; revision integer;
begin
  assert public.cp_pin_login('bad')->>'code'='PIN_FORMAT_INVALID','PIN shape';
  assert public.cp_pin_login('9999')->>'code'='PIN_INCORRECT','incorrect PIN';
  result:=public.cp_pin_login('0123'); token:=result->>'sessionToken';
  assert token ~ '^[a-f0-9]{64}$','opaque bearer';
  assert public.cp_pin_load_board('bad')->>'code'='UNAUTHENTICATED','no token no data';
  result:=public.cp_pin_load_board(token); revision:=(result->>'revision')::integer;
  assert revision>=0,'valid session load';
  result:=public.cp_pin_save_board(token,'{"format":"cherrypulse-board-draft","schemaVersion":1,"symbols":[],"patterns":[]}',revision,gen_random_uuid());
  assert (result->>'revision')::integer=revision+1,'valid session save';
  assert public.cp_pin_save_board('bad','{}',0,gen_random_uuid())->>'code'='UNAUTHENTICATED','invalid session save';
  perform public.cp_pin_logout(token);
  assert public.cp_pin_load_board(token)->>'code'='UNAUTHENTICATED','logout revokes immediately';
  for attempt in 1..5 loop result:=public.cp_pin_login('9999'); end loop;
  assert result->>'code'='PIN_LOCKED','global attempts limit';
  assert public.cp_pin_login('0123')->>'code'='PIN_LOCKED','correct PIN blocked during lock';
end $$;
reset role;
update cherrypulse_private.pin_access set locked_until=now()-interval '1 second';
set local role anon;
do $$ begin
  assert public.cp_pin_login('0123')->>'sessionToken' is not null,'expired lock resets';
end $$;
reset role;
do $$ begin
  assert not has_table_privilege('anon','cherrypulse_private.pin_access','select'),'PIN hash private';
  assert not has_table_privilege('anon','cherrypulse_private.pin_sessions','select'),'session hashes private';
end $$;
rollback;
select 'PASS: PIN format/login/load/save/logout/lockout and private privileges; fixture writes rolled back' as result;
