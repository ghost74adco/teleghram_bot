#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║   BOT TELEGRAM V3.0.1 - VERSION CORRIGÉE                        ║
║   Bug /admin résolu - Parse mode supprimé                        ║
║                                                                   ║
║   ✅ Ce fichier est la VERSION CORRIGÉE                          ║
║   ✅ Le panel admin fonctionne sans erreur                        ║
║   ✅ Toutes les fonctionnalités sont préservées                   ║
║                                                                   ║
║   Date du fix : 06/01/2026                                       ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝

BOT TELEGRAM V3.0.1 - SYSTÈME MULTI-ADMINS (CORRIGÉ)
Gestion complète e-commerce avec interface admin Telegram
Version corrigée - Bug admin_panel résolu - Parse mode supprimé
"""


import os
import sys
import json
import csv
import asyncio
import logging
import hashlib
import math
from pathlib import Path
from datetime import datetime, time
from typing import Dict, List, Set, Optional
from functools import wraps

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

# Réduire les logs des bibliothèques externes
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

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

# TOKEN BOT (CRITIQUE)
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN manquant dans infos.env !")
    logger.critical("Ajoutez: BOT_TOKEN=votre_token_telegram")
    sys.exit(1)

# Admin principal (pour initialisation)
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")
if not ADMIN_TELEGRAM_ID:
    logger.critical("❌ ADMIN_TELEGRAM_ID manquant dans infos.env !")
    logger.critical("Ajoutez: ADMIN_TELEGRAM_ID=votre_id_telegram")
    sys.exit(1)

try:
    ADMIN_ID = int(ADMIN_TELEGRAM_ID)
except ValueError:
    logger.critical("❌ ADMIN_TELEGRAM_ID doit être un nombre !")
    logger.critical(f"Valeur actuelle: {ADMIN_TELEGRAM_ID}")
    sys.exit(1)

# Adresse admin pour calcul distance
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS", "Paris, France")

# OpenRouteService (optionnel)
OPENROUTE_API_KEY = os.getenv("OPENROUTE_API_KEY")

logger.info(f"✅ BOT_TOKEN chargé: {BOT_TOKEN[:10]}...")
logger.info(f"✅ ADMIN_ID: {ADMIN_ID}")
logger.info(f"✅ ADMIN_ADDRESS: {ADMIN_ADDRESS}")

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

# ==================== FICHIERS DE DONNÉES ====================

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

FRAIS_POSTAL = 10
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

# ==================== GESTION DES ADMINS ====================

def load_admins() -> Dict:
    """Charge la liste des administrateurs depuis admins.json"""
    if ADMINS_FILE.exists():
        try:
            with open(ADMINS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Erreur lecture admins.json: {e}")
            return {}
    else:
        logger.warning("⚠️ Fichier admins.json non trouvé, création...")
        return {}

def save_admins(admins: Dict) -> bool:
    """Sauvegarde les administrateurs dans admins.json"""
    try:
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
    admins = load_admins()
    return str(user_id) in admins

def is_super_admin(user_id: int) -> bool:
    """Vérifie si un utilisateur est super-admin"""
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

# ==================== PRIX DE BASE ====================

PRIX_FR = {
    "❄️ Coco": 60, "💊 Squid Game": 15, "💊 Punisher": 15,
    "🫒 Hash": 10, "🍀 Weed": 10, "🪨 MDMA": 40,
    "🪨 4MMC": 20, "🍄 Ketamine": 40
}

PRIX_CH = {
    "❄️ Coco": 80, "💊 Squid Game": 20, "💊 Punisher": 20,
    "🫒 Hash": 15, "🍀 Weed": 15, "🪨 MDMA": 50,
    "🪨 4MMC": 25, "🍄 Ketamine": 50
}

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

def tr(user_data: dict, key: str, default_lang: str = 'fr') -> str:
    """Traduction simple"""
    lang = user_data.get('language_code', default_lang)
    return TRANSLATIONS.get(lang, TRANSLATIONS['fr']).get(key, key)

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

BOT_VERSION = "3.3.0"
BOT_NAME = "E-Commerce Bot Multi-Admins"

logger.info(f"🤖 {BOT_NAME} v{BOT_VERSION}")

# FIN DU BLOC 1
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
    """Crée le registre initial avec les produits de base"""
    return {
        "coco": {"name": "❄️ Coco", "code": "coco", "emoji": "❄️", "category": "powder", "image": "coco.jpg", "video": "coco_demo.mp4", "created_at": datetime.now().isoformat()},
        "squid_game": {"name": "💊 Squid Game", "code": "squid_game", "emoji": "💊", "category": "pill", "image": "squid_game.jpg", "video": "squid_game_demo.mp4", "created_at": datetime.now().isoformat()},
        "punisher": {"name": "💊 Punisher", "code": "punisher", "emoji": "💊", "category": "pill", "image": "punisher.jpg", "video": "punisher_demo.mp4", "created_at": datetime.now().isoformat()},
        "hash": {"name": "🫒 Hash", "code": "hash", "emoji": "🫒", "category": "powder", "image": "hash.jpg", "video": "hash_demo.mp4", "created_at": datetime.now().isoformat()},
        "weed": {"name": "🍀 Weed", "code": "weed", "emoji": "🍀", "category": "powder", "image": "weed.jpg", "video": "weed_demo.mp4", "created_at": datetime.now().isoformat()},
        "mdma": {"name": "🪨 MDMA", "code": "mdma", "emoji": "🪨", "category": "rock", "image": "mdma.jpg", "video": "mdma_demo.mp4", "created_at": datetime.now().isoformat()},
        "fourmmc": {"name": "🪨 4MMC", "code": "fourmmc", "emoji": "🪨", "category": "rock", "image": "fourmmc.jpg", "video": "fourmmc_demo.mp4", "created_at": datetime.now().isoformat()},
        "ketamine": {"name": "🍄 Ketamine", "code": "ketamine", "emoji": "🍄", "category": "powder", "image": "ketamine.jpg", "video": "ketamine_demo.mp4", "created_at": datetime.now().isoformat()}
    }

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
    """Charge la liste des produits disponibles"""
    if AVAILABLE_PRODUCTS_FILE.exists():
        try:
            with open(AVAILABLE_PRODUCTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get("available", list(PRIX_FR.keys())))
        except:
            pass
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

def get_stock(product_name):
    """Récupère le stock d'un produit"""
    stocks = load_stocks()
    if product_name not in stocks:
        return None
    return stocks[product_name].get("quantity", 0)

