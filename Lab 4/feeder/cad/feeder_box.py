"""Laser-cut enclosure + hopper tube for the cat feeder (Boxes.py).
Inner box 210 (W) x 170 (D) x 270 (H) mm, shelf at 105 mm.
The 3D-printed housing sits on the shelf, centred, servo to the left.
Usage: python feeder_box.py <thickness_mm> <out.svg>
"""
import sys
from boxes import Boxes, edges

W, D, H = 210.0, 170.0, 270.0
SHELF = 105.0                 # underside of shelf above inner floor
CX, CY = W / 2, D / 2         # outlet / hopper centre on the shelf
HOP_OUT_X, HOP_OUT_Y = 59.4, 75.4   # hopper tube outside size (fits printed collar)
HOP_H = 100.0
PI_X, PI_TOP = 80.0, 250.0    # Pi 5 board top-left corner on the front panel (inner coords)
CAM_Y = 28.0                  # webcam lens hole, distance from the front wall
DS = 150.0                    # shelf depth (centred, 10 mm cable gap front/back)
SY0 = (D - DS) / 2


class FeederBox(Boxes):
    def __init__(self):
        Boxes.__init__(self)
        self.addSettingsArgs(edges.FingerJointSettings)

    # --- holes, in each wall's inner coordinates (x right, y up) ---------
    def front_holes(self):
        self.rectangularHole(CX, 12 + 83 / 2, 150, 83, r=15)          # cat window
        # Pi 5 hangs on the inside, parts facing out, GPIO header on top.
        # Board top-left corner at (PI_X, PI_TOP); PiTFT glass ~ (24, 12) from it.
        self.rectangularHole(PI_X + 24, PI_TOP - 12, 34, 22, r=2)     # PiTFT window
        for dx in (3.5, 61.5):                                        # Pi 5 M2.5 holes
            for dz in (3.5, 52.5):
                self.hole(PI_X + dx, PI_TOP - dz, d=2.8)

    def back_holes(self):
        for x in (40, W - 40):                                        # USB-C cables
            self.rectangularHole(x, SHELF + 25, 30, 16, r=3)
        for i in range(5):                                            # vents for the Pi
            self.rectangularHole(CX, 205 + i * 10, 60, 4, r=2)

    def side_holes(self):
        self.fingerHolesAt(SY0, SHELF + self.thickness / 2, DS, 0)   # shelf slots

    def side_holes_speaker(self):
        self.side_holes()
        for i in (-1, 0, 1):                                          # speaker grille
            for j in (-1, 0, 1):
                self.hole(D / 2 + 9 * i, SHELF + 30 + 9 * j, d=4.5)

    def top_holes(self):
        self.rectangularHole(CX, CY, HOP_OUT_X + 1.6, HOP_OUT_Y + 1.6, r=2)   # hopper

    def shelf_holes(self):
        ox, cy, cam = CX - 17.0, CY - SY0, CAM_Y - SY0                # shelf-local Y
        self.rectangularHole(CX, cy, 38, 34)                          # kibble outlet
        for x in (ox - 5.5, ox + 35.5):                               # M3 housing mount
            for y in (cy - 34, cy + 34):
                self.hole(x, y, d=3.4)
        self.hole(CX, cam, d=5)                                       # webcam lens, looks down
        self.rectangularHole(W - 35, cam, 15, 15)                     # APDS-9960 window

    def render(self):
        t = self.thickness
        sheet = str(self.sheet)
        if sheet == "1":    # front + back
            self.rectangularWall(W, H, "FFFF", callback=[self.front_holes], move="right")
            self.rectangularWall(W, H, "FFFF", callback=[self.back_holes])
        elif sheet == "2":  # two sides + 2 narrow hopper walls
            self.rectangularWall(D, H, "FfFf", callback=[self.side_holes_speaker], move="right")
            self.rectangularWall(D, H, "FfFf", callback=[self.side_holes], move="right")
            ix = HOP_OUT_X - 2 * t
            self.rectangularWall(ix, HOP_H, "eFeF", move="up")
            self.rectangularWall(ix, HOP_H, "eFeF")
        elif sheet == "3a":  # top + bottom
            self.rectangularWall(W, D, "ffff", callback=[self.top_holes], move="right")
            self.rectangularWall(W, D, "ffff")
        elif sheet == "3b":  # shelf only
            self.rectangularWall(W, DS, "efef", callback=[self.shelf_holes])
        elif sheet in ("3c", "3d"):  # one wide hopper wall
            self.rectangularWall(HOP_OUT_Y - 2 * t, HOP_H, "efef")
        else:               # row 1: shelf + 2 wide hopper walls; row 2: top + bottom
            iy = HOP_OUT_Y - 2 * t
            self.rectangularWall(W, DS, "efef", callback=[self.shelf_holes], move="right")
            self.rectangularWall(iy, HOP_H, "efef", move="right")
            self.rectangularWall(iy, HOP_H, "efef", move="right")
            self.rectangularWall(iy, HOP_H, "efef", move="left only")
            self.rectangularWall(iy, HOP_H, "efef", move="left only")
            self.rectangularWall(W, DS, "efef", move="left only")
            self.rectangularWall(W, DS, "efef", move="up only")
            self.rectangularWall(W, D, "ffff", callback=[self.top_holes], move="right")
            self.rectangularWall(W, D, "ffff")                                 # bottom


if __name__ == "__main__":
    thickness, out = sys.argv[1], sys.argv[2]
    b = FeederBox()
    b.sheet = sys.argv[3]
    b.parseArgs([f"--thickness={thickness}", "--labels=0", "--reference=0", "--burn=0.1"])
    b.open()
    b.render()
    data = b.close()
    with open(out, "wb") as f:
        f.write(data.getvalue())
    print("wrote", out)
