"""Vector parser integrity/safety, not recognition accuracy tests."""
import hashlib
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('evaluation_import', pathlib.Path(__file__).with_name('prepare_evaluation.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class VectorImport(unittest.TestCase):
    def test_namespace_channel_order_identity_and_original_label(self):
        raw = b'''<ink xmlns="http://www.w3.org/2003/InkML"><annotation type="label">x^2+1</annotation>
        <traceFormat><channel name="T"/><channel name="Y"/><channel name="X"/></traceFormat>
        <trace id="dot">10 5 2</trace><trace id="curve">11 6 3,12 7 4</trace></ink>'''
        result = module.parse_inkml(raw, 'source', 'sample.inkml')
        self.assertEqual(result['label'], 'x^2+1')
        self.assertEqual([t['id'] for t in result['traces']], ['dot', 'curve'])
        self.assertEqual(result['traces'][0]['points'], [{'x': 2, 'y': 5, 't': 10}])
        self.assertEqual(result['traces'][1]['points'][1], {'x': 4, 'y': 7, 't': 12})
        self.assertEqual(result['checksum'], hashlib.sha256(raw).hexdigest())

    def test_rejects_non_absolute_unsafe_or_invalid_vectors(self):
        for raw in [b'<!DOCTYPE ink><ink/>', b'<ink><trace>!1 2</trace></ink>',
                    b'<ink><trace>nan 2</trace></ink>', b'<ink><trace>1 inf</trace></ink>',
                    b'<ink><trace id="a">1 2</trace><trace id="a">3 4</trace></ink>',
                    b'<ink><trace>1</trace></ink>']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                module.parse_inkml(raw, 'source', 'sample.inkml')

if __name__ == '__main__': unittest.main()
