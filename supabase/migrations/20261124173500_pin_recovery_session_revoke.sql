create or replace function cherrypulse_private.owner_pin_settings(p_code text,p_pin text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare owner uuid;
begin
 if p_code is null and p_pin is null then
   return jsonb_build_object('configured',exists(select from cherrypulse_private.pin_access where singleton and pin_hash is not null));
 end if;
 if p_code is null or p_code !~ '^[a-f0-9]{64}$' or p_pin is null or p_pin !~ '^[0-9]{4}$' then return '{"status":422}'; end if;
 select owner_id into owner from cherrypulse_private.pin_access where singleton for update;
 delete from cherrypulse_private.pin_recovery where owner_id=owner and expires_at>clock_timestamp()
 and digest=sha256(convert_to(p_code,'UTF8'));
 if not found then return '{"status":403}'; end if;
 update cherrypulse_private.pin_access set pin_hash=extensions.crypt(p_pin,extensions.gen_salt('bf',12)),
 failed_attempts=0,locked_until=null where owner_id=owner;
 delete from cherrypulse_private.pin_sessions where expires_at > statement_timestamp();
 return '{"configured":true}';
end $$;
