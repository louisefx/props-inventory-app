import flask
from flask import (
    render_template, request, session, redirect, url_for, g, flash
)
from flask_cors import CORS
import sqlite3
import os
import json
import base64
import uuid
import time
import click
from werkzeug.security import generate_password_hash, check_password_hash
import functools

# --- Flask App Setup ---
app = flask.Flask(__name__)
# This SECRET_KEY is essential for session security.
# In a real app, this should be a long, random string stored securely.
app.config['SECRET_KEY'] = 'dev' # Use 'dev' for now, but change for production
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
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database using schema.sql."""
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
        print(f"INFO: Created upload folder at: '{app.config['UPLOAD_FOLDER']}'")
    try:
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
        print(f"INFO_INIT_DB: Database initialized from schema.sql in '{DATABASE}'.")
    except Exception as e:
        print(f"ERROR_INIT_DB: An error occurred during database initialization: {e}")

# --- CLI Commands ---
@app.cli.command('init-db')
def init_db_command():
    """Clears existing data and creates new tables."""
    init_db()
    click.echo('Initialized the database.')

@app.cli.command('add-user')
@click.argument('username')
@click.argument('password')
def add_user_command(username, password):
    """Creates a new user."""
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        db.commit()
        click.echo(f"User {username} created successfully.")
    except db.IntegrityError:
        click.echo(f"Error: User {username} already exists.")
    finally:
        close_connection(None)

# --- Authentication Logic and Routes ---

@app.before_request
def load_logged_in_user():
    """If a user id is stored in the session, load the user object from the database."""
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

def login_required(view):
    """View decorator that redirects anonymous users to the login page."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            # For API endpoints, return a 401 Unauthorized error
            if request.path.startswith('/api/'):
                return flask.jsonify({"error": "Authentication required"}), 401
            # For web pages, redirect to the login page
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        error = None
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user['password'], password):
            error = 'Incorrect password.'

        if error is None:
            # store the user id in a new session and return to the main app
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('index'))
        
        flash(error, 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Clear the current session, including the user id."""
    session.clear()
    return redirect(url_for('login'))

# --- PROTECTED Application Routes ---

@app.route('/')
@login_required
def index():
    """Renders the main unified HTML page."""
    return render_template('index.html')

@app.route('/api/locations', methods=['GET'])
@login_required
def get_locations_api():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name FROM locations ORDER BY name ASC")
    locations_list = [dict(row) for row in cursor.fetchall()]
    return flask.jsonify(locations_list), 200

@app.route('/api/locations', methods=['POST'])
@login_required
def add_location_api():
    db = get_db()
    data = request.get_json()
    location_name = data['name'].strip()
    try:
        cursor = db.cursor()
        cursor.execute("INSERT INTO locations (name) VALUES (?)", (location_name,))
        db.commit()
        return flask.jsonify({"message": "Location added successfully!", "id": cursor.lastrowid, "name": location_name}), 201
    except db.IntegrityError:
        return flask.jsonify({"error": f"Location '{location_name}' already exists."}), 409

# (Apply @login_required to all other API routes as well)

@app.route('/api/add_prop', methods=['POST'])
@login_required
def add_prop():
    # ... your existing add_prop code ...
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
@login_required
def get_props():
    # ... your existing get_props code ...
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


@app.route('/api/prop/<int:prop_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def handle_prop(prop_id):
    if request.method == 'GET':
        # ... your get_prop_by_id logic ...
        db = get_db()
        cursor = db.cursor()
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
            
    elif request.method == 'PUT':
        # ... your update_prop logic ...
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

    elif request.method == 'DELETE':
        # ... your delete_prop logic ...
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute("SELECT file FROM props WHERE id = ?", (prop_id,))
            row = cursor.fetchone()
            if row and row['file']:
                image_filenames = json.loads(row['file'])
                for filename in image_filenames:
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    if os.path.exists(filepath):
                        os.remove(filepath)
            
            cursor.execute("DELETE FROM props WHERE id = ?", (prop_id,))
            db.commit()
            return flask.jsonify({"message": "Prop deleted successfully!", "id": prop_id}), 200
        except sqlite3.Error as e:
            db.rollback()
            return flask.jsonify({"error": f"Database error deleting prop: {str(e)}"}), 500

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return flask.send_from_directory(app.config['UPLOAD_FOLDER'], filename)