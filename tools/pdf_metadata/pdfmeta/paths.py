"""Shared machine-local PDF storage defaults, independent of the checkout."""
import os
from pathlib import Path


def storage_root():
    default = Path('C:/CoachLearningPdf') if os.name == 'nt' else Path(__file__).parents[3] / '.tmp'
    return Path(os.environ.get('PDFMETA_STORAGE_ROOT') or default).expanduser().resolve()


def runtime_root():
    return Path(os.environ.get('PDFMETA_RUNTIME_ROOT') or storage_root() / 'pdf-pipeline-runtime').expanduser().resolve()
