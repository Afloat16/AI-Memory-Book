"""Integer-framed client for the isolated persistent Bash ASCII scanner."""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
METHODS = {"terms_ascii": 1, "ascii_tokens": 0}


def decode(value):
    if isinstance(value, dict):
        if set(value) == {"$codepoints"}:
            return "".join(chr(number) for number in value["$codepoints"])
        return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


def captured_cases(path, standard_stop):
    document = decode(json.loads(Path(path).read_bytes()))
    selected, omitted = [], []
    for case in document["cases"]:
        if case["function"] not in METHODS:
            continue
        text, query, stop = case["args"]
        if (type(text) is not str or not text.isascii() or type(query) is not bool
                or frozenset(stop) != frozenset(standard_stop)):
            omitted.append({"id": case["id"], "reason": "outside exact ASCII/boolean/standard-stop domain"})
            continue
        selected.append(case)
    return selected, omitted


class BashClient:
    def __init__(self, stop, *, bash=None, timeout=30):
        self.stop = tuple(sorted(set(stop)))
        if any(type(word) is not str or not word.isascii() for word in self.stop):
            raise ValueError("The diagnostic worker accepts ASCII stop strings")
        self.timeout = timeout
        executable = bash or shutil.which("bash")
        if not executable:
            raise RuntimeError("Bash is unavailable")
        env = os.environ.copy()
        for key in list(env):
            if key in {"BASH_ENV", "ENV"} or key.startswith("BASH_FUNC_"):
                env.pop(key, None)
        env["LC_ALL"] = "C"
        self.stderr = tempfile.TemporaryFile()
        try:
            self.process = subprocess.Popen(
                [executable, "--noprofile", "--norc", str(HERE / "worker.bash")],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                text=True, encoding="ascii", bufsize=1, env=env)
        except BaseException:
            self.stderr.close()
            raise
        try:
            if self._read() != "READY 1":
                raise RuntimeError("Unexpected Bash handshake")
            fields = [str(len(self.stop))]
            for word in self.stop:
                fields.append(str(len(word)))
                fields.extend(str(ord(character)) for character in word)
            self._write("S " + " ".join(fields))
            if self._read() != "ACK STOP":
                raise RuntimeError("Bash stop-set initialization failed")
        except BaseException:
            self.close()
            raise

    def _read(self):
        if not select.select([self.process.stdout], [], [], self.timeout)[0]:
            raise TimeoutError("Bash diagnostic response timed out")
        line = self.process.stdout.readline()
        if not line:
            self.stderr.seek(0)
            raise RuntimeError("Bash worker stopped: " + self.stderr.read().decode("utf-8", "replace")[-2000:])
        return line.rstrip("\r\n")

    def _write(self, line):
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def invoke(self, method, text, query=False, *, repetitions=1):
        if method not in METHODS:
            raise ValueError("Unsupported Bash helper")
        if type(text) is not str or not text.isascii():
            raise ValueError("Bash helper requires an exact ASCII str")
        if type(query) is not bool:
            raise TypeError("Bash helper requires an exact bool")
        if type(repetitions) is not int or not 1 <= repetitions <= 100000:
            raise ValueError("Invalid diagnostic batch length")
        prefix = "Q" if repetitions == 1 else "R"
        fields = [] if repetitions == 1 else [str(repetitions)]
        fields.extend((str(METHODS[method]), str(int(query)), str(len(text))))
        fields.extend(str(ord(character)) for character in text)
        self._write(prefix + " " + " ".join(fields))
        parts = self._read().split()
        if len(parts) < 2 or parts[0] != "OK":
            raise RuntimeError("Bash helper returned " + " ".join(parts))
        count = int(parts[1])
        result = parts[2:]
        if len(result) != count:
            raise RuntimeError("Bash result frame length differs")
        return result

    def close(self):
        if hasattr(self, "process"):
            if self.process.poll() is None:
                try:
                    self._write("X")
                except (BrokenPipeError, OSError, ValueError):
                    pass
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            if self.process.stdin:
                self.process.stdin.close()
            if self.process.stdout:
                self.process.stdout.close()
        self.stderr.close()

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()
