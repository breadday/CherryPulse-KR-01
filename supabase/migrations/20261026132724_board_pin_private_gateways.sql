-- Keep privileged implementations outside the exposed API schema.
alter function public.cp_pin_login(text) set schema cherrypulse_private;
alter function public.cp_pin_load_board(text) set schema cherrypulse_private;
alter function public.cp_pin_logout(text) set schema cherrypulse_private;
alter function public.cp_pin_save_board(text,jsonb,integer,uuid) set schema cherrypulse_private;
grant usage on schema cherrypulse_private to anon;

create function public.cp_pin_login(p_pin text) returns jsonb
language sql security invoker set search_path='' as $$
  select cherrypulse_private.cp_pin_login(p_pin);
$$;
create function public.cp_pin_load_board(p_session text) returns jsonb
language sql security invoker set search_path='' as $$
  select cherrypulse_private.cp_pin_load_board(p_session);
$$;
create function public.cp_pin_logout(p_session text) returns jsonb
language sql security invoker set search_path='' as $$
  select cherrypulse_private.cp_pin_logout(p_session);
$$;
create function public.cp_pin_save_board(p_session text,p_snapshot jsonb,p_expected_revision integer,p_request_key uuid) returns jsonb
language sql security invoker set search_path='' as $$
  select cherrypulse_private.cp_pin_save_board(p_session,p_snapshot,p_expected_revision,p_request_key);
$$;
revoke all on function public.cp_pin_login(text) from public;
revoke all on function public.cp_pin_load_board(text) from public;
revoke all on function public.cp_pin_logout(text) from public;
revoke all on function public.cp_pin_save_board(text,jsonb,integer,uuid) from public;
grant execute on function public.cp_pin_login(text) to anon,authenticated;
grant execute on function public.cp_pin_load_board(text) to anon,authenticated;
grant execute on function public.cp_pin_logout(text) to anon,authenticated;
grant execute on function public.cp_pin_save_board(text,jsonb,integer,uuid) to anon,authenticated;

-- No direct access to PIN/session rows for API roles; only checked private gateways.
create policy pin_access_no_direct_access on cherrypulse_private.pin_access
  as restrictive for all to public using(false) with check(false);
create policy pin_sessions_no_direct_access on cherrypulse_private.pin_sessions
  as restrictive for all to public using(false) with check(false);
