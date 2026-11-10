import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle
SP = "."  # run from a folder that has fonts/EBGaramond.ttf and fonts/EBGaramond-Italic.ttf
for f in ("EBGaramond.ttf", "EBGaramond-Italic.ttf"):
    fm.fontManager.addfont(f"{SP}/fonts/{f}")
plt.rcParams["mathtext.fontset"] = "cm"
NAVY, GOLD, CREAM, DIM = "#0e1a34", "#c9a24a", "#f3ecdd", "#8f9bb5"
W, Hh = 32.0, 16.76          # inches; at 310 dpi = 9920 x 5196 px (print area 9921 x 5197)
dpi = int(sys.argv[1]) if len(sys.argv) > 1 else 80
out = sys.argv[2] if len(sys.argv) > 2 else f"{SP}/deskmat/preview.png"
fig = plt.figure(figsize=(W, Hh), dpi=dpi, facecolor=NAVY)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, Hh); ax.axis("off")
m = 1.1                       # safe margin (hemmed edge)
ax.add_patch(Rectangle((m * 0.55, m * 0.55), W - m * 1.1, Hh - m * 1.1, fill=False, ec=GOLD, lw=2.2 * dpi / 80))
ax.add_patch(Rectangle((m * 0.75, m * 0.75), W - m * 1.5, Hh - m * 1.5, fill=False, ec="#2a3a63", lw=1.0 * dpi / 80))
ax.text(W / 2, Hh - 2.0, "THE FORMULA SHEET", ha="center", va="center", color=GOLD, fontsize=44, family="EB Garamond", )
ax.text(W / 2, Hh - 3.15, "twelve equations that explain a lot of the world", ha="center", va="center", color=DIM, fontsize=26, family="EB Garamond", style="italic")
cells = [
 ("EULER'S IDENTITY", [r"$e^{i\pi}+1=0$"], 74),
 ("MAXWELL'S EQUATIONS", [r"$\nabla\cdot\mathbf{E}=\rho/\varepsilon_0$", r"$\nabla\cdot\mathbf{B}=0$", r"$\nabla\times\mathbf{E}=-\partial\mathbf{B}/\partial t$", r"$\nabla\times\mathbf{B}=\mu_0\mathbf{J}+\mu_0\varepsilon_0\,\partial\mathbf{E}/\partial t$"], 26),
 ("FOURIER SERIES", [r"$f(x)=\frac{a_0}{2}+\sum_{n=1}^{\infty}\left(a_n\cos nx+b_n\sin nx\right)$"], 30),
 ("SCHRÖDINGER EQUATION", [r"$i\hbar\,\frac{\partial\psi}{\partial t}=\hat{H}\psi$"], 58),
 ("NAVIER–STOKES (INCOMPRESSIBLE)", [r"$\rho\left(\frac{\partial\mathbf{u}}{\partial t}+\mathbf{u}\cdot\nabla\mathbf{u}\right)=-\nabla p+\mu\nabla^{2}\mathbf{u}+\mathbf{f}$", r"$\nabla\cdot\mathbf{u}=0$"], 25),
 ("WAVE EQUATION", [r"$\frac{\partial^{2}u}{\partial t^{2}}=c^{2}\nabla^{2}u$"], 58),
 ("GAUSSIAN INTEGRAL", [r"$\int_{-\infty}^{\infty}e^{-x^{2}}\,dx=\sqrt{\pi}$"], 44),
 ("DIRAC EQUATION", [r"$\left(i\gamma^{\mu}\partial_{\mu}-m\right)\psi=0$"], 54),
 ("BASEL PROBLEM", [r"$\sum_{n=1}^{\infty}\frac{1}{n^{2}}=\frac{\pi^{2}}{6}$"], 46),
 ("MANDELBROT ITERATION", [r"$z_{n+1}=z_{n}^{2}+c$"], 66),
 ("NORMAL DISTRIBUTION", [r"$f(x)=\frac{1}{\sigma\sqrt{2\pi}}\,e^{-\frac{(x-\mu)^{2}}{2\sigma^{2}}}$"], 52),
 ("QUADRATIC FORMULA", [r"$x=\frac{-b\pm\sqrt{b^{2}-4ac}}{2a}$"], 56),
]
cols, rows = 4, 3
x0, x1, y0, y1 = m + 0.9, W - m - 0.9, m + 1.0, Hh - 3.7
cw, ch = (x1 - x0) / cols, (y1 - y0) / rows
for i, (cap, lines, fs) in enumerate(cells):
    r, c = divmod(i, cols)
    cx, top = x0 + c * cw + cw / 2, y1 - r * ch
    ax.plot([x0 + c * cw + 0.5, x0 + (c + 1) * cw - 0.5], [top - 0.5, top - 0.5], color=GOLD, lw=1.4 * dpi / 80, alpha=0.7)
    ax.text(cx, top - 1.05, cap, ha="center", va="center", color=GOLD, fontsize=19, family="EB Garamond", )
    n = len(lines)
    cy = top - 1.5 - (ch - 1.5) / 2
    step = 0.62 if n > 2 else 0.8
    for k, ln in enumerate(lines):
        ax.text(cx, cy - (k - (n - 1) / 2) * step, ln, ha="center", va="center", color=CREAM, fontsize=fs)
ax.text(W - m - 0.9, m + 0.55, "MathRelaxing", ha="right", va="center", color=GOLD, fontsize=22, family="EB Garamond", style="italic")
fig.savefig(out, dpi=dpi, facecolor=NAVY)
print(out)
