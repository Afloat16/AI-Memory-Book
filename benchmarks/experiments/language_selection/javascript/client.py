"""Research-only persistent Node bridge. Importing does not patch production.

All subprocess and serialization overhead remains in public adapter timings.
The direct Node kernel benchmark is separately exposed, never labeled E2E.
"""
from __future__ import annotations

import atexit
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace
import unicodedata

HERE = Path(__file__).resolve().parent
MAX_SAFE_INTEGER = 2**53 - 1


def ordinary_builtin(value, module, name):
    return (type(value) is type(len) and getattr(value, "__self__", None) is module
            and getattr(value, "__name__", None) == name)


def encode(value):
    if type(value) is str:
        # JSON conflates an astral character and an explicit surrogate pair.
        # Preserve only affected inputs as exact Python code-point sequences.
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            return {"$codepoints": list(map(ord, value))}
        return value
    if type(value) in (list, tuple):
        return [encode(item) for item in value]
    if type(value) is dict:
        return {key: encode(item) for key, item in value.items()}
    return value


def decode(value):
    if type(value) is dict:
        if set(value) == {"$codepoints"}:
            return "".join(map(chr, value["$codepoints"]))
        return {key: decode(item) for key, item in value.items()}
    if type(value) is list:
        return [decode(item) for item in value]
    return value


