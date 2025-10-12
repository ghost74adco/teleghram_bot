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
    logger.warning("⚠️ geopy non installé")

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
                    logger.warning(f"{filename} est vide, initialisation")
                    save_json_file(filename, default)
                    return default
                data = json.loads(content)
                return data if isinstance(data, list) else default
        except json.JSONDecodeError as e:
            logger.error(f"Erreur JSON dans {filename}: {e}")
            try:
                import shutil
                shutil.copy(filename, f"{filename}.backup")
                logger.warning(f"Backup créé")
            except:
                pass
            save_json_file(filename, default)
            return default
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

def ensure_valid_json_files():
    for filename in [PRODUCTS_FILE, ORDERS_FILE]:
        try:
            if not os.path.exists(filename):
                logger.warning(f"📁 {filename} introuvable, création...")
                save_json_file(filename, [])
                logger.warning(f"✅ {filename} créé avec succès")
                continue
            
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                logger.warning(f"⚠️ {filename} vide, initialisation...")
                save_json_file(filename, [])
                continue
            
            try:
                data = json.loads(content)
                
                if not isinstance(data, list):
                    logger.error(f"❌ {filename} n'est pas une liste, réinitialisation")
                    backup_name = f"{filename}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    try:
                        import shutil
                        shutil.copy(filename, backup_name)
                        logger.warning(f"💾 Backup créé: {backup_name}")
                    except:
                        pass
                    save_json_file(filename, [])
                else:
                    logger.warning(f"✅ {filename} valide ({len(data)} élément(s))")
                    
            except json.JSONDecodeError as e:
                logger.error(f"❌ Erreur JSON dans {filename}: {e.msg} (ligne {e.lineno})")
                
                backup_name = f"{filename}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                try:
                    import shutil
                    shutil.copy(filename, backup_name)
                    logger.warning(f"💾 Backup créé: {backup_name}")
                except Exception as backup_error:
                    logger.error(f"⚠️ Impossible de créer backup: {backup_error}")
                
                logger.warning(f"🔧 Réinitialisation de {filename}...")
                save_json_file(filename, [])
                logger.warning(f"✅ {filename} réinitialisé")
                
        except Exception as e:
            logger.error(f"❌ Erreur lors de la vérification de {filename}: {e}")
            try:
                save_json_file(filename, [])
                logger.warning(f"✅ {filename} recréé en dernier recours")
            except:
                logger.critical(f"💥 IMPOSSIBLE de créer {filename}")

logger.warning("🔍 Vérification des fichiers JSON...")
ensure_valid_json_files()
logger.warning("✅ Vérification terminée")

# Affichage de la configuration au démarrage
logger.warning("=" * 50)
logger.warning("🔧 CONFIGURATION DE L'APPLICATION")
logger.warning("=" * 50)
logger.warning(f"📱 TELEGRAM_BOT_TOKEN: {'✅ Configuré' if TELEGRAM_BOT_TOKEN else '❌ Manquant'}")
logger.warning(f"👤 TELEGRAM_ADMIN_ID: {'✅ Configuré (' + TELEGRAM_ADMIN_ID + ')' if TELEGRAM_ADMIN_ID else '❌ Manquant'}")
logger.warning(f"🔑 ADMIN_PASSWORD: {'✅ Configuré' if os.environ.get('ADMIN_PASSWORD') else '❌ Manquant'}")
logger.warning(f"📍 ADMIN_ADDRESS: {ADMIN_ADDRESS}")
logger.warning(f"☁️ CLOUDINARY: {'✅ Configuré' if os.environ.get('CLOUD_NAME') or os.environ.get('CLOUDINARY_CLOUD_NAME') else '❌ Manquant'}")
logger.warning("=" * 50)

products = load_json_file(PRODUCTS_FILE)
orders = load_json_file(ORDERS_FILE)

