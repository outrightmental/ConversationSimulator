#!/usr/bin/env python3
# Steam capsule art set for Conversation Simulator — v3 (flat fills, no
# letter-spacing/gradients: ImageMagick's SVG renderer is limited).
#
# v3 (Valve store-presence review, Jul 2026): store capsules may contain ONLY
# game artwork + the game name, and library assets only the game title
# (https://partner.steamgames.com/doc/store/assets/rules).  The tagline
# ("The simulator for conversations.") and the OUTRIGHT MENTAL publisher
# wordmark were removed from header_capsule, main_capsule, vertical_capsule,
# and library_header; compositions re-centred to absorb the removed lines.
import subprocess, os

OUT = "/tmp/assets/capsules"
os.makedirs(OUT, exist_ok=True)

BG      = "#0d0d15"
BG_TOP  = "#151522"
PURP, PURP_D = "#6D28D9", "#4C1D95"
GRN,  GRN_D  = "#15803D", "#14532D"
WHITE, GRAY, DIM = "#F4F4F5", "#A1A1AA", "#71717A"
F = "Carlito"

def base(w, h):
    return (f'<rect width="{w}" height="{h}" fill="{BG}"/>'
            f'<rect width="{w}" height="{h*0.55:.0f}" fill="{BG_TOP}" opacity="0.55"/>'
            f'<rect y="{h*0.55:.0f}" width="{w}" height="{h*0.45:.0f}" fill="{BG}"/>')

def mark(x, y, s):
    """Conversation mark. Footprint ~ (340w x 250h) * s at (x,y)."""
    return f'''
  <g transform="translate({x},{y}) scale({s})">
    <rect x="122" y="0" width="218" height="126" rx="26" fill="{GRN}"/>
    <rect x="122" y="0" width="218" height="30" rx="26" fill="#1D9C4B" opacity="0.6"/>
    <path d="M 296 124 L 296 160 L 260 124 Z" fill="{GRN}"/>
    <rect x="152" y="32" width="118" height="13" rx="6.5" fill="#ffffff" opacity="0.95"/>
    <rect x="152" y="57" width="158" height="13" rx="6.5" fill="#ffffff" opacity="0.60"/>
    <rect x="152" y="82" width="86"  height="13" rx="6.5" fill="#ffffff" opacity="0.32"/>
    <rect x="0" y="92" width="198" height="116" rx="24" fill="{PURP}"/>
    <rect x="0" y="92" width="198" height="28" rx="24" fill="#7E3BF2" opacity="0.6"/>
    <path d="M 40 206 L 40 242 L 76 206 Z" fill="{PURP}"/>
    <circle cx="64" cy="150" r="11" fill="#ffffff"/>
    <circle cx="99" cy="150" r="11" fill="#ffffff" opacity="0.70"/>
    <circle cx="134" cy="150" r="11" fill="#ffffff" opacity="0.42"/>
  </g>'''

def words(cx, y, size):
    """Stacked logotype (game name ONLY — Steam asset rules) at cx; y = baseline of line 1."""
    gap = size * 1.06
    return f'''
  <g text-anchor="middle" font-family="{F}" font-weight="700">
    <text x="{cx}" y="{y}" font-size="{size}" fill="{WHITE}">CONVERSATION</text>
    <text x="{cx}" y="{y+gap:.0f}" font-size="{size}" fill="{WHITE}">SIMULATOR</text>
  </g>'''

def svg(w, h, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{base(w,h)}{body}</svg>'

jobs = {}

# Header 920x430 — mark left, name right-center
jobs["header_capsule"] = (920, 430, svg(920, 430,
    mark(52, 96, 0.92) + words(628, 197, 62)))

# Small 462x174 — words only, centered
jobs["small_capsule"] = (462, 174, svg(462, 174, words(231, 72, 47)))

# Main 1232x706 — mark top-center, name below
jobs["main_capsule"] = (1232, 706, svg(1232, 706,
    mark(452, 96, 0.98) + words(616, 468, 82)))

# Vertical 748x896
jobs["vertical_capsule"] = (748, 896, svg(748, 896,
    mark(202, 200, 1.0) + words(374, 590, 68)))

# Library capsule 600x900
jobs["library_capsule"] = (600, 900, svg(600, 900,
    mark(136, 200, 0.96) + words(300, 590, 56)))

# Library header 920x430 — same as header
jobs["library_header"] = jobs["header_capsule"]

# Library hero 3840x1240 — pure graphic, no text (Steam overlays the logo)
jobs["library_hero"] = (3840, 1240, svg(3840, 1240, mark(1748, 480, 1.05)))

# Library logo 1280x720 transparent — mark + words
jobs["library_logo"] = (1280, 720, (
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
    + mark(478, 60, 0.95) + words(640, 430, 92) + "</svg>"))

# Page background 1438x810 — very subtle
jobs["page_background"] = (1438, 810, svg(1438, 810,
    f'<g opacity="0.14">{mark(1010, 130, 0.85)}</g><g opacity="0.09">{mark(180, 430, 0.62)}</g>'))

# Community icon 184x184
jobs["community_icon"] = (184, 184, f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 184 184">
<rect width="184" height="184" fill="{BG}"/>
<rect x="20" y="38" width="144" height="86" rx="20" fill="{PURP}"/>
<path d="M 46 122 L 46 154 L 78 122 Z" fill="{PURP}"/>
<circle cx="60" cy="81" r="10" fill="#fff"/><circle cx="92" cy="81" r="10" fill="#fff" opacity="0.7"/><circle cx="124" cy="81" r="10" fill="#fff" opacity="0.42"/>
</svg>''')

for name, (w, h, code) in jobs.items():
    p = f"{OUT}/{name}.svg"; open(p, "w").write(code)
    png = f"{OUT}/{name}.png"
    subprocess.run(["convert", "-background", "none", p, "-resize", f"{w}x{h}!", png], check=True)
    r = subprocess.run(["identify", "-format", "%wx%h", png], capture_output=True, text=True).stdout
    print(f"{name}: {r}")
