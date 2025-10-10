from flask import Flask, request, jsonify, abort
import os
import hmac
import hashlib
import json
from dotenv import load_dotenv
from functools import wraps

# Charger le fichier infos.env
load_dotenv('infos.env')

app = Flask(__name__)

# Configuration de sécurité - Adaptation à votre fichier infos.env
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mon-super-secret-aleatoire-2024')
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN', os.environ.get('BOT_TOKEN', ''))  # Support des deux noms
ADMIN_USER_IDS = [int(id) for id in os.environ.get('ADMIN_USER_IDS', os.environ.get('ADMIN_ID', '')).split(',') if id]

# Stockage des produits (remplacer par une base de données en production)
products = [
    {
        "id": 1,
        "name": "Produit Example 1",
        "price": 29.99,
        "description": "Description du produit 1",
        "category": "Électronique",
        "image_url": "https://via.placeholder.com/400x300/667eea/ffffff?text=Produit+1",
        "video_url": "",
        "stock": 10
    },
    {
        "id": 2,
        "name": "Produit Example 2",
        "price": 49.99,
        "description": "Description du produit 2",
        "category": "Vêtements",
        "image_url": "https://via.placeholder.com/400x300/764ba2/ffffff?text=Produit+2",
        "video_url": "",
        "stock": 5
    }
]

