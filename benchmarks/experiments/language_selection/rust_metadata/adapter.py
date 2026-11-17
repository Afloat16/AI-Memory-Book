"""Shared C/Rust metadata experiment adapter; never edits the product sources.

SQL callbacks can change dependencies or candidate containers. The native entry
therefore owns two exact Python continuations which resume after the already
executed query, preserving its side effects instead of rerunning the method.
"""
from __future__ import annotations

import ast
import builtins
import copy
import functools
import hashlib
import math
from pathlib import Path
import sqlite3
import types


STORE_SHA256 = "355687bb28eff83160b42120d7a22be1273c6405fa77e8549266f92dfe0e8b87"
_TYPE = (0).__class__.__class__
_GETATTR = getattr
_OBJECT = ().__class__.__base__
_FUNCTION = (lambda: None).__class__
_BUILTIN = [].append.__class__
_LRU = functools._lru_cache_wrapper
_BUILTIN_NAMES = ("len", "type", "str", "int", "any", "sorted", "set", "list", "dict", "getattr")
_CANONICAL_TYPES = {"type": _TYPE, "dict": {}.__class__, "list": [].__class__,
                    "set": {None}.__class__, "str": "".__class__, "int": (0).__class__}


def _code(module_code, name):
    return next(value for value in module_code.co_consts
                if isinstance(value, types.CodeType) and value.co_name == name)


def _continuation(node, start, name, arguments, globals_dict, filename):
    function = ast.FunctionDef(
        name=name,
        args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=value) for value in arguments],
                           vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]),
        body=copy.deepcopy(node.body[start:]), decorator_list=[], returns=None,
        type_comment=None)
    tree = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    compiled = compile(tree, filename, "exec", dont_inherit=True)
    return _FUNCTION(_code(compiled, name), globals_dict, name)


