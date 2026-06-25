import base64
import io
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
from matplotlib.gridspec import GridSpec

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# --- Optional dependency loading ---
try:
    import jdatetime
    _HAS_JDATETIME = True
except ImportError:
    _HAS_JDATETIME = False
    logger.warning("jdatetime not installed; Gregorian dates will be used. Run: pip install jdatetime")

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_BIDI = True
except ImportError:
    _HAS_BIDI = False
    logger.warning("arabic_reshaper/python-bidi not installed; Persian text may not render correctly.")

# Try to register a Persian-capable font for matplotlib
_PERSIAN_FONT_PATH = None
for _fp in [r"C:\Windows\Fonts\tahoma.ttf", r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
    try:
        font_manager.fontManager.addfont(_fp)
        _PERSIAN_FONT_PATH = _fp
        break
    except Exception:
        pass

plt.rcParams.update({
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.facecolor": "#f8fafc",
    "figure.facecolor": "#ffffff",
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
})
if _PERSIAN_FONT_PATH:
    try:
        _font_name = font_manager.FontProperties(fname=_PERSIAN_FONT_PATH).get_name()
        plt.rcParams["font.family"] = [_font_name, "DejaVu Sans"]
    except Exception:
        pass

PALETTE = {
    "weight":  "#2b6cb0",
    "fat":     "#e53e3e",
    "muscle":  "#38a169",
    "water":   "#3182ce",
}


# ─── Jalali helpers ────────────────────────────────────────────────────────────

def _to_jalali(dt) -> str:
    if _HAS_JDATETIME:
        try:
            jdt = jdatetime.datetime.fromgregorian(datetime=dt)
            return f"{jdt.year}/{jdt.month:02d}/{jdt.day:02d}"
        except Exception:
            pass
    return dt.strftime('%Y/%m/%d')


# ─── Persian text helpers (PIL) ────────────────────────────────────────────────

def _p(text: str) -> str:
    """Reshape + apply BiDi to Persian text so PIL renders it correctly."""
    if not text:
        return ""
    text = str(text)
    if _HAS_BIDI:
        try:
            return get_display(arabic_reshaper.reshape(text))
        except Exception:
            pass
    return text


def _pil_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a PIL TrueType font with Persian support."""
    for path in [r"C:\Windows\Fonts\tahoma.ttf", r"C:\Windows\Fonts\arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.Draw, text: str, font) -> tuple[int, int]:
    try:
        bb = font.getbbox(text)
        return bb[2] - bb[0], bb[3] - bb[1]
    except Exception:
        return draw.textsize(text, font=font)  # type: ignore[attr-defined]


def _draw_text_centered(draw, text, x1, x2, y, h, font, color):
    tw, th = _text_size(draw, text, font)
    tx = x1 + (x2 - x1 - tw) // 2
    ty = y + max(0, (h - th) // 2)
    draw.text((tx, ty), text, fill=color, font=font)


# ─── Progress chart ────────────────────────────────────────────────────────────

def _calc_bmi(weight, height_cm):
    try:
        h = height_cm / 100
        return round(weight / (h * h), 1)
    except Exception:
        return None


def generate_progress_chart(patient, measurements) -> str | None:
    """5-panel progress chart (Weight, BMI, Body Fat%, Muscle, Water) with Jalali dates."""
    try:
        dates    = [m.recorded_at for m in measurements]
        jalali   = [_to_jalali(d) for d in dates]
        weights  = [m.weight for m in measurements]
        bmis     = [_calc_bmi(m.weight, patient.height_cm) for m in measurements]
        fat_pcts = [m.body_fat_pct for m in measurements]
        muscles  = [m.muscle_mass for m in measurements]
        waters   = [m.water_kg for m in measurements]

        fig = plt.figure(figsize=(14, 8))
        fig.suptitle(f"Progress Report — {patient.name}", fontsize=14, fontweight="bold", y=1.01, color="#1a202c")

        gs = GridSpec(2, 6, figure=fig, hspace=0.45, wspace=0.5)
        ax_w   = fig.add_subplot(gs[0, 0:2])
        ax_bmi = fig.add_subplot(gs[0, 2:4])
        ax_fat = fig.add_subplot(gs[0, 4:6])
        ax_mus = fig.add_subplot(gs[1, 1:3])
        ax_wat = fig.add_subplot(gs[1, 3:5])

        panels = [
            (ax_w,   weights,  "Weight (kg)",     PALETTE["weight"]),
            (ax_bmi, bmis,     "BMI",             "#7b2d8b"),
            (ax_fat, fat_pcts, "Body Fat (%)",    PALETTE["fat"]),
            (ax_mus, muscles,  "Muscle (kg)",     PALETTE["muscle"]),
            (ax_wat, waters,   "Water (kg)",      PALETTE["water"]),
        ]
        for ax, vals, title, color in panels:
            _plot_line(ax, dates, vals, jalali, title, color)

        # BMI reference lines
        ax_bmi.axhline(18.5, color="#aaa", linewidth=0.8, linestyle="--", alpha=0.7)
        ax_bmi.axhline(25.0, color="#aaa", linewidth=0.8, linestyle="--", alpha=0.7)
        ax_bmi.axhline(30.0, color="#aaa", linewidth=0.8, linestyle="--", alpha=0.7)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode("utf-8")
        logger.info("Progress chart generated for patient %d (%d points).", patient.id, len(dates))
        return encoded

    except Exception:
        logger.exception("Failed to generate progress chart for patient %d.", patient.id)
        return None


def _plot_line(ax, dates, values, jalali_labels, title, color):
    valid = [(d, v, j) for d, v, j in zip(dates, values, jalali_labels) if v is not None]
    if not valid:
        ax.set_title(title)
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes, color="#a0aec0")
        return

    xs, ys, jlabels = zip(*valid)
    ax.plot(xs, ys, marker="o", color=color, linewidth=2.2, markersize=5, zorder=3)
    ax.fill_between(xs, ys, alpha=0.12, color=color)

    # Dynamic y-axis: pad by 20% of the data range so fluctuations are visible
    y_min, y_max = min(ys), max(ys)
    y_range = y_max - y_min if y_max != y_min else max(abs(y_max) * 0.05, 1.0)
    pad = y_range * 0.20
    ax.set_ylim(y_min - pad, y_max + pad)

    # Highlight first and last
    ax.scatter([xs[0], xs[-1]], [ys[0], ys[-1]], color=color, s=60, zorder=4)

    if len(ys) >= 2:
        delta = ys[-1] - ys[0]
        sign = "+" if delta >= 0 else ""
        ax.set_title(f"{title}  ({sign}{delta:.1f})", fontsize=10, color="#2d3748")
    else:
        ax.set_title(title, fontsize=10, color="#2d3748")

    # Jalali x-axis labels (numbers only — work with any font)
    n = len(xs)
    step = max(1, n // 7)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    ax.set_xticks([xs[i] for i in idx])
    ax.set_xticklabels([jlabels[i] for i in idx], rotation=35, ha="right", fontsize=7.5)
    ax.tick_params(axis="y", labelsize=8)
    ax.spines["bottom"].set_color("#cbd5e0")
    ax.spines["left"].set_color("#cbd5e0")


# ─── Table image ───────────────────────────────────────────────────────────────

# Table columns in RTL visual order (index 0 = rightmost column)
_TABLE_COLS = [
    {"key": "row_num", "header": "ردیف",      "w": 48},
    {"key": "date",    "header": "تاریخ",      "w": 108},
    {"key": "weight",  "header": "وزن",        "w": 65},
    {"key": "bmi",     "header": "BMI",        "w": 60},
    {"key": "fat_pct", "header": "چربی %",     "w": 62},
    {"key": "fat_kg",  "header": "چربی kg",    "w": 68},
    {"key": "muscle",  "header": "عضله kg",    "w": 72},
    {"key": "water",   "header": "آب kg",      "w": 65},
    {"key": "notes",   "header": "یادداشت",    "w": 140},
]

# Colours
_C = {
    "hdr_bg":   (21, 60, 120),      # deep navy header
    "hdr_text": (255, 255, 255),
    "col_bg":   (43, 108, 176),     # column header blue
    "col_text": (255, 255, 255),
    "row_even": (255, 255, 255),
    "row_odd":  (235, 244, 255),    # very light blue
    "border":   (197, 210, 226),
    "text":     (26, 32, 44),
    "text_dim": (113, 128, 150),
    "bg":       (248, 250, 252),
    "accent":   (160, 210, 250),
}


def generate_table_image(patient, measurements) -> str | None:
    """Generate a professional RTL Persian measurement table. Returns base64 PNG."""
    try:
        MARGIN = 20
        HDR_H  = 72   # patient info banner
        COL_H  = 42   # column label row
        ROW_H  = 36   # data rows

        display_rows = list(reversed(measurements[-15:]))  # newest first
        n_rows = len(display_rows)

        content_w = sum(c["w"] for c in _TABLE_COLS)  # 688
        IMG_W = content_w + 2 * MARGIN                # 728
        IMG_H = HDR_H + COL_H + ROW_H * n_rows + MARGIN

        # Assign x positions RTL: col[0] rightmost, col[-1] leftmost
        x_right = IMG_W - MARGIN
        for col in _TABLE_COLS:
            col["x2"] = x_right
            col["x1"] = x_right - col["w"]
            x_right -= col["w"]

        img = Image.new("RGB", (IMG_W, IMG_H), _C["bg"])
        draw = ImageDraw.Draw(img)

        fnt_title  = _pil_font(17)
        fnt_sub    = _pil_font(12)
        fnt_col    = _pil_font(12)
        fnt_data   = _pil_font(12)
        fnt_small  = _pil_font(10)

        # ── Header banner ──────────────────────────────────────────────
        draw.rectangle([0, 0, IMG_W, HDR_H], fill=_C["hdr_bg"])

        # Decorative accent bar on left
        draw.rectangle([0, 0, 6, HDR_H], fill=_C["accent"])

        title = _p("جدول سوابق اندازه‌گیری")
        _draw_text_centered(draw, title, 0, IMG_W, 8, 28, fnt_title, _C["hdr_text"])

        # Patient name + generation date
        gen_date = _to_jalali(__import__('datetime').datetime.utcnow())
        sub = _p(f"{patient.name}  |  تاریخ تهیه: {gen_date}")
        _draw_text_centered(draw, sub, 0, IMG_W, 38, 18, fnt_sub, (190, 220, 255))

        # Stats line
        if measurements:
            first_w = measurements[0].weight
            last_w  = measurements[-1].weight
            delta   = last_w - first_w
            sign    = "+" if delta >= 0 else ""
            stats = _p(f"تعداد ویزیت‌ها: {len(measurements)}  |  تغییر وزن: {sign}{delta:.1f} kg")
            _draw_text_centered(draw, stats, 0, IMG_W, 56, 14, fnt_small, (160, 200, 240))

        # ── Column headers ─────────────────────────────────────────────
        y = HDR_H
        for col in _TABLE_COLS:
            draw.rectangle([col["x1"], y, col["x2"], y + COL_H - 1], fill=_C["col_bg"])
            _draw_text_centered(draw, _p(col["header"]),
                                col["x1"], col["x2"], y, COL_H, fnt_col, _C["col_text"])

        # Vertical column borders (header)
        _draw_v_borders(draw, _TABLE_COLS, y, y + COL_H, _C["border"])
        # Bottom of header row
        draw.line([(MARGIN, y + COL_H - 1), (IMG_W - MARGIN, y + COL_H - 1)],
                  fill=_C["border"], width=2)

        # ── Data rows ──────────────────────────────────────────────────
        for i, m in enumerate(display_rows):
            y = HDR_H + COL_H + i * ROW_H
            row_bg = _C["row_even"] if i % 2 == 0 else _C["row_odd"]

            for col in _TABLE_COLS:
                draw.rectangle([col["x1"], y, col["x2"], y + ROW_H - 1], fill=row_bg)

            bmi_val = _calc_bmi(m.weight, patient.height_cm)
            cells = {
                "row_num": str(i + 1),
                "date":    _to_jalali(m.recorded_at),
                "weight":  f"{m.weight:.1f}",
                "bmi":     f"{bmi_val:.1f}" if bmi_val is not None else "—",
                "fat_pct": f"{m.body_fat_pct:.1f}" if m.body_fat_pct is not None else "—",
                "fat_kg":  f"{m.fat_mass:.1f}"     if m.fat_mass     is not None else "—",
                "muscle":  f"{m.muscle_mass:.1f}"  if m.muscle_mass  is not None else "—",
                "water":   f"{m.water_kg:.1f}"     if m.water_kg     is not None else "—",
                "notes":   _p((m.notes or "")[:18]) or "—",
            }

            text_color = _C["text"]
            for col in _TABLE_COLS:
                val = cells.get(col["key"], "—")
                _draw_text_centered(draw, val,
                                    col["x1"], col["x2"], y, ROW_H, fnt_data, text_color)

            # Row separator
            draw.line([(MARGIN, y + ROW_H - 1), (IMG_W - MARGIN, y + ROW_H - 1)],
                      fill=_C["border"], width=1)
            _draw_v_borders(draw, _TABLE_COLS, y, y + ROW_H, _C["border"])

        # ── Outer border ───────────────────────────────────────────────
        table_top = HDR_H
        table_bot = HDR_H + COL_H + ROW_H * n_rows
        draw.rectangle([MARGIN, table_top, IMG_W - MARGIN, table_bot],
                       outline=_C["col_bg"], width=2)

        # ── Footer ─────────────────────────────────────────────────────
        footer_y = table_bot + 6
        footer = _p("SmartWeigh MedDash — سیستم مدیریت بیماران")
        tw, _ = _text_size(draw, footer, fnt_small)
        draw.text(((IMG_W - tw) // 2, footer_y), footer,
                  fill=_C["text_dim"], font=fnt_small)

        buf = io.BytesIO()
        img.save(buf, format="PNG", dpi=(150, 150))
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode("utf-8")
        logger.info("Table image generated for patient %d (%d rows).", patient.id, n_rows)
        return encoded

    except Exception:
        logger.exception("Failed to generate table image for patient %d.", patient.id)
        return None


def _draw_v_borders(draw, cols, y1, y2, color):
    """Draw vertical separators between all columns."""
    for col in cols:
        draw.line([(col["x1"], y1), (col["x1"], y2)], fill=color, width=1)
        draw.line([(col["x2"], y1), (col["x2"], y2)], fill=color, width=1)


# ─── Metric summary card ───────────────────────────────────────────────────────

_CARD_PALETTE = {
    "normal":  {"line": (34, 197, 94),  "text": (21, 128, 61)},
    "warning": {"line": (234, 179, 8),  "text": (133, 77, 14)},
    "alert":   {"line": (239, 68, 68),  "text": (185, 28, 28)},
    "info":    {"line": (59, 130, 246), "text": (29, 78, 216)},
}


def _cs(label, stype):
    return {"label": label, "type": stype}


def _cs_bmi(bmi):
    if not bmi:    return _cs("—", "info")
    if bmi < 18.5: return _cs("کم‌وزن", "info")
    if bmi < 25.0: return _cs("نرمال", "normal")
    if bmi < 30.0: return _cs("اضافه‌وزن", "warning")
    return          _cs("چاقی", "alert")


def _cs_fat(fat_pct, is_male):
    if fat_pct is None: return _cs("—", "info")
    lo, hi = (8, 20) if is_male else (21, 33)
    if fat_pct < lo:     return _cs("ورزشکاری", "info")
    if fat_pct < hi:     return _cs("استاندارد", "normal")
    if fat_pct < hi + 5: return _cs("بالا", "warning")
    return                       _cs("خیلی بالا", "alert")


def _cs_muscle(muscle_kg, weight, is_male):
    if not muscle_kg or not weight: return _cs("—", "info")
    pct = muscle_kg / weight * 100
    lo, hi = (40, 55) if is_male else (30, 45)
    if pct < lo: return _cs("کم", "warning")
    if pct < hi: return _cs("استاندارد", "normal")
    return              _cs("خوب", "info")


def _cs_water(water_kg, weight, is_male):
    if not water_kg or not weight: return _cs("—", "info")
    pct = water_kg / weight * 100
    lo, hi = (50, 65) if is_male else (45, 60)
    if pct < lo: return _cs("کم", "warning")
    if pct < hi: return _cs("نرمال", "normal")
    return              _cs("زیاد", "alert")


def _cs_bodytype(fat_pct, is_male):
    if fat_pct is None: return _cs("نامشخص", "info")
    thresholds = [
        (10, "ورزشکار", "info"), (15, "لاغر", "normal"),
        (20, "متوسط",   "normal"), (25, "بالای متوسط", "warning"),
    ] if is_male else [
        (21, "ورزشکار", "info"), (26, "لاغر", "normal"),
        (31, "متوسط",   "normal"), (36, "بالای متوسط", "warning"),
    ]
    for thr, lbl, st in thresholds:
        if fat_pct < thr:
            return _cs(lbl, st)
    return _cs("چاق", "alert")


# ─── Icon draw functions (40×40 bounding box, ox/oy = top-left corner) ─────────
# All icons are outline/stroke style to match the reference design images.
# Arc angle convention (PIL): 0°=3-o'clock, clockwise.
#   0→180 = bottom arc (∪);  180→360 = top arc (∩);  200→340 = narrower top arc.

def _ic_weight(draw, ox, oy, c):
    """Digital bathroom scale: rounded square body + screen + reading bar."""
    draw.rounded_rectangle([ox+2, oy+3, ox+38, oy+38], radius=8, outline=c, width=3)
    draw.rounded_rectangle([ox+9, oy+12, ox+31, oy+23], radius=4, outline=c, width=2)
    draw.rounded_rectangle([ox+14, oy+16, ox+26, oy+20], radius=2, fill=c)


def _ic_bmi(draw, ox, oy, c):
    """Speedometer gauge: semicircle arc + radial tick marks + needle."""
    import math
    cx, cy = ox + 20, oy + 28
    R = 15
    draw.arc([cx-R, cy-R, cx+R, cy+R], start=200, end=340, fill=c, width=3)
    for ang in [205, 222, 242, 270, 298, 318, 335]:
        a = math.radians(ang)
        r_in = R - 7 if ang == 270 else R - 5
        draw.line(
            [(cx + int(r_in * math.cos(a)), cy + int(r_in * math.sin(a))),
             (cx + int(R     * math.cos(a)), cy + int(R     * math.sin(a)))],
            fill=c, width=2)
    a = math.radians(315)
    draw.line([(cx, cy),
               (cx + int(11 * math.cos(a)), cy + int(11 * math.sin(a)))],
              fill=c, width=2)
    draw.ellipse([cx-2, cy-2, cx+2, cy+2], fill=c)


def _ic_fat(draw, ox, oy, c):
    """Person outline with % symbol on body (body fat %)."""
    draw.ellipse([ox+13, oy+1, ox+27, oy+14], outline=c, width=2)
    draw.arc([ox+5, oy+12, ox+35, oy+29], start=0, end=180, fill=c, width=2)
    draw.line([(ox+5,  oy+20), (ox+5,  oy+38)], fill=c, width=2)
    draw.line([(ox+35, oy+20), (ox+35, oy+38)], fill=c, width=2)
    draw.line([(ox+5,  oy+38), (ox+35, oy+38)], fill=c, width=2)
    draw.line([(ox+13, oy+34), (ox+27, oy+22)], fill=c, width=2)
    draw.ellipse([ox+10, oy+20, ox+16, oy+26], outline=c, width=2)
    draw.ellipse([ox+24, oy+30, ox+30, oy+36], outline=c, width=2)


def _ic_muscle(draw, ox, oy, c):
    """Flexed arm (bicep): arch + two sides + wrist bar + peak curl."""
    draw.arc([ox+4, oy+4, ox+36, oy+24], start=180, end=360, fill=c, width=3)
    draw.line([(ox+4,  oy+14), (ox+4,  oy+38)], fill=c, width=3)
    draw.line([(ox+36, oy+14), (ox+36, oy+38)], fill=c, width=3)
    draw.rounded_rectangle([ox+4, oy+36, ox+36, oy+40], radius=2, fill=c)
    draw.arc([ox+4, oy+2, ox+18, oy+14], start=180, end=360, fill=c, width=2)


def _ic_water(draw, ox, oy, c):
    """Water drop: outline teardrop + horizontal wave inside."""
    cx = ox + 20
    draw.line([(cx, oy+2), (ox+7, oy+29)], fill=c, width=2)
    draw.line([(cx, oy+2), (ox+33, oy+29)], fill=c, width=2)
    draw.arc([ox+7, oy+18, ox+33, oy+40], start=0, end=180, fill=c, width=2)
    draw.arc([ox+9,  oy+26, ox+21, oy+34], start=180, end=0,   fill=c, width=2)
    draw.arc([ox+19, oy+26, ox+31, oy+34], start=0,   end=180, fill=c, width=2)


def _ic_bodytype(draw, ox, oy, c):
    """Person silhouette: circle head + shoulder arc + body sides + base."""
    draw.ellipse([ox+12, oy+1, ox+28, oy+17], outline=c, width=2)
    draw.arc([ox+5, oy+15, ox+35, oy+31], start=0, end=180, fill=c, width=2)
    draw.line([(ox+5,  oy+23), (ox+8,  oy+38)], fill=c, width=2)
    draw.line([(ox+35, oy+23), (ox+32, oy+38)], fill=c, width=2)
    draw.line([(ox+8,  oy+38), (ox+32, oy+38)], fill=c, width=2)


def generate_summary_card(patient, measurement) -> str | None:
    """Generate a 6-tile metric summary card. Returns base64 PNG."""
    try:
        COLS, ROWS  = 2, 3
        IMG_W       = 800
        MARGIN, GAP = 18, 14
        TILE_W      = (IMG_W - 2 * MARGIN - GAP) // 2          # 375
        TILE_H      = 190
        IMG_H       = 2 * MARGIN + ROWS * TILE_H + (ROWS - 1) * GAP  # 634

        bmi     = _calc_bmi(measurement.weight, patient.height_cm)
        fat_pct = measurement.body_fat_pct
        muscle  = measurement.muscle_mass
        water   = measurement.water_kg
        weight  = measurement.weight
        is_male = patient.is_male

        bmi_st    = _cs_bmi(bmi)
        weight_st = _cs(bmi_st["label"], bmi_st["type"])
        fat_st    = _cs_fat(fat_pct, is_male)
        mus_st    = _cs_muscle(muscle, weight, is_male)
        wat_st    = _cs_water(water, weight, is_male)
        bt        = _cs_bodytype(fat_pct, is_male)

        # (label, value, unit, status, icon_fn, colored_value)
        tiles = [
            (_p("وزن"),          f"{weight:.1f}",                      "kg", weight_st, _ic_weight,   False),
            ("BMI",               f"{bmi:.1f}" if bmi else "—",          "",  bmi_st,    _ic_bmi,      False),
            (_p("چربی بدن"),     f"{fat_pct:.1f}" if fat_pct else "—", "%" , fat_st,    _ic_fat,      False),
            (_p("توده عضلانی"),  f"{muscle:.1f}" if muscle else "—",    "kg", mus_st,    _ic_muscle,   False),
            (_p("آب بدن"),       f"{water:.1f}"  if water  else "—",    "kg", wat_st,    _ic_water,    False),
            (_p("تیپ بدنی"),     _p(bt["label"]),                        "",  bt,         _ic_bodytype, True),
        ]

        img  = Image.new("RGB", (IMG_W, IMG_H), (241, 245, 249))
        draw = ImageDraw.Draw(img)

        fnt_label  = _pil_font(10)
        fnt_value  = _pil_font(28)
        fnt_unit   = _pil_font(13)
        fnt_status = _pil_font(13)

        for idx, (label, value, unit, status, icon_fn, colored_val) in enumerate(tiles):
            row, col = divmod(idx, COLS)
            tx = MARGIN + col * (TILE_W + GAP)
            ty = MARGIN + row * (TILE_H + GAP)

            sc     = _CARD_PALETTE.get(status["type"], _CARD_PALETTE["info"])
            line_c = sc["line"]
            text_c = sc["text"]

            # Drop shadow
            draw.rounded_rectangle(
                [tx+3, ty+3, tx+TILE_W+3, ty+TILE_H+3],
                radius=14, fill=(210, 218, 228))
            # White tile background
            draw.rounded_rectangle(
                [tx, ty, tx+TILE_W, ty+TILE_H],
                radius=14, fill=(255, 255, 255))

            # Icon (40×40 box at tile+14, tile+14)
            icon_fn(draw, tx+14, ty+14, line_c)

            # Metric label (small, gray, right of icon)
            draw.text((tx+60, ty+26), label, fill=(156, 163, 175), font=fnt_label)

            # Colored straight line below icon
            draw.line([(tx+14, ty+62), (tx+TILE_W-14, ty+62)],
                      fill=line_c, width=3)

            # Value + unit
            if colored_val:
                draw.text((tx+14, ty+74), value, fill=text_c, font=fnt_value)
            else:
                draw.text((tx+14, ty+74), value, fill=(17, 24, 39), font=fnt_value)
                if unit:
                    vw, _ = _text_size(draw, value, fnt_value)
                    draw.text((tx+14+vw+4, ty+93), unit,
                              fill=(107, 114, 128), font=fnt_unit)
                draw.text(
                    (tx+14, ty+TILE_H-34), _p(status["label"]),
                    fill=text_c, font=fnt_status)

        buf = io.BytesIO()
        img.save(buf, format="PNG", dpi=(150, 150))
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode("utf-8")
        logger.info("Summary card generated for patient %d.", patient.id)
        return encoded

    except Exception:
        logger.exception("Failed to generate summary card for patient %d.", patient.id)
        return None
