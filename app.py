from flask import Flask, request, jsonify, abort, send_from_directory, redirect, render_template_string, session
from dotenv import load_dotenv
from functools import wraps
import os, json, cloudinary, cloudinary.uploader

# ==============================
# CONFIGURATION
# ==============================

load_dotenv('infos.env')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mon-super-secret')

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

PRODUCTS_FILE = 'products.json'

# Configuration Cloudinary
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

# ==============================
# FONCTIONS PRODUITS
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
# SECURITÉ ADMIN
# ==============================

def require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            abort(403)
        return f(*args, **kwargs)
    return decorated

# ==============================
# LOGIN / LOGOUT
# ==============================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect('/')
        else:
            return render_template_string("""
                <h2>❌ Mot de passe incorrect</h2>
                <a href="/login">↩️ Réessayer</a>
            """)
    return render_template_string("""
        <html>
        <head><meta charset="UTF-8"><title>Connexion admin</title></head>
        <body style="font-family: sans-serif; text-align: center; margin-top: 100px;">
            <h2>🔐 Connexion administrateur</h2>
            <form method="POST">
                <input type="password" name="password" placeholder="Mot de passe" required style="padding:8px;"/>
                <button type="submit" style="padding:8px;">Se connecter</button>
            </form>
        </body>
        </html>
    """)

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect('/')

@app.route('/admin')
def admin_redirect():
    return redirect('/login')

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
        upload_result = cloudinary.uploader.upload(file, resource_type="auto")
        return jsonify({'url': upload_result['secure_url']}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==============================
# API PRODUITS
# ==============================

@app.route('/api/products')
def get_products():
    return jsonify(products)

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
# INTERFACE WEB REACT
# ==============================

@app.route('/')
def catalogue():
    logged_in = session.get('admin_logged_in', False)
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Mon Catalogue</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Roboto;background:#f5f5f5;margin:0;padding:16px;}}
button,input,textarea{{font-family:inherit}}
.card{{background:#fff;padding:10px;border-radius:8px;margin:10px 0;box-shadow:0 2px 4px rgba(0,0,0,0.1)}}
</style>
</head>
<body>
<div id="root"></div>
<script type="text/babel">
const {{useState,useEffect}}=React;

function App(){{
 const[products,setProducts]=useState([]);
 const[isAdmin,setIsAdmin]=useState({str(logged_in).lower()});
 const[formData,setFormData]=useState({{name:'',price:0,description:'',category:'',stock:0,image_url:'',video_url:''}});
 const[showForm,setShowForm]=useState(false);
 const[edit,setEdit]=useState(null);

 useEffect(()=>{{load();}},[]);
 async function load(){{setProducts(await (await fetch('/api/products')).json());}}

 async function save(){{
  if(!formData.name.trim() || Number(formData.price) <= 0){{
    alert('Veuillez renseigner un nom et un prix valide');
    return;
  }}
  const url=edit?`/api/admin/products/${{edit.id}}`:'/api/admin/products';
  const method=edit?'PUT':'POST';
  const res=await fetch(url,{{method,headers:{{'Content-Type':'application/json'}},body:JSON.stringify(formData)}});
  if(res.ok){{setShowForm(false);setEdit(null);await load();}}
 }}

 async function del(id){{if(!confirm('Supprimer ?'))return;await fetch(`/api/admin/products/${{id}}`,{{method:'DELETE'}});load();}}

 async function uploadFile(e){{
  const file=e.target.files[0];if(!file)return;
  const fd=new FormData();fd.append('file',file);
  const res=await fetch('/api/upload',{{method:'POST',body:fd}});
  const data=await res.json();if(data.url){{
    if(file.type.startsWith('video'))setFormData({{...formData,video_url:data.url,image_url:''}});
    else setFormData({{...formData,image_url:data.url,video_url:''}});
  }}else alert('Erreur upload');
 }}

 return <div style={{maxWidth:'800px',margin:'0 auto'}}>
  <h1>🛍️ Mon Catalogue</h1>
  {{isAdmin && <p><b>👤 Admin connecté</b></p>}}
  {{!isAdmin && <a href="/login"><button>🔐 Se connecter en admin</button></a>}}
  {{isAdmin && <a href="/logout"><button>🚪 Se déconnecter</button></a>}}
  {{isAdmin&&!showForm&&
    <button onClick={{() => {{
      setEdit(null);
      setFormData({{name:'',price:0,description:'',category:'',stock:0,image_url:'',video_url:''}});
      setShowForm(true);
    }}}}>
      ➕ Ajouter un produit
    </button>
  }}
  {{isAdmin&&showForm&&<div>
    <input placeholder="Nom" value={{formData.name}} onChange={{e=>setFormData({...formData,name:e.target.value})}}/>
    <input type="number" placeholder="Prix" value={{formData.price}} onChange={{e=>setFormData({...formData,price:e.target.value})}}/>
    <input placeholder="Catégorie" value={{formData.category}} onChange={{e=>setFormData({...formData,category:e.target.value})}}/>
    <input type="number" placeholder="Stock" value={{formData.stock}} onChange={{e=>setFormData({...formData,stock:e.target.value})}}/>
    <textarea placeholder="Description" value={{formData.description}} onChange={{e=>setFormData({...formData,description:e.target.value})}}></textarea>
    <input type="file" accept="image/*,video/*" onChange={{uploadFile}}/>
    <button onClick={{save}}>💾 Sauvegarder</button><button onClick={{()=>setShowForm(false)}}>❌ Annuler</button>
  </div>}}
  {{products.map(p=>
    <div key={{p.id}} className="card">
      {{p.image_url&&<img src={{p.image_url}} style={{width:'100%',borderRadius:'8px'}}/>}}
      {{p.video_url&&<video src={{p.video_url}} controls style={{width:'100%'}}/>}}
      <h3>{{p.name}}</h3><p>{{p.description}}</p><b>{{p.price}} €</b>
      {{isAdmin&&<div><button onClick={{()=>{{setEdit(p);setFormData(p);setShowForm(true);}}}}>✏️</button>
      <button onClick={{()=>del(p.id)}}>🗑️</button></div>}}
    </div>
  )}}
 </div>
}}
ReactDOM.render(<App/>,document.getElementById('root'));
</script>
</body>
</html>
"""

# ==============================
# MAIN
# ==============================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Démarrage sur le port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
