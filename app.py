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
import asyncio
from telegram import Update

# Google Sheets
try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False

# Géolocalisation
try:
    from geopy.geocoders import Nominatim
    from geopy.distance import geodesic
    GEOPY_AVAILABLE = True
except ImportError:
    GEOPY_AVAILABLE = False

# Configuration logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Charger variables d'environnement
load_dotenv('infos.env')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True, origins=['*'])

# Configuration
ADMIN_PASSWORD_HASH = hashlib.sha256(os.environ.get('ADMIN_PASSWORD', 'changeme123').encode()).hexdigest()
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('BOT_TOKEN') or os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_ADMIN_ID = os.environ.get('TELEGRAM_ADMIN_ID') or os.environ.get('ADMIN_ID')
ADMIN_ADDRESS = os.environ.get('ADMIN_ADDRESS', '858 Rte du Chef Lieu, 74250 Fillinges')
BACKGROUND_IMAGE = os.environ.get('BACKGROUND_URL') or os.environ.get('BACKGROUND_IMAGE', 'https://res.cloudinary.com/dfhrrtzsd/image/upload/v1760118433/ChatGPT_Image_8_oct._2025_03_01_21_zm5zfy.png')

# Google Sheets
GOOGLE_SHEETS_ENABLED = False
SPREADSHEET_ID = os.environ.get('GOOGLE_SPREADSHEET_ID', '')
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON', '')
sheets_service = None

limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["200 per day", "50 per hour"], storage_uri="memory://")

admin_tokens = {}
failed_login_attempts = {}

# Cloudinary
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
logger.warning(f"🏠 ADMIN_ADDRESS: {ADMIN_ADDRESS}")
logger.warning("=" * 50)

products = load_json_file(PRODUCTS_FILE)
orders = load_json_file(ORDERS_FILE)

# ==================== IMPORT DU BOT ====================
try:
    from bot import bot_application
    BOT_AVAILABLE = True
    logger.warning("✅ Bot Telegram importé avec succès")
except Exception as e:
    BOT_AVAILABLE = False
    logger.error(f"❌ Erreur import bot: {e}")

# ==================== GOOGLE SHEETS ====================
def init_google_sheets():
    global sheets_service, GOOGLE_SHEETS_ENABLED
    if not GOOGLE_SHEETS_AVAILABLE:
        logger.warning("⚠️ google-api-python-client non installé")
        return False
    if not SPREADSHEET_ID or not GOOGLE_CREDENTIALS_JSON:
        logger.warning("⚠️ Google Sheets non configuré")
        return False
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        credentials = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        sheets_service = build('sheets', 'v4', credentials=credentials)
        GOOGLE_SHEETS_ENABLED = True
        logger.warning("✅ Google Sheets API initialisée")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur Google Sheets: {e}")
        return False

logger.warning("📊 Initialisation Google Sheets...")
init_google_sheets()
logger.warning("=" * 50)

# ==================== UTILITY FUNCTIONS ====================
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
        return jsonify({'error': 'Erreur'}), 500

# ==================== UPLOAD ====================
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
        
        # Vérifier la taille du fichier
        file.seek(0, os.SEEK_END)
        file_length = file.tell()
        if file_length > 10 * 1024 * 1024:
            return jsonify({'error': 'Fichier trop volumineux (max 10 MB)'}), 400
        
        file.seek(0)
        
        # Vérifier le type de fichier
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'avi'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'Type de fichier non autorisé'}), 400
        
        # Upload vers Cloudinary
        filename_log = file.filename
        logger.warning(f"📤 Upload de {filename_log} vers Cloudinary...")
        
        resource_type = 'video' if file_ext in {'mp4', 'mov', 'avi'} else 'image'
        
        result = cloudinary.uploader.upload(
            file,
            resource_type=resource_type,
            folder='carte_du_pirate',
            allowed_formats=list(allowed_extensions)
        )
        
        url = result.get('secure_url')
        logger.warning(f"✅ Upload réussi: {url}")
        
        return jsonify({
            'success': True,
            'url': url,
            'public_id': result.get('public_id'),
            'resource_type': resource_type
        }), 200
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Erreur upload: {e}")
        return jsonify({'error': f'Erreur upload: {error_msg}'}), 500