class NodeClient:
    def __init__(self, *, native=None, node=None):
        # Capture methods before any research-only caller patches the module.
        self.native = (SimpleNamespace(**{name: getattr(native, name) for name in
            ("terms_ascii", "ascii_tokens", "unicode_tokens", "literal_positions", "evidence_units",
             "context_allocations", "excerpt_window", "fold_excerpt_source")}) if native is not None else None)
        self.node = node or os.environ.get("MEMORY_BOOK_LAB_NODE") or shutil.which("node")
        if not self.node:
            raise RuntimeError("Node is unavailable")
        self.process = subprocess.Popen([self.node, str(HERE / "worker.mjs")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1)
        self.lock = threading.Lock()
        atexit.register(self.close)
        self.log1p, self.fsum = math.log1p, math.fsum
        try:
            from memory_book import text
            self.reference_evidence_units = text._NATIVE_EVIDENCE_UNITS
        except ImportError:
            self.reference_evidence_units = None
        values = self.invoke("log1p_values", list(range(1, 41)))
        self.math_verified = (ordinary_builtin(self.log1p, math, "log1p")
            and ordinary_builtin(self.fsum, math, "fsum")
            and all(actual.hex() == self.log1p(n).hex() for n, actual in enumerate(values, 1)))
        self.normalize, self.category = unicodedata.normalize, unicodedata.category
        self.unicode_identity = self.invoke("unicode_identity")
        self.unicode_verified = (ordinary_builtin(self.normalize, unicodedata, "normalize")
            and ordinary_builtin(self.category, unicodedata, "category")
            and self.unicode_identity["properties_unicode_version"] == unicodedata.unidata_version
            and self.unicode_identity["fold_unicode_version"] == unicodedata.unidata_version)

    def close(self):
        process = self.process
        if process.poll() is None:
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=3)

    def request(self, payload):
        with self.lock:
            self.process.stdin.write(json.dumps(encode(payload), ensure_ascii=True, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("Node worker stopped: " + self.process.stderr.read())
        result = decode(json.loads(line))
        if not result["ok"]:
            raise RuntimeError(result["error"])
        return result["result"]

    def invoke(self, name, *args):
        return self.request({"op": "invoke", "name": name, "args": args})

    def _ascii(self, name, text, query, stop):
        if type(text) is not str:
            raise TypeError("text must be an exact str")
        if not text.isascii():
            raise ValueError("text must contain only ASCII code points")
        if type(query) is not bool:
            raise TypeError("query must be an exact bool")
        # Nonstandard Python membership callbacks retain the original backend.
        if query and (type(stop) not in (set, frozenset) or any(type(item) is not str for item in stop)):
            if self.native is None:
                raise TypeError("Research bridge requires a standard string stop set")
            return getattr(self.native, name)(text, query, stop)
        return self.invoke(name, text, query, list(stop) if query else [])

    def terms_ascii(self, text, query, stop):
        return self._ascii("terms_ascii", text, query, stop)

    def ascii_tokens(self, text, query, stop):
        return self._ascii("ascii_tokens", text, query, stop)

    def unicode_tokens(self, text, query, stop, zh_stop):
        if type(text) is not str:
            raise TypeError("text must be an exact str")
        if type(query) is not bool:
            raise TypeError("query must be an exact bool")
        ordinary = self.unicode_verified and all(type(values) in (set, frozenset)
            and all(type(value) is str for value in values) for values in (stop, zh_stop))
        if not ordinary:
            if self.native is None:
                raise TypeError("Research bridge requires matching Unicode tables and standard stop sets")
            return self.native.unicode_tokens(text, query, stop, zh_stop)
        return self.invoke("unicode_tokens", text, query, list(stop), list(zh_stop))

    def fold_excerpt_source(self, text, normalize, category):
        if type(text) is not str:
            raise TypeError("text must be an exact str")
        if not self.unicode_verified or normalize is not self.normalize or category is not self.category:
            if self.native is None:
                raise TypeError("Research bridge requires matching original Unicode primitives")
            return self.native.fold_excerpt_source(text, normalize, category)
        folded, positions = self.invoke("fold_table", text)
        return folded, positions

    def literal_positions(self, lower, terms, source_positions):
        if type(lower) is not str:
            raise TypeError("text must be an exact str")
        if type(terms) is not list:
            raise TypeError("terms must be an exact list")
        if source_positions is not None and type(source_positions) is not list:
            raise TypeError("source_positions must be None or an exact list")
        if any(type(term) is not str for term in terms):
            raise TypeError("text must be an exact str")
        found = self.invoke("literal_positions", lower, terms)
        return [(position if source_positions is None else source_positions[position], terms[term_id])
                for position, term_id in found]

    def evidence_units(self, text, width):
        if type(text) is not str:
            raise TypeError("text must be an exact str")
        if type(width) is not int or not -MAX_SAFE_INTEGER <= width <= MAX_SAFE_INTEGER:
            if self.native is None:
                raise TypeError("Research bridge requires a safe integer width")
            return self.native.evidence_units(text, width)
        return [tuple(pair) for pair in self.invoke("evidence_units", text, width)]

    def context_allocations(self, pages, budget):
        if type(pages) is not list or type(budget) is not int or budget < 0:
            return NotImplemented
        fields = ("id", "project_id", "session_id", "created_at", "content")
        if any(type(row) is not dict or any(type(key) is not str for key in row)
               or any(type(row.get(field)) is not str for field in fields) for row in pages):
            return NotImplemented
        if budget > MAX_SAFE_INTEGER:
            if self.native is None:
                return NotImplemented
            return self.native.context_allocations(pages, budget)
        prepared = [{field: row[field] for field in fields} for row in pages]
        result = self.invoke("context_allocations", prepared, budget)
        return [(pages[index], header, allowance) for index, header, allowance in result]

    def excerpt_window(self, text, q, positions, width, evidence_units, log1p, fsum):
        ordinary = (self.math_verified and type(text) is str and type(q) is list
            and len(q) <= 64 and all(type(term) is str for term in q) and len(set(q)) == len(q)
            and type(width) is int and 0 < width < len(text) and type(positions) is list
            and len(positions) <= 2560 and len(text) * len(positions) <= MAX_SAFE_INTEGER
            and evidence_units is self.reference_evidence_units and log1p is self.log1p and fsum is self.fsum)
        counts = {}
        if ordinary:
            for hit in positions:
                if (type(hit) is not tuple or len(hit) != 2 or type(hit[0]) is not int
                    or not 0 <= hit[0] <= len(text) or type(hit[1]) is not str or hit[1] not in q):
                    ordinary = False
                    break
                counts[hit[1]] = counts.get(hit[1], 0) + 1
                if counts[hit[1]] > 40:
                    ordinary = False
                    break
        if not ordinary:
            return (self.native.excerpt_window(text, q, positions, width, evidence_units, log1p, fsum)
                    if self.native is not None else NotImplemented)
        # Native/reference window selection sorts the supplied positions list.
        positions.sort()
        indexes = {term: index for index, term in enumerate(q)}
        hits = [(position, indexes[term]) for position, term in positions]
        value, spans = self.invoke("excerpt_window", text, q, hits, width)
        return value, [tuple(span) for span in spans]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
