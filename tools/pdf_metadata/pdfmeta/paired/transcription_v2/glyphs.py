"""Font-qualified display mapping with stable original glyph identifiers."""
from copy import deepcopy
import re
import unicodedata

from ...text_cleanup import normalize_block,ASSEMBLY,SYMBOL_FONTS,is_suspicious


def canonical_char(glyph):
    raw=glyph['text'];font=glyph['font'].split('+')[-1].casefold()
    if len(raw)!=1:
        normalized=unicodedata.normalize('NFC',raw)
        if len(normalized)==1 and not is_suspicious(normalized):return normalized,'NFC_SOURCE_GLYPH'
        return '□','UNSUPPORTED_MULTICODEPOINT_GLYPH'
    if ord(raw) in ASSEMBLY and font in SYMBOL_FONTS:
        return ASSEMBLY[ord(raw)],'DIRECT_ADOBE_SYMBOL_ASSEMBLY'
    value,quality=normalize_block({'text_raw':raw,'glyphs':[glyph]})
    if quality['unresolved_glyph_count'] or len(value)!=1:return '□','UNMAPPED_SOURCE_GLYPH'
    return value,None


def canonical_page(page):
    result=deepcopy(page);unknown=[]
    for block in result['blocks']:
        raw=block['text_raw'];cursor=0;parts=[];alignment_failed=False
        for i,g in enumerate(block['glyphs']):
            key=block['block_id']+':'+str(i);at=raw.find(g['text'],cursor)
            if at<0:
                alignment_failed=True;break
            parts.append(raw[cursor:at]);value,flag=canonical_char(g)
            prefix=raw[:at]
            decoration=('wingdings' in g['font'].lower() and not prefix.strip()
                        and re.search(r'(?:Câu|Bài|Ví dụ|Example)\s*\d',raw[at+len(g['text']):],re.I))
            if decoration:value=' ';flag='DECORATIVE_HEADING_PREFIX'
            g.update(original_text=g['text'],source_key=key,text=value,mapping_flag=flag)
            if flag in {'UNMAPPED_SOURCE_GLYPH','UNSUPPORTED_MULTICODEPOINT_GLYPH'}:unknown.append(key)
            parts.append(value);cursor=at+len(g['original_text'])
        if alignment_failed:
            # pdfplumber can deduplicate overprinted combining glyphs in its
            # line text but retain both char objects. Do not guess which char
            # was real or lose an entire item because of an unrelated line.
            block['original_line_text']=raw;block['alignment_error']='DEDUPLICATED_OR_MULTICODEPOINT_SOURCE_LINE'
            for i,g in enumerate(block['glyphs']):
                g.setdefault('original_text',g['text']);g.update(text='□',source_key=block['block_id']+':'+str(i),mapping_flag='SOURCE_LINE_ALIGNMENT_ERROR')
            block['text_raw']='□'*len(block['glyphs'])
        else:
            parts.append(raw[cursor:]);block['text_raw']=''.join(parts)
    result['unmapped_glyph_keys']=unknown
    return result


def glyph_lookup(page):
    return {b['block_id']+':'+str(i):dict(g,key=b['block_id']+':'+str(i),block_id=b['block_id'])
            for b in page['blocks'] for i,g in enumerate(b['glyphs'])}
