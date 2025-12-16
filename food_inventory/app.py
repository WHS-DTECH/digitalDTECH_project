from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, current_user
from google_auth_oauthlib.flow import Flow
import sqlite3
import json
import csv
import io
import re
import os
import datetime
from dotenv import load_dotenv
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None
from recipe_parser import parse_recipes_from_text, format_recipe, parse_ingredient_line
from auth import User, get_staff_code_from_email, require_login, require_role, public_with_auth


# Load environment variables
load_dotenv()

# Allow OAuth over HTTP for local development (DO NOT use in production)
# Only enable in development, not production
if os.getenv('FLASK_ENV') == 'development':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
# Database path
basedir = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(basedir, 'recipes.db')

app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.anonymous_user = lambda: type('AnonymousUser', (), {'is_authenticated': False})()

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/auth/callback')

SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]


@login_manager.user_loader
def load_user(user_id):
    """Load user from session."""
    if 'user' in session and session['user'].get('google_id') == user_id:
        user_data = session['user']
        return User(
            user_data['google_id'],
            user_data['email'],
            user_data['name'],
            user_data.get('staff_code')
        )
    return None

# Initialize database
def init_db():
    # Create DB and include `equipment` column to avoid ALTER on every upload
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS recipes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT NOT NULL,
                      ingredients TEXT,
                      instructions TEXT,
                      serving_size INTEGER,
                      equipment TEXT)''')
        # Ensure new columns exist
        c.execute("PRAGMA table_info(recipes)")
        cols = [r[1] for r in c.fetchall()]
        if 'photo' not in cols:
            try:
                c.execute('ALTER TABLE recipes ADD COLUMN photo TEXT')
            except Exception:
                pass
        if 'dietary_tags' not in cols:
            try:
                c.execute('ALTER TABLE recipes ADD COLUMN dietary_tags TEXT')
            except Exception:
                pass
        if 'cuisine' not in cols:
            try:
                c.execute('ALTER TABLE recipes ADD COLUMN cuisine TEXT')
            except Exception:
                pass
        if 'difficulty' not in cols:
            try:
                c.execute('ALTER TABLE recipes ADD COLUMN difficulty TEXT')
            except Exception:
                pass

    # Ensure teachers and classes tables exist (setup_database.py normally creates these)
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            last_name TEXT NOT NULL,
            first_name TEXT NOT NULL,
            title TEXT,
            email TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS classes (
            ClassCode TEXT NOT NULL,
            LineNo INTEGER,
            Misc1 TEXT,
            RoomNo TEXT,
            CourseName TEXT,
            Misc2 TEXT,
            Year INTEGER,
            Dept TEXT,
            StaffCode TEXT,
            ClassSize INTEGER,
            TotalSize INTEGER,
            TimetableYear INTEGER,
            Misc3 TEXT,
            PRIMARY KEY (ClassCode, LineNo)
        )''')
        # Bookings table to record class recipe bookings
        c.execute('''CREATE TABLE IF NOT EXISTS class_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_code TEXT,
            class_code TEXT,
            date_required TEXT,
            period INTEGER,
            recipe_id INTEGER,
            desired_servings INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # User roles table for assigning additional roles to users
        c.execute('''CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(email, role)
        )''')

@app.route('/')
def index():
    """Main page shows recipe book for everyone."""
    return redirect(url_for('recbk'))


# ============== Authentication Routes ==============

@app.route('/login')
def login():
    """Render login page."""
    if current_user.is_authenticated:
        return redirect(url_for('class_ingredients'))
    return render_template('login.html')


@app.route('/auth/google')
def auth_google():
    """Initiate Google OAuth flow."""
    if GOOGLE_CLIENT_ID is None or GOOGLE_CLIENT_SECRET is None:
        flash('Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.')
        return redirect(url_for('login'))
    
    # Use Flow.from_client_config for direct configuration instead of file
    client_config = {
        'web': {
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://accounts.google.com/o/oauth2/token',
            'redirect_uris': [GOOGLE_REDIRECT_URI]
        }
    }
    
    # Use the full callback URL to avoid mismatches
    redirect_uri = GOOGLE_REDIRECT_URI  # Use the configured URI from .env
    
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    
    # Generate the authorization URL
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='select_account'
    )
    
    session['oauth_state'] = state
    session['redirect_uri'] = redirect_uri
    return redirect(authorization_url)


@app.route('/auth/callback')
def auth_callback():
    """Handle Google OAuth callback."""
    # Verify state for security
    state = session.get('oauth_state')
    redirect_uri = session.get('redirect_uri', GOOGLE_REDIRECT_URI)  # Use configured URI
    
    if not state:
        flash('OAuth state mismatch. Please try logging in again.')
        return redirect(url_for('login'))
    
    try:
        # Use the stored client config
        client_config = {
            'web': {
                'client_id': GOOGLE_CLIENT_ID,
                'client_secret': GOOGLE_CLIENT_SECRET,
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://accounts.google.com/o/oauth2/token',
                'redirect_uris': [redirect_uri]
            }
        }
        
        flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri, state=state)
        
        # Get the authorization code from the callback
        authorization_response = request.url.replace('http://', 'http://')  # Ensure consistent scheme
        flow.fetch_token(authorization_response=authorization_response)
        
        # Get user info
        credentials = flow.credentials
        user_info_url = 'https://www.googleapis.com/oauth2/v1/userinfo'
        import requests as req_lib
        headers = {'Authorization': f'Bearer {credentials.token}'}
        response = req_lib.get(user_info_url, headers=headers)
        user_info = response.json()
        
        # Extract user data
        google_id = user_info.get('id')
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0])
        
        # Get staff code from email lookup
        staff_code = get_staff_code_from_email(email)
        
        # Create user and store in session
        user = User(google_id, email, name, staff_code)
        session['user'] = {
            'google_id': google_id,
            'email': email,
            'name': name,
            'staff_code': staff_code,
            'role': user.role
        }
        
        login_user(user, remember=True)
        flash(f'Welcome, {name}!', 'success')
        
        return redirect(url_for('recbk'))
    
    except Exception as e:
        flash(f'Authentication error: {str(e)}')
        return redirect(url_for('login'))


@app.route('/logout')
def logout():
    """Log out the current user."""
    logout_user()
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('recbk'))


# ============== End Authentication Routes ==============


@app.route('/admin', methods=['GET', 'POST'])
@require_role('VP')
def admin():
    # Get recipe suggestions for display
    suggestions = []
    try:
        with sqlite3.connect(DATABASE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute('''SELECT id, recipe_name, recipe_url, reason, suggested_by_name, 
                        suggested_by_email, created_at, status 
                        FROM recipe_suggestions 
                        ORDER BY created_at DESC''')
            suggestions = [dict(row) for row in c.fetchall()]
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        suggestions = []
    
    preview_data = None
    if request.method == 'POST':
        # staff CSV upload
        uploaded = request.files.get('staff_csv')
        if not uploaded:
            flash('No file uploaded')
            return redirect(url_for('admin'))

        # Read and normalize file content
        file_content = uploaded.stream.read().decode('utf-8', errors='ignore')
        # Normalize line endings
        file_content = file_content.replace('\r\n', '\n').replace('\r', '\n')
        stream = io.StringIO(file_content)
        reader = csv.DictReader(stream)
        rows = []
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            try:
                for row in reader:
                    code = row.get('Code') or row.get('code') or row.get('StaffCode') or row.get('staffcode')
                    last = row.get('Last Name') or row.get('last_name') or row.get('Last') or row.get('last')
                    first = row.get('First Name') or row.get('first_name') or row.get('First') or row.get('first')
                    title = row.get('Title') or row.get('title')
                    email = row.get('Email (School)') or row.get('email') or row.get('Email')
                    if code and last and first:
                        c.execute('INSERT OR IGNORE INTO teachers (code, last_name, first_name, title, email) VALUES (?, ?, ?, ?, ?)',
                                  (code, last, first, title, email))
                    rows.append(row)
            except Exception as e:
                flash(f'Error processing CSV: {str(e)}')
                return redirect(url_for('admin'))
        preview_data = rows
        flash(f'Staff CSV processed: {len(rows)} rows')

    return render_template('admin.html', preview_data=preview_data, suggestions=suggestions)


@app.route('/uploadclass', methods=['POST'])
@require_role('VP')
def uploadclass():
    uploaded = request.files.get('csvfile')
    if not uploaded:
        flash('No class file uploaded')
        return redirect(url_for('admin'))

    # Normalize line endings
    file_content = uploaded.stream.read().decode('utf-8', errors='ignore')
    file_content = file_content.replace('\r\n', '\n').replace('\r', '\n')
    stream = io.StringIO(file_content)
    reader = csv.DictReader(stream)
    rows = []
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        for row in reader:
            # Map expected fields, allow flexible header names
            classcode = row.get('ClassCode') or row.get('classcode') or row.get('Class') or row.get('class')
            lineno = row.get('LineNo') or row.get('lineno') or row.get('Line')
            try:
                ln = int(lineno) if lineno not in (None, '') else None
            except ValueError:
                ln = None
            # Insert or replace to update existing
            c.execute('INSERT OR REPLACE INTO classes (ClassCode, LineNo, Misc1, RoomNo, CourseName, Misc2, Year, Dept, StaffCode, ClassSize, TotalSize, TimetableYear, Misc3) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (
                          classcode,
                          ln,
                          row.get('Misc1'),
                          row.get('RoomNo'),
                          row.get('CourseName'),
                          row.get('Misc2'),
                          row.get('Year'),
                          row.get('Dept'),
                          row.get('StaffCode'),
                          row.get('ClassSize'),
                          row.get('TotalSize'),
                          row.get('TimetableYear'),
                          row.get('Misc3'),
                      ))
            rows.append(row)

    flash('Classes CSV processed')
    
    return render_template('admin.html', preview_data=rows, suggestions=suggestions)


@app.route('/admin/permissions', methods=['GET', 'POST'])
@require_role('VP')
def admin_permissions():
    """Manage role-based permissions."""
    if request.method == 'POST':
        role = request.form.get('role')
        route = request.form.get('route')
        action = request.form.get('action')  # 'add' or 'remove'
        
        if role and route and action:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                if action == 'add':
                    c.execute('INSERT OR IGNORE INTO role_permissions (role, route) VALUES (?, ?)', (role, route))
                    flash(f'Added {route} access for {role}', 'success')
                elif action == 'remove':
                    c.execute('DELETE FROM role_permissions WHERE role = ? AND route = ?', (role, route))
                    flash(f'Removed {route} access for {role}', 'success')
        
        return redirect(url_for('admin_permissions'))
    
    # Get current permissions
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT role, route FROM role_permissions ORDER BY role, route')
        permissions = {}
        for row in c.fetchall():
            role = row['role']
            route = row['route']
            if role not in permissions:
                permissions[role] = []
            permissions[role].append(route)
    
    # Available routes
    routes = ['recipes', 'recbk', 'class_ingredients', 'booking', 'shoplist', 'admin']
    roles = ['VP', 'DK', 'MU', 'public']
    
    return render_template('admin_permissions.html', permissions=permissions, routes=routes, roles=roles)


@app.route('/admin/user_roles', methods=['GET', 'POST'])
@require_role('VP')
def admin_user_roles():
    """Manage additional user roles."""
    if request.method == 'POST':
        email = request.form.get('email')
        role = request.form.get('role')
        action = request.form.get('action')  # 'add' or 'remove'
        
        if email and role and action:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                if action == 'add':
                    try:
                        c.execute('INSERT INTO user_roles (email, role) VALUES (?, ?)', (email, role))
                        flash(f'Added role {role} to {email}', 'success')
                    except sqlite3.IntegrityError:
                        flash(f'{email} already has role {role}', 'warning')
                elif action == 'remove':
                    c.execute('DELETE FROM user_roles WHERE email = ? AND role = ?', (email, role))
                    flash(f'Removed role {role} from {email}', 'success')
        
        return redirect(url_for('admin_user_roles'))
    
    # Get all users with additional roles
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT email, GROUP_CONCAT(role, ', ') as roles
            FROM user_roles
            GROUP BY email
            ORDER BY email
        ''')
        users_with_roles = [dict(row) for row in c.fetchall()]
        
        # Get all teachers for the dropdown
        c.execute('SELECT email, code, first_name, last_name FROM teachers WHERE email IS NOT NULL ORDER BY last_name, first_name')
        teachers = [dict(row) for row in c.fetchall()]
    
    roles = ['VP', 'DK', 'MU', 'public']
    
    return render_template('admin_user_roles.html', users_with_roles=users_with_roles, teachers=teachers, roles=roles)


