import pytest
from pdfmeta.direct_pdf_ocr import selected_pages,clean_markdown


@pytest.fixture(autouse=True)
def local_layout_without_model(monkeypatch):
    import pdfmeta.direct_pdf_ocr as direct
    from pdfmeta.direct_pdf_layout import prepare
    class EmptyDetector:
        def predict(self,path):return []
    monkeypatch.setattr(direct,'ensure_layout',lambda pdf,runtime,output,pages,dpi:
        prepare(pdf,runtime,output,pages=pages,dpi=dpi,detector=EmptyDetector(),model={'fixture':'no-model'}))


def test_page_selection_is_bounded_and_deduplicated():
    assert selected_pages('2-4,3,1',5)==[1,2,3,4]
    assert selected_pages('all',3)==[1,2,3]
    for invalid in ['0','2-1','6','2,x']:
        with pytest.raises(ValueError):selected_pages(invalid,5)


def test_vision_image_links_are_removed_without_changing_transcribed_math():
    text='Visible text $x^2$.\n![invented](https://example.invalid/picture.png)'
    value,flags=clean_markdown(text)
    assert value=='Visible text $x^2$.' and flags==['MODEL_IMAGE_REFERENCE_REMOVED']
    assert clean_markdown('Native OCR text $x^2$.')==('Native OCR text $x^2$.',[])


def test_pdf_only_image_input_can_run_and_resume_without_reference_files(tmp_path,monkeypatch):
    import base64,io
    from PIL import Image,ImageDraw
    import pdfmeta.direct_pdf_ocr as direct
    from pdfmeta.storage import write_json
    image=Image.new('RGB',(200,100),'white');ImageDraw.Draw(image).rectangle((20,20,100,70),fill='black')
    pdf=tmp_path/'only-input.pdf';image.save(pdf,resolution=72)
    runtime=tmp_path/'runtime';write_json(runtime/'local-qwen-runtime.json',{'model':'test-local-reader'})
    seen=[]
    class Reader:
        def __init__(self,*args):pass
        def preflight(self,*args):pass
        def close(self):pass
        def generate(self,parts,*args):
            data=base64.b64decode(parts[1]['inlineData']['data'])
            with Image.open(io.BytesIO(data)) as crop:
                assert 0<crop.width<=200 and 0<crop.height<=100 and crop.convert('L').getextrema()[0]<50
            seen.append(1)
            return {'status':'RESPONSE_RECEIVED','result':{'markdown':'Observed pixels $x^2$.','uncertain':False}}
    monkeypatch.setattr(direct,'LocalClient',Reader)
    first=direct.run(pdf,runtime,tmp_path/'output',dpi=72)
    second=direct.run(pdf,runtime,tmp_path/'output',dpi=72)
    assert first['external_reference_inputs']==[] and len(seen)==1
    assert first['inference_calls_this_run']==1 and second['cache_hits_this_run']==1
    assert (tmp_path/'output/document.ocr.md').read_text(encoding='utf-8').count('Observed pixels')==1


def test_truncated_repetitive_and_invalid_responses_are_not_accepted():
    from pdfmeta.direct_pdf_ocr import response_error
    assert response_error({'status':'INCOMPLETE_OR_BLOCKED','payload':{'choices':[{'finish_reason':'length'}]}})=='OUTPUT_TOKEN_LIMIT'
    assert response_error({'status':'RESPONSE_RECEIVED','result':{'markdown':'word '*100,'uncertain':False}})=='REPEATED_MODEL_TEXT'
    assert response_error({'status':'RESPONSE_RECEIVED','result':{'markdown':'text','uncertain':'false'}})=='INVALID_MODEL_FIELDS'
    assert response_error({'status':'INCOMPLETE_OR_BLOCKED','payload':{'choices':[]}})=='INCOMPLETE_OR_BLOCKED'


