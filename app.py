import flask
from flask import render_template
from flask_cors import CORS
import sqlite3
import os
import json
import base64
import uuid
import time
import click # <--- IMPORT CLICK

# --- Flask App Setup ---
app = flask.Flask(__name__)
CORS(app)

# --- Persistent Storage Configuration for Render ---
# Make sure you have created a Disk on Render with a mount path of /var/data
DATA_DIR = '/var/data'
DATABASE_NAME = 'TCF_props.db'
DATABASE = os.path.join(DATA_DIR, DATABASE_NAME)
UPLOAD_FOLDER_NAME = 'uploads'
UPLOAD_FOLDER = os.path.join(DATA_DIR, UPLOAD_FOLDER_NAME)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# This check should now be part of the init_db command logic
# if not os.path.exists(UPLOAD_FOLDER):
#     os.makedirs(UPLOAD_FOLDER)

# --- Database Functions ---
def get_db():
    db = getattr(flask.g, '_database', None)
    if db is None:
        db = flask.g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(flask.g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database and creates tables."""
    # Check for upload folder and create it
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
        print(f"INFO: Created upload folder at: '{app.config['UPLOAD_FOLDER']}'")

    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()
    print(f"INFO_INIT_DB: Database initialized and tables created in '{DATABASE}'.")

# NEW: Define a command-line command `flask init-db`
@app.cli.command('init-db')
def init_db_command():
    """Clears the existing data and creates new tables."""
    init_db()
    click.echo('Initialized the database.')


# --- HTML Rendering Route ---
@app.route('/')
def index():
    """Renders the main unified HTML page."""
    return render_template('index.html')

# --- API Endpoints (No changes needed here) ---

@app.route('/api/locations', methods=['GET'])
def get_locations_api():
    db = get_db()
    # ... (rest of the function is the same)
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, name FROM locations ORDER BY name ASC")
        locations_rows = cursor.fetchall()
        locations_list = [dict(row) for row in locations_rows]
        return flask.jsonify(locations_list), 200
    except sqlite3.Error as e:
        print(f"DATABASE_ERROR_GET_LOCATIONS: {e}")
        return flask.jsonify({"error": f"Database error fetching locations: {str(e)}"}), 500

# ... (paste all your other API routes here: add_location_api, add_prop, etc.) ...
# All of your other functions like add_location_api, add_prop, get_props, update_prop, etc. go here unchanged.

# --- REMOVE a section ---
# We no longer need the if __name__ == '__main__' block to call init_db
# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=5000, debug=True)