def set_stock(product_name, quantity, alert_threshold=20):
    """Définit le stock d'un produit"""
    stocks = load_stocks()
    if product_name not in stocks:
        stocks[product_name] = {}
    
    old_quantity = stocks[product_name].get("quantity", 0)
    stocks[product_name]["quantity"] = quantity
    stocks[product_name]["alert_threshold"] = alert_threshold
    stocks[product_name]["last_updated"] = datetime.now().isoformat()
    
    # GESTION AUTOMATIQUE RUPTURE DE STOCK
    available_products = load_available_products()
    
    if quantity == 0 and old_quantity > 0:
        # Rupture de stock : désactiver automatiquement
        if product_name in available_products:
            available_products.remove(product_name)
            save_available_products(available_products)
            logger.warning(f"📦 Rupture de stock : {product_name} désactivé automatiquement")
    
    elif quantity > 0 and old_quantity == 0:
        # Réapprovisionnement : réactiver automatiquement
        if product_name not in available_products:
            available_products.add(product_name)  # set.add() au lieu de list.append()
            save_available_products(available_products)
            logger.info(f"✅ Réappro : {product_name} réactivé automatiquement (stock: {quantity})")
    
    return save_stocks(stocks)

def update_stock(product_name, quantity_change):
    """Met à jour le stock (+ pour ajout, - pour retrait)"""
    stocks = load_stocks()
    if product_name not in stocks:
        return True
    
    current = stocks[product_name].get("quantity", 0)
    new_quantity = max(0, current + quantity_change)
    stocks[product_name]["quantity"] = new_quantity
    stocks[product_name]["last_updated"] = datetime.now().isoformat()
    
    return save_stocks(stocks)

def is_in_stock(product_name, requested_quantity):
    """Vérifie si la quantité demandée est disponible"""
    stock = get_stock(product_name)
    if stock is None:
        return True
    return stock >= requested_quantity

def get_low_stock_products():
    """Récupère les produits avec stock faible"""
    stocks = load_stocks()
    low_stock = []
    
    for product_name, data in stocks.items():
        quantity = data.get("quantity", 0)
        threshold = data.get("alert_threshold", 20)
        if quantity <= threshold and quantity > 0:
            low_stock.append({
                "product": product_name,
                "quantity": quantity,
                "threshold": threshold
            })
    
    return low_stock

