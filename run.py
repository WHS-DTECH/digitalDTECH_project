from flask import Flask, render_template
from food_inventory.blueprint import food_inventory_bp

app = Flask(__name__, template_folder="maintemplates")

# Register the food_inventory blueprint under /food_inventory
app.register_blueprint(food_inventory_bp, url_prefix='/food_inventory')

@app.route('/')
def portal_index():
    """Portal welcome page with links to projects."""
    return render_template('portal_welcome.html')

if __name__ == '__main__':
    app.run(debug=True)
