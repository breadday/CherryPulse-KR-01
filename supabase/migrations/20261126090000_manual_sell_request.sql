create table cherrypulse_private.manual_paper_sell_requests (
  request_id uuid primary key, owner_id uuid not null, trade_day date not null, symbol text not null,
  qty bigint not null, price bigint not null, created_at timestamptz not null default now()
);
alter table cherrypulse_private.manual_paper_sell_requests enable row level security;
revoke all on cherrypulse_private.manual_paper_sell_requests from public, anon, authenticated;

create function public.cp_claim_manual_sell_request(p_session text, p_auth text, p_request uuid, p_symbol text, p_qty bigint, p_price bigint)
returns integer language plpgsql security definer set search_path='' as $$
declare owner uuid := cherrypulse_private.pin_owner(p_session);
begin
  if owner is null or p_auth is null or encode(sha256(convert_to(p_auth,'UTF8')),'hex') <>
     '78d2fd4acb568ead49c941a3f15e0232a0a62b226e53aeddca937041aa58bf29' then return 403; end if;
  if p_request is null or p_symbol is null or p_symbol !~ '^[0-9]{6}$' or p_qty is null or p_qty <= 0
     or p_price is null or p_price <= 0 then return 422; end if;
  insert into cherrypulse_private.manual_paper_sell_requests(request_id,owner_id,trade_day,symbol,qty,price)
    values(p_request,owner,(now() at time zone 'Asia/Seoul')::date,p_symbol,p_qty,p_price)
    on conflict do nothing;
  if not found then return 409; end if;
  return 201;
end; $$;
revoke all on function public.cp_claim_manual_sell_request(text,text,uuid,text,bigint,bigint) from public;
grant execute on function public.cp_claim_manual_sell_request(text,text,uuid,text,bigint,bigint) to anon;
