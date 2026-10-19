"""Cat feeder 3D-printed parts: two-pocket rotor (180 deg swing), housing with
MS18/SG90 servo mount + funnel, idler end cap.  Units: mm.
Rotor axis = X.  Servo is on the -X side.  Z is up.
"""
import os
import numpy as np
import trimesh
from manifold3d import Manifold, CrossSection

SEG = 128
OUT = os.path.join(os.path.dirname(__file__), "..", "stl")

# ---- servo (MS18 / SG90 class) -------------------------------------------
SERVO_L, SERVO_W = 22.8, 12.6      # body footprint
SHAFT_FROM_END = 5.1               # measured on the user's MS18 (2026-10-18)
EAR_SPACING = 27.8                 # ear screw hole spacing
CUT_CLR = 0.35                     # clearance per side for body cut-out

# ---- rotor / housing -----------------------------------------------------
R_ROTOR, L_ROTOR = 25.0, 40.0
R_BORE = 25.5
WALL = 3.0
R_OUT = R_BORE + WALL
X_FACE = -3.0                      # rotor servo-side face (nominal)
X_WALL_IN, X_WALL_OUT = -6.5, -10.5
X_END = X_FACE + L_ROTOR + 3.5     # open end of the bore (cap side)
PK_L = 32.0                        # pocket axial length
PK_X0 = X_FACE + (L_ROTOR - PK_L) / 2
XC = X_FACE + L_ROTOR / 2          # rotor centre along X


def box(x0, x1, y0, y1, z0, z1):
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def cyl_x(r, x0, x1, seg=SEG):
    return Manifold.cylinder(x1 - x0, r, circular_segments=seg).rotate([0, 90, 0]).translate([x0, 0, 0])


def hull(*ms):
    return Manifold.batch_hull(list(ms))


def slab(x0, x1, y0, y1, z):
    return box(x0, x1, y0, y1, z, z + 0.01)


# ------------------------------------------------------------------ rotor
def make_rotor():
    rotor = cyl_x(R_ROTOR, X_FACE, X_FACE + L_ROTOR)
    pocket = hull(cyl_x(9.0, PK_X0, PK_X0 + PK_L).translate([0, 0, 19.0]),
                  box(PK_X0, PK_X0 + PK_L, -13, 13, 24, 32))
    rotor = rotor - pocket - pocket.rotate([180, 0, 0])
    # servo-horn slot (double-arm horn) along Y on the servo face, 8 deep
    slot2d = CrossSection.batch_hull([
        CrossSection.circle(4.3, 48),
        CrossSection.circle(3.1, 48).translate([0, 15.5]),
        CrossSection.circle(3.1, 48).translate([0, -15.5])])
    slot = slot2d.extrude(8.0).rotate([0, 90, 0]).translate([X_FACE, 0, 0])
    hub = cyl_x(6.6, X_FACE - 1, X_FACE + 12)          # clears gear boss + screw head
    pin_hole = cyl_x(3.35, X_FACE + L_ROTOR - 10, X_FACE + L_ROTOR + 1, 48)
    return rotor - slot - hub - pin_hole


