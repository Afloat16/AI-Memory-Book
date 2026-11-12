"""Small Linux process-tree RSS sampler and source-free storage accounting."""
from __future__ import annotations

import os
from pathlib import Path
import resource
import threading
import time


def tree_rss(pid, proc=Path("/proc")):
    pending, seen, total, measured = [pid], set(), 0, 0
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            status = (proc / str(current) / "status").read_text()
            rss = next(int(line.split()[1]) * 1024 for line in status.splitlines()
                       if line.startswith("VmRSS:"))
            total += rss
            measured += 1
        except (OSError, StopIteration, ValueError):
            pass  # A child may exit between enumeration and sampling.
        try:
            pending.extend(int(value) for value in
                           (proc / str(current) / "task" / str(current) / "children").read_text().split())
        except (OSError, ValueError):
            pass
    return total if measured else None, measured


class Resources:
    def __init__(self, interval=.02):
        self.interval = interval
        self.phase = "setup"
        self.peaks = {}
        self.samples = {}
        self.max_processes = {}
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.started = time.perf_counter()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def sample(self):
        value, processes = tree_rss(os.getpid())
        with self.lock:
            phase = self.phase
            if value is not None:
                self.peaks[phase] = max(self.peaks.get(phase, 0), value)
                self.samples[phase] = self.samples.get(phase, 0) + 1
                self.max_processes[phase] = max(self.max_processes.get(phase, 0), processes)

    def set_phase(self, phase):
        self.sample()
        with self.lock:
            self.phase = phase
        self.sample()

    def _loop(self):
        while not self.stop.is_set():
            self.sample()
            self.stop.wait(self.interval)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
        self.sample()
        return {"sampling_interval_ms": self.interval * 1000,
                "sampled_process_tree_peak_rss_bytes": dict(self.peaks),
                "samples": dict(self.samples), "max_observed_processes": dict(self.max_processes),
                "worker_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                "sampler_wall_ms": (time.perf_counter() - self.started) * 1000,
                "boundary": "Linux worker plus live descendant RSS sampled every 20ms; shared mappings can be counted more than once. Peaks are observed lower bounds, not unique physical memory. Worker ru_maxrss includes the Python evaluator and loaded corpus. The sampler runs during all engine phases."}


def storage(root):
    root = Path(root)
    sizes = {"regular_file_bytes": 0, "regular_files": 0,
             "sqlite_main_file_bytes": 0, "sqlite_wal_file_bytes": 0, "sqlite_shm_file_bytes": 0}
    if not root.exists():
        return {**sizes, "exists": False}
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        if any(parent.is_symlink() for parent in path.parents if parent != root.parent):
            continue
        size = path.stat().st_size
        sizes["regular_files"] += 1
        sizes["regular_file_bytes"] += size
        if path.name.endswith("-wal"):
            sizes["sqlite_wal_file_bytes"] += size
        elif path.name.endswith("-shm"):
            sizes["sqlite_shm_file_bytes"] += size
        elif path.suffix in {".db", ".sqlite", ".sqlite3"}:
            sizes["sqlite_main_file_bytes"] += size
    return {**sizes, "exists": True,
            "boundary": "Allocated content lengths of regular files, excluding symlinked caches; not filesystem allocated blocks. State can contain native source-page Markdown and logs in addition to database files."}
