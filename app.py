import flask
from flask import render_template # <--- IMPORT THIS
from flask_cors import CORS
import sqlite3
import os
import json
import base64
import uuid
import time

# --- Flask App Setup ---
app = flask.Flask(__name__)
CORS(app)

# --- Absolute Paths Configuration ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_NAME = 'TCF_props.db'
DATABASE = os.path.join(BASE_DIR, DATABASE_NAME)
UPLOAD_FOLDER_NAME = 'uploads'
UPLOAD_FOLDER = os.path.join(BASE_DIR, UPLOAD_FOLDER_NAME)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    print(f"INFO: Created upload folder at absolute path: '{UPLOAD_FOLDER}'")
else:
    print(f"INFO: Upload folder already exists at absolute path: '{UPLOAD_FOLDER}'.")

print(f"INFO: Using database at absolute path: '{DATABASE}'")

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
    print(f"INFO_INIT_DB: Attempting to initialize database at '{DATABASE}'")
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        # Props table - Added Quantity INTEGER
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS props (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Location TEXT,
                Storage_id TEXT NOT NULL,
                Description TEXT,
                Keywords TEXT,
                Category TEXT,
                Status TEXT,
                Quantity INTEGER DEFAULT 1, -- <<<< New Column Added with default
                file TEXT,
                timestamp TEXT
            )
        ''')
        print("INFO_INIT_DB: 'props' table ensured (with Quantity column).")

        # Locations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        print("INFO_INIT_DB: 'locations' table ensured.")

        conn.commit()
        conn.close()
        print(f"INFO_INIT_DB: Database initialization complete for '{DATABASE}'.")
    except sqlite3.Error as e:
        print(f"ERROR_INIT_DB: Failed to initialize database at '{DATABASE}'. Error: {e}")

# --- NEW ROUTE TO SERVE THE MAIN HTML PAGE ---
@app.route('/')
def index():
    """Renders the main unified HTML page."""
    return render_template('index.html')

# --- API Endpoints (No changes needed below) ---

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
    required_fields = ['storageId', 'photos', 'timestamp', 'location', 'quantity'] # Added 'quantity'
    for field in required_fields:
        if field not in data:
             return flask.jsonify({"error": f"Missing field: {field}"}), 400
        if field == 'location' and (data.get(field) is None or (isinstance(data[field], str) and not data[field].strip())):
            return flask.jsonify({"error": f"Field '{field}' is required and cannot be empty."}), 400
        if field == 'quantity' and not isinstance(data.get(field), int):
             try:
                 int(data.get(field)) # Check if it can be converted to int
             except (ValueError, TypeError):
                 return flask.jsonify({"error": f"Field '{field}' must be a valid integer."}), 400


    if not data['storageId'].strip():
         return flask.jsonify({"error": "Storage_id cannot be empty"}), 400
    if not isinstance(data['photos'], list):
        return flask.jsonify({"error": "'photos' must be an array"}), 400

    photo_filenames = []
    if data['photos']:
        for i, photo_data_url in enumerate(data['photos']):
            filename, filepath = None, None
            try:
                if not isinstance(photo_data_url, str) or ',' not in photo_data_url:
                    raise ValueError("Photo data URL invalid.")
                header, encoded = photo_data_url.split(',', 1)
                if not header.startswith("data:image/"):
                    raise ValueError(f"Invalid photo header: {header[:30]}")
                file_ext = header.split('/')[1].split(';')[0]
                if not file_ext: file_ext = 'jpg'
                photo_bytes = base64.b64decode(encoded)
                filename = f"prop_{uuid.uuid4().hex}.{file_ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                with open(filepath, 'wb') as f: f.write(photo_bytes)
                time.sleep(0.1)
                if os.path.exists(filepath): photo_filenames.append(filename)
                else: print(f"CRITICAL_ERROR_FILE_NOT_FOUND_POST_SAVE: '{filepath}'")
            except Exception as e: print(f"CRITICAL_ERROR_SAVING_PHOTO: {type(e).__name__} - {e}")

    files_json_string = json.dumps(photo_filenames)
    try:
        cursor.execute('''
            INSERT INTO props (Location, Storage_id, Description, Keywords, Category, Status, Quantity, file, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('location'), data.get('storageId'), data.get('description'),
            data.get('keywords'), data.get('category'), data.get('status'),
            int(data.get('quantity', 1)), # Ensure quantity is an int, default to 1
            files_json_string, data.get('timestamp')
        ))
        db.commit()
        inserted_id = cursor.lastrowid
        print(f"SUCCESS_ADD_PROP: Prop (ID: {inserted_id}) inserted. Location: '{data.get('location')}', Quantity: {data.get('quantity')}")
        new_prop_details = { "id": inserted_id, **data, "file": photo_filenames }
        return flask.jsonify({"message": "Prop added successfully!", "prop": new_prop_details}), 201
    except sqlite3.Error as e:
        db.rollback(); print(f"DATABASE_ERROR_ADD_PROP: {e}")
        return flask.jsonify({"error": f"Database error: {str(e)}"}), 500

