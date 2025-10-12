from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from functools import wraps
import os, cloudinary, cloudinary.uploader
import logging
import secrets
import hashlib
import requests
import json
import math
from datetime import datetime, timedelta

# Géolocalisation
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

# Configuration
ADMIN_PASSWORD_HASH = hashlib.sha256(os.environ.get('ADMIN_PASSWORD', 'changeme123').encode()).hexdigest()
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('BOT_TOKEN') or os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_ADMIN_ID = os.environ.get('TELEGRAM_ADMIN_ID') or os.environ.get('ADMIN_ID')
ADMIN_ADDRESS = os.environ.get('ADMIN_ADDRESS', 'Chamonix-Mont-Blanc, France')
BACKGROUND_IMAGE = os.environ.get('BACKGROUND_URL') or os.environ.get('BACKGROUND_IMAGE', 'https://res.cloudinary.com/dfhrrtzsd/image/upload/v1760118433/ChatGPT_Image_8_oct._2025_03_01_21_zm5zfy.png')

limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["200 per day", "50 per hour"], storage_uri="memory://")

admin_tokens = {}
failed_login_attempts = {}

# Configuration Cloudinary
try:
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME') or os.environ.get('CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY') or os.environ.get('CLOUD_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET') or os.environ.get('CLOUD_API_SECRET'),
        secure=True
    )
    logger.warning("✅ Cloudinary configuré")
except Exception as e:
    logger.error(f"❌ Erreur Cloudinary: {e}")

PRODUCTS_FILE = 'products.json'
ORDERS_FILE = 'orders.json'
FRAIS_POSTAL = 10

def calculate_delivery_fee(delivery_type: str, distance: float = 0, subtotal: float = 0) -> float:
    if delivery_type == "postal":
        return FRAIS_POSTAL
    elif delivery_type == "express":
        base_fee = (distance * 2) + (subtotal * 0.03)
        return math.ceil(base_fee / 10) * 10
    return 0

def load_json_file(filename, default=[]):
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
            logger.error(f"Erreur lecture {filename}: {e}")
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
        logger.error(f"Erreur sauvegarde {filename}: {e}")

def ensure_valid_json_files():
    for filename in [PRODUCTS_FILE, ORDERS_FILE]:
        if not os.path.exists(filename):
            save_json_file(filename, [])

logger.warning("🔍 Vérification des fichiers JSON...")
ensure_valid_json_files()
logger.warning("✅ Vérification terminée")

logger.warning("=" * 50)
logger.warning("🔧 CONFIGURATION DE L'APPLICATION")
logger.warning("=" * 50)
logger.warning(f"📱 TELEGRAM_BOT_TOKEN: {'✅ Configuré' if TELEGRAM_BOT_TOKEN else '❌ Manquant'}")
logger.warning(f"👤 TELEGRAM_ADMIN_ID: {'✅ Configuré (' + TELEGRAM_ADMIN_ID + ')' if TELEGRAM_ADMIN_ID else '❌ Manquant'}")
logger.warning(f"📍 ADMIN_ADDRESS: {ADMIN_ADDRESS}")
logger.warning("=" * 50)

products = load_json_file(PRODUCTS_FILE)
orders = load_json_file(ORDERS_FILE)

