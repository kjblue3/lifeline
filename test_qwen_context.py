import unittest
from offline_ai.qwen_context import build_qwen_messages

SYSTEM = "Original system instructions"


class QwenContextTests(unittest.TestCase):

    def test_feature_off_preserves_prompt(self):
        question = "My ankle is sprained"
        messages, result = build_qwen_messages(
            question, SYSTEM, enabled=False
        )
        self.assertEqual(messages, [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ])
        self.assertEqual(result["references"], [])

    def test_medical_context_added(self):
        messages, result = build_qwen_messages(
            "My friend twisted their ankle",
            SYSTEM,
            enabled=True,
            predictor=lambda _: "medical"
        )
        self.assertIn("Sprains and Strains", messages[1]["content"])
        self.assertEqual(messages[0]["content"], SYSTEM)
        self.assertEqual(len(result["references"]), 1)

    def test_nonmedical_chat_unchanged(self):
        question = "Tell me a joke"
        messages, result = build_qwen_messages(
            question,
            SYSTEM,
            enabled=True,
            predictor=lambda _: "other"
        )
        self.assertEqual(messages[1]["content"], question)
        self.assertEqual(result["references"], [])

    def test_classifier_failure_does_not_break_chat(self):
        def broken(_):
            raise RuntimeError("ExecuTorch unavailable")

        messages, result = build_qwen_messages(
            "My friend twisted their ankle",
            SYSTEM,
            enabled=True,
            predictor=broken
        )
        self.assertEqual(messages[0]["content"], SYSTEM)
        self.assertEqual(
            result["references"][0]["title"],
            "Sprains and Strains"
        )


if __name__ == "__main__":
    unittest.main()
