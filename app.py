from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from functools import wraps
import os, json, cloudinary, cloudinary.uploader
import logging
import secrets
import hashlib
import requests
from datetime import datetime, timedelta

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

load_dotenv('infos.env')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True, origins=['*'])

# Configuration
ADMIN_PASSWORD_HASH = hashlib.sha256(os.environ.get('ADMIN_PASSWORD', 'changeme123').encode()).hexdigest()
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_ADMIN_ID = os.environ.get('TELEGRAM_ADMIN_ID')
BACKGROUND_IMAGE = os.environ.get('BACKGROUND_URL', 'https://res.cloudinary.com/dfhrrtzsd/image/upload/v1760118433/ChatGPT_Image_8_oct._2025_03_01_21_zm5zfy.png')

limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["200 per day", "50 per hour"], storage_uri="memory://")

admin_tokens = {}
failed_login_attempts = {}

try:
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
        secure=True
    )
    logger.warning("Cloudinary configuré")
except Exception as e:
    logger.error(f"Erreur Cloudinary: {e}")

PRODUCTS_FILE = 'products.json'
ORDERS_FILE = 'orders.json'

def load_json_file(filename, default=[]):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else default
        except Exception as e:
            logger.warning(f"Erreur lecture {filename}: {e}")
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

products = load_json_file(PRODUCTS_FILE)
orders = load_json_file(ORDERS_FILE)

def send_telegram_message(text):
    """Envoie un message à l'admin via Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_ID:
        logger.warning("Configuration Telegram manquante")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_ADMIN_ID,
            "text": text,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Erreur envoi Telegram: {e}")
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
  animation: float 3s ease-in-out infinite;
}}
@keyframes float {{
  0%, 100% {{ transform: translateY(0px); }}
  50% {{ transform: translateY(-10px); }}
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
    try:
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'status': 'error'}), 500

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
        logger.error(f"Erreur login")
        return jsonify({'error': 'Erreur serveur'}), 500

@app.route('/api/admin/logout', methods=['POST'])
def api_logout():
    try:
        token = request.headers.get('X-Admin-Token')
        if token and token in admin_tokens:
            del admin_tokens[token]
        return jsonify({'success': True})
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        return jsonify({'error': 'Erreur upload'}), 500

@app.route('/api/products', methods=['GET'])
def get_products():
    try:
        return jsonify(products), 200
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        return jsonify({'error': 'Erreur suppression'}), 500

@app.route('/api/orders', methods=['POST'])
@limiter.limit("5 per hour")
def create_order():
    """Créer une nouvelle commande"""
    global orders
    try:
        data = request.json or {}
        
        # Validation
        if not data.get('items') or len(data.get('items', [])) == 0:
            return jsonify({'error': 'Panier vide'}), 400
        
        if not data.get('customer_name') or not data.get('customer_contact'):
            return jsonify({'error': 'Nom et contact requis'}), 400
        
        # Calculer le total
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
        
        # Créer la commande
        order_id = max([o['id'] for o in orders]) + 1 if orders else 1
        new_order = {
            'id': order_id,
            'order_number': f"CMD-{order_id:05d}",
            'customer_name': data['customer_name'],
            'customer_contact': data['customer_contact'],
            'customer_address': data.get('customer_address', ''),
            'customer_notes': data.get('customer_notes', ''),
            'items': order_items,
            'total': total,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        orders.append(new_order)
        save_json_file(ORDERS_FILE, orders)
        
        # Envoyer notification Telegram à l'admin
        message = f"""🛒 <b>NOUVELLE COMMANDE #{new_order['order_number']}</b>

👤 <b>Client:</b> {new_order['customer_name']}
📞 <b>Contact:</b> {new_order['customer_contact']}
📍 <b>Adresse:</b> {new_order['customer_address'] or 'Non spécifiée'}

