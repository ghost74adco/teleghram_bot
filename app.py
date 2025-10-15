from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from functools import wraps
import os
import cloudinary
import cloudinary.uploader
import logging
import secrets
import hashlib
import json
import math
from datetime import datetime, timedelta

try:
    from geopy.geocoders import Nominatim
    from geopy.distance import geodesic
    GEOPY_AVAILABLE = True
except ImportError:
    GEOPY_AVAILABLE = False

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

load_dotenv('infos.env')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True, origins=['*'])

ADMIN_PASSWORD_HASH = hashlib.sha256(os.environ.get('ADMIN_PASSWORD', 'changeme123').encode()).hexdigest()
ADMIN_ADDRESS = os.environ.get('ADMIN_ADDRESS', '858 Rte du Chef Lieu, 74250 Fillinges')
BACKGROUND_IMAGE = os.environ.get('BACKGROUND_URL') or os.environ.get('BACKGROUND_IMAGE', 'https://res.cloudinary.com/dfhrrtzsd/image/upload/v1760118433/ChatGPT_Image_8_oct._2025_03_01_21_zm5zfy.png')

limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["200 per day", "50 per hour"], storage_uri="memory://")

admin_tokens = {}
failed_login_attempts = {}

try:
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME') or os.environ.get('CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY') or os.environ.get('CLOUD_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET') or os.environ.get('CLOUD_API_SECRET'),
        secure=True
    )
    logger.warning("✅ Cloudinary configuré")
except Exception as e:
    logger.error("❌ Erreur Cloudinary: " + str(e))

PRODUCTS_FILE = 'products.json'

def load_json_file(filename, default=None):
    if default is None:
        default = []
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    save_json_file(filename, default)
                    return default
                data = json.loads(content)
                return data if isinstance(data, list) else default
        except Exception as e:
            logger.error("Erreur lecture " + filename + ": " + str(e))
            save_json_file(filename, default)
            return default
    else:
        save_json_file(filename, default)
        return default

