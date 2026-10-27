"""Product mockups of the hyperboloid with Blender (Cycles). Usage: python mockup.py SHOT [samples]
Every shot is a digital render; the listing says so."""
import sys, math, bpy
from mathutils import Vector

SHOT = sys.argv[1]; SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 96
HERE = "/tmp/claude-0/-home-user/661d7c00-130c-5805-82d8-1f86fe22eb52/scratchpad/p3d/"
MM = 0.001

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
sc.view_settings.exposure = float(sys.argv[4]) if len(sys.argv) > 4 else -4.5
sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Punchy"


def node_mat(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    return m, m.node_tree.nodes, m.node_tree.links, m.node_tree.nodes["Principled BSDF"]


def layer_lines(nodes, links, bsdf, pitch=0.2, strength=0.25):
    """FDM layer lines: a fine ripple along the print height (object space, mm)."""
    tc = nodes.new("ShaderNodeTexCoord"); sep = nodes.new("ShaderNodeSeparateXYZ")
    mul = nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 2 * math.pi / pitch
    sin = nodes.new("ShaderNodeMath"); sin.operation = "SINE"
    bump = nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = 0.00004
    links.new(tc.outputs["Object"], sep.inputs[0]); links.new(sep.outputs["Z"], mul.inputs[0])
    links.new(mul.outputs[0], sin.inputs[0]); links.new(sin.outputs[0], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return sep


def pla(name, color, metallic=0.0, rough=0.5, coat=0.0):
    m, n, l, b = node_mat(name)
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough; b.inputs["Coat Weight"].default_value = coat
    layer_lines(n, l, b)
    return m


def silk_rainbow():
    m, n, l, b = node_mat("silk rainbow")
    b.inputs["Metallic"].default_value = 0.35; b.inputs["Roughness"].default_value = 0.25
    sep = layer_lines(n, l, b)
    div = n.new("ShaderNodeMath"); div.operation = "DIVIDE"; div.inputs[1].default_value = 103.0
    ramp = n.new("ShaderNodeValToRGB"); cr = ramp.color_ramp
    stops = [(0.0, (0.85, 0.25, 0.12)), (0.2, (0.95, 0.7, 0.1)), (0.4, (0.2, 0.75, 0.3)),
             (0.6, (0.1, 0.5, 0.85)), (0.8, (0.45, 0.2, 0.8)), (1.0, (0.85, 0.2, 0.5))]
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
    for p, c in stops[1:-1]:
        e = cr.elements.new(p); e.color = (*c, 1)
    l.new(sep.outputs["Z"], div.inputs[0]); l.new(div.outputs[0], ramp.inputs[0])
    l.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def wood():
    m, n, l, b = node_mat("walnut")
    tc = n.new("ShaderNodeTexCoord"); mp = n.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1, 0.12, 1)
    noise = n.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 3; noise.inputs["Detail"].default_value = 8
    wave = n.new("ShaderNodeTexWave"); wave.inputs["Scale"].default_value = 6; wave.inputs["Distortion"].default_value = 14
    wave.inputs["Detail"].default_value = 8; wave.inputs["Detail Scale"].default_value = 2.5
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.10, 0.05, 0.025, 1); ramp.color_ramp.elements[1].color = (0.25, 0.13, 0.06, 1)
    l.new(tc.outputs["Object"], mp.inputs[0]); l.new(mp.outputs[0], wave.inputs[0])
    wave.bands_direction = "X"
    l.new(wave.outputs["Fac"], ramp.inputs[0]); l.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.42
    return m


def flat(name, color, rough=0.8):
    m, n, l, b = node_mat(name)
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Roughness"].default_value = rough
    return m


def stl(path, mat, loc=(0, 0, 0), rot=(0, 0, 0)):
    bpy.ops.wm.stl_import(filepath=HERE + path)
    o = bpy.context.selected_objects[0]
    o.scale = (MM,) * 3; o.location = loc; o.rotation_euler = rot
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return o


