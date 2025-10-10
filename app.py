from flask import Flask, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv
from functools import wraps
import os, json, hmac, hashlib, cloudinary, cloudinary.uploader

# ----------------------------
# Configuration
# ----------------------------
load_dotenv('infos.env')

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = os.environ.get('SECRET_KEY', 'change_this_secret_key_in_production')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True

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
# Frontend HTML (React)
# ----------------------------
BACKGROUND_URL = "https://res.cloudinary.com/dfhrrtzsd/image/upload/v1760118433/ChatGPT_Image_8_oct._2025_03_01_21_zm5zfy.png"

@app.route('/')
@app.route('/catalogue')
def catalogue():
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Catalogue Produits</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
  background: url('{BACKGROUND_URL}') no-repeat center center fixed;
  background-size: cover;
  margin: 0;
  padding: 0;
  color: #fff;
}}
.container {{
  background: rgba(0,0,0,0.6);
  backdrop-filter: blur(6px);
  border-radius: 16px;
  padding: 20px;
  margin: 20px auto;
  max-width: 800px;
  min-height: 90vh;
}}
button {{
  background: #ffcc00;
  color: #000;
  border: none;
  padding: 10px 15px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: bold;
  margin-right: 10px;
  margin-bottom: 10px;
}}
button:hover {{ background: #ffd633; }}
button.secondary {{
  background: #666;
  color: #fff;
}}
button.secondary:hover {{ background: #777; }}
input, textarea {{
  width: 100%;
  margin: 5px 0;
  padding: 8px;
  border-radius: 6px;
  border: none;
  box-sizing: border-box;
}}
.card {{
  background: rgba(255,255,255,0.9);
  color: #000;
  border-radius: 12px;
  margin: 10px 0;
  padding: 15px;
}}
.card img, .card video {{
  width: 100%;
  max-height: 300px;
  object-fit: cover;
  border-radius: 8px;
  margin-bottom: 10px;
}}
.login-form {{
  background: rgba(255,255,255,0.95);
  color: #000;
  border-radius: 12px;
  padding: 20px;
  max-width: 400px;
  margin: 50px auto;
}}
.admin-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
}}
.badge {{
  background: #4CAF50;
  color: white;
  padding: 5px 10px;
  border-radius: 5px;
  font-size: 12px;
}}
</style>
</head>
<body>
<div id="root"></div>
<script type="text/babel">
const {{useState, useEffect}} = React;
const tg = window.Telegram?.WebApp;

function App() {{
  const [products, setProducts] = useState([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [showLogin, setShowLogin] = useState(false);
  const [password, setPassword] = useState('');
  const [formData, setFormData] = useState({{
    name: '',
    price: '',
    description: '',
    category: '',
    stock: '',
    image_url: '',
    video_url: ''
  }});
  const [showForm, setShowForm] = useState(false);
  const [edit, setEdit] = useState(null);

  useEffect(() => {{
    if (tg) {{
      tg.ready();
      tg.expand();
    }}
    load();
    check();
  }}, []);

  const headers = () => ({{
    'Content-Type': 'application/json',
    'X-Telegram-Init-Data': tg?.initData || ''
  }});

  async function load() {{
    try {{
      const res = await fetch('/api/products');
      const data = await res.json();
      setProducts(data);
    }} catch (e) {{
      console.error('Erreur chargement produits:', e);
    }}
  }}

  async function check() {{
    try {{
      const res = await fetch('/api/admin/check', {{
        headers: headers(),
        credentials: 'include'
      }});
      const data = await res.json();
      setIsAdmin(data.admin);
    }} catch (e) {{
      console.error('Erreur vérification admin:', e);
      setIsAdmin(false);
    }}
  }}

  async function login() {{
    if (!password) {{
      alert('Veuillez entrer un mot de passe');
      return;
    }}
    try {{
      const res = await fetch('/api/admin/login', {{
        method: 'POST',
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify({{ password }})
      }});
      const data = await res.json();
      if (res.ok) {{
        setIsAdmin(true);
        setShowLogin(false);
        setPassword('');
        alert('Connexion réussie !');
      }} else {{
        alert(data.error || 'Erreur de connexion');
      }}
    }} catch (e) {{
      console.error('Erreur login:', e);
      alert('Erreur de connexion');
    }}
  }}

  async function logout() {{
    try {{
      await fetch('/api/admin/logout', {{
        method: 'POST',
        headers: headers(),
        credentials: 'include'
      }});
      setIsAdmin(false);
      setShowForm(false);
      setShowLogin(false);
      alert('Déconnexion réussie');
    }} catch (e) {{
      console.error('Erreur logout:', e);
    }}
  }}

  async function save() {{
    if (!formData.name || !formData.price) {{
      alert('Nom et prix requis');
      return;
    }}
    try {{
      const url = edit ? `/api/admin/products/${{edit.id}}` : '/api/admin/products';
      const method = edit ? 'PUT' : 'POST';
      const res = await fetch(url, {{
        method,
        headers: headers(),
        credentials: 'include',
        body: JSON.stringify(formData)
      }});
      if (res.ok) {{
        setShowForm(false);
        setEdit(null);
        setFormData({{
          name: '',
          price: '',
          description: '',
          category: '',
          stock: '',
          image_url: '',
          video_url: ''
        }});
        await load();
        alert('Produit sauvegardé !');
      }} else {{
        const data = await res.json();
        alert(data.error || 'Erreur lors de la sauvegarde');
      }}
    }} catch (e) {{
      console.error('Erreur sauvegarde:', e);
      alert('Erreur lors de la sauvegarde');
    }}
  }}

  async function del(id) {{
    if (!confirm('Supprimer ce produit ?')) return;
    try {{
      const res = await fetch(`/api/admin/products/${{id}}`, {{
        method: 'DELETE',
        headers: headers(),
        credentials: 'include'
      }});
      if (res.ok) {{
        await load();
        alert('Produit supprimé');
      }} else {{
        alert('Erreur lors de la suppression');
      }}
    }} catch (e) {{
      console.error('Erreur suppression:', e);
      alert('Erreur lors de la suppression');
    }}
  }}

  async function uploadFile(e) {{
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    try {{
      const res = await fetch('/api/upload', {{
        method: 'POST',
        headers: {{ 'X-Telegram-Init-Data': tg?.initData || '' }},
        credentials: 'include',
        body: fd
      }});
      const data = await res.json();
      if (data.url) {{
        if (file.type.startsWith('video')) {{
          setFormData({{ ...formData, video_url: data.url, image_url: '' }});
        }} else {{
          setFormData({{ ...formData, image_url: data.url, video_url: '' }});
        }}
        alert('Fichier uploadé avec succès !');
      }} else {{
        alert(data.error || 'Erreur upload');
      }}
    }} catch (e) {{
      console.error('Erreur upload:', e);
      alert('Erreur lors de l\'upload');
    }}
  }}

  if (showLogin) {{
    return (
      <div className="container">
        <div className="login-form">
          <h2>🔐 Connexion Admin</h2>
          <input
            type="password"
            placeholder="Mot de passe"
            value={{password}}
            onChange={{e => setPassword(e.target.value)}}
            onKeyPress={{e => e.key === 'Enter' && login()}}
          />
          <button onClick={{login}}>Se connecter</button>
          <button className="secondary" onClick={{() => setShowLogin(false)}}>Annuler</button>
        </div>
      </div>
    );
  }}

  return (
    <div className="container">
      <div className="admin-header">
        <h1>🛍️ Mon Catalogue</h1>
        <div>
          {{isAdmin && <span className="badge">👑 Admin</span>}}
          {{!isAdmin && <button onClick={{() => setShowLogin(true)}}>🔑 Mode Admin</button>}}
          {{isAdmin && <button className="secondary" onClick={{logout}}>🚪 Déconnexion</button>}}
        </div>
      </div>

      {{isAdmin && !showForm && (
        <button onClick={{() => {{
          setShowForm(true);
          setEdit(null);
          setFormData({{
            name: '',
            price: '',
            description: '',
            category: '',
            stock: '',
            image_url: '',
            video_url: ''
          }});
        }}}}>
          ➕ Ajouter un produit
        </button>
      )}}

      {{isAdmin && showForm && (
        <div className="card">
          <h3>{{edit ? '✏️ Modifier le produit' : '➕ Nouveau produit'}}</h3>
          <input
            placeholder="Nom du produit"
            value={{formData.name}}
            onChange={{e => setFormData({{ ...formData, name: e.target.value }})}}
          />
          <input
            type="number"
            step="0.01"
            placeholder="Prix (€)"
            value={{formData.price}}
            onChange={{e => setFormData({{ ...formData, price: e.target.value }})}}
          />
          <input
            placeholder="Catégorie"
            value={{formData.category}}
            onChange={{e => setFormData({{ ...formData, category: e.target.value }})}}
          />
          <input
            type="number"
            placeholder="Stock"
            value={{formData.stock}}
            onChange={{e => setFormData({{ ...formData, stock: e.target.value }})}}
          />
          <textarea
            placeholder="Description"
            rows="4"
            value={{formData.description}}
            onChange={{e => setFormData({{ ...formData, description: e.target.value }})}}
          ></textarea>
          <input type="file" accept="image/*,video/*" onChange={{uploadFile}} />
          {{(formData.image_url || formData.video_url) && (
            <p style={{{{color: 'green'}}}}>✓ Fichier chargé</p>
          )}}
          <button onClick={{save}}>💾 Sauvegarder</button>
          <button className="secondary" onClick={{() => {{
            setShowForm(false);
            setEdit(null);
          }}}}>
            ❌ Annuler
          </button>
        </div>
      )}}

      {{products.length === 0 && (
        <div className="card">
          <p style={{{{textAlign: 'center', color: '#666'}}}}>
            Aucun produit disponible pour le moment
          </p>
        </div>
      )}}

      {{products.map(p => (
        <div key={{p.id}} className="card">
          {{p.image_url && <img src={{p.image_url}} alt={{p.name}} />}}
          {{p.video_url && <video src={{p.video_url}} controls />}}
          <h3>{{p.name}}</h3>
          {{p.category && <p><em>📁 {{p.category}}</em></p>}}
          {{p.description && <p>{{p.description}}</p>}}
          <p><strong style={{{{fontSize: '20px', color: '#4CAF50'}}}}>{{p.price}} €</strong></p>
          <p><em>📦 Stock : {{p.stock}}</em></p>
          {{isAdmin && (
            <div>
              <button onClick={{() => {{
                setEdit(p);
                setFormData(p);
                setShowForm(true);
              }}}}>
                ✏️ Modifier
              </button>
              <button className="secondary" onClick={{() => del(p.id)}}>
                🗑️ Supprimer
              </button>
            </div>
          )}}
        </div>
      ))}}
    </div>
  );
}}

ReactDOM.render(<App />, document.getElementById('root'));
</script>
</body>
</html>
"""

# ----------------------------
# Run
# ----------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Starting app on port", port)
    app.run(host='0.0.0.0', port=port, debug=False)