def get_out_of_stock_products():
    """Récupère les produits en rupture de stock"""
    stocks = load_stocks()
    out_of_stock = []
    
    for product_name, data in stocks.items():
        if data.get("quantity", 0) == 0:
            out_of_stock.append(product_name)
    
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
    """Sauvegarde une commande en CSV"""
    csv_path = DATA_DIR / "orders.csv"
    try:
        file_exists = csv_path.exists()
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            fieldnames = [
                'date', 'order_id', 'user_id', 'username', 'first_name', 'language',
                'products', 'country', 'address', 'delivery_type', 'distance_km',
                'payment_method', 'subtotal', 'delivery_fee', 'promo_discount',
                'vip_discount', 'total', 'promo_code', 'status', 'price_modified',
                'old_total', 'delivery_modified', 'old_delivery_fee', 'validated_date',
                'ready_date', 'delivered_date'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            if not file_exists:
                writer.writeheader()
            writer.writerow(order_data)
        return True
    except Exception as e:
        logger.error(f"CSV: {e}")
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
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour la commande /start"""
    user = update.effective_user
    user_id = user.id

    if is_maintenance_mode(user_id):
        await update.message.reply_text(
            f"{EMOJI_THEME['warning']} BOT EN MAINTENANCE\n\n"
            "Le service est temporairement indisponible.\n"
            "Veuillez réessayer dans quelques instants."
        )
        return

    user_data = {
        "username": user.username or "N/A",
        "first_name": user.first_name or "Utilisateur",
        "last_name": user.last_name or "",
        "language_code": user.language_code or "fr"
    }

    keyboard = [
        [
            InlineKeyboardButton("🇫🇷 France", callback_data="country_fr"),
            InlineKeyboardButton("🇨🇭 Suisse", callback_data="country_ch")
        ],
        [InlineKeyboardButton(f"{EMOJI_THEME['info']} Aide", callback_data="help")]
    ]

    if is_new_user(user_id):
        add_user(user_id, user_data)
        logger.info(f"🆕 Nouvel utilisateur: {user_id} - {user_data['first_name']}")
        await notify_admin_new_user(context, user_id, user_data)

        welcome_message = f"""{EMOJI_THEME['celebration']} BIENVENUE {user_data['first_name']} !

Merci de nous rejoindre sur notre plateforme.

{EMOJI_THEME['gift']} OFFRE DE BIENVENUE
Utilisez le code WELCOME10 pour bénéficier de 10% de réduction sur votre première commande !

{EMOJI_THEME['info']} COMMENT COMMANDER ?
1️⃣ Choisissez votre pays 🇫🇷 🇨🇭
2️⃣ Parcourez nos produits
3️⃣ Ajoutez au panier
4️⃣ Validez votre commande

{EMOJI_THEME['delivery']} MODES DE LIVRAISON
- Postale (48-72h) - 10€
- Express (30min+) - Variable selon distance
- Meetup - Gratuit

{EMOJI_THEME['support']} BESOIN D'AIDE ?
Notre équipe est disponible {get_horaires_text()}
"""

        await update.message.reply_text(
            welcome_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        update_user_visit(user_id)
        stats = get_client_stats(user_id)

        vip_message = ""
        if stats and stats.get("vip_status"):
            vip_message = f"{EMOJI_THEME['vip']} Statut VIP actif - {VIP_DISCOUNT}% de réduction automatique\n"

        returning_message = f"""{EMOJI_THEME['wave']} Bon retour {user_data['first_name']} !

{vip_message}
Choisissez votre pays pour commencer :

🕐 Horaires : {get_horaires_text()}
"""
        
        keyboard = [
            [InlineKeyboardButton("🇫🇷 France", callback_data="country_fr"),
             InlineKeyboardButton("🇨🇭 Suisse", callback_data="country_ch")],
            [InlineKeyboardButton(f"{EMOJI_THEME['cart']} Mon Panier", callback_data="view_cart"),
             InlineKeyboardButton(f"{EMOJI_THEME['history']} Historique", callback_data="my_history")],
            [InlineKeyboardButton(f"{EMOJI_THEME['gift']} Parrainage", callback_data="referral_info")]
        ]
        
        await update.message.reply_text(
            returning_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    logger.info(f"✅ /start traité: {user_id}")

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
         InlineKeyboardButton("🇨🇭 Suisse", callback_data="country_ch")],
        [InlineKeyboardButton(f"{EMOJI_THEME['cart']} Mon Panier", callback_data="view_cart"),
         InlineKeyboardButton(f"{EMOJI_THEME['history']} Historique", callback_data="my_history")],
        [InlineKeyboardButton(f"{EMOJI_THEME['info']} Aide", callback_data="help_inline")]
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
    
    flag = "🇫🇷" if country_code == "fr" else "🇨🇭"
    country_name = "France" if country_code == "fr" else "Suisse"
    
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
    
    registry = load_product_registry()
    available = get_available_products()
    
    message = "✅ ACTIVER/DÉSACTIVER PRODUITS\n\nCliquez pour changer le statut :\n"
    
    keyboard = []
    for code, product in sorted(registry.items()):
        name = product['name']
        is_available = name in available
        icon = "✅" if is_available else "❌"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {name}",
                callback_data=f"admin_toggle_{code}"
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
    
    code = query.data.replace("admin_toggle_", "")
    registry = load_product_registry()
    
    if code not in registry:
        await query.answer("Produit introuvable", show_alert=True)
        return
    
    product_name = registry[code]['name']
    available = get_available_products()
    
    if product_name in available:
        available.remove(product_name)
        action = "désactivé"
    else:
        available.add(product_name)
        action = "activé"
    
    save_available_products(available)
    
    await query.answer(f"{product_name} {action}", show_alert=True)
    
    # Rafraîchir la liste
    await admin_toggle_products(update, context)
    
    logger.info(f"🔄 Produit {action}: {product_name}")

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
    """Prix dégressifs - Fonctionnalité à venir"""
    query = update.callback_query
    await query.answer()
    
    message = """📊 PRIX DÉGRESSIFS

Cette fonctionnalité est en cours de développement.

Elle permettra de configurer des prix dégressifs par quantité :
• 1-10g : Prix normal
• 11-50g : -5%
• 51-100g : -10%
• etc.

Pour l'instant, utilisez la gestion des prix par pays.
"""
    
    keyboard = [
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
        context.user_data['delivery_fee'] = FRAIS_POSTAL
    
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
    save_order_to_csv(order_data)
    
    # Mettre à jour l'historique client
    update_client_history(user_id, {
        'order_id': order_id,
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
    
    # Mettre à jour les stocks
    for item in cart:
        update_stock(item['produit'], -item['quantite'])
        
        # Vérifier stock après mise à jour
        new_stock = get_stock(item['produit'])
        if new_stock is not None:
            if new_stock == 0:
                await notify_admin_out_of_stock(context, item['produit'])
                # Désactiver le produit
                available = get_available_products()
                if item['produit'] in available:
                    available.remove(item['produit'])
                    save_available_products(available)
            elif new_stock <= 20:
                await notify_admin_low_stock(context, item['produit'], new_stock)
    
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
    
    # Vider le panier
    context.user_data['cart'] = []
    
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
                with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=orders[0].keys())
                    writer.writeheader()
                    writer.writerows(orders)
    except Exception as e:
        logger.error(f"Erreur lecture/écriture commande: {e}")
    
    # Enregistrer la vente dans le livre de comptes
    if order_data:
        try:
            total = float(order_data.get('total', 0))
            first_name = order_data.get('first_name', 'Client')
            
            add_ledger_entry(
                'income',
                total,
                f"Vente commande {order_id} - {first_name} (Livrée)",
                'Vente',
                order_id
            )
            logger.info(f"📒 Vente ajoutée au livre de comptes: {total:.2f}€")
        except Exception as e:
            logger.error(f"Erreur ajout livre de comptes: {e}")
    else:
        logger.warning(f"⚠️ Commande {order_id} introuvable dans CSV - vente non enregistrée")
    
    # Notifier le client
    try:
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

async def schedule_reports(context: ContextTypes.DEFAULT_TYPE):
    """Planifie les rapports automatiques"""
    now = datetime.now()
    stats = load_stats()
    
    if now.weekday() == 6 and now.hour == 23 and now.minute == 59:
        last_weekly = stats.get("last_weekly_report")
        if not last_weekly or (now - datetime.fromisoformat(last_weekly)).days >= 7:
            await send_weekly_report(context)

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
            [InlineKeyboardButton("✅ Approuver", callback_data=f"approve_pay_{payment['id']}")],
            [InlineKeyboardButton("❌ Refuser", callback_data=f"reject_pay_{payment['id']}")]
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
            
            for order in orders:
                # Parser les produits de chaque commande
                products_str = order.get('products', '')
                
                # Format attendu : "Coco (10.0g) × 1, K (5.0g) × 2"
                if products_str:
                    import re
                    # Extraire chaque produit
                    for product_entry in products_str.split(','):
                        product_entry = product_entry.strip()
                        
                        # Chercher correspondance avec nos produits
                        for product_name in PRODUCT_COSTS.keys():
                            if product_name in product_entry:
                                # Extraire quantité
                                # Format: "Coco (10.0g) × 1" ou "Pills Squid-Game (5 unités) × 2"
                                match_weight = re.search(r'\((\d+(?:\.\d+)?)\s*g\)', product_entry)
                                match_units = re.search(r'\((\d+)\s*unités?\)', product_entry)
                                match_multiplier = re.search(r'×\s*(\d+)', product_entry)
                                
                                quantity = 0
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
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_finances")]]
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
    
    # Retour à la liste
    await admin_finances_all_expenses(update, context)
    
    logger.info(f"✅ Consommable classé: {expense_id} par {query.from_user.id}")

    logger.info(f"✅ Consommable approuvé: {expense_id} - {expense_found['amount']}€")

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
    
    # Retour à la liste
    await admin_finances_all_expenses(update, context)
    
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
                    
                    # Chercher correspondance avec nos produits
                    for product_name in PRODUCT_COSTS.keys():
                        if product_name in product_entry:
                            # Extraire quantité
                            match_weight = re.search(r'\((\d+(?:\.\d+)?)\s*g\)', product_entry)
                            match_units = re.search(r'\((\d+)\s*unités?\)', product_entry)
                            match_multiplier = re.search(r'×\s*(\d+)', product_entry)
                            
                            quantity = 0
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
    all_products = load_product_registry().get('products', {})
    
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
    
    # Sauvegarder le produit en cours d'édition
    context.user_data['awaiting_cost_update'] = product_name

@error_handler
async def receive_cost_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réceptionne le nouveau prix de revient"""
    if not is_admin(update.effective_user.id):
        return
    
    product_name = context.user_data.get('awaiting_cost_update')
    
    if not product_name:
        return
    
    try:
        new_cost = float(update.message.text.strip())
        
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
        else:
            saved_costs = dict(PRODUCT_COSTS)
        
        old_cost = saved_costs.get(product_name, PRODUCT_COSTS.get(product_name, 0))
        saved_costs[product_name] = new_cost
        
        # Sauvegarder
        with open(costs_file, 'w', encoding='utf-8') as f:
            json.dump(saved_costs, f, indent=2, ensure_ascii=False)
        
        # Mettre à jour PRODUCT_COSTS en mémoire
        PRODUCT_COSTS[product_name] = new_cost
        
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
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Prix invalide. Utilisez un nombre.\n"
            "Exemple : 42.50"
        )