def verify_telegram_auth(init_data):
    """Vérifie l'authenticité des données Telegram WebApp"""
    if not BOT_TOKEN:
        print("⚠️ BOT_TOKEN non configuré - mode développement")
        return False
    try:
        parsed_data = dict(item.split('=', 1) for item in init_data.split('&') if '=' in item)
        received_hash = parsed_data.pop('hash', '')
        
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new("WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(calculated_hash, received_hash)
    except Exception as e:
        print(f"❌ Erreur authentification: {e}")
        return False

def is_admin(user_data):
    """Vérifie si l'utilisateur est admin"""
    try:
        user_info = json.loads(user_data)
        user_id = user_info.get('id')
        is_admin_user = user_id in ADMIN_USER_IDS
        print(f"🔍 Vérification admin - User ID: {user_id}, Admin IDs: {ADMIN_USER_IDS}, Est admin: {is_admin_user}")
        return is_admin_user
    except Exception as e:
        print(f"❌ Erreur vérification admin: {e}")
        return False

def require_admin(f):
    """Décorateur pour vérifier les droits admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_data = request.headers.get('X-Telegram-Init-Data', '')
        
        # En développement, autoriser sans authentification si pas de BOT_TOKEN
        if not BOT_TOKEN:
            print("⚠️ Mode développement - accès admin autorisé sans authentification")
            return f(*args, **kwargs)
        
        if not init_data:
            print("❌ Pas de données Telegram Init Data")
            abort(403, description="Unauthorized - No Telegram data")
        
        if not verify_telegram_auth(init_data):
            print("❌ Authentification Telegram échouée")
            abort(403, description="Unauthorized - Invalid Telegram data")
        
        try:
            parsed_data = dict(item.split('=', 1) for item in init_data.split('&') if '=' in item)
            user_data = parsed_data.get('user', '')
            if not is_admin(user_data):
                print("❌ Utilisateur non autorisé (pas admin)")
                abort(403, description="Admin access required")
        except Exception as e:
            print(f"❌ Erreur lors de la vérification: {e}")
            abort(403, description="Invalid request")
        
        print("✅ Accès admin autorisé")
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>Catalogue Produits</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
        <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
        <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
                background: #f5f5f5;
                overflow-x: hidden;
            }
            #root { min-height: 100vh; }
            img { max-width: 100%; height: auto; }
        </style>
    </head>
    <body>
        <div id="root"></div>
        
        <script type="text/babel">
            const { useState, useEffect } = React;
            const tg = window.Telegram?.WebApp;

            function App() {
                const [products, setProducts] = useState([]);
                const [isAdmin, setIsAdmin] = useState(false);
                const [loading, setLoading] = useState(true);
                const [editingProduct, setEditingProduct] = useState(null);
                const [showForm, setShowForm] = useState(false);
                const [formData, setFormData] = useState({
                    name: '', price: '', description: '', category: '', 
                    image_url: '', video_url: '', stock: ''
                });

                useEffect(() => {
                    console.log('🚀 App démarrée');
                    if (tg) {
                        console.log('✅ Telegram WebApp détecté');
                        tg.ready();
                        tg.expand();
                        tg.BackButton.hide();
                        console.log('📱 Init Data:', tg.initData ? 'Présent' : 'Absent');
                    } else {
                        console.log('⚠️ Telegram WebApp non disponible (mode navigateur?)');
                    }
                    loadProducts();
                    checkAdmin();
                }, []);

                const getHeaders = () => {
                    const headers = {
                        'Content-Type': 'application/json',
                        'X-Telegram-Init-Data': tg?.initData || ''
                    };
                    console.log('📤 Headers:', headers['X-Telegram-Init-Data'] ? 'Init Data présent' : 'Init Data absent');
                    return headers;
                };

                const loadProducts = async () => {
                    console.log('📦 Chargement des produits...');
                    try {
                        const res = await fetch('/api/products');
                        const data = await res.json();
                        console.log('✅ Produits chargés:', data.length);
                        setProducts(data);
                    } catch (err) {
                        console.error('❌ Erreur chargement:', err);
                    } finally {
                        setLoading(false);
                    }
                };

                const checkAdmin = async () => {
                    console.log('🔍 Vérification droits admin...');
                    try {
                        const res = await fetch('/api/admin/check', {
                            headers: getHeaders()
                        });
                        const isAdminUser = res.ok;
                        console.log(isAdminUser ? '✅ Utilisateur admin détecté' : '👤 Utilisateur standard');
                        setIsAdmin(isAdminUser);
                    } catch (err) {
                        console.log('👤 Pas d\'accès admin:', err.message);
                        setIsAdmin(false);
                    }
                };

                const handleSaveProduct = async () => {
                    if (!formData.name || !formData.price) {
                        alert('Le nom et le prix sont requis');
                        return;
                    }

                    console.log('💾 Sauvegarde du produit...');
                    try {
                        const url = editingProduct 
                            ? `/api/admin/products/${editingProduct.id}`
                            : '/api/admin/products';
                        
                        const method = editingProduct ? 'PUT' : 'POST';
                        
                        const res = await fetch(url, {
                            method,
                            headers: getHeaders(),
                            body: JSON.stringify(formData)
                        });

                        if (res.ok) {
                            console.log('✅ Produit sauvegardé');
                            await loadProducts();
                            setShowForm(false);
                            setEditingProduct(null);
                            setFormData({
                                name: '', price: '', description: '', category: '', 
                                image_url: '', video_url: '', stock: ''
                            });
                            if (tg) {
                                tg.showAlert('✅ Produit sauvegardé !');
                            } else {
                                alert('✅ Produit sauvegardé !');
                            }
                        } else {
                            const error = await res.text();
                            console.error('❌ Erreur sauvegarde:', error);
                            alert('❌ Erreur: ' + error);
                        }
                    } catch (err) {
                        console.error('❌ Exception:', err);
                        alert('❌ Erreur: ' + err.message);
                    }
                };

                const handleDeleteProduct = async (id) => {
                    const confirmed = window.confirm('Supprimer ce produit ?');
                    if (!confirmed) return;
                    
                    console.log('🗑️ Suppression du produit', id);
                    try {
                        const res = await fetch(`/api/admin/products/${id}`, {
                            method: 'DELETE',
                            headers: getHeaders()
                        });

                        if (res.ok) {
                            console.log('✅ Produit supprimé');
                            await loadProducts();
                            if (tg) {
                                tg.showAlert('✅ Produit supprimé !');
                            } else {
                                alert('✅ Produit supprimé !');
                            }
                        }
                    } catch (err) {
                        console.error('❌ Erreur suppression:', err);
                        alert('❌ Erreur: ' + err.message);
                    }
                };

                const handleEditProduct = (product) => {
                    console.log('✏️ Édition du produit', product.id);
                    setEditingProduct(product);
                    setFormData({
                        name: product.name,
                        price: product.price,
                        description: product.description,
                        category: product.category,
                        image_url: product.image_url || '',
                        video_url: product.video_url || '',
                        stock: product.stock
                    });
                    setShowForm(true);
                    window.scrollTo(0, 0);
                };

                const categories = [...new Set(products.map(p => p.category))];

                if (loading) {
                    return (
                        <div style={{ 
                            display: 'flex', 
                            justifyContent: 'center', 
                            alignItems: 'center', 
                            minHeight: '100vh',
                            fontSize: '18px',
                            color: '#666'
                        }}>
                            ⏳ Chargement...
                        </div>
                    );
                }

                return (
                    <div style={{ minHeight: '100vh', background: '#f5f5f5', paddingBottom: '20px' }}>
                        {/* Header */}
                        <div style={{ 
                            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', 
                            boxShadow: '0 2px 10px rgba(0,0,0,0.15)', 
                            position: 'sticky', 
                            top: 0, 
                            zIndex: 10 
                        }}>
                            <div style={{ padding: '20px 16px', maxWidth: '800px', margin: '0 auto' }}>
                                <h1 style={{ fontSize: '24px', fontWeight: 'bold', color: 'white', marginBottom: '4px' }}>
                                    🛍️ Catalogue Produits
                                </h1>
                                {isAdmin && (
                                    <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.9)' }}>
                                        ✅ Mode Administrateur activé
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Add Button (Admin only) */}
                        {isAdmin && !showForm && (
                            <div style={{ padding: '16px', maxWidth: '800px', margin: '0 auto' }}>
                                <button
                                    onClick={() => {
                                        setEditingProduct(null);
                                        setFormData({
                                            name: '', price: '', description: '', category: '', 
                                            image_url: '', video_url: '', stock: ''
                                        });
                                        setShowForm(true);
                                    }}
                                    style={{
                                        width: '100%',
                                        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                        color: 'white',
                                        padding: '14px',
                                        borderRadius: '12px',
                                        border: 'none',
                                        fontSize: '16px',
                                        fontWeight: 'bold',
                                        cursor: 'pointer',
                                        boxShadow: '0 4px 12px rgba(102, 126, 234, 0.4)'
                                    }}
                                >
                                    ➕ Ajouter un produit
                                </button>
                            </div>
                        )}

                        {/* Form (Admin only) */}
                        {isAdmin && showForm && (
                            <div style={{ padding: '16px', maxWidth: '800px', margin: '0 auto' }}>
                                <div style={{ 
                                    background: 'white', 
                                    borderRadius: '16px', 
                                    padding: '20px', 
                                    boxShadow: '0 4px 16px rgba(0,0,0,0.1)' 
                                }}>
                                    <h2 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '16px', color: '#333' }}>
                                        {editingProduct ? '✏️ Modifier le produit' : '➕ Nouveau produit'}
                                    </h2>
                                    
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                        <input
                                            type="text"
                                            placeholder="Nom du produit *"
                                            value={formData.name}
                                            onChange={(e) => setFormData({...formData, name: e.target.value})}
                                            style={{ 
                                                padding: '12px', 
                                                borderRadius: '8px', 
                                                border: '2px solid #e5e5e5', 
                                                fontSize: '16px',
                                                outline: 'none'
                                            }}
                                        />
                                        <input
                                            type="number"
                                            step="0.01"
                                            placeholder="Prix (€) *"
                                            value={formData.price}
                                            onChange={(e) => setFormData({...formData, price: e.target.value})}
                                            style={{ 
                                                padding: '12px', 
                                                borderRadius: '8px', 
                                                border: '2px solid #e5e5e5', 
                                                fontSize: '16px',
                                                outline: 'none'
                                            }}
                                        />
                                        <input
                                            type="text"
                                            placeholder="Catégorie *"
                                            value={formData.category}
                                            onChange={(e) => setFormData({...formData, category: e.target.value})}
                                            style={{ 
                                                padding: '12px', 
                                                borderRadius: '8px', 
                                                border: '2px solid #e5e5e5', 
                                                fontSize: '16px',
                                                outline: 'none'
                                            }}
                                        />
                                        <input
                                            type="number"
                                            placeholder="Stock"
                                            value={formData.stock}
                                            onChange={(e) => setFormData({...formData, stock: e.target.value})}
                                            style={{ 
                                                padding: '12px', 
                                                borderRadius: '8px', 
                                                border: '2px solid #e5e5e5', 
                                                fontSize: '16px',
                                                outline: 'none'
                                            }}
                                        />
                                        <textarea
                                            placeholder="Description"
                                            value={formData.description}
                                            onChange={(e) => setFormData({...formData, description: e.target.value})}
                                            rows="3"
                                            style={{ 
                                                padding: '12px', 
                                                borderRadius: '8px', 
                                                border: '2px solid #e5e5e5', 
                                                fontSize: '16px', 
                                                resize: 'vertical',
                                                outline: 'none',
                                                fontFamily: 'inherit'
                                            }}
                                        />
                                        <input
                                            type="url"
                                            placeholder="URL de l'image (https://...)"
                                            value={formData.image_url}
                                            onChange={(e) => setFormData({...formData, image_url: e.target.value})}
                                            style={{ 
                                                padding: '12px', 
                                                borderRadius: '8px', 
                                                border: '2px solid #e5e5e5', 
                                                fontSize: '16px',
                                                outline: 'none'
                                            }}
                                        />
                                        <input
                                            type="url"
                                            placeholder="URL de la vidéo (https://...)"
                                            value={formData.video_url}
                                            onChange={(e) => setFormData({...formData, video_url: e.target.value})}
                                            style={{ 
                                                padding: '12px', 
                                                borderRadius: '8px', 
                                                border: '2px solid #e5e5e5', 
                                                fontSize: '16px',
                                                outline: 'none'
                                            }}
                                        />

                                        <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                                            <button
                                                onClick={handleSaveProduct}
                                                style={{
                                                    flex: 1,
                                                    background: '#10B981',
                                                    color: 'white',
                                                    padding: '14px',
                                                    borderRadius: '8px',
                                                    border: 'none',
                                                    fontSize: '16px',
                                                    fontWeight: 'bold',
                                                    cursor: 'pointer'
                                                }}
                                            >
                                                💾 Sauvegarder
                                            </button>
                                            <button
                                                onClick={() => {
                                                    setShowForm(false);
                                                    setEditingProduct(null);
                                                }}
                                                style={{
                                                    flex: 1,
                                                    background: '#6B7280',
                                                    color: 'white',
                                                    padding: '14px',
                                                    borderRadius: '8px',
                                                    border: 'none',
                                                    fontSize: '16px',
                                                    fontWeight: 'bold',
                                                    cursor: 'pointer'
                                                }}
                                            >
                                                ❌ Annuler
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Products List */}
                        <div style={{ padding: '16px', maxWidth: '800px', margin: '0 auto' }}>
                            {products.length === 0 ? (
                                <div style={{ 
                                    textAlign: 'center', 
                                    padding: '60px 20px', 
                                    color: '#666',
                                    fontSize: '16px'
                                }}>
                                    📦 Aucun produit pour le moment
                                    {isAdmin && <div style={{ marginTop: '12px', color: '#999' }}>Ajoutez votre premier produit !</div>}
                                </div>
                            ) : (
                                categories.map(category => (
                                    <div key={category} style={{ marginBottom: '32px' }}>
                                        <h2 style={{ 
                                            fontSize: '20px', 
                                            fontWeight: 'bold', 
                                            marginBottom: '16px', 
                                            color: '#1F2937',
                                            borderBottom: '3px solid #667eea',
                                            paddingBottom: '8px'
                                        }}>
                                            {category}
                                        </h2>
                                        
                                        {products.filter(p => p.category === category).map(product => (
                                            <div key={product.id} style={{ 
                                                background: 'white', 
                                                borderRadius: '16px', 
                                                marginBottom: '16px',
                                                overflow: 'hidden',
                                                boxShadow: '0 2px 12px rgba(0,0,0,0.08)'
                                            }}>
                                                {/* Image/Video */}
                                                {product.image_url ? (
                                                    <img 
                                                        src={product.image_url} 
                                                        alt={product.name}
                                                        style={{ 
                                                            width: '100%', 
                                                            height: '220px', 
                                                            objectFit: 'cover',
                                                            display: 'block'
                                                        }}
                                                        onError={(e) => {
                                                            e.target.style.display = 'none';
                                                        }}
                                                    />
                                                ) : product.video_url ? (
                                                    <video 
                                                        src={product.video_url}
                                                        controls
                                                        style={{ 
                                                            width: '100%', 
                                                            height: '220px', 
                                                            objectFit: 'cover', 
                                                            background: '#000',
                                                            display: 'block'
                                                        }}
                                                    />
                                                ) : (
                                                    <div style={{ 
                                                        height: '220px', 
                                                        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        justifyContent: 'center',
                                                        fontSize: '72px'
                                                    }}>
                                                        📦
                                                    </div>
                                                )}

                                                <div style={{ padding: '16px' }}>
                                                    <div style={{ 
                                                        display: 'flex', 
                                                        justifyContent: 'space-between', 
                                                        alignItems: 'start', 
                                                        marginBottom: '8px' 
                                                    }}>
                                                        <h3 style={{ 
                                                            fontSize: '18px', 
                                                            fontWeight: 'bold', 
                                                            color: '#1F2937',
                                                            flex: 1
                                                        }}>
                                                            {product.name}
                                                        </h3>
                                                        {isAdmin && (
                                                            <div style={{ display: 'flex', gap: '6px', marginLeft: '8px' }}>
                                                                <button
                                                                    onClick={() => handleEditProduct(product)}
                                                                    style={{
                                                                        padding: '8px 12px',
                                                                        background: '#3B82F6',
                                                                        color: 'white',
                                                                        border: 'none',
                                                                        borderRadius: '6px',
                                                                        cursor: 'pointer',
                                                                        fontSize: '14px'
                                                                    }}
                                                                >
                                                                    ✏️
                                                                </button>
                                                                <button
                                                                    onClick={() => handleDeleteProduct(product.id)}
                                                                    style={{
                                                                        padding: '8px 12px',
                                                                        background: '#EF4444',
                                                                        color: 'white',
                                                                        border: 'none',
                                                                        borderRadius: '6px',
                                                                        cursor: 'pointer',
                                                                        fontSize: '14px'
                                                                    }}
                                                                >
                                                                    🗑️
                                                                </button>
                                                            </div>
                                                        )}
                                                    </div>
                                                    
                                                    {product.description && (
                                                        <p style={{ 
                                                            color: '#6B7280', 
                                                            fontSize: '14px', 
                                                            marginBottom: '12px',
                                                            lineHeight: '1.5'
                                                        }}>
                                                            {product.description}
                                                        </p>
                                                    )}
                                                    
                                                    <div style={{ 
                                                        display: 'flex', 
                                                        justifyContent: 'space-between', 
                                                        alignItems: 'center' 
                                                    }}>
                                                        <span style={{ 
                                                            fontSize: '28px', 
                                                            fontWeight: 'bold', 
                                                            color: '#667eea' 
                                                        }}>
                                                            {parseFloat(product.price).toFixed(2)} €
                                                        </span>
                                                        <span style={{ 
                                                            fontSize: '13px', 
                                                            color: '#9CA3AF',
                                                            background: '#F3F4F6',
                                                            padding: '4px 12px',
                                                            borderRadius: '12px'
                                                        }}>
                                                            Stock: {product.stock}
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                );
            }

            ReactDOM.render(<App />, document.getElementById('root'));
        </script>
    </body>
    </html>
    """

@app.route('/api/products', methods=['GET'])
def get_products():
    """API publique - Voir les produits (accessible à tous)"""
    return jsonify(products)

@app.route('/api/admin/check', methods=['GET'])
@require_admin
def check_admin():
    """Vérifie si l'utilisateur est admin"""
    return jsonify({"admin": True})

@app.route('/api/admin/products', methods=['POST'])
@require_admin
def add_product():
    """Admin uniquement - Ajouter un produit"""
    data = request.json
    
    if not data.get('name') or not data.get('price'):
        return jsonify({"error": "Nom et prix requis"}), 400
    
    new_product = {
        "id": max([p["id"] for p in products]) + 1 if products else 1,
        "name": data.get("name"),
        "price": float(data.get("price")),
        "description": data.get("description", ""),
        "category": data.get("category", "Sans catégorie"),
        "image_url": data.get("image_url", ""),
        "video_url": data.get("video_url", ""),
        "stock": int(data.get("stock", 0))
    }
    products.append(new_product)
    print(f"✅ Produit ajouté: {new_product['name']}")
    return jsonify(new_product), 201

@app.route('/api/admin/products/<int:product_id>', methods=['PUT'])
@require_admin
def update_product(product_id):
    """Admin uniquement - Modifier un produit"""
    data = request.json
    
    for product in products:
        if product["id"] == product_id:
            product.update({
                "name": data.get("name", product["name"]),
                "price": float(data.get("price", product["price"])),
                "description": data.get("description", product["description"]),
                "category": data.get("category", product["category"]),
                "image_
