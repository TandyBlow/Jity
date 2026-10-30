"""Review bookkeeping only. Synthetic opinions are never real human approval."""
import copy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import review_io


def packet():
    world = {"time": "2026-10-30T12:00:00+08:00", "places": [], "items": [],
             "characters": [{"id": "qa", "name": "工程夹具", "position": {"containerId": "test", "slot": "test"},
                             "tasks": [], "personality": [], "sanity": 50, "appearance": "工程夹具"}]}
    return {"inputSha256": "a"*64, "reviewDraftSha256": "b"*64, "provenanceSha256": "c"*64,
            "cases": [{"caseId": "qa-only-"+str(i), "sourceGroup": "qa-source-"+str(i), "task": "D02",
                       "inputSha256": str(i)*64, "reviewSha256": str(i+2)*64,
                       "input": {"world": world, "actorId": "qa", "protagonistId": "qa",
                                 "advance": {"inputText": "工程测试，不能当成人审", "intentStatus": "expired"}},
                       "guard": {"reason": "ready"},
                       "review": {"sourceNote": "仅工程夹具，非项目题目", "draftExpected": {"expectedCall": True, "kind": "skip"}}}
                      for i in (1, 2)]}


def claims(p):
    c = p["cases"][0]
    return {"schema": "jity-d-user-review-claims-v1", "reviewer": "QA SYNTHETIC ONLY",
            "exportedAt": "2026-10-30T01:00:00Z", "inputFileSha256": p["inputSha256"],
            "reviewDraftFileSha256": p["reviewDraftSha256"], "provenanceFileSha256": p["provenanceSha256"],
            "verificationStatus": "unverified_export_pending_reconciliation", "formalEvaluationAllowed": False,
            "decisions": [{"caseId": c["caseId"], "sourceGroup": c["sourceGroup"], "decision": "agree", "note": "",
                           "inputSha256": c["inputSha256"], "reviewDraftSha256": c["reviewSha256"],
                           "recordedAt": "2026-10-30T00:59:00Z"}]}


class ReviewClaimsTests(unittest.TestCase):
    def setUp(self):
        self.packet = packet()
        self.claims = claims(self.packet)

    def reject(self, edit):
        edit(self.claims)
        with self.assertRaises(ValueError):
            review_io.reconcile_claims(self.claims, self.packet)

    def test_partial_claims_preserved_without_approval_or_mutation(self):
        before = copy.deepcopy(self.claims)
        result = review_io.reconcile_claims(self.claims, self.packet)
        self.assertEqual(result["summary"]["recorded"], 1)
        self.assertEqual(result["summary"]["missing"], 1)
        self.assertEqual(result["missingCaseIds"], ["qa-only-2"])
        for key in ("formalEvaluationAllowed", "modelExecutionAuthorized", "humanSemanticApproval", "reviewerIdentityAuthenticated"):
            self.assertIs(result[key], False)
        self.assertEqual(self.claims, before)

    def test_all_claims_agree_still_cannot_approve(self):
        second = copy.deepcopy(self.claims["decisions"][0]); c = self.packet["cases"][1]
        second.update(caseId=c["caseId"], sourceGroup=c["sourceGroup"], inputSha256=c["inputSha256"], reviewDraftSha256=c["reviewSha256"])
        self.claims["decisions"].append(second)
        result = review_io.reconcile_claims(self.claims, self.packet)
        self.assertEqual(result["summary"]["agree"], 2)
        self.assertFalse(result["formalEvaluationAllowed"])
        self.assertFalse(result["humanSemanticApproval"])

    def test_batch_or_provenance_version_mismatch_rejected(self):
        for key in ("inputFileSha256", "reviewDraftFileSha256", "provenanceFileSha256"):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.claims); bad[key] = "0"*64
                with self.assertRaises(ValueError): review_io.reconcile_claims(bad, self.packet)

    def test_all_three_file_bindings_are_required(self):
        for key in ("inputFileSha256", "reviewDraftFileSha256", "provenanceFileSha256"):
            with self.subTest(missing=key):
                bad = copy.deepcopy(self.claims)
                del bad[key]
                with self.assertRaises(ValueError):
                    review_io.reconcile_claims(bad, self.packet)

    def test_case_hash_group_or_id_mismatch_rejected(self):
        for key in ("inputSha256", "reviewDraftSha256", "sourceGroup", "caseId"):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.claims); bad["decisions"][0][key] = "different"
                with self.assertRaises(ValueError): review_io.reconcile_claims(bad, self.packet)

    def test_duplicate_case_rejected(self):
        self.reject(lambda d: d["decisions"].append(copy.deepcopy(d["decisions"][0])))

    def test_revise_requires_reason(self):
        self.reject(lambda d: d["decisions"][0].update(decision="revise", note=" "))

    def test_revise_and_uncertain_stay_distinct(self):
        for decision in ("revise", "uncertain"):
            self.claims["decisions"][0].update(decision=decision, note="工程反例")
            result = review_io.reconcile_claims(self.claims, self.packet)
            self.assertEqual(result["summary"][decision], 1)
            self.assertEqual(result["summary"]["agree"], 0)

    def test_invalid_decision_and_empty_reviewer_rejected(self):
        self.reject(lambda d: d["decisions"][0].update(decision="approved"))
        self.claims = claims(self.packet)
        self.reject(lambda d: d.update(reviewer=" "))

    def test_export_cannot_grant_permissions(self):
        self.reject(lambda d: d.update(formalEvaluationAllowed=True))

    def test_invalid_timestamp_or_duplicate_json_key_rejected(self):
        self.reject(lambda d: d["decisions"][0].update(recordedAt="2026-10-30T01:00:00"))
        with self.assertRaises(ValueError):
            review_io._parse_json('{"formalEvaluationAllowed":false,"formalEvaluationAllowed":true}')

    def test_cli_saves_new_record_and_refuses_to_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/"claims.json", Path(tmp)/"result.json"
            original = json.dumps(self.claims).encode()
            source.write_bytes(original)
            args = ["review_io.py", "reconcile", str(source), "--out", str(output)]
            with mock.patch.object(sys, "argv", args), mock.patch.object(review_io, "build_packet", return_value=self.packet), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(review_io.main(), 0)
                recorded = output.read_bytes()
                with self.assertRaises(SystemExit):
                    review_io.main()
            self.assertEqual(output.read_bytes(), recorded)
            self.assertEqual(source.read_bytes(), original)

    def test_ui_logic_with_synthetic_packet_matches_reconciliation(self):
        html = BASE.parents[1] / "artifacts/world-components-logic/l3-1-review.html"
        probe = subprocess.run(["node", str(Path(__file__).with_name("review_ui_probe.js")), str(html)],
                               input=json.dumps(self.packet), text=True, capture_output=True, check=True)
        result = json.loads(probe.stdout)
        self.assertEqual(result["checks"], 7)
        for exported in result["exports"]:
            reconciled = review_io.reconcile_claims(exported, self.packet)
            self.assertFalse(reconciled["humanSemanticApproval"])
        self.assertEqual(result["exports"][0]["decisions"][0]["decision"], "revise")


if __name__ == "__main__":
    unittest.main()