def save_json_file(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Erreur sauvegarde " + filename + ": " + str(e))

def ensure_valid_json_files():
    if not os.path.exists(PRODUCTS_FILE):
        save_json_file(PRODUCTS_FILE, [])

logger.warning("🔍 Vérification des fichiers JSON...")
ensure_valid_json_files()
logger.warning("✅ Vérification terminée")

logger.warning("=" * 50)
logger.warning("🔧 CONFIGURATION DE L'APPLICATION")
logger.warning("=" * 50)
logger.warning("🏠 ADMIN_ADDRESS: " + ADMIN_ADDRESS)
logger.warning("=" * 50)

products = load_json_file(PRODUCTS_FILE)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_rate_limit(ip):
    if ip not in failed_login_attempts:
        failed_login_attempts[ip] = {'count': 0, 'blocked_until': None}
    attempt = failed_login_attempts[ip]
    if attempt['blocked_until']:
        if datetime.now() < attempt['blocked_until']:
            return False, "Trop de tentatives. Réessayez dans 15 minutes."
        else:
            attempt['count'] = 0
            attempt['blocked_until'] = None
    return True, None

def register_failed_attempt(ip):
    if ip not in failed_login_attempts:
        failed_login_attempts[ip] = {'count': 0, 'blocked_until': None}
    failed_login_attempts[ip]['count'] += 1
    if failed_login_attempts[ip]['count'] >= 5:
        failed_login_attempts[ip]['blocked_until'] = datetime.now() + timedelta(minutes=15)
        return True
    return False

def require_admin(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        token = request.headers.get('X-Admin-Token')
        if not token or token not in admin_tokens:
            return jsonify({'error': 'Non autorisé'}), 403
        token_data = admin_tokens[token]
        if datetime.now() > token_data['expires']:
            del admin_tokens[token]
            return jsonify({'error': 'Session expirée'}), 403
        return f(*args, **kwargs)
    wrapped.__name__ = f.__name__
    return wrapped

@app.route('/')
def index():
    try:
        html = '<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">'
        html += '<title>Carte du Pirate</title>'
        html += '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        html += '<style>* { margin: 0; padding: 0; box-sizing: border-box; }'
        html += 'body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;'
        html += 'background: url(' + BACKGROUND_IMAGE + ') center center fixed;'
        html += 'background-size: cover; min-height: 100vh; display: flex;'
        html += 'align-items: center; justify-content: center; padding: 20px; position: relative; }'
        html += 'body::before { content: ""; position: absolute; top: 0; left: 0; right: 0; bottom: 0;'
        html += 'background: rgba(0, 0, 0, 0.4); z-index: 1; }'
        html += '.container { text-align: center; color: white; max-width: 800px;'
        html += 'position: relative; z-index: 2; }'
        html += 'h1 { font-size: 3.5em; margin-bottom: 30px;'
        html += 'text-shadow: 4px 4px 8px rgba(0,0,0,0.8); }'
        html += '.subtitle { font-size: 1.3em; margin-bottom: 40px; opacity: 0.95;'
        html += 'text-shadow: 2px 2px 4px rgba(0,0,0,0.8); }'
        html += '.btn { display: inline-block; padding: 20px 50px; font-size: 1.5em;'
        html += 'background: linear-gradient(45deg, #d4af37, #f4e5a1);'
        html += 'border: 3px solid #8b7220; border-radius: 15px; color: #2c1810;'
        html += 'text-decoration: none; font-weight: bold; transition: all 0.3s ease;'
        html += 'margin: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.5); }'
        html += '.btn:hover { transform: scale(1.05) translateY(-5px);'
        html += 'box-shadow: 0 15px 40px rgba(212, 175, 55, 0.6); }'
        html += '</style></head><body><div class="container">'
        html += '<h1>🏴‍☠️ Carte du Pirate 🏴‍☠️</h1>'
        html += '<p class="subtitle">Catalogue de consultation</p>'
        html += '<a href="/catalogue" class="btn">📦 Voir le Catalogue</a>'
        html += '</div></body></html>'
        return html, 200
    except Exception as e:
        logger.error("Erreur route index: " + str(e))
        return "Erreur serveur", 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200

@app.route('/catalogue')
def catalogue():
    try:
        with open('catalogue.html', 'r', encoding='utf-8') as f:
            html = f.read()
            html = html.replace('{{BACKGROUND_IMAGE}}', BACKGROUND_IMAGE)
            return html, 200
    except FileNotFoundError:
        return "Fichier catalogue.html introuvable", 404
    except Exception as e:
        logger.error("Erreur route catalogue: " + str(e))
        return "Erreur serveur", 500

@app.route('/api/admin/login', methods=['POST'])
@limiter.limit("5 per 15 minutes")
def api_login():
    try:
        ip = get_remote_address()
        allowed, message = check_rate_limit(ip)
        if not allowed:
            return jsonify({'error': message}), 429
        data = request.json or {}
        password_hash = hash_password(data.get('password', ''))
        if password_hash == ADMIN_PASSWORD_HASH:
            token = secrets.token_urlsafe(32)
            admin_tokens[token] = {
                'created': datetime.now(),
                'expires': datetime.now() + timedelta(hours=12),
                'ip': ip
            }
            if ip in failed_login_attempts:
                failed_login_attempts[ip]['count'] = 0
            return jsonify({'success': True, 'token': token})
        blocked = register_failed_attempt(ip)
        if blocked:
            return jsonify({'error': 'Trop de tentatives'}), 429
        return jsonify({'error': 'Mot de passe incorrect'}), 403
    except Exception as e:
        return jsonify({'error': 'Erreur serveur'}), 500

@app.route('/api/admin/logout', methods=['POST'])
def api_logout():
    try:
        token = request.headers.get('X-Admin-Token')
        if token and token in admin_tokens:
            del admin_tokens[token]
        return jsonify({'success': True})
    except:
        return jsonify({'success': False}), 500

@app.route('/api/admin/check', methods=['GET'])
def api_check_admin():
    try:
        token = request.headers.get('X-Admin-Token')
        ip = get_remote_address()
        is_admin = False
        if token and token in admin_tokens:
            token_ip = admin_tokens[token]['ip']
            token_expires = admin_tokens[token]['expires']
            if token_ip == ip and datetime.now() <= token_expires:
                is_admin = True
            else:
                del admin_tokens[token]
        return jsonify({'admin': is_admin}), 200
    except:
        return jsonify({'admin': False}), 200

@app.route('/api/products', methods=['GET'])
def get_products():
    try:
        return jsonify(products), 200
    except:
        return jsonify([]), 200

@app.route('/api/admin/products', methods=['POST'])
@require_admin
def add_product():
    global products
    try:
        data = request.json or {}
        if not data.get('name') or not data.get('price'):
            return jsonify({'error': 'Nom et prix requis'}), 400
        new_product = {
            "id": max([p["id"] for p in products]) + 1 if products else 1,
            "name": data.get("name"),
            "price": float(data.get("price", 0)),
            "description": data.get("description", ""),
            "category": data.get("category", ""),
            "image_url": data.get("image_url", ""),
            "video_url": data.get("video_url", ""),
            "stock": int(data.get("stock", 0))
        }
        products.append(new_product)
        save_json_file(PRODUCTS_FILE, products)
        return jsonify(new_product), 201
    except:
        return jsonify({'error': 'Erreur'}), 500

@app.route('/api/admin/products/<int:pid>', methods=['PUT'])
@require_admin
def update_product(pid):
    try:
        data = request.json or {}
        for p in products:
            if p['id'] == pid:
                p.update({
                    "name": data.get("name", p["name"]),
                    "price": float(data.get("price", p["price"])),
                    "description": data.get("description", p["description"]),
                    "category": data.get("category", p["category"]),
                    "image_url": data.get("image_url", p.get("image_url", "")),
                    "video_url": data.get("video_url", p.get("video_url", "")),
                    "stock": int(data.get("stock", p["stock"]))
                })
                save_json_file(PRODUCTS_FILE, products)
                return jsonify(p)
        return jsonify({'error': 'Produit non trouvé'}), 404
    except:
        return jsonify({'error': 'Erreur'}), 500

@app.route('/api/admin/products/<int:pid>', methods=['DELETE'])
@require_admin
def delete_product(pid):
    global products
    try:
        before = len(products)
        products = [p for p in products if p['id'] != pid]
        if len(products) < before:
            save_json_file(PRODUCTS_FILE, products)
            return jsonify({'success': True})
        return jsonify({'error': 'Produit non trouvé'}), 404
    except:
        return jsonify({'error': 'Erreur'}), 500

@app.route('/api/upload', methods=['POST'])
@require_admin
@limiter.limit("10 per hour")
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'Nom de fichier vide'}), 400
        
        file.seek(0, os.SEEK_END)
        file_length = file.tell()
        if file_length > 10 * 1024 * 1024:
            return jsonify({'error': 'Fichier trop volumineux (max 10 MB)'}), 400
        
        file.seek(0)
        
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'avi'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'Type de fichier non autorisé'}), 400
        
        filename_log = file.filename
        logger.warning("📤 Upload de " + filename_log + " vers Cloudinary...")
        
        resource_type = 'video' if file_ext in {'mp4', 'mov', 'avi'} else 'image'
        
        result = cloudinary.uploader.upload(
            file,
            resource_type=resource_type,
            folder='carte_du_pirate',
            allowed_formats=list(allowed_extensions)
        )
        
        url = result.get('secure_url')
        logger.warning("✅ Upload réussi: " + url)
        
        return jsonify({
            'success': True,
            'url': url,
            'public_id': result.get('public_id'),
            'resource_type': resource_type
        }), 200
        
    except Exception as e:
        error_msg = str(e)
        logger.error("❌ Erreur upload: " + str(e))
        return jsonify({'error': 'Erreur upload: ' + error_msg}), 500

