import unittest

from eligibility_v1 import VALID_STATUSES, classify_status


class EligibilityV1Tests(unittest.TestCase):
    def test_state_priority(self):
        self.assertEqual(classify_status(source_ok=False, mapping_ok=True, texture_ok=True, conditioning_ok=True, generated_ok=True, memory_known=True), "SOURCE_MISSING")
        self.assertEqual(classify_status(source_ok=True, mapping_ok=False, texture_ok=False, conditioning_ok=False, generated_ok=False, memory_known=False), "MAPPING_UNRESOLVED")
        self.assertEqual(classify_status(source_ok=True, mapping_ok=True, texture_ok=False, conditioning_ok=False, generated_ok=False, memory_known=False), "NEEDS_SHAPENET_FILE")
        self.assertEqual(classify_status(source_ok=True, mapping_ok=True, texture_ok=True, conditioning_ok=False, generated_ok=False, memory_known=False), "NEEDS_CONDITIONING")
        self.assertEqual(classify_status(source_ok=True, mapping_ok=True, texture_ok=True, conditioning_ok=True, generated_ok=False, memory_known=False), "UNSAFE_OR_UNKNOWN_MEMORY")
        self.assertEqual(classify_status(source_ok=True, mapping_ok=True, texture_ok=True, conditioning_ok=True, generated_ok=False, memory_known=True), "READY_FOR_INFERENCE")
        self.assertEqual(classify_status(source_ok=True, mapping_ok=True, texture_ok=True, conditioning_ok=True, generated_ok=True, memory_known=True), "COMPLETE_NOW")

    def test_every_return_is_declared(self):
        values = [classify_status(source_ok=a, mapping_ok=b, texture_ok=c, conditioning_ok=d, generated_ok=e, memory_known=f)
                  for a in (False, True) for b in (False, True) for c in (False, True) for d in (False, True) for e in (False, True) for f in (False, True)]
        self.assertTrue(set(values) <= VALID_STATUSES)