# ---------------------------------------------------------------- housing
def make_housing():
    tube = cyl_x(R_OUT, X_WALL_OUT, X_END)
    web = box(X_WALL_OUT, X_END, -18, 18, -R_OUT - 0.5, -16)
    base = box(X_WALL_OUT, X_END, -40, 40, -R_OUT - 3, -R_OUT)

    # funnel (outer solid), inlet = +/-45 deg of bore, 30 mm long
    ix0, ix1 = PK_X0 + 1, PK_X0 + PK_L - 1
    t = 3.0
    f_out = (hull(slab(ix0 - t, ix1 + t, -18 - t, 18 + t, 14),
                  slab(ix0 - t, ix1 + t, -30.2 - t, 30.2 + t, 32))
             + hull(slab(ix0 - t, ix1 + t, -30.2 - t, 30.2 + t, 32),
                    slab(ix0 - 15 - t, ix1 + 15 + t, -38 - t, 38 + t, 47))
             + box(ix0 - 15 - t, ix1 + 15 + t, -38 - t, 38 + t, 47, 57))
    f_in = (box(ix0, ix1, -18, 18, 8, 18.01)
            + hull(slab(ix0, ix1, -18, 18, 18), slab(ix0, ix1, -30.2, 30.2, 32))
            + hull(slab(ix0, ix1, -30.2, 30.2, 32), slab(ix0 - 15, ix1 + 15, -38, 38, 47))
            + box(ix0 - 15, ix1 + 15, -38, 38, 46.99, 60))

    h = tube + web + base + f_out
    h = h - cyl_x(R_BORE, X_WALL_IN, X_END + 1) - f_in
    # flat-topped teardrop roof over the bore ends -> prints without supports
    k = R_BORE * 0.7071                      # 45 deg point on the bore
    zt = R_OUT - 1.2                         # flat top, keeps 1.2 mm skin
    yt = 2 * k - zt
    # 2D (u, v) = (-z, y); extrude along w, rotate so w -> X
    roof = CrossSection([[(-(k - 0.5), -k), (-(k - 0.5), k), (-zt, yt), (-zt, -yt)]])
    roof = roof.extrude(X_END + 1 - X_WALL_IN).rotate([0, 90, 0]).translate([X_WALL_IN, 0, 0])
    h = h - roof

    # outlet (bottom), +/-36 deg, 34 long
    h = h - box(PK_X0 - 1, PK_X0 + PK_L + 1, -15, 15, -45, -8)

    # servo body cut-out through the end wall; shaft on the rotor axis
    yc = -(SERVO_L / 2 - SHAFT_FROM_END)
    h = h - box(X_WALL_OUT - 1, X_WALL_IN + 1,
                yc - SERVO_L / 2 - CUT_CLR, yc + SERVO_L / 2 + CUT_CLR,
                -SERVO_W / 2 - CUT_CLR, SERVO_W / 2 + CUT_CLR)
    for s in (-1, 1):                                  # 1.8 mm slots, -0.3/+1.0 along Y
        y0 = yc + s * EAR_SPACING / 2
        h = h - hull(cyl_x(0.9, X_WALL_OUT - 1, X_WALL_IN + 1, 24).translate([0, y0 - s * 0.3, 0]),
                     cyl_x(0.9, X_WALL_OUT - 1, X_WALL_IN + 1, 24).translate([0, y0 + s * 1.0, 0]))

    # M3 mounting holes in the base
    for x in (X_WALL_OUT + 5, X_END - 5):
        for y in (-34, 34):
            h = h - Manifold.cylinder(20, 1.7, circular_segments=32).translate([x, y, -R_OUT - 10])
    return h


# --------------------------------------------------------------- end cap
def make_cap():
    x0 = X_FACE + L_ROTOR + 0.5                      # inner face of the plug
    plug = cyl_x(R_BORE - 0.25, x0, X_END)
    flange = cyl_x(R_BORE + 2.0, X_END, X_END + 3)
    pin = cyl_x(3.0, x0 - 9, x0 + 0.5, 48)
    return plug + flange + pin


def save(m, name, rot=None):
    mesh = m.to_mesh()
    tm = trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3],
                         faces=np.asarray(mesh.tri_verts), process=True)
    if rot is not None:
        tm.apply_transform(rot)
    tm.apply_translation(-tm.bounds[0])              # sit on the bed at origin
    os.makedirs(OUT, exist_ok=True)
    tm.export(os.path.join(OUT, name))
    print(f"{name}: {np.round(tm.extents, 1)} mm, volume {tm.volume / 1000:.1f} cm3, "
          f"watertight={tm.is_watertight}")
    return tm


if __name__ == "__main__":
    ry = trimesh.transformations.rotation_matrix
    rotor = make_rotor()
    housing = make_housing()
    cap = make_cap()
    # print orientations: rotor & cap upright (axis vertical), housing base down
    save(rotor, "rotor.stl", ry(-np.pi / 2, [0, 1, 0]))       # servo face on bed
    save(housing, "housing.stl")
    save(cap, "end_cap.stl", ry(np.pi / 2, [0, 1, 0]))
    # assembly check
    print("rotor/housing overlap cm3:", round((rotor ^ housing).volume() / 1000, 3))
    print("rotor/cap overlap cm3:", round((rotor ^ cap).volume() / 1000, 3))
    print("cap/housing overlap cm3:", round((cap ^ housing).volume() / 1000, 3))
    pk = hull(cyl_x(9.0, PK_X0, PK_X0 + PK_L).translate([0, 0, 19.0]),
              box(PK_X0, PK_X0 + PK_L, -13, 13, 24, 32)) ^ cyl_x(R_ROTOR, X_FACE, X_FACE + L_ROTOR)
    print("pocket volume mL:", round(pk.volume() / 1000, 1))
    trimesh.util.concatenate([
        trimesh.Trimesh(np.asarray(m.to_mesh().vert_properties)[:, :3], np.asarray(m.to_mesh().tri_verts))
        for m in (rotor, housing, cap)]).export(os.path.join(os.path.dirname(__file__), "assembly_preview.stl"))
