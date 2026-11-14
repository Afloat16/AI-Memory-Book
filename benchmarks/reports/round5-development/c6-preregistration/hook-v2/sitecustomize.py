"""Diagnostic revision 2 hook; only the explicitly registered observer is loaded."""
import os

if os.environ.get("ROUND5_C6_SQL_TRACE"):
    from diagnostic_v2 import install_observer
    install_observer()
