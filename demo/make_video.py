"""Render demo/demo.mp4 (about 75 s, 1280x720, H.264) from the committed build outputs.

Every number on screen is read from docs/metrics.json, and the terminal scene shows the real output of
`python -m nut build`, `python -m nut verify` and the unit tests, captured when this script runs.

Usage:  python demo/make_video.py [--dashboard-png PATH]   (needs ffmpeg on PATH; Pillow ships with matplotlib)
--dashboard-png is an optional full-page screenshot of docs/index.html (1280 px wide) for the scrolling scene.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import matplotlib
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H, FPS = 1280, 720, 30
DARK_BG, LIGHT_BG = (15, 23, 32), (255, 255, 255)
GREEN, WHITE, MUTED, INK = (0, 236, 151), (240, 244, 248), (150, 164, 178), (31, 41, 51)
FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
REPO_URL = "github.com/Raindess69/near-usage-thesis"
PAGES_URL = "raindess69.github.io/near-usage-thesis"


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSansMono" if mono else "DejaVuSans"
    return ImageFont.truetype(str(FONT_DIR / f"{name}{'-Bold' if bold else ''}.ttf"), size)


def wrap(draw: ImageDraw.ImageDraw, text: str, f, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=f) <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def text_block(draw, xy, text, f, fill, max_w, spacing=1.25) -> int:
    x, y = xy
    for line in wrap(draw, text, f, max_w):
        draw.text((x, y), line, font=f, fill=fill)
        y += int(f.size * spacing)
    return y


def pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}%"


def usd(x: float) -> str:
    return f"${x / 1e6:,.0f}M" if x >= 1e6 else f"${x / 1e3:,.0f}K"


class Video:
    def __init__(self, out: Path):
        self.proc = subprocess.Popen(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(out),
            ],
            stdin=subprocess.PIPE,
        )
        self.frames = 0

    def frame(self, im: Image.Image) -> None:
        self.proc.stdin.write(im.convert("RGB").tobytes())
        self.frames += 1

    def hold(self, im: Image.Image, seconds: float, bg=DARK_BG, fade: float = 0.35) -> None:
        n = int(seconds * FPS)
        nf = max(1, int(fade * FPS))
        base = Image.new("RGB", (W, H), bg)
        for i in range(n):
            a = min(1.0, (i + 1) / nf, (n - i) / nf)
            self.frame(im if a >= 1 else Image.blend(base, im, a))

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait()


def dark_slide() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), DARK_BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 6], fill=GREEN)
    d.text((60, H - 48), REPO_URL, font=font(20), fill=MUTED)
    d.text((W - 60 - d.textlength("NEAR HACKATHON - thesis track", font=font(20)), H - 48), "NEAR HACKATHON - thesis track", font=font(20), fill=MUTED)
    return im, d


def title_scene(v: Video, m: dict) -> None:
    im, d = dark_slide()
    d.text((60, 150), "OPEN-DATA INVESTMENT THESIS", font=font(26, bold=True), fill=GREEN)
    y = text_block(d, (60, 200), "Can NEAR usage pay for NEAR issuance?", font(64, bold=True), WHITE, 1100, 1.15)
    text_block(d, (60, y + 30), "Every number is computed from public data and can be rebuilt with one command.", font(30), MUTED, 1100)
    v.hold(im, 3.0)


def question_scene(v: Video, m: dict) -> None:
    iss = m["issuance"]
    im, d = dark_slide()
    d.text((60, 90), "The question", font=font(26, bold=True), fill=GREEN)
    y = 150
    for line in (
        f"NEAR mints about {iss['rpc_minted_per_day_near'] / 1e3:.0f}K new NEAR a day ({pct(iss['rpc_annualized_issuance'], 2)} a year), measured from block headers.",
        "Two things take NEAR back out: gas burn, and NEAR Intents revenue spent on buybacks.",
        "How much of issuance does usage actually pay for, and what would it take to pay for all of it?",
    ):
        y = text_block(d, (60, y), line, font(38), WHITE, 1150, 1.25) + 28
    v.hold(im, 5.5)


def run_capture(args: list[str]) -> list[str]:
    res = subprocess.run([sys.executable] + args, cwd=ROOT, capture_output=True, text=True)
    return [l for l in (res.stdout + res.stderr).splitlines() if l.strip()]


def terminal_scene(v: Video, m: dict) -> None:
    build = [l for l in run_capture(["-m", "nut", "build"]) if not l.startswith("done")]
    verify = [l for l in run_capture(["-m", "nut", "verify"]) if not l.startswith("done")]
    tests = [l for l in run_capture(["-m", "unittest", "discover", "-s", "tests"]) if l.startswith(("Ran", "OK", "FAILED"))]
    script = [("$ make build", True)] + [(l, False) for l in build] + [("$ make verify", True)] + [(l, False) for l in verify]
    script += [("$ make test", True)] + [(l, False) for l in tests]
    f, fh = font(22, mono=True), 31
    base, d = dark_slide()
    d.text((60, 40), "Rebuild and check everything offline from the committed raw snapshot", font=font(26, bold=True), fill=GREEN)
    box = (60, 90, W - 60, 640)
    d.rounded_rectangle(box, radius=12, fill=(8, 12, 18), outline=(48, 60, 72))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([box[0] + 16 + i * 24, box[1] + 14, box[0] + 30 + i * 24, box[1] + 28], fill=c)
    # timeline: commands type at 30 chars/s, output lines appear every 0.22 s
    events, t = [], 0.3
    for text, is_cmd in script:
        if is_cmd:
            for k in range(1, len(text) + 1):
                events.append((t, len(events), text[:k], True))
                t += 1 / 30
            t += 0.25
        else:
            events.append((t, len(events), text, False))
            t += 0.22
    total = t + 2.0
    n = int(total * FPS)
    for i in range(n):
        now = i / FPS
        lines: dict[int, tuple[str, bool]] = {}
        row = -1
        last_cmd = None
        for (et, _, text, is_cmd) in events:
            if et > now:
                break
            if is_cmd:
                if last_cmd is None or not text.startswith(last_cmd) or len(text) == 1:
                    row += 1
                last_cmd = text
            else:
                row += 1
                last_cmd = None
            lines[row] = (text, is_cmd)
        im = base.copy()
        dd = ImageDraw.Draw(im)
        rows = sorted(lines)
        visible = rows[-16:]
        for j, r in enumerate(visible):
            text, is_cmd = lines[r]
            dd.text((box[0] + 22, box[1] + 46 + j * fh), text, font=f, fill=GREEN if is_cmd else WHITE)
        if i < FPS * 0.35:
            im = Image.blend(Image.new("RGB", (W, H), DARK_BG), im, (i + 1) / (FPS * 0.35))
        v.frame(im)
    v.hold(im, 0.4, fade=0.3)


def answer_scene(v: Video, m: dict) -> None:
    d90, off, cap = m["capture"]["d90"], m["official"], m["capture"]
    im, d = dark_slide()
    d.text((60, 80), "The answer, last 90 days", font=font(26, bold=True), fill=GREEN)
    d.text((60, 120), pct(d90["coverage_total"]), font=font(150, bold=True), fill=WHITE)
    text_block(d, (60, 300), "of new NEAR issuance was paid for by usage", font(40), WHITE, 1150)
    y = 380
    for line in (
        f"gas burn {pct(d90['coverage_burn'])}  +  NEAR Intents revenue {pct(d90['coverage_intents'])}  ({d90['intents_revenue_over_gas_fees']:.0f}x the chain's gas fees)",
        f"Year to date: {pct(cap['ytd']['coverage_total'])} here vs {pct(off['official_ytd_offset'])} on the official revenue.near.org dashboard",
        f"Monthly in 2026: {pct(cap['coverage_2026_min'])} to {pct(cap['coverage_2026_max'])}",
    ):
        y = text_block(d, (60, y), line, font(30), MUTED, 1160) + 14
    v.hold(im, 7.0)


def chart_scene(v: Video, png: Path, title: str, caption: str, seconds: float) -> None:
    im = Image.new("RGB", (W, H), LIGHT_BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 6], fill=GREEN)
    d.text((50, 22), title, font=font(32, bold=True), fill=INK)
    chart = Image.open(png).convert("RGB")
    bw, bh = 1180, 505
    s = min(bw / chart.width, bh / chart.height)
    chart = chart.resize((int(chart.width * s), int(chart.height * s)), Image.LANCZOS)
    im.paste(chart, ((W - chart.width) // 2, 72 + (bh - chart.height) // 2))
    d.rectangle([0, 590, W, H], fill=(243, 246, 249))
    text_block(d, (50, 606), caption, font(26), INK, 1180, 1.3)
    v.hold(im, seconds, bg=LIGHT_BG, fade=0.3)


def chart_scenes(v: Video, m: dict) -> None:
    iss, cap, off, use, ll, be = (m[k] for k in ("issuance", "capture", "official", "usage", "leadlag", "breakeven"))
    c = ROOT / "docs" / "charts"
    scenes = [
        ("issuance", "1. Issuance was cut in half",
         f"Gross issuance fell from {pct(iss['gross_issuance_rate_before'], 2)} to {pct(iss['gross_issuance_rate_after'], 2)} a year (cut detected {iss['halving_detected_on']}). "
         f"{iss['supply_check_samples']} archival block headers match the indexer's supply within {pct(iss['supply_check_max_abs_rel_diff'], 3)}."),
        ("capture_monthly", "2. Usage vs issuance, month by month",
         f"Gas burn plus NEAR Intents revenue offset {pct(cap['coverage_2026_min'])} to {pct(cap['coverage_2026_max'])} of monthly issuance in 2026 "
         f"({pct(cap['last_full_month_coverage_total'])} in {cap['last_full_month']}). Burn alone is about 1%."),
        ("coverage_official", "3. Checked against the official dashboard",
         f"Independent estimate vs revenue.near.org: {off['mean_abs_diff_pp']:.1f} pp mean gap, {off['months_within_5pp']} of {off['months_compared']} months within 5 pp. "
         "Differences are reported, not explained away."),
        ("usage", "4. L1 activity fell, cross-chain volume grew",
         f"Q1 2026 to the last 90 days: L1 transactions {100 * use['txns_change_q1_to_last90']:+.0f}%, active accounts {100 * use['active_accounts_change_q1_to_last90']:+.0f}%, "
         f"NEAR Intents volume {100 * use['intents_volume_usd_change_q1_to_last90']:+.0f}%."),
        ("reflexivity", "5. A higher price raises the bar",
         f"Intents revenue grew {cap['revenue_usd_growth_multiple']:.1f}x in USD but only {cap['revenue_near_growth_multiple']:.1f}x in NEAR, "
         f"because the price rose {cap['price_growth_multiple']:.1f}x. Issuance is fixed in NEAR."),
        ("leadlag", "6. Does usage lead price? Not in this data",
         f"{ll['n_significant']} of {ll['n_tests']} weekly lead-lag tests are significant after Holm correction ({ll['weeks']} weeks). "
         f"Intents volume beats price as a predictor of L1 usage for {ll['h2_intents_better_count']} of 3 metrics."),
        ("breakeven", "7. What break-even would take",
         f"Usage-based capture must grow {be['multiple']:.1f}x: about {usd(be['required_daily_intents_volume_usd'])} of Intents volume a day vs "
         f"{usd(be['current_daily_intents_volume_usd'])} now. Scenarios, not forecasts."),
    ]
    for cid, title, caption in scenes:
        chart_scene(v, c / f"{cid}.png", title, caption, 4.6)


def dashboard_scene(v: Video, png: Path) -> None:
    page = Image.open(png).convert("RGB")
    # zoom into the 940 px content column of the 1280 px page so the text stays legible
    x0 = max(0, (page.width - 1000) // 2)
    page = page.crop((x0, 0, min(page.width, x0 + 1000), page.height))
    page = page.resize((W, int(page.height * W / page.width)), Image.LANCZOS)
    top_h = 56
    view_h = H - top_h
    travel = min(page.height - view_h, 3300)
    seconds = 8.0
    n = int(seconds * FPS)
    hold = int(1.2 * FPS)
    for i in range(n):
        t = max(0, i - hold) / max(1, n - hold - 1)
        ease = t * t * (3 - 2 * t)
        y = int(ease * travel)
        im = Image.new("RGB", (W, H), LIGHT_BG)
        im.paste(page.crop((0, y, W, y + view_h)), (0, top_h))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, top_h], fill=DARK_BG)
        label = f"Dashboard: {PAGES_URL}   |   every chart lists its source, method, code and data"
        fs = 22
        while d.textlength(label, font=font(fs, bold=True)) > W - 48 and fs > 12:
            fs -= 1
        d.text((24, (top_h - fs) // 2 - 2), label, font=font(fs, bold=True), fill=WHITE)
        a = min(1.0, (i + 1) / 10, (n - i) / 10)
        v.frame(im if a >= 1 else Image.blend(Image.new("RGB", (W, H), LIGHT_BG), im, a))


def verdict_scene(v: Video, m: dict) -> None:
    be, d90, use = m["breakeven"], m["capture"]["d90"], m["usage"]
    im, d = dark_slide()
    d.text((60, 60), "The thesis", font=font(26, bold=True), fill=GREEN)
    y = text_block(
        d, (60, 105),
        f"NEAR is a bet that NEAR Intents volume grows about {be['required_volume_multiple']:.1f}x at a stable or rising capture rate, "
        "and that bought-back NEAR becomes a real supply reduction. It is not a bet on L1 activity.",
        font(34, bold=True), WHITE, 1160, 1.25,
    )
    d.text((60, y + 30), "What would change our mind", font=font(26, bold=True), fill=GREEN)
    y += 75
    for line in (
        "More bullish: usage covering 50% or more of issuance for two 90-day windows in a row; bought-back NEAR burned or locked onchain.",
        f"More bearish: 90-day coverage below 10% (now {pct(d90['coverage_total'])}); Intents volume growth turning negative year over year.",
    ):
        y = text_block(d, (60, y), "- " + line, font(28), WHITE, 1160, 1.25) + 12
    v.hold(im, 8.0)


def end_scene(v: Video, m: dict) -> None:
    im, d = dark_slide()
    d.text((60, 110), "Rebuild it yourself", font=font(26, bold=True), fill=GREEN)
    f = font(28, mono=True)
    d.rounded_rectangle([60, 160, W - 60, 300], radius=10, fill=(8, 12, 18), outline=(48, 60, 72))
    d.text((84, 182), f"git clone https://{REPO_URL}", font=f, fill=WHITE)
    d.text((84, 232), "cd near-usage-thesis && make build && make verify", font=f, fill=WHITE)
    d.text((60, 340), f"Dashboard: {PAGES_URL}", font=font(32, bold=True), fill=WHITE)
    d.text((60, 392), f"Thesis: {REPO_URL}/blob/main/THESIS.md", font=font(28), fill=WHITE)
    d.text((60, 470), "Built at NEAR HACKATHON  @NEARProtocol  #NEARHackathon", font=font(28, bold=True), fill=GREEN)
    d.text((60, 520), f"Data as of {m['as_of']}. MIT licensed. Not investment advice.", font=font(24), fill=MUTED)
    v.hold(im, 5.5)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dashboard-png", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "demo" / "demo.mp4")
    a = ap.parse_args()
    m = json.loads((ROOT / "docs" / "metrics.json").read_text(encoding="utf-8"))
    v = Video(a.out)
    title_scene(v, m)
    question_scene(v, m)
    terminal_scene(v, m)
    answer_scene(v, m)
    chart_scenes(v, m)
    if a.dashboard_png and a.dashboard_png.exists():
        dashboard_scene(v, a.dashboard_png)
    verdict_scene(v, m)
    end_scene(v, m)
    v.close()
    print(f"wrote {a.out} ({v.frames / FPS:.1f} s, {a.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
