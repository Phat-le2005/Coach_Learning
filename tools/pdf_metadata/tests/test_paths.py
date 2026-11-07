from pdfmeta.paths import storage_root,runtime_root


def test_runtime_follows_configured_storage_outside_repository(tmp_path,monkeypatch):
    monkeypatch.setenv('PDFMETA_STORAGE_ROOT',str(tmp_path/'storage'))
    monkeypatch.delenv('PDFMETA_RUNTIME_ROOT',raising=False)
    assert storage_root()==(tmp_path/'storage').resolve()
    assert runtime_root()==(tmp_path/'storage/pdf-pipeline-runtime').resolve()


def test_explicit_runtime_override_is_used(tmp_path,monkeypatch):
    monkeypatch.setenv('PDFMETA_STORAGE_ROOT',str(tmp_path/'storage'))
    monkeypatch.setenv('PDFMETA_RUNTIME_ROOT',str(tmp_path/'separate-runtime'))
    assert runtime_root()==(tmp_path/'separate-runtime').resolve()