def load_product_costs():
    """Charge les prix de revient depuis le fichier JSON"""
    costs_file = DATA_DIR / "product_costs.json"
    
    if costs_file.exists():
        try:
            with open(costs_file, 'r', encoding='utf-8') as f:
                saved_costs = json.load(f)
            
            # Mettre à jour PRODUCT_COSTS
            for product_name, cost in saved_costs.items():
                if product_name in PRODUCT_COSTS:
                    PRODUCT_COSTS[product_name] = cost
            
            logger.info(f"💵 Prix de revient chargés: {len(saved_costs)} produits")
            return True
        except Exception as e:
            logger.error(f"Erreur chargement prix: {e}")
            return False
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
    if admin_config['commission_type'] == 'percentage':
        commission_info = f"{admin_config['commission_value']}% par commande"
    elif admin_config['commission_type'] == 'fixed':
        commission_info = f"{admin_config['commission_value']:.2f}€ par commande"
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
    """Choisir type de commission"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.data.replace("set_commission_", "")
    
    message = """💸 TYPE DE COMMISSION

Choisissez le type de commission :
"""
    
    keyboard = [
        [InlineKeyboardButton("📊 Pourcentage (%)", callback_data=f"commission_percent_{admin_id}")],
        [InlineKeyboardButton("💵 Montant fixe (€)", callback_data=f"commission_fixed_{admin_id}")],
        [InlineKeyboardButton("❌ Aucune", callback_data=f"commission_none_{admin_id}")],
        [InlineKeyboardButton("🔙 Annuler", callback_data=f"salary_admin_{admin_id}")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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
async def edit_order_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permet de modifier le prix total d'une commande"""
    query = update.callback_query
    await query.answer()
    
    order_id = query.data.replace("edit_order_total_", "")
    
    # Charger commande depuis CSV
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        await query.answer("Erreur: commande introuvable", show_alert=True)
        return
    
    try:
        import csv as csv_module
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        order = next((o for o in orders if o.get('order_id') == order_id), None)
        
        if not order:
            await query.answer("Commande introuvable", show_alert=True)
            return
        
        message = f"""✏️ MODIFIER PRIX TOTAL

📋 Commande : {order_id}
💰 Prix actuel : {order.get('total', 'N/A')}€

Entrez le nouveau prix total :
Exemple : 550.00
"""
        
        keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data=f"cancel_edit_order_{order_id}")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Nettoyer les autres états d'édition
        context.user_data.pop('editing_order_delivery', None)
        context.user_data['editing_order_total'] = order_id
        logger.info(f"📝 État défini: editing_order_total={order_id}, user_data={context.user_data}")
    
    except Exception as e:
        logger.error(f"Erreur edit_order_total: {e}")
        await query.answer("Erreur", show_alert=True)

