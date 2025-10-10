from flask import Flask, request, jsonify, session
from dotenv import load_dotenv
from functools import wraps
import os, json, hmac, hashlib, cloudinary, cloudinary.uploader

# ----------------------------
# Configuration
# ----------------------------
load_dotenv('infos.env')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change_this_secret_key_in_production')
app.config['SESSION_TYPE'] = 'filesystem'

BOT_TOKEN = os.environ.get('BOT_TOKEN', os.environ.get('TELEGRAM_TOKEN', ''))
ADMIN_USER_IDS = [int(i) for i in os.environ.get('ADMIN_USER_IDS', '').split(',') if i.strip()]
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# Cloudinary
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

PRODUCTS_FILE = 'products.json'
BACKGROUND_IMAGE = os.environ.get('BACKGROUND_IMAGE', '')

# ----------------------------
# Products helpers
# ----------------------------
def load_products():
    if os.path.exists(PRODUCTS_FILE):
        try:
            with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Erreur lors du chargement des produits: {e}")
            return []
    return []

def save_products(products):
    try:
        with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(products, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des produits: {e}")

products = load_products()

# ----------------------------
# Telegram WebApp verification
# ----------------------------
def verify_telegram_auth(init_data):
    if not BOT_TOKEN or not init_data:
        return False
    try:
        parsed = dict(item.split('=', 1) for item in init_data.split('&') if '=' in item)
        received_hash = parsed.pop('hash', '')
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(calculated_hash, received_hash)
    except Exception as e:
        print(f"Erreur vérification Telegram: {e}")
        return False

def is_admin_via_telegram(init_data):
    try:
        parsed = dict(item.split('=', 1) for item in init_data.split('&') if '=' in item)
        user_json = parsed.get('user', '{}')
        user = json.loads(user_json)
        return int(user.get('id', -1)) in ADMIN_USER_IDS
    except Exception as e:
        print(f"Erreur vérification admin Telegram: {e}")
        return False

# ----------------------------
# Décorateur require_admin
# ----------------------------
def require_admin(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get('admin_logged_in'):
            return f(*args, **kwargs)
        init_data = request.headers.get('X-Telegram-Init-Data', '')
        if init_data and verify_telegram_auth(init_data) and is_admin_via_telegram(init_data):
            return f(*args, **kwargs)
        return jsonify({'error': 'Non autorisé'}), 403
    return wrapped

# ----------------------------
# Auth routes
# ----------------------------
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
    if session.get('admin_logged_in'):
        return jsonify({'admin': True})
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    if init_data and verify_telegram_auth(init_data) and is_admin_via_telegram(init_data):
        return jsonify({'admin': True})
    return jsonify({'admin': False})

# ----------------------------
# Upload Cloudinary
# ----------------------------
@app.route('/api/upload', methods=['POST'])
@require_admin
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier reçu'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400
    try:
        result = cloudinary.uploader.upload(file, resource_type='auto', folder='catalogue')
        return jsonify({'url': result.get('secure_url')}), 200
    except Exception as e:
        print(f"Erreur upload Cloudinary: {e}")
        return jsonify({'error': str(e)}), 500

# ----------------------------
# CRUD Produits
# ----------------------------
@app.route('/api/products', methods=['GET'])
def get_products():
    return jsonify(products)

@app.route('/api/admin/products', methods=['POST'])
@require_admin
def add_product():
    data = request.json or {}
    if not data.get('name') or (str(data.get('price', '')).strip() == ''):
        return jsonify({'error': 'Nom et prix requis'}), 400
    try:
        new_product = {
            "id": max([p["id"] for p in products]) + 1 if products else 1,
            "name": data.get("name"),
            "price": float(data.get("price", 0)),
            "description": data.get("description", ""),
            "category": data.get("category", "Sans catégorie"),
            "image_url": data.get("image_url", ""),
            "video_url": data.get("video_url", ""),
            "stock": int(data.get("stock", 0))
        }
        products.append(new_product)
        save_products(products)
        return jsonify(new_product), 201
    except Exception as e:
        print(f"Erreur ajout produit: {e}")
        return jsonify({'error': 'Erreur lors de l\'ajout du produit'}), 500

@app.route('/api/admin/products/<int:pid>', methods=['PUT'])
@require_admin
def update_product(pid):
    data = request.json or {}
    for p in products:
        if p['id'] == pid:
            try:
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
            except Exception as e:
                print(f"Erreur mise à jour produit: {e}")
                return jsonify({'error': 'Erreur lors de la mise à jour'}), 500
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

# ----------------------------
# Frontend HTML
# ----------------------------
def get_html():
    bg_style = f"url('{BACKGROUND_IMAGE}') no-repeat center center fixed" if BACKGROUND_IMAGE else "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
    
    return '''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Catalogue Produits</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
  background: ''' + bg_style + ''';
  background-size: cover;
  color: #fff;
  min-height: 100vh;
  padding: 20px;
}
.container {
  background: rgba(0,0,0,0.7);
  backdrop-filter: blur(10px);
  border-radius: 16px;
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 10px;
}
h1 { font-size: 24px; }
button {
  background: #ffcc00;
  color: #000;
  border: none;
  padding: 10px 15px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: bold;
  margin-right: 5px;
  margin-bottom: 5px;
  transition: all 0.3s ease;
}
button:hover {
  background: #ffd633;
  transform: translateY(-2px);
}
button.secondary {
  background: #666;
  color: #fff;
}
button.secondary:hover { background: #777; }
input, textarea {
  width: 100%;
  margin: 8px 0;
  padding: 10px;
  border-radius: 6px;
  border: 2px solid #ddd;
  font-size: 14px;
}
.card {
  background: rgba(255,255,255,0.95);
  color: #000;
  border-radius: 12px;
  margin: 15px 0;
  padding: 15px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.card img, .card video {
  width: 100%;
  max-height: 300px;
  object-fit: cover;
  border-radius: 8px;
  margin-bottom: 10px;
}
.badge {
  background: #4CAF50;
  color: white;
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: bold;
}
.modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0,0,0,0.8);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal.show { display: flex; }
.modal-content {
  background: white;
  color: black;
  padding: 30px;
  border-radius: 12px;
  max-width: 400px;
  width: 90%;
}
.empty { text-align: center; padding: 60px 20px; }
.loading { text-align: center; padding: 40px; font-size: 18px; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🛍️ Mon Catalogue</h1>
    <div id="admin-controls"></div>
  </div>
  <div id="content" class="loading">⏳ Chargement...</div>
</div>

<div id="login-modal" class="modal">
  <div class="modal-content">
    <h2>🔐 Connexion Admin</h2>
    <input type="password" id="password-input" placeholder="Mot de passe">
    <button onclick="login()">Se connecter</button>
    <button class="secondary" onclick="closeLogin()">Annuler</button>
  </div>
</div>

<div id="form-modal" class="modal">
  <div class="modal-content">
    <h3 id="form-title">➕ Nouveau produit</h3>
    <input type="text" id="name" placeholder="Nom du produit *">
    <input type="number" id="price" step="0.01" placeholder="Prix (€) *">
    <input type="text" id="category" placeholder="Catégorie">
    <input type="number" id="stock" placeholder="Stock">
    <textarea id="description" rows="4" placeholder="Description"></textarea>
    <input type="file" id="file-input" accept="image/*,video/*">
    <div id="file-status"></div>
    <button onclick="saveProduct()">💾 Sauvegarder</button>
    <button class="secondary" onclick="closeForm()">❌ Annuler</button>
  </div>
</div>

<script>
console.log('=== SCRIPT START ===');
const tg = window.Telegram && window.Telegram.WebApp;
let isAdmin = false;
let products = [];
let editingProduct = null;
let currentImageUrl = '';
let currentVideoUrl = '';

if (tg) {
  console.log('Telegram WebApp détecté');
  tg.ready();
  tg.expand();
}

async function init() {
  console.log('Init...');
  await checkAdmin();
  await loadProducts();
  render();
  console.log('Init terminé');
}

async function checkAdmin() {
  try {
    const res = await fetch('/api/admin/check', {
      credentials: 'same-origin',
      headers: { 'X-Telegram-Init-Data': tg ? (tg.initData || '') : '' }
    });
    const data = await res.json();
    isAdmin = data.admin;
    console.log('Admin:', isAdmin);
  } catch (e) {
    console.error('Erreur check admin:', e);
    isAdmin = false;
  }
}

async function loadProducts() {
  try {
    const res = await fetch('/api/products');
    products = await res.json();
    console.log('Produits chargés:', products.length);
  } catch (e) {
    console.error('Erreur chargement:', e);
    alert('Erreur lors du chargement des produits');
  }
}

function render() {
  console.log('Render...');
  const adminControls = document.getElementById('admin-controls');
  const content = document.getElementById('content');
  
  if (isAdmin) {
    adminControls.innerHTML = '<span class="badge">👑 Admin</span><button onclick="showForm()">➕ Ajouter</button><button class="secondary" onclick="logout()">🚪 Déconnexion</button>';
  } else {
    adminControls.innerHTML = '<button onclick="showLogin()">🔑 Mode Admin</button>';
  }
  
  if (products.length === 0) {
    content.innerHTML = '<div class="empty"><h2>📦 Catalogue vide</h2><p>Aucun produit disponible</p></div>';
  } else {
    content.innerHTML = products.map(p => '<div class="card">' +
      (p.image_url ? '<img src="' + p.image_url + '" alt="' + p.name + '">' : '') +
      (p.video_url ? '<video src="' + p.video_url + '" controls></video>' : '') +
      '<h3>' + p.name + '</h3>' +
      (p.category ? '<p><em>📁 ' + p.category + '</em></p>' : '') +
      (p.description ? '<p>' + p.description + '</p>' : '') +
      '<p><strong style="font-size: 24px; color: #4CAF50;">' + p.price + ' €</strong></p>' +
      '<p><em>📦 Stock : ' + p.stock + '</em></p>' +
      (isAdmin ? '<button onclick="editProduct(' + p.id + ')">✏️ Modifier</button><button class="secondary" onclick="deleteProduct(' + p.id + ')">🗑️ Supprimer</button>' : '') +
      '</div>').join('');
  }
  console.log('Render terminé');
}

function showLogin() {
  document.getElementById('login-modal').classList.add('show');
}

function closeLogin() {
  document.getElementById('login-modal').classList.remove('show');
  document.getElementById('password-input').value = '';
}

async function login() {
  const password = document.getElementById('password-input').value;
  if (!password) {
    alert('Entrez un mot de passe');
    return;
  }
  try {
    const res = await fetch('/api/admin/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: password })
    });
    if (res.ok) {
      isAdmin = true;
      closeLogin();
      render();
      alert('✅ Connexion réussie !');
    } else {
      const data = await res.json();
      alert(data.error || 'Erreur');
    }
  } catch (e) {
    console.error('Erreur login:', e);
    alert('Erreur de connexion');
  }
}

async function logout() {
  try {
    await fetch('/api/admin/logout', {
      method: 'POST',
      credentials: 'same-origin'
    });
    isAdmin = false;
    render();
    alert('👋 Déconnexion réussie');
  } catch (e) {
    console.error('Erreur logout:', e);
  }
}

function showForm() {
  editingProduct = null;
  currentImageUrl = '';
  currentVideoUrl = '';
  document.getElementById('form-title').textContent = '➕ Nouveau produit';
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
  const product = products.find(function(p) { return p.id === id; });
  if (!product) return;
  
  editingProduct = product;
  currentImageUrl = product.image_url || '';
  currentVideoUrl = product.video_url || '';
  
  document.getElementById('form-title').textContent = '✏️ Modifier le produit';
  document.getElementById('name').value = product.name;
  document.getElementById('price').value = product.price;
  document.getElementById('category').value = product.category || '';
  document.getElementById('stock').value = product.stock;
  document.getElementById('description').value = product.description || '';
  document.getElementById('file-input').value = '';
  document.getElementById('file-status').innerHTML = (currentImageUrl || currentVideoUrl) ? '<p style="color:green">✓ Fichier existant</p>' : '';
  document.getElementById('form-modal').classList.add('show');
}

function closeForm() {
  document.getElementById('form-modal').classList.remove('show');
  editingProduct = null;
}

document.getElementById('file-input').addEventListener('change', async function(e) {
  const file = e.target.files[0];
  if (!file) return;
  
  if (file.size > 10 * 1024 * 1024) {
    alert('⚠️ Fichier trop volumineux (max 10MB)');
    return;
  }
  
  const fd = new FormData();
  fd.append('file', file);
  
  document.getElementById('file-status').innerHTML = '<p>⏳ Upload en cours...</p>';
  
  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-Telegram-Init-Data': tg ? (tg.initData || '') : '' },
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
      document.getElementById('file-status').innerHTML = '<p style="color:green">✅ Fichier uploadé !</p>';
    } else {
      alert(data.error || 'Erreur upload');
      document.getElementById('file-status').innerHTML = '';
    }
  } catch (e) {
    console.error('Erreur upload:', e);
    alert('Erreur lors de l\'upload');
    document.getElementById('file-status').innerHTML = '';
  }
});

async function saveProduct() {
  const name = document.getElementById('name').value;
  const price = document.getElementById('price').value;
  const category = document.getElementById('category').value;
  const stock = document.getElementById('stock').value;
  const description = document.getElementById('description').value;
  
  if (!name || !price) {
    alert('⚠️ Nom et prix requis');
    return;
  }
  
  const data = {
    name: name,
    price: parseFloat(price),
    category: category,
    stock: parseInt(stock) || 0,
    description: description,
    image_url: currentImageUrl,
    video_url: currentVideoUrl
  };
  
  try {
    const url = editingProduct ? '/api/admin/products/' + editingProduct.id : '/api/admin/products';
    const method = editingProduct ? 'PUT' : 'POST';
    
    const res = await fetch(url, {
      method: method,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-Telegram-Init-Data': tg ? (tg.initData || '') : ''
      },
      body: JSON.stringify(data)
    });
    
    if (res.ok) {
      closeForm();
      await loadProducts();
      render();
      alert('✅ Produit sauvegardé !');
    } else {
      const err = await res.json();
      alert(err.error || 'Erreur');
    }
  } catch (e) {
    console.error('Erreur save:', e);
    alert('Erreur lors de la sauvegarde');
  }
}

async function deleteProduct(id) {
  if (!confirm('🗑️ Supprimer ce produit ?')) return;
  
  try {
    const res = await fetch('/api/admin/products/' + id, {
      method: 'DELETE',
      credentials: 'same-origin',
      headers: { 'X-Telegram-Init-Data': tg ? (tg.initData || '') : '' }
    });
    
    if (res.ok) {
      await loadProducts();
      render();
      alert('✅ Produit supprimé');
    } else {
      alert('Erreur lors de la suppression');
    }
  } catch (e) {
    console.error('Erreur delete:', e);
    alert('Erreur lors de la suppression');
  }
}

document.querySelectorAll('.modal').forEach(function(modal) {
  modal.addEventListener('click', function(e) {
    if (e.target === modal) {
      modal.classList.remove('show');
    }
  });
});

console.log('Appel de init()...');
init();
console.log('=== SCRIPT END ===');
</script>
</body>
</html>'''

@app.route('/')
@app.route('/catalogue')
def catalogue():
    return get_html()

# ----------------------------
# Run
# ----------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Starting app on port", port)
    app.run(host='0.0.0.0', port=port, debug=False)