def open_grid():
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(320,250),'white');draw=ImageDraw.Draw(image)
    draw.line((25,70,300,70),fill='black',width=2)
    draw.line((25,110,300,110),fill='black',width=2)
    draw.line((65,30,65,210),fill='black',width=2)
    draw.text((80,40),'1 2 3',fill='black')
    draw.text((80,90),'+ - +',fill='black')
    draw.text((80,140),'values',fill='black')
    draw.text((30,5),'question',fill='black')
    draw.text((30,230),'solution',fill='black')
    return image


def test_open_variation_table_is_separated_into_visible_rows_and_columns():
    from pdfmeta.direct_pdf_regions import detect_tables,plan_regions
    image=open_grid();tables=detect_tables(image)
    assert len(tables)==1 and tables[0]['rows']==3 and tables[0]['columns']==2
    nodes=plan_regions(image,500)
    assert [n['kind'] for n in nodes]==['TEXT','TABLE','TEXT']
    assert len(tables[0]['cells'])==6


def test_failed_whole_crop_splits_and_successful_children_resume(tmp_path):
    from PIL import Image,ImageDraw
    from pdfmeta.direct_pdf_ocr import RegionReader
    image=Image.new('RGB',(200,140),'white');draw=ImageDraw.Draw(image)
    draw.text((10,10),'top text',fill='black');draw.text((10,110),'bottom text',fill='black')
    class Reader:
        calls=0
        def generate(self,*args):
            self.calls+=1
            if self.calls==1:return {'status':'INCOMPLETE_OR_BLOCKED','payload':{'choices':[{'finish_reason':'length'}]}}
            return {'status':'RESPONSE_RECEIVED','result':{'markdown':f'Observed part {self.calls}','uncertain':False}}
    client=Reader();reader=RegionReader(client,tmp_path,'binding',2048,7,2)
    row=reader.read(image,(0,0,200,140),'region')
    assert row['status']=='OK' and client.calls==3 and len(row['children'])==2
    assert 'OCR_INCOMPLETE' not in row['markdown']
    reader.read(image,(0,0,200,140),'region')
    assert client.calls==3 and reader.hits==1


def test_budget_failure_continues_to_next_page_and_resume_retries_only_failed_leaves(tmp_path,monkeypatch):
    from PIL import Image,ImageDraw
    import pdfmeta.direct_pdf_ocr as direct
    from pdfmeta.storage import write_json,read_json
    images=[]
    for page_index in range(2):
        image=Image.new('RGB',(200,140),'white')
        for y in [10,55,110]:ImageDraw.Draw(image).text((10,y),f'printed text {page_index}',fill='black')
        images.append(image)
    pdf=tmp_path/'input.pdf';images[0].save(pdf,resolution=72,save_all=True,append_images=images[1:])
    runtime=tmp_path/'runtime';write_json(runtime/'local-qwen-runtime.json',{'model':'test','threads':3})
    class Reader:
        calls=0
        recover=False
        def __init__(self,*args):pass
        def preflight(self,*args):pass
        def close(self):pass
        def generate(self,*args):
            Reader.calls+=1
            if not Reader.recover and Reader.calls<=3:
                return {'status':'INCOMPLETE_OR_BLOCKED','payload':{'choices':[{'finish_reason':'length'}]}}
            return {'status':'RESPONSE_RECEIVED','result':{'markdown':'Câu 2. Printed question\nGiải\nPrinted solution $x^2$.','uncertain':False}}
    monkeypatch.setattr(direct,'LocalClient',Reader)
    first=direct.run(pdf,runtime,tmp_path/'output',dpi=72,max_calls_per_region=3,max_split_depth=1)
    assert first['status']=='OCR_DRAFT_INCOMPLETE' and first['processed_pages']==2
    assert first['failed_regions']==1 and first['inference_calls_this_run']==4
    assert 'Printed solution' in (tmp_path/'output/document.ocr.md').read_text(encoding='utf-8')
    content=read_json(tmp_path/'output/content.draft.pretty.json')
    assert content[0]['solution']['markdown'].endswith('$x^2$.') and content[0]['source']['sha256']==first['input_sha256']
    assert content[0]['academic_review']=='PENDING' and not content[0]['publishable']
    Reader.recover=True
    second=direct.run(pdf,runtime,tmp_path/'output',dpi=72,max_calls_per_region=3,max_split_depth=1)
    assert second['failed_regions']==0 and second['inference_calls_this_run']==2 and second['cache_hits_this_run']==1
    assert read_json(tmp_path/'output/failures.json')==[]


