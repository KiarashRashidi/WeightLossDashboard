import logging
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required

from models import Patient, Measurement
from services.gapgpt_service import generate_patient_report
from services.bale_service import send_bale_message, send_bale_photo
from services.chart_service import (
    generate_progress_chart, generate_table_image, generate_summary_card, generate_forecast_chart,
)
from services.forecast_service import compute_scenarios, format_forecast_summary

logger = logging.getLogger(__name__)
messaging_bp = Blueprint("messaging", __name__)


def _to_jalali(dt):
    """Convert datetime to Jalali date string."""
    try:
        import jdatetime
        jdt = jdatetime.datetime.fromgregorian(datetime=dt)
        return f"{jdt.year}/{jdt.month:02d}/{jdt.day:02d}"
    except Exception:
        return dt.strftime('%Y/%m/%d') if hasattr(dt, 'strftime') else str(dt)


PRESET_PROMPTS = [
    {
        "id": "comprehensive",
        "label": "Comprehensive Report",
        "description": "Full progress report with clinical analysis of all metrics, trends, and personalized lifestyle recommendations.",
        "text": (
            "You are an expert bariatric physician writing a professional medical progress report in Persian (Farsi) "
            "for a weight-loss patient. Based on the provided measurement data, write a comprehensive, elegant "
            "clinical report that includes:\n"
            "1. A warm, professional greeting addressing the patient by name\n"
            "2. A precise clinical analysis of the patient's current health status: weight trend direction and rate "
            "of change, body fat percentage improvements, muscle mass preservation or development, and hydration levels\n"
            "3. A comparison between the earliest and most recent measurements, with specific numbers and percentages "
            "highlighting progress\n"
            "4. A personalized lifestyle recommendations section covering: optimal nutritional strategy for their "
            "current phase (protein intake, meal timing, foods to focus on), appropriate exercise prescription "
            "(cardio and resistance training balance), sleep quality, and stress management\n"
            "5. A strong motivational closing that acknowledges their specific achievements\n"
            "Write in a warm yet authoritative medical tone. Use formal Persian (Farsi). 280-340 words. "
            "Structure with clear paragraphs. The report should feel personalized, not generic."
        ),
    },
    {
        "id": "plateau",
        "label": "Plateau Analysis",
        "description": "Scientific explanation of why the weight has stalled with 4 specific, evidence-based strategies to break through.",
        "text": (
            "You are a bariatric specialist writing in Persian (Farsi). The patient's weight has plateaued. "
            "Write a professional, scientifically-grounded message that:\n"
            "1. Acknowledges the plateau with empathy and immediately normalizes it as a known physiological response\n"
            "2. Provides a clear, accessible medical explanation of why weight plateaus occur: metabolic adaptation, "
            "glycogen and water shifts, increased muscle density, and hormonal adjustments\n"
            "3. Analyzes the patient's other metrics (body fat %, muscle mass, water retention) to show progress "
            "happening even when scale weight stalls\n"
            "4. Gives 4 specific, evidence-based strategies to break through the plateau: dietary caloric cycling, "
            "exercise variation or intensity increase, sleep and cortisol management, and intermittent fasting "
            "considerations appropriate for their stage\n"
            "5. Sets realistic expectations for the coming 2-3 weeks with an encouraging close\n"
            "Use precise but accessible language. 260-310 words in formal Persian."
        ),
    },
    {
        "id": "first_visit",
        "label": "First Visit Welcome",
        "description": "AI writes a short personalized Persian greeting about the patient's specific weight goals, then a predefined general-guidance section is appended automatically.",
        "text": None,  # composed server-side — see FIRST_VISIT_PROMPT / FIRST_VISIT_GENERAL_TEXT below
    },
    {
        "id": "motivation",
        "label": "Motivation Recovery",
        "description": "Empowering message for patients feeling discouraged — highlights every positive change and sets achievable mini-goals.",
        "text": (
            "You are a compassionate bariatric health coach and psychologist writing in Persian (Farsi). "
            "The patient may be struggling with motivation, consistency, or feeling discouraged. "
            "Write an empowering, psychologically-informed message that:\n"
            "1. Opens with genuine acknowledgment of how mentally and physically challenging the weight-loss "
            "journey truly is — no toxic positivity\n"
            "2. Reframes any setbacks using positive psychology: every attempt teaches something, the process "
            "itself creates health benefits even without perfect numbers\n"
            "3. Reviews the patient's data and highlights EVERY positive change, no matter how small — "
            "even 0.1 kg muscle gain or 0.5% fat reduction deserves recognition\n"
            "4. Provides 3 concrete, immediately achievable mini-goals for the next 2 weeks that build momentum\n"
            "5. Includes one powerful behavioral insight about sleep, stress, or mindful eating that directly "
            "impacts weight regulation\n"
            "6. Closes with a personalized, powerful statement that connects their specific data to their "
            "future potential\n"
            "Be warm, empathetic, and genuinely encouraging without being dismissive. "
            "240-290 words in formal Persian."
        ),
    },
    {
        "id": "lifestyle",
        "label": "Lifestyle Prescription",
        "description": "Detailed personalized plan covering nutrition, exercise, sleep, hydration, and one key behavioral change for this week.",
        "text": (
            "You are a bariatric nutritionist and lifestyle medicine specialist writing in Persian (Farsi). "
            "Based on the patient's current body composition data, write a detailed, highly personalized "
            "lifestyle prescription that includes:\n"
            "1. Nutritional strategy tailored to their current composition: target macronutrient ratios "
            "(protein/carbs/healthy fats) with specific examples, meal frequency and timing for their "
            "phase of weight loss, priority foods to include and foods to minimize\n"
            "2. Exercise prescription appropriate for their current weight and fitness level: specific cardio "
            "type, duration and frequency (e.g., 30 min moderate walking 5x/week), resistance training focus "
            "and why it's critical for preserving muscle during weight loss, NEAT (non-exercise activity "
            "thermogenesis) strategies for daily life\n"
            "3. Sleep and recovery protocol: target sleep duration, sleep hygiene practices that specifically "
            "affect appetite hormones (ghrelin/leptin), and why poor sleep stalls fat loss\n"
            "4. Hydration and key micronutrients: daily water target, timing of water intake, "
            "top 3 supplements to consider for their situation\n"
            "5. One key behavioral change to prioritize this week above all else\n"
            "Write with clinical precision in accessible language. 320-370 words in formal Persian."
        ),
    },
    {
        "id": "reminder",
        "label": "Visit Reminder",
        "description": "Friendly, concise reminder to schedule a follow-up — explains the medical value of check-ins and includes one actionable tip.",
        "text": (
            "You are a caring bariatric physician writing in Persian (Farsi) to remind a patient to "
            "schedule their next follow-up appointment. Write a friendly, professional message that:\n"
            "1. Opens with a warm, personal greeting that shows genuine interest in their wellbeing\n"
            "2. Briefly acknowledges the time since their last visit without making them feel guilty\n"
            "3. Explains two specific medical reasons why regular monitoring is essential: early plateau "
            "detection and intervention, and keeping metabolic adaptation in check\n"
            "4. Mentions one concrete benefit they'll receive at their next visit "
            "(updated body composition analysis, adjusted plan)\n"
            "5. Offers one actionable health tip they can implement right now, before their appointment\n"
            "6. Closes with a warm, welcoming invitation that makes them feel excited to return, not obligated\n"
            "Keep it concise (160-200 words), warm, and motivating in formal Persian."
        ),
    },
    {
        "id": "forecast_plan",
        "label": "6-Month Forecast Plan",
        "description": "AI-narrated 6-month weight forecast across optimistic, normal, and cautious scenarios, based on the patient's actual trend, with a chart and goal-setting explanation.",
        "text": None,  # not user-editable — see FORECAST_PROMPT below
    },
]


