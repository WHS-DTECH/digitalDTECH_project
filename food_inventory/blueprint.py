
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
@food_inventory_bp.route('/login')
def login():
    return render_template('login.html')

# ... (move all other routes here, updating decorators)