# ==================== GEOLOCALISATION ====================
@app.route('/api/calculate-distance', methods=['POST'])
def calculate_distance():
    """Calcule la distance entre l'adresse du client et l'admin"""
    if not GEOPY_AVAILABLE:
        return jsonify({'error': 'Service de géolocalisation non disponible'}), 503
    
    try:
        data = request.json or {}
        customer_address = data.get('address')
        
        if not customer_address:
            return jsonify({'error': 'Adresse requise'}), 400
        
        geolocator = Nominatim(user_agent="carte_du_pirate")
        
        # Géolocaliser l'adresse admin
        admin_location = geolocator.geocode(ADMIN_ADDRESS)
        if not admin_location:
            return jsonify({'error': 'Impossible de localiser l\'adresse admin'}), 500
        
        # Géolocaliser l'adresse client
        customer_location = geolocator.geocode(customer_address)
        if not customer_location:
            return jsonify({'error': 'Adresse client introuvable'}), 404
        
        # Calculer la distance
        admin_coords = (admin_location.latitude, admin_location.longitude)
        customer_coords = (customer_location.latitude, customer_location.longitude)
        distance_km = geodesic(admin_coords, customer_coords).kilometers
        
        return jsonify({
            'success': True,
            'distance_km': round(distance_km, 2),
            'customer_address_formatted': customer_location.address
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur calcul distance: {e}")
        return jsonify({'error': 'Erreur calcul distance'}), 500

# ==================== GOOGLE SHEETS SYNC ====================
@app.route('/api/admin/sync-sheets', methods=['POST'])
@require_admin
def sync_to_sheets():
    """Synchronise les commandes vers Google Sheets"""
    if not GOOGLE_SHEETS_ENABLED:
        return jsonify({'error': 'Google Sheets non configuré'}), 503
    
    try:
        headers = ['N° Commande', 'Client', 'Contact', 'Adresse', 'Articles', 
                   'Sous-total', 'Livraison', 'Frais livraison', 'Total', 'Statut', 'Date']
        
        rows = [headers]
        
        for order in orders:
            items_text = ', '.join([f"{item['product_name']} x{item['quantity']}" 
                                    for item in order['items']])
            
            order_number = order['order_number']
            customer_name = order['customer_name']
            customer_contact = order['customer_contact']
            customer_address = order.get('customer_address', '')
            subtotal_value = order['subtotal']
            shipping_type = order.get('shipping_type', '')
            delivery_fee_value = order.get('delivery_fee', 0)
            total_value = order['total']
            status_value = order['status']
            created_at = order['created_at']
            
            row = [
                order_number,
                customer_name,
                customer_contact,
                customer_address,
                items_text,
                f"{subtotal_value:.2f}€",
                shipping_type,
                f"{delivery_fee_value:.2f}€",
                f"{total_value:.2f}€",
                status_value,
                created_at
            ]
            rows.append(row)
        
        # Écrire dans Google Sheets
        body = {'values': rows}
        sheets_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range='Commandes!A1',
            valueInputOption='RAW',
            body=body
        ).execute()
        
        orders_count = len(orders)
        logger.warning(f"✅ {orders_count} commandes synchronisées vers Google Sheets")
        
        return jsonify({
            'success': True,
            'message': f'{orders_count} commandes synchronisées'
        }), 200
        
    except Exception as e:
        error_text = str(e)
        logger.error(f"❌ Erreur sync Google Sheets: {e}")
        return jsonify({'error': f'Erreur synchronisation: {error_text}'}), 500

# ==================== STATISTICS ====================
@app.route('/api/admin/stats', methods=['GET'])
@require_admin
def get_statistics():
    """Retourne des statistiques sur les commandes"""
    try:
        total_orders = len(orders)
        total_revenue = sum(order['total'] for order in orders)
        
        pending_orders = len([o for o in orders if o['status'] == 'pending'])
        delivered_orders = len([o for o in orders if o['status'] == 'delivered'])
        
        # Produits les plus vendus
        product_sales = {}
        for order in orders:
            for item in order['items']:
                pid = item['product_id']
                if pid not in product_sales:
                    product_sales[pid] = {
                        'name': item['product_name'],
                        'quantity': 0,
                        'revenue': 0
                    }
                product_sales[pid]['quantity'] += item['quantity']
                product_sales[pid]['revenue'] += item['subtotal']
        
        top_products = sorted(
            product_sales.values(),
            key=lambda x: x['quantity'],
            reverse=True
        )[:5]
        
        avg_order = round(total_revenue / total_orders, 2) if total_orders > 0 else 0
        
        stats = {
            'total_orders': total_orders,
            'total_revenue': round(total_revenue, 2),
            'pending_orders': pending_orders,
            'delivered_orders': delivered_orders,
            'top_products': top_products,
            'average_order_value': avg_order
        }
        
        return jsonify(stats), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur stats: {e}")
        return jsonify({'error': 'Erreur calcul statistiques'}), 500

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Route introuvable'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Erreur 500: {e}")
    return jsonify({'error': 'Erreur serveur interne'}), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Trop de requêtes, réessayez plus tard'}), 429

# ==================== STARTUP ====================
if __name__ == '__main__':
    logger.warning("=" * 70)
    logger.warning("🚀 DÉMARRAGE DE L'APPLICATION")
    logger.warning("=" * 70)
    
    # Configuration du webhook Telegram
    if TELEGRAM_BOT_TOKEN:
        logger.warning("🔧 Configuration du webhook Telegram...")
        configure_telegram_webhook()
    else:
        logger.warning("⚠️ Webhook Telegram non configuré (token manquant)")
    
    logger.warning("=" * 70)
    logger.warning("✅ Serveur prêt!")
    logger.warning("=" * 70)
    
    # Démarrer le serveur
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)'Non autorisé'}), 403
        token_data = admin_tokens[token]
        if datetime.now() > token_data['expires']:
            del admin_tokens[token]
            return jsonify({'error': 'Session expirée'}), 403
        return f(*args, **kwargs)
    return wrapped

