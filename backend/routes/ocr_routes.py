import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

logger = logging.getLogger(__name__)
ocr_bp = Blueprint("ocr", __name__)


@ocr_bp.route("/analyze", methods=["POST"])
@jwt_required()
def analyze():
    """
    Accept a smart scale screenshot and return extracted measurement fields.

    Accepts either:
      - multipart/form-data with field 'image' (file upload)
      - application/json with field 'image' (base64 data-URL or raw base64)
    """
    from services.ocr_service import analyze_image, analyze_base64_image

    if "image" in request.files:
        image_bytes = request.files["image"].read()
        if not image_bytes:
            return jsonify({"error": "Uploaded file is empty."}), 400
        result = analyze_image(image_bytes)
    elif request.is_json:
        b64 = (request.json or {}).get("image", "")
        if not b64:
            return jsonify({"error": "No 'image' field in JSON body."}), 400
        result = analyze_base64_image(b64)
    else:
        return jsonify({"error": "Provide image as multipart file or JSON base64."}), 400

    if "error" in result:
        return jsonify(result), 422

    # Remove internal debug key before returning to client
    result.pop("_ocr_text", None)
    return jsonify(result)
