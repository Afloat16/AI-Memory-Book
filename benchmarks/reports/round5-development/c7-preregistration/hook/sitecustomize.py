"""Only enable the explicitly registered C7 diagnostic in its SDK child."""
import os

if os.environ.get("ROUND5_C7_PROFILE_DIRECTORY"):
    try:
        from diagnostic import install_observer
        install_observer()
    except BaseException:
        import sys
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(97)
