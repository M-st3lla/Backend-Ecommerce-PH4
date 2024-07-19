from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from flask_migrate import Migrate
import os
from config import Config
from auth import auth_bp
from flask_jwt_extended import JWTManager
from extensions import db,bcrypt

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config.from_object(Config)
app.register_blueprint(auth_bp)
jwt = JWTManager(app)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "app.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Disable modification tracking
db.init_app(app)
bcrypt.init_app(app)
migrate = Migrate(app, db)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Define the Order model
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    total_price = db.Column(db.Float)  # Ensure this is FLOAT and NOT NULL
    payment_method = db.Column(db.String(50), nullable=False)
    order_items = db.relationship('OrderItem', backref='order', lazy=True)

    def __repr__(self):
        return f'<Order {self.id}>'

# Define the OrderItem model
class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return f'<OrderItem {self.id}>'

# Create database tables
with app.app_context():
    db.create_all()

# Routes
@app.route('/create_order', methods=['POST'])
def create_order():
    try:
        data = request.json
        app.logger.debug(f'Received data: {data}')

        # Validate required parameters
        required_params = ['name', 'email', 'address', 'payment_method', 'items']
        for param in required_params:
            if param not in data:
                return jsonify({'error': f'Missing required parameter: {param}'}), 400

        # Ensure total_price is a valid float
        try:
            total_price = float(data['total_price'])
        except ValueError:
            return jsonify({'error': 'Invalid total_price format'}), 400

        # Ensure items is a list of objects with the correct structure
        if not isinstance(data['items'], list):
            return jsonify({'error': 'Items should be a list'}), 400
        
        for item in data['items']:
            if not all(k in item for k in ['name', 'price', 'quantity', 'description']):
                return jsonify({'error': 'Each item must include name, price, quantity, and description'}), 400
            try:
                price = float(item['price'])
            except ValueError:
                return jsonify({'error': f'Invalid price format for item {item["name"]}'}), 400

        # Create new Order
        new_order = Order(
            name=data['name'],
            email=data['email'],
            address=data['address'],
            total_price=total_price,
            payment_method=data['payment_method']
        )

        for item in data['items']:
            order_item = OrderItem(
                name=item['name'],
                price=float(item['price']),
                quantity=item['quantity'],
                description=item['description'],
                order=new_order
            )
            db.session.add(order_item)

        db.session.add(new_order)
        db.session.commit()

        return jsonify({
            'message': 'Order created successfully',
            'order_id': new_order.id,
            'name': new_order.name,
            'email': new_order.email,
            'address': new_order.address,
            'total_price': new_order.total_price,
            'payment_method': new_order.payment_method,
            'items': [{
                'name': item.name,
                'price': item.price,
                'quantity': item.quantity,
                'description': item.description
            } for item in new_order.order_items]
        }), 200

    except KeyError as e:
        error_message = f'Missing required parameter: {str(e)}'
        app.logger.error(f'KeyError: {error_message}')
        return jsonify({'error': error_message}), 400

    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Exception: {str(e)}')
        return jsonify({'error': str(e)}), 500


@app.route('/orders', methods=['GET'])
def get_orders():
    try:
        orders = Order.query.all()
        formatted_orders = []
        for order in orders:
            order_data = {
                'id': order.id,
                'name': order.name,
                'email': order.email,
                'address': order.address,
                'total_price': order.total_price,
                'payment_method': order.payment_method,
                'items': [{
                    'name': item.name,
                    'price': item.price,
                    'quantity': item.quantity,
                    'description': item.description
                } for item in order.order_items]
            }
            formatted_orders.append(order_data)

        return jsonify({'orders': formatted_orders}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(port=5555)