FIRST_VISIT_PROMPT = (
    "You are an expert, compassionate bariatric physician. Your task is to write a warm, personalized "
    "welcome message to a new patient who is starting a weight-loss medication program.\n\n"
    "Write the response ENTIRELY in formal, polite, and compassionate Persian (Farsi).\n\n"
    "Use the given patient data (name, current weight, target/ideal weight, and any specific health "
    "conditions/notes) to personalize the message. If no target weight is given, speak with confidence "
    "about reaching a healthy weight without inventing a specific number. If no health conditions/notes "
    "are given, simply skip that part.\n\n"
    "Instructions for the message:\n"
    "1. Greet the patient warmly by name.\n"
    "2. Congratulate them on taking this brave and important step toward better health.\n"
    "3. Acknowledge their current weight and their goal weight, expressing strong confidence that you "
    "will achieve this target together.\n"
    "4. If specific health conditions are provided, briefly and empathetically mention how this "
    "weight-loss journey will help improve those specific conditions.\n"
    "5. Keep the tone highly encouraging, medical, and professional.\n"
    "6. DO NOT include general advice about diet, exercise, medication side effects, or follow-up "
    "schedules — that will be provided separately.\n"
    "7. End the message with exactly this transition sentence, verbatim, as the final line, and add "
    "nothing after it:\n"
    "\"در ادامه، چند نکته بسیار مهم وجود دارد که برای موفقیت در این مسیر باید به آن‌ها توجه داشته باشید:\""
)

