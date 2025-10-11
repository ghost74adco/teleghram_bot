from flask import Flask, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv
from functools import wraps
import os, json, cloudinary, cloudinary.uploader
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv('infos.env')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24).hex())
CORS(app, supports_credentials=True, origins=['*'])

app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
# Configuration du fond d'écran
# Pour utiliser Cloudinary : uploadez l'image via l'admin, puis mettez l'URL ici
# Pour le moment, utilisons une image de test
BACKGROUND_IMAGE = 'https://images.unsplash.com/photo-1559827260-dc66d52bef19?w=1920&q=80'

# Fonction pour obtenir l'URL de fond personnalisée
def get_background_url():
    # Vous pouvez stocker l'URL dans une variable d'environnement
    custom_bg = os.environ.get('BACKGROUND_URL')
    return custom_bg if custom_bg else BACKGROUND_IMAGE

try:
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
        secure=True
    )
    logger.info("✅ Cloudinary configuré")
except Exception as e:
    logger.error(f"⚠️ Erreur Cloudinary: {e}")

PRODUCTS_FILE = 'products.json'

def load_products():
    if os.path.exists(PRODUCTS_FILE):
        try:
            with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"Erreur lecture products.json: {e}")
            return []
    else:
        save_products([])
        return []

def save_products(products):
    try:
        with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(products, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erreur sauvegarde products: {e}")

try:
    products = load_products()
    logger.info(f"✅ {len(products)} produits chargés")
except Exception as e:
    logger.error(f"❌ Erreur chargement produits: {e}")
    products = []

def require_admin(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            if session.get('admin_logged_in'):
                return f(*args, **kwargs)
        except:
            pass
        return jsonify({'error': 'Non autorisé'}), 403
    return wrapped

@app.route('/')
def index():
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
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
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
.btn:active {{
  transform: scale(0.98);
}}
.api-status {{
  margin-top: 40px;
  padding: 15px;
  background: rgba(0,0,0,0.6);
  border-radius: 10px;
  font-size: 0.9em;
  backdrop-filter: blur(10px);
}}
.status-badge {{
  display: inline-block;
  padding: 5px 15px;
  background: #28a745;
  color: white;
  border-radius: 20px;
  font-weight: bold;
  margin-top: 10px;
}}
</style>
</head>
<body>
<div class="container">
  <h1>🏴‍☠️ Carte du Pirate 🏴‍☠️</h1>
  <p class="subtitle">Votre boutique de trésors en ligne</p>
  
  <a href="/catalogue" class="btn">📦 Catalogue du Pirate</a>
  
  <div class="api-status">
    <p>Système API</p>
    <span class="status-badge">✅ Actif</span>
  </div>
</div>
</body>
</html>'''
    return html, 200

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200

@app.route('/api/admin/login', methods=['POST'])
def api_login():
    try:
        data = request.json or {}
        if data.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return jsonify({'success': True})
        return jsonify({'error': 'Mot de passe incorrect'}), 403
    except Exception as e:
        logger.error(f"Erreur login: {e}")
        return jsonify({'error': 'Erreur serveur'}), 500

@app.route('/api/admin/logout', methods=['POST'])
def api_logout():
    try:
        session.pop('admin_logged_in', None)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Erreur logout: {e}")
        return jsonify({'success': False}), 500

@app.route('/api/admin/check', methods=['GET'])
def api_check_admin():
    try:
        is_admin = session.get('admin_logged_in', False)
        return jsonify({'admin': is_admin}), 200
    except Exception as e:
        logger.error(f"Erreur check admin: {e}")
        return jsonify({'admin': False}), 200

@app.route('/api/upload', methods=['POST'])
@require_admin
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier'}), 400
        file = request.files['file']
        result = cloudinary.uploader.upload(file, resource_type='auto', folder='catalogue', timeout=60)
        return jsonify({'url': result.get('secure_url')}), 200
    except Exception as e:
        logger.error(f"Erreur upload: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/products', methods=['GET'])
def get_products():
    try:
        return jsonify(products), 200
    except Exception as e:
        logger.error(f"Erreur GET products: {e}")
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
        save_products(products)
        return jsonify(new_product), 201
    except Exception as e:
        logger.error(f"Erreur add product: {e}")
        return jsonify({'error': str(e)}), 500

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
                save_products(products)
                return jsonify(p)
        return jsonify({'error': 'Produit non trouvé'}), 404
    except Exception as e:
        logger.error(f"Erreur update product: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/products/<int:pid>', methods=['DELETE'])
@require_admin
def delete_product(pid):
    global products
    try:
        before = len(products)
        products = [p for p in products if p['id'] != pid]
        if len(products) < before:
            save_products(products)
            return jsonify({'success': True})
        return jsonify({'error': 'Produit non trouvé'}), 404
    except Exception as e:
        logger.error(f"Erreur delete product: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/catalogue')
def catalogue():
    logger.info("📄 Chargement catalogue")
    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Mon Catalogue</title>
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
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
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
.back-btn {{
  background: #6c757d;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  text-decoration: none;
  display: inline-block;
}}
.back-btn:hover {{ background: #5a6268; }}
button {{
  background: #667eea;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  margin: 5px;
}}
button:hover {{ background: #5568d3; }}
button.delete {{ background: #e74c3c; }}
button.delete:hover {{ background: #c0392b; }}
input, textarea {{
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
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
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
  max-width: 400px;
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
.loading {{ text-align: center; padding: 40px; color: #666; }}
.empty {{ text-align: center; padding: 60px 20px; color: #999; }}
.error {{ text-align: center; padding: 40px; color: #e74c3c; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <a href="/" class="back-btn">← Retour</a>
      <h1 style="display: inline; margin-left: 15px;">🛍️ Mon Catalogue</h1>
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

<script>
let isAdmin = false;
let products = [];
let editingProduct = null;
let currentImageUrl = '';
let currentVideoUrl = '';

async function init() {{
  try {{
    await checkAdmin();
    await loadProducts();
    render();
  }} catch (e) {{
    console.error('Erreur init:', e);
    document.getElementById('content').innerHTML = '<div class="error">❌ Erreur de chargement: ' + e.message + '</div>';
  }}
}}

async function checkAdmin() {{
  try {{
    const res = await fetch('/api/admin/check', {{ credentials: 'same-origin' }});
    if (!res.ok) throw new Error('Erreur check admin');
    const data = await res.json();
    isAdmin = data.admin;
  }} catch (e) {{
    console.error('Erreur checkAdmin:', e);
    isAdmin = false;
  }}
}}

async function loadProducts() {{
  try {{
    const res = await fetch('/api/products');
    if (!res.ok) throw new Error('Erreur chargement produits');
    products = await res.json();
    console.log('Produits chargés:', products.length);
  }} catch (e) {{
    console.error('Erreur loadProducts:', e);
    throw e;
  }}
}}

function render() {{
  const adminControls = document.getElementById('admin-controls');
  const content = document.getElementById('content');
  
  if (isAdmin) {{
    adminControls.innerHTML = '<span class="badge">Admin</span><button onclick="showForm()">➕ Ajouter</button><button onclick="logout()">Déconnexion</button>';
  }} else {{
    adminControls.innerHTML = '<button onclick="showLogin()">Mode Admin</button>';
  }}
  
  if (products.length === 0) {{
    content.innerHTML = '<div class="empty"><h2>📦 Catalogue vide</h2><p>Aucun produit pour le moment</p></div>';
  }} else {{
    content.innerHTML = products.map(p => `
      <div class="card">
        ${{p.image_url ? `<img src="${{p.image_url}}" alt="${{p.name}}">` : ''}}
        ${{p.video_url ? `<video src="${{p.video_url}}" controls></video>` : ''}}
        <h3>${{p.name}}</h3>
        ${{p.category ? `<p><em>${{p.category}}</em></p>` : ''}}
        ${{p.description ? `<p>${{p.description}}</p>` : ''}}
        <p class="price">${{p.price}} €</p>
        <p>Stock : ${{p.stock}}</p>
        ${{isAdmin ? `
          <button onclick="editProduct(${{p.id}})">✏️ Modifier</button>
          <button class="delete" onclick="deleteProduct(${{p.id}})">🗑️ Supprimer</button>
        ` : ''}}
      </div>
    `).join('');
  }}
}}

function showLogin() {{
  document.getElementById('login-modal').classList.add('show');
}}

function closeLogin() {{
  document.getElementById('login-modal').classList.remove('show');
}}

async function login() {{
  const password = document.getElementById('password-input').value;
  try {{
    const res = await fetch('/api/admin/login', {{
      method: 'POST',
      credentials: 'same-origin',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ password }})
    }});
    if (res.ok) {{
      isAdmin = true;
      closeLogin();
      render();
      alert('✅ Connecté');
    }} else {{
      alert('❌ Mot de passe incorrect');
    }}
  }} catch (e) {{
    alert('❌ Erreur de connexion');
  }}
}}

async function logout() {{
  await fetch('/api/admin/logout', {{ method: 'POST', credentials: 'same-origin' }});
  isAdmin = false;
  render();
}}

function showForm() {{
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
}}

function editProduct(id) {{
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
}}

function closeForm() {{
  document.getElementById('form-modal').classList.remove('show');
}}

document.getElementById('file-input').addEventListener('change', async function(e) {{
  const file = e.target.files[0];
  if (!file) return;
  
  const fd = new FormData();
  fd.append('file', file);
  
  document.getElementById('file-status').innerHTML = '<p>⏳ Upload...</p>';
  
  try {{
    const res = await fetch('/api/upload', {{
      method: 'POST',
      credentials: 'same-origin',
      body: fd
    }});
    const data = await res.json();
    if (data.url) {{
      if (file.type.startsWith('video')) {{
        currentVideoUrl = data.url;
        currentImageUrl = '';
      }} else {{
        currentImageUrl = data.url;
        currentVideoUrl = '';
      }}
      document.getElementById('file-status').innerHTML = '<p style="color:green">✅ Uploadé</p>';
    }} else {{
      alert('Erreur upload');
      document.getElementById('file-status').innerHTML = '';
    }}
  }} catch (e) {{
    alert('Erreur upload');
    document.getElementById('file-status').innerHTML = '';
  }}
}});

async function saveProduct() {{
  const name = document.getElementById('name').value;
  const price = document.getElementById('price').value;
  
  if (!name || !price) {{
    alert('Nom et prix requis');
    return;
  }}
  
  const data = {{
    name,
    price: parseFloat(price),
    category: document.getElementById('category').value,
    stock: parseInt(document.getElementById('stock').value) || 0,
    description: document.getElementById('description').value,
    image_url: currentImageUrl,
    video_url: currentVideoUrl
  }};
  
  const url = editingProduct ? `/api/admin/products/${{editingProduct.id}}` : '/api/admin/products';
  const method = editingProduct ? 'PUT' : 'POST';
  
  try {{
    const res = await fetch(url, {{
      method,
      credentials: 'same-origin',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(data)
    }});
    
    if (res.ok) {{
      closeForm();
      await loadProducts();
      render();
      alert('✅ Sauvegardé');
    }} else {{
      alert('Erreur sauvegarde');
    }}
  }} catch (e) {{
    alert('Erreur: ' + e.message);
  }}
}}

async function deleteProduct(id) {{
  if (!confirm('Supprimer ce produit ?')) return;
  
  try {{
    const res = await fetch(`/api/admin/products/${{id}}`, {{
      method: 'DELETE',
      credentials: 'same-origin'
    }});
    
    if (res.ok) {{
      await loadProducts();
      render();
      alert('✅ Supprimé');
    }}
  }} catch (e) {{
    alert('Erreur suppression');
  }}
}}

document.querySelectorAll('.modal').forEach(modal => {{
  modal.addEventListener('click', e => {{
    if (e.target === modal) modal.classList.remove('show');
  }});
}});

init();
</script>
</body>
</html>'''
    return html, 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Démarrage sur le port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