@app.route('/api/calculate-distance', methods=['POST'])
def calculate_distance():
    if not GEOPY_AVAILABLE:
        return jsonify({'error': 'Service de géolocalisation non disponible'}), 503
    
    try:
        data = request.json or {}
        customer_address = data.get('address')
        
        if not customer_address:
            return jsonify({'error': 'Adresse requise'}), 400
        
        geolocator = Nominatim(user_agent="carte_du_pirate")
        
        admin_location = geolocator.geocode(ADMIN_ADDRESS)
        if not admin_location:
            return jsonify({'error': 'Impossible de localiser adresse admin'}), 500
        
        customer_location = geolocator.geocode(customer_address)
        if not customer_location:
            return jsonify({'error': 'Adresse client introuvable'}), 404
        
        admin_coords = (admin_location.latitude, admin_location.longitude)
        customer_coords = (customer_location.latitude, customer_location.longitude)
        distance_km = geodesic(admin_coords, customer_coords).kilometers
        
        return jsonify({
            'success': True,
            'distance_km': round(distance_km, 2),
            'customer_address_formatted': customer_location.address
        }), 200
        
    except Exception as e:
        logger.error("❌ Erreur calcul distance: " + str(e))
        return jsonify({'error': 'Erreur calcul distance'}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Route introuvable'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error("Erreur 500: " + str(e))
    return jsonify({'error': 'Erreur serveur interne'}), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Trop de requêtes, réessayez plus tard'}), 429

if __name__ == '__main__':
    logger.warning("=" * 70)
    logger.warning("🚀 DÉMARRAGE DE L'APPLICATION")
    logger.warning("=" * 70)
    logger.warning("✅ Serveur prêt!")
    logger.warning("=" * 70)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
