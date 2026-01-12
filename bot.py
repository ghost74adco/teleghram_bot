#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║   BOT TELEGRAM V4.0.0 - SQUELETTE COMMERCIAL UNIVERSEL           ║
║   Système de licences + Multi-langues + 100% JSON                ║
║                                                                   ║
║   ✅ Tout en JSON (produits, config, langues)                     ║
║   ✅ Système de licences 3 niveaux                                ║
║   ✅ 5 langues complètes (FR, EN, DE, ES, IT)                     ║
║   ✅ Interface adaptative selon licence                           ║
║   ✅ Migration complète depuis V3.2.8                             ║
║                                                                   ║
║   Date : 12/01/2025 - Version 4.0.0                              ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
"""

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
from datetime import datetime, time
from typing import Dict, List, Set, Optional, Any
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
        logging.FileHandler('/data/bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Réduire les logs des bibliothèques externes
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

# ==================== CONSTANTES ====================

DATA_DIR = Path("/data")
BOT_VERSION = "4.0.0"

# Fichiers JSON
PRODUCTS_FILE = DATA_DIR / "products.json"
CONFIG_FILE = DATA_DIR / "config.json"
LICENSE_FILE = DATA_DIR / "license.json"
LANGUAGES_FILE = DATA_DIR / "languages.json"
ADMINS_FILE = DATA_DIR / "admins.json"

# Fichiers de données (conservés)
ORDERS_FILE = DATA_DIR / "orders.csv"
CLIENT_HISTORY_FILE = DATA_DIR / "client_history.json"
USERS_FILE = DATA_DIR / "users.json"
LEDGER_FILE = DATA_DIR / "ledger.json"
SALARIES_FILE = DATA_DIR / "salaries.json"
COMMISSIONS_FILE = DATA_DIR / "commissions.json"
EXPENSES_FILE = DATA_DIR / "expenses.json"
VIP_CONFIG_FILE = DATA_DIR / "vip_config.json"

# ==================== CHARGEMENT JSON ====================

def load_json_file(filepath: Path, default: Any = None) -> Any:
    """Charge un fichier JSON avec gestion d'erreur"""
    try:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"✅ Fichier chargé : {filepath.name}")
                return data
        else:
            logger.warning(f"⚠️ Fichier manquant : {filepath.name}, utilisation valeur par défaut")
            return default if default is not None else {}
    except json.JSONDecodeError as e:
        logger.error(f"❌ Erreur JSON dans {filepath.name}: {e}")
        return default if default is not None else {}
    except Exception as e:
        logger.error(f"❌ Erreur chargement {filepath.name}: {e}")
        return default if default is not None else {}

def save_json_file(filepath: Path, data: Any) -> bool:
    """Sauvegarde un fichier JSON"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Fichier sauvegardé : {filepath.name}")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde {filepath.name}: {e}")
        return False

# Chargement des données au démarrage
PRODUCTS_DATA = load_json_file(PRODUCTS_FILE, {"products": {}, "categories": {}})
CONFIG_DATA = load_json_file(CONFIG_FILE, {})
LICENSE_DATA = load_json_file(LICENSE_FILE, {"license": {"level": 1, "status": "active"}})
LANGUAGES_DATA = load_json_file(LANGUAGES_FILE, {"languages": {}, "translations": {}})
ADMINS_DATA = load_json_file(ADMINS_FILE, {"admins": {}, "roles": {}})

logger.info(f"""
╔════════════════════════════════════════╗
║   BOT V{BOT_VERSION} - DÉMARRAGE           ║
╚════════════════════════════════════════╝

📦 Produits chargés : {len(PRODUCTS_DATA.get('products', {}))}
⚙️  Configuration : ✅
🔐 Licence Niveau : {LICENSE_DATA.get('license', {}).get('level', 1)}
🌐 Langues : {len(LANGUAGES_DATA.get('languages', {}))}
👥 Admins : {len(ADMINS_DATA.get('admins', {}))}
""")

# ==================== SYSTÈME DE LICENCES ====================

def get_license_level() -> int:
    """Retourne le niveau de licence actuel"""
    return LICENSE_DATA.get('license', {}).get('level', 1)

def get_license_status() -> str:
    """Retourne le statut de la licence"""
    return LICENSE_DATA.get('license', {}).get('status', 'inactive')

def check_feature(feature_name: str) -> bool:
    """Vérifie si une fonctionnalité est disponible selon la licence"""
    if get_license_status() != 'active':
        return False
    
    features = LICENSE_DATA.get('features', {})
    
    # Si la feature est un dict (comme multi_admin), vérifier 'enabled'
    feature = features.get(feature_name)
    if isinstance(feature, dict):
        return feature.get('enabled', False)
    
    return bool(feature)

def get_feature_limit(feature_name: str, attribute: str) -> Any:
    """Récupère une limite d'une fonctionnalité"""
    features = LICENSE_DATA.get('features', {})
    feature = features.get(feature_name, {})
    
    if isinstance(feature, dict):
        return feature.get(attribute)
    
    return None

def require_level(min_level: int):
    """Décorateur pour restreindre l'accès selon le niveau de licence"""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            current_level = get_license_level()
            
            if current_level < min_level:
                query = update.callback_query
                if query:
                    await query.answer(
                        f"⚠️ FONCTIONNALITÉ PREMIUM\n\n"
                        f"Cette fonction nécessite le Niveau {min_level}.\n"
                        f"Votre niveau actuel : {current_level}\n\n"
                        f"Tapez /upgrade pour débloquer.",
                        show_alert=True
                    )
                return
            
            return await func(update, context)
        return wrapper
    return decorator

# ==================== SYSTÈME DE TRADUCTION ====================

def t(key: str, lang: str = 'fr', **kwargs) -> str:
    """
    Traduit une clé dans la langue spécifiée
    
    Args:
        key: Clé de traduction
        lang: Code langue (fr, en, de, es, it)
        **kwargs: Variables à formatter dans la traduction
    
    Returns:
        Texte traduit
    """
    translations = LANGUAGES_DATA.get('translations', {})
    
    if key not in translations:
        logger.warning(f"⚠️ Clé de traduction manquante : {key}")
        return key
    
    translation = translations[key].get(lang, translations[key].get('fr', key))
    
    if kwargs:
        try:
            return translation.format(**kwargs)
        except KeyError as e:
            logger.error(f"❌ Erreur formatage traduction {key}: {e}")
            return translation
    
    return translation

