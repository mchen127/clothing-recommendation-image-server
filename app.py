from flask import Flask, request, send_file, jsonify, g
from flask_cors import CORS
from dotenv import load_dotenv
import psycopg2
from psycopg2 import pool
import os
import io
import logging

# Load environment variables
load_dotenv()


def create_app():
    """Application factory to set up the Flask app and resources."""
    app = Flask(__name__)
    CORS(app, resources={r"/<string:image_id>": {"methods": ["GET"], "origins": "*"}})

    # Enable logging
    app.logger.setLevel(logging.DEBUG)

    # Database connection pool setup
    db_pool = psycopg2.pool.SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

    if not db_pool:
        raise RuntimeError("Failed to create the database connection pool.")

    @app.before_request
    def pre_request_processing():
        """Log request details and restrict POST methods."""
        # Log request details
        app.logger.debug("Headers: %s", request.headers)
        app.logger.debug("Content-Type: %s", request.content_type)
        if request.content_type and "multipart/form-data" not in request.content_type:
            app.logger.warning("Request does not contain 'multipart/form-data'")
        # Restrict POST requests to specific origin and validate ACCESS_SECRET
        # if request.method == "POST":
        #     origin = request.headers.get("Origin")
        #     auth_header = request.headers.get("Authorization")

        #     if origin != os.getenv("ALLOWED_ORIGIN"):
        #         app.logger.warning("Unauthorized origin: %s", origin)
        #         return jsonify({"error": "Unauthorized: Invalid origin"}), 403

        #     if auth_header != f"Bearer {os.getenv('ACCESS_SECRET')}":
        #         app.logger.warning("Unauthorized access token")
        #         return jsonify({"error": "Unauthorized: Invalid access token"}), 401

    @app.teardown_appcontext
    def close_db_pool(exception):
        """Close the database connection pool when the app context ends."""
        if hasattr(g, "db_conn"):
            db_pool.putconn(g.db_conn)
        if exception:
            app.logger.error("Exception during teardown: %s", exception)
        app.logger.info("Database connection returned to pool.")

    def get_db_connection():
        """Get a database connection from the pool."""
        if not hasattr(g, "db_conn"):
            g.db_conn = db_pool.getconn()
        return g.db_conn

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
        try:
            conn = get_db_connection()
            cur = conn.cursor()
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

            image_url = f"{os.getenv('BASE_URL')}/{image_id}"
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

    @app.route("/<string:image_id>", methods=["GET"])
    def get_image(image_id):
        """Retrieve an image by its ID."""
        try:
            conn = get_db_connection()
            cur = conn.cursor()
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

    @app.route("/")
    def home():
        return "Hello, World!"

    return app


def get_mime_type(filename):
    """Helper function to get MIME type from filename."""
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


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
