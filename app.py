from flask import Flask, request, send_file, jsonify
from dotenv import load_dotenv
import psycopg2
import os
import io

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Database connection details from environment variables
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
BASE_URL = os.getenv("BASE_URL")
ACCESS_SECRET = os.getenv('ACCESS_SECRET')


# Helper function to get MIME type from filename
def get_mime_type(filename):
    extension = os.path.splitext(filename)[1].lower()
    if extension == ".png":
        return "image/png"
    elif extension in [".jpg", ".jpeg"]:
        return "image/jpeg"
    elif extension == ".gif":
        return "image/gif"
    elif extension == ".webp":
        return "image/webp"
    elif extension == ".bmp":
        return "image/bmp"
    elif extension == ".tiff":
        return "image/tiff"
    elif extension == ".avif":
        return "image/avif"
    else:
        return None


# Endpoint to insert an image into the database
@app.route("/upload", methods=["POST"])
def upload_image():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    filename = file.filename
    mime_type = get_mime_type(filename)
    print(filename, mime_type)
    if mime_type is None:
        return jsonify({"error": "Unsupported file type"}), 400

    # Read file data
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

        # Insert image into database
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
        image_url = f"{BASE_URL}/image/{image_id}"
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
        return jsonify({"error": str(e)}), 500


# Endpoint to retrieve an image by ID
@app.route("/image/<int:image_id>", methods=["GET"])
def get_image(image_id):
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
        return jsonify({"error": str(e)}), 500


@app.before_request
def check_secret():
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {ACCESS_SECRET}":
        return jsonify({"error": "Unauthorized"}), 401


@app.route("/")
def home():
    return "Hello, World!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8086)
