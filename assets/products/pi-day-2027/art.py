import math, sys, numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, '.')
from pidigits import pi_digits
SP = Path('/tmp/claude-0/-home-user/661d7c00-130c-5805-82d8-1f86fe22eb52/scratchpad'); FONT = SP/'fonts'/'EBGaramond.ttf'
W, H = 4500, 5400
def hexc(h): return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))
# ten colours, one per digit, in the shop's navy/gold/teal family
PAL = [hexc(x) for x in ['#e9d8a6', '#2ea6a0', '#e6a23c', '#c8553d', '#7b6dc8', '#58b6e8', '#e8789a', '#8fcf8f', '#f2c14e', '#d9d9d9']]

def spiral(digits=3000):
    ds = pi_digits(digits)
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    f = ImageFont.truetype(str(FONT), 66)
    cx, cy = W/2, 2500
    pitch = 78.0          # distance between turns
    step = 70.0           # arc length between digits
    b = pitch / (2*math.pi); theta = 4.2; a = 0.0
    r_max = 2230
    i = 0
    while i < len(ds):
        r = b * theta
        if r > r_max: break
        x = cx + r*math.cos(theta); y = cy + r*math.sin(theta)
        ch = ds[i]
        col = PAL[int(ch)]
        # digits sit upright; slightly dimmer towards the rim keeps the eye in the middle
        fade = 1.0 - 0.28 * (r / r_max)
        d.text((x, y), ch, font=f, fill=col + (int(255*fade),), anchor='mm')
        # advance by constant arc length: ds = sqrt(r^2 + b^2) dtheta
        theta += step / math.sqrt(r*r + b*b); i += 1
    # big pi in the centre
    big = ImageFont.truetype(str(FONT), 330)
    d.text((cx, cy), 'π', font=big, fill=(233, 216, 166, 255), anchor='mm')
    cap = ImageFont.truetype(str(SP/'fonts'/'EBGaramond-Italic.ttf'), 120)
    d.text((W/2, 5080), '3.14159265358979…  ·  every digit computed', font=cap, fill=(233, 216, 166, 235), anchor='mm')
    return im, i

def walk(digits=9000):
    ds = pi_digits(digits)[1:]    # digits after the decimal point
    pts = [(0.0, 0.0)]; x = y = 0.0
    for ch in ds:
        ang = int(ch) * math.tau / 10
        x += math.cos(ang); y += math.sin(ang); pts.append((x, y))
    P = np.array(pts); mn, mx = P.min(0), P.max(0); span = mx - mn
    scale = min((W - 500) / span[0], (4600 - 300) / span[1])
    P = (P - mn) * scale
    P[:, 0] += (W - P[:, 0].max()) / 2; P[:, 1] += 250 + (4300 - P[:, 1].max()) / 2
    k = 2  # supersample for smooth lines
    big = Image.new('RGBA', (W*k//2, H*k//2), (0, 0, 0, 0))
    bd = ImageDraw.Draw(big)
    n = len(P)
    stops = [hexc(c) for c in ['#2ea6a0', '#58b6e8', '#7b6dc8', '#e8789a', '#e6a23c', '#e9d8a6']]
    for i in range(n - 1):
        t = i / (n - 1) * (len(stops) - 1); j = min(int(t), len(stops) - 2); f = t - j
        col = tuple(int(stops[j][c]*(1-f) + stops[j+1][c]*f) for c in range(3))
        bd.line([tuple(P[i]*k/2), tuple(P[i+1]*k/2)], fill=col + (255,), width=5)
    im = big.resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    cap = ImageFont.truetype(str(SP/'fonts'/'EBGaramond-Italic.ttf'), 120)
    d.text((W/2, 5080), 'π  ·  a walk along its first 9,000 digits', font=cap, fill=(233, 216, 166, 235), anchor='mm')
    return im

if __name__ == '__main__':
    a, n = spiral(); print('spiral digits placed:', n)
    a.save('pi_spiral.png')
    b = walk(); b.save('pi_walk.png')
    navy = (16, 36, 54, 255)
    for name in ('pi_spiral', 'pi_walk'):
        im = Image.open(f'{name}.png'); bg = Image.new('RGBA', im.size, navy); bg.alpha_composite(im)
        bg.convert('RGB').resize((750, 900), Image.LANCZOS).save(f'{name}_prev.jpg', quality=90)
    s = Image.new('RGB', (1500, 900)); s.paste(Image.open('pi_spiral_prev.jpg'), (0, 0)); s.paste(Image.open('pi_walk_prev.jpg'), (750, 0)); s.save('both.jpg', quality=90)


def spiral_apparel(out='pi-day-spiral-apparel-4500x5100.png'):
    """Bolder spiral for garments: ~1,100 larger, brighter digits that read from across a room."""
    ds = pi_digits(1500)
    im = Image.new('RGBA', (4500, 5100), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    f = ImageFont.truetype(str(FONT), 118)
    try: f.set_variation_by_name('SemiBold')
    except Exception: pass
    cx, cy = 2250, 2300
    pitch, step, r_max = 140.0, 112.0, 2080
    b = pitch / (2*math.pi); theta = 3.2; i = 0
    while i < len(ds):
        r = b * theta
        if r > r_max: break
        x = cx + r*math.cos(theta); y = cy + r*math.sin(theta)
        col = PAL[int(ds[i])]
        d.text((x, y), ds[i], font=f, fill=col + (255,), anchor='mm')
        theta += step / math.sqrt(r*r + b*b); i += 1
    big = ImageFont.truetype(str(FONT), 420)
    d.text((cx, cy), 'π', font=big, fill=(233, 216, 166, 255), anchor='mm')
    cap = ImageFont.truetype(str(SP/'fonts'/'EBGaramond-Italic.ttf'), 150)
    d.text((2250, 4720), '3.14159265358979…  ·  every digit computed', font=cap, fill=(233, 216, 166, 255), anchor='mm')
    im.save(out, optimize=True)
    return i