def box(size, loc, mat, rot_z=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object; o.scale = size; o.rotation_euler[2] = rot_z
    o.data.materials.append(mat)
    m = o.modifiers.new("b", "BEVEL"); m.width = 0.0008; m.segments = 3
    return o


def book(w, d, h, loc, cover, rot_z=0.0):
    x, y, z = loc
    box((w, d, h), (x, y, z + h / 2), cover, rot_z)
    pages = flat("pages", (0.86, 0.82, 0.72), 0.9)
    box((w - 0.006, d - 0.004, h - 0.004), (x + 0.003 * math.cos(rot_z), y + 0.003 * math.sin(rot_z), z + h / 2), pages, rot_z)


def area(name, loc, size, power, color=(1, 0.96, 0.9)):
    bpy.ops.object.light_add(type="AREA", location=loc)
    o = bpy.context.object; o.data.size = size; o.data.energy = power; o.data.color = color
    d = Vector((0, 0, 0.05)) - o.location; o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return o


def camera(loc, target, lens=70):
    bpy.ops.object.camera_add(location=loc)
    c = bpy.context.object; c.data.lens = lens
    c.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    c.data.dof.use_dof = True; c.data.dof.focus_distance = (Vector(target) - Vector(loc)).length
    c.data.dof.aperture_fstop = 5.6
    sc.camera = c


def world(color=(0.9, 0.85, 0.78), strength=0.35):
    w = bpy.data.worlds.new("w"); w.use_nodes = True
    bg = w.node_tree.nodes["Background"]; bg.inputs[0].default_value = (*color, 1); bg.inputs[1].default_value = strength
    sc.world = w


def sweep(color):
    """Seamless studio paper: floor curving up into a wall."""
    bpy.ops.mesh.primitive_plane_add(size=1)
    o = bpy.context.object
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.delete(type="VERT"); bpy.ops.object.mode_set(mode="OBJECT")
    import bmesh
    bm = bmesh.new(); prof = []
    for i in range(40):
        a = i / 39 * math.pi / 2
        prof.append((0.25 - 0.25 * math.cos(a) if False else 0, 0.3 - 0.25 * math.sin(a) * 0 , 0))
    pts = [(-1.0 + 0.05 * i, 0) for i in range(0)]
    ys, zs = [], []
    for i in range(60):            # floor from y=-1.0 to 0.3, then a curve of radius 0.25 up to a wall
        ys.append(-1.0 + 1.3 * i / 59); zs.append(0)
    for i in range(1, 30):
        a = i / 29 * math.pi / 2; ys.append(0.3 + 0.25 * math.sin(a)); zs.append(0.25 - 0.25 * math.cos(a))
    for i in range(1, 20):
        ys.append(0.55); zs.append(0.25 + 1.0 * i / 19)
    rows = []
    for x in (-1.5, 1.5):
        rows.append([bm.verts.new((x, y, z)) for y, z in zip(ys, zs)])
    for i in range(len(ys) - 1):
        bm.faces.new((rows[0][i], rows[1][i], rows[1][i + 1], rows[0][i + 1]))
    bm.to_mesh(o.data); bm.free()
    o.data.materials.append(flat("paper", color, 0.9))
    bpy.ops.object.shade_smooth()


def height_ramp(stops_file, top_mm, metallic=0.35, rough=0.28):
    """Colour by print height: each layer comes from one stretch of a gradient filament."""
    import json
    m, n, l, b = node_mat("gradient by height")
    b.inputs["Metallic"].default_value = metallic; b.inputs["Roughness"].default_value = rough
    sep = layer_lines(n, l, b)
    div = n.new("ShaderNodeMath"); div.operation = "DIVIDE"; div.inputs[1].default_value = top_mm
    ramp = n.new("ShaderNodeValToRGB"); cr = ramp.color_ramp
    stops = json.load(open(HERE + stops_file))
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
    for pos, c in stops[1:-1]:
        cr.elements.new(pos).color = (*c, 1)
    l.new(sep.outputs["Z"], div.inputs[0]); l.new(div.outputs[0], ramp.inputs[0])
    l.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


GOLD = lambda: pla("gold PLA", (0.80, 0.55, 0.20), metallic=0.75, rough=0.32)
BLACK = lambda: pla("matte black PLA", (0.018, 0.018, 0.02), rough=0.62)
LATTICE, PLINTH, ONE = "hyperboloid_lattice.stl", "plinth_engraved.stl", "hyperboloid_strong.stl"
H = 0.110                      # height of the assembled piece, m

if SHOT == "hero":             # gold and black on a walnut desk next to a stack of books
    world((0.95, 0.88, 0.78), 0.25)
    bpy.ops.mesh.primitive_plane_add(size=3); bpy.context.object.data.materials.append(wood())
    bpy.ops.mesh.primitive_plane_add(size=3, location=(0, 0.45, 1.5), rotation=(math.pi / 2, 0, 0))
    bpy.context.object.data.materials.append(flat("plaster", (0.72, 0.66, 0.58), 0.95))
    stl(PLINTH, BLACK()); stl(LATTICE, GOLD(), loc=(0, 0, 0.004))
    book(0.16, 0.24, 0.03, (-0.17, 0.05, 0), flat("green cloth", (0.06, 0.16, 0.10), 0.8), 0.25)
    book(0.15, 0.22, 0.026, (-0.165, 0.055, 0.03), flat("red cloth", (0.32, 0.05, 0.04), 0.8), 0.12)
    book(0.14, 0.21, 0.022, (-0.16, 0.05, 0.056), flat("blue cloth", (0.05, 0.08, 0.2), 0.8), 0.3)
    area("key", (-0.5, -0.45, 0.6), 0.6, 120); area("fill", (0.6, -0.4, 0.3), 0.8, 35)
    area("rim", (0.25, 0.35, 0.45), 0.3, 40, (1, 0.9, 0.75))
    camera((0.24, -0.33, 0.14), (-0.04, 0.02, H * 0.45), 60)
elif SHOT in ("studio", "rainbow"):
    world((1, 1, 1), 0.4); sweep((0.86, 0.83, 0.78))
    if SHOT == "studio":
        stl(PLINTH, BLACK()); stl(LATTICE, GOLD(), loc=(0, 0, 0.004))
    else:
        stl(ONE, silk_rainbow())
    area("key", (-0.4, -0.35, 0.5), 0.7, 110); area("fill", (0.45, -0.3, 0.25), 0.8, 40)
    area("top", (0.0, 0.1, 0.6), 0.5, 40)
    camera((0.0, -0.40, 0.13), (0, 0, H * 0.47), 85)
elif SHOT == "underside":      # the plinth turned over, lit low so the cut reads
    world((1, 0.95, 0.9), 0.15)
    bpy.ops.mesh.primitive_plane_add(size=3); bpy.context.object.data.materials.append(wood())
    stl(PLINTH, BLACK(), loc=(0, 0, 0.0069), rot=(0, math.pi, 0))
    area("rake", (-0.35, 0.12, 0.09), 0.25, 110); area("soft", (0.2, -0.3, 0.5), 0.6, 40)
    camera((0.0, -0.16, 0.21), (0, 0, 0.007), 85)
    sc.camera.data.dof.aperture_fstop = 16
elif SHOT == "parts":          # the two pieces side by side, before they fit together
    world((1, 1, 1), 0.4); sweep((0.86, 0.83, 0.78))
    stl(PLINTH, BLACK(), loc=(0.055, 0.02, 0)); stl(LATTICE, GOLD(), loc=(-0.05, -0.01, 0))
    area("key", (-0.4, -0.35, 0.5), 0.7, 110); area("fill", (0.45, -0.3, 0.25), 0.8, 40)
    camera((0.0, -0.38, 0.17), (0, 0, 0.04), 70)

elif SHOT in ("spin-gold", "spin-rainbow"):   # seamless loop: the lattice repeats every 360/18 degrees
    world((1, 1, 1), 0.4); sweep((0.86, 0.83, 0.78))
    bpy.ops.object.empty_add(location=(0, 0, 0)); pivot = bpy.context.object
    parts = [stl(PLINTH, BLACK()), stl(LATTICE, GOLD(), loc=(0, 0, 0.004))] if SHOT == "spin-gold" else [stl(ONE, silk_rainbow())]
    for o in parts:
        o.parent = pivot
    frames = 60
    area("key", (-0.4, -0.35, 0.5), 0.7, 110); area("fill", (0.45, -0.3, 0.25), 0.8, 40)
    area("top", (0.0, 0.1, 0.6), 0.5, 40)
    camera((0.0, -0.40, 0.13), (0, 0, H * 0.47), 85)
    first = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    last = int(sys.argv[6]) if len(sys.argv) > 6 else frames
    sc.render.use_persistent_data = True
    for f in range(first, last + 1):           # constant speed: 20 degrees over the loop, last frame excluded
        pivot.rotation_euler[2] = math.radians(20) * (f - 1) / frames
        sc.render.filepath = HERE + f"mock/{SHOT}/f{f:04d}.png"
        bpy.ops.render.render(write_still=True)
    raise SystemExit

elif SHOT == "horn-desk":
    world((0.95, 0.88, 0.78), 0.25)
    bpy.ops.mesh.primitive_plane_add(size=3); bpy.context.object.data.materials.append(wood())
    bpy.ops.mesh.primitive_plane_add(size=3, location=(0, 0.45, 1.5), rotation=(math.pi / 2, 0, 0))
    bpy.context.object.data.materials.append(flat("plaster", (0.72, 0.66, 0.58), 0.95))
    stl("gabriel_plinth_light.stl", BLACK())
    stl("gabriel_horn_hollow_light.stl", GOLD(), loc=(0, 0, 0.0045))
    book(0.16, 0.24, 0.03, (-0.2, 0.08, 0), flat("green cloth", (0.06, 0.16, 0.10), 0.8), 0.25)
    book(0.15, 0.22, 0.026, (-0.195, 0.085, 0.03), flat("red cloth", (0.32, 0.05, 0.04), 0.8), 0.12)
    area("key", (-0.5, -0.45, 0.6), 0.6, 120); area("fill", (0.6, -0.4, 0.3), 0.8, 35)
    area("rim", (0.25, 0.35, 0.45), 0.3, 40, (1, 0.9, 0.75))
    camera((0.13, -0.21, 0.11), (-0.012, 0.004, 0.045), 55)
elif SHOT == "horn-spin":              # the whole piece turns once, so the engraved ring passes in front
    world((1, 1, 1), 0.4); sweep((0.86, 0.83, 0.78))
    bpy.ops.object.empty_add(location=(0, 0, 0)); pivot = bpy.context.object
    stl("gabriel_plinth_light.stl", BLACK()).parent = pivot
    stl("gabriel_horn_hollow_light.stl", height_ramp("linear_ramp.json", 97.2), loc=(0, 0, 0.0045)).parent = pivot
    area("key", (-0.4, -0.35, 0.5), 0.7, 110); area("fill", (0.45, -0.3, 0.25), 0.8, 40)
    area("top", (0.0, 0.1, 0.6), 0.5, 50)
    camera((0.0, -0.36, 0.20), (0, 0, 0.040), 70)
    frames = 96
    first = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    last = int(sys.argv[6]) if len(sys.argv) > 6 else frames
    sc.render.use_persistent_data = True
    for f in range(first, last + 1):
        pivot.rotation_euler[2] = math.tau * (f - 1) / frames
        sc.render.filepath = HERE + f"mock/{SHOT}/f{f:04d}.png"
        bpy.ops.render.render(write_still=True)
    raise SystemExit
elif SHOT == "horn-tunnel":           # the horn lifted off its plinth and tipped, to show the tunnel
    world((1, 1, 1), 0.4); sweep((0.86, 0.83, 0.78))
    stl("gabriel_plinth_light.stl", BLACK(), loc=(0.07, 0.03, 0))
    stl("gabriel_horn_hollow_light.stl", height_ramp("linear_ramp.json", 97.2), loc=(-0.035, 0.0, 0.045),
        rot=(math.radians(-115), 0, math.radians(15)))
    area("key", (-0.4, -0.35, 0.5), 0.7, 110); area("fill", (0.45, -0.3, 0.25), 0.8, 40)
    area("top", (0.0, 0.1, 0.6), 0.5, 50); area("in", (-0.05, -0.25, 0.05), 0.2, 25)
    camera((0.02, -0.36, 0.16), (0.0, 0.0, 0.035), 60)
elif SHOT in ("horn-rainbow", "horn-gold", "horn-top"):
    world((1, 1, 1), 0.4); sweep((0.86, 0.83, 0.78))
    stl("gabriel_plinth_light.stl", BLACK())
    horn_mat = GOLD() if SHOT == "horn-gold" else height_ramp("linear_ramp.json", 97.2)
    stl("gabriel_horn_hollow_light.stl", horn_mat, loc=(0, 0, 0.0045))
    area("key", (-0.4, -0.35, 0.5), 0.7, 110); area("fill", (0.45, -0.3, 0.25), 0.8, 40)
    area("top", (0.0, 0.1, 0.6), 0.5, 50)
    if SHOT == "horn-top":                 # the ring of text, seen from the front and above
        camera((0.0, -0.15, 0.11), (0, -0.035, 0.008), 70)
    else:
        camera((0.0, -0.44, 0.15), (0, 0, 0.047), 80)
elif SHOT.startswith("lookc-"):       # colour by height with a linear rainbow ramp
    world((1, 1, 1), 0.4); sweep((0.86, 0.83, 0.78))
    o = stl(SHOT[6:] + ".stl", height_ramp("linear_ramp.json", float(sys.argv[5]) if len(sys.argv) > 5 else 25.0))
    area("key", (-0.4, -0.35, 0.5), 0.7, 110); area("fill", (0.45, -0.3, 0.25), 0.8, 40)
    area("top", (0.0, 0.1, 0.6), 0.5, 50)
    if o.dimensions.z > 0.05:                      # a tall piece: studio framing
        camera((0.0, -0.40, 0.13), (0, 0, o.dimensions.z * 0.47), 85)
    else:
        camera((0.10, -0.24, 0.20), (0, 0.004, 0.006), 60)
elif SHOT.startswith("look-"):        # quick look at any STL: look-<name> renders <name>.stl in gold
    world((1, 1, 1), 0.4); sweep((0.86, 0.83, 0.78))
    name = SHOT[5:]
    o = stl(name + ".stl", GOLD())
    if o.dimensions.y > o.dimensions.x:
        o.rotation_euler[2] = math.pi / 2              # long side across the frame
    area("key", (-0.4, -0.35, 0.5), 0.7, 110); area("fill", (0.45, -0.3, 0.25), 0.8, 40)
    area("top", (0.0, 0.1, 0.6), 0.5, 40)
    camera((0.0, -0.30, 0.26), (0, 0, 0.012), 60)
elif SHOT in ("mandel-hero", "mandel-top", "mandel-sunset"):
    world((1, 1, 1), 0.4); sweep((0.86, 0.83, 0.78))
    ramp = "mandel_ramp_sunset.json" if SHOT == "mandel-sunset" else "mandel_ramp.json"
    stl("mandelbrot_light.stl", height_ramp(ramp, 27.75, metallic=0.0 if SHOT == "mandel-sunset" else 0.35,
                                            rough=0.6 if SHOT == "mandel-sunset" else 0.28))
    area("key", (-0.4, -0.35, 0.5), 0.7, 110); area("fill", (0.45, -0.3, 0.25), 0.8, 40)
    area("top", (0.0, 0.1, 0.6), 0.5, 50)
    if SHOT in ("mandel-hero", "mandel-sunset"):
        camera((0.12, -0.27, 0.17), (0, 0.004, 0.008), 60)
    else:
        camera((0.0, -0.10, 0.33), (0, 0.0, 0.0), 60)
elif SHOT == "mandel-desk":
    world((0.95, 0.88, 0.78), 0.25)
    bpy.ops.mesh.primitive_plane_add(size=3); bpy.context.object.data.materials.append(wood())
    bpy.ops.mesh.primitive_plane_add(size=3, location=(0, 0.45, 1.5), rotation=(math.pi / 2, 0, 0))
    bpy.context.object.data.materials.append(flat("plaster", (0.72, 0.66, 0.58), 0.95))
    stl("mandelbrot_light.stl", height_ramp("mandel_ramp.json", 27.75), rot=(0, 0, 0.35))
    book(0.16, 0.24, 0.03, (-0.2, 0.12, 0), flat("green cloth", (0.06, 0.16, 0.10), 0.8), 0.25)
    book(0.15, 0.22, 0.026, (-0.195, 0.125, 0.03), flat("red cloth", (0.32, 0.05, 0.04), 0.8), 0.12)
    area("key", (-0.5, -0.45, 0.6), 0.6, 120); area("fill", (0.6, -0.4, 0.3), 0.8, 35)
    area("rim", (0.25, 0.35, 0.45), 0.3, 40, (1, 0.9, 0.75))
    camera((0.14, -0.21, 0.14), (-0.005, 0.004, 0.008), 55)
elif SHOT == "mandel-spin":                 # one slow full turn, 96 frames
    world((1, 1, 1), 0.4); sweep((0.86, 0.83, 0.78))
    bpy.ops.object.empty_add(location=(0, 0, 0)); pivot = bpy.context.object
    stl("mandelbrot_light.stl", height_ramp("mandel_ramp.json", 27.75)).parent = pivot
    area("key", (-0.4, -0.35, 0.5), 0.7, 110); area("fill", (0.45, -0.3, 0.25), 0.8, 40)
    area("top", (0.0, 0.1, 0.6), 0.5, 50)
    camera((0.0, -0.26, 0.19), (0, 0.0, 0.006), 60)
    frames = 96
    first = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    last = int(sys.argv[6]) if len(sys.argv) > 6 else frames
    sc.render.use_persistent_data = True
    for f in range(first, last + 1):
        pivot.rotation_euler[2] = math.tau * (f - 1) / frames
        sc.render.filepath = HERE + f"mock/{SHOT}/f{f:04d}.png"
        bpy.ops.render.render(write_still=True)
    raise SystemExit
elif SHOT == "mandel-under":
    world((1, 0.95, 0.9), 0.15)
    bpy.ops.mesh.primitive_plane_add(size=3); bpy.context.object.data.materials.append(wood())
    stl("mandelbrot_light.stl", height_ramp("mandel_ramp.json", 27.75), loc=(0, 0, 0.0278), rot=(0, math.pi, 0))
    area("rake", (-0.35, 0.12, 0.09), 0.25, 110); area("soft", (0.2, -0.3, 0.5), 0.6, 40)
    camera((0.0, -0.17, 0.24), (0, 0, 0.026), 70)
    sc.camera.data.dof.aperture_fstop = 16

sc.render.filepath = HERE + f"mock/{SHOT}.png"
bpy.ops.render.render(write_still=True)
print("saved", sc.render.filepath)
