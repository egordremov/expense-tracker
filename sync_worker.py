"""Run one sync in a process that the API can stop on timeout."""
import json
import os
import sys
from contextlib import redirect_stdout
from resource_limits import apply_worker_limits


def run():
    os.umask(0o077)
    apply_worker_limits()
    request = json.load(sys.stdin)
    with redirect_stdout(sys.stderr):
        import main

        main.db.init_db()
        main.cfg.invalidate()
        main._state.update(request.pop("state"))
        result = main.sync(**request)
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    run()