def send_telegram_notification(order_data):
    """Envoie une notification Telegram pour une nouvelle commande"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_ID:
        logger.error("❌ Configuration Telegram manquante - BOT_TOKEN ou ADMIN_ID non défini")
        return False
    
    try:
        logger.warning(f"📤 Envoi notification Telegram pour commande #{order_data['order_number']}")
        
        message = f"""🆕 *NOUVELLE COMMANDE WEB #{order_data['order_number']}*

👤 *Client:*
• Nom: {order_data['customer_name']}
• Contact: {order_data['customer_contact']}
"""
        
        if order_data.get('customer_address'):
            message += f"• 📍 Adresse: {order_data['customer_address']}\n"
        
        message += "\n📦 *Articles:*\n"
        
        for item in order_data['items']:
            message += f"• {item['product_name']} x{item['quantity']} = {item['subtotal']:.2f}€\n"
        
        shipping_type = order_data.get('shipping_type', 'N/A')
        delivery_fee = order_data.get('delivery_fee', 0)
        distance = order_data.get('distance_km', 0)
        
        message += f"\n💵 *Sous-total:* {order_data['subtotal']:.2f}€\n"
        
        if shipping_type == 'postal':
            message += f"📦 *Livraison:* ✉️ Postale 48-72H (+{FRAIS_POSTAL}€)\n"
        elif shipping_type == 'express':
            message += f"📦 *Livraison:* ⚡ Express à domicile\n"
            message += f"💶 *Frais de livraison:* {delivery_fee:.2f}€\n"
        else:
            message += f"📦 *Livraison:* {shipping_type}\n"
        
        message += f"\n💰 *TOTAL: {order_data['total']:.2f}€*\n"
        
        if order_data.get('customer_notes'):
            message += f"\n📝 *Notes:* {order_data['customer_notes']}\n"
        
        message += f"\n📅 {order_data['created_at']}"
        message += f"\n🌐 Source: Site Web"
        
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
        
        logger.warning(f"🔄 Envoi vers Telegram API...")
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.warning(f"✅ Notification Telegram envoyée avec succès pour commande #{order_data['order_number']}")
            return True
        else:
            logger.error(f"❌ Erreur Telegram HTTP {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error(f"⏱️ Timeout lors de l'envoi Telegram")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"🌐 Erreur réseau Telegram: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"❌ Erreur inattendue envoi Telegram: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
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

@app.route('/catalogue')
def catalogue():
    try:
        # Utilisation de triple quotes et échappement correct
        html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Catalogue & Commandes</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  background: url('{BACKGROUND_IMAGE}') center center fixed;
  background-size: cover;
  min-height: 100vh;
  padding: 15px;
  position: relative;
}}
body::before {{
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 0;
}}
.container {{
  max-width: 800px;
  margin: 0 auto;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
  position: relative;
  z-index: 1;
  backdrop-filter: blur(10px);
}}
.header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 10px;
}}
h1 {{ color: #333; font-size: 24px; }}
.back-btn, button {{
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
}}
.back-btn:hover {{ background: #5a6268; }}
button {{ background: #667eea; }}
button:hover {{ background: #5568d3; }}
button.delete {{ background: #e74c3c; }}
button.delete:hover {{ background: #c0392b; }}
button.success {{ background: #27ae60; }}
button.success:hover {{ background: #229954; }}
input, textarea, select {{
  width: 100%;
  padding: 12px;
  margin: 8px 0;
  border: 2px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}}
.card {{
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
  margin: 15px 0;
  border: 1px solid #e0e0e0;
}}
.card img, .card video {{
  width: 100%;
  max-height: 250px;
  object-fit: cover;
  border-radius: 6px;
  margin-bottom: 10px;
}}
.card h3 {{ color: #333; margin: 10px 0; }}
.card p {{ color: #666; margin: 5px 0; }}
.price {{ font-size: 22px; color: #27ae60; font-weight: bold; }}
.modal {{
  display: none;
  position: fixed;
  top: 0; left: 0;
  width: 100%; height: 100%;
  background: rgba(0,0,0,0.7);
  align-items: center;
  justify-content: center;
  z-index: 1000;
}}
.modal.show {{ display: flex; }}
.modal-content {{
  background: white;
  padding: 30px;
  border-radius: 12px;
  max-width: 500px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
}}
.badge {{
  background: #27ae60;
  color: white;
  padding: 5px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: bold;
}}
.badge.cart {{
  background: #667eea;
  position: relative;
  margin-left: 10px;
}}
.cart-count {{
  position: absolute;
  top: -8px;
  right: -8px;
  background: #e74c3c;
  color: white;
  border-radius: 50%;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
}}
.cart-item {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  background: #f8f9fa;
  border-radius: 8px;
  margin: 10px 0;
}}
.total-section {{
  background: #667eea;
  color: white;
  padding: 20px;
  border-radius: 8px;
  margin: 20px 0;
  text-align: center;
}}
.total-section h2 {{
  font-size: 32px;
  margin: 10px 0;
}}
.loading, .empty, .error {{
  text-align: center;
  padding: 40px;
  color: #666;
}}
.error {{ color: #e74c3c; }}
.form-group {{ margin: 15px 0; }}
.form-group label {{
  display: block;
  font-weight: 600;
  margin-bottom: 5px;
  color: #333;
}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <a href="/" class="back-btn">← Retour</a>
      <h1 style="display: inline; margin-left: 15px;">🛒 Catalogue</h1>
    </div>
    <div id="admin-controls"></div>
  </div>
  <div id="content" class="loading">Chargement...</div>
</div>
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
    <h2>📋 Finaliser la commande</h2>
    <div class="form-group">
      <label for="customer-name">Votre nom *</label>
      <input type="text" id="customer-name" placeholder="Jean Dupont">
    </div>
    <div class="form-group">
      <label for="customer-contact">Téléphone ou Email *</label>
      <input type="text" id="customer-contact" placeholder="+33 6 12 34 56 78">
    </div>
    <div class="form-group">
      <label for="customer-address">Adresse de livraison *</label>
      <textarea id="customer-address" rows="3" placeholder="123 Rue de la Paix, 75001 Paris, France"></textarea>
    </div>
    <div class="form-group">
      <label for="shipping-type">Type de livraison *</label>
      <select id="shipping-type" onchange="handleShippingChange()">
        <option value="">-- Sélectionner --</option>
        <option value="postal">📦 Livraison postale : 48H à 72H (10€)</option>
        <option value="express">⚡ Livraison Express : livraison à votre adresse (30 min minimum)</option>
      </select>
    </div>
    <div id="express-info" style="display:none; margin: 15px 0; padding: 10px; background: #e3f2fd; border-radius: 6px;">
      <p style="margin:0; color:#1976d2;">
        <strong>ℹ️ Calcul automatique de distance</strong><br>
        La distance sera calculée automatiquement depuis notre entrepôt.
      </p>
    </div>
    <div id="distance-result" style="display:none; margin: 15px 0; padding: 10px; background: #e8f5e9; border-radius: 6px; border-left: 4px solid #4caf50;">
      <div id="distance-detail"></div>
    </div>
    <div class="form-group">
      <label for="customer-notes">Notes ou instructions</label>
      <textarea id="customer-notes" rows="2" placeholder="Sonnez 2 fois, code: 1234..."></textarea>
    </div>
    <div class="total-section" id="checkout-total"></div>
    <button class="success" onclick="submitOrder()">🚀 Valider la commande</button>
    <button onclick="closeCheckout()">Retour au panier</button>
    <div id="checkout-error" style="color:red;margin-top:10px;"></div>
  </div>
</div>
<script>
let adminToken=sessionStorage.getItem('adminToken')||'';
let products=[];
let cart=JSON.parse(localStorage.getItem('cart')||'[]');
let editingProduct=null;
let currentImageUrl='';
let currentVideoUrl='';
let calculatedDistance=0;

async function init(){{
  try{{
    await checkAdmin();
    await loadProducts();
    render();
  }}catch(e){{
    document.getElementById('content').innerHTML='<div class="error">❌ Erreur</div>';
  }}
}}

async function checkAdmin(){{
  try{{
    const res=await fetch('/api/admin/check',{{headers:{{'X-Admin-Token':adminToken}}}});
    if(!res.ok)throw new Error('Erreur');
    const data=await res.json();
    if(!data.admin){{
      adminToken='';
      sessionStorage.removeItem('adminToken');
    }}
    return data.admin;
  }}catch(e){{
    adminToken='';
    sessionStorage.removeItem('adminToken');
    return false;
  }}
}}

async function loadProducts(){{
  const res=await fetch('/api/products');
  if(!res.ok)throw new Error('Erreur');
  products=await res.json();
}}

function getCartCount(){{
  return cart.reduce((sum,item)=>sum+item.quantity,0);
}}

function getCartTotal(){{
  return cart.reduce((sum,item)=>{{
    const product=products.find(p=>p.id===item.product_id);
    return sum+(product?product.price*item.quantity:0);
  }},0);
}}

function calculateShippingFee(){{
  const shippingType=document.getElementById('shipping-type').value;
  const subtotal=getCartTotal();
  
  if(shippingType==='postal'){{
    return 10;
  }}else if(shippingType==='express'){{
    if(calculatedDistance<=0)return 0;
    const baseFee=(calculatedDistance*2)+(subtotal*0.03);
    return Math.ceil(baseFee/10)*10;
  }}
  return 0;
}}

async function handleShippingChange(){{
  const shippingType=document.getElementById('shipping-type').value;
  const expressInfo=document.getElementById('express-info');
  const distanceResult=document.getElementById('distance-result');
  
  if(shippingType==='express'){{
    expressInfo.style.display='block';
    
    const address=document.getElementById('customer-address').value.trim();
    
    if(address.length>=15){{
      await calculateDistance(address);
    }}else{{
      distanceResult.style.display='none';
      alert('Veuillez entrer une adresse complète (min 15 caractères)');
      document.getElementById('shipping-type').value='';
    }}
  }}else{{
    expressInfo.style.display='none';
    distanceResult.style.display='none';
    calculatedDistance=0;
  }}
  
  updateCheckoutTotal();
}}

async function calculateDistance(address){{
  const distanceResult=document.getElementById('distance-result');
  const distanceDetail=document.getElementById('distance-detail');
  
  try{{
    distanceDetail.innerHTML='<p style="margin:0; color:#666;">⏳ Calcul en cours...</p>';
    distanceResult.style.display='block';
    
    const res=await fetch('/api/calculate-distance',{{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{address}})
    }});
    
    const data=await res.json();
    
    if(res.ok && data.success){{
      calculatedDistance=data.distance_km;
      
      distanceDetail.innerHTML=`
        <p style="margin:0; color:#2e7d32;"><strong>✅ Distance: ${{calculatedDistance}} km</strong></p>
      `;
      
      updateCheckoutTotal();
    }}else{{
      calculatedDistance=0;
      distanceDetail.innerHTML=`<p style="margin:0; color:#d32f2f;">❌ ${{data.error || 'Erreur'}}</p>`;
      document.getElementById('shipping-type').value='';
    }}
  }}catch(e){{
    calculatedDistance=0;
    distanceDetail.innerHTML='<p style="margin:0; color:#d32f2f;">❌ Erreur connexion</p>';
    document.getElementById('shipping-type').value='';
  }}
}}

function updateCheckoutTotal(){{
  const subtotal=getCartTotal();
  const shippingFee=calculateShippingFee();
  const total=subtotal+shippingFee;
  
  document.getElementById('checkout-total').innerHTML=`
    <div>Sous-total: ${{subtotal.toFixed(2)}}€</div>
    <div>Livraison: ${{shippingFee.toFixed(2)}}€</div>
    <h2>${{total.toFixed(2)}} €</h2>
    <p>${{getCartCount()}} article(s)</p>
  `;
}}

function addToCart(productId){{
  const product=products.find(p=>p.id===productId);
  if(!product)return;
  const existing=cart.find(item=>item.product_id===productId);
  if(existing){{
    if(existing.quantity<product.stock){{
      existing.quantity++;
    }}else{{
      alert('Stock insuffisant');
      return;
    }}
  }}else{{
    cart.push({{product_id:productId,quantity:1}});
  }}
  localStorage.setItem('cart',JSON.stringify(cart));
  render();
  alert('✅ Ajouté au panier');
}}

function updateCartQuantity(productId,change){{
  const item=cart.find(i=>i.product_id===productId);
  const product=products.find(p=>p.id===productId);
  if(!item||!product)return;
  const newQty=item.quantity+change;
  if(newQty<=0){{
    cart=cart.filter(i=>i.product_id!==productId);
  }}else if(newQty<=product.stock){{
    item.quantity=newQty;
  }}else{{
    alert('Stock insuffisant');
    return;
  }}
  localStorage.setItem('cart',JSON.stringify(cart));
  showCart();
}}

function removeFromCart(productId){{
  cart=cart.filter(item=>item.product_id!==productId);
  localStorage.setItem('cart',JSON.stringify(cart));
  showCart();
}}

function showCart(){{
  const modal=document.getElementById('cart-modal');
  const itemsDiv=document.getElementById('cart-items');
  const totalDiv=document.getElementById('cart-total');
  if(cart.length===0){{
    itemsDiv.innerHTML='<p style="text-align:center;padding:40px;color:#999;">Panier vide</p>';
    totalDiv.innerHTML='';
  }}else{{
    itemsDiv.innerHTML=cart.map(item=>{{
      const product=products.find(p=>p.id===item.product_id);
      if(!product)return '';
      return `<div class="cart-item"><div><strong>${{product.name}}</strong><br><span style="color:#27ae60;">${{product.price}}€</span> x ${{item.quantity}}</div><div><button onclick="updateCartQuantity(${{item.product_id}},-1)">-</button><span style="margin:0 10px;">${{item.quantity}}</span><button onclick="updateCartQuantity(${{item.product_id}},1)">+</button><button class="delete" onclick="removeFromCart(${{item.product_id}})">🗑️</button></div></div>`;
    }}).join('');
    totalDiv.innerHTML=`<h2>${{getCartTotal().toFixed(2)}} €</h2><p>${{getCartCount()}} article(s)</p>`;
  }}
  modal.classList.add('show');
}}

function closeCart(){{
  document.getElementById('cart-modal').classList.remove('show');
}}

function showCheckout(){{
  if(cart.length===0){{
    alert('Panier vide');
    return;
  }}
  document.getElementById('cart-modal').classList.remove('show');
  updateCheckoutTotal();
  document.getElementById('checkout-modal').classList.add('show');
}}

function closeCheckout(){{
  document.getElementById('checkout-modal').classList.remove('show');
  showCart();
}}

async function submitOrder(){{
  const name=document.getElementById('customer-name').value.trim();
  const contact=document.getElementById('customer-contact').value.trim();
  const address=document.getElementById('customer-address').value.trim();
  const shippingType=document.getElementById('shipping-type').value;
  const notes=document.getElementById('customer-notes').value.trim();
  const errorDiv=document.getElementById('checkout-error');
  
  if(!name||!contact){{
    errorDiv.textContent='Nom et contact requis';
    return;
  }}
  
  if(!address||address.length<15){{
    errorDiv.textContent='Adresse complète requise (min 15 caractères)';
    return;
  }}
  
  if(!shippingType){{
    errorDiv.textContent='Type de livraison requis';
    return;
  }}
  
  if(shippingType==='express' && calculatedDistance<=0){{
    errorDiv.textContent='Distance non calculée';
    return;
  }}
  
  const orderData={{
    customer_name:name,
    customer_contact:contact,
    customer_address:address,
    customer_notes:notes,
    shipping_type:shippingType,
    distance_km:shippingType==='express'?calculatedDistance:0,
    items:cart
  }};
  
  try{{
    const res=await fetch('/api/orders',{{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify(orderData)
    }});
    const data=await res.json();
    if(res.ok){{
      cart=[];
      localStorage.removeItem('cart');
      calculatedDistance=0;
      document.getElementById('checkout-modal').classList.remove('show');
      alert(`✅ Commande ${{data.order.order_number}}\\nTotal: ${{data.order.total.toFixed(2)}}€\\n\\nVous serez contacté!`);
      render();
    }}else{{
      errorDiv.textContent=data.error||'Erreur';
    }}
  }}catch(e){{
    errorDiv.textContent='Erreur réseau';
  }}
}}

function render(){{
  const adminControls=document.getElementById('admin-controls');
  const content=document.getElementById('content');
  const cartCount=getCartCount();
  const cartBadge=cartCount>0?`<span class="badge cart">🛒<span class="cart-count">${{cartCount}}</span></span>`:'';
  if(adminToken){{
    adminControls.innerHTML=`<span class="badge">Admin</span><button onclick="showForm()">➕</button><button onclick="logout()">Déconnexion</button>${{cartBadge?`<button onclick="showCart()">${{cartBadge}}</button>`:''}}}`;
  }}else{{
    adminControls.innerHTML=`<button onclick="showLogin()">Admin</button>${{cartBadge?`<button onclick="showCart()">${{cartBadge}}</button>`:''}}}`;
  }}
  if(products.length===0){{
    content.innerHTML='<div class="empty"><h2>📦 Catalogue vide</h2></div>';
  }}else{{
    content.innerHTML=products.map(p=>`<div class="card">${{p.image_url?`<img src="${{p.image_url}}" alt="${{p.name}}">`:''}}}${{p.video_url?`<video src="${{p.video_url}}" controls></video>`:''}}<h3>${{p.name}}</h3>${{p.category?`<p><em>${{p.category}}</em></p>`:''}}<p>${{p.description||''}}</p><p class="price">${{p.price}} €</p><p>Stock: ${{p.stock}}</p>${{p.stock>0?`<button class="success" onclick="addToCart(${{p.id}})">🛒</button>`:'<p style="color:#e74c3c;">Rupture</p>'}}}${{adminToken?`<button onclick="editProduct(${{p.id}})">✏️</button><button class="delete" onclick="deleteProduct(${{p.id}})">🗑️</button>`:''}}</div>`).join('');
  }}
}}

function showLogin(){{
  document.getElementById('login-modal').classList.add('show');
  document.getElementById('login-error').textContent='';
}}

function closeLogin(){{
  document.getElementById('login-modal').classList.remove('show');
}}

async function login(){{
  const password=document.getElementById('password-input').value;
  const errorDiv=document.getElementById('login-error');
  try{{
    const res=await fetch('/api/admin/login',{{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{password}})
    }});
    const data=await res.json();
    if(res.ok&&data.token){{
      adminToken=data.token;
      sessionStorage.setItem('adminToken',adminToken);
      closeLogin();
      render();
      alert('✅ Connecté');
    }}else{{
      errorDiv.textContent=data.error||'Erreur';
    }}
  }}catch(e){{
    errorDiv.textContent='Erreur réseau';
  }}
}}

async function logout(){{
  await fetch('/api/admin/logout',{{
    method:'POST',
    headers:{{'X-Admin-Token':adminToken}}
  }});
  adminToken='';
  sessionStorage.removeItem('adminToken');
  render();
}}

function showForm(){{
  editingProduct=null;
  currentImageUrl='';
  currentVideoUrl='';
  document.getElementById('form-title').textContent='Nouveau produit';
  document.getElementById('name').value='';
  document.getElementById('price').value='';
  document.getElementById('category').value='';
  document.getElementById('stock').value='';
  document.getElementById('description').value='';
  document.getElementById('file-input').value='';
  document.getElementById('file-status').innerHTML='';
  document.getElementById('form-modal').classList.add('show');
}}

function editProduct(id){{
  const product=products.find(p=>p.id===id);
  if(!product)return;
  editingProduct=product;
  currentImageUrl=product.image_url||'';
  currentVideoUrl=product.video_url||'';
  document.getElementById('form-title').textContent='Modifier';
  document.getElementById('name').value=product.name;
  document.getElementById('price').value=product.price;
  document.getElementById('category').value=product.category||'';
  document.getElementById('stock').value=product.stock;
  document.getElementById('description').value=product.description||'';
  document.getElementById('file-status').innerHTML=(currentImageUrl||currentVideoUrl)?'<p style="color:green">✓ Fichier existant</p>':'';
  document.getElementById('form-modal').classList.add('show');
}}

function closeForm(){{
  document.getElementById('form-modal').classList.remove('show');
}}

document.getElementById('file-input').addEventListener('change',async function(e){{
  const file=e.target.files[0];
  if(!file)return;
  const fd=new FormData();
  fd.append('file',file);
  document.getElementById('file-status').innerHTML='<p>⏳ Upload...</p>';
  try{{
    const res=await fetch('/api/upload',{{
      method:'POST',
      headers:{{'X-Admin-Token':adminToken}},
      body:fd
    }});
    const data=await res.json();
    if(data.url){{
      if(file.type.startsWith('video')){{
        currentVideoUrl=data.url;
        currentImageUrl='';
      }}else{{
        currentImageUrl=data.url;
        currentVideoUrl='';
      }}
      document.getElementById('file-status').innerHTML='<p style="color:green">✅ Uploadé</p>';
    }}else{{
      alert('Erreur upload');
      document.getElementById('file-status').innerHTML='';
    }}
  }}catch(e){{
    alert('Erreur');
    document.getElementById('file-status').innerHTML='';
  }}
}});

async function saveProduct(){{
  const name=document.getElementById('name').value;
  const price=document.getElementById('price').value;
  if(!name||!price){{
    alert('Nom et prix requis');
    return;
  }}
  const data={{
    name,
    price:parseFloat(price),
    category:document.getElementById('category').value,
    stock:parseInt(document.getElementById('stock').value)||0,
    description:document.getElementById('description').value,
    image_url:currentImageUrl,
    video_url:currentVideoUrl
  }};
  const url=editingProduct?`/api/admin/products/${{editingProduct.id}}`:'/api/admin/products';
  const method=editingProduct?'PUT':'POST';
  try{{
    const res=await fetch(url,{{
      method,
      headers:{{'Content-Type':'application/json','X-Admin-Token':adminToken}},
      body:JSON.stringify(data)
    }});
    if(res.ok){{
      closeForm();
      await loadProducts();
      render();
      alert('✅ Sauvegardé');
    }}else{{
      const err=await res.json();
      alert('Erreur: '+(err.error||''));
    }}
  }}catch(e){{
    alert('Erreur');
  }}
}}

async function deleteProduct(id){{
  if(!confirm('Supprimer?'))return;
  try{{
    const res=await fetch(`/api/admin/products/${{id}}`,{{
      method:'DELETE',
      headers:{{'X-Admin-Token':adminToken}}
    }});
    if(res.ok){{
      await loadProducts();
      render();
      alert('✅ Supprimé');
    }}
  }}catch(e){{
    alert('Erreur');
  }}
}}

document.querySelectorAll('.modal').forEach(modal=>{{
  modal.addEventListener('click',e=>{{
    if(e.target===modal)modal.classList.remove('show');
  }});
}});

init();
</script>
</body>
</html>'''
        return html, 200
    except Exception as e:
        logger.error(f"Erreur route catalogue: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return "Erreur serveur", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.warning(f"Démarrage sur le port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