def send_telegram_notification(order_data):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_ID:
        logger.error("❌ Configuration Telegram manquante")
        return False
    
    try:
        logger.warning(f"📤 Envoi notification Telegram pour commande #{order_data['order_number']}")
        
        message = f"""🆕 *NOUVELLE COMMANDE WEB #{order_data['order_number']}*

👤 *Client:*
• Nom: {order_data['customer_name']}
• Contact: {order_data['customer_contact']}
• 📍 Adresse: {order_data.get('customer_address', '')}

📦 *Articles:*
"""
        
        for item in order_data['items']:
            message += f"• {item['product_name']} x{item['quantity']} = {item['subtotal']:.2f}€\n"
        
        shipping_type = order_data.get('shipping_type', 'N/A')
        delivery_fee = order_data.get('delivery_fee', 0)
        
        message += f"\n💵 *Sous-total:* {order_data['subtotal']:.2f}€\n"
        
        if shipping_type == 'postal':
            message += f"📦 *Livraison:* ✉️ Postale 48-72H (+{FRAIS_POSTAL}€)\n"
        elif shipping_type == 'express':
            message += f"📦 *Livraison:* ⚡ Express\n💶 *Frais:* {delivery_fee:.2f}€\n"
        
        message += f"\n💰 *TOTAL: {order_data['total']:.2f}€*\n"
        
        if order_data.get('customer_notes'):
            message += f"\n📝 *Notes:* {order_data['customer_notes']}\n"
        
        message += f"\n📅 {order_data['created_at']}"
        
        keyboard = {
            "inline_keyboard": [[
                {
                    "text": "✅ Valider la livraison",
                    "callback_data": f"webapp_validate_{order_data['id']}"
                }
            ]]
        }
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_ADMIN_ID,
            "text": message,
            "parse_mode": "Markdown",
            "reply_markup": json.dumps(keyboard)
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.warning(f"✅ Notification Telegram envoyée")
            return True
        else:
            logger.error(f"❌ Erreur Telegram: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur envoi Telegram: {str(e)}")
        return False

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
    return wrapped

