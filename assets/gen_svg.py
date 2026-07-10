#!/usr/bin/env python3
"""Generate dark_mode.svg + light_mode.svg for GitJamieK profile.
Celebi ASCII colored by sampling Celebi_ascii.png per character cell.
Right panel = fastfetch-style, dynamic stat ids preserved for today.py.
Run from the repo root:  python3 assets/gen_svg.py

TO EDIT PANEL TEXT (labels like "Languages.Programming" or their values):
  see the panel() function below — each line is  field(y, 'Label', 'Value').
TO CHANGE LOOK: tweak the LAYOUT CONFIG constants right below.
"""
from PIL import Image
import numpy as np
from xml.sax.saxutils import escape

PNG   = 'assets/Celebi_ascii.png'
GRID  = 'assets/celebi.txt'
OUTDIR= '.'

# ================= LAYOUT CONFIG (safe to tweak) =================
ASCII_X    = 15
CW         = 9.6     # px advance per monospace char (used only to place the panel)
ASCII_DY   = 16      # art line height. LOWER => Celebi looks WIDER (fixes squish)
ASCII_Y0   = 60      # art top baseline (centers the art beside the panel)
PANEL_DY   = 20      # panel line height
Y0         = 30      # panel top baseline
GAP        = 20      # px gap between art and panel
R          = 60      # panel values right-align to this column (chars); raise = wider panel
ASCII_COLS = 50      # art grid width in chars
PANEL_X    = ASCII_X + round(ASCII_COLS*CW) + GAP
WIDTH      = PANEL_X + round(R*CW) + 40
HEIGHT     = 515

# ---- palettes (display fill per class) ----
DARK = {'body':'#d69cc4','grn':'#5fae4c','mag':'#b25aa8','wht':'#f2f2f2','gry':'#797f8a'}
LIGHT= {'body':'#b0568f','grn':'#2f8f2f','mag':'#8a2d80','wht':'#57606a','gry':'#9aa0ab'}

# ================= ASCII sampling =================
def load_grid():
    lines = open(GRID).read().split('\n')
    while lines and lines[-1].strip()=='':
        lines.pop()
    W = max(len(l) for l in lines)
    return [l.ljust(W) for l in lines], W

def classify(r,g,b):
    """Classify a sampled char color by saturation + hue, not nearest-RGB:
    light pink body has chroma, white eyes don't."""
    mx=max(r,g,b); mn=min(r,g,b); chroma=mx-mn; br=(r+g+b)/3
    if g>=r and g>=b and g-min(r,b) > 20: return 'grn'   # green markings
    if chroma < 28:                                       # neutral
        return 'wht' if br>=180 else 'gry'
    if chroma >= 70 and br < 195: return 'mag'            # deep tail magenta
    return 'body'                                         # light pink mass

def sample_classes(grid, W):
    H=len(grid)
    rows=[r for r in range(H) if grid[r].strip()!='']
    cols=[c for c in range(W) if any(grid[r][c]!=' ' for r in range(H))]
    gr0,gr1=min(rows),max(rows); gc0,gc1=min(cols),max(cols)
    im=Image.open(PNG).convert('RGBA'); arr=np.asarray(im).astype(int)
    a=arr[:,:,:3]; alpha=arr[:,:,2+1]        # RGB + alpha; opaque = char pixels
    ys,xs=np.where(alpha>40)                  # alpha-masked bbox (bg is transparent)
    py0,py1,px0,px1=ys.min(),ys.max(),xs.min(),xs.max()
    cw=(px1-px0+1)/(gc1-gc0+1); ch=(py1-py0+1)/(gr1-gr0+1)
    cls={}
    for r in range(H):
        for c in range(W):
            if grid[r][c]==' ': continue
            cx=int(px0+(c-gc0+0.5)*cw); cy=int(py0+(r-gr0+0.5)*ch)
            x0=max(0,cx-int(cw/3)); x1=min(a.shape[1],cx+int(cw/3)+1)
            y0=max(0,cy-int(ch/3)); y1=min(a.shape[0],cy+int(ch/3)+1)
            win=a[y0:y1,x0:x1].reshape(-1,3)
            aw=alpha[y0:y1,x0:x1].reshape(-1)
            sel=win[aw>40]                     # only opaque (char stroke) pixels
            if len(sel)==0: continue
            m=sel.mean(0)
            cls[(r,c)]=classify(int(m[0]),int(m[1]),int(m[2]))
    return cls