@error_handler
async def edit_order_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permet de modifier les frais de livraison d'une commande"""
    query = update.callback_query
    await query.answer()
    
    order_id = query.data.replace("edit_order_delivery_", "")
    
    # Charger commande
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        await query.answer("Erreur: commande introuvable", show_alert=True)
        return
    
    try:
        import csv as csv_module
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            orders = list(reader)
        
        order = next((o for o in orders if o.get('order_id') == order_id), None)
        
        if not order:
            await query.answer("Commande introuvable", show_alert=True)
            return
        
        message = f"""✏️ MODIFIER FRAIS LIVRAISON

📋 Commande : {order_id}
🚚 Frais actuels : {order.get('delivery_fee', 'N/A')}€
📦 Type : {order.get('delivery_type', 'N/A')}

Entrez les nouveaux frais de livraison :
Exemple : 15.00
"""
        
        keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data=f"cancel_edit_order_{order_id}")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Nettoyer les autres états d'édition
        context.user_data.pop('editing_order_total', None)
        context.user_data['editing_order_delivery'] = order_id
        logger.info(f"📝 État défini: editing_order_delivery={order_id}, user_data={context.user_data}")
    
    except Exception as e:
        logger.error(f"Erreur edit_order_delivery: {e}")
        await query.answer("Erreur", show_alert=True)

