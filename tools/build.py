import glob, io, json, math, os, random, re, shutil, sys, zipfile, zlib
from PIL import Image, ImageChops, ImageFilter, ImageMath, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = 'circinus'
TILE = 32
GENERATED = [f'assets/{NS}', 'assets/conquest', 'assets/minecraft', 'assets/architects']
LIB = os.path.join(ROOT, 'lib')


def out(path):
    p = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def wjson(path, obj):
    with open(out(path), 'w', newline='\n') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')


class Assets:
    def __init__(self, paths):
        self.zips = [zipfile.ZipFile(p) for p in paths]
        self.names = [set(z.namelist()) for z in self.zips]

    def json(self, path):
        for z, n in zip(self.zips, self.names):
            if path in n:
                return json.loads(z.read(path))
        return None

    def layers(self):
        out = []
        for z, n in zip(self.zips, self.names):
            l = Assets([])
            l.zips, l.names = [z], [n]
            out.append(l)
        return out

    def raw(self, path):
        for z, n in zip(self.zips, self.names):
            if path in n:
                return z.read(path).decode('utf-8', 'replace')
        return None

    def blob(self, path):
        for z, n in zip(self.zips, self.names):
            if path in n:
                return z.read(path)
        return None

    def list(self, prefix):
        return sorted({x for n in self.names for x in n if x.startswith(prefix)})


def sources(argv):
    jar = argv[1] if len(argv) > 1 else glob.glob(os.path.join(LIB, 'ConquestReforged*.jar'))[0]
    acrp = argv[2] if len(argv) > 2 else next((p for p in glob.glob(os.path.join(LIB, 'ACRP*.zip')) if 'Patch' not in p), None)
    return glob.glob(os.path.join(LIB, 'ACRP Architects Patch*.zip')) + [p for p in (acrp, jar) if p] + glob.glob(os.path.join(LIB, 'Architects*.jar'))