@app.route('/')
def index():
    try:
        html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Carte du Pirate</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: url('{BACKGROUND_IMAGE}') center center fixed;
  background-size: cover;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  position: relative;
}}
body::before {{
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 1;
}}
.container {{
  text-align: center;
  color: white;
  max-width: 800px;
  position: relative;
  z-index: 2;
}}
h1 {{
  font-size: 3.5em;
  margin-bottom: 30px;
  text-shadow: 4px 4px 8px rgba(0,0,0,0.8);
}}
.subtitle {{
  font-size: 1.3em;
  margin-bottom: 40px;
  opacity: 0.95;
  text-shadow: 2px 2px 4px rgba(0,0,0,0.8);
}}
.btn {{
  display: inline-block;
  padding: 20px 50px;
  font-size: 1.5em;
  background: linear-gradient(45deg, #d4af37, #f4e5a1);
  border: 3px solid #8b7220;
  border-radius: 15px;
  color: #2c1810;
  text-decoration: none;
  font-weight: bold;
  transition: all 0.3s ease;
  margin: 10px;
  box-shadow: 0 5px 15px rgba(0,0,0,0.5);
}}
.btn:hover {{
  transform: scale(1.05) translateY(-5px);
  box-shadow: 0 15px 40px rgba(212, 175, 55, 0.6);
}}
</style>
</head>
<body>
<div class="container">
  <h1>🏴‍☠️ Carte du Pirate 🏴‍☠️</h1>
  <p class="subtitle">Votre boutique de trésors en ligne</p>
  <a href="/catalogue" class="btn">📦 Catalogue & Commandes</a>
</div>
</body>
</html>'''
        return html, 200
    except Exception as e:
        logger.error(f"Erreur route index: {e}")
        return "Erreur serveur", 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200

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
            return jsonify({'error': 'Trop de tentatives. Compte bloqué 15 minutes.'}), 429
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
            if admin_tokens[token]['ip'] == ip:
                if datetime.now() <= admin_tokens[token]['expires']:
                    is_admin = True
                else:
                    del admin_tokens[token]
            else:
                del admin_tokens[token]
        return jsonify({'admin': is_admin}), 200
    except:
        return jsonify({'admin': False}), 200

@app.route('/api/upload', methods=['POST'])
@require_admin
@limiter.limit("10 per hour")
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier'}), 400
        file = request.files['file']
        file.seek(0, os.SEEK_END)
        file_length = file.tell()
        if file_length > 10 * 1024 * 1024:
            return jsonify({'error': 'Fichier trop gros (max 10MB)'}), 400
        file.seek(0)
        result = cloudinary.uploader.upload(file, resource_type='auto', folder='catalogue', timeout=60)
        return jsonify({'url': result.get('secure_url')}), 200
    except:
        return jsonify({'error': 'Erreur upload'}), 500

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
        return jsonify({'error': 'Erreur création'}), 500

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
        return jsonify({'error': 'Erreur modification'}), 500

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
        return jsonify({'error': 'Erreur suppression'}), 500

@app.route('/api/calculate-distance', methods=['POST'])
def calculate_distance():
    try:
        data = request.json or {}
        client_address = data.get('address', '').strip()
        
        if not client_address or len(client_address) < 15:
            return jsonify({'error': 'Adresse invalide (min 15 caractères)'}), 400
        
        if not GEOPY_AVAILABLE:
            return jsonify({'error': 'Service de géolocalisation non disponible'}), 503
        
        try:
            geolocator = Nominatim(user_agent="carte_du_pirate_webapp")
            
            location1 = geolocator.geocode(ADMIN_ADDRESS, timeout=10)
            location2 = geolocator.geocode(client_address, timeout=10)
            
            if not location1:
                return jsonify({'error': f'Adresse de départ introuvable'}), 400
            
            if not location2:
                return jsonify({'error': 'Adresse de livraison introuvable'}), 400
            
            coords1 = (location1.latitude, location1.longitude)
            coords2 = (location2.latitude, location2.longitude)
            
            distance = geodesic(coords1, coords2).kilometers
            distance_rounded = round(distance, 1)
            
            return jsonify({
                'success': True,
                'distance_km': distance_rounded,
                'from': ADMIN_ADDRESS,
                'to': client_address
            }), 200
            
        except Exception as e:
            logger.error(f"Erreur géolocalisation: {e}")
            return jsonify({'error': f'Erreur de géolocalisation'}), 500
        
    except Exception as e:
        logger.error(f"Erreur calcul distance: {e}")
        return jsonify({'error': 'Erreur serveur'}), 500

@app.route('/api/orders', methods=['POST'])
@limiter.limit("5 per hour")
def create_order():
    global orders
    try:
        data = request.json or {}
        
        logger.warning(f"📥 Nouvelle commande reçue")
        
        if not data.get('items') or len(data.get('items', [])) == 0:
            return jsonify({'error': 'Panier vide'}), 400
        if not data.get('customer_name') or not data.get('customer_contact'):
            return jsonify({'error': 'Nom et contact requis'}), 400
        
        total = 0
        order_items = []
        for item in data['items']:
            product = next((p for p in products if p['id'] == item['product_id']), None)
            if not product:
                return jsonify({'error': f'Produit {item["product_id"]} introuvable'}), 404
            if product['stock'] < item['quantity']:
                return jsonify({'error': f'Stock insuffisant pour {product["name"]}'}), 400
            item_total = product['price'] * item['quantity']
            total += item_total
            order_items.append({
                'product_id': product['id'],
                'product_name': product['name'],
                'price': product['price'],
                'quantity': item['quantity'],
                'subtotal': item_total
            })
        
        shipping_type = data.get('shipping_type', 'postal')
        distance = float(data.get('distance_km', 0))
        delivery_fee = calculate_delivery_fee(shipping_type, distance, total)
        final_total = total + delivery_fee
        
        order_id = max([o['id'] for o in orders]) + 1 if orders else 1
        new_order = {
            'id': order_id,
            'order_number': f"CMD-{order_id:05d}",
            'customer_name': data['customer_name'],
            'customer_contact': data['customer_contact'],
            'customer_address': data.get('customer_address', ''),
            'customer_notes': data.get('customer_notes', ''),
            'items': order_items,
            'subtotal': total,
            'shipping_type': shipping_type,
            'distance_km': distance,
            'delivery_fee': delivery_fee,
            'total': final_total,
            'status': 'pending',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        orders.append(new_order)
        save_json_file(ORDERS_FILE, orders)
        
        logger.warning(f"✅ Commande #{new_order['order_number']} créée")
        
        telegram_sent = send_telegram_notification(new_order)
        
        if telegram_sent:
            logger.warning(f"✅ Notification Telegram envoyée")
        else:
            logger.error(f"❌ Échec notification Telegram")
        
        return jsonify({'success': True, 'order': new_order}), 201
        
    except Exception as e:
        logger.error(f"❌ Erreur création commande: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Erreur serveur'}), 500

@app.route('/api/admin/orders', methods=['GET'])
@require_admin
def get_orders():
    try:
        return jsonify(orders), 200
    except:
        return jsonify([]), 200

@app.route('/api/admin/orders/<int:order_id>', methods=['PUT'])
@require_admin
def update_order_status(order_id):
    try:
        data = request.json or {}
        new_status = data.get('status')
        if new_status not in ['pending', 'confirmed', 'preparing', 'ready', 'delivered', 'cancelled']:
            return jsonify({'error': 'Statut invalide'}), 400
        for order in orders:
            if order['id'] == order_id:
                order['status'] = new_status
                order['updated_at'] = datetime.now().isoformat()
                save_json_file(ORDERS_FILE, orders)
                return jsonify(order)
        return jsonify({'error': 'Commande non trouvée'}), 404
    except:
        return jsonify({'error': 'Erreur modification'}), 500

@app.route('/api/telegram/webhook', methods=['POST'])
def telegram_webhook():
    try:
        data = request.json
        logger.warning(f"📨 Webhook Telegram reçu")
        
        if 'callback_query' in data:
            callback_data = data['callback_query']['data']
            callback_id = data['callback_query']['id']
            
            # ÉTAPE 1: Répondre IMMÉDIATEMENT au callback
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                answer_response = requests.post(url, json={
                    "callback_query_id": callback_id,
                    "text": "⏳ Traitement..."
                }, timeout=5)
                logger.warning(f"✅ Callback answer envoyé ({answer_response.status_code})")
            except Exception as e:
                logger.error(f"❌ Erreur answer callback: {e}")
            
            # ÉTAPE 2: Traiter la commande
            if callback_data.startswith('webapp_validate_'):
                try:
                    order_id = int(callback_data.split('_')[2])
                    logger.warning(f"🔄 Validation commande #{order_id}")
                    
                    order_found = False
                    for order in orders:
                        if order['id'] == order_id:
                            order['status'] = 'delivered'
                            order['delivered_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            order_found = True
                            logger.warning(f"✅ Commande #{order_id} livrée")
                            break
                    
                    if order_found:
                        save_json_file(ORDERS_FILE, orders)
                        
                        # ÉTAPE 3: Éditer le message
                        try:
                            message_id = data['callback_query']['message']['message_id']
                            chat_id = data['callback_query']['message']['chat']['id']
                            original_text = data['callback_query']['message']['text']
                            
                            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
                            edit_response = requests.post(url, json={
                                "chat_id": chat_id,
                                "message_id": message_id,
                                "text": original_text + "\n\n✅ *COMMANDE LIVRÉE*",
                                "parse_mode": "Markdown"
                            }, timeout=5)
                            logger.warning(f"✅ Message mis à jour ({edit_response.status_code})")
                        except Exception as e:
                            logger.error(f"❌ Erreur édition message: {e}")
                    else:
                        logger.error(f"❌ Commande #{order_id} non trouvée")
                        
                except Exception as e:
                    logger.error(f"❌ Erreur traitement: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
        
        return jsonify({'ok': True}), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook: {e}")
        return jsonify({'ok': True}), 200

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
        logger.error(f"Erreur route catalogue: {e}")
        return "Erreur serveur", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.warning(f"Démarrage sur le port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