# ==================== TELEGRAM FUNCTIONS ====================
def send_telegram_notification(order_data):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_ID:
        logger.error("❌ Configuration Telegram manquante")
        return False
    
    try:
        order_number = order_data['order_number']
        customer_name = order_data['customer_name']
        customer_contact = order_data['customer_contact']
        customer_address = order_data.get('customer_address', '')
        
        message = f"""🆕 *NOUVELLE COMMANDE WEB #{order_number}*

👤 *Client:*
• Nom: {customer_name}
• Contact: {customer_contact}
• 🏠 Adresse: {customer_address}

📦 *Articles:*
"""
        for item in order_data['items']:
            product_name = item['product_name']
            quantity = item['quantity']
            subtotal = item['subtotal']
            message += f"• {product_name} x{quantity} = {subtotal:.2f}€\n"
        
        order_subtotal = order_data['subtotal']
        shipping_type = order_data.get('shipping_type', 'N/A')
        order_total = order_data['total']
        created_at = order_data['created_at']
        
        message += f"\n💵 *Sous-total:* {order_subtotal:.2f}€\n"
        message += f"📦 *Livraison:* {shipping_type}\n"
        message += f"💰 *TOTAL: {order_total:.2f}€*\n"
        message += f"\n📅 {created_at}"
        
        order_id = order_data['id']
        keyboard = {"inline_keyboard": [[{"text": "✅ Valider", "callback_data": f"webapp_validate_{order_id}"}]]}
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_ADMIN_ID, "text": message, "parse_mode": "Markdown", "reply_markup": json.dumps(keyboard)}
        
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"❌ Erreur Telegram: {e}")
        return False