def models_in(o, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == 'model':
                acc.add(v)
            else:
                models_in(v, acc)
    elif isinstance(o, list):
        for x in o:
            models_in(x, acc)


def model_path(m):
    ns, p = m.split(':', 1) if ':' in m else ('minecraft', m)
    return f'assets/{ns}/models/{p}.json'


def textures(a, m, depth=0):
    d = a.json(model_path(m))
    if d is None or depth > 8:
        return {}
    t = textures(a, d['parent'], depth + 1) if 'parent' in d else {}
    t.update(d.get('textures', {}))
    return t


GUI = {'gui': {'rotation': [30, 135, 0], 'translation': [0, 0, 0], 'scale': [0.625, 0.625, 0.625]},
       'head': {'rotation': [0, -90, 0], 'translation': [0, 0, 0], 'scale': [1, 1, 1]},
       'thirdperson_lefthand': {'rotation': [75, -135, 0], 'translation': [0, 2.5, 0], 'scale': [0.375, 0.375, 0.375]}}


def box(f, t, key=None):
    faces = {}
    for d, axis, side in (('down', 1, 0), ('up', 1, 1), ('north', 2, 0), ('south', 2, 1), ('west', 0, 0), ('east', 0, 1)):
        k = key or ('#bottom' if d == 'down' else '#top' if d == 'up' else '#side')
        face = {'texture': k}
        if (t if side else f)[axis] == (16 if side else 0):
            face['cullface'] = d
        faces[d] = face
    return {'from': f, 'to': t, 'faces': faces}


SLAB = ([0, 0, 0], [16, 8, 16])
VANILLA = {
    'minecraft:block/stairs': [SLAB, ([8, 8, 0], [16, 16, 16])],
    'minecraft:block/inner_stairs': [SLAB, ([8, 8, 0], [16, 16, 16]), ([0, 8, 8], [8, 16, 16])],
    'minecraft:block/outer_stairs': [SLAB, ([8, 8, 8], [16, 16, 16])],
    'minecraft:block/wall_inventory': [([4, 0, 4], [12, 16, 12]), ([5, 0, 0], [11, 13, 16])],
}


def vanilla(pid):
    key = '#wall' if 'wall' in pid else None
    tex = {'particle': '#wall'} if key else {'particle': '#side'}
    return {'parent': 'block/block', 'display': GUI, 'textures': tex, 'elements': [box(f, t, key) for f, t in VANILLA[pid]]}


def unlock(elements, tb=False):
    out = json.loads(json.dumps(elements))
    for el in out:
        if tb:
            for dname, face in el.get('faces', {}).items():
                if dname in ('up', 'down'):
                    face['texture'] = '#top' if dname == 'up' else '#bottom'
        inside = all(0 <= c <= 16 for c in el.get('from', []) + el.get('to', []))
        if inside and el.get('rotation', {}).get('angle', 0) == 0:
            for face in el.get('faces', {}).values():
                face.pop('uv', None)
                face.pop('rotation', None)
    return out


def fix_uv(a, d, done, tb=False):
    if 'elements' in d:
        d['elements'] = unlock(d['elements'], tb)
        return
    p = d.get('parent')
    if not p or p.startswith('builtin/'):
        return
    pid = p if ':' in p else 'minecraft:' + p
    fixed = f"{NS}:block/{'uv_tb' if tb else 'uv'}/{pid.replace(':', '/')}"
    if (pid, tb) not in done:
        pd = a.json(model_path(pid)) or (vanilla(pid) if pid in VANILLA else None)
        if pd is None:
            return
        pd = json.loads(json.dumps(pd))
        fix_uv(a, pd, done, tb)
        wjson(model_path(fixed), pd)
        done.add((pid, tb))
    d['parent'] = fixed


def own_textures(a, m, depth=0):
    d = a.json(model_path(m))
    if d is None or depth > 8:
        return {}
    p = d.get('parent', '')
    t = own_textures(a, p, depth + 1) if p.startswith('conquest:block/') and '/templates/' not in p else {}
    t.update(d.get('textures', {}))
    return t


def pct(img, q):
    h = img.histogram()
    n, acc = sum(h), 0
    for v, c in enumerate(h):
        acc += c
        if acc >= q * n:
            return v
    return 255


def median(img, mask):
    vs = sorted(v for v, m in zip(img.tobytes(), mask.tobytes()) if m)
    return vs[len(vs) // 2] if vs else 128


def tile_noise(size, cells, seed):
    rnd = random.Random(seed)
    small = Image.new('L', (cells, cells))
    small.putdata([rnd.randrange(256) for _ in range(cells * cells)])
    big = Image.new('L', (cells * 3, cells * 3))
    for i in range(3):
        for j in range(3):
            big.paste(small, (i * cells, j * cells))
    big = big.resize((size[0] * 3, size[1] * 3), Image.BICUBIC)
    return ImageOps.autocontrast(big.crop((size[0], size[1], size[0] * 2, size[1] * 2)))


def paint_chroma(cb, cr):
    a, b = cb.resize((128, 128)).tobytes(), cr.resize((128, 128)).tobytes()
    o = sorted(y - x for x, y in zip(a, b))
    lim = o[len(o) * 3 // 10]
    hist = {}
    for x, y in zip(a, b):
        if y - x <= lim:
            k = (x // 2, y // 2)
            hist[k] = hist.get(k, 0) + 1
    best = max(hist, key=lambda k: sum(hist.get((k[0] + i, k[1] + j), 0) for i in (-1, 0, 1) for j in (-1, 0, 1)))
    return best[0] * 2 + 1, best[1] * 2 + 1


def analyse(rgb):
    F = lambda im: im.convert('F')
    y, cb, cr = rgb.convert('YCbCr').split()
    pcb, pcr = paint_chroma(cb, cr)
    dc = ImageMath.lambda_eval(lambda a: ((a['cb'] - pcb) ** 2 + (a['cr'] - pcr) ** 2) ** 0.5, cb=F(cb), cr=F(cr))
    dc8 = dc.point(lambda v: v * 4).convert('L')
    lim = pct(dc8, 0.3)
    base = dc8.point(lambda v: 255 if v <= lim else 0)
    py = median(y, base)
    d8 = ImageMath.lambda_eval(lambda a: (a['dc'] ** 2 + (0.35 * (a['y'] - py)) ** 2) ** 0.5 * 4, dc=dc, y=F(y)).convert('L')
    bd = sorted(v for v, m in zip(d8.tobytes(), base.tobytes()) if m)
    med = bd[len(bd) // 2]
    mad = sorted(abs(v - med) for v in bd)[len(bd) // 2]
    t0 = (med + 3 * mad) / 4
    e = ImageMath.lambda_eval(lambda a: a['min'](a['max']((a['d'] / 4 - t0) / 10, 0), 1) * 255, d=F(d8)).convert('L')
    e = e.filter(ImageFilter.GaussianBlur(1.5))
    paint = ImageOps.invert(e).point(lambda v: 255 if v > 200 else 0)
    return y, py, d8, e, paint


def process(t, size):
    src = lambda m: Image.open(os.path.join(ROOT, 'src', f"{t['asset']}_{m}.png"))
    fit = lambda im: im if im.size == size else im.resize(size, Image.LANCZOS)
    rgb, arm, nrm = fit(src('diff').convert('RGB')), fit(src('arm').convert('RGB')), fit(src('nor_gl').convert('RGB'))
    F = lambda im: im.convert('F')
    def rust_parts():
        rsrc = lambda m: fit(Image.open(os.path.join(ROOT, 'src', f"{t['rust_asset']}_{m}.png")).convert('RGB'))
        rgb4, arm4, nrm4 = rsrc('diff'), rsrc('arm'), rsrc('nor_gl')
        ry, rcb, rcr = rgb4.convert('YCbCr').split()
        rr = ImageMath.lambda_eval(lambda a: (a['cr'] - a['cb'] + 64) * 2, cb=F(rcb), cr=F(rcr)).convert('L')
        m = rr.point(lambda v, q=pct(rr, 0.5): 255 if v > q else 0)
        blur = lambda im: im.filter(ImageFilter.GaussianBlur(16))
        mb = blur(m)
        fill = lambda im: Image.merge(im.mode, [ImageMath.lambda_eval(lambda a: a['c'] / a['max'](a['w'], 1) * 255, c=F(blur(ImageChops.multiply(ch, m))), w=F(mb)).convert('L') for ch in im.split()])
        detail = ImageMath.lambda_eval(lambda a: a['min'](a['max'](a['y'] / a['max'](a['b'], 1), 0.7), 1.3), y=F(ry), b=F(blur(ry)))
        frgb = Image.merge('RGB', [ImageMath.lambda_eval(lambda a: a['c'] * a['d'], c=F(ch), d=detail).convert('L') for ch in fill(rgb4).split()])
        conf = mb.point(lambda v: max(0, min(255, (v - 20) * 4)))
        med_rgb = Image.new('RGB', size, tuple(median(ch, m) for ch in rgb4.split()))
        med_rgb = Image.merge('RGB', [ImageMath.lambda_eval(lambda a: a['c'] * a['d'], c=F(ch), d=detail).convert('L') for ch in med_rgb.split()])
        frgb = Image.composite(frgb, med_rgb, conf)
        farm = Image.composite(fill(arm4), Image.new('RGB', size, tuple(median(ch, m) for ch in arm4.split())), conf)
        rust = Image.composite(rgb4, frgb, m), Image.composite(arm4, farm, m), nrm4
        return rust, rr
    if 'color' not in t:
        e = Image.new('L', size, 0)
        if t.get('blur'):
            rgb = rgb.filter(ImageFilter.GaussianBlur(t['blur']))
        if t.get('height_shade'):
            h = fit(src('disp').convert('I').point(lambda v: v * (1 / 257)).convert('L'))
            hm, k, g = sum(h.getdata()) / (size[0] * size[1]), t['height_shade'], t.get('height_sharpen', 0)
            sp = max(1, (pct(h, 0.95) - pct(h, 0.05)) / 2)
            curve = (lambda v: math.tanh(g * (v - hm) / sp)) if g else (lambda v: (v - hm) / 128)
            kd, kl = k if isinstance(k, list) else (k, k)
            f = h.point(lambda v: max(0, min(255, round(128 * (1 - (kd if curve(v) > 0 else kl) * curve(v))))))
            rgb = Image.merge('RGB', [ImageMath.lambda_eval(lambda a: a['c'] * a['f'] / 128, c=F(ch), f=F(f)).convert('L') for ch in rgb.split()])
        if t.get('bands'):
            amp, jit = t['bands']
            r = random.Random(zlib.crc32(t['name'].encode()))
            ph = [(fq, r.uniform(0, 2 * math.pi), r.uniform(0.3, 1) / fq ** 0.6) for fq in range(2, 40)]
            pr = [sum(av * math.sin(2 * math.pi * fq * x / size[0] + q) for fq, q, av in ph) for x in range(size[0])]
            mx = max(abs(v) for v in pr)
            row = Image.new('L', (size[0], 1))
            row.putdata([max(0, min(255, round(128 * (1 + amp * v / mx + jit * r.uniform(-1, 1))))) for v in pr])
            f = row.resize(size, Image.NEAREST)
            rgb = Image.merge('RGB', [ImageMath.lambda_eval(lambda a: a['c'] * a['f'] / 128, c=F(ch), f=F(f)).convert('L') for ch in rgb.split()])
        if t.get('rust_asset'):
            rust, rr = rust_parts()
            p = pct(rr, t.get('rust_full_cut', 0.68))
            op = t.get('rust_opacity', 0.85)
            w = rr.point(lambda v: round(255 * op * min(1, max(0, (v - p + 10) / 20)))).filter(ImageFilter.GaussianBlur(1))
            rgb = Image.composite(rust[0], rgb, w)
            arm = Image.composite(rust[1], arm, w)
            nrm = Image.composite(rust[2], nrm, w)
        return spec_layers(t, rgb.convert('RGBA'), arm, nrm), e, e
    y, py, d8, e, paint = analyse(rgb)
    noise = tile_noise(size, t.get('erosion_cells', 6), zlib.crc32(t['name'].encode()))
    thr = pct(noise, 1 - t.get('erosion', 0.12))
    k = noise.point(lambda v: max(0, min(255, (v - thr) * 4)))
    w = ImageMath.lambda_eval(lambda a: a['e'] * a['k'] / 255 * 0.85, e=F(e), k=F(k)).convert('L')
    rust, rr = rust_parts() if t.get('rust_asset') else (None, None)
    if t.get('rust') == 'full':
        p = pct(rr, t.get('rust_full_cut', 0.68))
        w = rr.point(lambda v: round(255 * min(1, max(0, (v - p + 10) / 20)))).filter(ImageFilter.GaussianBlur(1))
    elif t.get('rust') == 'light':
        ds = sorted(v for v, m in zip(d8.tobytes(), e.tobytes()) if m > 128)
        p = ds[int(len(ds) * t.get('rust_light_cut', 0.7))] if ds else 255
        core = d8.point(lambda v: round(255 * min(1, max(0, (v - p + 12) / 24)))).filter(ImageFilter.GaussianBlur(1))
        w = ImageChops.darker(e, core)
    if t.get('rust'):
        op = t.get('rust_opacity', 0.85)
        w = w.point(lambda v: round(v * op))
    r = e if rust else ImageChops.subtract(e, w)
    if t.get('uniform_pbr'):
        r = Image.new('L', size, 255)
    det = t.get('detail', 0.7) * t.get('contrast', 1.0)
    s = ImageMath.lambda_eval(lambda a: a['min'](a['max'](1 + ((a['y'] / py) * (1 - a['e'] / 255) + a['e'] / 255 - 1) * det, 0.35), 1.65), y=F(y), e=F(e))
    if t.get('flatten'):
        sb = s.point(lambda v: v * 127).convert('L').filter(ImageFilter.GaussianBlur(t['flatten']))
        s = ImageMath.lambda_eval(lambda a: a['s'] * 127 / a['max'](a['b'], 1), s=s, b=F(sb))
    col = tuple(int(t['color'].lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
    lift = t.get('lift', 40)
    painted = Image.merge('RGB', [ImageMath.lambda_eval(lambda a, c=c: a['s'] * c + (a['s'] - 1) * lift, s=s).convert('L') for c in col])
    diffuse = Image.composite(rust[0] if rust else rgb, painted, w).convert('RGBA')
    a_r, a_g, a_b = arm.split()
    arm = Image.composite(Image.new('RGB', size, (median(a_r, paint), median(a_g, paint), median(a_b, paint))), arm, r)
    nrm = Image.composite(Image.new('RGB', size, (128, 128, 255)), nrm, r)
    if rust:
        arm = Image.composite(rust[1], arm, w)
        nrm = Image.composite(rust[2], nrm, w)
    ns = t.get('normal_strength', 1.0)
    if ns != 1.0:
        raw, px = nrm.tobytes(), bytearray()
        for i in range(0, len(raw), 3):
            x, yy, z = (c / 127.5 - 1 for c in raw[i:i + 3])
            x, yy = x * ns, yy * ns
            l = (x * x + yy * yy + z * z) ** 0.5 or 1
            px += bytes(round((c / l + 1) * 127.5) for c in (x, yy, z))
        nrm = Image.frombytes('RGB', size, bytes(px))
    return spec_layers(t, diffuse, arm, nrm), e, w


def spec_layers(t, diffuse, arm, nrm):
    nrm.putalpha(255)
    if t.get('spread'):
        rgb, al = diffuse.convert('RGB'), diffuse.getchannel('A')
        mean = tuple(round(sum(ch.getdata()) / (rgb.size[0] * rgb.size[1])) for ch in rgb.split())
        diffuse = Image.blend(Image.new('RGB', rgb.size, mean), rgb, t['spread']).convert('RGBA')
        diffuse.putalpha(al)
    _, rough, metal = arm.split()
    sm, mt = t.get('smoothness', 1.0), t.get('metalness', 1.0)
    spec = Image.merge('RGBA', (ImageOps.invert(rough).point(lambda v: round(v * sm)), metal.point(lambda v: round(v * mt)), Image.new('L', arm.size, 0), Image.new('L', arm.size, 255)))
    return {'': diffuse, '_n': nrm, '_s': spec}


def write_layers(layers, pick, name, gw, gh):
    small = pick.resize((gw, gh), Image.BOX).tobytes()
    bi = max(range(gw * gh), key=lambda i: small[i])
    box = ((bi % gw) * TILE, (bi // gw) * TILE, (bi % gw + 1) * TILE, (bi // gw + 1) * TILE)
    for sfx, img in layers.items():
        img.crop(box).save(out(f'assets/{NS}/textures/block/{name}{sfx}.png'))
    ctm = f'assets/minecraft/optifine/ctm/{NS}/{name}'
    for sfx, img in layers.items():
        i = 1
        for yy in range(gh):
            for x in range(gw):
                img.crop((x * TILE, yy * TILE, (x + 1) * TILE, (yy + 1) * TILE)).save(out(f'{ctm}/{i}{sfx}.png'))
                i += 1
    with open(out(f'{ctm}/{name}.properties'), 'w', newline='\n') as f:
        f.write(f'method=repeat\nwidth={gw}\nheight={gh}\ntiles=1-{gw * gh}\nmatchTiles={NS}:textures/block/{name}\n')


def obj_mesh(parts, boxes, sides=12, tiles=1, t0=0, wrap=False):
    v, vt, vn, f = [], [], [], []
    cnt = [t0]
    def vert(p, n, uv):
        v.append(tuple(c / 16 for c in p)); vn.append(n); vt.append(uv)
        return len(v)
    def norm(x):
        l = math.sqrt(sum(c * c for c in x)) or 1
        return tuple(c / l for c in x)
    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    def basis(t):
        h = (0, 1, 0) if abs(t[1]) < 0.9 else (1, 0, 0)
        n1 = norm(cross(t, h))
        return n1, cross(n1, t)
    def ring(c, n1, n2, r):
        out = []
        for k in range(sides + 1):
            a = 2 * math.pi * k / sides
            d = tuple(math.cos(a) * n1[i] + math.sin(a) * n2[i] for i in range(3))
            out.append((tuple(c[i] + r * d[i] for i in range(3)), d, k / sides))
        return out
    def sweep(path, r, mat, caps=(False, False)):
        ti = cnt[0] % (tiles if wrap else tiles * tiles)
        cnt[0] += 1
        tv = (lambda uv: (uv[0], (ti + uv[1]) / tiles)) if wrap else (lambda uv: ((ti % tiles + uv[0]) / tiles, (ti // tiles + uv[1]) / tiles))
        length, rings = 0, []
        for j, (c, n1, n2) in enumerate(path):
            if j:
                length += math.dist(c, path[j - 1][0])
            rings.append((ring(c, n1, n2, r), length / 16))
        for (ra, va), (rb, vb) in zip(rings, rings[1:]):
            for k in range(sides):
                q = [vert(ra[k][0], ra[k][1], tv((ra[k][2], va))), vert(rb[k][0], rb[k][1], tv((rb[k][2], vb))),
                     vert(rb[k + 1][0], rb[k + 1][1], tv((rb[k + 1][2], vb))), vert(ra[k + 1][0], ra[k + 1][1], tv((ra[k + 1][2], va)))]
                f.append((mat, q))
        for (c, n1, n2), use, sg in ((path[0], caps[0], -1), (path[-1], caps[1], 1)):
            if use:
                t = cross(n2, n1)
                nn = tuple(sg * x for x in t)
                rg = ring(c, n1, n2, r)
                ci = vert(c, nn, tv((0.5, 0.5)))
                for k in range(sides):
                    a, b = rg[k], rg[k + 1]
                    ia = vert(a[0], nn, tv((0.5 + a[1][0] * r / 16, 0.5 + a[1][2] * r / 16)))
                    ib = vert(b[0], nn, tv((0.5 + b[1][0] * r / 16, 0.5 + b[1][2] * r / 16)))
                    f.append((mat, (ci, ia, ib) if sg < 0 else (ci, ib, ia)))
    ax = {'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}
    for pt in parts:
        kind = pt[0]
        if kind in ('tube', 'flange'):
            axis, a0, a1 = pt[1], pt[2], pt[3]
            t = ax[axis]
            n1, n2 = basis(t)
            cen = lambda s: tuple(8 + (s - 8) * t[i] for i in range(3))
            r = pt[4] if len(pt) > 4 else (4.1 if kind == 'flange' else 3.1)
            caps = (True, True) if kind == 'flange' else tuple(pt[5]) if len(pt) > 5 else (False, False)
            mat = pt[6] if len(pt) > 6 else ('flange' if kind == 'flange' else 'pipe')
            n = max(1, math.ceil(abs(a1 - a0) / 16 - 1e-9))
            for j in range(n):
                s0, s1 = a0 + (a1 - a0) * j / n, a0 + (a1 - a0) * (j + 1) / n
                sweep([(cen(s0), n1, n2), (cen(s1), n1, n2)], r, mat, (caps[0] and j == 0, caps[1] and j == n - 1))
        elif kind == 'torus':
            c, R, r, n, a0, runs = pt[1:7]
            pos = lambda th, ph: tuple(c[i] + [(R + r * math.cos(ph)) * math.cos(th), (R + r * math.cos(ph)) * math.sin(th), r * math.sin(ph)][i] for i in range(3))
            nrm = lambda th, ph: (math.cos(ph) * math.cos(th), math.cos(ph) * math.sin(th), math.sin(ph))
            seg, s = 2 * math.pi * R / n / 16, 0
            for cnt, mat in runs:
                for j in range(cnt):
                    t0, t1 = math.radians(a0 + 360 * s / n), math.radians(a0 + 360 * (s + 1) / n)
                    for k in range(sides):
                        p0, p1 = 2 * math.pi * k / sides, 2 * math.pi * (k + 1) / sides
                        v0, v1 = k / sides * 2 * math.pi * r / 16, (k + 1) / sides * 2 * math.pi * r / 16
                        corners4 = [(t0, p0, j * seg, v0), (t1, p0, (j + 1) * seg, v0), (t1, p1, (j + 1) * seg, v1), (t0, p1, j * seg, v1)]
                        P = [pos(th, ph) for th, ph, _, _ in corners4]
                        fn = cross(tuple(P[1][i] - P[0][i] for i in range(3)), tuple(P[2][i] - P[0][i] for i in range(3)))
                        mid = nrm((t0 + t1) / 2, (p0 + p1) / 2)
                        if sum(fn[i] * mid[i] for i in range(3)) < 0:
                            corners4.reverse()
                        f.append((mat, [vert(pos(th, ph), nrm(th, ph), (u, vv)) for th, ph, u, vv in corners4]))
                    s += 1
        elif kind == 'bend':
            c, rb, a0, a1 = pt[1], pt[2], pt[3], pt[4]
            i, j2 = pt[5] if len(pt) > 5 else (0, 1)
            k = 3 - i - j2
            path = []
            for j in range(13):
                th = math.radians(a0 + (a1 - a0) * j / 12)
                p0, t, n1 = list(c), [0, 0, 0], [0, 0, 0]
                p0[i] += rb * math.cos(th)
                p0[j2] += rb * math.sin(th)
                t[i], t[j2] = -math.sin(th) * (a1 - a0), math.cos(th) * (a1 - a0)
                n1[k] = 1 if (i, j2) in ((0, 1), (1, 2), (2, 0)) else -1
                t, n1 = norm(t), tuple(n1)
                path.append((tuple(p0), n1, cross(n1, t)))
            sweep(path, 3.1, 'pipe')
    corners = {
        'north': lambda a, b: [(b[0], b[1], a[2]), (a[0], b[1], a[2]), (a[0], a[1], a[2]), (b[0], a[1], a[2])],
        'south': lambda a, b: [(a[0], b[1], b[2]), (b[0], b[1], b[2]), (b[0], a[1], b[2]), (a[0], a[1], b[2])],
        'west': lambda a, b: [(a[0], b[1], a[2]), (a[0], b[1], b[2]), (a[0], a[1], b[2]), (a[0], a[1], a[2])],
        'east': lambda a, b: [(b[0], b[1], b[2]), (b[0], b[1], a[2]), (b[0], a[1], a[2]), (b[0], a[1], b[2])],
        'up': lambda a, b: [(a[0], b[1], a[2]), (b[0], b[1], a[2]), (b[0], b[1], b[2]), (a[0], b[1], b[2])],
        'down': lambda a, b: [(a[0], a[1], b[2]), (b[0], a[1], b[2]), (b[0], a[1], a[2]), (a[0], a[1], a[2])],
    }
    normals = {'north': (0, 0, -1), 'south': (0, 0, 1), 'west': (-1, 0, 0), 'east': (1, 0, 0), 'up': (0, 1, 0), 'down': (0, -1, 0)}
    for el in boxes:
        for face, fc in el['faces'].items():
            u1, v1, u2, v2 = fc.get('uv', (0, 0, 16, 16))
            uvs = [(u1, v1), (u2, v1), (u2, v2), (u1, v2)]
            k = fc.get('rotation', 0) // 90
            uvs = uvs[-k:] + uvs[:-k] if k else uvs
            f.append(('orig', [vert(p, normals[face], (uv[0] / 16, 1 - uv[1] / 16)) for p, uv in reversed(list(zip(corners[face](el['from'], el['to']), uvs)))]))
    out = ['mtllib pipe.mtl', 'o pipe']
    out += ['v %.5f %.5f %.5f' % x for x in v] + ['vt %.5f %.5f' % x for x in vt] + ['vn %.5f %.5f %.5f' % x for x in vn]
    cur = None
    for mat, q in f:
        if mat != cur:
            out.append(f'usemtl {mat}'); cur = mat
        out.append('f ' + ' '.join(f'{i}/{i}/{i}' for i in q))
    return '\n'.join(out) + '\n'


def main():
    cfg = json.load(open(os.path.join(ROOT, 'src/mappings.json'), encoding='utf-8'))
    a = Assets(sources(sys.argv))
    for g in GENERATED:
        shutil.rmtree(os.path.join(ROOT, g), ignore_errors=True)
    if os.path.isdir(os.path.join(ROOT, 'src', 'assets')):
        shutil.copytree(os.path.join(ROOT, 'src', 'assets'), os.path.join(ROOT, 'assets'), dirs_exist_ok=True)
    for t in cfg['textures']:
        t.setdefault('contrast', cfg.get('contrast', 1.0))
    done = set()
    lang = {}
    tab = []
    for t in cfg['textures']:
        name, (gw, gh) = t['name'], t.get('grid', (1, 1))
        tex_id = f'{NS}:block/{name}'
        edge = t.get('edge')
        if not edge:
            layers, e, w = process(t, (gw * TILE, gh * TILE))
            write_layers(layers, w if t.get('rust') else ImageOps.invert(e), name, gw, gh)
            if t.get('shifted'):
                dx, dy = gw * TILE // 2, gh * TILE // 2
                pick = w if t.get('rust') else ImageOps.invert(e)
                write_layers({k: ImageChops.offset(im, dx, dy) for k, im in layers.items()}, ImageChops.offset(pick, dx, dy), f'{name}_shift', gw, gh)
            if t.get('period'):
                for sfx, img in process(t, (t['period'] * TILE, t['period'] * TILE))[0].items():
                    img.save(out(f'assets/{NS}/textures/block/{name}_plain{sfx}.png'))
            elif t.get('plain'):
                k = t['plain']
                hl, hp = layers, (w if t.get('rust') else ImageOps.invert(e))
                if t.get('shifted'):
                    hl = {kk: ImageChops.offset(im, gw * TILE // 2, gh * TILE // 2) for kk, im in hl.items()}
                    hp = ImageChops.offset(hp, gw * TILE // 2, gh * TILE // 2)
                small = hp.resize((gw, gh), Image.BOX).tobytes()
                bi = max(range(gw * gh), key=lambda i: small[i])
                for sfx, img in hl.items():
                    ImageChops.offset(img, -(bi % gw) * TILE, -(bi // gw) * TILE).crop((0, 0, k * TILE, k * TILE)).save(out(f'assets/{NS}/textures/block/{name}_plain{sfx}.png'))
        n_blocks = n_models = 0
        for fam in t['targets']:
            ns, block = fam.split(':')
            base = set()
            for layer in [a] + a.layers():
                ms = set()
                models_in(layer.json(f'assets/{ns}/blockstates/{block}.json'), ms)
                base |= {v for m in ms for v in own_textures(layer, m).values() if not v.startswith('#')}
            for bs in a.list(f'assets/{ns}/blockstates/'):
                bn = bs.rsplit('/', 1)[1][:-5]
                if bn != block and not bn.startswith(block + '_'):
                    continue
                src_layer = next(l for l in a.layers() if l.json(bs) is not None)
                la = Assets([])
                la.zips = src_layer.zips + [z for z in a.zips if z not in src_layer.zips]
                la.names = src_layer.names + [n for z, n in zip(a.zips, a.names) if z not in src_layer.zips]
                ms = set()
                models_in(la.json(bs), ms)
                item = la.json(f'assets/{ns}/models/item/{bn}.json')
                if item and item.get('parent', '').startswith(f'{ns}:block/'):
                    ms.add(item['parent'])
                tx = [own_textures(la, m) for m in ms]
                if not ms or any(not x or not {v for v in x.values() if not v.startswith('#')} <= base for x in tx):
                    continue
                for m in ms:
                    d = la.json(model_path(m))
                    if any(v in base for v in d.get('textures', {}).values()):
                        if edge:
                            ids = {k: f'{NS}:block/{v}' for k, v in edge.items()}
                            top, bottom = ids['top'], ids['bottom']
                            if any(bn.endswith('_' + x) for x in t.get('edge_flip', [])):
                                top, bottom = bottom, top
                            d['textures'] = {kk: ids['side'] for kk in d['textures']}
                            d['textures'].update(top=top, bottom=bottom, particle=ids['side'])
                            fix_uv(la, d, done, True)
                        else:
                            tid = tex_id
                            if d.get('loader'):
                                tid = f'{tex_id}_full'
                                n = t.get('obj_size', gw * TILE)
                                for sfx, img in layers.items():
                                    img.resize((n, n), Image.LANCZOS).save(out(f'assets/{NS}/textures/block/{name}_full{sfx}.png'))
                            d['textures'] = {kk: (tid if v in base else v) for kk, v in d['textures'].items()}
                            fix_uv(la, d, done)
                        wjson(model_path(m), d)
                        n_models += 1
                n_blocks += 1
                tab.append(f'{ns}:{bn}')
                if t.get('display_name'):
                    suffix = bn[len(block):].replace('_', ' ').title()
                    lang.setdefault(ns, {})[f'block.{ns}.{bn}'] = t.get('names', {}).get(f'{ns}:{bn}') or t['display_name'] + suffix
        print(f'{name}: {gw}x{gh}, {n_blocks} Block-IDs, {n_models} Models')


    def tex_ref(v):
        if isinstance(v, str):
            return f'{NS}:block/{v}'
        if 'frame' in v:
            key = f"block/frame/{v['material']}_{v['frame']}"
            w = round(v['frame'] * TILE / 16)
            mask = Image.new('L', (TILE, TILE), 255)
            mask.paste(0, (w, w, TILE - w, TILE - w))
            fill = {'': v.get('fill', (0, 0, 0, 0)), '_n': (128, 128, 255, 255), '_s': tuple(v.get('fill_spec', (0, 0))) + (0, 255)}
            for sfx in ('', '_n', '_s'):
                img = Image.open(out(f"assets/{NS}/textures/block/{v['material']}{sfx}.png")).convert('RGBA')
                img = Image.composite(img, Image.new('RGBA', img.size, tuple(fill[sfx])), mask)
                img.save(out(f'assets/{NS}/textures/{key}{sfx}.png'))
            return f'{NS}:{key}'
        mns, mp = v['mask'].split(':')
        key = f"block/masked/{v['material']}/{mp.rsplit('/', 1)[1]}"
        mask = Image.open(io.BytesIO(a.blob(f'assets/{mns}/textures/{mp}.png'))).convert('RGBA').split()[3]
        if v.get('mask_min'):
            mask = mask.point(lambda x: 255 if x >= v['mask_min'] else 0)
        for sfx in ('', '_n', '_s'):
            img = Image.open(out(f"assets/{NS}/textures/block/{v['material']}{sfx}.png")).convert('RGBA').resize(mask.size, Image.NEAREST)
            if sfx == '':
                img.putalpha(mask)
            img.save(out(f'assets/{NS}/textures/{key}{sfx}.png'))
        return f'{NS}:{key}'

    written = {}
    cutout, translucent = [], []
    for ri, rt in enumerate(cfg.get('retexture', [])):
        cutout += rt['blocks'] if rt.get('cutout') else []
        tab += rt['blocks']
        if 'can_occlude' in rt:
            for bid in rt['blocks']:
                bns, bp = bid.split(':')
                wjson(f'assets/{bns}/polytone/block_modifiers/{bp}.json', {'can_occlude': rt['can_occlude']})
        for nid, nm in rt.get('names', {}).items():
            lang.setdefault(nid.split(':')[0], {})[f"block.{nid.replace(':', '.')}"] = nm
        translucent += rt['blocks'] if rt.get('translucent') else []
        for bid in rt['blocks']:
            ns, block = bid.split(':')
            path = f'assets/{ns}/blockstates/{block}.json'
            bs = written.get(path) or a.json(path)
            copies = {}
            orig = a.json(path)['variants']
            for k, var in bs.get('variants', {}).items():
                props = dict(p.split('=') for p in k.split(',') if '=' in p)
                if any(props.get(pk) not in (pv if isinstance(pv, list) else [pv]) for pk, pv in rt.get('when', {}).items()):
                    continue
                if rt.get('model_from'):
                    want = dict(props, **rt['model_from'])
                    src = next(v for kk, v in orig.items() if dict(p.split('=') for p in kk.split(',') if '=' in p) == want)
                    var = json.loads(json.dumps(src))
                    bs['variants'][k] = var
                for x in (var if isinstance(var, list) else [var]):
                    m = rt.get('source', x['model'])
                    copy = f"{NS}:block/retex/{ri}/{m.replace(':', '/')}"
                    copies[m] = copies[x['model']] = copy
                    md = json.loads(json.dumps(a.json(model_path(m))))
                    md['textures'] = {kk: (tex_ref(rt['textures'][kk]) if kk in rt['textures'] else vv) for kk, vv in md.get('textures', {}).items()}
                    if rt.get('obj'):
                        src_m = md
                        while 'elements' not in src_m and src_m.get('parent'):
                            src_m = a.json(model_path(src_m['parent']))
                        keep = [e for i, e in enumerate(src_m.get('elements', [])) if i in rt['obj'].get('keep', [])]
                        cp = copy.split(':', 1)[1]
                        nt, wr = rt['obj'].get('tiles', 1), rt['obj'].get('wrap', False)
                        for ti in range(nt if wr else nt * nt):
                            with open(out(f'assets/{NS}/models/{cp}{"_" + str(ti) if ti else ""}.obj'), 'w', newline='\n') as fo:
                                fo.write(obj_mesh(rt['obj']['parts'], keep, tiles=nt, t0=ti, wrap=wr))
                        with open(out(f'assets/{NS}/models/{cp.rsplit("/", 1)[0]}/pipe.mtl'), 'w', newline='\n') as fo:
                            fo.write('newmtl pipe\nmap_Kd #pipe\nnewmtl flange\nmap_Kd #flange\nnewmtl orig\nmap_Kd #orig\n')
                        orig = md.get('textures', {}).get('orig') or json.loads(json.dumps(a.json(model_path(m)))).get('textures', {}).get('pipe')
                        md = {'loader': 'porting_lib:obj', 'flip_v': True, 'automaticCulling': False, 'model': f'{NS}:models/{cp}.obj',
                              'textures': {'pipe': tex_ref(rt['textures']['pipe']), 'flange': tex_ref(rt['textures'].get('flange', rt['textures']['pipe'])), 'orig': tex_ref(rt['textures']['orig']) if 'orig' in rt['textures'] else orig, 'particle': tex_ref(rt['textures']['pipe'])}}
                    elif rt.get('offset') and md.get('loader'):
                        ons, op = md['model'].split(':')
                        od = op.rsplit('/', 1)[0]
                        obj = a.raw(f'assets/{ons}/{op}')
                        lines = []
                        for ln in obj.splitlines():
                            if ln.startswith('v '):
                                ln = 'v ' + ' '.join(f'{float(c) + o / 16:.6f}' for c, o in zip(ln.split()[1:4], rt['offset']))
                            elif ln.startswith('mtllib '):
                                mtl = ln.split(None, 1)[1]
                                with open(out(f'assets/{NS}/models/retex/{ons}/{od}/{mtl}'), 'w', newline='\n') as f:
                                    f.write(a.raw(f'assets/{ons}/{od}/{mtl}'))
                            lines.append(ln)
                        with open(out(f'assets/{NS}/models/retex/{ons}/{op}'), 'w', newline='\n') as f:
                            f.write('\n'.join(lines) + '\n')
                        md['model'] = f'{NS}:models/retex/{ons}/{op}'
                    if 'elements' in rt:
                        md['elements'] = rt['elements']
                    if rt.get('shade'):
                        src_m = md
                        while 'elements' not in src_m and src_m.get('parent'):
                            src_m = a.json(model_path(src_m['parent']))
                        md['elements'] = [{k: v for k, v in el.items() if k != 'shade'} for el in src_m.get('elements', [])]
                    wjson(model_path(copy), md)
                    x['model'] = copy
                    if rt.get('no_rotation'):
                        x.pop('x', None)
                        x.pop('y', None)
                    if rt.get('upright'):
                        x.pop('x', None)
                        y = (x.get('y', 0) + rt.get('y_offset', {}).get(bid, 0)) % 360
                        if y:
                            x['y'] = y
                        else:
                            x.pop('y', None)
                    if rt.get('obj') and rt['obj'].get('tiles', 1) > 1:
                        alts = [copy]
                        for ti in range(1, rt['obj']['tiles'] if rt['obj'].get('wrap') else rt['obj']['tiles'] ** 2):
                            wjson(model_path(f'{copy}_{ti}'), dict(md, model=md['model'][:-4] + f'_{ti}.obj'))
                            alts.append(f'{copy}_{ti}')
                        bs['variants'][k] = [dict(x, model=c) for c in alts]
            wjson(path, bs)
            written[path] = bs
            item = a.json(f'assets/{ns}/models/item/{block}.json')
            if rt.get('item') and item and item.get('parent'):
                ip = item['parent']
                if ip not in copies:
                    copies[ip] = f"{NS}:block/retex/{ri}/{ip.replace(':', '/')}"
                    md = json.loads(json.dumps(a.json(model_path(ip))))
                    md['textures'] = {kk: (tex_ref(rt['textures'][kk]) if kk in rt['textures'] else vv) for kk, vv in md.get('textures', {}).items()}
                    wjson(model_path(copies[ip]), md)
                wjson(f'assets/{ns}/models/item/{block}.json', dict(item, parent=copies[ip]))
    for gs in cfg.get('glyphs', []):
        font, margin = gs['font'], gs.get('margin', 0)
        chars = ''.join(b['chars'] for b in gs['blocks'])
        masks = {c: Image.open(os.path.join(ROOT, 'src', 'glyphs', font, f'{c}.png')).convert('L') for c in chars}
        big = max(max(m.size) for m in masks.values())
        sc = (TILE - 2 * margin) / big
        hmax = round(max(m.size[1] for m in masks.values()) * sc)
        bottom = (TILE + hmax) // 2
        mat = next(x for x in cfg['textures'] if x['name'] == gs['material'])
        mgw, mgh = mat['grid']
        layers, _, _ = process(mat, (mgw * TILE, mgh * TILE))
        def glyph_alpha(m, size):
            k = (size - 2 * margin * size // TILE) / big
            g = m.resize((max(1, round(m.size[0] * k)), max(1, round(m.size[1] * k))), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
            hm = round(max(x.size[1] for x in masks.values()) * k)
            a = Image.new('L', (size, size), 0)
            a.paste(g, ((size - g.size[0]) // 2, (size + hm) // 2 - g.size[1]))
            return a
        for i, c in enumerate(chars):
            alpha = glyph_alpha(masks[c], TILE)
            tx, ty = (i * 7) % mgw, (i * 7 // mgw) % mgh
            box = (tx * TILE, ty * TILE, (tx + 1) * TILE, (ty + 1) * TILE)
            key = f"block/glyph/{font}/{gs['material']}/{c.lower()}"
            for sfx, img in layers.items():
                tile = img.crop(box).convert('RGBA')
                if sfx == '':
                    tile.putalpha(alpha)
                tile.save(out(f'assets/{NS}/textures/{key}{sfx}.png'))
            if gs.get('big', True):
                ctm = f"assets/minecraft/optifine/ctm/{NS}/glyph/{font}/{gs['material']}/{c.lower()}"
                big_a = glyph_alpha(masks[c], 2 * TILE)
                bx, by = (tx // 2 * 2) % mgw, (ty // 2 * 2) % mgh
                region = (bx * TILE, by * TILE, bx * TILE + 2 * TILE, by * TILE + 2 * TILE)
                quads = {'tl': (0, 0), 'tr': (1, 0), 'bl': (0, 1), 'br': (1, 1)}
                for sfx, img in layers.items():
                    reg = img.crop(region).convert('RGBA')
                    if sfx == '':
                        reg.putalpha(big_a)
                    for q, (qx, qy) in quads.items():
                        reg.crop((qx * TILE, qy * TILE, (qx + 1) * TILE, (qy + 1) * TILE)).save(out(f'{ctm}/{q}{sfx}.png'))
                    img.crop(box).convert('RGBA').save(out(f'{ctm}/n{sfx}.png')) if sfx else None
                tile = layers[''].crop(box).convert('RGBA'); tile.putalpha(alpha); tile.save(out(f'{ctm}/n.png'))
                names = ['n'] * 47
                names[13], names[15], names[37], names[39] = 'tl', 'tr', 'bl', 'br'
                with open(out(f'{ctm}/{c.lower()}.properties'), 'w', newline='\n') as f:
                    f.write(f"method=ctm\ntiles={' '.join(names)}\nmatchTiles={NS}:textures/{key}\nconnect=state\n")
            wjson(f'assets/{NS}/models/{key}.json', {'parent': 'block/block', 'textures': {'particle': f'{NS}:{key}', 'g': f'{NS}:{key}'},
                  'elements': [{'from': [0, 0, 15.9], 'to': [16, 16, 15.9], 'faces': {'north': {'uv': [0, 0, 16, 16], 'texture': '#g'}}}]})
        i = 0
        for b in gs['blocks']:
            ns, block = b['id'].split(':')
            props = b.get('states', [['toggle', len(b['chars'])]])
            combos = [{}]
            for p, n in reversed(props):
                combos = [dict(c, **{p: v}) for c in combos for v in range(1, n + 1)]
            variants = {}
            for c, combo in zip(b['chars'], combos):
                for f, y in (('north', 0), ('east', 90), ('south', 180), ('west', 270)):
                    k = ','.join(f'{p}={v}' for p, v in sorted(dict(combo, facing=f).items()))
                    m = f"{NS}:block/glyph/{font}/{gs['material']}/{c.lower()}"
                    variants[k] = {'model': m, 'y': y} if y else {'model': m}
            wjson(f'assets/{ns}/blockstates/{block}.json', {'variants': variants})
            ch = b['chars']
            wjson(f'assets/{ns}/models/item/{block}.json', {'parent': 'item/generated', 'textures': {'layer0': f"{NS}:block/glyph/{font}/{gs['material']}/{ch[0].lower()}"}})
            lang.setdefault(ns, {})[f'block.{ns}.{block}'] = f"{mat['display_name']} {'Digits' if ch.isdigit() else 'Letters'} {ch[0]}–{ch[-1]}"
            cutout.append(b['id'])
            tab.append(b['id'])
        print(f"glyphs {font}: {len(chars)} Zeichen, Skalierung {sc:.3f}")
    if cutout or translucent:
        base = a.raw('assets/minecraft/optifine/block.properties') or ''
        lines = [l for l in base.splitlines() if l.strip() and not l.lstrip().startswith('#')]
        for layer, ids in (('cutout', cutout), ('translucent', translucent)):
            if not ids:
                continue
            found = False
            for j, l in enumerate(lines):
                if l.startswith(f'layer.{layer}='):
                    lines[j] = (l + ' ' + ' '.join(ids)).replace('= ', '=')
                    found = True
            if not found:
                lines.append(f'layer.{layer}=' + ' '.join(ids))
        with open(out('assets/minecraft/optifine/block.properties'), 'w', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
    for d in cfg.get('doors', []):
        mat = next(x for x in cfg['textures'] if x['name'] == d['material'])
        px = lambda v: round(v * TILE / 16)
        fw, (wx0, wy0, wx1, wy1), bw = px(d['frame']), [px(v) for v in d['window']], px(d['bar'])
        frame = Image.new('L', (TILE, TILE), 0)
        frame.paste(255, (0, 0, fw, TILE))
        frame.paste(255, (TILE - fw, 0, TILE, TILE))
        parts = {}
        for part, ti in (('top', 1), ('bottom', 1 + mat['grid'][0])):
            fm = frame.copy()
            hole = Image.new('L', (TILE, TILE), 255)
            if part == 'top':
                fm.paste(255, (0, 0, TILE, fw))
                cx, cy = (wx0 + wx1) // 2, (wy0 + wy1) // 2
                hole.paste(0, (wx0, wy0, wx1, wy1))
                hole.paste(255, (cx - bw // 2, wy0, cx - bw // 2 + bw, wy1))
                hole.paste(255, (wx0, cy - bw // 2, wx1, cy - bw // 2 + bw))
                fm.paste(255, (cx - bw // 2, wy0, cx - bw // 2 + bw, wy1))
                fm.paste(255, (wx0, cy - bw // 2, wx1, cy - bw // 2 + bw))
            ns, tp = d[part].split(':')
            for sfx in ('', '_n', '_s'):
                img = Image.open(out(f"assets/minecraft/optifine/ctm/{NS}/{d['material']}/{ti}{sfx}.png")).convert('RGBA')
                if sfx == '':
                    img = Image.composite(img.point(lambda v: round(v * d['shade'])).convert('RGBA'), img, fm)
                    img.putalpha(ImageChops.multiply(img.split()[3], hole))
                    parts[part] = img
                img.save(out(f'assets/{ns}/textures/{tp}{sfx}.png'))
        icon = Image.new('RGBA', (TILE, TILE), (0, 0, 0, 0))
        tall = Image.new('RGBA', (TILE, 2 * TILE))
        tall.paste(parts['top'], (0, 0))
        tall.paste(parts['bottom'], (0, TILE))
        icon.paste(tall.resize((TILE // 2, TILE), Image.LANCZOS), (TILE // 4, 0))
        ins, ip = d['item'].split(':')
        icon.save(out(f'assets/{ins}/textures/{ip}.png'))
        lang.setdefault(d['block'].split(':')[0], {})[f"block.{d['block'].replace(':', '.')}"] = d['name']
        tab.append(d['block'])
    for p in glob.glob(os.path.join(ROOT, 'src', 'assets', '*', 'blockstates', '*.json')):
        tab.append(f"{p.split(os.sep)[-3]}:{os.path.basename(p)[:-5]}")
    for nid, nm in cfg.get('names', {}).items():
        lang.setdefault(nid.split(':')[0], {})[f"block.{nid.replace(':', '.')}"] = nm
    if cfg.get('creative_tab'):
        ct = cfg['creative_tab']
        wjson(f'assets/{NS}/polytone/creative_tab_modifiers/{NS}.json', {'create_new': True, 'name': {'text': ct['name']}, 'icon': ct['icon'],
              'additions': [{'items': list(dict.fromkeys(tab))}]})
    for ns, entries in lang.items():
        wjson(f'assets/{ns}/lang/en_us.json', dict(sorted(entries.items())))


if __name__ == '__main__':
    main()
