"""Run against the disposable PostgreSQL database prepared by the CI job."""
import subprocess

TICK = "select cherrypulse_private.run_reservation_dry_tick"
COMMAND = ["psql", "-XAtq", "-v", "ON_ERROR_STOP=1"]


def sql(statement):
    return subprocess.check_output([*COMMAND, "-c", statement], text=True).strip()


def run(at):
    return sql(f"{TICK}('2026-11-24 {at}+09')")


assert run("08:57:59") == "0"  # all scheduled instants are still in the future
worker = subprocess.Popen(COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
try:
    worker.stdin.write(f"begin; {TICK}('2026-11-24 09:00+09');\n")
    worker.stdin.flush()
    assert worker.stdout.readline().strip() == "2"
    assert run("09:00:00") == "0"  # another connection holds the transaction lock
finally:
    worker.stdin.close()  # exit with an open transaction, like an interrupted process
    worker.wait(timeout=10)
assert run("09:00:00") == "2"  # rollback made both unfinished records eligible
assert run("09:00:01") == "0"  # committed results survive new connections
assert run("09:01:00") == "1"
assert sql(f"{TICK}('2026-12-25 09:00+09')") == "0"
assert sql("""select string_agg((r.details->>'code')||':'||d.result,',' order by r.details->>'code')
 from cherrypulse_private.reservation_dry_runs d join cherrypulse_private.reservations r
 on (d.owner_id,d.reservation_id)=(r.owner_id,r.id)""") == "future:DRY_RUN,invalid_total:ERROR,on_time:DRY_RUN"
assert sql("""select has_function_privilege('anon',
 'cherrypulse_private.run_reservation_dry_tick(timestamptz)','execute')""") == "f"
print("PASS: KST boundary, concurrent lock, restart, replay, error, expired, cancelled, holiday, private access")
