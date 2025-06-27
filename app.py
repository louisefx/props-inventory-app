import flask
from flask import render_template
from flask_cors import CORS
import sqlite3
import os
import json
import base64
import uuid
import time
import click

# --- Flask App Setup ---
app = flask.Flask(__name__)
CORS(app)

# --- Persistent Storage Configuration for Render ---
DATA_DIR = '/var/data'
DATABASE_NAME = 'TCF_props.db'
DATABASE = os.path.join(DATA_DIR, DATABASE_NAME)
UPLOAD_FOLDER_NAME = 'uploads'
UPLOAD_FOLDER = os.path.join(DATA_DIR, UPLOAD_FOLDER_NAME)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Database Functions ---
def get_db():
    # Use getattr to safely access flask.g attributes
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
    """Initializes the database using schema.sql and creates upload folder."""
    # Check for upload folder and create it
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
        print(f"INFO: Created upload folder at: '{app.config['UPLOAD_FOLDER']}'")
    
    # Use a try-except block for robustness
    try:
        db = get_db()
        # Ensure the schema.sql file is being found
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
        print(f"INFO_INIT_DB: Database initialized from schema.sql in '{DATABASE}'.")
    except Exception as e:
        print(f"ERROR_INIT_DB: An error occurred during database initialization: {e}")


# --- NEW: Define a command-line command `flask init-db` ---
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


# --- ALL YOUR API ENDPOINTS ---
# These routes were likely missing before.

@app.route('/api/locations', methods=['GET'])
def get_locations_api():
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, name FROM locations ORDER BY name ASC")
        locations_rows = cursor.fetchall()
        locations_list = [dict(row) for row in locations_rows]
        return flask.jsonify(locations_list), 200
    except sqlite3.Error as e:
        print(f"DATABASE_ERROR_GET_LOCATIONS: {e}")
        # This will return a 500 if the "locations" table doesn't exist.
        return flask.jsonify({"error": f"Database error fetching locations: {str(e)}"}), 500

@app.route('/api/locations', methods=['POST'])
def add_location_api():
    db = get_db()
    cursor = db.cursor()
    if not flask.request.is_json:
        return flask.jsonify({"error": "Request must be JSON"}), 400
    data = flask.request.get_json()
    location_name = data.get('name')
    if not location_name or not location_name.strip():
        return flask.jsonify({"error": "Location name cannot be empty"}), 400
    location_name = location_name.strip()
    try:
        cursor.execute("INSERT INTO locations (name) VALUES (?)", (location_name,))
        db.commit()
        new_location_id = cursor.lastrowid
        print(f"SUCCESS_ADD_LOCATION: Location '{location_name}' (ID: {new_location_id}) added to database.")
        return flask.jsonify({"message": "Location added successfully!", "id": new_location_id, "name": location_name}), 201
    except sqlite3.IntegrityError:
        db.rollback()
        print(f"DATABASE_ERROR_ADD_LOCATION: Location '{location_name}' already exists.")
        return flask.jsonify({"error": f"Location '{location_name}' already exists."}), 409
    except sqlite3.Error as e:
        db.rollback()
        print(f"DATABASE_ERROR_ADD_LOCATION: {e}")
        return flask.jsonify({"error": f"Database error adding location: {str(e)}"}), 500