def get_user_language(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Récupère la langue de l'utilisateur"""
    return context.user_data.get('language', 'fr')

# ==================== GESTION DES PRODUITS ====================

def get_all_products() -> Dict:
    """Retourne tous les produits"""
    return PRODUCTS_DATA.get('products', {})

def get_product(product_id: str) -> Optional[Dict]:
    """Récupère un produit par son ID"""
    return PRODUCTS_DATA.get('products', {}).get(product_id)

def get_product_name(product_id: str, lang: str = 'fr') -> str:
    """Récupère le nom d'un produit dans une langue"""
    product = get_product(product_id)
    if not product:
        return "Produit inconnu"
    
    name = product.get('name', {})
    if isinstance(name, dict):
        return name.get(lang, name.get('fr', 'Produit'))
    return str(name)

def get_product_price(product_id: str, country: str = 'FR') -> float:
    """Récupère le prix d'un produit pour un pays"""
    product = get_product(product_id)
    if not product:
        return 0.0
    
    prices = product.get('prices', {})
    return float(prices.get(country, 0))

def get_product_stock(product_id: str) -> int:
    """Récupère le stock d'un produit"""
    product = get_product(product_id)
    if not product:
        return 0
    
    return int(product.get('stock', 0))

def update_product_stock(product_id: str, new_stock: int) -> bool:
    """Met à jour le stock d'un produit"""
    if product_id not in PRODUCTS_DATA.get('products', {}):
        return False
    
    PRODUCTS_DATA['products'][product_id]['stock'] = new_stock
    return save_json_file(PRODUCTS_FILE, PRODUCTS_DATA)

def deduct_stock(product_id: str, quantity: float) -> bool:
    """Déduit une quantité du stock"""
    current_stock = get_product_stock(product_id)
    new_stock = current_stock - quantity
    
    if new_stock < 0:
        logger.error(f"❌ Stock insuffisant pour {product_id}: {current_stock} < {quantity}")
        return False
    
    return update_product_stock(product_id, new_stock)

def get_categories() -> Dict:
    """Retourne toutes les catégories"""
    return PRODUCTS_DATA.get('categories', {})

def get_category_name(category_id: str, lang: str = 'fr') -> str:
    """Récupère le nom d'une catégorie dans une langue"""
    categories = get_categories()
    category = categories.get(category_id, {})
    
    name = category.get('name', {})
    if isinstance(name, dict):
        return name.get(lang, name.get('fr', 'Catégorie'))
    return str(name)

def get_products_by_category(category_id: str) -> List[Dict]:
    """Récupère tous les produits d'une catégorie"""
    products = []
    for product_id, product in get_all_products().items():
        if product.get('category') == category_id and product.get('active', True):
            products.append({**product, 'id': product_id})
    return products

# ==================== GESTION DES PAYS ====================

def get_countries() -> Dict:
    """Retourne tous les pays configurés"""
    return CONFIG_DATA.get('countries', {})

def get_country_name(country_code: str, lang: str = 'fr') -> str:
    """Récupère le nom d'un pays"""
    countries = get_countries()
    country = countries.get(country_code, {})
    return country.get('name', country_code)

def get_delivery_modes(country_code: str) -> Dict:
    """Récupère les modes de livraison disponibles pour un pays"""
    countries = get_countries()
    country = countries.get(country_code, {})
    return country.get('delivery', {})

def get_delivery_fee(country_code: str, mode: str) -> float:
    """Récupère les frais de livraison"""
    delivery_modes = get_delivery_modes(country_code)
    mode_config = delivery_modes.get(mode, {})
    return float(mode_config.get('fee', 0))

# ==================== GESTION DES ADMINS ====================

def is_admin(user_id: int) -> bool:
    """Vérifie si un utilisateur est admin"""
    admins = ADMINS_DATA.get('admins', {})
    user_id_str = str(user_id)
    
    if user_id_str in admins:
        admin = admins[user_id_str]
        return admin.get('active', True)
    
    return False

def get_admin_role(user_id: int) -> Optional[str]:
    """Récupère le rôle d'un admin"""
    admins = ADMINS_DATA.get('admins', {})
    admin = admins.get(str(user_id))
    
    if admin:
        return admin.get('role', 'admin')
    
    return None

def has_permission(user_id: int, permission: str) -> bool:
    """Vérifie si un admin a une permission"""
    role_name = get_admin_role(user_id)
    if not role_name:
        return False
    
    roles = ADMINS_DATA.get('roles', {})
    role = roles.get(role_name, {})
    
    # Super admin a tous les droits
    if 'all' in role.get('permissions', []):
        return True
    
    return permission in role.get('permissions', [])

def get_admin_ids() -> List[int]:
    """Retourne la liste des IDs admin actifs"""
    admins = ADMINS_DATA.get('admins', {})
    return [int(uid) for uid, data in admins.items() if data.get('active', True)]

# ==================== DÉCORATEURS ET LOGGING ====================

def error_handler(func):
    """Décorateur pour gérer les erreurs"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"❌ Erreur dans {func.__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Notifier l'utilisateur
            try:
                if update.callback_query:
                    await update.callback_query.answer("❌ Une erreur est survenue", show_alert=True)
                elif update.message:
                    await update.message.reply_text("❌ Une erreur est survenue. Veuillez réessayer.")
            except:
                pass
    
    return wrapper

def log_callback(func):
    """Décorateur pour logger les callbacks"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        callback_data = query.data
        
        logger.info(f"🔘 CALLBACK: {func.__name__} | User: {user_id} | Data: {callback_data}")
        
        return await func(update, context)
    
    return wrapper

# ==================== FONCTIONS UTILITAIRES ====================

def anonymize_id(user_id: int) -> str:
    """Anonymise un ID Telegram"""
    hash_obj = hashlib.sha256(str(user_id).encode())
    return f"User-{hash_obj.hexdigest()[:8].upper()}"

def anonymize_admin_id(admin_id: int) -> str:
    """Anonymise un ID admin"""
    hash_obj = hashlib.sha256(str(admin_id).encode())
    return f"Admin-{hash_obj.hexdigest()[:8].upper()}"

def log_user_action(user_id: int, action: str, details: str = "", level: str = "info"):
    """Log une action utilisateur avec ID anonymisé"""
    anon_id = anonymize_id(user_id)
    message = f"👤 [{action}] {anon_id}"
    if details:
        message += f" | {details}"
    
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)

