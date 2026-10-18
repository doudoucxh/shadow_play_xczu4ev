#!/usr/bin/env python3
"""Rebuild the frozen offline UI using Python 3 only, without training data."""
import argparse,base64,json
from pathlib import Path

def build(source,output):
    read=lambda name:(source/name).read_text(encoding='utf-8-sig')
    html=read('shadow-book-ui.html')
    fonts=''
    for name,license_file in [('shadow-brush-font.css','ShadowBrush-OFL.txt'),('shadow-ink-font.css','ShadowInk-OFL.txt')]:
        fonts+='/*\n'+read('assets/'+license_file).replace('*/','* /')+'\n*/\n'+read('assets/'+name)
    for name in ['shadow-ink-sequence-font.css','shadow-ink-twenty-font.css','shadow-ink-board-font.css']:
        fonts+=read('assets/'+name)
    html=html.replace('<!-- BRUSH_FONT_STYLE -->','<style>'+fonts+'</style>')
    assets={}
    for name,filename,mime in [('wusong','real-wusong.webp','image/webp'),('tiger','real-tiger.webp','image/webp'),('flag','real-wine-flag.jpg','image/jpeg')]:
        assets[name]='data:'+mime+';base64,'+base64.b64encode((source/'assets'/filename).read_bytes()).decode('ascii')
    catalog=json.loads(read('catalog.json'))
    public_catalog={'catalog_id':catalog['catalog_id'],'actions':[{key:row[key] for key in ['id','name','pose','instruction','distinguishing_instruction'] if key in row} for row in catalog['actions']]}
    asset_script='window.ShadowPuppetAssets='+json.dumps(assets,separators=(',',':'))+';window.ShadowActionCatalog='+json.dumps(public_catalog,ensure_ascii=True,separators=(',',':'))+';\n'
    modules=[('STAGE_ART','stage-art.js'),('BOOK_EFFECTS','book-effects.js'),('PAPER_BURN','paper-burn.js'),('PAGE_TURN','page-turn.js'),('SKETCH_MODEL','sketch-model.js'),('BRUSH_INK','brush-ink.js'),('CAMERA_PREVIEW','camera-preview.js'),('APPLICATION','shadow-app.js')]
    for marker,name in modules:
        script=read(name)
        if name=='stage-art.js':script=asset_script+script
        if name=='brush-ink.js':script=read('sketch-paper.js')+'\n'+script
        if name=='sketch-model.js':
            for helper in ['sketch-geometry.js','sketch-topology.js','sketch-recognition.js']:script+='\n'+read(helper)
        if name=='shadow-app.js':script=read('board-client.js')+'\n'+script+'\n'+read('action-reference.js')
        token='<!-- '+marker+'_SCRIPT -->'
        if token not in html:raise ValueError('Missing module marker: '+token)
        prefix='<style>'+read('board-client.css')+'</style>' if name=='shadow-app.js' else ''
        html=html.replace(token,prefix+'<script>\n'+script+'\n</script>')
    # The deployment uses the offline drawing guide instead of a collector link.
    html=html.replace('href="http://127.0.0.1:8780/"','href="#"')
    html+='\n<style>'+read('button-brush.css')+'</style>'
    performance=read('board-performance.css')
    for marker,filename in [('BOARD_PAPER','board-paper.png'),('BOARD_VIGNETTE','board-vignette.png')]:
        performance=performance.replace(marker,'data:image/png;base64,'+base64.b64encode((source/'assets'/filename).read_bytes()).decode('ascii'))
    shell='html,body{margin:0;min-height:100%;background:#19140f}body{display:flex;align-items:center;justify-content:center;min-height:100vh}body>#shadow-theatre-preview{width:1024px;max-width:100%}'
    document='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#19140f"><title>皮影戏台 · HDMI</title><style>'+shell+'</style></head><body><script>'+read('platform.js')+'</script>'+html+'<style id="shadow-board-performance">'+performance+'</style></body></html>'
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8',newline='\n') as handle:handle.write(document)
    print(str(output)+' ('+str(output.stat().st_size)+' bytes)')

if __name__=='__main__':
    default_root=Path(__file__).resolve().parent.parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=default_root/'source')
    parser.add_argument('--output',type=Path,default=default_root/'runtime/web/index.html')
    args=parser.parse_args();build(args.source.resolve(),args.output.resolve())
