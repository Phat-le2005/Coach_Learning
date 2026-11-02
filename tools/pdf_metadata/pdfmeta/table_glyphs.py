"""Constrained printed boundary glyph matching; scores are not probabilities.

Used only for table header numbers and infinity when formula OCR is unreadable.
Font file hashes and per-character alternatives remain in the review evidence.
"""
from __future__ import annotations

from pathlib import Path
import math

from PIL import Image,ImageDraw,ImageFont,ImageOps,ImageFilter

from .safe_math import UnsupportedMath
from .storage import file_hash
from .sign_table import clusters


VERSION='table-boundary-font-match/v1'


def normalized(image):
    image=ImageOps.invert(image.convert('L')).point(lambda x:255 if x>65 else 0)
    box=image.getbbox()
    if box is None:
        raise UnsupportedMath('GLYPH_IMAGE_EMPTY')
    crop=image.crop(box)
    ratio=crop.width/crop.height
    crop=crop.resize((32,48),Image.Resampling.BILINEAR).point(lambda x:255 if x>=100 else 0)
    return crop,ratio


def similarity(a,b):
    def pixels(image):
        return list(image.get_flattened_data()) if hasattr(image,'get_flattened_data') else list(image.getdata())
    aa=pixels(a);bb=pixels(b)
    ad=pixels(a.filter(ImageFilter.MaxFilter(3)));bd=pixels(b.filter(ImageFilter.MaxFilter(3)))
    one=sum(x>0 and y>0 for x,y in zip(aa,bd))/max(1,sum(x>0 for x in aa))
    two=sum(x>0 and y>0 for x,y in zip(bb,ad))/max(1,sum(y>0 for y in bb))
    return (one+two)/2


class BoundaryGlyphs:
    def __init__(self,font_paths=None,*,alphabet='0123456789+-∞',axis=False):
        self.axis=axis
        if font_paths is None:
            font_paths=[Path(p) for p in [r'C:\Windows\Fonts\times.ttf',r'C:\Windows\Fonts\timesi.ttf',
                        r'C:\Windows\Fonts\arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'] if Path(p).is_file()]
        if not font_paths:
            raise UnsupportedMath('LOCAL_BOUNDARY_TEMPLATE_FONTS_MISSING')
        self.fonts=[{'path':str(p),'sha256':file_hash(Path(p))} for p in font_paths]
        self.templates=[]
        for path in font_paths:
            font=ImageFont.truetype(str(path),64)
            for char in alphabet:
                im=Image.new('L',(160,120),255);ImageDraw.Draw(im).text((10,10),char,font=font,fill=0)
                norm,ratio=normalized(im)
                self.templates.append((char,norm,ratio,str(path)))

    def read(self,image):
        gray=image.convert('L');ink=ImageOps.invert(gray).point(lambda x:255 if x>65 else 0)
        box=ink.getbbox()
        if box is None:
            raise UnsupportedMath('BOUNDARY_IMAGE_EMPTY')
        # A blank column separates glyphs. Bridging it would merge a tightly
        # printed '+' and infinity into one unknown glyph.
        cols=[x for x in range(box[0],box[2]) if any(ink.getpixel((x,y)) for y in range(box[1],box[3]))]
        groups=clusters(cols,distance=2 if self.axis else 1)
        if not 1<=len(groups)<=6:
            raise UnsupportedMath('BOUNDARY_GLYPH_COUNT_UNSUPPORTED')
        result,evidence=[],[]
        for columns in groups:
            crop=gray.crop((min(columns),box[1],max(columns)+1,box[3]))
            norm,ratio=normalized(crop)
            ranks={}
            for char,template,aspect,path in self.templates:
                score=similarity(norm,template)-min(.45,abs(math.log(ratio/aspect))*.2)
                if char not in ranks or score>ranks[char]['score']:
                    ranks[char]={'char':char,'score':score,'font_path':path}
            top=sorted(ranks.values(),key=lambda r:r['score'],reverse=True)[:3]
            margin=top[0]['score']-top[1]['score']
            evidence.append({'bbox_pixel':[min(columns),box[1],max(columns)+1,box[3]],
                             'alternatives':[{**r,'score':round(r['score'],4)} for r in top],
                             'score_margin':round(margin,4)})
            if top[0]['score']<.76 or margin<.035:
                raise UnsupportedMath('BOUNDARY_FONT_MATCH_AMBIGUOUS')
            result.append(top[0]['char'])
        text=''.join(result)
        import re
        if not re.fullmatch(r'[A-Za-z]' if self.axis else r'[+-]?(?:\d{1,5}|∞)',text):
            raise UnsupportedMath('BOUNDARY_FONT_MATCH_NOT_A_NUMBER_OR_INFINITY')
        return {'text':text,'algorithm':VERSION,'glyphs':evidence,'font_files':self.fonts,
                'status':'FONT_TEMPLATE_CANDIDATE_NOT_CALIBRATED_OR_VISUALLY_VERIFIED'}