@error_handler
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
                order['price_modified'] = 'Yes'
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
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            if orders:
                writer = csv.DictWriter(f, fieldnames=orders[0].keys())
                writer.writeheader()
                writer.writerows(orders)
        
        context.user_data.pop('editing_order_total', None)
        
        message = f"""{EMOJI_THEME['success']} PRIX MODIFIÉ

📋 Commande : {order_id}

Ancien prix : {old_total}€
Nouveau prix : {new_total}€

Cliquez sur "Valider commande" pour confirmer.
"""
        
        keyboard = [[InlineKeyboardButton("🔙 Voir notification", callback_data=f"view_order_{order_id}")]]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"💰 Prix modifié: {order_id} - {old_total}€ → {new_total}€")
    
    except ValueError as e:
        logger.error(f"❌ ValueError dans receive_order_total: {e}")
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Prix invalide. Utilisez un nombre.\n"
            "Exemple : 550.00"
        )

@error_handler
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
                subtotal = float(order.get('subtotal', 0))
                
                # Recalculer le total
                new_total = subtotal + new_delivery_fee
                
                order['delivery_fee'] = str(new_delivery_fee)
                order['total'] = str(new_total)
                order['delivery_modified'] = 'Yes'
                order['old_delivery_fee'] = old_delivery
                
                order_found = True
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
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            if orders:
                writer = csv.DictWriter(f, fieldnames=orders[0].keys())
                writer.writeheader()
                writer.writerows(orders)
        
        context.user_data.pop('editing_order_delivery', None)
        
        message = f"""{EMOJI_THEME['success']} FRAIS MODIFIÉS

📋 Commande : {order_id}

Anciens frais : {old_delivery}€
Nouveaux frais : {new_delivery_fee}€

Nouveau total : {new_total}€

Cliquez sur "Valider commande" pour confirmer.
"""
        
        keyboard = [[InlineKeyboardButton("🔙 Voir notification", callback_data=f"view_order_{order_id}")]]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"🚚 Frais modifiés: {order_id} - {old_delivery}€ → {new_delivery_fee}€")
    
    except ValueError:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Montant invalide. Utilisez un nombre.\n"
            "Exemple : 15.00"
        )

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
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=orders[0].keys())
        writer.writeheader()
        writer.writerows(orders)
    
    # Calculer commission pour l'admin qui valide
    await calculate_commission_on_order(context, query.from_user.id, order)
    
    # NOTIFICATION AU CLIENT
    try:
        client_message = f"""✅ COMMANDE VALIDÉE !

📋 Commande : {order_id}

Votre commande a été validée par notre équipe.

🛍️ Produits :
{order.get('products_display', order.get('products', 'N/A'))}

💰 Total : {order.get('total')}€
💳 Paiement : {order.get('payment_method', 'N/A')}

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
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=orders[0].keys())
        writer.writeheader()
        writer.writerows(orders)
    
    # NOTIFICATION AU CLIENT
    client_notification = f"""✅ VOTRE COMMANDE EST PRÊTE !

