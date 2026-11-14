"""Exact SDK output scheduling, fallbacks and shutdown without timing claims."""
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import mcp_server

HAS_MCP = importlib.util.find_spec("mcp") is not None
HAS_ANYIO = importlib.util.find_spec("anyio") is not None
SOURCE = str(Path(mcp_server.__file__).resolve().parents[1])


class Stream:
    def __init__(self):
        self.operations = []
        self.write_error = self.flush_error = None

    def write(self, text):
        self.operations.append(("write", text))
        if self.write_error is not None:
            raise self.write_error
        return len(text)

    def flush(self):
        self.operations.append(("flush",))
        if self.flush_error is not None:
            raise self.flush_error


class OutputSchedulingTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self, stream):
        dispatches, checkpoints = [], []

        async def run_sync(function, *args):
            dispatches.append(function.__name__)
            return function(*args)

        async def checkpoint():
            checkpoints.append(True)
            await asyncio.sleep(0)

        return mcp_server._FlushedStdout(stream, run_sync, checkpoint), dispatches, checkpoints

    async def test_one_dispatch_per_message_and_independent_repeated_flush(self):
        stream = Stream()
        writer, dispatches, checkpoints = self.adapter(stream)
        await writer.flush()
        self.assertEqual(await writer.write("first\n"), 6)
        await writer.flush()
        self.assertEqual(stream.operations, [("flush",), ("write", "first\n"), ("flush",)])
        self.assertEqual(len(dispatches), 2)
        await writer.flush()
        self.assertEqual(stream.operations[-1], ("flush",))
        self.assertEqual(len(dispatches), 3)
        self.assertEqual(await writer.write("second\n"), 7)
        await writer.flush()
        self.assertEqual(len(dispatches), 4)
        self.assertEqual(len(checkpoints), 2)
        self.assertEqual(stream.operations[-2:], [("write", "second\n"), ("flush",)])

    async def test_write_error_propagates_without_flushing_or_marking_success(self):
        stream = Stream()
        stream.write_error = BrokenPipeError("write failed")
        writer, dispatches, checkpoints = self.adapter(stream)
        with self.assertRaises(BrokenPipeError) as raised:
            await writer.write("evidence\n")
        self.assertIs(raised.exception, stream.write_error)
        self.assertEqual(stream.operations, [("write", "evidence\n")])
        await writer.flush()
        self.assertEqual(stream.operations[-1], ("flush",))
        self.assertEqual(len(dispatches), 2)
        self.assertFalse(checkpoints)

    async def test_flush_error_propagates_and_next_flush_is_not_skipped(self):
        stream = Stream()
        stream.flush_error = OSError("flush failed")
        writer, dispatches, checkpoints = self.adapter(stream)
        with self.assertRaises(OSError) as raised:
            await writer.write("evidence\n")
        self.assertIs(raised.exception, stream.flush_error)
        with self.assertRaises(OSError) as repeated:
            await writer.flush()
        self.assertIs(repeated.exception, stream.flush_error)
        self.assertEqual(stream.operations, [("write", "evidence\n"), ("flush",), ("flush",)])
        self.assertEqual(len(dispatches), 2)
        self.assertFalse(checkpoints)

    async def test_unicode_control_characters_large_lines_and_exact_return_values(self):
        output = io.BytesIO()
        stream = io.TextIOWrapper(output, encoding="utf-8")
        writer, dispatches, _ = self.adapter(stream)
        messages = [json.dumps({"text": value}, ensure_ascii=False, separators=(",", ":")) + "\n"
                    for value in ("Café 压力 🌈\r\n\t\0 \\\"", "证据🌈" * 20000, "")]
        for message in messages:
            self.assertEqual(await writer.write(message), len(message))
            await writer.flush()
        self.assertEqual(output.getvalue(), "".join(messages).encode("utf-8"))
        self.assertGreater(len(output.getvalue()), 65536)
        self.assertEqual(len(dispatches), len(messages))
        stream.detach()

    async def test_utf8_encoding_failure_keeps_original_error(self):
        output = io.BytesIO()
        stream = io.TextIOWrapper(output, encoding="utf-8")
        writer, dispatches, _ = self.adapter(stream)
        with self.assertRaises(UnicodeEncodeError) as expected:
            stream.write("bad\ud800")
        with self.assertRaises(UnicodeEncodeError) as actual:
            await writer.write("bad\ud800")
        self.assertEqual(actual.exception.args, expected.exception.args)
        await writer.flush()
        self.assertEqual(len(dispatches), 2)
        self.assertEqual(output.getvalue(), b"")
        stream.detach()

    def test_unknown_server_keeps_original_run_and_arguments(self):
        class CustomServer:
            def __init__(self):
                self.calls = []

            def run(self, **kwargs):
                self.calls.append(kwargs)

        server = CustomServer()
        with patch.object(mcp_server, "create_server", return_value=server) as factory:
            mcp_server.serve("sample.db", allow_write=True,
                             semantic_model_dir="models", source_format="indexed")
        factory.assert_called_once_with("sample.db", allow_write=True,
                                        semantic_model_dir="models", source_format="indexed")
        self.assertEqual(server.calls, [{"transport": "stdio"}])


