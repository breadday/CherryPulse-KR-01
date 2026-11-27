-- Preserve deployed login/recovery implementations, existing grants and owner credentials.
do $$
declare
  target regprocedure;
  definition text;
begin
  foreach target in array array[
    'cherrypulse_private.cp_pin_login(text)'::regprocedure,
    'cherrypulse_private.owner_pin_settings(text,text)'::regprocedure
  ] loop
    definition := pg_get_functiondef(target);
    if strpos(definition, '''^[0-9]{4}$''') = 0 then
      raise exception 'Unexpected PIN validator in %',target;
    end if;
    execute replace(definition, '''^[0-9]{4}$''', '''^[0-9]{4}([0-9]{2})?$''');
  end loop;
end $$;
