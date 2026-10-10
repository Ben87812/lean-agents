"""Capture post.html as images and a video: post-card.png, post-card-dark.png and post-replay.mp4.

    python bench/post_capture.py <work>/<tier>/post.html

Needs Playwright (pip install playwright) with Chrome or Edge installed, and
ffmpeg on the PATH for the MP4.
"""

import os
import pathlib
import shutil
import subprocess
import sys

from playwright.sync_api import sync_playwright

FPS = 30
HOLD = 3


def main():
    page_path = os.path.abspath(sys.argv[1])
    out = os.path.dirname(page_path)
    url = pathlib.Path(page_path).as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        for scheme, name in (("light", "post-card.png"), ("dark", "post-card-dark.png")):
            ctx = browser.new_context(viewport={"width": 1240, "height": 900}, device_scale_factor=2, color_scheme=scheme)
            page = ctx.new_page()
            page.goto(url)
            page.wait_for_load_state("networkidle")
            page.locator("#card").screenshot(path=os.path.join(out, name))
            ctx.close()
        # The replay is rendered frame by frame (renderAt), not screen-recorded, so no frame is dropped.
        frames = os.path.join(out, "frames-tmp")
        os.makedirs(frames, exist_ok=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5, color_scheme="light")
        page = ctx.new_page()
        page.goto(url + "#record")
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        seconds = page.evaluate("window.REPLAY_SECONDS")
        total = int(seconds * FPS)
        for i in range(total + 1):
            page.evaluate(f"renderAt({i / FPS})")
            page.screenshot(path=os.path.join(frames, f"{i:05d}.png"))
        ctx.close()
        browser.close()
    mp4 = os.path.join(out, "post-replay.mp4")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit(f"ffmpeg not found; the frames are in {frames}")
    # Hold the last frame for HOLD seconds so the result can be read.
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(frames, "%05d.png"),
                    "-vf", f"tpad=stop_mode=clone:stop_duration={HOLD},scale=1920:1080:flags=lanczos",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4],
                   check=True)
    shutil.rmtree(frames)
    for name in sorted(os.listdir(out)):
        if name.startswith("post-"):
            print(os.path.join(out, name))


if __name__ == "__main__":
    main()
