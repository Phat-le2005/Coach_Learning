"""Render detector overlays from observed browser PNGs; never recognition/GT generation."""
import json,pathlib
from PIL import Image,ImageDraw
out=pathlib.Path(__file__).resolve().parents[2]/'.tmp/tri-ocr-v2-e2e/overlays'
for f in out.glob('*.boxes.json'):
    name=f.name.removesuffix('.boxes.json'); value=json.loads(f.read_text());image=Image.open(out/(name+'.input.png')).convert('RGB');draw=ImageDraw.Draw(image)
    for i,r in enumerate(value['regions']):
        draw.rectangle(r['box'],outline='#a02090',width=2)
        draw.text((r['box'][0],max(0,r['box'][1]-14)),f"{i+1} {r['label']} {r.get('score')}",fill='#a02090')
    image.save(out/(name+'.overlay.png'))
