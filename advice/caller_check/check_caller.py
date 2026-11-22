"""D56: does the deadline_s parameter of the Python advice functions end the call early? Local server that reads the
request and never answers; the caller passes deadline_s=1.
  docker run --rm --network none -v "$PWD/advice:/adv:ro" --entrypoint python3 lcr-run-python:dev /adv/caller_check/check_caller.py
"""
import importlib.util
import socket
import threading
import time

srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(16)
conns = []
threading.Thread(target=lambda: [conns.append(srv.accept()) for _ in iter(int, 1)], daemon=True).start()
base = f"http://127.0.0.1:{srv.getsockname()[1]}"
for name, path, args in (("py-retry-budget", "/adv/R1/py-retry-budget.py", ("u-1",)),
                         ("py-idem-key", "/adv/W1/py-idem-key.py", ("ord-1", "1.00", "EUR"))):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    f = getattr(m, "get_user_profile", None) or m.create_payment
    t0 = time.monotonic()
    try:
        f(base, *args, deadline_s=1.0)
        res = "returned a result"
    except Exception as e:  # noqa: BLE001
        res = type(e).__name__
    print(f"{name}, deadline_s=1: {res} after {time.monotonic() - t0:.1f} s")