def test_table_is_preserved_whole_without_ocr_cells_with_pdf_coordinate_provenance(tmp_path):
    from pdfmeta.direct_pdf_ocr import RegionReader,read_region
    class Reader:
        def generate(self,*args):
            return {'status':'RESPONSE_RECEIVED','result':{'markdown':'visible content','uncertain':False}}
    reader=RegionReader(Reader(),tmp_path,'binding',2048,24,2)
    row=read_region(reader,open_grid(),[100,200,420,450],1,1,72)
    tables=[b['visual_asset'] for b in row['blocks'] if b['kind']=='VISUAL']
    assert row['status']=='OK' and len(tables)==1 and tables[0]['kind']=='TABLE'
    assert tables[0]['status']=='PRESERVED_AS_IMAGE' and tables[0]['path'].startswith('visual_assets/')
    assert 100<=tables[0]['bbox'][0]<tables[0]['bbox'][2]<=420
    assert 200<=tables[0]['bbox'][1]<tables[0]['bbox'][3]<=450
    assert (tmp_path/tables[0]['path']).exists() and 'cells' not in tables[0]


def test_changing_cpu_threads_keeps_source_binding_but_other_pdf_is_rejected(tmp_path,monkeypatch):
    from PIL import Image,ImageDraw
    import pdfmeta.direct_pdf_ocr as direct
    from pdfmeta.storage import write_json
    image=Image.new('RGB',(200,100),'white');ImageDraw.Draw(image).text((10,10),'source',fill='black')
    pdf=tmp_path/'input.pdf';image.save(pdf,resolution=72)
    runtime=tmp_path/'runtime';write_json(runtime/'local-qwen-runtime.json',{'model':'test','threads':3})
    class Reader:
        def __init__(self,*args):pass
        def preflight(self,*args):pass
        def close(self):pass
        def generate(self,*args):return {'status':'RESPONSE_RECEIVED','result':{'markdown':'Câu 1. Source text','uncertain':False}}
    monkeypatch.setattr(direct,'LocalClient',Reader)
    direct.run(pdf,runtime,tmp_path/'output',dpi=72)
    write_json(runtime/'local-qwen-runtime.json',{'model':'test','threads':6})
    second=direct.run(pdf,runtime,tmp_path/'output',dpi=72)
    assert second['inference_calls_this_run']==0 and second['cache_hits_this_run']==1
    ImageDraw.Draw(image).text((10,50),'changed',fill='black');image.save(pdf,resolution=72)
    with pytest.raises(ValueError,match='INPUT_OR_MODEL_CHANGED'):
        direct.run(pdf,runtime,tmp_path/'output',dpi=72)


