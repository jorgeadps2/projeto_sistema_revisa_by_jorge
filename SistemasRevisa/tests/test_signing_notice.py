import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from revisa_integrado.modules import folha


class SigningNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name) / "assinatura_digital.json"

    def set_expiry(self, expires):
        self.config_path.write_text(
            json.dumps({"validade": expires.isoformat()}), encoding="utf-8")

    def test_expired_signature_is_reported(self):
        expires = date.today() - timedelta(days=1)
        self.set_expiry(expires)

        with patch.object(folha, "signing_config_path", return_value=self.config_path):
            text, status, when = folha.signing_status()

        self.assertEqual(status, "expired")
        self.assertEqual(when, expires.strftime("%d/%m/%Y"))
        self.assertIn("VENCEU", text)

    def test_signature_near_expiry_is_reported_as_warning(self):
        expires = date.today() + timedelta(days=5)
        self.set_expiry(expires)

        with patch.object(folha, "signing_config_path", return_value=self.config_path):
            text, status, _ = folha.signing_status()

        self.assertEqual(status, "warning")
        self.assertIn("5 dia(s)", text)

    def test_valid_signature_and_missing_expiry_are_distinguished(self):
        expires = date.today() + timedelta(days=60)
        self.set_expiry(expires)
        with patch.object(folha, "signing_config_path", return_value=self.config_path):
            text, status, _ = folha.signing_status()
        self.assertEqual(status, "ok")
        self.assertIn(expires.strftime("%d/%m/%Y"), text)

        self.config_path.unlink()
        with patch.object(folha, "signing_config_path", return_value=self.config_path):
            text, status, _ = folha.signing_status()
        self.assertEqual(status, "unavailable")
        self.assertIn("indisponível", text)


if __name__ == "__main__":
    unittest.main()