@app.route('/admin/clean_recipes', methods=['POST'])

@require_role('VP')
def clean_recipes_route():
    """Clean recipe database - remove junk and duplicates."""
    try:
        from clean_recipes import remove_junk_recipes, remove_duplicate_recipes, fix_recipe_names
        
        with sqlite3.connect(DATABASE) as conn:
            # Run all cleaning operations
            junk_deleted = remove_junk_recipes(conn)
            dupes_deleted = remove_duplicate_recipes(conn)
            names_fixed = fix_recipe_names(conn)
            
            # Get final count
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM recipes')
            total = c.fetchone()[0]
            
            message = f'Database cleaned! Removed {len(junk_deleted)} junk entries, {len(dupes_deleted)} duplicates, and fixed {len(names_fixed)} recipe names. Total recipes: {total}'
            flash(message, 'success')
    except Exception as e:
        flash(f'Error cleaning database: {str(e)}', 'error')
    
    return redirect(url_for('admin'))


@app.route('/staff')
@require_role('VP')
def staff():
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT code, last_name, first_name, title, email FROM teachers ORDER BY last_name, first_name')
        rows = [dict(r) for r in c.fetchall()]
    return render_template('staff.html', rows=rows)


@app.route('/classes')
@require_role('VP')
def classes_page():
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM classes ORDER BY ClassCode, LineNo')
        rows = [dict(r) for r in c.fetchall()]
    return render_template('classes.html', rows=rows)


