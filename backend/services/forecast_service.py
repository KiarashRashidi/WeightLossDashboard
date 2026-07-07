import logging

import numpy as np

logger = logging.getLogger(__name__)

try:
    import jdatetime
    _HAS_JDATETIME = True
except ImportError:
    _HAS_JDATETIME = False

# Recommended sustainable weight-loss pace, matching the guidance already given
# to patients in the "first_visit" template (0.5-1 kg/week ~= 2-4 kg/month).
MIN_NORMAL_RATE = 1.0
MAX_NORMAL_RATE = 4.0
DEFAULT_NORMAL_RATE = 2.0
OPTIMISTIC_MULTIPLIER = 1.5
OPTIMISTIC_CAP = 4.5
BAD_MULTIPLIER = 0.4
BAD_FLOOR = 0.3

SCENARIO_LABELS_FA = {
    "optimistic": "خوش‌بینانه",
    "normal": "متعادل",
    "bad": "محتاطانه",
}


def _monthly_rate_kg(measurements) -> float:
    """Fit a line through recent weights vs. days elapsed, return kg/month lost (positive = losing)."""
    recent = measurements[-6:] if len(measurements) > 6 else measurements
    first_day = recent[0].recorded_at
    days = np.array([(m.recorded_at - first_day).total_seconds() / 86400 for m in recent])
    weights = np.array([m.weight for m in recent])

    if len(set(days.tolist())) < 2:
        return 0.0

    slope_per_day, _ = np.polyfit(days, weights, 1)
    return -slope_per_day * 30.44  # kg/month; positive means losing weight


def _future_month_labels(start_date, n=6):
    labels = []
    if _HAS_JDATETIME:
        try:
            jdt = jdatetime.datetime.fromgregorian(datetime=start_date)
            year, month = jdt.year, jdt.month
            for _ in range(n):
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                labels.append(f"{year}/{month:02d}")
            return labels
        except Exception:
            pass

    year, month = start_date.year, start_date.month
    for _ in range(n):
        month += 1
        if month > 12:
            month = 1
            year += 1
        labels.append(f"{year}/{month:02d}")
    return labels


def compute_scenarios(measurements) -> dict | None:
    """
    Compute 6-month weight forecast milestones under 3 scenarios, derived from the
    patient's own recent measurement trend (not from LLM guessing).
    Returns None if there isn't enough data (fewer than 2 measurements).
    """
    if not measurements or len(measurements) < 2:
        return None

    current_weight = measurements[-1].weight
    fitted_rate = _monthly_rate_kg(measurements)

    if fitted_rate > 0:
        base_rate = min(max(fitted_rate, MIN_NORMAL_RATE), MAX_NORMAL_RATE)
    else:
        base_rate = DEFAULT_NORMAL_RATE

    optimistic_rate = min(base_rate * OPTIMISTIC_MULTIPLIER, OPTIMISTIC_CAP)
    bad_rate = max(base_rate * BAD_MULTIPLIER, BAD_FLOOR)

    def milestones(rate):
        return [round(current_weight - rate * i, 1) for i in range(1, 7)]

    scenarios = {
        "optimistic": {"rate": round(optimistic_rate, 2), "milestones": milestones(optimistic_rate)},
        "normal": {"rate": round(base_rate, 2), "milestones": milestones(base_rate)},
        "bad": {"rate": round(bad_rate, 2), "milestones": milestones(bad_rate)},
    }

    return {
        "current_weight": round(current_weight, 1),
        "base_rate_kg_per_month": round(base_rate, 2),
        "month_labels": _future_month_labels(measurements[-1].recorded_at),
        "scenarios": scenarios,
        "goal_weight": scenarios["normal"]["milestones"][-1],
    }


def format_forecast_summary(forecast: dict) -> str:
    """Render the computed forecast as plain text for the LLM to narrate around."""
    lines = [
        "6-Month Weight Forecast (pre-computed — use these exact numbers, do not invent different ones):",
        f"  Current weight: {forecast['current_weight']} kg",
        f"  6-month goal weight (normal scenario): {forecast['goal_weight']} kg",
        "",
    ]
    for key in ("optimistic", "normal", "bad"):
        sc = forecast["scenarios"][key]
        label = SCENARIO_LABELS_FA[key]
        milestone_str = ", ".join(
            f"month {i + 1} ({month_label}) = {w}kg"
            for i, (month_label, w) in enumerate(zip(forecast["month_labels"], sc["milestones"]))
        )
        lines.append(f"  {key.capitalize()} scenario ({label}), rate {sc['rate']} kg/month: {milestone_str}")

    return "\n".join(lines)