def log_admin_action(admin_id: int, action: str, details: str = "", level: str = "info"):
    """Log une action admin avec ID anonymisé"""
    anon_id = anonymize_admin_id(admin_id)
    message = f"🔑 [{action}] {anon_id}"
    if details:
        message += f" | {details}"
    
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)

def format_price(amount: float, country: str = 'FR') -> str:
    """Formate un prix avec la devise du pays"""
    countries = get_countries()
    currency = countries.get(country, {}).get('currency', 'EUR')
    return f"{amount:.2f}{currency}"

def get_emoji(emoji_name: str) -> str:
    """Récupère un emoji depuis la config"""
    theme = CONFIG_DATA.get('theme', {})
    emojis = theme.get('emojis', {})
    return emojis.get(emoji_name, '•')

logger.info("✅ Core système chargé")
# ==================== GESTION DES UTILISATEURS ====================

def load_users() -> Dict:
    """Charge la base utilisateurs"""
    return load_json_file(USERS_FILE, {})

def save_users(users: Dict) -> bool:
    """Sauvegarde la base utilisateurs"""
    return save_json_file(USERS_FILE, users)

def is_new_user(user_id: int) -> bool:
    """Vérifie si c'est un nouvel utilisateur"""
    users = load_users()
    return str(user_id) not in users

def add_user(user_id: int, user_data: Dict) -> bool:
    """Ajoute un nouvel utilisateur"""
    users = load_users()
    users[str(user_id)] = {
        **user_data,
        'registered_at': datetime.now().isoformat(),
        'total_spent': 0,
        'order_count': 0,
        'vip_status': False
    }
    return save_users(users)

def get_user_data(user_id: int) -> Optional[Dict]:
    """Récupère les données d'un utilisateur"""
    users = load_users()
    return users.get(str(user_id))

def update_user_visit(user_id: int) -> bool:
    """Met à jour la dernière visite d'un utilisateur"""
    users = load_users()
    user_id_str = str(user_id)
    
    if user_id_str in users:
        users[user_id_str]['last_visit'] = datetime.now().isoformat()
        return save_users(users)
    
    return False

# ==================== GESTION DU PANIER ====================

def get_cart(context: ContextTypes.DEFAULT_TYPE) -> Dict:
    """Récupère le panier de l'utilisateur"""
    return context.user_data.get('cart', {})

def add_to_cart(context: ContextTypes.DEFAULT_TYPE, product_id: str, quantity: float) -> bool:
    """Ajoute un produit au panier"""
    cart = get_cart(context)
    
    if product_id in cart:
        cart[product_id] += quantity
    else:
        cart[product_id] = quantity
    
    context.user_data['cart'] = cart
    return True

def remove_from_cart(context: ContextTypes.DEFAULT_TYPE, product_id: str) -> bool:
    """Retire un produit du panier"""
    cart = get_cart(context)
    
    if product_id in cart:
        del cart[product_id]
        context.user_data['cart'] = cart
        return True
    
    return False

def clear_cart(context: ContextTypes.DEFAULT_TYPE):
    """Vide le panier"""
    context.user_data['cart'] = {}

def get_cart_total(context: ContextTypes.DEFAULT_TYPE, country: str = 'FR') -> float:
    """Calcule le total du panier"""
    cart = get_cart(context)
    total = 0.0
    
    for product_id, quantity in cart.items():
        price = get_product_price(product_id, country)
        total += price * quantity
    
    return total

def get_cart_summary(context: ContextTypes.DEFAULT_TYPE, lang: str = 'fr', country: str = 'FR') -> str:
    """Génère un résumé du panier"""
    cart = get_cart(context)
    
    if not cart:
        return t('empty_cart', lang)
    
    lines = []
    total = 0.0
    
    for product_id, quantity in cart.items():
        product = get_product(product_id)
        if not product:
            continue
        
        name = get_product_name(product_id, lang)
        emoji = product.get('emoji', '')
        unit = product.get('unit', 'unité')
        price = get_product_price(product_id, country)
        line_total = price * quantity
        total += line_total
        
        lines.append(f"{emoji} {name} - {quantity}{unit} = {format_price(line_total, country)}")
    
    summary = "\n".join(lines)
    summary += f"\n\n{t('total', lang)}: {format_price(total, country)}"
    
    return summary

# ==================== GESTION VIP ====================

def load_vip_config() -> Dict:
    """Charge la configuration VIP"""
    return load_json_file(VIP_CONFIG_FILE, {"threshold": 500, "discount": 5})

def get_vip_threshold() -> float:
    """Récupère le seuil VIP"""
    config = load_vip_config()
    return float(config.get('threshold', 500))

def get_vip_discount() -> float:
    """Récupère la réduction VIP"""
    config = load_vip_config()
    return float(config.get('discount', 5))

def is_vip(user_id: int) -> bool:
    """Vérifie si un utilisateur est VIP"""
    if not check_feature('vip_system'):
        return False
    
    users = load_users()
    user = users.get(str(user_id), {})
    return user.get('vip_status', False)

def get_client_stats(user_id: int) -> Optional[Dict]:
    """Récupère les statistiques d'un client"""
    users = load_users()
    user = users.get(str(user_id))
    
    if not user:
        return None
    
    return {
        'total_spent': user.get('total_spent', 0),
        'order_count': user.get('order_count', 0),
        'vip_status': user.get('vip_status', False),
        'registered_at': user.get('registered_at', '')
    }

def apply_vip_discount(amount: float, user_id: int) -> float:
    """Applique la réduction VIP si applicable"""
    if not is_vip(user_id):
        return amount
    
    discount_percent = get_vip_discount()
    discount = amount * (discount_percent / 100)
    
    return amount - discount

# ==================== GESTION DES COMMANDES ====================

