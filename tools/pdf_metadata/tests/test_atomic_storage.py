import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from pdfmeta.storage import write_json,write_jsonl


@pytest.mark.parametrize('jsonl',[False,True])
def test_windows_reader_lock_is_retried_without_losing_previous_data(tmp_path,monkeypatch,jsonl):
    target=tmp_path/('data.jsonl' if jsonl else 'data.json')
    target.write_text('old',encoding='utf-8')
    original=Path.replace;calls=[]
    def briefly_locked(self,destination):
        calls.append(str(self))
        if len(calls)==1:raise PermissionError('simulated Windows open-reader lock')
        return original(self,destination)
    monkeypatch.setattr(Path,'replace',briefly_locked)
    write_jsonl(target,[{'value':1}]) if jsonl else write_json(target,{'value':1})
    assert json.loads(target.read_text(encoding='utf-8'))=={'value':1}
    assert len(calls)==2 and not list(tmp_path.glob('*.pending'))


def test_concurrent_publishers_use_separate_temporary_files(tmp_path):
    target=tmp_path/'progress.json'
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n:write_json(target,{'writer':n,'text':'x'*10000}),range(12)))
    assert json.loads(target.read_text())['writer'] in range(12)
    assert not list(tmp_path.glob('*.pending'))


def test_invalid_payload_cannot_replace_a_valid_checkpoint(tmp_path):
    target=tmp_path/'checkpoint.json';write_json(target,{'ok':True})
    before=target.read_bytes()
    with pytest.raises(TypeError):write_json(target,object())
    assert target.read_bytes()==before and not list(tmp_path.glob('*.pending'))
