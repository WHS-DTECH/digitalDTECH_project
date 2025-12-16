
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../food_inventory'))
from flask import Flask, render_template
from app import app as food_inventory_app

app = Flask(__name__, template_folder="maintemplates")

# Import and register blueprints for each project here in the future
# from projects.food_inventory.app import food_inventory_bp
# app.register_blueprint(food_inventory_bp, url_prefix='/food_inventory')

@app.route('/')
def welcome():
    return render_template('welcome.html')

# Route to Food Inventory System at /recbk
@app.route('/recbk')
def recbk():
    # Call the index view of the food_inventory app
    return food_inventory_app.view_functions['index']()

if __name__ == '__main__':
    app.run(debug=True)
