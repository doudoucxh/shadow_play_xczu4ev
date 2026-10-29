"""Build the offline HTML/PDF operator guide from one shared content source."""
import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT/'shadow_play/docs/bus_servo_user_guide.content.json'
HTML = ROOT/'shadow_play/docs/bus_servo_user_guide.html'
PDF = ROOT/'output/pdf/bus_servo_user_guide.pdf'


def wiring_html():
    return '''<div class="wiring" aria-label="两条独立信号总线接线示意">
    <div><strong>原9口 · E14</strong><span>人物信号总线</span><b>ID 1 / 2 / 3 / 4 / 5 / 6</b></div>
    <div><strong>原10口 · E15</strong><span>老虎信号总线</span><b>ID 7 / 8 / 9 / 10</b></div>
    <small>两组信号互不相通；舵机外接供电，地与控制板共地。</small></div>'''


def render_html(data):
    e = html.escape
    def block(b):
        kind = b['type']
        if kind == 'wiring': return wiring_html()
        if kind == 'heading': return '<h3>'+e(b['text'])+'</h3>'
        if kind == 'p': return '<p>'+e(b['text'])+'</p>'
        if kind == 'notice': return '<aside><strong>'+e(b['title'])+'</strong><p>'+e(b['text'])+'</p></aside>'
        if kind == 'steps': return '<ol>'+''.join('<li>'+e(t)+'</li>' for t in b['items'])+'</ol>'
        if kind == 'table':
            return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+e(t)+'</th>' for t in b['headers'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(t)+'</td>' for t in row)+'</tr>' for row in b['rows'])+'</tbody></table></div>'
        raise ValueError(kind)
    nav = ''.join(f'<a href="#{p["id"]}"><span>{i:02d}</span>{e(p["title"])}</a>' for i,p in enumerate(data['pages'],1))
    pages = ''.join(f'<section id="{p["id"]}"><div class="chapter">操作手册 / {i:02d}</div><h2>{e(p["title"])}</h2><p class="lead">{e(p["lead"])}</p>'+''.join(block(b) for b in p['blocks'])+'<a class="back" href="#top">返回目录 ↑</a></section>' for i,p in enumerate(data['pages'],1))
    css = '''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#eef3f5;color:#233443;font:16px/1.85 "Microsoft YaHei UI","Microsoft YaHei",sans-serif}header{background:#163e49;color:#fff;padding:42px max(5vw,24px)}header small{letter-spacing:.14em;color:#9edbd9}h1{font-size:36px;line-height:1.4;margin:8px 0}header p{margin:7px 0;color:#d5e7e9}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:20px}.actions a{background:#fff;color:#163e49;padding:8px 18px;border-radius:6px;text-decoration:none;font-weight:600}.layout{max-width:1320px;margin:28px auto;display:grid;grid-template-columns:260px minmax(0,1fr);gap:26px;padding:0 24px}nav{position:sticky;top:20px;align-self:start;background:#fff;border:1px solid #d5e1e5;border-radius:10px;padding:12px}nav a{display:block;text-decoration:none;color:#304957;padding:7px 4px;font-size:13px;border-bottom:1px solid #edf2f4}nav span{color:#207d82;font-weight:700;margin-right:9px}nav a:hover{background:#e7f3f3}section{background:#fff;padding:35px 40px;margin-bottom:25px;border:1px solid #d5e1e5;border-radius:12px;scroll-margin-top:20px}.chapter{font-size:12px;font-weight:bold;color:#247c82;letter-spacing:.12em}h2{font-size:27px;line-height:1.4;margin:8px 0 14px}h3{font-size:19px;margin:26px 0 10px;color:#145e68}p{margin:12px 0}.lead{color:#526c78;border-bottom:1px solid #dbe6e9;padding-bottom:18px}aside{background:#eaf4f4;border-left:4px solid #25888a;border-radius:4px;padding:14px 18px;margin:20px 0}aside strong{color:#175d67}aside p{margin:5px 0 0}ol{padding-left:26px}li{padding-left:4px;margin:12px 0}li::marker{color:#197a82;font-weight:bold}.table-wrap{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:14px;table-layout:fixed}th{background:#e8f0f3;text-align:left;color:#264958}th,td{padding:11px 14px;border:1px solid #d6e1e6;vertical-align:top;overflow-wrap:anywhere}th:first-child,td:first-child{width:30%}td:first-child{font-weight:600}tr:nth-child(even){background:#f8fafb}.wiring{padding:20px;border:1px solid #cadfdf;background:#f5fbfb;border-radius:8px;margin:20px 0}.wiring div{display:grid;grid-template-columns:130px 1fr 1.5fr;gap:10px;align-items:center;margin:12px 0}.wiring strong{color:#fff;background:#246f79;padding:8px;border-radius:4px;text-align:center}.wiring span{font-size:13px;text-align:center;border-bottom:2px solid #479296}.wiring b{font-size:14px;color:#205e67}.wiring small{display:block;color:#5d7078}.back{display:block;text-align:right;color:#3e7e85;font-size:13px;margin-top:24px}footer{text-align:center;padding:10px 20px 35px;font-size:12px;color:#617786}@media(max-width:900px){.layout{display:block;padding:0 12px}nav{position:static;margin-bottom:20px;display:grid;grid-template-columns:1fr 1fr}section{padding:25px 20px}h1{font-size:27px}.wiring div{grid-template-columns:110px 1fr}.wiring b{grid-column:1/-1;text-align:center}}@media print{@page{size:A4;margin:16mm}body{background:white;font-size:10pt}header{background:white;color:#163e49;padding:0}header p,header small{color:#526c78}.actions,nav,.back,footer{display:none}.layout{display:block;padding:0;margin:15px 0}section{padding:0;border:0;border-radius:0;break-before:page;margin:0}h2{font-size:20pt}h3{font-size:13pt}table{font-size:9pt}aside,table,.wiring{break-inside:avoid}a{color:inherit}}'''
    css += '\nbody{overflow-wrap:anywhere}main{min-width:0}'
    result=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(data['title'])} · 使用说明</title><style>{css}</style></head><body><header id="top"><small>SHADOW PLAY / OPERATOR GUIDE / {data['date']}</small><h1>{e(data['title'])}</h1><p>{e(data['subtitle'])}</p><div class="actions"><a href="#record">我想手演一遍并录制</a><a href="#poses">我想逐步录入姿势</a><a href="../../output/pdf/bus_servo_user_guide.pdf">打开10页打印版PDF</a></div></header><div class="layout"><nav aria-label="手册目录">{nav}</nav><main>{pages}</main></div><footer>根据本项目上位机实际按钮与功能编写 · {data['date']} · {e(data["deployment_footer"])}</footer></body></html>'''
    HTML.write_text(result,encoding='utf-8',newline='\n')


def render_pdf(data, font_dir):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
    pdfmetrics.registerFont(TTFont('Guide',str(font_dir/'msyh.ttc'),subfontIndex=0))
    pdfmetrics.registerFont(TTFont('GuideBold',str(font_dir/'msyhbd.ttc'),subfontIndex=0))
    pdfmetrics.registerFontFamily('Guide',normal='Guide',bold='GuideBold',italic='Guide',boldItalic='GuideBold')
    ink, teal, muted, line = [colors.HexColor(s) for s in ('#233443','#216f79','#526c78','#d6e1e6')]
    style=ParagraphStyle('Body',fontName='Guide',fontSize=10.2,leading=16,textColor=ink,wordWrap='CJK',spaceAfter=9,alignment=TA_LEFT)
    styles={
        'body':style,
        'title':ParagraphStyle('Title',parent=style,fontName='GuideBold',fontSize=22,leading=30,spaceAfter=10),
        'lead':ParagraphStyle('Lead',parent=style,fontSize=10.4,leading=17,textColor=muted,spaceAfter=16),
        'heading':ParagraphStyle('Heading',parent=style,fontName='GuideBold',fontSize=12,leading=18,textColor=teal,spaceBefore=7,spaceAfter=7,keepWithNext=True),
        'cell':ParagraphStyle('Cell',parent=style,fontSize=9,leading=14,spaceAfter=0),
        'note':ParagraphStyle('Note',parent=style,fontSize=9.5,leading=15,spaceAfter=0),
        'number':ParagraphStyle('Number',parent=style,fontName='GuideBold',fontSize=11,textColor=teal,spaceAfter=0),
    }
    width=A4[0]-88
    def p(text,key='body'):return Paragraph(html.escape(text),styles[key])
    class Wiring(Flowable):
        def __init__(self):super().__init__();self.width=width;self.height=102
        def draw(self):
            c=self.canv
            for y,port,group,ids in [(71,'原9口 · E14','人物信号总线','ID 1 / 2 / 3 / 4 / 5 / 6'),(36,'原10口 · E15','老虎信号总线','ID 7 / 8 / 9 / 10')]:
                c.setFillColor(teal);c.roundRect(0,y-10,108,27,4,fill=1,stroke=0)
                c.setFont('GuideBold',10);c.setFillColor(colors.white);c.drawCentredString(54,y-1,port)
                c.setStrokeColor(teal);c.line(119,y,224,y);c.setFillColor(muted);c.setFont('Guide',9);c.drawCentredString(172,y+5,group)
                c.setFillColor(ink);c.setFont('GuideBold',10);c.drawString(238,y-1,ids)
            c.setFont('Guide',9);c.setFillColor(muted);c.drawString(0,5,'两组信号互不相通；舵机外接供电，地与控制板共地。')
    story=[]
    for i,page in enumerate(data['pages'],1):
        if i>1:story.append(PageBreak())
        story += [p(f'{i:02d}  {page["title"]}','title'),p(page['lead'],'lead')]
        for b in page['blocks']:
            kind=b['type']
            if kind=='wiring':story.append(Wiring())
            elif kind=='p':story.append(p(b['text']))
            elif kind=='heading':story.append(p(b['text'],'heading'))
            elif kind=='notice':
                content=[Paragraph('<b>'+html.escape(b['title'])+'</b>',styles['note']),Spacer(1,4),p(b['text'],'note')]
                box=Table([[content]],colWidths=[width],style=TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eaf4f4')),('LINEBEFORE',(0,0),(0,-1),3,teal),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
                story += [box,Spacer(1,11)]
            elif kind=='steps':
                for n,t in enumerate(b['items'],1):
                    row=Table([[p(f'{n:02d}','number'),p(t)]],colWidths=[29,width-29],style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
                    story.append(row)
            elif kind=='table':
                rows=[[Paragraph('<b>'+html.escape(t)+'</b>',styles['cell']) for t in b['headers']]]+[[p(t,'cell') for t in row] for row in b['rows']]
                table=Table(rows,colWidths=[width*.29,width*.71],repeatRows=1,style=TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f0f3')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f8fafb')]),('GRID',(0,0),(-1,-1),.5,line),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
                story += [table,Spacer(1,11)]
            else:raise ValueError(kind)
    def decorate(c,doc):
        c.saveState();c.setFillColor(muted);c.setFont('Guide',8)
        c.drawString(44,A4[1]-29,data['title']+' / 操作手册')
        c.drawRightString(A4[0]-44,A4[1]-29,data['date'])
        c.setStrokeColor(line);c.line(44,39,A4[0]-44,39)
        c.drawString(44,25,'人物1至6 → 原9口  |  老虎7至10 → 原10口  |  BS10自启动，联调待完成')
        c.drawRightString(A4[0]-44,25,f'{doc.page} / {len(data["pages"])}')
        if doc.page<=len(data['pages']):
            page=data['pages'][doc.page-1];c.bookmarkPage(page['id']);c.addOutlineEntry(page['title'],page['id'],level=0)
        c.restoreState()
    PDF.parent.mkdir(parents=True,exist_ok=True)
    doc=SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=54,bottomMargin=52,title=data['title']+' - 使用说明',author='皮影项目',pageCompression=1)
    doc.build(story,onFirstPage=decorate,onLaterPages=decorate)
    from pypdf import PdfReader
    reader=PdfReader(PDF)
    if len(reader.pages)!=len(data['pages']):raise ValueError(f'Expected {len(data["pages"])} pages, got {len(reader.pages)}; inspect overflow before delivery')
    for page,source in zip(reader.pages,data['pages']):
        if source['title'] not in page.extract_text():raise ValueError('Page title moved: '+source['title'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font-dir',type=Path,default=Path('C:/Windows/Fonts'))
    args=parser.parse_args()
    data=json.loads(CONTENT.read_text(encoding='utf-8'))
    render_html(data);render_pdf(data,args.font_dir)
    print(json.dumps({'html':str(HTML),'pdf':str(PDF),'pages':len(data['pages'])},ensure_ascii=False))


if __name__=='__main__':main()
