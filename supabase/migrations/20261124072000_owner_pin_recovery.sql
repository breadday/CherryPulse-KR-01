-- Only the project administrator in SQL Editor can issue an owner-bound challenge.
create table cherrypulse_private.pin_recovery (
 owner_id uuid primary key references auth.users(id),
 digest bytea not null,
 expires_at timestamptz not null
);
alter table cherrypulse_private.pin_recovery enable row level security;
revoke all on cherrypulse_private.pin_recovery from public,anon,authenticated,service_role;
create function cherrypulse_private.issue_owner_pin_recovery() returns text
language plpgsql security invoker set search_path='' as $$
declare owner uuid; challenge text;
begin
 select owner_id into strict owner from cherrypulse_private.pin_access where singleton for update;
 challenge:=encode(extensions.gen_random_bytes(32),'hex');
 insert into cherrypulse_private.pin_recovery values(owner,sha256(convert_to(challenge,'UTF8')),clock_timestamp()+interval '10 minutes')
 on conflict(owner_id) do update set digest=excluded.digest,expires_at=excluded.expires_at;
 return challenge;
end $$;
revoke all on function cherrypulse_private.issue_owner_pin_recovery() from public,anon,authenticated,service_role;

create function cherrypulse_private.owner_pin_settings(p_code text,p_pin text) returns jsonb
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
 delete from cherrypulse_private.pin_sessions;
 return '{"configured":true}';
end $$;
create function public.cp_owner_pin_settings(p_code text,p_pin text) returns jsonb
 language sql security invoker set search_path='' as $$ select cherrypulse_private.owner_pin_settings(p_code,p_pin) $$;
revoke all on function cherrypulse_private.owner_pin_settings(text,text),public.cp_owner_pin_settings(text,text) from public;
grant execute on function cherrypulse_private.owner_pin_settings(text,text),public.cp_owner_pin_settings(text,text) to anon,authenticated;