FIRST_VISIT_GENERAL_TEXT = (
    "در حالی که این دارو ابزاری بسیار مؤثر برای کمک به شما جهت رسیدن ایمن به وزن ایده‌آل است، لطفاً به خاطر "
    "داشته باشید که موفقیت پایدار و طولانی‌مدت در نهایت به تغییرات ماندگار در سبک زندگی بستگی دارد. پایبندی "
    "به یک رژیم غذایی سالم و متعادل و همچنین داشتن یک برنامه ورزشی منظم برای حفظ نتایج شما کاملاً ضروری "
    "است.\n\n"
    "برای کمک به سیستم گوارش و به حداکثر رساندن فواید درمان، اکیداً توصیه می‌کنیم وعده‌های غذایی کوچک و "
    "مکرر داشته باشید و سعی کنید غذا را به آرامی و کامل بجوید. نوشیدن مایعات کافی در طول روز و افزایش "
    "تدریجی فیبر دریافتی از اهمیت بالایی برخوردار است. علاوه بر این، لطفاً از مصرف غذاهای چرب، سنگین و "
    "نوشیدنی‌های گازدار خودداری کنید، زیرا این موارد می‌توانند باعث ناراحتی‌های گوارشی قابل‌توجهی شوند.\n\n"
    "سلامتی و ایمنی شما بالاترین اولویت ماست. لطفاً حتماً ما را در جریان هرگونه دارو یا مکمل دیگری که در "
    "حال حاضر مصرف می‌کنید قرار دهید. ما ویزیت‌های دوره‌ای را هر یک ماه یک‌بار تنظیم خواهیم کرد تا روند "
    "پیشرفت، فشار خون و سطح قند خون شما را به دقت ارزیابی کنیم. در نهایت، با سازگار شدن بدنتان با شرایط "
    "جدید، لطفاً به علائم خود توجه داشته باشید؛ در صورت تجربه درد شکم، سوءهاضمه، سوزش سر دل مداوم، ریزش "
    "مو، یا هرگونه واکنش در محل تزریق، حتماً با کلینیک تماس بگیرید تا بتوانیم در سریع‌ترین زمان ممکن به "
    "آن‌ها رسیدگی کرده و اطمینان حاصل کنیم که مسیر درمان شما در کمال آرامش و راحتی پیش می‌رود."
)


FORECAST_PROMPT = (
    "You are a bariatric physician writing in Persian (Farsi) to explain a 6-month weight forecast to a patient. "
    "You are given the patient's measurement history plus THREE pre-computed 6-month projections (optimistic, "
    "normal, and cautious scenarios) with exact monthly weight milestones — these numbers are already calculated; "
    "do not invent different numbers, only reference the ones given. Write a message that:\n"
    "1. States the 6-month goal weight (the 'normal' scenario's final milestone) and frames it as an achievable, "
    "medically grounded target\n"
    "2. Explains WHY this specific goal was set — referencing the patient's own recent rate of progress, current "
    "body composition, and realistic physiological limits of sustainable weight loss\n"
    "3. Briefly describes what happens along the way in each of the three scenarios (optimistic/normal/cautious) "
    "using the given monthly milestones, in plain and encouraging language\n"
    "4. Explains concretely what behaviors move the patient from the cautious path toward the optimistic path "
    "(adherence, consistency, specific actions)\n"
    "5. Closes with a motivating statement connecting today's data to the 6-month goal\n"
    "Use formal, warm Persian. 240-300 words. Do not use markdown formatting."
)


