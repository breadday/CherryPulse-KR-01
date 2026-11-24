create table cherrypulse_private.account_pairings (
  code_hash text primary key,
  pin_hash text not null,
  issuer text not null unique,
  failures smallint not null default 0,
  expires_at timestamptz not null default (now() + interval '3 minutes')
);
alter table cherrypulse_private.account_pairings enable row level security;
revoke all on cherrypulse_private.account_pairings from public, anon, authenticated;

create function public.cp_pair_account_device(p_auth text, p_issue boolean, p_code text,
  p_pin text, p_device text, p_verifier text)
returns integer language plpgsql security definer set search_path = '' as $$
declare
  pairing cherrypulse_private.account_pairings%rowtype;
  checked integer;
begin
  if p_auth is null or encode(sha256(convert_to(p_auth,'UTF8')),'hex') <>
     '78d2fd4acb568ead49c941a3f15e0232a0a62b226e53aeddca937041aa58bf29' then return 403; end if;
  if p_code is null or p_pin is null or p_code !~ '^[a-f0-9]{64}$'
     or p_pin !~ '^[a-f0-9]{64}$' then return 422; end if;
  if p_issue then
    checked := public.cp_account_device(p_auth,p_device,p_verifier,false);
    if checked <> 200 then return checked; end if;
    delete from cherrypulse_private.account_pairings where expires_at <= now() or issuer=p_device;
    insert into cherrypulse_private.account_pairings(code_hash,pin_hash,issuer) values(p_code,p_pin,p_device);
    return 201;
  end if;
  select * into pairing from cherrypulse_private.account_pairings where code_hash=p_code for update;
  if not found or pairing.expires_at <= now() then return 401; end if;
  if pairing.failures >= 5 then return 429; end if;
  if p_pin <> pairing.pin_hash then
    update cherrypulse_private.account_pairings set failures=failures+1 where code_hash=p_code;
    return case when pairing.failures=4 then 429 else 401 end;
  end if;
  checked := public.cp_account_device(p_auth,p_device,p_verifier,true);
  if checked=201 then delete from cherrypulse_private.account_pairings where code_hash=p_code; end if;
  return checked;
end $$;
revoke all on function public.cp_pair_account_device(text,boolean,text,text,text,text) from public, anon, authenticated;
grant execute on function public.cp_pair_account_device(text,boolean,text,text,text,text) to anon;