@app.route('/api/add_prop', methods=['POST'])
def add_prop():
    db = get_db()
    cursor = db.cursor()
    if not flask.request.is_json:
        return flask.jsonify({"error": "Request must be JSON"}), 400
    data = flask.request.get_json()
    required_fields = ['storageId', 'photos', 'timestamp', 'location', 'quantity']
    for field in required_fields:
        if field not in data or data.get(field) in [None, ""]:
             return flask.jsonify({"error": f"Missing or empty field: {field}"}), 400
    
    if not isinstance(data['photos'], list):
        return flask.jsonify({"error": "'photos' must be an array"}), 400

    photo_filenames = []
    if data['photos']:
        for photo_data_url in data['photos']:
            try:
                header, encoded = photo_data_url.split(',', 1)
                file_ext = header.split('/')[1].split(';')[0]
                if not file_ext: file_ext = 'jpg'
                photo_bytes = base64.b64decode(encoded)
                filename = f"prop_{uuid.uuid4().hex}.{file_ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                with open(filepath, 'wb') as f:
                    f.write(photo_bytes)
                photo_filenames.append(filename)
            except Exception as e:
                print(f"CRITICAL_ERROR_SAVING_PHOTO: {e}")

    files_json_string = json.dumps(photo_filenames)
    try:
        cursor.execute('''
            INSERT INTO props (Location, Storage_id, Description, Keywords, Category, Status, Quantity, file, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('location'), data.get('storageId'), data.get('description'),
            data.get('keywords'), data.get('category'), data.get('status', 'Available'),
            int(data.get('quantity', 1)),
            files_json_string, data.get('timestamp')
        ))
        db.commit()
        inserted_id = cursor.lastrowid
        print(f"SUCCESS_ADD_PROP: Prop (ID: {inserted_id}) inserted.")
        new_prop_details = { "id": inserted_id, **data, "file": photo_filenames }
        return flask.jsonify({"message": "Prop added successfully!", "prop": new_prop_details}), 201
    except sqlite3.Error as e:
        db.rollback()
        print(f"DATABASE_ERROR_ADD_PROP: {e}")
        return flask.jsonify({"error": f"Database error: {str(e)}"}), 500

@app.route('/api/props', methods=['GET'])
def get_props():
    db = get_db()
    cursor = db.cursor()
    search_query = flask.request.args.get('search', '').strip()
    try:
        base_select = "SELECT id, Location, Storage_id, Description, Keywords, Category, Status, Quantity, file, timestamp FROM props"
        if search_query:
            like_query = f"%{search_query}%"
            cursor.execute(f"""
                {base_select}
                WHERE Storage_id LIKE ? OR Description LIKE ? OR Keywords LIKE ? OR Category LIKE ? OR Location LIKE ?
                ORDER BY timestamp DESC
            """, (like_query, like_query, like_query, like_query, like_query))
        else:
            cursor.execute(f"{base_select} ORDER BY timestamp DESC")
        
        props_rows = cursor.fetchall()
        props_list = [dict(row) for row in props_rows]
        for prop_item in props_list:
            if prop_item.get('file'):
                try:
                    prop_item['file'] = json.loads(prop_item['file'])
                except json.JSONDecodeError:
                    prop_item['file'] = []
            else:
                prop_item['file'] = []
        return flask.jsonify(props_list), 200
    except sqlite3.Error as e:
        print(f"DATABASE_ERROR_GET_PROPS: {e}")
        return flask.jsonify({"error": f"Database error: {str(e)}"}), 500

@app.route('/api/prop/<int:prop_id>', methods=['GET'])
def get_prop_by_id(prop_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT * FROM props WHERE id = ?", (prop_id,))
        prop_row = cursor.fetchone()
        if prop_row:
            prop_item = dict(prop_row)
            if prop_item.get('file'):
                prop_item['file'] = json.loads(prop_item['file'])
            else:
                prop_item['file'] = []
            return flask.jsonify(prop_item), 200
        else:
            return flask.jsonify({"error": "Prop not found"}), 404
    except sqlite3.Error as e:
        print(f"DATABASE_ERROR_GET_PROP_ID ({prop_id}): {e}")
        return flask.jsonify({"error": f"Database error: {str(e)}"}), 500

@app.route('/api/prop/<int:prop_id>', methods=['PUT'])
def update_prop(prop_id):
    db = get_db()
    cursor = db.cursor()
    data = flask.request.get_json()
    try:
        cursor.execute("""
            UPDATE props SET Location = ?, Storage_id = ?, Description = ?, Keywords = ?, Category = ?, Status = ?, Quantity = ? WHERE id = ?
        """, (
            data.get('Location'), data.get('Storage_id'), data.get('Description'),
            data.get('Keywords'), data.get('Category'), data.get('Status'),
            data.get('Quantity'), prop_id
        ))
        db.commit()
        return flask.jsonify({"message": "Prop updated successfully!", "id": prop_id}), 200
    except sqlite3.Error as e:
        db.rollback()
        return flask.jsonify({"error": f"Database error updating prop: {str(e)}"}), 500

@app.route('/api/prop/<int:prop_id>', methods=['DELETE'])
def delete_prop(prop_id):
    db = get_db()
    cursor = db.cursor()
    try:
        # First, get image filenames to delete them
        cursor.execute("SELECT file FROM props WHERE id = ?", (prop_id,))
        row = cursor.fetchone()
        if row and row['file']:
            image_filenames = json.loads(row['file'])
            for filename in image_filenames:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
        
        # Now, delete the prop record
        cursor.execute("DELETE FROM props WHERE id = ?", (prop_id,))
        db.commit()
        return flask.jsonify({"message": "Prop deleted successfully!", "id": prop_id}), 200
    except sqlite3.Error as e:
        db.rollback()
        return flask.jsonify({"error": f"Database error deleting prop: {str(e)}"}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return flask.send_from_directory(app.config['UPLOAD_FOLDER'], filename)
