import unittest

from access_trace.source_patch import apply_unified_patch
from access_trace.source_review import SourceReviewError


class SourcePatchTests(unittest.TestCase):
    def test_applies_exact_patch_and_preserves_crlf(self):
        patch = (
            "diff --git a/src/a.css b/src/a.css\n"
            "index 1234567..7654321 100644\n"
            "--- a/src/a.css\n+++ b/src/a.css\n"
            "@@ -1,2 +1,2 @@\n-old {\r\n+new {\r\n body {}\r\n"
        )
        self.assertEqual(
            {"src/a.css": "new {\r\nbody {}\r\n"},
            apply_unified_patch(patch, {"src/a.css": "old {\r\nbody {}\r\n"}),
        )

    def test_preserves_missing_final_newline(self):
        patch = (
            "diff --git a/src/a.js b/src/a.js\n"
            "--- a/src/a.js\n+++ b/src/a.js\n"
            "@@ -1 +1 @@\n-old\n\\ No newline at end of file\n"
            "+new\n\\ No newline at end of file\n"
        )
        self.assertEqual({"src/a.js": "new"}, apply_unified_patch(patch, {"src/a.js": "old"}))

    def test_rejects_stale_source_and_new_files(self):
        patch = (
            "diff --git a/src/a.js b/src/a.js\n"
            "--- a/src/a.js\n+++ b/src/a.js\n@@ -1 +1 @@\n-old\n+new\n"
        )
        with self.assertRaises(SourceReviewError):
            apply_unified_patch(patch, {"src/a.js": "different\n"})
        new_file = patch.replace("--- a/src/a.js", "--- /dev/null")
        with self.assertRaises(SourceReviewError):
            apply_unified_patch(new_file, {"src/a.js": "old\n"})

    def test_rejects_paths_outside_approval_manifest(self):
        patch = (
            "diff --git a/../../outside b/../../outside\n"
            "--- a/../../outside\n+++ b/../../outside\n@@ -1 +1 @@\n-old\n+new\n"
        )
        with self.assertRaises(SourceReviewError):
            apply_unified_patch(patch, {})


if __name__ == "__main__":
    unittest.main()
