import io, json, math, os, random
from PIL import Image

BLOCKS = ('conquest:tudor_cross_frame_vertical_quarter', 'conquest:tudor_cross_frame_vertical_corner', 'conquest:tudor_cross_frame_vertical_slab')


def generate(ROOT, out, lang, cutout, tab):
    BB = os.path.join(ROOT, 'src', 'control_panel') + os.sep
    files = {}

    def png(im):
        b = io.BytesIO()
        im.save(b, 'PNG')
        return b.getvalue()

    def js(o):
        return json.dumps(o, indent=2).encode()

    # plating: 8x8 repeat tiles from mossy_sandstone, recolored
    T="assets/minecraft/optifine/ctm/circinus/mossy_sandstone/"
    C="assets/minecraft/optifine/ctm/circinus/control_panel_plating/"
    CD="assets/minecraft/optifine/ctm/circinus/control_panel_plating_dark/"
    tiles={}
    for sfx in ("","_n","_s"):
        for ty in range(8):
            for tx in range(8):
                tiles[(tx,ty,sfx)]=Image.open(os.path.join(ROOT,f"{T}{1+ty*16+tx}{sfx}.png")).convert("RGBA")
    n=0; m=[0,0,0]
    for ty in range(8):
        for tx in range(8):
            for p in tiles[(tx,ty,"")].getdata():
                for c in range(3): m[c]+=p[c]
                n+=1
    m=[v/n for v in m]; tgt=(0,112,113)
    orig_tiles={k:v.copy() for k,v in tiles.items()}
    for (tx,ty,sfx),im in list(tiles.items()):
        if sfx=="":
            px=im.load()
            for y in range(32):
                for x in range(32):
                    p=px[x,y]; l=(p[0]/max(m[0],1)+p[1]/m[1]+p[2]/m[2])/3; l=1+(l-1)*0.45
                    px[x,y]=tuple(min(255,round(t*l)) for t in tgt)+(255,)
        files[f"{C}{1+ty*8+tx}{sfx}.png"]=png(im)
        if tx==0 and ty==0: files[f"assets/circinus/textures/block/control_panel/plating{sfx}.png"]=png(im)
        dk=im if sfx!="" else Image.eval(im.convert("RGB"),lambda v:round(v*0.5)).convert("RGBA")
        files[f"{CD}{1+ty*8+tx}{sfx}.png"]=png(dk)
        if tx==0 and ty==0: files[f"assets/circinus/textures/block/control_panel/plating_dark{sfx}.png"]=png(dk)
    files[CD+"control_panel_plating_dark.properties"]=b"method=repeat\nwidth=8\nheight=8\ntiles=1-64\nmatchTiles=circinus:textures/block/control_panel/plating_dark\n"
    files[C+"control_panel_plating.properties"]=b"method=repeat\nwidth=8\nheight=8\ntiles=1-64\nmatchTiles=circinus:textures/block/control_panel/plating\n"
    # screens (animated)
    import random
    FRAMEC=((26,25,50),(27,27,27),(19,19,19),(39,39,39),(0,0,0))
    def lamps(im):
        W,Hh=im.size; px=im.load(); out=[]
        for y in range(Hh):
            for x in range(W):
                if px[x,y][3]==0: continue
                if all(not(0<=x+dx<W and 0<=y+dy<Hh) or px[x+dx,y+dy][3]==0 for dx in(-1,0,1) for dy in(-1,0,1) if dx or dy): out.append((x,y))
        return out
    def screen_frames(i,im):
        rnd=random.Random(i*7919)
        base=im.copy(); px=base.load()
        N,ft={1:(276,3),2:(24,4),3:(24,4),4:(32,2),5:(24,4),6:(24,4),7:(24,4)}[i]
        if i==1: px[18,10]=(255,255,255,255)
        frames=[]; offmasks=[]
        L=lamps(im); rnd.shuffle(L); blink=L[:max(1,round(len(L)/2))] if L else []
        seqs={}
        halves=[h for h in (2,3,4,6,12) if N%(2*h)==0]
        rnd.shuffle(halves)
        for k,p in enumerate(blink):
            h=halves[k%len(halves)]; ph=rnd.randrange(2*h)
            seqs[p]=[((f+ph)//h)%2==0 for f in range(N)]
        for f in range(N):
            fr=base.copy(); fp=fr.load(); off=set()
            if i==1:
                for y in range(10,25):
                    row=[px[x,y] for x in range(2,25)]
                    for k,x in enumerate(range(2,25)): fp[x,y]=row[(k+f)%len(row)]
            if i==4:
                cx,cy=15,16; th=math.pi+f*2*math.pi/N
                trail=[(39,39,39,255),(27,27,27,255),(19,19,19,255)]
                mask=[]
                for y in range(32):
                    for x in range(32):
                        c=px[x,y]
                        if c[:3] in ((0,0,0),(199,207,221),(39,39,39),(27,27,27),(19,19,19),(0,152,220)) and math.hypot(x-cx,y-cy)<=8.6: mask.append((x,y))
                ms=set(mask)
                for x,y in mask:
                    if px[x,y][:3]!=(0,152,220): fp[x,y]=(0,0,0,255)
                    dx,dy=x-cx,y-cy
                    if dx==0 and dy==0: continue
                    d=(th-math.atan2(dy,dx))%(2*math.pi)
                    band=int((d-math.radians(4))/math.radians(9)) if d>math.radians(4) else -1
                    if 0<=band<len(trail) and px[x,y][:3]!=(0,152,220): fp[x,y]=trail[band]
                t=0.0
                while t<=9.5:
                    q=(round(cx+t*math.cos(th)),round(cy+t*math.sin(th)))
                    if q in ms or q==(cx,cy): fp[q]=(199,207,221,255)
                    t+=0.1
            for p,seq in seqs.items():
                if not seq[f]:
                    c=px[p]; fp[p]=(round(c[0]*.25),round(c[1]*.25),round(c[2]*.25),255); off.add(p)
            frames.append(fr); offmasks.append(off)
        return frames,offmasks,ft
    def spec(fr,off):
        s=Image.new("RGBA",fr.size,(0,0,0,255)); ip,sp=fr.load(),s.load()
        for y in range(fr.size[1]):
            for x in range(fr.size[0]):
                r,g,b,a=ip[x,y]
                if a==0: continue
                lum=(r*.3+g*.59+b*.11)/255
                e=255 if ((r,g,b) in FRAMEC or (x,y) in off) else max(1,min(254,round(60+194*lum)))
                sp[x,y]=(242,0,0,e)
        return s
    def stack(ims):
        W,Hh=ims[0].size; o=Image.new("RGBA",(W,Hh*len(ims)))
        for k,im in enumerate(ims): o.paste(im,(0,k*Hh))
        return o
    for i in range(1,8):
        im=Image.open(BB+f"control_panel_0{i}.png").convert("RGBA")
        frames,offs,ft=screen_frames(i,im)
        D=f"assets/circinus/textures/block/control_panel/screen_{i}"
        meta=js({"animation":{"frametime":ft,"interpolate":False}})
        files[D+".png"]=png(stack(frames)); files[D+".png.mcmeta"]=meta
        files[D+"_s.png"]=png(stack([spec(f,o) for f,o in zip(frames,offs)])); files[D+"_s.png.mcmeta"]=meta
        files[D+"_n.png"]=png(Image.new("RGBA",(32,32*len(frames)),(128,128,255,255))); files[D+"_n.png.mcmeta"]=meta
        print("screen",i,len(frames),"frames, lamps blinking:",sum(1 for o in offs for _ in [0]) and len(set().union(*offs)))
    P="circinus:block/control_panel/plating"
    H=4.0; TT=math.tan(math.radians(22.5)); YT=15+H; YF=YT-15*TT
    def clean(poly):
        p=list(poly); ch=True
        while ch and len(p)>=3:
            ch=False
            for k in range(len(p)):
                a,b,c=p[k-1],p[k],p[(k+1)%len(p)]
                if abs(a[0]-b[0])<1e-7 and abs(a[1]-b[1])<1e-7 or abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))<1e-7:
                    p.pop(k); ch=True; break
        return p
    def tri(poly):
        pts=list(range(len(poly))); out=[]
        area=sum(poly[i][0]*poly[(i+1)%len(poly)][1]-poly[(i+1)%len(poly)][0]*poly[i][1] for i in range(len(poly)))
        sg=1 if area>0 else -1
        while len(pts)>3:
            for k in range(len(pts)):
                i0,i1,i2=pts[k-1],pts[k],pts[(k+1)%len(pts)]
                a,b,c=poly[i0],poly[i1],poly[i2]
                cr=((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))*sg
                if cr<=1e-9: continue
                def inside(p):
                    d1=((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))*sg
                    d2=((c[0]-b[0])*(p[1]-b[1])-(c[1]-b[1])*(p[0]-b[0]))*sg
                    d3=((a[0]-c[0])*(p[1]-c[1])-(a[1]-c[1])*(p[0]-c[0]))*sg
                    return d1>1e-9 and d2>1e-9 and d3>1e-9
                if any(inside(poly[j]) for j in pts if j not in (i0,i1,i2)): continue
                out.append((i0,i1,i2)); pts.pop(k); break
            else:
                for k in range(len(pts)):
                    a,b,c=poly[pts[k-1]],poly[pts[k]],poly[pts[(k+1)%len(pts)]]
                    if abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))<1e-7: pts.pop(k); break
                else: raise Exception("tri fail %r"%poly)
        out.append(tuple(pts)); return out,sg
    class Obj:
        def __init__(s): s.L=["mtllib control_panel.mtl"]; s.nv=0; s.cur=None
        def quad(s,P,N,mat,uvs=None):
            if mat=="p" and max(q[1] for q in P)<=1.5001: mat="c"
            if mat=="p" and abs(N[1])<0.5: mat="d"
            e1=[P[1][j]-P[0][j] for j in range(3)]; e2=[P[2][j]-P[0][j] for j in range(3)]
            cr=(e1[1]*e2[2]-e1[2]*e2[1],e1[2]*e2[0]-e1[0]*e2[2],e1[0]*e2[1]-e1[1]*e2[0])
            if sum(c*c for c in cr)<1e-12: return
            if sum(cr[j]*N[j] for j in range(3))<0:
                P=P[::-1]
                if uvs: uvs=uvs[::-1]
            if mat!=s.cur: s.L.append("usemtl "+mat); s.cur=mat
            for i,p in enumerate(P):
                s.L.append("v %.5f %.5f %.5f"%tuple(c/16 for c in p))
                if uvs: u,v=uvs[i]
                else:
                    ax=max(range(3),key=lambda k:abs(N[k]))
                    cu,cv={0:(2,1),1:(0,2),2:(0,1)}[ax]
                    bu=math.floor(min(q[cu] for q in P)/16+1e-6)*16; bv=math.floor(min(q[cv] for q in P)/16+1e-6)*16
                    u,v=(p[cu]-bu)/16,(p[cv]-bv)/16
                    if ax==1: v=1-v
                s.L.append("vt %.5f %.5f"%(u,v))
            s.L.append("vn %.4f %.4f %.4f"%tuple(N))
            k=s.nv; n=len(P); vn=sum(1 for l in s.L if l.startswith("vn "))
            idx=[k+1+i for i in range(n)]
            s.L.append("f "+" ".join(f"{i}/{i}/{vn}" for i in idx)); s.nv+=n
        def prism(s,prof,slope_from=None,skip=()):
            def clip(poly,ax,val,keep):
                out=[]
                for i in range(len(poly)):
                    A,B=poly[i-1],poly[i]; ia,ib=keep(A[ax]),keep(B[ax])
                    if ia!=ib:
                        t=(val-A[ax])/(B[ax]-A[ax]); q=[A[0]+t*(B[0]-A[0]),A[1]+t*(B[1]-A[1])]; q[ax]=val; out.append(tuple(q))
                    if ib: out.append(B)
                return out
            parts=[]
            pys=[]
            for pa in (clip(prof,1,1.5,lambda y:y<=1.5),clip(prof,1,1.5,lambda y:y>=1.5)):
                if len(pa)<3: continue
                pys+= [clip(pa,1,16,lambda y:y<=16),clip(pa,1,16,lambda y:y>=16)]
            for py in pys:
                py=clean(py)
                if len(py)<3: continue
                for pz in (clip(py,0,0,lambda z:z<=0),clip(py,0,0,lambda z:z>=0)):
                    pz=clean(pz)
                    if len(pz)>=3 and abs(sum(pz[i][0]*pz[i-1][1]-pz[i-1][0]*pz[i][1] for i in range(len(pz))))>1e-6: parts.append(pz)
            for part in parts:
                t,sg=tri(part)
                for x0,nx in ((0,-1),(16,1)):
                    for a,b,c in t:
                        pts=[(x0,part[i][1],part[i][0]) for i in (a,b,c)]
                        s.quad(pts,(nx,0,0),"p")
            t,sg=tri(prof)
            n=len(prof)
            for i in range(n):
                if i in skip: continue
                (z0,y0),(z1,y1)=prof[i],prof[(i+1)%n]
                dz,dy=z1-z0,y1-y0; L=math.hypot(dz,dy)
                N=(0,dz/L if sg<0 else -dz/L, -dy/L if sg<0 else dy/L)
                cuts=[0.0,1.0]
                if (y0-16)*(y1-16)<0: cuts.append((16-y0)/(y1-y0))
                if (y0-1.5)*(y1-1.5)<0: cuts.append((1.5-y0)/(y1-y0))
                if z0*z1<0: cuts.append(-z0/(z1-z0))
                cuts.sort(); segs=[((z0+a*dz,y0+a*dy),(z0+b*dz,y0+b*dy)) for a,b in zip(cuts,cuts[1:])]
                for (za,ya),(zb,yb) in segs:
                    P4=[(0,ya,za),(16,ya,za),(16,yb,zb),(0,yb,zb)]
                    e1=[P4[1][j]-P4[0][j] for j in range(3)]; e2=[P4[2][j]-P4[0][j] for j in range(3)]
                    cr=(e1[1]*e2[2]-e1[2]*e2[1],e1[2]*e2[0]-e1[0]*e2[2],e1[0]*e2[1]-e1[1]*e2[0])
                    if sum(cr[j]*N[j] for j in range(3))<0: P4=P4[::-1]
                    if 0.05<abs(N[1])<0.95:
                        hi=max(P4,key=lambda p:p[1])
                        uv=[(p[0]/16,1-math.hypot(p[1]-hi[1],p[2]-hi[2])/16) for p in P4]
                        s.quad(P4,N,"p",uv)
                    else: s.quad(P4,N,"p")
        def text(s): return ("\n".join(s.L)+"\n").encode()
    ZB=5.0
    ZF=16-(YF-2-3.5)*TT
    panel_prof=[(0,0),(0,YT),(ZB,YT),(16,YF),(16,YF-2),(ZF,3.5),(ZF,1.5),(ZF-1,1.5),(ZF-1,0)]
    def panel(scr_i):
        o=Obj(); o.prism(panel_prof,skip=(3,4)); add_front(o,16)
        if scr_i:
            im=Image.open(BB+f"control_panel_0{scr_i}.png").convert("RGBA"); ip=im.load()
            hm=[[0.0]*32 for _ in range(32)]
            for y in range(32):
                for x in range(32):
                    if ip[x,y][3]: hm[y][x]=1.0 if ip[x,y][:3]==(26,25,50) else 0.5
            dz,dy=16-ZB,YF-YT; L=math.hypot(dz,dy); tz,ty=dz/L,dy/L; N=(0,tz,-ty); T=(0,ty,tz)
            S=L-0.24; ps=S/32; t0=0.12; x0=8-S/2
            def pt(px,py,h): 
                t=t0+py*ps; return (x0+px*ps, YT+t*ty+h*N[1]+0.01*N[1], ZB+t*tz+h*N[2]+0.01*N[2])
            def H(x,y): return hm[y][x] if 0<=x<32 and 0<=y<32 else 0.0
            for y in range(32):
                x=0
                while x<32:
                    h=hm[y][x]
                    if h==0: x+=1; continue
                    x2=x
                    while x2+1<32 and hm[y][x2+1]==h: x2+=1
                    o.quad([pt(x,y,h),pt(x,y+1,h),pt(x2+1,y+1,h),pt(x2+1,y,h)],N,"s",[(x/32,1-y/32),(x/32,1-(y+1)/32),((x2+1)/32,1-(y+1)/32),((x2+1)/32,1-y/32)])
                    x=x2+1
            for y in range(32):
                for x in range(32):
                    h=hm[y][x]
                    if h==0: continue
                    c=((x+.5)/32,1-(y+.5)/32)
                    for (nx,ny),edge,n in (((-1,0),((x,y),(x,y+1)),(-1,0,0)),((1,0),((x+1,y),(x+1,y+1)),(1,0,0)),((0,-1),((x,y),(x+1,y)),tuple(-v for v in T)),((0,1),((x,y+1),(x+1,y+1)),T)):
                        hn=H(x+nx,y+ny)
                        if hn>=h: continue
                        (ax,ay),(bx,by)=edge
                        o.quad([pt(ax,ay,hn),pt(bx,by,hn),pt(bx,by,h),pt(ax,ay,h)],n,"s",[c]*4)
        return o.text()
    # front decor
    FRONT_COLS={}
    def front_mat(c):
        key="f%02x%02x%02x"%c[:3]
        if key not in FRONT_COLS:
            ctm=c[:3] in ((61,61,61),(27,27,27),(39,39,39),(19,76,76))
            FRONT_COLS[key]=ctm
            base_t=f"assets/circinus/textures/block/control_panel/{key}"
            cd=f"assets/minecraft/optifine/ctm/circinus/control_panel_{key}/"
            for (tx,ty,sfx),im in orig_tiles.items():
                if not ctm and (tx,ty)!=(0,0): continue
                im=im.copy()
                if sfx=="":
                    px=im.load()
                    for yy in range(32):
                        for xx in range(32):
                            p=px[xx,yy]; l=(p[0]/max(m[0],1)+p[1]/m[1]+p[2]/m[2])/3; l=1+(l-1)*0.45
                            px[xx,yy]=tuple(min(255,round(t*l)) for t in c[:3])+(255,)
                if ctm: files[f"{cd}{1+ty*8+tx}{sfx}.png"]=png(im)
                if (tx,ty)==(0,0): files[f"{base_t}{sfx}.png"]=png(im)
            if ctm: files[f"{cd}control_panel_{key}.properties"]=f"method=repeat\nwidth=8\nheight=8\ntiles=1-64\nmatchTiles=circinus:textures/block/control_panel/{key}\n".encode()
        return key
    def hmface(o,O,U,V,N,H,M,vfun):
        R=len(H); C=len(H[0])
        def P(r,c,h): return tuple(O[i]+U[i]*c+V[i]*r+N[i]*h for i in range(3))
        def uv(r,c): return (c/C, vfun(r))
        for r in range(R):
            c=0
            while c<C:
                h,mt=H[r][c],M[r][c]; c2=c
                while c2+1<C and H[r][c2+1]==h and M[r][c2+1]==mt: c2+=1
                o.quad([P(r,c,h),P(r+1,c,h),P(r+1,c2+1,h),P(r,c2+1,h)],N,mt,[uv(r,c),uv(r+1,c),uv(r+1,c2+1),uv(r,c2+1)])
                c=c2+1
        def Hc(r,c): return H[r][c] if 0<=r<R and 0<=c<C else 0.0
        def Mc(r,c): return M[r][c] if 0<=r<R and 0<=c<C else "p"
        for r in range(R+1):
            for c in range(C+1):
                for (ra,ca),(rb,cb),edge,dirv in (((r,c-1),(r,c),((r,c),(r+1,c)),U),((r-1,c),(r,c),((r,c),(r,c+1)),V)):
                    if r==R and dirv is U: continue
                    if c==C and dirv is V: continue
                    ha,hb=Hc(ra,ca),Hc(rb,cb)
                    if abs(ha-hb)<1e-9: continue
                    hi,lo=(ra,ca),(rb,cb)
                    if hb>ha: hi,lo=lo,hi
                    hh,hl=max(ha,hb),min(ha,hb)
                    sgn=1 if hi==(rb,cb) else -1
                    L=math.sqrt(sum(x*x for x in dirv)); n=tuple(-sgn*x/L for x in dirv)
                    (r1,c1),(r2,c2)=edge
                    cu=uv(min(max(hi[0],0),R-1)+.5,min(max(hi[1],0),C-1)+.5)
                    o.quad([P(r1,c1,hl),P(r2,c2,hl),P(r2,c2,hh),P(r1,c1,hh)],n,Mc(*hi),[cu]*4)
    GRID=[[4 if c in ((_r*3)%8,(_r*3+4)%8) else 1 for c in range(8)] for _r in range(8)]
    def recolor(im,c,dark=1.0):
        im=im.copy(); px=im.load()
        for yy in range(32):
            for xx in range(32):
                p=px[xx,yy]; l=(p[0]/max(m[0],1)+p[1]/m[1]+p[2]/m[2])/3; l=1+(l-1)*0.45
                px[xx,yy]=tuple(min(255,round(t*l*dark)) for t in c[:3])+(255,)
        return im
    def masked_mat(c,S):
        code="".join(str(k) for k in sorted(S))
        key=("dk" if c is None else "f%02x%02x%02x"%c[:3])+"_v"+code
        if key in FRONT_COLS: return key
        FRONT_COLS[key]=True
        cd=f"assets/minecraft/optifine/ctm/circinus/control_panel_{key}/"
        for (tx,ty,sfx),im in orig_tiles.items():
            if sfx=="": im=recolor(im,(0,112,113),0.5) if c is None else recolor(im,c)
            else: im=im.copy()
            if sfx=="" and GRID[ty][tx] not in S: im=Image.new("RGBA",(32,32),(0,0,0,0))
            files[f"{cd}{1+ty*8+tx}{sfx}.png"]=png(im)
            if (tx,ty)==(0,0): files[f"assets/circinus/textures/block/control_panel/{key}{sfx}.png"]=png(im)
        files[f"{cd}control_panel_{key}.properties"]=f"method=repeat\nwidth=8\nheight=8\ntiles=1-64\nmatchTiles=circinus:textures/block/control_panel/{key}\n".encode()
        return key
    class Col:
        def __init__(s): s.q=[]
        def quad(s,P,N,mat,uvs): s.q.append((P,N,mat,uvs))
    def front_layout(fi):
        im=Image.open(BB+f"front_{fi}.png").convert("RGBA"); ip=im.load()
        if fi==4: sl=[6,7,9,10,12,13,14,16,17,18,19,None,21,None,23]
        else: sl=[6,7,None,None,None,None,None,None,19,20,21,22,23,24,25]
        def grid(rows,hfun):
            H=[];M=[]
            for ir in rows:
                hr=[];mr=[]
                for c in range(32):
                    p=ip[c,ir] if ir is not None else (0,0,0,0)
                    if p[3]==0: hr.append(0.0); mr.append(None)
                    else: hr.append(hfun(p,ir)); mr.append(p[:3])
                H.append(hr); M.append(mr)
            return H,M
        def sh(p,ir):
            if p[:3]==(19,76,76): return -1.0
            if fi==4 and 6<=ir<=19: return 0.15
            return -0.5
        return grid([2,3,4,5],lambda p,ir:1.0),grid(sl,sh)
    def cellface(col,O,U,V,N,H,M,vfun):
        R=len(H); C=len(H[0])
        def P(r,c,h): return tuple(round(O[i]+U[i]*c+V[i]*r+N[i]*h,6) for i in range(3))
        def uv(r,c): return (c/C, vfun(r))
        for r in range(R):
            for c in range(C):
                h=H[r][c]
                col.quad([P(r,c,h),P(r+1,c,h),P(r+1,c+1,h),P(r,c+1,h)],N,M[r][c],[uv(r,c),uv(r+1,c),uv(r+1,c+1),uv(r,c+1)])
        def Hc(r,c): return H[r][c] if 0<=r<R and 0<=c<C else 0.0
        def Mc(r,c): return M[r][c] if 0<=r<R and 0<=c<C else None
        for r in range(R+1):
            for c in range(C+1):
                for (ra,ca),(rb,cb),edge,dirv in (((r,c-1),(r,c),((r,c),(r+1,c)),U),((r-1,c),(r,c),((r,c),(r,c+1)),V)):
                    if r==R and dirv is U: continue
                    if c==C and dirv is V: continue
                    ha,hb=Hc(ra,ca),Hc(rb,cb)
                    if abs(ha-hb)<1e-9: continue
                    hi=(rb,cb) if hb>ha else (ra,ca)
                    hh,hl=max(ha,hb),min(ha,hb)
                    sgn=1 if hi==(rb,cb) else -1
                    L=math.sqrt(sum(x*x for x in dirv)); n=tuple(-sgn*x/L for x in dirv)
                    (r1,c1),(r2,c2)=edge
                    cu=uv(min(max(hi[0],0),R-1)+.5,min(max(hi[1],0),C-1)+.5)
                    col.quad([P(r1,c1,hl),P(r2,c2,hl),P(r2,c2,hh),P(r1,c1,hh)],n,Mc(*hi),[cu]*4)
    LAYOUTS={k:front_layout(k) for k in (1,4)}
    def slant_variant(k,O,U,V,N,vfun):
        H,M=LAYOUTS[k][1]; R=len(H); C=len(H[0]); out=[]
        PET=lambda r,c: 0<=r<R and 0<=c<C and H[r][c]<=-0.45
        soft=lambda r,c: H[r][c] if (0<=r<R and 0<=c<C and not PET(r,c) and H[r][c]!=0) else 0.0
        dp=lambda r,c: H[r][c] if PET(r,c) else 0.0
        def sv(h): return -0.5 if h<0 else 0.15
        def vh(r,c):
            cs=[soft(r-1,c-1),soft(r-1,c),soft(r,c-1),soft(r,c)]
            if all(x<0 for x in cs) or all(x>0 for x in cs): return sv(cs[0])
            return 0.0
        def P(r,c,h): return tuple(round(O[i]+U[i]*c+V[i]*r+N[i]*h,6) for i in range(3))
        def uv(r,c): return (c/C, vfun(r))
        for r in range(R):
            for c in range(C):
                col=M[r][c]
                if PET(r,c):
                    out.append(([P(r,c,dp(r,c)),P(r+1,c,dp(r,c)),P(r+1,c+1,dp(r,c)),P(r,c+1,dp(r,c))],N,col,[uv(r,c),uv(r+1,c),uv(r+1,c+1),uv(r,c+1)],True))
                    continue
                hs=[vh(r,c),vh(r+1,c),vh(r+1,c+1),vh(r,c+1)]; cr=[(r,c),(r+1,c),(r+1,c+1),(r,c+1)]
                pts=[P(rr,cc,h) for (rr,cc),h in zip(cr,hs)]; uvs=[uv(rr,cc) for rr,cc in cr]
                if len(set(hs))==1: out.append((pts,N,col,uvs,False))
                else:
                    for tri_ in ((0,1,2),(0,2,3)):
                        out.append(([pts[i] for i in tri_],N,col,[uvs[i] for i in tri_],False))
        for r in range(R+1):
            for c in range(C+1):
                for (ra,ca),(rb,cb),edge,dirv in (((r,c-1),(r,c),((r,c),(r+1,c)),U),((r-1,c),(r,c),((r,c),(r,c+1)),V)):
                    if r==R and dirv is U: continue
                    if c==C and dirv is V: continue
                    pa,pb=PET(ra,ca),PET(rb,cb)
                    if pa==pb: continue
                    lo=(ra,ca) if pa else (rb,cb); hi=(rb,cb) if pa else (ra,ca)
                    sgn=1 if hi==(rb,cb) else -1
                    L=math.sqrt(sum(x*x for x in dirv)); n=tuple(-sgn*x/L for x in dirv)
                    (r1,c1),(r2,c2)=edge
                    hr,hc=min(max(hi[0],0),R-1),min(max(hi[1],0),C-1)
                    cu=uv(hr+.5,hc+.5)
                    out.append(([P(r1,c1,dp(*lo)),P(r2,c2,dp(*lo)),P(r2,c2,0),P(r1,c1,0)],n,M[hr][hc] if 0<=hi[0]<R and 0<=hi[1]<C else None,[cu]*4,2))
        return out
    def add_front(o,z0):
        lip=LAYOUTS[1][0]
        lipcol=Col(); cellface(lipcol,(0,YF,z0),(0.5,0,0),(0,-0.5,0),(0,0,1),lip[0],lip[1],lambda r:YF/16-(r*0.5)/16)
        for P_,N_,mt,uvs in lipcol.q:
            o.quad(list(P_),N_,"p" if mt is None else front_mat(mt),uvs)
        D=(0,3.5-(YF-2),-(16-ZF)); L=math.hypot(D[1],D[2]); NR=len(LAYOUTS[1][1][0]); V=(0,D[1]/NR,D[2]/NR); N=(0,D[2]/L,-D[1]/L)
        merged={}
        for k in (1,4):
            for P_,N_,mt,uvs,fixed in slant_variant(k,(0,YF-2,z0),(0.5,0,0),V,N,lambda r:1-(r*L/NR)/16):
                key=(tuple(P_),mt,fixed)
                if key in merged: merged[key][4].add(k)
                else: merged[key]=[P_,N_,mt,uvs,{k},fixed]
        for P_,N_,mt,uvs,S,fixed in merged.values():
            if fixed==2 or len(S)==2: name="p" if mt is None else front_mat(mt)
            else: name=masked_mat(mt,S)
            o.quad(list(P_),N_,name,uvs)
    def jm(name,tex):
        return js({"loader":"porting_lib:obj","flip_v":True,"automaticCulling":False,"model":f"circinus:models/block/control_panel/{name}.obj","textures":dict(tex,d=P+"_dark",c="circinus:block/corrugated_metal",particle=P,**{k:f"circinus:block/control_panel/{k}" for k in FRONT_COLS})})
    base="circinus:block/control_panel/"
    files["assets/circinus/models/block/control_panel/panel_off.obj"]=panel(0)
    for i in range(1,8): files[f"assets/circinus/models/block/control_panel/panel_screen_{i}.obj"]=panel(i)
    files["assets/circinus/models/block/control_panel/panel_off.json"]=jm("panel_off",{"p":P})
    for i in range(1,8):
        files[f"assets/circinus/models/block/control_panel/panel_{i}.json"]=jm(f"panel_screen_{i}",{"p":P,"s":f"circinus:block/control_panel/screen_{i}"})
    for n in range(1,5):
        d=4*n; o=Obj(); o.prism([(ZF-17,0),(ZF-17,1.5),(ZF-16,1.5),(ZF-16,3.5),(0,YF-2),(0,YF),(d,YF),(d,YF-2),(d-16+ZF,3.5),(d-16+ZF,1.5),(d-17+ZF,1.5),(d-17+ZF,0)],skip=(6,7)); add_front(o,d)
        files[f"assets/circinus/models/block/control_panel/extension_{n}.obj"]=o.text()
        files[f"assets/circinus/models/block/control_panel/extension_{n}.json"]=jm(f"extension_{n}",{"p":P})
    files["assets/circinus/models/block/control_panel/control_panel.mtl"]=("newmtl p\nmap_Kd #p\nnewmtl d\nmap_Kd #d\nnewmtl c\nmap_Kd #c\nnewmtl s\nmap_Kd #s\n"+"".join(f"newmtl {k}\nmap_Kd #{k}\n" for k in FRONT_COLS)).encode()
    rot={"south":0,"west":90,"north":180,"east":270}
    def var(m,f):
        v={"model":m}
        if rot[f]: v["y"]=rot[f]
        return v
    files["assets/conquest/blockstates/tudor_cross_frame_vertical_quarter.json"]=js({"variants":{f"facing={f},layer={l}":var(base+f"panel_{l}",f) for l in range(1,5) for f in rot}})
    files["assets/conquest/blockstates/tudor_cross_frame_vertical_corner.json"]=js({"variants":{f"facing={f},layer={l}":var(base+(f"panel_{l+4}" if l<=3 else "panel_off"),f) for l in range(1,5) for f in rot}})
    files["assets/conquest/blockstates/tudor_cross_frame_vertical_slab.json"]=js({"variants":{f"facing={f},layer={l}":var(base+f"extension_{l}",f) for l in range(1,5) for f in rot}})
    files["assets/conquest/models/item/tudor_cross_frame_vertical_quarter.json"]=js({"parent":base+"panel_1"})
    files["assets/conquest/models/item/tudor_cross_frame_vertical_corner.json"]=js({"parent":base+"panel_5"})
    files["assets/conquest/models/item/tudor_cross_frame_vertical_slab.json"]=js({"parent":base+"extension_4"})

    lang.setdefault('conquest', {}).update({'block.conquest.tudor_cross_frame_vertical_quarter': 'Control Panel', 'block.conquest.tudor_cross_frame_vertical_corner': 'Control Panel Corner', 'block.conquest.tudor_cross_frame_vertical_slab': 'Control Panel Extension'})
    cutout.extend(BLOCKS)
    tab.extend(BLOCKS)
    for k, v in files.items():
        with open(out(k), 'wb') as f:
            f.write(v)