def ascii_tspans(grid, W, cls):
    out=[]
    for r,row in enumerate(grid):
        y=ASCII_Y0+r*ASCII_DY
        segs=[]; cur=None; buf=''
        for c in range(W):
            ch=row[c]
            if ch==' ':
                if cur is None: cur='body'
                buf+=' '; continue
            k=cls.get((r,c),'body')
            if k==cur: buf+=ch
            else:
                if buf: segs.append((cur,buf))
                cur=k; buf=ch
        if buf: segs.append((cur,buf))
        if not segs: segs=[('body',' '*W)]
        parts=[]
        for i,(k,t) in enumerate(segs):
            e=escape(t)
            if i==0: parts.append(f'<tspan class="{k}" x="{ASCII_X}" y="{y}">{e}</tspan>')
            else:    parts.append(f'<tspan class="{k}">{e}</tspan>')
        out.append(''.join(parts))
    return '\n'.join(out)

# ================= right panel =================
def key_markup(key):
    # split on '.' so "Languages.Programming" -> two key tspans with literal dot
    parts=key.split('.')
    return '.'.join(f'<tspan class="key">{p}</tspan>' for p in parts)

def line_start(x,y):
    return f'<tspan x="{PANEL_X}" y="{y}" class="cc">. </tspan>'

def field(y, key, value, val_id=None, dots_id=None):
    # right-align value to column R with a dotted leader (fastfetch style)
    ndots=max(1, R - (len(key)+3) - len(value) - 2)
    dots=' '+'.'*ndots+' '
    di=f' id="{dots_id}"' if dots_id else ''
    vi=f' id="{val_id}"' if val_id else ''
    return (f'<tspan x="{PANEL_X}" y="{y}" class="cc">. </tspan>'
            f'{key_markup(key)}:'
            f'<tspan class="cc"{di}>{dots}</tspan>'
            f'<tspan class="value"{vi}>{escape(value)}</tspan>')

def spacer(y):
    return f'<tspan x="{PANEL_X}" y="{y}" class="cc">. </tspan>'

def header(y, title):
    dash=max(1, R - len(title) - 1)
    return f'<tspan x="{PANEL_X}" y="{y}">{escape(title)}</tspan> {"—"*dash}'

def blank(y):
    return f'<tspan x="{PANEL_X}" y="{y}"> </tspan>'

