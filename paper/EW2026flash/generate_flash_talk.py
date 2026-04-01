#!/usr/bin/env python3
from __future__ import annotations

import base64
import mimetypes
import os
import subprocess
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from odf import draw, style, text
from odf.opendocument import OpenDocumentPresentation
from odf.style import DrawingPageProperties, MasterPage, PageLayout, PageLayoutProperties, Style


ROOT = Path("/home/o/git/athena-rods/paper/EW2026flash")
POSTER_ROOT = Path("/home/o/git/athena-rods/paper/EW2026poster")
ASSETS = POSTER_ROOT / "assets"

SLIDE1_SVG = ROOT / "slide1.svg"
SLIDE2_SVG = ROOT / "slide2.svg"
SLIDE1_PNG = ROOT / "slide1.png"
SLIDE2_PNG = ROOT / "slide2.png"
SLIDE1_PDF = ROOT / "slide1_page.pdf"
SLIDE2_PDF = ROOT / "slide2_page.pdf"
OUT_ODP = ROOT / "athena_rods_flash_talk.odp"
OUT_PDF = ROOT / "athena_rods_flash_talk.pdf"
OUT_PREVIEW_PREFIX = ROOT / "athena_rods_flash_talk_preview"

W, H = 1920, 1080

COLORS = {
    "bg": "#f7f1e8",
    "bg_alt": "#e9eef4",
    "navy": "#0f2234",
    "navy_soft": "#20384d",
    "ink": "#16293a",
    "muted": "#526678",
    "orange": "#bf5700",
    "orange_light": "#d9751d",
    "orange_soft": "#f3d9c2",
    "line": "#d7dee6",
    "card": "#ffffff",
    "card_alt": "#f8fbfd",
    "teal": "#1c8479",
}

TOOL_ENV = {
    **os.environ,
    "HOME": "/tmp",
    "XDG_CONFIG_HOME": "/tmp",
    "XDG_CACHE_HOME": "/tmp",
    "XDG_RUNTIME_DIR": "/tmp",
}


def b64_data_uri(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if mime is None:
        mime = "application/octet-stream"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def rounded_rect(x: int, y: int, w: int, h: int, rx: int = 24, fill: str | None = None, stroke: str | None = None, stroke_width: int = 0, opacity: float | None = None) -> str:
    attrs = [f'x="{x}"', f'y="{y}"', f'width="{w}"', f'height="{h}"', f'rx="{rx}"']
    if fill is not None:
        attrs.append(f'fill="{fill}"')
    if stroke is not None:
        attrs.append(f'stroke="{stroke}"')
        if stroke_width:
            attrs.append(f'stroke-width="{stroke_width}"')
    if opacity is not None:
        attrs.append(f'opacity="{opacity}"')
    return f'<rect {" ".join(attrs)}/>'


def t(
    x: int | float,
    y: int | float,
    s: str,
    *,
    size: int = 36,
    weight: str = "normal",
    fill: str | None = None,
    anchor: str = "start",
    family: str = "Cabin, Liberation Sans, DejaVu Sans, sans-serif",
) -> str:
    fill = fill or COLORS["ink"]
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
        f'font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}">{escape(s)}</text>'
    )


def wrapped_lines(text: str, width_chars: int) -> list[str]:
    return textwrap.wrap(text, width=width_chars, break_long_words=False, break_on_hyphens=False)


def text_block(
    x: int,
    y: int,
    text: str,
    *,
    width_chars: int,
    size: int = 34,
    line_gap: float = 1.22,
    fill: str | None = None,
    weight: str = "normal",
) -> tuple[str, int]:
    parts: list[str] = []
    lines = wrapped_lines(text, width_chars)
    line_h = int(size * line_gap)
    for idx, line in enumerate(lines):
        parts.append(t(x, y + idx * line_h, line, size=size, fill=fill, weight=weight))
    return "".join(parts), y + max(1, len(lines)) * line_h


