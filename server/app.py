from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from flask_migrate import Migrate
import os
from config import Config
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from extensions import db, bcrypt
from flask_jwt_extended import decode_token
from auth import auth_bp
from models import User, Order, OrderItem, Sales, Review
from alembic import op
import sqlalchemy as sa

# Initialize the Flask application
app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "http://localhost:3000"}})

# Configure the app
app.config.from_object(Config)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "app.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Disable modification tracking

# Initialize extensions
jwt = JWTManager(app)
db.init_app(app)
bcrypt.init_app(app)
migrate = Migrate(app, db)

# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')

# Create database tables
with app.app_context():
    db.create_all()

def upgrade():
    op.add_column('user', sa.Column('created_at', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('user', 'created_at')

logging.basicConfig(level=logging.DEBUG)

# Routes
@app.route('/create_order', methods=['POST'])
def create_order():
    try:
        data = request.get_json()

        app.logger.debug(f'Received order data: {data}')

        if not data.get('name') or not data.get('email') or not data.get('address'):
            return jsonify({'error': 'Missing required fields'}), 400

        new_order = Order(
            name=data['name'],
            email=data['email'],
            address=data['address'],
            total_price=convert_price(data['total_price']),
            payment_method=data['payment_method']
        )

        for item in data.get('items', []):
            if not item.get('name') or not item.get('price') or not item.get('quantity') or not item.get('description'):
                return jsonify({'error': 'Missing item details'}), 400

            item_price = convert_price(item['price'])
            app.logger.debug(f'Item price after conversion: {item_price}')
            if item_price is None:
                return jsonify({'error': 'Invalid price value'}), 400

            order_item = OrderItem(
                name=item['name'],
                price=item_price,
                quantity=item['quantity'],
                description=item['description'],
                order=new_order
            )
            db.session.add(order_item)

        db.session.add(new_order)
        db.session.commit()

        return jsonify({
            'message': 'Order created successfully',
            'order': {
                'id': new_order.id,
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
            }
        }), 201

    except KeyError as e:
        error_message = f'Missing required parameter: {str(e)}'
        app.logger.error(f'KeyError: {error_message}')
        return jsonify({'error': error_message}), 400

    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Exception: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/verify_token', methods=['GET'])
@jwt_required()
def verify_token():
    token = request.headers.get('Authorization').split()[1]
    decoded_token = decode_token(token)
    return jsonify(decoded_token), 200

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
        app.logger.error(f'Exception: {str(e)}')
        return jsonify({'error': str(e)}), 500
    
@app.route('/reviews', methods=['POST'])
@jwt_required()
def create_review():
    identity = get_jwt_identity()
    user_id = identity.get('id')

    if user_id is None:
        return jsonify({'error': 'User ID not found in token'}), 401

    data = request.get_json()

    try:
        order_item_id = data['order_item_id']
        rating = int(data['rating'])  # Convert to integer
        comment = data.get('comment')

        if not (1 <= rating <= 5):
            return jsonify({'error': 'Rating must be between 1 and 5'}), 400

        new_review = Review(
            user_id=user_id,
            order_item_id=order_item_id,
            rating=rating,  # Ensure rating is an integer
            comment=comment
        )
        db.session.add(new_review)
        db.session.commit()

        return jsonify({'message': 'Review created successfully', 'review': {
            'id': new_review.id,
            'order_item_id': new_review.order_item_id,
            'rating': new_review.rating,
            'comment': new_review.comment,
            'timestamp': new_review.timestamp
        }}), 201

    except KeyError as e:
        return jsonify({'error': f'Missing required parameter: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

    

@app.route('/reviews/<int:order_item_id>', methods=['GET'])
def get_reviews(order_item_id):
    reviews = Review.query.filter_by(order_item_id=order_item_id).all()
    reviews_data = [{
        'id': review.id,
        'rating': review.rating,
        'comment': review.comment,
        'timestamp': review.timestamp
    } for review in reviews]
    return jsonify({'reviews': reviews_data})

@app.route('/sales', methods=['GET'])
def get_sales():
    try:
        sales_data = Sales.query.all()
        if not sales_data:
            return jsonify({"message": "No sales data available"}), 404
        return jsonify([sale.to_dict() for sale in sales_data]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.before_request
def before_request():
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        headers = None
        if hasattr(response, 'headers'):
            headers = response.headers
        elif hasattr(response, 'getheaders'):
            headers = response.getheaders()
        headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'
        headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS, PUT, DELETE'
        headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        headers['Access-Control-Allow-Credentials'] = 'true'
        return response


def convert_price(price_str):
    if isinstance(price_str, str):
        price_str = price_str.replace(',', '')
        try:
            return float(price_str)
        except ValueError as e:
            app.logger.error(f"Error converting price: {e}, Input price: {price_str}")
            return None
    elif isinstance(price_str, (int, float)):
        return float(price_str)
    else:
        app.logger.error(f"Invalid price type: {type(price_str)}")
        return None


if __name__ == '__main__':
    app.run(port=5555)
