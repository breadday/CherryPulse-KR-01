create extension if not exists pg_net;
create function cherrypulse_private.dispatch_approved_paper()
returns void language plpgsql security definer set search_path='' as $$
begin
  perform cherrypulse_private.run_reservation_dry_tick();
  perform net.http_post(url:='https://cherryplus-ui-preview.vercel.app/api/scheduled-paper',
    body:=jsonb_build_object('key',r.paper_worker_key),timeout_milliseconds:=45000)
  from cherrypulse_private.reservations r
  join cherrypulse_private.reservation_dry_runs d on d.owner_id=r.owner_id and d.reservation_id=r.id
    and d.reservation_version=r.version and d.result='DRY_RUN'
  where not r.cancelled and r.paper_approved_version=r.version and r.execute_at<=now()
    and r.execute_at>now()-interval '2 minutes' and not exists(select from cherrypulse_private.reservation_paper_orders a
      where a.owner_id=r.owner_id and a.reservation_id=r.id);
end; $$;
revoke all on function cherrypulse_private.dispatch_approved_paper() from public,anon,authenticated;
select cron.schedule('cherryplus-approved-paper','* * * * *','select cherrypulse_private.dispatch_approved_paper()');
