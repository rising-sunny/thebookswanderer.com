import numpy as np, sys
sys.path.insert(0,'.')
from PIL import Image
W,H=345,440
def hexc(h): return np.array([int(h[i:i+2],16) for i in (1,3,5)],float)
STOPS=[hexc(x) for x in ['#0b1d3a','#1f5f8b','#2ea6a0','#e9d8a6','#e6a23c','#c8553d','#7b2d6e','#0b1d3a']]
def pal(t):
    t=t%1.0*(len(STOPS)-1); i=np.minimum(t.astype(int),len(STOPS)-2); f=(t-i)[...,None]
    S=np.array(STOPS); return S[i]*(1-f)+S[i+1]*f
def color(N,T,period=4.0,stripes=True):
    m=N<0; v=np.where(m,0,N)
    rgb=pal(v/period)
    if stripes:
        s=0.82+0.18*np.cos(np.where(m,0,T)*6+v*0.4)
        rgb=rgb*s[...,None]
    rgb[m]=(8,14,30); return rgb