@app.route('/class_ingredients', methods=['GET', 'POST'])
@require_role('VP', 'DK')
def class_ingredients():
    # Provide staff codes, class codes, and recipes for selection on the page
    # Can be called via GET (blank form) or POST (from booking calendar with pre-populated data)
    
    # Extract booking data from POST request if present
    staff_code = request.form.get('staff_code') if request.method == 'POST' else None
    class_code = request.form.get('class_code') if request.method == 'POST' else None
    date_required = request.form.get('date_required') if request.method == 'POST' else None
    period = request.form.get('period') if request.method == 'POST' else None
    
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Get most used staff (top 5 by booking count)
        c.execute('''SELECT staff_code, COUNT(*) as booking_count FROM class_bookings 
                    GROUP BY staff_code ORDER BY booking_count DESC LIMIT 5''')
        most_used_staff_codes = [r['staff_code'] for r in c.fetchall()]
        
        # Get all staff
        c.execute('SELECT code, last_name, first_name, title FROM teachers ORDER BY last_name, first_name')
        all_staff = [dict(r) for r in c.fetchall()]
        
        # Sort staff: most used first, then rest alphabetically
        most_used_staff = [s for s in all_staff if s['code'] in most_used_staff_codes]
        other_staff = [s for s in all_staff if s['code'] not in most_used_staff_codes]
        most_used_staff.sort(key=lambda x: most_used_staff_codes.index(x['code']))
        staff = most_used_staff + other_staff
        
        # If no pre-selected staff from booking, try to match current user's name to a staff member
        if not staff_code and current_user.is_authenticated:
            user_name_parts = current_user.name.split()
            if len(user_name_parts) >= 2:
                # Try to match first name and last name
                user_first = user_name_parts[0]
                user_last = user_name_parts[-1]
                for s in staff:
                    if (s['first_name'].lower() == user_first.lower() and 
                        s['last_name'].lower() == user_last.lower()):
                        staff_code = s['code']
                        break
        
        # Get most used classes (top 5 by booking count)
        c.execute('''SELECT class_code, COUNT(*) as booking_count FROM class_bookings 
                    GROUP BY class_code ORDER BY booking_count DESC LIMIT 5''')
        most_used_class_codes = [r['class_code'] for r in c.fetchall()]
        
        # Get all classes
        c.execute('SELECT DISTINCT ClassCode FROM classes ORDER BY ClassCode')
        all_classes = [r['ClassCode'] for r in c.fetchall() if r['ClassCode']]
        
        # Sort classes: most used first, then rest alphabetically
        most_used_classes = [c for c in all_classes if c in most_used_class_codes]
        other_classes = [c for c in all_classes if c not in most_used_class_codes]
        most_used_classes.sort(key=lambda x: most_used_class_codes.index(x))
        classes = most_used_classes + other_classes
        
        # Get recipes
        c.execute('SELECT id, name, ingredients, serving_size FROM recipes ORDER BY name COLLATE NOCASE')
        rows = c.fetchall()
        
        # If called from booking, get the booking's recipe and servings
        booking_recipe_id = None
        booking_servings = None
        if request.method == 'POST' and staff_code and class_code and date_required and period:
            c.execute('''SELECT recipe_id, desired_servings FROM class_bookings 
                        WHERE staff_code = ? AND class_code = ? AND date_required = ? AND period = ?''',
                     (staff_code, class_code, date_required, period))
            booking = c.fetchone()
            if booking:
                booking_recipe_id = booking['recipe_id']
                booking_servings = booking['desired_servings']

    recipes = []
    for r in rows:
        try:
            ings = json.loads(r['ingredients'] or '[]')
        except Exception:
            ings = []
        recipes.append({'id': r['id'], 'name': r['name'], 'ingredients': ings, 'serving_size': r['serving_size']})

    # Get existing bookings for display (ordered by date descending, most recent first)
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT cb.id, cb.staff_code, cb.class_code, cb.date_required, cb.period, 
                   cb.recipe_id, cb.desired_servings, r.name as recipe_name,
                   t.first_name, t.last_name
            FROM class_bookings cb
            LEFT JOIN recipes r ON cb.recipe_id = r.id
            LEFT JOIN teachers t ON cb.staff_code = t.code
            ORDER BY cb.date_required DESC, cb.period ASC
        ''')
        bookings = [dict(row) for row in c.fetchall()]

    return render_template('class_ingred.html', staff=staff, classes=classes, recipes=recipes,
                          bookings=bookings,
                          most_used_staff_count=len(most_used_staff), most_used_classes_count=len(most_used_classes),
                          pre_staff_code=staff_code, pre_class_code=class_code, 
                          pre_date_required=date_required, pre_period=period,
                          pre_recipe_id=booking_recipe_id, pre_servings=booking_servings)


@app.route('/class_ingredients/download', methods=['POST'])
@require_role('VP', 'DK')
def class_ingredients_download():
    # Expects JSON: {recipe_id, desired_servings}
    data = request.get_json() or {}
    recipe_id = data.get('recipe_id')
    desired = int(data.get('desired_servings') or 24)
    if not recipe_id:
        return jsonify({'error':'recipe_id required'}), 400

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT id, name, ingredients, serving_size FROM recipes WHERE id = ?', (recipe_id,))
        row = c.fetchone()
        if not row:
            return jsonify({'error':'recipe not found'}), 404
        try:
            ings = json.loads(row['ingredients'] or '[]')
        except Exception:
            ings = []

    # Build CSV
    import io, csv
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['ingredient','quantity','unit','notes'])
    orig_serv = int(row['serving_size']) if row['serving_size'] else 1
    for it in ings:
        name = ''
        qty = ''
        unit = ''
        if isinstance(it, dict):
            name = it.get('ingredient') or ''
            qty = it.get('quantity') or ''
            unit = it.get('unit') or ''
            # calculate scaled
            try:
                qn = float(str(qty))
                per_single = qn / orig_serv
                scaled = per_single * desired
                qty = round(scaled,2)
            except Exception:
                qty = ''
        else:
            name = str(it)
        writer.writerow([name, qty, unit, ''])

    csv_data = buf.getvalue()
    return (csv_data, 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': f'attachment; filename="shopping_{recipe_id}.csv"'
    })


@app.route('/class_ingredients/save', methods=['POST'])
@require_role('VP', 'DK')
def class_ingredients_save():
    # Save a booking to `class_bookings` (INSERT or UPDATE)
    data = request.get_json() or {}
    booking_id = data.get('booking_id')  # If provided, update existing booking
    staff_code = data.get('staff')
    class_code = data.get('classcode')
    date_required = data.get('date')
    period = data.get('period')
    recipe_id = data.get('recipe_id')
    desired = int(data.get('desired_servings') or 24)
    
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        if booking_id:
            # Update existing booking
            c.execute('''UPDATE class_bookings 
                        SET staff_code=?, class_code=?, date_required=?, period=?, recipe_id=?, desired_servings=?
                        WHERE id=?''',
                     (staff_code, class_code, date_required, period, recipe_id, desired, booking_id))
            conn.commit()
        else:
            # Insert new booking
            c.execute('INSERT INTO class_bookings (staff_code, class_code, date_required, period, recipe_id, desired_servings) VALUES (?, ?, ?, ?, ?, ?)',
                      (staff_code, class_code, date_required, period, recipe_id, desired))
            conn.commit()
            booking_id = c.lastrowid
    return jsonify({'success': True, 'booking_id': booking_id})

@app.route('/class_ingredients/delete/<int:booking_id>', methods=['POST'])
@require_role('VP', 'DK')
def class_ingredients_delete(booking_id):
    # Delete a booking
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('DELETE FROM class_bookings WHERE id = ?', (booking_id,))
        conn.commit()
    return jsonify({'success': True})

@app.route('/upload', methods=['GET', 'POST'])
@require_role('VP')
def upload():
    # GET request - show the upload form
    if request.method == 'GET':
        return render_template('upload_recipe.html')
    
    # POST request - handle form submission
    # Check if PDF file is being uploaded
    if 'pdfFile' in request.files:
        if not PyPDF2:
            flash('PyPDF2 not installed - cannot parse PDF files', 'error')
            return redirect(url_for('recipes_page'))
        
        pdf_file = request.files.get('pdfFile')
        if not pdf_file or pdf_file.filename == '':
            flash('No PDF file selected', 'error')
            return redirect(url_for('recipes_page'))
        
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # Extract ALL text from entire PDF first (recipes span multiple pages)
            print(f"DEBUG: PDF has {len(pdf_reader.pages)} pages")  # Debug
            full_text = ""
            for page in pdf_reader.pages:
                full_text += page.extract_text() + "\n"
            
            # Parse the complete text for recipes
            recipes_found = parse_recipes_from_text(full_text)
            print(f"DEBUG: Total recipes found: {len(recipes_found)}")  # Debug
            if not recipes_found:
                flash(f'No recipes found with Ingredients, Equipment, and Method sections in the PDF ({len(pdf_reader.pages)} pages scanned). Try using manual recipe upload instead.', 'warning')
                return redirect(url_for('recipes_page'))
            
            # Save recipes to database (skip duplicates)
            saved_count = 0
            skipped_count = 0
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                for recipe in recipes_found:
                    try:
                        c.execute(
                            "INSERT INTO recipes (name, ingredients, instructions, serving_size, equipment) VALUES (?, ?, ?, ?, ?)",
                            (
                                recipe['name'],
                                json.dumps(recipe.get('ingredients', [])),
                                recipe.get('method', ''),
                                recipe.get('serving_size'),
                                json.dumps(recipe.get('equipment', []))
                            ),
                        )
                        saved_count += 1
                    except sqlite3.IntegrityError:
                        # Recipe name already exists, skip it
                        skipped_count += 1

            # Run cleaners after insert (temporarily disabled for debugging)
            # dup_deleted = remove_duplicate_recipes()
            # nonfood_deleted = remove_nonfood_recipes()
            dup_deleted = []
            nonfood_deleted = []

            message = f'Saved {saved_count} new recipe(s).'
            if skipped_count > 0:
                message += f' Skipped {skipped_count} duplicate(s).'
            # if len(dup_deleted) > 0 or len(nonfood_deleted) > 0:
            #     message += f' Cleaned {len(dup_deleted)} duplicates and {len(nonfood_deleted)} non-food entries.'
            
            flash(message, 'success')
            return redirect(url_for('recipes_page'))
        except Exception as e:
            flash(f'Error uploading PDF: {str(e)}', 'error')
            return redirect(url_for('recipes_page'))
    
    # Handle form data upload
    name = request.form.get('name', '').strip()
    instructions = request.form.get('instructions', '').strip()
    
    if not name or not instructions:
        flash('Recipe name and instructions required', 'error')
        return redirect(url_for('recipes_page'))

    # Validate serving_size
    serving_size_raw = request.form.get('serving_size', '').strip()
    try:
        serving_size = int(serving_size_raw) if serving_size_raw != '' else None
    except ValueError:
        flash('Invalid serving size', 'error')
        return redirect(url_for('recipes_page'))

    equipment_text = request.form.get('equipment', '')

    # Collect structured ingredients
    quantities = request.form.getlist('quantity[]')
    units = request.form.getlist('unit[]')
    ingredients_names = request.form.getlist('ingredient[]')

    # Check if ingredients were parsed
    if not quantities or len(quantities) == 0:
        flash('No ingredients found. Please click "Format Ingredients" button before saving.', 'error')
        return redirect(url_for('admin'))

    ingredients = []
    for q, u, ing in zip(quantities, units, ingredients_names):
        ingredients.append({"quantity": q, "unit": u, "ingredient": ing})

    # Convert equipment text into a list
    equipment_list = [item.strip() for item in equipment_text.split('\n') if item.strip()]

    try:
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            
            # Check if recipe name already exists
            c.execute("SELECT id, name FROM recipes WHERE name = ?", (name,))
            existing = c.fetchone()
            if existing:
                flash(f'Recipe "{name}" already exists in the database. Please use a different name or edit the existing recipe.', 'warning')
                return redirect(url_for('admin'))
            
            c.execute(
                "INSERT INTO recipes (name, ingredients, instructions, serving_size, equipment) VALUES (?, ?, ?, ?, ?)",
                (name, json.dumps(ingredients), instructions, serving_size, json.dumps(equipment_list)),
            )
            conn.commit()
            
        # Run cleaners after form insert
        dup_deleted = remove_duplicate_recipes()
        nonfood_deleted = remove_nonfood_recipes()

        flash(f'Recipe "{name}" saved successfully! Cleaned {len(dup_deleted)} duplicates and {len(nonfood_deleted)} non-food entries.', 'success')
    except sqlite3.IntegrityError as e:
        flash(f'Recipe "{name}" already exists in the database. Please use a different name.', 'error')
        return redirect(url_for('admin'))
    except Exception as e:
        flash(f'Error saving recipe: {str(e)}', 'error')
        return redirect(url_for('admin'))
        
    return redirect(url_for('recipes_page'))

@app.route('/shoplist')
@require_role('VP', 'DK', 'MU')
def shoplist():
    from datetime import datetime, timedelta
    
    # Get week offset from query parameter (0 = current week, -1 = last week, 1 = next week, etc.)
    week_offset = request.args.get('week', type=int)
    
    # If no week specified, default intelligently based on day of week
    if week_offset is None:
        today = datetime.now()
        # If it's Saturday (5) or Sunday (6), default to next week instead of current
        if today.weekday() >= 5:
            week_offset = 1
        else:
            week_offset = 0
    
    # Calculate the target week (Monday to Friday)
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())  # Get Monday of current week
    monday = monday + timedelta(weeks=week_offset)  # Adjust by week offset
    
    dates = []
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    
    for i in range(5):
        date_obj = monday + timedelta(days=i)
        date_str = date_obj.strftime('%Y-%m-%d')
        # Format for NZ date display: ddmmyy
        nz_format = date_obj.strftime('%d/%m/%y')
        dates.append({'date': date_str, 'day_name': day_names[i], 'nz_date': nz_format})
    
    # Calculate previous and next week offsets for navigation
    prev_week = week_offset - 1
    next_week = week_offset + 1
    week_label = f"Week of {dates[0]['nz_date']} to {dates[4]['nz_date']}"
    
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Get all bookings for this week
        week_start = dates[0]['date']
        week_end = dates[4]['date']
        
        c.execute('''SELECT cb.id, cb.staff_code, cb.class_code, cb.date_required, cb.period, 
                           cb.recipe_id, cb.desired_servings, r.name as recipe_name, t.last_name, t.first_name
                    FROM class_bookings cb
                    LEFT JOIN recipes r ON cb.recipe_id = r.id
                    LEFT JOIN teachers t ON cb.staff_code = t.code
                    WHERE cb.date_required BETWEEN ? AND ?
                    ORDER BY cb.date_required, cb.period''',
                   (week_start, week_end))
        bookings_list = [dict(r) for r in c.fetchall()]
        
        # Get all recipes for ingredient lookup
        c.execute('SELECT id, name, ingredients, serving_size FROM recipes ORDER BY name')
        all_recipes = {}
        for r in c.fetchall():
            try:
                ings = json.loads(r['ingredients'] or '[]')
            except Exception:
                ings = []
            all_recipes[r['id']] = {'name': r['name'], 'ingredients': ings, 'serving_size': r['serving_size']}
    
    # Organize bookings into a grid structure
    grid = {}
    for date_obj in dates:
        for period in range(1, 6):
            grid[f"{date_obj['date']}_P{period}"] = None
    
    for booking in bookings_list:
        key = f"{booking['date_required']}_P{booking['period']}"
        if key in grid:
            grid[key] = booking
    
    return render_template('shoplist.html', dates=dates, grid=grid, bookings=bookings_list, recipes=all_recipes, 
                          week_offset=week_offset, prev_week=prev_week, next_week=next_week, week_label=week_label)


@app.route('/api/generate-shopping-list', methods=['POST'])
@require_role('VP', 'DK', 'MU')
def generate_shopping_list():
    """Auto-generate shopping list from selected booking IDs."""
    data = request.get_json()
    booking_ids = data.get('booking_ids', [])
    
    if not booking_ids:
        return jsonify({'error': 'No bookings selected'}), 400
    
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Get all bookings with their recipes
        placeholders = ','.join('?' * len(booking_ids))
        c.execute(f'''
            SELECT 
                cb.id,
                cb.recipe_id,
                cb.desired_servings,
                cb.date_required,
                cb.period,
                cb.class_code,
                r.name as recipe_name,
                r.ingredients,
                r.serving_size,
                t.first_name || ' ' || t.last_name as teacher_name
            FROM class_bookings cb
            LEFT JOIN recipes r ON cb.recipe_id = r.id
            LEFT JOIN teachers t ON cb.staff_code = t.code
            WHERE cb.id IN ({placeholders})
        ''', booking_ids)
        
        bookings = [dict(row) for row in c.fetchall()]
    
    # Aggregate ingredients
    ingredient_map = {}  # {normalized_name: {qty, unit, original_name}}
    
    for booking in bookings:
        if not booking['ingredients']:
            continue
        
        try:
            ingredients = json.loads(booking['ingredients'])
        except:
            continue
        
        recipe_servings = booking['serving_size'] or 1
        desired_servings = booking['desired_servings'] or recipe_servings
        scale_factor = desired_servings / recipe_servings if recipe_servings > 0 else 1
        
        for ing in ingredients:
            if isinstance(ing, dict):
                name = ing.get('name', ing.get('item', ''))
                qty = ing.get('qty', ing.get('quantity', 0))
                unit = ing.get('unit', '')
            elif isinstance(ing, str):
                # Parse string format
                parts = ing.split()
                qty = 0
                unit = ''
                name = ing
                if len(parts) >= 2:
                    try:
                        qty = float(parts[0])
                        unit = parts[1]
                        name = ' '.join(parts[2:]) if len(parts) > 2 else parts[1]
                    except:
                        pass
            else:
                continue
            
            if not name:
                continue
            
            # Normalize name for aggregation
            normalized = name.lower().strip()
            
            # Scale quantity
            scaled_qty = (float(qty) if qty else 0) * scale_factor
            
            if normalized in ingredient_map:
                # Add to existing
                if unit == ingredient_map[normalized]['unit']:
                    ingredient_map[normalized]['qty'] += scaled_qty
                else:
                    # Different units - keep separate
                    key = f"{normalized}_{unit}"
                    if key in ingredient_map:
                        ingredient_map[key]['qty'] += scaled_qty
                    else:
                        ingredient_map[key] = {
                            'qty': scaled_qty,
                            'unit': unit,
                            'name': name
                        }
            else:
                ingredient_map[normalized] = {
                    'qty': scaled_qty,
                    'unit': unit,
                    'name': name
                }
    
    # Convert to list and sort
    shopping_list = []
    for key, data in ingredient_map.items():
        shopping_list.append({
            'name': data['name'],
            'quantity': round(data['qty'], 2) if data['qty'] else '',
            'unit': data['unit']
        })
    
    shopping_list.sort(key=lambda x: x['name'].lower())
    
    return jsonify({
        'items': shopping_list,
        'total_count': len(shopping_list),
        'bookings_processed': len(bookings)
    })


def categorize_ingredient(ingredient_name):
    """Categorize ingredient by store section."""
    name_lower = ingredient_name.lower()
    
    # Produce
    produce = ['apple', 'banana', 'orange', 'lemon', 'lime', 'tomato', 'potato', 'onion', 'garlic', 
               'carrot', 'lettuce', 'spinach', 'cabbage', 'broccoli', 'cauliflower', 'pepper', 'capsicum',
               'cucumber', 'zucchini', 'mushroom', 'avocado', 'celery', 'ginger', 'herbs', 'parsley',
               'cilantro', 'basil', 'mint', 'thyme', 'rosemary', 'kale', 'chard', 'beetroot', 'pumpkin']
    
    # Dairy
    dairy = ['milk', 'cream', 'butter', 'cheese', 'yogurt', 'yoghurt', 'sour cream', 'feta', 'mozzarella',
             'parmesan', 'cheddar', 'brie', 'cottage cheese', 'ricotta', 'halloumi']
    
    # Meat & Seafood
    meat = ['chicken', 'beef', 'pork', 'lamb', 'turkey', 'bacon', 'sausage', 'mince', 'steak',
            'fish', 'salmon', 'tuna', 'prawns', 'shrimp', 'mussels', 'seafood']
    
    # Pantry/Dry Goods
    pantry = ['flour', 'sugar', 'rice', 'pasta', 'bread', 'cereal', 'oats', 'quinoa', 'couscous',
              'lentils', 'beans', 'chickpeas', 'oil', 'vinegar', 'sauce', 'stock', 'broth',
              'honey', 'jam', 'peanut butter', 'nuts', 'almonds', 'cashews', 'seeds', 'spice',
              'salt', 'pepper', 'cumin', 'paprika', 'cinnamon', 'vanilla', 'cocoa', 'chocolate',
              'baking powder', 'baking soda', 'yeast', 'cornstarch', 'cornflour']
    
    # Frozen
    frozen = ['frozen', 'ice cream', 'peas', 'corn', 'berries mixed']
    
    # Beverages
    beverages = ['juice', 'soda', 'water', 'tea', 'coffee', 'wine', 'beer']
    
    # Check categories
    for item in produce:
        if item in name_lower:
            return 'Produce'
    for item in dairy:
        if item in name_lower:
            return 'Dairy'
    for item in meat:
        if item in name_lower:
            return 'Meat & Seafood'
    for item in pantry:
        if item in name_lower:
            return 'Pantry'
    for item in frozen:
        if item in name_lower:
            return 'Frozen'
    for item in beverages:
        if item in name_lower:
            return 'Beverages'
    
    return 'Other'


@app.route('/api/shopping-list/toggle-item', methods=['POST'])
@require_role('VP', 'DK', 'MU')
def toggle_shopping_item():
    """Toggle 'already have' status for a shopping list item."""
    data = request.get_json()
    week_start = data.get('week_start')
    ingredient_name = data.get('ingredient_name')
    quantity = data.get('quantity', 0)
    unit = data.get('unit', '')
    
    if not week_start or not ingredient_name:
        return jsonify({'error': 'Missing required fields'}), 400
    
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        
        # Check if item exists
        c.execute('SELECT id, already_have FROM shopping_list_items WHERE week_start = ? AND ingredient_name = ?',
                  (week_start, ingredient_name))
        row = c.fetchone()
        
        if row:
            # Toggle status
            new_status = 0 if row[1] else 1
            c.execute('UPDATE shopping_list_items SET already_have = ? WHERE id = ?', (new_status, row[0]))
        else:
            # Create new item with already_have = 1
            category = categorize_ingredient(ingredient_name)
            c.execute('''INSERT INTO shopping_list_items 
                        (week_start, ingredient_name, quantity, unit, category, already_have)
                        VALUES (?, ?, ?, ?, ?, 1)''',
                      (week_start, ingredient_name, quantity, unit, category))
            new_status = 1
        
        conn.commit()
    
    return jsonify({'success': True, 'already_have': new_status})


@app.route('/api/shopping-list/get-status', methods=['POST'])
@require_role('VP', 'DK', 'MU')
def get_shopping_status():
    """Get 'already have' status for items in a week."""
    data = request.get_json()
    week_start = data.get('week_start')
    
    if not week_start:
        return jsonify({'error': 'Missing week_start'}), 400
    
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT ingredient_name, already_have FROM shopping_list_items WHERE week_start = ? AND already_have = 1',
                  (week_start,))
        items = {row['ingredient_name']: row['already_have'] for row in c.fetchall()}
    
    return jsonify({'items': items})


@app.route('/api/shopping-list/save', methods=['POST'])
@require_role('VP', 'DK', 'MU')
def save_shopping_list():
    """Save a shopping list for reuse."""
    data = request.get_json()
    list_name = data.get('list_name', '').strip()
    week_label = data.get('week_label', '')
    items = data.get('items', [])
    
    if not list_name or not items:
        return jsonify({'error': 'Missing list name or items'}), 400
    
    user_email = current_user.email if current_user.is_authenticated else 'unknown'
    
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('''INSERT INTO saved_shopping_lists (list_name, week_label, items, created_by)
                    VALUES (?, ?, ?, ?)''',
                  (list_name, week_label, json.dumps(items), user_email))
        conn.commit()
        list_id = c.lastrowid
    
    return jsonify({'success': True, 'list_id': list_id})


@app.route('/api/shopping-list/saved', methods=['GET'])
@require_role('VP', 'DK', 'MU')
def get_saved_lists():
    """Get all saved shopping lists."""
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT id, list_name, week_label, created_at FROM saved_shopping_lists ORDER BY created_at DESC')
        lists = [dict(row) for row in c.fetchall()]
    
    return jsonify({'lists': lists})


@app.route('/api/shopping-list/load/<int:list_id>', methods=['GET'])
@require_role('VP', 'DK', 'MU')
def load_saved_list(list_id):
    """Load a saved shopping list."""
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM saved_shopping_lists WHERE id = ?', (list_id,))
        row = c.fetchone()
        
        if not row:
            return jsonify({'error': 'List not found'}), 404
        
        list_data = dict(row)
        list_data['items'] = json.loads(list_data['items'])
    
    return jsonify(list_data)


@app.route('/recipes')
@require_role('VP', 'DK', 'MU')
def recipes_page():
    q = request.args.get('q', '').strip()
    dietary = request.args.get('dietary', '').strip()
    cuisine = request.args.get('cuisine', '').strip()
    difficulty = request.args.get('difficulty', '').strip()
    
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Build dynamic query
        query = "SELECT id, name, ingredients, instructions, serving_size, equipment, dietary_tags, cuisine, difficulty FROM recipes WHERE 1=1"
        params = []
        
        if q:
            query += " AND (name LIKE ? OR ingredients LIKE ? OR instructions LIKE ?)"
            term = f"%{q}%"
            params.extend([term, term, term])
        
        if dietary:
            query += " AND dietary_tags LIKE ?"
            params.append(f"%{dietary}%")
        
        if cuisine:
            query += " AND cuisine LIKE ?"
            params.append(f"%{cuisine}%")
        
        if difficulty:
            query += " AND difficulty = ?"
            params.append(difficulty)
        
        query += " ORDER BY name COLLATE NOCASE"
        
        c.execute(query, params)
        rows = [dict(r) for r in c.fetchall()]
        
        # Get all unique values for filters
        c.execute("SELECT DISTINCT cuisine FROM recipes WHERE cuisine IS NOT NULL AND cuisine != '' ORDER BY cuisine")
        all_cuisines = [r[0] for r in c.fetchall()]
        
        c.execute("SELECT DISTINCT dietary_tags FROM recipes WHERE dietary_tags IS NOT NULL AND dietary_tags != ''")
        all_tags_raw = [r[0] for r in c.fetchall()]
        all_dietary_tags = set()
        for tags in all_tags_raw:
            if tags:
                all_dietary_tags.update([t.strip() for t in tags.split(',')])
        all_dietary_tags = sorted(all_dietary_tags)

    # Decode JSON fields for template
    for r in rows:
        try:
            r['ingredients'] = json.loads(r.get('ingredients') or '[]')
        except Exception:
            r['ingredients'] = []
        try:
            r['equipment'] = json.loads(r.get('equipment') or '[]')
        except Exception:
            r['equipment'] = []
        # Parse dietary tags
        r['dietary_tags_list'] = [t.strip() for t in (r.get('dietary_tags') or '').split(',') if t.strip()]

    return render_template('recipes.html', rows=rows, q=q, dietary=dietary, cuisine=cuisine, difficulty=difficulty,
                         all_cuisines=all_cuisines, all_dietary_tags=all_dietary_tags)


@app.route('/api/update-recipe-tags/<int:recipe_id>', methods=['POST'])
@require_role('VP', 'DK')
def update_recipe_tags(recipe_id):
    """Quick API to update recipe dietary tags, cuisine, and difficulty."""
    data = request.get_json()
    
    dietary_tags = data.get('dietary_tags', '')  # comma-separated
    cuisine = data.get('cuisine', '')
    difficulty = data.get('difficulty', '')
    
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('''UPDATE recipes 
                    SET dietary_tags = ?, cuisine = ?, difficulty = ?
                    WHERE id = ?''',
                 (dietary_tags, cuisine, difficulty, recipe_id))
    
    return jsonify({'success': True, 'message': 'Tags updated'})


@app.route('/recipes/suggest', methods=['POST'])
@require_login
def suggest_recipe():
    """Handle recipe suggestion submissions and email to VP"""
    try:
        recipe_name = request.form.get('recipe_name', '').strip()
        recipe_url = request.form.get('recipe_url', '').strip()
        reason = request.form.get('reason', '').strip()
        
        if not recipe_name:
            flash('Recipe name is required.', 'error')
            return redirect(url_for('recipes_page'))
        
        # Get VP email from database
        vp_email = None
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute("SELECT email FROM teachers WHERE code = 'VP' LIMIT 1")
            result = c.fetchone()
            if result:
                vp_email = result[0]
        
        if not vp_email:
            flash('Could not find VP email address.', 'error')
            return redirect(url_for('recipes_page'))
        
        # Get current user info safely
        user_name = current_user.name if hasattr(current_user, 'name') else 'Unknown User'
        user_email = current_user.email if hasattr(current_user, 'email') else 'No email'
        
        # Save suggestion to database
        try:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute('''INSERT INTO recipe_suggestions 
                            (recipe_name, recipe_url, reason, suggested_by_name, suggested_by_email) 
                            VALUES (?, ?, ?, ?, ?)''',
                         (recipe_name, recipe_url, reason, user_name, user_email))
        except sqlite3.OperationalError as e:
            print(f"Error saving suggestion to database (table may not exist): {e}")
            flash('Note: Your suggestion was logged but not saved to the database. Please contact VP to run setup_database.py', 'warning')
        
        # Compose email
        subject = f"Recipe Suggestion: {recipe_name}"
        body = f"""A new recipe has been suggested for the Food Room Recipe Book.

Suggested by: {user_name} ({user_email})
Recipe Name: {recipe_name}
"""
        
        if recipe_url:
            body += f"Recipe URL: {recipe_url}\n"
        
        if reason:
            body += f"\nReason:\n{reason}\n"
        
        body += f"\n---\nSubmitted on {datetime.datetime.now().strftime('%Y-%m-%d at %H:%M')}"
        
        # Send actual email
        email_sent = False
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Get SMTP configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME')
            smtp_password = os.getenv('SMTP_PASSWORD')
            smtp_from_email = os.getenv('SMTP_FROM_EMAIL', smtp_username)
            
            if smtp_username and smtp_password:
                # Create message
                msg = MIMEMultipart()
                msg['From'] = smtp_from_email or 'Food Room System <noreply@whsdtech.com>'
                msg['To'] = vp_email
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'plain'))
                
                # Send email
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
                server.quit()
                
                email_sent = True
                print(f"Email sent successfully to {vp_email}")
            else:
                print("SMTP credentials not configured - email not sent")
                print(f"RECIPE SUGGESTION EMAIL:\nTo: {vp_email}\nSubject: {subject}\n\n{body}")
                
        except Exception as email_error:
            print(f"Failed to send email: {email_error}")
            print(f"RECIPE SUGGESTION EMAIL (not sent):\nTo: {vp_email}\nSubject: {subject}\n\n{body}")
        
        if email_sent:
            flash(f'Thank you! Your suggestion for "{recipe_name}" has been emailed to the VP and saved to the database.', 'success')
        else:
            flash(f'Thank you! Your suggestion for "{recipe_name}" has been saved. The VP will review it in the Admin panel.', 'success')
        
    except Exception as e:
        print(f"Error in suggest_recipe: {e}")
        import traceback
        traceback.print_exc()
        flash('There was an error submitting your suggestion. Please try again or contact the VP directly.', 'error')
    
    return redirect(url_for('recipes_page'))


@app.route('/recbk')
def recbk():
    q = request.args.get('q', '').strip()
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        if q:
            term = f"%{q}%"
            c.execute(
                "SELECT id, name, ingredients, instructions, serving_size, equipment, dietary_tags, cuisine, difficulty FROM recipes "
                "WHERE name LIKE ? OR ingredients LIKE ? "
                "ORDER BY name COLLATE NOCASE",
                (term, term),
            )
        else:
            c.execute(
                "SELECT id, name, ingredients, instructions, serving_size, equipment, dietary_tags, cuisine, difficulty FROM recipes "
                "ORDER BY name COLLATE NOCASE"
            )
        rows = [dict(r) for r in c.fetchall()]

    # Decode JSON fields for template
    for r in rows:
        try:
            r['ingredients'] = json.loads(r.get('ingredients') or '[]')
        except Exception:
            r['ingredients'] = []
        try:
            r['equipment'] = json.loads(r.get('equipment') or '[]')
        except Exception:
            r['equipment'] = []
        try:
            r['dietary_tags_list'] = json.loads(r.get('dietary_tags') or '[]')
        except Exception:
            r['dietary_tags_list'] = []

    # Get user's favorites if logged in
    favorites = []
    if current_user.is_authenticated:
        try:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute('SELECT recipe_id FROM recipe_favorites WHERE user_email = ?', (current_user.email,))
                favorites = [row[0] for row in c.fetchall()]
        except sqlite3.OperationalError:
            # Table doesn't exist yet - run setup_database.py to create it
            favorites = []

    return render_template('recbk.html', rows=rows, q=q, favorites=favorites)


@app.route('/recipe/favorite/<int:recipe_id>', methods=['POST'])
@require_login
def add_favorite(recipe_id):
    """Add a recipe to user's favorites"""
    try:
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute('INSERT OR IGNORE INTO recipe_favorites (user_email, recipe_id) VALUES (?, ?)',
                     (current_user.email, recipe_id))
        return jsonify({'success': True, 'message': 'Added to favorites'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/recipe/unfavorite/<int:recipe_id>', methods=['POST'])
@require_login
def remove_favorite(recipe_id):
    """Remove a recipe from user's favorites"""
    try:
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM recipe_favorites WHERE user_email = ? AND recipe_id = ?',
                     (current_user.email, recipe_id))
        return jsonify({'success': True, 'message': 'Removed from favorites'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/recipe/<int:recipe_id>', methods=['GET', 'POST'])
@require_role('VP', 'DK', 'MU')
def recipe_detail(recipe_id):
    # Handle photo upload
    if request.method == 'POST':
        # Delete photo action
        if request.form.get('delete_photo'):
            import os
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute('SELECT photo FROM recipes WHERE id = ?', (recipe_id,))
                row = c.fetchone()
                if row and row[0]:
                    photo_name = row[0]
                    photo_path = os.path.join('static', 'uploads', 'recipes', photo_name)
                    try:
                        if os.path.exists(photo_path):
                            os.remove(photo_path)
                    except Exception:
                        pass
                c.execute('UPDATE recipes SET photo = NULL WHERE id = ?', (recipe_id,))
            return redirect(url_for('recipe_detail', recipe_id=recipe_id))

        # Upload/replace photo
        photo = request.files.get('photo')
        if photo and photo.filename:
            import os
            upload_dir = os.path.join('static', 'uploads', 'recipes')
            os.makedirs(upload_dir, exist_ok=True)
            _, ext = os.path.splitext(photo.filename)
            filename = f"{recipe_id}{ext.lower()}"
            path = os.path.join(upload_dir, filename)
            # overwrite if exists
            photo.save(path)
            # store relative path in DB
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute('UPDATE recipes SET photo = ? WHERE id = ?', (filename, recipe_id))
            return redirect(url_for('recipe_detail', recipe_id=recipe_id))

    # GET: show recipe
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT id, name, ingredients, instructions, serving_size, equipment, photo, dietary_tags, cuisine, difficulty FROM recipes WHERE id = ?', (recipe_id,))
        row = c.fetchone()
        if not row:
            return ('Recipe not found', 404)
        recipe = dict(row)
        try:
            ingredients = json.loads(recipe.get('ingredients') or '[]')
        except Exception:
            ingredients = []
        try:
            equipment = json.loads(recipe.get('equipment') or '[]')
        except Exception:
            equipment = []

        # --- Nutrient estimation and dietary flags (lightweight heuristics) ---
        # Simple per-100g nutrition lookup for common ingredients (kcal, protein, carbs, fat)
        nutrition_db = {
            'beef': (250, 26, 0, 15),
            'chicken': (165, 31, 0, 3.6),
            'pork': (242, 27, 0, 14),
            'potato': (77, 2, 17, 0.1),
            'carrot': (41, 0.9, 10, 0.2),
            'onion': (40, 1.1, 9, 0.1),
            'mushroom': (22, 3.1, 3.3, 0.3),
            'tomato': (18, 0.9, 3.9, 0.2),
            'cheese': (402, 25, 1.3, 33),
            'milk': (42, 3.4, 5, 1),
            'butter': (717, 0.9, 0.1, 81),
            'flour': (364, 10, 76, 1),
            'rice': (130, 2.7, 28, 0.3),
            'pasta': (131, 5, 25, 1.1),
            'beans': (347, 21, 63, 1.2),
            'lentils': (116, 9, 20, 0.4),
            'tofu': (76, 8, 1.9, 4.8),
            'egg': (155, 13, 1.1, 11),
            'olive oil': (884, 0, 0, 100),
            'sugar': (387, 0, 100, 0),
            'bread': (265, 9, 49, 3.2),
            'salmon': (208, 20, 0, 13),
        }

        gluten_keywords = ['flour', 'bread', 'pasta', 'breadcrumbs', 'cereal', 'wheat', 'barley', 'rye', 'semolina']
        dairy_keywords = ['milk', 'cheese', 'butter', 'cream', 'yogurt', 'yoghurt', 'custard']

        total_kcal = 0.0
        total_protein = 0.0
        total_carbs = 0.0
        total_fat = 0.0

        found_gluten = False
        found_dairy = False

        # Inspect ingredient names for keywords and approximate nutrition by presence
        for ing in ingredients:
            name = ''
            if isinstance(ing, dict):
                name = (ing.get('ingredient') or '')
            else:
                name = str(ing)
            lname = (name or '').lower()

            # dietary flags
            if any(k in lname for k in gluten_keywords):
                found_gluten = True
            if any(k in lname for k in dairy_keywords):
                found_dairy = True

            # pick a nutrition row by keyword match
            matched = None
            for key in nutrition_db:
                if key in lname:
                    matched = key
                    break

            if matched:
                kcal, prot, carbs, fat = nutrition_db[matched]
                # crude: assume 100g per listed ingredient item unless quantity in grams is provided
                qty = 100.0
                # try to extract numeric gram quantity from ingredient dict
                try:
                    if isinstance(ing, dict):
                        q = str(ing.get('quantity') or '').strip()
                        u = str(ing.get('unit') or '').lower()
                        if q:
                            # handle simple numeric values
                            qn = None
                            try:
                                qn = float(q)
                            except Exception:
                                m = re.search(r"(\d+[\.,]?\d*)", q)
                                if m:
                                    qn = float(m.group(1).replace(',','.'))
                            if qn is not None:
                                if u in ('g','gram','grams'):
                                    qty = qn
                                elif u in ('kg','kilogram','kilograms'):
                                    qty = qn * 1000.0
                                elif u in ('mg',):
                                    qty = qn / 1000.0
                                elif u in ('tbsp', 'tablespoon', 'tablespoons'):
                                    qty = qn * 15.0
                                elif u in ('tsp', 'teaspoon', 'teaspoons'):
                                    qty = qn * 5.0
                                elif u in ('cup','cups'):
                                    qty = qn * 240.0
                                else:
                                    # unknown unit: keep default 100g
                                    pass
                except Exception:
                    qty = 100.0

                factor = qty / 100.0
                total_kcal += kcal * factor
                total_protein += prot * factor
                total_carbs += carbs * factor
                total_fat += fat * factor

        # Dietary decisions: if no gluten/dairy keywords found -> likely free
        looks_gluten_free = not found_gluten
        looks_dairy_free = not found_dairy

        # Per-serving if serving_size available
        per_serving = None
        if recipe.get('serving_size'):
            try:
                s = int(recipe.get('serving_size'))
                per_serving = {
                    'kcal': round(total_kcal / s, 1),
                    'protein': round(total_protein / s, 1),
                    'carbs': round(total_carbs / s, 1),
                    'fat': round(total_fat / s, 1)
                }
            except Exception:
                per_serving = None

        nutrition = {
            'total': {'kcal': round(total_kcal,1), 'protein': round(total_protein,1), 'carbs': round(total_carbs,1), 'fat': round(total_fat,1)},
            'per_serving': per_serving,
            'gluten_free': looks_gluten_free,
            'dairy_free': looks_dairy_free
        }

        return render_template('recipe_details.html', recipe=recipe, ingredients=ingredients, equipment=equipment, nutrition=nutrition)


@app.route('/admin/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
@require_role('VP')
def edit_recipe(recipe_id):
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        instructions = request.form.get('instructions','').strip()
        serving_raw = request.form.get('serving_size','').strip()
        dietary_tags = request.form.get('dietary_tags','').strip()
        cuisine = request.form.get('cuisine','').strip()
        difficulty = request.form.get('difficulty','').strip()
        try:
            serving = int(serving_raw) if serving_raw != '' else None
        except ValueError:
            serving = None

            # Ingredients: support array inputs from dynamic form
            ingredients = []
            ing_lines = request.form.getlist('ingredient_line[]') or request.form.getlist('ingredient_line')
            if ing_lines:
                for line in ing_lines:
                    line = line.strip()
                    if not line:
                        continue
                    parsed = parse_ingredient_line(line)
                    ingredients.append(parsed)
            else:
                # fallback to textarea
                ingredients_text = request.form.get('ingredients_text','').strip()
                for line in ingredients_text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    parsed = parse_ingredient_line(line)
                    ingredients.append(parsed)

        # Equipment: textarea, one item per line or comma separated
        # Equipment: support array inputs
        equipment = []
        eq_items = request.form.getlist('equipment_item[]') or request.form.getlist('equipment_item')
        if eq_items:
            for it in eq_items:
                it = it.strip()
                if it:
                    # split comma-separated pieces in each field too
                    for part in it.split(','):
                        p = part.strip()
                        if p:
                            equipment.append(p)
        else:
            equipment_text = request.form.get('equipment_text','').strip()
            if equipment_text:
                for line in equipment_text.splitlines():
                    for part in line.split(','):
                        p = part.strip()
                        if p:
                            equipment.append(p)

        # Update DB
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute('UPDATE recipes SET name = ?, ingredients = ?, instructions = ?, serving_size = ?, equipment = ?, dietary_tags = ?, cuisine = ?, difficulty = ? WHERE id = ?',
                      (name, json.dumps(ingredients), instructions, serving, json.dumps(equipment), dietary_tags, cuisine, difficulty, recipe_id))
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))

    # GET - load recipe
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT id, name, ingredients, instructions, serving_size, equipment, dietary_tags, cuisine, difficulty FROM recipes WHERE id = ?', (recipe_id,))
        row = c.fetchone()
        if not row:
            return ('Not found', 404)
        recipe = dict(row)
        try:
            ingredients = json.loads(recipe.get('ingredients') or '[]')
        except Exception:
            ingredients = []
        try:
            equipment = json.loads(recipe.get('equipment') or '[]')
        except Exception:
            equipment = []

    # Prepare textareas content
    ingredients_text = '\n'.join([f"{it.get('quantity','')} {it.get('unit','')} {it.get('ingredient','')}'.strip()" for it in ingredients])
    equipment_text = '\n'.join(equipment)

    return render_template('edit_recipe.html', recipe=recipe, ingredients_text=ingredients_text, equipment_text=equipment_text)


# parse_recipes_from_text and format_recipe are imported from recipe_parser.py


def remove_duplicate_recipes(conn=None):
    """Remove duplicate recipes based on normalized name+instructions, keep earliest id."""
    close_conn = False
    if conn is None:
        conn = sqlite3.connect(DATABASE)
        close_conn = True
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT id, name, instructions FROM recipes')
    rows = c.fetchall()

    def _norm(s):
        if not s:
            return ''
        s = s.lower()
        s = s.replace('•', ' ').replace('●', ' ')
        s = re.sub(r"[^a-z0-9]+", ' ', s)
        s = ' '.join(s.split()).strip()
        return s

    groups = {}
    for r in rows:
        key = (_norm(r['name']), _norm(r['instructions']))
        groups.setdefault(key, []).append((r['id'], r['name']))

    deleted = []
    for key, items in groups.items():
        if len(items) > 1:
            items_sorted = sorted(items, key=lambda x: x[0])
            keep_id = items_sorted[0][0]
            for dup_id, dup_name in items_sorted[1:]:
                c.execute('DELETE FROM recipes WHERE id = ?', (dup_id,))
                deleted.append({'id': dup_id, 'name': dup_name, 'kept_id': keep_id})

    conn.commit()
    if close_conn:
        conn.close()
    return deleted


def remove_nonfood_recipes(conn=None):
    """Delete recipes that don't contain any common food keywords in name/ingredients/instructions."""
    keywords = [
        'beef','chicken','pork','lamb','turkey','tuna','salmon','tofu','prawn','prawns','shrimp',
        'mince','sausage','bacon','ham','beans','bean','lentil','lentils','rice','pasta','noodle','noodles',
        'potato','potatoes','carrot','carrots','onion','onions','garlic','tomato','tomatoes','mushroom','mushrooms',
        'pepper','peppers','cheese','milk','egg','eggs','butter','flour','sugar','salt','oil','olive oil','bread',
        'cucumber','lettuce','spinach','pea','peas','sweetcorn','corn','broccoli','cauliflower','cabbage',
        'courgette','zucchini','yogurt','yoghurt','chickpea','chickpeas','kidney','quinoa','oats','porridge','apple',
        'banana','orange','tomato','beansprout','spring onion','spring onions','pulses','lentil'
    ]
    kw_re = re.compile(r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b", re.I)

    close_conn = False
    if conn is None:
        conn = sqlite3.connect(DATABASE)
        close_conn = True
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('SELECT id, name, instructions, ingredients FROM recipes')
    rows = c.fetchall()
    to_delete = []
    for r in rows:
        texts = []
        if r['name']:
            texts.append(r['name'])
        if r['instructions']:
            texts.append(r['instructions'])
        if r['ingredients']:
            try:
                data = json.loads(r['ingredients'])
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            for k in ('ingredient','name','text'):
                                if k in item and item[k]:
                                    texts.append(str(item[k]))
                        else:
                            texts.append(str(item))
                else:
                    texts.append(str(data))
            except Exception:
                texts.append(str(r['ingredients']))
        combined = ' '.join(t for t in texts if t).lower()
        if not combined.strip():
            to_delete.append((r['id'], r['name']))
            continue
        if not kw_re.search(combined):
            to_delete.append((r['id'], r['name']))

    deleted = []
    for tid, name in to_delete:
        c.execute('DELETE FROM recipes WHERE id = ?', (tid,))
        deleted.append({'id': tid, 'name': name})

    conn.commit()
    if close_conn:
        conn.close()
    return deleted


def extract_recipe_from_url(url):
    """Extract recipe data from a URL (JSON-LD, microdata, or fallback HTML parsing)."""
    if not requests or not BeautifulSoup:
        return {'error': 'requests or BeautifulSoup not installed'}
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        return {'error': f'Failed to fetch URL: {str(e)}'}
    
    # Try to extract JSON-LD structured data
    soup = BeautifulSoup(response.text, 'html.parser')
    
    recipe_data = None
    # Look for JSON-LD Recipe schema
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'Recipe':
                recipe_data = data
                break
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('@type') == 'Recipe':
                        recipe_data = item
                        break
        except Exception:
            pass
    
    if recipe_data:
        # Extract fields from JSON-LD
        return {
            'success': True,
            'source': 'json-ld',
            'name': recipe_data.get('name', ''),
            'ingredients': recipe_data.get('recipeIngredient', []),
            'instructions': recipe_data.get('recipeInstructions', []),
            'serving_size': recipe_data.get('recipeYield', ''),
            'prep_time': recipe_data.get('prepTime', ''),
            'cook_time': recipe_data.get('cookTime', ''),
            'url': url
        }
    
    # Fallback: basic HTML parsing with improved extraction
    title_tag = soup.find('h1') or soup.find('title')
    name = title_tag.get_text(strip=True) if title_tag else 'Recipe from URL'
    
    # Remove title from name if it's in the page title
    if name and '|' in name:
        name = name.split('|')[0].strip()
    
    ingredients = []
    instructions_text = ''
    
    # First try: look for structured data with itemProp="recipeIngredient"
    ing_items = soup.find_all(itemprop='recipeIngredient')
    if ing_items:
        for item in ing_items:
            # Extract text, handling bold spans for quantity
            bold_span = item.find('span', style=lambda x: x and 'bold' in x.lower())
            
            # Look for description in parent <li> or sibling elements
            parent_li = item.find_parent('li')
            desc_span = parent_li.find('span', class_='desc') if parent_li else None
            
            if bold_span:
                quantity_text = bold_span.get_text(strip=True)
                # Get ingredient name (everything else in the tag)
                ingredient_parts = []
                for elem in item.children:
                    if elem.name is None:  # Text node
                        text = str(elem).strip()
                        if text and text != '<!-- -->':
                            ingredient_parts.append(text)
                    elif elem.name != 'span' or 'bold' not in elem.get('style', ''):
                        # Not the bold quantity span
                        ingredient_parts.append(elem.get_text(strip=True))
                
                ingredient_text = ' '.join(p for p in ingredient_parts if p).strip()
                
                # Add description if it contains measurement info
                desc_text = desc_span.get_text(strip=True) if desc_span else ''
                if desc_text:
                    # Check if description has measurement info (numbers or weight/volume units)
                    if any(char.isdigit() for char in desc_text) or any(unit in desc_text.lower() for unit in ['g', 'kg', 'ml', 'l', 'oz', 'lb']):
                        ingredient_text += f' ({desc_text})'
                    else:
                        # Just append without parens for things like "crushed", "sliced", etc.
                        ingredient_text += f', {desc_text}'
                
                # For countable items without a standard unit, add "no." after quantity
                # Check if ingredient_text contains words that are typically countable items
                countable_keywords = ['fillet', 'steak', 'chop', 'clove', 'onion', 
                                     'egg', 'tomato', 'potato', 'apple', 'pepper', 'carrot',
                                     'breast', 'thigh', 'drumstick', 'cutlet']
                
                # Check if this looks like a countable item (no weight/volume unit in quantity)
                has_standard_unit = any(unit in quantity_text.lower() for unit in 
                                       ['cup', 'cups', 'tbsp', 'tsp', 'g', 'kg', 'ml', 'l', 'oz', 'lb'])
                
                contains_countable = any(keyword in ingredient_text.lower() for keyword in countable_keywords)
                
                if not has_standard_unit and contains_countable:
                    # Insert "no." after the quantity
                    full_text = f"{quantity_text} no. {ingredient_text}".strip()
                else:
                    full_text = f"{quantity_text} {ingredient_text}".strip()
            else:
                full_text = item.get_text(separator=' ', strip=True)
            
            if full_text and len(full_text) > 2:
                ingredients.append(full_text)
    
    # Fallback: Look for ingredient list - try multiple common selectors
    if not ingredients:
        ing_selectors = [
            ('ul', 'ingredient'),
            ('ol', 'ingredient'),
            ('ul', 'ingred'),
            ('div', 'ingredient'),
            ('section', 'ingredient'),
        ]
        
        for tag_name, class_pattern in ing_selectors:
            ing_sections = soup.find_all(tag_name, class_=re.compile(class_pattern, re.I))
            for section in ing_sections:
                # Only process direct list items, not nested ones
                list_items = section.find_all('li', recursive=False) if tag_name in ['ul', 'ol'] else section.find_all(['div', 'p'], recursive=False)
                
                for li in list_items:
                    ing_text = li.get_text(separator=' ', strip=True)
                    if ing_text and len(ing_text) > 3:  # Filter out very short text
                        ingredients.append(ing_text)
            if ingredients:
                break
    
    # If no ingredients found, try extracting from any list-like structure
    if not ingredients:
        for ul in soup.find_all(['ul', 'ol']):
            for li in ul.find_all('li', recursive=False):
                # Get text with better spacing
                ing_text = li.get_text(separator=' ', strip=True)
                if ing_text and len(ing_text) > 3 and not any(skip in ing_text.lower() for skip in ['menu', 'navigation', 'sidebar', 'advertisement']):
                    ingredients.append(ing_text)
    
    # Look for instructions - try multiple patterns
    inst_selectors = [
        ('div', 'instruction'),
        ('div', 'method'),
        ('div', 'direction'),
        ('section', 'instruction'),
        ('ol', 'instruction'),
    ]
    
    for tag_name, class_pattern in inst_selectors:
        inst_sections = soup.find_all(tag_name, class_=re.compile(class_pattern, re.I))
        for section in inst_sections:
            instructions_text += section.get_text(strip=True) + '\n'
        if instructions_text:
            break
    
    # Clean up instructions
    instructions_text = instructions_text.strip() or 'Instructions not found - please add manually'
    
    # Remove duplicates from ingredients
    ingredients = list(dict.fromkeys(ingredients))  # Preserve order, remove dupes
    
    return {
        'success': True,
        'source': 'html-fallback',
        'name': name,
        'ingredients': ingredients,  # Return as simple strings, form will parse them
        'instructions': instructions_text,
        'url': url,
        'warning': 'No structured recipe data found - extracted from HTML. Please review and edit carefully.'
    }


@app.route('/upload_url', methods=['POST'])
@require_role('VP')
def upload_url():
    """Handle recipe upload from URL."""
    url = request.form.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    # Ensure URL is valid
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    recipe_data = extract_recipe_from_url(url)
    
    if 'error' in recipe_data:
        return jsonify(recipe_data), 400
    
    return jsonify(recipe_data)


@app.route('/load_recipe_from_url', methods=['POST'])
@require_role('VP')
def load_recipe_from_url():
    """Load extracted recipe data into the upload form."""
    try:
        recipe_json = request.form.get('recipe_data', '{}')
        recipe_data = json.loads(recipe_json)
        
        # Convert ingredients to text format for the form
        ing_list = recipe_data.get('ingredients', [])
        ing_text = '\n'.join(ing_list) if isinstance(ing_list, list) else str(ing_list)
        
        # Convert instructions to text
        inst = recipe_data.get('instructions', '')
        if isinstance(inst, list):
            inst = '\n'.join([str(s.get('text', s)) if isinstance(s, dict) else str(s) for s in inst])
        
        # Render the upload form with pre-filled data
        return render_template('upload_recipe.html', 
                             prefilled_name=recipe_data.get('name', ''),
                             prefilled_ingredients=ing_text,
                             prefilled_instructions=inst,
                             prefilled_serving=recipe_data.get('serving_size', 4),
                             from_url=True)
    except Exception as e:
        flash(f'Error loading recipe: {str(e)}')
        return redirect(url_for('recipes_page'))


@app.route('/booking')
@require_role('VP', 'DK', 'MU')
def booking_calendar():
    """Show booking calendar with all class bookings."""
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT 
                cb.id,
                cb.date_required as date,
                'Period ' || cb.period as period,
                cb.staff_code,
                cb.class_code,
                cb.recipe_id,
                cb.desired_servings as servings,
                r.name as recipe_name,
                t.first_name || ' ' || t.last_name as staff_name
            FROM class_bookings cb
            LEFT JOIN recipes r ON cb.recipe_id = r.id
            LEFT JOIN teachers t ON cb.staff_code = t.code
            ORDER BY cb.date_required, cb.period
        ''')
        bookings = [dict(row) for row in c.fetchall()]
    
    return render_template('booking.html', bookings_json=json.dumps(bookings))


