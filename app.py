from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import psycopg2
from psycopg2 import pool
import os
import io
import logging

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Allow GET requests from any origin
CORS(app, resources={r"/<string:image_id>": {"methods": ["GET"], "origins": "*"}})

# Database connection pool
db_pool = None

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


@app.on_event("startup")
def setup_db_connection_pool():
    """Initialize the database connection pool when the app starts."""
    global db_pool
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        if db_pool:
            app.logger.info("Database connection pool created successfully.")
    except Exception as e:
        app.logger.error("Error creating database connection pool: %s", str(e))


@app.on_event("shutdown")
def close_db_pool():
    """Close the database connection pool when the app context ends."""
    global db_pool
    if db_pool:
        db_pool.closeall()
        app.logger.info("Database connection pool closed.")


def get_db_connection():
    """Get a database connection from the pool."""
    try:
        return db_pool.getconn()
    except Exception as e:
        app.logger.error("Error getting connection from pool: %s", str(e))
        raise


def release_db_connection(conn):
    """Release a database connection back to the pool."""
    try:
        db_pool.putconn(conn)
    except Exception as e:
        app.logger.error("Error releasing connection back to pool: %s", str(e))


@app.before_request
def pre_request_processing():
    """Log request details and restrict POST methods."""
    # Log request details
    app.logger.debug("Headers: %s", request.headers)
    app.logger.debug("Content-Type: %s", request.content_type)
    if request.content_type and "multipart/form-data" not in request.content_type:
        app.logger.warning("Request does not contain 'multipart/form-data'")
    # app.logger.debug("Body: %s", request.get_data(as_text=True))

    # Restrict POST requests to specific origin and validate ACCESS_SECRET
    if request.method == "POST":
        origin = request.headers.get("Origin")
        auth_header = request.headers.get("Authorization")

        if origin != ALLOWED_ORIGIN:
            app.logger.warning("Unauthorized origin: %s", origin)
            return jsonify({"error": "Unauthorized: Invalid origin"}), 403

        if auth_header != f"Bearer {ACCESS_SECRET}":
            app.logger.warning("Unauthorized access token")
            return jsonify({"error": "Unauthorized: Invalid access token"}), 401


def get_db_connection():
    """Get a database connection from the pool."""
    try:
        return db_pool.getconn()
    except Exception as e:
        app.logger.error("Error getting connection from pool: %s", str(e))
        raise


def release_db_connection(conn):
    """Release a database connection back to the pool."""
    try:
        db_pool.putconn(conn)
    except Exception as e:
        app.logger.error("Error releasing connection back to pool: %s", str(e))


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
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    filename = file.filename
    mime_type = get_mime_type(filename)

    if not mime_type:
        return jsonify({"error": "Unsupported file type"}), 400

    image_data = file.read()
    conn = None
    try:
        conn = get_db_connection()
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
    finally:
        if conn:
            release_db_connection(conn)


# Endpoint to retrieve an image by ID
@app.route("/<string:image_id>", methods=["GET"])
def get_image(image_id):
    """Retrieve an image by its ID."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Retrieve image from the database
        cur.execute(
            "SELECT image_data, mime_type FROM images WHERE id = %s", (image_id,)
        )
        result = cur.fetchone()
        cur.close()

        if result is None:
            return jsonify({"error": "Image not found"}), 404

        image_data, mime_type = result
        return send_file(io.BytesIO(image_data), mimetype=mime_type)
    except Exception as e:
        app.logger.error("Database error: %s", str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)


@app.route("/")
def home():
    """Home endpoint."""
    return "Hello, World!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
