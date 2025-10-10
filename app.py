from flask import Flask, request, jsonify, send_from_directory, session, redirect
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import os, json, cloudinary, cloudinary.uploader

# ==============================
# CONFIGURATION
# ==============================

load_dotenv("infos.env")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret-key")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

PRODUCTS_FILE = "products.json"

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# ==============================
# PRODUITS
# ==============================

def load_products():
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r") as f:
            return json.load(f)
    return []

def save_products(products):
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

products = load_products()

# ==============================
# ROUTES D’AUTHENTIFICATION ADMIN
# ==============================

@app.route("/api/admin/login", methods=["POST"])
def login():
    data = request.json
    if data.get("password") == ADMIN_PASSWORD:
        session["is_admin"] = True
        return jsonify({"success": True})
    return jsonify({"error": "Mot de passe incorrect"}), 403

@app.route("/api/admin/logout")
def logout():
    session.pop("is_admin", None)
    return jsonify({"success": True})

@app.route("/api/admin/check")
def check_admin():
    return jsonify({"admin": session.get("is_admin", False)})

def require_admin(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify({"error": "Non autorisé"}), 403
        return f(*args, **kwargs)
    return wrapper

# ==============================
# UPLOAD CLOUDINARY
# ==============================

@app.route("/api/upload", methods=["POST"])
@require_admin
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier reçu"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Nom de fichier vide"}), 400

    result = cloudinary.uploader.upload(file, resource_type="auto")
    return jsonify({"url": result["secure_url"]})

# ==============================
# API PRODUITS
# ==============================

@app.route("/api/products")
def get_products():
    return jsonify(products)

@app.route("/api/admin/products", methods=["POST"])
@require_admin
def add_product():
    data = request.json
    new_product = {
        "id": max([p["id"] for p in products]) + 1 if products else 1,
        "name": data.get("name", ""),
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

@app.route("/api/admin/products/<int:pid>", methods=["PUT"])
@require_admin
def update_product(pid):
    data = request.json
    for p in products:
        if p["id"] == pid:
            p.update({
                "name": data.get("name", p["name"]),
                "price": float(data.get("price", p["price"])),
                "description": data.get("description", p["description"]),
                "category": data.get("category", p["category"]),
                "image_url": data.get("image_url", p["image_url"]),
                "video_url": data.get("video_url", p["video_url"]),
                "stock": int(data.get("stock", p["stock"]))
            })
            save_products(products)
            return jsonify(p)
    return jsonify({"error": "Produit non trouvé"}), 404

@app.route("/api/admin/products/<int:pid>", methods=["DELETE"])
@require_admin
def delete_product(pid):
    global products
    before = len(products)
    products = [p for p in products if p["id"] != pid]
    if len(products) < before:
        save_products(products)
        return jsonify({"success": True})
    return jsonify({"error": "Produit non trouvé"}), 404

# ==============================
# INTERFACE WEB REACT
# ==============================

@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Mon catalogue</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,Roboto;background:#f5f5f5;margin:0;padding:20px;}
button,input,textarea{font-family:inherit;margin:5px;padding:8px;}
.card{background:white;border-radius:8px;padding:10px;margin:10px 0;}
img,video{max-width:100%;border-radius:8px;}
</style>
</head>
<body>
<div id="root"></div>
<script type="text/babel">
const {useState,useEffect}=React;

function App(){
 const[products,setProducts]=useState([]);
 const[isAdmin,setIsAdmin]=useState(false);
 const[password,setPassword]=useState("");
 const[formData,setFormData]=useState({name:'',price:0,description:'',category:'',stock:0,image_url:'',video_url:''});
 const[showForm,setShowForm]=useState(false);
 const[edit,setEdit]=useState(null);

 useEffect(()=>{load();check();},[]);

 async function load(){
   setProducts(await (await fetch('/api/products')).json());
 }
 async function check(){
   const res = await fetch('/api/admin/check');
   const data = await res.json();
   setIsAdmin(data.admin);
 }

 async function login(){
   const res = await fetch('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
   const data = await res.json();
   if(data.success){setIsAdmin(true);setPassword('');}
   else alert('Mot de passe incorrect');
 }

 async function logout(){
   await fetch('/api/admin/logout');
   setIsAdmin(false);
 }

 async function save(){
   if(!formData.name.trim() || Number(formData.price)<=0){alert('Veuillez renseigner un nom et un prix valide');return;}
   const url = edit ? `/api/admin/products/${edit.id}` : '/api/admin/products';
   const method = edit ? 'PUT' : 'POST';
   const res = await fetch(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(formData)});
   if(res.ok){setShowForm(false);setEdit(null);await load();}
 }

 async function del(id){
   if(!confirm('Supprimer ?'))return;
   await fetch(`/api/admin/products/${id}`,{method:'DELETE'});
   load();
 }

 async function uploadFile(e){
   const file = e.target.files[0];
   if(!file)return;
   const fd = new FormData();
   fd.append('file',file);
   const res = await fetch('/api/upload',{method:'POST',body:fd});
   const data = await res.json();
   if(data.url){
     if(file.type.startsWith('video'))setFormData({...formData,video_url:data.url,image_url:''});
     else setFormData({...formData,image_url:data.url,video_url:''});
   }else alert('Erreur upload');
 }

 return <div style={{maxWidth:'800px',margin:'0 auto'}}>
  <h1>🛍️ Mon catalogue</h1>
  {!isAdmin && <div>
    <input type="password" placeholder="Mot de passe admin" value={password} onChange={e=>setPassword(e.target.value)}/>
    <button onClick={login}>Se connecter</button>
  </div>}
  {isAdmin && <div><button onClick={logout}>🚪 Déconnexion</button></div>}
  {isAdmin && !showForm &&
    <button onClick={()=>{
      setEdit(null);
      setFormData({name:'',price:0,description:'',category:'',stock:0,image_url:'',video_url:''});
      setShowForm(true);
    }}>➕ Ajouter un produit</button>}
  {isAdmin && showForm &&
    <div style={{background:'#fff',padding:'10px',borderRadius:'8px'}}>
      <input placeholder="Nom" value={formData.name} onChange={e=>setFormData({...formData,name:e.target.value})}/>
      <input type="number" placeholder="Prix" value={formData.price} onChange={e=>setFormData({...formData,