def test_verified_legacy_success_is_reused_after_upgrade_without_model_calls(tmp_path,monkeypatch):
    import hashlib
    import pypdfium2 as pdfium
    from PIL import Image,ImageDraw
    import pdfmeta.direct_pdf_ocr as direct
    from pdfmeta.storage import file_hash,write_json,read_json
    image=Image.new('RGB',(200,100),'white');ImageDraw.Draw(image).text((10,10),'printed question',fill='black')
    pdf=tmp_path/'input.pdf';image.save(pdf,resolution=72)
    runtime=tmp_path/'runtime';manifest={'model':'test','threads':3}
    write_json(runtime/'local-qwen-runtime.json',manifest)
    output=tmp_path/'output';asset=output/'assets/page-0001-region-001.png';asset.parent.mkdir(parents=True)
    with pdfium.PdfDocument(pdf) as doc:
        page=doc[0];bitmap=page.render(scale=1)
        try:bitmap.to_pil().save(asset)
        finally:bitmap.close();page.close()
    identity=direct.content_hash({'pdf':file_hash(pdf),'dpi':72,'pages':'all','max_tokens':2048,
                                 'prompt':direct.PROMPT,'model':manifest,'code_sha256':direct.LEGACY_CODE_SHA})
    write_json(output/'run-identity.json',{'identity':identity,'input_sha256':file_hash(pdf),'dpi':72})
    write_json(output/'preflight.json',{'threads':3})
    response={'status':'RESPONSE_RECEIVED','result':{'markdown':'Câu 1. Existing source text\nGiải\nExisting solution.','uncertain':False}}
    write_json(output/'pages/page-0001-region-001.json',{
        'identity':hashlib.sha256((identity+file_hash(asset)).encode()).hexdigest(),
        'source_image_sha256':file_hash(asset),'raw_response':response,'uncertain':False})
    class Reader:
        def __init__(self,*args):pass
        def preflight(self,*args):pass
        def close(self):pass
        def generate(self,*args):raise AssertionError('A verified successful crop must not be inferred again')
    monkeypatch.setattr(direct,'LocalClient',Reader)
    manifest['threads']=6;write_json(runtime/'local-qwen-runtime.json',manifest)
    result=direct.run(pdf,runtime,output,dpi=72)
    assert result['inference_calls_this_run']==0 and result['cache_hits_this_run']==1
    assert read_json(output/'run-identity.legacy.json')['identity']==identity
    assert read_json(output/'content.draft.pretty.json')[0]['solution']['markdown']=='Giải\nExisting solution.'


def test_content_export_preserves_unlabelled_material_and_never_infers_an_answer(tmp_path):
    from pdfmeta.direct_pdf_content import publish_pages
    from pdfmeta.storage import read_json
    source={'name':'only-input.pdf','sha256':'a'*64}
    block={'kind':'TEXT','bbox':[0,0,200,100],'source_image':'assets/crop.png','source_image_sha256':'b'*64,
           'status':'OK','markdown':'Printed heading\nCâu 1. First question\nGiải\nFirst solution\nCâu 2. Second question'}
    rows=[{'page_number':1,'native_text_from_this_pdf':'','markdown':block['markdown'],
           'regions':[{'region_number':1,'blocks':[block]}]}]
    assert publish_pages(tmp_path,rows,source)==2
    content=read_json(tmp_path/'content.draft.pretty.json')
    assert content[0]['solution']['markdown']=='Giải\nFirst solution'
    assert content[1]['solution']['markdown']=='' and content[0]['answer']['markdown']==''
    assert content[0]['question']['fragments'][0]['coverage']['complete_formula_recall_established'] is False
    assert read_json(tmp_path/'content.unassigned.pretty.json')[0]['markdown']=='Printed heading'
    assert set(content[0])=={'collection_number','question_id','chapter_title','source','question','solution','answer','tables',
                             'academic_review','grading_support','publishable','visual_assets'}


def test_uncertainty_is_not_reported_as_a_complete_success(tmp_path):
    from PIL import Image,ImageDraw
    from pdfmeta.direct_pdf_ocr import RegionReader
    image=Image.new('RGB',(100,50),'white');ImageDraw.Draw(image).text((5,5),'text',fill='black')
    class Reader:
        def generate(self,*args):
            return {'status':'RESPONSE_RECEIVED','result':{'markdown':'Some [unreadable] text','uncertain':True}}
    row=RegionReader(Reader(),tmp_path,'binding',2048,1,0).read(image,(0,0,100,50),'crop')
    assert row['status']=='REVIEW_REQUIRED' and row['uncertain'] and not row['errors']
