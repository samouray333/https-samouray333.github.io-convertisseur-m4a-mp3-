"""Protocole JSON avec le processus moteur (interpréteur courant, moteur de test)."""

import sys
from pathlib import Path


def test_worker_progress_events():
    from doublys.core.engines import installer
    from doublys.core.engines.neural import WorkerProcess

    installer.engine_root("dummy").mkdir(parents=True, exist_ok=True)
    w = WorkerProcess("dummy", "dummy", Path(sys.executable), installer.worker_env("dummy"))
    w.start()
    try:
        w.request("load", device="cpu", options={})
        seen = []
        res = w.request("translate", texts=["Hello", "World", "Again"], on_progress=lambda v, m: seen.append(v))
        assert res["texts"] == ["[fr] Hello", "[fr] World", "[fr] Again"]
        assert seen and seen[-1] == 1.0
        assert not w._progress  # rappel retiré une fois la requête terminée
    finally:
        w.stop()