def generate_order_id() -> str:
    """Génère un ID de commande unique"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:6]
    return f"CMD{timestamp}{random_suffix.upper()}"

def save_order(order_data: Dict) -> bool:
    """Sauvegarde une commande dans orders.csv"""
    try:
        file_exists = ORDERS_FILE.exists()
        
        with open(ORDERS_FILE, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ['order_id', 'timestamp', 'user_id', 'username', 'first_name', 
                         'country', 'delivery_mode', 'address', 'payment_method', 
                         'products', 'total', 'status', 'notes']
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(order_data)
        
        logger.info(f"💾 Commande sauvegardée : {order_data['order_id']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde commande : {e}")
        return False

def update_client_history(user_id: int, order_total: float) -> bool:
    """Met à jour l'historique client"""
    users = load_users()
    user_id_str = str(user_id)
    
    if user_id_str not in users:
        return False
    
    users[user_id_str]['total_spent'] = users[user_id_str].get('total_spent', 0) + order_total
    users[user_id_str]['order_count'] = users[user_id_str].get('order_count', 0) + 1
    users[user_id_str]['last_order'] = datetime.now().isoformat()
    
    # Vérifier éligibilité VIP
    if check_feature('vip_system'):
        threshold = get_vip_threshold()
        if users[user_id_str]['total_spent'] >= threshold:
            users[user_id_str]['vip_status'] = True
    
    return save_users(users)

# ==================== GESTION DU LIVRE DE COMPTES ====================

def load_ledger() -> Dict:
    """Charge le livre de comptes"""
    return load_json_file(LEDGER_FILE, {
        "ledgers": {
            "weed": {"name": "Caisse WEED", "balance": 0, "entries": []},
            "autres": {"name": "Caisse AUTRES", "balance": 0, "entries": []}
        }
    })

def save_ledger(ledger_data: Dict) -> bool:
    """Sauvegarde le livre de comptes"""
    return save_json_file(LEDGER_FILE, ledger_data)

def add_ledger_entry(ledger_type: str, amount: float, category: str, description: str, order_id: str = "") -> bool:
    """Ajoute une entrée dans le livre de comptes"""
    if not check_feature('accounting'):
        return False
    
    ledger_data = load_ledger()
    
    if ledger_type not in ledger_data['ledgers']:
        logger.error(f"❌ Type de caisse inconnu : {ledger_type}")
        return False
    
    entry = {
        'timestamp': datetime.now().isoformat(),
        'amount': amount,
        'category': category,
        'description': description,
        'order_id': order_id
    }
    
    ledger_data['ledgers'][ledger_type]['entries'].append(entry)
    ledger_data['ledgers'][ledger_type]['balance'] += amount
    
    return save_ledger(ledger_data)

def get_ledger_balance(ledger_type: str) -> float:
    """Récupère le solde d'une caisse"""
    ledger_data = load_ledger()
    return ledger_data['ledgers'].get(ledger_type, {}).get('balance', 0)

# ==================== GESTION DES CODES PROMO ====================

def get_promo_codes() -> Dict:
    """Récupère tous les codes promo"""
    return CONFIG_DATA.get('promo_codes', {})

def validate_promo_code(code: str, order_total: float) -> Optional[Dict]:
    """Valide un code promo"""
    if not check_feature('promo_codes'):
        return None
    
    promo_codes = get_promo_codes()
    promo = promo_codes.get(code.upper())
    
    if not promo:
        return None
    
    if not promo.get('active', True):
        return None
    
    # Vérifier montant minimum
    min_order = promo.get('min_order', 0)
    if order_total < min_order:
        return None
    
    # Vérifier expiration
    expires = promo.get('expires')
    if expires:
        expiry_date = datetime.fromisoformat(expires)
        if datetime.now() > expiry_date:
            return None
    
    return promo

def apply_promo_code(amount: float, promo: Dict) -> float:
    """Applique un code promo"""
    promo_type = promo.get('type', 'percent')
    value = promo.get('value', 0)
    
    if promo_type == 'percent':
        discount = amount * (value / 100)
    else:  # fixed
        discount = value
    
    return max(0, amount - discount)

# ==================== MAINTENANCE ====================

def is_maintenance_mode(user_id: int) -> bool:
    """Vérifie si le mode maintenance est actif"""
    security = CONFIG_DATA.get('security', {})
    maintenance = security.get('maintenance', {})
    
    if not maintenance.get('active', False):
        return False
    
    # Admins et utilisateurs autorisés peuvent accéder
    allowed_users = maintenance.get('allowed_users', [])
    if is_admin(user_id) or str(user_id) in allowed_users:
        return False
    
    return True

def get_maintenance_message(lang: str = 'fr') -> str:
    """Récupère le message de maintenance"""
    security = CONFIG_DATA.get('security', {})
    maintenance = security.get('maintenance', {})
    message = maintenance.get('message', {})
    
    return message.get(lang, t('error', lang))

logger.info("✅ Gestion utilisateurs et commandes chargée")
# ==================== HANDLER: START ====================

@error_handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour la commande /start"""
    user = update.effective_user
    user_id = user.id
    
    # LOG ACTION
    log_user_action(user_id, "START", f"Démarrage bot - Nom: {user.first_name}")
    
    # Vérifier maintenance
    if is_maintenance_mode(user_id):
        lang = get_user_language(context)
        await update.message.reply_text(get_maintenance_message(lang))
        return
    
    # Enregistrer nouvel utilisateur
    if is_new_user(user_id):
        user_data = {
            "username": user.username or "N/A",
            "first_name": user.first_name or "Utilisateur",
            "last_name": user.last_name or "",
            "language_code": user.language_code or "fr"
        }
        add_user(user_id, user_data)
        logger.info(f"🆕 Nouvel utilisateur: {user_id} - {user_data['first_name']}")
        
        # Notifier admins
        await notify_admin_new_user(context, user_id, user_data)
        
        # Sélection de langue
        await select_language(update, context, is_new=True)
    else:
        update_user_visit(user_id)
        
        # Si pas de langue, demander
        if 'language' not in context.user_data:
            await select_language(update, context)
        # Si pas de pays, demander
        elif 'country' not in context.user_data:
            await select_country(update, context)
        else:
            await show_main_menu(update, context)

# ==================== SÉLECTION LANGUE ====================

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE, is_new: bool = False):
    """Affiche le menu de sélection de langue"""
    languages = LANGUAGES_DATA.get('languages', {})
    
    keyboard = []
    for lang_code, lang_data in languages.items():
        if lang_data.get('active', True):
            flag = lang_data.get('flag', '')
            name = lang_data.get('name', lang_code)
            button = InlineKeyboardButton(f"{flag} {name}", callback_data=f"lang_{lang_code}")
            keyboard.append([button])
    
    message = "🌍 CHOISIR LA LANGUE / CHOOSE LANGUAGE / SPRACHE WÄHLEN / ELEGIR IDIOMA / SCEGLI LINGUA"
    
    if is_new:
        message = f"🎉 BIENVENUE / WELCOME / WILLKOMMEN / BIENVENIDO / BENVENUTO\n\n{message}"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

@error_handler
@log_callback
async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour la sélection de langue"""
    query = update.callback_query
    await query.answer()
    
    lang_code = query.data.replace("lang_", "")
    context.user_data['language'] = lang_code
    
    log_user_action(query.from_user.id, "SELECT_LANGUAGE", f"Langue: {lang_code}")
    
    # Passer à la sélection du pays
    await select_country(update, context)

