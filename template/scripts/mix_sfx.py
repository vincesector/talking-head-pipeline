#!/usr/bin/env python3
"""Mix plan.json's sfx events onto an existing render without re-rendering the picture.

    mix_sfx.py <project> <render_in.mp4> <render_out.mp4>

Same result as a Remotion render with the sfx events (linear volume, same start frames), in seconds
instead of minutes: video stream copied, audio re-encoded once.
"""
import json, subprocess, sys

proj, src, dst = sys.argv[1:4]
plan = json.load(open(f"{proj}/remotion/plan.json"))
fps = plan.get("fps", 30)
sfx = [e for e in plan["events"] if e["type"] == "sfx"]
cmd = ["ffmpeg", "-v", "error", "-y", "-i", src]
parts, labels = [], []
for i, e in enumerate(sfx, 1):
    cmd += ["-i", f"{proj}/remotion/public/{e['src']}"]
    ms = round(e["at"] / fps * 1000)
    parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={e.get('volume', 0.04)},adelay={ms}|{ms}[s{i}]")
    labels.append(f"[s{i}]")
parts.append(f"[0:a]aresample=48000,aformat=channel_layouts=stereo[v0]")
parts.append(f"[v0]{''.join(labels)}amix=inputs={len(sfx) + 1}:duration=first:normalize=0[a]")
cmd += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", dst]
subprocess.run(cmd, check=True)
print(f"{dst}: {len(sfx)} sfx mixed")
