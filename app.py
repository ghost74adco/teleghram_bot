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
app.secret_key = os.environ.get('SECRET_KEY', 'change_this_secret_key_in_production')
CORS(app, supports_credentials=True, origins=['*'])

app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

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
                return json.load(f)
        except:
            return []
    return []

def save_products(products):
    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

products = load_products()

def require_admin(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get('admin_logged_in'):
            return f(*args, **kwargs)
        return jsonify({'error': 'Non autorisé'}), 403
    return wrapped

@app.route('/')
def index():
    return jsonify({'status': 'ok', 'message': 'API active'}), 200

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200

@app.route('/api/admin/login', methods=['POST'])
def api_login():
    data = request.json or {}
    if data.get('password') == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'error': 'Mot de passe incorrect'}), 403

@app.route('/api/admin/logout', methods=['POST'])
def api_logout():
    session.pop('admin_logged_in', None)
    return jsonify({'success': True})

@app.route('/api/admin/check', methods=['GET'])
def api_check_admin():
    return jsonify({'admin': session.get('admin_logged_in', False)})

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
        return jsonify({'error': str(e)}), 500

@app.route('/api/products', methods=['GET'])
def get_products():
    return jsonify(products)

@app.route('/api/admin/products', methods=['POST'])
@require_admin
def add_product():
    global products
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

@app.route('/api/admin/products/<int:pid>', methods=['PUT'])
@require_admin
def update_product(pid):
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

@app.route('/api/admin/products/<int:pid>', methods=['DELETE'])
@require_admin
def delete_product(pid):
    global products
    before = len(products)
    products = [p for p in products if p['id'] != pid]
    if len(products) < before:
        save_products(products)
        return jsonify({'success': True})
    return jsonify({'error': 'Produit non trouvé'}), 404

@app.route('/catalogue')
def catalogue():
    logger.info("📄 Chargement catalogue")
    html = '''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Mon Catalogue</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
  padding: 15px;
}
.container {
  max-width: 800px;
  margin: 0 auto;
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
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
button {
  background: #667eea;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  margin: 5px;
}
button:hover { background: #5568d3; }
button.delete { background: #e74c3c; }
button.delete:hover { background: #c0392b; }
input, textarea {
  width: 100%;
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
  width: 100%;
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
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
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
  max-width: 400px;
  width: 90%;
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
.loading { text-align: center; padding: 40px; color: #666; }
.empty { text-align: center; padding: 60px 20px; color: #999; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🛍️ Mon Catalogue</h1>
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

async function init() {
  try {
    await checkAdmin();
    await loadProducts();
    render();
  } catch (e) {
    console.error(e);
    document.getElementById('content').innerHTML = '<div class="empty">Erreur de chargement</div>';
  }
}

async function checkAdmin() {
  const res = await fetch('/api/admin/check', { credentials: 'same-origin' });
  const data = await res.json();
  isAdmin = data.admin;
}

async function loadProducts() {
  const res = await fetch('/api/products');
  products = await res.json();
}

function render() {
  const adminControls = document.getElementById('admin-controls');
  const content = document.getElementById('content');
  
  if (isAdmin) {
    adminControls.innerHTML = '<span class="badge">Admin</span><button onclick="showForm()">➕ Ajouter</button><button onclick="logout()">Déconnexion</button>';
  } else {
    adminControls.innerHTML = '<button onclick="showLogin()">Mode Admin</button>';
  }
  
  if (products.length === 0) {
    content.innerHTML = '<div class="empty"><h2>📦 Catalogue vide</h2></div>';
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
        ${isAdmin ? `
          <button onclick="editProduct(${p.id})">✏️ Modifier</button>
          <button class="delete" onclick="deleteProduct(${p.id})">🗑️ Supprimer</button>
        ` : ''}
      </div>
    `).join('');
  }
}

function showLogin() {
  document.getElementById('login-modal').classList.add('show');
}

function closeLogin() {
  document.getElementById('login-modal').classList.remove('show');
}

async function login() {
  const password = document.getElementById('password-input').value;
  const res = await fetch('/api/admin/login', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password })
  });
  if (res.ok) {
    isAdmin = true;
    closeLogin();
    render();
    alert('✅ Connecté');
  } else {
    alert('❌ Mot de passe incorrect');
  }
}

async function logout() {
  await fetch('/api/admin/logout', { method: 'POST', credentials: 'same-origin' });
  isAdmin = false;
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
      credentials: 'same-origin',
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
      alert('Erreur upload');
      document.getElementById('file-status').innerHTML = '';
    }
  } catch (e) {
    alert('Erreur upload');
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
  
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  
  if (res.ok) {
    closeForm();
    await loadProducts();
    render();
    alert('✅ Sauvegardé');
  } else {
    alert('Erreur');
  }
}

async function deleteProduct(id) {
  if (!confirm('Supprimer ce produit ?')) return;
  
  const res = await fetch(`/api/admin/products/${id}`, {
    method: 'DELETE',
    credentials: 'same-origin'
  });
  
  if (res.ok) {
    await loadProducts();
    render();
    alert('✅ Supprimé');
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
</html>'''
    return html, 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Démarrage sur le port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
