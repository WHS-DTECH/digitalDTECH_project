from flask import Blueprint

food_inventory_bp = Blueprint(
    'food_inventory',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/food_inventory'
)

# Import all routes and views from the original app.py
# You will need to move all route functions from app.py to this file and change '@app.route' to '@food_inventory_bp.route'

# Example:
# @food_inventory_bp.route('/')
# def index():
#     return render_template('recbk.html')

# ... (move all other routes here, updating decorators)