📋 Commande : {order_id}

Votre commande a été préparée et est prête à être livrée.

🛍️ Produits :
{order.get('products_display', order.get('products', 'N/A'))}

💰 Total : {order.get('total')}€

📍 Livraison : {order.get('delivery_type')}

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

def load_ledger():
    """Charge le livre de comptes"""
    ledger_file = DATA_DIR / "ledger.json"
    if ledger_file.exists():
        with open(ledger_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "entries": [],
        "balance": 0,
        "last_updated": datetime.now().isoformat()
    }

def save_ledger(data):
    """Sauvegarde le livre de comptes"""
    ledger_file = DATA_DIR / "ledger.json"
    data['last_updated'] = datetime.now().isoformat()
    with open(ledger_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def add_ledger_entry(entry_type, amount, description, category, reference_id=None):
    """Ajoute une entrée dans le livre de comptes
    
    entry_type: 'income' ou 'expense'
    amount: montant positif
    description: texte libre
    category: catégorie (Vente, Salaire, Consommable, etc.)
    reference_id: ID de référence (order_id, payment_id, etc.)
    """
    logger.info(f"📒 Début add_ledger_entry: type={entry_type}, amount={amount}, category={category}")
    
    ledger = load_ledger()
    logger.info(f"📒 Ledger chargé: {len(ledger.get('entries', []))} entrées, solde={ledger.get('balance', 0)}")
    
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
    
    logger.info(f"📒 Entrée créée: {entry['id']}, nouveau solde={ledger['balance']}")
    
    save_ledger(ledger)
    logger.info(f"📒 Livre de comptes: {entry_type} {amount:.2f}€ - {description}")
    
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

@error_handler
async def admin_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu principal livre de comptes avec stats automatiques (super-admin uniquement)"""
    query = update.callback_query
    await query.answer()
    
    if not is_super_admin(query.from_user.id):
        await query.answer("Accès refusé", show_alert=True)
        return
    
    ledger = load_ledger()
    
    # Statistiques rapides
    total_income = sum(e['amount'] for e in ledger['entries'] if e['type'] == 'income')
    total_expenses = sum(e['amount'] for e in ledger['entries'] if e['type'] == 'expense')
    balance = ledger.get('balance', 0)
    
    # Stats par catégorie
    ventes = sum(e['amount'] for e in ledger['entries'] if e['type'] == 'income' and e.get('category') == 'Vente')
    salaires = sum(e['amount'] for e in ledger['entries'] if e['type'] == 'expense' and e.get('category') == 'Salaire')
    consommables = sum(e['amount'] for e in ledger['entries'] if e['type'] == 'expense' and e.get('category') == 'Consommable')
    
    message = f"""📒 LIVRE DE COMPTES

💰 SOLDE ACTUEL : {balance:.2f}€

━━━━━━━━━━━━━━━━━━━━━━

📊 STATISTIQUES :
• Total entrées : {total_income:.2f}€
  └ Ventes : {ventes:.2f}€
• Total sorties : {total_expenses:.2f}€
  └ Salaires : {salaires:.2f}€
  └ Consommables : {consommables:.2f}€

📋 Transactions : {len(ledger['entries'])}

━━━━━━━━━━━━━━━━━━━━━━

🔄 SYNCHRONISATION AUTO :
✅ Ventes clients
✅ Paiements salaires
✅ Consommables approuvés

Que voulez-vous faire ?
"""
    
    keyboard = [
        [
            InlineKeyboardButton("📥 Voir Entrées", callback_data="ledger_income"),
            InlineKeyboardButton("📤 Voir Sorties", callback_data="ledger_expenses")
        ],
        [
            InlineKeyboardButton("📋 Toutes transactions", callback_data="ledger_all")
        ],
        [
            InlineKeyboardButton("➕ Ajouter Entrée", callback_data="ledger_add_income"),
            InlineKeyboardButton("➖ Ajouter Sortie", callback_data="ledger_add_expense")
        ],
        [
            InlineKeyboardButton("🔄 Importer historique", callback_data="ledger_import_history")
        ],
        [
            InlineKeyboardButton("✏️ Modifier Solde", callback_data="ledger_edit_balance")
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

# ==================== CONFIGURATION DES HANDLERS ====================

def setup_handlers(application):
    """Configure tous les handlers du bot"""
    
    # Commandes de base
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("myid", get_my_id))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # Callbacks généraux
    application.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
    application.add_handler(CallbackQueryHandler(help_inline, pattern="^help_inline$"))
    application.add_handler(CallbackQueryHandler(my_history, pattern="^my_history$"))
    application.add_handler(CallbackQueryHandler(referral_info, pattern="^referral_info$"))
    
    # Callbacks pays
    application.add_handler(CallbackQueryHandler(select_country, pattern="^country_(fr|ch)$"))
    
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
    application.add_handler(CallbackQueryHandler(approve_payment, pattern="^approve_payment_"))
    application.add_handler(CallbackQueryHandler(reject_payment, pattern="^reject_payment_"))
    application.add_handler(CallbackQueryHandler(admin_finances_payroll, pattern="^admin_finances_payroll"))
    application.add_handler(CallbackQueryHandler(admin_finances_full_report, pattern="^admin_finances_full_report"))
    
    # Callbacks admin - prix de revient
    application.add_handler(CallbackQueryHandler(admin_costs, pattern="^admin_costs$"))
    application.add_handler(CallbackQueryHandler(admin_cost_edit, pattern="^admin_cost_edit_"))
    
    # Callbacks admin - gestion salaires
    application.add_handler(CallbackQueryHandler(admin_salary_config, pattern="^admin_salary_config$"))
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
    application.add_handler(CallbackQueryHandler(ledger_view_entries, pattern="^ledger_(income|expenses|all)$"))
    application.add_handler(CallbackQueryHandler(ledger_add_entry, pattern="^ledger_add_(income|expense)$"))
    application.add_handler(CallbackQueryHandler(ledger_select_category, pattern="^ledger_cat_"))
    application.add_handler(CallbackQueryHandler(ledger_edit_balance, pattern="^ledger_edit_balance$"))
    application.add_handler(CallbackQueryHandler(ledger_monthly_report, pattern="^ledger_monthly_report$"))
    application.add_handler(CallbackQueryHandler(ledger_import_history, pattern="^ledger_import_history$"))
    
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
    
    # Callbacks admin - paramètres
    application.add_handler(CallbackQueryHandler(admin_settings, pattern="^admin_settings$"))
    application.add_handler(CallbackQueryHandler(admin_maintenance, pattern="^admin_maintenance$"))
    application.add_handler(CallbackQueryHandler(admin_maintenance_toggle, pattern="^admin_maintenance_(on|off)$"))
    
    # Callbacks admin - stats
    application.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_detailed_stats, pattern="^admin_detailed_stats$"))
    
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

async def main():
    """Fonction principale du bot"""
    
    # Bannière de démarrage
    logger.info("=" * 60)
    logger.info(f"🤖 TELEGRAM BOT V{BOT_VERSION}")
    logger.info("=" * 60)
    logger.info(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # Vérifications
    if not BOT_TOKEN or BOT_TOKEN == "VOTRE_TOKEN_ICI":
        logger.error("❌ BOT_TOKEN non configuré")
        return
    
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
