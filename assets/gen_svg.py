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
ASCII_FONT = 18      # art font-size px
ASCII_CW   = 10.8    # px advance per art char (= ASCII_FONT*0.6)
ASCII_DY   = 18      # art line height (= ASCII_CW/0.6 keeps the Celebi at correct scale)
ASCII_COLS = 50      # art grid width in chars
ASCII_ROWS = 26      # art grid height in rows
PANEL_FONT = 20      # panel font-size px (larger than the art)
PANEL_CW   = 12      # px advance per panel char (= PANEL_FONT*0.6)
PANEL_DY   = 21      # panel line height (smaller ratio => more compact)
PANEL_LINES= 24      # number of panel rows
Y0         = 30      # panel top baseline
GAP        = 16      # px gap between art and panel
R          = 53      # panel values right-align to this column (chars); lower => tighter panel
PANEL_X    = ASCII_X + round(ASCII_COLS*ASCII_CW) + GAP
WIDTH      = PANEL_X + round(R*PANEL_CW) + 34
# vertically center the art beside the panel
ASCII_Y0   = Y0 + round(((PANEL_LINES-1)*PANEL_DY - (ASCII_ROWS-1)*ASCII_DY)/2)
HEIGHT     = max(Y0 + (PANEL_LINES-1)*PANEL_DY, ASCII_Y0 + (ASCII_ROWS-1)*ASCII_DY) + 26

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

# GitHub-Stats field widths. Each number is right-justified to (label_end + LEN + 2),
# giving fixed columns so the 2-column grid stays aligned at any digit count.
# MUST match the justify_format lengths in today.py's svg_overwrite().
STAT_LEN = {'repo':3,'contrib':3,'star':13,'commit':17,'follower':9,
            'loc':11,'loc_add':8,'loc_del':6}

def stat_leader(length, value='0'):
    jl=max(0, length-len(value))
    if jl>2: return ' '+'.'*jl+' '
    return {0:'',1:' ',2:'. '}[jl]

def tight_leader(length, value='0'):
    # Placeholder leader whose (leader+value) width == length exactly, matching what
    # today.py produces for real (multi-digit) LOC numbers. Avoids the +2 overshoot
    # stat_leader adds for a 1-char '0', so the committed zero-state ends at the edge too.
    n=max(0, length-len(value))
    if n==0: return ''
    if n==1: return ' '
    return ' '+'.'*(n-2)+' '

def stat_cell(label, vid, dots_id, length, value='0'):
    return (f'<tspan class="key">{label}</tspan>:'
            f'<tspan class="cc" id="{dots_id}">{stat_leader(length,value)}</tspan>'
            f'<tspan class="value" id="{vid}">{value}</tspan>')

SEP='<tspan class="cc"> | </tspan>'

def stats_repos(y):
    # Combined line: "Repos <n> {Contributed: <n>} | Stars <n>".
    return (f'<tspan x="{PANEL_X}" y="{y}" class="cc">. </tspan>'
            '<tspan class="key">Repos</tspan>:'
            f'<tspan class="cc" id="repo_data_dots">{tight_leader(STAT_LEN["repo"])}</tspan>'
            '<tspan class="value" id="repo_data">0</tspan>'
            ' {<tspan class="key">Contributed</tspan>:'
            f'<tspan class="cc" id="contrib_data_dots">{tight_leader(STAT_LEN["contrib"])}</tspan>'
            '<tspan class="value" id="contrib_data">0</tspan>}'
            + SEP +
            '<tspan class="key">Stars</tspan>:'
            f'<tspan class="cc" id="star_data_dots">{stat_leader(STAT_LEN["star"])}</tspan>'
            '<tspan class="value" id="star_data">0</tspan>')

def stats_commits(y):
    return (f'<tspan x="{PANEL_X}" y="{y}" class="cc">. </tspan>'
            + stat_cell('Commits','commit_data','commit_data_dots',STAT_LEN['commit'])
            + SEP + stat_cell('Followers','follower_data','follower_data_dots',STAT_LEN['follower']))

def stats_loc(y):
    # total right-justifies so "(" lands under the "|"; deletions so ")" hits the edge.
    return (f'<tspan x="{PANEL_X}" y="{y}" class="cc">. </tspan>'
            '<tspan class="key">Lines of Code</tspan>:'
            f'<tspan class="cc" id="loc_data_dots">{stat_leader(STAT_LEN["loc"])}</tspan>'
            '<tspan class="value" id="loc_data">0</tspan> ('
            f'<tspan class="cc" id="loc_add_dots">{tight_leader(STAT_LEN["loc_add"])}</tspan>'
            '<tspan class="addColor" id="loc_add">0</tspan><tspan class="addColor">++</tspan>, '
            f'<tspan class="cc" id="loc_del_dots">{tight_leader(STAT_LEN["loc_del"])}</tspan>'
            '<tspan class="delColor" id="loc_del">0</tspan><tspan class="delColor">--</tspan> )')

def panel():
    L=[]; y=Y0
    def push(s):
        nonlocal y; L.append(s); y+=PANEL_DY
    push(header(y, 'jamie@kofler'))
    push(field(y, 'OS',     'Arch Linux (btw), Windows, MacOS'))
    push(field(y, 'Uptime', '00 years, 00 months, 00 days', val_id='age_data', dots_id='age_data_dots'))
    push(field(y, 'Host',   'Ratter Studios'))
    push(field(y, 'Kernel', 'Game Programmer, Tech Lead'))
    push(field(y, 'IDE',    'Neovim, Rider, VScode'))
    push(spacer(y))
    push(field(y, 'Languages.Programming', 'C#, C++, Lua, TypeScript, Rust'))
    push(field(y, 'Languages.Computer',    'HTML, CSS, JSON, YAML'))
    push(field(y, 'Languages.Real',        'English, Swedish, German'))
    push(spacer(y))
    push(field(y, 'Hobbies.Software', 'Gaming, RetroTech'))
    push(blank(y))
    push(header(y, '- Contact'))
    push(field(y, 'Email.Personal', 'koflerjamie@gmail.com'))
    push(field(y, 'Website',        'jamiek.cc'))
    push(field(y, 'Addons',         'addons.jamiek.cc'))
    push(field(y, 'LinkedIn',       'jamie-kofler'))
    push(field(y, 'Discord',        'jamie.'))
    push(blank(y))
    push(header(y, '- GitHub Stats'))
    push(stats_repos(y))
    push(stats_commits(y))
    push(stats_loc(y))
    return '\n'.join(L)

def panel_bottom():
    return Y0 + 23*PANEL_DY   # y of the last (24th) panel line

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
        f'width="{WIDTH}px" height="{HEIGHT}px" font-size="{ASCII_FONT}px">\n'
        f'{style_block(pal, ui, bg)}\n'
        f'<rect width="{WIDTH}px" height="{HEIGHT}px" fill="{bg}" rx="15"/>\n'
        f'<text x="{ASCII_X}" y="{ASCII_Y0}" fill="{textfill}" class="ascii">\n{ascii_body}\n</text>\n'
        f'<text x="{PANEL_X}" y="{Y0}" fill="{textfill}" font-size="{PANEL_FONT}px">\n{panel()}\n</text>\n'
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
