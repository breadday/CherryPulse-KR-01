begin;
do $$
declare challenge text; previous text; existing_owner uuid; saved record; after_reset record;
begin
 assert not has_function_privilege('anon','cherrypulse_private.issue_owner_pin_recovery()','EXECUTE');
 assert not has_function_privilege('authenticated','cherrypulse_private.issue_owner_pin_recovery()','EXECUTE');
 assert not has_table_privilege('anon','cherrypulse_private.pin_recovery','SELECT');
 select owner_id into existing_owner from cherrypulse_private.pin_access where singleton;
 insert into cherrypulse_private.board_snapshots values(existing_owner,1,'{"format":"cherrypulse-board-draft","schemaVersion":1,"symbols":[],"patterns":[]}',now());
 select (select jsonb_agg(to_jsonb(r) order by id) from cherrypulse_private.reservations r) as reservations,
 (select jsonb_agg(to_jsonb(b)) from cherrypulse_private.board_snapshots b) as board into saved;
 assert public.cp_owner_pin_settings(null,null)='{"configured":false}'::jsonb;
 challenge:=cherrypulse_private.issue_owner_pin_recovery();
 assert public.cp_owner_pin_settings(challenge,'4372')='{"configured":true}'::jsonb;
 previous:=public.cp_pin_login('4372')->>'sessionToken';
 assert previous is not null;
 assert public.cp_owner_pin_settings(challenge,'5936')->>'status'='403';
 challenge:=cherrypulse_private.issue_owner_pin_recovery();
 update cherrypulse_private.pin_recovery set expires_at=now();
 assert public.cp_owner_pin_settings(challenge,'5936')->>'status'='403';
 challenge:=cherrypulse_private.issue_owner_pin_recovery();
 assert public.cp_owner_pin_settings(challenge,'5936')='{"configured":true}'::jsonb;
 assert cherrypulse_private.pin_owner(previous) is null;
 assert cherrypulse_private.pin_owner(public.cp_pin_login('5936')->>'sessionToken')=existing_owner;
 select (select jsonb_agg(to_jsonb(r) order by id) from cherrypulse_private.reservations r) as reservations,
 (select jsonb_agg(to_jsonb(b)) from cherrypulse_private.board_snapshots b) as board into after_reset;
 assert saved is not distinct from after_reset;
end $$;
rollback;