def install(store_module, native_module) -> bool:
    """Install one process-local experimental method, or leave it untouched."""
    # Reject preinstallation overrides before pathlib/AST/builtin calls can
    # accidentally execute them while preparing the experimental registration.
    builtin_objects = {name: builtins.__dict__[name] for name in _BUILTIN_NAMES}
    for name, canonical in _CANONICAL_TYPES.items():
        if builtin_objects[name] is not canonical:
            return False
    for name in ("len", "any", "sorted", "getattr"):
        value = builtin_objects[name]
        if (_TYPE(value) is not _BUILTIN or value.__self__ is not builtins
                or value.__name__ != name):
            return False
    if _TYPE(store_module) is not types.ModuleType:
        return False
    store_globals = store_module.__dict__
    math_globals = math.__dict__
    sqlite_globals = sqlite3.__dict__
    builtin_globals = builtins.__dict__
    ordinary_book = store_globals.get("MemoryBook")
    if _TYPE(ordinary_book) is not _TYPE:
        return False
    book_namespace = ordinary_book.__dict__
    original = book_namespace.get("_bounded_candidate_metadata")
    if _TYPE(original) is not _FUNCTION:
        return False
    filename = original.__code__.co_filename
    raw = Path(filename).read_bytes()
    if hashlib.sha256(raw).hexdigest() != STORE_SHA256:
        return False
    compiled = compile(raw, filename, "exec", dont_inherit=True)
    expected = _code(_code(compiled, "MemoryBook"), "_bounded_candidate_metadata")
    if original.__code__ != expected or original.__globals__ is not store_module.__dict__:
        return False
    original_code = original.__code__
    ordinary_candidates = store_globals.get("_RecallCandidates")
    if _TYPE(ordinary_candidates) is not _TYPE:
        return False
    candidates_namespace = ordinary_candidates.__dict__
    directory_function = store_globals.get("_ORDINARY_DIRECTORY_TOKENS")
    ordinary_isfinite = math_globals.get("isfinite")
    if (_TYPE(ordinary_isfinite) is not _BUILTIN or ordinary_isfinite.__self__ is not math
            or ordinary_isfinite.__name__ != "isfinite"):
        return False
    if store_globals.get("math") is not math or store_globals.get("sqlite3") is not sqlite3:
        return False
    ordinary_row = sqlite3.Row
    ordinary_connection = sqlite3.Connection
    candidates_methods = {
        name: _GETATTR(dict, name) for name in
        ("values", "items", "__iter__", "__len__", "__getitem__", "__setitem__", "__getattribute__")
    }
    metadata_descriptor = candidates_namespace.get("metadata")
    if (_TYPE(ordinary_candidates) is not _TYPE or ordinary_candidates.__bases__ != ({}.__class__,)
            or _TYPE(metadata_descriptor) is not types.MemberDescriptorType
            or metadata_descriptor.__objclass__ is not ordinary_candidates
            or metadata_descriptor.__name__ != "metadata"):
        return False
    book_dict_descriptor = book_namespace.get("__dict__")
    if (_TYPE(book_dict_descriptor) is not types.GetSetDescriptorType
            or book_dict_descriptor.__objclass__ is not ordinary_book):
        return False
    tree = ast.parse(raw, filename)
    class_node = next(value for value in tree.body if isinstance(value, ast.ClassDef) and value.name == "MemoryBook")
    node = next(value for value in class_node.body if isinstance(value, ast.FunctionDef)
                and value.name == "_bounded_candidate_metadata")
    # The exact source digest above pins these AST cut points to the statements
    # following light.fetch and directories.fetch, including all original guards.
    assert len(node.body) == 14 and node.body[6].lineno == 1398 and node.body[9].lineno == 1411
    after_light = _continuation(node, 6, "metadata_after_light",
        ("self", "rows", "retained", "light"), store_module.__dict__, filename)
    after_directories = _continuation(node, 9, "metadata_after_directories",
        ("rows", "retained", "light", "pairs", "directories"), store_module.__dict__, filename)
    wrapper_holder = [None]

    def ordinary_ready():
        if (original.__code__ is not original_code
                or store_globals.get("MemoryBook") is not ordinary_book
                or store_globals.get("_RecallCandidates") is not ordinary_candidates
                or store_globals.get("_ORDINARY_DIRECTORY_TOKENS") is not directory_function
                or store_globals.get("math") is not math or store_globals.get("sqlite3") is not sqlite3
                or math_globals.get("isfinite") is not ordinary_isfinite
                or sqlite_globals.get("Row") is not ordinary_row
                or sqlite_globals.get("Connection") is not ordinary_connection
                or ordinary_book.__bases__ != (_OBJECT,)
                or ordinary_candidates.__bases__ != (_CANONICAL_TYPES["dict"],)
                or book_namespace.get("__getattribute__", _OBJECT.__getattribute__) is not _OBJECT.__getattribute__
                or "__getattr__" in book_namespace
                or "db" in book_namespace
                or "_directory_tokens" in book_namespace
                or "_ordinary_directory_cache" in book_namespace
                or book_namespace.get("__dict__") is not book_dict_descriptor
                or "__getattr__" in candidates_namespace
                or candidates_namespace.get("metadata") is not metadata_descriptor):
            return False
        for name, expected_value in builtin_objects.items():
            if (builtin_globals.get(name) is not expected_value
                    or store_globals.get(name, expected_value) is not expected_value):
                return False
        for name, expected_value in candidates_methods.items():
            if candidates_namespace.get(name, expected_value) is not expected_value:
                return False
        current = book_namespace.get("_bounded_candidate_metadata")
        return current is original or current is wrapper_holder[0]

    env = {"store": store_module, "ordinary_ready": ordinary_ready,
           "after_light": after_light, "after_directories": after_directories,
           "lru_type": _LRU}

    def bounded_metadata_wrapper(self, rows, relevance, count):
        result = NotImplemented
        if _TYPE(self) is ordinary_book and ordinary_ready():
            state = self.__dict__
            if (_TYPE(state.get("db")) is ordinary_connection
                    and _TYPE(state.get("_directory_tokens")) is _LRU
                    and _TYPE(state.get("_ordinary_directory_cache")) is _LRU):
                result = native_module.bounded_metadata(self, rows, relevance, count, env)
        if result is NotImplemented:
            return original(self, rows, relevance, count)
        return result

    wrapper_holder[0] = bounded_metadata_wrapper
    if not ordinary_ready():
        return False
    bounded_metadata_wrapper._language_metadata_env = env
    bounded_metadata_wrapper._language_original = original
    bounded_metadata_wrapper._language_backend = native_module.__name__
    ordinary_book._bounded_candidate_metadata = bounded_metadata_wrapper
    return True