def pill(x: int, y: int, w: int, h: int, label: str, *, fill: str, text_fill: str = "#ffffff") -> str:
    return rounded_rect(x, y, w, h, rx=h // 2, fill=fill) + t(x + w / 2, y + h * 0.66, label, size=24, weight="700", fill=text_fill, anchor="middle")


def card(x: int, y: int, w: int, h: int, *, fill: str = COLORS["card"], stroke: str = COLORS["line"]) -> str:
    return (
        rounded_rect(x + 10, y + 14, w, h, rx=28, fill="#000000", opacity=0.09)
        + rounded_rect(x, y, w, h, rx=28, fill=fill, stroke=stroke, stroke_width=2)
    )


def image_card(x: int, y: int, w: int, h: int, href: str, *, label: str | None = None, fit: str = "xMidYMid meet", pad: int = 16) -> str:
    parts = [card(x, y, w, h, fill="#ffffff")]
    parts.append(image_tag(x + pad, y + pad, w - 2 * pad, h - 2 * pad, href, fit=fit))
    if label:
        parts.append(pill(x + 18, y + 16, max(120, 16 * len(label)), 36, label, fill=COLORS["orange"]))
    return "".join(parts)


def metric_card(x: int, y: int, w: int, h: int, tag: str, body: str) -> str:
    parts = [card(x, y, w, h, fill=COLORS["card_alt"])]
    parts.append(rounded_rect(x + 18, y + 18, 120, h - 36, rx=18, fill=COLORS["orange_soft"]))
    parts.append(t(x + 78, y + 54, tag, size=28, weight="700", fill=COLORS["orange"], anchor="middle"))
    body_svg, _ = text_block(x + 165, y + 52, body, width_chars=40, size=30, line_gap=1.18, fill=COLORS["ink"], weight="600")
    parts.append(body_svg)
    return "".join(parts)


def callout_item(x: int, y: int, text: str) -> tuple[str, int]:
    parts = [
        rounded_rect(x, y - 20, 18, 18, rx=5, fill=COLORS["orange"]),
    ]
    block, end_y = text_block(x + 34, y, text, width_chars=35, size=30, line_gap=1.20, fill="#ffffff")
    parts.append(block)
    return "".join(parts), end_y + 10


def image_tag(x: int, y: int, w: int, h: int, href: str, *, fit: str = "xMidYMid meet", opacity: float | None = None) -> str:
    opacity_attr = f' opacity="{opacity}"' if opacity is not None else ""
    return (
        f'<image x="{x}" y="{y}" width="{w}" height="{h}" '
        f'href="{href}" xlink:href="{href}" preserveAspectRatio="{fit}"{opacity_attr}/>'
    )


def svg_root(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        "<defs>"
        '<linearGradient id="bgGrad1" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{COLORS["bg"]}"/>'
        f'<stop offset="100%" stop-color="{COLORS["bg_alt"]}"/>'
        "</linearGradient>"
        '<linearGradient id="bgGrad2" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="{COLORS["bg_alt"]}"/>'
        f'<stop offset="100%" stop-color="{COLORS["bg"]}"/>'
        "</linearGradient>"
        '<linearGradient id="navyGrad" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{COLORS["navy_soft"]}"/>'
        f'<stop offset="100%" stop-color="{COLORS["navy"]}"/>'
        "</linearGradient>"
        '<linearGradient id="orangeGrad" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{COLORS["orange_light"]}"/>'
        f'<stop offset="100%" stop-color="{COLORS["orange"]}"/>'
        "</linearGradient>"
        "</defs>"
        + body
        + "</svg>"
    )


def slide1_svg() -> str:
    logo = b64_data_uri(ASSETS / "UTEW26_Square_Color-RGB.png")
    owl = b64_data_uri(ASSETS / "owl.png")
    img_ctrl = b64_data_uri(ASSETS / "odp_pictures/10000000000003B9000004F71F91EBEB.png")
    img_hw1 = b64_data_uri(ASSETS / "odp_pictures/10000000000003B9000004F7DE05E82C.png")
    img_vis = b64_data_uri(ASSETS / "visbox.png")
    img_chain = b64_data_uri(ASSETS / "odp_pictures/10000000000001FF0000017DD8DA8883.png")

    left_x = 96
    right_x = 1008
    right_w = 816
    hero_w, hero_h = 650, 520
    hero_x = right_x + (right_w - hero_w) // 2
    hero_y = 150
    row_y = 696
    row_h = 204
    row_gap = 22
    ctrl_w = 418
    small_w = (right_w - ctrl_w - 2 * row_gap) // 2
    ctrl_x = right_x
    vis_x = ctrl_x + ctrl_w + row_gap
    sec_x = vis_x + small_w + row_gap
    cta_w = 620
    cta_x = right_x + (right_w - cta_w) // 2
    owl_pad = 10
    # Keep the full owl image (646x954) and scale its displayed height by ~10%.
    owl_ratio = 646 / 954
    owl_img_h = int(round((400 - 2 * owl_pad)))
    owl_img_w = int(round(owl_img_h * owl_ratio))
    owl_badge_w = owl_img_w + 2 * owl_pad
    owl_badge_h = owl_img_h + 2 * owl_pad
    # Keep Athena graphic next to the hero image with equal x/y spacing.
    owl_badge_x = hero_x - owl_badge_w - owl_pad
    owl_badge_y = hero_y + owl_pad

    parts = [
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="url(#bgGrad1)"/>',
        f'<rect x="0" y="0" width="{W}" height="18" fill="url(#orangeGrad)"/>',
        pill(left_x, 88, 360, 48, "UT Energy Week 2026 Flash Talk", fill=COLORS["orange"]),
        rounded_rect(1710, 60, 140, 140, rx=28, fill="#ffffff", stroke=COLORS["line"], stroke_width=2),
        image_tag(1724, 74, 112, 112, logo),
        rounded_rect(
            owl_badge_x,
            owl_badge_y,
            owl_badge_w,
            owl_badge_h,
            rx=28,
            fill="#fff4ea",
            stroke=COLORS["orange_soft"],
            stroke_width=2,
        ),
        image_tag(owl_badge_x + owl_pad, owl_badge_y + owl_pad, owl_img_w, owl_img_h, owl),
        t(left_x, 250, "ATHENA-rods", size=104, weight="700", fill=COLORS["orange"]),
    ]

    subtitle_svg, subtitle_end = text_block(
        left_x,
        318,
        "A low-cost cyber-physical platform for nuclear control education and secure digital I&C prototyping",
        width_chars=42,
        size=38,
        line_gap=1.18,
        fill=COLORS["ink"],
        weight="600",
    )
    parts.append(subtitle_svg)
    parts.append(f'<rect x="{left_x}" y="{subtitle_end + 8}" width="580" height="5" rx="3" fill="{COLORS["orange"]}" opacity="0.85"/>')

    bridge_svg, bridge_end = text_block(
        left_x,
        subtitle_end + 58,
        "A tabletop bridge between reactor kinetics, physical actuation, and secure digital I&C.",
        width_chars=48,
        size=30,
        line_gap=1.20,
        fill=COLORS["muted"],
        weight="600",
    )
    parts.append(bridge_svg)

    metrics_y = bridge_end + 32
    parts.append(metric_card(left_x, metrics_y, 820, 118, "Physics", "Physical control rod motion tied to live point-kinetics response."))
    parts.append(metric_card(left_x, metrics_y + 142, 820, 118, "Security", "X.509 and TLS networking plus face and RFID operator authorization."))
    parts.append(metric_card(left_x, metrics_y + 284, 820, 118, "Access", "Home-printable parts, open-source code, and about $390 build cost."))

    parts.append(
        t(
            left_x,
            1050,
            "Ondrej Chvala | Walker Department of Mechanical Engineering | The University of Texas at Austin | ochvala@utexas.edu | https://github.com/ondrejch/athena-rods",
            size=16,
            fill=COLORS["muted"],
            weight="600",
        )
    )

    parts.append(image_card(hero_x, hero_y, hero_w, hero_h, img_hw1, label="instrument", fit="xMidYMid slice"))
    parts.append(image_card(ctrl_x, row_y, ctrl_w, row_h, img_ctrl, label="control", fit="xMidYMid slice"))
    parts.append(image_card(vis_x, row_y, small_w, row_h, img_vis, label="visualization"))
    parts.append(image_card(sec_x, row_y, small_w, row_h, img_chain, label="security"))
    parts.append(pill(cta_x, 948, cta_w, 52, "Poster shows the full build, workflow, and validation.", fill=COLORS["navy"]))
    return svg_root("".join(parts))


def slide2_svg() -> str:
    poster = b64_data_uri(POSTER_ROOT / "poster_redesign_preview.png")

    poster_x = 76
    poster_y = 144
    poster_w = 1036
    poster_h = 820
    poster_pad = 28
    text_x = 1250

    parts = [
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="url(#bgGrad2)"/>',
        rounded_rect(1185, 0, 735, H, rx=0, fill="url(#navyGrad)"),
        f'<rect x="0" y="0" width="{W}" height="18" fill="url(#orangeGrad)"/>',
        pill(90, 82, 210, 46, "Poster Invitation", fill=COLORS["orange"]),
        pill(320, 82, 220, 46, "poster preview", fill=COLORS["navy"]),
        card(poster_x, poster_y, poster_w, poster_h, fill="#ffffff"),
        image_tag(poster_x + poster_pad, poster_y + poster_pad, poster_w - 2 * poster_pad, poster_h - 2 * poster_pad, poster, fit="xMidYMid meet"),
        t(text_x, 186, "Come see the poster", size=60, weight="700", fill="#ffffff"),
    ]

    sub_svg, sub_end = text_block(
        text_x,
        250,
        "Live DEMO!",
        width_chars=22,
        size=52,
        line_gap=1.0,
        fill="#dce7f0",
        weight="700",
    )
    parts.append(sub_svg)
    parts.append(f'<rect x="{text_x}" y="{sub_end + 8}" width="470" height="4" rx="2" fill="{COLORS["orange_light"]}" opacity="0.90"/>')

    y = sub_end + 62
    for item in [
        "3D-printed hardware, Raspberry Pi nodes, and the parts-to-buy list.",
        "The software flow from sensors to point kinetics and Dash visualization.",
        "Certificates, TLS or mTLS, and face plus RFID authorization.",
        "Control-performance tests, security verification, and reproducibility.",
    ]:
        item_svg, y = callout_item(text_x, y, item)
        parts.append(item_svg)

    parts.append(rounded_rect(1210, 740, 650, 102, rx=26, fill="url(#orangeGrad)"))
    parts.append(t(1236, 800, "https://github.com/ondrejch/athena-rods", size=32, fill="#ffffff", weight="700"))

    parts.append(
        t(
            96,
            1050,
            "Ondrej Chvala | The University of Texas at Austin | ochvala@utexas.edu | https://github.com/ondrejch/athena-rods",
            size=16,
            fill=COLORS["muted"],
            weight="600",
        )
    )

    note_svg, _ = text_block(
        text_x,
        986,
        "Part of the ongoing UT nuclear digital twins effort.",
        width_chars=60,
        size=24,
        line_gap=1.15,
        fill="#dce7f0",
        weight="600",
    )
    parts.append(note_svg)
    return svg_root("".join(parts))


def write_svg(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def svg_to_png(svg_path: Path, png_path: Path) -> None:
    subprocess.run(
        [
            "inkscape",
            str(svg_path),
            "--export-type=png",
            f"--export-filename={png_path}",
            f"--export-width={W}",
            f"--export-height={H}",
        ],
        env=TOOL_ENV,
        check=True,
    )


def px_to_pt(px: float) -> str:
    return f"{px * 0.5:.2f}pt"


def px_to_font(px: float) -> int:
    return max(6, int(round(px * 0.5)))


def build_odp() -> None:
    doc = OpenDocumentPresentation()

    pagelayout = PageLayout(name="FlashLayout")
    doc.automaticstyles.addElement(pagelayout)
    pagelayout.addElement(
        PageLayoutProperties(
            margin="0pt",
            pagewidth="960pt",
            pageheight="540pt",
            printorientation="landscape",
        )
    )

    slide_style = Style(name="FlashPage", family="drawing-page")
    slide_style.addElement(
        DrawingPageProperties(
            displayfooter="false",
            displaypagenumber="false",
            displaydatetime="false",
        )
    )
    doc.automaticstyles.addElement(slide_style)

    masterpage = MasterPage(name="FlashMaster", pagelayoutname=pagelayout)
    doc.masterstyles.addElement(masterpage)

    gcache: dict[tuple[str | None, str | None, str], Style] = {}
    pcache: dict[str, Style] = {}
    tcache: dict[tuple[int, str, bool], Style] = {}

    def gstyle(fill: str | None, stroke: str | None, stroke_width: str = "0.8pt") -> Style:
        key = (fill, stroke, stroke_width)
        if key in gcache:
            return gcache[key]
        st = Style(name=f"grf_{len(gcache)+1}", family="graphic")
        kwargs: dict[str, str] = {}
        if fill is None:
            kwargs["fill"] = "none"
        else:
            kwargs["fill"] = "solid"
            kwargs["fillcolor"] = fill
        if stroke is None:
            kwargs["stroke"] = "none"
        else:
            kwargs["stroke"] = "solid"
            kwargs["strokecolor"] = stroke
            kwargs["strokewidth"] = stroke_width
        st.addElement(style.GraphicProperties(**kwargs))
        doc.automaticstyles.addElement(st)
        gcache[key] = st
        return st

    def pstyle(align: str = "left") -> Style:
        key = align
        if key in pcache:
            return pcache[key]
        st = Style(name=f"par_{len(pcache)+1}", family="paragraph")
        st.addElement(style.ParagraphProperties(textalign=align))
        doc.automaticstyles.addElement(st)
        pcache[key] = st
        return st

    def tstyle(size_px: float, color: str, bold: bool = False) -> Style:
        size_pt = px_to_font(size_px)
        key = (size_pt, color, bold)
        if key in tcache:
            return tcache[key]
        st = Style(name=f"txt_{len(tcache)+1}", family="text")
        st.addElement(
            style.TextProperties(
                fontsize=f"{size_pt}pt",
                color=color,
                fontweight="bold" if bold else "normal",
                fontfamily="'Liberation Sans'",
            )
        )
        doc.automaticstyles.addElement(st)
        tcache[key] = st
        return st

    frame_no_fill = gstyle(None, None)

    def add_rect(page, x: float, y: float, w: float, h: float, fill: str, stroke: str | None = COLORS["line"]) -> None:
        page.addElement(
            draw.Rect(
                stylename=gstyle(fill, stroke),
                x=px_to_pt(x),
                y=px_to_pt(y),
                width=px_to_pt(w),
                height=px_to_pt(h),
            )
        )

    def add_text(page, x: float, y: float, w: float, h: float, content: str, *, size_px: float, color: str, bold: bool = False, align: str = "left") -> None:
        fr = draw.Frame(
            stylename=frame_no_fill,
            x=px_to_pt(x),
            y=px_to_pt(y),
            width=px_to_pt(w),
            height=px_to_pt(h),
        )
        tb = draw.TextBox()
        p_st = pstyle(align)
        t_st = tstyle(size_px, color, bold)
        for ln in content.split("\n"):
            p = text.P(stylename=p_st)
            p.addElement(text.Span(stylename=t_st, text=ln))
            tb.addElement(p)
        fr.addElement(tb)
        page.addElement(fr)

    def add_image(page, x: float, y: float, w: float, h: float, path: Path) -> None:
        fr = draw.Frame(
            stylename=frame_no_fill,
            x=px_to_pt(x),
            y=px_to_pt(y),
            width=px_to_pt(w),
            height=px_to_pt(h),
        )
        href = doc.addPicture(str(path))
        fr.addElement(draw.Image(href=href))
        page.addElement(fr)

    # Slide 1: invitation pitch
    page1 = draw.Page(name="page1", stylename=slide_style, masterpagename=masterpage)
    doc.presentation.addElement(page1)

    add_rect(page1, 0, 0, W, H, COLORS["bg"], stroke=None)
    add_rect(page1, 0, 0, W, 18, COLORS["orange"], stroke=None)
    add_rect(page1, 96, 88, 360, 48, COLORS["orange"], stroke=None)
    add_text(page1, 96, 96, 360, 36, "UT Energy Week 2026 Flash Talk", size_px=24, color="#ffffff", bold=True, align="center")
    add_rect(page1, 1710, 60, 140, 140, "#ffffff", stroke=COLORS["line"])
    add_image(page1, 1724, 74, 112, 112, ASSETS / "UTEW26_Square_Color-RGB.png")

    add_text(page1, 96, 130, 760, 100, "ATHENA-rods", size_px=104, color=COLORS["orange"], bold=True)
    add_text(
        page1,
        96,
        286,
        780,
        150,
        "A low-cost cyber-physical platform for\nnuclear control education and secure\ndigital I&C prototyping",
        size_px=38,
        color=COLORS["ink"],
        bold=True,
    )
    add_rect(page1, 96, 468, 580, 5, COLORS["orange"], stroke=None)
    add_text(
        page1,
        96,
        486,
        760,
        90,
        "A tabletop bridge between reactor kinetics,\nphysical actuation, and secure digital I&C.",
        size_px=30,
        color=COLORS["muted"],
        bold=True,
    )

    metric_y = 620
    for idx, (tag, body) in enumerate(
        [
            ("Physics", "Physical control rod motion tied to live\npoint-kinetics response."),
            ("Security", "X.509 and TLS networking plus face and\nRFID operator authorization."),
            ("Access", "Home-printable parts, open-source code,\nand about $390 build cost."),
        ]
    ):
        y = metric_y + idx * 142
        add_rect(page1, 96, y, 820, 118, COLORS["card_alt"], stroke=COLORS["line"])
        add_rect(page1, 114, y + 18, 120, 82, COLORS["orange_soft"], stroke=None)
        add_text(page1, 114, y + 30, 120, 40, tag, size_px=28, color=COLORS["orange"], bold=True, align="center")
        add_text(page1, 262, y + 26, 630, 84, body, size_px=30, color=COLORS["ink"], bold=True)

    add_text(
        page1,
        96,
        1028,
        1720,
        26,
        "Ondrej Chvala | Walker Department of Mechanical Engineering | The University of Texas at Austin | ochvala@utexas.edu | https://github.com/ondrejch/athena-rods",
        size_px=16,
        color=COLORS["muted"],
        bold=True,
    )

    hero_x_odp, hero_y_odp = 1091, 150
    hero_w_odp, hero_h_odp = 650, 520
    owl_pad_odp = 10
    owl_gap_odp = owl_pad_odp
    owl_ratio_odp = 646 / 954
    owl_img_h_odp = int(round((260 - 2 * owl_pad_odp) * 1.10))
    owl_img_w_odp = int(round(owl_img_h_odp * owl_ratio_odp))
    owl_badge_w_odp = owl_img_w_odp + 2 * owl_pad_odp
    owl_badge_h_odp = owl_img_h_odp + 2 * owl_pad_odp
    owl_badge_x_odp = hero_x_odp - owl_badge_w_odp - owl_gap_odp
    owl_badge_y_odp = hero_y_odp + owl_pad_odp

    add_rect(page1, owl_badge_x_odp, owl_badge_y_odp, owl_badge_w_odp, owl_badge_h_odp, "#fff4ea", stroke=COLORS["orange_soft"])
    add_image(
        page1,
        owl_badge_x_odp + owl_pad_odp,
        owl_badge_y_odp + owl_pad_odp,
        owl_img_w_odp,
        owl_img_h_odp,
        ASSETS / "owl.png",
    )
    add_rect(page1, 1091, 150, 650, 520, "#ffffff", stroke=COLORS["line"])
    add_image(page1, 1107, 166, 618, 488, ASSETS / "odp_pictures/10000000000003B9000004F7DE05E82C.png")
    add_rect(page1, 1008, 696, 418, 204, "#ffffff", stroke=COLORS["line"])
    add_image(page1, 1024, 712, 386, 172, ASSETS / "odp_pictures/10000000000003B9000004F71F91EBEB.png")
    add_rect(page1, 1448, 696, 188, 204, "#ffffff", stroke=COLORS["line"])
    add_image(page1, 1460, 708, 164, 180, ASSETS / "visbox.png")
    add_rect(page1, 1658, 696, 166, 204, "#ffffff", stroke=COLORS["line"])
    add_image(page1, 1670, 708, 142, 180, ASSETS / "odp_pictures/10000000000001FF0000017DD8DA8883.png")

    add_rect(page1, 1098, 948, 620, 52, COLORS["navy"], stroke=None)
    add_text(
        page1,
        1114,
        960,
        590,
        36,
        "Poster shows the full build, workflow, and validation.",
        size_px=42,
        color="#ffffff",
        bold=True,
        align="center",
    )
    add_rect(page1, 1115, 154, 200, 44, COLORS["orange"], stroke=None)
    add_text(page1, 1115, 164, 200, 30, "instrument", size_px=24, color="#ffffff", bold=True, align="center")
    add_rect(page1, 1020, 704, 140, 44, COLORS["orange"], stroke=None)
    add_text(page1, 1020, 714, 140, 30, "control", size_px=24, color="#ffffff", bold=True, align="center")
    add_rect(page1, 1458, 704, 170, 44, COLORS["orange"], stroke=None)
    add_text(page1, 1458, 714, 170, 30, "visualization", size_px=24, color="#ffffff", bold=True, align="center")
    add_rect(page1, 1668, 704, 150, 44, COLORS["orange"], stroke=None)
    add_text(page1, 1668, 714, 150, 30, "security", size_px=24, color="#ffffff", bold=True, align="center")

    # Slide 2: poster invitation
    page2 = draw.Page(name="page2", stylename=slide_style, masterpagename=masterpage)
    doc.presentation.addElement(page2)

    add_rect(page2, 0, 0, W, H, COLORS["bg_alt"], stroke=None)
    add_rect(page2, 1185, 0, 735, H, COLORS["navy"], stroke=None)
    add_rect(page2, 0, 0, W, 18, COLORS["orange"], stroke=None)

    add_rect(page2, 90, 82, 210, 46, COLORS["orange"], stroke=None)
    add_text(page2, 90, 92, 210, 34, "Poster Invitation", size_px=24, color="#ffffff", bold=True, align="center")
    add_rect(page2, 320, 82, 220, 46, COLORS["navy"], stroke=None)
    add_text(page2, 320, 92, 220, 34, "poster preview", size_px=24, color="#ffffff", bold=True, align="center")

    add_rect(page2, 76, 144, 1036, 820, "#ffffff", stroke=COLORS["line"])
    add_image(page2, 104, 172, 980, 764, POSTER_ROOT / "poster_redesign_preview.png")

    add_text(page2, 1250, 176, 600, 74, "Come see the poster", size_px=60, color="#ffffff", bold=True)
    add_text(
        page2,
        1250,
        248,
        600,
        132,
        "Live DEMO!",
        size_px=32,
        color="#dce7f0",
        bold=True,
    )
    add_rect(page2, 1250, 402, 470, 4, COLORS["orange_light"], stroke=None)

    bullets = [
        "- 3D-printed hardware, Raspberry Pi nodes,\n   and the parts-to-buy list.",
        "- The software flow from sensors to point\n   kinetics and Dash visualization.",
        "- Certificates, TLS or mTLS, and face plus\n   RFID authorization.",
        "- Control-performance tests, security\n   verification, and reproducibility.",
    ]
    by = 430
    for b in bullets:
        add_text(page2, 1250, by, 620, 92, b, size_px=30, color="#ffffff")
        by += 122

    add_rect(page2, 1200, 846, 690, 102, COLORS["orange"], stroke=None)
    add_text(
        page2,
        1236,
        872,
        650,
        50,
        "https://github.com/ondrejch/athena-rods",
        size_px=32,
        color="#ffffff",
        bold=True,
    )
    add_text(
        page2,
        1250,
        978,
        560,
        68,
        "Part of the ongoing UT nuclear\ndigital twins effort.",
        size_px=24,
        color="#dce7f0",
        bold=True,
    )

    doc.save(str(OUT_ODP))


def svg_to_pdf(svg_path: Path, pdf_path: Path) -> None:
    subprocess.run(
        [
            "inkscape",
            str(svg_path),
            "--export-type=pdf",
            f"--export-filename={pdf_path}",
            "--export-text-to-path",
        ],
        env=TOOL_ENV,
        check=True,
    )


def build_pdf() -> None:
    svg_to_pdf(SLIDE1_SVG, SLIDE1_PDF)
    svg_to_pdf(SLIDE2_SVG, SLIDE2_PDF)
    subprocess.run(
        [
            "pdfunite",
            str(SLIDE1_PDF),
            str(SLIDE2_PDF),
            str(OUT_PDF),
        ],
        check=True,
    )
    SLIDE1_PDF.unlink(missing_ok=True)
    SLIDE2_PDF.unlink(missing_ok=True)


def build_previews() -> None:
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            "2",
            "-png",
            str(OUT_PDF),
            str(OUT_PREVIEW_PREFIX),
        ],
        check=True,
    )


def main() -> None:
    write_svg(SLIDE1_SVG, slide1_svg())
    write_svg(SLIDE2_SVG, slide2_svg())

    svg_to_png(SLIDE1_SVG, SLIDE1_PNG)
    svg_to_png(SLIDE2_SVG, SLIDE2_PNG)

    build_odp()
    build_pdf()
    build_previews()

    print(f"Wrote {SLIDE1_SVG}")
    print(f"Wrote {SLIDE2_SVG}")
    print(f"Wrote {SLIDE1_PNG}")
    print(f"Wrote {SLIDE2_PNG}")
    print(f"Wrote {OUT_ODP}")
    print(f"Wrote {OUT_PDF}")


if __name__ == "__main__":
    main()
