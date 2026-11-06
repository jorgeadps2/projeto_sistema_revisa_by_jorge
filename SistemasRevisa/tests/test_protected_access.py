import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.core.security import AttemptLimiter
from revisa_integrado.ui import pages


class ProtectedAccessTests(unittest.TestCase):
    def setUp(self):
        self.window = SimpleNamespace(
            sync_limiter=AttemptLimiter(),
            log=Mock(),
        )

    def test_password_is_checked_each_time_protected_area_is_opened(self):
        with patch.object(pages.simpledialog, "askstring", return_value="secret") as ask, \
                patch.object(pages.folha, "verify_password", return_value=True) as verify:
            self.assertTrue(pages.verify_main_password(self.window))
            self.assertTrue(pages.verify_main_password(self.window))

        self.assertEqual(ask.call_count, 2)
        self.assertEqual(verify.call_count, 2)

    def test_wrong_password_is_rejected_and_limited(self):
        with patch.object(pages.simpledialog, "askstring", return_value="wrong"), \
                patch.object(pages.folha, "verify_password", return_value=False), \
                patch.object(pages.messagebox, "showerror") as showerror:
            self.assertFalse(pages.verify_main_password(self.window))

        self.assertEqual(self.window.sync_limiter.failures, 1)
        showerror.assert_called_once()


if __name__ == "__main__":
    unittest.main()
