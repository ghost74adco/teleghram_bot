import os
import sys
import json
import csv
import asyncio
import logging
import hashlib
import math
import re
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import Dict, List, Set, Optional, Any, Tuple
from functools import wraps
from collections import defaultdict

# Telegram imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler,
    PicklePersistence
)

# Distance calculation
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

# ==================== DÉCORATEUR ERROR_HANDLER ====================

def error_handler(func):
    """Décorateur pour gérer les erreurs de manière uniforme"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"❌ Erreur dans {func.__name__}: {e}", exc_info=True)
            
            error_message = (
                "❌ Erreur technique\n\n"
                "Une erreur s'est produite. Veuillez réessayer."
            )
            
            try:
                if update.callback_query:
                    await update.callback_query.answer("Erreur technique", show_alert=True)
                    await update.callback_query.message.reply_text(error_message)
                elif update.message:
                    await update.message.reply_text(error_message)
            except Exception as notify_error:
                logger.error(f"Impossible de notifier l'erreur: {notify_error}")
    
    return wrapper



# Code Super Admin pour éditer la licence
SUPER_ADMIN_CODE = "ADMIN2025"  # Modifiez ce code selon vos besoins


# ==================== CONFIGURATION LOGGING ====================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

# ==================== CONSTANTES ====================

DATA_DIR = Path(".")
MEDIA_DIR = DATA_DIR / "media"

# ==================== SYSTÈME PRIX DÉGRESSIFS ====================

# États pour la conversation d'ajout de produit
PRODUCT_NAME, PRODUCT_PRICE_FR, PRODUCT_PRICE_CH, PRODUCT_PRICE_AU, PRODUCT_QUANTITY, PRODUCT_CATEGORY = range(6)


# Structure des prix dégressifs par pays
# Format: {country: {product_id: [{min_qty: X, max_qty: Y, price: Z}, ...]}}
TIERED_PRICING_FILE = DATA_DIR / "tiered_pricing.json"

def load_tiered_pricing():
    """Charge les prix dégressifs depuis le fichier JSON"""
    return load_json_file(TIERED_PRICING_FILE, {})

def save_tiered_pricing(data):
    """Sauvegarde les prix dégressifs"""
    return save_json_file(TIERED_PRICING_FILE, data)

def get_tiered_price(country, product_id, quantity):
    """Retourne le prix unitaire en fonction de la quantité"""
    tiered = load_tiered_pricing()
    
    if country not in tiered:
        return None
    
    if product_id not in tiered[country]:
        return None
    
    tiers = tiered[country][product_id]
    
    # Trier les tiers par quantité minimum
    sorted_tiers = sorted(tiers, key=lambda x: x.get('min_qty', 0))
    
    # Trouver le tier approprié
    for tier in sorted_tiers:
        min_qty = tier.get('min_qty', 0)
        max_qty = tier.get('max_qty', 999999)
        
        if min_qty <= quantity <= max_qty:
            return tier.get('price', 0)
    
    return None

def add_tiered_price(country, product_id, min_qty, max_qty, price):
    """Ajoute un palier de prix dégressif"""
    tiered = load_tiered_pricing()
    
    if country not in tiered:
        tiered[country] = {}
    
    if product_id not in tiered[country]:
        tiered[country][product_id] = []
    
    # Vérifier si un tier avec ces quantités existe déjà
    for i, tier in enumerate(tiered[country][product_id]):
        if tier.get('min_qty') == min_qty and tier.get('max_qty') == max_qty:
            # Mettre à jour le prix
            tiered[country][product_id][i]['price'] = price
            return save_tiered_pricing(tiered)
    
    # Ajouter nouveau tier
    tiered[country][product_id].append({
        'min_qty': min_qty,
        'max_qty': max_qty,
        'price': price
    })
    
    return save_tiered_pricing(tiered)

def remove_tiered_price(country, product_id, tier_index):
    """Supprime un palier de prix dégressif"""
    tiered = load_tiered_pricing()
    
    if country not in tiered or product_id not in tiered[country]:
        return False
    
    if 0 <= tier_index < len(tiered[country][product_id]):
        tiered[country][product_id].pop(tier_index)
        
        # Si plus de tiers, supprimer le produit
        if not tiered[country][product_id]:
            del tiered[country][product_id]
        
        # Si plus de produits, supprimer le pays
        if not tiered[country]:
            del tiered[country]
        
        return save_tiered_pricing(tiered)
    
    return False



BOT_VERSION = "4.0.0"


# Configuration auto-suppression des messages
AUTO_DELETE_ENABLED = True  # Active/désactive l'auto-suppression
AUTO_DELETE_DELAY = 600  # Délai en secondes (600 = 10 minutes)

# Messages à NE PAS supprimer (notifications de commande importantes)
PERMANENT_MESSAGE_TYPES = [
    'order_status_pending',      # Commande en attente de validation
    'order_status_validated',    # Commande validée
    'order_status_ready',        # Commande prête
    'order_status_delivered',    # Commande livrée
    'order_notification',        # Notification générale de commande
]
BOT_NAME = "E-Commerce Bot Multi-Admins"

# Limites
MAX_CART_ITEMS = 50
MAX_QUANTITY_PER_ITEM = 1000
MIN_ORDER_AMOUNT = 10

# Fichiers JSON
PRODUCTS_FILE = DATA_DIR / "products.json"
CONFIG_FILE = DATA_DIR / "config.json"
LICENSE_FILE = DATA_DIR / "license.json"
LANGUAGES_FILE = DATA_DIR / "languages.json"
ADMINS_FILE = DATA_DIR / "admins.json"

# Fichiers de données
ORDERS_FILE = DATA_DIR / "orders.csv"
USERS_FILE = DATA_DIR / "users.json"
CLIENT_HISTORY_FILE = DATA_DIR / "client_history.json"
LEDGER_FILE = DATA_DIR / "ledger.json"
SALARIES_FILE = DATA_DIR / "salaries.json"
COMMISSIONS_FILE = DATA_DIR / "commissions.json"
EXPENSES_FILE = DATA_DIR / "expenses.json"
VIP_CONFIG_FILE = DATA_DIR / "vip_config.json"
STOCK_HISTORY_FILE = DATA_DIR / "stock_history.json"
PRODUCT_COSTS_FILE = DATA_DIR / "product_costs.json"

# Créer répertoires
def ensure_dir(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return directory

ensure_dir(DATA_DIR)
ensure_dir(MEDIA_DIR)

logger.info(f"🤖 {BOT_NAME} v{BOT_VERSION}")

# ==================== SYSTÈME JSON ====================

def load_json_file(filepath: Path, default: Any = None) -> Any:
    """Charge un fichier JSON avec gestion d'erreurs"""
    if not filepath.exists():
        logger.warning(f"⚠️ Fichier manquant : {filepath.name}")
        return default if default is not None else {}
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"✅ Fichier chargé : {filepath.name}")
            return data
    except json.JSONDecodeError as e:
        logger.error(f"❌ Erreur JSON dans {filepath.name}: {e}")
        return default if default is not None else {}
    except Exception as e:
        logger.error(f"❌ Erreur lecture {filepath.name}: {e}")
        return default if default is not None else {}

def save_json_file(filepath: Path, data: Any) -> bool:
    """Sauvegarde un fichier JSON"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde {filepath.name}: {e}")
        return False

# Charger tous les JSON au démarrage
PRODUCTS_DATA = load_json_file(PRODUCTS_FILE, {})
CONFIG_DATA = load_json_file(CONFIG_FILE, {})
LICENSE_DATA = load_json_file(LICENSE_FILE, {})
LANGUAGES_DATA = load_json_file(LANGUAGES_FILE, {})
ADMINS_DATA = load_json_file(ADMINS_FILE, {})

logger.info(f"""
╔════════════════════════════════════════╗
║   BOT V{BOT_VERSION} - DÉMARRAGE           ║
╚════════════════════════════════════════╝
📦 Produits chargés : {len(PRODUCTS_DATA.get('products', {}))}
⚙️  Configuration : {'✅' if CONFIG_DATA else '❌'}
🔐 Licence Niveau : {LICENSE_DATA.get('license', {}).get('level', 1)}
🌐 Langues : {len(LANGUAGES_DATA)}
👥 Admins : {len(ADMINS_DATA.get('admins', {}))}
""")

# ==================== TOKEN ET ADMIN DEPUIS ENV ====================

def get_bot_token() -> str:
    """Récupère le token depuis ENV"""
    token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
    if token:
        logger.info("✅ Token récupéré depuis environnement")
        return token
    
    # Fallback config.json
    try:
        token = CONFIG_DATA.get('bot_token', '')
        if token and token != "VOTRE_BOT_TOKEN_ICI":
            logger.warning("⚠️ Token depuis config.json (dev local)")
            return token
    except:
        pass
    
    logger.error("❌ Token introuvable")
    return ""

def get_admin_id_from_env() -> Optional[int]:
    """Récupère l'admin ID depuis ENV"""
    admin_id_str = os.getenv('ADMIN_ID') or os.getenv('TELEGRAM_ADMIN_ID')
    
    if admin_id_str:
        try:
            admin_id = int(admin_id_str)
            logger.info(f"✅ Admin ID récupéré depuis environnement")
            return admin_id
        except ValueError:
            logger.error("❌ Admin ID invalide")
            return None
    
    # Fallback admins.json
    try:
        admins = ADMINS_DATA.get('admins', {})
        for uid_str, data in admins.items():
            if uid_str.isdigit() and data.get('active', True):
                admin_id = int(uid_str)
                logger.warning(f"⚠️ Admin ID depuis JSON (dev local)")
                return admin_id
    except:
        pass
    
    return None

# Définir ADMIN_ID global (compatible V3)
ADMIN_ID = get_admin_id_from_env()

if ADMIN_ID:
    logger.info(f"✅ ADMIN_ID configuré")
else:
    logger.error("❌ ADMIN_ID non configuré")

# ==================== COUCHE DE COMPATIBILITÉ V3 ↔ JSON ====================

class JSONDict(dict):
    """
    Dictionnaire magique qui émule les dicts V3 hardcodés
    mais lit les données depuis products.json
    """
    def __init__(self, country: str):
        super().__init__()
        self.country = country
        self._load_from_json()
    
    def _load_from_json(self):
        """Charge les prix depuis JSON (UNIQUEMENT depuis products.json)"""
        # Charger UNIQUEMENT depuis products.json (SEULEMENT les produits actifs)
        products = PRODUCTS_DATA.get('products', {})
        for product_id, product_data in products.items():
            # Vérifier si le produit est actif
            if not product_data.get('active', True):
                continue  # Ignorer les produits inactifs
            
            # Nom du produit en français
            name = product_data.get('name', {}).get('fr', product_id)
            # Prix pour ce pays
            price = product_data.get('price', {}).get(self.country, 0)
            # Stocker dans le dict SEULEMENT si prix > 0
            if price > 0:
                self[name] = price
    
    def reload(self):
        """Recharge depuis JSON après modification"""
        self.clear()
        self._load_from_json()

class QuantitiesDict(dict):
    """Dictionnaire magique pour les quantités disponibles"""
    def __init__(self):
        super().__init__()
        self._load_from_json()
    
    def _load_from_json(self):
        """Charge les quantités depuis JSON (seulement produits actifs)"""
        products = PRODUCTS_DATA.get('products', {})
        for product_id, product_data in products.items():
            # Ignorer les produits inactifs
            if not product_data.get('active', True):
                continue
            name = product_data.get('name', {}).get('fr', product_id)
            quantities = product_data.get('available_quantities', [1.0])
            self[name] = quantities
    
    def reload(self):
        self.clear()
        self._load_from_json()

class StockDict(dict):
    """Dictionnaire magique pour les stocks"""
    def __init__(self):
        super().__init__()
        self._load_from_json()
    
    def _load_from_json(self):
        """Charge les stocks depuis JSON (seulement produits actifs)"""
        products = PRODUCTS_DATA.get('products', {})
        for product_id, product_data in products.items():
            # Ignorer les produits inactifs
            if not product_data.get('active', True):
                continue
            name = product_data.get('name', {}).get('fr', product_id)
            # CORRECTION: 'quantity' et non 'stock'
            stock = product_data.get('quantity', 0)
            self[name] = stock
    
    def reload(self):
        self.clear()
        self._load_from_json()
    
    def save_to_json(self):
        """Sauvegarde les stocks dans JSON"""
        products = PRODUCTS_DATA.get('products', {})
        
        # Créer mapping nom → id
        name_to_id = {}
        for product_id, product_data in products.items():
            name = product_data.get('name', {}).get('fr', product_id)
            name_to_id[name] = product_id
        
        # Mettre à jour les stocks (CORRECTION: 'quantity' et non 'stock')
        for name, stock in self.items():
            product_id = name_to_id.get(name)
            if product_id and product_id in products:
                products[product_id]['quantity'] = stock
        
        # Sauvegarder
        PRODUCTS_DATA['products'] = products
        return save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)

# ==================== VARIABLES COMPATIBLES V3 ====================

# Prix par pays (lisent depuis JSON mais se comportent comme les anciens dicts)
PRIX_FR = JSONDict('FR')
PRIX_CH = JSONDict('CH')
PRIX_AU = JSONDict('AU')

# Quantités disponibles par produit
QUANTITES_DISPONIBLES = QuantitiesDict()

# Stocks (avec sauvegarde automatique dans JSON)
STOCK_PRODUITS = StockDict()

logger.info("✅ Couche de compatibilité V3↔JSON chargée")
logger.info(f"   📦 Produits PRIX_FR : {len(PRIX_FR)} items")
logger.info(f"   📦 Produits PRIX_CH : {len(PRIX_CH)} items")
logger.info(f"   📦 Quantités : {len(QUANTITES_DISPONIBLES)} items")
logger.info(f"   📦 Stocks : {len(STOCK_PRODUITS)} items")

# ==================== FONCTIONS HELPER ====================

def reload_products():
    """Recharge tous les produits depuis JSON (après modification admin)"""
    global PRODUCTS_DATA, PRIX_FR, PRIX_CH, PRIX_AU, QUANTITES_DISPONIBLES, STOCK_PRODUITS
    
    PRODUCTS_DATA = load_json_file(PRODUCTS_FILE, {})
    PRIX_FR.reload()
    PRIX_CH.reload()
    PRIX_AU.reload()
    QUANTITES_DISPONIBLES.reload()
    STOCK_PRODUITS.reload()
    
    logger.info("♻️ Produits rechargés depuis JSON")

def save_stock():
    """Sauvegarde les stocks dans JSON"""
    return STOCK_PRODUITS.save_to_json()

# ==================== DÉCORATEURS ET FONCTIONS DE LOGGING ====================

def log_callback(func):
    """Décorateur pour logger automatiquement tous les callbacks"""
    @wraps(func)
    async def wrapper(update, context):
        query = update.callback_query
        user_id = query.from_user.id
        username = query.from_user.username or "N/A"
        callback_data = query.data
        
        logger.info(f"🔘 CALLBACK: {func.__name__}")
        logger.info(f"   👤 User: {user_id} (@{username})")
        logger.info(f"   📲 Data: {callback_data}")
        
        try:
            result = await func(update, context)
            logger.info(f"✅ CALLBACK SUCCESS: {func.__name__}")
            return result
        except Exception as e:
            logger.error(f"❌ CALLBACK ERROR: {func.__name__}")
            logger.error(f"   Error: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
            raise
    
    return wrapper

def log_handler(func):
    """Décorateur pour logger automatiquement tous les handlers"""
    @wraps(func)
    async def wrapper(update, context):
        user = update.effective_user
        message_text = update.message.text if update.message else "N/A"
        
        logger.info(f"📩 HANDLER: {func.__name__}")
        logger.info(f"   👤 User: {user.id} (@{user.username or 'N/A'})")
        logger.info(f"   💬 Message: {message_text[:50]}")
        
        try:
            result = await func(update, context)
            logger.info(f"✅ HANDLER SUCCESS: {func.__name__}")
            return result
        except Exception as e:
            logger.error(f"❌ HANDLER ERROR: {func.__name__}")
            logger.error(f"   Error: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
            raise
    
    return wrapper

def log_action(action: str, user_id: int, details: str = ""):
    """Log une action utilisateur"""
    logger.info(f"🎬 ACTION: {action} | User: {user_id} | {details}")

def log_state_change(user_id: int, state_name: str, new_value):
    """Log un changement d'état"""
    logger.info(f"🔄 STATE: {state_name}={new_value} | User: {user_id}")

def log_db_operation(operation: str, table: str, details: str = ""):
    """Log une opération base de données"""
    logger.info(f"💾 DB: {operation} | Table: {table} | {details}")

def log_order_status(order_id: str, old_status: str, new_status: str, admin_id: int = None):
    """Log un changement de statut de commande"""
    logger.info(f"📦 ORDER STATUS: {order_id} | {old_status} → {new_status}" + (f" | By admin: {admin_id}" if admin_id else ""))

# ==================== CHARGEMENT VARIABLES D'ENVIRONNEMENT ====================

def load_env_file(filepath: str = "infos.env") -> dict:
    """Charge les variables depuis le fichier .env"""
    env_vars = {}
    env_path = Path(filepath)
    
    if not env_path.exists():
        logger.error(f"❌ Fichier {filepath} introuvable")
        return env_vars
    
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env_vars[key] = value
                    os.environ[key] = value
        
        logger.info(f"✅ Variables: {filepath}")
        return env_vars
    
    except Exception as e:
        logger.error(f"❌ Erreur lecture {filepath}: {e}")
        return env_vars

# Charger les variables
ENV_VARS = load_env_file("infos.env")

# ==================== VARIABLES D'ENVIRONNEMENT ESSENTIELLES ====================

# TOKEN et ADMIN_ID sont récupérés dans la fonction main()
# via get_bot_token() et get_admin_id_from_env()

# Admin principal (pour initialisation)
# Admin ID déjà défini globalement (ligne 199)


# Adresse admin pour calcul distance
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS", "Paris, France")

# OpenRouteService (optionnel)
OPENROUTE_API_KEY = os.getenv("OPENROUTE_API_KEY")

# Les logs de token/admin sont dans la fonction main()

# ==================== CONFIGURATION DISQUE PERSISTANT ====================

# Détection automatique de l'environnement
if os.path.exists("/data"):
    DATA_DIR = Path("/data")
    logger.info("✅ Utilisation du disque persistant : /data")
elif os.path.exists("/persistent"):
    DATA_DIR = Path("/persistent")
    logger.info("✅ Utilisation du disque persistant : /persistent")
else:
    DATA_DIR = Path(__file__).parent / "data"
    DATA_DIR.mkdir(exist_ok=True)
    logger.info(f"✅ Mode local : {DATA_DIR}")

# Créer les sous-dossiers
MEDIA_DIR = DATA_DIR / "media"
MEDIA_DIR.mkdir(exist_ok=True)

ADMINS_FILE = DATA_DIR / "admins.json"
PRODUCT_REGISTRY_FILE = DATA_DIR / "product_registry.json"
PRICES_FILE = DATA_DIR / "prices.json"
AVAILABLE_PRODUCTS_FILE = DATA_DIR / "available_products.json"
USERS_FILE = DATA_DIR / "users.json"
STOCKS_FILE = DATA_DIR / "stocks.json"
PROMO_CODES_FILE = DATA_DIR / "promo_codes.json"
CLIENT_HISTORY_FILE = DATA_DIR / "client_history.json"
REFERRALS_FILE = DATA_DIR / "referrals.json"
HORAIRES_FILE = DATA_DIR / "horaires.json"
STATS_FILE = DATA_DIR / "stats.json"
PRICING_TIERS_FILE = DATA_DIR / "pricing_tiers.json"

# ==================== CONSTANTES MÉTIER ====================

FRAIS_POSTAL_EU = 10   # France/Suisse
FRAIS_POSTAL_AU = 30   # Australie
FRAIS_POSTAL = FRAIS_POSTAL_EU  # Par défaut (compatibilité)
FRAIS_MEETUP = 0
VIP_THRESHOLD = 500
VIP_DISCOUNT = 5
REFERRAL_REWARD = 5

# ==================== CONFIGURATION SYSTÈME FINANCIER AVANCÉ ====================

# Poids à peser par produit (ratio de pesée)
PRODUCT_WEIGHTS = {
    # Exception : Coco et K - 1g commandé = 0.9g à peser
    "Coco": {"type": "weight", "ratio": 0.9},
    "K": {"type": "weight", "ratio": 0.9},
    
    # Crystal : poids normal
    "Crystal": {"type": "weight", "ratio": 1.0},
    
    # Pills : unités (pas de pesée)
    "Pills Squid-Game": {"type": "unit", "ratio": 1},
    "Pills Punisher": {"type": "unit", "ratio": 1}
}

# Prix coûtants (prix d'achat) en €
PRODUCT_COSTS = {
    "Coco": 45.00,              # €/g
    "K": 50.00,                 # €/g
    "Crystal": 55.00,           # €/g
    "Pills Squid-Game": 8.00,   # €/unité
    "Pills Punisher": 8.00      # €/unité
}

# Fichiers de données financières
PAYROLL_FILE = DATA_DIR / "payroll.json"
EXPENSES_FILE = DATA_DIR / "expenses.json"

# Catégories de consommables
EXPENSE_CATEGORIES = ["Emballage", "Transport", "Matériel", "Autre"]

# ==================== ÉTATS DE CONVERSATION ====================

ADMIN_MANAGE_MENU = 120
ADMIN_ADD_ID = 121
ADMIN_ADD_LEVEL = 122
ADMIN_REMOVE_CONFIRM = 123
ADMIN_VIEW_LIST = 124

# ==================== MÉTHODE DE CALCUL DISTANCE ====================

DISTANCE_METHOD = "geopy"
distance_client = Nominatim(user_agent="telegram_bot_v3", timeout=10)

if OPENROUTE_API_KEY:
    try:
        import openrouteservice
        distance_client = openrouteservice.Client(key=OPENROUTE_API_KEY)
        DISTANCE_METHOD = "openroute"
        logger.info("✅ OpenRouteService configuré")
    except ImportError:
        logger.warning("⚠️ openrouteservice non installé, fallback sur geopy")
        distance_client = Nominatim(user_agent="telegram_bot_v3", timeout=10)
        DISTANCE_METHOD = "geopy"
    except Exception as e:
        logger.warning(f"⚠️ Erreur OpenRouteService: {e}, fallback sur geopy")
        distance_client = Nominatim(user_agent="telegram_bot_v3", timeout=10)
        DISTANCE_METHOD = "geopy"
else:
    distance_client = Nominatim(user_agent="telegram_bot_v3", timeout=10)
    logger.info("✅ Geopy - Distance approximative")

if distance_client is None:
    distance_client = Nominatim(user_agent="telegram_bot_v3", timeout=10)
    logger.warning("⚠️ Fallback final sur Geopy")


# ==================== SYSTÈME DE LICENCES ====================

# Niveaux de licence
LICENSE_LEVELS = {
    1: {
        'name': 'Basic',
        'max_products': 5,
        'max_admins': 1,
        'features': ['basic_commerce', 'orders', 'cart'],
        'disabled': ['vip', 'promos', 'salaries', 'commissions', 'ledger', 'multi_admin']
    },
    2: {
        'name': 'Pro',
        'max_products': 20,
        'max_admins': 3,
        'features': ['basic_commerce', 'orders', 'cart', 'vip', 'promos', 'stats'],
        'disabled': ['salaries', 'commissions', 'ledger']
    },
    3: {
        'name': 'Enterprise',
        'max_products': 999,
        'max_admins': 999,
        'features': ['all'],
        'disabled': []
    }
}

def get_license_level() -> int:
    """Récupère le niveau de licence actuel"""
    try:
        license_info = LICENSE_DATA.get('license', {})
        level = license_info.get('level', 1)
        return min(max(level, 1), 3)  # Entre 1 et 3
    except:
        return 1

def get_license_info() -> dict:
    """Récupère les infos complètes de licence"""
    level = get_license_level()
    return LICENSE_LEVELS.get(level, LICENSE_LEVELS[1])

def is_feature_allowed(feature: str) -> bool:
    """Vérifie si une fonctionnalité est autorisée"""
    license_info = get_license_info()
    
    # Niveau 3 = tout autorisé
    if 'all' in license_info['features']:
        return True
    
    # Vérifier si désactivé
    if feature in license_info['disabled']:
        return False
    
    # Vérifier si dans features
    return feature in license_info['features']

def check_product_limit() -> tuple:
    """Vérifie si on peut ajouter un produit"""
    license_info = get_license_info()
    max_products = license_info['max_products']
    
    products = PRODUCTS_DATA.get('products', {})
    current = len(products)
    
    can_add = current < max_products
    
    return can_add, current, max_products

def check_admin_limit() -> tuple:
    """Vérifie si on peut ajouter un admin"""
    license_info = get_license_info()
    max_admins = license_info['max_admins']
    
    admins = load_admins()
    current = len(admins)
    
    can_add = current < max_admins
    
    return can_add, current, max_admins

@error_handler
async def show_license_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les infos de licence"""
    query = update.callback_query if update.callback_query else None
    
    if query:
        await query.answer()
    
    level = get_license_level()
    license_info = get_license_info()
    
    products = PRODUCTS_DATA.get('products', {})
    admins = load_admins()
    
    features_text = ""
    if 'all' in license_info['features']:
        features_text = "✅ Toutes les fonctionnalités"
    else:
        features_map = {
            'basic_commerce': '🛒 Commerce de base',
            'orders': '📦 Gestion commandes',
            'cart': '🛍️ Panier',
            'vip': '⭐ Système VIP',
            'promos': '🎁 Codes promo',
            'stats': '📊 Statistiques',
            'salaries': '💼 Salaires',
            'commissions': '💰 Commissions',
            'ledger': '📒 Livre de comptes'
        }
        
        for feature in license_info['features']:
            if feature in features_map:
                features_text += f"{features_map[feature]}\n"
    
    disabled_text = ""
    if license_info['disabled']:
        disabled_text = "\n❌ Fonctions désactivées :\n"
        features_map = {
            'vip': '⭐ VIP',
            'promos': '🎁 Codes promo',
            'salaries': '💼 Salaires',
            'commissions': '💰 Commissions',
            'ledger': '📒 Livre de comptes',
            'multi_admin': '👥 Multi-admins'
        }
        
        for feature in license_info['disabled']:
            if feature in features_map:
                disabled_text += f"{features_map[feature]}\n"
    
    message = f"""🔐 INFORMATIONS LICENCE

Niveau : {level} - {license_info['name']}

📦 Produits : {len(products)}/{license_info['max_products']}
👥 Admins : {len(admins)}/{license_info['max_admins']}

✅ Fonctionnalités actives :
{features_text}
{disabled_text}

━━━━━━━━━━━━━━━━━━━━━━

Pour upgrader votre licence, contactez le support.
"""
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_settings" if query else "admin_panel")]]
    
    if query:
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

# ==================== GESTION DES ADMINS ====================

def load_admins() -> Dict:
    """Charge la liste des administrateurs depuis admins.json (compatible V3 et V4)"""
    if ADMINS_FILE.exists():
        try:
            with open(ADMINS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Si structure V4 (avec clé "admins")
                if 'admins' in data:
                    admins_v4 = data['admins']
                    # Convertir en format V3 pour compatibilité
                    admins_v3 = {}
                    for uid, user_data in admins_v4.items():
                        # Ignorer les placeholders
                        if uid == "ADMIN_ID_ICI":
                            continue
                        
                        admins_v3[uid] = {
                            'level': user_data.get('role', 'admin'),  # role → level
                            'name': user_data.get('name', 'Admin'),
                            'added_by': user_data.get('added_by', 'unknown'),
                            'added_at': user_data.get('added_at', ''),
                            'permissions': ['all'] if user_data.get('role') == 'super_admin' else [],
                            'active': user_data.get('active', True)
                        }
                    
                    logger.info(f"✅ Admins chargés (format V4): {len(admins_v3)} admin(s)")
                    return admins_v3
                
                # Sinon format V3 (direct)
                logger.info(f"✅ Admins chargés (format V3): {len(data)} admin(s)")
                return data
                
        except Exception as e:
            logger.error(f"❌ Erreur lecture admins.json: {e}")
            return {}
    else:
        logger.warning("⚠️ Fichier admins.json non trouvé, création...")
        return {}


def save_admins(admins: Dict) -> bool:
    """Sauvegarde les administrateurs dans admins.json (format V3 uniquement)"""
    try:
        # Sauvegarder en format V3 (plus simple pour le code V3)
        # Si besoin de format V4, le faire manuellement
        with open(ADMINS_FILE, 'w', encoding='utf-8') as f:
            json.dump(admins, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Admins sauvegardés: {len(admins)} administrateur(s)")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde admins: {e}")
        return False

def init_admins() -> Dict:
    """Initialise le système d'admins (crée le super-admin si nécessaire)"""
    admins = load_admins()
    
    if not admins:
        logger.info("🔧 Initialisation du premier super-admin...")
        admins[str(ADMIN_ID)] = {
            'level': 'super_admin',
            'name': 'Proprietaire',
            'added_by': 'system',
            'added_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'permissions': ['all']
        }
        save_admins(admins)
        logger.info(f"✅ Super-admin créé: {ADMIN_ID}")
    
    return admins

def is_admin(user_id: int) -> bool:
    """Vérifie si un utilisateur est admin"""
    # ADMIN_ID depuis ENV est TOUJOURS admin
    if ADMIN_ID and user_id == ADMIN_ID:
        return True
    
    # Puis vérifier dans admins.json
    admins = load_admins()
    return str(user_id) in admins

def is_super_admin(user_id: int) -> bool:
    """Vérifie si un utilisateur est super-admin"""
    # ADMIN_ID depuis ENV est TOUJOURS super_admin
    if ADMIN_ID and user_id == ADMIN_ID:
        return True
    
    # Puis vérifier dans admins.json
    admins = load_admins()
    user_data = admins.get(str(user_id))
    if not user_data:
        return False
    return user_data.get('level') == 'super_admin'

def get_admin_info(user_id: int) -> Optional[Dict]:
    """Récupère les informations complètes d'un admin"""
    admins = load_admins()
    return admins.get(str(user_id))

def get_admin_level(user_id: int) -> Optional[str]:
    """Récupère le niveau d'un admin"""
    info = get_admin_info(user_id)
    return info.get('level') if info else None

def get_admin_ids() -> List[int]:
    """Retourne la liste des IDs de tous les admins"""
    admins = load_admins()
    return [int(uid) for uid in admins.keys()]

# Initialiser les admins au démarrage
ADMINS = init_admins()
logger.info(f"✅ Bot configuré avec {len(ADMINS)} administrateur(s)")

# ==================== EMOJI THEME ====================

EMOJI_THEME = {
    'success': '✅', 'error': '❌', 'warning': '⚠️', 'info': 'ℹ️',
    'money': '💰', 'cart': '🛒', 'delivery': '🚚', 'product': '📦',
    'admin': '👨‍💼', 'user': '👤', 'stats': '📊', 'gift': '🎁',
    'vip': '⭐', 'celebration': '🎉', 'wave': '👋', 'history': '📜',
    'support': '💬', 'security': '🔒', 'online': '🟢', 'offline': '🔴'
}

# ==================== DICTIONNAIRES PRODUITS ====================

PRODUCT_CODES = {}
PILL_SUBCATEGORIES = {}
ROCK_SUBCATEGORIES = {}
IMAGES_PRODUITS = {}
VIDEOS_PRODUITS = {}

# ==================== TRADUCTIONS ====================

TRANSLATIONS = {
    'fr': {
        'welcome': 'Bienvenue',
        'cart_title': '🛒 Votre panier :',
        'menu': 'Menu principal'
    },
    'en': {
        'welcome': 'Welcome',
        'cart_title': '🛒 Your cart:',
        'menu': 'Main menu'
    }
}

def load_translations():
    """Charge les traductions depuis languages.json"""
    try:
        lang_file = DATA_DIR / "languages.json"
        if lang_file.exists():
            with open(lang_file, 'r', encoding='utf-8') as f:
                import json
                data = json.load(f)
                translations = data.get('translations', {})
                languages = data.get('languages', {})
                
                # Si les données sont chargées correctement
                if translations and languages:
                    return translations, languages
        
        # Fallback: retourner les données en dur si le fichier n'existe pas ou est vide
        print("⚠️ languages.json non trouvé ou vide - utilisation du fallback")
    except Exception as e:
        print(f"❌ Erreur chargement languages.json: {e}")
    
    # FALLBACK: Configuration en dur
    fallback_languages = {
        'fr': {'name': 'Français', 'flag': '🇫🇷', 'active': True},
        'en': {'name': 'English', 'flag': '🇬🇧', 'active': True},
        'de': {'name': 'Deutsch', 'flag': '🇩🇪', 'active': True},
        'es': {'name': 'Español', 'flag': '🇪🇸', 'active': True},
        'it': {'name': 'Italiano', 'flag': '🇮🇹', 'active': True}
    }
    
    fallback_translations = {
        'welcome': {
            'fr': 'Bienvenue {name} !',
            'en': 'Welcome {name}!',
            'de': 'Willkommen {name}!',
            'es': '¡Bienvenido {name}!',
            'it': 'Benvenuto {name}!'
        },
        'choose_language': {
            'fr': '🌍 Choisir la langue',
            'en': '🌍 Choose language',
            'de': '🌍 Sprache wählen',
            'es': '🌍 Elegir idioma',
            'it': '🌍 Scegli lingua'
        },
        'choose_country': {
            'fr': 'Choisissez votre pays',
            'en': 'Choose your country',
            'de': 'Wählen Sie Ihr Land',
            'es': 'Elija su país',
            'it': 'Scegli il tuo paese'
        },
        'cart': {
            'fr': '🛒 Panier',
            'en': '🛒 Cart',
            'de': '🛒 Warenkorb',
            'es': '🛒 Carrito',
            'it': '🛒 Carrello'
        },
        'help': {
            'fr': 'Aide',
            'en': 'Help',
            'de': 'Hilfe',
            'es': 'Ayuda',
            'it': 'Aiuto'
        }
    }
    
    return fallback_translations, fallback_languages

# Charger les traductions au démarrage
LANG_TRANSLATIONS, LANG_CONFIG = load_translations()

def tr(context_or_user_data, key: str, default_lang: str = 'fr', **kwargs) -> str:
    """
    Traduction intelligente avec support de variables
    
    Args:
        context_or_user_data: context.user_data (dict) ou context (ContextTypes)
        key: Clé de traduction
        default_lang: Langue par défaut
        **kwargs: Variables à remplacer dans la traduction (ex: name="John")
    
    Returns:
        Texte traduit avec variables remplacées
    """
    # Déterminer si c'est user_data ou context
    if isinstance(context_or_user_data, dict):
        user_data = context_or_user_data
    else:
        user_data = getattr(context_or_user_data, 'user_data', {})
    
    # Récupérer la langue
    lang = user_data.get('language', default_lang)
    
    # Si la langue n'existe pas, fallback sur fr
    if lang not in LANG_CONFIG or not LANG_CONFIG[lang].get('active', False):
        lang = 'fr'
    
    # Récupérer la traduction
    translation = LANG_TRANSLATIONS.get(key, {}).get(lang, key)
    
    # Remplacer les variables {name}, {percent}, etc.
    if kwargs:
        try:
            translation = translation.format(**kwargs)
        except KeyError:
            pass  # Garder la traduction même si une variable manque
    
    return translation

# ==================== GÉNÉRATEURS ====================

def generate_referral_code() -> str:
    """Génère un code de parrainage unique"""
    import random
    import string
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def generate_order_id() -> str:
    """Génère un ID de commande unique"""
    timestamp = int(datetime.now().timestamp())
    return f"CMD{timestamp}"

# ==================== FONCTION D'ANONYMISATION ====================

def anonymize_id(user_id: int) -> str:
    """Anonymise un ID utilisateur avec hash"""
    # Créer un hash court et lisible de l'ID
    hash_obj = hashlib.sha256(str(user_id).encode())
    hash_hex = hash_obj.hexdigest()[:8].upper()
    return f"User-{hash_hex}"

def anonymize_admin_id(admin_id: int) -> str:
    """Anonymise un ID admin avec hash"""
    hash_obj = hashlib.sha256(str(admin_id).encode())
    hash_hex = hash_obj.hexdigest()[:8].upper()
    return f"Admin-{hash_hex}"

# ==================== SYSTÈME FINANCIER AVANCÉ ====================

def calculate_weight_to_prepare(product_name: str, quantity_ordered: float) -> dict:
    """
    Calcule le poids/unité à préparer pour une commande
    
    Returns:
        {
            'to_prepare': float,  # Quantité à peser/préparer
            'type': str,          # 'weight' ou 'unit'
            'unit': str,          # 'g' ou 'unités'
            'note': str           # Note pour l'admin
        }
    """
    if product_name not in PRODUCT_WEIGHTS:
        return {
            'to_prepare': quantity_ordered,
            'type': 'weight',
            'unit': 'g',
            'note': f'Peser {quantity_ordered:.1f}g normalement'
        }
    
    config = PRODUCT_WEIGHTS[product_name]
    
    if config['type'] == 'unit':
        return {
            'to_prepare': quantity_ordered,
            'type': 'unit',
            'unit': 'unités',
            'note': f'{int(quantity_ordered)} unité(s) - Pas de pesée'
        }
    else:
        weight_to_prepare = quantity_ordered * config['ratio']
        return {
            'to_prepare': weight_to_prepare,
            'type': 'weight',
            'unit': 'g',
            'note': f'Peser {weight_to_prepare:.1f}g (ratio {config["ratio"]})'
        }

def calculate_margins(product_name: str, quantity: float, selling_price: float) -> dict:
    """
    Calcule les marges d'une vente
    
    Returns:
        {
            'cost': float,        # Coût total
            'revenue': float,     # CA (prix de vente)
            'margin': float,      # Marge brute
            'margin_rate': float  # Taux de marge en %
        }
    """
    if product_name not in PRODUCT_COSTS:
        return {
            'cost': 0,
            'revenue': selling_price,
            'margin': selling_price,
            'margin_rate': 100.0
        }
    
    unit_cost = PRODUCT_COSTS[product_name]
    total_cost = unit_cost * quantity
    margin = selling_price - total_cost
    margin_rate = (margin / selling_price * 100) if selling_price > 0 else 0
    
    return {
        'cost': total_cost,
        'revenue': selling_price,
        'margin': margin,
        'margin_rate': margin_rate
    }

def load_payroll():
    """Charge les données de payes"""
    if PAYROLL_FILE.exists():
        with open(PAYROLL_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "payments": [],
        "balances": {}
    }

def save_payroll(data):
    """Sauvegarde les données de payes"""
    with open(PAYROLL_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_expenses():
    """Charge les données de consommables"""
    if EXPENSES_FILE.exists():
        with open(EXPENSES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "expenses": [],
        "categories": EXPENSE_CATEGORIES
    }

def save_expenses(data):
    """Sauvegarde les données de consommables"""
    with open(EXPENSES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_salary_config():
    """Charge la configuration des salaires"""
    salary_config_file = DATA_DIR / "salary_config.json"
    if salary_config_file.exists():
        with open(salary_config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"admins": {}}

def save_salary_config(data):
    """Sauvegarde la configuration des salaires"""
    salary_config_file = DATA_DIR / "salary_config.json"
    with open(salary_config_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_commissions():
    """Charge les commissions accumulées"""
    commissions_file = DATA_DIR / "commissions.json"
    if commissions_file.exists():
        with open(commissions_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_commissions(data):
    """Sauvegarde les commissions"""
    commissions_file = DATA_DIR / "commissions.json"
    with open(commissions_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ==================== DÉCORATEUR ERROR HANDLER ====================

def error_handler(func):
    """Décorateur pour gérer les erreurs de manière uniforme"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"❌ Erreur dans {func.__name__}: {e}", exc_info=True)
            
            error_message = (
                f"{EMOJI_THEME['error']} Erreur technique\n\n"
                "Une erreur s'est produite. Veuillez réessayer."
            )
            
            try:
                if update.callback_query:
                    await update.callback_query.answer("Erreur technique", show_alert=True)
                    await update.callback_query.message.reply_text(error_message)
                elif update.message:
                    await update.message.reply_text(error_message)
            except Exception as notify_error:
                logger.error(f"Impossible de notifier l'erreur: {notify_error}")
    
    return wrapper

# ==================== HELPERS ====================

def format_datetime(dt: datetime) -> str:
    return dt.strftime('%d/%m/%Y %H:%M:%S')

def format_price(price: float) -> str:
    return f"{price:.2f}€"

def ensure_dir(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return directory

# ==================== CONSTANTES SUPPLÉMENTAIRES ====================

MAX_CART_ITEMS = 50
MAX_QUANTITY_PER_ITEM = 1000
MIN_ORDER_AMOUNT = 10

BOT_VERSION = "3.1.1"
BOT_NAME = "E-Commerce Bot Multi-Admins"

logger.info(f"🤖 {BOT_NAME} v{BOT_VERSION}")
# ==================== BLOC 2 : FONCTIONS DE PERSISTANCE + GESTION DONNÉES ====================

# ==================== FONCTIONS DE CHARGEMENT ====================

def load_users():
    """Charge les utilisateurs"""
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_client_history():
    """Charge l'historique client"""
    if CLIENT_HISTORY_FILE.exists():
        try:
            with open(CLIENT_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_stats():
    """Charge les statistiques"""
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_product_registry():
    """Charge le registre des produits"""
    if PRODUCT_REGISTRY_FILE.exists():
        try:
            with open(PRODUCT_REGISTRY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("products", {})
        except:
            return {}
    return {}

def load_prices():
    """Charge les prix"""
    if PRICES_FILE.exists():
        try:
            with open(PRICES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"FR": PRIX_FR.copy(), "CH": PRIX_CH.copy()}
    return {"FR": PRIX_FR.copy(), "CH": PRIX_CH.copy()}

def load_stocks():
    """Charge les stocks"""
    if STOCKS_FILE.exists():
        try:
            with open(STOCKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_promo_codes():
    """Charge les codes promo"""
    if PROMO_CODES_FILE.exists():
        try:
            with open(PROMO_CODES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_referrals():
    """Charge les données de parrainage"""
    if REFERRALS_FILE.exists():
        try:
            with open(REFERRALS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

# ==================== VÉRIFICATION DE LA PERSISTANCE ====================

def verify_data_persistence():
    """Vérifie que les données sont bien persistées"""
    test_file = DATA_DIR / "persistence_test.txt"
    
    if test_file.exists():
        try:
            with open(test_file, 'r') as f:
                boot_count = int(f.read().strip())
            boot_count += 1
        except:
            boot_count = 1
    else:
        boot_count = 1
    
    with open(test_file, 'w') as f:
        f.write(str(boot_count))
    
    logger.info(f"🔄 Démarrage #{boot_count} - Données dans: {DATA_DIR}")
    
    files_found = []
    required_files = [
        "product_registry.json", "prices.json", "available_products.json",
        "users.json", "stocks.json", "promo_codes.json", 
        "client_history.json", "referrals.json", "admins.json"
    ]
    
    for file in required_files:
        if (DATA_DIR / file).exists():
            files_found.append(file)
    
    if files_found:
        logger.info(f"✅ Fichiers trouvés: {', '.join(files_found)}")
    else:
        logger.warning("⚠️ Aucun fichier de données trouvé - Premier démarrage")
    
    return boot_count

# ==================== GESTION DES ADMINISTRATEURS ====================

async def add_admin(user_id: int, level: str, added_by: int, name: str = "Admin") -> bool:
    """Ajoute un nouvel administrateur"""
    global ADMINS
    
    if str(user_id) in ADMINS:
        logger.warning(f"⚠️ User {user_id} est déjà admin")
        return False
    
    permissions_map = {
        'super_admin': ['all'],
        'admin': ['manage_products', 'manage_stocks', 'view_orders', 
                  'validate_payment', 'manage_promos'],
        'moderator': ['view_orders', 'customer_support']
    }
    
    ADMINS[str(user_id)] = {
        'level': level,
        'name': name,
        'added_by': str(added_by),
        'added_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'permissions': permissions_map.get(level, [])
    }
    
    save_admins(ADMINS)
    logger.info(f"✅ Admin ajouté: {user_id} ({level}) par {added_by}")
    
    return True

async def remove_admin(user_id: int, removed_by: int) -> bool:
    """Supprime un administrateur"""
    global ADMINS
    
    if str(user_id) not in ADMINS:
        logger.warning(f"⚠️ User {user_id} n'est pas admin")
        return False
    
    if user_id == removed_by:
        logger.warning(f"⚠️ Admin {user_id} a tenté de se supprimer")
        return False
    
    admin_info = ADMINS[str(user_id)]
    del ADMINS[str(user_id)]
    save_admins(ADMINS)
    
    logger.info(f"🗑️ Admin supprimé: {user_id} ({admin_info['level']}) par {removed_by}")
    
    return True

def get_admin_stats() -> Dict:
    """Retourne les statistiques des admins"""
    stats = {
        'total': len(ADMINS),
        'super_admins': 0,
        'admins': 0,
        'moderators': 0
    }
    
    for admin_info in ADMINS.values():
        level = admin_info.get('level', 'admin')
        if level == 'super_admin':
            stats['super_admins'] += 1
        elif level == 'admin':
            stats['admins'] += 1
        elif level == 'moderator':
            stats['moderators'] += 1
    
    return stats

def format_admin_list() -> str:
    """Formate la liste des admins pour affichage"""
    if not ADMINS:
        return "Aucun administrateur"
    
    super_admins = []
    admins = []
    moderators = []
    
    for user_id, info in ADMINS.items():
        level = info.get('level', 'admin')
        name = info.get('name', 'Admin')
        added_at = info.get('added_at', 'N/A')
        
        # Anonymiser l'ID
        anonymous_id = anonymize_admin_id(int(user_id))
        admin_str = f"• {name}\n  ID: {anonymous_id}\n  Depuis: {added_at[:10]}"
        
        if level == 'super_admin':
            super_admins.append(admin_str)
        elif level == 'admin':
            admins.append(admin_str)
        else:
            moderators.append(admin_str)
    
    result = ""
    
    if super_admins:
        result += f"👑 SUPER-ADMINS ({len(super_admins)})\n"
        result += "━━━━━━━━━━━━━━━━━━━━━━\n"
        result += "\n\n".join(super_admins)
        result += "\n\n"
    
    if admins:
        result += f"🔐 ADMINS ({len(admins)})\n"
        result += "━━━━━━━━━━━━━━━━━━━━━━\n"
        result += "\n\n".join(admins)
        result += "\n\n"
    
    if moderators:
        result += f"🛡️ MODÉRATEURS ({len(moderators)})\n"
        result += "━━━━━━━━━━━━━━━━━━━━━━\n"
        result += "\n\n".join(moderators)
    
    return result

# ==================== GESTION DU REGISTRE PRODUITS ====================

def save_product_registry(registry):
    """Sauvegarde le registre des produits"""
    try:
        with open(PRODUCT_REGISTRY_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "products": registry,
                "last_updated": datetime.now().isoformat(),
                "version": "3.0"
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Registre sauvegardé: {len(registry)} produits")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde registre: {e}")
        return False

def create_initial_registry():
    """Crée le registre initial (vide - les produits sont créés via /migrate ou /admin)"""
    return {}

def init_product_codes():
    """Initialise tous les dictionnaires produits depuis le registre"""
    global PRODUCT_CODES, PILL_SUBCATEGORIES, ROCK_SUBCATEGORIES, IMAGES_PRODUITS, VIDEOS_PRODUITS
    
    logger.info("🔄 Initialisation des produits depuis le registre...")
    
    registry = load_product_registry()
    
    if not registry:
        logger.info("📦 Création du registre initial...")
        registry = create_initial_registry()
        save_product_registry(registry)
    
    PRODUCT_CODES.clear()
    PILL_SUBCATEGORIES.clear()
    ROCK_SUBCATEGORIES.clear()
    IMAGES_PRODUITS.clear()
    VIDEOS_PRODUITS.clear()
    
    for code, product_data in registry.items():
        name = product_data["name"]
        category = product_data.get("category", "powder")
        
        PRODUCT_CODES[code] = name
        
        if category == "pill":
            PILL_SUBCATEGORIES[code] = name
        elif category == "rock":
            ROCK_SUBCATEGORIES[code] = name
        
        if product_data.get("image"):
            image_path = MEDIA_DIR / product_data["image"]
            IMAGES_PRODUITS[name] = image_path
        
        if product_data.get("video"):
            video_path = MEDIA_DIR / product_data["video"]
            VIDEOS_PRODUITS[name] = video_path
    
    logger.info(f"✅ {len(PRODUCT_CODES)} produits chargés")
    logger.info(f"   • Pills: {len(PILL_SUBCATEGORIES)}")
    logger.info(f"   • Crystal: {len(ROCK_SUBCATEGORIES)}")
    logger.info(f"   • Images: {len(IMAGES_PRODUITS)}")
    logger.info(f"   • Vidéos: {len(VIDEOS_PRODUITS)}")

# ==================== GESTION PRODUITS DISPONIBLES ====================

def load_available_products():
    """Charge la liste des produits disponibles (actifs uniquement)"""
    # PRIX_FR est LA source de vérité unique
    # Il contient déjà tous les produits (JSON + hardcodés) après reload()
    return set(PRIX_FR.keys())

def save_available_products(products):
    """Sauvegarde la liste des produits disponibles"""
    try:
        with open(AVAILABLE_PRODUCTS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "available": list(products),
                "updated": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde produits: {e}")
        return False

def is_product_available(product_name):
    """Vérifie si un produit est disponible"""
    available = load_available_products()
    return product_name in available

def get_available_products():
    """Récupère tous les produits disponibles"""
    return load_available_products()

# ==================== GESTION DES STOCKS ====================

def save_stocks(stocks):
    """Sauvegarde les stocks"""
    try:
        with open(STOCKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stocks, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde stocks: {e}")
        return False

def save_orders_csv(csv_path, orders):
    """Sauvegarde le CSV des commandes en filtrant les clés None"""
    try:
        logger.info(f"💾 save_orders_csv appelé: {len(orders)} commandes")
        
        if not orders:
            logger.info(f"💾 Aucune commande à sauvegarder")
            return True
        
        # Nettoyer TOUS les orders d'abord (supprimer clés None)
        clean_orders = []
        for order in orders:
            clean_order = {k: v for k, v in order.items() if k is not None and k != ''}
            clean_orders.append(clean_order)
        
        if not clean_orders:
            logger.info(f"💾 Aucune commande propre après nettoyage")
            return True
        
        # Collecter toutes les clés uniques de TOUS les orders
        all_keys = set()
        for order in clean_orders:
            all_keys.update(order.keys())
        
        fieldnames = sorted([k for k in all_keys if k])  # Trier pour cohérence
        
        logger.info(f"💾 Écriture de {len(clean_orders)} commandes avec {len(fieldnames)} colonnes")
        
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(clean_orders)
        
        logger.info(f"✅ CSV sauvegardé avec succès")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde orders CSV: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return False


def get_stock(product_name):
    """Récupère le stock d'un produit depuis products.json via STOCK_PRODUITS"""
    # Utiliser STOCK_PRODUITS qui lit depuis products.json
    if product_name not in STOCK_PRODUITS:
        return None
    return STOCK_PRODUITS.get(product_name, 0)

def set_stock(product_name, quantity, alert_threshold=20):
    """Définit le stock d'un produit dans products.json"""
    # Trouver le product_id correspondant au nom
    products = PRODUCTS_DATA.get('products', {})
    product_id = None
    
    for pid, pdata in products.items():
        if pdata.get('name', {}).get('fr') == product_name:
            product_id = pid
            break
    
    if not product_id:
        logger.error(f"❌ Produit introuvable: {product_name}")
        return False
    
    old_quantity = products[product_id].get('quantity', 0)
    
    # Mettre à jour dans products.json
    products[product_id]['quantity'] = quantity
    products[product_id]['alert_threshold'] = alert_threshold
    
    PRODUCTS_DATA['products'] = products
    success = save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)
    
    if success:
        # Recharger STOCK_PRODUITS
        STOCK_PRODUITS.reload()
        
        # GESTION AUTOMATIQUE RUPTURE DE STOCK
        if quantity == 0 and old_quantity > 0:
            # Rupture de stock : désactiver automatiquement
            products[product_id]['active'] = False
            PRODUCTS_DATA['products'] = products
            save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)
            reload_products()
            logger.warning(f"📦 Rupture de stock : {product_name} désactivé automatiquement")
        
        elif quantity > 0 and old_quantity == 0:
            # Réapprovisionnement : réactiver automatiquement
            products[product_id]['active'] = True
            PRODUCTS_DATA['products'] = products
            save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)
            reload_products()
            logger.info(f"✅ Réappro : {product_name} réactivé automatiquement (stock: {quantity})")
    
    return success

def update_stock(product_name, quantity_change):
    """Met à jour le stock (+ pour ajout, - pour retrait) dans products.json"""
    current = get_stock(product_name)
    if current is None:
        logger.error(f"❌ Produit introuvable: {product_name}")
        return False
    
    new_quantity = max(0, current + quantity_change)
    return set_stock(product_name, new_quantity)

def is_in_stock(product_name, requested_quantity):
    """Vérifie si la quantité demandée est disponible"""
    stock = get_stock(product_name)
    if stock is None:
        return True
    return stock >= requested_quantity

def get_low_stock_products():
    """Récupère les produits avec stock faible depuis products.json"""
    products = PRODUCTS_DATA.get('products', {})
    low_stock = []
    
    for product_id, product_data in products.items():
        if not product_data.get('active', True):
            continue  # Ignorer les produits inactifs
        
        quantity = product_data.get('quantity', 0)
        threshold = product_data.get('alert_threshold', 20)
        name = product_data.get('name', {}).get('fr', product_id)
        
        if quantity <= threshold and quantity > 0:
            low_stock.append({
                "product": name,
                "quantity": quantity,
                "threshold": threshold
            })
    
    return low_stock

def get_out_of_stock_products():
    """Récupère les produits en rupture de stock depuis products.json"""
    products = PRODUCTS_DATA.get('products', {})
    out_of_stock = []
    
    for product_id, product_data in products.items():
        if not product_data.get('active', True):
            continue  # Ignorer les produits inactifs
        
        name = product_data.get('name', {}).get('fr', product_id)
        if product_data.get('quantity', 0) == 0:
            out_of_stock.append(name)
    
    return out_of_stock

# ==================== GESTION DES PRIX ====================

def save_prices(prices):
    """Sauvegarde les prix"""
    try:
        with open(PRICES_FILE, 'w', encoding='utf-8') as f:
            json.dump(prices, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde prix: {e}")
        return False

def get_price(product_name, country):
    """Récupère le prix d'un produit"""
    prices = load_prices()
    return prices.get(country, {}).get(product_name, 0)

def set_price(product_name, country, new_price):
    """Définit le prix d'un produit"""
    prices = load_prices()
    if country not in prices:
        prices[country] = {}
    prices[country][product_name] = new_price
    return save_prices(prices)

# ==================== GESTION DES PRIX DÉGRESSIFS ====================

def load_pricing_tiers():
    """Charge les paliers de prix"""
    if PRICING_TIERS_FILE.exists():
        try:
            with open(PRICING_TIERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_pricing_tiers(tiers):
    """Sauvegarde les paliers de prix"""
    try:
        with open(PRICING_TIERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tiers, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde pricing tiers: {e}")
        return False

def get_price_for_quantity(product_name, country, quantity):
    """Retourne le prix en fonction de la quantité commandée"""
    tiers = load_pricing_tiers()
    product_key = f"{product_name}_{country}"
    
    if product_key in tiers and tiers[product_key]:
        sorted_tiers = sorted(tiers[product_key], key=lambda x: x['min_qty'], reverse=True)
        for tier in sorted_tiers:
            if quantity >= tier['min_qty']:
                return tier['price']
    
    return get_price(product_name, country)

def get_pricing_tiers_display(product_name, country):
    """Retourne l'affichage formaté des paliers de prix"""
    tiers = load_pricing_tiers()
    product_key = f"{product_name}_{country}"
    
    if product_key not in tiers or not tiers[product_key]:
        base_price = get_price(product_name, country)
        return f"Prix unique : {base_price}€/g"
    
    text = ""
    sorted_tiers = sorted(tiers[product_key], key=lambda x: x['min_qty'])
    
    for i, tier in enumerate(sorted_tiers):
        if i < len(sorted_tiers) - 1:
            text += f"• {tier['min_qty']}-{sorted_tiers[i+1]['min_qty']-1}g : {tier['price']}€/g\n"
        else:
            text += f"• {tier['min_qty']}g+ : {tier['price']}€/g\n"
    
    return text

# ==================== GESTION DES CODES PROMO ====================

def save_promo_codes(codes):
    """Sauvegarde les codes promo"""
    try:
        with open(PROMO_CODES_FILE, 'w', encoding='utf-8') as f:
            json.dump(codes, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde codes promo: {e}")
        return False

def validate_promo_code(code, subtotal, user_id):
    """Valide un code promo et retourne la réduction"""
    codes = load_promo_codes()
    code_upper = code.upper()
    
    if code_upper not in codes:
        return None, "Code invalide"
    
    promo = codes[code_upper]
    
    if "valid_until" in promo:
        expiry = datetime.fromisoformat(promo["valid_until"])
        if datetime.now() > expiry:
            return None, "Code expiré"
    
    min_order = promo.get("min_order", 0)
    if subtotal < min_order:
        return None, f"Commande minimum : {min_order}€"
    
    max_uses = promo.get("max_uses", 999999)
    used_count = promo.get("used_count", 0)
    if used_count >= max_uses:
        return None, "Code épuisé"
    
    if promo.get("first_order_only", False):
        history = load_client_history()
        if str(user_id) in history and history[str(user_id)].get("orders_count", 0) > 0:
            return None, "Réservé aux nouvelles commandes"
    
    if promo["type"] == "percentage":
        discount = subtotal * (promo["value"] / 100)
    else:
        discount = promo["value"]
    
    return discount, "OK"

def use_promo_code(code):
    """Incrémente le compteur d'utilisation d'un code promo"""
    codes = load_promo_codes()
    code_upper = code.upper()
    
    if code_upper in codes:
        codes[code_upper]["used_count"] = codes[code_upper].get("used_count", 0) + 1
        save_promo_codes(codes)

# FIN DU BLOC 2
# ==================== BLOC 3 : FONCTIONS MÉTIER, CALCULS ET NOTIFICATIONS ====================

# ==================== GESTION HISTORIQUE CLIENT ====================

def save_client_history(history):
    """Sauvegarde l'historique client"""
    try:
        with open(CLIENT_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde historique: {e}")
        return False

def update_client_history(user_id, order_data):
    """Met à jour l'historique d'un client"""
    history = load_client_history()
    user_key = str(user_id)
    
    if user_key not in history:
        history[user_key] = {
            "total_spent": 0,
            "orders_count": 0,
            "vip_status": False,
            "favorite_products": {},
            "last_order_date": None,
            "orders": []
        }
    
    history[user_key]["total_spent"] += order_data.get("total", 0)
    history[user_key]["orders_count"] += 1
    history[user_key]["last_order_date"] = datetime.now().isoformat()
    
    if history[user_key]["total_spent"] >= VIP_THRESHOLD:
        history[user_key]["vip_status"] = True
    
    for product in order_data.get("products", []):
        product_name = product.get("produit")
        if product_name:
            history[user_key]["favorite_products"][product_name] = \
                history[user_key]["favorite_products"].get(product_name, 0) + 1
    
    history[user_key]["orders"].append({
        "order_id": order_data.get("order_id"),
        "date": datetime.now().isoformat(),
        "total": order_data.get("total", 0),
        "products": [p.get("produit") for p in order_data.get("products", [])]
    })
    
    return save_client_history(history)

def get_client_stats(user_id):
    """Récupère les statistiques d'un client"""
    history = load_client_history()
    user_key = str(user_id)
    
    if user_key not in history:
        return None
    
    stats = history[user_key].copy()
    
    if stats["favorite_products"]:
        sorted_products = sorted(
            stats["favorite_products"].items(),
            key=lambda x: x[1],
            reverse=True
        )
        stats["top_products"] = sorted_products[:3]
    else:
        stats["top_products"] = []
    
    return stats

def is_vip_client(user_id):
    """Vérifie si un client est VIP"""
    history = load_client_history()
    return history.get(str(user_id), {}).get("vip_status", False)

# ==================== SYSTÈME DE PARRAINAGE ====================

def save_referrals(referrals):
    """Sauvegarde les données de parrainage"""
    try:
        with open(REFERRALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(referrals, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde parrainage: {e}")
        return False

def get_or_create_referral_code(user_id):
    """Récupère ou crée un code de parrainage pour un utilisateur"""
    referrals = load_referrals()
    user_key = str(user_id)
    
    if user_key not in referrals:
        while True:
            code = generate_referral_code()
            if not any(data.get("referral_code") == code for data in referrals.values()):
                break
        
        referrals[user_key] = {
            "referral_code": code,
            "referred_by": None,
            "referred_users": [],
            "earnings": 0,
            "created_at": datetime.now().isoformat()
        }
        save_referrals(referrals)
    
    return referrals[user_key]["referral_code"]

def apply_referral(user_id, referral_code):
    """Applique un code de parrainage pour un nouvel utilisateur"""
    referrals = load_referrals()
    user_key = str(user_id)
    
    referrer_id = None
    for uid, data in referrals.items():
        if data.get("referral_code") == referral_code.upper():
            referrer_id = uid
            break
    
    if not referrer_id:
        return False, "Code invalide"
    
    if user_key == referrer_id:
        return False, "Impossible de se parrainer soi-même"
    
    if user_key in referrals and referrals[user_key].get("referred_by"):
        return False, "Déjà parrainé"
    
    if user_key not in referrals:
        referrals[user_key] = {
            "referral_code": generate_referral_code(),
            "referred_by": referrer_id,
            "referred_users": [],
            "earnings": 0,
            "created_at": datetime.now().isoformat()
        }
    else:
        referrals[user_key]["referred_by"] = referrer_id
    
    if user_key not in referrals[referrer_id]["referred_users"]:
        referrals[referrer_id]["referred_users"].append(user_key)
    
    save_referrals(referrals)
    return True, f"Parrainé par l'utilisateur {referrer_id}"

def add_referral_earnings(referrer_id, amount):
    """Ajoute des gains de parrainage"""
    referrals = load_referrals()
    referrer_key = str(referrer_id)
    
    if referrer_key in referrals:
        referrals[referrer_key]["earnings"] = referrals[referrer_key].get("earnings", 0) + amount
        save_referrals(referrals)

def get_referral_stats(user_id):
    """Récupère les statistiques de parrainage d'un utilisateur"""
    referrals = load_referrals()
    user_key = str(user_id)
    
    if user_key not in referrals:
        return None
    
    return referrals[user_key]

# ==================== GESTION UTILISATEURS ====================

def save_users(users):
    """Sauvegarde les utilisateurs"""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def is_new_user(user_id):
    """Vérifie si l'utilisateur est nouveau"""
    users = load_users()
    return str(user_id) not in users

def add_user(user_id, user_data):
    """Ajoute un nouvel utilisateur"""
    users = load_users()
    users[str(user_id)] = {
        "first_seen": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
        "username": user_data.get("username"),
        "first_name": user_data.get("first_name"),
        "last_name": user_data.get("last_name"),
        "visit_count": 1
    }
    save_users(users)
    get_or_create_referral_code(user_id)
    return True

def update_user_visit(user_id):
    """Met à jour la dernière visite d'un utilisateur"""
    users = load_users()
    if str(user_id) in users:
        users[str(user_id)]["last_seen"] = datetime.now().isoformat()
        users[str(user_id)]["visit_count"] = users[str(user_id)].get("visit_count", 0) + 1
        save_users(users)

# ==================== GESTION HORAIRES ====================

def load_horaires():
    """Charge les horaires d'ouverture"""
    if HORAIRES_FILE.exists():
        try:
            with open(HORAIRES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "enabled": True,
        "start_hour": 9,
        "start_minute": 0,
        "end_hour": 23,
        "end_minute": 0
    }

def save_horaires(horaires):
    """Sauvegarde les horaires"""
    try:
        with open(HORAIRES_FILE, 'w', encoding='utf-8') as f:
            json.dump(horaires, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde horaires: {e}")
        return False

def is_within_delivery_hours(user_id=None):
    """Vérifie si on est dans les horaires d'ouverture"""
    if user_id and is_admin(user_id):
        return True
    
    horaires = load_horaires()
    if not horaires.get("enabled", True):
        return True
    
    now = datetime.now().time()
    start = time(horaires["start_hour"], horaires["start_minute"])
    end = time(horaires["end_hour"], horaires["end_minute"])
    
    return start <= now <= end

def get_horaires_text():
    """Retourne le texte des horaires"""
    horaires = load_horaires()
    if not horaires.get("enabled", True):
        return "24h/24 (toujours ouvert)"
    return f"{horaires['start_hour']:02d}:{horaires['start_minute']:02d} - {horaires['end_hour']:02d}:{horaires['end_minute']:02d}"

# ==================== GESTION STATISTIQUES ====================

def save_stats(stats):
    """Sauvegarde les statistiques"""
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde stats: {e}")
        return False

def add_sale(amount, country, products, subtotal=0, delivery_fee=0, promo_discount=0, vip_discount=0):
    """Ajoute une vente aux statistiques"""
    stats = load_stats()
    sale_data = {
        "date": datetime.now().isoformat(),
        "amount": amount,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "promo_discount": promo_discount,
        "vip_discount": vip_discount,
        "country": country,
        "products": products
    }
    
    if "weekly" not in stats:
        stats["weekly"] = []
    if "monthly" not in stats:
        stats["monthly"] = []
    
    stats["weekly"].append(sale_data)
    stats["monthly"].append(sale_data)
    save_stats(stats)

# ==================== SYSTÈME MAINTENANCE ====================

def load_maintenance_status():
    """Charge l'état du mode maintenance"""
    maintenance_file = DATA_DIR / "maintenance.json"
    if maintenance_file.exists():
        try:
            with open(maintenance_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "enabled": False,
        "last_online": datetime.now().isoformat(),
        "downtime_threshold": 300
    }

def save_maintenance_status(status):
    """Sauvegarde l'état du mode maintenance"""
    maintenance_file = DATA_DIR / "maintenance.json"
    try:
        with open(maintenance_file, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde maintenance: {e}")
        return False

def set_maintenance_mode(enabled, reason=None):
    """Active/désactive le mode maintenance"""
    status = load_maintenance_status()
    status["enabled"] = enabled
    status["last_updated"] = datetime.now().isoformat()
    if reason:
        status["reason"] = reason
    save_maintenance_status(status)
    logger.info(f"🔧 Mode maintenance: {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}")
    return True

def is_maintenance_mode(user_id=None):
    """Vérifie si le mode maintenance est actif"""
    if user_id and is_admin(user_id):
        return False
    status = load_maintenance_status()
    return status.get("enabled", False)

def update_last_online():
    """Met à jour le timestamp de dernière activité"""
    status = load_maintenance_status()
    status["last_online"] = datetime.now().isoformat()
    save_maintenance_status(status)

def check_downtime_and_activate_maintenance():
    """Vérifie si le bot était down et active maintenance si nécessaire"""
    status = load_maintenance_status()
    
    if status.get("enabled", False):
        return True
    
    last_online = status.get("last_online")
    if not last_online:
        return False
    
    try:
        last_time = datetime.fromisoformat(last_online)
        downtime = (datetime.now() - last_time).total_seconds()
        threshold = status.get("downtime_threshold", 300)
        
        if downtime > threshold:
            logger.warning(f"⚠️ Downtime détecté: {int(downtime)}s (seuil: {threshold}s)")
            set_maintenance_mode(True, reason=f"Redémarrage après {int(downtime/60)}min d'arrêt")
            return True
    except Exception as e:
        logger.error(f"Erreur check downtime: {e}")
    
    return False

# ==================== CALCULS DE DISTANCE ET LIVRAISON ====================

def calculate_delivery_fee(delivery_type, distance=0, subtotal=0):
    """Calcule les frais de livraison"""
    if delivery_type == "postal":
        return FRAIS_POSTAL
    
    elif delivery_type == "express":
        if subtotal < 30:
            logger.warning(f"⚠️ Commande {subtotal}€ < 30€ minimum pour Express")
        
        frais_brut = (distance / 10) * 10
        
        if distance >= 25:
            frais_arrondi = math.ceil(frais_brut / 10) * 10
        else:
            frais_arrondi = math.floor(frais_brut / 10) * 10
        
        frais_final = min(frais_arrondi, 70)
        
        logger.info(f"🚚 Express: {distance:.1f}km → {frais_brut:.1f}€ → {frais_arrondi}€ → plafonné {frais_final}€")
        
        return frais_final
    
    elif delivery_type == "meetup":
        return FRAIS_MEETUP
    
    return 0

def calculate_distance_openroute(origin, destination):
    """Calcule la distance avec OpenRouteService"""
    try:
        geocode_origin = distance_client.pelias_search(text=origin)
        geocode_dest = distance_client.pelias_search(text=destination)
        
        if not geocode_origin["features"] or not geocode_dest["features"]:
            raise Exception("Adresse non trouvée")
        
        coords_origin = geocode_origin["features"][0]["geometry"]["coordinates"]
        coords_dest = geocode_dest["features"][0]["geometry"]["coordinates"]
        
        route = distance_client.directions(
            coordinates=[coords_origin, coords_dest],
            profile="driving-car",
            format="geojson"
        )
        
        distance_m = route["features"][0]["properties"]["segments"][0]["distance"]
        distance_km = distance_m / 1000
        logger.info(f"📍 Distance: {distance_km:.1f} km (OpenRouteService)")
        return distance_km
    except Exception as e:
        logger.error(f"❌ OpenRouteService: {e}")
        return None

def calculate_distance_geopy(origin, destination):
    """Calcule la distance avec Geopy"""
    try:
        loc_origin = distance_client.geocode(origin)
        loc_dest = distance_client.geocode(destination)
        
        if not loc_origin or not loc_dest:
            raise Exception("Adresse non trouvée")
        
        coords_origin = (loc_origin.latitude, loc_origin.longitude)
        coords_dest = (loc_dest.latitude, loc_dest.longitude)
        
        distance_km = geodesic(coords_origin, coords_dest).kilometers * 1.3
        logger.info(f"📍 Distance: {distance_km:.1f} km (Geopy approximatif)")
        return distance_km
    except Exception as e:
        logger.error(f"❌ Geopy: {e}")
        return None

def calculate_distance_simulation(address):
    """Simulation de distance pour fallback"""
    hash_val = int(hashlib.md5(address.encode()).hexdigest()[:8], 16)
    distance = (hash_val % 50) + 5
    logger.info(f"📍 Distance: {distance} km (simulée)")
    return distance

def calculate_distance_simple(address):
    """Calcule la distance avec fallback"""
    distance = None
    
    if DISTANCE_METHOD == "openroute":
        distance = calculate_distance_openroute(ADMIN_ADDRESS, address)
    elif DISTANCE_METHOD == "geopy":
        distance = calculate_distance_geopy(ADMIN_ADDRESS, address)
    
    if distance is None:
        logger.warning("⚠️ Fallback sur simulation")
        distance = calculate_distance_simulation(address)
    
    return distance

# ==================== CALCUL TOTAL AVEC TOUTES LES RÉDUCTIONS ====================

def calculate_total(cart, country, delivery_type=None, distance=0, promo_code=None, user_id=None):
    """Calcule le total avec tous les éléments"""
    prices = load_prices()
    prix_table = prices.get(country, PRIX_FR if country == "FR" else PRIX_CH)
    
    subtotal = 0
    for item in cart:
        product_name = item["produit"]
        quantity = item["quantite"]
        price_per_unit = get_price_for_quantity(product_name, country, quantity)
        subtotal += price_per_unit * quantity
    
    delivery_fee = 0
    if delivery_type:
        delivery_fee = calculate_delivery_fee(delivery_type, distance, subtotal)
    
    promo_discount = 0
    promo_valid = False
    if promo_code:
        discount, message = validate_promo_code(promo_code, subtotal, user_id)
        if discount is not None:
            promo_discount = discount
            promo_valid = True
    
    vip_discount = 0
    if user_id and is_vip_client(user_id):
        vip_discount = subtotal * (VIP_DISCOUNT / 100)
    
    total = subtotal + delivery_fee - promo_discount - vip_discount
    total = max(0, total)
    
    return {
        "total": total,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "promo_discount": promo_discount,
        "vip_discount": vip_discount,
        "promo_valid": promo_valid
    }

# ==================== FORMATAGE ET AFFICHAGE ====================

def format_cart(cart, user_data):
    """Formate l'affichage du panier"""
    if not cart:
        return ""
    text = "\n" + tr(user_data, 'cart_title') + "\n"
    for item in cart:
        text += f"• {item['produit']} x {item['quantite']}\n"
    return text

def format_cart_summary(cart):
    """Résumé rapide du panier (une ligne)"""
    if not cart:
        return "Vide"
    
    items = []
    for item in cart:
        items.append(f"{item['produit']} x{item['quantite']}g")
    
    return ", ".join(items)

def format_product_card(product_name, country, stock=None):
    """Formate une carte produit style e-commerce"""
    price = get_price(product_name, country)
    flag = "🇫🇷" if country == "FR" else "🇨🇭"
    
    card = f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
    card += f"┃  {product_name}\n"
    card += f"┣━━━━━━━━━━━━━━━━━━━━━┫\n"
    card += f"┃ {EMOJI_THEME['money']} Prix: {price}€/g {flag}\n"
    
    if stock is None:
        card += f"┃ {EMOJI_THEME['online']} En stock (illimité)\n"
    elif stock > 50:
        card += f"┃ {EMOJI_THEME['online']} En stock ({stock}g)\n"
    elif stock > 0:
        card += f"┃ {EMOJI_THEME['warning']} Stock limité ({stock}g)\n"
    else:
        card += f"┃ {EMOJI_THEME['offline']} Rupture de stock\n"
    
    card += f"┃ {EMOJI_THEME['delivery']} Livraison: 24-48h\n"
    card += f"┗━━━━━━━━━━━━━━━━━━━━━┛"
    
    return card

def get_formatted_price_list(country_code):
    """Génère la liste formatée des prix"""
    prices = load_prices()
    country = "FR" if country_code == "fr" else "CH"
    country_prices = prices.get(country, PRIX_FR if country == "FR" else PRIX_CH)
    
    available = get_available_products()
    
    if not available:
        return "Aucun produit disponible"
    
    text = ""
    
    for product_name in sorted(available):
        stock = get_stock(product_name)
        price = country_prices.get(product_name, 0)
        
        if stock is not None and stock == 0:
            text += f"{EMOJI_THEME['offline']} {product_name} : RUPTURE\n"
        elif stock is not None and stock <= 20:
            text += f"{EMOJI_THEME['warning']} {product_name} : {price}€/g (Stock: {stock}g)\n"
        else:
            text += f"{product_name} : {price}€/g\n"
    
    text += f"\n{EMOJI_THEME['delivery']} Livraison :\n"
    text += f"  • Postale (48-72h) : 10€\n"
    text += f"  • Express (30min+) : 10€/10km (min 30€, max 70€)\n"
    text += f"  • Meetup : Gratuit"
    
    return text

# FIN DU BLOC 3
# ==================== BLOC 4 : SUITE FORMATAGE, NOTIFICATIONS ET COMMANDES ====================

# ==================== SUITE FORMATAGE ====================

def format_order_summary(cart, country, delivery_type, delivery_fee, promo_discount, vip_discount, total, order_id=None):
    """Formate le récapitulatif de commande style ticket de caisse"""
    ticket = f"╔════════════════════════════╗\n"
    ticket += f"║     🧾 RÉCAPITULATIF      ║\n"
    ticket += f"╚════════════════════════════╝\n"
    
    ticket += f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    if order_id:
        ticket += f"🆔 Commande #{order_id}\n"
    
    ticket += f"┌────────────────────────────┐\n"
    ticket += f"│  PRODUITS                  │\n"
    ticket += f"├────────────────────────────┤\n"
    
    subtotal = 0
    for item in cart:
        product = item['produit']
        qty = item['quantite']
        price = get_price_for_quantity(product, country, qty)
        line_total = price * qty
        subtotal += line_total
        
        product_short = product[:15] if len(product) > 15 else product
        ticket += f"│  {product_short:<15} {qty}g │\n"
        ticket += f"│  {price}€/g × {qty} = {line_total}€{' '*(12-len(str(line_total)))}│\n"
    
    ticket += f"└────────────────────────────┘\n"
    
    ticket += f"\n💵 Sous-total: {subtotal:.2f}€\n"
    ticket += f"{EMOJI_THEME['delivery']} Livraison ({delivery_type}): {delivery_fee:.2f}€\n"
    
    if promo_discount > 0:
        ticket += f"{EMOJI_THEME['gift']} Promo: -{promo_discount:.2f}€\n"
    
    if vip_discount > 0:
        ticket += f"{EMOJI_THEME['vip']} VIP: -{vip_discount:.2f}€\n"
    
    ticket += f"\n╔════════════════════════════╗\n"
    ticket += f"║  {EMOJI_THEME['money']} TOTAL: {total:.2f}€{' '*(17-len(str(total)))}║\n"
    ticket += f"╚════════════════════════════╝"
    
    return ticket

# ==================== SAUVEGARDE COMMANDES ====================

def save_order_to_csv(order_data):
    """Sauvegarde une commande en CSV (lecture + ajout + réécriture)"""
    csv_path = DATA_DIR / "orders.csv"
    try:
        logger.info(f"💾 save_order_to_csv: ordre {order_data.get('order_id')}")
        
        # Lire toutes les commandes existantes
        orders = []
        if csv_path.exists():
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                orders = list(reader)
            logger.info(f"💾 {len(orders)} commandes existantes chargées")
        else:
            logger.info(f"💾 Nouveau fichier CSV")
        
        # Ajouter la nouvelle commande
        orders.append(order_data)
        logger.info(f"💾 Nouvelle commande ajoutée, total: {len(orders)}")
        
        # Réécrire tout le fichier avec save_orders_csv
        result = save_orders_csv(csv_path, orders)
        
        if result:
            logger.info(f"✅ Commande {order_data.get('order_id')} sauvegardée dans CSV")
        else:
            logger.error(f"❌ Échec sauvegarde via save_orders_csv")
        
        return result
    except Exception as e:
        logger.error(f"❌ Erreur save_order_to_csv: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return False

# ==================== ENVOI MÉDIAS ====================

async def send_product_media(context, chat_id, product_name, caption):
    """Envoie la photo ou vidéo d'un produit"""
    product_video_path = VIDEOS_PRODUITS.get(product_name)
    product_image_path = IMAGES_PRODUITS.get(product_name)
    
    if product_video_path and product_video_path.exists():
        try:
            with open(product_video_path, 'rb') as video:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=video,
                    caption=caption,
                    supports_streaming=True
                )
            logger.info(f"✅ Vidéo envoyée: {product_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur vidéo {product_name}: {e}")
    
    if product_image_path and product_image_path.exists():
        try:
            with open(product_image_path, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption
                )
            logger.info(f"✅ Image envoyée: {product_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur image {product_name}: {e}")
    
    logger.warning(f"⚠️ Aucun média pour {product_name}")
    await context.bot.send_message(chat_id=chat_id, text=caption)
    return False

# ==================== NOTIFICATIONS ADMIN ====================

async def notify_admin_new_user(context, user_id, user_data):
    """Notifie l'admin d'un nouvel utilisateur"""
    username = user_data.get("username", "N/A")
    first_name = user_data.get("first_name", "N/A")
    last_name = user_data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()
    
    # Anonymiser l'ID
    anonymous_id = anonymize_id(user_id)
    
    notification = f"""{EMOJI_THEME['celebration']} NOUVELLE CONNEXION

👤 Utilisateur :
- Nom : {full_name}
- Username : @{username if username != 'N/A' else 'Non défini'}
- ID : {anonymous_id}

📅 Date : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

💬 L'utilisateur vient de démarrer le bot
"""
    try:
        for admin_id in get_admin_ids():
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification
            )
        logger.info(f"✅ Admins notifiés - Nouveau user: {user_id}")
    except Exception as e:
        logger.error(f"❌ Erreur notification admin: {e}")

async def notify_admin_new_order(context, order_data, user_info):
    """Notifie l'admin d'une nouvelle commande avec détails de préparation"""
    total_info = order_data.get('total_info', {})
    
    # Anonymiser l'ID
    anonymous_id = anonymize_id(order_data['user_id'])
    
    notification = f"""{EMOJI_THEME['cart']} NOUVELLE COMMANDE

📋 Commande : {order_data['order_id']}
👤 Client : {user_info['first_name']} (@{user_info['username']})
🆔 ID : {anonymous_id}

🛍️ PRODUITS À PRÉPARER :
"""
    
    # Parser les produits pour calculs avancés
    import re
    total_cost = 0
    total_margin = 0
    products_lines = order_data['products_display'].split('\n')
    
    for line in products_lines:
        if not line.strip() or line.strip().startswith('━'):
            continue
        
        # Ajouter la ligne produit
        notification += f"{line}\n"
        
        # Essayer d'extraire le nom du produit et la quantité
        for product_name in PRODUCT_WEIGHTS.keys():
            if product_name in line:
                # Extraire la quantité
                match = re.search(r'(\d+(?:\.\d+)?)\s*(?:g|unité)', line)
                if match:
                    qty = float(match.group(1))
                    
                    # Calcul poids à peser
                    prep = calculate_weight_to_prepare(product_name, qty)
                    notification += f"  ⚖️  {prep['note']}\n"
                    
                    # Calcul marge (estimation basée sur sous-total)
                    # On prend le prix moyen par produit
                    avg_price = total_info['subtotal'] / len([p for p in products_lines if p.strip() and not p.startswith('━')])
                    margins = calculate_margins(product_name, qty, avg_price)
                    
                    total_cost += margins['cost']
                    total_margin += margins['margin']
                    
                    notification += f"  💰 Coût: {margins['cost']:.2f}€ | Marge: {margins['margin']:.2f}€\n"
                
                break
    
    notification += f"""
{EMOJI_THEME['money']} DÉTAILS FINANCIERS :
- Sous-total : {total_info['subtotal']:.2f}€
- Livraison : {total_info['delivery_fee']:.2f}€
"""
    
    if total_info.get('promo_discount', 0) > 0:
        notification += f"• {EMOJI_THEME['gift']} Promo : -{total_info['promo_discount']:.2f}€\n"
    
    if total_info.get('vip_discount', 0) > 0:
        notification += f"• {EMOJI_THEME['vip']} VIP : -{total_info['vip_discount']:.2f}€\n"
    
    notification += f"\n💵 TOTAL : {total_info['total']:.2f}€\n"
    
    # Ajouter les marges calculées
    if total_cost > 0:
        margin_rate = (total_margin / total_info['total'] * 100) if total_info['total'] > 0 else 0
        notification += f"""
📊 ANALYSE MARGES :
- Coût produits : {total_cost:.2f}€
- Marge brute : {total_margin:.2f}€
- Taux de marge : {margin_rate:.1f}%
"""
    
    notification += f"""
📍 LIVRAISON :
- Adresse : {order_data['address']}
- Type : {order_data['delivery_type']}
- Paiement : {order_data['payment_method']}

⚠️ Vérifiez et validez les montants avant de confirmer
"""
    
    keyboard = [
        [
            InlineKeyboardButton(
                "✏️ Modifier prix",
                callback_data=f"edit_order_total_{order_data['order_id']}"
            ),
            InlineKeyboardButton(
                "✏️ Modifier livraison",
                callback_data=f"edit_order_delivery_{order_data['order_id']}"
            )
        ],
        [
            InlineKeyboardButton(
                "💬 Contacter client",
                callback_data=f"contact_user_{order_data['user_id']}"
            )
        ],
        [
            InlineKeyboardButton(
                f"{EMOJI_THEME['success']} Valider commande",
                callback_data=f"admin_confirm_order_{order_data['order_id']}_{order_data['user_id']}"
            )
        ]
    ]
    
    try:
        for admin_id in get_admin_ids():
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        logger.info(f"✅ Admins notifiés - Nouvelle commande: {order_data['order_id']}")
    except Exception as e:
        logger.error(f"❌ Erreur notification commande: {e}")

async def notify_admin_low_stock(context, product_name, quantity):
    """Alerte stock faible"""
    notification = f"""{EMOJI_THEME['warning']} ALERTE STOCK FAIBLE

{EMOJI_THEME['product']} Produit : {product_name}
📊 Stock restant : {quantity}g

💡 Pensez à réapprovisionner
"""
    try:
        for admin_id in get_admin_ids():
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification
            )
        logger.info(f"⚠️ Alerte stock envoyée: {product_name}")
    except Exception as e:
        logger.error(f"❌ Erreur notification stock: {e}")

async def notify_admin_out_of_stock(context, product_name):
    """Alerte rupture de stock"""
    notification = f"""{EMOJI_THEME['offline']} RUPTURE DE STOCK

{EMOJI_THEME['product']} Produit : {product_name}
📊 Stock : 0g

{EMOJI_THEME['warning']} Le produit a été automatiquement masqué
"""
    try:
        for admin_id in get_admin_ids():
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification
            )
        logger.info(f"🔴 Alerte rupture envoyée: {product_name}")
    except Exception as e:
        logger.error(f"❌ Erreur notification rupture: {e}")

async def notify_admin_vip_client(context, user_id, user_info, total_spent):
    """Notifie qu'un client devient VIP"""
    # Anonymiser l'ID
    anonymous_id = anonymize_id(user_id)
    
    notification = f"""{EMOJI_THEME['vip']} NOUVEAU CLIENT VIP

👤 Client :
- Nom : {user_info['first_name']}
- Username : @{user_info['username']}
- ID : {anonymous_id}

{EMOJI_THEME['money']} Total dépensé : {total_spent:.2f}€

{EMOJI_THEME['celebration']} Le client a atteint le statut VIP !
"""
    try:
        for admin_id in get_admin_ids():
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification
            )
        logger.info(f"👑 Nouveau VIP notifié: {user_id}")
    except Exception as e:
        logger.error(f"❌ Erreur notification VIP: {e}")

# ==================== COMMANDES DE BASE ====================

# ==================== COMMANDE /START ====================

@error_handler
async def language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu de sélection de langue"""
    query = update.callback_query
    if query:
        await query.answer()
    
    # DEBUG: Vérifier si LANG_CONFIG est chargé
    logger.info(f"🌐 LANG_CONFIG disponible: {len(LANG_CONFIG)} langues")
    logger.info(f"🌐 Langues: {list(LANG_CONFIG.keys())}")
    
    message = """🌐 CHOISISSEZ VOTRE LANGUE
CHOOSE YOUR LANGUAGE
WÄHLEN SIE IHRE SPRACHE
ELIGE TU IDIOMA
SCEGLI LA TUA LINGUA

Sélectionnez votre langue préférée :"""
    
    keyboard = []
    
    # Construire le menu depuis LANG_CONFIG
    for lang_code, lang_data in LANG_CONFIG.items():
        logger.info(f"  → {lang_code}: {lang_data}")
        if lang_data.get('active', False):
            flag = lang_data.get('flag', '')
            name = lang_data.get('name', lang_code.upper())
            keyboard.append([InlineKeyboardButton(f"{flag} {name}", callback_data=f"lang_{lang_code}")])
            logger.info(f"    ✅ Ajouté: {flag} {name}")
    
    logger.info(f"🌐 Keyboard final: {len(keyboard)} boutons")
    
    # Ajouter le bouton retour SEULEMENT si appelé depuis le menu (query existe)
    # Pas de retour au premier /start
    if query:
        keyboard.append([InlineKeyboardButton("🔙 Retour / Back", callback_data="start_menu")])
    
    if query:
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

@error_handler
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit la langue de l'utilisateur"""
    query = update.callback_query
    await query.answer()
    
    # Extraire le code langue
    lang_code = query.data.replace("lang_", "")
    
    if lang_code not in LANG_CONFIG or not LANG_CONFIG[lang_code].get('active', False):
        await query.answer("❌ Langue non supportée", show_alert=True)
        return
    
    # Sauvegarder dans user_data
    context.user_data['language'] = lang_code
    
    # Sauvegarder dans users.json
    user_id = query.from_user.id
    users = load_users()
    if str(user_id) in users:
        users[str(user_id)]['language'] = lang_code
        save_users(users)
    
    # Messages de confirmation par langue
    confirmations = {
        'fr': "✅ Langue changée en Français",
        'en': "✅ Language changed to English",
        'es': "✅ Idioma cambiado a Español",
        'de': "✅ Sprache geändert auf Deutsch",
        'it': "✅ Lingua cambiata in Italiano"
    }
    
    await query.answer(confirmations.get(lang_code, "✅ OK"), show_alert=True)
    
    # Retourner au menu principal avec start_menu
    await start_menu(update, context)

@error_handler
async def start_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu principal après sélection langue"""
    query = update.callback_query
    user = query.from_user if query else update.effective_user
    user_id = user.id
    
    if query:
        await query.answer()# Charger les données utilisateur
    users = load_users()
    user_data = users.get(str(user_id), {})
    
    # Récupérer la langue
    lang = context.user_data.get('language', user_data.get('language', 'fr'))
    context.user_data['language'] = lang
    
    stats = get_client_stats(user_id)
    
    vip_message = ""
    if stats and stats.get("vip_status"):
        vip_message = f"{EMOJI_THEME['vip']} Statut VIP actif - {VIP_DISCOUNT}% de réduction automatique\n"
    
    first_name = user.first_name or "Utilisateur"
    
    message = f"""{tr(context, 'welcome', name=first_name)}

{vip_message}{tr(context, 'choose_country')} :

🕐 Horaires : {get_horaires_text()}
"""
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data="country_fr"),
         InlineKeyboardButton("🇨🇭 Suisse", callback_data="country_ch"),
         InlineKeyboardButton("🇦🇺 Australie", callback_data="country_au")],
        [InlineKeyboardButton(tr(context, 'cart'), callback_data="view_cart"),
         InlineKeyboardButton(f"{EMOJI_THEME['history']} Historique", callback_data="my_history")],
        [InlineKeyboardButton("📞 Contact Admin", callback_data="contact_admin_menu"),
         InlineKeyboardButton(f"{EMOJI_THEME['gift']} Parrainage", callback_data="referral_info")],
        [InlineKeyboardButton(tr(context, 'choose_language'), callback_data="language_menu")]
    ]
    
    if query:
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

@error_handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour la commande /start - AFFICHE TOUJOURS LE MENU DE LANGUE"""
    user = update.effective_user
    user_id = user.id

    if is_maintenance_mode(user_id):
        await update.message.reply_text(
            f"{EMOJI_THEME['warning']} BOT EN MAINTENANCE\n\n"
            "Le service est temporairement indisponible.\n"
            "Veuillez réessayer dans quelques instants."
        )
        return

    # Vérifier si nouveau ou existant
    if is_new_user(user_id):
        # Nouvel utilisateur - créer le compte
        user_data_dict = {
            "username": user.username or "N/A",
            "first_name": user.first_name or "Utilisateur",
            "last_name": user.last_name or "",
            "language_code": user.language_code or "fr",
            "language": "fr"  # Par défaut FR, l'utilisateur choisira
        }
        
        add_user(user_id, user_data_dict)
        logger.info(f"🆕 Nouvel utilisateur: {user_id} - {user_data_dict['first_name']}")
        
        # Notification admin en arrière-plan (non-bloquant)
        try:
            admin_ids = get_admin_ids()
            if not admin_ids:
                logger.warning("⚠️ Aucun admin configuré - notification nouvelle connexion non envoyée")
            else:
                logger.info(f"📨 Envoi notification nouvelle connexion à {len(admin_ids)} admin(s)")
                await notify_admin_new_user(context, user_id, user_data_dict)
        except Exception as e:
            logger.error(f"❌ Erreur notification admin nouvelle connexion: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Initialiser la langue par défaut dans context
        context.user_data['language'] = 'fr'
    else:
        # Utilisateur existant - charger sa langue sauvegardée
        users = load_users()
        saved_user_data = users.get(str(user_id), {})
        lang = saved_user_data.get('language', 'fr')
        context.user_data['language'] = lang
    
    # AFFICHER LE MENU DE LANGUE POUR TOUS (nouveau ET existant)
    await language_menu(update, context)
    
    logger.info(f"✅ /start traité: {user_id}")

# ==================== COMMANDE /FIX_CSV ====================

@error_handler
async def fix_csv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /fix_csv - Nettoie le CSV corrompu (super-admin uniquement)"""
    user_id = update.effective_user.id
    
    if not is_super_admin(user_id):
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Accès refusé.\n\n"
            "Cette commande est réservée au super-administrateur."
        )
        logger.warning(f"⚠️ Tentative /fix_csv non autorisée: {user_id}")
        return
    
    await update.message.reply_text("🔧 Démarrage du nettoyage du CSV...\n\nCela peut prendre quelques secondes...")
    
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        await update.message.reply_text("❌ Fichier orders.csv introuvable")
        return
    
    try:
        # Lire le CSV
        import csv as csv_module
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        total_lines = len(orders)
        
        # Filtrer les lignes valides
        valid_orders = []
        invalid_lines = []
        
        for idx, order in enumerate(orders):
            order_id = order.get('order_id', '')
            if order_id.startswith('ORD-') or order_id.startswith('CMD'):
                valid_orders.append(order)
            else:
                invalid_lines.append(f"Ligne {idx+2}: '{order_id[:50]}'")
        
        # Rapport
        if len(valid_orders) == len(orders):
            await update.message.reply_text(
                f"✅ Aucune corruption détectée !\n\n"
                f"📋 Total: {total_lines} commandes\n"
                f"✅ Toutes valides"
            )
            return
        
        # Sauvegarder backup
        import shutil
        backup_path = DATA_DIR / "orders_backup.csv"
        shutil.copy(csv_path, backup_path)
        
        # Réécrire le fichier propre
        if valid_orders:
            # Utiliser save_orders_csv pour garantir la cohérence
            result = save_orders_csv(csv_path, valid_orders)
            
            if result:
                message = f"✅ NETTOYAGE RÉUSSI\n\n"
                message += f"📊 Résumé:\n"
                message += f"• Total lignes: {total_lines}\n"
                message += f"• Lignes valides: {len(valid_orders)}\n"
                message += f"• Lignes supprimées: {total_lines - len(valid_orders)}\n\n"
                message += f"💾 Backup: orders_backup.csv\n\n"
                
                if len(invalid_lines) <= 10:
                    message += "🗑️ Lignes supprimées:\n"
                    message += "\n".join(invalid_lines[:10])
                else:
                    message += f"🗑️ {len(invalid_lines)} lignes supprimées\n"
                    message += "(Voir logs pour détails)"
                
                await update.message.reply_text(message)
                logger.info(f"✅ CSV nettoyé: {len(valid_orders)} commandes gardées, {len(invalid_lines)} supprimées")
            else:
                await update.message.reply_text("❌ Erreur lors de la sauvegarde du CSV nettoyé")
        else:
            await update.message.reply_text("⚠️ Aucune ligne valide trouvée dans le CSV")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {e}")
        logger.error(f"❌ Erreur fix_csv: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")

# ==================== COMMANDE /ADMIN ====================

@error_handler
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /admin - Accès au panel admin"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Accès refusé.\n\n"
            "Cette commande est réservée aux administrateurs.\n\n"
            f"💡 Tapez /myid pour obtenir votre ID Telegram."
        )
        logger.warning(f"⚠️ Tentative accès admin: {user_id}")
        return
    
    admin_info = get_admin_info(user_id)
    level = admin_info.get('level', 'admin')
    
    # Afficher le panel admin
    await admin_panel(update, context)
    
    logger.info(f"🔐 Panel admin ouvert: {user_id} ({level})")

# ==================== COMMANDE /HELP ====================

@error_handler
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche l'aide"""
    help_text = f"""{EMOJI_THEME['info']} AIDE ET INFORMATIONS

━━━━━━━━━━━━━━━━━━━━━━

{EMOJI_THEME['cart']} COMMENT COMMANDER ?

1️⃣ Sélectionnez votre pays (🇫🇷 ou 🇨🇭)
2️⃣ Parcourez le catalogue
3️⃣ Ajoutez des produits au panier
4️⃣ Validez votre commande
5️⃣ Choisissez le mode de livraison
6️⃣ Effectuez le paiement

━━━━━━━━━━━━━━━━━━━━━━

{EMOJI_THEME['delivery']} MODES DE LIVRAISON

📮 Postale (48-72h)
- Frais fixes : 10€
- Livraison sécurisée
- Suivi de colis

⚡ Express (30min - 2h)
- Calcul selon distance
- Min 30€ de commande
- Tarif : 10€/10km (max 70€)

🤝 Meetup
- Gratuit
- Rendez-vous à convenir
- Discrétion assurée

━━━━━━━━━━━━━━━━━━━━━━

{EMOJI_THEME['gift']} CODES PROMO

Profitez de réductions avec nos codes promo !
Entrez-les lors de la validation de commande.

Code WELCOME10 : -10% première commande

━━━━━━━━━━━━━━━━━━━━━━

{EMOJI_THEME['vip']} STATUT VIP

Devenez VIP en dépensant {VIP_THRESHOLD}€
Avantages :
- {VIP_DISCOUNT}% de réduction automatique
- Priorité sur les commandes
- Produits en avant-première

━━━━━━━━━━━━━━━━━━━━━━

{EMOJI_THEME['support']} HORAIRES

{get_horaires_text()}

━━━━━━━━━━━━━━━━━━━━━━

💳 PAIEMENT

Nous acceptons :
- Espèces
- Crypto-monnaies

━━━━━━━━━━━━━━━━━━━━━━

{EMOJI_THEME['security']} SÉCURITÉ

✅ Transactions sécurisées
✅ Données chiffrées
✅ Confidentialité garantie
✅ Livraison discrète

━━━━━━━━━━━━━━━━━━━━━━

📱 COMMANDES DISPONIBLES

/start - Menu principal
/help - Afficher cette aide
/myid - Obtenir votre ID
/admin - Panel admin (admins uniquement)

━━━━━━━━━━━━━━━━━━━━━━

❓ QUESTIONS ?

Notre support est disponible pendant nos horaires d'ouverture.
"""
    
    keyboard = [[InlineKeyboardButton("🏠 Retour Menu", callback_data="back_to_main")]]
    
    await update.message.reply_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"ℹ️ Aide affichée: {update.effective_user.id}")

# ==================== COMMANDE /MYID ====================

@error_handler
async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande pour obtenir son ID Telegram"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Aucun"
    first_name = update.effective_user.first_name or "Utilisateur"
    
    is_already_admin = is_admin(user_id)
    
    # Afficher l'ID RÉEL uniquement à l'utilisateur (pour communiquer aux admins)
    # Mais anonymiser dans tous les messages publics/logs
    
    if is_already_admin:
        admin_info = get_admin_info(user_id)
        level = admin_info.get('level', 'admin')
        status = f"✅ Vous êtes {level.upper()}"
    else:
        status = "👤 Vous êtes UTILISATEUR"
    
    message = f"""🆔 VOS INFORMATIONS TELEGRAM

━━━━━━━━━━━━━━━━━━━━━━

{status}

👤 Nom : {first_name}
🔢 ID : {user_id}
📝 Username : @{username}

━━━━━━━━━━━━━━━━━━━━━━
"""
    
    if not is_already_admin:
        message += """
ℹ️  Pour devenir administrateur :
1. Copiez votre ID ci-dessus
2. Envoyez-le à l'administrateur principal
3. Attendez la validation

⚠️ IMPORTANT : Gardez votre ID confidentiel
"""
    else:
        message += f"""
🔐 Accès administrateur actif
Niveau : {level}
Tapez /admin pour accéder au panel
"""
    
    keyboard = [[InlineKeyboardButton("🏠 Retour Menu", callback_data="back_to_main")]]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"👤 ID demandé: {first_name} ({user_id}) - Admin: {is_already_admin}")

# FIN DU BLOC 4
# ==================== BLOC 5 : CALLBACKS NAVIGATION ET SHOPPING ====================

# ==================== CALLBACKS NAVIGATION ====================

@error_handler
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au menu principal"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = user.id
    user_data = {
        "first_name": user.first_name or "Utilisateur",
        "language_code": user.language_code or "fr"
    }
    
    stats = get_client_stats(user_id)
    
    if stats and stats.get("vip_status"):
        vip_message = f"{EMOJI_THEME['vip']} Statut VIP actif\n"
    else:
        vip_message = ""
    
    message = f"""{EMOJI_THEME['wave']} Bienvenue {user_data['first_name']} !

{vip_message}
Choisissez votre pays pour commencer :
"""
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data="country_fr"),
         InlineKeyboardButton("🇨🇭 Suisse", callback_data="country_ch"),
         InlineKeyboardButton("🇦🇺 Australie", callback_data="country_au")],
        [InlineKeyboardButton(f"{EMOJI_THEME['cart']} Mon Panier", callback_data="view_cart"),
         InlineKeyboardButton(f"{EMOJI_THEME['history']} Historique", callback_data="my_history")],
        [InlineKeyboardButton("📞 Contact Admin", callback_data="contact_admin_menu"),
         InlineKeyboardButton(f"{EMOJI_THEME['info']} Aide", callback_data="help_inline")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def help_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche l'aide en inline"""
    query = update.callback_query
    await query.answer()
    
    help_text = f"""{EMOJI_THEME['info']} AIDE RAPIDE

{EMOJI_THEME['cart']} Commander
1. Choisissez pays
2. Sélectionnez produits
3. Validez commande

{EMOJI_THEME['delivery']} Livraison
- Postale : 10€ (48-72h)
- Express : Variable (30min+)
- Meetup : Gratuit

{EMOJI_THEME['gift']} Réductions
- Codes promo disponibles
- VIP : {VIP_DISCOUNT}% après {VIP_THRESHOLD}€

🕐 Horaires
{get_horaires_text()}
"""
    
    keyboard = [[InlineKeyboardButton("🏠 Retour", callback_data="back_to_main")]]
    
    await query.edit_message_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def my_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche l'historique client"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    stats = get_client_stats(user_id)
    
    if not stats:
        message = f"""{EMOJI_THEME['info']} HISTORIQUE

Vous n'avez pas encore passé de commande.

Commencez dès maintenant et profitez de nos offres !
"""
        keyboard = [[InlineKeyboardButton("🛍️ Commander", callback_data="back_to_main")]]
    
    else:
        total_spent = stats.get("total_spent", 0)
        orders_count = stats.get("orders_count", 0)
        vip = stats.get("vip_status", False)
        top_products = stats.get("top_products", [])
        
        message = f"""{EMOJI_THEME['history']} VOTRE HISTORIQUE

━━━━━━━━━━━━━━━━━━━━━━

{EMOJI_THEME['money']} Total dépensé : {total_spent:.2f}€
{EMOJI_THEME['cart']} Commandes : {orders_count}
{EMOJI_THEME['vip']} Statut : {'VIP ⭐' if vip else 'Standard'}

"""
        
        if top_products:
            message += f"{EMOJI_THEME['product']} Produits favoris :\n"
            for product, count in top_products:
                message += f"• {product} ({count}x)\n"
        
        if vip:
            message += f"\n{EMOJI_THEME['gift']} Réduction VIP : {VIP_DISCOUNT}% sur toutes vos commandes !"
        elif total_spent > 0:
            remaining = VIP_THRESHOLD - total_spent
            if remaining > 0:
                message += f"\n💡 Plus que {remaining:.2f}€ pour devenir VIP !"
        
        keyboard = [[InlineKeyboardButton("🏠 Retour Menu", callback_data="back_to_main")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def referral_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les infos de parrainage"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    referral_code = get_or_create_referral_code(user_id)
    referral_stats = get_referral_stats(user_id)
    
    referred_count = len(referral_stats.get("referred_users", []))
    earnings = referral_stats.get("earnings", 0)
    
    message = f"""{EMOJI_THEME['gift']} PROGRAMME DE PARRAINAGE

━━━━━━━━━━━━━━━━━━━━━━

👥 Parrainez vos amis et gagnez !

🎁 Votre code : {referral_code}

📊 Vos statistiques :
- Parrainages : {referred_count}
- Gains cumulés : {earnings:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

💰 Comment ça marche ?

1️⃣ Partagez votre code
2️⃣ Votre ami l'utilise à sa 1ère commande
3️⃣ Vous recevez 5€ de réduction
4️⃣ Il reçoit 10% de réduction

━━━━━━━━━━━━━━━━━━━━━━

📱 Partagez maintenant :

"Rejoins-moi sur ce service avec le code {referral_code} pour obtenir 10% de réduction sur ta première commande !"
"""
    
    keyboard = [[InlineKeyboardButton("🏠 Retour Menu", callback_data="back_to_main")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== CALLBACK: SÉLECTION PAYS ====================

@error_handler
async def select_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la sélection du pays"""
    query = update.callback_query
    await query.answer()
    
    country_code = query.data.split('_')[1]
    context.user_data['country'] = country_code.upper()
    
    # Dictionnaire des pays
    COUNTRIES = {
        'fr': {'flag': '🇫🇷', 'name': 'France'},
        'ch': {'flag': '🇨🇭', 'name': 'Suisse'},
        'au': {'flag': '🇦🇺', 'name': 'Australie'}
    }
    
    country_info = COUNTRIES.get(country_code, {'flag': '🇫🇷', 'name': 'France'})
    flag = country_info['flag']
    country_name = country_info['name']
    
    message = f"""{flag} {country_name} sélectionné

{EMOJI_THEME['product']} NOS PRODUITS

{get_formatted_price_list(country_code)}

━━━━━━━━━━━━━━━━━━━━━━

{EMOJI_THEME['info']} Choisissez une catégorie :
"""
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI_THEME['product']} Voir tous les produits", callback_data="browse_all")],
        [InlineKeyboardButton("💊 Pills", callback_data="browse_pills"),
         InlineKeyboardButton("🪨 Crystal", callback_data="browse_rocks")],
        [InlineKeyboardButton(f"{EMOJI_THEME['cart']} Mon Panier", callback_data="view_cart")],
        [InlineKeyboardButton("🏠 Retour", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"🌍 Pays sélectionné: {country_name} - User: {query.from_user.id}")

# ==================== CALLBACK: PARCOURIR PRODUITS ====================

@error_handler
async def browse_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche la liste des produits"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.split('_')[1] if '_' in query.data else "all"
    country = context.user_data.get('country', 'FR')
    
    available_products = get_available_products()
    
    if category == "pills":
        products_to_show = [p for p in available_products if p in PILL_SUBCATEGORIES.values()]
        title = "💊 PILLS"
    elif category == "rocks":
        products_to_show = [p for p in available_products if p in ROCK_SUBCATEGORIES.values()]
        title = "🪨 CRYSTAL"
    else:
        products_to_show = list(available_products)
        title = f"{EMOJI_THEME['product']} TOUS LES PRODUITS"
    
    if not products_to_show:
        message = f"{EMOJI_THEME['error']} Aucun produit disponible dans cette catégorie."
        keyboard = [[InlineKeyboardButton("🏠 Retour", callback_data="back_to_main")]]
    else:
        message = f"{title}\n\nSélectionnez un produit :"
        
        keyboard = []
        for product_name in sorted(products_to_show):
            stock = get_stock(product_name)
            if stock is not None and stock == 0:
                button_text = f"{EMOJI_THEME['offline']} {product_name} (Rupture)"
                callback = "out_of_stock"
            else:
                button_text = product_name
                callback = f"product_{product_name}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback)])
        
        keyboard.append([InlineKeyboardButton(f"{EMOJI_THEME['cart']} Mon Panier", callback_data="view_cart")])
        keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data=f"country_{country.lower()}")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== CALLBACK: DÉTAIL PRODUIT ====================

@error_handler
async def product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le détail d'un produit"""
    query = update.callback_query
    await query.answer()
    
    product_name = query.data.replace("product_", "")
    country = context.user_data.get('country', 'FR')
    
    stock = get_stock(product_name)
    price = get_price(product_name, country)
    
    # Vérifier disponibilité
    if stock is not None and stock == 0:
        await query.edit_message_text(
            f"{EMOJI_THEME['offline']} RUPTURE DE STOCK\n\n"
            f"Le produit {product_name} est actuellement indisponible.\n"
            "Revenez plus tard !",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Retour", callback_data="browse_all")]
            ])
        )
        return
    
    # Créer la carte produit
    card = format_product_card(product_name, country, stock)
    
    # Prix dégressifs
    tiers_display = get_pricing_tiers_display(product_name, country)
    
    message = f"""{card}

💰 TARIFS
{tiers_display}

{EMOJI_THEME['info']} Quelle quantité souhaitez-vous ?
(Entrez la quantité en grammes)
"""
    
    keyboard = [
        [InlineKeyboardButton("1g", callback_data=f"addcart_{product_name}_1"),
         InlineKeyboardButton("5g", callback_data=f"addcart_{product_name}_5"),
         InlineKeyboardButton("10g", callback_data=f"addcart_{product_name}_10")],
        [InlineKeyboardButton("25g", callback_data=f"addcart_{product_name}_25"),
         InlineKeyboardButton("50g", callback_data=f"addcart_{product_name}_50"),
         InlineKeyboardButton("100g", callback_data=f"addcart_{product_name}_100")],
        [InlineKeyboardButton("📝 Autre quantité", callback_data=f"customqty_{product_name}")],
        [InlineKeyboardButton("🔙 Retour", callback_data="browse_all")]
    ]
    
    # Envoyer média si disponible
    try:
        await query.message.delete()
        await send_product_media(context, query.message.chat_id, product_name, message)
        
        # Envoyer les boutons séparément
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="👇 Choisissez la quantité :",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Erreur envoi média: {e}")
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    logger.info(f"📦 Produit affiché: {product_name} - User: {query.from_user.id}")

# ==================== CALLBACK: QUANTITÉ PERSONNALISÉE ====================

@error_handler
async def custom_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande quantité personnalisée"""
    query = update.callback_query
    await query.answer()
    
    product_name = query.data.replace("customqty_", "")
    context.user_data['pending_product'] = product_name
    context.user_data['awaiting_quantity'] = True
    
    logger.info(f"📝 custom_quantity: product={product_name}, awaiting_quantity=True, user_id={query.from_user.id}")
    logger.info(f"📝 user_data après: {context.user_data}")
    
    message = f"""📝 QUANTITÉ PERSONNALISÉE

Produit : {product_name}

Envoyez la quantité souhaitée en grammes.
(Exemple: 15 ou 37.5)

💡 Tapez /cancel pour annuler
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="browse_all")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== HANDLER: RÉCEPTION QUANTITÉ ====================

@error_handler
async def receive_custom_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne la quantité personnalisée"""
    logger.info(f"📝 receive_custom_quantity appelé: awaiting={context.user_data.get('awaiting_quantity')}, text={update.message.text}")
    
    if not context.user_data.get('awaiting_quantity'):
        logger.warning("⚠️ awaiting_quantity=False, abandon")
        return
    
    user_id = update.effective_user.id
    product_name = context.user_data.get('pending_product')
    
    logger.info(f"📝 product_name={product_name}")
    
    if not product_name:
        logger.warning("⚠️ product_name manquant")
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Session expirée. Veuillez recommencer."
        )
        context.user_data.pop('awaiting_quantity', None)
        return
    
    try:
        quantity = float(update.message.text.strip().replace(',', '.'))
        
        logger.info(f"📝 Quantité saisie: {quantity}g")
        
        if quantity <= 0:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} La quantité doit être supérieure à 0."
            )
            return
        
        if quantity > 1000:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Quantité maximale : 1000g"
            )
            return
        
        # Vérifier stock
        stock = get_stock(product_name)
        if stock is not None and quantity > stock:
            await update.message.reply_text(
                f"{EMOJI_THEME['warning']} Stock insuffisant.\n"
                f"Disponible : {stock}g"
            )
            return
        
        # Ajouter au panier
        context.user_data['awaiting_quantity'] = False
        context.user_data['pending_product'] = None
        
        logger.info(f"✅ Ajout au panier: {product_name} {quantity}g")
        
        if 'cart' not in context.user_data:
            context.user_data['cart'] = []
        
        context.user_data['cart'].append({
            'produit': product_name,
            'quantite': quantity
        })
        
        country = context.user_data.get('country', 'FR')
        price = get_price_for_quantity(product_name, country, quantity)
        total = price * quantity
        
        message = f"""{EMOJI_THEME['success']} AJOUTÉ AU PANIER

{product_name} - {quantity}g
Prix unitaire : {price}€/g
Total : {total:.2f}€

{format_cart(context.user_data['cart'], context.user_data)}
"""
        
        keyboard = [
            [InlineKeyboardButton("➕ Ajouter autre produit", callback_data="browse_all")],
            [InlineKeyboardButton(f"{EMOJI_THEME['cart']} Voir Panier", callback_data="view_cart")],
            [InlineKeyboardButton("✅ Commander", callback_data="validate_cart")]
        ]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"🛒 Ajouté panier: {product_name} {quantity}g - User: {user_id}")
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Quantité invalide. Entrez un nombre."
        )

# ==================== CALLBACK: AJOUTER AU PANIER ====================

@error_handler
async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajoute un produit au panier"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    product_name = '_'.join(parts[1:-1])
    quantity = float(parts[-1])
    
    # Vérifier stock
    stock = get_stock(product_name)
    if stock is not None and quantity > stock:
        await query.answer(
            f"{EMOJI_THEME['error']} Stock insuffisant (Dispo: {stock}g)",
            show_alert=True
        )
        return
    
    # Initialiser panier si nécessaire
    if 'cart' not in context.user_data:
        context.user_data['cart'] = []
    
    # Ajouter au panier
    context.user_data['cart'].append({
        'produit': product_name,
        'quantite': quantity
    })
    
    country = context.user_data.get('country', 'FR')
    price = get_price_for_quantity(product_name, country, quantity)
    total = price * quantity
    
    message = f"""{EMOJI_THEME['success']} AJOUTÉ AU PANIER

{product_name} - {quantity}g
Prix : {price}€/g × {quantity} = {total:.2f}€

{format_cart(context.user_data['cart'], context.user_data)}
"""
    
    keyboard = [
        [InlineKeyboardButton("➕ Continuer shopping", callback_data="browse_all")],
        [InlineKeyboardButton(f"{EMOJI_THEME['cart']} Voir Panier", callback_data="view_cart")],
        [InlineKeyboardButton("✅ Passer commande", callback_data="validate_cart")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"✅ Ajouté: {product_name} {quantity}g - User: {query.from_user.id}")

# ==================== CALLBACK: VOIR PANIER ====================

@error_handler
async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le panier"""
    query = update.callback_query
    await query.answer()
    
    cart = context.user_data.get('cart', [])
    
    if not cart:
        message = f"""{EMOJI_THEME['cart']} VOTRE PANIER

Votre panier est vide.

Commencez vos achats dès maintenant !
"""
        keyboard = [[InlineKeyboardButton("🛍️ Voir produits", callback_data="browse_all")]]
    else:
        country = context.user_data.get('country', 'FR')
        
        message = f"{EMOJI_THEME['cart']} VOTRE PANIER\n\n"
        
        subtotal = 0
        for i, item in enumerate(cart, 1):
            product = item['produit']
            qty = item['quantite']
            price = get_price_for_quantity(product, country, qty)
            line_total = price * qty
            subtotal += line_total
            
            message += f"{i}. {product}\n"
            message += f"   {qty}g × {price}€/g = {line_total:.2f}€\n\n"
        
        message += f"━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"{EMOJI_THEME['money']} SOUS-TOTAL : {subtotal:.2f}€\n\n"
        message += f"(Frais de livraison calculés à l'étape suivante)"
        
        keyboard = [
            [InlineKeyboardButton("➕ Ajouter produit", callback_data="browse_all")],
            [InlineKeyboardButton("🗑️ Vider panier", callback_data="clear_cart")],
            [InlineKeyboardButton("✅ Commander", callback_data="validate_cart")]
        ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== CALLBACK: VIDER PANIER ====================

@error_handler
async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vide le panier"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['cart'] = []
    
    message = f"""{EMOJI_THEME['success']} PANIER VIDÉ

Votre panier a été vidé avec succès.
"""
    
    keyboard = [[InlineKeyboardButton("🛍️ Voir produits", callback_data="browse_all")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"🗑️ Panier vidé - User: {query.from_user.id}")

# FIN DU BLOC 5
# ==================== BLOC 6 : PANEL ADMINISTRATEUR (VERSION CORRIGÉE) ====================

# ==================== PANEL ADMIN PRINCIPAL - VERSION CORRIGÉE - BUG FIXÉ ====================

@error_handler
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le panel administrateur - VERSION CORRIGÉE SANS PARSE_MODE"""
    # Gérer à la fois Command et CallbackQuery
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        is_callback = True
    else:
        user_id = update.effective_user.id
        is_callback = False
    
    if not is_admin(user_id):
        return
    
    admin_info = get_admin_info(user_id)
    level = admin_info.get('level', 'admin')
    name = admin_info.get('name', 'Admin')
    
    # Stats rapides
    users_count = len(load_users())
    low_stock = len(get_low_stock_products())
    out_stock = len(get_out_of_stock_products())
    
    # MESSAGE EN TEXTE BRUT - AUCUN FORMATAGE MARKDOWN/HTML
    message = f"""🎛️ PANEL ADMINISTRATEUR

👤 {name} ({level.upper()})

━━━━━━━━━━━━━━━━━━━━━━

📊 STATISTIQUES RAPIDES

👥 Utilisateurs : {users_count}
📦 Produits : {len(load_product_registry())}
⚠️ Stock faible : {low_stock}
🔴 Ruptures : {out_stock}

━━━━━━━━━━━━━━━━━━━━━━

Choisissez une section :
"""
    
    keyboard = []
    
    # Gestion des produits (tous les admins)
    if level in ['super_admin', 'admin']:
        keyboard.append([
            InlineKeyboardButton("📦 Produits", callback_data="admin_products"),
            InlineKeyboardButton("📊 Stocks", callback_data="admin_stocks")
        ])
        keyboard.append([
            InlineKeyboardButton("💰 Prix", callback_data="admin_prices"),
            InlineKeyboardButton("🎁 Promos", callback_data="admin_promos")
        ])
    
    # Commandes (tous niveaux)
    keyboard.append([InlineKeyboardButton("🛒 Commandes", callback_data="admin_orders")])
    
    # Finances (tous niveaux - accès différent selon niveau)
    keyboard.append([InlineKeyboardButton("💰 Finances", callback_data="admin_finances")])
    
    # Prix de revient (admin et super-admin)
    if level in ['super_admin', 'admin']:
        keyboard.append([InlineKeyboardButton("💵 Prix de revient", callback_data="admin_costs")])
    
    # Gestion admins (super-admin uniquement)
    if level == 'super_admin':
        keyboard.append([
            InlineKeyboardButton("✏️ ÉDITION COMPLÈTE", callback_data="admin_edit_menu")
        ])
        keyboard.append([
            InlineKeyboardButton("👥 Gérer Admins", callback_data="admin_manage_admins"),
            InlineKeyboardButton("💼 Gestion Salaires", callback_data="admin_salary_config")
        ])
        keyboard.append([
            InlineKeyboardButton("📒 Livre de Comptes", callback_data="admin_ledger")
        ])
    
    # Paramètres (admin+)
    if level in ['super_admin', 'admin']:
        keyboard.append([
            InlineKeyboardButton("⚙️ Paramètres", callback_data="admin_settings"),
            InlineKeyboardButton("📈 Statistiques", callback_data="admin_stats")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Fermer", callback_data="admin_close")])
    
    # ENVOI SANS PARSE_MODE - C'EST LA CLÉ DU FIX
    if is_callback:
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    logger.info(f"🔐 Panel admin affiché: {user_id} ({level})")

# ==================== GESTION PRODUITS ====================

@error_handler
async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu gestion produits"""
    query = update.callback_query
    await query.answer()
    
    registry = load_product_registry()
    available = get_available_products()
    
    message = f"""📦 GESTION DES PRODUITS

Total produits : {len(registry)}
Disponibles : {len(available)}
Masqués : {len(registry) - len(available)}

Que souhaitez-vous faire ?
"""
    
    keyboard = [
        [InlineKeyboardButton("📋 Liste produits", callback_data="admin_list_products")],
        [InlineKeyboardButton("✅ Activer/Désactiver", callback_data="admin_toggle_products")],
        [InlineKeyboardButton("➕ Ajouter produit", callback_data="admin_add_product")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler

@error_handler
async def admin_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajouter un nouveau produit - Guide"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    message = """➕ AJOUTER UN PRODUIT

⚠️ Les produits sont gérés via fichier JSON.

📝 Pour ajouter un produit:

1️⃣ Modifier le fichier:
   data/product_registry.json

2️⃣ Ajouter votre produit:
```json
{
  "nom_produit": {
    "name": "Nom affiché",
    "code": "nom_produit",
    "emoji": "🎯",
    "category": "pill",
    "image": "image.jpg",
    "created_at": "2025-01-19T12:00:00"
  }
}
```

3️⃣ Redémarrer le bot

4️⃣ Définir le prix:
   /admin → Tarifs

5️⃣ Définir le stock:
   /admin → Stocks

6️⃣ Activer le produit:
   /admin → Produits → Activer/Désactiver

📂 Catégories disponibles:
• pill - Pills (prix unitaire)
• rock - Crystal (prix/gramme)
• powder - Weed (prix/gramme)
"""
    
    keyboard = [
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_products")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liste tous les produits"""
    query = update.callback_query
    await query.answer()
    
    registry = load_product_registry()
    available = get_available_products()
    
    message = "📋 LISTE DES PRODUITS\n\n"
    
    for code, product in sorted(registry.items()):
        name = product['name']
        status = "✅" if name in available else "❌"
        stock = get_stock(name)
        stock_text = f"({stock}g)" if stock is not None else "(∞)"
        
        message += f"{status} {name} {stock_text}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_products")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_toggle_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Active/désactive des produits"""
    query = update.callback_query
    await query.answer()
    
    products = PRODUCTS_DATA.get('products', {})
    
    message = "✅ ACTIVER/DÉSACTIVER PRODUITS\n\nCliquez pour changer le statut :\n"
    
    keyboard = []
    for product_id, product_data in sorted(products.items()):
        name = product_data.get('name', {}).get('fr', product_id)
        is_active = product_data.get('active', True)
        icon = "✅" if is_active else "❌"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {name}",
                callback_data=f"admin_toggle_{product_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_products")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_toggle_product_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute le toggle d'un produit"""
    query = update.callback_query
    await query.answer()
    
    product_id = query.data.replace("admin_toggle_", "")
    products = PRODUCTS_DATA.get('products', {})
    
    if product_id not in products:
        await query.answer("Produit introuvable", show_alert=True)
        return
    
    product = products[product_id]
    product_name = product.get('name', {}).get('fr', product_id)
    current_state = product.get('active', True)
    
    # Toggle l'état
    product['active'] = not current_state
    
    # Sauvegarder
    PRODUCTS_DATA['products'] = products
    save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)
    
    # Recharger tout
    reload_products()
    init_product_codes()
    
    action = "activé" if not current_state else "désactivé"
    
    await query.answer(f"{product_name} {action}", show_alert=True)
    
    # Rafraîchir la liste
    await admin_toggle_products(update, context)
    
    logger.info(f"🔄 Produit {action}: {product_name} (ID: {product_id})")

# ==================== GESTION STOCKS ====================

@error_handler
async def admin_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu gestion stocks"""
    query = update.callback_query
    await query.answer()
    
    stocks = load_stocks()
    low_stock = get_low_stock_products()
    out_stock = get_out_of_stock_products()
    
    message = f"""📊 GESTION DES STOCKS

Total produits : {len(stocks)}
⚠️ Stock faible : {len(low_stock)}
🔴 Ruptures : {len(out_stock)}

Que souhaitez-vous faire ?
"""
    
    keyboard = [
        [InlineKeyboardButton("📋 Voir stocks", callback_data="admin_view_stocks")],
        [InlineKeyboardButton("➕ Ajouter stock", callback_data="admin_add_stock")],
        [InlineKeyboardButton("⚠️ Alertes stock", callback_data="admin_stock_alerts")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_view_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche tous les stocks"""
    query = update.callback_query
    await query.answer()
    
    stocks = load_stocks()
    registry = load_product_registry()
    
    message = "📊 ÉTAT DES STOCKS\n\n"
    
    for code, product in sorted(registry.items()):
        name = product['name']
        stock_info = stocks.get(name, {})
        qty = stock_info.get('quantity', '∞')
        threshold = stock_info.get('alert_threshold', 20)
        
        if qty == '∞':
            icon = "♾️"
            message += f"{icon} {name}: Illimité\n"
        elif qty == 0:
            icon = "🔴"
            message += f"{icon} {name}: RUPTURE\n"
        elif qty <= threshold:
            icon = "⚠️"
            message += f"{icon} {name}: {qty}g (seuil: {threshold}g)\n"
        else:
            icon = "✅"
            message += f"{icon} {name}: {qty}g\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_stocks")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Interface pour ajouter du stock"""
    query = update.callback_query
    await query.answer()
    
    registry = load_product_registry()
    
    message = "➕ AJOUTER DU STOCK\n\nSélectionnez un produit :"
    
    keyboard = []
    for code, product in sorted(registry.items()):
        name = product['name']
        current_stock = get_stock(name)
        stock_text = f"({current_stock}g)" if current_stock is not None else "(∞)"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{name} {stock_text}",
                callback_data=f"admin_stock_select_{code}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_stocks")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_stock_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les alertes stock"""
    query = update.callback_query
    await query.answer()
    
    low_stock = get_low_stock_products()
    out_stock = get_out_of_stock_products()
    
    message = "⚠️ ALERTES STOCK\n\n"
    
    if out_stock:
        message += "🔴 RUPTURES DE STOCK\n"
        for product in out_stock:
            message += f"• {product}\n"
        message += "\n"
    
    if low_stock:
        message += "⚠️ STOCK FAIBLE\n"
        for item in low_stock:
            message += f"• {item['product']}: {item['quantity']}g (seuil: {item['threshold']}g)\n"
        message += "\n"
    
    if not out_stock and not low_stock:
        message += "✅ Tous les stocks sont OK !"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_stocks")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== GESTION PRIX ====================

@error_handler
async def admin_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu gestion prix"""
    query = update.callback_query
    await query.answer()
    
    message = f"""💰 GESTION DES PRIX

Gérez les prix de vos produits par pays et configurez des tarifs dégressifs.

Que souhaitez-vous faire ?
"""
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Prix France", callback_data="admin_prices_fr")],
        [InlineKeyboardButton("🇨🇭 Prix Suisse", callback_data="admin_prices_ch")],
        [InlineKeyboardButton("📊 Prix dégressifs", callback_data="admin_pricing_tiers")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_pricing_tiers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de gestion des prix dégressifs"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé - Super Admin uniquement", show_alert=True)
        return
    
    tiered = load_tiered_pricing()
    
    # Compter les configurations
    total_configs = 0
    countries_with_tiers = []
    for country, products in tiered.items():
        if products:
            countries_with_tiers.append(country)
            for product_id, tiers in products.items():
                total_configs += len(tiers)
    
    message = f"""📊 PRIX DÉGRESSIFS

Configurations: {total_configs}
Pays configurés: {len(countries_with_tiers)}

Les prix dégressifs permettent d'offrir des réductions automatiques selon la quantité commandée.

Choisissez un pays:
"""
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data="tiered_country_FR")],
        [InlineKeyboardButton("🇨🇭 Suisse", callback_data="tiered_country_CH")],
        [InlineKeyboardButton("🇦🇺 Australie", callback_data="tiered_country_AU")],
        [InlineKeyboardButton("➕ Ajouter pays", callback_data="tiered_add_country")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_manage_prices")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_prices_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les prix d'un pays"""
    query = update.callback_query
    await query.answer()
    
    country = "FR" if "fr" in query.data else "CH"
    flag = "🇫🇷" if country == "FR" else "🇨🇭"
    
    prices = load_prices()
    country_prices = prices.get(country, {})
    
    message = f"{flag} PRIX {country}\n\n"
    
    for product, price in sorted(country_prices.items()):
        message += f"• {product}: {price}€/g\n"
    
    keyboard = [
        [InlineKeyboardButton("✏️ Modifier prix", callback_data=f"admin_edit_prices_{country.lower()}")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_prices")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== GESTION CODES PROMO ====================

@error_handler
async def admin_promos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu gestion codes promo"""
    query = update.callback_query
    await query.answer()
    
    promo_codes = load_promo_codes()
    active_codes = sum(1 for code in promo_codes.values() 
                      if code.get('used_count', 0) < code.get('max_uses', 999999))
    
    message = f"""🎁 GESTION CODES PROMO

Total codes : {len(promo_codes)}
Codes actifs : {active_codes}

Que souhaitez-vous faire ?
"""
    
    keyboard = [
        [InlineKeyboardButton("📋 Liste codes", callback_data="admin_list_promos")],
        [InlineKeyboardButton("➕ Créer code", callback_data="admin_create_promo")],
        [InlineKeyboardButton("🗑️ Supprimer code", callback_data="admin_delete_promo")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_list_promos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liste tous les codes promo"""
    query = update.callback_query
    await query.answer()
    
    promo_codes = load_promo_codes()
    
    if not promo_codes:
        message = "🎁 CODES PROMO\n\nAucun code promo créé."
    else:
        message = "🎁 CODES PROMO\n\n"
        
        for code, data in sorted(promo_codes.items()):
            type_icon = "%" if data['type'] == 'percentage' else "€"
            value = data['value']
            used = data.get('used_count', 0)
            max_uses = data.get('max_uses', '∞')
            
            status = "✅" if used < max_uses else "❌"
            
            message += f"{status} {code}\n"
            message += f"   Réduction: {value}{type_icon}\n"
            message += f"   Utilisations: {used}/{max_uses}\n"
            
            if 'min_order' in data:
                message += f"   Minimum: {data['min_order']}€\n"
            
            if 'valid_until' in data:
                expiry = datetime.fromisoformat(data['valid_until'])
                message += f"   Expire: {expiry.strftime('%d/%m/%Y')}\n"
            
            message += "\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_promos")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== GESTION COMMANDES ====================

@error_handler
async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les commandes"""
    query = update.callback_query
    await query.answer()
    
    message = """🛒 GESTION DES COMMANDES

Que souhaitez-vous consulter ?
"""
    
    keyboard = [
        [InlineKeyboardButton("📋 Toutes les commandes", callback_data="admin_orders_all")],
        [InlineKeyboardButton("⏳ En attente", callback_data="admin_orders_pending")],
        [InlineKeyboardButton("📊 Statistiques", callback_data="admin_orders_stats")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_orders_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche toutes les commandes récentes"""
    query = update.callback_query
    await query.answer()
    
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        message = """🛒 AUCUNE COMMANDE

Aucune commande n'a encore été enregistrée.
"""
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_orders")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    try:
        import csv as csv_module
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        if not orders:
            message = """🛒 AUCUNE COMMANDE

Aucune commande n'a encore été enregistrée.
"""
        else:
            # Prendre les 10 dernières commandes
            recent_orders = orders[-10:][::-1]  # Inverser pour avoir les plus récentes en premier
            
            message = f"""🛒 DERNIÈRES COMMANDES

Total: {len(orders)} commandes

━━━━━━━━━━━━━━━━━━━━━━

"""
            
            for order in recent_orders:
                order_id = order.get('order_id', 'N/A')
                date = order.get('date', 'N/A')[:16]  # Juste date et heure
                client = order.get('first_name', 'N/A')
                total = order.get('total', '0')
                status = order.get('status', 'N/A')
                
                status_icon = "⏳" if status == "En attente" else "✅"
                
                message += f"""{status_icon} {order_id}
📅 {date}
👤 {client}
💰 {total}€
━━━━━━━━━━━━━━━━━━━━━━

"""
            
            if len(orders) > 10:
                message += f"\n... et {len(orders) - 10} autres commandes"
        
        keyboard = [
            [InlineKeyboardButton("⏳ En attente", callback_data="admin_orders_pending")],
            [InlineKeyboardButton("🔙 Retour", callback_data="admin_orders")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    except Exception as e:
        logger.error(f"Erreur lecture commandes: {e}")
        await query.edit_message_text(
            f"{EMOJI_THEME['error']} Erreur lors de la lecture des commandes.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="admin_orders")]])
        )

@error_handler
async def admin_orders_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les commandes en attente"""
    query = update.callback_query
    await query.answer()
    
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        message = """⏳ AUCUNE COMMANDE EN ATTENTE

Toutes les commandes ont été traitées.
"""
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_orders")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    try:
        import csv as csv_module
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        # Filtrer les commandes en attente
        pending = [o for o in orders if o.get('status') == 'En attente']
        
        if not pending:
            message = """✅ TOUTES LES COMMANDES TRAITÉES

Aucune commande en attente actuellement.
"""
        else:
            message = f"""⏳ COMMANDES EN ATTENTE

{len(pending)} commande(s) à traiter

━━━━━━━━━━━━━━━━━━━━━━

"""
            
            for order in pending[-20:]:  # Max 20 commandes
                order_id = order.get('order_id', 'N/A')
                date = order.get('date', 'N/A')[:16]
                client = order.get('first_name', 'N/A')
                username = order.get('username', 'N/A')
                total = order.get('total', '0')
                delivery = order.get('delivery_type', 'N/A')
                
                message += f"""📋 {order_id}
📅 {date}
👤 {client} (@{username})
🚚 {delivery}
💰 {total}€
━━━━━━━━━━━━━━━━━━━━━━

"""
        
        keyboard = [
            [InlineKeyboardButton("📋 Toutes", callback_data="admin_orders_all")],
            [InlineKeyboardButton("🔙 Retour", callback_data="admin_orders")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    except Exception as e:
        logger.error(f"Erreur lecture commandes en attente: {e}")
        await query.edit_message_text(
            f"{EMOJI_THEME['error']} Erreur lors de la lecture des commandes.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="admin_orders")]])
        )

@error_handler
async def admin_orders_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les statistiques des commandes"""
    query = update.callback_query
    await query.answer()
    
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        message = """📊 STATISTIQUES

Aucune donnée disponible.
"""
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_orders")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    try:
        import csv as csv_module
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        if not orders:
            message = "📊 STATISTIQUES\n\nAucune donnée disponible."
        else:
            total_orders = len(orders)
            pending = len([o for o in orders if o.get('status') == 'En attente'])
            
            # Calcul CA total
            try:
                total_ca = sum(float(o.get('total', 0)) for o in orders)
                avg_order = total_ca / total_orders if total_orders > 0 else 0
            except:
                total_ca = 0
                avg_order = 0
            
            # Répartition par pays
            fr_count = len([o for o in orders if o.get('country') == 'FR'])
            ch_count = len([o for o in orders if o.get('country') == 'CH'])
            
            # Répartition par livraison
            postal = len([o for o in orders if o.get('delivery_type') == 'postal'])
            express = len([o for o in orders if o.get('delivery_type') == 'express'])
            meetup = len([o for o in orders if o.get('delivery_type') == 'meetup'])
            
            message = f"""📊 STATISTIQUES COMMANDES

━━━━━━━━━━━━━━━━━━━━━━

📈 GLOBAL
Total commandes : {total_orders}
⏳ En attente : {pending}
✅ Traitées : {total_orders - pending}

💰 CHIFFRE D'AFFAIRES
CA total : {total_ca:.2f}€
Panier moyen : {avg_order:.2f}€

🌍 PAR PAYS
🇫🇷 France : {fr_count} ({fr_count/total_orders*100:.1f}%)
🇨🇭 Suisse : {ch_count} ({ch_count/total_orders*100:.1f}%)

🚚 PAR LIVRAISON
📦 Postale : {postal}
⚡ Express : {express}
🤝 Rendez-vous : {meetup}

━━━━━━━━━━━━━━━━━━━━━━
"""
        
        keyboard = [
            [InlineKeyboardButton("📋 Voir commandes", callback_data="admin_orders_all")],
            [InlineKeyboardButton("🔙 Retour", callback_data="admin_orders")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    except Exception as e:
        logger.error(f"Erreur calcul stats commandes: {e}")
        await query.edit_message_text(
            f"{EMOJI_THEME['error']} Erreur lors du calcul des statistiques.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="admin_orders")]])
        )

# ==================== GESTION ADMINS (SUPER-ADMIN) ====================

@error_handler
async def admin_manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu gestion des administrateurs (super-admin uniquement)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not is_super_admin(user_id):
        await query.answer("Accès refusé - Super-admin requis", show_alert=True)
        return
    
    stats = get_admin_stats()
    
    message = f"""👥 GESTION DES ADMINS

📊 Statistiques :
- Total : {stats['total']}
- Super-admins : {stats['super_admins']}
- Admins : {stats['admins']}
- Modérateurs : {stats['moderators']}

Que souhaitez-vous faire ?
"""
    
    keyboard = [
        [InlineKeyboardButton("📋 Liste admins", callback_data="admin_list_admins")],
        [InlineKeyboardButton("➕ Ajouter admin", callback_data="admin_add_admin")],
        [InlineKeyboardButton("🗑️ Supprimer admin", callback_data="admin_remove_admin")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ADMIN_MANAGE_MENU

@error_handler
async def admin_list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche la liste de tous les admins"""
    query = update.callback_query
    await query.answer()
    
    admin_list = format_admin_list()
    
    message = f"👥 LISTE DES ADMINISTRATEURS\n\n{admin_list}"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_manage_admins")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ADMIN_VIEW_LIST

# FIN DU BLOC 6
# ==================== BLOC 7 : SUITE ADMIN + PROCESSUS COMMANDE ====================

# ==================== SUITE GESTION ADMINS ====================

@error_handler
async def admin_add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Démarre le processus d'ajout d'admin"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not is_super_admin(user_id):
        await query.answer("Accès refusé - Super-admin requis", show_alert=True)
        return
    
    message = f"""➕ AJOUTER UN ADMINISTRATEUR

Pour ajouter un nouvel administrateur :

1️⃣ Demandez-lui d'envoyer /myid au bot
2️⃣ Il vous communiquera son ID Telegram
3️⃣ Entrez cet ID ci-dessous

💡 L'ID est un nombre (ex: 123456789)

Envoyez l'ID Telegram du nouvel admin :
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_manage_admins")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Utiliser user_data au lieu de ConversationHandler
    context.user_data['awaiting_admin_id'] = True
    context.user_data['admin_action'] = 'add'
    
    logger.info(f"✅ État admin configuré pour user {user_id}")
    logger.info(f"🔍 user_data après config: {context.user_data}")

@error_handler
async def admin_remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Démarre le processus de suppression d'admin"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not is_super_admin(user_id):
        await query.answer("Accès refusé", show_alert=True)
        return ConversationHandler.END
    
    message = "🗑️ SUPPRIMER UN ADMIN\n\nSélectionnez l'admin à supprimer :\n\n"
    message += "⚠️ Vous ne pouvez pas vous supprimer vous-même.\n"
    
    keyboard = []
    
    for admin_id, admin_info in ADMINS.items():
        if int(admin_id) == user_id:
            continue  # Ne pas afficher soi-même
        
        name = admin_info.get('name', f'Admin_{admin_id}')
        level = admin_info.get('level', 'admin')
        
        level_icons = {
            'super_admin': '👑',
            'admin': '🔐',
            'moderator': '🛡️'
        }
        
        icon = level_icons.get(level, '👤')
        
        # Anonymiser l'ID
        anonymous_id = anonymize_admin_id(int(admin_id))
        
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {name} (ID: {anonymous_id})",
                callback_data=f"admin_remove_{admin_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="admin_manage_admins")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ADMIN_REMOVE_CONFIRM

# ==================== PARAMÈTRES SYSTÈME ====================

@error_handler
async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu paramètres système"""
    query = update.callback_query
    await query.answer()
    
    horaires = load_horaires()
    maintenance = load_maintenance_status()
    
    horaires_status = "✅ Activé" if horaires.get('enabled') else "❌ Désactivé"
    maintenance_status = "🔧 Actif" if maintenance.get('enabled') else "✅ Normal"
    
    message = f"""⚙️ PARAMÈTRES SYSTÈME

🕐 Horaires : {horaires_status}
   {get_horaires_text()}

🔧 Maintenance : {maintenance_status}

Que souhaitez-vous faire ?
"""
    
    keyboard = [
        [InlineKeyboardButton("🔐 Informations Licence", callback_data="show_license")],
        [InlineKeyboardButton("🕐 Horaires", callback_data="admin_horaires")],
        [InlineKeyboardButton("🔧 Maintenance", callback_data="admin_maintenance")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_horaires(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion des horaires de livraison"""
    query = update.callback_query
    await query.answer()
    
    horaires = load_horaires()
    enabled = horaires.get('enabled', True)
    start = horaires.get('start', '09:00')
    end = horaires.get('end', '22:00')
    
    status_icon = "✅" if enabled else "❌"
    status_text = "Actif" if enabled else "Désactivé"
    
    message = f"""🕐 HORAIRES DE LIVRAISON

Statut : {status_icon} {status_text}

📅 Horaires actuels :
De {start} à {end}

ℹ️ Les commandes passées en dehors de ces horaires seront traitées le lendemain.

Que souhaitez-vous faire ?
"""
    
    keyboard = []
    
    if enabled:
        keyboard.append([InlineKeyboardButton("❌ Désactiver", callback_data="admin_horaires_toggle")])
    else:
        keyboard.append([InlineKeyboardButton("✅ Activer", callback_data="admin_horaires_toggle")])
    
    keyboard.extend([
        [InlineKeyboardButton("✏️ Modifier heures", callback_data="admin_horaires_edit")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_settings")]
    ])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_horaires_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Active/désactive les horaires"""
    query = update.callback_query
    await query.answer()
    
    horaires = load_horaires()
    enabled = horaires.get('enabled', True)
    
    # Inverser
    horaires['enabled'] = not enabled
    save_horaires(horaires)
    
    new_status = "activés" if horaires['enabled'] else "désactivés"
    
    await query.answer(f"✅ Horaires {new_status}", show_alert=True)
    
    # Retour au menu horaires
    await admin_horaires(update, context)

@error_handler
async def admin_horaires_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Interface d'édition des horaires"""
    query = update.callback_query
    await query.answer()
    
    message = """✏️ MODIFIER LES HORAIRES

Quelle heure souhaitez-vous modifier ?
"""
    
    keyboard = [
        [InlineKeyboardButton("🌅 Heure d'ouverture", callback_data="admin_horaires_edit_start")],
        [InlineKeyboardButton("🌙 Heure de fermeture", callback_data="admin_horaires_edit_end")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_horaires")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_horaires_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande la nouvelle heure d'ouverture"""
    query = update.callback_query
    await query.answer()
    
    horaires = load_horaires()
    current = horaires.get('start', '09:00')
    
    message = f"""🌅 HEURE D'OUVERTURE

Heure actuelle : {current}

Entrez la nouvelle heure d'ouverture au format HH:MM

Exemples : 08:00, 09:30, 10:00
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_horaires")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_horaire_start'] = True

@error_handler
async def admin_horaires_edit_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande la nouvelle heure de fermeture"""
    query = update.callback_query
    await query.answer()
    
    horaires = load_horaires()
    current = horaires.get('end', '22:00')
    
    message = f"""🌙 HEURE DE FERMETURE

Heure actuelle : {current}

Entrez la nouvelle heure de fermeture au format HH:MM

Exemples : 21:00, 22:30, 23:00
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_horaires")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_horaire_end'] = True

@error_handler
async def receive_horaire_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne et valide la nouvelle heure"""
    if not is_admin(update.effective_user.id):
        return
    
    time_str = update.message.text.strip()
    
    # Valider le format HH:MM
    import re
    if not re.match(r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$', time_str):
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Format invalide !\n\n"
            "Utilisez le format HH:MM\n"
            "Exemples : 09:00, 14:30, 22:00"
        )
        return
    
    horaires = load_horaires()
    
    if context.user_data.get('awaiting_horaire_start'):
        horaires['start'] = time_str
        save_horaires(horaires)
        
        context.user_data.pop('awaiting_horaire_start', None)
        
        message = f"""{EMOJI_THEME['success']} HEURE D'OUVERTURE MISE À JOUR

Nouvelle heure : {time_str}

Les livraisons seront disponibles à partir de {time_str}.
"""
        
    elif context.user_data.get('awaiting_horaire_end'):
        horaires['end'] = time_str
        save_horaires(horaires)
        
        context.user_data.pop('awaiting_horaire_end', None)
        
        message = f"""{EMOJI_THEME['success']} HEURE DE FERMETURE MISE À JOUR

Nouvelle heure : {time_str}

Les livraisons seront disponibles jusqu'à {time_str}.
"""
    else:
        return
    
    keyboard = [
        [InlineKeyboardButton("🕐 Horaires", callback_data="admin_horaires")],
        [InlineKeyboardButton("🏠 Panel", callback_data="admin_back_panel")]
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"⏰ Horaires modifiés: {horaires}")

@error_handler
async def admin_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion mode maintenance"""
    query = update.callback_query
    await query.answer()
    
    status = load_maintenance_status()
    is_active = status.get('enabled', False)
    
    if is_active:
        button_text = "✅ Désactiver maintenance"
        button_callback = "admin_maintenance_off"
        status_text = "🔧 MODE MAINTENANCE ACTIF"
    else:
        button_text = "🔧 Activer maintenance"
        button_callback = "admin_maintenance_on"
        status_text = "✅ FONCTIONNEMENT NORMAL"
    
    message = f"""{status_text}

Le mode maintenance empêche les utilisateurs normaux d'utiliser le bot.

Les administrateurs gardent l'accès complet.
"""
    
    keyboard = [
        [InlineKeyboardButton(button_text, callback_data=button_callback)],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_settings")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_maintenance_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Active/désactive la maintenance"""
    query = update.callback_query
    await query.answer()
    
    enable = "on" in query.data
    
    set_maintenance_mode(enable)
    
    if enable:
        message = f"{EMOJI_THEME['warning']} MAINTENANCE ACTIVÉE\n\nLe bot est maintenant en mode maintenance."
    else:
        message = f"{EMOJI_THEME['success']} MAINTENANCE DÉSACTIVÉE\n\nLe bot fonctionne normalement."
    
    await query.answer(message, show_alert=True)
    await admin_maintenance(update, context)

# ==================== STATISTIQUES ====================

@error_handler
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les statistiques"""
    query = update.callback_query
    await query.answer()
    
    # Stats utilisateurs
    users = load_users()
    history = load_client_history()
    
    total_users = len(users)
    vip_users = sum(1 for data in history.values() if data.get('vip_status'))
    
    # Stats commandes
    stats = load_stats()
    weekly_sales = stats.get('weekly', [])
    
    if weekly_sales:
        weekly_total = sum(sale['amount'] for sale in weekly_sales)
        weekly_count = len(weekly_sales)
        avg_order = weekly_total / weekly_count if weekly_count > 0 else 0
    else:
        weekly_total = 0
        weekly_count = 0
        avg_order = 0
    
    # Stats stocks
    stocks = load_stocks()
    low_stock = len(get_low_stock_products())
    out_stock = len(get_out_of_stock_products())
    
    message = f"""📈 STATISTIQUES

━━━━━━━━━━━━━━━━━━━━━━

👥 UTILISATEURS
- Total : {total_users}
- VIP : {vip_users}

━━━━━━━━━━━━━━━━━━━━━━

🛒 COMMANDES (7 JOURS)
- Nombre : {weekly_count}
- CA : {weekly_total:.2f}€
- Panier moyen : {avg_order:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

📦 STOCKS
- Total produits : {len(stocks)}
- ⚠️ Stock faible : {low_stock}
- 🔴 Ruptures : {out_stock}

━━━━━━━━━━━━━━━━━━━━━━
"""
    
    keyboard = [
        [InlineKeyboardButton("📊 Rapport détaillé", callback_data="admin_detailed_stats")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_detailed_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche des statistiques détaillées"""
    query = update.callback_query
    await query.answer()
    
    # Stats utilisateurs
    users = load_users()
    history = load_client_history()
    
    # Calculer top clients
    top_clients = sorted(
        [(uid, data.get('total_spent', 0)) for uid, data in history.items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    # Stats produits
    registry = load_product_registry()
    stocks = load_stocks()
    
    # Stats ventes
    stats = load_stats()
    weekly_sales = stats.get('weekly', [])
    
    # Produits les plus vendus
    product_sales = {}
    for sale in weekly_sales:
        for product in sale.get('products', []):
            product_sales[product] = product_sales.get(product, 0) + 1
    
    top_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:5]
    
    message = f"""📊 STATISTIQUES DÉTAILLÉES

━━━━━━━━━━━━━━━━━━━━━━

👥 TOP 5 CLIENTS
"""
    
    for i, (uid, total) in enumerate(top_clients, 1):
        client_data = history.get(uid, {})
        orders = client_data.get('orders_count', 0)
        message += f"{i}. User {uid}: {total:.2f}€ ({orders} cmd)\n"
    
    message += f"\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    message += f"🏆 TOP 5 PRODUITS (7j)\n"
    
    for i, (product, count) in enumerate(top_products, 1):
        message += f"{i}. {product}: {count} ventes\n"
    
    message += f"\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    message += f"📦 ÉTAT DES STOCKS\n"
    
    total_stock_value = 0
    for name in registry.values():
        product_name = name['name']
        stock = get_stock(product_name)
        if stock and stock > 0:
            price = get_price(product_name, 'FR')
            total_stock_value += stock * price
    
    message += f"Valeur totale: {total_stock_value:.2f}€"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_stats")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== CALLBACKS ADMIN ====================

@error_handler
async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ferme le panel admin"""
    query = update.callback_query
    await query.answer("Panel fermé")
    
    await query.edit_message_text(
        f"{EMOJI_THEME['success']} Panel administrateur fermé."
    )

@error_handler
async def admin_back_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au panel principal"""
    await admin_panel(update, context)

# ==================== VALIDATION COMMANDE - DÉBUT ====================

# États de conversation pour le processus de commande
(COUNTRY_SELECT, SHOPPING, CART_VIEW, DELIVERY_SELECT, ADDRESS_INPUT,
 PAYMENT_SELECT, PROMO_CODE_INPUT, ORDER_CONFIRM) = range(8)

@error_handler
async def validate_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Valide le panier et démarre le processus de commande"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    cart = context.user_data.get('cart', [])
    
    if not cart:
        await query.answer("Votre panier est vide !", show_alert=True)
        return
    
    # Vérifier les horaires
    if not is_within_delivery_hours(user_id):
        horaires_text = get_horaires_text()
        message = f"""{EMOJI_THEME['warning']} FERMÉ

Nous sommes actuellement fermés.

🕐 Horaires : {horaires_text}

Vous pouvez continuer votre commande, elle sera traitée à la réouverture.
"""
        keyboard = [
            [InlineKeyboardButton("✅ Continuer quand même", callback_data="delivery_select")],
            [InlineKeyboardButton("❌ Annuler", callback_data="view_cart")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Passer à la sélection de livraison
    await delivery_select(update, context)

# ==================== SÉLECTION LIVRAISON ====================

@error_handler
async def delivery_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du mode de livraison"""
    query = update.callback_query
    await query.answer()
    
    cart = context.user_data.get('cart', [])
    country = context.user_data.get('country', 'FR')
    
    # Calculer le sous-total
    subtotal = 0
    for item in cart:
        price = get_price_for_quantity(item['produit'], country, item['quantite'])
        subtotal += price * item['quantite']
    
    message = f"""{EMOJI_THEME['delivery']} MODE DE LIVRAISON

{format_cart(cart, context.user_data)}

💰 Sous-total : {subtotal:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

Choisissez votre mode de livraison :
"""
    
    # Si Australie, uniquement livraison postale
    if country == 'AU':
        keyboard = [
            [InlineKeyboardButton("📮 Expédition Postale (30€)", callback_data="delivery_postal")],
            [InlineKeyboardButton("🔙 Retour panier", callback_data="view_cart")]
        ]
        message += f"""\n🇦🇺 AUSTRALIE

Pour l'Australie, seule l'expédition postale internationale est disponible.

📮 Frais : 30€
⏱️ Délai : 15-25 jours ouvrés
📦 Suivi international inclus
"""
    else:
        # Choix normal pour France/Suisse
        keyboard = [
            [InlineKeyboardButton("📮 Postale (10€)", callback_data="delivery_postal")],
            [InlineKeyboardButton("⚡ Express (variable)", callback_data="delivery_express")],
            [InlineKeyboardButton("🤝 Meetup (gratuit)", callback_data="delivery_meetup")],
            [InlineKeyboardButton("🔙 Retour panier", callback_data="view_cart")]
        ]
        
        # Info Express si sous-total < 30€
        if subtotal < 30:
            message += f"\n⚠️ Express nécessite 30€ minimum (actuel: {subtotal:.2f}€)"
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def delivery_mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite la sélection du mode de livraison"""
    query = update.callback_query
    await query.answer()
    
    delivery_type = query.data.replace("delivery_", "")
    
    cart = context.user_data.get('cart', [])
    country = context.user_data.get('country', 'FR')
    
    # Calculer sous-total
    subtotal = 0
    for item in cart:
        price = get_price_for_quantity(item['produit'], country, item['quantite'])
        subtotal += price * item['quantite']
    
    # Vérifier minimum pour Express
    if delivery_type == "express" and subtotal < 30:
        await query.answer(
            f"Express nécessite 30€ minimum (actuel: {subtotal:.2f}€)",
            show_alert=True
        )
        return
    
    context.user_data['delivery_type'] = delivery_type
    
    # Pour postal et express, demander l'adresse
    if delivery_type in ["postal", "express"]:
        delivery_names = {
            "postal": "📮 Postale",
            "express": "⚡ Express"
        }
        
        message = f"""{delivery_names[delivery_type]} LIVRAISON {delivery_type.upper()}

Veuillez entrer votre adresse complète :

📍 Format attendu :
Numéro, Rue
Code postal, Ville

Exemple :
15 Rue de la Paix
75002 Paris

💡 Tapez /cancel pour annuler
"""
        
        keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="delivery_select")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data['awaiting_address'] = True
    
    elif delivery_type == "meetup":
        context.user_data['delivery_address'] = "Meetup - Lieu à définir"
        context.user_data['delivery_fee'] = 0
        await promo_code_prompt(update, context)

# ==================== RÉCEPTION ADRESSE ====================

@error_handler
async def receive_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne l'adresse de livraison"""
    if not context.user_data.get('awaiting_address'):
        return
    
    address = update.message.text.strip()
    
    if len(address) < 10:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Adresse trop courte. Veuillez entrer une adresse complète."
        )
        return
    
    context.user_data['delivery_address'] = address
    context.user_data['awaiting_address'] = False
    
    delivery_type = context.user_data.get('delivery_type')
    cart = context.user_data.get('cart', [])
    country = context.user_data.get('country', 'FR')
    
    # Calculer sous-total
    subtotal = 0
    for item in cart:
        price = get_price_for_quantity(item['produit'], country, item['quantite'])
        subtotal += price * item['quantite']
    
    # Calculer distance et frais
    if delivery_type == "express":
        message_calculating = await update.message.reply_text(
            f"{EMOJI_THEME['delivery']} Calcul de la distance en cours..."
        )
        
        distance = calculate_distance_simple(address)
        delivery_fee = calculate_delivery_fee(delivery_type, distance, subtotal)
        
        context.user_data['distance'] = distance
        context.user_data['delivery_fee'] = delivery_fee
        
        await message_calculating.edit_text(
            f"✅ Distance calculée : {distance:.1f} km\n"
            f"💵 Frais de livraison : {delivery_fee:.2f}€"
        )
    
    elif delivery_type == "postal":
        context.user_data['distance'] = 0
        # Frais selon pays
        if country == 'AU':
            context.user_data['delivery_fee'] = FRAIS_POSTAL_AU
        else:
            context.user_data['delivery_fee'] = FRAIS_POSTAL_EU
    
    # Passer au code promo
    await asyncio.sleep(1)
    await promo_code_prompt_message(update, context)

# ==================== CODE PROMO ====================

async def promo_code_prompt_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande le code promo (via message)"""
    message = f"""🎁 CODE PROMO

Avez-vous un code promo ?

Si oui, entrez-le maintenant.
Sinon, tapez "NON" pour continuer.

💡 Codes disponibles :
- WELCOME10 : -10% première commande
- Et d'autres codes exclusifs !
"""
    
    keyboard = [[InlineKeyboardButton("❌ Pas de code", callback_data="promo_skip")]]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_promo'] = True

async def promo_code_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande le code promo (via callback)"""
    query = update.callback_query
    
    message = f"""🎁 CODE PROMO

Avez-vous un code promo ?

Si oui, entrez-le maintenant.
Sinon, cliquez sur "Pas de code".

💡 Codes disponibles :
- WELCOME10 : -10% première commande
"""
    
    keyboard = [[InlineKeyboardButton("❌ Pas de code", callback_data="promo_skip")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_promo'] = True

@error_handler
async def promo_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passe l'étape du code promo"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['promo_code'] = None
    context.user_data['promo_discount'] = 0
    context.user_data['awaiting_promo'] = False
    
    await payment_select(update, context)

# FIN DU BLOC 7
# ==================== BLOC 8 : SUITE PROCESSUS COMMANDE ET HANDLERS ====================

# ==================== RÉCEPTION CODE PROMO ====================

@error_handler
async def receive_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne et valide le code promo"""
    if not context.user_data.get('awaiting_promo'):
        return
    
    promo_code = update.message.text.strip().upper()
    
    if promo_code == "NON":
        context.user_data['promo_code'] = None
        context.user_data['awaiting_promo'] = False
        await payment_select_message(update, context)
        return
    
    user_id = update.effective_user.id
    cart = context.user_data.get('cart', [])
    country = context.user_data.get('country', 'FR')
    delivery_fee = context.user_data.get('delivery_fee', 0)
    
    # Calculer sous-total
    subtotal = 0
    for item in cart:
        price = get_price_for_quantity(item['produit'], country, item['quantite'])
        subtotal += price * item['quantite']
    
    # Valider le code
    discount, message_status = validate_promo_code(promo_code, subtotal, user_id)
    
    if discount is None:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Code invalide\n\n{message_status}\n\n"
            "Réessayez ou tapez NON pour continuer."
        )
        return
    
    context.user_data['promo_code'] = promo_code
    context.user_data['promo_discount'] = discount
    context.user_data['awaiting_promo'] = False
    
    await update.message.reply_text(
        f"{EMOJI_THEME['success']} Code promo validé !\n\n"
        f"Réduction : -{discount:.2f}€"
    )
    
    await asyncio.sleep(1)
    await payment_select_message(update, context)

# ==================== SÉLECTION PAIEMENT ====================

async def payment_select_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection méthode de paiement (via message)"""
    message = f"""💳 MODE DE PAIEMENT

Choisissez votre mode de paiement :
"""
    
    keyboard = [
        [InlineKeyboardButton("💵 Espèces", callback_data="payment_cash")],
        [InlineKeyboardButton("₿ Crypto", callback_data="payment_crypto")]
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def payment_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection méthode de paiement (via callback)"""
    query = update.callback_query
    
    message = f"""💳 MODE DE PAIEMENT

Choisissez votre mode de paiement :
"""
    
    keyboard = [
        [InlineKeyboardButton("💵 Espèces", callback_data="payment_cash")],
        [InlineKeyboardButton("₿ Crypto", callback_data="payment_crypto")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def payment_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite la sélection du mode de paiement"""
    query = update.callback_query
    await query.answer()
    
    payment_method = query.data.replace("payment_", "")
    
    payment_names = {
        "cash": "💵 Espèces",
        "crypto": "₿ Crypto-monnaie"
    }
    
    context.user_data['payment_method'] = payment_names.get(payment_method, payment_method)
    
    # Afficher le récapitulatif final
    await order_summary(update, context)

# ==================== RÉCAPITULATIF COMMANDE ====================

@error_handler
async def order_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le récapitulatif final de la commande"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    cart = context.user_data.get('cart', [])
    country = context.user_data.get('country', 'FR')
    delivery_type = context.user_data.get('delivery_type')
    delivery_address = context.user_data.get('delivery_address', 'N/A')
    payment_method = context.user_data.get('payment_method', 'N/A')
    promo_code = context.user_data.get('promo_code')
    
    # Calculer le total
    total_info = calculate_total(
        cart=cart,
        country=country,
        delivery_type=delivery_type,
        distance=context.user_data.get('distance', 0),
        promo_code=promo_code,
        user_id=user_id
    )
    
    # Formater le récapitulatif
    order_id = f"CMD{int(datetime.now().timestamp())}"
    
    summary = format_order_summary(
        cart=cart,
        country=country,
        delivery_type=delivery_type,
        delivery_fee=total_info['delivery_fee'],
        promo_discount=total_info['promo_discount'],
        vip_discount=total_info['vip_discount'],
        total=total_info['total'],
        order_id=order_id
    )
    
    message = f"""{summary}

━━━━━━━━━━━━━━━━━━━━━━

📍 Adresse :
{delivery_address}

💳 Paiement :
{payment_method}

━━━━━━━━━━━━━━━━━━━━━━

Confirmez-vous cette commande ?
"""
    
    keyboard = [
        [InlineKeyboardButton("✅ CONFIRMER LA COMMANDE", callback_data="order_confirm")],
        [InlineKeyboardButton("❌ Annuler", callback_data="view_cart")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Stocker pour confirmation
    context.user_data['order_id'] = order_id
    context.user_data['total_info'] = total_info

# ==================== CONFIRMATION COMMANDE ====================

@error_handler
@log_callback
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirme et enregistre la commande"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = user.id
    
    # Récupérer toutes les données
    order_id = context.user_data.get('order_id')
    cart = context.user_data.get('cart', [])
    country = context.user_data.get('country', 'FR')
    delivery_type = context.user_data.get('delivery_type')
    delivery_address = context.user_data.get('delivery_address')
    payment_method = context.user_data.get('payment_method')
    distance = context.user_data.get('distance', 0)
    total_info = context.user_data.get('total_info', {})
    promo_code = context.user_data.get('promo_code')
    
    # Préparer les données de commande
    products_display = ""
    for item in cart:
        products_display += f"• {item['produit']} x {item['quantite']}g\n"
    
    order_data = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'order_id': order_id,
        'user_id': user_id,
        'username': user.username or 'N/A',
        'first_name': user.first_name or 'Utilisateur',
        'language': user.language_code or 'fr',
        'products': format_cart_summary(cart),
        'products_display': products_display,
        'country': country,
        'address': delivery_address,
        'delivery_type': delivery_type,
        'distance_km': distance,
        'payment_method': payment_method,
        'subtotal': total_info['subtotal'],
        'delivery_fee': total_info['delivery_fee'],
        'promo_discount': total_info.get('promo_discount', 0),
        'vip_discount': total_info.get('vip_discount', 0),
        'total': total_info['total'],
        'promo_code': promo_code or '',
        'status': 'En attente',
        'total_info': total_info
    }
    
    # Sauvegarder en CSV
    logger.info(f"💾 Appel save_order_to_csv pour {order_id}...")
    save_result = save_order_to_csv(order_data)
    logger.info(f"💾 Résultat save_order_to_csv: {save_result}")
    
    if not save_result:
        logger.error(f"❌ Échec sauvegarde commande {order_id} dans CSV")
    
    # Mettre à jour l'historique client
    update_client_history(user_id, {'order_id': order_id,
        'total': total_info['total'],
        'products': cart
    })
    
    # Utiliser le code promo
    if promo_code:
        use_promo_code(promo_code)
    
    # Mettre à jour les statistiques
    add_sale(
        amount=total_info['total'],
        country=country,
        products=[item['produit'] for item in cart],
        subtotal=total_info['subtotal'],
        delivery_fee=total_info['delivery_fee'],
        promo_discount=total_info.get('promo_discount', 0),
        vip_discount=total_info.get('vip_discount', 0)
    )
    
    # NOTE: Le stock sera déduit quand l'admin marquera la commande comme livrée
    # (dans admin_validate_order)
    
    # Vérifier si client devient VIP
    stats = get_client_stats(user_id)
    if stats and stats.get('vip_status') and stats.get('orders_count') == 1:
        await notify_admin_vip_client(
            context, 
            user_id, 
            {'first_name': user.first_name, 'username': user.username},
            stats['total_spent']
        )
    
    # Notifier les admins
    await notify_admin_new_order(
        context,
        order_data,
        {
            'first_name': user.first_name,
            'username': user.username or 'N/A'
        }
    )
    
    # Message de confirmation au client
    confirmation_message = f"""{EMOJI_THEME['success']} COMMANDE CONFIRMÉE !

Votre commande #{order_id} a été enregistrée avec succès.

📧 Vous recevrez une confirmation dès que votre commande sera validée par notre équipe.

{EMOJI_THEME['delivery']} Délai de livraison estimé :
"""
    
    if delivery_type == "postal":
        confirmation_message += "48-72 heures"
    elif delivery_type == "express":
        confirmation_message += "30 minutes - 2 heures"
    else:
        confirmation_message += "À convenir"
    
    confirmation_message += f"""

━━━━━━━━━━━━━━━━━━━━━━

💰 Montant total : {total_info['total']:.2f}€
💳 Paiement : {payment_method}

━━━━━━━━━━━━━━━━━━━━━━

{EMOJI_THEME['support']} Merci de votre confiance !
"""
    
    keyboard = [
        [InlineKeyboardButton("🏠 Retour au menu", callback_data="back_to_main")],
        [InlineKeyboardButton(f"{EMOJI_THEME['history']} Mon historique", callback_data="my_history")]
    ]
    
    await query.edit_message_text(
        confirmation_message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Vider le panier et nettoyer tous les états
    context.user_data['cart'] = []
    context.user_data.pop('editing_order_total', None)
    context.user_data.pop('editing_order_delivery', None)
    context.user_data.pop('awaiting_ledger_balance', None)
    context.user_data.pop('awaiting_quantity', None)
    context.user_data.pop('pending_product', None)
    context.user_data.pop('awaiting_address', None)
    context.user_data.pop('awaiting_promo', None)
    
    logger.info(f"✅ Commande confirmée: {order_id} - User: {user_id} - Total: {total_info['total']:.2f}€")

# ==================== VALIDATION ADMIN ====================

@error_handler
async def admin_validate_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Valide une commande et enregistre la vente dans le livre de comptes"""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data: admin_validate_ORDER_ID_USER_ID
    parts = query.data.split('_')
    order_id = parts[2]
    customer_id = int(parts[3])
    
    # Charger les infos de la commande depuis le CSV
    csv_path = DATA_DIR / "orders.csv"
    order_data = None
    orders = []
    
    try:
        if csv_path.exists():
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                orders = list(reader)
                
            for row in orders:
                if row.get('order_id') == order_id:
                    order_data = row
                    # Mettre à jour le statut
                    row['status'] = 'Livrée'
                    row['delivered_date'] = datetime.now().isoformat()
                    break
            
            # Sauvegarder le CSV mis à jour
            if orders and order_data:
                save_orders_csv(csv_path, orders)
    except Exception as e:
        logger.error(f"Erreur lecture/écriture commande: {e}")
    
    # Enregistrer la vente dans le livre de comptes
    if order_data:
        try:
            total = float(order_data.get('total', 0))
            delivery_fee = float(order_data.get('delivery_fee', 0))
            first_name = order_data.get('first_name', 'Client')
            products_str = order_data.get('products', '')
            
            # Déterminer la caisse selon le produit
            is_weed = 'Weed' in products_str or '🍀' in products_str
            
            if is_weed:
                # COMMANDE WEED: Tout → Caisse WEED
                add_ledger_entry(
                    'income',
                    total,
                    f"Vente Weed {order_id} - {first_name}",
                    'Vente',
                    order_id,
                    ledger_type='weed'
                )
                logger.info(f"📒 Vente Weed ajoutée (Caisse WEED): {total:.2f}€")
            else:
                # COMMANDE AUTRES: Split Livraison + Produits
                # 1. Frais livraison → Caisse WEED
                if delivery_fee > 0:
                    add_ledger_entry(
                        'income',
                        delivery_fee,
                        f"Livraison {order_id} - {first_name}",
                        'Livraison',
                        order_id,
                        ledger_type='weed'
                    )
                    logger.info(f"📒 Livraison ajoutée (Caisse WEED): {delivery_fee:.2f}€")
                
                # 2. Produits → Caisse AUTRES
                products_amount = total - delivery_fee
                if products_amount > 0:
                    add_ledger_entry(
                        'income',
                        products_amount,
                        f"Vente {order_id} - {first_name}",
                        'Vente',
                        order_id,
                        ledger_type='autres'
                    )
                    logger.info(f"📒 Vente produits ajoutée (Caisse AUTRES): {products_amount:.2f}€")
            
            # DÉDUIRE LE STOCK (maintenant que la commande est livrée)
            products_str = order_data.get('products', '')
            logger.info(f"📦 DÉDUCTION STOCK START - Commande {order_id}")
            logger.info(f"📦 Raw products: {repr(products_str)}")
            
            if products_str:
                # Parser les produits - formats possibles:
                # "Coco x 10.0g"
                # "Pills x 5 unités"
                # "🍀 Weed x 30.0g\n💊 Pills x 10 unités"
                import re
                
                lines = products_str.strip().split('\n')
                logger.info(f"📦 {len(lines)} produit(s) détecté(s)")
                
                for line in lines:
                    line = line.strip()
                    if not line or 'x' not in line:
                        logger.info(f"📦 Ligne ignorée (pas de 'x'): {repr(line)}")
                        continue
                    
                    logger.info(f"📦 Processing: {repr(line)}")
                    
                    # Supprimer les emojis et nettoyer
                    # Regex: "Nom x Quantité g/unités" (avec ou SANS espaces autour du x)
                    match = re.match(r'[^\w\s]*\s*(.+?)\s*[xX×]\s*([\d.]+)\s*(g|grammes?|unités?|u|pcs?)', line, re.UNICODE | re.IGNORECASE)
                    
                    if match:
                        product_raw = match.group(1).strip()
                        quantity_str = match.group(2)
                        unit = match.group(3)
                        
                        # Nettoyer le nom du produit (enlever emojis résiduels)
                        product_name = re.sub(r'[^\w\s-]', '', product_raw).strip()
                        
                        logger.info(f"✅ Product found: {product_name}")
                        
                        # Convertir quantité
                        try:
                            quantity = float(quantity_str)
                            logger.info(f"📦 Quantity: {quantity}")
                        except ValueError:
                            logger.error(f"❌ Invalid quantity: {quantity_str}")
                            continue
                        
                        # Si le produit n'est pas trouvé directement, essayer de matcher
                        stock_before = get_stock(product_name)
                        
                        if stock_before is None:
                            # Essayer de matcher avec les produits connus
                            known_products = {
                                'Coco': ['Coco', 'coco'],
                                'K': ['K', 'Ketamine', 'ketamine'],
                                'Crystal': ['Crystal', 'crystal', 'MDMA', 'mdma', '4MMC', '4mmc'],
                                'Pills': ['Pills', 'pills', 'Squid-Game', 'Punisher']
                            }
                            
                            for canonical_name, aliases in known_products.items():
                                if product_name in aliases or any(alias.lower() in product_name.lower() for alias in aliases):
                                    product_name = canonical_name
                                    logger.info(f"🔄 Product matched to: {product_name}")
                                    stock_before = get_stock(product_name)
                                    break
                        
                        if stock_before is None:
                            # Dernière tentative: chercher dans PRODUCT_COSTS
                            from collections import OrderedDict
                            PRODUCT_COSTS_KEYS = list(PRODUCT_COSTS.keys())
                            for key in PRODUCT_COSTS_KEYS:
                                if product_name.lower() in key.lower() or key.lower() in product_name.lower():
                                    product_name = key
                                    logger.info(f"🔄 Product matched via PRODUCT_COSTS: {product_name}")
                                    stock_before = get_stock(product_name)
                                    break
                        
                        if stock_before is None:
                            logger.warning(f"⚠️ Produit '{product_name}' introuvable dans stocks.json - skip")
                            continue
                        
                        logger.info(f"📦 Stock BEFORE: {stock_before}")
                        
                        # Déduire le stock
                        result = update_stock(product_name, -quantity)
                        
                        # Vérifier stock APRÈS
                        stock_after = get_stock(product_name)
                        logger.info(f"📦 Stock AFTER: {stock_after}")
                        
                        if stock_after == stock_before:
                            logger.error(f"❌ Stock NON déduit ! {product_name}: {stock_before} → {stock_after}")
                        else:
                            logger.info(f"✅ Stock OK: {product_name} {stock_before} → {stock_after}")
                        
                        # Alertes stock
                        if stock_after is not None:
                            if stock_after == 0:
                                await notify_admin_out_of_stock(context, product_name)
                                # Désactiver le produit
                                available = get_available_products()
                                if product_name in available:
                                    available.remove(product_name)
                                    save_available_products(available)
                                    logger.info(f"🔴 Produit {product_name} désactivé (rupture stock)")
                            elif stock_after <= 20:
                                await notify_admin_low_stock(context, product_name, stock_after)
                    else:
                        logger.warning(f"⚠️ Regex no match: {repr(line)}")
                
                logger.info(f"📦 DÉDUCTION STOCK END - Commande {order_id}")
            else:
                logger.warning(f"⚠️ products_str vide pour commande {order_id}")
            
        except Exception as e:
            logger.error(f"Erreur ajout livre de comptes / déduction stock: {e}")
    else:
        logger.warning(f"⚠️ Commande {order_id} introuvable dans CSV - vente non enregistrée")
    
    # Notifier le client avec résumé complet
    try:
        if order_data:
            products_detail = order_data.get('products_display', order_data.get('products', 'N/A'))
            
            delivery_message = f"""{EMOJI_THEME['success']} COMMANDE LIVRÉE

📋 Commande : #{order_id}

Votre commande a été livrée avec succès !

━━━━━━━━━━━━━━━━━━━━━━

🛍️ PRODUITS LIVRÉS :
{products_detail}

━━━━━━━━━━━━━━━━━━━━━━

💰 RÉCAPITULATIF :
• Sous-total : {order_data.get('subtotal', 'N/A')}€
• Livraison : {order_data.get('delivery_fee', '0')}€
• TOTAL : {order_data.get('total')}€

💳 Paiement : {order_data.get('payment_method', 'N/A')}
📍 Adresse : {order_data.get('address', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━

✨ Merci d'avoir commandé chez nous ! 🙏

Nous espérons vous revoir très bientôt.
N'hésitez pas à nous contacter avec /support si besoin.
"""
            await context.bot.send_message(
                chat_id=customer_id,
                text=delivery_message
            )
        else:
            # Fallback si pas de order_data
            await context.bot.send_message(
                chat_id=customer_id,
                text=f"{EMOJI_THEME['success']} COMMANDE LIVRÉE\n\n"
                     f"Votre commande #{order_id} a été livrée !\n\n"
                     f"Merci d'avoir commandé chez nous ! 🙏"
            )
    except Exception as e:
        logger.error(f"Erreur notification client: {e}")
    
    # Modifier le message admin
    if order_data:
        await query.edit_message_text(
            f"✅ COMMANDE VALIDÉE ET LIVRÉE\n\n"
            f"Commande #{order_id} validée avec succès.\n"
            f"📒 Vente enregistrée dans le livre de comptes.\n"
            f"💰 Montant: {order_data.get('total')}€"
        )
    else:
        await query.edit_message_text(
            f"⚠️ COMMANDE VALIDÉE\n\n"
            f"Commande #{order_id} validée.\n"
            f"⚠️ Erreur: commande introuvable dans CSV.\n"
            f"Vérifiez les logs."
        )
    
    logger.info(f"✅ Commande validée: {order_id} par admin {query.from_user.id}")

# ==================== HANDLERS TEXTE ====================

@error_handler
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal pour tous les messages texte"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    logger.info(f"📩 Message texte: user={user_id}, text={text}, user_data={context.user_data}")
    
    # Vérifier maintenance
    if is_maintenance_mode(user_id):
        await update.message.reply_text(
            f"{EMOJI_THEME['warning']} BOT EN MAINTENANCE\n\n"
            "Le service est temporairement indisponible."
        )
        return
    
    # État: En attente de quantité personnalisée
    if context.user_data.get('awaiting_quantity'):
        logger.info(f"✅ Routing vers receive_custom_quantity")
        await receive_custom_quantity(update, context)
        return
    
    # État: En attente d'adresse
    if context.user_data.get('awaiting_address'):
        await receive_address(update, context)
        return
    
    # État: En attente de code promo
    if context.user_data.get('awaiting_promo'):
        await receive_promo_code(update, context)
        return
    
    # État: En attente de prix (admin)
    if context.user_data.get('awaiting_price'):
        await receive_new_price(update, context)
        return
    
    # État: En attente de stock (admin)
    if context.user_data.get('awaiting_stock'):
        await receive_new_stock(update, context)
        return
    
    # État: En attente de code promo à créer (admin)
    if context.user_data.get('awaiting_promo_creation'):
        await receive_promo_creation_data(update, context)
        return
    
    # État: En attente d'ID admin (admin)
    if context.user_data.get('awaiting_admin_id'):
        logger.info(f"🔍 État détecté: awaiting_admin_id pour user {user_id}")
        await receive_admin_id(update, context)
        return
    
    # État: En attente du nom admin (admin)
    if context.user_data.get('awaiting_admin_name'):
        logger.info(f"🔍 État détecté: awaiting_admin_name pour user {user_id}")
        await receive_admin_name(update, context)
        return
    
    # ===== ÉDITION ADMIN =====
    if context.user_data.get('awaiting_fee'):
        await receive_fee(update, context)
        return
    
    if context.user_data.get('awaiting_stock_edit'):
        await receive_stock_edition(update, context)
        return
    
    if context.user_data.get('awaiting_price_edit'):
        await receive_price(update, context)
        return
    
    if context.user_data.get('awaiting_config'):
        await receive_config(update, context)
        return
    
    # Contact admin
    if context.user_data.get('awaiting_contact_message'):
        await receive_contact_message(update, context)
        return
    
    # État: En attente d'heure pour horaires (admin)
    if context.user_data.get('awaiting_horaire_start') or context.user_data.get('awaiting_horaire_end'):
        await receive_horaire_time(update, context)
        return
    
    # État: En attente montant paye (admin)
    if context.user_data.get('awaiting_pay_amount'):
        await receive_pay_amount(update, context)
        return
    
    # État: En attente description consommable (admin)
    if context.user_data.get('awaiting_expense_description'):
        await receive_expense_description(update, context)
        return
    
    # État: En attente montant consommable (admin)
    if context.user_data.get('awaiting_expense_amount'):
        await receive_expense_amount(update, context)
        return
    
    # État: En attente édition consommable (super-admin)
    if context.user_data.get('editing_expense'):
        await receive_expense_edit(update, context)
        return
    
    # État: En attente nouveau prix de revient (admin)
    if context.user_data.get('awaiting_cost_update'):
        await receive_cost_update(update, context)
        return
    
    # État: En attente nouveau prix commande (admin)
    if context.user_data.get('editing_order_total'):
        await receive_order_total(update, context)
        return
    
    # État: En attente nouveaux frais livraison commande (admin)
    if context.user_data.get('editing_order_delivery'):
        await receive_order_delivery(update, context)
        return
    
    # État: En attente salaire fixe (super-admin)
    if context.user_data.get('setting_fixed_salary'):
        await receive_fixed_salary(update, context)
        return

    # État: En attente ID pour donner VIP
    if context.user_data.get('awaiting_vip_grant'):
        await receive_vip_grant(update, context)
        return

    # État: En attente ID pour révoquer VIP
    if context.user_data.get('awaiting_vip_revoke'):
        await receive_vip_revoke(update, context)
        return
    
    # État: En attente valeur commission (super-admin)
    if context.user_data.get('setting_commission'):
        await receive_commission_value(update, context)
        return
    
    # États: Livre de comptes (super-admin)
    if context.user_data.get('awaiting_ledger_description'):
        await receive_ledger_description(update, context)
        return
    
    if context.user_data.get('awaiting_ledger_amount'):
        await receive_ledger_amount(update, context)
        return
    
    if context.user_data.get('awaiting_ledger_balance'):
        await receive_ledger_balance(update, context)
        return
    
    # Message par défaut
    await update.message.reply_text(
        f"{EMOJI_THEME['info']} Utilisez /start pour accéder au menu principal."
    )

# ==================== COMMANDE /CANCEL ====================

@error_handler
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annule l'opération en cours"""
    # Nettoyer tous les états
    context.user_data.pop('awaiting_quantity', None)
    context.user_data.pop('awaiting_address', None)
    context.user_data.pop('awaiting_promo', None)
    context.user_data.pop('awaiting_price', None)
    context.user_data.pop('awaiting_stock', None)
    context.user_data.pop('awaiting_promo_creation', None)
    context.user_data.pop('awaiting_admin_id', None)
    context.user_data.pop('awaiting_admin_level', None)
    context.user_data.pop('awaiting_admin_name', None)
    context.user_data.pop('awaiting_horaire_start', None)
    context.user_data.pop('awaiting_horaire_end', None)
    context.user_data.pop('awaiting_pay_amount', None)
    context.user_data.pop('expense_category', None)
    context.user_data.pop('awaiting_expense_description', None)
    context.user_data.pop('awaiting_expense_amount', None)
    context.user_data.pop('awaiting_expense_photo', None)
    context.user_data.pop('awaiting_cost_update', None)
    context.user_data.pop('editing_order_total', None)
    context.user_data.pop('editing_order_delivery', None)
    context.user_data.pop('setting_fixed_salary', None)
    context.user_data.pop('awaiting_vip_grant', None)
    context.user_data.pop('awaiting_vip_revoke', None)
    context.user_data.pop('setting_commission', None)
    context.user_data.pop('awaiting_ledger_description', None)
    context.user_data.pop('awaiting_ledger_amount', None)
    context.user_data.pop('awaiting_ledger_balance', None)
    context.user_data.pop('ledger_entry_type', None)
    context.user_data.pop('ledger_category', None)
    context.user_data.pop('ledger_description', None)
    context.user_data.pop('new_admin_id', None)
    context.user_data.pop('new_admin_level', None)
    context.user_data.pop('admin_action', None)
    context.user_data.pop('pending_product', None)
    
    await update.message.reply_text(
        f"{EMOJI_THEME['success']} Opération annulée.\n\n"
        "Utilisez /start pour revenir au menu."
    )
    
    logger.info(f"❌ Opération annulée - User: {update.effective_user.id}")

# ==================== ADMIN: RÉCEPTION PRIX ====================

@error_handler
async def receive_new_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne et met à jour un nouveau prix"""
    if not is_admin(update.effective_user.id):
        return
    
    product_name = context.user_data.get('pending_product')
    country = context.user_data.get('pending_country')
    
    if not product_name or not country:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Erreur: données manquantes."
        )
        return
    
    try:
        new_price = float(update.message.text.strip())
        
        if new_price <= 0:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Le prix doit être supérieur à 0."
            )
            return
        
        if new_price > 1000:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Prix trop élevé (max: 1000€)."
            )
            return
        
        # Mettre à jour le prix
        success = set_price(product_name, country, new_price)
        
        if success:
            context.user_data.pop('awaiting_price', None)
            context.user_data.pop('pending_product', None)
            context.user_data.pop('pending_country', None)
            
            flag = "🇫🇷" if country == "FR" else "🇨🇭"
            
            await update.message.reply_text(
                f"{EMOJI_THEME['success']} PRIX MIS À JOUR\n\n"
                f"{flag} {product_name}\n"
                f"Nouveau prix: {new_price}€/g"
            )
            
            logger.info(f"💰 Prix modifié: {product_name} ({country}) = {new_price}€")
        else:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Erreur lors de la mise à jour."
            )
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Prix invalide. Entrez un nombre."
        )

# ==================== ADMIN: RÉCEPTION ID ADMIN ====================

@error_handler
async def receive_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne l'ID du nouvel admin"""
    logger.info(f"🔍 receive_admin_id appelé - User: {update.effective_user.id}")
    logger.info(f"🔍 user_data: {context.user_data}")
    
    if not is_admin(update.effective_user.id):
        logger.warning(f"⚠️ Non-admin a tenté receive_admin_id: {update.effective_user.id}")
        return
    
    user_id = update.effective_user.id
    admin_action = context.user_data.get('admin_action', 'add')
    
    logger.info(f"🔍 Action admin: {admin_action}")
    
    try:
        new_admin_id = int(update.message.text.strip())
        logger.info(f"✅ ID parsé: {new_admin_id}")
        
        if admin_action == 'add':
            # Vérifier que l'utilisateur n'est pas déjà admin
            if is_admin(new_admin_id):
                await update.message.reply_text(
                    f"{EMOJI_THEME['error']} Cet utilisateur est déjà administrateur."
                )
                logger.info(f"⚠️ Utilisateur déjà admin: {new_admin_id}")
                return
            
            # Demander le niveau d'admin
            context.user_data['new_admin_id'] = new_admin_id
            context.user_data['awaiting_admin_id'] = False
            context.user_data['awaiting_admin_level'] = True
            
            logger.info(f"✅ État mis à jour - awaiting_admin_level: True")
            
            # Anonymiser l'ID dans le message
            anonymous_id = anonymize_id(new_admin_id)
            
            message = f"""👤 NIVEAU D'ADMINISTRATION

ID: {anonymous_id}

Choisissez le niveau d'accès :

👑 SUPER-ADMIN
   • Accès complet
   • Gestion des admins
   • Tous les privilèges

🔐 ADMIN
   • Gestion produits/stocks/prix
   • Gestion commandes
   • Pas de gestion des admins

🛡️ MODÉRATEUR
   • Vue des commandes
   • Support client
   • Pas de modifications
"""
            
            keyboard = [
                [InlineKeyboardButton("👑 Super-admin", callback_data="admin_level_super_admin")],
                [InlineKeyboardButton("🔐 Admin", callback_data="admin_level_admin")],
                [InlineKeyboardButton("🛡️ Modérateur", callback_data="admin_level_moderator")],
                [InlineKeyboardButton("❌ Annuler", callback_data="admin_manage_admins")]
            ]
            
            await update.message.reply_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} ID invalide. L'ID doit être un nombre.\\n\\n"
            "Exemple: 123456789\\n\\n"
            "Demandez à l'utilisateur d'envoyer /myid au bot pour obtenir son ID."
        )

@error_handler
async def admin_level_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite la sélection du niveau d'admin"""
    query = update.callback_query
    await query.answer()
    
    level = query.data.replace("admin_level_", "")
    new_admin_id = context.user_data.get('new_admin_id')
    
    if not new_admin_id:
        await query.answer("Erreur: ID admin non trouvé", show_alert=True)
        return
    
    # Demander le nom
    context.user_data['new_admin_level'] = level
    context.user_data['awaiting_admin_level'] = False
    context.user_data['awaiting_admin_name'] = True
    
    level_names = {
        'super_admin': '👑 Super-admin',
        'admin': '🔐 Admin',
        'moderator': '🛡️ Modérateur'
    }
    
    # Anonymiser l'ID
    anonymous_id = anonymize_id(new_admin_id)
    
    message = f"""✏️ NOM DE L'ADMINISTRATEUR

ID: {anonymous_id}
Niveau: {level_names.get(level, level)}

Entrez le nom/pseudo de cet administrateur :
(Ce nom sera affiché dans la liste des admins)

Exemple: John Doe
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_manage_admins")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def receive_admin_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne le nom du nouvel admin et finalise l'ajout"""
    if not is_admin(update.effective_user.id):
        return
    
    user_id = update.effective_user.id
    new_admin_id = context.user_data.get('new_admin_id')
    level = context.user_data.get('new_admin_level')
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Le nom doit contenir au moins 2 caractères."
        )
        return
    
    if len(name) > 50:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Le nom ne peut pas dépasser 50 caractères."
        )
        return
    
    # Ajouter l'admin
    success = await add_admin(new_admin_id, level, user_id, name)
    
    # Nettoyer user_data
    context.user_data.pop('awaiting_admin_name', None)
    context.user_data.pop('new_admin_id', None)
    context.user_data.pop('new_admin_level', None)
    context.user_data.pop('admin_action', None)
    
    if success:
        level_names = {
            'super_admin': '👑 Super-admin',
            'admin': '🔐 Admin',
            'moderator': '🛡️ Modérateur'
        }
        
        # Anonymiser l'ID dans le message
        anonymous_id = anonymize_id(new_admin_id)
        
        message = f"""{EMOJI_THEME['success']} ADMIN AJOUTÉ

👤 Nom: {name}
🆔 ID: {anonymous_id}
📊 Niveau: {level_names.get(level, level)}

L'utilisateur peut maintenant utiliser /admin pour accéder au panel.
"""
        
        keyboard = [
            [InlineKeyboardButton("📋 Liste admins", callback_data="admin_list_admins")],
            [InlineKeyboardButton("🏠 Retour Panel", callback_data="admin_back_panel")]
        ]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"✅ Admin ajouté: {name} (ID: {new_admin_id}, Niveau: {level}) par {user_id}")
    else:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Erreur lors de l'ajout de l'administrateur."
        )

# ==================== ADMIN: RÉCEPTION STOCK ====================

@error_handler
async def receive_new_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne et met à jour le stock"""
    if not is_admin(update.effective_user.id):
        return
    
    product_name = context.user_data.get('pending_product')
    
    if not product_name:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Erreur: produit non spécifié."
        )
        return
    
    try:
        new_stock = float(update.message.text.strip())
        
        if new_stock < 0:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Le stock ne peut pas être négatif."
            )
            return
        
        if new_stock > 100000:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Stock trop élevé (max: 100000g)."
            )
            return
        
        # Mettre à jour le stock
        success = set_stock(product_name, new_stock)
        
        if success:
            context.user_data.pop('awaiting_stock', None)
            context.user_data.pop('pending_product', None)
            
            # Vérifier si produit était en rupture et le réactiver
            if new_stock > 0:
                available = get_available_products()
                if product_name not in available:
                    available.add(product_name)
                    save_available_products(available)
                    status_msg = "\n✅ Produit réactivé automatiquement"
                else:
                    status_msg = ""
            else:
                status_msg = "\n⚠️ Produit en rupture"
            
            await update.message.reply_text(
                f"{EMOJI_THEME['success']} STOCK MIS À JOUR\n\n"
                f"{product_name}\n"
                f"Nouveau stock: {new_stock}g{status_msg}"
            )
            
            logger.info(f"📦 Stock modifié: {product_name} = {new_stock}g")
        else:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Erreur lors de la mise à jour."
            )
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Stock invalide. Entrez un nombre."
        )

# ==================== ADMIN: CALLBACKS POUR MODIFICATION PRIX/STOCK ====================

@error_handler
async def admin_edit_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Démarre la modification d'un prix"""
    query = update.callback_query
    await query.answer()
    
    country = query.data.replace("admin_edit_prices_", "").upper()
    
    registry = load_product_registry()
    
    message = f"✏️ MODIFIER LES PRIX - {country}\n\nSélectionnez un produit :"
    
    keyboard = []
    for code, product in sorted(registry.items()):
        name = product['name']
        current_price = get_price(name, country)
        
        keyboard.append([
            InlineKeyboardButton(
                f"{name} ({current_price}€/g)",
                callback_data=f"admin_price_edit_{country.lower()}_{code}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data=f"admin_prices_{country.lower()}")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_price_edit_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du produit pour modification prix"""
    query = update.callback_query
    await query.answer()
    
    # Parse: admin_price_edit_fr_coco
    parts = query.data.split('_')
    country = parts[3].upper()
    code = parts[4]
    
    registry = load_product_registry()
    if code not in registry:
        await query.answer("Produit introuvable", show_alert=True)
        return
    
    product_name = registry[code]['name']
    current_price = get_price(product_name, country)
    
    context.user_data['awaiting_price'] = True
    context.user_data['pending_product'] = product_name
    context.user_data['pending_country'] = country
    
    flag = "🇫🇷" if country == "FR" else "🇨🇭"
    
    await query.edit_message_text(
        f"✏️ MODIFIER LE PRIX\n\n"
        f"{flag} {product_name}\n"
        f"Prix actuel: {current_price}€/g\n\n"
        f"Entrez le nouveau prix en €/g :"
    )

@error_handler
async def admin_stock_select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du produit pour ajout stock"""
    query = update.callback_query
    await query.answer()
    
    # Parse: admin_stock_select_coco
    code = query.data.replace("admin_stock_select_", "")
    
    registry = load_product_registry()
    if code not in registry:
        await query.answer("Produit introuvable", show_alert=True)
        return
    
    product_name = registry[code]['name']
    current_stock = get_stock(product_name)
    stock_text = f"{current_stock}g" if current_stock is not None else "Illimité"
    
    context.user_data['awaiting_stock'] = True
    context.user_data['pending_product'] = product_name
    
    await query.edit_message_text(
        f"➕ DÉFINIR LE STOCK\n\n"
        f"Produit: {product_name}\n"
        f"Stock actuel: {stock_text}\n\n"
        f"Entrez le nouveau stock en grammes :"
    )

# FIN DU BLOC 8
# ==================== BLOC 9 : HANDLERS FINAUX, JOBS ET MAIN ====================

# ==================== ADMIN: CRÉATION CODE PROMO ====================

@error_handler
async def receive_promo_creation_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne les données pour créer un code promo"""
    if not is_admin(update.effective_user.id):
        return
    
    step = context.user_data.get('promo_creation_step', 'code')
    
    # ÉTAPE 1: Code promo
    if step == 'code':
        code = update.message.text.strip().upper()
        
        if len(code) < 3:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Le code doit contenir au moins 3 caractères."
            )
            return
        
        if len(code) > 20:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Le code ne peut pas dépasser 20 caractères."
            )
            return
        
        # Vérifier si le code existe déjà
        promo_codes = load_promo_codes()
        if code in promo_codes:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Ce code existe déjà."
            )
            return
        
        context.user_data['new_promo_code'] = code
        context.user_data['promo_creation_step'] = 'type'
        
        keyboard = [
            [InlineKeyboardButton("% Pourcentage", callback_data="promo_type_percentage")],
            [InlineKeyboardButton("€ Montant fixe", callback_data="promo_type_fixed")],
            [InlineKeyboardButton("❌ Annuler", callback_data="admin_promos")]
        ]
        
        await update.message.reply_text(
            f"✅ Code: {code}\n\n"
            "Type de réduction ?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # ÉTAPE 2: Valeur de réduction (après sélection du type)
    elif step == 'value':
        try:
            value = float(update.message.text.strip())
            
            promo_type = context.user_data.get('new_promo_type')
            
            if promo_type == 'percentage' and (value <= 0 or value > 100):
                await update.message.reply_text(
                    f"{EMOJI_THEME['error']} Le pourcentage doit être entre 1 et 100."
                )
                return
            
            if promo_type == 'fixed' and value <= 0:
                await update.message.reply_text(
                    f"{EMOJI_THEME['error']} Le montant doit être supérieur à 0."
                )
                return
            
            context.user_data['new_promo_value'] = value
            context.user_data['promo_creation_step'] = 'max_uses'
            
            await update.message.reply_text(
                f"💯 Nombre d'utilisations maximum\n\n"
                "Entrez le nombre de fois que ce code peut être utilisé.\n"
                "Tapez 0 pour illimité."
            )
        
        except ValueError:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Valeur invalide. Entrez un nombre."
            )
    
    # ÉTAPE 3: Nombre d'utilisations max
    elif step == 'max_uses':
        try:
            max_uses = int(update.message.text.strip())
            
            if max_uses < 0:
                await update.message.reply_text(
                    f"{EMOJI_THEME['error']} Le nombre ne peut pas être négatif."
                )
                return
            
            if max_uses == 0:
                max_uses = 999999  # Illimité
            
            # Créer le code promo
            code = context.user_data.get('new_promo_code')
            promo_type = context.user_data.get('new_promo_type')
            value = context.user_data.get('new_promo_value')
            
            promo_codes = load_promo_codes()
            promo_codes[code] = {
                'type': promo_type,
                'value': value,
                'max_uses': max_uses,
                'used_count': 0,
                'created_at': datetime.now().isoformat(),
                'created_by': update.effective_user.id
            }
            
            save_promo_codes(promo_codes)
            
            # Nettoyer
            context.user_data.pop('awaiting_promo_creation', None)
            context.user_data.pop('promo_creation_step', None)
            context.user_data.pop('new_promo_code', None)
            context.user_data.pop('new_promo_type', None)
            context.user_data.pop('new_promo_value', None)
            
            type_icon = "%" if promo_type == 'percentage' else "€"
            uses_text = "Illimité" if max_uses == 999999 else str(max_uses)
            
            await update.message.reply_text(
                f"{EMOJI_THEME['success']} CODE PROMO CRÉÉ\n\n"
                f"Code: {code}\n"
                f"Réduction: {value}{type_icon}\n"
                f"Utilisations max: {uses_text}\n\n"
                "Le code est immédiatement actif !"
            )
            
            logger.info(f"🎁 Code promo créé: {code} ({value}{type_icon})")
        
        except ValueError:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Nombre invalide."
            )

@error_handler
async def promo_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Type de promo sélectionné"""
    query = update.callback_query
    await query.answer()
    
    promo_type = query.data.replace("promo_type_", "")
    context.user_data['new_promo_type'] = promo_type
    context.user_data['promo_creation_step'] = 'value'
    
    if promo_type == 'percentage':
        prompt = "Entrez le pourcentage de réduction (1-100):"
        example = "Exemple: 10 pour 10%"
    else:
        prompt = "Entrez le montant de réduction en euros:"
        example = "Exemple: 5 pour 5€"
    
    await query.edit_message_text(
        f"💰 VALEUR DE RÉDUCTION\n\n{prompt}\n\n{example}"
    )

@error_handler
async def admin_create_promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Démarre la création d'un code promo"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['awaiting_promo_creation'] = True
    context.user_data['promo_creation_step'] = 'code'
    
    await query.edit_message_text(
        f"🎁 CRÉER UN CODE PROMO\n\n"
        f"Étape 1/4: Entrez le code promo\n\n"
        f"Exemple: NOEL2025, WELCOME10, etc.\n"
        f"(3-20 caractères, lettres et chiffres uniquement)"
    )

@error_handler
async def admin_delete_promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liste les codes promo pour suppression"""
    query = update.callback_query
    await query.answer()
    
    promo_codes = load_promo_codes()
    
    if not promo_codes:
        await query.answer("Aucun code promo à supprimer", show_alert=True)
        return
    
    message = "🗑️ SUPPRIMER UN CODE PROMO\n\nSélectionnez le code à supprimer :"
    
    keyboard = []
    for code in sorted(promo_codes.keys()):
        keyboard.append([
            InlineKeyboardButton(
                f"{code}",
                callback_data=f"admin_delete_promo_confirm_{code}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_promos")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_delete_promo_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirme la suppression d'un code promo"""
    query = update.callback_query
    await query.answer()
    
    code = query.data.replace("admin_delete_promo_confirm_", "")
    
    promo_codes = load_promo_codes()
    
    if code not in promo_codes:
        await query.answer("Code introuvable", show_alert=True)
        return
    
    promo = promo_codes[code]
    type_icon = "%" if promo['type'] == 'percentage' else "€"
    
    message = f"""⚠️ CONFIRMER LA SUPPRESSION

Code: {code}
Réduction: {promo['value']}{type_icon}
Utilisé: {promo.get('used_count', 0)}/{promo.get('max_uses', '∞')}

Voulez-vous vraiment supprimer ce code ?
"""
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirmer", callback_data=f"admin_delete_promo_yes_{code}")],
        [InlineKeyboardButton("❌ Annuler", callback_data="admin_delete_promo")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_delete_promo_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute la suppression du code promo"""
    query = update.callback_query
    await query.answer()
    
    code = query.data.replace("admin_delete_promo_yes_", "")
    
    promo_codes = load_promo_codes()
    
    if code in promo_codes:
        del promo_codes[code]
        save_promo_codes(promo_codes)
        
        await query.edit_message_text(
            f"{EMOJI_THEME['success']} CODE SUPPRIMÉ\n\n"
            f"Le code {code} a été supprimé avec succès."
        )
        
        logger.info(f"🗑️ Code promo supprimé: {code}")
    else:
        await query.answer("Code introuvable", show_alert=True)

# ==================== JOBS PÉRIODIQUES ====================

async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Envoie le rapport hebdomadaire"""
    stats = load_stats()
    weekly_sales = stats.get("weekly", [])
    
    if not weekly_sales:
        return
    
    total = sum(sale["amount"] for sale in weekly_sales)
    total_subtotal = sum(sale.get("subtotal", sale["amount"]) for sale in weekly_sales)
    total_delivery_fees = sum(sale.get("delivery_fee", 0) for sale in weekly_sales)
    total_promo = sum(sale.get("promo_discount", 0) for sale in weekly_sales)
    total_vip = sum(sale.get("vip_discount", 0) for sale in weekly_sales)
    count = len(weekly_sales)
    fr_count = sum(1 for sale in weekly_sales if sale.get("country") == "FR")
    ch_count = sum(1 for sale in weekly_sales if sale.get("country") == "CH")
    
    report = f"""{EMOJI_THEME['stats']} RAPPORT HEBDOMADAIRE

📅 Semaine du {datetime.now().strftime('%d/%m/%Y')}

{EMOJI_THEME['money']} CA TOTAL : {total:.2f}€
🛍️ Ventes : {total_subtotal:.2f}€
{EMOJI_THEME['delivery']} Frais : {total_delivery_fees:.2f}€
{EMOJI_THEME['gift']} Promos : -{total_promo:.2f}€
{EMOJI_THEME['vip']} VIP : -{total_vip:.2f}€

{EMOJI_THEME['product']} Commandes : {count}
🇫🇷 France : {fr_count}
🇨🇭 Suisse : {ch_count}
💵 Panier moyen : {total/count:.2f}€
"""
    
    try:
        for admin_id in get_admin_ids():
            await context.bot.send_message(
                chat_id=admin_id,
                text=report
            )
        stats["weekly"] = []
        stats["last_weekly_report"] = datetime.now().isoformat()
        save_stats(stats)
        logger.info("✅ Rapport hebdomadaire envoyé")
    except Exception as e:
        logger.error(f"Erreur envoi rapport hebdo: {e}")

async def check_salary_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Vérifie si aujourd'hui est un jour de paie et envoie les notifications"""
    try:
        config = load_salary_config()
        now = datetime.now()
        today = now.day  # Jour du mois (1-31)
        weekday = now.isoweekday()  # Jour de la semaine (1=Lundi, 7=Dimanche)
        
        logger.info(f"🔔 Vérification notifications salaire - Jour: {today}, Semaine: {weekday}")
        
        if 'admins' not in config:
            logger.info("⚠️ Aucun admin configuré pour les salaires")
            return
        
        for admin_id, admin_config in config['admins'].items():
            if not admin_config.get('active', False):
                logger.info(f"⏭️ Admin {admin_id} inactif, skip")
                continue
            
            salary_type = admin_config.get('salary_type', 'monthly')
            payment_day = admin_config.get('payment_day', 1)
            fixed_salary = admin_config.get('fixed_salary', 0)
            admin_name = admin_config.get('name', 'Admin')
            
            should_notify = False
            period_label = ""
            
            if salary_type == 'monthly':
                # Vérifier si c'est le jour du mois
                if today == payment_day:
                    should_notify = True
                    period_label = f"du mois de {now.strftime('%B %Y')}"
                    logger.info(f"✅ Jour de paie mensuel pour {admin_name} (jour {payment_day})")
            
            elif salary_type == 'weekly':
                # Vérifier si c'est le jour de la semaine
                if weekday == payment_day:
                    should_notify = True
                    period_label = f"de la semaine du {now.strftime('%d/%m/%Y')}"
                    logger.info(f"✅ Jour de paie hebdomadaire pour {admin_name} (jour {payment_day})")
            
            if should_notify:
                # Charger commissions et dépenses
                commissions_data = load_commissions()
                expenses = load_expenses()
                
                # Calculer commissions
                commissions = 0
                if str(admin_id) in commissions_data:
                    admin_commissions = commissions_data[str(admin_id)]
                    if isinstance(admin_commissions, dict):
                        commissions = sum(admin_commissions.values())
                    elif isinstance(admin_commissions, (int, float)):
                        commissions = admin_commissions
                
                # Calculer remboursements non payés
                unreimbursed = 0
                if str(admin_id) in expenses:
                    for expense in expenses[str(admin_id)]:
                        if not expense.get('reimbursed', False):
                            unreimbursed += expense.get('amount', 0)
                
                total = fixed_salary + commissions + unreimbursed
                
                # Construire le message
                message = f"""💼 NOTIFICATION SALAIRE

👤 {admin_name}

📅 Période: {period_label}

━━━━━━━━━━━━━━━━━━━━━━

💰 DÉTAILS:
• Salaire fixe : {fixed_salary:.2f}€
• Commissions : {commissions:.2f}€
• Remboursements : {unreimbursed:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

💵 TOTAL À PAYER : {total:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

📝 Pour enregistrer le paiement:
/admin → 💼 Gestion Salaires → Payer {admin_name}
"""
                
                try:
                    await context.bot.send_message(
                        chat_id=int(admin_id),
                        text=message
                    )
                    logger.info(f"✅ Notification salaire envoyée à {admin_name} (ID: {admin_id})")
                    
                    # Notifier aussi les super-admins
                    for super_admin_id in get_super_admin_ids():
                        if str(super_admin_id) != admin_id:
                            try:
                                await context.bot.send_message(
                                    chat_id=super_admin_id,
                                    text=f"🔔 Notification salaire envoyée à {admin_name}\nMontant: {total:.2f}€"
                                )
                            except:
                                pass
                
                except Exception as e:
                    logger.error(f"❌ Erreur envoi notification salaire à {admin_id}: {e}")
    
    except Exception as e:
        logger.error(f"❌ Erreur check_salary_notifications: {e}")

@error_handler
async def diag_salaires(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Diagnostic des notifications de salaires - Commande /diag_salaires"""
    user_id = update.effective_user.id
    
    # Vérifier si admin
    if not is_admin(user_id):
        await update.message.reply_text("❌ Accès refusé - Commande admin uniquement")
        return
    
    try:
        config = load_salary_config()
        now = datetime.now()
        today = now.day
        weekday = now.isoweekday()
        
        days_fr = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
        
        message = f"""🔍 DIAGNOSTIC NOTIFICATIONS SALAIRES

📅 Date actuelle: {now.strftime('%d/%m/%Y %H:%M')}
   • Jour du mois: {today}
   • Jour de la semaine: {days_fr[weekday-1]} ({weekday})

━━━━━━━━━━━━━━━━━━━━━━

"""
        
        if 'admins' not in config or not config['admins']:
            message += """❌ PROBLÈME: Aucun admin configuré

📝 Solution:
/admin → 💼 Gestion Salaires → Configurer
"""
            await update.message.reply_text(message)
            return
        
        admins = config['admins']
        message += f"👥 Admins configurés: {len(admins)}\n\n"
        
        active_count = 0
        payday_today = False
        
        for admin_id, admin_config in admins.items():
            name = admin_config.get('name', f'Admin {admin_id}')
            active = admin_config.get('active', False)
            salary_type = admin_config.get('salary_type', 'N/A')
            payment_day = admin_config.get('payment_day', 'N/A')
            fixed_salary = admin_config.get('fixed_salary', 0)
            
            if active:
                active_count += 1
            
            status_emoji = "✅" if active else "❌"
            message += f"{status_emoji} {name}\n"
            message += f"   Type: {salary_type}\n"
            message += f"   Jour: {payment_day}\n"
            message += f"   Salaire: {fixed_salary}€\n"
            
            # Vérifier si aujourd'hui est jour de paie
            is_payday = False
            next_pay = ""
            
            if active:
                if salary_type == 'monthly':
                    if payment_day == today:
                        is_payday = True
                        payday_today = True
                        message += f"   🎉 AUJOURD'HUI = JOUR DE PAIE !\n"
                    else:
                        if payment_day > today:
                            next_pay = f"le {payment_day}/{now.month}"
                        else:
                            next_month = now.month + 1 if now.month < 12 else 1
                            next_pay = f"le {payment_day}/{next_month}"
                        message += f"   📅 Prochain: {next_pay}\n"
                
                elif salary_type == 'weekly':
                    if payment_day == weekday:
                        is_payday = True
                        payday_today = True
                        message += f"   🎉 AUJOURD'HUI = JOUR DE PAIE !\n"
                    else:
                        message += f"   📅 Prochain: chaque {days_fr[payment_day-1]}\n"
            else:
                message += f"   ⚠️  INACTIF - Pas de notification\n"
            
            message += "\n"
        
        message += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Résumé
        if active_count == 0:
            message += """❌ PROBLÈME: Tous les admins sont inactifs

📝 Solution:
/admin → Gestion Salaires → Configurer → Activer
"""
        else:
            message += f"✅ Admins actifs: {active_count}/{len(admins)}\n\n"
        
        # Info sur les notifications
        message += """⏰ HEURE DE NOTIFICATION

Les notifications sont envoyées à 8h00 UTC:
• France hiver: 9h00
• France été: 10h00
• Suisse: 9h00 (hiver) / 10h00 (été)

"""
        
        if payday_today:
            message += """🔔 NOTIFICATION AUJOURD'HUI

Une notification devrait être envoyée à 8h00 UTC.

Vérifiez les logs du bot pour confirmer:
"✅ Notification salaire envoyée à..."

"""
        else:
            message += "⏸️  Aucune notification prévue aujourd'hui\n\n"
        
        # Vérifications
        message += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        message += "✅ CHECKLIST:\n"
        message += f"{'✅' if config.get('admins') else '❌'} salaries.json configuré\n"
        message += f"{'✅' if active_count > 0 else '❌'} Au moins 1 admin actif\n"
        message += f"{'✅' if payday_today else '⏸️ '} Jour de paie aujourd'hui\n"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        logger.error(f"❌ Erreur diag_salaires: {e}")
        await update.message.reply_text(
            f"❌ Erreur lors du diagnostic\n\n"
            f"Détails: {str(e)}"
        )

@error_handler
async def migrate_hardcoded_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Migration des produits hardcodés vers products.json - Commande /migrate"""
    user_id = update.effective_user.id
    
    # Vérifier si super admin
    if not is_super_admin(user_id):
        await update.message.reply_text("❌ Accès refusé - Commande super-admin uniquement")
        return
    
    await update.message.reply_text("🔄 Migration en cours...\n\nCela peut prendre quelques secondes.")
    
    try:
        # Définition de TOUS les produits hardcodés
        HARDCODED_PRODUCTS = [
            {
                "id": "COKE_POWDER",
                "name": {"fr": "❄️ Coco", "en": "❄️ Coke", "es": "❄️ Coca", "de": "❄️ Koks"},
                "price": {"FR": 60.0, "CH": 80.0, "AU": 70.0},
                "quantity": 1000,
                "category": "powder"
            },
            {
                "id": "SQUID_GAME_PILL",
                "name": {"fr": "💊 Squid Game", "en": "💊 Squid Game", "es": "💊 Squid Game", "de": "💊 Squid Game"},
                "price": {"FR": 15.0, "CH": 20.0, "AU": 18.0},
                "quantity": 500,
                "category": "pill"
            },
            {
                "id": "PUNISHER_PILL",
                "name": {"fr": "💊 Punisher", "en": "💊 Punisher", "es": "💊 Punisher", "de": "💊 Punisher"},
                "price": {"FR": 15.0, "CH": 20.0, "AU": 18.0},
                "quantity": 500,
                "category": "pill"
            },
            {
                "id": "HASH",
                "name": {"fr": "🫒 Hash", "en": "🫒 Hash", "es": "🫒 Hash", "de": "🫒 Hash"},
                "price": {"FR": 10.0, "CH": 15.0, "AU": 12.0},
                "quantity": 2000,
                "category": "hash"
            },
            {
                "id": "WEED",
                "name": {"fr": "🍀 Weed", "en": "🍀 Weed", "es": "🍀 Hierba", "de": "🍀 Gras"},
                "price": {"FR": 10.0, "CH": 15.0, "AU": 12.0},
                "quantity": 2000,
                "category": "herb"
            },
            {
                "id": "MDMA_ROCK",
                "name": {"fr": "🪨 MDMA", "en": "🪨 MDMA", "es": "🪨 MDMA", "de": "🪨 MDMA"},
                "price": {"FR": 40.0, "CH": 50.0, "AU": 45.0},
                "quantity": 500,
                "category": "rock"
            },
            {
                "id": "4MMC_ROCK",
                "name": {"fr": "🪨 4MMC", "en": "🪨 4MMC", "es": "🪨 4MMC", "de": "🪨 4MMC"},
                "price": {"FR": 20.0, "CH": 25.0, "AU": 23.0},
                "quantity": 500,
                "category": "rock"
            },
            {
                "id": "KETAMINE",
                "name": {"fr": "🍄 Ketamine", "en": "🍄 Ketamine", "es": "🍄 Ketamina", "de": "🍄 Ketamin"},
                "price": {"FR": 40.0, "CH": 50.0, "AU": 45.0},
                "quantity": 500,
                "category": "powder"
            }
        ]
        
        products = PRODUCTS_DATA.get('products', {})
        
        added = 0
        skipped = 0
        message_lines = ["📦 MIGRATION DES PRODUITS HARDCODÉS\n"]
        
        # Migrer chaque produit
        for product in HARDCODED_PRODUCTS:
            product_id = product['id']
            product_name = product['name']['fr']
            
            if product_id in products:
                message_lines.append(f"⏭️  {product_name} - Déjà existant")
                skipped += 1
                continue
            
            # Ajouter le produit
            products[product_id] = {
                "name": product['name'],
                "price": product['price'],
                "quantity": product['quantity'],
                "available_quantities": [1.0, 2.0, 3.0, 5.0, 10.0, 25.0, 50.0, 100.0],
                "category": product['category'],
                "active": True,
                "created_at": datetime.now().isoformat(),
                "alert_threshold": 50 if product['quantity'] <= 500 else 100
            }
            
            message_lines.append(f"✅ {product_name} - Ajouté")
            added += 1
        
        # Sauvegarder
        PRODUCTS_DATA['products'] = products
        save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)
        
        # Mettre à jour le registry
        registry = load_product_registry()
        for product in HARDCODED_PRODUCTS:
            product_id = product['id']
            if product_id not in registry:
                registry[product_id] = {
                    "name": product['name']['fr'],
                    "category": product['category'],
                    "hash": hashlib.sha256(product['name']['fr'].encode()).hexdigest()[:8]
                }
        save_product_registry(registry)
        
        # Recharger
        reload_products()
        init_product_codes()
        
        # Résumé
        message_lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
        message_lines.append("\n📊 RÉSUMÉ:")
        message_lines.append(f"✅ Ajoutés: {added}")
        message_lines.append(f"⏭️  Déjà existants: {skipped}")
        message_lines.append(f"📦 Total: {len(products)} produits")
        
        if added > 0:
            message_lines.append("\n✅ Migration réussie !")
            message_lines.append("\nVous pouvez maintenant gérer ces produits via /admin")
        else:
            message_lines.append("\nℹ️  Tous les produits étaient déjà migrés")
        
        await update.message.reply_text("\n".join(message_lines))
        
        logger.info(f"✅ Migration produits: {added} ajoutés, {skipped} skippés")
        
    except Exception as e:
        logger.error(f"❌ Erreur migration: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            f"❌ Erreur lors de la migration\n\n"
            f"Détails: {str(e)}\n\n"
            f"Vérifiez les logs du bot pour plus d'infos"
        )

@error_handler
async def test_notif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test des notifications admin - Commande /test_notif"""
    user_id = update.effective_user.id
    
    # Vérifier si admin
    if not is_admin(user_id):
        await update.message.reply_text("❌ Accès refusé - Commande admin uniquement")
        return
    
    await update.message.reply_text("🔍 Test des notifications...\n")
    
    try:
        # Test 1 : Vérifier les admins
        admin_ids = get_admin_ids()
        super_admin_ids = get_super_admin_ids()
        
        message = f"""📊 DIAGNOSTIC NOTIFICATIONS

━━━━━━━━━━━━━━━━━━━━━━

👥 ADMINS CONFIGURÉS

Total admins: {len(admin_ids)}
Super-admins: {len(super_admin_ids)}

Liste des IDs:
"""
        
        for aid in admin_ids:
            is_super = aid in super_admin_ids
            marker = "⭐" if is_super else "👤"
            message += f"{marker} {aid}\n"
        
        if not admin_ids:
            message += "\n❌ PROBLÈME: Aucun admin configuré !\n"
            message += "\nSolution: Ajoutez des admins dans admins.json\n"
        
        message += "\n━━━━━━━━━━━━━━━━━━━━━━\n"
        
        # Test 2 : Tester l'envoi
        if admin_ids:
            message += "\n🧪 TEST D'ENVOI\n\n"
            
            test_message = f"""🧪 MESSAGE DE TEST

Ceci est un test des notifications admin.

✅ Si vous recevez ce message, les notifications fonctionnent !

📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
            
            success_count = 0
            fail_count = 0
            
            for admin_id in admin_ids:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=test_message
                    )
                    success_count += 1
                    logger.info(f"✅ Test notification envoyée à {admin_id}")
                except Exception as e:
                    fail_count += 1
                    logger.error(f"❌ Erreur envoi à {admin_id}: {e}")
            
            message += f"✅ Envoyés: {success_count}/{len(admin_ids)}\n"
            if fail_count > 0:
                message += f"❌ Échecs: {fail_count}\n"
                message += "\nVérifiez les logs pour plus de détails\n"
        
        message += "\n━━━━━━━━━━━━━━━━━━━━━━\n"
        message += "\n📝 CONFIGURATION\n\n"
        
        # Vérifier admins.json
        try:
            admins_data = load_admins()
            message += f"✅ admins.json: {len(admins_data)} entrée(s)\n"
        except:
            message += "❌ admins.json: Erreur de lecture\n"
        
        message += "\n━━━━━━━━━━━━━━━━━━━━━━\n"
        message += "\n💡 TYPES DE NOTIFICATIONS\n\n"
        message += "• Nouvelle connexion utilisateur\n"
        message += "• Nouvelle commande\n"
        message += "• Stock faible\n"
        message += "• Rupture de stock\n"
        message += "• Nouveau client VIP\n"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        logger.error(f"❌ Erreur test_notif: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            f"❌ Erreur lors du test\n\n"
            f"Détails: {str(e)}"
        )

async def schedule_reports(context: ContextTypes.DEFAULT_TYPE):
    """Planifie les rapports automatiques"""
    now = datetime.now()
    stats = load_stats()
    
    if now.weekday() == 6 and now.hour == 23 and now.minute == 59:
        last_weekly = stats.get("last_weekly_report")
        if not last_weekly or (now - datetime.fromisoformat(last_weekly)).days >= 7:
            await send_weekly_report(context)

# ==================== ADMIN: GESTION VIP ====================

@error_handler
async def admin_vip_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu principal gestion VIP"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    message = f"""💎 GESTION VIP

📊 Configuration actuelle:
• Seuil VIP : {VIP_THRESHOLD}€
• Réduction VIP : {VIP_DISCOUNT}%

👥 Gestion des clients VIP:
"""
    
    keyboard = [
        [InlineKeyboardButton("💰 Modifier seuil VIP", callback_data="edit_vip_threshold")],
        [InlineKeyboardButton("💸 Modifier réduction VIP", callback_data="edit_vip_discount")],
        [InlineKeyboardButton("👥 Voir clients VIP", callback_data="vip_list_clients")],
        [InlineKeyboardButton("🎁 Donner statut VIP", callback_data="vip_grant_status")],
        [InlineKeyboardButton("❌ Révoquer statut VIP", callback_data="vip_revoke_status")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def vip_list_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liste tous les clients VIP"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    history = load_client_history()
    
    vip_clients = []
    for user_id, data in history.items():
        if data.get('vip_status', False):
            vip_clients.append({
                'user_id': user_id,
                'name': data.get('first_name', 'Inconnu'),
                'total_spent': data.get('total_spent', 0),
                'orders': data.get('orders_count', 0)
            })
    
    # Trier par dépenses
    vip_clients.sort(key=lambda x: x['total_spent'], reverse=True)
    
    if not vip_clients:
        message = """💎 CLIENTS VIP

Aucun client VIP pour le moment.
"""
    else:
        message = f"""💎 CLIENTS VIP ({len(vip_clients)})

"""
        for i, client in enumerate(vip_clients[:20], 1):
            message += f"""{i}. {client['name']} (ID: {client['user_id']})
   💰 {client['total_spent']:.2f}€ • 📦 {client['orders']} commandes

"""
    
    keyboard = [
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_vip_management")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def vip_grant_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Donner manuellement le statut VIP"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    message = """🎁 DONNER STATUT VIP

Entrez l'ID Telegram du client:

Example: 123456789

Pour trouver l'ID d'un client:
1. /admin → 👥 Clients
2. Chercher le client
3. Copier son ID
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_vip_management")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_vip_grant'] = True

@error_handler
async def receive_vip_grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne l'ID pour donner le statut VIP"""
    if not is_super_admin(update.effective_user.id):
        return
    
    try:
        user_id_to_grant = int(update.message.text.strip())
        
        history = load_client_history()
        
        if str(user_id_to_grant) not in history:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Client introuvable (ID: {user_id_to_grant})\n\n"
                "Vérifiez que ce client a déjà passé au moins une commande."
            )
            context.user_data.pop('awaiting_vip_grant', None)
            return
        
        # Donner le statut VIP
        history[str(user_id_to_grant)]['vip_status'] = True
        history[str(user_id_to_grant)]['vip_granted_manually'] = True
        history[str(user_id_to_grant)]['vip_granted_date'] = datetime.now().isoformat()
        history[str(user_id_to_grant)]['vip_granted_by'] = update.effective_user.id
        
        save_client_history(history)
        
        client_name = history[str(user_id_to_grant)].get('first_name', 'Client')
        total_spent = history[str(user_id_to_grant)].get('total_spent', 0)
        
        # Notifier le client
        try:
            await context.bot.send_message(
                chat_id=user_id_to_grant,
                text=f"""🎉 FÉLICITATIONS !

Vous avez reçu le statut VIP ! 💎

Vous bénéficiez maintenant de {VIP_DISCOUNT}% de réduction sur toutes vos commandes.

Merci de votre fidélité ! 🙏
"""
            )
        except Exception as e:
            logger.error(f"Erreur notification VIP granted: {e}")
        
        await update.message.reply_text(
            f"""{EMOJI_THEME['success']} STATUT VIP ACCORDÉ

👤 Client : {client_name}
🆔 ID : {user_id_to_grant}
💰 Total dépensé : {total_spent:.2f}€

✅ Le client bénéficie maintenant de {VIP_DISCOUNT}% de réduction.
""",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Gestion VIP", callback_data="admin_vip_management")
            ]])
        )
        
        context.user_data.pop('awaiting_vip_grant', None)
        
        logger.info(f"💎 Statut VIP accordé manuellement à {user_id_to_grant} par {update.effective_user.id}")
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} ID invalide. Utilisez un nombre.\n"
            "Exemple : 123456789"
        )

@error_handler
async def vip_revoke_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Révoquer le statut VIP"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    message = """❌ RÉVOQUER STATUT VIP

Entrez l'ID Telegram du client:

Example: 123456789

⚠️ Le client perdra sa réduction VIP sur ses prochaines commandes.
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_vip_management")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_vip_revoke'] = True

@error_handler
async def receive_vip_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne l'ID pour révoquer le statut VIP"""
    if not is_super_admin(update.effective_user.id):
        return
    
    try:
        user_id_to_revoke = int(update.message.text.strip())
        
        history = load_client_history()
        
        if str(user_id_to_revoke) not in history:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Client introuvable (ID: {user_id_to_revoke})"
            )
            context.user_data.pop('awaiting_vip_revoke', None)
            return
        
        if not history[str(user_id_to_revoke)].get('vip_status', False):
            await update.message.reply_text(
                f"{EMOJI_THEME['warning']} Ce client n'est pas VIP."
            )
            context.user_data.pop('awaiting_vip_revoke', None)
            return
        
        # Révoquer le statut VIP
        history[str(user_id_to_revoke)]['vip_status'] = False
        history[str(user_id_to_revoke)]['vip_revoked_date'] = datetime.now().isoformat()
        history[str(user_id_to_revoke)]['vip_revoked_by'] = update.effective_user.id
        
        save_client_history(history)
        
        client_name = history[str(user_id_to_revoke)].get('first_name', 'Client')
        total_spent = history[str(user_id_to_revoke)].get('total_spent', 0)
        
        # Notifier le client
        try:
            await context.bot.send_message(
                chat_id=user_id_to_revoke,
                text=f"""💎 STATUT VIP RÉVOQUÉ

Votre statut VIP a été révoqué.

Vous pouvez le récupérer en atteignant {VIP_THRESHOLD}€ de dépenses.

Merci de votre compréhension.
"""
            )
        except Exception as e:
            logger.error(f"Erreur notification VIP revoked: {e}")
        
        await update.message.reply_text(
            f"""{EMOJI_THEME['success']} STATUT VIP RÉVOQUÉ

👤 Client : {client_name}
🆔 ID : {user_id_to_revoke}
💰 Total dépensé : {total_spent:.2f}€

✅ Le client ne bénéficie plus de la réduction VIP.
""",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Gestion VIP", callback_data="admin_vip_management")
            ]])
        )
        
        context.user_data.pop('awaiting_vip_revoke', None)
        
        logger.info(f"💎 Statut VIP révoqué pour {user_id_to_revoke} par {update.effective_user.id}")
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} ID invalide. Utilisez un nombre.\n"
            "Exemple : 123456789"
        )

@error_handler
async def test_stock_deduction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test de déduction de stock (commande /test_stock)"""
    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("❌ Accès refusé")
        return
    
    product = "Crystal"
    quantity = 1
    
    stock_before = get_stock(product)
    update_stock(product, -quantity)
    stock_after = get_stock(product)
    
    await update.message.reply_text(
        f"📦 TEST DÉDUCTION STOCK\n\n"
        f"Produit: {product}\n"
        f"Quantité: -{quantity}\n\n"
        f"Stock AVANT: {stock_before}\n"
        f"Stock APRÈS: {stock_after}\n\n"
        f"{'✅ OK' if stock_after < stock_before else '❌ ÉCHEC'}"
    )


async def heartbeat_maintenance(context: ContextTypes.DEFAULT_TYPE):
    """Met à jour régulièrement le timestamp pour éviter les faux positifs"""
    update_last_online()

async def check_stocks_job(context: ContextTypes.DEFAULT_TYPE):
    """Job périodique qui vérifie les stocks et envoie des alertes"""
    low_stock_products = get_low_stock_products()
    
    if low_stock_products:
        now = datetime.now()
        if now.hour == 9 and now.minute == 0:
            for item in low_stock_products:
                await notify_admin_low_stock(
                    context,
                    item['product'],
                    item['quantity']
                )

def create_backup(backup_dir: Path = None) -> Optional[Path]:
    """Crée une sauvegarde complète de toutes les données"""
    if backup_dir is None:
        backup_dir = DATA_DIR / "backups"
    
    ensure_dir(backup_dir)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = backup_dir / f"backup_{timestamp}.json"
    
    try:
        backup_data = {
            'timestamp': timestamp,
            'admins': load_admins(),
            'users': load_users(),
            'products': load_product_registry(),
            'prices': load_prices(),
            'stocks': load_stocks(),
            'promo_codes': load_promo_codes(),
            'client_history': load_client_history(),
            'referrals': load_referrals(),
            'stats': load_stats(),
            'bot_version': BOT_VERSION
        }
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Backup créé: {backup_file}")
        return backup_file
    
    except Exception as e:
        logger.error(f"❌ Erreur création backup: {e}")
        return None

# ==================== ADMIN: MENU FINANCES ====================

@error_handler
async def admin_finances(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu principal finances"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    message = """💰 GESTION FINANCIÈRE

Que souhaitez-vous consulter ?
"""
    
    keyboard = []
    
    # Tous les admins peuvent voir les analyses
    keyboard.append([InlineKeyboardButton("📊 Analyse marges", callback_data="admin_finances_margins")])
    keyboard.append([InlineKeyboardButton("🧾 Mes consommables", callback_data="admin_finances_my_expenses")])
    
    # Seul le super-admin voit tout
    if is_super_admin(user_id):
        keyboard.append([InlineKeyboardButton("💳 Payes", callback_data="admin_finances_payroll")])
        keyboard.append([InlineKeyboardButton("🧾 Tous consommables", callback_data="admin_finances_all_expenses")])
        keyboard.append([InlineKeyboardButton("📈 Bilan complet", callback_data="admin_finances_full_report")])
    else:
        keyboard.append([InlineKeyboardButton("💳 Demander paye", callback_data="admin_request_pay")])
        keyboard.append([InlineKeyboardButton("🧾 Ajouter consommable", callback_data="admin_add_expense")])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== ADMIN: SYSTÈME DE PAYES ====================

@error_handler
async def admin_request_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin demande une paye avec suggestion incluant consommables"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    admin_info = get_admin_info(user_id)
    
    if not admin_info:
        await query.answer("Erreur: Admin non trouvé", show_alert=True)
        return
    
    # Charger config salaire
    config = load_salary_config()
    admin_config = config['admins'].get(str(user_id), {})
    fixed_salary = admin_config.get('fixed_salary', 0)
    
    # Charger commissions
    commissions_data = load_commissions()
    commissions = commissions_data.get(str(user_id), {}).get('current_period', {}).get('total_commission', 0)
    
    # Charger consommables non remboursés
    expenses = load_expenses()
    unreimbursed = sum(
        e['amount'] for e in expenses['expenses']
        if e['admin_id'] == str(user_id)
        and e['status'] == 'classée'
        and not e.get('reimbursed', False)
    )
    
    # Total suggéré
    suggested_amount = fixed_salary + commissions + unreimbursed
    
    # Charger le solde actuel
    payroll = load_payroll()
    balance = payroll['balances'].get(str(user_id), 0)
    
    message = f"""💳 DEMANDER UNE PAYE

👤 {admin_info['name']}
💰 Solde actuel : {balance:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

📊 DÉTAIL PÉRIODE ACTUELLE :
• Salaire fixe : {fixed_salary:.2f}€
• Commissions : {commissions:.2f}€
• Remb. consommables : {unreimbursed:.2f}€

💵 MONTANT SUGGÉRÉ : {suggested_amount:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

Entrez le montant souhaité :
Exemple : {suggested_amount:.2f}
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_finances")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_pay_amount'] = True

@error_handler
async def receive_pay_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne le montant de paye demandé"""
    if not is_admin(update.effective_user.id):
        return
    
    user_id = update.effective_user.id
    admin_info = get_admin_info(user_id)
    
    try:
        amount = float(update.message.text.strip())
        
        if amount <= 0:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Le montant doit être positif."
            )
            return
        
        if amount > 10000:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Montant trop élevé (max 10,000€)."
            )
            return
        
        # Enregistrer la demande
        payroll = load_payroll()
        
        payment = {
            "id": f"PAY{int(datetime.now().timestamp())}",
            "admin_id": user_id,
            "admin_name": admin_info['name'],
            "amount": amount,
            "note": "",
            "date": datetime.now().isoformat(),
            "status": "pending"
        }
        
        payroll['payments'].append(payment)
        
        # Mettre à jour le solde (négatif = dette)
        if str(user_id) not in payroll['balances']:
            payroll['balances'][str(user_id)] = 0
        
        payroll['balances'][str(user_id)] -= amount
        
        save_payroll(payroll)
        
        context.user_data.pop('awaiting_pay_amount', None)
        
        # Notifier le super-admin
        notification = f"""💳 NOUVELLE DEMANDE DE PAYE

👤 Admin : {admin_info['name']}
💰 Montant : {amount:.2f}€
📅 Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}

ID : {payment['id']}
"""
        
        keyboard = [
            [InlineKeyboardButton("✅ Approuver", callback_data=f"approve_payment_{payment['id']}")],
            [InlineKeyboardButton("❌ Refuser", callback_data=f"reject_payment_{payment['id']}")]
        ]
        
        try:
            for admin_id in get_admin_ids():
                if is_super_admin(admin_id):
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=notification,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
        except Exception as e:
            logger.error(f"Erreur notification paye: {e}")
        
        # Confirmation à l'admin
        message = f"""{EMOJI_THEME['success']} DEMANDE ENVOYÉE

💰 Montant : {amount:.2f}€
📋 ID : {payment['id']}

Votre demande a été transmise au super-admin.
Vous serez notifié de la décision.
"""
        
        keyboard_conf = [
            [InlineKeyboardButton("💰 Finances", callback_data="admin_finances")],
            [InlineKeyboardButton("🏠 Panel", callback_data="admin_back_panel")]
        ]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard_conf)
        )
        
        logger.info(f"💳 Demande paye: {admin_info['name']} - {amount}€")
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Montant invalide. Utilisez un nombre.\n"
            "Exemple : 250.50"
        )

# ==================== ADMIN: GESTION DES CONSOMMABLES ====================

@error_handler
async def admin_add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajouter un consommable"""
    query = update.callback_query
    await query.answer()
    
    message = """🧾 AJOUTER UN CONSOMMABLE

Sélectionnez la catégorie :
"""
    
    keyboard = [
        [InlineKeyboardButton("📦 Emballage", callback_data="expense_cat_Emballage")],
        [InlineKeyboardButton("🚗 Transport", callback_data="expense_cat_Transport")],
        [InlineKeyboardButton("🔧 Matériel", callback_data="expense_cat_Matériel")],
        [InlineKeyboardButton("📋 Autre", callback_data="expense_cat_Autre")],
        [InlineKeyboardButton("❌ Annuler", callback_data="admin_finances")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def expense_category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catégorie de consommable sélectionnée"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("expense_cat_", "")
    context.user_data['expense_category'] = category
    
    message = f"""📝 DESCRIPTION - {category}

Décrivez l'achat effectué :
Exemple : "Sachets zippés 100 pcs" ou "Essence pour livraison"
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_finances")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_expense_description'] = True

@error_handler
async def receive_expense_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne la description du consommable"""
    if not is_admin(update.effective_user.id):
        return
    
    description = update.message.text.strip()
    
    if len(description) < 3:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Description trop courte (min 3 caractères)."
        )
        return
    
    context.user_data['expense_description'] = description
    context.user_data.pop('awaiting_expense_description', None)
    
    message = f"""💰 MONTANT

Description : {description}

Entrez le montant payé :
Exemple : 25.50
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_finances")]]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_expense_amount'] = True

@error_handler
async def receive_expense_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne le montant du consommable"""
    if not is_admin(update.effective_user.id):
        return
    
    user_id = update.effective_user.id
    admin_info = get_admin_info(user_id)
    
    try:
        amount = float(update.message.text.strip())
        
        if amount <= 0:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Le montant doit être positif."
            )
            return
        
        if amount > 5000:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Montant trop élevé (max 5,000€)."
            )
            return
        
        category = context.user_data.get('expense_category')
        description = context.user_data.get('expense_description')
        
        # Enregistrer le consommable
        expenses = load_expenses()
        
        expense = {
            "id": f"EXP{int(datetime.now().timestamp())}",
            "admin_id": user_id,
            "admin_name": admin_info['name'],
            "amount": amount,
            "category": category,
            "description": description,
            "receipt_photo_id": None,
            "date": datetime.now().isoformat(),
            "status": "pending"
        }
        
        expenses['expenses'].append(expense)
        save_expenses(expenses)
        
        # Nettoyer user_data
        context.user_data.pop('awaiting_expense_amount', None)
        context.user_data.pop('expense_category', None)
        context.user_data.pop('expense_description', None)
        
        # Demander photo justificatif (optionnel)
        message = f"""📸 JUSTIFICATIF (Optionnel)

✅ Consommable enregistré :
📋 {expense['id']}
📦 {category}
💰 {amount:.2f}€
📝 {description}

Envoyez une photo du ticket de caisse
ou tapez /skip pour passer.
"""
        
        await update.message.reply_text(message)
        
        context.user_data['awaiting_expense_photo'] = expense['id']
        
        # Notifier le super-admin
        notification = f"""🧾 NOUVEAU CONSOMMABLE

👤 Admin : {admin_info['name']}
📦 Catégorie : {category}
💰 Montant : {amount:.2f}€
📝 Description : {description}
📅 Date : {datetime.now().strftime('%d/%m/%Y')}

ID : {expense['id']}
"""
        
        keyboard = [
            [InlineKeyboardButton("✅ Approuver", callback_data=f"approve_expense_{expense['id']}")],
            [InlineKeyboardButton("❌ Refuser", callback_data=f"reject_expense_{expense['id']}")]
        ]
        
        try:
            for admin_id in get_admin_ids():
                if is_super_admin(admin_id):
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=notification,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
        except Exception as e:
            logger.error(f"Erreur notification consommable: {e}")
        
        logger.info(f"🧾 Consommable ajouté: {admin_info['name']} - {category} - {amount}€")
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Montant invalide. Utilisez un nombre.\n"
            "Exemple : 25.50"
        )

# ==================== ADMIN: ANALYSE MARGES ====================

@error_handler
async def admin_finances_margins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche l'analyse des marges"""
    query = update.callback_query
    await query.answer("🔄 Actualisation...", show_alert=False)
    
    csv_path = DATA_DIR / "orders.csv"
    
    # Ajouter timestamp pour éviter l'erreur
    import time
    timestamp = int(time.time())
    
    if not csv_path.exists():
        message = f"""📊 ANALYSE DES MARGES

Aucune commande enregistrée.

Actualisé à {datetime.now().strftime('%H:%M:%S')}
"""
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    try:
        import csv as csv_module
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        if not orders:
            message = f"📊 ANALYSE DES MARGES\n\nAucune donnée disponible.\n\nActualisé à {datetime.now().strftime('%H:%M:%S')}"
        else:
            # Calculs revenus
            gross_revenue = sum(float(o.get('total', 0)) for o in orders)
            delivery_fees = sum(float(o.get('delivery_fee', 0)) for o in orders)
            product_revenue = gross_revenue - delivery_fees
            
            # CALCUL RÉEL DES COÛTS avec prix de revient
            total_costs = 0
            products_matched = 0
            products_unmatched = []
            
            logger.info(f"💰 Calcul des marges - {len(orders)} commandes")
            logger.info(f"💰 Prix de revient disponibles: {list(PRODUCT_COSTS.keys())}")
            
            for order in orders:
                # Parser les produits de chaque commande
                products_str = order.get('products', '')
                logger.info(f"🔍 Produits dans commande: '{products_str}'")
                
                # Format attendu : "Coco x10g, K x5g" OU "Coco (10.0g) × 1, K (5.0g) × 2"
                if products_str:
                    import re
                    # Extraire chaque produit
                    for product_entry in products_str.split(','):
                        product_entry = product_entry.strip()
                        logger.info(f"🔍 Analyse: '{product_entry}'")
                        matched = False
                        
                        # Chercher correspondance avec nos produits (insensible à la casse)
                        for product_name in PRODUCT_COSTS.keys():
                            # Comparaison insensible à la casse pour éviter les erreurs de correspondance
                            if product_name.lower() in product_entry.lower():
                                matched = True
                                logger.info(f"✅ Match trouvé: {product_name}")
                                
                                # Extraire quantité - supporter DEUX formats:
                                # Format 1: "Coco x10g" ou "Coco x10.5g"
                                # Format 2: "Coco (10.0g) × 1" ou "Pills (5 unités) × 2"
                                
                                quantity = 0
                                
                                # Essayer format simple "x10g" ou "x10.5g"
                                match_simple = re.search(r'x\s*(\d+(?:\.\d+)?)\s*g', product_entry, re.IGNORECASE)
                                if match_simple:
                                    quantity = float(match_simple.group(1))
                                    logger.info(f"🔍 Quantité (format simple): {quantity}g")
                                else:
                                    # Essayer format avec parenthèses "(10.0g) × 1"
                                    match_weight = re.search(r'\((\d+(?:\.\d+)?)\s*g\)', product_entry)
                                    match_units = re.search(r'\((\d+)\s*unités?\)', product_entry)
                                    match_multiplier = re.search(r'×\s*(\d+)', product_entry)
                                    
                                    multiplier = int(match_multiplier.group(1)) if match_multiplier else 1
                                    
                                    if match_weight:
                                        quantity = float(match_weight.group(1)) * multiplier
                                        logger.info(f"🔍 Quantité (format parenthèses): {quantity}g (base: {match_weight.group(1)}, mult: {multiplier})")
                                    elif match_units:
                                        quantity = int(match_units.group(1)) * multiplier
                                        logger.info(f"🔍 Quantité (format unités): {quantity} unités")
                                
                                if quantity > 0:
                                    unit_cost = PRODUCT_COSTS.get(product_name, 0)
                                    cost = unit_cost * quantity
                                    total_costs += cost
                                    products_matched += 1
                                    logger.info(f"💰 {product_name}: {quantity}g/u × {unit_cost}€ = {cost:.2f}€")
                                else:
                                    logger.warning(f"⚠️ Quantité = 0 pour {product_name} dans '{product_entry}'")
                                    
                                break
                        
                        if not matched and product_entry:
                            products_unmatched.append(product_entry)
                            logger.warning(f"⚠️ Produit non trouvé dans PRODUCT_COSTS: '{product_entry}'")
            
            if products_unmatched:
                logger.warning(f"⚠️ {len(products_unmatched)} produits non matchés (coûts = 0)")
                logger.warning(f"⚠️ Produits non matchés: {products_unmatched[:5]}...")  # Afficher les 5 premiers
            
            logger.info(f"💰 RÉSULTAT: {products_matched} produits matchés, coûts totaux = {total_costs:.2f}€")
            
            gross_margin = product_revenue - total_costs
            margin_rate = (gross_margin / product_revenue * 100) if product_revenue > 0 else 0
            
            # Consommables
            expenses = load_expenses()
            approved_expenses = sum(e['amount'] for e in expenses['expenses'] if e['status'] == 'classée')
            
            # Payes
            payroll = load_payroll()
            paid_payroll = sum(p['amount'] for p in payroll['payments'] if p['status'] == 'paid')
            
            net_profit = gross_margin - approved_expenses - paid_payroll
            
            message = f"""📊 ANALYSE FINANCIÈRE

Ce mois : {len(orders)} commandes

━━━━━━━━━━━━━━━━━━━━━━

💵 CHIFFRE D'AFFAIRES
CA total TTC : {gross_revenue:.2f}€
  • Livraisons : {delivery_fees:.2f}€ ({delivery_fees/gross_revenue*100:.1f}%)
  • Produits : {product_revenue:.2f}€ ({product_revenue/gross_revenue*100:.1f}%)

💰 MARGES (PRIX RÉELS)
Coûts produits : {total_costs:.2f}€
Marge brute : {gross_margin:.2f}€
Taux marge : {margin_rate:.1f}%

📉 DÉPENSES
Consommables : {approved_expenses:.2f}€
Payes : {paid_payroll:.2f}€
Total : {approved_expenses + paid_payroll:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

✨ BÉNÉFICE NET : {net_profit:.2f}€

Actualisé à {datetime.now().strftime('%H:%M:%S')}
"""
        
        keyboard = [
            [InlineKeyboardButton("🔄 Actualiser", callback_data=f"admin_finances_margins_{timestamp}")],
            [InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")]
        ]
        
        try:
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            # Ignorer l'erreur "Message is not modified"
            if "Message is not modified" not in str(e):
                raise
    
    except Exception as e:
        logger.error(f"Erreur analyse marges: {e}")
        await query.edit_message_text(
            f"{EMOJI_THEME['error']} Erreur lors de l'analyse.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")]])
        )
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    except Exception as e:
        logger.error(f"Erreur analyse marges: {e}")
        await query.edit_message_text(
            f"{EMOJI_THEME['error']} Erreur lors de l'analyse.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")]])
        )


# ==================== ADMIN: FONCTIONS FINANCES SUPPLÉMENTAIRES ====================

@error_handler
async def admin_finances_my_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les consommables de l'admin"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    expenses = load_expenses()
    
    my_expenses = [e for e in expenses['expenses'] if e['admin_id'] == user_id]
    
    if not my_expenses:
        message = """🧾 MES CONSOMMABLES

Aucun consommable enregistré.
"""
    else:
        pending = [e for e in my_expenses if e['status'] == 'pending']
        approved = [e for e in my_expenses if e['status'] == 'classée']
        rejected = [e for e in my_expenses if e['status'] == 'rejected']
        
        total_pending = sum(e['amount'] for e in pending)
        total_approved = sum(e['amount'] for e in approved)
        
        message = f"""🧾 MES CONSOMMABLES

⏳ En attente : {len(pending)} ({total_pending:.2f}€)
✅ Approuvés : {len(approved)} ({total_approved:.2f}€)
❌ Refusés : {len(rejected)}

━━━━━━━━━━━━━━━━━━━━━━

DERNIERS CONSOMMABLES :

"""
        
        for expense in my_expenses[-5:]:
            status_emoji = "⏳" if expense['status'] == 'pending' else "✅" if expense['status'] == 'classée' else "❌"
            date = expense['date'][:10]
            message += f"""{status_emoji} {expense['category']}
💰 {expense['amount']:.2f}€
📝 {expense['description']}
📅 {date}

"""
    
    keyboard = [
        [InlineKeyboardButton("🧾 Ajouter", callback_data="admin_add_expense")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_finances_all_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche tous les consommables en attente avec actions (tous admins)"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    expenses = load_expenses()
    
    pending = [e for e in expenses['expenses'] if e['status'] == 'pending']
    
    if not pending:
        message = """🧾 CONSOMMABLES EN ATTENTE

✅ Tous les consommables ont été traités.
"""
        keyboard = [
            [InlineKeyboardButton("📋 Voir les classés", callback_data="admin_expenses_approved")],
            [InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")]
        ]
    else:
        total_pending = sum(e['amount'] for e in pending)
        
        message = f"""🧾 CONSOMMABLES À VALIDER

{len(pending)} consommable(s) - {total_pending:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

"""
        
        keyboard = []
        
        for expense in pending:
            date = expense['date'][:10]
            message += f"""📋 {expense['id']}
👤 {expense['admin_name']}
📦 {expense['category']}
💰 {expense['amount']:.2f}€
📝 {expense['description']}
📅 {date}

"""
            # Ajouter boutons pour ce consommable
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Classer {expense['id'][-6:]}",
                    callback_data=f"approve_expense_{expense['id']}"
                ),
                InlineKeyboardButton(
                    f"❌ Rejeter {expense['id'][-6:]}",
                    callback_data=f"reject_expense_{expense['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("📋 Voir les classés", callback_data="admin_expenses_approved")])
        keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_finances_payroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les payes en attente avec actions (super-admin)"""
    query = update.callback_query
    await query.answer("🔄 Actualisation...", show_alert=False)
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    payroll = load_payroll()
    
    pending = [p for p in payroll['payments'] if p['status'] == 'pending']
    
    # Ajouter timestamp pour forcer le changement
    import time
    timestamp = int(time.time())
    
    if not pending:
        message = f"""💳 PAYES EN ATTENTE

✅ Toutes les payes ont été traitées.

Actualisé à {datetime.now().strftime('%H:%M:%S')}
"""
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")]]
    else:
        total_pending = sum(p['amount'] for p in pending)
        
        message = f"""💳 PAYES À TRAITER

{len(pending)} demande(s) - {total_pending:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

"""
        
        keyboard = []
        
        for payment in pending:
            date = payment['date'][:10]
            message += f"""📋 {payment['id']}
👤 {payment['admin_name']}
💰 {payment['amount']:.2f}€
📅 {date}
📝 {payment.get('note', 'Aucune note')}

"""
            # Ajouter boutons pour cette paye
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Approuver {payment['id'][-6:]}",
                    callback_data=f"approve_payment_{payment['id']}"
                ),
                InlineKeyboardButton(
                    f"❌ Rejeter {payment['id'][-6:]}",
                    callback_data=f"reject_payment_{payment['id']}"
                )
            ])
        
        message += f"\nActualisé à {datetime.now().strftime('%H:%M:%S')}"
        
        keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")])
    
    try:
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        # Si le message est identique, ignorer l'erreur
        if "Message is not modified" not in str(e):
            raise

@error_handler
async def approve_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Classe un consommable (tous admins)"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    expense_id = query.data.replace("approve_expense_", "")
    
    expenses = load_expenses()
    
    # Trouver et classer le consommable
    expense_found = None
    for expense in expenses['expenses']:
        if expense['id'] == expense_id:
            # Vérifier qu'il n'a pas déjà été traité
            if expense['status'] != 'pending':
                await query.answer("Ce consommable a déjà été traité", show_alert=True)
                return
            
            expense['status'] = 'classée'
            expense['validated_date'] = datetime.now().isoformat()
            expense['validated_by'] = query.from_user.id
            expense['validated_by_name'] = ADMINS.get(str(query.from_user.id), {}).get('name', 'Admin')
            expense_found = expense
            break
    
    if not expense_found:
        await query.answer("Consommable introuvable", show_alert=True)
        return
    
    save_expenses(expenses)
    
    # Notifier l'admin qui a fait la demande
    try:
        validator_name = ADMINS.get(str(query.from_user.id), {}).get('name', 'Un admin')
        await context.bot.send_message(
            chat_id=int(expense_found['admin_id']),
            text=f"""✅ CONSOMMABLE CLASSÉ

📋 ID : {expense_id}
📦 Catégorie : {expense_found['category']}
💰 Montant : {expense_found['amount']:.2f}€
📝 Description : {expense_found['description']}

✅ Validé par : {validator_name}

💵 PAIEMENT :
Le montant sera payé avec votre prochain salaire de la semaine.
"""
        )
    except Exception as e:
        logger.error(f"Erreur notification validation: {e}")
    
    # Enregistrer automatiquement dans le livre de comptes
    try:
        admin_name = expense_found.get('admin_name', 'Admin')
        category = expense_found.get('category', 'Consommable')
        description = f"{category} - {admin_name}: {expense_found['description']}"
        
        add_ledger_entry(
            'expense',
            expense_found['amount'],
            description,
            'Consommable',
            expense_id
        )
        logger.info(f"📒 Consommable ajouté au livre de comptes: {expense_found['amount']:.2f}€")
    except Exception as e:
        logger.error(f"Erreur ajout livre de comptes: {e}")
    
    # Éditer le message pour retirer les boutons (éviter double validation)
    try:
        validator_name = ADMINS.get(str(query.from_user.id), {}).get('name', 'Admin')
        await query.edit_message_text(
            f"✅ CONSOMMABLE CLASSÉ PAR {validator_name}\n\n"
            f"📋 ID : {expense_id}\n"
            f"💰 Montant : {expense_found['amount']:.2f}€\n"
            f"📝 {expense_found['description']}\n\n"
            f"✅ Validé et enregistré en comptabilité"
        )
    except Exception as e:
        logger.error(f"Erreur édition message: {e}")
    
    logger.info(f"✅ Consommable classé: {expense_id} par {query.from_user.id}")

@error_handler
async def admin_expenses_approved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les consommables classés avec possibilité de les éditer/supprimer"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    expenses = load_expenses()
    
    # Filtrer les classés (pas rejected)
    approved = [e for e in expenses['expenses'] if e['status'] == 'classée']
    
    # Trier par date décroissante
    approved.sort(key=lambda x: x['date'], reverse=True)
    
    if not approved:
        message = """📋 CONSOMMABLES CLASSÉS

Aucun consommable classé pour le moment.
"""
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_finances_expenses")]]
    else:
        total = sum(e['amount'] for e in approved)
        
        message = f"""📋 CONSOMMABLES CLASSÉS

{len(approved)} consommable(s) - {total:.2f}€

Derniers 10 :

━━━━━━━━━━━━━━━━━━━━━━

"""
        
        keyboard = []
        
        # Afficher les 10 derniers
        for expense in approved[:10]:
            date = expense['date'][:10]
            validator = expense.get('validated_by_name', 'N/A')
            
            message += f"""📋 {expense['id'][-8:]}
👤 {expense['admin_name']}
📦 {expense['category']}
💰 {expense['amount']:.2f}€
📝 {expense['description']}
✅ Validé par: {validator}
📅 {date}

"""
            # Boutons édition/suppression
            keyboard.append([
                InlineKeyboardButton(
                    f"✏️ Éditer {expense['id'][-6:]}",
                    callback_data=f"edit_expense_{expense['id']}"
                ),
                InlineKeyboardButton(
                    f"🗑️ Supprimer {expense['id'][-6:]}",
                    callback_data=f"delete_expense_{expense['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_finances_expenses")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def edit_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Édite un consommable classé"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Seul le super-admin peut éditer", show_alert=True)
        return
    
    expense_id = query.data.replace("edit_expense_", "")
    
    expenses = load_expenses()
    expense = next((e for e in expenses['expenses'] if e['id'] == expense_id), None)
    
    if not expense:
        await query.answer("Consommable introuvable", show_alert=True)
        return
    
    message = f"""✏️ ÉDITER CONSOMMABLE

📋 ID : {expense_id}
👤 Admin : {expense['admin_name']}
📦 Catégorie : {expense['category']}
💰 Montant actuel : {expense['amount']:.2f}€
📝 Description : {expense['description']}

Entrez le nouveau montant (ou 0 pour annuler) :
"""
    
    context.user_data['editing_expense'] = expense_id
    
    await query.edit_message_text(message)

@error_handler
async def receive_expense_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne le nouveau montant du consommable"""
    if not is_super_admin(update.effective_user.id):
        return
    
    expense_id = context.user_data.get('editing_expense')
    
    if not expense_id:
        return
    
    try:
        new_amount = float(update.message.text.strip().replace(',', '.'))
        
        if new_amount == 0:
            await update.message.reply_text("❌ Édition annulée")
            context.user_data.pop('editing_expense', None)
            return
        
        if new_amount < 0:
            await update.message.reply_text("❌ Le montant ne peut pas être négatif")
            return
        
        # Charger expenses
        expenses = load_expenses()
        expense = next((e for e in expenses['expenses'] if e['id'] == expense_id), None)
        
        if not expense:
            await update.message.reply_text("❌ Consommable introuvable")
            context.user_data.pop('editing_expense', None)
            return
        
        old_amount = expense['amount']
        expense['amount'] = new_amount
        expense['edited_date'] = datetime.now().isoformat()
        expense['edited_by'] = update.effective_user.id
        
        save_expenses(expenses)
        
        # Mettre à jour dans le livre de comptes
        ledger = load_ledger()
        for entry in ledger['entries']:
            if entry.get('reference_id') == expense_id:
                # Recalculer le solde
                diff = new_amount - old_amount
                entry['amount'] = new_amount
                
                # Mettre à jour tous les soldes après
                idx = ledger['entries'].index(entry)
                for i in range(idx, len(ledger['entries'])):
                    ledger['entries'][i]['balance_after'] -= diff
                
                ledger['balance'] -= diff
                break
        
        save_ledger(ledger)
        
        await update.message.reply_text(
            f"""✅ CONSOMMABLE MODIFIÉ\n"

📋 ID : {expense_id}
💰 Ancien montant : {old_amount:.2f}€
💰 Nouveau montant : {new_amount:.2f}€

✅ Mise à jour effectuée dans :
• Liste des consommables
• Livre de comptes
"""
        )
        
        context.user_data.pop('editing_expense', None)
        logger.info(f"✏️ Consommable édité: {expense_id} - {old_amount}€ → {new_amount}€")
        
    except ValueError:
        await update.message.reply_text("❌ Montant invalide. Utilisez un nombre.")

@error_handler
async def delete_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Supprime un consommable et son entrée comptable"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Seul le super-admin peut supprimer", show_alert=True)
        return
    
    expense_id = query.data.replace("delete_expense_", "")
    
    expenses = load_expenses()
    expense = next((e for e in expenses['expenses'] if e['id'] == expense_id), None)
    
    if not expense:
        await query.answer("Consommable introuvable", show_alert=True)
        return
    
    # Supprimer du expenses.json
    expenses['expenses'] = [e for e in expenses['expenses'] if e['id'] != expense_id]
    save_expenses(expenses)
    
    # Supprimer du livre de comptes et recalculer les soldes
    ledger = load_ledger()
    removed_amount = 0
    removed_idx = -1
    
    for i, entry in enumerate(ledger['entries']):
        if entry.get('reference_id') == expense_id:
            removed_amount = entry['amount']
            removed_idx = i
            break
    
    if removed_idx >= 0:
        ledger['entries'].pop(removed_idx)
        
        # Recalculer tous les soldes après la suppression
        balance = 0
        for entry in ledger['entries']:
            if entry['type'] == 'income':
                balance += entry['amount']
            else:
                balance -= entry['amount']
            entry['balance_after'] = balance
        
        ledger['balance'] = balance
        save_ledger(ledger)
    
    await query.edit_message_text(
        f"""✅ CONSOMMABLE SUPPRIMÉ\n"

📋 ID : {expense_id}
💰 Montant : {expense['amount']:.2f}€

✅ Suppression effectuée dans :
• Liste des consommables
• Livre de comptes (solde recalculé)
"""
    )
    
    logger.info(f"🗑️ Consommable supprimé: {expense_id} - {expense['amount']}€")

@error_handler
async def reject_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rejette un consommable (tous admins)"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    expense_id = query.data.replace("reject_expense_", "")
    
    expenses = load_expenses()
    
    # Trouver et rejeter le consommable
    expense_found = None
    for expense in expenses['expenses']:
        if expense['id'] == expense_id:
            # Vérifier qu'il n'a pas déjà été traité
            if expense['status'] != 'pending':
                await query.answer("Ce consommable a déjà été traité", show_alert=True)
                return
            
            expense['status'] = 'rejected'
            expense['rejected_date'] = datetime.now().isoformat()
            expense['rejected_by'] = query.from_user.id
            expense['rejected_by_name'] = ADMINS.get(str(query.from_user.id), {}).get('name', 'Admin')
            expense_found = expense
            break
    
    if not expense_found:
        await query.answer("Consommable introuvable", show_alert=True)
        return
    
    save_expenses(expenses)
    
    # Notifier l'admin qui a fait la demande
    try:
        rejector_name = ADMINS.get(str(query.from_user.id), {}).get('name', 'Un admin')
        await context.bot.send_message(
            chat_id=int(expense_found['admin_id']),
            text=f"""❌ CONSOMMABLE REJETÉ

📋 ID : {expense_id}
📦 Catégorie : {expense_found['category']}
💰 Montant : {expense_found['amount']:.2f}€
📝 Description : {expense_found['description']}

Votre demande a été rejetée.
Contactez le super-admin pour plus d'informations.
"""
        )
    except Exception as e:
        logger.error(f"Erreur notification rejet: {e}")
    
    # Retour à la listeawait admin_finances_all_expenses(update, context)
    
    logger.info(f"❌ Consommable rejeté: {expense_id} - {expense_found['amount']}€")

@error_handler
async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approuve une demande de paye et marque consommables comme remboursés"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    payment_id = query.data.replace("approve_payment_", "")
    
    payroll = load_payroll()
    
    # Trouver et approuver la paye
    payment_found = None
    for payment in payroll['payments']:
        if payment['id'] == payment_id:
            payment['status'] = 'paid'
            payment['paid_date'] = datetime.now().isoformat()
            payment['paid_by'] = query.from_user.id
            payment_found = payment
            break
    
    if not payment_found:
        await query.answer("Paye introuvable", show_alert=True)
        return
    
    save_payroll(payroll)
    
    # Marquer les consommables de cet admin comme remboursés
    expenses = load_expenses()
    reimbursed_expenses = []
    reimbursed_total = 0
    
    for expense in expenses['expenses']:
        if (expense['admin_id'] == str(payment_found['admin_id']) 
            and expense['status'] == 'classée' 
            and not expense.get('reimbursed', False)):
            expense['reimbursed'] = True
            expense['reimbursed_date'] = datetime.now().isoformat()
            expense['reimbursed_with_payment'] = payment_id
            reimbursed_expenses.append(expense)
            reimbursed_total += expense['amount']
    
    if reimbursed_expenses:
        save_expenses(expenses)
        logger.info(f"💰 {len(reimbursed_expenses)} consommables marqués remboursés ({reimbursed_total:.2f}€)")
    
    # Calculer détail du paiement
    config = load_salary_config()
    admin_config = config['admins'].get(str(payment_found['admin_id']), {})
    fixed_salary = admin_config.get('fixed_salary', 0)
    
    commissions_data = load_commissions()
    commissions = commissions_data.get(str(payment_found['admin_id']), {}).get('current_period', {}).get('total_commission', 0)
    
    # Notifier l'admin avec détail complet
    try:
        notification = f"""✅ PAYE APPROUVÉE

📋 ID : {payment_id}
💰 Montant total : {payment_found['amount']:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

💵 DÉTAIL :
• Salaire fixe : {fixed_salary:.2f}€
• Commissions : {commissions:.2f}€
• Remb. consommables : {reimbursed_total:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

✅ Votre paiement sera effectué prochainement.
"""
        
        if reimbursed_expenses:
            notification += f"\n🧾 {len(reimbursed_expenses)} consommable(s) remboursé(s)"
        
        await context.bot.send_message(
            chat_id=int(payment_found['admin_id']),
            text=notification
        )
    except Exception as e:
        logger.error(f"Erreur notification approbation paye: {e}")
    
    # Enregistrer automatiquement dans le livre de comptes
    try:
        admin_name = payment_found.get('admin_name', 'Admin')
        description = f"Paiement salaire {admin_name}"
        
        # Ajouter détails si disponibles
        if fixed_salary > 0:
            description += f" (Fixe: {fixed_salary:.2f}€"
        if commissions > 0:
            description += f", Comm: {commissions:.2f}€"
        if reimbursed_total > 0:
            description += f", Remb: {reimbursed_total:.2f}€"
        if fixed_salary > 0 or commissions > 0 or reimbursed_total > 0:
            description += ")"
        
        add_ledger_entry(
            'expense',
            payment_found['amount'],
            description,
            'Salaire',
            payment_id
        )
        logger.info(f"📒 Salaire ajouté au livre de comptes: {payment_found['amount']:.2f}€")
    except Exception as e:
        logger.error(f"Erreur ajout livre de comptes: {e}")
    
    # Retour à la liste
    await admin_finances_payroll(update, context)
    
    logger.info(f"✅ Paye approuvée: {payment_id} - {payment_found['amount']}€")

@error_handler
async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rejette une demande de paye"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    payment_id = query.data.replace("reject_payment_", "")
    
    payroll = load_payroll()
    
    # Trouver et rejeter la paye
    payment_found = None
    for payment in payroll['payments']:
        if payment['id'] == payment_id:
            payment['status'] = 'rejected'
            payment['rejected_date'] = datetime.now().isoformat()
            payment['rejected_by'] = query.from_user.id
            payment_found = payment
            
            # Restaurer le balance (retirer le négatif)
            admin_id = str(payment['admin_id'])
            if admin_id in payroll['balances']:
                payroll['balances'][admin_id] += payment['amount']  # Annuler la déduction
            
            break
    
    if not payment_found:
        await query.answer("Paye introuvable", show_alert=True)
        return
    
    save_payroll(payroll)
    
    # Notifier l'admin qui a fait la demande
    try:
        await context.bot.send_message(
            chat_id=int(payment_found['admin_id']),
            text=f"""❌ PAYE REJETÉE

📋 ID : {payment_id}
💰 Montant : {payment_found['amount']:.2f}€
📅 Date demande : {payment_found['date'][:10]}

Votre demande de paye a été rejetée.
Contactez le super-admin pour plus d'informations.
"""
        )
    except Exception as e:
        logger.error(f"Erreur notification rejet paye: {e}")
    
    # Retour à la liste
    await admin_finances_payroll(update, context)
    
    logger.info(f"❌ Paye rejetée: {payment_id} - {payment_found['amount']}€")

@error_handler
async def admin_finances_full_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bilan financier complet (super-admin)"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        message = """📈 BILAN FINANCIER COMPLET

Aucune donnée disponible.
"""
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    try:
        import csv as csv_module
        import re
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        # Calculs revenus
        gross_revenue = sum(float(o.get('total', 0)) for o in orders)
        delivery_fees = sum(float(o.get('delivery_fee', 0)) for o in orders)
        product_revenue = gross_revenue - delivery_fees
        
        # CALCUL RÉEL DES COÛTS avec prix de revient
        total_costs = 0
        
        for order in orders:
            # Parser les produits de chaque commande
            products_str = order.get('products', '')
            
            if products_str:
                # Extraire chaque produit
                for product_entry in products_str.split(','):
                    product_entry = product_entry.strip()
                    
                    # Chercher correspondance avec nos produits (insensible à la casse)
                    for product_name in PRODUCT_COSTS.keys():
                        if product_name.lower() in product_entry.lower():
                            # Extraire quantité - supporter DEUX formats:
                            # Format 1: "Coco x10g" ou "Coco x10.5g"
                            # Format 2: "Coco (10.0g) × 1" ou "Pills (5 unités) × 2"
                            
                            quantity = 0
                            
                            # Essayer format simple "x10g" ou "x10.5g"
                            match_simple = re.search(r'x\s*(\d+(?:\.\d+)?)\s*g', product_entry, re.IGNORECASE)
                            if match_simple:
                                quantity = float(match_simple.group(1))
                            else:
                                # Essayer format avec parenthèses
                                match_weight = re.search(r'\((\d+(?:\.\d+)?)\s*g\)', product_entry)
                                match_units = re.search(r'\((\d+)\s*unités?\)', product_entry)
                                match_multiplier = re.search(r'×\s*(\d+)', product_entry)
                                
                                multiplier = int(match_multiplier.group(1)) if match_multiplier else 1
                                
                                if match_weight:
                                    quantity = float(match_weight.group(1)) * multiplier
                                elif match_units:
                                    quantity = int(match_units.group(1)) * multiplier
                            
                            if quantity > 0:
                                cost = PRODUCT_COSTS.get(product_name, 0) * quantity
                                total_costs += cost
                                
                            break
        
        gross_margin = product_revenue - total_costs
        
        # Dépenses
        expenses = load_expenses()
        approved_expenses = sum(e['amount'] for e in expenses['expenses'] if e['status'] == 'classée')
        
        # Payes
        payroll = load_payroll()
        paid_payroll = sum(p['amount'] for p in payroll['payments'] if p['status'] == 'paid')
        
        # Bénéfice net
        net_profit = gross_margin - approved_expenses - paid_payroll
        
        # Timestamp pour éviter erreur
        import time
        timestamp = int(time.time())
        
        message = f"""📈 BILAN FINANCIER COMPLET

Période : Ce mois
Commandes : {len(orders)}

━━━━━━━━━━━━━━━━━━━━━━

💵 REVENUS
CA total TTC : {gross_revenue:.2f}€
• Livraisons : {delivery_fees:.2f}€
• Produits : {product_revenue:.2f}€

💰 MARGES (PRIX RÉELS)
Coûts produits : {total_costs:.2f}€
Marge brute : {gross_margin:.2f}€
Taux : {(gross_margin/product_revenue*100):.1f}%

📉 DÉPENSES
Consommables : {approved_expenses:.2f}€
Payes : {paid_payroll:.2f}€
Total : {approved_expenses + paid_payroll:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

✨ BÉNÉFICE NET : {net_profit:.2f}€

💡 Taux profit : {(net_profit/gross_revenue*100):.1f}%

Actualisé à {datetime.now().strftime('%H:%M:%S')}
"""
        
        keyboard = [
            [InlineKeyboardButton("🔄 Actualiser", callback_data=f"admin_finances_full_report_{timestamp}")],
            [InlineKeyboardButton("💰 Finances", callback_data="admin_finances")],
            [InlineKeyboardButton("🏠 Panel", callback_data="admin_back_panel")]
        ]
        
        try:
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                raise
    
    except Exception as e:
        logger.error(f"Erreur bilan complet: {e}")
        await query.edit_message_text(
            f"{EMOJI_THEME['error']} Erreur lors de l'analyse.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")]])
        )

# ==================== ADMIN: GESTION PRIX DE REVIENT ====================

@error_handler
async def admin_costs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de gestion des prix de revient"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    # Récupérer TOUS les produits (du registre)
    all_products = load_product_registry()
    
    if not all_products:
        await query.edit_message_text(
            "❌ Aucun produit trouvé dans le registre.\n\n"
            "Activez d'abord des produits depuis le menu Admin.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")
            ]])
        )
        return
    
    message = """💵 GESTION PRIX DE REVIENT

Prix d'achat actuels :

"""
    
    # Afficher les prix pour tous les produits
    for product_name in all_products.keys():
        cost = PRODUCT_COSTS.get(product_name, 0)
        
        # Déterminer l'unité
        if product_name in PRODUCT_WEIGHTS:
            unit = PRODUCT_WEIGHTS[product_name].get('unit', 'g')
            if unit == 'unités':
                unit_str = "/unité"
            else:
                unit_str = "/g"
        else:
            unit_str = "/g"
        
        if cost > 0:
            message += f"• {product_name}: {cost:.2f}€{unit_str}\n"
        else:
            message += f"• {product_name}: ❌ Non défini\n"
    
    message += """

Sélectionnez un produit à modifier :
"""
    
    keyboard = []
    
    # Un bouton par produit (TOUS les produits)
    for product_name in all_products.keys():
        cost = PRODUCT_COSTS.get(product_name, 0)
        if cost > 0:
            label = f"✏️ {product_name} ({cost:.2f}€)"
        else:
            label = f"➕ {product_name} (définir)"
        
        keyboard.append([InlineKeyboardButton(
            label,
            callback_data=f"admin_cost_edit_{product_name}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_cost_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Éditer le prix de revient d'un produit"""
    query = update.callback_query
    await query.answer()
    
    # Extraire le nom du produit
    product_name = query.data.replace("admin_cost_edit_", "")
    
    current_cost = PRODUCT_COSTS.get(product_name, 0)
    
    # Déterminer l'unité
    if product_name in PRODUCT_WEIGHTS:
        unit = PRODUCT_WEIGHTS[product_name].get('unit', 'g')
        if unit == 'unités':
            unit_str = "par unité"
        else:
            unit_str = "par gramme"
    else:
        unit_str = "par gramme"
    
    if current_cost > 0:
        title = "✏️ MODIFIER PRIX DE REVIENT"
        status = f"💰 Prix actuel : {current_cost:.2f}€ {unit_str}"
    else:
        title = "➕ DÉFINIR PRIX DE REVIENT"
        status = "❌ Prix non défini (nouveau produit)"
    
    message = f"""{title}

📦 Produit : {product_name}
{status}

Entrez le nouveau prix de revient :
Exemple : 42.50
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_costs")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Nettoyer TOUS les autres états pour éviter les conflits
    context.user_data.pop('awaiting_config', None)
    context.user_data.pop('awaiting_stock_edit', None)
    context.user_data.pop('awaiting_price_edit', None)
    context.user_data.pop('awaiting_fee', None)
    context.user_data.pop('editing_expense', None)
    context.user_data.pop('awaiting_expense_amount', None)
    context.user_data.pop('awaiting_expense_description', None)
    context.user_data.pop('editing_order_total', None)
    context.user_data.pop('editing_order_delivery', None)
    
    # Sauvegarder le produit en cours d'édition
    context.user_data['awaiting_cost_update'] = product_name
    logger.info(f"🔍 État défini: awaiting_cost_update = {product_name}")
    logger.info(f"🔍 États actifs: {[k for k, v in context.user_data.items() if k.startswith('awaiting') or k.startswith('editing')]}")

@error_handler
async def receive_cost_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne le nouveau prix de revient"""
    logger.info(f"🔍 DEBUG receive_cost_update appelé")
    
    if not is_admin(update.effective_user.id):
        logger.info(f"🔍 DEBUG User {update.effective_user.id} n'est pas admin")
        return
    
    product_name = context.user_data.get('awaiting_cost_update')
    logger.info(f"🔍 DEBUG product_name = {product_name}")
    
    if not product_name:
        logger.info(f"🔍 DEBUG product_name est None ou vide")
        return
    
    input_text = update.message.text.strip()
    logger.info(f"🔍 DEBUG input_text = '{input_text}'")
    
    try:
        new_cost = float(input_text)
        logger.info(f"🔍 DEBUG new_cost converti = {new_cost}")
        
        if new_cost < 0:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Le prix ne peut pas être négatif."
            )
            return
        
        if new_cost > 10000:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Prix trop élevé (max 10,000€)."
            )
            return
        
        # Sauvegarder dans un fichier JSON
        costs_file = DATA_DIR / "product_costs.json"
        
        # Charger les coûts existants
        if costs_file.exists():
            with open(costs_file, 'r', encoding='utf-8') as f:
                saved_costs = json.load(f)
            logger.info(f"📂 Fichier product_costs.json trouvé - {len(saved_costs)} prix existants")
        else:
            saved_costs = dict(PRODUCT_COSTS)
            logger.info(f"📂 Création nouveau fichier product_costs.json")
        
        old_cost = saved_costs.get(product_name, PRODUCT_COSTS.get(product_name, 0))
        saved_costs[product_name] = new_cost
        
        # Sauvegarder
        logger.info(f"💾 Sauvegarde de {product_name}: {new_cost}€ dans {costs_file}")
        with open(costs_file, 'w', encoding='utf-8') as f:
            json.dump(saved_costs, f, indent=2, ensure_ascii=False)
        
        # Vérifier que la sauvegarde a réussi
        if costs_file.exists():
            file_size = costs_file.stat().st_size
            logger.info(f"✅ Fichier sauvegardé avec succès ({file_size} bytes)")
            
            # Re-lire pour vérifier
            with open(costs_file, 'r', encoding='utf-8') as f:
                verify_costs = json.load(f)
            if product_name in verify_costs and verify_costs[product_name] == new_cost:
                logger.info(f"✅ Vérification OK: {product_name} = {new_cost}€")
            else:
                logger.error(f"❌ ERREUR: Le prix n'a pas été sauvegardé correctement!")
        else:
            logger.error(f"❌ ERREUR: Le fichier n'existe pas après sauvegarde!")
        
        # Mettre à jour PRODUCT_COSTS en mémoire
        PRODUCT_COSTS[product_name] = new_cost
        logger.info(f"💾 PRODUCT_COSTS mis à jour en mémoire")
        
        context.user_data.pop('awaiting_cost_update', None)
        
        # Déterminer l'unité
        if product_name in PRODUCT_WEIGHTS:
            unit = PRODUCT_WEIGHTS[product_name].get('unit', 'g')
            if unit == 'unités':
                unit_str = "/unité"
            else:
                unit_str = "/g"
        else:
            unit_str = "/g"
        
        message = f"""{EMOJI_THEME['success']} PRIX MIS À JOUR

📦 Produit : {product_name}

Ancien prix : {old_cost:.2f}€{unit_str}
Nouveau prix : {new_cost:.2f}€{unit_str}

Les marges seront calculées avec ce nouveau prix à partir de maintenant.
"""
        
        keyboard = [
            [InlineKeyboardButton("💵 Prix de revient", callback_data="admin_costs")],
            [InlineKeyboardButton("🏠 Panel", callback_data="admin_back_panel")]
        ]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"💵 Prix de revient modifié: {product_name} - {old_cost:.2f}€ → {new_cost:.2f}€")
    
    except ValueError as e:
        logger.error(f"🔍 DEBUG ValueError: {e}")
        logger.error(f"🔍 DEBUG input_text qui a causé l'erreur: '{input_text}'")
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Prix invalide. Utilisez un nombre.\n"
            "Exemple : 42.50"
        )
    except Exception as e:
        logger.error(f"🔍 DEBUG Exception inattendue: {type(e).__name__}: {e}")
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Erreur: {str(e)}"
        )

def load_product_costs():
    """Charge les prix de revient depuis le fichier JSON"""
    global PRODUCT_COSTS
    
    costs_file = DATA_DIR / "product_costs.json"
    
    if costs_file.exists():
        try:
            with open(costs_file, 'r', encoding='utf-8') as f:
                saved_costs = json.load(f)
            
            # Mettre à jour PRODUCT_COSTS avec TOUS les prix sauvegardés
            # Pas seulement ceux qui existent déjà dans PRODUCT_COSTS
            for product_name, cost in saved_costs.items():
                PRODUCT_COSTS[product_name] = cost
            
            logger.info(f"💵 Prix de revient chargés: {len(saved_costs)} produits")
            logger.info(f"📦 Produits avec prix: {list(saved_costs.keys())}")
            return True
        except Exception as e:
            logger.error(f"Erreur chargement prix: {e}")
            return False
    else:
        logger.info("ℹ️ Aucun fichier product_costs.json trouvé - utilisation des prix par défaut")
    return False

# ==================== ADMIN: GESTION SALAIRES ====================

@error_handler
async def admin_salary_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu configuration salaires (super-admin uniquement)"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    config = load_salary_config()
    
    message = """💼 GESTION DES SALAIRES

Configurez les salaires de vos admins :
• Salaire fixe (hebdo/mensuel)
• Commissions sur ventes
• Fréquence de paiement
• Calcul automatique

Sélectionnez un admin :
"""
    
    keyboard = []
    
    for admin_id, admin_data in ADMINS.items():
        admin_config = config['admins'].get(str(admin_id), {})
        status = "✅" if admin_config.get('active', False) else "❌"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {admin_data['name']}",
                callback_data=f"salary_admin_{admin_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("📊 Vue d'ensemble", callback_data="salary_overview")])
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def salary_admin_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche configuration salaire d'un admin"""
    query = update.callback_query
    await query.answer()
    
    admin_id = int(query.data.replace("salary_admin_", ""))
    
    config = load_salary_config()
    
    # Récupérer le nom de l'admin
    admin_name = "Admin"
    if str(admin_id) in ADMINS:
        admin_name = ADMINS[str(admin_id)]['name']
    
    admin_config = config['admins'].get(str(admin_id), {
        "name": admin_name,
        "fixed_salary": 0,
        "salary_type": "monthly",
        "commission_type": "none",
        "commission_value": 0,
        "payment_day": 1,
        "active": False
    })
    
    # Info salaire
    if admin_config['salary_type'] == 'monthly':
        salary_info = f"{admin_config['fixed_salary']:.2f}€/mois"
    else:
        salary_info = f"{admin_config['fixed_salary']:.2f}€/semaine"
    
    # Info commission
    commission_value = admin_config.get('commission_value', 0)
    if commission_value > 0:
        commission_info = f"{commission_value:.2f}€ par commande"
    else:
        commission_info = "Aucune"
    
    # Fréquence
    if admin_config['salary_type'] == 'monthly':
        freq_info = f"Mensuel (le {admin_config['payment_day']} du mois)"
    else:
        days = {1: "Lundi", 2: "Mardi", 3: "Mercredi", 4: "Jeudi", 5: "Vendredi", 6: "Samedi", 7: "Dimanche"}
        freq_info = f"Hebdomadaire (chaque {days.get(admin_config['payment_day'], 'Lundi')})"
    
    # Commissions actuelles
    commissions_data = load_commissions()
    current_commissions = commissions_data.get(str(admin_id), {}).get('current_period', {}).get('total_commission', 0)
    
    # Consommables approuvés non remboursés
    expenses = load_expenses()
    approved_expenses = sum(
        e['amount'] for e in expenses['expenses']
        if e['admin_id'] == str(admin_id) 
        and e['status'] == 'classée' 
        and not e.get('reimbursed', False)
    )
    
    # Total à verser
    total_to_pay = admin_config['fixed_salary'] + current_commissions + approved_expenses
    
    message = f"""💼 CONFIGURATION SALAIRE

👤 Admin : {admin_config['name']}

💰 SALAIRE FIXE
{salary_info}

💸 COMMISSION
{commission_info}

📅 PAIEMENT
{freq_info}

━━━━━━━━━━━━━━━━━━━━━━

📊 PÉRIODE ACTUELLE :
• Commissions : {current_commissions:.2f}€
• Remb. consommables : {approved_expenses:.2f}€

💵 TOTAL À VERSER : {total_to_pay:.2f}€

🔔 Statut : {'Actif ✅' if admin_config['active'] else 'Inactif ❌'}

Modifier :
"""
    
    keyboard = [
        [
            InlineKeyboardButton("💰 Salaire fixe", callback_data=f"set_fixed_{admin_id}"),
            InlineKeyboardButton("💸 Commission", callback_data=f"set_commission_{admin_id}")
        ],
        [
            InlineKeyboardButton("📅 Fréquence", callback_data=f"set_frequency_{admin_id}"),
            InlineKeyboardButton("📆 Jour", callback_data=f"set_day_{admin_id}")
        ],
        [
            InlineKeyboardButton(
                "✅ Activer" if not admin_config['active'] else "❌ Désactiver",
                callback_data=f"toggle_salary_{admin_id}"
            )
        ],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_salary_config")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def set_fixed_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définir salaire fixe"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.data.replace("set_fixed_", "")
    
    message = f"""💰 SALAIRE FIXE

Entrez le montant du salaire fixe :

Exemple : 1500
(pour 1500€/mois ou 1500€/semaine selon la fréquence)

Entrez 0 pour aucun salaire fixe.
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data=f"salary_admin_{admin_id}")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['setting_fixed_salary'] = admin_id

@error_handler
async def receive_fixed_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne montant salaire fixe"""
    if not is_super_admin(update.effective_user.id):
        return
    
    admin_id = context.user_data.get('setting_fixed_salary')
    if not admin_id:
        return
    
    try:
        amount = float(update.message.text.strip())
        
        if amount < 0:
            await update.message.reply_text(f"{EMOJI_THEME['error']} Le montant ne peut pas être négatif.")
            return
        
        if amount > 100000:
            await update.message.reply_text(f"{EMOJI_THEME['error']} Montant trop élevé (max 100,000€).")
            return
        
        # Mettre à jour config
        config = load_salary_config()
        
        if str(admin_id) not in config['admins']:
            admin_name = ADMINS.get(str(admin_id), {}).get('name', 'Admin')
            config['admins'][str(admin_id)] = {
                "name": admin_name,
                "fixed_salary": 0,
                "salary_type": "monthly",
                "commission_type": "none",
                "commission_value": 0,
                "payment_day": 1,
                "active": False
            }
        
        config['admins'][str(admin_id)]['fixed_salary'] = amount
        save_salary_config(config)
        
        context.user_data.pop('setting_fixed_salary', None)
        
        message = f"""{EMOJI_THEME['success']} SALAIRE FIXE DÉFINI

Montant : {amount:.2f}€

Configurez maintenant la fréquence (mensuel/hebdomadaire).
"""
        
        keyboard = [[InlineKeyboardButton("📋 Voir configuration", callback_data=f"salary_admin_{admin_id}")]]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"💰 Salaire fixe défini: Admin {admin_id} - {amount:.2f}€")
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Montant invalide. Utilisez un nombre.\n"
            "Exemple : 1500"
        )

@error_handler
async def set_commission_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définir commission (montant fixe par commande)"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.data.replace("set_commission_", "")
    
    message = """💸 COMMISSION PAR COMMANDE

Entrez le montant FIXE que cet admin recevra 
pour chaque commande qu'il valide :

Exemples :
• 5 → 5€ par commande
• 10 → 10€ par commande
• 0 → Désactiver les commissions

Le montant est en EUROS (pas en %).
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data=f"salary_admin_{admin_id}")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Sauvegarder dans user_data
    context.user_data['setting_commission'] = {
        'admin_id': admin_id,
        'type': 'fixed'  # TOUJOURS fixe (pas de pourcentage)
    }

@error_handler
async def set_commission_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définir valeur commission"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split("_")
    comm_type = data_parts[1]  # percent, fixed, none
    admin_id = data_parts[2]
    
    if comm_type == "none":
        # Pas de commission
        config = load_salary_config()
        
        if str(admin_id) not in config['admins']:
            admin_name = ADMINS.get(str(admin_id), {}).get('name', 'Admin')
            config['admins'][str(admin_id)] = {
                "name": admin_name,
                "fixed_salary": 0,
                "salary_type": "monthly",
                "commission_type": "none",
                "commission_value": 0,
                "payment_day": 1,
                "active": False
            }
        
        config['admins'][str(admin_id)]['commission_type'] = 'none'
        config['admins'][str(admin_id)]['commission_value'] = 0
        save_salary_config(config)
        
        await query.edit_message_text(
            f"{EMOJI_THEME['success']} Commission désactivée",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Voir configuration", callback_data=f"salary_admin_{admin_id}")
            ]])
        )
        return
    
    # Demander la valeur
    if comm_type == "percent":
        message = """💸 COMMISSION EN POURCENTAGE

Entrez le pourcentage par commande validée :

Exemple : 5
(pour 5% du montant de chaque commande)
"""
    else:
        message = """💸 COMMISSION MONTANT FIXE

Entrez le montant fixe par commande validée :

Exemple : 50
(pour 50€ par commande)
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data=f"salary_admin_{admin_id}")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['setting_commission'] = {
        'admin_id': admin_id,
        'type': comm_type
    }

@error_handler
async def receive_commission_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne valeur commission"""
    if not is_super_admin(update.effective_user.id):
        return
    
    comm_data = context.user_data.get('setting_commission')
    if not comm_data:
        return
    
    try:
        value = float(update.message.text.strip())
        
        if value < 0:
            await update.message.reply_text(f"{EMOJI_THEME['error']} La valeur ne peut pas être négative.")
            return
        
        if comm_data['type'] == 'percent' and value > 100:
            await update.message.reply_text(f"{EMOJI_THEME['error']} Pourcentage maximum : 100%")
            return
        
        if comm_data['type'] == 'fixed' and value > 10000:
            await update.message.reply_text(f"{EMOJI_THEME['error']} Montant trop élevé (max 10,000€).")
            return
        
        # Mettre à jour config
        config = load_salary_config()
        admin_id = comm_data['admin_id']
        
        if str(admin_id) not in config['admins']:
            admin_name = ADMINS.get(str(admin_id), {}).get('name', 'Admin')
            config['admins'][str(admin_id)] = {
                "name": admin_name,
                "fixed_salary": 0,
                "salary_type": "monthly",
                "commission_type": "none",
                "commission_value": 0,
                "payment_day": 1,
                "active": False
            }
        
        config['admins'][str(admin_id)]['commission_type'] = 'percentage' if comm_data['type'] == 'percent' else 'fixed'
        config['admins'][str(admin_id)]['commission_value'] = value
        save_salary_config(config)
        
        context.user_data.pop('setting_commission', None)
        
        if comm_data['type'] == 'percent':
            info = f"{value}% par commande"
        else:
            info = f"{value:.2f}€ par commande"
        
        message = f"""{EMOJI_THEME['success']} COMMISSION DÉFINIE

Type : {info}

Les commissions seront calculées automatiquement.
"""
        
        keyboard = [[InlineKeyboardButton("📋 Voir configuration", callback_data=f"salary_admin_{admin_id}")]]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"💸 Commission définie: Admin {admin_id} - {info}")
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Valeur invalide. Utilisez un nombre.\n"
            "Exemple : 5"
        )

@error_handler
async def set_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définir fréquence de paiement"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.data.replace("set_frequency_", "")
    
    message = """📅 FRÉQUENCE DE PAIEMENT

Choisissez la fréquence :
"""
    
    keyboard = [
        [InlineKeyboardButton("📅 Mensuel", callback_data=f"freq_monthly_{admin_id}")],
        [InlineKeyboardButton("📆 Hebdomadaire", callback_data=f"freq_weekly_{admin_id}")],
        [InlineKeyboardButton("🔙 Annuler", callback_data=f"salary_admin_{admin_id}")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def save_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sauvegarde fréquence"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split("_")
    freq_type = data_parts[1]  # monthly, weekly
    admin_id = data_parts[2]
    
    config = load_salary_config()
    
    if str(admin_id) not in config['admins']:
        admin_name = ADMINS.get(str(admin_id), {}).get('name', 'Admin')
        config['admins'][str(admin_id)] = {
            "name": admin_name,
            "fixed_salary": 0,
            "salary_type": "monthly",
            "commission_type": "none",
            "commission_value": 0,
            "payment_day": 1,
            "active": False
        }
    
    config['admins'][str(admin_id)]['salary_type'] = freq_type
    save_salary_config(config)
    
    freq_label = "Mensuel" if freq_type == "monthly" else "Hebdomadaire"
    
    await query.edit_message_text(
        f"{EMOJI_THEME['success']} Fréquence : {freq_label}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Voir configuration", callback_data=f"salary_admin_{admin_id}")
        ]])
    )

@error_handler
async def toggle_salary_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Active/désactive salaire d'un admin"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.data.replace("toggle_salary_", "")
    
    config = load_salary_config()
    
    if str(admin_id) not in config['admins']:
        admin_name = ADMINS.get(str(admin_id), {}).get('name', 'Admin')
        config['admins'][str(admin_id)] = {
            "name": admin_name,
            "fixed_salary": 0,
            "salary_type": "monthly",
            "commission_type": "none",
            "commission_value": 0,
            "payment_day": 1,
            "active": False
        }
    
    current_status = config['admins'][str(admin_id)].get('active', False)
    config['admins'][str(admin_id)]['active'] = not current_status
    save_salary_config(config)
    
    status_label = "Activé" if not current_status else "Désactivé"
    
    await query.edit_message_text(
        f"{EMOJI_THEME['success']} Salaire {status_label}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Voir configuration", callback_data=f"salary_admin_{admin_id}")
        ]])
    )

@error_handler
async def set_payment_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande le jour de paiement"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.data.replace("set_day_", "")
    
    config = load_salary_config()
    admin_config = config['admins'].get(str(admin_id), {})
    
    freq_type = admin_config.get('salary_type', 'monthly')
    
    if freq_type == 'monthly':
        message = """📆 JOUR DE PAIEMENT MENSUEL

Choisissez le jour du mois (1-31) :
"""
        keyboard = []
        row = []
        for day in range(1, 32):
            row.append(InlineKeyboardButton(str(day), callback_data=f"payday_{admin_id}_{day}"))
            if len(row) == 7:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
    else:  # weekly
        message = """📆 JOUR DE PAIEMENT HEBDOMADAIRE

Choisissez le jour de la semaine :
"""
        keyboard = [
            [InlineKeyboardButton("Lundi", callback_data=f"payday_{admin_id}_1")],
            [InlineKeyboardButton("Mardi", callback_data=f"payday_{admin_id}_2")],
            [InlineKeyboardButton("Mercredi", callback_data=f"payday_{admin_id}_3")],
            [InlineKeyboardButton("Jeudi", callback_data=f"payday_{admin_id}_4")],
            [InlineKeyboardButton("Vendredi", callback_data=f"payday_{admin_id}_5")],
            [InlineKeyboardButton("Samedi", callback_data=f"payday_{admin_id}_6")],
            [InlineKeyboardButton("Dimanche", callback_data=f"payday_{admin_id}_7")]
        ]
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data=f"salary_admin_{admin_id}")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def save_payment_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sauvegarde le jour de paiement"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.replace("payday_", "").split("_")
    admin_id = data_parts[0]
    day = int(data_parts[1])
    
    config = load_salary_config()
    
    if str(admin_id) not in config['admins']:
        admin_name = ADMINS.get(str(admin_id), {}).get('name', 'Admin')
        config['admins'][str(admin_id)] = {
            "name": admin_name,
            "fixed_salary": 0,
            "salary_type": "monthly",
            "commission_type": "none",
            "commission_value": 0,
            "payment_day": 1,
            "active": False
        }
    
    config['admins'][str(admin_id)]['payment_day'] = day
    save_salary_config(config)
    
    freq_type = config['admins'][str(admin_id)]['salary_type']
    
    if freq_type == 'monthly':
        day_label = f"le {day} du mois"
    else:
        days = {1: "Lundi", 2: "Mardi", 3: "Mercredi", 4: "Jeudi", 5: "Vendredi", 6: "Samedi", 7: "Dimanche"}
        day_label = f"chaque {days.get(day, 'Lundi')}"
    
    await query.edit_message_text(
        f"{EMOJI_THEME['success']} Jour de paiement défini: {day_label}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Voir configuration", callback_data=f"salary_admin_{admin_id}")
        ]])
    )

@error_handler
async def salary_overview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vue d'ensemble tous salaires avec remboursements"""
    query = update.callback_query
    await query.answer()
    
    config = load_salary_config()
    commissions_data = load_commissions()
    expenses = load_expenses()
    
    message = """💼 VUE D'ENSEMBLE SALAIRES

"""
    
    total_fixed = 0
    total_commissions = 0
    total_expenses = 0
    active_count = 0
    
    for admin_id, admin_config in config['admins'].items():
        if not admin_config.get('active', False):
            continue
        
        active_count += 1
        fixed = admin_config.get('fixed_salary', 0)
        commissions = commissions_data.get(admin_id, {}).get('current_period', {}).get('total_commission', 0)
        
        # Consommables approuvés non remboursés
        admin_expenses = sum(
            e['amount'] for e in expenses['expenses']
            if e['admin_id'] == admin_id
            and e['status'] == 'classée'
            and not e.get('reimbursed', False)
        )
        
        total = fixed + commissions + admin_expenses
        
        total_fixed += fixed
        total_commissions += commissions
        total_expenses += admin_expenses
        
        freq = "Mensuel" if admin_config.get('salary_type') == 'monthly' else "Hebdo"
        
        message += f"""👤 {admin_config['name']}
Fixe : {fixed:.2f}€ ({freq})
Commissions : {commissions:.2f}€
Remb. consommables : {admin_expenses:.2f}€
Total à verser : {total:.2f}€

"""
    
    if active_count == 0:
        message += "Aucun salaire actif.\n"
    
    message += f"""━━━━━━━━━━━━━━━━━━━━━━

💰 TOTAUX PÉRIODE ACTUELLE :
Fixes : {total_fixed:.2f}€
Commissions : {total_commissions:.2f}€
Remboursements : {total_expenses:.2f}€

💵 TOTAL À VERSER : {total_fixed + total_commissions + total_expenses:.2f}€

👥 Admins actifs : {active_count}
"""
    
    keyboard = [
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_salary_config")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def calculate_commission_on_order(context, admin_id, order_data):
    """Calcule et enregistre commission pour une commande"""
    config = load_salary_config()
    admin_config = config['admins'].get(str(admin_id))
    
    if not admin_config or not admin_config.get('active', False):
        return
    
    # Calculer commission
    commission = 0
    order_total = float(order_data.get('total', 0))
    
    if admin_config.get('commission_type') == 'percentage':
        commission = order_total * (admin_config.get('commission_value', 0) / 100)
    elif admin_config.get('commission_type') == 'fixed':
        commission = admin_config.get('commission_value', 0)
    
    if commission == 0:
        return
    
    # Charger commissions
    commissions_data = load_commissions()
    
    if str(admin_id) not in commissions_data:
        commissions_data[str(admin_id)] = {
            "current_period": {
                "start_date": datetime.now().isoformat(),
                "orders": [],
                "total_commission": 0
            },
            "history": []
        }
    
    # Ajouter la commission
    commissions_data[str(admin_id)]['current_period']['orders'].append({
        "order_id": order_data['order_id'],
        "date": datetime.now().isoformat(),
        "total": order_total,
        "commission": commission
    })
    
    commissions_data[str(admin_id)]['current_period']['total_commission'] += commission
    
    # Sauvegarder
    save_commissions(commissions_data)
    
    logger.info(f"💸 Commission enregistrée: Admin {admin_id} - {commission:.2f}€ sur {order_total:.2f}€")

# ==================== ADMIN: WORKFLOW VALIDATION COMMANDE ====================

@error_handler
@log_callback
async def edit_order_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permet de modifier le prix total d'une commande"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"🔧 edit_order_total appelé: callback_data={query.data}, user={query.from_user.id}")
    
    order_id = query.data.replace("edit_order_total_", "")
    logger.info(f"📋 order_id extrait: {order_id}")
    
    # Nettoyer les autres états d'édition
    context.user_data.pop('editing_order_delivery', None)
    
    # Charger commande depuis CSV
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        logger.error(f"❌ Fichier CSV introuvable: {csv_path}")
        await query.answer("Erreur: fichier commandes introuvable", show_alert=True)
        return
    
    try:
        import csv as csv_module
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        logger.info(f"📋 CSV chargé: {len(orders)} commandes")
        logger.info(f"🔍 Recherche order_id: '{order_id}'")
        
        # Log des order_ids disponibles
        all_ids = [o.get('order_id', 'NO_ID') for o in orders]
        logger.info(f"🔍 Order IDs disponibles (5 premiers): {all_ids[:5]}")
        logger.info(f"🔍 TOUS les Order IDs: {all_ids}")
        
        order = next((o for o in orders if o.get('order_id') == order_id), None)
        
        if not order:
            logger.error(f"❌ Commande '{order_id}' INTROUVABLE dans {len(orders)} commandes")
            await query.answer("Commande introuvable dans le CSV", show_alert=True)
            return
        
        logger.info(f"✅ Commande trouvée: {order_id}, total={order.get('total', 'N/A')}")
        
        message = f"""✏️ MODIFIER PRIX TOTAL

📋 Commande : {order_id}
💰 Prix actuel : {order.get('total', 'N/A')}€

Entrez le nouveau prix total :
Exemple : 550.00
"""
        
        keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data=f"cancel_edit_order_{order_id}")]]
        
        logger.info(f"📤 Prêt à envoyer message PRIX à {query.from_user.id}")
        logger.info(f"📤 Message length: {len(message)} chars")
        
        # Envoyer un nouveau message au lieu d'éditer
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"✅ Message PRIX envoyé à {query.from_user.id}")
        
        # Répondre au callback pour arrêter le chargement
        await query.answer("✏️ Prêt à modifier le prix")
        
        logger.info(f"✅ Callback answer envoyé")
        
        # Nettoyer TOUS les autres états d'édition pour éviter les conflits
        context.user_data.pop('editing_order_delivery', None)
        context.user_data.pop('awaiting_config', None)
        context.user_data.pop('awaiting_stock_edit', None)
        context.user_data.pop('awaiting_price_edit', None)
        context.user_data.pop('awaiting_fee', None)
        context.user_data.pop('awaiting_cost_update', None)
        context.user_data.pop('editing_expense', None)
        
        # Définir le nouvel état
        context.user_data['editing_order_total'] = order_id
        logger.info(f"📝 État défini: editing_order_total={order_id}")
        logger.info(f"📝 États actifs: {[k for k, v in context.user_data.items() if k.startswith('awaiting') or k.startswith('editing')]}")
    
    except Exception as e:
        import traceback
        logger.error(f"❌ Erreur edit_order_total: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        await query.answer("Erreur", show_alert=True)

@error_handler
@log_callback
async def edit_order_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permet de modifier les frais de livraison d'une commande"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"🔧 edit_order_delivery appelé: callback_data={query.data}, user={query.from_user.id}")
    
    order_id = query.data.replace("edit_order_delivery_", "")
    logger.info(f"📋 order_id extrait: {order_id}")
    
    # Nettoyer les autres états d'édition
    context.user_data.pop('editing_order_total', None)
    
    # Charger commande
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        logger.error(f"❌ Fichier CSV introuvable: {csv_path}")
        await query.answer("Erreur: fichier commandes introuvable", show_alert=True)
        return
    
    try:
        import csv as csv_module
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        logger.info(f"🚚 CSV chargé: {len(orders)} commandes")
        logger.info(f"🔍 Recherche order_id (delivery): '{order_id}'")
        
        # Log des order_ids disponibles
        available_ids = [o.get('order_id', 'NO_ID') for o in orders[:5]]
        logger.info(f"🔍 Order IDs disponibles (5 premiers): {available_ids}")
        
        order = next((o for o in orders if o.get('order_id') == order_id), None)
        
        if not order:
            logger.error(f"❌ Commande '{order_id}' INTROUVABLE (delivery) dans {len(orders)} commandes")
            await query.answer("Commande introuvable dans le CSV", show_alert=True)
            return
        
        logger.info(f"✅ Commande trouvée (delivery): {order_id}")
        
        message = f"""✏️ MODIFIER FRAIS LIVRAISON

📋 Commande : {order_id}
🚚 Frais actuels : {order.get('delivery_fee', 'N/A')}€
📦 Type : {order.get('delivery_type', 'N/A')}

Entrez les nouveaux frais de livraison :
Exemple : 15.00
"""
        
        keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data=f"cancel_edit_order_{order_id}")]]
        
        logger.info(f"📤 Prêt à envoyer message LIVRAISON à {query.from_user.id}")
        logger.info(f"📤 Message length: {len(message)} chars")
        
        # Envoyer un nouveau message au lieu d'éditer
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"✅ Message LIVRAISON envoyé à {query.from_user.id}")
        
        # Répondre au callback pour arrêter le chargement
        await query.answer("✏️ Prêt à modifier les frais")
        
        logger.info(f"✅ Callback answer envoyé")
        
        # Nettoyer TOUS les autres états d'édition pour éviter les conflits
        context.user_data.pop('editing_order_total', None)
        context.user_data.pop('awaiting_config', None)
        context.user_data.pop('awaiting_stock_edit', None)
        context.user_data.pop('awaiting_price_edit', None)
        context.user_data.pop('awaiting_fee', None)
        context.user_data.pop('awaiting_cost_update', None)
        context.user_data.pop('editing_expense', None)
        
        # Définir le nouvel état
        context.user_data['editing_order_delivery'] = order_id
        logger.info(f"📝 État défini: editing_order_delivery={order_id}")
        logger.info(f"📝 États actifs: {[k for k, v in context.user_data.items() if k.startswith('awaiting') or k.startswith('editing')]}")
    
    except Exception as e:
        import traceback
        logger.error(f"❌ Erreur edit_order_delivery: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        await query.answer("Erreur", show_alert=True)

@error_handler
@log_handler
async def receive_order_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne le nouveau prix total"""
    if not is_admin(update.effective_user.id):
        return
    
    order_id = context.user_data.get('editing_order_total')
    
    logger.info(f"📝 receive_order_total appelé: order_id={order_id}, text={update.message.text}")
    
    if not order_id:
        logger.warning("⚠️ order_id manquant dans user_data")
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Session expirée. Veuillez recommencer."
        )
        return
    
    try:
        new_total = float(update.message.text.strip().replace(',', '.'))
        
        logger.info(f"📝 Prix saisi: {new_total}€")
        
        if new_total < 0:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Le prix ne peut pas être négatif."
            )
            return
        
        if new_total > 50000:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Prix trop élevé (max 50,000€)."
            )
            return
        
        # Mettre à jour dans CSV
        csv_path = DATA_DIR / "orders.csv"
        
        if not csv_path.exists():
            logger.error(f"❌ Fichier CSV introuvable: {csv_path}")
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Erreur: fichier commandes introuvable."
            )
            return
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            orders = list(reader)
        
        logger.info(f"📝 {len(orders)} commandes chargées, recherche de {order_id}")
        
        order_found = False
        old_total = "0"  # Initialiser avant la boucle
        
        for order in orders:
            if order.get('order_id') == order_id:
                old_total = order.get('total', '0')
                delivery_fee = float(order.get('delivery_fee', 0))
                
                order['total'] = str(new_total)
                order['subtotal'] = str(new_total - delivery_fee)
                
                # Ajouter colonnes seulement si elles existent déjà
                if 'price_modified' in order:
                    order['price_modified'] = 'Yes'
                if 'old_total' in order:
                    order['old_total'] = old_total
                
                order_found = True
                logger.info(f"✅ Commande trouvée et modifiée: {old_total}€ → {new_total}€")
                break
        
        if not order_found:
            logger.error(f"❌ Commande {order_id} introuvable dans CSV")
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Commande introuvable.\n"
                f"ID recherché: {order_id}"
            )
            return
        
        # Sauvegarder
        logger.info(f"💾 Appel save_orders_csv...")
        save_result = save_orders_csv(csv_path, orders)
        logger.info(f"💾 Résultat save_orders_csv: {save_result}")
        
        if not save_result:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Erreur lors de la sauvegarde.\n"
                "Veuillez réessayer."
            )
            return
        
        logger.info(f"💾 CSV sauvegardé, nettoyage état...")
        context.user_data.pop('editing_order_total', None)
        logger.info(f"💾 État nettoyé")
        
        message = f"""{EMOJI_THEME['success']} PRIX MODIFIÉ

📋 Commande : {order_id}

Ancien prix : {old_total}€
Nouveau prix : {new_total}€

✅ Modification enregistrée.
"""
        
        # Bouton pour retourner à la notification
        keyboard = [[InlineKeyboardButton("🔙 Retour à la notification", callback_data=f"view_order_{order_id}")]]
        
        logger.info(f"📤 Envoi message confirmation...")
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        logger.info(f"✅ Message confirmation envoyé")
        
        logger.info(f"💰 Prix modifié: {order_id} - {old_total}€ → {new_total}€")
    
    except ValueError as e:
        logger.error(f"❌ ValueError dans receive_order_total: {e}")
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Prix invalide. Utilisez un nombre.\n"
            "Exemple : 550.00"
        )

@error_handler
@log_handler
async def receive_order_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne les nouveaux frais de livraison"""
    if not is_admin(update.effective_user.id):
        return
    
    order_id = context.user_data.get('editing_order_delivery')
    
    logger.info(f"📝 receive_order_delivery appelé: order_id={order_id}, text={update.message.text}")
    
    if not order_id:
        logger.warning("⚠️ order_id manquant dans user_data")
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Session expirée. Veuillez recommencer."
        )
        return
    
    try:
        new_delivery_fee = float(update.message.text.strip().replace(',', '.'))
        
        logger.info(f"📝 Frais saisis: {new_delivery_fee}€")
        
        if new_delivery_fee < 0:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Les frais ne peuvent pas être négatifs."
            )
            return
        
        if new_delivery_fee > 200:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Frais trop élevés (max 200€)."
            )
            return
        
        # Mettre à jour dans CSV
        csv_path = DATA_DIR / "orders.csv"
        
        if not csv_path.exists():
            logger.error(f"❌ Fichier CSV introuvable: {csv_path}")
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Erreur: fichier commandes introuvable."
            )
            return
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            orders = list(reader)
        
        logger.info(f"📝 {len(orders)} commandes chargées, recherche de {order_id}")
        
        order_found = False
        old_delivery = "0"  # Initialiser avant la boucle
        new_total = 0.0  # Initialiser avant la boucle
        
        for order in orders:
            if order.get('order_id') == order_id:
                old_delivery = order.get('delivery_fee', '0')
                old_total = float(order.get('total', 0))
                old_delivery_float = float(old_delivery)
                
                # Calculer le nouveau total en remplaçant les anciens frais par les nouveaux
                # (au lieu de recalculer depuis subtotal qui peut être obsolète)
                new_total = old_total - old_delivery_float + new_delivery_fee
                
                order['delivery_fee'] = str(new_delivery_fee)
                order['total'] = str(new_total)
                
                # Ajouter colonnes seulement si elles existent déjà
                if 'delivery_modified' in order:
                    order['delivery_modified'] = 'Yes'
                if 'old_delivery_fee' in order:
                    order['old_delivery_fee'] = old_delivery
                
                order_found = True
                logger.info(f"✅ Frais modifiés: {old_delivery}€ → {new_delivery_fee}€")
                logger.info(f"💰 Nouveau total: {old_total}€ - {old_delivery_float}€ + {new_delivery_fee}€ = {new_total}€")
                logger.info(f"✅ Commande trouvée et modifiée: {old_delivery}€ → {new_delivery_fee}€")
                break
        
        if not order_found:
            logger.error(f"❌ Commande {order_id} introuvable dans CSV")
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Commande introuvable.\n"
                f"ID recherché: {order_id}"
            )
            return
        
        # Sauvegarder
        logger.info(f"💾 Appel save_orders_csv (livraison)...")
        save_result = save_orders_csv(csv_path, orders)
        logger.info(f"💾 Résultat save_orders_csv (livraison): {save_result}")
        
        if not save_result:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Erreur lors de la sauvegarde.\n"
                "Veuillez réessayer."
            )
            return
        
        logger.info(f"💾 CSV livraison sauvegardé, nettoyage état...")
        context.user_data.pop('editing_order_delivery', None)
        logger.info(f"💾 État livraison nettoyé")
        
        message = f"""{EMOJI_THEME['success']} FRAIS MODIFIÉS

📋 Commande : {order_id}

Anciens frais : {old_delivery}€
Nouveaux frais : {new_delivery_fee}€

Nouveau total : {new_total}€

✅ Modification enregistrée.
"""
        
        # Bouton pour retourner à la notification
        keyboard = [[InlineKeyboardButton("🔙 Retour à la notification", callback_data=f"view_order_{order_id}")]]
        
        logger.info(f"📤 Envoi message confirmation livraison...")
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        logger.info(f"✅ Message confirmation livraison envoyé")
        
        logger.info(f"🚚 Frais modifiés: {order_id} - {old_delivery}€ → {new_delivery_fee}€")
    
    except ValueError as e:
        logger.error(f"❌ ValueError dans receive_order_delivery: {e}")
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Montant invalide. Utilisez un nombre.\n"
            "Exemple : 15.00"
        )

@error_handler
async def view_order_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche à nouveau la notification de commande (retour depuis modification)"""
    query = update.callback_query
    await query.answer()
    
    order_id = query.data.replace("view_order_", "")
    logger.info(f"🔙 view_order_notification: {order_id}")
    
    # Charger la commande
    csv_path = DATA_DIR / "orders.csv"
    if not csv_path.exists():
        await query.edit_message_text("❌ Fichier commandes introuvable")
        return
    
    try:
        import csv as csv_module
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        order = next((o for o in orders if o.get('order_id') == order_id), None)
        
        if not order:
            await query.edit_message_text("❌ Commande introuvable")
            return
        
        # Reconstruire le message de notification
        user_id = int(order.get('user_id', 0))
        username = order.get('username', 'N/A')
        first_name = order.get('first_name', 'Client')
        products_str = order.get('products', 'N/A')
        address = order.get('address', 'N/A')
        delivery_type = order.get('delivery_type', 'N/A')
        total = order.get('total', '0')
        delivery_fee = order.get('delivery_fee', '0')
        payment_method = order.get('payment_method', 'N/A')
        status = order.get('status', 'En attente')
        
        message = f"""🔔 NOUVELLE COMMANDE

📋 ID: {order_id}
👤 Client: {first_name} (@{username})
🆔 User ID: {user_id}

📦 Produits:
{products_str}

📍 Adresse: {address}
🚚 Livraison: {delivery_type}
💰 Frais livraison: {delivery_fee}€

💵 Paiement: {payment_method}
💰 TOTAL: {total}€

📊 Statut: {status}
"""
        
        # Boutons selon statut
        if status == "En attente":
            keyboard = [
                [InlineKeyboardButton("✅ Valider", callback_data=f"admin_confirm_order_{order_id}_{user_id}"),
                 InlineKeyboardButton("❌ Refuser", callback_data=f"admin_reject_order_{order_id}_{user_id}")],
                [InlineKeyboardButton("✏️ Modifier prix", callback_data=f"edit_order_total_{order_id}"),
                 InlineKeyboardButton("✏️ Modifier livraison", callback_data=f"edit_order_delivery_{order_id}")]
            ]
        elif status == "Validée":
            keyboard = [
                [InlineKeyboardButton("📦 Marquer prête", callback_data=f"mark_ready_{order_id}_{user_id}")]
            ]
        elif status == "Prête":
            keyboard = [
                [InlineKeyboardButton("✅ Marquer livrée", callback_data=f"mark_delivered_{order_id}_{user_id}")]
            ]
        else:
            keyboard = []
        
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        logger.info(f"✅ Notification réaffichée: {order_id}")
        
    except Exception as e:
        logger.error(f"❌ Erreur view_order_notification: {e}")
        await query.edit_message_text(f"❌ Erreur: {e}")

@error_handler
async def admin_confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Valide la commande après vérification des prix (admin)"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"🔍 admin_confirm_order appelé avec callback_data: {query.data}")
    
    # Extraire order_id et user_id
    try:
        data_parts = query.data.replace("admin_confirm_order_", "").split("_")
        logger.info(f"🔍 data_parts après split: {data_parts}")
        
        if len(data_parts) < 2:
            logger.error(f"❌ Format callback invalide: {query.data}, parts: {data_parts}")
            await query.edit_message_text("❌ Erreur: format de callback invalide")
            return
        
        order_id = data_parts[0]
        user_id = int(data_parts[1])
        
        logger.info(f"🔍 Parsed: order_id={order_id}, user_id={user_id}")
    except (ValueError, IndexError) as e:
        logger.error(f"❌ Erreur parsing callback {query.data}: {e}")
        await query.edit_message_text(f"❌ Erreur: impossible de parser les données ({e})")
        return
    
    # Charger la commande
    csv_path = DATA_DIR / "orders.csv"
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        orders = list(reader)
    
    order = next((o for o in orders if o.get('order_id') == order_id), None)
    
    if not order:
        await query.answer("Commande introuvable", show_alert=True)
        return
    
    # Mettre à jour le statut
    for o in orders:
        if o.get('order_id') == order_id:
            o['status'] = 'Validée'
            o['validated_date'] = datetime.now().isoformat()
            break
    
    # Sauvegarder
    save_orders_csv(csv_path, orders)
    
    # Calculer commission pour l'admin qui valide
    await calculate_commission_on_order(context, query.from_user.id, order)
    
    # NOTIFICATION AU CLIENT
    try:
        # Récupérer les détails depuis products_display s'il existe, sinon depuis products
        products_detail = order.get('products_display', order.get('products', 'N/A'))
        
        client_message = f"""✅ COMMANDE VALIDÉE !

📋 Commande : {order_id}

Votre commande a été validée par notre équipe.

━━━━━━━━━━━━━━━━━━━━━━

🛍️ PRODUITS :
{products_detail}

━━━━━━━━━━━━━━━━━━━━━━

💰 RÉCAPITULATIF :
• Sous-total : {order.get('subtotal', 'N/A')}€
• Livraison : {order.get('delivery_fee', '0')}€
• TOTAL : {order.get('total')}€

💳 Paiement : {order.get('payment_method', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━

📦 Nous préparons actuellement votre commande.
Vous recevrez une notification dès qu'elle sera prête !

Merci de votre confiance ! 🙏
"""
        
        await context.bot.send_message(
            chat_id=user_id,
            text=client_message
        )
        logger.info(f"✅ Client notifié - Commande validée: {order_id}")
    except Exception as e:
        logger.error(f"❌ Erreur notification client validation: {e}")
    
    # Notification admin
    message = f"""{EMOJI_THEME['success']} COMMANDE VALIDÉE

📋 Commande : {order_id}
💰 Total : {order.get('total')}€
🚚 Livraison : {order.get('delivery_fee')}€

✅ Commande confirmée et figée
📦 Vous pouvez maintenant la préparer

Une fois prête, cliquez sur "Commande prête" pour prévenir le client.
"""
    
    keyboard = [[
        InlineKeyboardButton(
            "✅ Commande prête",
            callback_data=f"mark_ready_{order_id}_{user_id}"
        )
    ]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"✅ Commande validée: {order_id}")

@error_handler
async def mark_order_ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Marque la commande comme prête et notifie le client"""
    query = update.callback_query
    await query.answer()
    
    # Extraire order_id et user_id
    data_parts = query.data.replace("mark_ready_", "").split("_")
    order_id = data_parts[0]
    user_id = int(data_parts[1])
    
    # Charger la commande
    csv_path = DATA_DIR / "orders.csv"
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        orders = list(reader)
    
    order = next((o for o in orders if o.get('order_id') == order_id), None)
    
    if not order:
        await query.answer("Commande introuvable", show_alert=True)
        return
    
    # Mettre à jour le statut
    for o in orders:
        if o.get('order_id') == order_id:
            o['status'] = 'Prête'
            o['ready_date'] = datetime.now().isoformat()
            break
    
    # Sauvegarder
    save_orders_csv(csv_path, orders)
    
    # NOTIFICATION AU CLIENT
    products_detail = order.get('products_display', order.get('products', 'N/A'))
    
    client_notification = f"""✅ VOTRE COMMANDE EST PRÊTE !

📋 Commande : {order_id}

Votre commande a été préparée et est prête à être livrée.

━━━━━━━━━━━━━━━━━━━━━━

🛍️ PRODUITS :
{products_detail}

━━━━━━━━━━━━━━━━━━━━━━

💰 RÉCAPITULATIF :
• Sous-total : {order.get('subtotal', 'N/A')}€
• Livraison : {order.get('delivery_fee', '0')}€
• TOTAL : {order.get('total')}€

💳 Paiement : {order.get('payment_method', 'N/A')}
📍 Livraison : {order.get('delivery_type', 'N/A')}
📍 Adresse : {order.get('address', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━

Nous vous contacterons très prochainement pour organiser la livraison.

Merci de votre confiance ! 🙏
"""
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=client_notification
        )
        logger.info(f"✅ Client notifié - Commande prête: {order_id}")
    except Exception as e:
        logger.error(f"Erreur notification client: {e}")
    
    # CONFIRMATION ADMIN
    admin_message = f"""{EMOJI_THEME['success']} COMMANDE PRÊTE

📋 Commande : {order_id}

✅ Statut : Prête
✅ Client automatiquement notifié par le bot

Vous pouvez maintenant livrer la commande.
Une fois livrée, cliquez sur "Marquer livrée".
"""
    
    keyboard = [[
        InlineKeyboardButton(
            "✅ Marquer livrée",
            callback_data=f"admin_validate_{order_id}_{user_id}"
        )
    ]]
    
    await query.edit_message_text(
        admin_message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"✅ Commande marquée prête: {order_id}")

# ==================== ADMIN: LIVRE DE COMPTES ====================

def load_ledger(ledger_type='global'):
    """Charge le livre de comptes
    
    Args:
        ledger_type: 'weed', 'autres', ou 'global' (compatibilité ancien système)
    
    Returns:
        dict: Données du ledger avec entries, balance, last_updated
    """
    if ledger_type == 'weed':
        ledger_file = DATA_DIR / "ledger_weed.json"
    elif ledger_type == 'autres':
        ledger_file = DATA_DIR / "ledger_autres.json"
    else:  # global (ancien système ou combiné)
        ledger_file = DATA_DIR / "ledger.json"
    
    if ledger_file.exists():
        with open(ledger_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    return {
        "entries": [],
        "balance": 0,
        "last_updated": datetime.now().isoformat()
    }

def save_ledger(data, ledger_type='global'):
    """Sauvegarde le livre de comptes
    
    Args:
        data: Données du ledger à sauvegarder
        ledger_type: 'weed', 'autres', ou 'global'
    """
    if ledger_type == 'weed':
        ledger_file = DATA_DIR / "ledger_weed.json"
    elif ledger_type == 'autres':
        ledger_file = DATA_DIR / "ledger_autres.json"
    else:
        ledger_file = DATA_DIR / "ledger.json"
    
    data['last_updated'] = datetime.now().isoformat()
    with open(ledger_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def add_ledger_entry(entry_type, amount, description, category, reference_id=None, ledger_type='autres'):
    """Ajoute une entrée dans le livre de comptes
    
    Args:
        entry_type: 'income' ou 'expense'
        amount: montant positif
        description: texte libre
        category: catégorie (Vente, Salaire, Consommable, etc.)
        reference_id: ID de référence (order_id, payment_id, etc.)
        ledger_type: 'weed' ou 'autres' (défaut: 'autres')
    
    Returns:
        dict: Entrée créée
    """
    logger.info(f"📒 Début add_ledger_entry: type={entry_type}, amount={amount}, category={category}, ledger={ledger_type}")
    
    ledger = load_ledger(ledger_type)
    logger.info(f"📒 Ledger {ledger_type} chargé: {len(ledger.get('entries', []))} entrées, solde={ledger.get('balance', 0)}")
    
    entry = {
        "id": f"LED-{int(datetime.now().timestamp())}",
        "date": datetime.now().isoformat(),
        "type": entry_type,
        "amount": float(amount),
        "description": description,
        "category": category,
        "reference_id": reference_id,
        "balance_after": 0  # sera calculé
    }
    
    # Calculer nouveau solde
    if entry_type == 'income':
        ledger['balance'] += amount
    else:  # expense
        ledger['balance'] -= amount
    
    entry['balance_after'] = ledger['balance']
    
    # Ajouter l'entrée
    ledger['entries'].insert(0, entry)  # Plus récent en premier
    
    logger.info(f"📒 Entrée créée dans {ledger_type}: {entry['id']}, nouveau solde={ledger['balance']}")
    
    save_ledger(ledger, ledger_type)
    logger.info(f"📒 Livre de comptes {ledger_type}: {entry_type} {amount:.2f}€ - {description}")
    
    return entry

def import_existing_orders_to_ledger():
    """Importe toutes les commandes livrées existantes dans le livre de comptes"""
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        logger.info("📒 Aucun fichier orders.csv à importer")
        return 0
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            orders = list(reader)
        
        logger.info(f"📒 {len(orders)} commande(s) trouvée(s) dans orders.csv")
        
        # Filtrer les commandes livrées qui ne sont pas déjà dans le ledger
        ledger = load_ledger()
        existing_refs = {e.get('reference_id') for e in ledger['entries'] if e.get('reference_id')}
        
        logger.info(f"📒 {len(existing_refs)} commande(s) déjà dans le livre")
        
        imported = 0
        skipped = 0
        
        for order in orders:
            order_id = order.get('order_id')
            status = order.get('status', '').strip()
            
            logger.info(f"📒 Commande {order_id}: statut='{status}'")
            
            # Accepter: Livrée, vide (anciennes commandes), ou commandes validées
            # On importe TOUTES les commandes sauf celles "En attente"
            should_import = False
            
            if order_id in existing_refs:
                logger.info(f"📒 Commande {order_id}: déjà importée, skip")
                skipped += 1
                continue
            
            # Importer si:
            # - Status == "Livrée"
            # - Status vide (anciennes commandes avant workflow)
            # - Status == "Validée" (validées mais pas encore workflow complet)
            if status == 'Livrée':
                should_import = True
                logger.info(f"📒 Commande {order_id}: statut Livrée, import")
            elif status == '' or status == 'Validée' or status == 'Prête':
                # Pour les anciennes commandes sans statut, on les importe aussi
                should_import = True
                logger.info(f"📒 Commande {order_id}: ancien système ou validée, import")
            elif status == 'En attente':
                logger.info(f"📒 Commande {order_id}: en attente, skip")
                skipped += 1
                continue
            else:
                # Autre statut, on importe quand même pour être sûr
                should_import = True
                logger.info(f"📒 Commande {order_id}: statut inconnu '{status}', import par sécurité")
            
            if should_import and order_id not in existing_refs:
                try:
                    total = float(order.get('total', 0))
                    first_name = order.get('first_name', 'Client')
                    date = order.get('date', datetime.now().isoformat())
                    
                    if total <= 0:
                        logger.warning(f"📒 Commande {order_id}: montant invalide {total}, skip")
                        skipped += 1
                        continue
                    
                    # Créer l'entrée avec la date originale
                    entry = {
                        "id": f"LED-{int(datetime.now().timestamp())}-{imported}",
                        "date": date,
                        "type": "income",
                        "amount": total,
                        "description": f"Vente commande {order_id} - {first_name} (Import historique)",
                        "category": "Vente",
                        "reference_id": order_id,
                        "balance_after": 0
                    }
                    
                    # Calculer solde
                    ledger['balance'] += total
                    entry['balance_after'] = ledger['balance']
                    
                    # Ajouter l'entrée
                    ledger['entries'].append(entry)
                    imported += 1
                    
                    logger.info(f"✅ Import commande {order_id}: {total:.2f}€")
                    
                except Exception as e:
                    logger.error(f"❌ Erreur import commande {order_id}: {e}")
                    skipped += 1
        
        if imported > 0:
            # Trier par date (plus récent en premier)
            ledger['entries'].sort(key=lambda x: x['date'], reverse=True)
            save_ledger(ledger)
            logger.info(f"✅ {imported} commande(s) importée(s) dans le livre de comptes")
        else:
            logger.info(f"📒 Aucune nouvelle commande à importer (skipped: {skipped})")
        
        return imported
        
    except Exception as e:
        logger.error(f"Erreur import historique: {e}")
        return 0

def import_existing_orders_to_ledger_split():
    """Importe toutes les commandes livrées existantes dans les 2 caisses (WEED / AUTRES)
    
    Logique de split:
    - Si commande contient Weed → Total va dans Caisse WEED
    - Sinon → Frais livraison → Caisse WEED, Reste → Caisse AUTRES
    
    Returns:
        tuple: (imported_weed, imported_autres)
    """
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        logger.info("📒 Aucun fichier orders.csv à importer")
        return (0, 0)
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            orders = list(reader)
        
        logger.info(f"📒 {len(orders)} commande(s) trouvée(s) dans orders.csv")
        
        # Charger les 2 ledgers
        ledger_weed = load_ledger('weed')
        ledger_autres = load_ledger('autres')
        
        # Références existantes pour éviter doublons
        existing_refs_weed = {e.get('reference_id') for e in ledger_weed['entries'] if e.get('reference_id')}
        existing_refs_autres = {e.get('reference_id') for e in ledger_autres['entries'] if e.get('reference_id')}
        
        logger.info(f"📒 Weed: {len(existing_refs_weed)} réfs, Autres: {len(existing_refs_autres)} réfs")
        
        imported_weed = 0
        imported_autres = 0
        skipped = 0
        
        for order in orders:
            order_id = order.get('order_id')
            status = order.get('status', '').strip()
            
            # Skip commandes en attente
            if status == 'En attente':
                logger.info(f"📒 {order_id}: en attente, skip")
                skipped += 1
                continue
            
            # Extraire données commande
            try:
                total = float(order.get('total', 0))
                delivery_fee = float(order.get('delivery_fee', 0))
                products_str = order.get('products', '')
                first_name = order.get('first_name', 'Client')
                date = order.get('date', datetime.now().isoformat())
                
                if total <= 0:
                    logger.warning(f"📒 {order_id}: montant invalide {total}, skip")
                    skipped += 1
                    continue
                
                # Déterminer si c'est une commande WEED
                is_weed = 'Weed' in products_str or '🍀' in products_str
                
                if is_weed:
                    # COMMANDE WEED: Tout va dans Caisse WEED
                    if order_id not in existing_refs_weed:
                        entry = {
                            "id": f"LED-W-{int(datetime.now().timestamp())}-{imported_weed}",
                            "date": date,
                            "type": "income",
                            "amount": total,
                            "description": f"Vente Weed {order_id} - {first_name} (Import)",
                            "category": "Vente",
                            "reference_id": order_id,
                            "balance_after": 0
                        }
                        
                        ledger_weed['balance'] += total
                        entry['balance_after'] = ledger_weed['balance']
                        ledger_weed['entries'].append(entry)
                        imported_weed += 1
                        
                        logger.info(f"✅ Import WEED {order_id}: {total:.2f}€")
                    else:
                        logger.info(f"📒 {order_id}: déjà dans WEED, skip")
                        skipped += 1
                        
                else:
                    # COMMANDE AUTRES: Split Livraison(WEED) / Produits(AUTRES)
                    
                    # 1. Frais de livraison → WEED
                    if delivery_fee > 0 and order_id not in existing_refs_weed:
                        entry_delivery = {
                            "id": f"LED-W-{int(datetime.now().timestamp())}-{imported_weed}",
                            "date": date,
                            "type": "income",
                            "amount": delivery_fee,
                            "description": f"Frais livraison {order_id} - {first_name} (Import)",
                            "category": "Livraison",
                            "reference_id": order_id,
                            "balance_after": 0
                        }
                        
                        ledger_weed['balance'] += delivery_fee
                        entry_delivery['balance_after'] = ledger_weed['balance']
                        ledger_weed['entries'].append(entry_delivery)
                        imported_weed += 1
                        
                        logger.info(f"✅ Import livraison→WEED {order_id}: {delivery_fee:.2f}€")
                    
                    # 2. Produits (total - livraison) → AUTRES
                    products_amount = total - delivery_fee
                    if products_amount > 0 and order_id not in existing_refs_autres:
                        entry_products = {
                            "id": f"LED-A-{int(datetime.now().timestamp())}-{imported_autres}",
                            "date": date,
                            "type": "income",
                            "amount": products_amount,
                            "description": f"Vente {order_id} - {first_name} (Import)",
                            "category": "Vente",
                            "reference_id": order_id,
                            "balance_after": 0
                        }
                        
                        ledger_autres['balance'] += products_amount
                        entry_products['balance_after'] = ledger_autres['balance']
                        ledger_autres['entries'].append(entry_products)
                        imported_autres += 1
                        
                        logger.info(f"✅ Import produits→AUTRES {order_id}: {products_amount:.2f}€")
                    
            except Exception as e:
                logger.error(f"❌ Erreur import {order_id}: {e}")
                skipped += 1
        
        # Sauvegarder les 2 ledgers
        if imported_weed > 0:
            ledger_weed['entries'].sort(key=lambda x: x['date'], reverse=True)
            save_ledger(ledger_weed, 'weed')
            logger.info(f"✅ {imported_weed} entrée(s) importée(s) dans Caisse WEED")
        
        if imported_autres > 0:
            ledger_autres['entries'].sort(key=lambda x: x['date'], reverse=True)
            save_ledger(ledger_autres, 'autres')
            logger.info(f"✅ {imported_autres} entrée(s) importée(s) dans Caisse AUTRES")
        
        logger.info(f"📊 Import terminé: WEED={imported_weed}, AUTRES={imported_autres}, Skipped={skipped}")
        
        return (imported_weed, imported_autres)
        
    except Exception as e:
        logger.error(f"Erreur import historique split: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return (0, 0)

@error_handler
async def admin_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu principal livre de comptes avec 2 caisses (WEED / AUTRES) - super-admin uniquement"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    # Charger les 2 ledgers
    ledger_weed = load_ledger('weed')
    ledger_autres = load_ledger('autres')
    
    # Stats Caisse WEED
    balance_weed = ledger_weed.get('balance', 0)
    income_weed = sum(e['amount'] for e in ledger_weed['entries'] if e['type'] == 'income')
    expenses_weed = sum(e['amount'] for e in ledger_weed['entries'] if e['type'] == 'expense')
    count_weed = len(ledger_weed['entries'])
    
    # Stats Caisse AUTRES
    balance_autres = ledger_autres.get('balance', 0)
    income_autres = sum(e['amount'] for e in ledger_autres['entries'] if e['type'] == 'income')
    expenses_autres = sum(e['amount'] for e in ledger_autres['entries'] if e['type'] == 'expense')
    count_autres = len(ledger_autres['entries'])
    
    # Totaux combinés
    balance_total = balance_weed + balance_autres
    income_total = income_weed + income_autres
    expenses_total = expenses_weed + expenses_autres
    
    message = f"""📒 LIVRE DE COMPTES - 2 CAISSES

💰 SOLDE TOTAL : {balance_total:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

🍀 CAISSE WEED
• Solde : {balance_weed:.2f}€
• Entrées : {income_weed:.2f}€
• Sorties : {expenses_weed:.2f}€
• Transactions : {count_weed}

💎 CAISSE AUTRES
• Solde : {balance_autres:.2f}€
• Entrées : {income_autres:.2f}€
• Sorties : {expenses_autres:.2f}€
• Transactions : {count_autres}

━━━━━━━━━━━━━━━━━━━━━━

📊 TOTAL GÉNÉRAL
• Entrées : {income_total:.2f}€
• Sorties : {expenses_total:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

ℹ️ RÉPARTITION :
🍀 Weed = Livraisons + Ventes Weed
💎 Autres = Coco, K, Crystal, Pills

Que voulez-vous faire ?
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🍀 Voir WEED", callback_data="ledger_view_weed"),
            InlineKeyboardButton("💎 Voir AUTRES", callback_data="ledger_view_autres")
        ],
        [
            InlineKeyboardButton("➕ Entrée Weed", callback_data="ledger_add_weed_income"),
            InlineKeyboardButton("➖ Sortie Weed", callback_data="ledger_add_weed_expense")
        ],
        [
            InlineKeyboardButton("➕ Entrée Autres", callback_data="ledger_add_other_income"),
            InlineKeyboardButton("➖ Sortie Autres", callback_data="ledger_add_other_expense")
        ],
        [
            InlineKeyboardButton("🔄 Réimporter historique", callback_data="ledger_reimport_split")
        ],
        [
            InlineKeyboardButton("📊 Rapport Mensuel", callback_data="ledger_monthly_report")
        ],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def ledger_view_weed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les transactions de la Caisse WEED"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    ledger = load_ledger('weed')
    entries = ledger.get('entries', [])
    balance = ledger.get('balance', 0)
    
    message = f"""🍀 CAISSE WEED

💰 Solde : {balance:.2f}€
📋 Transactions : {len(entries)}

━━━━━━━━━━━━━━━━━━━━━━

📊 DERNIÈRES TRANSACTIONS :

"""
    
    # Afficher les 10 dernières transactions
    for entry in entries[:10]:
        date = entry.get('date', '')[:10]
        amount = entry.get('amount', 0)
        desc = entry.get('description', '')
        entry_type = entry.get('type', '')
        
        icon = "📥" if entry_type == 'income' else "📤"
        sign = "+" if entry_type == 'income' else "-"
        
        message += f"{icon} {date} | {sign}{amount:.2f}€\n"
        message += f"   {desc[:50]}\n\n"
    
    if len(entries) > 10:
        message += f"\n... et {len(entries) - 10} transaction(s) de plus"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_ledger")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def ledger_view_autres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les transactions de la Caisse AUTRES"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    ledger = load_ledger('autres')
    entries = ledger.get('entries', [])
    balance = ledger.get('balance', 0)
    
    message = f"""💎 CAISSE AUTRES

💰 Solde : {balance:.2f}€
📋 Transactions : {len(entries)}

━━━━━━━━━━━━━━━━━━━━━━

📊 DERNIÈRES TRANSACTIONS :

"""
    
    # Afficher les 10 dernières transactions
    for entry in entries[:10]:
        date = entry.get('date', '')[:10]
        amount = entry.get('amount', 0)
        desc = entry.get('description', '')
        entry_type = entry.get('type', '')
        
        icon = "📥" if entry_type == 'income' else "📤"
        sign = "+" if entry_type == 'income' else "-"
        
        message += f"{icon} {date} | {sign}{amount:.2f}€\n"
        message += f"   {desc[:50]}\n\n"
    
    if len(entries) > 10:
        message += f"\n... et {len(entries) - 10} transaction(s) de plus"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_ledger")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def ledger_reimport_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réimporte l'historique dans les 2 caisses avec classification"""
    query = update.callback_query
    await query.answer("⏳ Import en cours...", show_alert=True)
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    # Lancer l'import
    imported_weed, imported_autres = import_existing_orders_to_ledger_split()
    
    message = f"""🔄 RÉIMPORT HISTORIQUE

✅ Import terminé !

📊 RÉSULTATS :
• 🍀 Caisse WEED : {imported_weed} entrée(s)
• 💎 Caisse AUTRES : {imported_autres} entrée(s)

━━━━━━━━━━━━━━━━━━━━━━

Les commandes ont été classées :
• Weed → Caisse WEED (total complet)
• Autres → Split :
  - Livraison → Caisse WEED
  - Produits → Caisse AUTRES

Les doublons ont été ignorés automatiquement.
"""
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_ledger")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def ledger_manage_duplicates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche et gère les entrées en double/triple dans le livre de comptes"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    ledger = load_ledger()
    
    # Identifier les doublons par reference_id
    from collections import Counter
    ref_counts = Counter(e.get('reference_id') for e in ledger['entries'] if e.get('reference_id'))
    duplicates = {ref: count for ref, count in ref_counts.items() if count > 1}
    
    if not duplicates:
        message = """🗑️ GESTION DOUBLONS

✅ Aucun doublon détecté !

Toutes les entrées ont des reference_id uniques.
"""
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_ledger")]]
    else:
        total_duplicates = sum(count - 1 for count in duplicates.values())
        
        message = f"""🗑️ GESTION DOUBLONS

⚠️ {len(duplicates)} référence(s) en double
📋 {total_duplicates} entrée(s) à supprimer

━━━━━━━━━━━━━━━━━━━━━━

"""
        
        keyboard = []
        
        # Afficher les premiers 10 doublons
        for ref, count in list(duplicates.items())[:10]:
            # Trouver la première entrée avec cette référence
            entry = next((e for e in ledger['entries'] if e.get('reference_id') == ref), None)
            if entry:
                amount = entry.get('amount', 0)
                entry_type = "📥" if entry.get('type') == 'income' else "📤"
                
                message += f"""{entry_type} {ref[-8:]}... x{count}
💰 {amount:.2f}€ x {count} = {amount * count:.2f}€
📝 {entry.get('description', 'N/A')[:40]}

"""
                
                # Bouton pour gérer ce doublon
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗑️ Nettoyer {ref[-8:]} (garder 1)",
                        callback_data=f"ledger_clean_dup_{ref}"
                    )
                ])
        
        if len(duplicates) > 10:
            message += f"\n... et {len(duplicates) - 10} autre(s)\n"
        
        # Bouton pour tout nettoyer automatiquement
        keyboard.append([InlineKeyboardButton("🧹 TOUT NETTOYER AUTO", callback_data="ledger_clean_all_dups")])
        keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_ledger")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def ledger_clean_duplicate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nettoie un doublon spécifique (garde la première occurrence)"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    reference_id = query.data.replace("ledger_clean_dup_", "")
    
    ledger = load_ledger()
    
    # Trouver toutes les entrées avec cette reference_id
    duplicates = [e for e in ledger['entries'] if e.get('reference_id') == reference_id]
    
    if len(duplicates) <= 1:
        await query.answer("Aucun doublon à nettoyer", show_alert=True)
        return
    
    # Garder la première, supprimer les autres
    first_entry = duplicates[0]
    removed_count = len(duplicates) - 1
    
    # Nouvelle liste sans les doublons
    cleaned_entries = []
    seen = False
    
    for entry in ledger['entries']:
        if entry.get('reference_id') == reference_id:
            if not seen:
                # Garder la première occurrence
                cleaned_entries.append(entry)
                seen = True
            # Ignorer les suivantes
        else:
            cleaned_entries.append(entry)
    
    # Recalculer les soldes
    ledger['entries'] = cleaned_entries
    balance = 0
    for entry in ledger['entries']:
        if entry['type'] == 'income':
            balance += entry['amount']
        else:
            balance -= entry['amount']
        entry['balance_after'] = balance
    
    ledger['balance'] = balance
    save_ledger(ledger)
    
    await query.answer(f"✅ {removed_count} doublon(s) supprimé(s)", show_alert=True)
    
    # Retourner à la liste des doublons
    await ledger_manage_duplicates(update, context)

@error_handler
async def ledger_clean_all_duplicates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nettoie TOUS les doublons automatiquement"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    ledger = load_ledger()
    
    # Identifier tous les doublons
    from collections import Counter
    ref_counts = Counter(e.get('reference_id') for e in ledger['entries'] if e.get('reference_id'))
    duplicates = {ref: count for ref, count in ref_counts.items() if count > 1}
    
    if not duplicates:
        await query.answer("Aucun doublon à nettoyer", show_alert=True)
        return
    
    # Nettoyer tous les doublons (garder première occurrence de chaque)
    cleaned_entries = []
    seen_refs = set()
    total_removed = 0
    
    for entry in ledger['entries']:
        ref = entry.get('reference_id')
        
        if ref and ref in duplicates:
            # C'est un doublon potentiel
            if ref not in seen_refs:
                # Première occurrence : garder
                cleaned_entries.append(entry)
                seen_refs.add(ref)
            else:
                # Doublon : supprimer
                total_removed += 1
        else:
            # Pas de doublon ou pas de reference_id : garder
            cleaned_entries.append(entry)
    
    # Recalculer tous les soldes
    ledger['entries'] = cleaned_entries
    balance = 0
    for entry in ledger['entries']:
        if entry['type'] == 'income':
            balance += entry['amount']
        else:
            balance -= entry['amount']
        entry['balance_after'] = balance
    
    ledger['balance'] = balance
    save_ledger(ledger)
    
    message = f"""✅ NETTOYAGE TERMINÉ

🗑️ {total_removed} doublon(s) supprimé(s)
📋 {len(cleaned_entries)} entrée(s) restantes
💰 Nouveau solde : {balance:.2f}€

Les soldes ont été recalculés automatiquement.
"""
    
    keyboard = [
        [InlineKeyboardButton("🔙 Retour Livre de Comptes", callback_data="admin_ledger")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"🧹 Nettoyage doublons: {total_removed} entrées supprimées")

@error_handler
async def ledger_view_entries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les transactions (filtrées par type)"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    # Déterminer le filtre
    if "income" in query.data:
        entry_filter = "income"
        title = "📥 ENTRÉES D'ARGENT"
        emoji = "💰"
    elif "expenses" in query.data:
        entry_filter = "expense"
        title = "📤 SORTIES D'ARGENT"
        emoji = "💸"
    else:
        entry_filter = None
        title = "📋 TOUTES LES TRANSACTIONS"
        emoji = "💵"
    
    ledger = load_ledger()
    
    # Filtrer les entrées
    if entry_filter:
        entries = [e for e in ledger['entries'] if e['type'] == entry_filter][:20]
    else:
        entries = ledger['entries'][:20]
    
    if not entries:
        message = f"""{title}

Aucune transaction trouvée.
"""
    else:
        total = sum(e['amount'] for e in entries)
        
        message = f"""{title}

{len(entries)} transaction(s) - Total: {total:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

"""
        
        for entry in entries:
            date_str = entry['date'][:10]
            sign = "+" if entry['type'] == 'income' else "-"
            type_emoji = "💰" if entry['type'] == 'income' else "💸"
            
            message += f"""{type_emoji} {entry['category']}
{sign}{entry['amount']:.2f}€ | Solde: {entry['balance_after']:.2f}€
📝 {entry['description']}
📅 {date_str}

"""
    
    keyboard = [
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_ledger")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def ledger_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande le type d'entrée à ajouter"""
    query = update.callback_query
    await query.answer()
    
    entry_type = "income" if "income" in query.data else "expense"
    
    if entry_type == "income":
        message = """➕ AJOUTER ENTRÉE D'ARGENT

Sélectionnez la catégorie :
"""
        categories = [
            ("💰 Vente", "ledger_cat_income_Vente"),
            ("🎁 Remboursement", "ledger_cat_income_Remboursement"),
            ("💵 Apport", "ledger_cat_income_Apport"),
            ("📦 Autre entrée", "ledger_cat_income_Autre")
        ]
    else:
        message = """➖ AJOUTER SORTIE D'ARGENT

Sélectionnez la catégorie :
"""
        categories = [
            ("💸 Salaire", "ledger_cat_expense_Salaire"),
            ("🧾 Consommable", "ledger_cat_expense_Consommable"),
            ("📦 Achat stock", "ledger_cat_expense_Stock"),
            ("🚗 Frais divers", "ledger_cat_expense_Divers"),
            ("📤 Autre sortie", "ledger_cat_expense_Autre")
        ]
    keyboard = []
    for label, callback in categories:
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="admin_ledger")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def ledger_select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catégorie sélectionnée, demander description"""
    query = update.callback_query
    await query.answer()
    
    # Extraire type et catégorie
    parts = query.data.replace("ledger_cat_", "").split("_")
    entry_type = parts[0]  # income ou expense
    category = parts[1]  # Vente, Salaire, etc.
    
    context.user_data['ledger_entry_type'] = entry_type
    context.user_data['ledger_category'] = category
    
    type_label = "entrée" if entry_type == "income" else "sortie"
    
    message = f"""📝 {category.upper()}

Entrez la description :
Exemple : Vente commande ORD-123456

Type : {type_label}
Catégorie : {category}
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_ledger")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_ledger_description'] = True

@error_handler
async def receive_ledger_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne la description"""
    if not is_super_admin(update.effective_user.id):
        return
    
    if not context.user_data.get('awaiting_ledger_description'):
        return
    
    description = update.message.text.strip()
    
    if len(description) > 200:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Description trop longue (max 200 caractères)."
        )
        return
    
    context.user_data['ledger_description'] = description
    context.user_data.pop('awaiting_ledger_description', None)
    
    # Demander montant
    entry_type = context.user_data.get('ledger_entry_type')
    type_label = "reçu" if entry_type == "income" else "dépensé"
    
    message = f"""💰 MONTANT

Description : {description}

Entrez le montant {type_label} :
Exemple : 550.50
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_ledger")]]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_ledger_amount'] = True

@error_handler
async def receive_ledger_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne le montant et enregistre"""
    if not is_super_admin(update.effective_user.id):
        return
    
    if not context.user_data.get('awaiting_ledger_amount'):
        return
    
    try:
        amount = float(update.message.text.strip())
        
        if amount <= 0:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Le montant doit être positif."
            )
            return
        
        if amount > 1000000:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Montant trop élevé (max 1,000,000€)."
            )
            return
        
        # Récupérer les données
        entry_type = context.user_data.get('ledger_entry_type')
        category = context.user_data.get('ledger_category')
        description = context.user_data.get('ledger_description')
        
        # Ajouter l'entrée
        entry = add_ledger_entry(entry_type, amount, description, category)
        
        # Nettoyer
        context.user_data.pop('ledger_entry_type', None)
        context.user_data.pop('ledger_category', None)
        context.user_data.pop('ledger_description', None)
        context.user_data.pop('awaiting_ledger_amount', None)
        
        # Confirmation
        sign = "+" if entry_type == "income" else "-"
        type_emoji = "📥" if entry_type == "income" else "📤"
        
        message = f"""{EMOJI_THEME['success']} TRANSACTION ENREGISTRÉE

{type_emoji} {category}
{sign}{amount:.2f}€

📝 {description}
💰 Nouveau solde : {entry['balance_after']:.2f}€

Transaction ID : {entry['id']}
"""
        
        keyboard = [
            [InlineKeyboardButton("📒 Livre de Comptes", callback_data="admin_ledger")],
            [InlineKeyboardButton("🏠 Panel", callback_data="admin_back_panel")]
        ]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Montant invalide. Utilisez un nombre.\n"
            "Exemple : 550.50"
        )

@error_handler
async def ledger_edit_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permet de corriger le solde manuellement"""
    query = update.callback_query
    await query.answer()
    
    ledger = load_ledger()
    current_balance = ledger.get('balance', 0)
    
    message = f"""✏️ MODIFIER LE SOLDE

Solde actuel : {current_balance:.2f}€

⚠️ ATTENTION : Cette action modifie directement le solde.
Utilisez uniquement pour corriger une erreur.

Entrez le nouveau solde :
Exemple : 5420.00
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_ledger")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_ledger_balance'] = True

@error_handler
async def receive_ledger_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne nouveau solde"""
    if not is_super_admin(update.effective_user.id):
        return
    
    if not context.user_data.get('awaiting_ledger_balance'):
        return
    
    try:
        new_balance = float(update.message.text.strip())
        
        if abs(new_balance) > 10000000:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Solde trop élevé (max ±10,000,000€)."
            )
            return
        
        ledger = load_ledger()
        old_balance = ledger.get('balance', 0)
        
        # Créer une entrée de correction
        diff = new_balance - old_balance
        
        if diff > 0:
            entry = add_ledger_entry(
                'income',
                diff,
                f"Correction solde : {old_balance:.2f}€ → {new_balance:.2f}€",
                "Correction"
            )
        elif diff < 0:
            entry = add_ledger_entry(
                'expense',
                abs(diff),
                f"Correction solde : {old_balance:.2f}€ → {new_balance:.2f}€",
                "Correction"
            )
        else:
            await update.message.reply_text(
                f"{EMOJI_THEME['warning']} Le solde est déjà à {new_balance:.2f}€"
            )
            context.user_data.pop('awaiting_ledger_balance', None)
            return
        
        context.user_data.pop('awaiting_ledger_balance', None)
        
        message = f"""{EMOJI_THEME['success']} SOLDE MODIFIÉ

Ancien solde : {old_balance:.2f}€
Nouveau solde : {new_balance:.2f}€
Différence : {diff:+.2f}€

Une entrée de correction a été créée.
"""
        
        keyboard = [
            [InlineKeyboardButton("📒 Livre de Comptes", callback_data="admin_ledger")],
            [InlineKeyboardButton("🏠 Panel", callback_data="admin_back_panel")]
        ]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Montant invalide. Utilisez un nombre.\n"
            "Exemple : 5420.00"
        )

@error_handler
async def ledger_import_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Importe l'historique des commandes dans le livre de comptes"""
    query = update.callback_query
    await query.answer("🔄 Import en cours...", show_alert=False)
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    # Lancer l'import
    imported = import_existing_orders_to_ledger()
    
    if imported > 0:
        message = f"""✅ IMPORT TERMINÉ

{imported} commande(s) livrée(s) importée(s) dans le livre de comptes.

Le solde a été mis à jour automatiquement.
"""
    else:
        message = """ℹ️ IMPORT TERMINÉ

Aucune nouvelle commande à importer.

Toutes les commandes livrées sont déjà dans le livre de comptes.
"""
    
    keyboard = [
        [InlineKeyboardButton("📒 Voir le livre", callback_data="admin_ledger")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def ledger_monthly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Génère un rapport mensuel"""
    query = update.callback_query
    await query.answer()
    
    ledger = load_ledger()
    
    # Filtrer ce mois
    now = datetime.now()
    month_start = datetime(now.year, now.month, 1)
    
    entries_this_month = [
        e for e in ledger['entries']
        if datetime.fromisoformat(e['date']) >= month_start
    ]
    
    if not entries_this_month:
        message = """📊 RAPPORT MENSUEL

Aucune transaction ce mois.
"""
    else:
        income_entries = [e for e in entries_this_month if e['type'] == 'income']
        expense_entries = [e for e in entries_this_month if e['type'] == 'expense']
        
        total_income = sum(e['amount'] for e in income_entries)
        total_expenses = sum(e['amount'] for e in expense_entries)
        net = total_income - total_expenses
        
        # Par catégorie
        income_by_cat = {}
        expense_by_cat = {}
        
        for e in income_entries:
            cat = e.get('category', 'Autre')
            income_by_cat[cat] = income_by_cat.get(cat, 0) + e['amount']
        
        for e in expense_entries:
            cat = e.get('category', 'Autre')
            expense_by_cat[cat] = expense_by_cat.get(cat, 0) + e['amount']
        
        message = f"""📊 RAPPORT MENSUEL

📅 {now.strftime('%B %Y')}

━━━━━━━━━━━━━━━━━━━━━━

📥 ENTRÉES : {total_income:.2f}€
"""
        
        for cat, amount in sorted(income_by_cat.items(), key=lambda x: x[1], reverse=True):
            message += f"  • {cat}: {amount:.2f}€\n"
        
        message += f"""
📤 SORTIES : {total_expenses:.2f}€
"""
        
        for cat, amount in sorted(expense_by_cat.items(), key=lambda x: x[1], reverse=True):
            message += f"  • {cat}: {amount:.2f}€\n"
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━

💰 SOLDE NET : {net:+.2f}€

📊 Transactions : {len(entries_this_month)}
💰 Solde actuel : {ledger.get('balance', 0):.2f}€
"""
    
    keyboard = [
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_ledger")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== LIVRE DES COMPTES WEED/AUTRES ====================

@error_handler
async def ledger_add_weed_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajouter une entrée Weed"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    # Nettoyer TOUS les autres états
    context.user_data.pop('awaiting_config', None)
    context.user_data.pop('awaiting_stock_edit', None)
    context.user_data.pop('awaiting_contact_message', None)
    context.user_data.pop('editing_order_delivery', None)
    context.user_data.pop('editing_order_total', None)
    context.user_data.pop('awaiting_cost_update', None)
    context.user_data.pop('awaiting_fee', None)
    context.user_data.pop('awaiting_price_edit', None)
    context.user_data.pop('awaiting_ledger_amount', None)
    
    context.user_data['ledger_entry_type'] = 'income'
    context.user_data['ledger_ledger'] = 'weed'
    
    message = """➕ ENTRÉE WEED

Catégories disponibles:
"""
    categories = [
        ("💰 Vente Weed", "ledger_weed_cat_income_Vente"),
        ("🎁 Remboursement", "ledger_weed_cat_income_Remboursement"),
        ("💵 Apport", "ledger_weed_cat_income_Apport"),
        ("📦 Autre", "ledger_weed_cat_income_Autre")
    ]
    
    keyboard = []
    for label, callback in categories:
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="admin_ledger")])
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def ledger_add_weed_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajouter une sortie Weed"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    # Nettoyer TOUS les autres états
    context.user_data.pop('awaiting_config', None)
    context.user_data.pop('awaiting_stock_edit', None)
    context.user_data.pop('awaiting_contact_message', None)
    context.user_data.pop('editing_order_delivery', None)
    context.user_data.pop('editing_order_total', None)
    context.user_data.pop('awaiting_cost_update', None)
    context.user_data.pop('awaiting_fee', None)
    context.user_data.pop('awaiting_price_edit', None)
    context.user_data.pop('awaiting_ledger_amount', None)
    
    context.user_data['ledger_entry_type'] = 'expense'
    context.user_data['ledger_ledger'] = 'weed'
    
    message = """➖ SORTIE WEED

Catégories disponibles:
"""
    categories = [
        ("💸 Salaire", "ledger_weed_cat_expense_Salaire"),
        ("🧾 Consommable", "ledger_weed_cat_expense_Consommable"),
        ("📦 Achat stock", "ledger_weed_cat_expense_Stock"),
        ("🚗 Frais divers", "ledger_weed_cat_expense_Divers"),
        ("📤 Autre", "ledger_weed_cat_expense_Autre")
    ]
    
    keyboard = []
    for label, callback in categories:
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="admin_ledger")])
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def ledger_add_other_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajouter une entrée Autres"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    # Nettoyer TOUS les autres états
    context.user_data.pop('awaiting_config', None)
    context.user_data.pop('awaiting_stock_edit', None)
    context.user_data.pop('awaiting_contact_message', None)
    context.user_data.pop('editing_order_delivery', None)
    context.user_data.pop('editing_order_total', None)
    context.user_data.pop('awaiting_cost_update', None)
    context.user_data.pop('awaiting_fee', None)
    context.user_data.pop('awaiting_price_edit', None)
    context.user_data.pop('awaiting_ledger_amount', None)
    
    context.user_data['ledger_entry_type'] = 'income'
    context.user_data['ledger_ledger'] = 'autres'
    
    message = """➕ ENTRÉE AUTRES

Catégories disponibles:
"""
    categories = [
        ("💰 Vente Autres", "ledger_other_cat_income_Vente"),
        ("🎁 Remboursement", "ledger_other_cat_income_Remboursement"),
        ("💵 Apport", "ledger_other_cat_income_Apport"),
        ("📦 Autre", "ledger_other_cat_income_Autre")
    ]
    
    keyboard = []
    for label, callback in categories:
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="admin_ledger")])
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def ledger_add_other_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajouter une sortie Autres"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    # Nettoyer TOUS les autres états
    context.user_data.pop('awaiting_config', None)
    context.user_data.pop('awaiting_stock_edit', None)
    context.user_data.pop('awaiting_contact_message', None)
    context.user_data.pop('editing_order_delivery', None)
    context.user_data.pop('editing_order_total', None)
    context.user_data.pop('awaiting_cost_update', None)
    context.user_data.pop('awaiting_fee', None)
    context.user_data.pop('awaiting_price_edit', None)
    context.user_data.pop('awaiting_ledger_amount', None)
    
    context.user_data['ledger_entry_type'] = 'expense'
    context.user_data['ledger_ledger'] = 'autres'
    
    message = """➖ SORTIE AUTRES

Catégories disponibles:
"""
    categories = [
        ("💸 Salaire", "ledger_other_cat_expense_Salaire"),
        ("🧾 Consommable", "ledger_other_cat_expense_Consommable"),
        ("📦 Achat stock", "ledger_other_cat_expense_Stock"),
        ("🚗 Frais divers", "ledger_other_cat_expense_Divers"),
        ("📤 Autre", "ledger_other_cat_expense_Autre")
    ]
    
    keyboard = []
    for label, callback in categories:
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton("❌ Annuler", callback_data="admin_ledger")])
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def ledger_select_weed_other_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection de catégorie pour weed/autres"""
    query = update.callback_query
    await query.answer()
    
    # Nettoyer TOUS les autres états
    context.user_data.pop('awaiting_config', None)
    context.user_data.pop('awaiting_stock_edit', None)
    context.user_data.pop('awaiting_contact_message', None)
    context.user_data.pop('editing_order_delivery', None)
    context.user_data.pop('editing_order_total', None)
    context.user_data.pop('awaiting_cost_update', None)
    context.user_data.pop('awaiting_fee', None)
    context.user_data.pop('awaiting_price_edit', None)
    context.user_data.pop('awaiting_ledger_amount', None)
    
    # Extraire ledger, type et catégorie
    if "ledger_weed_cat_" in query.data:
        ledger_type = 'weed'
        parts = query.data.replace("ledger_weed_cat_", "").split("_")
    else:
        ledger_type = 'autres'
        parts = query.data.replace("ledger_other_cat_", "").split("_")
    
    entry_type = parts[0]  # income ou expense
    category = parts[1]  # Vente, Salaire, etc.
    
    context.user_data['ledger_entry_type'] = entry_type
    context.user_data['ledger_category'] = category
    context.user_data['ledger_ledger'] = ledger_type
    
    type_label = "entrée" if entry_type == "income" else "sortie"
    ledger_label = "🍀 WEED" if ledger_type == "weed" else "💎 AUTRES"
    
    message = f"""📝 {category.upper()}

{ledger_label}
Type: {type_label}

Entrez la description:
Exemple: Vente commande ORD-123456
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_ledger")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    context.user_data['awaiting_ledger_description'] = True

# ==================== CONFIGURATION DES HANDLERS ====================

def setup_handlers(application):
    """Configure tous les handlers du bot"""
    
    # Commandes de base
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("fix_csv", fix_csv_command))
    application.add_handler(CommandHandler("myid", get_my_id))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("diag_salaires", diag_salaires))
    application.add_handler(CommandHandler("migrate", migrate_hardcoded_products))
    application.add_handler(CommandHandler("test_notif", test_notif))
    
    # Callbacks généraux
    application.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
    application.add_handler(CallbackQueryHandler(help_inline, pattern="^help_inline$"))
    application.add_handler(CallbackQueryHandler(my_history, pattern="^my_history$"))
    application.add_handler(CallbackQueryHandler(referral_info, pattern="^referral_info$"))
    
    # Callbacks pays
    application.add_handler(CallbackQueryHandler(select_country, pattern="^country_(fr|ch|au)$"))
    
    # Callbacks shopping
    application.add_handler(CallbackQueryHandler(browse_products, pattern="^browse_(all|pills|rocks)$"))
    application.add_handler(CallbackQueryHandler(product_detail, pattern="^product_"))
    application.add_handler(CallbackQueryHandler(custom_quantity, pattern="^customqty_"))
    application.add_handler(CallbackQueryHandler(add_to_cart, pattern="^addcart_"))
    
    # Callbacks panier
    application.add_handler(CallbackQueryHandler(view_cart, pattern="^view_cart$"))
    application.add_handler(CallbackQueryHandler(clear_cart, pattern="^clear_cart$"))
    application.add_handler(CallbackQueryHandler(validate_cart, pattern="^validate_cart$"))
    
    # Callbacks livraison
    application.add_handler(CallbackQueryHandler(delivery_select, pattern="^delivery_select$"))
    application.add_handler(CallbackQueryHandler(delivery_mode_selected, pattern="^delivery_(postal|express|meetup)$"))
    
    # Callbacks promo
    application.add_handler(CallbackQueryHandler(promo_skip, pattern="^promo_skip$"))
    
    # Callbacks paiement
    application.add_handler(CallbackQueryHandler(payment_method_selected, pattern="^payment_(cash|transfer|crypto)$"))
    
    # Callbacks commande
    application.add_handler(CallbackQueryHandler(confirm_order, pattern="^order_confirm$"))
    # Callbacks admin - validation commandes
    application.add_handler(CallbackQueryHandler(edit_order_total, pattern="^edit_order_total_"))
    application.add_handler(CallbackQueryHandler(edit_order_delivery, pattern="^edit_order_delivery_"))
    application.add_handler(CallbackQueryHandler(view_order_notification, pattern="^view_order_"))
    application.add_handler(CallbackQueryHandler(admin_confirm_order, pattern="^admin_confirm_order_"))
    application.add_handler(CallbackQueryHandler(mark_order_ready, pattern="^mark_ready_"))
    application.add_handler(CallbackQueryHandler(admin_validate_order, pattern="^admin_validate_"))
    
    # Callbacks admin panel
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_back_panel$"))
    application.add_handler(CallbackQueryHandler(admin_close, pattern="^admin_close$"))
    
    # Callbacks admin - produits
    application.add_handler(CallbackQueryHandler(admin_products, pattern="^admin_products$"))
    application.add_handler(CallbackQueryHandler(admin_list_products, pattern="^admin_list_products$"))
    application.add_handler(CallbackQueryHandler(admin_toggle_products, pattern="^admin_toggle_products$"))
    application.add_handler(CallbackQueryHandler(admin_toggle_product_execute, pattern="^admin_toggle_"))
    application.add_handler(CallbackQueryHandler(admin_add_product, pattern="^admin_add_product$"))
    
    # Callbacks admin - stocks
    application.add_handler(CallbackQueryHandler(admin_stocks, pattern="^admin_stocks$"))
    application.add_handler(CallbackQueryHandler(admin_view_stocks, pattern="^admin_view_stocks$"))
    application.add_handler(CallbackQueryHandler(admin_add_stock, pattern="^admin_add_stock$"))
    application.add_handler(CallbackQueryHandler(admin_stock_alerts, pattern="^admin_stock_alerts$"))
    application.add_handler(CallbackQueryHandler(admin_stock_select_product, pattern="^admin_stock_select_"))
    
    # Callbacks admin - prix
    application.add_handler(CallbackQueryHandler(admin_prices, pattern="^admin_prices$"))
    application.add_handler(CallbackQueryHandler(admin_prices_country, pattern="^admin_prices_(fr|ch)$"))
    application.add_handler(CallbackQueryHandler(admin_pricing_tiers, pattern="^admin_pricing_tiers$"))
    application.add_handler(CallbackQueryHandler(admin_edit_price_start, pattern="^admin_edit_prices_"))
    application.add_handler(CallbackQueryHandler(admin_price_edit_product, pattern="^admin_price_edit_"))
    
    # Callbacks admin - promos
    application.add_handler(CallbackQueryHandler(admin_promos, pattern="^admin_promos$"))
    application.add_handler(CallbackQueryHandler(admin_list_promos, pattern="^admin_list_promos$"))
    application.add_handler(CallbackQueryHandler(admin_create_promo_start, pattern="^admin_create_promo$"))
    application.add_handler(CallbackQueryHandler(promo_type_selected, pattern="^promo_type_"))
    application.add_handler(CallbackQueryHandler(admin_delete_promo_start, pattern="^admin_delete_promo$"))
    application.add_handler(CallbackQueryHandler(admin_delete_promo_confirm, pattern="^admin_delete_promo_confirm_"))
    application.add_handler(CallbackQueryHandler(admin_delete_promo_execute, pattern="^admin_delete_promo_yes_"))
    
    # Callbacks admin - commandes
    application.add_handler(CallbackQueryHandler(admin_orders, pattern="^admin_orders$"))
    application.add_handler(CallbackQueryHandler(admin_orders_all, pattern="^admin_orders_all$"))
    application.add_handler(CallbackQueryHandler(admin_orders_pending, pattern="^admin_orders_pending$"))
    application.add_handler(CallbackQueryHandler(admin_orders_stats, pattern="^admin_orders_stats$"))
    
    # Callbacks admin - finances
    application.add_handler(CallbackQueryHandler(admin_finances, pattern="^admin_finances$"))
    application.add_handler(CallbackQueryHandler(admin_request_pay, pattern="^admin_request_pay$"))
    application.add_handler(CallbackQueryHandler(admin_add_expense, pattern="^admin_add_expense$"))
    application.add_handler(CallbackQueryHandler(expense_category_selected, pattern="^expense_cat_"))
    application.add_handler(CallbackQueryHandler(admin_finances_margins, pattern="^admin_finances_margins"))
    application.add_handler(CallbackQueryHandler(admin_finances_my_expenses, pattern="^admin_finances_my_expenses$"))
    application.add_handler(CallbackQueryHandler(admin_finances_all_expenses, pattern="^admin_finances_all_expenses$"))
    application.add_handler(CallbackQueryHandler(approve_expense, pattern="^approve_expense_"))
    application.add_handler(CallbackQueryHandler(reject_expense, pattern="^reject_expense_"))
    application.add_handler(CallbackQueryHandler(admin_expenses_approved, pattern="^admin_expenses_approved"))
    application.add_handler(CallbackQueryHandler(edit_expense, pattern="^edit_expense_"))
    application.add_handler(CallbackQueryHandler(delete_expense, pattern="^delete_expense_"))
    application.add_handler(CallbackQueryHandler(approve_payment, pattern="^approve_payment_"))
    application.add_handler(CallbackQueryHandler(reject_payment, pattern="^reject_payment_"))
    application.add_handler(CallbackQueryHandler(admin_finances_payroll, pattern="^admin_finances_payroll"))
    application.add_handler(CallbackQueryHandler(admin_finances_full_report, pattern="^admin_finances_full_report"))
    
    # Callbacks admin - prix de revient
    application.add_handler(CallbackQueryHandler(admin_costs, pattern="^admin_costs$"))
    application.add_handler(CallbackQueryHandler(admin_cost_edit, pattern="^admin_cost_edit_"))
    
    # Callbacks admin - gestion salaires
    application.add_handler(CallbackQueryHandler(admin_salary_config, pattern="^admin_salary_config$"))

    # Gestion VIP
    application.add_handler(CallbackQueryHandler(admin_vip_management, pattern="^admin_vip_management$"))
    application.add_handler(CallbackQueryHandler(vip_list_clients, pattern="^vip_list_clients$"))
    application.add_handler(CallbackQueryHandler(vip_grant_status, pattern="^vip_grant_status$"))
    application.add_handler(CallbackQueryHandler(vip_revoke_status, pattern="^vip_revoke_status$"))
    application.add_handler(CommandHandler("test_stock", test_stock_deduction))
    application.add_handler(CallbackQueryHandler(salary_admin_detail, pattern="^salary_admin_"))
    application.add_handler(CallbackQueryHandler(set_fixed_salary, pattern="^set_fixed_"))
    application.add_handler(CallbackQueryHandler(set_commission_type, pattern="^set_commission_"))
    application.add_handler(CallbackQueryHandler(set_commission_value, pattern="^commission_(percent|fixed|none)_"))
    application.add_handler(CallbackQueryHandler(set_frequency, pattern="^set_frequency_"))
    application.add_handler(CallbackQueryHandler(save_frequency, pattern="^freq_(monthly|weekly)_"))
    application.add_handler(CallbackQueryHandler(toggle_salary_active, pattern="^toggle_salary_"))
    application.add_handler(CallbackQueryHandler(salary_overview, pattern="^salary_overview$"))
    application.add_handler(CallbackQueryHandler(set_payment_day, pattern="^set_day_"))
    application.add_handler(CallbackQueryHandler(save_payment_day, pattern="^payday_"))
    
    # Callbacks admin - livre de comptes
    application.add_handler(CallbackQueryHandler(admin_ledger, pattern="^admin_ledger$"))
    application.add_handler(CallbackQueryHandler(ledger_view_weed, pattern="^ledger_view_weed$"))
    application.add_handler(CallbackQueryHandler(ledger_view_autres, pattern="^ledger_view_autres$"))
    application.add_handler(CallbackQueryHandler(ledger_reimport_split, pattern="^ledger_reimport_split$"))
    application.add_handler(CallbackQueryHandler(ledger_view_entries, pattern="^ledger_(income|expenses|all)$"))
    application.add_handler(CallbackQueryHandler(ledger_add_entry, pattern="^ledger_add_(income|expense)$"))
    application.add_handler(CallbackQueryHandler(ledger_select_category, pattern="^ledger_cat_"))
    application.add_handler(CallbackQueryHandler(ledger_edit_balance, pattern="^ledger_edit_balance$"))
    application.add_handler(CallbackQueryHandler(ledger_monthly_report, pattern="^ledger_monthly_report$"))
    application.add_handler(CallbackQueryHandler(ledger_import_history, pattern="^ledger_import_history$"))
    application.add_handler(CallbackQueryHandler(ledger_manage_duplicates, pattern="^ledger_manage_duplicates$"))
    application.add_handler(CallbackQueryHandler(ledger_clean_duplicate, pattern="^ledger_clean_dup_"))
    application.add_handler(CallbackQueryHandler(ledger_clean_all_duplicates, pattern="^ledger_clean_all_dups$"))
    
    # Callbacks admin - horaires
    application.add_handler(CallbackQueryHandler(admin_horaires, pattern="^admin_horaires$"))
    application.add_handler(CallbackQueryHandler(admin_horaires_toggle, pattern="^admin_horaires_toggle$"))
    application.add_handler(CallbackQueryHandler(admin_horaires_edit, pattern="^admin_horaires_edit$"))
    application.add_handler(CallbackQueryHandler(admin_horaires_edit_start, pattern="^admin_horaires_edit_start$"))
    application.add_handler(CallbackQueryHandler(admin_horaires_edit_end, pattern="^admin_horaires_edit_end$"))
    
    # Callbacks admin - admins
    application.add_handler(CallbackQueryHandler(admin_manage_admins, pattern="^admin_manage_admins$"))
    application.add_handler(CallbackQueryHandler(admin_list_admins, pattern="^admin_list_admins$"))
    application.add_handler(CallbackQueryHandler(admin_add_admin_start, pattern="^admin_add_admin$"))
    application.add_handler(CallbackQueryHandler(admin_level_selected, pattern="^admin_level_"))
    application.add_handler(CallbackQueryHandler(admin_remove_admin_start, pattern="^admin_remove_admin$"))
    
    # ===== HANDLERS ÉDITION COMPLÈTE =====
    application.add_handler(CallbackQueryHandler(admin_edit_menu, pattern="^admin_edit_menu$"))
    
    # Frais livraison
    application.add_handler(CallbackQueryHandler(edit_delivery_fees, pattern="^edit_delivery_fees$"))
    application.add_handler(CallbackQueryHandler(edit_fee_eu, pattern="^edit_fee_eu$"))
    application.add_handler(CallbackQueryHandler(edit_fee_au, pattern="^edit_fee_au$"))
    
    # Stocks
    application.add_handler(CallbackQueryHandler(edit_stocks_menu, pattern="^edit_stocks_menu$"))
    application.add_handler(CallbackQueryHandler(edit_stock, pattern="^editstock_"))
    
    # Prix
    application.add_handler(CallbackQueryHandler(edit_prices_simple, pattern="^edit_prices_simple$"))
    application.add_handler(CallbackQueryHandler(edit_price_select, pattern="^editprice_(?!.*_(FR|CH|AU)$)"))
    application.add_handler(CallbackQueryHandler(edit_price_country, pattern="^editprice_.*_(FR|CH|AU)$"))
    
    # Produits
    # Handler pour ajouter des produits (ConversationHandler - doit être avant les autres)
    application.add_handler(get_add_product_conversation_handler())
    
    application.add_handler(CallbackQueryHandler(edit_products_menu, pattern="^edit_products_menu$"))
    application.add_handler(CallbackQueryHandler(toggle_products, pattern="^toggle_products$"))
    application.add_handler(CallbackQueryHandler(toggle_product, pattern="^toggle_prod_"))
    
    # Config
    application.add_handler(CallbackQueryHandler(edit_config_menu, pattern="^edit_config_menu$"))
    application.add_handler(CallbackQueryHandler(edit_vip_threshold, pattern="^edit_vip_threshold$"))
    application.add_handler(CallbackQueryHandler(edit_vip_discount, pattern="^edit_vip_discount$"))
    
    # Liste produits
    application.add_handler(CallbackQueryHandler(list_products, pattern="^list_products$"))
    
    # Contact admin
    application.add_handler(CallbackQueryHandler(contact_admin_menu, pattern="^contact_admin_menu$"))
    application.add_handler(CallbackQueryHandler(contact_admin_selected, pattern="^contact_"))
    
    # Callbacks admin - paramètres
    application.add_handler(CallbackQueryHandler(admin_settings, pattern="^admin_settings$"))
    application.add_handler(CallbackQueryHandler(show_license_info, pattern="^show_license$"))
    application.add_handler(CallbackQueryHandler(admin_maintenance, pattern="^admin_maintenance$"))
    application.add_handler(CallbackQueryHandler(admin_maintenance_toggle, pattern="^admin_maintenance_(on|off)$"))
    
    # Callbacks admin - stats
    application.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_detailed_stats, pattern="^admin_detailed_stats$"))
    
    # Handler contact client par ID
    application.add_handler(CallbackQueryHandler(contact_user_by_id, pattern=r"^contact_user_\d+$"))
    
    # Handlers langue
    application.add_handler(CallbackQueryHandler(language_menu, pattern="^language_menu$"))
    application.add_handler(CallbackQueryHandler(set_language, pattern=r"^lang_[a-z]{2}$"))
    application.add_handler(CallbackQueryHandler(start_menu, pattern="^start_menu$"))
    
    # Handlers prix dégressifs
    application.add_handler(CallbackQueryHandler(tiered_country_menu, pattern=r"^tiered_country_"))
    application.add_handler(CallbackQueryHandler(tiered_product_menu, pattern=r"^tiered_product_"))
    application.add_handler(CallbackQueryHandler(tiered_add_tier, pattern=r"^tiered_add_[A-Z]{2}_"))
    application.add_handler(CallbackQueryHandler(tiered_delete_confirm, pattern=r"^tiered_delete_[A-Z]{2}_"))
    application.add_handler(CallbackQueryHandler(tiered_delete_execute, pattern=r"^tiered_delete_confirm_"))
    application.add_handler(CallbackQueryHandler(tiered_add_product, pattern=r"^tiered_add_product_"))
    application.add_handler(CallbackQueryHandler(tiered_add_country, pattern=r"^tiered_add_country$"))
    
    # Handlers auto-suppression
    application.add_handler(CallbackQueryHandler(admin_auto_delete_config, pattern="^admin_auto_delete_config$"))
    application.add_handler(CallbackQueryHandler(admin_auto_delete_toggle, pattern="^auto_delete_(enable|disable)$"))
    application.add_handler(CallbackQueryHandler(admin_auto_delete_set_delay, pattern="^auto_delete_delay_"))
    
    # Handlers ledger weed/autres
    application.add_handler(CallbackQueryHandler(ledger_add_weed_income, pattern="^ledger_add_weed_income$"))
    application.add_handler(CallbackQueryHandler(ledger_add_weed_expense, pattern="^ledger_add_weed_expense$"))
    application.add_handler(CallbackQueryHandler(ledger_add_other_income, pattern="^ledger_add_other_income$"))
    application.add_handler(CallbackQueryHandler(ledger_add_other_expense, pattern="^ledger_add_other_expense$"))
    application.add_handler(CallbackQueryHandler(ledger_select_weed_other_category, pattern=r"^ledger_(weed|other)_cat_"))
    
    # Handlers édition licence
    application.add_handler(CallbackQueryHandler(admin_edit_license, pattern="^admin_edit_license$"))
    
    # Message handlers (doit être en dernier)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    logger.info("✅ Tous les handlers configurés")

# ==================== KILL SWITCH ====================

async def kill_switch_check(application):
    """Kill switch: attend 30 secondes au démarrage"""
    logger.warning("⏳ KILL SWITCH ACTIVÉ - 30 secondes pour arrêter le bot avec Ctrl+C")
    
    for i in range(30, 0, -1):
        logger.info(f"⏱️  Démarrage dans {i}s...")
        await asyncio.sleep(1)
    
    logger.info("✅ Kill switch terminé - Démarrage du bot")

# ==================== FONCTION MAIN ====================


# ==================== SYSTÈME ÉDITION ADMIN COMPLET ====================

@error_handler
async def admin_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu principal édition"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("⛔ Réservé aux super admins", show_alert=True)
        return
    
    message = """✏️ ÉDITION COMPLÈTE

Vous pouvez tout modifier :

📦 Produits (ajouter/modifier/supprimer)
💰 Prix (tous les pays)
📊 Stocks
🚚 Frais de livraison
⚙️ Configuration système

Choisissez ce que vous voulez éditer :
"""
    
    keyboard = [
        [InlineKeyboardButton("📦 Produits", callback_data="edit_products_menu")],
        [InlineKeyboardButton("💰 Prix", callback_data="edit_prices_simple")],
        [InlineKeyboardButton("📊 Stocks", callback_data="edit_stocks_menu")],
        [InlineKeyboardButton("🚚 Frais", callback_data="edit_delivery_fees")],
        [InlineKeyboardButton("⚙️ Config", callback_data="edit_config_menu")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_panel")]
    ]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

# ===== FRAIS LIVRAISON =====

@error_handler
async def edit_delivery_fees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu frais livraison"""
    query = update.callback_query
    await query.answer()
    
    message = f"""🚚 FRAIS DE LIVRAISON

Actuels :
📮 Postal EU : {FRAIS_POSTAL_EU}€
📮 Postal AU : {FRAIS_POSTAL_AU}€
🤝 Meetup : {FRAIS_MEETUP}€

Que modifier ?
"""
    
    keyboard = [
        [InlineKeyboardButton("📮 Postal EU", callback_data="edit_fee_eu")],
        [InlineKeyboardButton("📮 Postal AU", callback_data="edit_fee_au")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_edit_menu")]
    ]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def edit_fee_eu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Éditer frais EU"""
    query = update.callback_query
    await query.answer()
    
    message = f"""📮 FRAIS POSTAL EU

Actuel : {FRAIS_POSTAL_EU}€

Entrez nouveau montant :
Exemple : 12

/cancel pour annuler
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="edit_delivery_fees")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    context.user_data['edit_fee_type'] = 'eu'
    context.user_data['awaiting_fee'] = True

@error_handler
async def edit_fee_au(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Éditer frais AU"""
    query = update.callback_query
    await query.answer()
    
    message = f"""📮 FRAIS POSTAL AUSTRALIE

Actuel : {FRAIS_POSTAL_AU}€

Entrez nouveau montant :
Exemple : 35

/cancel pour annuler
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="edit_delivery_fees")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    context.user_data['edit_fee_type'] = 'au'
    context.user_data['awaiting_fee'] = True

@error_handler
async def receive_fee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reçoit nouveau frais"""
    global FRAIS_POSTAL_EU, FRAIS_POSTAL_AU, FRAIS_POSTAL
    
    if not context.user_data.get('awaiting_fee'):
        return
    
    try:
        new_fee = float(update.message.text.strip())
        if new_fee < 0:
            raise ValueError
        
        fee_type = context.user_data.get('edit_fee_type')
        
        if fee_type == 'eu':
            old = FRAIS_POSTAL_EU
            FRAIS_POSTAL_EU = new_fee
            FRAIS_POSTAL = new_fee
            name = "Postal EU"
        else:
            old = FRAIS_POSTAL_AU
            FRAIS_POSTAL_AU = new_fee
            name = "Postal AU"
        
        # Sauvegarder
        CONFIG_DATA['delivery_fees'] = {
            'postal_eu': FRAIS_POSTAL_EU,
            'postal_au': FRAIS_POSTAL_AU,
            'meetup': FRAIS_MEETUP
        }
        save_json_file(CONFIG_FILE, CONFIG_DATA)
        
        message = f"""✅ FRAIS MIS À JOUR

{name}
Ancien : {old}€
Nouveau : {new_fee}€
"""
        
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="edit_delivery_fees")]]
        
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        context.user_data['awaiting_fee'] = False
        logger.info(f"✏️ Frais {name} : {old}€ → {new_fee}€ par {update.effective_user.id}")
        
    except:
        await update.message.reply_text("❌ Montant invalide")

# ===== STOCKS =====

@error_handler
async def edit_stocks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu stocks"""
    query = update.callback_query
    await query.answer()
    
    products = PRODUCTS_DATA.get('products', {})
    
    message = f"""📊 GESTION STOCKS

Total : {len(products)} produits

Sélectionnez produit :
"""
    
    keyboard = []
    for product_id, product_data in list(products.items())[:15]:
        name = product_data.get('name', {}).get('fr', product_id)
        stock = product_data.get('quantity', 0)  # CORRECTION: 'quantity' au lieu de 'stock'
        emoji = "🔴" if stock < 20 else "⚠️" if stock < 50 else "✅"
        keyboard.append([InlineKeyboardButton(f"{emoji} {name} ({stock}g)", callback_data=f"editstock_{product_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_edit_menu")])
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def edit_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Éditer stock"""
    query = update.callback_query
    await query.answer()
    
    product_id = query.data.replace('editstock_', '')
    products = PRODUCTS_DATA.get('products', {})
    product = products.get(product_id)
    
    if not product:
        await query.answer("❌ Produit introuvable", show_alert=True)
        return
    
    name = product.get('name', {}).get('fr', product_id)
    stock = product.get('quantity', 0)  # CORRECTION: 'quantity' au lieu de 'stock'
    
    message = f"""📦 MODIFIER STOCK

Produit : {name}
Stock actuel : {stock}g

Entrez nouveau stock (g) :
Exemple : 150

/cancel pour annuler
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="edit_stocks_menu")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    context.user_data['edit_stock_id'] = product_id
    context.user_data['awaiting_stock_edit'] = True

@error_handler
async def receive_stock_edition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reçoit nouveau stock"""
    
    if not context.user_data.get('awaiting_stock_edit'):
        return
    
    product_id = context.user_data.get('edit_stock_id')
    
    try:
        new_stock = float(update.message.text.strip())
        if new_stock < 0:
            raise ValueError
        
        products = PRODUCTS_DATA.get('products', {})
        product = products.get(product_id)
        
        if not product:
            await update.message.reply_text("❌ Produit introuvable")
            return
        
        old_stock = product.get('quantity', 0)  # CORRECTION
        product['quantity'] = new_stock  # CORRECTION
        
        PRODUCTS_DATA['products'] = products
        save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)
        reload_products()
        
        name = product.get('name', {}).get('fr', product_id)
        
        message = f"""✅ STOCK MODIFIÉ

{name}
Ancien : {old_stock}g
Nouveau : {new_stock}g
"""
        
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="edit_stocks_menu")]]
        
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        context.user_data['awaiting_stock_edit'] = False
        logger.info(f"✏️ Stock {product_id} : {old_stock}g → {new_stock}g")
        
    except:
        await update.message.reply_text("❌ Valeur invalide")

# ===== PRIX SIMPLE =====

@error_handler
async def edit_prices_simple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu prix simple"""
    query = update.callback_query
    await query.answer()
    
    products = PRODUCTS_DATA.get('products', {})
    
    message = f"""💰 MODIFIER PRIX

Total : {len(products)} produits

Sélectionnez produit :
"""
    
    keyboard = []
    for product_id, product_data in list(products.items())[:15]:
        name = product_data.get('name', {}).get('fr', product_id)
        keyboard.append([InlineKeyboardButton(name, callback_data=f"editprice_{product_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_edit_menu")])
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def edit_price_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélectionner pays pour prix"""
    query = update.callback_query
    await query.answer()
    
    product_id = query.data.replace('editprice_', '')
    products = PRODUCTS_DATA.get('products', {})
    product = products.get(product_id)
    
    if not product:
        await query.answer("❌ Produit introuvable", show_alert=True)
        return
    
    name = product.get('name', {}).get('fr', product_id)
    prices = product.get('price', {})  # CORRECTION: 'price' au lieu de 'prices'
    
    message = f"""💰 MODIFIER PRIX

Produit : {name}

Prix actuels :
🇫🇷 FR : {prices.get('FR', 0)}€
🇨🇭 CH : {prices.get('CH', 0)}€
🇦🇺 AU : {prices.get('AU', 0)}€

Quel pays modifier ?
"""
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data=f"editprice_{product_id}_FR")],
        [InlineKeyboardButton("🇨🇭 Suisse", callback_data=f"editprice_{product_id}_CH")],
        [InlineKeyboardButton("🇦🇺 Australie", callback_data=f"editprice_{product_id}_AU")],
        [InlineKeyboardButton("🔙 Retour", callback_data="edit_prices_simple")]
    ]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def edit_price_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Éditer prix pour un pays"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.replace('editprice_', '').split('_')
    country = parts[-1]
    product_id = '_'.join(parts[:-1])
    
    products = PRODUCTS_DATA.get('products', {})
    product = products.get(product_id)
    
    if not product:
        await query.answer("❌ Produit introuvable", show_alert=True)
        return
    
    name = product.get('name', {}).get('fr', product_id)
    current_price = product.get('price', {}).get(country, 0)  # CORRECTION
    
    country_names = {'FR': 'France', 'CH': 'Suisse', 'AU': 'Australie'}
    
    message = f"""💰 MODIFIER PRIX {country_names.get(country, country)}

Produit : {name}
Prix actuel : {current_price}€

Entrez nouveau prix :
Exemple : 65

/cancel pour annuler
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data=f"editprice_{product_id}")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    context.user_data['edit_price_id'] = product_id
    context.user_data['edit_price_country'] = country
    context.user_data['awaiting_price_edit'] = True

@error_handler
async def receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reçoit nouveau prix"""
    
    if not context.user_data.get('awaiting_price_edit'):
        return
    
    product_id = context.user_data.get('edit_price_id')
    country = context.user_data.get('edit_price_country')
    
    try:
        new_price = float(update.message.text.strip())
        if new_price <= 0:
            raise ValueError
        
        products = PRODUCTS_DATA.get('products', {})
        product = products.get(product_id)
        
        if not product:
            await update.message.reply_text("❌ Produit introuvable")
            return
        
        old_price = product.get('price', {}).get(country, 0)  # CORRECTION
        product['price'][country] = new_price  # CORRECTION
        
        PRODUCTS_DATA['products'] = products
        save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)
        reload_products()
        
        name = product.get('name', {}).get('fr', product_id)
        
        message = f"""✅ PRIX MODIFIÉ

{name} ({country})
Ancien : {old_price}€
Nouveau : {new_price}€
"""
        
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data=f"editprice_{product_id}")]]
        
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        context.user_data['awaiting_price_edit'] = False
        logger.info(f"✏️ Prix {product_id} {country} : {old_price}€ → {new_price}€")
        
    except:
        await update.message.reply_text("❌ Valeur invalide")

# ==================== AJOUT DE PRODUITS VIA BOT ====================
# À intégrer dans votre bot.py

# États pour la conversation d'ajout de produit
PRODUCT_NAME, PRODUCT_PRICE_FR, PRODUCT_PRICE_CH, PRODUCT_PRICE_AU, PRODUCT_QUANTITY, PRODUCT_CATEGORY = range(6)

# ===== FONCTIONS UTILITAIRES =====

def generate_product_id():
    """Génère un ID unique pour un nouveau produit"""
    products = PRODUCTS_DATA.get('products', {})
    if not products:
        return "P001"
    
    # Extraire les numéros existants
    existing_ids = []
    for pid in products.keys():
        if pid.startswith('P') and pid[1:].isdigit():
            existing_ids.append(int(pid[1:]))
    
    if not existing_ids:
        return "P001"
    
    next_id = max(existing_ids) + 1
    return f"P{next_id:03d}"

def add_product_to_json(product_data: dict) -> bool:
    """Ajoute un produit au fichier products.json et au product_registry.json"""
    try:
        # Récupérer et retirer l'ID du dictionnaire
        product_id = product_data.pop('id')
        product_name_fr = product_data['name']['fr']
        product_category = product_data.get('category', 'powder')
        
        logger.info(f"📝 Ajout produit {product_id}: {product_name_fr}")
        
        # 1. Ajouter au products.json
        products = PRODUCTS_DATA.get('products', {})
        products[product_id] = product_data
        PRODUCTS_DATA['products'] = products
        success = save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)
        
        if not success:
            logger.error("❌ Échec sauvegarde products.json")
            return False
        
        logger.info("✅ Sauvegarde products.json OK")
        
        # 2. Ajouter au product_registry.json
        registry = load_product_registry()
        registry[product_id] = {
            "name": product_name_fr,
            "category": product_category,
            "hash": hashlib.sha256(product_name_fr.encode()).hexdigest()[:8]
        }
        save_product_registry(registry)
        logger.info("✅ Sauvegarde product_registry.json OK")
        
        # 3. Vérifier les types avant reload
        logger.info(f"🔍 Type de PRIX_FR avant reload: {type(PRIX_FR)}")
        logger.info(f"🔍 Type de PRIX_CH avant reload: {type(PRIX_CH)}")
        logger.info(f"🔍 A reload? {hasattr(PRIX_FR, 'reload')}")
        
        # 4. Recharger tout
        reload_products()
        init_product_codes()
        
        # 5. Vérifier que le produit est bien accessible
        logger.info(f"🔍 Vérification après ajout:")
        logger.info(f"   • Produit dans PRIX_FR? {product_name_fr in PRIX_FR}")
        logger.info(f"   • Prix FR: {PRIX_FR.get(product_name_fr, 'NON TROUVÉ')}")
        logger.info(f"   • Produit dans available? {product_name_fr in load_available_products()}")
        logger.info(f"   • Total produits disponibles: {len(load_available_products())}")
        
        logger.info(f"✅ Produit {product_id} ajouté avec succès")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur ajout produit: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# ===== HANDLERS DE CONVERSATION =====

@error_handler
async def start_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Démarre le processus d'ajout de produit"""
    query = update.callback_query
    await query.answer()
    
    message = """➕ AJOUTER UN PRODUIT

Étape 1/5 : Nom du produit

Entrez le nom du produit en français :
(ex: Cocaïne Rock, Cocaïne Poudre, MDMA Cristaux)"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="cancel_add_product")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    return PRODUCT_NAME

@error_handler
async def product_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupère le nom du produit"""
    name = update.message.text.strip()
    
    # Vérifier si le produit existe déjà
    products = PRODUCTS_DATA.get('products', {})
    for product_data in products.values():
        if product_data.get('name', {}).get('fr', '').lower() == name.lower():
            await update.message.reply_text(
                f"⚠️ Un produit avec ce nom existe déjà !\n\n"
                f"Veuillez choisir un autre nom :"
            )
            return PRODUCT_NAME
    
    # Stocker le nom
    context.user_data['new_product'] = {
        'name_fr': name
    }
    
    message = f"""✅ Nom : {name}

Étape 2/5 : Prix France (€)

Entrez le prix pour la France en euros :
(ex: 50 ou 50.00)"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="cancel_add_product")]]
    
    await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    return PRODUCT_PRICE_FR

@error_handler
async def product_price_fr_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupère le prix France"""
    try:
        price = float(update.message.text.replace(',', '.'))
        
        if price <= 0:
            await update.message.reply_text(
                "❌ Le prix doit être supérieur à 0.\n\n"
                "Veuillez entrer un prix valide :"
            )
            return PRODUCT_PRICE_FR
        
        context.user_data['new_product']['price_fr'] = price
        
        name = context.user_data['new_product']['name_fr']
        message = f"""✅ Nom : {name}
✅ Prix France : {price}€

Étape 3/5 : Prix Suisse (CHF)

Entrez le prix pour la Suisse en francs suisses :
(ex: 55 ou 55.00)"""
        
        keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="cancel_add_product")]]
        
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        return PRODUCT_PRICE_CH
        
    except ValueError:
        await update.message.reply_text(
            "❌ Prix invalide. Veuillez entrer un nombre.\n"
            "(ex: 50 ou 50.00)"
        )
        return PRODUCT_PRICE_FR

@error_handler
async def product_price_ch_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupère le prix Suisse"""
    try:
        price = float(update.message.text.replace(',', '.'))
        
        if price <= 0:
            await update.message.reply_text(
                "❌ Le prix doit être supérieur à 0.\n\n"
                "Veuillez entrer un prix valide :"
            )
            return PRODUCT_PRICE_CH
        
        context.user_data['new_product']['price_ch'] = price
        
        name = context.user_data['new_product']['name_fr']
        price_fr = context.user_data['new_product']['price_fr']
        message = f"""✅ Nom : {name}
✅ Prix France : {price_fr}€
✅ Prix Suisse : {price} CHF

Étape 4/5 : Prix Autres pays (€)

Entrez le prix pour les autres pays en euros :
(ex: 60 ou 60.00)"""
        
        keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="cancel_add_product")]]
        
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        return PRODUCT_PRICE_AU
        
    except ValueError:
        await update.message.reply_text(
            "❌ Prix invalide. Veuillez entrer un nombre.\n"
            "(ex: 55 ou 55.00)"
        )
        return PRODUCT_PRICE_CH

@error_handler
async def product_price_au_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupère le prix Autres pays"""
    try:
        price = float(update.message.text.replace(',', '.'))
        
        if price <= 0:
            await update.message.reply_text(
                "❌ Le prix doit être supérieur à 0.\n\n"
                "Veuillez entrer un prix valide :"
            )
            return PRODUCT_PRICE_AU
        
        context.user_data['new_product']['price_au'] = price
        
        name = context.user_data['new_product']['name_fr']
        price_fr = context.user_data['new_product']['price_fr']
        price_ch = context.user_data['new_product']['price_ch']
        message = f"""✅ Nom : {name}
✅ Prix France : {price_fr}€
✅ Prix Suisse : {price_ch} CHF
✅ Prix Autres : {price}€

Étape 5/5 : Quantité disponible

Entrez la quantité disponible en grammes :
(ex: 1000 pour 1kg)"""
        
        keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="cancel_add_product")]]
        
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        return PRODUCT_QUANTITY
        
    except ValueError:
        await update.message.reply_text(
            "❌ Prix invalide. Veuillez entrer un nombre.\n"
            "(ex: 60 ou 60.00)"
        )
        return PRODUCT_PRICE_AU

@error_handler
async def product_quantity_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupère la quantité et demande la catégorie"""
    try:
        quantity = int(update.message.text)
        
        if quantity < 0:
            await update.message.reply_text(
                "❌ La quantité ne peut pas être négative.\n\n"
                "Veuillez entrer une quantité valide :"
            )
            return PRODUCT_QUANTITY
        
        context.user_data['new_product']['quantity'] = quantity
        
        # Afficher les catégories disponibles
        name = context.user_data['new_product']['name_fr']
        price_fr = context.user_data['new_product']['price_fr']
        price_ch = context.user_data['new_product']['price_ch']
        price_au = context.user_data['new_product']['price_au']
        
        message = f"""✅ Nom : {name}
✅ Prix France : {price_fr}€
✅ Prix Suisse : {price_ch} CHF
✅ Prix Autres : {price_au}€
✅ Quantité : {quantity}g

📂 Sélectionnez la catégorie du produit :"""
        
        keyboard = [
            [InlineKeyboardButton("💊 Pilules", callback_data="cat_pill")],
            [InlineKeyboardButton("🪨 Rocks", callback_data="cat_rock")],
            [InlineKeyboardButton("💨 Poudres", callback_data="cat_powder")],
            [InlineKeyboardButton("💎 Cristaux", callback_data="cat_crystal")],
            [InlineKeyboardButton("🌿 Herbes", callback_data="cat_herb")],
            [InlineKeyboardButton("🫒 Hash", callback_data="cat_hash")],
            [InlineKeyboardButton("🧪 Liquides", callback_data="cat_liquid")],
            [InlineKeyboardButton("❌ Annuler", callback_data="cancel_add_product")]
        ]
        
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        return PRODUCT_CATEGORY
        
    except ValueError:
        await update.message.reply_text(
            "❌ Quantité invalide. Veuillez entrer un nombre entier.\n"
            "(ex: 1000)"
        )
        return PRODUCT_QUANTITY

@error_handler
async def product_category_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finalise l'ajout du produit"""
    query = update.callback_query
    await query.answer()
    
    # Récupérer la catégorie
    category_map = {
        'cat_pill': 'pill',
        'cat_rock': 'rock',
        'cat_powder': 'powder',
        'cat_crystal': 'crystal',
        'cat_herb': 'herb',
        'cat_hash': 'hash',
        'cat_liquid': 'liquid'
    }
    
    category = category_map.get(query.data)
    if not category:
        await query.answer("❌ Catégorie invalide", show_alert=True)
        return ConversationHandler.END
    
    # Récupérer toutes les données
    product_data = context.user_data['new_product']
    product_id = generate_product_id()
    
    # Construire l'objet produit selon le format de votre JSON
    new_product = {
        "name": {
            "fr": product_data['name_fr'],
            "en": product_data['name_fr'],  # Par défaut, même nom
            "es": product_data['name_fr'],
            "de": product_data['name_fr']
        },
        "price": {
            "FR": product_data['price_fr'],
            "CH": product_data['price_ch'],
            "AU": product_data['price_au']
        },
        "quantity": product_data['quantity'],
        "available_quantities": [1.0, 2.0, 3.0, 5.0, 10.0, 25.0, 50.0, 100.0],  # Quantités standard
        "category": category,
        "active": True,
        "created_at": datetime.now().isoformat(),
        "alert_threshold": 20
    }
    
    # Ajouter l'ID
    new_product_with_id = {'id': product_id, **new_product}
    
    # Sauvegarder dans products.json
    success = add_product_to_json(new_product_with_id)
    
    if success:
        category_emoji = {
            'pill': '💊',
            'rock': '🪨',
            'powder': '💨',
            'crystal': '💎',
            'herb': '🌿',
            'hash': '🫒',
            'liquid': '🧪'
        }
        
        message = f"""✅ PRODUIT AJOUTÉ AVEC SUCCÈS !

🆔 ID : {product_id}
📦 Nom : {product_data['name_fr']}
📂 Catégorie : {category_emoji.get(category, '📦')} {category.capitalize()}
💰 Prix FR : {product_data['price_fr']}€
💰 Prix CH : {product_data['price_ch']} CHF
💰 Prix AU : {product_data['price_au']}€
📊 Stock : {product_data['quantity']}g

Le produit est maintenant disponible dans le catalogue !"""
        
        keyboard = [
            [InlineKeyboardButton("➕ Ajouter un autre", callback_data="add_product")],
            [InlineKeyboardButton("📋 Voir les produits", callback_data="list_products")],
            [InlineKeyboardButton("🏠 Menu admin", callback_data="admin_edit_menu")]
        ]
        
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
    else:
        message = """❌ ERREUR LORS DE L'AJOUT

Une erreur s'est produite lors de la sauvegarde.
Veuillez réessayer."""
        
        keyboard = [
            [InlineKeyboardButton("🔄 Réessayer", callback_data="add_product")],
            [InlineKeyboardButton("🏠 Menu admin", callback_data="admin_edit_menu")]
        ]
        
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Nettoyer les données temporaires
    context.user_data.clear()
    
    return ConversationHandler.END

@error_handler
async def cancel_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annule l'ajout de produit"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    message = "❌ Ajout de produit annulé."
    keyboard = [[InlineKeyboardButton("🏠 Menu admin", callback_data="admin_edit_menu")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

# ===== HANDLER À AJOUTER DANS LA FONCTION MAIN() =====

def get_add_product_conversation_handler():
    """Retourne le ConversationHandler pour ajouter un produit"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_product, pattern="^add_product$")
        ],
        states={
            PRODUCT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, product_name_received)
            ],
            PRODUCT_PRICE_FR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, product_price_fr_received)
            ],
            PRODUCT_PRICE_CH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, product_price_ch_received)
            ],
            PRODUCT_PRICE_AU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, product_price_au_received)
            ],
            PRODUCT_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, product_quantity_received)
            ],
            PRODUCT_CATEGORY: [
                CallbackQueryHandler(product_category_received, pattern="^cat_")
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_add_product, pattern="^cancel_add_product$")
        ],
        allow_reentry=True
    )

@error_handler
async def edit_products_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu produits"""
    query = update.callback_query
    await query.answer()
    
    products = PRODUCTS_DATA.get('products', {})
    
    message = f"""📦 GESTION PRODUITS

Total : {len(products)} produits

Actions disponibles :
"""
    
    keyboard = [
        [InlineKeyboardButton("➕ Ajouter un produit", callback_data="add_product")],
        [InlineKeyboardButton("👁️ Activer/Désactiver", callback_data="toggle_products")],
        [InlineKeyboardButton("📋 Liste complète", callback_data="list_products")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_edit_menu")]
    ]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))


@error_handler
async def toggle_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activer/Désactiver produits"""
    query = update.callback_query
    await query.answer()
    
    products = PRODUCTS_DATA.get('products', {})
    
    message = """👁️ ACTIVER/DÉSACTIVER

Sélectionnez produit :
"""
    
    keyboard = []
    for product_id, product_data in list(products.items())[:15]:
        name = product_data.get('name', {}).get('fr', product_id)
        active = product_data.get('active', True)
        emoji = "✅" if active else "❌"
        keyboard.append([InlineKeyboardButton(f"{emoji} {name}", callback_data=f"toggle_prod_{product_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="edit_products_menu")])
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def toggle_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle produit"""
    query = update.callback_query
    await query.answer()
    
    product_id = query.data.replace('toggle_prod_', '')
    products = PRODUCTS_DATA.get('products', {})
    product = products.get(product_id)
    
    if not product:
        await query.answer("❌ Produit introuvable", show_alert=True)
        return
    
    name = product.get('name', {}).get('fr', product_id)
    active = product.get('active', True)
    
    # Toggle
    product['active'] = not active
    
    PRODUCTS_DATA['products'] = products
    save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)
    reload_products()
    
    new_state = "activé" if not active else "désactivé"
    
    await query.answer(f"✅ {name} {new_state}", show_alert=True)
    
    # Refresh menu
    await toggle_products(update, context)
    
    logger.info(f"✏️ Produit {product_id} : {new_state}")

# ===== CONFIG =====

@error_handler
async def edit_config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu configuration"""
    query = update.callback_query
    await query.answer()
    
    message = f"""⚙️ CONFIGURATION

Paramètres actuels :

💰 Seuil VIP : {VIP_THRESHOLD}€
🎁 Réduction VIP : {VIP_DISCOUNT}%
🛒 Max panier : {MAX_CART_ITEMS}
💰 Min commande : {MIN_ORDER_AMOUNT}€

Que modifier ?
"""
    
    keyboard = [
        [InlineKeyboardButton("💰 Seuil VIP", callback_data="edit_vip_threshold")],
        [InlineKeyboardButton("🎁 Réduction VIP", callback_data="edit_vip_discount")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_edit_menu")]
    ]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def edit_vip_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Éditer seuil VIP"""
    query = update.callback_query
    await query.answer()
    
    message = f"""💰 SEUIL VIP

Actuel : {VIP_THRESHOLD}€

Entrez nouveau seuil :
Exemple : 600

/cancel pour annuler
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="edit_config_menu")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    context.user_data['edit_config_type'] = 'vip_threshold'
    context.user_data['awaiting_config'] = True

@error_handler
async def edit_vip_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Éditer réduction VIP"""
    query = update.callback_query
    await query.answer()
    
    message = f"""🎁 RÉDUCTION VIP

Actuelle : {VIP_DISCOUNT}%

Entrez nouvelle réduction (%) :
Exemple : 7

/cancel pour annuler
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="edit_config_menu")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    context.user_data['edit_config_type'] = 'vip_discount'
    context.user_data['awaiting_config'] = True

@error_handler
async def receive_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reçoit config"""
    global VIP_THRESHOLD, VIP_DISCOUNT
    
    if not context.user_data.get('awaiting_config'):
        return
    
    config_type = context.user_data.get('edit_config_type')
    
    try:
        new_value = float(update.message.text.strip())
        if new_value <= 0:
            raise ValueError
        
        if config_type == 'vip_threshold':
            old = VIP_THRESHOLD
            VIP_THRESHOLD = new_value
            CONFIG_DATA['vip_threshold'] = VIP_THRESHOLD
            name = "Seuil VIP"
            unit = "€"
        elif config_type == 'vip_discount':
            old = VIP_DISCOUNT
            VIP_DISCOUNT = new_value
            CONFIG_DATA['vip_discount'] = VIP_DISCOUNT
            name = "Réduction VIP"
            unit = "%"
        
        save_json_file(CONFIG_FILE, CONFIG_DATA)
        
        message = f"""✅ {name.upper()} MODIFIÉ

Ancien : {old}{unit}
Nouveau : {new_value}{unit}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="edit_config_menu")]]
        
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        context.user_data['awaiting_config'] = False
        logger.info(f"✏️ Config {name} : {old} → {new_value}")
        
    except:
        await update.message.reply_text("❌ Valeur invalide")


@error_handler
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liste tous les produits"""
    query = update.callback_query
    await query.answer()
    
    products = PRODUCTS_DATA.get('products', {})
    
    message = """📋 LISTE PRODUITS

"""
    
    for product_id, product_data in products.items():
        name = product_data.get('name', {}).get('fr', product_id)
        active = "✅" if product_data.get('active', True) else "❌"
        stock = product_data.get('quantity', 0)  # CORRECTION
        prices_fr = product_data.get('price', {}).get('FR', 0)  # CORRECTION: 'price' au lieu de 'prices'
        message += f"{active} {name}\n  Stock: {stock}g | Prix FR: {prices_fr}€\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="edit_products_menu")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))


# ==================== CONTACT ADMIN ====================

@error_handler
async def contact_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu contact admin"""
    query = update.callback_query
    await query.answer()
    
    # Charger tous les admins
    admins = load_admins()
    
    message = """📞 CONTACTER UN ADMIN

Choisissez l'admin à contacter :

"""
    
    keyboard = []
    
    for admin_id, admin_data in admins.items():
        if admin_data.get('active', True):
            name = admin_data.get('name', f'Admin {admin_id}')
            level = admin_data.get('level', 'admin')
            
            level_emoji = {
                'super_admin': '👑',
                'admin': '👤',
                'support': '💬'
            }.get(level, '👤')
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{level_emoji} {name}",
                    callback_data=f"contact_{admin_id}"
                )
            ])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="back_to_main")])
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@error_handler
async def contact_admin_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin sélectionné pour contact"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.data.replace('contact_', '')
    
    # Récupérer infos admin
    admins = load_admins()
    admin_data = admins.get(admin_id, {})
    admin_name = admin_data.get('name', 'Admin')
    
    message = f"""📞 CONTACTER {admin_name.upper()}

Entrez votre message :

L'admin recevra votre message avec votre contact.

💡 Tapez /cancel pour annuler
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="contact_admin_menu")]]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    context.user_data['contact_admin_id'] = admin_id
    context.user_data['contact_admin_name'] = admin_name
    context.user_data['awaiting_contact_message'] = True

@error_handler
async def receive_contact_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reçoit message de contact"""
    
    if not context.user_data.get('awaiting_contact_message'):
        return
    
    user_id = update.effective_user.id
    user = update.effective_user
    user_name = user.first_name
    if user.last_name:
        user_name += f" {user.last_name}"
    if user.username:
        user_name += f" (@{user.username})"
    
    message_text = update.message.text.strip()
    admin_id = context.user_data.get('contact_admin_id')
    admin_name = context.user_data.get('contact_admin_name')
    
    # Envoyer au admin
    admin_message = f"""📞 NOUVEAU CONTACT CLIENT

De : {user_name}
ID : {user_id}

Message :
{message_text}

━━━━━━━━━━━━━━━━━━━━━━

Répondez directement à ce message pour répondre au client.
"""
    
    try:
        await context.bot.send_message(
            chat_id=int(admin_id),
            text=admin_message
        )
        
        # Confirmer au client
        confirm_message = f"""✅ MESSAGE ENVOYÉ

Votre message a été envoyé à {admin_name}.

Vous serez contacté rapidement.
"""
        
        keyboard = [[InlineKeyboardButton("🔙 Menu principal", callback_data="back_to_main")]]
        
        await update.message.reply_text(
            confirm_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data['awaiting_contact_message'] = False
        
        logger.info(f"📞 Contact: User {user_id} → Admin {admin_id}")
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Erreur lors de l'envoi. Réessayez ou contactez un autre admin."
        )
        logger.error(f"Erreur contact admin: {e}")


@error_handler
async def contact_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permet de contacter un utilisateur en cliquant sur son ID"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    if not is_admin(user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    # Extraire l'ID utilisateur du callback
    target_user_id = int(query.data.replace("contact_user_", ""))
    
    # Récupérer les infos de l'utilisateur
    user_info = get_user_info(target_user_id)
    username = user_info.get('username', 'Unknown')
    first_name = user_info.get('first_name', 'User')
    
    text = f"""💬 CONTACTER UTILISATEUR

👤 {first_name} (@{username})
🆔 ID: {target_user_id}

Envoyez votre message:
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin")]]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Sauvegarder l'ID cible dans le contexte
    context.user_data['contact_target'] = target_user_id
    context.user_data['awaiting_contact_message'] = True

@error_handler
async def handle_contact_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère l'envoi du message de contact"""
    user = update.effective_user
    
    if not is_admin(user.id):
        return
    
    if not context.user_data.get('awaiting_contact_message'):
        return
    
    target_user_id = context.user_data.get('contact_target')
    if not target_user_id:
        await update.message.reply_text("❌ Session expirée")
        return
    
    message_text = update.message.text
    
    # Envoyer le message à l'utilisateur cible
    try:
        admin_name = user.first_name
        full_message = f"""📩 MESSAGE D'UN ADMIN

{message_text}

━━━━━━━━━━━━━━━
De: {admin_name} (Admin)
"""
        
        await context.bot.send_message(
            chat_id=target_user_id,
            text=full_message
        )
        
        await update.message.reply_text(
            "✅ Message envoyé avec succès !",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour Admin", callback_data="admin")
            ]])
        )
        
        logger.info(f"💬 Admin {user.id} a contacté user {target_user_id}")
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Erreur lors de l'envoi: {str(e)}"
        )
        logger.error(f"Erreur contact user: {e}")
    
    # Nettoyer
    context.user_data.pop('contact_target', None)
    context.user_data.pop('awaiting_contact_message', None)



@error_handler
async def admin_edit_license(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu d'édition de la licence"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    if not is_super_admin(user.id):
        await query.answer("❌ Accès refusé - Super Admin uniquement", show_alert=True)
        return
    
    license_level = get_license_level()
    
    text = f"""🔐 ÉDITION LICENCE

Niveau actuel: {license_level}

Pour modifier le niveau de licence, vous devez entrer le code Super Admin.

Envoyez le code:
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin")]]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_license_code'] = True

@error_handler
async def handle_license_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la saisie du code licence"""
    user = update.effective_user
    
    if not is_super_admin(user.id):
        return
    
    if not context.user_data.get('awaiting_license_code'):
        return
    
    code = update.message.text.strip()
    
    if code != SUPER_ADMIN_CODE:
        await update.message.reply_text(
            "❌ Code incorrect!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin")
            ]])
        )
        context.user_data.pop('awaiting_license_code', None)
        return
    
    # Code correct, demander le nouveau niveau
    context.user_data.pop('awaiting_license_code', None)
    context.user_data['license_code_verified'] = True
    
    current_level = get_license_level()
    
    text = f"""✅ CODE VÉRIFIÉ

Niveau actuel: {current_level}

Entrez le nouveau niveau de licence (1-10):
"""
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Annuler", callback_data="admin")
        ]])
    )
    
    context.user_data['awaiting_license_level'] = True

@error_handler
async def handle_license_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la saisie du niveau de licence"""
    user = update.effective_user
    
    if not is_super_admin(user.id):
        return
    
    if not context.user_data.get('awaiting_license_level'):
        return
    
    if not context.user_data.get('license_code_verified'):
        await update.message.reply_text("❌ Veuillez d'abord vérifier le code")
        return
    
    try:
        new_level = int(update.message.text.strip())
        
        if new_level < 1 or new_level > 10:
            raise ValueError("Niveau doit être entre 1 et 10")
        
        # Mettre à jour le niveau
        success = set_license_level(new_level)
        
        if success:
            await update.message.reply_text(
                f"✅ Niveau de licence mis à jour!\n\nNouveau niveau: {new_level}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour Admin", callback_data="admin")
                ]])
            )
            logger.info(f"🔐 Licence modifiée par {user.id}: niveau {new_level}")
        else:
            await update.message.reply_text("❌ Erreur lors de la mise à jour")
        
    except ValueError as e:
        await update.message.reply_text(f"❌ Niveau invalide: {e}")
        return
    
    # Nettoyer
    context.user_data.pop('awaiting_license_level', None)
    context.user_data.pop('license_code_verified', None)


def get_license_level():
    """Retourne le niveau de licence actuel"""
    license_data = load_json_file(LICENSE_FILE, {})
    return license_data.get('license', {}).get('level', 1)

def set_license_level(level: int) -> bool:
    """Définit le nouveau niveau de licence"""
    license_data = load_json_file(LICENSE_FILE, {})
    
    if 'license' not in license_data:
        license_data['license'] = {}
    
    license_data['license']['level'] = level
    license_data['license']['updated_at'] = datetime.now().isoformat()
    
    return save_json_file(LICENSE_FILE, license_data)



@error_handler
async def tiered_country_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu des prix dégressifs pour un pays"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    country = query.data.replace("tiered_country_", "")
    context.user_data['tiered_country'] = country
    
    country_flags = {'FR': '🇫🇷', 'CH': '🇨🇭', 'AU': '🇦🇺'}
    flag = country_flags.get(country, '🌍')
    
    tiered = load_tiered_pricing()
    country_tiers = tiered.get(country, {})
    
    products = PRODUCTS_DATA.get('products', {})
    
    message = f"""📊 PRIX DÉGRESSIFS {flag} {country}

Produits configurés: {len(country_tiers)}

Sélectionnez un produit:
"""
    
    keyboard = []
    
    # Liste des produits configurés
    for product_id, tiers in country_tiers.items():
        product_name = products.get(product_id, {}).get('name', {}).get('fr', product_id)
        tier_count = len(tiers)
        keyboard.append([
            InlineKeyboardButton(
                f"📦 {product_name} ({tier_count} paliers)",
                callback_data=f"tiered_product_{country}_{product_id}"
            )
        ])
    
    # Bouton pour ajouter un produit
    keyboard.append([
        InlineKeyboardButton("➕ Ajouter produit", callback_data=f"tiered_add_product_{country}")
    ])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing_tiers")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def tiered_product_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de gestion des paliers pour un produit"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    parts = query.data.replace("tiered_product_", "").split("_", 1)
    country = parts[0]
    product_id = parts[1]
    
    context.user_data['tiered_country'] = country
    context.user_data['tiered_product'] = product_id
    
    products = PRODUCTS_DATA.get('products', {})
    product_name = products.get(product_id, {}).get('name', {}).get('fr', product_id)
    
    tiered = load_tiered_pricing()
    tiers = tiered.get(country, {}).get(product_id, [])
    
    # Trier les paliers par quantité minimum
    sorted_tiers = sorted(tiers, key=lambda x: x.get('min_qty', 0))
    
    country_flags = {'FR': '🇫🇷', 'CH': '🇨🇭', 'AU': '🇦🇺'}
    flag = country_flags.get(country, '🌍')
    
    message = f"""📊 PRIX DÉGRESSIFS
{flag} {country} - {product_name}

Paliers configurés:

"""
    
    if sorted_tiers:
        for i, tier in enumerate(sorted_tiers):
            min_qty = tier.get('min_qty', 0)
            max_qty = tier.get('max_qty', 999999)
            price = tier.get('price', 0)
            
            max_display = f"{max_qty}g" if max_qty < 999999 else "∞"
            message += f"{i+1}. {min_qty}g - {max_display}: {price}€/g\n"
    else:
        message += "Aucun palier configuré.\n"
    
    message += "\nChoisissez une action:"
    
    keyboard = []
    
    # Boutons pour éditer/supprimer les paliers existants
    for i, tier in enumerate(sorted_tiers):
        min_qty = tier.get('min_qty', 0)
        max_qty = tier.get('max_qty', 999999)
        price = tier.get('price', 0)
        max_display = f"{max_qty}g" if max_qty < 999999 else "∞"
        
        keyboard.append([
            InlineKeyboardButton(
                f"✏️ {min_qty}-{max_display}: {price}€",
                callback_data=f"tiered_edit_{country}_{product_id}_{i}"
            ),
            InlineKeyboardButton(
                "🗑️",
                callback_data=f"tiered_delete_{country}_{product_id}_{i}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("➕ Ajouter palier", callback_data=f"tiered_add_{country}_{product_id}")
    ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 Retour", callback_data=f"tiered_country_{country}")
    ])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def tiered_add_tier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande les infos pour ajouter un palier"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    parts = query.data.replace("tiered_add_", "").split("_", 1)
    country = parts[0]
    product_id = parts[1]
    
    context.user_data['tiered_country'] = country
    context.user_data['tiered_product'] = product_id
    context.user_data['tiered_action'] = 'add'
    
    products = PRODUCTS_DATA.get('products', {})
    product_name = products.get(product_id, {}).get('name', {}).get('fr', product_id)
    
    message = f"""➕ AJOUTER PALIER

Produit: {product_name}
Pays: {country}

Envoyez les informations du palier au format:
`min_qty max_qty price`

Exemples:
• `1 10 50` = 1-10g à 50€/g
• `11 50 45` = 11-50g à 45€/g
• `51 999999 40` = 51g et + à 40€/g

Format: quantité_min quantité_max prix
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data=f"tiered_product_{country}_{product_id}")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_tiered_info'] = True

@error_handler
async def handle_tiered_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère l'ajout d'un palier de prix"""
    user = update.effective_user
    
    if not is_super_admin(user.id):
        return
    
    if not context.user_data.get('awaiting_tiered_info'):
        return
    
    country = context.user_data.get('tiered_country')
    product_id = context.user_data.get('tiered_product')
    
    if not country or not product_id:
        await update.message.reply_text("❌ Session expirée")
        return
    
    try:
        # Parser l'entrée: min_qty max_qty price
        parts = update.message.text.strip().split()
        
        if len(parts) != 3:
            raise ValueError("Format incorrect. Utilisez: min_qty max_qty price")
        
        min_qty = int(parts[0])
        max_qty = int(parts[1])
        price = float(parts[2])
        
        if min_qty < 0 or max_qty < min_qty or price < 0:
            raise ValueError("Valeurs invalides")
        
        # Ajouter le palier
        success = add_tiered_price(country, product_id, min_qty, max_qty, price)
        
        if success:
            products = PRODUCTS_DATA.get('products', {})
            product_name = products.get(product_id, {}).get('name', {}).get('fr', product_id)
            
            max_display = f"{max_qty}g" if max_qty < 999999 else "∞"
            
            await update.message.reply_text(
                f"✅ Palier ajouté!\n\n"
                f"📦 {product_name}\n"
                f"🌍 {country}\n"
                f"📊 {min_qty}g - {max_display}: {price}€/g",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data=f"tiered_product_{country}_{product_id}")
                ]])
            )
        else:
            await update.message.reply_text("❌ Erreur lors de l'ajout")
        
    except ValueError as e:
        await update.message.reply_text(
            f"❌ Erreur: {e}\n\n"
            f"Format attendu: min_qty max_qty price\n"
            f"Exemple: 1 10 50"
        )
        return
    
    # Nettoyer
    context.user_data.pop('awaiting_tiered_info', None)

@error_handler
async def tiered_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation de suppression d'un palier"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    parts = query.data.replace("tiered_delete_", "").split("_")
    country = parts[0]
    product_id = "_".join(parts[1:-1])
    tier_index = int(parts[-1])
    
    products = PRODUCTS_DATA.get('products', {})
    product_name = products.get(product_id, {}).get('name', {}).get('fr', product_id)
    
    tiered = load_tiered_pricing()
    tier = tiered.get(country, {}).get(product_id, [])[tier_index]
    
    min_qty = tier.get('min_qty', 0)
    max_qty = tier.get('max_qty', 999999)
    price = tier.get('price', 0)
    max_display = f"{max_qty}g" if max_qty < 999999 else "∞"
    
    message = f"""🗑️ SUPPRIMER PALIER

Produit: {product_name}
Pays: {country}

Palier: {min_qty}g - {max_display}: {price}€/g

⚠️ Confirmer la suppression?
"""
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirmer", callback_data=f"tiered_delete_confirm_{country}_{product_id}_{tier_index}"),
            InlineKeyboardButton("❌ Annuler", callback_data=f"tiered_product_{country}_{product_id}")
        ]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def tiered_delete_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exécute la suppression d'un palier"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    parts = query.data.replace("tiered_delete_confirm_", "").split("_")
    country = parts[0]
    product_id = "_".join(parts[1:-1])
    tier_index = int(parts[-1])
    
    success = remove_tiered_price(country, product_id, tier_index)
    
    if success:
        await query.answer("✅ Palier supprimé", show_alert=True)
    else:
        await query.answer("❌ Erreur suppression", show_alert=True)
    
    # Retourner au menu du produit
    await tiered_product_menu(update, context)

@error_handler
async def tiered_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection d'un produit pour ajouter des prix dégressifs"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    country = query.data.replace("tiered_add_product_", "")
    context.user_data['tiered_country'] = country
    
    products = PRODUCTS_DATA.get('products', {})
    tiered = load_tiered_pricing()
    country_tiers = tiered.get(country, {})
    
    message = f"""➕ AJOUTER PRODUIT

Pays: {country}

Sélectionnez un produit:
"""
    
    keyboard = []
    
    # Lister les produits pas encore configurés
    for product_id, product_data in products.items():
        if product_id not in country_tiers:
            product_name = product_data.get('name', {}).get('fr', product_id)
            keyboard.append([
                InlineKeyboardButton(
                    f"📦 {product_name}",
                    callback_data=f"tiered_add_{country}_{product_id}"
                )
            ])
    
    if not keyboard:
        message += "\n✅ Tous les produits sont déjà configurés!"
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data=f"tiered_country_{country}")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def tiered_add_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajouter un nouveau pays pour les prix dégressifs"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    message = """➕ AJOUTER PAYS

Envoyez le code pays (2 lettres):
Exemples: BE, NL, DE, IT, ES

/cancel pour annuler
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_pricing_tiers")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data['awaiting_new_country'] = True

@error_handler
async def handle_new_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère l'ajout d'un nouveau pays"""
    user = update.effective_user
    
    if not is_super_admin(user.id):
        return
    
    if not context.user_data.get('awaiting_new_country'):
        return
    
    country_code = update.message.text.strip().upper()
    
    # Valider le code pays
    if len(country_code) != 2 or not country_code.isalpha():
        await update.message.reply_text(
            "❌ Code pays invalide. Utilisez 2 lettres.\n"
            "Exemples: BE, NL, DE"
        )
        return
    
    # Ajouter le pays dans les prix dégressifs
    tiered = load_tiered_pricing()
    
    if country_code in tiered:
        await update.message.reply_text(
            f"⚠️ Le pays {country_code} existe déjà!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing_tiers")
            ]])
        )
    else:
        tiered[country_code] = {}
        save_tiered_pricing(tiered)
        
        await update.message.reply_text(
            f"✅ Pays {country_code} ajouté!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📊 Configurer", callback_data=f"tiered_country_{country_code}"),
                InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing_tiers")
            ]])
        )
    
    context.user_data.pop('awaiting_new_country', None)



# ==================== SYSTÈME AUTO-SUPPRESSION ====================

async def schedule_message_deletion(message, delay: int = AUTO_DELETE_DELAY, message_type: str = None):
    """
    Programme la suppression automatique d'un message après un délai
    
    Args:
        message: Le message Telegram à supprimer
        delay: Délai en secondes avant suppression (défaut: 10 minutes)
        message_type: Type de message (pour vérifier s'il doit être conservé)
    """
    # Ne pas supprimer si l'auto-suppression est désactivée
    if not AUTO_DELETE_ENABLED:
        return
    
    # Ne pas supprimer les messages importants
    if message_type and message_type in PERMANENT_MESSAGE_TYPES:
        logger.info(f"🔒 Message permanent conservé: {message_type}")
        return
    
    # Attendre le délai
    await asyncio.sleep(delay)
    
    # Supprimer le message
    try:
        await message.delete()
        logger.info(f"🗑️ Message auto-supprimé après {delay}s")
    except Exception as e:
        logger.warning(f"⚠️ Impossible de supprimer le message: {e}")

async def send_auto_delete_message(context, chat_id: int, text: str, reply_markup=None, 
                                   delay: int = AUTO_DELETE_DELAY, message_type: str = None,
                                   parse_mode=None):
    """
    Envoie un message qui sera automatiquement supprimé après un délai
    
    Args:
        context: Context Telegram
        chat_id: ID du chat destinataire
        text: Texte du message
        reply_markup: Clavier inline optionnel
        delay: Délai avant suppression
        message_type: Type de message (pour exceptions)
        parse_mode: Mode de parsing (Markdown, HTML, etc.)
    
    Returns:
        Le message envoyé
    """
    # Envoyer le message
    message = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    
    # Programmer la suppression si ce n'est pas un message permanent
    if message_type not in PERMANENT_MESSAGE_TYPES:
        asyncio.create_task(schedule_message_deletion(message, delay, message_type))
    
    return message

async def reply_auto_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                           text: str, reply_markup=None, 
                           delay: int = AUTO_DELETE_DELAY, message_type: str = None,
                           parse_mode=None):
    """
    Répond à un message avec auto-suppression
    
    Args:
        update: Update Telegram
        context: Context Telegram
        text: Texte de la réponse
        reply_markup: Clavier inline optionnel
        delay: Délai avant suppression
        message_type: Type de message
        parse_mode: Mode de parsing
    
    Returns:
        Le message envoyé
    """
    # Déterminer d'où vient la requête
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        # Supprimer aussi le message original
        try:
            await update.callback_query.message.delete()
        except:
            pass
    elif update.message:
        chat_id = update.message.chat_id
        # Supprimer aussi le message de l'utilisateur
        try:
            await update.message.delete()
        except:
            pass
    else:
        return None
    
    # Envoyer la réponse avec auto-suppression
    return await send_auto_delete_message(
        context=context,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        delay=delay,
        message_type=message_type,
        parse_mode=parse_mode
    )

async def edit_message_auto_delete(query, text: str, reply_markup=None,
                                   delay: int = AUTO_DELETE_DELAY, message_type: str = None,
                                   parse_mode=None):
    """
    Édite un message avec auto-suppression programmée
    
    Args:
        query: CallbackQuery
        text: Nouveau texte
        reply_markup: Nouveau clavier
        delay: Délai avant suppression
        message_type: Type de message
        parse_mode: Mode de parsing
    """
    # Éditer le message
    await query.edit_message_text(
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    
    # Programmer la suppression
    if message_type not in PERMANENT_MESSAGE_TYPES:
        asyncio.create_task(schedule_message_deletion(query.message, delay, message_type))

# Fonctions helper pour les notifications de commande (messages permanents)

async def send_order_notification(context, user_id: int, order_id: str, status: str, details: str = ""):
    """
    Envoie une notification de changement de statut de commande (PERMANENT)
    
    Args:
        context: Context Telegram
        user_id: ID de l'utilisateur
        order_id: ID de la commande
        status: Nouveau statut
        details: Détails supplémentaires
    """
    # Mapper les statuts aux types de messages permanents
    status_map = {
        'pending': 'order_status_pending',
        'validated': 'order_status_validated',
        'ready': 'order_status_ready',
        'delivered': 'order_status_delivered'
    }
    
    # Emojis pour chaque statut
    status_emoji = {
        'pending': '⏳',
        'validated': '✅',
        'ready': '📦',
        'delivered': '🎉'
    }
    
    # Messages pour chaque statut
    status_messages = {
        'pending': 'Votre commande est en attente de validation',
        'validated': 'Votre commande a été validée et est en préparation',
        'ready': 'Votre commande est prête !',
        'delivered': 'Votre commande a été livrée !'
    }
    
    emoji = status_emoji.get(status, '📬')
    status_msg = status_messages.get(status, 'Mise à jour de votre commande')
    message_type = status_map.get(status, 'order_notification')
    
    text = f"""{emoji} COMMANDE #{order_id}

{status_msg}

{details}

━━━━━━━━━━━━━━━
Ce message ne sera pas supprimé automatiquement.
"""
    
    # Envoyer sans auto-suppression (message permanent)
    message = await context.bot.send_message(
        chat_id=user_id,
        text=text
    )
    
    logger.info(f"📬 Notification commande envoyée (PERMANENT): User {user_id}, Order #{order_id}, Status: {status}")
    
    return message



@error_handler
async def admin_auto_delete_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configuration de l'auto-suppression des messages (Super Admin)"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé - Super Admin uniquement", show_alert=True)
        return
    
    global AUTO_DELETE_ENABLED, AUTO_DELETE_DELAY
    
    status = "✅ Activé" if AUTO_DELETE_ENABLED else "❌ Désactivé"
    delay_min = AUTO_DELETE_DELAY // 60
    
    message = f"""🗑️ AUTO-SUPPRESSION DES MESSAGES

Statut: {status}
Délai: {delay_min} minutes

Les messages sont automatiquement supprimés après {delay_min} minutes, SAUF:
• Notifications de commande en attente
• Notifications de commande validée
• Notifications de commande prête
• Notifications de commande livrée

Ces messages restent visibles pour que le client puisse suivre sa commande.

Que souhaitez-vous faire?
"""
    
    keyboard = []
    
    if AUTO_DELETE_ENABLED:
        keyboard.append([InlineKeyboardButton("❌ Désactiver", callback_data="auto_delete_disable")])
    else:
        keyboard.append([InlineKeyboardButton("✅ Activer", callback_data="auto_delete_enable")])
    
    keyboard.extend([
        [
            InlineKeyboardButton("⏱️ 5 min", callback_data="auto_delete_delay_300"),
            InlineKeyboardButton("⏱️ 10 min", callback_data="auto_delete_delay_600"),
            InlineKeyboardButton("⏱️ 30 min", callback_data="auto_delete_delay_1800")
        ],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin")]
    ])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
async def admin_auto_delete_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Active/désactive l'auto-suppression"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    global AUTO_DELETE_ENABLED
    
    if "enable" in query.data:
        AUTO_DELETE_ENABLED = True
        await query.answer("✅ Auto-suppression activée", show_alert=True)
    else:
        AUTO_DELETE_ENABLED = False
        await query.answer("❌ Auto-suppression désactivée", show_alert=True)
    
    # Retourner au menu de config
    await admin_auto_delete_config(update, context)

@error_handler
async def admin_auto_delete_set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit le délai d'auto-suppression"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    global AUTO_DELETE_DELAY
    
    # Extraire le délai du callback
    delay = int(query.data.replace("auto_delete_delay_", ""))
    AUTO_DELETE_DELAY = delay
    
    delay_min = delay // 60
    await query.answer(f"✅ Délai défini: {delay_min} minutes", show_alert=True)
    
    # Retourner au menu de config
    await admin_auto_delete_config(update, context)


# ==================== CONTACT CLIENT PAR ID ====================

@error_handler
async def contact_user_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permet de contacter un utilisateur en cliquant sur son ID"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    # Extraire l'user_id du callback
    user_id_str = query.data.replace("contact_user_", "")
    
    try:
        target_user_id = int(user_id_str)
    except ValueError:
        await query.answer("❌ ID invalide", show_alert=True)
        return
    
    # Charger les infos utilisateur
    users = load_users()
    user_info = users.get(str(target_user_id), {})
    username = user_info.get('username', 'Utilisateur')
    
    message = f"""💬 CONTACTER L'UTILISATEUR

👤 ID: {target_user_id}
📝 Nom: {username}

Écrivez votre message ci-dessous et il sera envoyé à cet utilisateur.
"""
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Nettoyer les autres états
    context.user_data.pop('editing_order_total', None)
    context.user_data.pop('editing_order_delivery', None)
    context.user_data.pop('awaiting_config', None)
    context.user_data.pop('awaiting_stock_edit', None)
    
    # Sauvegarder l'user_id à contacter
    context.user_data['awaiting_contact_message'] = target_user_id
    logger.info(f"💬 Admin {query.from_user.id} va contacter user {target_user_id}")

@error_handler
async def receive_contact_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne et envoie le message à l'utilisateur"""
    target_user_id = context.user_data.get('awaiting_contact_message')
    
    if not target_user_id:
        return
    
    if not is_admin(update.effective_user.id):
        return
    
    message_text = update.message.text.strip()
    
    if not message_text:
        await update.message.reply_text("❌ Message vide")
        return
    
    # Envoyer le message à l'utilisateur
    try:
        admin_name = get_admin_name(update.effective_user.id)
        
        full_message = f"""📬 MESSAGE DE L'ADMINISTRATION

De: {admin_name}

{message_text}

━━━━━━━━━━━━━━━
Pour répondre, utilisez /support
"""
        
        await context.bot.send_message(
            chat_id=target_user_id,
            text=full_message
        )
        
        context.user_data.pop('awaiting_contact_message', None)
        
        keyboard = [[InlineKeyboardButton("🏠 Panel Admin", callback_data="admin")]]
        
        await update.message.reply_text(
            f"✅ Message envoyé à l'utilisateur {target_user_id}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"💬 Admin {update.effective_user.id} a contacté user {target_user_id}")
    
    except Exception as e:
        logger.error(f"❌ Erreur envoi message: {e}")
        await update.message.reply_text(
            f"❌ Erreur lors de l'envoi du message.\n"
            f"L'utilisateur {target_user_id} a peut-être bloqué le bot."
        )
        context.user_data.pop('awaiting_contact_message', None)

def get_admin_name(admin_id):
    """Retourne le nom d'un admin"""
    if str(admin_id) in ADMINS:
        return ADMINS[str(admin_id)].get('name', 'Admin')
    return 'Admin'

# ==================== MAIN ====================

async def main():
    """Fonction principale du bot"""
    
    # Récupérer token depuis ENV
    BOT_TOKEN = get_bot_token()
    
    if not BOT_TOKEN:
        logger.error("❌ Token introuvable")
        logger.error("💡 Configurez BOT_TOKEN ou TELEGRAM_BOT_TOKEN")
        return
    
    # Bannière de démarrage
    logger.info("=" * 60)
    logger.info(f"🤖 TELEGRAM BOT V{BOT_VERSION}")
    logger.info("=" * 60)
    logger.info(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    logger.info("✅ Token configuré")
    
    ensure_dir(DATA_DIR)
    logger.info(f"✅ Répertoire données: {DATA_DIR}")
    
    ensure_dir(MEDIA_DIR)
    logger.info(f"✅ Répertoire média: {MEDIA_DIR}")
    
    # Vérification persistance
    boot_count = verify_data_persistence()
    
    # Initialisation
    global ADMINS
    ADMINS = load_admins()
    logger.info(f"✅ Admins chargés: {len(ADMINS)}")
    
    # Charger les prix de revient personnalisés
    load_product_costs()
    
    init_product_codes()
    
    # Désactiver maintenance auto
    maintenance_status = load_maintenance_status()
    if maintenance_status.get('enabled', False):
        logger.info("🔧 Mode maintenance détecté - Désactivation automatique...")
        set_maintenance_mode(False)
        logger.info("✅ Mode maintenance désactivé")
    else:
        logger.info("✅ Mode maintenance: Inactif")
    
    update_last_online()
    
    # Création application
    logger.info("🔧 Création de l'application...")
    
    # Créer persistence pour sauvegarder user_data
    persistence = PicklePersistence(filepath=DATA_DIR / "bot_persistence.pkl")
    
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence)
        .concurrent_updates(True)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )
    
    logger.info("✅ Application créée avec persistence")
    
    # Configuration handlers
    setup_handlers(application)
    
    # Jobs périodiques
    job_queue = application.job_queue
    
    job_queue.run_repeating(heartbeat_maintenance, interval=300, first=10)
    logger.info("✅ Job: Heartbeat (5 min)")
    
    job_queue.run_daily(check_stocks_job, time=time(9, 0))
    logger.info("✅ Job: Vérification stocks (9h)")
    
    job_queue.run_daily(check_salary_notifications, time=time(8, 0))
    logger.info("✅ Job: Notifications salaires (8h)")
    
    job_queue.run_daily(schedule_reports, time=time(23, 59))
    logger.info("✅ Job: Rapport hebdomadaire (tous les jours 23h59, filtrage interne)")
    
    # Kill switch
    await kill_switch_check(application)
    
    # Initialisation application
    logger.info("🚀 Initialisation de l'application...")
    await application.initialize()
    logger.info("✅ Application initialisée")
    
    # Démarrage avec retry
    max_retries = 20
    retry_count = 0
    retry_delay = 5
    
    while retry_count < max_retries:
        try:
            logger.info("=" * 60)
            logger.info(f"🚀 DÉMARRAGE DU POLLING (Tentative {retry_count + 1}/{max_retries})")
            logger.info("=" * 60)
            
            await application.start()
            logger.info("✅ Application démarrée")
            
            bot_info = await application.bot.get_me()
            logger.info("=" * 60)
            logger.info(f"✅ BOT CONNECTÉ: @{bot_info.username}")
            logger.info(f"   ID: {bot_info.id}")
            logger.info(f"   Nom: {bot_info.first_name}")
            logger.info("=" * 60)
            
            # Notifier les admins
            startup_message = f"""🤖 BOT DÉMARRÉ

Version: {BOT_VERSION}
Démarrage #{boot_count}
Date: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

✅ Tous les systèmes opérationnels
"""
            
            for admin_id in get_admin_ids():
                try:
                    await application.bot.send_message(
                        chat_id=admin_id,
                        text=startup_message
                    )
                except Exception as e:
                    logger.warning(f"⚠️  Impossible de notifier admin {admin_id}: {e}")
            
            logger.info("✅ Admins notifiés du démarrage")
            
            # Démarrer le polling
            logger.info("🔄 Démarrage du polling...")
            await application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                poll_interval=1.0,
                timeout=30
            )
            
            logger.info("=" * 60)
            logger.info("✅ LE BOT EST EN LIGNE ET OPÉRATIONNEL")
            logger.info("=" * 60)
            logger.info("📊 Statistiques:")
            logger.info(f"   • Utilisateurs: {len(load_users())}")
            logger.info(f"   • Produits: {len(load_product_registry())}")
            logger.info(f"   • Admins: {len(ADMINS)}")
            logger.info("=" * 60)
            logger.info("ℹ️  Appuyez sur Ctrl+C pour arrêter le bot")
            logger.info("=" * 60)
            
            # Garder le bot en vie
            stop_event = asyncio.Event()
            await stop_event.wait()
        
        except Exception as e:
            retry_count += 1
            logger.error("=" * 60)
            logger.error(f"❌ ERREUR (Tentative {retry_count}/{max_retries})")
            logger.error(f"   Type: {type(e).__name__}")
            logger.error(f"   Message: {str(e)}")
            logger.error("=" * 60)
            
            if retry_count < max_retries:
                wait_time = retry_delay * retry_count
                logger.info(f"⏳ Nouvelle tentative dans {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error("❌ NOMBRE MAXIMUM DE TENTATIVES ATTEINT")
                break
    
    # Arrêt propre
    logger.info("=" * 60)
    logger.info("🛑 ARRÊT DU BOT")
    logger.info("=" * 60)
    
    try:
        shutdown_message = f"""🛑 BOT ARRÊTÉ

Date: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

Le bot a été arrêté proprement.
"""
        
        for admin_id in get_admin_ids():
            try:
                await application.bot.send_message(
                    chat_id=admin_id,
                    text=shutdown_message
                )
            except:
                pass
        
        if application.updater and application.updater.running:
            await application.updater.stop()
            logger.info("✅ Polling arrêté")
        
        if application.running:
            await application.stop()
            logger.info("✅ Application arrêtée")
        
        await application.shutdown()
        logger.info("✅ Application fermée")
    
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'arrêt: {e}")
    
    logger.info("=" * 60)
    logger.info("👋 AU REVOIR")
    logger.info("=" * 60)

# ==================== POINT D'ENTRÉE ====================

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️  Interruption clavier (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
    finally:
        logger.info("🏁 Programme terminé")

# ==================== FIN DU FICHIER BOT.PY CORRIGÉ ====================
