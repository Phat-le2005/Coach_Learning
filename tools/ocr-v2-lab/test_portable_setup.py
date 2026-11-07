"""Software setup checks only: no model download, inference or private fixtures."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import htr_setup


class PortableSetupTests(unittest.TestCase):
    def test_model_setup_does_not_require_private_research_captures(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            out = root / '.tmp/tri-vietnamese-htr'
            data = b'unit-test-checkpoint; not an inference model'

            def local_asset(name):
                path = out / 'model' / name
                path.write_bytes(data if name.endswith('.pth') else b'test metadata')
                return path

            with patch.multiple(htr_setup, ROOT=root, OUT=out, WEIGHT_BYTES=len(data),
                                WEIGHT_SHA=hashlib.sha256(data).hexdigest()), patch.object(htr_setup, 'download', local_asset):
                htr_setup.prepare()
            manifest = json.loads((out / 'model-manifest.json').read_text(encoding='utf8'))
            self.assertEqual(manifest['revision'], htr_setup.REVISION)
            self.assertFalse((out / 'references.utf8.json').exists())
            self.assertIsNone(manifest['originalDiagnosticsSha256'])


if __name__ == '__main__':
    unittest.main()
