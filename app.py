from flask import Flask, request, jsonify, abort
import os
import hmac
import hashlib
import json
from dotenv import load_dotenv
from functools import wraps

load_dotenv()
app = Flask(__name__)

# Configuration de sécurité
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'votre-cle-secrete-a-changer')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
ADMIN_USER_IDS = [int(id) for id in os.environ.get('ADMIN_USER_IDS', '').split(',') if id]

# Stockage des produits (remplacer par une base de données en production)
products = [
    {
        "id": 1,
        "name": "Produit Example 1",
        "price": 29.99,
        "description": "Description du produit 1",
        "category": "Électronique",
        "image_url": "",
        "video_url": "",
        "stock": 10
    },
    {
        "id": 2,
        "name": "Produit Example 2",
        "price": 49.99,
        "description": "Description du produit 2",
        "category": "Vêtements",
        "image_url": "",
        "video_url": "",
        "stock": 5
    }
]

def verify_telegram_auth(init_data):
    """Vérifie l'authenticité des données Telegram WebApp"""
    try:
        parsed_data = dict(item.split('=') for item in init_data.split('&'))
        received_hash = parsed_data.pop('hash', '')
        
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new("WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(calculated_hash, received_hash)
    except:
        return False

def is_admin(user_data):
    """Vérifie si l'utilisateur est admin"""
    try:
        user_id = json.loads(user_data).get('id')
        return user_id in ADMIN_USER_IDS
    except:
        return False

def require_auth(f):
    """Décorateur pour vérifier l'authentification Telegram"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_data = request.headers.get('X-Telegram-Init-Data', '')
        if not init_data or not verify_telegram_auth(init_data):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    """Décorateur pour vérifier les droits admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_data = request.headers.get('X-Telegram-Init-Data', '')
        if not init_data or not verify_telegram_auth(init_data):
            abort(403)
        
        parsed_data = dict(item.split('=') for item in init_data.split('&'))
        user_data = parsed_data.get('user', '')
        if not is_admin(user_data):
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Catalogue Produits</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
        <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
        <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f5f5f5;
            }
            #root { min-height: 100vh; }
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
                    if (tg) {
                        tg.ready();
                        tg.expand();
                        tg.BackButton.hide();
                    }
                    loadProducts();
                    checkAdmin();
                }, []);

                const getHeaders = () => ({
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': tg?.initData || ''
                });

                const loadProducts = async () => {
                    try {
                        const res = await fetch('/api/products');
                        const data = await res.json();
                        setProducts(data);
                    } catch (err) {
                        console.error('Erreur chargement:', err);
                    } finally {
                        setLoading(false);
                    }
                };

                const checkAdmin = async () => {
                    try {
                        const res = await fetch('/api/admin/check', {
                            headers: getHeaders()
                        });
                        setIsAdmin(res.ok);
                    } catch (err) {
                        setIsAdmin(false);
                    }
                };

                const handleSaveProduct = async () => {
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
                            await loadProducts();
                            setShowForm(false);
                            setEditingProduct(null);
                            setFormData({
                                name: '', price: '', description: '', category: '', 
                                image_url: '', video_url: '', stock: ''
                            });
                            tg?.showAlert('✅ Produit sauvegardé !');
                        } else {
                            tg?.showAlert('❌ Erreur lors de la sauvegarde');
                        }
                    } catch (err) {
                        tg?.showAlert('❌ Erreur: ' + err.message);
                    }
                };

                const handleDeleteProduct = async (id) => {
                    if (!confirm('Supprimer ce produit ?')) return;
                    
                    try {
                        const res = await fetch(`/api/admin/products/${id}`, {
                            method: 'DELETE',
                            headers: getHeaders()
                        });

                        if (res.ok) {
                            await loadProducts();
                            tg?.showAlert('✅ Produit supprimé !');
                        }
                    } catch (err) {
                        tg?.showAlert('❌ Erreur: ' + err.message);
                    }
                };

                const handleEditProduct = (product) => {
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
                };

                const categories = [...new Set(products.map(p => p.category))];

                if (loading) {
                    return (
                        <div style={{ 
                            display: 'flex', 
                            justifyContent: 'center', 
                            alignItems: 'center', 
                            minHeight: '100vh' 
                        }}>
                            <div style={{ fontSize: '20px', color: '#666' }}>Chargement...</div>
                        </div>
                    );
                }

                return (
                    <div style={{ minHeight: '100vh', background: '#f5f5f5', paddingBottom: isAdmin ? '80px' : '20px' }}>
                        {/* Header */}
                        <div style={{ 
                            background: 'white', 
                            boxShadow: '0 2px 10px rgba(0,0,0,0.1)', 
                            position: 'sticky', 
                            top: 0, 
                            zIndex: 10 
                        }}>
                            <div style={{ padding: '16px', maxWidth: '800px', margin: '0 auto' }}>
                                <h1 style={{ fontSize: '24px', fontWeight: 'bold', color: '#2563EB' }}>
                                    📱 Catalogue Produits
                                </h1>
                                {isAdmin && (
                                    <div style={{ marginTop: '8px', fontSize: '12px', color: '#10B981' }}>
                                        ✅ Mode Administrateur
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
                                        background: '#2563EB',
                                        color: 'white',
                                        padding: '12px',
                                        borderRadius: '8px',
                                        border: 'none',
                                        fontSize: '16px',
                                        fontWeight: 'bold',
                                        cursor: 'pointer'
                                    }}
                                >
                                    ➕ Ajouter un produit
                                </button>
                            </div>
                        )}

                        {/* Form (Admin only) */}
                        {isAdmin && showForm && (
                            <div style={{ padding: '16px', maxWidth: '800px', margin: '0 auto' }}>
                                <div style={{ background: 'white', borderRadius: '12px', padding: '20px', boxShadow: '0 2px 10px rgba(0,0,0,0.1)' }}>
                                    <h2 style={{ fontSize: '18px', fontWeight: 'bold', marginBottom: '16px' }}>
                                        {editingProduct ? '✏️ Modifier' : '➕ Nouveau produit'}
                                    </h2>
                                    
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                        <input
                                            type="text"
                                            placeholder="Nom du produit *"
                                            value={formData.name}
                                            onChange={(e) => setFormData({...formData, name: e.target.value})}
                                            style={{ padding: '12px', borderRadius: '8px', border: '1px solid #ddd', fontSize: '16px' }}
                                        />
                                        <input
                                            type="number"
                                            step="0.01"
                                            placeholder="Prix (€) *"
                                            value={formData.price}
                                            onChange={(e) => setFormData({...formData, price: e.target.value})}
                                            style={{ padding: '12px', borderRadius: '8px', border: '1px solid #ddd', fontSize: '16px' }}
                                        />
                                        <input
                                            type="text"
                                            placeholder="Catégorie *"
                                            value={formData.category}
                                            onChange={(e) => setFormData({...formData, category: e.target.value})}
                                            style={{ padding: '12px', borderRadius: '8px', border: '1px solid #ddd', fontSize: '16px' }}
                                        />
                                        <input
                                            type="number"
                                            placeholder="Stock"
                                            value={formData.stock}
                                            onChange={(e) => setFormData({...formData, stock: e.target.value})}
                                            style={{ padding: '12px', borderRadius: '8px', border: '1px solid #ddd', fontSize: '16px' }}
                                        />
                                        <textarea
                                            placeholder="Description"
                                            value={formData.description}
                                            onChange={(e) => setFormData({...formData, description: e.target.value})}
                                            rows="3"
                                            style={{ padding: '12px', borderRadius: '8px', border: '1px solid #ddd', fontSize: '16px', resize: 'vertical' }}
                                        />
                                        <input
                                            type="url"
                                            placeholder="URL de l'image (https://...)"
                                            value={formData.image_url}
                                            onChange={(e) => setFormData({...formData, image_url: e.target.value})}
                                            style={{ padding: '12px', borderRadius: '8px', border: '1px solid #ddd', fontSize: '16px' }}
                                        />
                                        <input
                                            type="url"
                                            placeholder="URL de la vidéo (https://...)"
                                            value={formData.video_url}
                                            onChange={(e) => setFormData({...formData, video_url: e.target.value})}
                                            style={{ padding: '12px', borderRadius: '8px', border: '1px solid #ddd', fontSize: '16px' }}
                                        />

                                        <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                                            <button
                                                onClick={handleSaveProduct}
                                                style={{
                                                    flex: 1,
                                                    background: '#10B981',
                                                    color: 'white',
                                                    padding: '12px',
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
                                                    padding: '12px',
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
                            {categories.map(category => (
                                <div key={category} style={{ marginBottom: '32px' }}>
                                    <h2 style={{ 
                                        fontSize: '20px', 
                                        fontWeight: 'bold', 
                                        marginBottom: '16px', 
                                        color: '#1F2937',
                                        borderBottom: '2px solid #2563EB',
                                        paddingBottom: '8px'
                                    }}>
                                        {category}
                                    </h2>
                                    
                                    {products.filter(p => p.category === category).map(product => (
                                        <div key={product.id} style={{ 
                                            background: 'white', 
                                            borderRadius: '12px', 
                                            marginBottom: '16px',
                                            overflow: 'hidden',
                                            boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
                                        }}>
                                            {/* Image/Video */}
                                            {product.image_url ? (
                                                <img 
                                                    src={product.image_url} 
                                                    alt={product.name}
                                                    style={{ width: '100%', height: '200px', objectFit: 'cover' }}
                                                />
                                            ) : product.video_url ? (
                                                <video 
                                                    src={product.video_url}
                                                    controls
                                                    style={{ width: '100%', height: '200px', objectFit: 'cover', background: '#000' }}
                                                />
                                            ) : (
                                                <div style={{ 
                                                    height: '200px', 
                                                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'center',
                                                    fontSize: '64px'
                                                }}>
                                                    📦
                                                </div>
                                            )}

                                            <div style={{ padding: '16px' }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '8px' }}>
                                                    <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1F2937' }}>
                                                        {product.name}
                                                    </h3>
                                                    {isAdmin && (
                                                        <div style={{ display: 'flex', gap: '8px' }}>
                                                            <button
                                                                onClick={() => handleEditProduct(product)}
                                                                style={{
                                                                    padding: '6px 12px',
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
                                                                    padding: '6px 12px',
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
                                                
                                                <p style={{ color: '#6B7280', fontSize: '14px', marginBottom: '12px' }}>
                                                    {product.description}
                                                </p>
                                                
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                    <span style={{ fontSize: '24px', fontWeight: 'bold', color: '#2563EB' }}>
                                                        {product.price.toFixed(2)} €
                                                    </span>
                                                    <span style={{ fontSize: '12px', color: '#6B7280' }}>
                                                        Stock: {product.stock}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ))}
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
    
    # Validation des données
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
                "image_url": data.get("image_url", product.get("image_url", "")),
                "video_url": data.get("video_url", product.get("video_url", "")),
                "stock": int(data.get("stock", product["stock"]))
            })
            return jsonify(product)
    
    return jsonify({"error": "Produit non trouvé"}), 404

@app.route('/api/admin/products/<int:product_id>', methods=['DELETE'])
@require_admin
def delete_product(product_id):
    """Admin uniquement - Supprimer un produit"""
    global products
    initial_length = len(products)
    products = [p for p in products if p["id"] != product_id]
    
    if len(products) < initial_length:
        return jsonify({"success": True})
    return jsonify({"error": "Produit non trouvé"}), 404

@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "Mini app is running"})

# Protection contre les attaques courantes
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
