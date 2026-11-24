-- Exercise the real functions with a disposable RPC credential, then roll back.
begin;
do $$
declare
  fn regprocedure;
  code text := repeat('c',64);
  pc text := repeat('a',64);
  phone text := repeat('b',64);
  verifier text := repeat('d',64);
  test_auth text := 'isolated-test-only';
begin
  foreach fn in array array['public.cp_account_device(text,text,text,boolean)'::regprocedure,
    'public.cp_pair_account_device(text,boolean,text,text,text,text)'::regprocedure] loop
    execute replace(pg_get_functiondef(fn),'78d2fd4acb568ead49c941a3f15e0232a0a62b226e53aeddca937041aa58bf29',
      encode(sha256(convert_to(test_auth,'UTF8')),'hex'));
  end loop;
  assert public.cp_account_device('wrong',pc,verifier,true)=403;
  assert public.cp_account_device(test_auth,pc,verifier,true)=201;
  assert public.cp_pair_account_device(test_auth,true,code,verifier,pc,verifier)=201;
  assert public.cp_pair_account_device(test_auth,false,code,verifier,phone,verifier)=201;
  assert public.cp_pair_account_device(test_auth,false,code,verifier,repeat('e',64),verifier)=401;
  assert public.cp_account_device(test_auth,phone,verifier,false)=200;
  assert cherrypulse_private.pin_owner(public.cp_device_owner_session(test_auth,phone,verifier)->>'sessionToken') is not null;
  assert public.cp_device_owner_session('wrong',phone,verifier)->>'status'='403';
  for n in 1..4 loop
    assert public.cp_account_device(test_auth,phone,code,false)=401;
  end loop;
  assert public.cp_account_device(test_auth,phone,code,false)=429;
  assert public.cp_account_device(test_auth,phone,verifier,false)=429;
  assert public.cp_device_owner_session(test_auth,phone,verifier)->>'status'='429';
  assert public.cp_account_device(test_auth,pc,verifier,false)=200;
  assert public.cp_pair_account_device(test_auth,true,code,verifier,pc,verifier)=201;
  update cherrypulse_private.account_pairings set expires_at=now() where code_hash=code;
  assert public.cp_pair_account_device(test_auth,false,code,verifier,repeat('e',64),verifier)=401;
end $$;
rollback;
