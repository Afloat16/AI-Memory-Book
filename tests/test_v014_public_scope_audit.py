"""Pure scope-audit integrity; no holdout response or retriever is read/run."""

from copy import deepcopy
import json
import unittest

from benchmarks import v014_public_scope_audit as audit


class PublicScopeAuditIntegrityTests(unittest.TestCase):
    SOURCE = ("class Client:\n"
              "    def __init__(self, http2: bool = False,):\n"
              "        self.http2 = http2\n\n"
              "class AsyncClient:\n"
              "    def __init__(self, http2: bool = False,):\n"
              "        self.http2 = http2\n")
    QUOTE = "http2: bool = False,"

    def case(self):
        anchor = audit.anchors_for(self.SOURCE, [self.SOURCE],
                                   ("parameter", "Client.__init__", "http2"), self.QUOTE)
        return {"id": "httpx:http2", "project": "public-httpx", "category": "current",
                "required": [{"session_id": "current.py", "quote": self.QUOTE,
                              "allowed_anchors": anchor}]}

    def response(self, start, end, turn=0):
        return {"results": [{"text": self.QUOTE, "source_refs": [{"project": "public-httpx",
                "session_id": "current.py", "turn_index": turn, "turn_start": start, "turn_end": end}]}]}

    def test_frozen_scope_plan_covers_all_unchanged_gold_without_response_input(self):
        plan = json.loads((audit.ROOT / audit.PLAN).read_text())
        self.assertEqual(plan["parent_holdout_commit"], audit.HOLDOUT_COMMIT)
        self.assertEqual(len(plan["cases"]), 48)
        self.assertEqual(sum(len(case["required"]) for case in plan["cases"]), 44)
        self.assertTrue(all(len(gold["allowed_anchors"]) == 1
                            for case in plan["cases"] for gold in case["required"]))
        self.assertEqual(sum(not case["required"] for case in plan["cases"]), 8)

    def test_equal_async_client_literal_does_not_satisfy_client_scope(self):
        case = self.case()
        wrong = 6 + self.SOURCE.index(self.QUOTE, self.SOURCE.index("class AsyncClient"))
        self.assertFalse(audit.strict_score(case, self.response(wrong, wrong + len(self.QUOTE)))["complete"])
        allowed = case["required"][0]["allowed_anchors"][0]
        self.assertTrue(audit.strict_score(case, self.response(allowed["turn_start"], allowed["turn_end"]))["complete"])

    def test_same_turn_id_is_not_enough_when_excerpt_does_not_cover_exact_declaration(self):
        case = self.case()
        allowed = case["required"][0]["allowed_anchors"][0]
        self.assertFalse(audit.strict_score(case, self.response(allowed["turn_start"] + 1, allowed["turn_end"]))["complete"])
        self.assertFalse(audit.strict_score(case, self.response(allowed["turn_start"], allowed["turn_end"], turn=1))["complete"])

    def test_foreign_project_and_wrong_source_never_receive_scope_credit(self):
        case = self.case()
        allowed = case["required"][0]["allowed_anchors"][0]
        for key, value in (("project", "clone-public-httpx"), ("session_id", "old.py")):
            response = self.response(allowed["turn_start"], allowed["turn_end"])
            response["results"][0]["source_refs"][0][key] = value
            self.assertFalse(audit.strict_score(case, response)["complete"])

    def test_module_and_class_assignments_have_distinct_anchors(self):
        text = "LIMIT = 10\nclass Other:\n    LIMIT = 10\n"
        module = audit.declaration_locations(text, ("module", "", "LIMIT"), "LIMIT = 10")
        other = audit.declaration_locations(text, ("class", "Other", "LIMIT"), "LIMIT = 10")
        self.assertEqual(module[0][0], 0)
        self.assertGreater(other[0][0], module[0][0])

    def test_initializer_does_not_credit_nested_function_assignment(self):
        text = ("class Session:\n    def __init__(self):\n"
                "        self.timeout = 10\n"
                "        def unrelated():\n            self.timeout = 99\n")
        self.assertEqual(len(audit.declaration_locations(text,
            ("assignment", "Session.__init__", "self.timeout"), "self.timeout = 10")), 1)
        with self.assertRaises(ValueError):
            audit.declaration_locations(text, ("assignment", "Session.__init__", "self.timeout"), "self.timeout = 99")

    def test_ast_utf8_columns_become_unicode_turn_coordinates(self):
        text = "class 配置:\n    def __init__(self, 前缀=None, 参数: int = 7,):\n        pass\n"
        quote = "参数: int = 7,"
        anchor = audit.anchors_for(text, [text], ("parameter", "配置.__init__", "参数"), quote)[0]
        self.assertEqual(anchor["source_start"], text.index(quote))
        self.assertEqual(anchor["turn_start"], 6 + text.index(quote))

    def test_wrong_or_ambiguous_named_function_is_rejected(self):
        for text, owner in ((self.SOURCE, "Unknown.__init__"),
                            (self.SOURCE.replace("class AsyncClient", "class Client"), "Client.__init__")):
            with self.assertRaises(ValueError):
                audit.declaration_locations(text, ("parameter", owner, "http2"), self.QUOTE)

    def test_scope_audit_cannot_make_missing_or_partial_gold_complete(self):
        case = self.case()
        allowed = case["required"][0]["allowed_anchors"][0]
        response = self.response(allowed["turn_start"], allowed["turn_end"])
        extra = deepcopy(case["required"][0])
        extra["session_id"] = "other-file.py"
        case["required"].append(extra)
        self.assertFalse(audit.strict_score(case, response)["complete"])
        case.update(required=[], category="missing")
        self.assertFalse(audit.strict_score(case, response)["complete"])


if __name__ == "__main__":
    unittest.main()