📦 <b>Articles:</b>
"""
        for item in order_items:
            message += f"• {item['product_name']} x{item['quantity']} = {item['subtotal']}€\n"
        
        message += f"\n💰 <b>TOTAL: {total}€</b>"
        
        if new_order['customer_notes']:
            message += f"\n\n📝 <b>Notes:</b> {new_order['customer_notes']}"
        
        message += f"\n\n⏰ {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
        
        send_telegram_message(message)
        
        return jsonify({
            'success': True,
            'order': new_order
        }), 201
        
    except Exception as e:
        logger.error(f"Erreur création commande: {e}")
        return jsonify({'error': 'Erreur serveur'}), 500

@app.route('/api/admin/orders', methods=['GET'])
@require_admin
def get_orders():
    """Récupérer toutes les commandes (admin)"""
    try:
        return jsonify(orders), 200
    except Exception as e:
        return jsonify([]), 200

@app.route('/api/admin/orders/<int:order_id>', methods=['PUT'])
@require_admin
def update_order_status(order_id):
    """Mettre à jour le statut d'une commande"""
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
    except Exception as e:
        return jsonify({'error': 'Erreur modification'}), 500

@app.route('/catalogue')
def catalogue():
    try:
        html = '''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Catalogue & Commandes</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  background: url('%(bg)s') center center fixed;
  background-size: cover;
  min-height: 100vh;
  padding: 15px;
  position: relative;
}
body::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 0;
}
.container {
  max-width: 800px;
  margin: 0 auto;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
  position: relative;
  z-index: 1;
  backdrop-filter: blur(10px);
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 10px;
}
h1 { color: #333; font-size: 24px; }
.back-btn, button {
  background: #6c757d;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  text-decoration: none;
  display: inline-block;
  margin: 5px;
}
.back-btn:hover { background: #5a6268; }
button {
  background: #667eea;
}
button:hover { background: #5568d3; }
button.delete { background: #e74c3c; }
button.delete:hover { background: #c0392b; }
button.success { background: #27ae60; }
button.success:hover { background: #229954; }
input, textarea, select {
  width: 100%%;
  padding: 12px;
  margin: 8px 0;
  border: 2px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}
.card {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
  margin: 15px 0;
  border: 1px solid #e0e0e0;
}
.card img, .card video {
  width: 100%%;
  max-height: 250px;
  object-fit: cover;
  border-radius: 6px;
  margin-bottom: 10px;
}
.card h3 { color: #333; margin: 10px 0; }
.card p { color: #666; margin: 5px 0; }
.price { font-size: 22px; color: #27ae60; font-weight: bold; }
.modal {
  display: none;
  position: fixed;
  top: 0; left: 0;
  width: 100%%; height: 100%%;
  background: rgba(0,0,0,0.7);
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal.show { display: flex; }
.modal-content {
  background: white;
  padding: 30px;
  border-radius: 12px;
  max-width: 500px;
  width: 90%%;
  max-height: 90vh;
  overflow-y: auto;
}
.badge { 
  background: #27ae60; 
  color: white; 
  padding: 5px 10px; 
  border-radius: 20px; 
  font-size: 12px; 
  font-weight: bold;
}
.badge.cart {
  background: #667eea;
  position: relative;
  margin-left: 10px;
}
.cart-count {
  position: absolute;
  top: -8px;
  right: -8px;
  background: #e74c3c;
  color: white;
  border-radius: 50%%;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
}
.quantity-control {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0;
}
.quantity-control button {
  width: 40px;
  height: 40px;
  padding: 0;
  font-size: 20px;
}
.quantity-control input {
  width: 60px;
  text-align: center;
  margin: 0;
}
.cart-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  background: #f8f9fa;
  border-radius: 8px;
  margin: 10px 0;
}
.total-section {
  background: #667eea;
  color: white;
  padding: 20px;
  border-radius: 8px;
  margin: 20px 0;
  text-align: center;
}
.total-section h2 {
  font-size: 32px;
  margin: 10px 0;
}
.loading, .empty, .error {
  text-align: center;
  padding: 40px;
  color: #666;
}
.error { color: #e74c3c; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <a href="/" class="back-btn">← Retour</a>
      <h1 style="display: inline; margin-left: 15px;">🛍️ Catalogue</h1>
    </div>
    <div id="admin-controls"></div>
  </div>
  <div id="content" class="loading">Chargement...</div>
</div>

<!-- Modals -->
<div id="login-modal" class="modal">
  <div class="modal-content">
    <h2>🔐 Connexion Admin</h2>
    <input type="password" id="password-input" placeholder="Mot de passe">
    <button onclick="login()">Se connecter</button>
    <button onclick="closeLogin()">Annuler</button>
    <div id="login-error" style="color:red;margin-top:10px;"></div>
  </div>
</div>

<div id="form-modal" class="modal">
  <div class="modal-content">
    <h3 id="form-title">Nouveau produit</h3>
    <input type="text" id="name" placeholder="Nom *">
    <input type="number" id="price" step="0.01" placeholder="Prix (€) *">
    <input type="text" id="category" placeholder="Catégorie">
    <input type="number" id="stock" placeholder="Stock">
    <textarea id="description" rows="3" placeholder="Description"></textarea>
    <input type="file" id="file-input" accept="image/*,video/*">
    <div id="file-status"></div>
    <button onclick="saveProduct()">💾 Sauvegarder</button>
    <button onclick="closeForm()">Annuler</button>
  </div>
</div>

<div id="cart-modal" class="modal">
  <div class="modal-content">
    <h2>🛒 Mon Panier</h2>
    <div id="cart-items"></div>
    <div class="total-section" id="cart-total"></div>
    <button class="success" onclick="showCheckout()">✅ Commander</button>
    <button onclick="closeCart()">Continuer mes achats</button>
  </div>
</div>

<div id="checkout-modal" class="modal">
  <div class="modal-content">
    <h2>📝 Finaliser la commande</h2>
    <input type="text" id="customer-name" placeholder="Votre nom *">
    <input type="text" id="customer-contact" placeholder="Téléphone ou Email *">
    <textarea id="customer-address" rows="2" placeholder="Adresse de livraison"></textarea>
    <textarea id="customer-notes" rows="2" placeholder="Notes ou instructions particulières"></textarea>
    <div class="total-section" id="checkout-total"></div>
    <button class="success" onclick="submitOrder()">🚀 Valider la commande</button>
    <button onclick="closeCheckout()">Retour au panier</button>
    <div id="checkout-error" style="color:red;margin-top:10px;"></div>
  </div>
</div>

<script>
let adminToken = sessionStorage.getItem('adminToken') || '';
let products = [];
let cart = JSON.parse(localStorage.getItem('cart') || '[]');
let editingProduct = null;
let currentImageUrl = '';
let currentVideoUrl = '';

async function init() {
  try {
    await checkAdmin();
    await loadProducts();
    render();
  } catch (e) {
    errorDiv.textContent = 'Erreur réseau';
  }
}

function render() {
  const adminControls = document.getElementById('admin-controls');
  const content = document.getElementById('content');
  
  const cartCount = getCartCount();
  const cartBadge = cartCount > 0 ? `<span class="badge cart">🛒 Panier<span class="cart-count">${cartCount}</span></span>` : '';
  
  if (adminToken) {
    adminControls.innerHTML = `
      <span class="badge">Admin</span>
      <button onclick="showForm()">➕ Ajouter</button>
      <button onclick="logout()">Déconnexion</button>
      ${cartBadge ? `<button onclick="showCart()">${cartBadge}</button>` : ''}
    `;
  } else {
    adminControls.innerHTML = `
      <button onclick="showLogin()">Mode Admin</button>
      ${cartBadge ? `<button onclick="showCart()">${cartBadge}</button>` : ''}
    `;
  }
  
  if (products.length === 0) {
    content.innerHTML = '<div class="empty"><h2>📦 Catalogue vide</h2><p>Aucun produit</p></div>';
  } else {
    content.innerHTML = products.map(p => `
      <div class="card">
        ${p.image_url ? `<img src="${p.image_url}" alt="${p.name}">` : ''}
        ${p.video_url ? `<video src="${p.video_url}" controls></video>` : ''}
        <h3>${p.name}</h3>
        ${p.category ? `<p><em>${p.category}</em></p>` : ''}
        ${p.description ? `<p>${p.description}</p>` : ''}
        <p class="price">${p.price} €</p>
        <p>Stock : ${p.stock}</p>
        ${p.stock > 0 ? `<button class="success" onclick="addToCart(${p.id})">🛒 Ajouter au panier</button>` : '<p style="color:#e74c3c;">Rupture de stock</p>'}
        ${adminToken ? `
          <button onclick="editProduct(${p.id})">✏️ Modifier</button>
          <button class="delete" onclick="deleteProduct(${p.id})">🗑️ Supprimer</button>
        ` : ''}
      </div>
    `).join('');
  }
}

function showLogin() {
  document.getElementById('login-modal').classList.add('show');
  document.getElementById('login-error').textContent = '';
}

function closeLogin() {
  document.getElementById('login-modal').classList.remove('show');
}

async function login() {
  const password = document.getElementById('password-input').value;
  const errorDiv = document.getElementById('login-error');
  
  try {
    const res = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    });
    const data = await res.json();
    
    if (res.ok && data.token) {
      adminToken = data.token;
      sessionStorage.setItem('adminToken', adminToken);
      closeLogin();
      render();
      alert('✅ Connecté');
    } else {
      errorDiv.textContent = data.error || 'Erreur de connexion';
    }
  } catch (e) {
    errorDiv.textContent = 'Erreur réseau';
  }
}

async function logout() {
  await fetch('/api/admin/logout', { 
    method: 'POST',
    headers: { 'X-Admin-Token': adminToken }
  });
  adminToken = '';
  sessionStorage.removeItem('adminToken');
  render();
}

function showForm() {
  editingProduct = null;
  currentImageUrl = '';
  currentVideoUrl = '';
  document.getElementById('form-title').textContent = 'Nouveau produit';
  document.getElementById('name').value = '';
  document.getElementById('price').value = '';
  document.getElementById('category').value = '';
  document.getElementById('stock').value = '';
  document.getElementById('description').value = '';
  document.getElementById('file-input').value = '';
  document.getElementById('file-status').innerHTML = '';
  document.getElementById('form-modal').classList.add('show');
}

function editProduct(id) {
  const product = products.find(p => p.id === id);
  if (!product) return;
  
  editingProduct = product;
  currentImageUrl = product.image_url || '';
  currentVideoUrl = product.video_url || '';
  
  document.getElementById('form-title').textContent = 'Modifier le produit';
  document.getElementById('name').value = product.name;
  document.getElementById('price').value = product.price;
  document.getElementById('category').value = product.category || '';
  document.getElementById('stock').value = product.stock;
  document.getElementById('description').value = product.description || '';
  document.getElementById('file-status').innerHTML = (currentImageUrl || currentVideoUrl) ? '<p style="color:green">✓ Fichier existant</p>' : '';
  document.getElementById('form-modal').classList.add('show');
}

function closeForm() {
  document.getElementById('form-modal').classList.remove('show');
}

document.getElementById('file-input').addEventListener('change', async function(e) {
  const file = e.target.files[0];
  if (!file) return;
  
  const fd = new FormData();
  fd.append('file', file);
  
  document.getElementById('file-status').innerHTML = '<p>⏳ Upload...</p>';
  
  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      headers: { 'X-Admin-Token': adminToken },
      body: fd
    });
    const data = await res.json();
    if (data.url) {
      if (file.type.startsWith('video')) {
        currentVideoUrl = data.url;
        currentImageUrl = '';
      } else {
        currentImageUrl = data.url;
        currentVideoUrl = '';
      }
      document.getElementById('file-status').innerHTML = '<p style="color:green">✅ Uploadé</p>';
    } else {
      alert('Erreur upload: ' + (data.error || 'Erreur inconnue'));
      document.getElementById('file-status').innerHTML = '';
    }
  } catch (e) {
    alert('Erreur upload: ' + e.message);
    document.getElementById('file-status').innerHTML = '';
  }
});

async function saveProduct() {
  const name = document.getElementById('name').value;
  const price = document.getElementById('price').value;
  
  if (!name || !price) {
    alert('Nom et prix requis');
    return;
  }
  
  const data = {
    name,
    price: parseFloat(price),
    category: document.getElementById('category').value,
    stock: parseInt(document.getElementById('stock').value) || 0,
    description: document.getElementById('description').value,
    image_url: currentImageUrl,
    video_url: currentVideoUrl
  };
  
  const url = editingProduct ? `/api/admin/products/${editingProduct.id}` : '/api/admin/products';
  const method = editingProduct ? 'PUT' : 'POST';
  
  try {
    const res = await fetch(url, {
      method,
      headers: { 
        'Content-Type': 'application/json',
        'X-Admin-Token': adminToken
      },
      body: JSON.stringify(data)
    });
    
    if (res.ok) {
      closeForm();
      await loadProducts();
      render();
      alert('✅ Sauvegardé');
    } else {
      const err = await res.json();
      alert('Erreur sauvegarde: ' + (err.error || 'Erreur inconnue'));
    }
  } catch (e) {
    alert('Erreur: ' + e.message);
  }
}

async function deleteProduct(id) {
  if (!confirm('Supprimer ce produit ?')) return;
  
  try {
    const res = await fetch(`/api/admin/products/${id}`, {
      method: 'DELETE',
      headers: { 'X-Admin-Token': adminToken }
    });
    
    if (res.ok) {
      await loadProducts();
      render();
      alert('✅ Supprimé');
    }
  } catch (e) {
    alert('Erreur suppression');
  }
}

document.querySelectorAll('.modal').forEach(modal => {
  modal.addEventListener('click', e => {
    if (e.target === modal) modal.classList.remove('show');
  });
});

init();
</script>
</body>
</html>''' % {'bg': BACKGROUND_IMAGE}
        return html, 200
    except Exception as e:
        logger.error(f"Erreur route catalogue: {e}")
        return "Erreur serveur", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.warning(f"Démarrage sur le port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
    console.error('Erreur init:', e);
    document.getElementById('content').innerHTML = '<div class="error">❌ Erreur de chargement</div>';
  }
}

