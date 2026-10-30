"""
Flask ML Microservice.
Exposes internal endpoints for OCR, Classification, and subsequent analytical modules.
Protected by X-Internal-Key header.
"""

import os
import tempfile
from flask import Flask, request, jsonify
from flask_cors import CORS
from src.ocr_engine import process_document
from src.classifier import DocumentClassifier

app = Flask(__name__)
CORS(app)

INTERNAL_KEY = os.environ.get("X_INTERNAL_KEY", "shared_internal_secret_key_placeholder")

# Eagerly initialize and cache models once on startup
print("Initializing ML service & loading model cache...")
classifier = DocumentClassifier.get_instance()
print("ML Service ready.")

@app.before_request
def authenticate_internal_call():
    # Allow health endpoint without key
    if request.path == "/health":
        return None
    key = request.headers.get("X-Internal-Key")
    if not key or key != INTERNAL_KEY:
        return jsonify({"error": "Unauthorized internal service request", "code": "INVALID_INTERNAL_KEY"}), 401

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "ml-service",
        "classifier_loaded": classifier.loaded,
        "classes": classifier.classes,
        "supported_features": ["ocr", "classifier", "preprocessing"]
    }), 200

@app.route("/ocr", methods=["POST"])
def ocr_endpoint():
    """Extracts text and preprocessing metadata from an uploaded file."""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    uploaded_file = request.files['file']
    filename = uploaded_file.filename
    ext = os.path.splitext(filename)[1].lower()
    
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        uploaded_file.save(tmp.name)
        tmp_path = tmp.name
        
    try:
        ocr_result = process_document(tmp_path)
        return jsonify(ocr_result), 200
    except Exception as e:
        return jsonify({"error": f"OCR processing failed: {str(e)}"}), 500
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

@app.route("/classify", methods=["POST"])
def classify_endpoint():
    """Classifies document from text or uploaded document file."""
    # Option 1: Direct text passed in JSON
    if request.is_json and "text" in request.json:
        text = request.json["text"]
        result = classifier.predict(text)
        return jsonify(result), 200
        
    # Option 2: Uploaded file to OCR then classify
    if 'file' in request.files:
        uploaded_file = request.files['file']
        ext = os.path.splitext(uploaded_file.filename)[1].lower()
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            uploaded_file.save(tmp.name)
            tmp_path = tmp.name
        try:
            ocr_res = process_document(tmp_path)
            text = ocr_res["text"]
            res = classifier.predict(text)
            res["ocr_confidence"] = ocr_res["confidence"]
            res["num_pages"] = ocr_res["num_pages"]
            return jsonify(res), 200
        except Exception as e:
            return jsonify({"error": f"Classification failed: {str(e)}"}), 500
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                    
    return jsonify({"error": "Provide either JSON payload with 'text' or multipart form with 'file'"}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
