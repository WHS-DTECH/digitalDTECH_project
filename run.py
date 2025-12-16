from flask import Flask, render_template

app = Flask(__name__)

# Import and register blueprints for each project here in the future
# from projects.food_inventory.app import food_inventory_bp
# app.register_blueprint(food_inventory_bp, url_prefix='/food_inventory')

@app.route('/')
def welcome():
    return render_template('welcome.html')

if __name__ == '__main__':
    app.run(debug=True)
