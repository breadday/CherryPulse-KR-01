-- Only a verified registered device can create a short-lived owner session.
create function public.cp_device_owner_session(p_auth text,p_device text,p_verifier text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare checked integer; token text;
begin
  checked := public.cp_account_device(p_auth,p_device,p_verifier,false);
  if checked <> 200 then return jsonb_build_object('status',checked); end if;
  if not exists(select from cherrypulse_private.pin_access where singleton) then
    return '{"status":503}';
  end if;
  token := encode(extensions.gen_random_bytes(32),'hex');
  delete from cherrypulse_private.pin_sessions where expires_at <= now();
  insert into cherrypulse_private.pin_sessions(token_hash,expires_at)
    values(encode(sha256(convert_to(token,'UTF8')),'hex'),now()+interval '15 minutes');
  return jsonb_build_object('sessionToken',token);
end $$;
revoke all on function public.cp_device_owner_session(text,text,text) from public,anon,authenticated;
grant execute on function public.cp_device_owner_session(text,text,text) to anon;
