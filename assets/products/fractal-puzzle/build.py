import numpy as np, sys
sys.path.insert(0,'.')
from mandel import render
from palette import pal
from PIL import Image
from multiprocessing import Pool
W,H=3450,4395; CX,CY,WID=-0.761151,-0.084989,0.0015
height=WID*H/W
def part(args):
    r0,r1=args
    # render rows r0..r1 using same global grid
    ys=np.linspace(CY-height/2,CY+height/2,H)[r0:r1]
    xs=np.linspace(CX-WID/2,CX+WID/2,W)
    c=xs[None,:]+1j*ys[:,None]
    z=np.zeros_like(c); n=np.full(c.shape,-1.0); th=np.zeros(c.shape); act=np.ones(c.shape,bool)
    for i in range(3000):
        z[act]=z[act]**2+c[act]
        esc=act&(np.abs(z)>1e4)
        if esc.any():
            zz=z[esc]; n[esc]=i+1-np.log2(np.log(np.abs(zz))); th[esc]=np.angle(zz); act&=~esc
        if not act.any(): break
    return r0,n,th
if __name__=='__main__':
    step=55
    jobs=[(r,min(r+step,H)) for r in range(0,H,step)]
    N=np.full((H,W),-1.0,dtype=np.float32); T=np.zeros((H,W),dtype=np.float32)
    with Pool(4) as p:
        for r0,n,th in p.imap_unordered(part,jobs):
            N[r0:r0+n.shape[0]]=n; T[r0:r0+n.shape[0]]=th
    m=N<0; v=np.where(m,0,N).astype(np.float64)
    out=np.zeros((H,W,3),np.uint8)
    for r0 in range(0,H,500):
        sl=slice(r0,r0+500)
        rgb=pal(v[sl]/30.0)
        rgb=rgb*(0.88+0.12*np.cos(np.where(m[sl],0,T[sl])*8))[...,None]
        rgb[m[sl]]=(8,14,30)
        out[sl]=np.clip(rgb,0,255).astype(np.uint8)
    im=Image.fromarray(out); im.save('spiral-puzzle-3450x4395.png',optimize=False)
    im.resize((690,879),Image.LANCZOS).save('preview2.png')
    print('done',m.mean())
