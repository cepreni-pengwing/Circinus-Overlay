import glob, json, os, random, re, shutil, sys, zipfile, zlib
from PIL import Image, ImageChops, ImageFilter, ImageMath, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = 'circinus'
TILE = 32
GENERATED = [f'assets/{NS}', 'assets/conquest', 'assets/minecraft']
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

    def list(self, prefix):
        return sorted({x for n in self.names for x in n if x.startswith(prefix)})


def sources(argv):
    jar = argv[1] if len(argv) > 1 else glob.glob(os.path.join(LIB, 'ConquestReforged*.jar'))[0]
    acrp = argv[2] if len(argv) > 2 else (glob.glob(os.path.join(LIB, 'ACRP*.zip')) or [None])[0]
    return [p for p in (acrp, jar) if p]


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


def unlock(elements):
    out = json.loads(json.dumps(elements))
    for el in out:
        inside = all(0 <= c <= 16 for c in el.get('from', []) + el.get('to', []))
        if inside and el.get('rotation', {}).get('angle', 0) == 0:
            for face in el.get('faces', {}).values():
                face.pop('uv', None)
                face.pop('rotation', None)
    return out


def fix_uv(a, d, done):
    if 'elements' in d:
        d['elements'] = unlock(d['elements'])
        return
    p = d.get('parent')
    if not p or p.startswith('builtin/'):
        return
    pid = p if ':' in p else 'minecraft:' + p
    fixed = f"{NS}:block/uv/{pid.replace(':', '/')}"
    if pid not in done:
        pd = a.json(model_path(pid)) or (vanilla(pid) if pid in VANILLA else None)
        if pd is None:
            return
        pd = json.loads(json.dumps(pd))
        fix_uv(a, pd, done)
        wjson(model_path(fixed), pd)
        done.add(pid)
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
    y, py, d8, e, paint = analyse(rgb)
    noise = tile_noise(size, t.get('erosion_cells', 6), zlib.crc32(t['name'].encode()))
    thr = pct(noise, 1 - t.get('erosion', 0.12))
    k = noise.point(lambda v: max(0, min(255, (v - thr) * 4)))
    w = ImageMath.lambda_eval(lambda a: a['e'] * a['k'] / 255 * 0.85, e=F(e), k=F(k)).convert('L')
    rust = None
    if t.get('rust_asset'):
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
    nrm.putalpha(255)
    _, rough, metal = arm.split()
    sm = t.get('smoothness', 1.0)
    spec = Image.merge('RGBA', (ImageOps.invert(rough).point(lambda v: round(v * sm)), metal, Image.new('L', size, 0), Image.new('L', size, 255)))
    return {'': diffuse, '_n': nrm, '_s': spec}, e, w


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


def main():
    cfg = json.load(open(os.path.join(ROOT, 'src/mappings.json'), encoding='utf-8'))
    a = Assets(sources(sys.argv))
    for g in GENERATED:
        shutil.rmtree(os.path.join(ROOT, g), ignore_errors=True)
    for t in cfg['textures']:
        t.setdefault('contrast', cfg.get('contrast', 1.0))
    done = set()
    lang = {}
    for t in cfg['textures']:
        name, (gw, gh) = t['name'], t['grid']
        tex_id = f'{NS}:block/{name}'
        layers, e, w = process(t, (gw * TILE, gh * TILE))
        write_layers(layers, w if t.get('rust') else ImageOps.invert(e), name, gw, gh)
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
                        d['textures'] = {kk: (tex_id if v in base else v) for kk, v in d['textures'].items()}
                        fix_uv(la, d, done)
                        wjson(model_path(m), d)
                        n_models += 1
                n_blocks += 1
                if t.get('display_name'):
                    suffix = bn[len(block):].replace('_', ' ').title()
                    lang.setdefault(ns, {})[f'block.{ns}.{bn}'] = t['display_name'] + suffix
        print(f'{name}: {gw}x{gh}, {n_blocks} Block-IDs, {n_models} Models')


    cutout = []
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
            key = f'block/glyph/{font}/{c.lower()}'
            for sfx, img in layers.items():
                tile = img.crop(box).convert('RGBA')
                if sfx == '':
                    tile.putalpha(alpha)
                tile.save(out(f'assets/{NS}/textures/{key}{sfx}.png'))
            if gs.get('big', True):
                ctm = f'assets/minecraft/optifine/ctm/{NS}/glyph/{font}/{c.lower()}'
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
                    variants[k] = {'model': f'{NS}:block/glyph/{font}/{c.lower()}', 'y': y} if y else {'model': f'{NS}:block/glyph/{font}/{c.lower()}'}
            wjson(f'assets/{ns}/blockstates/{block}.json', {'variants': variants})
            cutout.append(b['id'])
        print(f"glyphs {font}: {len(chars)} Zeichen, Skalierung {sc:.3f}")
    if cutout:
        base = a.raw('assets/minecraft/optifine/block.properties') or ''
        lines = [l for l in base.splitlines() if l.strip() and not l.lstrip().startswith('#')]
        found = False
        for j, l in enumerate(lines):
            if l.startswith('layer.cutout='):
                lines[j] = (l + ' ' + ' '.join(cutout)).replace('= ', '=')
                found = True
        if not found:
            lines.append('layer.cutout=' + ' '.join(cutout))
        with open(out('assets/minecraft/optifine/block.properties'), 'w', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
    for ns, entries in lang.items():
        wjson(f'assets/{ns}/lang/en_us.json', dict(sorted(entries.items())))


if __name__ == '__main__':
    main()
