import unittest
from offline_ai.reference_context import build_reference_context


class ReferenceBridgeTests(unittest.TestCase):

    def test_medical_reference(self):
        result = build_reference_context(
            "My friend twisted their ankle",
            predict=lambda _: "medical"
        )
        self.assertEqual(
            [r["title"] for r in result["references"]],
            ["Sprains and Strains"]
        )
        self.assertTrue(result["context"])

    def test_nonmedical_question(self):
        result = build_reference_context(
            "How do I cook pasta?",
            predict=lambda _: "other"
        )
        self.assertEqual(result["references"], [])
        self.assertEqual(result["context"], "")

    def test_executorch_changes_ranking(self):
        question = "Someone is bleeding and has burns"
        normal = build_reference_context(question)
        model = build_reference_context(
            question,
            predict=lambda _: "fire"
        )

        self.assertEqual(
            [r["title"] for r in normal["references"]],
            ["Bleeding", "Burns"]
        )
        self.assertEqual(
            [r["title"] for r in model["references"]],
            ["Burns", "Bleeding"]
        )

    def test_classifier_failure_fallback(self):
        def broken(_):
            raise RuntimeError("ExecuTorch unavailable")

        result = build_reference_context(
            "My friend is bleeding heavily",
            predict=broken
        )

        self.assertEqual(
            [r["title"] for r in result["references"]],
            ["Bleeding"]
        )
        self.assertIsNone(result["executorch_topic"])


if __name__ == "__main__":
    unittest.main()
