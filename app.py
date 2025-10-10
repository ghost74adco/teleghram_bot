from flask import Flask, request, jsonify, abort, send_from_directory, session, redirect, url_for
from dotenv import load_dotenv
from functools import wraps
from werkzeug.utils import secure_filename
import os, hmac, hashlib, json, cloudinary, cloudinary.uploader

# ==============================
# CONFIGURATION
# ==============================

load_dotenv('infos.env')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecret')

BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
ADMIN_USER_IDS = [int(i) for i in os.environ.get('ADMIN_USER_IDS', '').split(',') if i]
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

PRODUCTS_FILE = 'products.json'

# ==============================
# CLOUDINARY CONFIG
# ==============================

cloudinary.config(
    cloud_name=os.environ.get("CLOUD_NAME"),
    api_key=os.environ.get("CLOUD_API_KEY"),
    api_secret=os.environ.get("CLOUD_API_SECRET"),
    secure=True
)

# ==============================
# PRODUITS
# ==============================

def load_products():
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_products():
    with open(PRODUCTS_FILE, 'w') as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

products = load_products()

# ==============================
# AUTHENTIFICATION
# ==============================

def verify_telegram_auth(init_data):
    if not BOT_TOKEN:
        return False
    try:
        parsed_data = dict(item.split('=', 1) for item in init_data.split('&') if '=' in item)
        received_hash = parsed_data.pop('hash', '')
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new("WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(calculated_hash, received_hash)
    except:
        return False

def is_admin(user_data):
    try:
        user_info = json.loads(user_data)
        return user_info.get('id') in ADMIN_USER_IDS
    except:
        return False

# --- Décorateur admin combiné ---
def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Cas 1 : déjà connecté via login
        if session.get("admin_logged_in"):
            return f(*args, **kwargs)
        # Cas 2 : via Telegram
        init_data = request.headers.get('X-Telegram-Init-Data', '')
        if BOT_TOKEN and init_data and verify_telegram_auth(init_data):
            parsed_data = dict(item.split('=', 1) for item in init_data.split('&') if '=' in item)
            if is_admin(parsed_data.get('user', '{}')):
                return f(*args, **kwargs)
        # Sinon : interdit
        abort(403)
    return decorated

# ==============================
# LOGIN / LOGOUT
# ==============================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        pw = request.form.get('password')
        if pw == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect('/')
        return "Mot de passe incorrect", 403
    return """
    <html><body style='font-family:sans-serif;text-align:center;margin-top:100px'>
    <h2>🔐 Connexion admin</h2>
    <form method='post'>
      <input type='password' name='password' placeholder='Mot de passe' style='padding:8px'>
      <button type='submit'>Se connecter</button>
    </form>
    </body></html>
    """

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect('/')

# ==============================
# UPLOAD CLOUDINARY
# ==============================

@app.route('/api/upload', methods=['POST'])
@require_admin
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier reçu'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400
    try:
        result = cloudinary.uploader.upload(file, resource_type="auto", folder="catalogue")
        return jsonify({'url': result['secure_url']}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==============================
# API PRODUITS
# ==============================

@app.route('/api/products')
def get_products():
    return jsonify(products)

@app.route('/api/admin/check')
@require_admin
def check_admin():
    return jsonify({'admin': True})

@app.route('/api/admin/products', methods=['POST'])
@require_admin
def add_product():
    data = request.json
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
    save_products()
    return jsonify(new_product), 201

@app.route('/api/admin/products/<int:pid>', methods=['PUT'])
@require_admin
def update_product(pid):
    data = request.json
    for p in products:
        if p['id'] == pid:
            p.update({
                "name": data.get("name", p["name"]),
                "price": float(data.get("price", p["price"])),
                "description": data.get("description", p["description"]),
                "category": data.get("category", p["category"]),
                "image_url": data.get("image_url", p["image_url"]),
                "video_url": data.get("video_url", p["video_url"]),
                "stock": int(data.get("stock", p["stock"]))
            })
            save_products()
            return jsonify(p)
    return jsonify({'error': 'Produit non trouvé'}), 404

@app.route('/api/admin/products/<int:pid>', methods=['DELETE'])
@require_admin
def delete_product(pid):
    global products
    before = len(products)
    products = [p for p in products if p['id'] != pid]
    if len(products) < before:
        save_products()
        return jsonify({'success': True})
    return jsonify({'error': 'Produit non trouvé'}), 404

# ==============================
# INTERFACE REACT
# ==============================

@app.route('/')
def home():
    # Si non connecté, rediriger vers /login
    if not session.get('admin_logged_in'):
        return redirect('/login')
    return """
    <html lang="fr"><head>
    <meta charset="UTF-8"><title>Catalogue Produits</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <style>
    body{font-family:-apple-system,BlinkMacSystemFont,Roboto;background:#f5f5f5;margin:0;}
    button,input,textarea{font-family:inherit}
    </style></head><body><div id="root"></div>
    <script type="text/babel">
    const {useState,useEffect}=React;
    function App(){
      const[products,setProducts]=useState([]);
      const[formData,setFormData]=useState({name:'',price:'',description:'',category:'',stock:'',image_url:'',video_url:''});
      const[edit,setEdit]=useState(null);
      useEffect(()=>{load();},[]);
      async function load(){setProducts(await (await fetch('/api/products')).json());}
      async function save(){
        if(!formData.name||!formData.price){alert('Nom et prix requis');return;}
        const url=edit?`/api/admin/products/${edit.id}`:'/api/admin/products';
        const method=edit?'PUT':'POST';
        const res=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(formData)});
        if(res.ok){setEdit(null);setFormData({name:'',price:'',description:'',category:'',stock:'',image_url:'',video_url:''});load();}
      }
      async function del(id){if(!confirm('Supprimer ?'))return;await fetch(`/api/admin/products/${id}`,{method:'DELETE'});load();}
      async function uploadFile(e){
        const file=e.target.files[0];if(!file)return;
        const fd=new FormData();fd.append('file',file);
        const res=await fetch('/api/upload',{method:'POST',body:fd});
        const data=await res.json();
        if(data.url){
          if(file.type.startsWith('video'))setFormData({...formData,video_url:data.url,image_url:''});
          else setFormData({...formData,image_url:data.url,video_url:''});
        }else alert('Erreur upload');
      }
      return <div style={{padding:'16px',maxWidth:'800px',margin:'0 auto'}}>
        <h1>🛍️ Mon Catalogue</h1>
        <a href='/logout'>🚪 Déconnexion</a>
        <div><input placeholder="Nom" value={formData.name} onChange={e=>setFormData({...formData,name:e.target.value})}/>
        <input type="number" placeholder="Prix" value={formData.price} onChange={e=>setFormData({...formData,price:e.target.value})}/>
        <input placeholder="Catégorie" value={formData.category} onChange={e=>setFormData({...formData,category:e.target.value})}/>
        <input type="number" placeholder="Stock" value={formData.stock} onChange={e=>setFormData({...formData,stock:e.target.value})}/>
        <textarea placeholder="Description" value={formData.description} onChange={e=>setFormData({...formData,description:e.target.value})}></textarea>
        <input type="file" accept="image/*,video/*" onChange={uploadFile}/>
        <button onClick={save}>💾 Sauvegarder</button>
        {edit && <button onClick={()=>setEdit(null)}>❌ Annuler</button>}
        </div>
        {products.map(p=><div key={p.id} style={{background:'#fff',padding:'10px',borderRadius:'8px',margin:'10px 0'}}>
          {p.image_url&&<img src={p.image_url} style={{width:'100%',borderRadius:'8px'}}/>}
          {p.video_url&&<video src={p.video_url} controls style={{width:'100%'}}/>}
          <h3>{p.name}</h3><p>{p.description}</p><b>{p.price} €</b>
          <div><button onClick={()=>{setEdit(p);setFormData(p);}}>✏️</button><button onClick={()=>del(p.id)}>🗑️</button></div>
        </div>)}
      </div>
    }
    ReactDOM.render(<App/>,document.getElementById('root'));
    </script></body></html>
    """

# ==============================
# MAIN
# ==============================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Démarrage sur le port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