# ==================== SÉLECTION PAYS ====================

async def select_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu de sélection de pays"""
    lang = get_user_language(context)
    countries = get_countries()
    
    keyboard = []
    for country_code, country_data in countries.items():
        if country_data.get('active', True):
            flag = country_data.get('flag', '')
            name = country_data.get('name', country_code)
            button = InlineKeyboardButton(f"{flag} {name}", callback_data=f"country_{country_code}")
            keyboard.append([button])
    
    # Bouton aide
    keyboard.append([InlineKeyboardButton(t('help', lang), callback_data="help")])
    
    message = t('choose_country', lang)
    
    query = update.callback_query
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
@log_callback
async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour la sélection de pays"""
    query = update.callback_query
    await query.answer()
    
    country_code = query.data.replace("country_", "")
    context.user_data['country'] = country_code
    
    log_user_action(query.from_user.id, "SELECT_COUNTRY", f"Pays: {country_code}")
    
    # Afficher le menu principal
    await show_main_menu(update, context)

# ==================== MENU PRINCIPAL ====================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu principal"""
    lang = get_user_language(context)
    country = context.user_data.get('country', 'FR')
    user_id = update.effective_user.id if update.effective_user else None
    
    # Message de bienvenue
    user_data = get_user_data(user_id) if user_id else {}
    first_name = user_data.get('first_name', 'Utilisateur')
    
    message = t('welcome', lang, name=first_name)
    message += f"\n\n{get_country_name(country, lang)}"
    
    # Statut VIP
    if user_id and is_vip(user_id):
        discount = get_vip_discount()
        message += f"\n\n{t('vip_discount', lang, percent=discount)}"
    
    # Boutons
    keyboard = [
        [InlineKeyboardButton(t('view_products', lang), callback_data="view_products")],
        [InlineKeyboardButton(t('cart', lang), callback_data="view_cart")],
        [
            InlineKeyboardButton(t('help', lang), callback_data="help"),
            InlineKeyboardButton(t('choose_language', lang), callback_data="change_language")
        ]
    ]
    
    # Bouton admin si admin
    if user_id and is_admin(user_id):
        keyboard.append([InlineKeyboardButton("🎛️ Admin", callback_data="admin_panel")])
    
    query = update.callback_query
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

# ==================== CATALOGUE PRODUITS ====================

@error_handler
@log_callback
async def view_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les catégories de produits"""
    query = update.callback_query
    await query.answer()
    
    lang = get_user_language(context)
    categories = get_categories()
    
    message = t('view_products', lang)
    
    # Boutons des catégories
    keyboard = []
    for cat_id, cat_data in sorted(categories.items(), key=lambda x: x[1].get('order', 0)):
        if cat_data.get('active', True):
            emoji = cat_data.get('emoji', '📦')
            name = get_category_name(cat_id, lang)
            button = InlineKeyboardButton(f"{emoji} {name}", callback_data=f"cat_{cat_id}")
            keyboard.append([button])
    
    # Bouton retour
    keyboard.append([InlineKeyboardButton(t('back', lang), callback_data="back_main")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
@log_callback
async def view_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les produits d'une catégorie"""
    query = update.callback_query
    await query.answer()
    
    category_id = query.data.replace("cat_", "")
    lang = get_user_language(context)
    country = context.user_data.get('country', 'FR')
    
    # Récupérer les produits
    products = get_products_by_category(category_id)
    
    if not products:
        await query.answer(t('error', lang), show_alert=True)
        return
    
    # Message
    category_name = get_category_name(category_id, lang)
    message = f"{category_name}\n\n"
    
    # Boutons des produits
    keyboard = []
    for product in products:
        product_id = product['id']
        name = get_product_name(product_id, lang)
        emoji = product.get('emoji', '📦')
        price = get_product_price(product_id, country)
        unit = product.get('unit', 'unité')
        stock = get_product_stock(product_id)
        
        # Afficher stock
        stock_emoji = "✅" if stock > 50 else ("⚠️" if stock > 10 else "❌")
        
        button_text = f"{emoji} {name} - {format_price(price, country)}/{unit} {stock_emoji}"
        button = InlineKeyboardButton(button_text, callback_data=f"prod_{product_id}")
        keyboard.append([button])
    
    # Boutons navigation
    keyboard.append([
        InlineKeyboardButton(t('cart', lang), callback_data="view_cart"),
        InlineKeyboardButton(t('back', lang), callback_data="view_products")
    ])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