async function checkAdmin() {
  try {
    const res = await fetch('/api/admin/check', { 
      headers: { 'X-Admin-Token': adminToken }
    });
    if (!res.ok) throw new Error('Erreur check admin');
    const data = await res.json();
    if (!data.admin) {
      adminToken = '';
      sessionStorage.removeItem('adminToken');
    }
    return data.admin;
  } catch (e) {
    adminToken = '';
    sessionStorage.removeItem('adminToken');
    return false;
  }
}

async function loadProducts() {
  try {
    const res = await fetch('/api/products');
    if (!res.ok) throw new Error('Erreur chargement produits');
    products = await res.json();
  } catch (e) {
    throw e;
  }
}

function getCartCount() {
  return cart.reduce((sum, item) => sum + item.quantity, 0);
}

function getCartTotal() {
  return cart.reduce((sum, item) => {
    const product = products.find(p => p.id === item.product_id);
    return sum + (product ? product.price * item.quantity : 0);
  }, 0);
}

function addToCart(productId) {
  const product = products.find(p => p.id === productId);
  if (!product) return;
  
  const existing = cart.find(item => item.product_id === productId);
  if (existing) {
    if (existing.quantity < product.stock) {
      existing.quantity++;
    } else {
      alert('Stock insuffisant');
      return;
    }
  } else {
    cart.push({ product_id: productId, quantity: 1 });
  }
  
  localStorage.setItem('cart', JSON.stringify(cart));
  render();
  alert('✅ Ajouté au panier');
}