def panel():
    L=[]
    L.append(header(Y0, 'jamie@kofler'))
    L.append(field(50,  'OS',     'Arch Linux (btw), Windows'))
    L.append(field(70,  'Uptime', '00 years, 00 months, 00 days', val_id='age_data', dots_id='age_data_dots'))
    L.append(field(90,  'Host',   'Ratter Studios'))
    L.append(field(110, 'Kernel', 'Game Programmer'))
    L.append(field(130, 'IDE',    'Neovim, Rider'))
    L.append(spacer(150))
    L.append(field(170, 'Languages.Programming', 'C#, C++, Lua, JavaScript'))
    L.append(field(190, 'Languages.Computer',    'HTML, CSS, JSON, YAML'))
    L.append(field(210, 'Languages.Real',        'English, Swedish, German'))
    L.append(spacer(230))
    L.append(field(250, 'Hobbies.Software', 'WoW Addon Dev, Game Jams'))
    L.append(blank(270))
    L.append(header(290, '- Contact'))
    L.append(field(310, 'Email.Personal', 'koflerjamie@gmail.com'))
    L.append(field(330, 'Website',        'jamiek.cc'))
    L.append(field(350, 'Addons',         'addons.jamiek.cc'))
    L.append(field(370, 'LinkedIn',       'jamie-kofler'))
    L.append(field(390, 'Discord',        'jamie.'))
    L.append(blank(410))
    L.append(header(430, '- GitHub Stats'))
    # dynamic stat lines: ids must match today.py
    L.append(f'<tspan x="{PANEL_X}" y="450" class="cc">. </tspan>'
             '<tspan class="key">Repos</tspan>:<tspan class="cc" id="repo_data_dots"> .... </tspan>'
             '<tspan class="value" id="repo_data">0</tspan> {<tspan class="key">Contributed</tspan>: '
             '<tspan class="value" id="contrib_data">0</tspan>} | <tspan class="key">Stars</tspan>:'
             '<tspan class="cc" id="star_data_dots"> ........... </tspan><tspan class="value" id="star_data">0</tspan>')
    L.append(f'<tspan x="{PANEL_X}" y="470" class="cc">. </tspan>'
             '<tspan class="key">Commits</tspan>:<tspan class="cc" id="commit_data_dots"> ................. </tspan>'
             '<tspan class="value" id="commit_data">0</tspan> | <tspan class="key">Followers</tspan>:'
             '<tspan class="cc" id="follower_data_dots"> ....... </tspan><tspan class="value" id="follower_data">0</tspan>')
    L.append(f'<tspan x="{PANEL_X}" y="490" class="cc">. </tspan>'
             '<tspan class="key">Lines of Code on GitHub</tspan>:<tspan class="cc" id="loc_data_dots">. </tspan>'
             '<tspan class="value" id="loc_data">0</tspan> ( <tspan class="addColor" id="loc_add">0</tspan>'
             '<tspan class="addColor">++</tspan>, <tspan id="loc_del_dots"> </tspan>'
             '<tspan class="delColor" id="loc_del">0</tspan><tspan class="delColor">--</tspan> )')
    return '\n'.join(L)

# ================= assemble =================
def style_block(pal, ascii_fill, bg_note):
    return f'''<style>
@font-face {{
src: local('Consolas'), local('Consolas Bold');
font-family: 'ConsolasFallback';
font-display: swap;
-webkit-size-adjust: 109%;
size-adjust: 109%;
}}
.key {{fill: {ascii_fill['key']};}}
.value {{fill: {ascii_fill['value']};}}
.addColor {{fill: {ascii_fill['add']};}}
.delColor {{fill: {ascii_fill['del']};}}
.cc {{fill: {ascii_fill['cc']};}}
.body {{fill: {pal['body']};}}
.grn {{fill: {pal['grn']};}}
.mag {{fill: {pal['mag']};}}
.wht {{fill: {pal['wht']};}}
.gry {{fill: {pal['gry']};}}
text, tspan {{white-space: pre;}}
</style>'''

DARK_UI ={'key':'#ffa657','value':'#a5d6ff','add':'#3fb950','del':'#f85149','cc':'#616e7f'}
LIGHT_UI={'key':'#953800','value':'#0a3069','add':'#1a7f37','del':'#cf222e','cc':'#c2cfde'}

def build(pal, ui, bg, textfill, ascii_body):
    return (f"<?xml version='1.0' encoding='UTF-8'?>\n"
        f'<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,monospace" '
        f'width="{WIDTH}px" height="{HEIGHT}px" font-size="16px">\n'
        f'{style_block(pal, ui, bg)}\n'
        f'<rect width="{WIDTH}px" height="{HEIGHT}px" fill="{bg}" rx="15"/>\n'
        f'<text x="{ASCII_X}" y="{ASCII_Y0}" fill="{textfill}" class="ascii">\n{ascii_body}\n</text>\n'
        f'<text x="{PANEL_X}" y="{Y0}" fill="{textfill}">\n{panel()}\n</text>\n'
        f'</svg>\n')

def main():
    grid,W=load_grid()
    cls=sample_classes(grid,W)
    body=ascii_tspans(grid,W,cls)
    dark =build(DARK , DARK_UI , '#161b22','#c9d1d9', body)
    light=build(LIGHT, LIGHT_UI, '#f6f8fa','#24292f', body)
    open(f'{OUTDIR}/dark_mode.svg','w').write(dark)
    open(f'{OUTDIR}/light_mode.svg','w').write(light)
    # stats
    from collections import Counter
    print('classes:',Counter(cls.values()))
    print('grid',W,'x',len(grid),'wrote dark_mode.svg + light_mode.svg')

if __name__=='__main__':
    main()
