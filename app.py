# app.py
from flask import Flask, request, jsonify, abort, redirect, session
from dotenv import load_dotenv
from functools import wraps
import os, json, hmac, hashlib, cloudinary, cloudinary.uploader

# ----------------------------
# Configuration
# ----------------------------
load_dotenv('infos.env')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change_this_secret')

# Admin / Telegram
BOT_TOKEN = os.environ.get('BOT_TOKEN') or os.environ.get('TELEGRAM_TOKEN', '')
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
        except Exception:
            return []
    return []

def save_products(products):
    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

products = load_products()

# ----------------------------
# Telegram WebApp verification
# ----------------------------
def verify_telegram_auth(init_data):
    """
    Vérifie la signature Telegram WebApp (init_data string).
    Retourne True si valide et BOT_TOKEN est configuré.
    """
    if not BOT_TOKEN or not init_data:
        return False
    try:
        parsed = dict(item.split('=', 1) for item in init_data.split('&') if '=' in item)
        received_hash = parsed.pop('hash', '')
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(calculated_hash, received_hash)
    except Exception:
        return False

def is_admin_via_telegram(init_data):
    """
    Vérifie si l'user contenu dans init_data est dans ADMIN_USER_IDS.
    """
    try:
        parsed = dict(item.split('=', 1) for item in init_data.split('&') if '=' in item)
        user_json = parsed.get('user', '{}')
        user = json.loads(user_json)
        return int(user.get('id', -1)) in ADMIN_USER_IDS
    except Exception:
        return False

