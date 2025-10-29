"""
Safe import helper with timeout.

Use a child process to attempt module import. If it doesn't complete within
timeout_seconds, terminate and raise TimeoutError. On success, perform the
actual import in the caller process and return the requested symbol.
"""
from multiprocessing import Process, Queue
from typing import Any
import importlib


def _attempt_import(module_name: str, q: Queue) -> None:
    try:
        importlib.import_module(module_name)
        q.put((True, None))
    except Exception as e:
        q.put((False, repr(e)))


def import_symbol_with_timeout(module_name: str, symbol_name: str, timeout_seconds: float = 5.0) -> Any:
    q: Queue = Queue(maxsize=1)
    p: Process = Process(target=_attempt_import, args=(module_name, q), daemon=True)
    p.start()
    p.join(timeout_seconds)

    if p.is_alive():
        try:
            p.terminate()
        finally:
            p.join(1.0)
        raise TimeoutError(f"Importing module '{module_name}' exceeded {timeout_seconds}s")

    ok, err = q.get() if not q.empty() else (False, "Unknown import state")
    if not ok:
        raise ImportError(f"Failed to import '{module_name}': {err}")

    # Import again in current process to get the actual symbol
    mod = importlib.import_module(module_name)
    if not hasattr(mod, symbol_name):
        raise AttributeError(f"Module '{module_name}' has no attribute '{symbol_name}'")
    return getattr(mod, symbol_name)


