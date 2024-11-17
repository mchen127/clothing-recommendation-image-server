from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import psycopg2
import os
import io
import logging

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Allow GET requests from any origin
CORS(app, resources={r"/<string:image_id>": {"methods": ["GET"], "origins": "*"}})

# Database connection details from environment variables
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
BASE_URL = os.getenv("BASE_URL")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN")
ACCESS_SECRET = os.getenv("ACCESS_SECRET")

# Enable logging
app.logger.setLevel(logging.DEBUG)


@app.before_request
def log_request_info():
    """Log request headers and body for debugging."""
    app.logger.debug("Headers: %s", request.headers)
    app.logger.debug("Content-Type: %s", request.content_type)
    if request.content_type and "multipart/form-data" not in request.content_type:
        app.logger.warning("Request does not contain 'multipart/form-data'")
    app.logger.debug("Body: %s", request.get_data(as_text=True))


@app.before_request
def limit_methods():
    """Restrict POST requests to a specific origin and validate ACCESS_SECRET."""
    if request.method == "POST":
        origin = request.headers.get("Origin")
        auth_header = request.headers.get("Authorization")

        if origin != ALLOWED_ORIGIN:
            return jsonify({"error": "Unauthorized: Invalid origin"}), 403

        if auth_header != f"Bearer {ACCESS_SECRET}":
            return jsonify({"error": "Unauthorized: Invalid access token"}), 401


# Helper function to get MIME type from filename
def get_mime_type(filename):
    extension = os.path.splitext(filename)[1].lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
        ".avif": "image/avif",
    }
    return mime_types.get(extension)


# Endpoint to insert an image into the database
@app.route("/upload", methods=["POST"])
def upload_image():
    """Upload an image and store it in the database."""
    # Check if the request contains a file
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    filename = file.filename
    mime_type = get_mime_type(filename)

    if not mime_type:
        return jsonify({"error": "Unsupported file type"}), 400

    # Read the file data as binary
    image_data = file.read()

    try:
        # Connect to the database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        cur = conn.cursor()

        # Insert image into the database
        cur.execute(
            """
            INSERT INTO images (image_name, image_data, mime_type)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (filename, psycopg2.Binary(image_data), mime_type),
        )

        image_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        # Construct the URL to access the image
        image_url = f"{BASE_URL}/{image_id}"
        return (
            jsonify(
                {
                    "message": "Image uploaded successfully",
                    "id": image_id,
                    "url": image_url,
                }
            ),
            201,
        )

    except Exception as e:
        app.logger.error("Database error: %s", str(e))
        return jsonify({"error": str(e)}), 500


# Endpoint to retrieve an image by ID
@app.route("/<string:image_id>", methods=["GET"])
def get_image(image_id):
    """Retrieve an image by its ID."""
    try:
        # Connect to the database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        cur = conn.cursor()

        # Retrieve image from the database
        cur.execute(
            "SELECT image_data, mime_type FROM images WHERE id = %s", (image_id,)
        )
        result = cur.fetchone()
        cur.close()
        conn.close()

        if result is None:
            return jsonify({"error": "Image not found"}), 404

        image_data, mime_type = result
        return send_file(io.BytesIO(image_data), mimetype=mime_type)
    except Exception as e:
        app.logger.error("Database error: %s", str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    """Home endpoint."""
    return "Hello, World!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
