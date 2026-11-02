"""
Turn the frames overnight.py saved in lapse/ into a time-lapse video with ffmpeg.

    python lapse.py                  # lapse/*.jpg -> lapse.mp4 at 10 frames per second
    python lapse.py --fps 6          # play it slower

Half an hour at one frame every 10 s is 180 frames, about 18 s of video at 10 fps.
The frames show where the camera points, so delete lapse/ with snaps/ after the demo.
"""
import argparse
import glob
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--fps", type=float, default=10, help="frames per second of the video")
parser.add_argument("--out", default="lapse.mp4")
args = parser.parse_args()

frames = sorted(glob.glob("lapse/*.jpg"))
if not frames:
    raise SystemExit("no frames in lapse/: run overnight.py --lapse 10 first")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(args.fps),
                "-pattern_type", "glob", "-i", "lapse/*.jpg",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", args.out], check=True)   # H.264 so it plays on a Mac and on GitHub
print(f"{len(frames)} frames -> {args.out} ({len(frames) / args.fps:.0f} s)")