# ----------------------------
# Décorateur require_admin (mot de passe OR Telegram)
# ----------------------------
def require_admin(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        # 1) session admin via password
        if session.get('admin_logged_in'):
            return f(*args, **kwargs)
        # 2) Telegram WebApp header
        init_data = request.headers.get('X-Telegram-Init-Data', '')
        if init_data and verify_telegram_auth(init_data) and is_admin_via_telegram(init_data):
            return f(*args, **kwargs)
        return jsonify({'error': 'Non autorisé'}), 403
    return wrapped

# ----------------------------
# Routes d'authentification via mini-app (mot de passe)
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
    # check both methods
    if session.get('admin_logged_in'):
        return jsonify({'admin': True})
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    if init_data and verify_telegram_auth(init_data) and is_admin_via_telegram(init_data):
        return jsonify({'admin': True})
    return jsonify({'admin': False})

# ----------------------------
# Upload via Cloudinary
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
        return jsonify({'error': str(e)}), 500

# ----------------------------
# API produits CRUD
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

# ----------------------------
# Frontend React HTML (mini-app)
# ----------------------------
# Background image (Cloudinary link you provided)
BACKGROUND_URL = "https://res.cloudinary.com/dfhrrtzsd/image/upload/v1760118433/ChatGPT_Image_8_oct._2025_03_01_21_zm5zfy.png"

# Return HTML as a plain string (do NOT use f-strings with braces in JSX)
@app.route('/')
@app.route('/catalogue')
def frontend():
    html = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Pirates Supply — Catalogue</title>

<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>

<style>
  :root {
    --card-bg: rgba(0,0,0,0.65);
    --accent: #ffcc00;
    --text: #ffffff;
  }
  html,body { height:100%; margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; color:var(--text); }
  body {
    background-image: url('""" + BACKGROUND_URL + """');
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    -webkit-font-smoothing:antialiased;
    -moz-osx-font-smoothing:grayscale;
  }
  .container {
    max-width:1000px;
    margin:28px auto;
    padding:20px;
    background: linear-gradient(rgba(0,0,0,0.45), rgba(0,0,0,0.35));
    border-radius:16px;
    box-shadow:0 8px 30px rgba(0,0,0,0.6);
  }
  header { text-align:center; margin-bottom:18px; }
  h1 { margin:0 0 6px 0; font-size:28px; letter-spacing:1px; }
  .subtitle { opacity:0.85; margin-bottom:12px; }
  .actions { display:flex; gap:8px; justify-content:center; flex-wrap:wrap; margin-bottom:12px; }
  button { background:var(--accent); color:#000; border:none; padding:10px 12px; border-radius:10px; cursor:pointer; font-weight:700; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:14px; }
  .card { background:var(--card-bg); border-radius:12px; padding:12px; overflow:hidden; }
  .card img, .card video { width:100%; height:180px; object-fit:cover; border-radius:8px; display:block; margin-bottom:8px; }
  .meta { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-top:6px; }
  input, textarea { width:100%; padding:8px; border-radius:8px; border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.03); color:var(--text); margin-bottom:8px; }
  .form { background: rgba(255,255,255,0.03); padding:12px; border-radius:12px; margin-bottom:12px; }
  a.link { color:var(--accent); text-decoration:none; font-weight:700; }
  .small-muted { font-size:13px; opacity:0.9; }
</style>
</head>
<body>
  <div id="root"></div>

<script type="text/babel">
const { useState, useEffect } = React;
const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

function App(){
  const [products, setProducts] = useState([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [edit, setEdit] = useState(null);
  const [formData, setFormData] = useState({ name:'', price:0, description:'', category:'', stock:0, image_url:'', video_url:'' });
  const [pw, setPw] = useState('');

  useEffect(() => {
    if (tg) {
      try { tg.ready(); tg.expand(); } catch(e){}
    }
    loadProducts();
    checkAdmin();
  }, []);

  const headersWithTelegram = () => {
    const headers = { 'Content-Type': 'application/json' };
    if (tg && tg.initData) {
      headers['X-Telegram-Init-Data'] = tg.initData;
    }
    return headers;
  };

  async function loadProducts(){
    try {
      const res = await fetch('/api/products');
      const data = await res.json();
      setProducts(data || []);
    } catch(e){
      console.error(e);
    }
  }

  async function checkAdmin(){
    try {
      const hdr = {};
      if (tg && tg.initData) hdr['X-Telegram-Init-Data'] = tg.initData;
      const res = await fetch('/api/admin/check', { headers: hdr });
      const data = await res.json();
      setIsAdmin(!!data.admin);
    } catch(e){
      setIsAdmin(false);
    }
  }

  async function loginWithPassword(){
    try {
      const res = await fetch('/api/admin/login', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ password: pw }) });
      if (res.ok){
        const j = await res.json();
        if (j.success){ setIsAdmin(true); setPw(''); }
      } else {
        alert('Mot de passe incorrect');
      }
    } catch(e){ alert('Erreur'); }
  }

  async function logout(){
    await fetch('/api/admin/logout', { method:'POST' });
    setIsAdmin(false);
  }

  function startAdd(){
    setEdit(null);
    setFormData({ name:'', price:0, description:'', category:'', stock:0, image_url:'', video_url:'' });
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function uploadFile(e){
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    // include Telegram header if present in WebApp
    const headers = {};
    if (tg && tg.initData) headers['X-Telegram-Init-Data'] = tg.initData;
    const res = await fetch('/api/upload', { method:'POST', headers: headers, body: fd });
    const j = await res.json();
    if (j.url){
      if (file.type.startsWith('video')) setFormData({...formData, video_url: j.url, image_url: ''});
      else setFormData({...formData, image_url: j.url, video_url: ''});
    } else {
      alert('Erreur upload');
    }
  }

  async function save(){
    if (!formData.name.trim() || Number(formData.price) <= 0){
      alert('Veuillez renseigner un nom et un prix valide');
      return;
    }
    const url = edit ? `/api/admin/products/${edit.id}` : '/api/admin/products';
    const method = edit ? 'PUT' : 'POST';
    // include Telegram header if present
    const headers = headersWithTelegram();
    const res = await fetch(url, { method, headers, body: JSON.stringify(formData) });
    if (res.ok){
      setShowForm(false); setEdit(null);
      await loadProducts();
    } else {
      const j = await res.json();
      alert(j.error || 'Erreur');
    }
  }

  async function removeProduct(id){
    if (!confirm('Supprimer ce produit ?')) return;
    const headers = headersWithTelegram();
    const res = await fetch(`/api/admin/products/${id}`, { method:'DELETE', headers });
    if (res.ok) loadProducts();
  }

  function startEdit(p){
    setEdit(p);
    setFormData({ ...p });
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  return (
    <div className="container">
      <header>
        <h1>🏴‍☠️ Pirates Supply</h1>
        <div className="subtitle small-muted">Boutique & catalogue — gérer photos, vidéos et prix</div>
        <div className="actions">
          {!isAdmin && (
            <>
              <input type="password" placeholder="Mot de passe admin" value={pw} onChange={e => setPw(e.target.value)} />
              <button onClick={loginWithPassword}>Se connecter</button>
            </>
          )}
          {isAdmin && <button onClick={logout}>🚪 Déconnexion admin</button>}
          {isAdmin && <button onClick={startAdd}>➕ Ajouter un produit</button>}
        </div>
      </header>

      {isAdmin && showForm && (
        <div className="form">
          <input placeholder="Nom" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} />
          <input type="number" placeholder="Prix (€)" value={formData.price} onChange={e => setFormData({...formData, price: e.target.value})} />
          <input placeholder="Catégorie" value={formData.category} onChange={e => setFormData({...formData, category: e.target.value})} />
          <input type="number" placeholder="Stock" value={formData.stock} onChange={e => setFormData({...formData, stock: e.target.value})} />
          <textarea placeholder="Description" value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})} />
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            <input type="file" accept="image/*,video/*" onChange={uploadFile} />
            <div style={{fontSize:13,color:'rgba(255,255,255,0.85)'}}>Uploader une image ou une vidéo (Cloudinary)</div>
          </div>
          <div style={{marginTop:8}}>
            <button onClick={save}>💾 Sauvegarder</button>
            <button onClick={() => { setShowForm(false); setEdit(null); }}>❌ Annuler</button>
          </div>
        </div>
      )}

      <section className="grid" style={{marginTop:12}}>
        {products.map(p => (
          <article className="card" key={p.id}>
            {p.image_url ? <img src={p.image_url} alt={p.name} /> : (p.video_url ? <video src={p.video_url} controls /> : null)}
            <h3 style={{margin:'8px 0 4px'}}>{p.name}</h3>
            <div style={{color:'#ffd', fontWeight:700}}>{Number(p.price).toFixed(2)} €</div>
            <div style={{marginTop:6, minHeight:36}}>{p.description}</div>
            <div className="meta">
              <div className="small-muted">Stock: {p.stock}</div>
              {isAdmin && (
                <div style={{display:'flex',gap:8}}>
                  <button onClick={() => startEdit(p)}>✏️</button>
                  <button onClick={() => removeProduct(p.id)}>🗑️</button>
                </div>
              )}
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

ReactDOM.render(<App />, document.getElementById('root'));
</script>
</body>
</html>"""
    return html

# ----------------------------
# Run
# ----------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Starting app on port", port)
    app.run(host='0.0.0.0', port=port, debug=False)
