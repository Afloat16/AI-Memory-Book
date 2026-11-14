"""Diagnostic-only child startup hook; absent from all product installations."""
import os

if os.environ.get("ROUND5_C6_SQL_TRACE"):
    from diagnostic import install_observer
    install_observer()