@app.route('/api/props', methods=['GET'])
def get_props():
    db = get_db()
    cursor = db.cursor()
    search_query = flask.request.args.get('search', '').strip()
    try:
        # Ensure Quantity is selected
        base_select = "SELECT id, Location, Storage_id, Description, Keywords, Category, Status, Quantity, file, timestamp FROM props"
        if search_query:
            print(f"INFO: Searching props with query: '{search_query}'")
            like_query = f"%{search_query}%"
            cursor.execute(f"""
                {base_select}
                WHERE Storage_id LIKE ? OR
                      Description LIKE ? OR
                      Keywords LIKE ? OR
                      Category LIKE ? OR
                      Location LIKE ?
                ORDER BY timestamp DESC
            """, (like_query, like_query, like_query, like_query, like_query))
        else:
            cursor.execute(f"{base_select} ORDER BY timestamp DESC")

        props_rows = cursor.fetchall()
        props_list = []
        for row in props_rows:
            prop_item = dict(row)
            try:
                if prop_item['file']: prop_item['file'] = json.loads(prop_item['file'])
                else: prop_item['file'] = []
            except json.JSONDecodeError: prop_item['file'] = []
            props_list.append(prop_item)
        return flask.jsonify(props_list), 200
    except sqlite3.Error as e:
        print(f"DATABASE_ERROR_GET_PROPS: {e}")
        return flask.jsonify({"error": f"Database error: {str(e)}"}), 500

@app.route('/api/prop/<int:prop_id>', methods=['GET'])
def get_prop_by_id(prop_id):
    db = get_db()
    cursor = db.cursor()
    try:
        # Ensure Quantity is selected
        cursor.execute("SELECT id, Location, Storage_id, Description, Keywords, Category, Status, Quantity, file, timestamp FROM props WHERE id = ?", (prop_id,))
        prop_row = cursor.fetchone()
        if prop_row:
            prop_item = dict(prop_row)
            try:
                if prop_item['file']: prop_item['file'] = json.loads(prop_item['file'])
                else: prop_item['file'] = []
            except json.JSONDecodeError: prop_item['file'] = []
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
    if not flask.request.is_json:
        return flask.jsonify({"error": "Request must be JSON"}), 400

    data = flask.request.get_json()
    print(f"INFO: Updating prop ID {prop_id} with data: {data}")

    location = data.get('Location')
    storage_id = data.get('Storage_id')
    description = data.get('Description')
    keywords = data.get('Keywords')
    category = data.get('Category')
    status = data.get('Status')
    quantity = data.get('Quantity') # Get Quantity

    if storage_id is not None and not storage_id.strip():
         return flask.jsonify({"error": "Storage_id cannot be empty"}), 400
    if location is not None and not location.strip():
         return flask.jsonify({"error": "Location cannot be empty"}), 400
    if quantity is not None:
        try:
            quantity = int(quantity)
            if quantity < 0: # Or < 1 depending on your rules
                 return flask.jsonify({"error": "Quantity cannot be negative"}), 400
        except (ValueError, TypeError):
            return flask.jsonify({"error": "Quantity must be a valid integer"}), 400
    else: # If quantity is not provided in update, keep existing or set to default
        # Fetch existing quantity to keep it if not provided in update
        cursor.execute("SELECT Quantity FROM props WHERE id = ?", (prop_id,))
        current_prop = cursor.fetchone()
        if current_prop:
            quantity = current_prop['Quantity'] if quantity is None else quantity
        else: # Prop not found, will be caught later
            quantity = 1 # Default if somehow prop not found here


    try:
        cursor.execute("SELECT id FROM props WHERE id = ?", (prop_id,))
        if not cursor.fetchone():
            return flask.jsonify({"error": "Prop not found"}), 404

        cursor.execute("""
            UPDATE props
            SET Location = ?,
                Storage_id = ?,
                Description = ?,
                Keywords = ?,
                Category = ?,
                Status = ?,
                Quantity = ?
            WHERE id = ?
        """, (location, storage_id, description, keywords, category, status, quantity, prop_id))
        db.commit()
        if cursor.rowcount == 0:
             return flask.jsonify({"error": "Prop not found or no changes made"}), 404
        print(f"SUCCESS_UPDATE_PROP: Prop ID {prop_id} updated. New Quantity: {quantity}")
        return flask.jsonify({"message": "Prop updated successfully!", "id": prop_id}), 200
    except sqlite3.Error as e:
        db.rollback()
        print(f"DATABASE_ERROR_UPDATE_PROP ({prop_id}): {e}")
        return flask.jsonify({"error": f"Database error updating prop: {str(e)}"}), 500

@app.route('/api/prop/<int:prop_id>', methods=['DELETE'])
def delete_prop(prop_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT file FROM props WHERE id = ?", (prop_id,))
        row = cursor.fetchone()
        if row and row['file']:
            try:
                image_filenames = json.loads(row['file'])
                for filename in image_filenames:
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        print(f"INFO_DELETE_PROP: Deleted image file '{filepath}' for prop ID {prop_id}.")
            except Exception as e:
                print(f"ERROR_DELETE_PROP: Could not delete image files for prop ID {prop_id}. Error: {e}")

        cursor.execute("DELETE FROM props WHERE id = ?", (prop_id,))
        db.commit()
        if cursor.rowcount == 0:
            return flask.jsonify({"error": "Prop not found"}), 404
        print(f"SUCCESS_DELETE_PROP: Prop ID {prop_id} deleted.")
        return flask.jsonify({"message": "Prop deleted successfully!", "id": prop_id}), 200
    except sqlite3.Error as e:
        db.rollback()
        print(f"DATABASE_ERROR_DELETE_PROP ({prop_id}): {e}")
        return flask.jsonify({"error": f"Database error deleting prop: {str(e)}"}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    serving_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(serving_path):
        print(f"ERROR_UPLOAD_ROUTE_SERVING: File not found at ABSOLUTE path '{serving_path}'")
    return flask.send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)

if __name__ == '__main__':
    try:
        with app.app_context():
             init_db()
    except Exception as e:
        print(f"CRITICAL_ERROR_ON_STARTUP: Failed during init_db. Error: {e}")
    app.run(host='0.0.0.0', port=5000, debug=True)