from flask import Flask, render_template
from food_inventory.blueprint import food_inventory_bp

import os
print("CWD:", os.getcwd())
print("TEMPLATE_DIR:", os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates'))

TEMPLATE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates')
print(f"[DEBUG] TEMPLATE_DIR: {TEMPLATE_DIR}")
app = Flask(__name__, template_folder=TEMPLATE_DIR)

# Register the food_inventory blueprint under /food_inventory
app.register_blueprint(food_inventory_bp, url_prefix='/food_inventory')

@app.route('/')
def portal_index():
    """Portal welcome page with links to projects."""
    return render_template('portal_welcome.html')

if __name__ == '__main__':
    app.run(debug=True)

# Ensure current_user is available in all templates
from flask_login import current_user
@app.context_processor
def inject_user():
    return dict(current_user=current_user)
