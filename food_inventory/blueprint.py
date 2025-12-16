
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