@app.route('/booking/export/ical')
@require_role('VP', 'DK', 'MU')
def export_ical():
    """Export bookings as iCal format for Google Calendar import."""
    from datetime import datetime
    
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT 
                cb.date_required as date,
                cb.period,
                cb.staff_code,
                cb.class_code,
                r.name as recipe_name,
                cb.desired_servings as servings,
                t.first_name || ' ' || t.last_name as staff_name
            FROM class_bookings cb
            LEFT JOIN recipes r ON cb.recipe_id = r.id
            LEFT JOIN teachers t ON cb.staff_code = t.code
            ORDER BY cb.date_required, cb.period
        ''')
        bookings = c.fetchall()
    
    # Build iCal format
    ical = ['BEGIN:VCALENDAR']
    ical.append('VERSION:2.0')
    ical.append('PRODID:-//Food Room Inventory//Class Bookings//EN')
    ical.append('CALSCALE:GREGORIAN')
    ical.append('METHOD:PUBLISH')
    ical.append('X-WR-CALNAME:Food Room Class Bookings')
    ical.append('X-WR-TIMEZONE:Pacific/Auckland')
    
    for booking in bookings:
        date_str = booking['date']
        period = booking['period']
        
        # Parse date and create event times based on period
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Map periods to times (adjust these to match your school schedule)
        period_times = {
            1: ('08:45', '09:45'),
            2: ('09:45', '10:45'),
            3: ('11:05', '12:05'),
            4: ('12:05', '13:05'),
            5: ('13:45', '14:45'),
        }
        
        start_time, end_time = period_times.get(period, ('09:00', '10:00'))
        
        # Format datetime for iCal (YYYYMMDDTHHMMSS)
        start_dt = f"{date_str.replace('-', '')}T{start_time.replace(':', '')}00"
        end_dt = f"{date_str.replace('-', '')}T{end_time.replace(':', '')}00"
        
        # Create unique ID
        uid = f"{date_str}-{period}-{booking['class_code']}@foodroom.local"
        
        # Build event
        ical.append('BEGIN:VEVENT')
        ical.append(f'UID:{uid}')
        ical.append(f'DTSTART:{start_dt}')
        ical.append(f'DTEND:{end_dt}')
        ical.append(f'SUMMARY:{booking["recipe_name"]} - {booking["class_code"]}')
        ical.append(f'DESCRIPTION:Recipe: {booking["recipe_name"]}\\nClass: {booking["class_code"]}\\nStaff: {booking["staff_name"]}\\nServings: {booking["servings"]}\\nPeriod: {period}')
        ical.append(f'LOCATION:Food Room')
        ical.append('STATUS:CONFIRMED')
        ical.append('END:VEVENT')
    
    ical.append('END:VCALENDAR')
    
    # Return as downloadable file
    from flask import Response
    return Response(
        '\r\n'.join(ical),
        mimetype='text/calendar',
        headers={
            'Content-Disposition': 'attachment; filename=food_room_bookings.ics'
        }
    )


if __name__ == '__main__':
    init_db()
    app.run(debug=True)