@messaging_bp.route("/templates", methods=["GET"])
@jwt_required()
def get_templates():
    return jsonify(PRESET_PROMPTS)


@messaging_bp.route("/generate-report", methods=["POST"])
@jwt_required()
def generate_report():
    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id")
    custom_prompt = data.get("prompt", "")
    template_id    = data.get("template_id")
    report_type    = data.get("report_type", "standard")
    include_chart   = data.get("include_chart",   True)
    include_table   = data.get("include_table",   True)
    include_report  = data.get("include_report",  True)
    include_summary = data.get("include_summary", False)

    if not patient_id:
        return jsonify({"error": "patient_id is required."}), 400

    patient = Patient.query.get_or_404(patient_id)
    measurements = (
        Measurement.query.filter_by(patient_id=patient_id)
        .order_by(Measurement.recorded_at)
        .all()
    )

    if report_type == "forecast":
        if len(measurements) < 2:
            return jsonify({"error": "Need at least 2 measurements to build a forecast."}), 400

        forecast = compute_scenarios(measurements)

        report_text = None
        if include_report:
            history_summary = _build_history_summary(patient, measurements) + "\n\n" + format_forecast_summary(forecast)
            report_text = generate_patient_report(prompt=FORECAST_PROMPT, data=history_summary)
            if report_text is None:
                return jsonify({"error": "GapGPT API failed. Please retry.", "retry": True}), 502

        chart_base64 = generate_forecast_chart(patient, measurements, forecast) if include_chart else None

        return jsonify({
            "report_text":    report_text,
            "chart_base64":   chart_base64,
            "table_base64":   None,
            "summary_base64": None,
            "patient_name":   patient.name,
        })

    report_text = None
    if include_report:
        if template_id == "first_visit":
            first_visit_data = _build_first_visit_summary(patient, measurements)
            ai_text = generate_patient_report(prompt=FIRST_VISIT_PROMPT, data=first_visit_data)
            if ai_text is None:
                return jsonify({"error": "GapGPT API failed. Please retry.", "retry": True}), 502
            report_text = ai_text.strip() + "\n\n" + FIRST_VISIT_GENERAL_TEXT
        else:
            if not custom_prompt:
                return jsonify({"error": "prompt is required when include_report is true."}), 400
            history_summary = _build_history_summary(patient, measurements)
            report_text = generate_patient_report(prompt=custom_prompt, data=history_summary)
            if report_text is None:
                return jsonify({"error": "GapGPT API failed. Please retry.", "retry": True}), 502

    chart_base64 = None
    if include_chart and len(measurements) >= 2:
        chart_base64 = generate_progress_chart(patient, measurements)

    table_base64 = None
    if include_table and len(measurements) >= 1:
        table_base64 = generate_table_image(patient, measurements)

    summary_base64 = None
    if include_summary and len(measurements) >= 1:
        summary_base64 = generate_summary_card(patient, measurements[-1])

    return jsonify({
        "report_text":   report_text,
        "chart_base64":  chart_base64,
        "table_base64":  table_base64,
        "summary_base64": summary_base64,
        "patient_name":  patient.name,
    })


