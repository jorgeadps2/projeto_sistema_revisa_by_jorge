import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from pypdf import PdfReader
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from revisa_integrado.core import paths

paths.ensure_module_paths()
import folha_pagamento as payroll


class SignaturePageTests(unittest.TestCase):
    def test_stamp_on_every_page_is_covered_by_one_valid_signature(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SIGNATARIO DE TESTE")])
            now = datetime.now(timezone.utc)
            certificate = (
                x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1))
                .not_valid_after(now + timedelta(days=1))
                .add_extension(x509.KeyUsage(
                    digital_signature=True, content_commitment=True, key_encipherment=False,
                    data_encipherment=False, key_agreement=False, key_cert_sign=False,
                    crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
                .sign(key, hashes.SHA256())
            )
            pfx = root / "test.pfx"
            pfx.write_bytes(pkcs12.serialize_key_and_certificates(
                b"test", key, certificate, None,
                serialization.BestAvailableEncryption(b"test-only")))
            for sizes in (((595, 842),), ((595, 842), (842, 595), (595, 842))):
                with self.subTest(pages=len(sizes)):
                    output = root / f"{len(sizes)}.pdf"
                    canvas = Canvas(str(output))
                    for index, size in enumerate(sizes):
                        canvas.setPageSize(size)
                        canvas.drawString(50, size[1] - 80, f"RELATORIO DE TESTE {index + 1}")
                        canvas.showPage()
                    canvas.save()
                    with patch.object(payroll, "signing_pfx_path", return_value=str(pfx)), \
                            patch.dict(payroll._SIGN_PASSWORD, {"value": "test-only"}), \
                            patch.object(payroll, "remember_signing_expiry"):
                        self.assertTrue(payroll.sign_pdf_file(str(output)))
                    reader = PdfReader(output)
                    self.assertEqual(len(reader.pages), len(sizes))
                    for index, page in enumerate(reader.pages):
                        text = page.extract_text()
                        self.assertIn(f"RELATORIO DE TESTE {index + 1}", text)
                        if index < len(sizes) - 1:
                            self.assertIn("Assinado digitalmente", text)
                            self.assertIn("SIGNATARIO DE TESTE", text)
                        else:
                            annotations = [ref.get_object() for ref in page["/Annots"]]
                            field = next(a for a in annotations if a.get("/FT") == "/Sig")
                            self.assertEqual(field["/T"], "AssinaturaRevisa")
                            self.assertTrue(field["/AP"]["/N"].get_object().get_data())
                    with output.open("rb") as stream:
                        signed = PdfFileReader(stream)
                        self.assertEqual(len(signed.embedded_signatures), 1)
                        signature = signed.embedded_signatures[0]
                        context = ValidationContext(
                            trust_roots=[signature.signer_cert], allow_fetching=False)
                        status = validate_pdf_signature(signature, context)
                        self.assertTrue(status.intact)
                        self.assertTrue(status.valid)
                    self.assertFalse(Path(str(output) + ".assinado").exists())


if __name__ == "__main__":
    unittest.main()
