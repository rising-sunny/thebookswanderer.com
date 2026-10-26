"""View of the plinth from below, matte black, lit from a low angle so the engraving reads."""
import numpy as np
from PIL import Image
from engrave import SDF2, PX, SIZE

R_OUT = 41.0
n = SDF2.shape[0]
u = (np.arange(n) + 0.5) / PX - SIZE / 2
X, Y = np.meshgrid(u, -u)
# seen from below the cut reads the right way round, so the flat layout is used as drawn
depth = 0.6 * np.clip(0.5 - SDF2 / 0.12, 0, 1)          # 0 on the face, 0.6 mm in the cut
gy, gx = np.gradient(-depth, 1 / PX)
nrm = np.dstack([-gx, -gy, np.ones_like(gx)]); nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
L = np.array([-0.55, 0.45, 0.7]); L /= np.linalg.norm(L)
diff = np.clip(nrm @ L, 0, 1)
inner = 1 - 0.55 * depth / 0.6                           # the cut sits in its own shadow
H = np.array([0, 0, 1.0]) + L; H /= np.linalg.norm(H)
spec = np.clip(nrm @ H, 0, 1) ** 30 * 0.10
v = (0.06 + 0.11 * diff) * inner + spec
rho = np.hypot(X, Y)
edge = np.clip((R_OUT - rho) * PX / 1.5, 0, 1)
img = np.dstack([v * 1.00, v * 1.00, v * 1.06])
bg = np.array([244, 239, 228]) / 255
img = img * edge[..., None] + bg * (1 - edge[..., None])
Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).resize((900, 900), Image.LANCZOS).save("c-underside.png")
