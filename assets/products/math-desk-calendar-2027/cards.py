import sys, io, glob
sys.path.insert(0, '.')
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib
matplotlib.rcParams['mathtext.fontset'] = 'cm'
SP = Path('.')  # run from a folder that has fonts/EBGaramond.ttf and fonts/EBGaramond-Italic.ttf
NAVY, GOLD, CREAM, DIM, LINE = (14, 26, 52), (201, 162, 74), (243, 236, 221), (150, 160, 185), (60, 78, 120)
def font(size, italic=False, bold=False):
    f = ImageFont.truetype(str(F / ('EBGaramond-Italic.ttf' if italic else 'EBGaramond.ttf')), size)
    try: f.set_variation_by_name('SemiBold' if bold and not italic else 'Regular')
    except Exception: pass
    return f
def mathimg(latex, px, color):
    fig = Figure(figsize=(14, 3), dpi=100); FigureCanvasAgg(fig)
    fig.patch.set_alpha(0); fig.text(0.02, 0.5, latex, fontsize=px * .72, color=[c / 255 for c in color], va='center', family='serif')
    fig.canvas.draw(); a = np.asarray(fig.canvas.buffer_rgba()).copy(); ys, xs = np.where(a[..., 3] > 8)
    return Image.fromarray(a[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
def wrap(d, text, f, width):
    lines, cur = [], ''
    for w in text.split():
        t = (cur + ' ' + w).strip()
        if d.textlength(t, font=f) <= width: cur = t
        else: lines.append(cur); cur = w
    return lines + [cur]
MONTHS = [
 ('I', 'January', 'Julia set', 'Square a number, add c, and repeat. The boundary between the points that stay and those that escape is the Julia set.', [r'$z\mapsto z^{2}+c,\quad c=-0.8+0.156\,i$']),
 ('II', 'February', 'Cardioid', 'Join each point n on a circle to point 2n. The chords draw a heart-shaped curve.', [r'$n\ \mathrm{joins}\ 2n\ (\mathrm{mod}\ 360)$']),
 ('III', 'March', 'Barnsley fern', 'A fern from four simple rules, applied again and again to a single point.', [r'$(x,y)\mapsto A\,(x,y)+b$']),
 ('IV', 'April', 'Phyllotaxis', 'Seeds placed one after another at the golden angle, so spirals appear on their own.', [r'$\theta_n=n\cdot137.5^{\circ},\quad r_n\propto\sqrt{n}$']),
 ('V', 'May', 'Lorenz attractor', 'Three equations, a path that never repeats and never settles: the butterfly effect.', [r'$\sigma=10,\quad\rho=28,\quad\beta=8/3$']),
 ('VI', 'June', 'Harmonograph', 'Two damped pendulums, one drawing a line: the swing fades and the curve folds in.', [r'$x(t)=\sum A_k\sin(f_k t+\varphi_k)$', r'$\mathrm{each\ term\ fades\ as}\ e^{-d_k t}$']),
 ('VII', 'July', 'Seahorse Valley', 'A deep zoom into the edge of the Mandelbrot set, where the same spirals keep returning.', [r'$z\mapsto z^{2}+c$']),
 ('VIII', 'August', 'Newton fractal', 'Newton’s method hunting the five roots of 1. Each colour is the root a starting point ends up at.', [r'$z\mapsto z-\frac{z^{5}-1}{5z^{4}}$']),
 ('IX', 'September', 'Heighway dragon', 'Fold a strip of paper in half again and again, then unfold it. This is what it draws.', [r'$\mathrm{folded\ in\ half\ 13\ times}$']),
 ('X', 'October', 'Clifford attractor', 'One point, moved by two formulas three million times, leaves this trace.', [r'$x^{\prime}=\sin(ay)+c\cos(ax)$', r'$y^{\prime}=\sin(bx)+d\cos(by)$']),
 ('XI', 'November', 'Fractal tree', 'Every branch splits into two smaller copies of itself, ten times over, ending in 1,024 tips.', [r'$\mathrm{angle}\ 26^{\circ},\quad \mathrm{ratio}\ 0.74$']),
 ('XII', 'December', 'Apollonian gasket', 'Circles packed inside circles, each one touching three others.', [r'$k_4=k_1+k_2+k_3$', r'$\qquad\pm\,2\sqrt{k_1k_2+k_2k_3+k_3k_1}$']),
]
W, H = 1862, 1571
def card(i, art):
    num, month, name, cap, forms = MONTHS[i]
    im = Image.new('RGB', (W, H), NAVY); d = ImageDraw.Draw(im)
    d.rectangle([38, 38, W - 39, H - 39], outline=GOLD, width=3); d.rectangle([54, 54, W - 55, H - 55], outline=LINE, width=1)
    A = 1000; ax, ay = 92, 235
    im.paste(art.resize((A, A), Image.LANCZOS), (ax, ay)); d.rectangle([ax - 2, ay - 2, ax + A + 1, ay + A + 1], outline=GOLD, width=3)
    x0 = ax + A + 70; cw = W - 110 - x0
    d.text((x0, 190), num + '.', font=font(150, bold=True), fill=GOLD)
    d.text((x0, 380), month, font=font(104, italic=True), fill=CREAM)
    d.line([x0, 520, x0 + cw, 520], fill=GOLD, width=2)
    d.text((x0, 560), name, font=font(66, bold=True), fill=CREAM)
    y = 660
    for ln in wrap(d, cap, font(48, italic=True), cw): d.text((x0, y), ln, font=font(48, italic=True), fill=DIM); y += 64
    y += 26
    for fm in forms:
        m = mathimg(fm, 62, GOLD)
        if m.width > cw: m = m.resize((cw, int(m.height * cw / m.width)), Image.LANCZOS)
        im.paste(m, (x0, y), m); y += m.height + 22
    d.text((W - 110, H - 130), 'MathRelaxing', font=font(40, italic=True), fill=GOLD, anchor='ra')
    d.text((ax, ay + A + 40), 'Plate ' + num + ' of XII  ·  every image is computed from its equation', font=font(34, italic=True), fill=DIM)
    return im
def cover(arts):
    Wc = 3075; im = Image.new('RGB', (Wc, H), NAVY); d = ImageDraw.Draw(im)
    d.rectangle([40, 40, Wc - 41, H - 41], outline=GOLD, width=4); d.rectangle([58, 58, Wc - 59, H - 59], outline=LINE, width=1)
    d.text((170, 200), 'DESK CALENDAR', font=font(54, bold=True), fill=GOLD)
    d.text((170, 290), '2027', font=font(330, bold=True), fill=GOLD)
    d.text((170, 660), 'A Year of', font=font(150, bold=True), fill=CREAM); d.text((170, 830), 'Mathematical Art', font=font(150, bold=True), fill=CREAM)
    d.line([170, 1050, 1250, 1050], fill=GOLD, width=3)
    for k, t in enumerate(['twelve fractals, attractors and curves,', 'each one computed from real mathematics']): d.text((170, 1090 + k * 70), t, font=font(58, italic=True), fill=DIM)
    d.text((170, 1400), 'MathRelaxing', font=font(60, italic=True), fill=GOLD)
    th, gap, x0, y0 = 330, 22, 1560, 170
    for k, a in enumerate(arts):
        r, c = divmod(k, 4); x, y = x0 + c * (th + gap), y0 + r * (th + gap)
        im.paste(a.resize((th, th), Image.LANCZOS), (x, y)); d.rectangle([x - 1, y - 1, x + th, y + th], outline=GOLD, width=2)
    return im
if __name__ == '__main__':
    out = Path('cards'); out.mkdir(exist_ok=True)
    arts = [Image.open(p).convert('RGB') for p in sorted(glob.glob('art/*.png'))]
    for i, a in enumerate(arts): card(i, a).save(out / f'month_{i + 1:02d}.png')
    cover(arts).save(out / 'cover.png'); print('ok', len(arts))
