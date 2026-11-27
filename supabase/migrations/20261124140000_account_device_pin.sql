create table cherrypulse_private.account_devices (
  device text primary key,
  verifier text not null,
  failures smallint not null default 0,
  expires_at timestamptz not null default (now() + interval '90 days')
);
alter table cherrypulse_private.account_devices enable row level security;
revoke all on cherrypulse_private.account_devices from public, anon, authenticated;

create function public.cp_account_device(p_auth text, p_device text, p_verifier text, p_register boolean)
returns integer language plpgsql security definer set search_path = '' as $$
declare
  registered cherrypulse_private.account_devices%rowtype;
begin
  if p_auth is null or encode(sha256(convert_to(p_auth,'UTF8')),'hex') <>
     '78d2fd4acb568ead49c941a3f15e0232a0a62b226e53aeddca937041aa58bf29' then return 403; end if;
  if p_device is null or p_verifier is null or p_device !~ '^[a-f0-9]{64}$'
     or p_verifier !~ '^[a-f0-9]{64}$' then return 422; end if;
  if p_register then
    delete from cherrypulse_private.account_devices where expires_at <= now();
    insert into cherrypulse_private.account_devices (device,verifier) values (p_device,p_verifier);
    return 201;
  end if;
  select * into registered from cherrypulse_private.account_devices where device=p_device for update;
  if not found or registered.expires_at <= now() then return 401; end if;
  if registered.failures >= 5 then return 429; end if;
  if registered.verifier <> p_verifier then
    update cherrypulse_private.account_devices set failures=failures+1 where device=p_device;
    return case when registered.failures=4 then 429 else 401 end;
  end if;
  update cherrypulse_private.account_devices set failures=0 where device=p_device;
  return 200;
end $$;
revoke all on function public.cp_account_device(text,text,text,boolean) from public, anon, authenticated;
grant execute on function public.cp_account_device(text,text,text,boolean) to anon;
