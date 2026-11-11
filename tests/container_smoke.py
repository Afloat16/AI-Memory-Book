"""Verify a built image's stdio MCP, local reader, and persistent volume.

Run after ``docker build -t ai-memory-book:ci .``. Requires Docker and the
official MCP Python SDK in the test runner. All containers and the named volume
are uniquely named and removed by this script; no existing volume is used.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
import json
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid


def docker(*arguments: str, input: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *arguments], input=input, text=True, capture_output=True, check=check, timeout=120)


async def check_mcp(image: str, volume: str, container_name: str) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    parameters = StdioServerParameters(
        command="docker",
        args=["run", "--rm", "--interactive", "--name", container_name, "--volume", f"{volume}:/data", image, "mcp"],
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=25)) as client:
            initialized = await client.initialize()
            assert initialized.serverInfo.name == "AI-Memory-Book"
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert "recall_memory" in names and "remember_session" not in names
            result = await client.call_tool("recall_memory", {
                "query": "callback retry interval", "project": "container-example", "budget_chars": 2000,
            })
            assert not result.isError, result
            body = json.loads("\n".join(part.text for part in result.content if part.type == "text"))
            assert "45 seconds" in body["context"]
            assert len(body["context"]) <= 2000
    print("PASS: container MCP initializes over stdio and recalls persisted evidence", flush=True)


def request_json(path: str) -> object:
    with urlopen("http://127.0.0.1:8765" + path, timeout=3) as response:
        return json.load(response)


def wait_for_reader() -> None:
    deadline = time.monotonic() + 30
    last_error = None
    while time.monotonic() < deadline:
        try:
            request_json("/api/stats")
            return
        except (OSError, URLError) as exc:
            last_error = exc
            time.sleep(0.2)
    raise AssertionError(f"The container reader did not become ready: {last_error}")


def run(image: str) -> None:
    identifier = uuid.uuid4().hex[:12]
    volume = "memory-book-ci-" + identifier
    mcp_name, reader_name = "memory-book-mcp-" + identifier, "memory-book-reader-" + identifier
    fixture = {
        "project": "container-example",
        "session_id": "container-session",
        "messages": [
            {"role": "user", "content": "Which callback retry interval was selected?"},
            {"role": "assistant", "content": "The callback retry interval is 45 seconds."},
        ],
    }
    try:
        user = docker("image", "inspect", "--format", "{{.Config.User}}", image).stdout.strip()
        assert user == "10001:10001", f"The image must run as its non-root user, got {user!r}"
        docker("volume", "create", volume)
        seed = "import json, os, sys\nfrom memory_book import MemoryBook\nwith MemoryBook(os.environ['MEMORY_BOOK_DB']) as book:\n    print(json.dumps(book.ingest(json.load(sys.stdin))))\n"
        docker("run", "--rm", "--interactive", "--volume", f"{volume}:/data", "--entrypoint", "python", image, "-c", seed, input=json.dumps(fixture))
        print("PASS: non-root image writes its new named data volume", flush=True)
        asyncio.run(check_mcp(image, volume, mcp_name))

        docker(
            "run", "--detach", "--name", reader_name,
            "--publish", "127.0.0.1:8765:8765",
            "--volume", f"{volume}:/data", "--read-only", "--tmpfs", "/tmp",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            image, "serve", "--host", "0.0.0.0", "--port", "8765", "--container-bind",
        )
        wait_for_reader()
        with urlopen("http://127.0.0.1:8765/", timeout=3) as response:
            assert "AI MEMORY BOOK" in response.read().decode("utf-8")
        assert any(project["id"] == "container-example" for project in request_json("/api/projects"))
        recalled = request_json("/api/recall?q=callback&project=container-example")
        assert "45 seconds" in recalled["context"]
        try:
            urlopen(Request("http://127.0.0.1:8765/api/projects", headers={"Host": "attacker.example:8765"}), timeout=3)
        except HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("Container binding bypassed the reader's Host protection")
        print("PASS: localhost-published reader shares MCP data and retains Host validation", flush=True)

        docker("restart", reader_name)
        wait_for_reader()
        assert any(project["id"] == "container-example" for project in request_json("/api/projects"))
        print("PASS: container restart preserves the named volume", flush=True)
    except BaseException:
        logs = docker("logs", reader_name, check=False)
        if logs.stdout or logs.stderr:
            print(logs.stdout + logs.stderr)
        raise
    finally:
        docker("rm", "--force", reader_name, mcp_name, check=False)
        docker("volume", "rm", volume, check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="ai-memory-book:ci")
    options = parser.parse_args()
    run(options.image)
