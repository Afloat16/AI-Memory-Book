"""Owned-process provenance tests; these fixtures are not model evaluations."""
import json
from pathlib import Path
import socket
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import local_answer_server as server


class LocalAnswerServerTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        cache = root / "cache"
        binary_root = cache / "fixture-build" / "fixture-runtime"
        binary_root.mkdir(parents=True)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        executable = binary_root / "llama-server"
        code = f"#!{sys.executable}\n" + '''
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        raw = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def log_message(self, *args): pass
HTTPServer(('127.0.0.1', int(sys.argv[sys.argv.index('--port') + 1])), Handler).serve_forever()
'''
        executable.write_text(code)
        executable.chmod(0o755)
        library = binary_root / "libfixture.so"
        library.write_bytes(b"fake fixture library")
        archive = cache / "server.tar.gz"
        with tarfile.open(archive, "w:gz") as package:
            for path in (executable, library):
                package.add(path, arcname="fixture-runtime/" + path.name)
        model = cache / "weights.gguf"
        model.write_bytes(b"not a model: provenance fixture only")
        pin = lambda path: {"file": path.name, "bytes": path.stat().st_size, "sha256": server.file_hash(path)}
        plan = root / "plan.json"
        plan.write_text(json.dumps({"model": pin(model), "server": {
            **pin(archive), "asset": archive.name, "tag": "fixture-build"}}))
        execution = root / "execution.json"
        execution.write_text(json.dumps({"server_argv": ["llama-server", "--model", "weights.gguf",
              "--host", "127.0.0.1", "--port", str(port), "--ctx-size", "4096", "--no-cache-prompt"]}))
        for name, value in (("PLAN", plan), ("EXECUTION", execution)):
            patched = patch.object(server, name, value)
            patched.start()
            self.addCleanup(patched.stop)
        prepared = root / "prepared.json"
        prepared.write_text('{"fixture":"no questions or generated answers"}')
        return cache, prepared, root / "run", library

    def test_changed_extracted_library_is_rejected_even_with_the_pinned_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            cache, _, _, library = self.fixture(directory)
            self.assertIn("fixture-runtime/libfixture.so", server.verified_runtime(cache)["runtime_files"])
            library.write_bytes(b"changed library")
            with self.assertRaisesRegex(ValueError, "Extracted local answer runtime"):
                server.verified_runtime(cache)

    def test_external_endpoint_or_edited_argv_cannot_be_exported_as_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            cache, prepared, prefix, _ = self.fixture(directory)
            proof = Path(str(prefix) + ".server.json")
            with self.assertRaises(FileNotFoundError):
                server.validate_proof(proof, prepared, prefix, cache)
            identity = {"runtime": server.verified_runtime(cache), "prepared_sha256": server.file_hash(prepared)}
            identity["runtime"]["argv"].append("--unregistered-option")
            proof.write_text(json.dumps({"identity": identity, "identity_sha256": server.digest(identity), "runs": []}))
            with self.assertRaisesRegex(ValueError, "Owned local server proof differs"):
                server.validate_proof(proof, prepared, prefix, cache)

    def test_owned_process_proof_binds_final_ledger_and_rejects_edited_results(self):
        with tempfile.TemporaryDirectory() as directory:
            cache, prepared, prefix, _ = self.fixture(directory)
            with server.owned_server(cache, prepared, prefix) as endpoint:
                self.assertTrue(endpoint.startswith("http://127.0.0.1:"))
                # Protocol-only bytes, never counted or described as model output.
                Path(str(prefix) + ".jsonl").write_text('{"fixture":true}\n')
                Path(str(prefix) + ".summary.json").write_text('{"fixture":true}\n')
            proof_path = Path(str(prefix) + ".server.json")
            proof = server.validate_proof(proof_path, prepared, prefix, cache)
            self.assertEqual(proof["runs"][-1]["status"], "completed")
            self.assertIsNotNone(proof["runs"][-1]["exit_code"])
            self.assertGreaterEqual(proof["runs"][-1]["ready_ms"], 0)
            Path(str(prefix) + ".jsonl").write_text('{"changed":true}\n')
            with self.assertRaisesRegex(ValueError, "not bound to these actual answer results"):
                server.validate_proof(proof_path, prepared, prefix, cache)


if __name__ == "__main__":
    unittest.main()
