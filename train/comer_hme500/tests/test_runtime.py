"""The former ImportError and grpcio-tools constraint must pass in a fresh process."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from packaging.requirements import Requirement
from hme_comer.check_runtime import check

ROOT=Path(__file__).resolve().parents[1]


class Runtime(unittest.TestCase):
    def test_import_in_fresh_training_interpreter(self):
        p=subprocess.run([sys.executable,'-m','hme_comer.check_runtime'],cwd=ROOT,
                         capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('W&B runtime ready:',p.stdout)

    def test_pins_satisfy_reported_grpcio_tools_constraint(self):
        requirements=[Requirement(line) for line in (ROOT/'requirements.txt').read_text().splitlines()
                      if line.strip() and not line.startswith('#')]
        pins={r.name:next(iter(r.specifier)).version for r in requirements if r.name in ('wandb','protobuf')}
        self.assertEqual(pins['wandb'],'0.26.0')
        self.assertIn(pins['protobuf'],Requirement('protobuf>=7.35.1,<8').specifier)
        versions=check()
        self.assertEqual(versions,pins)


if __name__=='__main__': unittest.main()