@log_callback
async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les détails d'un produit"""
    query = update.callback_query
    await query.answer()
    
    product_id = query.data.replace("prod_", "")
    lang = get_user_language(context)
    country = context.user_data.get('country', 'FR')
    
    product = get_product(product_id)
    if not product:
        await query.answer(t('error', lang), show_alert=True)
        return
    
    # Message
    name = get_product_name(product_id, lang)
    emoji = product.get('emoji', '📦')
    price = get_product_price(product_id, country)
    unit = product.get('unit', 'unité')
    stock = get_product_stock(product_id)
    
    # Description
    description = product.get('description', {})
    if isinstance(description, dict):
        desc_text = description.get(lang, description.get('fr', ''))
    else:
        desc_text = str(description)
    
    message = f"{emoji} **{name}**\n\n"
    message += f"{desc_text}\n\n"
    message += f"💰 Prix: {format_price(price, country)}/{unit}\n"
    message += f"📦 {t('stock_available', lang, stock=stock, unit=unit)}"
    
    # Boutons quantités
    keyboard = []
    quantities = product.get('available_quantities', [1, 2, 5, 10])
    
    row = []
    for qty in quantities:
        if stock >= qty:
            row.append(InlineKeyboardButton(f"{qty}{unit}", callback_data=f"add_{product_id}_{qty}"))
            
            if len(row) == 3:
                keyboard.append(row)
                row = []
    
    if row:
        keyboard.append(row)
    
    # Boutons navigation
    category_id = product.get('category', '')
    keyboard.append([
        InlineKeyboardButton(t('cart', lang), callback_data="view_cart"),
        InlineKeyboardButton(t('back', lang), callback_data=f"cat_{category_id}")
    ])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

