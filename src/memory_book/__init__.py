"""AI-Memory-Book's zero-network, standard-library memory engine."""

__all__ = ["MemoryBook"]
__version__ = "0.3.3"


def __getattr__(name):
    if name == "MemoryBook":
        # Metadata/help commands do not need SQLite or the retrieval engine.
        # Preserve the public class itself, its identity and pickle location.
        from .store import MemoryBook
        globals()[name] = MemoryBook
        return MemoryBook
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