function updateCartQuantity(productId, change) {
  const item = cart.find(i => i.product_id === productId);
  const product = products.find(p => p.id === productId);
  
  if (!item || !product) return;
  
  const newQty = item.quantity + change;
  
  if (newQty <= 0) {
    cart = cart.filter(i => i.product_id !== productId);
  } else if (newQty <= product.stock) {
    item.quantity = newQty;
  } else {
    alert('Stock insuffisant');
    return;
  }
  
  localStorage.setItem('cart', JSON.stringify(cart));
  showCart();
}

function removeFromCart(productId) {
  cart = cart.filter(item => item.product_id !== productId);
  localStorage.setItem('cart', JSON.stringify(cart));
  showCart();
}

function showCart() {
  const modal = document.getElementById('cart-modal');
  const itemsDiv = document.getElementById('cart-items');
  const totalDiv = document.getElementById('cart-total');
  
  if (cart.length === 0) {
    itemsDiv.innerHTML = '<p style="text-align:center;padding:40px;color:#999;">Votre panier est vide</p>';
    totalDiv.innerHTML = '';
  } else {
    itemsDiv.innerHTML = cart.map(item => {
      const product = products.find(p => p.id === item.product_id);
      if (!product) return '';
      
      return `
        <div class="cart-item">
          <div>
            <strong>${product.name}</strong><br>
            <span style="color:#27ae60;">${product.price}€</span> x ${item.quantity}
          </div>
          <div>
            <button onclick="updateCartQuantity(${item.product_id}, -1)">-</button>
            <span style="margin:0 10px;">${item.quantity}</span>
            <button onclick="updateCartQuantity(${item.product_id}, 1)">+</button>
            <button class="delete" onclick="removeFromCart(${item.product_id})">🗑️</button>
          </div>
        </div>
      `;
    }).join('');
    
    totalDiv.innerHTML = `<h2>${getCartTotal().toFixed(2)} €</h2><p>${getCartCount()} article(s)</p>`;
  }
  
  modal.classList.add('show');
}