def configure_telegram_webhook():
    """Configure le webhook Telegram"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN manquant")
        return False
    
    webhook_url = os.environ.get('WEBHOOK_URL', 'https://carte-du-pirate.onrender.com')
    full_webhook_url = f"{webhook_url}/telegram/bot/{TELEGRAM_BOT_TOKEN}"
    
    try:
        logger.warning("=" * 70)
        logger.warning("🔧 CONFIGURATION WEBHOOK TELEGRAM")
        logger.warning("=" * 70)
        logger.warning(f"📍 URL: {full_webhook_url}")
        
        # Supprimer l'ancien webhook
        delete_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"
        requests.post(delete_url, json={"drop_pending_updates": True}, timeout=10)
        logger.warning("🗑️ Ancien webhook supprimé")
        
        # Configurer le nouveau
        set_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
        payload = {
            "url": full_webhook_url,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": True
        }
        
        response = requests.post(set_url, json=payload, timeout=10)
        
        if response.status_code == 200 and response.json().get('ok'):
            logger.warning("✅ Webhook configuré")
            
            # Vérifier
            info_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
            info_response = requests.get(info_url, timeout=10)
            
            if info_response.status_code == 200:
                info = info_response.json().get('result', {})
                info_url_value = info.get('url', 'N/A')
                pending_count = info.get('pending_update_count', 0)
                last_error = info.get('last_error_message', 'Aucune')
                
                logger.warning(f"📡 URL: {info_url_value}")
                logger.warning(f"📨 Updates en attente: {pending_count}")
                logger.warning(f"❌ Dernière erreur: {last_error}")
            
            logger.warning("=" * 70)
            return True
        else:
            logger.error(f"❌ Erreur: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Exception: {e}")
        return False

# ==================== ROUTES ====================
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
</html>
return html, 200
    except Exception as e:
        logger.error(f"Erreur route index: {e}")
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
        logger.error(f"Erreur route catalogue: {e}")
        return "Erreur serveur", 500

# ==================== TELEGRAM WEBHOOK ====================
@app.route('/telegram/bot/<path:token>', methods=['POST'])
def telegram_bot_webhook(token):
    """Route webhook principale - VERSION FINALE CORRIGÉE"""
    try:
        token_short = token[:20] if len(token) >= 20 else token
        current_time = datetime.now().strftime('%H:%M:%S')
        
        logger.warning("=" * 70)
        logger.warning("🔔 WEBHOOK APPELÉ!")
        logger.warning(f"📍 Route: /telegram/bot/{token_short}...")
        logger.warning(f"🕐 {current_time}")
        logger.warning("=" * 70)
        
        # Vérifier token
        if token != TELEGRAM_BOT_TOKEN:
            logger.error("❌ Token invalide")
            return jsonify({'error': 'Unauthorized'}), 403
        
        logger.warning("✅ Token valide")
        
        if not BOT_AVAILABLE:
            logger.error("❌ Bot non disponible")
            return jsonify({'error': 'Bot not available'}), 503
        
        logger.warning("✅ Bot disponible")
        
        # Récupérer données
        data = request.get_json()
        
        if not data:
            logger.error("❌ Pas de données")
            return jsonify({'error': 'No data'}), 400
        
        logger.warning("✅ Données reçues")
        
        # Identifier type - VERSION FINALE CORRIGÉE
        if 'message' in data:
            msg = data['message']
            from_user = msg.get('from', {})
            user_first_name = from_user.get('first_name', 'Unknown')
            user_id_value = from_user.get('id', 'N/A')
            message_text = msg.get('text', 'N/A')
            
            logger.warning(f"📧 MESSAGE de {user_first_name} (ID: {user_id_value})")
            logger.warning(f"💬 Texte: {message_text}")
            
        elif 'callback_query' in data:
            cb_query = data['callback_query']
            from_user = cb_query.get('from', {})
            user_first_name = from_user.get('first_name', 'Unknown')
            callback_data_value = cb_query.get('data', 'N/A')
            
            logger.warning(f"📧 CALLBACK de {user_first_name}")
            logger.warning(f"🔘 Data: {callback_data_value}")
        
        # Créer Update
        logger.warning("🔄 Création Update...")
        update = Update.de_json(data, bot_application.bot)
        logger.warning("✅ Update créé")
        
        # Traiter
        logger.warning("⚙️ Traitement...")
        asyncio.run(bot_application.process_update(update))
        logger.warning("✅ Traité avec succès")
        
        logger.warning("=" * 70)
        return jsonify({'ok': True}), 200
        
    except Exception as e:
        logger.error("=" * 70)
        logger.error(f"❌ ERREUR: {e}")
        import traceback
        logger.error(traceback.format_exc())
        logger.error("=" * 70)
        return jsonify({'ok': True}), 200

@app.route('/api/telegram/webapp-callback', methods=['POST'])
def telegram_webapp_callback():
    """Callback pour webapp uniquement"""
    try:
        data = request.json
        if 'callback_query' not in data:
            return jsonify({'ok': True}), 200
        
        callback_query = data['callback_query']
        callback_data = callback_query.get('data', '')
        
        if not callback_data.startswith('webapp_validate_'):
            return jsonify({'ok': True}), 200
        
        order_id = int(callback_data.split('_')[2])
        
        for order in orders:
            if order['id'] == order_id:
                order['status'] = 'delivered'
                order['delivered_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                break
        
        save_json_file(ORDERS_FILE, orders)
        return jsonify({'ok': True}), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur webapp callback: {e}")
        return jsonify({'ok': True}), 200

# ==================== ADMIN ROUTES ====================
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

# ==================== PRODUCT ROUTES ====================
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

# ==================== ORDER ROUTES ====================
@app.route('/api/orders', methods=['POST'])
@limiter.limit("5 per hour")
def create_order():
    global orders
    try:
        data = request.json or {}
        
        if not data.get('items') or len(data.get('items', [])) == 0:
            return jsonify({'error': 'Panier vide'}), 400
        if not data.get('customer_name') or not data.get('customer_contact'):
            return jsonify({'error': 'Nom et contact requis'}), 400
        
        total = 0
        order_items = []
        for item in data['items']:
            product = next((p for p in products if p['id'] == item['product_id']), None)
            if not product:
                product_id_missing = item['product_id']
                return jsonify({'error': f'Produit {product_id_missing} introuvable'}), 404
            if product['stock'] < item['quantity']:
                product_name_insufficient = product['name']
                return jsonify({'error': f'Stock insuffisant pour {product_name_insufficient}'}), 400
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
        order_number = f"CMD-{order_id:05d}"
        new_order = {
            'id': order_id,
            'order_number': order_number,
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
        
        send_telegram_notification(new_order)
        
        return jsonify({'success': True, 'order': new_order}), 201
        
    except Exception as e:
        logger.error(f"❌ Erreur création commande: {e}")
        return jsonify({'error':
