"""Build optional CPython text loops; retain a compiler-free Python package."""

import os
import sys
import sysconfig

from setuptools import Extension, setup


mode = os.environ.get("MEMORY_BOOK_BUILD_NATIVE", "auto")
if mode not in {"auto", "0", "1"}:
    raise ValueError("MEMORY_BOOK_BUILD_NATIVE must be auto, 0 or 1")
supported = sys.implementation.name == "cpython" and not sysconfig.get_config_var("Py_GIL_DISABLED")
if mode == "1" and not supported:
    raise RuntimeError("The native extension currently requires a CPython build with the GIL")
extensions = []
if mode != "0" and supported:
    extensions.append(Extension(
        "memory_book._native",
        sources=["src/memory_book/_native.c"],
        extra_compile_args=["/O2"] if os.name == "nt" else ["-O3"],
        optional=mode == "auto",
    ))

setup(ext_modules=extensions)
