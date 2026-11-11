"""A loopback-only reader for MemoryBook, built with the Python standard library.

The reader is deliberately a local desktop companion, not a multi-user service.
Every request uses its own SQLite connection. A strict Host allowlist prevents
DNS rebinding; mutations also require a same-origin Origin and a startup token.
"""

from __future__ import annotations

import ipaddress
import json
import secrets
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .store import MemoryBook

MAX_IMPORT_BYTES = 8 * 1024 * 1024


class _LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(15)
        return request, address


def make_server(db_path, host: str = "127.0.0.1", port: int = 8765, *, container_bind: bool = False) -> ThreadingHTTPServer:
    """Create an unstarted local server. ``port=0`` is useful in integration tests.

    The explicit container option permits 0.0.0.0 inside a container whose host
    port is published to loopback only. Host/Origin checks remain local-only.
    """
    if host == "0.0.0.0" and container_bind:
        pass
    elif host != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError("The reader can only bind to a loopback address.")
        except ValueError as exc:
            raise ValueError("The reader can only bind to a loopback address.") from exc
    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535.")

    db_path = str(db_path)
    csrf_token = secrets.token_urlsafe(32)
    template = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        server_version = "MemoryBook"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):
            # Search text and session identifiers should not end up in access logs.
            return

        def _valid_host(self) -> bool:
            values = self.headers.get_all("Host", [])
            return len(values) == 1 and values[0].lower() in self.server.allowed_hosts

        def _send(self, status, payload, content_type="application/json; charset=utf-8", *, nonce=None):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            if nonce:
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; connect-src 'self'; img-src 'self' data:; "
                    f"style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
                    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
                )
            else:
                self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _error(self, status, message):
            self._send(status, {"error": message})

        def _checked(self):
            if not self._valid_host():
                self.close_connection = True
                self._error(HTTPStatus.FORBIDDEN, "Unrecognized local Host header.")
                return False
            return True

        def _query(self):
            if len(self.path) > 24000:
                raise ValueError("The request URL is too long.")
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc:
                raise ValueError("Only relative request targets are accepted.")
            return parsed.path, parse_qs(parsed.query, keep_blank_values=True, max_num_fields=20)

        @staticmethod
        def _param(params, name, default=None):
            values = params.get(name)
            if values is None:
                return default
            if len(values) != 1:
                raise ValueError(f"Repeated parameter: {name}")
            return values[0]

        def _integer(self, params, name, default, minimum, maximum):
            value = int(self._param(params, name, default))
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}.")
            return value

        def _dispatch_get(self):
            path, params = self._query()
            if path == "/":
                nonce = secrets.token_urlsafe(24)
                body = template.replace("__MEMORY_BOOK_CSRF__", csrf_token).replace("__MEMORY_BOOK_NONCE__", nonce)
                self._send(HTTPStatus.OK, body.encode("utf-8"), "text/html; charset=utf-8", nonce=nonce)
                return
            if path == "/favicon.ico":
                self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
                return
            routes = {"/api/projects", "/api/stats", "/api/toc", "/api/chapter", "/api/section", "/api/read", "/api/recall"}
            if path not in routes:
                self._error(HTTPStatus.NOT_FOUND, "Unknown resource.")
                return
            book = MemoryBook(db_path)
            try:
                if path == "/api/projects":
                    result = book.projects()
                elif path == "/api/stats":
                    result = book.stats()
                elif path == "/api/toc":
                    project = self._param(params, "project")
                    if not project:
                        raise ValueError("A project is required.")
                    result = book.toc(project, offset=self._integer(params, "offset", 0, 0, 1000000), limit=self._integer(params, "limit", 50, 1, 100))
                elif path == "/api/chapter":
                    chapter_id = self._param(params, "id")
                    if not chapter_id:
                        raise ValueError("A chapter id is required.")
                    result = book.chapter(
                        chapter_id,
                        offset=self._integer(params, "offset", 0, 0, 1000000),
                        limit=self._integer(params, "limit", 50, 1, 100),
                        page_limit=self._integer(params, "page_limit", 20, 1, 100),
                    )
                elif path == "/api/section":
                    section_id = self._param(params, "id")
                    if not section_id:
                        raise ValueError("A section id is required.")
                    result = book.section(section_id, offset=self._integer(params, "offset", 0, 0, 1000000), limit=self._integer(params, "limit", 50, 1, 100))
                elif path == "/api/read":
                    page_id = self._param(params, "id")
                    if not page_id:
                        raise ValueError("A page id is required.")
                    result = book.read(page_id, offset=self._integer(params, "offset", 0, 0, 100000000), limit=self._integer(params, "limit", 12000, 1, 24000))
                else:
                    query = self._param(params, "q", "")
                    if not query.strip() or len(query) > 4000:
                        raise ValueError("Search text must contain 1 to 4000 characters.")
                    result = book.recall(
                        query,
                        project=self._param(params, "project") or None,
                        chapter=self._param(params, "chapter") or None,
                        session=self._param(params, "session") or None,
                        budget_chars=self._integer(params, "budget_chars", 4000, 256, 24000),
                        limit=self._integer(params, "limit", 5, 1, 20),
                    )
                self._send(HTTPStatus.OK, result)
            finally:
                book.close()

        def do_GET(self):
            if not self._checked():
                return
            try:
                self._dispatch_get()
            except (ValueError, TypeError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except KeyError:
                self._error(HTTPStatus.NOT_FOUND, "The requested book, chapter, or page does not exist.")
            except Exception as exc:
                print(f"MemoryBook reader error: {type(exc).__name__}", file=sys.stderr)
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "The reader could not complete this request.")

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            if not self._checked():
                return
            try:
                path, _ = self._query()
                if path != "/api/import":
                    self.close_connection = True
                    self._error(HTTPStatus.NOT_FOUND, "Unknown resource.")
                    return
                origin = self.headers.get("Origin", "")
                if origin not in {"http://" + value for value in self.server.allowed_hosts}:
                    self.close_connection = True
                    self._error(HTTPStatus.FORBIDDEN, "Import requires a same-origin request.")
                    return
                if not secrets.compare_digest(self.headers.get("X-Memory-Book-Token", ""), csrf_token):
                    self.close_connection = True
                    self._error(HTTPStatus.FORBIDDEN, "Refresh this reader before importing a conversation.")
                    return
                if self.headers.get("Transfer-Encoding"):
                    self.close_connection = True
                    self._error(HTTPStatus.BAD_REQUEST, "Chunked uploads are not supported.")
                    return
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1:
                    self.close_connection = True
                    self._error(HTTPStatus.LENGTH_REQUIRED, "An exact Content-Length is required.")
                    return
                length = int(lengths[0])
                if not 0 < length <= MAX_IMPORT_BYTES:
                    self.close_connection = True
                    self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Import one JSON conversation of at most 8 MiB.")
                    return
                if self.headers.get_content_type() != "application/json":
                    self.close_connection = True
                    self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send application/json.")
                    return
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("The upload was incomplete.")
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Import one conversation object at a time.")
                book = MemoryBook(db_path)
                try:
                    result = book.ingest(payload)
                finally:
                    book.close()
                self._send(HTTPStatus.OK, result)
            except (ValueError, TypeError, UnicodeError) as exc:
                self.close_connection = True
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except KeyError as exc:
                self._error(HTTPStatus.BAD_REQUEST, f"Missing field: {exc}")
            except Exception as exc:
                print(f"MemoryBook reader error: {type(exc).__name__}", file=sys.stderr)
                self.close_connection = True
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "The conversation could not be imported.")

    server_class = _LocalServer
    if ":" in host:
        class IPv6LocalServer(_LocalServer):
            address_family = socket.AF_INET6
        server_class = IPv6LocalServer
    server = server_class((host, port), Handler)
    actual_port = server.server_address[1]
    rendered_host = f"[{host}]" if ":" in host else host
    server.allowed_hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}", f"[::1]:{actual_port}"}
    if host != "0.0.0.0":
        server.allowed_hosts.add(f"{rendered_host}:{actual_port}")
    server.reader_url = f"http://{'127.0.0.1' if host == '0.0.0.0' else rendered_host}:{actual_port}"
    return server


def serve(db_path, host: str = "127.0.0.1", port: int = 8765, *, container_bind: bool = False) -> None:
    """Run the local reader until interrupted."""
    server = make_server(db_path, host=host, port=port, container_bind=container_bind)
    print(f"MemoryBook reader: {server.reader_url}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