@error_handler
@log_callback
async def add_product_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajoute un produit au panier"""
    query = update.callback_query
    
    # Extraire product_id et quantité
    parts = query.data.replace("add_", "").split("_")
    product_id = "_".join(parts[:-1])
    quantity = float(parts[-1])
    
    lang = get_user_language(context)
    
    # Vérifier stock
    stock = get_product_stock(product_id)
    if stock < quantity:
        await query.answer(t('out_of_stock', lang), show_alert=True)
        return
    
    # Ajouter au panier
    add_to_cart(context, product_id, quantity)
    
    log_user_action(query.from_user.id, "ADD_TO_CART", f"Produit: {product_id} x{quantity}")
    
    # Notification
    name = get_product_name(product_id, lang)
    product = get_product(product_id)
    unit = product.get('unit', 'unité') if product else 'unité'
    
    await query.answer(f"✅ {name} ({quantity}{unit}) ajouté au panier", show_alert=False)
    
    # Retour au produit
    await view_product(update, context)

logger.info("✅ Handlers principaux chargés")
# ==================== HANDLER: PANIER ====================

@error_handler
@log_callback
async def view_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le panier"""
    query = update.callback_query
    await query.answer()
    
    lang = get_user_language(context)
    country = context.user_data.get('country', 'FR')
    cart = get_cart(context)
    
    if not cart:
        message = t('empty_cart', lang)
        keyboard = [[InlineKeyboardButton(t('view_products', lang), callback_data="view_products")]]
    else:
        # Résumé panier
        message = f"{t('cart', lang)}\n\n"
        message += get_cart_summary(context, lang, country)
        
        # Appliquer VIP si applicable
        subtotal = get_cart_total(context, country)
        user_id = query.from_user.id
        
        if is_vip(user_id):
            discount_percent = get_vip_discount()
            discount = subtotal * (discount_percent / 100)
            total = subtotal - discount
            message += f"\n\n{t('vip_discount', lang, percent=discount_percent)}: -{format_price(discount, country)}"
            message += f"\n{t('total', lang)}: {format_price(total, country)}"
        
        # Boutons
        keyboard = [
            [InlineKeyboardButton(t('confirm_order', lang), callback_data="start_order")],
            [InlineKeyboardButton("🗑️ Vider le panier", callback_data="clear_cart")],
            [InlineKeyboardButton(t('view_products', lang), callback_data="view_products")],
            [InlineKeyboardButton(t('back', lang), callback_data="back_main")]
        ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
@log_callback
async def clear_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vide le panier"""
    query = update.callback_query
    
    clear_cart(context)
    
    lang = get_user_language(context)
    await query.answer("🗑️ Panier vidé", show_alert=False)
    
    await view_cart_handler(update, context)

# ==================== PROCESSUS DE COMMANDE ====================

@error_handler
@log_callback
async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Démarre le processus de commande"""
    query = update.callback_query
    await query.answer()
    
    lang = get_user_language(context)
    country = context.user_data.get('country', 'FR')
    
    # Vérifier que le panier n'est pas vide
    cart = get_cart(context)
    if not cart:
        await query.answer(t('empty_cart', lang), show_alert=True)
        return
    
    # Sélection mode de livraison
    await select_delivery_mode(update, context)

async def select_delivery_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du mode de livraison"""
    query = update.callback_query
    lang = get_user_language(context)
    country = context.user_data.get('country', 'FR')
    
    delivery_modes = get_delivery_modes(country)
    
    message = f"{t('delivery_mode', lang)}\n\n"
    
    keyboard = []
    for mode_id, mode_data in delivery_modes.items():
        if mode_data.get('enabled', True):
            fee = mode_data.get('fee', 0)
            delay = mode_data.get('delay', '')
            
            desc = mode_data.get('description', {})
            if isinstance(desc, dict):
                desc_text = desc.get(lang, desc.get('fr', mode_id))
            else:
                desc_text = str(desc)
            
            if mode_id == 'postal':
                emoji = "📮"
                button_text = f"{emoji} {t('postal', lang)} - {format_price(fee, country)}"
            elif mode_id == 'express':
                emoji = "🚀"
                button_text = f"{emoji} {t('express', lang)} - Variable"
            elif mode_id == 'meetup':
                emoji = "🤝"
                button_text = f"{emoji} {t('meetup', lang)} - Gratuit"
            else:
                emoji = "🚚"
                button_text = f"{emoji} {mode_id} - {format_price(fee, country)}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delivery_{mode_id}")])
    
    keyboard.append([InlineKeyboardButton(t('cancel', lang), callback_data="view_cart")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@error_handler
@log_callback
async def delivery_mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler sélection mode de livraison"""
    query = update.callback_query
    await query.answer()
    
    mode = query.data.replace("delivery_", "")
    context.user_data['delivery_mode'] = mode
    
    lang = get_user_language(context)
    
    # Si meetup, pas d'adresse nécessaire
    if mode == 'meetup':
        context.user_data['address'] = "Meetup"
        await select_payment_method(update, context)
    else:
        # Demander l'adresse
        message = t('enter_address', lang)
        keyboard = [[InlineKeyboardButton(t('cancel', lang), callback_data="view_cart")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data['awaiting_address'] = True

async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection méthode de paiement"""
    query = update.callback_query if update.callback_query else None
    lang = get_user_language(context)
    
    message = f"{t('payment_method', lang)}\n\n"
    
    payment_methods = CONFIG_DATA.get('payment', {}).get('methods', {})
    
    keyboard = []
    
    # Crypto
    if payment_methods.get('crypto', {}).get('enabled', False):
        keyboard.append([InlineKeyboardButton(t('crypto', lang), callback_data="payment_crypto")])
    
    # Cash (si meetup uniquement)
    delivery_mode = context.user_data.get('delivery_mode', '')
    if payment_methods.get('cash', {}).get('enabled', False):
        if delivery_mode == 'meetup' or not payment_methods['cash'].get('meetup_only', False):
            keyboard.append([InlineKeyboardButton(t('cash', lang), callback_data="payment_cash")])
    
    keyboard.append([InlineKeyboardButton(t('cancel', lang), callback_data="view_cart")])
    
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
@log_callback
async def payment_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler sélection méthode de paiement"""
    query = update.callback_query
    await query.answer()
    
    method = query.data.replace("payment_", "")
    context.user_data['payment_method'] = method
    
    # Récapitulatif commande
    await show_order_summary(update, context)

async def show_order_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le récapitulatif de la commande"""
    query = update.callback_query
    lang = get_user_language(context)
    country = context.user_data.get('country', 'FR')
    user_id = query.from_user.id
    
    # Récupérer les données
    cart = get_cart(context)
    delivery_mode = context.user_data.get('delivery_mode', '')
    address = context.user_data.get('address', '')
    payment_method = context.user_data.get('payment_method', '')
    
    # Calculer le total
    subtotal = get_cart_total(context, country)
    delivery_fee = get_delivery_fee(country, delivery_mode)
    
    # Appliquer VIP
    vip_discount = 0
    if is_vip(user_id):
        discount_percent = get_vip_discount()
        vip_discount = subtotal * (discount_percent / 100)
    
    # Appliquer code promo si présent
    promo_discount = 0
    promo_code = context.user_data.get('promo_code')
    if promo_code:
        promo = validate_promo_code(promo_code, subtotal)
        if promo:
            promo_type = promo.get('type', 'percent')
            value = promo.get('value', 0)
            if promo_type == 'percent':
                promo_discount = subtotal * (value / 100)
            else:
                promo_discount = value
    
    total = subtotal - vip_discount - promo_discount + delivery_fee
    
    # Message
    message = f"📋 RÉCAPITULATIF\n\n"
    message += get_cart_summary(context, lang, country)
    message += f"\n\n🚚 {t('delivery', lang)}: {delivery_mode.upper()}"
    if delivery_mode != 'meetup':
        message += f"\n📍 Adresse: {address}"
    message += f"\n💰 Frais livraison: {format_price(delivery_fee, country)}"
    
    if vip_discount > 0:
        message += f"\n⭐ Réduction VIP: -{format_price(vip_discount, country)}"
    
    if promo_discount > 0:
        message += f"\n🎁 Code promo: -{format_price(promo_discount, country)}"
    
    message += f"\n\n💳 {t('payment', lang)}: {payment_method.upper()}"
    message += f"\n\n{t('total', lang)}: **{format_price(total, country)}**"
    
    keyboard = [
        [InlineKeyboardButton(t('confirm_order', lang), callback_data="confirm_order")],
        [InlineKeyboardButton(t('cancel', lang), callback_data="view_cart")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

@error_handler
@log_callback
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirme et enregistre la commande"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = user.id
    lang = get_user_language(context)
    country = context.user_data.get('country', 'FR')
    
    # Générer ID commande
    order_id = generate_order_id()
    
    # Récupérer données
    cart = get_cart(context)
    delivery_mode = context.user_data.get('delivery_mode', '')
    address = context.user_data.get('address', '')
    payment_method = context.user_data.get('payment_method', '')
    
    # Calculer totaux
    subtotal = get_cart_total(context, country)
    delivery_fee = get_delivery_fee(country, delivery_mode)
    
    vip_discount = 0
    if is_vip(user_id):
        discount_percent = get_vip_discount()
        vip_discount = subtotal * (discount_percent / 100)
    
    total = subtotal - vip_discount + delivery_fee
    
    # Préparer données commande
    products_str = json.dumps(cart)
    
    order_data = {
        'order_id': order_id,
        'timestamp': datetime.now().isoformat(),
        'user_id': user_id,
        'username': user.username or 'N/A',
        'first_name': user.first_name or 'N/A',
        'country': country,
        'delivery_mode': delivery_mode,
        'address': address,
        'payment_method': payment_method,
        'products': products_str,
        'total': total,
        'status': 'pending',
        'notes': ''
    }
    
    # Sauvegarder commande
    if save_order(order_data):
        # Déduire stocks
        for product_id, quantity in cart.items():
            deduct_stock(product_id, quantity)
        
        # Mettre à jour historique client
        update_client_history(user_id, total)
        
        # Ajouter au livre de comptes (si niveau 3)
        if check_feature('accounting'):
            for product_id, quantity in cart.items():
                product = get_product(product_id)
                ledger_type = product.get('ledger_type', 'autres') if product else 'autres'
                price = get_product_price(product_id, country)
                amount = price * quantity
                add_ledger_entry(ledger_type, amount, 'vente', f"Commande {order_id}", order_id)
            
            # Frais de livraison
            if delivery_fee > 0:
                add_ledger_entry('weed', delivery_fee, 'livraison', f"Livraison {order_id}", order_id)
        
        # Vider le panier
        clear_cart(context)
        
        # Notifier l'utilisateur
        message = f"{t('order_confirmed', lang)}\n\n"
        message += f"{t('order_number', lang, order_id=order_id)}\n"
        message += f"{t('total', lang)}: {format_price(total, country)}\n\n"
        message += t('thank_you', lang)
        
        # Notifier les admins
        await notify_admin_new_order(context, order_data, user)
        
        keyboard = [[InlineKeyboardButton(t('back', lang), callback_data="back_main")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        log_user_action(user_id, "ORDER_CONFIRMED", f"Commande: {order_id} | Total: {total}€")
    else:
        await query.answer("❌ Erreur enregistrement commande", show_alert=True)

# ==================== NOTIFICATIONS ADMIN ====================

async def notify_admin_new_user(context: ContextTypes.DEFAULT_TYPE, user_id: int, user_data: Dict):
    """Notifie les admins d'un nouvel utilisateur"""
    username = user_data.get("username", "N/A")
    first_name = user_data.get("first_name", "N/A")
    last_name = user_data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()
    
    anonymous_id = anonymize_id(user_id)
    
    notification = f"{get_emoji('celebration')} NOUVELLE CONNEXION\n\n"
    notification += f"👤 Utilisateur :\n"
    notification += f"- Nom : {full_name}\n"
    notification += f"- Username : @{username if username != 'N/A' else 'Non défini'}\n"
    notification += f"- ID Anonyme : {anonymous_id}\n\n"
    notification += f"💬 Chat ID : <code>{user_id}</code>\n"
    notification += f"(Cliquez pour copier)\n\n"
    notification += f"📅 Date : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    
    keyboard = [[InlineKeyboardButton("💬 Envoyer un message", callback_data=f"send_msg_{user_id}")]]
    
    try:
        for admin_id in get_admin_ids():
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"❌ Erreur notification admin: {e}")

async def notify_admin_new_order(context: ContextTypes.DEFAULT_TYPE, order_data: Dict, user):
    """Notifie les admins d'une nouvelle commande"""
    order_id = order_data['order_id']
    total = order_data['total']
    products = json.loads(order_data['products'])
    
    notification = f"{get_emoji('celebration')} NOUVELLE COMMANDE\n\n"
    notification += f"📋 Commande : {order_id}\n"
    notification += f"👤 Client : {user.first_name}\n"
    notification += f"💰 Total : {total}€\n\n"
    notification += f"📦 Produits :\n"
    
    for product_id, quantity in products.items():
        product = get_product(product_id)
        if product:
            name = get_product_name(product_id, 'fr')
            unit = product.get('unit', 'unité')
            notification += f"• {name} x {quantity}{unit}\n"
    
    notification += f"\n🚚 Livraison : {order_data['delivery_mode']}\n"
    notification += f"📍 Adresse : {order_data['address']}\n"
    notification += f"💳 Paiement : {order_data['payment_method']}"
    
    try:
        for admin_id in get_admin_ids():
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification
            )
    except Exception as e:
        logger.error(f"❌ Erreur notification admin: {e}")

# ==================== HANDLER: TEXTE ====================

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour les messages texte"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Log
    log_user_action(user_id, "TEXT_MESSAGE", f"Texte: '{text[:50]}'")
    
    # État: En attente d'adresse
    if context.user_data.get('awaiting_address'):
        context.user_data['address'] = text
        context.user_data.pop('awaiting_address', None)
        
        # Passer au paiement
        await select_payment_method(update, context)
        return
    
    # Autre état
    lang = get_user_language(context)
    await update.message.reply_text(t('error', lang))

# ==================== HANDLER: ADMIN ====================

@error_handler
@log_callback
@require_level(1)
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Panel administrateur"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.answer("❌ Accès refusé", show_alert=True)
        return
    
    log_admin_action(user_id, "ADMIN_PANEL", "Accès au panel admin")
    
    level = get_license_level()
    level_badges = {1: "🥉 Starter", 2: "🥈 Business", 3: "🥇 Enterprise"}
    
    message = f"🎛️ PANEL ADMINISTRATEUR\n\nNiveau : {level_badges.get(level, 'Inconnu')}\n\nChoisissez une section :"
    
    keyboard = [
        [InlineKeyboardButton("📦 Produits", callback_data="admin_products")],
        [InlineKeyboardButton("🛒 Commandes", callback_data="admin_orders")],
    ]
    
    # Niveau 2+
    if level >= 2:
        keyboard.append([InlineKeyboardButton("📊 Statistiques", callback_data="admin_stats")])
        keyboard.append([InlineKeyboardButton("⭐ VIP", callback_data="admin_vip")])
    
    # Niveau 3
    if level >= 3:
        keyboard.append([InlineKeyboardButton("💰 Finances", callback_data="admin_finances")])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="back_main")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== MAIN ====================