@unittest.skipUnless(HAS_ANYIO, "requires optional AnyIO dependency")
class CancellationTests(unittest.TestCase):
    def test_cancel_before_dispatch_leaves_output_untouched(self):
        import anyio

        async def scenario():
            stream = Stream()
            writer = mcp_server._FlushedStdout(stream, anyio.to_thread.run_sync,
                                              anyio.lowlevel.checkpoint)
            with anyio.CancelScope() as scope:
                scope.cancel()
                await writer.write("not dispatched\n")
                self.fail("Cancelled write was dispatched")
            self.assertTrue(scope.cancelled_caught)
            self.assertEqual(stream.operations, [])

        anyio.run(scenario)

    def test_cancel_does_not_abandon_write_flush_worker(self):
        import anyio

        async def scenario():
            started, release = threading.Event(), threading.Event()
            done = anyio.Event()
            operations = []

            class BlockingStream:
                def write(self, text):
                    operations.append(("write", text))
                    return len(text)

                def flush(self):
                    operations.append(("flush_started",))
                    started.set()
                    if not release.wait(3):
                        raise RuntimeError("test failed to release the flush worker")
                    operations.append(("flush_finished",))

            writer = mcp_server._FlushedStdout(BlockingStream(), anyio.to_thread.run_sync,
                                              anyio.lowlevel.checkpoint)
            scope = anyio.CancelScope()

            async def write_message():
                with scope:
                    await writer.write("complete\n")
                    await writer.flush()
                done.set()

            async with anyio.create_task_group() as group:
                group.start_soon(write_message)
                try:
                    self.assertTrue(await anyio.to_thread.run_sync(started.wait, 3))
                    scope.cancel()
                    await anyio.sleep(0)
                    self.assertFalse(done.is_set())
                finally:
                    release.set()
            self.assertTrue(scope.cancelled_caught)
            self.assertEqual(operations, [("write", "complete\n"), ("flush_started",), ("flush_finished",)])

        anyio.run(scenario)

    def test_paired_flush_still_checks_cancellation_and_consumes_marker(self):
        import anyio

        async def scenario():
            stream = Stream()
            writer = mcp_server._FlushedStdout(stream, anyio.to_thread.run_sync,
                                              anyio.lowlevel.checkpoint)
            await writer.write("complete\n")
            with anyio.CancelScope() as scope:
                scope.cancel()
                await writer.flush()
                self.fail("Paired flush lost its cancellation checkpoint")
            self.assertTrue(scope.cancelled_caught)
            await writer.flush()
            self.assertEqual(stream.operations, [("write", "complete\n"), ("flush",), ("flush",)])

        anyio.run(scenario)