@messaging_bp.route("/send", methods=["POST"])
@jwt_required()
def send_message():
    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id")
    report_type = data.get("report_type", "standard")
    message = data.get("message", "").strip()
    chart_base64   = data.get("chart_base64")
    table_base64   = data.get("table_base64")
    summary_base64 = data.get("summary_base64")
    send_report  = data.get("send_report",  True)
    send_chart   = data.get("send_chart",   True)
    send_table   = data.get("send_table",   True)
    send_summary = data.get("send_summary", False)

    if not patient_id:
        return jsonify({"error": "patient_id is required."}), 400

    patient = Patient.query.get_or_404(patient_id)
    if not patient.bale_chat_id:
        return jsonify({"error": "This patient has no linked Bale account."}), 400

    token = current_app.config["BALE_BOT_TOKEN"]
    sent = []
    failed = []

    if send_summary and summary_base64:
        caption = "📊 کارت وضعیت اندازه‌گیری"
        result = send_bale_photo(token, patient.bale_chat_id, summary_base64, caption=caption)
        (sent if result else failed).append("summary")

    if send_table and table_base64:
        caption = "📋 جدول سوابق اندازه‌گیری"
        result = send_bale_photo(token, patient.bale_chat_id, table_base64, caption=caption)
        (sent if result else failed).append("table")

    if send_chart and chart_base64:
        caption = "🔮 نمودار پیش‌بینی ۶ ماهه" if report_type == "forecast" else "📈 نمودار پیشرفت"
        result = send_bale_photo(token, patient.bale_chat_id, chart_base64, caption=caption)
        (sent if result else failed).append("chart")

    if send_report and message:
        result = send_bale_message(token, patient.bale_chat_id, message)
        (sent if result else failed).append("report")

    if not sent and not failed:
        return jsonify({"error": "Nothing was selected to send."}), 400

    if failed and not sent:
        return jsonify({"error": "All sends failed. Check your bot token and patient chat ID."}), 502

    logger.info("Bale send to patient %d — sent: %s, failed: %s", patient_id, sent, failed)
    return jsonify({"sent": sent, "failed": failed})


@messaging_bp.route("/bulk-send", methods=["POST"])
@jwt_required()
def bulk_send():
    data = request.get_json(silent=True) or {}
    patient_ids = data.get("patient_ids", [])
    message = data.get("message", "").strip()

    if not patient_ids or not message:
        return jsonify({"error": "patient_ids and message are required."}), 400

    token = current_app.config["BALE_BOT_TOKEN"]
    results = {"sent": [], "failed": [], "no_bale": []}

    for pid in patient_ids:
        patient = Patient.query.get(pid)
        if not patient:
            continue
        if not patient.bale_chat_id:
            results["no_bale"].append({"id": pid, "name": patient.name})
            continue

        result = send_bale_message(token, patient.bale_chat_id, message)
        if result:
            results["sent"].append({"id": pid, "name": patient.name})
        else:
            results["failed"].append({"id": pid, "name": patient.name})

    logger.info(
        "Bulk send: %d sent, %d failed, %d no Bale.",
        len(results["sent"]), len(results["failed"]), len(results["no_bale"])
    )
    return jsonify(results)


def _build_first_visit_summary(patient, measurements):
    lines = [f"Patient Name: {patient.name}"]
    if measurements:
        latest = measurements[-1]
        lines.append(f"Current Weight: {latest.weight} kg")
        if latest.notes:
            lines.append(f"Specific Health Conditions/Notes: {latest.notes}")
    if patient.target_weight:
        lines.append(f"Target/Ideal Weight: {patient.target_weight} kg")
    return "\n".join(lines)


def _build_history_summary(patient, measurements):
    lines = [
        f"Patient: {patient.name}",
        f"Age: {patient.age}, Height: {patient.height_cm} cm, "
        f"Sex: {'Male' if patient.is_male else 'Female'}",
        "",
        "Measurement History (dates in Jalali/Persian calendar):",
    ]
    for m in measurements[-12:]:
        lines.append(
            f"  {_to_jalali(m.recorded_at)}: "
            f"Weight={m.weight} kg, Body Fat={m.body_fat_pct}%, "
            f"Fat Mass={m.fat_mass} kg, Muscle={m.muscle_mass} kg, Water={m.water_kg} kg"
            + (f", Notes: {m.notes}" if m.notes else "")
        )

    if len(measurements) >= 2:
        first = measurements[0]
        last = measurements[-1]
        delta_w = last.weight - first.weight
        delta_fat = (last.body_fat_pct or 0) - (first.body_fat_pct or 0)
        delta_muscle = (last.muscle_mass or 0) - (first.muscle_mass or 0)
        lines.append(
            f"\nSummary since {_to_jalali(first.recorded_at)}:"
            f"\n  Weight change: {delta_w:+.1f} kg"
            f"\n  Body fat change: {delta_fat:+.1f}%"
            f"\n  Muscle change: {delta_muscle:+.1f} kg"
            f"\n  Total visits: {len(measurements)}"
        )

    return "\n".join(lines)
