create extension if not exists pg_cron;
select cron.schedule('cherryplus-reservation-dry-run','* * * * *',
 'select cherrypulse_private.run_reservation_dry_tick()');
