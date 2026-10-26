-- Rollback-only integration probe: no real user data or persistent test accounts.
begin;
select set_config('cp_test.owner',gen_random_uuid()::text,true);
select set_config('cp_test.other',gen_random_uuid()::text,true);
insert into auth.users(id) values (current_setting('cp_test.owner')::uuid),(current_setting('cp_test.other')::uuid);
select set_config('request.jwt.claims', jsonb_build_object('sub',current_setting('cp_test.owner'),'role','authenticated')::text, true);
set local role authenticated;
do $$
declare
  snap jsonb := '{"format":"cherrypulse-board-draft","schemaVersion":1,"symbols":[],"patterns":[]}';
  k uuid := gen_random_uuid();
  first_result jsonb;
begin
  assert public.cp_load_board()->>'revision'='0','empty revision';
  first_result := public.cp_save_board(snap,0,k);
  assert first_result->>'revision'='1','initial write';
  assert public.cp_save_board(snap,0,k)=first_result,'idempotent replay';
  assert public.cp_save_board(snap,1,k)->>'code'='IDEMPOTENCY_MISMATCH','key reuse';
  assert public.cp_save_board(snap,0,gen_random_uuid())->>'code'='VERSION_CONFLICT','stale version';
  assert public.cp_save_board('{}',1,gen_random_uuid())->>'code'='VALIDATION_FAILED','invalid snapshot';
  assert public.cp_save_board(snap,1,gen_random_uuid())->>'revision'='2','next version';
  assert public.cp_load_board()->'snapshot'=snap,'roundtrip';
  perform set_config('request.jwt.claims',jsonb_build_object('sub',current_setting('cp_test.other'),'role','authenticated')::text,true);
  assert public.cp_load_board()->>'revision'='0','other user isolation';
  assert (select count(*) from cherrypulse_private.board_snapshots)=0,'RLS blocks other owner';
  perform set_config('request.jwt.claims',jsonb_build_object('sub',current_setting('cp_test.other'),'role','authenticated','is_anonymous',true)::text,true);
  assert public.cp_load_board()->>'code'='UNAUTHENTICATED','anonymous auth rejected';
end $$;
reset role;
do $$ begin
  assert not has_function_privilege('anon','public.cp_load_board()','execute'),'anon load revoked';
  assert not has_function_privilege('anon','public.cp_save_board(jsonb,integer,uuid)','execute'),'anon save revoked';
end $$;
rollback;
select 'PASS: 12 DB assertions, all probe writes rolled back' as result;