@unittest.skipUnless(HAS_MCP, "requires optional MCP SDK")
class StandardSdkTests(unittest.TestCase):
    def test_guards_use_real_native_child_stdout_and_reject_custom_paths(self):
        script = r'''
import io, json, sys
from functools import wraps
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import anyio
from anyio._core import _fileio
import mcp.server.fastmcp.server as sdk
import mcp.server.stdio as stdio
from memory_book import mcp_server as product
server = product.create_server(":memory:")
assert product._standard_stdio_config(server) is not None
with patch("importlib.metadata.version", return_value="1.31.0"):
    assert product._standard_stdio_config(server) is None
ordinary = sdk.FastMCP.run_stdio_async
@wraps(ordinary)
async def changed(self):
    return await ordinary(self)
with patch.object(sdk.FastMCP, "run_stdio_async", changed):
    assert product._standard_stdio_config(server) is None
other = product.create_server(":memory:")
with patch.object(server, "run_stdio_async", other.run_stdio_async):
    assert product._standard_stdio_config(server) is None
with patch.object(server._mcp_server, "run", other._mcp_server.run):
    assert product._standard_stdio_config(server) is None
with patch.object(sdk, "stdio_server", lambda: None):
    assert product._standard_stdio_config(server) is None
with patch.object(stdio, "TextIOWrapper", lambda *args, **kwargs: None):
    assert product._standard_stdio_config(server) is None
proxy = SimpleNamespace(stdin=sys.stdin, stdout=io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))
with patch.object(stdio, "sys", proxy):
    assert product._standard_stdio_config(server) is None
with patch.object(anyio, "wrap_file", lambda *args, **kwargs: None):
    assert product._standard_stdio_config(server) is None
with patch.object(_fileio, "to_thread", SimpleNamespace(run_sync=changed)):
    assert product._standard_stdio_config(server) is None
for name in ("__init__", "write", "flush"):
    with patch.object(anyio.AsyncFile, name, changed):
        assert product._standard_stdio_config(server) is None
with patch.object(anyio.to_thread, "run_sync", changed):
    assert product._standard_stdio_config(server) is None
with patch.object(sys, "stdout", io.StringIO()):
    assert product._standard_stdio_config(server) is None
with patch.object(sys, "stdin", io.StringIO()):
    assert product._standard_stdio_config(server) is None
closed_input = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
closed_input.close()
with patch.object(sys, "stdin", closed_input), patch.object(sys, "__stdin__", closed_input):
    assert product._standard_stdio_config(server) is None
alternate = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
with patch.object(sys, "stdout", alternate), patch.object(sys, "__stdout__", alternate):
    assert product._standard_stdio_config(server) is None
assert product._standard_stdio_config(server) is not None
print(json.dumps({"standard_guard": True, "custom_fallbacks": True}))
'''
        for flags in ([], ["-u"]):
            with self.subTest(flags=flags):
                result = subprocess.run([sys.executable, *flags, "-c", script, SOURCE],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout),
                                 {"standard_guard": True, "custom_fallbacks": True})

    def test_real_sdk_transcript_large_unicode_cache_writes_and_eof(self):
        async def scenario(root, original):
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            child = r'''
import io, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import anyio
from memory_book import mcp_server as product
state = {"selected": [], "closes": 0, "dispatches": {"combined": 0, "write": 0, "flush": 0}}
original_config = product._standard_stdio_config
original_run_sync = anyio.to_thread.run_sync
async def observe_dispatch(function, *args, **kwargs):
    owner = getattr(function, "__self__", None)
    if isinstance(owner, product._FlushedStdout):
        state["dispatches"]["combined"] += 1
    elif (type(owner) is io.TextIOWrapper and owner.buffer is sys.stdout.buffer
          and function.__name__ in ("write", "flush")):
        state["dispatches"][function.__name__] += 1
    return await original_run_sync(function, *args, **kwargs)
def config(server):
    value = original_config(server)
    assert value is not None, "default child stdout must qualify"
    state["selected"].append(sys.argv[4] != "fallback")
    # Observe only after the genuine SDK/default-stream guards have passed.
    anyio.to_thread.run_sync = observe_dispatch
    return None if sys.argv[4] == "fallback" else value
product._standard_stdio_config = config
original_close = product.MemoryBook.close
def close(book):
    state["closes"] += 1
    return original_close(book)
product.MemoryBook.close = close
product.serve(sys.argv[2])
state["stdout_closed"] = sys.stdout.closed
state["buffer_closed"] = sys.stdout.buffer.closed
Path(sys.argv[3]).write_text(json.dumps(state))
'''
            transcripts, states = [], []
            for mode in ("standard", "fallback"):
                database, state = root / (mode + ".db"), root / (mode + ".json")
                shutil.copyfile(original, database)
                parameters = StdioServerParameters(command=sys.executable,
                    args=["-c", child, SOURCE, str(database), str(state), mode])
                results = []
                with (root / (mode + ".stderr")).open("w") as errors:
                    async with stdio_client(parameters, errlog=errors) as (reader, writer):
                        async with ClientSession(reader, writer) as client:
                            init = await client.initialize()
                            results.append(init.model_dump_json(exclude_none=True))
                            results.append((await client.list_tools()).model_dump_json(exclude_none=True))
                            arguments = {"query": "calibration pressure", "project": "lab",
                                         "budget_chars": 100000, "limit": 5}
                            for _ in range(2):
                                response = await client.call_tool("recall_memory", arguments)
                                self.assertFalse(response.isError)
                                results.append(response.model_dump_json(exclude_none=True))
                                with MemoryBook(database) as check:
                                    cached = check.db.execute("SELECT payload FROM recall_cache").fetchall()
                                    self.assertEqual(len(cached), 1)
                                    self.assertEqual(json.loads(cached[0][0])["cache_hit"], False)
                            page = json.loads(response.content[0].text)["results"][0]["id"]
                            response = await client.call_tool("read_page", {"page_id": page, "limit": 100000})
                            self.assertFalse(response.isError)
                            wire = response.model_dump_json(exclude_none=True)
                            self.assertGreater(len(wire.encode()), 65536)
                            results.append(wire)
                self.assertTrue(state.exists(), (root / (mode + ".stderr")).read_text())
                states.append(json.loads(state.read_text()))
                transcripts.append(results)
            self.assertEqual(transcripts[0], transcripts[1])
            self.assertEqual(states[0]["selected"], [True])
            self.assertEqual(states[1]["selected"], [False])
            self.assertEqual(states[0]["closes"], 1)
            self.assertEqual(states[1]["closes"], 1)
            self.assertEqual(states[0]["dispatches"], {"combined": 5, "write": 0, "flush": 0})
            self.assertEqual(states[1]["dispatches"], {"combined": 0, "write": 5, "flush": 5})
            for field in ("stdout_closed", "buffer_closed"):
                self.assertEqual(states[0][field], states[1][field])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.db"
            with MemoryBook(original, segmentation="session", max_page_chars=100000) as book:
                book.ingest({"project": "lab", "session_id": "unicode",
                    "title": "pressure", "created_at": "2026-01-01T00:00:00Z",
                    "messages": [{"role": "user", "content": "calibration pressure Café 🌈\n" + "证据 🌈\\\"\t" * 6000}]})
                book.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            asyncio.run(scenario(root, original))


if __name__ == "__main__":
    unittest.main()