def main():
    """Point d'entrée principal"""
    
    # Créer l'application
    token = CONFIG_DATA.get('bot_token')
    if not token or token == "VOTRE_BOT_TOKEN_ICI":
        logger.error("❌ Token bot non configuré dans config.json")
        sys.exit(1)
    
    persistence = PicklePersistence(filepath="/data/bot_data")
    application = Application.builder().token(token).persistence(persistence).build()
    
    # Handlers commandes
    application.add_handler(CommandHandler("start", start))
    
    # Handlers callbacks
    application.add_handler(CallbackQueryHandler(language_selected, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern="^back_main$"))
    application.add_handler(CallbackQueryHandler(select_language, pattern="^change_language$"))
    
    # Produits
    application.add_handler(CallbackQueryHandler(view_products, pattern="^view_products$"))
    application.add_handler(CallbackQueryHandler(view_category, pattern="^cat_"))
    application.add_handler(CallbackQueryHandler(view_product, pattern="^prod_"))
    application.add_handler(CallbackQueryHandler(add_product_to_cart, pattern="^add_"))
    
    # Panier
    application.add_handler(CallbackQueryHandler(view_cart_handler, pattern="^view_cart$"))
    application.add_handler(CallbackQueryHandler(clear_cart_handler, pattern="^clear_cart$"))
    
    # Commande
    application.add_handler(CallbackQueryHandler(start_order, pattern="^start_order$"))
    application.add_handler(CallbackQueryHandler(delivery_mode_selected, pattern="^delivery_"))
    application.add_handler(CallbackQueryHandler(payment_method_selected, pattern="^payment_"))
    application.add_handler(CallbackQueryHandler(confirm_order, pattern="^confirm_order$"))
    
    # Admin
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    
    # Messages texte
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    logger.info(f"""
╔════════════════════════════════════════╗
║   BOT V{BOT_VERSION} - PRÊT !                 ║
╚════════════════════════════════════════╝

🚀 Le bot est en ligne !
📦 Produits : {len(PRODUCTS_DATA.get('products', {}))}
🔐 Licence : Niveau {get_license_level()}
👥 Admins : {len(get_admin_ids())}
""")
    
    # Démarrer le bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