function closeCart() {
  document.getElementById('cart-modal').classList.remove('show');
}

function showCheckout() {
  if (cart.length === 0) {
    alert('Votre panier est vide');
    return;
  }
  
  document.getElementById('cart-modal').classList.remove('show');
  document.getElementById('checkout-total').innerHTML = `<h2>${getCartTotal().toFixed(2)} €</h2><p>${getCartCount()} article(s)</p>`;
  document.getElementById('checkout-modal').classList.add('show');
}

function closeCheckout() {
  document.getElementById('checkout-modal').classList.remove('show');
  showCart();
}

async function submitOrder() {
  const name = document.getElementById('customer-name').value.trim();
  const contact = document.getElementById('customer-contact').value.trim();
  const address = document.getElementById('customer-address').value.trim();
  const notes = document.getElementById('customer-notes').value.trim();
  const errorDiv = document.getElementById('checkout-error');
  
  if (!name || !contact) {
    errorDiv.textContent = 'Nom et contact sont requis';
    return;
  }
  
  const orderData = {
    customer_name: name,
    customer_contact: contact,
    customer_address: address,
    customer_notes: notes,
    items: cart
  };
  
  try {
    const res = await fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(orderData)
    });
    
    const data = await res.json();
    
    if (res.ok) {
      cart = [];
      localStorage.removeItem('cart');
      document.getElementById('checkout-modal').classList.remove('show');
      alert(`✅ Commande validée !\\n\\nNuméro: ${data.order.order_number}\\nTotal: ${data.order.total}€\\n\\nVous serez contacté rapidement !`);
      render();
    } else {
      errorDiv.textContent = data.error || 'Erreur lors de la commande';
    }
  } catch (e) {

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.warning(f"Démarrage sur le port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
