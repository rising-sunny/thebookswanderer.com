import numpy as np
def render(W,H,cx,cy,width,maxit=1500,chunk=64):
    height=width*H/W
    xs=np.linspace(cx-width/2,cx+width/2,W); ys=np.linspace(cy-height/2,cy+height/2,H)
    N=np.full((H,W),-1.0); T=np.zeros((H,W))
    for r0 in range(0,H,chunk):
        y=ys[r0:r0+chunk][:,None]; c=(xs[None,:]+1j*y)
        z=np.zeros_like(c); n=np.full(c.shape,-1.0); th=np.zeros(c.shape); act=np.ones(c.shape,bool)
        for i in range(maxit):
            z[act]=z[act]**2+c[act]
            esc=act&(np.abs(z)>1e4)
            if esc.any():
                zz=z[esc]; n[esc]=i+1-np.log2(np.log(np.abs(zz))); th[esc]=np.angle(zz); act&=~esc
            if not act.any(): break
        N[r0:r0+chunk]=n; T[r0:r0+chunk]=th
    return N,T
