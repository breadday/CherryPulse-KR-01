create table cherrypulse_private.paper_order_changes (
  owner_id uuid not null, order_key text not null, request_id uuid not null,
  primary key(owner_id,order_key)
);
alter table cherrypulse_private.paper_order_changes enable row level security;
revoke all on cherrypulse_private.paper_order_changes from public, anon, authenticated;

create function public.cp_claim_order_change(p_session text,p_auth text,p_key text,p_request uuid,p_rejected boolean)
returns integer language plpgsql security definer set search_path='' as $$
declare owner uuid := cherrypulse_private.pin_owner(p_session);
begin
  if owner is null or p_auth is null or encode(sha256(convert_to(p_auth,'UTF8')),'hex') <>
     '78d2fd4acb568ead49c941a3f15e0232a0a62b226e53aeddca937041aa58bf29' then return 403; end if;
  if p_key is null or p_key !~ '^[a-f0-9]{64}$' or p_request is null then return 422; end if;
  if p_rejected then
    delete from cherrypulse_private.paper_order_changes where owner_id=owner and order_key=p_key and request_id=p_request;
    return 200;
  end if;
  insert into cherrypulse_private.paper_order_changes values(owner,p_key,p_request) on conflict do nothing;
  if not found then return 409; end if;
  return 201;
end; $$;
revoke all on function public.cp_claim_order_change(text,text,text,uuid,boolean) from public;
grant execute on function public.cp_claim_order_change(text,text,text,uuid,boolean) to anon;
