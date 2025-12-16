

from flask import Blueprint, render_template, request
import json
import sqlite3
from flask_login import current_user
import os

# Define the Blueprint at the top before any route decorators
food_inventory_bp = Blueprint(
    'food_inventory',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/food_inventory'
)

# Recipe Book (recbk) route (moved from app.py)
@food_inventory_bp.route('/recbk')
def recbk():
    db_path = os.path.join(os.path.dirname(__file__), 'recipes.db')
    q = request.args.get('q', '').strip()
    with sqlite3.connect(db_path) as conn:
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
            with sqlite3.connect(db_path) as conn:
                c = conn.cursor()
                c.execute('SELECT recipe_id FROM recipe_favorites WHERE user_email = ?', (current_user.email,))
                favorites = [row[0] for row in c.fetchall()]
        except sqlite3.OperationalError:
            # Table doesn't exist yet - run setup_database.py to create it
            favorites = []

    return render_template('recbk.html', rows=rows, q=q, favorites=favorites)

# Admin route (moved from app.py)
import csv, io, sqlite3, os
from .auth import require_role

@food_inventory_bp.route('/admin', methods=['GET', 'POST'])
@require_role('VP')
def admin():
    # Get recipe suggestions for display
    suggestions = []
    try:
        db_path = os.path.join(os.path.dirname(__file__), 'recipes.db')
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute('''SELECT id, recipe_name, recipe_url, reason, suggested_by_name, \
                        suggested_by_email, created_at, status \
                        FROM recipe_suggestions \
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
            return redirect(url_for('food_inventory.admin'))

        # Read and normalize file content
        file_content = uploaded.stream.read().decode('utf-8', errors='ignore')
        # Normalize line endings
        file_content = file_content.replace('\r\n', '\n').replace('\r', '\n')
        stream = io.StringIO(file_content)
        reader = csv.DictReader(stream)
        rows = []
        db_path = os.path.join(os.path.dirname(__file__), 'recipes.db')
        with sqlite3.connect(db_path) as conn:
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
                return redirect(url_for('food_inventory.admin'))
        preview_data = rows
        flash(f'Staff CSV processed: {len(rows)} rows')

    return render_template('admin.html', preview_data=preview_data, suggestions=suggestions)

from flask import Blueprint, render_template

food_inventory_bp = Blueprint(
    'food_inventory',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/food_inventory'
)

# Ensure current_user is available in all templates rendered by this blueprint
from flask_login import current_user
@food_inventory_bp.app_context_processor
def inject_user():
    return dict(current_user=current_user)

# Import all routes and views from the original app.py
# You will need to move all route functions from app.py to this file and change '@app.route' to '@food_inventory_bp.route'



# Root route for food_inventory blueprint
@food_inventory_bp.route('/')
def index():
    return render_template('recbk.html')


# Login route for food_inventory blueprint
from flask import request, redirect, url_for, flash, session
from flask_login import login_user, logout_user
from google_auth_oauthlib.flow import Flow
import os

# These should be imported from app.py or set here as needed
from .auth import User, get_staff_code_from_email

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/auth/callback')
SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]

@food_inventory_bp.route('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('food_inventory.index'))
    return render_template('login.html')

@food_inventory_bp.route('/auth/google')
def auth_google():
    if GOOGLE_CLIENT_ID is None or GOOGLE_CLIENT_SECRET is None:
        flash('Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.')
        return redirect(url_for('food_inventory.login'))
    client_config = {
        'web': {
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://accounts.google.com/o/oauth2/token',
            'redirect_uris': [GOOGLE_REDIRECT_URI]
        }
    }
    redirect_uri = GOOGLE_REDIRECT_URI
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='select_account'
    )
    session['oauth_state'] = state
    session['redirect_uri'] = redirect_uri
    return redirect(authorization_url)

@food_inventory_bp.route('/auth/callback')
def auth_callback():
    state = session.get('oauth_state')
    redirect_uri = session.get('redirect_uri', GOOGLE_REDIRECT_URI)
    if not state:
        flash('OAuth state mismatch. Please try logging in again.')
        return redirect(url_for('food_inventory.login'))
    try:
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
        authorization_response = request.url.replace('http://', 'http://')
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials
        user_info_url = 'https://www.googleapis.com/oauth2/v1/userinfo'
        import requests as req_lib
        headers = {'Authorization': f'Bearer {credentials.token}'}
        response = req_lib.get(user_info_url, headers=headers)
        user_info = response.json()
        google_id = user_info.get('id')
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0])
        staff_code = get_staff_code_from_email(email)
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
        return redirect(url_for('food_inventory.index'))
    except Exception as e:
        flash(f'Authentication error: {str(e)}')
        return redirect(url_for('food_inventory.login'))

@food_inventory_bp.route('/logout')
def logout():
    logout_user()
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('food_inventory.index'))

# ... (move all other routes here, updating decorators)
