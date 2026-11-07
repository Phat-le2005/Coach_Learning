"""Conservative whole-line OCR section hints; never rewrite source text."""
import re
import unicodedata


def distance(a,b):
    row=list(range(len(b)+1))
    for i,left in enumerate(a,1):
        following=[i]
        for j,right in enumerate(b,1):following.append(min(following[-1]+1,row[j]+1,row[j-1]+(left!=right)))
        row=following
    return row[-1]


def hint(text):
    plain=''.join(c for c in unicodedata.normalize('NFD',text.casefold().replace('đ','d')) if not unicodedata.combining(c))
    plain=re.sub(r'[.:…]+$','',plain.strip()).strip()
    plain=re.sub(r'\s+',' ',plain)
    # Short standalone labels lose accents (or one character) in scanned books.
    # Keep this allowlist narrow: arbitrary short prose is not a solution label.
    if plain in {'giai','gii'}:
        return {'kind':'SOLUTION','normalized_ocr':plain,'matched_label':'giai',
                'edit_distance':distance(plain,'giai'),'status':'OCR_SECTION_HINT_REQUIRES_SOURCE_REVIEW'}
    if not re.fullmatch(r'[a-z ]{4,18}',plain):return None
    options={'SOLUTION':['loi giai','huong dan','solution'],'RESPONSE':['tra loi']}
    matches=[]
    for kind,targets in options.items():
        for target in targets:
            edits=distance(plain,target)
            if plain[:1]==target[:1] and edits<=2 and edits/max(len(plain),len(target))<=.3:
                matches.append((edits,kind,target))
    if not matches:return None
    matches.sort()
    if len({kind for edits,kind,target in matches if edits==matches[0][0]})!=1:return None
    edits,kind,target=matches[0]
    return {'kind':kind,'normalized_ocr':plain,'matched_label':target,'edit_distance':edits,
            'status':'OCR_SECTION_HINT_REQUIRES_SOURCE_REVIEW'}
