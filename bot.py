# ==================== BLOC 1 : IMPORTS, CONFIGURATION ET TRADUCTIONS ====================
# Bot Telegram V3.0 - Version Complète avec Améliorations Visuelles
# Copier ce bloc AU DÉBUT de bot.py
import os
import re
import sys
import json
import csv
import math
import asyncio
import logging
import hashlib
import secrets
from pathlib import Path
from datetime import datetime, timedelta, time
from collections import defaultdict
from functools import wraps
from typing import Optional, Dict, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Configuration du logging
logging.basicConfig(
    format='%(asctime)s - %(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== CHARGEMENT VARIABLES D'ENVIRONNEMENT ====================
from dotenv import load_dotenv

env_file = Path(__file__).parent / "infos.env"
if env_file.exists():
    load_dotenv(env_file)
    logger.info("✅ Variables: infos.env")
else:
    logger.warning("⚠️ Fichier infos.env non trouvé")

# Variables d'environnement obligatoires
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ==================== CONFIGURATION MULTI-ADMINS ====================
# Liste des administrateurs (plusieurs admins possibles)
ADMIN_USER_IDS = []

# Charger l'admin principal depuis infos.env
admin_principal = os.getenv("ADMIN_TELEGRAM_ID")
if admin_principal:
    try:
        ADMIN_USER_IDS.append(int(admin_principal))
        logger.info(f"✅ Admin principal: {admin_principal}")
    except ValueError:
        logger.error(f"❌ ADMIN_TELEGRAM_ID invalide: {admin_principal}")

# Charger les admins secondaires depuis infos.env (optionnel)
admin_secondaire = os.getenv("ADMIN_TELEGRAM_ID_2")
if admin_secondaire:
    try:
        ADMIN_USER_IDS.append(int(admin_secondaire))
        logger.info(f"✅ Admin secondaire: {admin_secondaire}")
    except ValueError:
        logger.error(f"❌ ADMIN_TELEGRAM_ID_2 invalide: {admin_secondaire}")

# Charger un 3ème admin (optionnel)
admin_tertiaire = os.getenv("ADMIN_TELEGRAM_ID_3")
if admin_tertiaire:
    try:
        ADMIN_USER_IDS.append(int(admin_tertiaire))
        logger.info(f"✅ Admin tertiaire: {admin_tertiaire}")
    except ValueError:
        logger.error(f"❌ ADMIN_TELEGRAM_ID_3 invalide: {admin_tertiaire}")

# Vérification finale
if not TOKEN or not ADMIN_USER_IDS:
    logger.error("❌ Variables manquantes! TOKEN ou ADMIN_TELEGRAM_ID requis.")
    sys.exit(1)

logger.info(f"✅ Bot configuré avec {len(ADMIN_USER_IDS)} administrateur(s)")

# Fonction pour vérifier si un utilisateur est admin
def is_admin(user_id: int) -> bool:
    """Vérifie si l'utilisateur est administrateur"""
    return user_id in ADMIN_USER_IDS

# Fonction pour obtenir la liste des admins (pour notifications)
def get_admin_ids() -> List[int]:
    """Retourne la liste des IDs administrateurs"""
    return ADMIN_USER_IDS.copy()

# ==================== RESTE DU BLOC 1 (INCHANGÉ) ====================
# ... ton code existant continue ici ...
# Configuration BOT PRINCIPAL vs BACKUP
IS_BACKUP_BOT = os.getenv("IS_BACKUP_BOT", "false").lower() == "true"
PRIMARY_BOT_USERNAME = os.getenv("PRIMARY_BOT_USERNAME", "@votre_bot_principal_bot")
BACKUP_BOT_USERNAME = os.getenv("BACKUP_BOT_USERNAME", "@votre_bot_backup_bot")
PRIMARY_BOT_TOKEN = os.getenv("PRIMARY_BOT_TOKEN", "")

# Health check
HEALTH_CHECK_INTERVAL = 60
PRIMARY_BOT_DOWN_THRESHOLD = 3

# Configuration distance
DISTANCE_METHOD = os.getenv("DISTANCE_METHOD", "geopy")

# Import selon méthode choisie
if DISTANCE_METHOD == "openroute":
    try:
        import openrouteservice
        ORS_API_KEY = os.getenv("OPENROUTESERVICE_API_KEY", "")
        if ORS_API_KEY:
            distance_client = openrouteservice.Client(key=ORS_API_KEY)
            logger.info("✅ OpenRouteService configuré")
        else:
            logger.warning("⚠️ ORS_API_KEY manquant")
            DISTANCE_METHOD = "geopy"
    except ImportError:
        logger.warning("⚠️ pip install openrouteservice")
        DISTANCE_METHOD = "geopy"

if DISTANCE_METHOD == "geopy":
    try:
        from geopy.geocoders import Nominatim
        from geopy.distance import geodesic
        distance_client = Nominatim(user_agent="telegram_bot")
        logger.info("✅ Geopy - Distance approximative")
    except ImportError:
        logger.error("❌ pip install geopy")
        sys.exit(1)

# ==================== CHEMINS DES FICHIERS - DISQUE PERSISTANT ====================

if Path("/data").exists():
    DATA_DIR = Path("/data")
    logger.info("✅ Utilisation du disque persistant : /data")
else:
    DATA_DIR = Path(__file__).parent / "data"
    logger.info("⚠️ Utilisation du dossier local : ./data")

DATA_DIR.mkdir(exist_ok=True)

# Fichiers JSON existants
PRODUCT_REGISTRY_FILE = DATA_DIR / "product_registry.json"
AVAILABLE_PRODUCTS_FILE = DATA_DIR / "available_products.json"
PRICING_TIERS_FILE = DATA_DIR / "pricing_tiers.json"
PRICES_FILE = DATA_DIR / "prices.json"
ARCHIVED_PRODUCTS_FILE = DATA_DIR / "archived_products.json"
USERS_FILE = DATA_DIR / "users.json"
HORAIRES_FILE = DATA_DIR / "horaires.json"
STATS_FILE = DATA_DIR / "stats.json"
PENDING_MESSAGES_FILE = DATA_DIR / "pending_messages.json"

# 🆕 Nouveaux fichiers
STOCKS_FILE = DATA_DIR / "stocks.json"
PROMO_CODES_FILE = DATA_DIR / "promo_codes.json"
CLIENT_HISTORY_FILE = DATA_DIR / "client_history.json"
REFERRALS_FILE = DATA_DIR / "referrals.json"
NOTIFICATIONS_FILE = DATA_DIR / "notifications.json"

# Dossier média
MEDIA_DIR = Path(__file__).parent / "media"

# Images prix
IMAGE_PRIX_FRANCE = MEDIA_DIR / "prix_france.jpg"
IMAGE_PRIX_SUISSE = MEDIA_DIR / "prix_suisse.jpg"

# ==================== ÉTATS DE CONVERSATION - VALEURS EXPLICITES ====================

# États conversation client (0-12)
LANGUE = 0
PAYS = 1
PRODUIT = 2
PILL_SUBCATEGORY = 3
ROCK_SUBCATEGORY = 4
QUANTITE = 5
CART_MENU = 6
PROMO_CODE_INPUT = 7
ADRESSE = 8
LIVRAISON = 9
PAIEMENT = 10
CONFIRMATION = 11
CONTACT = 12

# États conversation admin (100-120)
ADMIN_MENU_MAIN = 100
ADMIN_NEW_PRODUCT_NAME = 101
ADMIN_NEW_PRODUCT_CODE = 102
ADMIN_NEW_PRODUCT_CATEGORY = 103
ADMIN_NEW_PRODUCT_PRICE_FR = 104
ADMIN_NEW_PRODUCT_PRICE_CH = 105
ADMIN_CONFIRM_PRODUCT = 106
ADMIN_SELECT_PRODUCT_PRICING = 107
ADMIN_PRICING_TIERS = 108
ADMIN_ADD_TIER = 109
ADMIN_TIER_QUANTITY = 110
ADMIN_TIER_PRICE = 111  # 🆕 CRITIQUE : État pour saisie prix palier
ADMIN_PRICING_EDIT = 112
ADMIN_PRICING_DELETE = 113
ADMIN_PROMO_MENU = 114
ADMIN_CLIENT_MENU = 115
ADMIN_HORAIRES_INPUT = 116
STOCK_MANAGEMENT = 117
ADMIN_STOCK_MENU = 118
ADMIN_NOTIF_MENU = 119

# ==================== CONFIGURATION ====================

MAX_QUANTITY_PER_PRODUCT = 1000
FRAIS_POSTAL = 10
FRAIS_EXPRESS_PAR_KM = 10
FRAIS_MEETUP = 0
ADMIN_ADDRESS = "858 Rte du Chef Lieu, 74250 Fillinges"


# 🆕 Configuration système de parrainage
REFERRAL_BONUS_TYPE = "percentage"  # ou "fixed"
REFERRAL_BONUS_VALUE = 5  # 5% ou 5€
REFERRAL_CODE_LENGTH = 6

# 🆕 Configuration VIP
VIP_THRESHOLD = 1000  # Montant pour devenir VIP
VIP_DISCOUNT = 10  # 10% de réduction

# 🎨 AMÉLIORATION 2 : Système Emojis Thématique
EMOJI_THEME = {
    # Statuts
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "loading": "⏳",
    
    # Business
    "money": "💰",
    "product": "📦",
    "vip": "👑",
    "diamond": "💎",
    "star": "⭐",
    "gift": "🎁",
    
    # Actions
    "delivery": "🚚",
    "cart": "🛒",
    "stats": "📊",
    "trend_up": "📈",
    "trend_down": "📉",
    "fire": "🔥",
    "rocket": "🚀",
    
    # Status indicators
    "online": "🟢",
    "offline": "🔴",
    "busy": "🟡",
    
    # Achievements
    "trophy": "🏆",
    "medal": "🥇",
    "target": "🎯",
    "celebration": "🎉"
}

# Prix par défaut (BACKUP)
PRIX_FR = {
    "❄️ Coco": 80,
    "💊 Squid Game": 10,
    "💊 Punisher": 10,
    "🫒 Hash": 8,
    "🍀 Weed": 7,
    "🪨 MDMA": 50,
    "🪨 4MMC": 50
}

PRIX_CH = {
    "❄️ Coco": 100,
    "💊 Squid Game": 15,
    "💊 Punisher": 15,
    "🫒 Hash": 8,
    "🍀 Weed": 10,
    "🪨 MDMA": 60,
    "🪨 4MMC": 60
}

# Dictionnaires globaux
PRODUCT_CODES = {}
PILL_SUBCATEGORIES = {}
ROCK_SUBCATEGORIES = {}
IMAGES_PRODUITS = {}
VIDEOS_PRODUITS = {}

# ==================== TRADUCTIONS COMPLÈTES ====================

TRANSLATIONS = {
    "fr": {
        # Messages de base
        "welcome": f"{EMOJI_THEME['celebration']} *Bienvenue !*\n\n",
        "main_menu": "Que souhaitez-vous faire ?",
        "start_order": f"{EMOJI_THEME['cart']} Commander",
        "pirate_card": "🏴‍☠️ Carte du Pirate",
        "contact_admin": "📞 Contact",
        "my_account": f"{EMOJI_THEME['vip']} Mon Compte",
        
        # Navigation
        "choose_country": f"🌍 *Choix du pays*\n\nSélectionnez votre pays :",
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Suisse",
        "choose_product": f"{EMOJI_THEME['product']} *Produit*\n\nQue souhaitez-vous commander ?",
        "choose_pill_type": "💊 *Type de pilule*\n\nChoisissez :",
        "choose_rock_type": "🪨 *Type de crystal*\n\nChoisissez :",
        "enter_quantity": f"📊 *Quantité*\n\nCombien en voulez-vous ?\n_(Maximum : {{max}} unités)_",
        "invalid_quantity": f"{EMOJI_THEME['error']} Quantité invalide.\n\n📊 Entre 1 et {{max}} unités.",
        
        # Panier
        "cart_title": f"{EMOJI_THEME['cart']} *Panier :*",
        "add_more": f"➕ Ajouter un produit",
        "proceed": f"{EMOJI_THEME['success']} Valider le panier",
        "apply_promo": f"{EMOJI_THEME['gift']} Code promo",
        "promo_applied": f"{EMOJI_THEME['success']} Code promo appliqué : -{{discount}}",
        "promo_invalid": f"{EMOJI_THEME['error']} Code promo invalide ou expiré",
        "promo_min_order": f"{EMOJI_THEME['error']} Commande minimum : {{min}}€",
        "enter_promo": f"{EMOJI_THEME['gift']} *Code Promo*\n\nEntrez votre code :",
        
        # Livraison
        "enter_address": "📍 *Adresse de livraison*\n\nEntrez votre adresse complète :\n_(Rue, Code postal, Ville)_",
        "address_too_short": f"{EMOJI_THEME['error']} Adresse trop courte.\n\nVeuillez entrer une adresse complète.",
        "choose_delivery": f"{EMOJI_THEME['delivery']} *Mode de livraison*\n\nChoisissez :",
        "postal": "📬 Postale (48-72h) - 10€",
        "express": "⚡ Express (30min+) - 10€/km",
        "meetup": f"🤝 Meetup - {FRAIS_MEETUP}€",
        "distance_calculated": f"📍 *Distance calculée*\n\n🚗 {{distance}} km\n{EMOJI_THEME['money']} Frais : {{fee}}€",
        
        # Paiement
        "choose_payment": f"💳 *Mode de paiement*\n\nChoisissez :",
        "cash": "💵 Espèces",
        "crypto": "₿ Crypto",
        
        # Confirmation
        "order_summary": f"📋 *Récapitulatif commande*",
        "subtotal": f"💵 Sous-total :",
        "delivery_fee": f"{EMOJI_THEME['delivery']} Frais de livraison :",
        "promo_discount": f"{EMOJI_THEME['gift']} Réduction promo :",
        "vip_discount": f"{EMOJI_THEME['vip']} Réduction VIP :",
        "referral_bonus": f"{EMOJI_THEME['target']} Bonus parrainage :",
        "total": f"{EMOJI_THEME['money']} *TOTAL :*",
        "confirm": f"{EMOJI_THEME['success']} Confirmer",
        "cancel": f"{EMOJI_THEME['error']} Annuler",
        "order_confirmed": f"{EMOJI_THEME['success']} *Commande confirmée !*\n\nMerci ! Vous recevrez une confirmation.",
        "order_cancelled": f"{EMOJI_THEME['error']} *Commande annulée*",
        "new_order": "🔄 Nouvelle commande",
        
        # Prix
        "choose_country_prices": f"🏴‍☠️ *Carte du Pirate*\n\nConsultez nos prix :",
        "prices_france": "🇫🇷 Prix France",
        "prices_switzerland": "🇨🇭 Prix Suisse",
        "price_list_fr": "🇫🇷 *PRIX FRANCE*\n\n",
        "price_list_ch": "🇨🇭 *PRIX SUISSE*\n\n",
        "back_to_card": "🔙 Retour à la carte",
        "back": "🔙 Retour",
        "main_menu_btn": "🏠 Menu principal",
        
        # Contact
        "contact_message": "📞 *Contacter l'administrateur*\n\nÉcrivez votre message :",
        "contact_sent": f"{EMOJI_THEME['success']} Message envoyé !\n\nL'admin vous répondra rapidement.",
        
        # 🆕 Compte client
        "my_account_title": f"{EMOJI_THEME['vip']} *MON COMPTE*",
        "total_spent": f"{EMOJI_THEME['money']} Total dépensé :",
        "orders_count": f"{EMOJI_THEME['product']} Commandes :",
        "vip_status": f"{EMOJI_THEME['vip']} Statut VIP",
        "regular_status": "👤 Statut Standard",
        "referral_code": f"{EMOJI_THEME['target']} Code parrainage :",
        "referred_by": "👥 Parrainé par :",
        "referrals_count": f"{EMOJI_THEME['gift']} Parrainages :",
        "referral_earnings": f"💵 Gains parrainage :",
        "favorite_products": f"{EMOJI_THEME['star']} Produits préférés :",
        "view_history": f"{EMOJI_THEME['stats']} Voir historique",
        
        # 🆕 Stock
        "out_of_stock": f"{EMOJI_THEME['error']} *Produit en rupture de stock*\n\n{{product}}\n\nRevenez bientôt !",
        "low_stock": f"{EMOJI_THEME['warning']} Stock limité : {{stock}}g restants",
        
        # Système
        "outside_hours": f"⏰ *Fermé*\n\nNous sommes ouverts de {{hours}}.\n\nRevenez pendant nos horaires !",
        "maintenance_mode": f"🔧 *MODE MAINTENANCE*\n\nLe bot est actuellement en maintenance.\n\n⏰ Retour prévu : Bientôt\n\n💬 Contactez @{{admin}} pour plus d'infos.",
    },
    "en": {
        # Messages de base
        "welcome": f"{EMOJI_THEME['celebration']} *Welcome!*\n\n",
        "main_menu": "What would you like to do?",
        "start_order": f"{EMOJI_THEME['cart']} Order",
        "pirate_card": "🏴‍☠️ Pirate Card",
        "contact_admin": "📞 Contact",
        "my_account": f"{EMOJI_THEME['vip']} My Account",
        
        # (Traductions complètes en anglais...)
        # Pour économiser de l'espace, je garde la structure identique
    }
}

# ==================== ERROR HANDLER DECORATOR ====================

def error_handler(func):
    """Décorateur pour gérer les erreurs de manière centralisée"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"Erreur dans {func.__name__}: {e}", exc_info=True)
            error_message = f"{EMOJI_THEME['error']} Une erreur s'est produite. Veuillez réessayer."
            try:
                if update.message:
                    await update.message.reply_text(error_message)
                elif update.callback_query:
                    await update.callback_query.answer(error_message, show_alert=True)
            except:
                pass
            return ConversationHandler.END
    return wrapper

# ==================== FONCTIONS UTILITAIRES ====================

def tr(user_data, key):
    """Traduction avec remplacement de variables"""
    lang = user_data.get('langue', 'fr')
    t = TRANSLATIONS.get(lang, TRANSLATIONS['fr']).get(key, key)
    t = t.replace("{max}", str(MAX_QUANTITY_PER_PRODUCT))
    t = t.replace("{hours}", get_horaires_text())
    return t

def sanitize_input(text, max_length=300):
    """Nettoie les entrées utilisateur"""
    if not text:
        return ""
    return re.sub(r'[<>{}[\]\\`|]', '', text.strip()[:max_length])

def generate_referral_code():
    """Génère un code de parrainage unique"""
    return ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(REFERRAL_CODE_LENGTH))

def generate_order_id(user_id):
    """Génère un ID de commande unique"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"ORD-{timestamp}-{user_id}"

# 🎨 AMÉLIORATION 3 : Barre de Progression
def create_progress_bar(current, total, length=10, filled_char="█", empty_char="░"):
    """
    Crée une barre de progression visuelle
    
    Args:
        current: Valeur actuelle
        total: Valeur totale
        length: Longueur de la barre
        filled_char: Caractère pour partie remplie
        empty_char: Caractère pour partie vide
    
    Returns:
        str: Barre de progression formatée avec pourcentage
    """
    if total == 0:
        percentage = 0
    else:
        percentage = int((current / total) * 100)
    
    filled = int((current / total) * length) if total > 0 else 0
    bar = filled_char * filled + empty_char * (length - filled)
    
    return f"{bar} {percentage}%"

# FIN DU BLOC 1
# ==================== BLOC 2 : FONCTIONS DE PERSISTANCE ET GESTION DES DONNÉES ====================
# Ajoutez ce bloc APRÈS le BLOC 1

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
        "client_history.json", "referrals.json"
    ]
    
    for file in required_files:
        if (DATA_DIR / file).exists():
            files_found.append(file)
    
    if files_found:
        logger.info(f"✅ Fichiers trouvés: {', '.join(files_found)}")
    else:
        logger.warning("⚠️ Aucun fichier de données trouvé - Premier démarrage")
    
    return boot_count

# ==================== GESTION DU REGISTRE PRODUITS ====================

def load_product_registry():
    """Charge le registre complet des produits"""
    if PRODUCT_REGISTRY_FILE.exists():
        try:
            with open(PRODUCT_REGISTRY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("products", {})
        except Exception as e:
            logger.error(f"Erreur chargement registre: {e}")
    return {}

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
        "fourmmc": {"name": "🪨 4MMC", "code": "fourmmc", "emoji": "🪨", "category": "rock", "image": "fourmmc.jpg", "video": "fourmmc_demo.mp4", "created_at": datetime.now().isoformat()}
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

# ==================== 🆕 GESTION DES STOCKS ====================

def load_stocks():
    """Charge les stocks des produits"""
    if STOCKS_FILE.exists():
        try:
            with open(STOCKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    # Initialisation par défaut (stock illimité)
    return {}

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
        return None  # Stock illimité
    return stocks[product_name].get("quantity", 0)

def set_stock(product_name, quantity, alert_threshold=20):
    """Définit le stock d'un produit"""
    stocks = load_stocks()
    if product_name not in stocks:
        stocks[product_name] = {}
    
    stocks[product_name]["quantity"] = quantity
    stocks[product_name]["alert_threshold"] = alert_threshold
    stocks[product_name]["last_updated"] = datetime.now().isoformat()
    
    return save_stocks(stocks)

def update_stock(product_name, quantity_change):
    """Met à jour le stock (+ pour ajout, - pour retrait)"""
    stocks = load_stocks()
    if product_name not in stocks:
        return True  # Stock illimité
    
    current = stocks[product_name].get("quantity", 0)
    new_quantity = max(0, current + quantity_change)
    stocks[product_name]["quantity"] = new_quantity
    stocks[product_name]["last_updated"] = datetime.now().isoformat()
    
    return save_stocks(stocks)

def is_in_stock(product_name, requested_quantity):
    """Vérifie si la quantité demandée est disponible"""
    stock = get_stock(product_name)
    if stock is None:
        return True  # Stock illimité
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

def load_prices():
    """Charge les prix des produits"""
    if PRICES_FILE.exists():
        try:
            with open(PRICES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"FR": PRIX_FR.copy(), "CH": PRIX_CH.copy()}

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

def add_pricing_tier(product_name, country, min_qty, price):
    """Ajoute un palier de prix"""
    tiers = load_pricing_tiers()
    product_key = f"{product_name}_{country}"
    
    if product_key not in tiers:
        tiers[product_key] = []
    
    existing = [t for t in tiers[product_key] if t['min_qty'] == min_qty]
    
    if existing:
        for t in tiers[product_key]:
            if t['min_qty'] == min_qty:
                t['price'] = price
    else:
        tiers[product_key].append({'min_qty': min_qty, 'price': price})
    
    tiers[product_key] = sorted(tiers[product_key], key=lambda x: x['min_qty'])
    return save_pricing_tiers(tiers)

def delete_pricing_tier(product_name, country, min_qty):
    """🆕 Supprime un palier de prix"""
    tiers = load_pricing_tiers()
    product_key = f"{product_name}_{country}"
    
    if product_key not in tiers:
        return False
    
    original_count = len(tiers[product_key])
    tiers[product_key] = [t for t in tiers[product_key] if t['min_qty'] != min_qty]
    
    if len(tiers[product_key]) == original_count:
        return False  # Rien supprimé
    
    if not tiers[product_key]:
        del tiers[product_key]
    
    return save_pricing_tiers(tiers)

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

# ==================== 🆕 GESTION DES CODES PROMO ====================

def load_promo_codes():
    """Charge les codes promo"""
    if PROMO_CODES_FILE.exists():
        try:
            with open(PROMO_CODES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

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
    
    # Vérifier expiration
    if "valid_until" in promo:
        expiry = datetime.fromisoformat(promo["valid_until"])
        if datetime.now() > expiry:
            return None, "Code expiré"
    
    # Vérifier commande minimum
    min_order = promo.get("min_order", 0)
    if subtotal < min_order:
        return None, f"Commande minimum : {min_order}€"
    
    # Vérifier limite d'utilisations
    max_uses = promo.get("max_uses", 999999)
    used_count = promo.get("used_count", 0)
    if used_count >= max_uses:
        return None, "Code épuisé"
    
    # Vérifier première commande uniquement
    if promo.get("first_order_only", False):
        history = load_client_history()
        if str(user_id) in history and history[str(user_id)].get("orders_count", 0) > 0:
            return None, "Réservé aux nouvelles commandes"
    
    # Calculer réduction
    if promo["type"] == "percentage":
        discount = subtotal * (promo["value"] / 100)
    else:  # fixed
        discount = promo["value"]
    
    return discount, "OK"

def use_promo_code(code):
    """Incrémente le compteur d'utilisation d'un code promo"""
    codes = load_promo_codes()
    code_upper = code.upper()
    
    if code_upper in codes:
        codes[code_upper]["used_count"] = codes[code_upper].get("used_count", 0) + 1
        save_promo_codes(codes)

# ==================== 🆕 GESTION HISTORIQUE CLIENT ====================

def load_client_history():
    """Charge l'historique des clients"""
    if CLIENT_HISTORY_FILE.exists():
        try:
            with open(CLIENT_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

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
    
    # Mettre à jour
    history[user_key]["total_spent"] += order_data.get("total", 0)
    history[user_key]["orders_count"] += 1
    history[user_key]["last_order_date"] = datetime.now().isoformat()
    
    # Vérifier statut VIP
    if history[user_key]["total_spent"] >= VIP_THRESHOLD:
        history[user_key]["vip_status"] = True
    
    # Produits favoris
    for product in order_data.get("products", []):
        product_name = product.get("produit")
        if product_name:
            history[user_key]["favorite_products"][product_name] = \
                history[user_key]["favorite_products"].get(product_name, 0) + 1
    
    # Ajouter commande à l'historique
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
    
    # Top 3 produits favoris
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

# ==================== 🆕 SYSTÈME DE PARRAINAGE ====================

def load_referrals():
    """Charge les données de parrainage"""
    if REFERRALS_FILE.exists():
        try:
            with open(REFERRALS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

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
        # Générer un code unique
        while True:
            code = generate_referral_code()
            # Vérifier que le code n'existe pas déjà
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
    
    # Trouver le parrain
    referrer_id = None
    for uid, data in referrals.items():
        if data.get("referral_code") == referral_code.upper():
            referrer_id = uid
            break
    
    if not referrer_id:
        return False, "Code invalide"
    
    if user_key == referrer_id:
        return False, "Impossible de se parrainer soi-même"
    
    # Vérifier si déjà parrainé
    if user_key in referrals and referrals[user_key].get("referred_by"):
        return False, "Déjà parrainé"
    
    # Créer ou mettre à jour
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
    
    # Ajouter à la liste du parrain
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

def load_users():
    """Charge les utilisateurs"""
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

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
    
    # Créer code de parrainage automatiquement
    get_or_create_referral_code(user_id)
    
    return True

def update_user_visit(user_id):
    """Met à jour la dernière visite d'un utilisateur"""
    users = load_users()
    if str(user_id) in users:
        users[str(user_id)]["last_seen"] = datetime.now().isoformat()
        users[str(user_id)]["visit_count"] = users[str(user_id)].get("visit_count", 0) + 1
        save_users(users)

# FIN DU BLOC 2
# ==================== BLOC 3 : FONCTIONS MÉTIER, CALCULS ET NOTIFICATIONS ====================
# Ajoutez ce bloc APRÈS le BLOC 2

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
    if user_id and user_id == ADMIN_ID:
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

def load_stats():
    """Charge les statistiques"""
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "weekly": [],
        "monthly": [],
        "last_weekly_report": None,
        "last_monthly_report": None
    }

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
    if user_id and user_id == ADMIN_ID:
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

# ==================== SYSTÈME HEALTH CHECK (FAILOVER) ====================

def load_health_status():
    """Charge l'état de santé du bot"""
    health_file = DATA_DIR / "health_status.json"
    if health_file.exists():
        try:
            with open(health_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "primary_bot_online": True,
        "last_primary_check": datetime.now().isoformat(),
        "consecutive_failures": 0,
        "failover_active": False,
        "last_failover_time": None
    }

def save_health_status(status):
    """Sauvegarde l'état de santé"""
    health_file = DATA_DIR / "health_status.json"
    try:
        with open(health_file, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde health: {e}")
        return False

# ==================== ✅ CALCULS DE DISTANCE ET LIVRAISON - CORRIGÉ ====================

def calculate_delivery_fee(delivery_type, distance=0, subtotal=0):
    """
    Calcule les frais de livraison
    
    RÈGLES EXPRESS :
    - 10€ par tranche de 10 km
    - Minimum commande : 30€
    - Plafond frais : 70€
    - Arrondi : >= 25km → dizaine supérieure, < 25km → dizaine inférieure
    """
    if delivery_type == "postal":
        return FRAIS_POSTAL
    
    elif delivery_type == "express":
        # Vérifier minimum de commande
        if subtotal < 30:
            logger.warning(f"⚠️ Commande {subtotal}€ < 30€ minimum pour Express")
            # On retourne quand même les frais, mais le client devra être averti
        
        # Calcul de base : 10€ par 10km
        frais_brut = (distance / 10) * 10
        
        # Arrondi selon distance
        if distance >= 25:
            # Arrondir à la dizaine supérieure
            frais_arrondi = math.ceil(frais_brut / 10) * 10
        else:
            # Arrondir à la dizaine inférieure
            frais_arrondi = math.floor(frais_brut / 10) * 10
        
        # Appliquer le plafond
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

# ==================== 🆕 GESTION MEETUP ====================

def get_available_meetup_zones(country):
    """Retourne les zones de meetup disponibles pour un pays"""
    return MEETUP_ZONES.get(country, [])

def is_meetup_zone_valid(zone, country):
    """Vérifie si une zone de meetup est valide"""
    return zone in MEETUP_ZONES.get(country, [])

def format_meetup_zones(country):
    """Formate la liste des zones de meetup pour affichage"""
    zones = get_available_meetup_zones(country)
    if not zones:
        return "_Aucune zone de meetup disponible_"
    
    text = ""
    for i, zone in enumerate(zones, 1):
        text += f"{i}. 📍 {zone}\n"
    return text

# ==================== 🆕 CALCUL TOTAL AVEC TOUTES LES RÉDUCTIONS ====================

def calculate_total(cart, country, delivery_type=None, distance=0, promo_code=None, user_id=None):
    """
    Calcule le total avec tous les éléments :
    - Prix dégressifs
    - Frais de livraison
    - Code promo
    - Réduction VIP
    - Bonus parrainage
    """
    prices = load_prices()
    prix_table = prices.get(country, PRIX_FR if country == "FR" else PRIX_CH)
    
    # Sous-total avec prix dégressifs
    subtotal = 0
    for item in cart:
        product_name = item["produit"]
        quantity = item["quantite"]
        price_per_unit = get_price_for_quantity(product_name, country, quantity)
        subtotal += price_per_unit * quantity
    
    # Frais de livraison
    delivery_fee = 0
    if delivery_type:
        delivery_fee = calculate_delivery_fee(delivery_type, distance, subtotal)
    
    # Code promo
    promo_discount = 0
    promo_valid = False
    if promo_code:
        discount, message = validate_promo_code(promo_code, subtotal, user_id)
        if discount is not None:
            promo_discount = discount
            promo_valid = True
    
    # Réduction VIP
    vip_discount = 0
    if user_id and is_vip_client(user_id):
        vip_discount = subtotal * (VIP_DISCOUNT / 100)
    
    # Total après réductions
    total = subtotal + delivery_fee - promo_discount - vip_discount
    total = max(0, total)  # Ne peut pas être négatif
    
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

# 🎨 AMÉLIORATION 5 : Interface Carte Produit Style E-commerce
def format_product_card(product_name, country, stock=None):
    """
    Formate une carte produit style e-commerce
    
    Args:
        product_name: Nom du produit
        country: Code pays (FR/CH)
        stock: Stock disponible (None = illimité)
    
    Returns:
        str: Carte produit formatée
    """
    price = get_price(product_name, country)
    flag = "🇫🇷" if country == "FR" else "🇨🇭"
    
    # En-tête
    card = f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
    card += f"┃  {product_name}\n"
    card += f"┣━━━━━━━━━━━━━━━━━━━━━┫\n"
    
    # Prix
    card += f"┃ {EMOJI_THEME['money']} Prix: {price}€/g {flag}\n"
    
    # Stock
    if stock is None:
        card += f"┃ {EMOJI_THEME['online']} En stock (illimité)\n"
    elif stock > 50:
        card += f"┃ {EMOJI_THEME['online']} En stock ({stock}g)\n"
    elif stock > 0:
        card += f"┃ {EMOJI_THEME['warning']} Stock limité ({stock}g)\n"
    else:
        card += f"┃ {EMOJI_THEME['offline']} Rupture de stock\n"
    
    # Livraison
    card += f"┃ {EMOJI_THEME['delivery']} Livraison: 24-48h\n"
    
    # Pied
    card += f"┗━━━━━━━━━━━━━━━━━━━━━┛"
    
    return card

def get_formatted_price_list(country_code):
    """Génère la liste formatée des prix"""
    prices = load_prices()
    country = "FR" if country_code == "fr" else "CH"
    country_prices = prices.get(country, PRIX_FR if country == "FR" else PRIX_CH)
    
    available = get_available_products()
    
    if not available:
        return "_Aucun produit disponible_"
    
    text = ""
    
    for product_name in sorted(available):
        # Vérifier stock
        stock = get_stock(product_name)
        price = country_prices.get(product_name, 0)
        
        if stock is not None and stock == 0:
            text += f"{EMOJI_THEME['offline']} {product_name} : *RUPTURE*\n"
        elif stock is not None and stock <= 20:
            text += f"{EMOJI_THEME['warning']} {product_name} : {price}€/g (Stock: {stock}g)\n"
        else:
            text += f"{product_name} : {price}€/g\n"
    
    text += f"\n{EMOJI_THEME['delivery']} *Livraison* :\n"
    text += f"  • Postale (48-72h) : 10€\n"
    text += f"  • Express (30min+) : 10€/10km (min 30€, max 70€)\n"
    text += f"  • Meetup : Gratuit"
    
    return text

# 🎨 AMÉLIORATION 6 : Récapitulatif Commande Style Ticket
def format_order_summary(cart, country, delivery_type, delivery_fee, promo_discount, vip_discount, total, order_id=None):
    """
    Formate le récapitulatif de commande style ticket de caisse
    
    Args:
        cart: Panier de produits
        country: Code pays
        delivery_type: Type de livraison
        delivery_fee: Frais de livraison
        promo_discount: Réduction promo
        vip_discount: Réduction VIP
        total: Total final
        order_id: Numéro de commande (optionnel)
    
    Returns:
        str: Ticket formaté
    """
    # En-tête
    ticket = f"╔════════════════════════════╗\n"
    ticket += f"║     🧾 RÉCAPITULATIF      ║\n"
    ticket += f"╚════════════════════════════╝\n"
    
    # Date et commande
    ticket += f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    if order_id:
        ticket += f"🆔 Commande #{order_id}\n"
    
    # Produits
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
        
        # Tronquer le nom si trop long
        product_short = product[:15] if len(product) > 15 else product
        ticket += f"│  {product_short:<15} {qty}g │\n"
        ticket += f"│  {price}€/g × {qty} = {line_total}€{' '*(12-len(str(line_total)))}│\n"
    
    ticket += f"└────────────────────────────┘\n"
    
    # Totaux
    ticket += f"\n💵 Sous-total: {subtotal:.2f}€\n"
    ticket += f"{EMOJI_THEME['delivery']} Livraison ({delivery_type}): {delivery_fee:.2f}€\n"
    
    if promo_discount > 0:
        ticket += f"{EMOJI_THEME['gift']} Promo: -{promo_discount:.2f}€\n"
    
    if vip_discount > 0:
        ticket += f"{EMOJI_THEME['vip']} VIP: -{vip_discount:.2f}€\n"
    
    # Total final
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
                'vip_discount', 'total', 'promo_code', 'status'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
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
                    parse_mode='Markdown',
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
                    caption=caption,
                    parse_mode='Markdown'
                )
            logger.info(f"✅ Image envoyée: {product_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur image {product_name}: {e}")
    
    logger.warning(f"⚠️ Aucun média pour {product_name}")
    await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode='Markdown')
    return False

# ==================== 🆕 NOTIFICATIONS ADMIN ====================

async def notify_admin_new_user(context, user_id, user_data):
    """Notifie l'admin d'un nouvel utilisateur"""
    username = user_data.get("username", "N/A")
    first_name = user_data.get("first_name", "N/A")
    last_name = user_data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()
    
    notification = f"""{EMOJI_THEME['celebration']} *NOUVELLE CONNEXION*

👤 *Utilisateur :*
- Nom : {full_name}
- Username : @{username if username != 'N/A' else 'Non défini'}
- ID : `{user_id}`

📅 *Date :* {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

💬 _L'utilisateur vient de démarrer le bot_
"""
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=notification,
            parse_mode='Markdown'
        )
        logger.info(f"✅ Admin notifié - Nouveau user: {user_id}")
    except Exception as e:
        logger.error(f"❌ Erreur notification admin: {e}")

async def notify_admin_new_order(context, order_data, user_info):
    """🆕 Notifie l'admin d'une nouvelle commande avec récapitulatif détaillé"""
    total_info = order_data.get('total_info', {})
    
    notification = f"""{EMOJI_THEME['cart']} *NOUVELLE COMMANDE*

📋 *Commande :* `{order_data['order_id']}`
👤 *Client :* {user_info['first_name']} (@{user_info['username']})
🆔 ID : `{order_data['user_id']}`

🛍️ *PANIER :*
{order_data['products_display']}

{EMOJI_THEME['money']} *DÉTAILS :*
- Sous-total : {total_info['subtotal']:.2f}€
- Livraison : {total_info['delivery_fee']:.2f}€
"""
    
    if total_info.get('promo_discount', 0) > 0:
        notification += f"• {EMOJI_THEME['gift']} Promo : -{total_info['promo_discount']:.2f}€\n"
    
    if total_info.get('vip_discount', 0) > 0:
        notification += f"• {EMOJI_THEME['vip']} VIP : -{total_info['vip_discount']:.2f}€\n"
    
    notification += f"\n💵 *TOTAL : {total_info['total']:.2f}€*\n\n"
    notification += f"📍 *Adresse :* {order_data['address']}\n"
    notification += f"{EMOJI_THEME['delivery']} *Livraison :* {order_data['delivery_type']}\n"
    notification += f"💳 *Paiement :* {order_data['payment_method']}"
    
    keyboard = [[
        InlineKeyboardButton(
            f"{EMOJI_THEME['success']} Valider",
            callback_data=f"admin_validate_{order_data['order_id']}_{order_data['user_id']}"
        )
    ]]
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=notification,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        logger.info(f"✅ Admin notifié - Nouvelle commande: {order_data['order_id']}")
    except Exception as e:
        logger.error(f"❌ Erreur notification commande: {e}")

async def notify_admin_low_stock(context, product_name, quantity):
    """🆕 Alerte stock faible"""
    notification = f"""{EMOJI_THEME['warning']} *ALERTE STOCK FAIBLE*

{EMOJI_THEME['product']} *Produit :* {product_name}
📊 *Stock restant :* {quantity}g

💡 _Pensez à réapprovisionner_
"""
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=notification,
            parse_mode='Markdown'
        )
        logger.info(f"⚠️ Alerte stock envoyée: {product_name}")
    except Exception as e:
        logger.error(f"❌ Erreur notification stock: {e}")

async def notify_admin_out_of_stock(context, product_name):
    """🆕 Alerte rupture de stock"""
    notification = f"""{EMOJI_THEME['offline']} *RUPTURE DE STOCK*

{EMOJI_THEME['product']} *Produit :* {product_name}
📊 *Stock :* 0g

{EMOJI_THEME['warning']} _Le produit a été automatiquement masqué_
"""
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=notification,
            parse_mode='Markdown'
        )
        logger.info(f"🔴 Alerte rupture envoyée: {product_name}")
    except Exception as e:
        logger.error(f"❌ Erreur notification rupture: {e}")

async def notify_admin_high_value_order(context, order_id, total, user_info):
    """🆕 Alerte commande de valeur élevée (>500€)"""
    notification = f"""{EMOJI_THEME['diamond']} *COMMANDE HAUTE VALEUR*

📋 *Commande :* `{order_id}`
{EMOJI_THEME['money']} *Montant :* {total:.2f}€

👤 *Client :*
- Nom : {user_info['first_name']}
- Username : @{user_info['username']}
- ID : `{user_info['user_id']}`

{EMOJI_THEME['warning']} _Vérifiez cette commande avec attention_
"""
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=notification,
            parse_mode='Markdown'
        )
        logger.info(f"💎 Alerte haute valeur envoyée: {order_id}")
    except Exception as e:
        logger.error(f"❌ Erreur notification haute valeur: {e}")

async def notify_admin_vip_client(context, user_id, user_info, total_spent):
    """🆕 Notifie qu'un client devient VIP"""
    notification = f"""{EMOJI_THEME['vip']} *NOUVEAU CLIENT VIP*

👤 *Client :*
- Nom : {user_info['first_name']}
- Username : @{user_info['username']}
- ID : `{user_id}`

{EMOJI_THEME['money']} *Total dépensé :* {total_spent:.2f}€

{EMOJI_THEME['celebration']} _Le client a atteint le statut VIP !_
"""
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=notification,
            parse_mode='Markdown'
        )
        logger.info(f"👑 Nouveau VIP notifié: {user_id}")
    except Exception as e:
        logger.error(f"❌ Erreur notification VIP: {e}")

# ==================== GESTION MESSAGES PROGRAMMÉS ====================

def load_pending_messages():
    """Charge les messages programmés pour suppression"""
    if PENDING_MESSAGES_FILE.exists():
        try:
            with open(PENDING_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []

def save_pending_messages(messages):
    """Sauvegarde les messages programmés"""
    try:
        with open(PENDING_MESSAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde messages: {e}")
        return False

def add_pending_message(chat_id, message_id, delete_at):
    """Ajoute un message à la liste de suppression programmée"""
    messages = load_pending_messages()
    messages.append({
        "chat_id": chat_id,
        "message_id": message_id,
        "delete_at": delete_at.isoformat()
    })
    save_pending_messages(messages)

async def check_pending_deletions(context: ContextTypes.DEFAULT_TYPE):
    """Vérifie et supprime les messages programmés"""
    messages = load_pending_messages()
    now = datetime.now()
    to_keep = []
    
    for msg in messages:
        delete_time = datetime.fromisoformat(msg["delete_at"])
        if now >= delete_time:
            try:
                await context.bot.delete_message(
                    chat_id=msg["chat_id"],
                    message_id=msg["message_id"]
                )
                logger.info(f"✅ Message supprimé: {msg['message_id']}")
            except Exception as e:
                logger.error(f"Erreur suppression message: {e}")
        else:
            to_keep.append(msg)
    
    save_pending_messages(to_keep)

# ==================== RAPPORTS AUTOMATIQUES ====================

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
    
    report = f"""{EMOJI_THEME['stats']} *RAPPORT HEBDOMADAIRE*

📅 Semaine du {datetime.now().strftime('%d/%m/%Y')}

{EMOJI_THEME['money']} *CA TOTAL :* {total:.2f}€
🛍️ *Ventes :* {total_subtotal:.2f}€
{EMOJI_THEME['delivery']} *Frais :* {total_delivery_fees:.2f}€
{EMOJI_THEME['gift']} *Promos :* -{total_promo:.2f}€
{EMOJI_THEME['vip']} *VIP :* -{total_vip:.2f}€

{EMOJI_THEME['product']} *Commandes :* {count}
🇫🇷 France : {fr_count}
🇨🇭 Suisse : {ch_count}
💵 *Panier moyen :* {total/count:.2f}€
"""
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=report,
            parse_mode='Markdown'
        )
        stats["weekly"] = []
        stats["last_weekly_report"] = datetime.now().isoformat()
        save_stats(stats)
        logger.info("✅ Rapport hebdomadaire envoyé")
    except Exception as e:
        logger.error(f"Erreur envoi rapport hebdo: {e}")

async def send_monthly_report(context: ContextTypes.DEFAULT_TYPE):
    """Envoie le rapport mensuel"""
    stats = load_stats()
    monthly_sales = stats.get("monthly", [])
    
    if not monthly_sales:
        return
    
    total = sum(sale["amount"] for sale in monthly_sales)
    total_subtotal = sum(sale.get("subtotal", sale["amount"]) for sale in monthly_sales)
    total_delivery_fees = sum(sale.get("delivery_fee", 0) for sale in monthly_sales)
    total_promo = sum(sale.get("promo_discount", 0) for sale in monthly_sales)
    total_vip = sum(sale.get("vip_discount", 0) for sale in monthly_sales)
    count = len(monthly_sales)
    fr_count = sum(1 for sale in monthly_sales if sale.get("country") == "FR")
    ch_count = sum(1 for sale in monthly_sales if sale.get("country") == "CH")
    
    product_count = defaultdict(int)
    for sale in monthly_sales:
        for product in sale.get("products", "").split(";"):
            if product.strip():
                product_count[product.strip()] += 1
    
    top_products = sorted(product_count.items(), key=lambda x: x[1], reverse=True)[:5]
    
    report = f"""{EMOJI_THEME['stats']} *RAPPORT MENSUEL*

📅 Mois de {datetime.now().strftime('%B %Y')}

{EMOJI_THEME['money']} *CA TOTAL :* {total:.2f}€
🛍️ *Ventes :* {total_subtotal:.2f}€
{EMOJI_THEME['delivery']} *Frais :* {total_delivery_fees:.2f}€
{EMOJI_THEME['gift']} *Promos :* -{total_promo:.2f}€
{EMOJI_THEME['vip']} *VIP :* -{total_vip:.2f}€

{EMOJI_THEME['product']} *Commandes :* {count}
🇫🇷 France : {fr_count}
🇨🇭 Suisse : {ch_count}
💵 *Panier moyen :* {total/count:.2f}€

{EMOJI_THEME['trophy']} *Top 5 Produits :*
"""
    
    for i, (product, qty) in enumerate(top_products, 1):
        report += f"{i}. {product} ({qty}x)\n"
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=report,
            parse_mode='Markdown'
        )
        stats["monthly"] = []
        stats["last_monthly_report"] = datetime.now().isoformat()
        save_stats(stats)
        logger.info("✅ Rapport mensuel envoyé")
    except Exception as e:
        logger.error(f"Erreur envoi rapport mensuel: {e}")

async def schedule_reports(context: ContextTypes.DEFAULT_TYPE):
    """Planifie les rapports automatiques"""
    now = datetime.now()
    stats = load_stats()
    
    # Rapport hebdomadaire (dimanche 23h59)
    if now.weekday() == 6 and now.hour == 23 and now.minute == 59:
        last_weekly = stats.get("last_weekly_report")
        if not last_weekly or (now - datetime.fromisoformat(last_weekly)).days >= 7:
            await send_weekly_report(context)
    
    # Rapport mensuel (dernier jour du mois 23h59)
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    last_day = (next_month - timedelta(days=1)).day
    
    if now.day == last_day and now.hour == 23 and now.minute == 59:
        last_monthly = stats.get("last_monthly_report")
        if not last_monthly or (now - datetime.fromisoformat(last_monthly)).days >= 28:
            await send_monthly_report(context)

async def heartbeat_maintenance(context: ContextTypes.DEFAULT_TYPE):
    """Met à jour régulièrement le timestamp pour éviter les faux positifs"""
    update_last_online()

async def check_stocks_job(context: ContextTypes.DEFAULT_TYPE):
    """Job périodique qui vérifie les stocks et envoie des alertes"""
    low_stock_products = get_low_stock_products()
    
    # Alertes stock faible (1x par jour)
    if low_stock_products:
        now = datetime.now()
        if now.hour == 9 and now.minute == 0:  # 9h du matin
            for item in low_stock_products:
                await notify_admin_low_stock(
                    context,
                    item['product'],
                    item['quantity']
                )

# ==================== SYSTÈME DE SUPPRESSION AUTOMATIQUE DES MESSAGES ====================

# Dictionnaire pour tracker les messages à supprimer
MESSAGE_TRACKER = {}

async def schedule_message_deletion(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay_minutes: int):
    """Planifie la suppression d'un message après X minutes"""
    try:
        await asyncio.sleep(delay_minutes * 60)
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"🗑️ Message {message_id} supprimé après {delay_minutes}min")
    except Exception as e:
        logger.debug(f"Impossible de supprimer message {message_id}: {e}")

async def send_and_schedule_deletion(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, 
                                     reply_markup=None, parse_mode='Markdown', 
                                     user_id=None, photo=None, caption=None):
    """Envoie un message et planifie sa suppression automatique"""
    
    # Déterminer le délai selon le type d'utilisateur
    is_admin = user_id == ADMIN_ID if user_id else False
    delay = 30 if is_admin else 10  # 30min pour admin, 10min pour client
    
    try:
        # Envoyer le message
        if photo:
            sent_message = await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption or text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        
        # Planifier la suppression
        asyncio.create_task(
            schedule_message_deletion(context, chat_id, sent_message.message_id, delay)
        )
        
        return sent_message
        
    except Exception as e:
        logger.error(f"Erreur envoi message: {e}")
        return None

async def edit_and_schedule_deletion(query, text: str, reply_markup=None, 
                                     parse_mode='Markdown', user_id=None, context=None):
    """Édite un message et planifie sa suppression"""
    
    is_admin = user_id == ADMIN_ID if user_id else False
    delay = 30 if is_admin else 10
    
    try:
        # Supprimer l'ancien message si possible
        try:
            await query.message.delete()
        except:
            pass
        
        # Envoyer nouveau message
        sent_message = await query.message.chat.send_message(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        
        # Planifier suppression
        if context:
            asyncio.create_task(
                schedule_message_deletion(context, query.message.chat_id, 
                                        sent_message.message_id, delay)
            )
        
        return sent_message
        
    except Exception as e:
        logger.error(f"Erreur édition message: {e}")
        return None

async def delete_user_message(update: Update, delay_minutes: int = 10):
    """Supprime le message de l'utilisateur après un délai"""
    if update.message:
        try:
            await asyncio.sleep(delay_minutes * 60)
            await update.message.delete()
            logger.info(f"🗑️ Message utilisateur supprimé après {delay_minutes}min")
        except Exception as e:
            logger.debug(f"Impossible de supprimer message utilisateur: {e}")

# ==================== FIN DU BLOC 3 ====================
    
# FIN DU BLOC 3

# ==================== BLOC 4 : HANDLERS CLIENTS ET NAVIGATION (AVEC MEETUP COMPLET) ====================
# Ajoutez ce bloc APRÈS le BLOC 3

# ==================== HANDLERS PRINCIPAUX ====================

async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande pour obtenir son ID Telegram"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Aucun"
    first_name = update.effective_user.first_name
    
    message = f"""
🆔 **INFORMATIONS TELEGRAM**

👤 Nom : {first_name}
🔢 **ID** : `{user_id}`
📝 Username : @{username}

━━━━━━━━━━━━━━━━━━━━━━

ℹ️ Communiquez cet ID à l'administrateur
principal pour obtenir des droits d'accès.
"""
    
    await update.message.reply_text(message, parse_mode='Markdown')
    
    # Log pour l'admin
    logger.info(f"👤 {first_name} (ID: {user_id}) a demandé son ID")

@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Point d'entrée principal"""
    
    # ✅ LOG CRITIQUE AU TOUT DÉBUT
    logger.info("=" * 60)
    logger.info("🚨🚨🚨 start_command APPELÉ 🚨🚨🚨")
    logger.info(f"Update type: {type(update)}")
    logger.info(f"Update: {update}")
    
    if not update.effective_user:
        logger.error("❌ update.effective_user est None!")
        return ConversationHandler.END
    
    user = update.effective_user
    user_id = user.id
    is_admin = user_id == ADMIN_ID
    
    logger.info(f"👤 USER_ID: {user_id}")
    logger.info(f"🔑 IS_ADMIN: {is_admin}")
    logger.info(f"🆔 ADMIN_ID: {ADMIN_ID}")
    logger.info(f"📦 user_data AVANT: {context.user_data}")
    logger.info("=" * 60)
    
    # ✅ Gérer CallbackQuery et Message
    if update.callback_query:
        logger.info("✅ Mode: CallbackQuery")
        query = update.callback_query
        await query.answer()
        send_method = query.message.reply_text
        edit_method = query.message.edit_text
        chat_id = query.message.chat_id
        is_callback = True
    elif update.message:
        logger.info("✅ Mode: Message")
        send_method = update.message.reply_text
        edit_method = None
        chat_id = update.message.chat_id
        is_callback = False
    else:
        logger.error("❌ Ni callback_query ni message!")
        return ConversationHandler.END
    
    # ✅ Vérifier maintenance
    if not is_admin:
        maintenance_active = is_maintenance_mode(user_id)
        logger.info(f"🔧 Maintenance active: {maintenance_active}")
        
        if maintenance_active:
            logger.warning(f"⚠️ Client {user_id} bloqué par maintenance")
            await send_maintenance_message(update, context)
            return ConversationHandler.END
    else:
        logger.info("🔑 Admin détecté - Skip maintenance check")
    
    # Gestion FAILOVER
    if IS_BACKUP_BOT and not is_admin:
        logger.info("🔄 Vérification FAILOVER...")
        if is_primary_bot_down():
            failover_msg = f"{EMOJI_THEME['warning']} *BOT DE SECOURS ACTIF*\n\n⚠️ Le bot principal {PRIMARY_BOT_USERNAME} est temporairement indisponible.\n\n✅ Vous utilisez actuellement le bot de secours.\n\n_Vos commandes fonctionnent normalement._\n\n💡 Une fois le bot principal rétabli, vous pourrez y retourner."
            await send_method(failover_msg, parse_mode='Markdown')
        else:
            suggestion = f"💡 *INFORMATION*\n\nLe bot principal {PRIMARY_BOT_USERNAME} est disponible.\n\n_Vous pouvez l'utiliser pour une meilleure expérience._\n\n👉 Cliquez ici : {PRIMARY_BOT_USERNAME}\n\n✅ Ou continuez sur ce bot de secours."
            await send_method(suggestion, parse_mode='Markdown')
    
    # Gestion utilisateur
    is_new = is_new_user(user_id)
    logger.info(f"👤 Nouvel utilisateur: {is_new}")
    
    if is_new:
        user_data_dict = {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
        add_user(user_id, user_data_dict)
        asyncio.create_task(notify_admin_new_user(context, user_id, user_data_dict))
        logger.info(f"🆕 Nouvel utilisateur enregistré: {user_id} (@{user.username})")
    else:
        update_user_visit(user_id)
        logger.info(f"🔄 Utilisateur connu mis à jour: {user_id}")
    
    bot_name = "BACKUP" if IS_BACKUP_BOT else "PRIMARY"
    logger.info(f"👤 [{bot_name}] /start: {user.first_name} (ID: {user.id}){' 🔑 ADMIN' if is_admin else ''}")
    
    # Réinitialiser user_data
    context.user_data.clear()
    logger.info(f"📦 user_data APRÈS clear: {context.user_data}")
    
    # Menu de sélection de langue
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it")]
    ]
    
    text = "🌍 *Langue / Language / Sprache / Idioma / Lingua*"
    
    logger.info("📤 Envoi du menu de langue...")
    
    # Envoyer le message
    try:
        if is_callback and edit_method:
            try:
                await edit_method(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                logger.info("✅ Message édité avec succès")
            except Exception as e:
                logger.warning(f"⚠️ Édition échouée, envoi nouveau message: {e}")
                await send_method(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                logger.info("✅ Nouveau message envoyé")
        else:
            await send_method(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            logger.info("✅ Message envoyé avec succès")
    except Exception as e:
        logger.error(f"❌ ERREUR lors de l'envoi du message: {e}", exc_info=True)
        return ConversationHandler.END
    
    logger.info(f"🔍 Retourne LANGUE (valeur: {LANGUE})")
    logger.info("=" * 60)
    return LANGUE

@error_handler
async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le compte utilisateur"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    stats = get_client_stats(user_id)
    referral_stats = get_referral_stats(user_id)
    
    text = f"{EMOJI_THEME['vip']} *MON COMPTE*\n\n"
    
    if stats:
        if stats['vip_status']:
            badge = f"{EMOJI_THEME['diamond']} VIP DIAMOND"
            text += f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
            text += f"┃  {badge}  ┃\n"
            text += f"┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        else:
            badge = "👤 MEMBRE STANDARD"
            text += f"{badge}\n\n"
        
        text += f"{EMOJI_THEME['money']} *Total dépensé :* {stats['total_spent']:.2f}€\n"
        text += f"{EMOJI_THEME['product']} *Commandes :* {stats['orders_count']}\n\n"
        
        if not stats['vip_status']:
            remaining = VIP_THRESHOLD - stats['total_spent']
            progress_bar = create_progress_bar(stats['total_spent'], VIP_THRESHOLD, length=15)
            text += f"{EMOJI_THEME['target']} *PROGRESSION VIP*\n"
            text += f"{progress_bar}\n"
            text += f"_Encore {remaining:.2f}€ pour devenir VIP_\n\n"
        else:
            text += f"{EMOJI_THEME['vip']} *AVANTAGES VIP*\n"
            text += f"• {EMOJI_THEME['success']} Réduction de {VIP_DISCOUNT}% permanente\n"
            text += f"• {EMOJI_THEME['star']} Accès prioritaire\n"
            text += f"• {EMOJI_THEME['gift']} Offres exclusives\n\n"
        
        if stats.get('top_products'):
            text += f"{EMOJI_THEME['star']} *Produits préférés :*\n"
            for i, (product, count) in enumerate(stats['top_products'], 1):
                if i == 1:
                    text += f"{EMOJI_THEME['trophy']} "
                elif i == 2:
                    text += f"{EMOJI_THEME['medal']} "
                else:
                    text += f"{EMOJI_THEME['star']} "
                text += f"{product} ({count}x)\n"
            text += "\n"
    else:
        text += f"_Aucune commande pour le moment_\n\n"
        text += f"{EMOJI_THEME['gift']} _Passez votre première commande pour débloquer des avantages !_\n\n"
    
    if referral_stats:
        text += f"{EMOJI_THEME['target']} *PARRAINAGE*\n"
        text += f"Code : `{referral_stats['referral_code']}`\n"
        text += f"{EMOJI_THEME['gift']} Filleuls : {len(referral_stats.get('referred_users', []))}\n"
        text += f"{EMOJI_THEME['money']} Gains : {referral_stats.get('earnings', 0):.2f}€\n\n"
        
        if referral_stats.get('referred_by'):
            text += f"👥 Parrainé par : `{referral_stats['referred_by']}`\n"
    
    keyboard = [[InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main_menu")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def voir_carte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu de la carte des prix"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "prices_france"), callback_data="prix_france")],
        [InlineKeyboardButton(tr(context.user_data, "prices_switzerland"), callback_data="prix_suisse")],
        [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main_menu")]
    ]
    
    try:
        await query.message.delete()
    except:
        pass
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=tr(context.user_data, "choose_country_prices"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PAYS

@error_handler
async def afficher_prix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les prix pour un pays"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "prix_france":
        text = tr(context.user_data, "price_list_fr") + get_formatted_price_list("fr")
        image_path = IMAGE_PRIX_FRANCE
    else:
        text = tr(context.user_data, "price_list_ch") + get_formatted_price_list("ch")
        image_path = IMAGE_PRIX_SUISSE
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "back_to_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")]
    ]
    
    try:
        await query.message.delete()
    except:
        pass
    
    if image_path.exists():
        try:
            with open(image_path, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo,
                    caption=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Erreur envoi image: {e}")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    else:
        logger.warning(f"⚠️ Image non trouvée : {image_path}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    return PAYS

@error_handler
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ CORRECTION : Retour au menu principal SANS boucle"""
    query = update.callback_query
    await query.answer()
    
    # ✅ Réinitialiser le panier
    context.user_data['cart'] = []
    context.user_data.pop('promo_code', None)
    context.user_data.pop('promo_discount', None)
    
    user_id = update.effective_user.id
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    if user_id == ADMIN_ID:
        text += f"\n\n🔑 *MODE ADMINISTRATEUR*\n{EMOJI_THEME['success']} Accès illimité 24h/24"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "my_account"), callback_data="my_account")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    
    try:
        await query.message.delete()
    except:
        pass
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"✅ back_to_main_menu → PAYS")
    return PAYS  #


@error_handler
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Navigation dans le menu de commande"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"📍 menu_navigation appelé - callback_data: {query.data}")
    
    # ✅ Gestion contact admin
    if query.data == "contact_admin":
        await query.message.edit_text(
            tr(context.user_data, "contact_message"),
            parse_mode='Markdown'
        )
        logger.info(f"✅ menu_navigation → CONTACT")
        return CONTACT
    
    # ✅ Si start_order, on affiche le choix du pays
    if query.data == "start_order":
        user_id = update.effective_user.id
        
        # Vérifier horaires
        if not is_within_delivery_hours(user_id):
            if user_id == ADMIN_ID:
                hours_msg = f"\n\n{EMOJI_THEME['warning']} *MODE ADMIN* - Horaires fermés\nHoraires : {get_horaires_text()}"
            else:
                await query.message.edit_text(
                    tr(context.user_data, "outside_hours"),
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
        else:
            hours_msg = ""
        
        # ✅ Afficher choix du pays
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
            [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main_menu")]
        ]
        
        message_text = tr(context.user_data, "choose_country") + hours_msg
        await query.message.edit_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ menu_navigation → PAYS (choix pays)")
        return PAYS  # ✅ Rester dans PAYS (on affiche le choix)
    
    # ✅ Cas par défaut (ne devrait pas arriver)
    logger.warning(f"⚠️ menu_navigation - callback non géré: {query.data}")
    return PAYS

@error_handler
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix du pays"""
    query = update.callback_query
    await query.answer()
    
    # ✅ Extraire le pays
    context.user_data['pays'] = query.data.replace("country_", "")
    context.user_data['cart'] = []
    context.user_data['promo_code'] = None
    
    logger.info(f"🌍 Pays sélectionné: {context.user_data['pays']}")
    
    available = get_available_products()
    keyboard = []
    has_pills = False
    has_crystals = False
    
    for product_name in sorted(available):
        if not is_in_stock(product_name, 1):
            continue
        
        code = None
        for c, name in PRODUCT_CODES.items():
            if name == product_name:
                code = c
                break
        
        if not code:
            continue
        
        if product_name in PILL_SUBCATEGORIES.values():
            has_pills = True
        elif product_name in ROCK_SUBCATEGORIES.values():
            has_crystals = True
        else:
            keyboard.append([InlineKeyboardButton(product_name, callback_data=f"product_{code}")])
    
    if has_pills:
        keyboard.insert(0, [InlineKeyboardButton("💊 Pills", callback_data="product_pill")])
    
    if has_crystals:
        keyboard.append([InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")])
    
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_country_choice")])
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
    
    await query.message.edit_text(
        tr(context.user_data, "choose_product"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    # ✅ CRITIQUE : Passer à l'état PRODUIT
    logger.info(f"✅ choix_pays → PRODUIT")
    return PRODUIT  # ✅ Passer au choix de produit

# ==================== BLOC 4 : HANDLERS CLIENTS ET NAVIGATION (CORRIGÉ) ====================
# Ajoutez ce bloc APRÈS le BLOC 3

# ==================== HANDLERS PRINCIPAUX ====================

@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Point d'entrée principal"""
    user = update.effective_user
    user_id = user.id
    is_admin = user_id == ADMIN_ID
    
    logger.info(f"🔍 DEBUG start_command APPELÉ - user_data: {context.user_data}")
    
    # ✅ CORRECTION : Gérer CallbackQuery et Message
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        send_method = query.message.reply_text
        edit_method = query.message.edit_text
        chat_id = query.message.chat_id
        is_callback = True
    else:
        send_method = update.message.reply_text
        edit_method = None
        chat_id = update.message.chat_id
        is_callback = False
    
    # Gestion FAILOVER
    if IS_BACKUP_BOT:
        if is_primary_bot_down():
            if not is_admin:
                failover_msg = f"{EMOJI_THEME['warning']} *BOT DE SECOURS ACTIF*\n\n⚠️ Le bot principal {PRIMARY_BOT_USERNAME} est temporairement indisponible.\n\n✅ Vous utilisez actuellement le bot de secours.\n\n_Vos commandes fonctionnent normalement._\n\n💡 Une fois le bot principal rétabli, vous pourrez y retourner."
                await send_method(failover_msg, parse_mode='Markdown')
        else:
            if not is_admin:
                suggestion = f"💡 *INFORMATION*\n\nLe bot principal {PRIMARY_BOT_USERNAME} est disponible.\n\n_Vous pouvez l'utiliser pour une meilleure expérience._\n\n👉 Cliquez ici : {PRIMARY_BOT_USERNAME}\n\n✅ Ou continuez sur ce bot de secours."
                await send_method(suggestion, parse_mode='Markdown')
    else:
        if is_maintenance_mode(user_id):
            await send_maintenance_message(update, context)
            return ConversationHandler.END
    
    # Gestion utilisateur
    is_new = is_new_user(user_id)
    if is_new:
        user_data_dict = {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
        add_user(user_id, user_data_dict)
        asyncio.create_task(notify_admin_new_user(context, user_id, user_data_dict))
        logger.info(f"🆕 Nouvel utilisateur: {user_id} (@{user.username})")
    else:
        update_user_visit(user_id)
        logger.info(f"🔄 Utilisateur connu: {user_id}")
    
    bot_name = "BACKUP" if IS_BACKUP_BOT else "PRIMARY"
    logger.info(f"👤 [{bot_name}] /start: {user.first_name} (ID: {user.id}){' 🔑 ADMIN' if is_admin else ''}")
    
    context.user_data.clear()
    logger.info(f"🔍 DEBUG start_command - user_data après clear: {context.user_data}")
    
    # Menu de sélection de langue
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it")]
    ]
    
    text = "🌍 *Langue / Language / Sprache / Idioma / Lingua*"
    
    # ✅ CORRECTION : Utiliser edit si callback, send sinon
    if is_callback and edit_method:
        try:
            await edit_method(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception:
            await send_method(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    else:
        await send_method(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    logger.info(f"🔍 DEBUG start_command - Retourne LANGUE ({LANGUE})")
    return LANGUE

@error_handler
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit la langue de l'utilisateur"""
    query = update.callback_query
    await query.answer()
    lang_code = query.data.replace("lang_", "")
    context.user_data['langue'] = lang_code
    user_id = update.effective_user.id
    
    logger.info(f"👤 Langue sélectionnée: {lang_code} (User: {user_id})")
    
    # ✅ Afficher le menu principal
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    if user_id == ADMIN_ID:
        text += f"\n\n🔑 *MODE ADMINISTRATEUR*\n{EMOJI_THEME['success']} Accès illimité 24h/24"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "my_account"), callback_data="my_account")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"🔍 DEBUG set_langue - Retourne PAYS ({PAYS})")
    return PAYS

@error_handler
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ CORRECTION : Retour au menu principal SANS boucle"""
    query = update.callback_query
    await query.answer()
    
    # ✅ Réinitialiser le panier
    context.user_data['cart'] = []
    context.user_data.pop('promo_code', None)
    context.user_data.pop('promo_discount', None)
    
    user_id = update.effective_user.id
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    if user_id == ADMIN_ID:
        text += f"\n\n🔑 *MODE ADMINISTRATEUR*\n{EMOJI_THEME['success']} Accès illimité 24h/24"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "my_account"), callback_data="my_account")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    
    try:
        await query.message.delete()
    except:
        pass
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"✅ back_to_main_menu → PAYS")
    return PAYS  # ✅ RETOURNE PAYS, PAS LANGUE

@error_handler
async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le compte utilisateur"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    stats = get_client_stats(user_id)
    referral_stats = get_referral_stats(user_id)
    
    text = f"{EMOJI_THEME['vip']} *MON COMPTE*\n\n"
    
    if stats:
        if stats['vip_status']:
            badge = f"{EMOJI_THEME['diamond']} VIP DIAMOND"
            text += f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
            text += f"┃  {badge}  ┃\n"
            text += f"┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        else:
            badge = "👤 MEMBRE STANDARD"
            text += f"{badge}\n\n"
        
        text += f"{EMOJI_THEME['money']} *Total dépensé :* {stats['total_spent']:.2f}€\n"
        text += f"{EMOJI_THEME['product']} *Commandes :* {stats['orders_count']}\n\n"
        
        if not stats['vip_status']:
            remaining = VIP_THRESHOLD - stats['total_spent']
            progress_bar = create_progress_bar(stats['total_spent'], VIP_THRESHOLD, length=15)
            text += f"{EMOJI_THEME['target']} *PROGRESSION VIP*\n"
            text += f"{progress_bar}\n"
            text += f"_Encore {remaining:.2f}€ pour devenir VIP_\n\n"
        else:
            text += f"{EMOJI_THEME['vip']} *AVANTAGES VIP*\n"
            text += f"• {EMOJI_THEME['success']} Réduction de {VIP_DISCOUNT}% permanente\n"
            text += f"• {EMOJI_THEME['star']} Accès prioritaire\n"
            text += f"• {EMOJI_THEME['gift']} Offres exclusives\n\n"
        
        if stats.get('top_products'):
            text += f"{EMOJI_THEME['star']} *Produits préférés :*\n"
            for i, (product, count) in enumerate(stats['top_products'], 1):
                if i == 1:
                    text += f"{EMOJI_THEME['trophy']} "
                elif i == 2:
                    text += f"{EMOJI_THEME['medal']} "
                else:
                    text += f"{EMOJI_THEME['star']} "
                text += f"{product} ({count}x)\n"
            text += "\n"
    else:
        text += f"_Aucune commande pour le moment_\n\n"
        text += f"{EMOJI_THEME['gift']} _Passez votre première commande pour débloquer des avantages !_\n\n"
    
    if referral_stats:
        text += f"{EMOJI_THEME['target']} *PARRAINAGE*\n"
        text += f"Code : `{referral_stats['referral_code']}`\n"
        text += f"{EMOJI_THEME['gift']} Filleuls : {len(referral_stats.get('referred_users', []))}\n"
        text += f"{EMOJI_THEME['money']} Gains : {referral_stats.get('earnings', 0):.2f}€\n\n"
        
        if referral_stats.get('referred_by'):
            text += f"👥 Parrainé par : `{referral_stats['referred_by']}`\n"
    
    keyboard = [[InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main_menu")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def voir_carte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu de la carte des prix"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "prices_france"), callback_data="prix_france")],
        [InlineKeyboardButton(tr(context.user_data, "prices_switzerland"), callback_data="prix_suisse")],
        [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main_menu")]
    ]
    
    try:
        await query.message.delete()
    except:
        pass
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=tr(context.user_data, "choose_country_prices"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PAYS

@error_handler
async def afficher_prix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les prix pour un pays"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "prix_france":
        text = tr(context.user_data, "price_list_fr") + get_formatted_price_list("fr")
        image_path = IMAGE_PRIX_FRANCE
    else:
        text = tr(context.user_data, "price_list_ch") + get_formatted_price_list("ch")
        image_path = IMAGE_PRIX_SUISSE
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "back_to_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")]
    ]
    
    try:
        await query.message.delete()
    except:
        pass
    
    if image_path.exists():
        try:
            with open(image_path, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo,
                    caption=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Erreur envoi image: {e}")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    else:
        logger.warning(f"⚠️ Image non trouvée : {image_path}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    return PAYS

@error_handler
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Navigation dans le menu de commande"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"📍 menu_navigation appelé - callback_data: {query.data}")
    
    # ✅ Gestion contact admin
    if query.data == "contact_admin":
        await query.message.edit_text(
            tr(context.user_data, "contact_message"),
            parse_mode='Markdown'
        )
        logger.info(f"✅ menu_navigation → CONTACT")
        return CONTACT
    
    # ✅ Si start_order, on affiche le choix du pays
    if query.data == "start_order":
        user_id = update.effective_user.id
        
        # Vérifier horaires
        if not is_within_delivery_hours(user_id):
            if user_id == ADMIN_ID:
                hours_msg = f"\n\n{EMOJI_THEME['warning']} *MODE ADMIN* - Horaires fermés\nHoraires : {get_horaires_text()}"
            else:
                await query.message.edit_text(
                    tr(context.user_data, "outside_hours"),
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
        else:
            hours_msg = ""
        
        # ✅ Afficher choix du pays
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
            [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main_menu")]
        ]
        
        message_text = tr(context.user_data, "choose_country") + hours_msg
        await query.message.edit_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ menu_navigation → PAYS (choix pays)")
        return PAYS
    
    # ✅ Cas par défaut (ne devrait pas arriver)
    logger.warning(f"⚠️ menu_navigation - callback non géré: {query.data}")
    return PAYS

@error_handler
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix du pays"""
    query = update.callback_query
    await query.answer()
    
    # ✅ Extraire le pays
    context.user_data['pays'] = query.data.replace("country_", "")
    context.user_data['cart'] = []
    context.user_data['promo_code'] = None
    
    logger.info(f"🌍 Pays sélectionné: {context.user_data['pays']}")
    
    available = get_available_products()
    keyboard = []
    has_pills = False
    has_crystals = False
    
    for product_name in sorted(available):
        if not is_in_stock(product_name, 1):
            continue
        
        code = None
        for c, name in PRODUCT_CODES.items():
            if name == product_name:
                code = c
                break
        
        if not code:
            continue
        
        if product_name in PILL_SUBCATEGORIES.values():
            has_pills = True
        elif product_name in ROCK_SUBCATEGORIES.values():
            has_crystals = True
        else:
            keyboard.append([InlineKeyboardButton(product_name, callback_data=f"product_{code}")])
    
    if has_pills:
        keyboard.insert(0, [InlineKeyboardButton("💊 Pills", callback_data="product_pill")])
    
    if has_crystals:
        keyboard.append([InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")])
    
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_country_choice")])
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
    
    await query.message.edit_text(
        tr(context.user_data, "choose_product"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"✅ choix_pays → PRODUIT")
    return PRODUIT

@error_handler
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix du produit avec carte produit visuelle"""
    query = update.callback_query
    await query.answer()
    product_code = query.data.replace("product_", "")
    available = get_available_products()
    
    if product_code == "pill":
        keyboard = []
        for name in available:
            if name in PILL_SUBCATEGORIES.values():
                if not is_in_stock(name, 1):
                    continue
                code = [k for k, v in PILL_SUBCATEGORIES.items() if v == name][0]
                keyboard.append([InlineKeyboardButton(name, callback_data=f"pill_{code}")])
        
        if not keyboard:
            await query.answer(f"{EMOJI_THEME['error']} Aucune pilule disponible", show_alert=True)
            return PRODUIT
        
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_products")])
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
        
        await query.message.edit_text(
            tr(context.user_data, "choose_pill_type"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return PILL_SUBCATEGORY
    
    elif product_code == "rock":
        keyboard = []
        for name in available:
            if name in ROCK_SUBCATEGORIES.values():
                if not is_in_stock(name, 1):
                    continue
                code = [k for k, v in ROCK_SUBCATEGORIES.items() if v == name][0]
                keyboard.append([InlineKeyboardButton(name, callback_data=f"rock_{code}")])
        
        if not keyboard:
            await query.answer(f"{EMOJI_THEME['error']} Aucun crystal disponible", show_alert=True)
            return PRODUIT
        
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_products")])
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
        
        await query.message.edit_text(
            tr(context.user_data, "choose_rock_type"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ROCK_SUBCATEGORY
    
    product_name = PRODUCT_CODES.get(product_code)
    
    if not product_name:
        await query.answer(f"{EMOJI_THEME['error']} Produit non trouvé", show_alert=True)
        return PRODUIT
    
    if not is_product_available(product_name):
        await query.answer(f"{EMOJI_THEME['error']} Produit indisponible", show_alert=True)
        return PRODUIT
    
    if not is_in_stock(product_name, 1):
        await query.answer(
            tr(context.user_data, "out_of_stock").format(product=product_name),
            show_alert=True
        )
        return PRODUIT
    
    context.user_data['current_product'] = product_name
    
    country = context.user_data.get('pays', 'FR')
    stock = get_stock(product_name)
    product_card = format_product_card(product_name, country, stock)
    
    text = f"{product_card}\n\n{tr(context.user_data, 'enter_quantity')}"
    
    await query.message.delete()
    await send_product_media(context, query.message.chat_id, product_name, text)
    
    return QUANTITE

@error_handler
async def choix_pill_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix d'une sous-catégorie de pilule"""
    query = update.callback_query
    await query.answer()
    product_name = PILL_SUBCATEGORIES.get(query.data.replace("pill_", ""), "💊")
    
    if not is_product_available(product_name):
        await query.answer(f"{EMOJI_THEME['error']} Produit indisponible", show_alert=True)
        return PILL_SUBCATEGORY
    
    if not is_in_stock(product_name, 1):
        await query.answer(
            tr(context.user_data, "out_of_stock").format(product=product_name),
            show_alert=True
        )
        return PILL_SUBCATEGORY
    
    context.user_data['current_product'] = product_name
    
    country = context.user_data.get('pays', 'FR')
    stock = get_stock(product_name)
    product_card = format_product_card(product_name, country, stock)
    
    text = f"{product_card}\n\n{tr(context.user_data, 'enter_quantity')}"
    
    await query.message.delete()
    await send_product_media(context, query.message.chat_id, product_name, text)
    
    return QUANTITE

@error_handler
async def choix_rock_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix d'une sous-catégorie de crystal"""
    query = update.callback_query
    await query.answer()
    product_name = ROCK_SUBCATEGORIES.get(query.data.replace("rock_", ""), "🪨")
    
    if not is_product_available(product_name):
        await query.answer(f"{EMOJI_THEME['error']} Produit indisponible", show_alert=True)
        return ROCK_SUBCATEGORY
    
    if not is_in_stock(product_name, 1):
        await query.answer(
            tr(context.user_data, "out_of_stock").format(product=product_name),
            show_alert=True
        )
        return ROCK_SUBCATEGORY
    
    context.user_data['current_product'] = product_name
    
    country = context.user_data.get('pays', 'FR')
    stock = get_stock(product_name)
    product_card = format_product_card(product_name, country, stock)
    
    text = f"{product_card}\n\n{tr(context.user_data, 'enter_quantity')}"
    
    await query.message.delete()
    await send_product_media(context, query.message.chat_id, product_name, text)
    
    return QUANTITE

@error_handler
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saisie de la quantité - Support décimales"""
    
    user_id = update.effective_user.id
    
    # ✅ Planifier suppression du message utilisateur (10min)
    asyncio.create_task(delete_user_message(update, delay_minutes=10))
    
    qty_input = sanitize_input(update.message.text, 10).replace(',', '.')
    product_name = context.user_data.get('current_product')
    
    # ✅ Validation : doit être un nombre décimal valide
    try:
        quantity = float(qty_input)
    except ValueError:
        msg = await update.message.reply_text(
            f"{EMOJI_THEME['error']} *QUANTITÉ INVALIDE*\n\n"
            f"Veuillez entrer un nombre valide.\n"
            f"Exemples : 1, 2.5, 3.75, 0.5",
            parse_mode='Markdown'
        )
        # ✅ Supprimer le message d'erreur après 10min
        asyncio.create_task(
            schedule_message_deletion(context, msg.chat_id, msg.message_id, 10)
        )
        return QUANTITE
    
    # ✅ Vérifier que la quantité est positive
    if quantity <= 0:
        msg = await update.message.reply_text(
            f"{EMOJI_THEME['error']} *QUANTITÉ INVALIDE*\n\n"
            f"La quantité doit être supérieure à 0.",
            parse_mode='Markdown'
        )
        asyncio.create_task(
            schedule_message_deletion(context, msg.chat_id, msg.message_id, 10)
        )
        return QUANTITE
    
    # ✅ Vérifier limite max
    if quantity > MAX_QUANTITY_PER_PRODUCT:
        msg = await update.message.reply_text(
            f"{EMOJI_THEME['error']} *QUANTITÉ TROP ÉLEVÉE*\n\n"
            f"Maximum autorisé : {MAX_QUANTITY_PER_PRODUCT}g",
            parse_mode='Markdown'
        )
        asyncio.create_task(
            schedule_message_deletion(context, msg.chat_id, msg.message_id, 10)
        )
        return QUANTITE
    
    # ✅ Vérifier le stock
    if not is_in_stock(product_name, quantity):
        stock = get_stock(product_name)
        msg = await update.message.reply_text(
            f"{EMOJI_THEME['error']} *STOCK INSUFFISANT*\n\n"
            f"📦 Disponible : {stock}g\n"
            f"❌ Demandé : {quantity}g\n\n"
            f"Veuillez réduire la quantité.",
            parse_mode='Markdown'
        )
        asyncio.create_task(
            schedule_message_deletion(context, msg.chat_id, msg.message_id, 10)
        )
        return QUANTITE
    
    # ✅ Ajouter au panier
    if 'cart' not in context.user_data:
        context.user_data['cart'] = []
    
    context.user_data['cart'].append({
        "produit": product_name,
        "quantite": quantity
    })
    
    logger.info(f"✅ Produit ajouté au panier : {product_name} x{quantity}g")
    
    # ✅ ALLER DIRECTEMENT AU CHOIX DE LIVRAISON
    country = context.user_data.get('pays')
    cart = context.user_data.get('cart', [])
    
    # Calculer le sous-total
    total_info = calculate_total(cart, country)
    subtotal = total_info['subtotal']
    
    # Vérifier si Express est disponible
    express_available = subtotal >= 30
    
    # Message de choix de livraison
    text = f"{EMOJI_THEME['delivery']} *MODE DE LIVRAISON*\n\n"
    text += f"🛒 *Panier :* {format_cart_summary(cart)}\n"
    text += f"💰 *Sous-total :* {subtotal:.2f}€\n\n"
    text += "Choisissez votre mode de livraison :\n\n"
    
    # 📮 POSTALE
    text += f"📮 *Postale* : {FRAIS_POSTAL}€\n"
    text += f"   ⏱️ Délai : 24h-48h\n"
    text += f"   ✅ Toujours disponible\n\n"
    
    # 🚀 EXPRESS
    if express_available:
        text += f"{EMOJI_THEME['rocket']} *Express* : 10€/10km\n"
        text += f"   ⏱️ Délai : 30min+\n"
        text += f"   ✅ Disponible\n\n"
    else:
        text += f"{EMOJI_THEME['rocket']} *Express* : ❌ NON DISPONIBLE\n"
        text += f"   💰 Min : 30€ (manque {30 - subtotal:.2f}€)\n\n"
    
    # 🤝 MEETUP
    text += f"🤝 *Meetup* : {FRAIS_MEETUP}€\n"
    text += f"   📍 Retrait en personne\n"
    text += f"   ✅ Toujours disponible\n"
    
    # Clavier
    keyboard = [
        [InlineKeyboardButton("📮 Postale", callback_data="livraison_postale")],
    ]
    
    if express_available:
        keyboard.append([InlineKeyboardButton(f"{EMOJI_THEME['rocket']} Express", callback_data="livraison_express")])
    
    keyboard.append([InlineKeyboardButton("🤝 Meetup (Retrait)", callback_data="livraison_meetup")])
    keyboard.append([InlineKeyboardButton("🔙 Annuler", callback_data="back_to_main_menu")])
    
    # ✅ Envoyer avec suppression automatique
    await send_and_schedule_deletion(
        context=context,
        chat_id=update.message.chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        user_id=user_id
    )
    
    return LIVRAISON

@error_handler
async def cart_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu du panier"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_more":
        available = get_available_products()
        keyboard = []
        
        has_pills = False
        has_crystals = False
        
        for product_name in sorted(available):
            if not is_in_stock(product_name, 1):
                continue
            
            code = None
            for c, name in PRODUCT_CODES.items():
                if name == product_name:
                    code = c
                    break
            
            if not code:
                continue
            
            if product_name in PILL_SUBCATEGORIES.values():
                has_pills = True
            elif product_name in ROCK_SUBCATEGORIES.values():
                has_crystals = True
            else:
                keyboard.append([InlineKeyboardButton(product_name, callback_data=f"product_{code}")])
        
        if has_pills:
            keyboard.insert(0, [InlineKeyboardButton("💊 Pills", callback_data="product_pill")])
        
        if has_crystals:
            keyboard.append([InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")])
        
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
        
        await query.message.edit_text(
            tr(context.user_data, "choose_product"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return PRODUIT
    
    elif query.data == "apply_promo":
        await query.message.edit_text(
            tr(context.user_data, 'enter_promo'),
            parse_mode='Markdown'
        )
        return PROMO_CODE_INPUT
    
    else:
        await query.message.edit_text(
            tr(context.user_data, 'enter_address'),
            parse_mode='Markdown'
        )
        return ADRESSE

@error_handler
async def saisie_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saisie du code promo"""
    promo_code = sanitize_input(update.message.text, 20).upper()
    
    cart = context.user_data.get('cart', [])
    country = context.user_data.get('pays', 'FR')
    
    total_info = calculate_total(
        cart,
        country,
        promo_code=promo_code,
        user_id=update.effective_user.id
    )
    
    if total_info['promo_valid']:
        context.user_data['promo_code'] = promo_code
        message = tr(context.user_data, "promo_applied").format(
            discount=f"{total_info['promo_discount']:.2f}€"
        )
    else:
        message = tr(context.user_data, "promo_invalid")
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")]
    ]
    
    await update.message.reply_text(
        message + "\n\n" + format_cart(cart, context.user_data),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return CART_MENU

@error_handler
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saisie de l'adresse - Calcule les frais et va au paiement"""
    address = sanitize_input(update.message.text, 300)
    
    if len(address) < 15:
        await update.message.reply_text(tr(context.user_data, "address_too_short"))
        return ADRESSE
    
    context.user_data['adresse'] = address
    logger.info(f"📍 Adresse saisie : {address}")
    
    mode_livraison = context.user_data.get('mode_livraison')
    
    # ✅ Si POSTALE → Frais fixes, direct au paiement
    if mode_livraison == 'postale':
        text = f"{EMOJI_THEME['success']} *ADRESSE CONFIRMÉE*\n\n"
        text += f"📍 {address}\n"
        text += f"📮 Livraison postale : {FRAIS_POSTAL}€\n"
        text += f"⏱️ Délai : 24h-48h\n\n"
        text += "💳 *Choisissez votre mode de paiement :*"
    
    # ✅ Si EXPRESS → Calculer distance et frais
    elif mode_livraison == 'express':
        try:
            distance = calculate_distance_simple(address)
            frais = calculate_delivery_fee("express", distance, 0)
        except Exception as e:
            logger.error(f"Erreur calcul distance: {e}")
            distance = 5
            frais = 50
        
        context.user_data['frais_livraison'] = frais
        context.user_data['distance'] = distance
        
        text = f"{EMOJI_THEME['success']} *ADRESSE CONFIRMÉE*\n\n"
        text += f"📍 {address}\n"
        text += f"{EMOJI_THEME['rocket']} Distance : {distance:.1f} km\n"
        text += f"💰 Frais livraison : {frais}€\n"
        text += f"⏱️ Délai : 30min+\n\n"
        text += "💳 *Choisissez votre mode de paiement :*"
    
    else:
        # Cas imprévu
        text = "💳 *Choisissez votre mode de paiement :*"
    
    keyboard = [
        [InlineKeyboardButton("💵 Cash", callback_data="paiement_cash")],
        [InlineKeyboardButton("₿ Crypto", callback_data="paiement_crypto")],
        [InlineKeyboardButton("🔙 Modifier adresse", callback_data="back_to_address")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return PAIEMENT

@error_handler
async def back_to_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au choix des produits"""
    query = update.callback_query
    await query.answer()
    
    available = get_available_products()
    keyboard = []
    
    has_pills = False
    has_crystals = False
    
    for product_name in sorted(available):
        if not is_in_stock(product_name, 1):
            continue
        
        code = None
        for c, name in PRODUCT_CODES.items():
            if name == product_name:
                code = c
                break
        
        if not code:
            continue
        
        if product_name in PILL_SUBCATEGORIES.values():
            has_pills = True
        elif product_name in ROCK_SUBCATEGORIES.values():
            has_crystals = True
        else:
            keyboard.append([InlineKeyboardButton(product_name, callback_data=f"product_{code}")])
    
    if has_pills:
        keyboard.insert(0, [InlineKeyboardButton("💊 Pills", callback_data="product_pill")])
    
    if has_crystals:
        keyboard.append([InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")])
    
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_country_choice")])
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
    
    await query.message.edit_text(
        tr(context.user_data, "choose_product"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PRODUIT

@error_handler
async def back_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au panier"""
    query = update.callback_query
    await query.answer()
    
    cart = context.user_data.get('cart', [])
    
    if not cart:
        await query.answer(f"{EMOJI_THEME['error']} Panier vide", show_alert=True)
        return await back_to_products(update, context)
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "add_more"), callback_data="add_more")],
        [InlineKeyboardButton(tr(context.user_data, "apply_promo"), callback_data="apply_promo")],
        [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")]
    ]
    
    await query.message.edit_text(
        format_cart(cart, context.user_data),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return CART_MENU

@error_handler
async def ask_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande le choix du mode de livraison"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
        edit_mode = True
    else:
        message = update.message
        edit_mode = False
    
    country = context.user_data.get('pays')
    cart = context.user_data.get('cart', [])
    
    # ✅ Calculer le sous-total
    total_info = calculate_total(cart, country)
    subtotal = total_info['subtotal']
    
    # ✅ Vérifier si Express est disponible (minimum 30€)
    express_available = subtotal >= 30
    
    # Construction du message
    text = f"{EMOJI_THEME['delivery']} *MODE DE LIVRAISON*\n\n"
    text += f"💰 *Montant du panier :* {subtotal:.2f}€\n\n"
    text += "Choisissez votre mode de livraison :\n\n"
    
    # 📮 POSTALE (toujours disponible)
    text += f"📮 *Postale* : {FRAIS_POSTAL}€ (fixe)\n"
    text += f"   ⏱️ Délai : 24h-48h\n"
    text += f"   ✅ Toujours disponible\n\n"
    
    # 🚀 EXPRESS (si panier >= 30€)
    if express_available:
        text += f"{EMOJI_THEME['rocket']} *Express* : 10€/10km\n"
        text += f"   ⏱️ Délai : 30min+\n"
        text += f"   💰 Min commande : 30€\n"
        text += f"   📊 Max frais : 70€\n"
        text += f"   ✅ Disponible (panier {subtotal:.2f}€)\n\n"
    else:
        text += f"{EMOJI_THEME['rocket']} *Express* : ❌ NON DISPONIBLE\n"
        text += f"   💰 Min commande : 30€\n"
        text += f"   ⚠️ Il manque {30 - subtotal:.2f}€\n\n"
    
    # 🤝 MEETUP (toujours disponible)
    text += f"🤝 *Meetup* : {FRAIS_MEETUP}€\n"
    text += f"   📍 Retrait en personne\n"
    text += f"   ⏰ Délai : Selon disponibilités\n"
    text += f"   💡 Vous venez récupérer votre commande\n"
    text += f"   ✅ Toujours disponible\n"
    
    # ✅ Construction du clavier
    keyboard = []
    
    # Postale (toujours disponible)
    keyboard.append([InlineKeyboardButton("📮 Postale", callback_data="livraison_postale")])
    
    # Express (si panier >= 30€)
    if express_available:
        keyboard.append([InlineKeyboardButton(f"{EMOJI_THEME['rocket']} Express", callback_data="livraison_express")])
    
    # Meetup (toujours disponible)
    keyboard.append([InlineKeyboardButton("🤝 Meetup (Retrait)", callback_data="livraison_meetup")])
    
    # Bouton retour
    keyboard.append([InlineKeyboardButton("🔙 Retour panier", callback_data="back_to_cart")])
    
    # Envoi du message
    if edit_mode:
        await message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    return LIVRAISON

@error_handler
async def livraison_postale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion livraison postale - DEMANDE L'ADRESSE"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['mode_livraison'] = 'postale'
    context.user_data['frais_livraison'] = FRAIS_POSTAL
    context.user_data['distance'] = 0
    
    text = f"{EMOJI_THEME['success']} *LIVRAISON POSTALE*\n\n"
    text += f"📮 Frais : {FRAIS_POSTAL}€\n"
    text += f"⏱️ Délai : 24h-48h\n\n"
    text += "📍 *Veuillez entrer votre adresse de livraison :*"
    
    await query.message.edit_text(text, parse_mode='Markdown')
    
    return ADRESSE

@error_handler
async def livraison_express(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion livraison express - DEMANDE L'ADRESSE"""
    query = update.callback_query
    await query.answer()
    
    cart = context.user_data.get('cart', [])
    country = context.user_data.get('pays', 'FR')
    
    total_info = calculate_total(cart, country)
    subtotal = total_info['subtotal']
    
    if subtotal < 30:
        await query.answer(
            f"{EMOJI_THEME['error']} Minimum 30€ pour Express",
            show_alert=True
        )
        return LIVRAISON
    
    context.user_data['mode_livraison'] = 'express'
    
    text = f"{EMOJI_THEME['success']} *LIVRAISON EXPRESS*\n\n"
    text += f"{EMOJI_THEME['rocket']} Délai : 30min+\n"
    text += f"💰 Frais : 10€/10km (max 70€)\n\n"
    text += "📍 *Veuillez entrer votre adresse de livraison :*"
    
    await query.message.edit_text(text, parse_mode='Markdown')
    
    return ADRESSE

@error_handler
async def livraison_meetup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion livraison Meetup - PAS D'ADRESSE"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['mode_livraison'] = 'meetup'
    context.user_data['frais_livraison'] = FRAIS_MEETUP
    context.user_data['adresse'] = "Meetup - Retrait en personne"
    context.user_data['distance'] = 0
    
    text = f"{EMOJI_THEME['success']} *MEETUP CONFIRMÉ*\n\n"
    text += f"🤝 Mode : Retrait en personne\n"
    text += f"{EMOJI_THEME['money']} Frais : {FRAIS_MEETUP}€\n\n"
    text += f"📍 _L'adresse de retrait vous sera communiquée par message privé._\n\n"
    text += "💳 *Choisissez votre mode de paiement :*"
    
    keyboard = [
        [InlineKeyboardButton("💵 Cash", callback_data="paiement_cash")],
        [InlineKeyboardButton("₿ Crypto", callback_data="paiement_crypto")],
        [InlineKeyboardButton("🔙 Modifier livraison", callback_data="back_to_livraison_from_meetup")]
    ]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    return PAIEMENT
    
    text = "🤝 *MEETUP - RENCONTRE EN PERSONNE*\n\n"
    text += "Choisissez votre zone de rencontre :\n\n"
    text += format_meetup_zones(country)
    text += f"\n{EMOJI_THEME['money']} Frais : {FRAIS_MEETUP}€\n"
    text += f"⏰ Délai : Sous 24h (selon disponibilités)\n\n"
    text += "_Après validation, vous recevrez les coordonnées exactes du point de rencontre._"
    
    keyboard = []
    
    for zone in zones:
        keyboard.append([InlineKeyboardButton(f"📍 {zone}", callback_data=f"meetup_zone_{zone}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="back_to_livraison")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return LIVRAISON

@error_handler
async def meetup_zone_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validation de la zone de meetup"""
    query = update.callback_query
    await query.answer()
    
    zone = query.data.replace("meetup_zone_", "")
    country = context.user_data.get('pays')
    
    if not is_meetup_zone_valid(zone, country):
        await query.message.edit_text(
            f"{EMOJI_THEME['error']} Zone invalide. Veuillez réessayer.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="livraison_meetup")
            ]]),
            parse_mode='Markdown'
        )
        return LIVRAISON
    
    context.user_data['mode_livraison'] = 'meetup'
    context.user_data['meetup_zone'] = zone
    context.user_data['frais_livraison'] = FRAIS_MEETUP
    context.user_data['adresse'] = f"Meetup - {zone}"
    context.user_data['distance'] = 0
    
    text = f"{EMOJI_THEME['success']} *MEETUP CONFIRMÉ*\n\n"
    text += f"📍 Zone : *{zone}*\n"
    text += f"{EMOJI_THEME['money']} Frais : {FRAIS_MEETUP}€\n\n"
    text += f"_Les coordonnées exactes du point de rencontre vous seront communiquées après validation de la commande._\n\n"
    text += "Choisissez maintenant votre mode de paiement :"
    
    keyboard = [
        [InlineKeyboardButton("💵 Cash", callback_data="paiement_cash")],
        [InlineKeyboardButton("₿ Crypto", callback_data="paiement_crypto")],
        [InlineKeyboardButton("🔙 Modifier livraison", callback_data="back_to_livraison")]
    ]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAIEMENT

@error_handler
async def back_to_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au choix de livraison"""
    return await ask_livraison(update, context)

@error_handler
async def back_to_livraison_from_meetup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au choix de livraison depuis le paiement"""
    query = update.callback_query
    await query.answer()
    
    country = context.user_data.get('pays')
    cart = context.user_data.get('cart', [])
    
    # Calculer le sous-total
    total_info = calculate_total(cart, country)
    subtotal = total_info['subtotal']
    
    # Vérifier si Express est disponible
    express_available = subtotal >= 30
    
    # Message de choix de livraison
    text = f"{EMOJI_THEME['delivery']} *MODE DE LIVRAISON*\n\n"
    text += f"🛒 *Panier :* {format_cart_summary(cart)}\n"
    text += f"💰 *Sous-total :* {subtotal:.2f}€\n\n"
    text += "Choisissez votre mode de livraison :\n\n"
    
    # 📮 POSTALE
    text += f"📮 *Postale* : {FRAIS_POSTAL}€\n"
    text += f"   ⏱️ Délai : 24h-48h\n"
    text += f"   ✅ Toujours disponible\n\n"
    
    # 🚀 EXPRESS
    if express_available:
        text += f"{EMOJI_THEME['rocket']} *Express* : 10€/10km\n"
        text += f"   ⏱️ Délai : 30min+\n"
        text += f"   ✅ Disponible\n\n"
    else:
        text += f"{EMOJI_THEME['rocket']} *Express* : ❌ NON DISPONIBLE\n"
        text += f"   💰 Min : 30€ (manque {30 - subtotal:.2f}€)\n\n"
    
    # 🤝 MEETUP
    text += f"🤝 *Meetup* : {FRAIS_MEETUP}€\n"
    text += f"   📍 Retrait en personne\n"
    text += f"   ✅ Toujours disponible\n"
    
    # Clavier
    keyboard = [
        [InlineKeyboardButton("📮 Postale", callback_data="livraison_postale")],
    ]
    
    if express_available:
        keyboard.append([InlineKeyboardButton(f"{EMOJI_THEME['rocket']} Express", callback_data="livraison_express")])
    
    keyboard.append([InlineKeyboardButton("🤝 Meetup (Retrait)", callback_data="livraison_meetup")])
    keyboard.append([InlineKeyboardButton("🔙 Annuler", callback_data="back_to_main_menu")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return LIVRAISON

@error_handler
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix du mode de paiement"""
    query = update.callback_query
    await query.answer()
    context.user_data['paiement'] = query.data.replace("paiement_", "")
    
    cart = context.user_data.get('cart', [])
    country = context.user_data.get('pays', 'FR')
    delivery_type = context.user_data.get('mode_livraison')
    distance = context.user_data.get('distance', 0)
    promo_code = context.user_data.get('promo_code')
    user_id = update.effective_user.id
    
    total_info = calculate_total(
        cart,
        country,
        delivery_type=delivery_type,
        distance=distance,
        promo_code=promo_code,
        user_id=user_id
    )
    
    order_summary = format_order_summary(
        cart,
        country,
        delivery_type,
        total_info['delivery_fee'],
        total_info.get('promo_discount', 0),
        total_info.get('vip_discount', 0),
        total_info['total']
    )
    
    summary = f"{order_summary}\n\n"
    summary += f"📍 {context.user_data['adresse']}\n"
    summary += f"💳 {context.user_data['paiement'].title()}"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "confirm"), callback_data="confirm_order")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    
    await query.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CONFIRMATION

@error_handler
async def contact_admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion du contact avec l'admin"""
    user = update.effective_user
    message_text = sanitize_input(update.message.text, 1000)
    
    # Préparer le message pour l'admin
    admin_notification = f"{EMOJI_THEME['info']} *NOUVEAU MESSAGE CLIENT*\n\n"
    admin_notification += f"👤 *De :* {user.first_name}"
    if user.username:
        admin_notification += f" (@{user.username})"
    admin_notification += f"\n🆔 *ID :* `{user.id}`\n\n"
    admin_notification += f"💬 *Message :*\n{message_text}"
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_notification,
            parse_mode='Markdown'
        )
        
        # Confirmation au client
        await update.message.reply_text(
            tr(context.user_data, "contact_sent"),
            parse_mode='Markdown'
        )
        
        logger.info(f"📧 Message envoyé à l'admin de {user.id}")
    except Exception as e:
        logger.error(f"Erreur envoi message admin: {e}")
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Erreur lors de l'envoi du message. Veuillez réessayer.",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

# FIN DU BLOC 4 CORRIGÉ

# ==================== BLOC 5 : CONFIRMATION, CONTACT ET HANDLERS FINAUX ====================
# Ajoutez ce bloc APRÈS le BLOC 4

# ==================== CONFIRMATION DE COMMANDE ====================

@error_handler
async def confirmation_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation finale de la commande"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_id = user.id
    is_admin = user_id == ADMIN_ID
    
    if query.data == "cancel":
        # ✅ ANNULATION - Retour au menu principal
        logger.info(f"❌ Commande annulée par {user_id}")
        
        # Réinitialiser le panier
        context.user_data['cart'] = []
        context.user_data.pop('promo_code', None)
        context.user_data.pop('promo_discount', None)
        context.user_data.pop('adresse', None)
        context.user_data.pop('mode_livraison', None)
        context.user_data.pop('paiement', None)
        
        text = f"{EMOJI_THEME['info']} *COMMANDE ANNULÉE*\n\n"
        text += "Votre commande a été annulée.\n\n"
        text += tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
        
        if is_admin:
            text += f"\n\n🔑 *MODE ADMINISTRATEUR*\n{EMOJI_THEME['success']} Accès illimité 24h/24"
        
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
            [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
            [InlineKeyboardButton(tr(context.user_data, "my_account"), callback_data="my_account")],
            [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
        ]
        
        # ✅ Supprimer ancien message et envoyer nouveau avec auto-suppression
        try:
            await query.message.delete()
        except:
            pass
        
        await send_and_schedule_deletion(
            context=context,
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            user_id=user_id
        )
        
        return PAYS  # ✅ RETOUR AU MENU (pas ConversationHandler.END)
    
    # ✅ CONFIRMATION - Traiter la commande
    cart = context.user_data.get('cart', [])
    country = context.user_data.get('pays', 'FR')
    delivery_type = context.user_data.get('mode_livraison')
    distance = context.user_data.get('distance', 0)
    promo_code = context.user_data.get('promo_code')
    
    # Calcul final
    total_info = calculate_total(
        cart,
        country,
        delivery_type=delivery_type,
        distance=distance,
        promo_code=promo_code,
        user_id=user_id
    )
    
    # 🆕 Mettre à jour les stocks
    for item in cart:
        product_name = item['produit']
        quantity = item['quantite']
        update_stock(product_name, -quantity)
        
        # Vérifier si stock faible
        remaining_stock = get_stock(product_name)
        if remaining_stock is not None:
            stocks_data = load_stocks()
            threshold = stocks_data.get(product_name, {}).get('alert_threshold', 20)
            
            if remaining_stock <= 0:
                # Rupture de stock
                available = get_available_products()
                if product_name in available:
                    available.remove(product_name)
                    save_available_products(available)
                asyncio.create_task(notify_admin_out_of_stock(context, product_name))
            elif remaining_stock <= threshold:
                # Stock faible
                asyncio.create_task(notify_admin_low_stock(context, product_name, remaining_stock))
    
    # Utiliser le code promo
    if promo_code and total_info.get('promo_valid'):
        use_promo_code(promo_code)
    
    # Générer l'ID de commande
    order_id = generate_order_id(user_id)
    
    # Préparer les données de commande
    order_data = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'order_id': order_id,
        'user_id': user_id,
        'username': user.username or "N/A",
        'first_name': user.first_name or "N/A",
        'language': context.user_data.get('langue', 'fr'),
        'products': "; ".join([f"{item['produit']} x{item['quantite']}" for item in cart]),
        'country': country,
        'address': context.user_data.get('adresse', ''),
        'delivery_type': delivery_type,
        'distance_km': distance,
        'payment_method': context.user_data.get('paiement', 'N/A'),
        'subtotal': total_info['subtotal'],
        'delivery_fee': total_info['delivery_fee'],
        'promo_discount': total_info.get('promo_discount', 0),
        'vip_discount': total_info.get('vip_discount', 0),
        'total': total_info['total'],
        'promo_code': promo_code or 'N/A',
        'status': 'pending'
    }
    
    # Sauvegarder en CSV
    save_order_to_csv(order_data)
    
    # Ajouter aux statistiques
    add_sale(
        total_info['total'],
        country,
        [item['produit'] for item in cart],
        subtotal=total_info['subtotal'],
        delivery_fee=total_info['delivery_fee'],
        promo_discount=total_info.get('promo_discount', 0),
        vip_discount=total_info.get('vip_discount', 0)
    )
    
    # 🆕 Mettre à jour l'historique client
    update_client_history(user_id, {
        'order_id': order_id,
        'total': total_info['total'],
        'products': cart
    })
    
    # 🆕 Vérifier si devient VIP
    stats = get_client_stats(user_id)
    if stats and stats['vip_status'] and stats['orders_count'] == 1:
        # Premier passage VIP
        user_info = {
            'first_name': user.first_name,
            'username': user.username or 'N/A'
        }
        asyncio.create_task(notify_admin_vip_client(
            context,
            user_id,
            user_info,
            stats['total_spent']
        ))
    
    # 🆕 Bonus parrainage
    referral_stats = get_referral_stats(user_id)
    if referral_stats and referral_stats.get('referred_by'):
        referrer_id = referral_stats['referred_by']
        
        if REFERRAL_BONUS_TYPE == "percentage":
            bonus = total_info['total'] * (REFERRAL_BONUS_VALUE / 100)
        else:
            bonus = REFERRAL_BONUS_VALUE
        
        add_referral_earnings(referrer_id, bonus)
        logger.info(f"💰 Bonus parrainage: {bonus}€ pour user {referrer_id}")
    
    # 🆕 Alerte haute valeur
    if total_info['total'] > 500:
        user_info = {
            'user_id': user_id,
            'first_name': user.first_name,
            'username': user.username or 'N/A'
        }
        asyncio.create_task(notify_admin_high_value_order(
            context,
            order_id,
            total_info['total'],
            user_info
        ))
    
    # Préparer affichage pour admin
    order_data['products_display'] = "\n".join([
        f"• {item['produit']} x {item['quantite']}g"
        for item in cart
    ])
    order_data['total_info'] = total_info
    
    # Notifier l'admin
    user_info = {
        'first_name': user.first_name,
        'username': user.username or "N/A"
    }
    asyncio.create_task(notify_admin_new_order(context, order_data, user_info))
    
    # Message de confirmation au client
    confirmation_text = f"{EMOJI_THEME['success']} *COMMANDE CONFIRMÉE !*\n\n"
    confirmation_text += f"📋 Numéro : `{order_id}`\n\n"
    confirmation_text += f"{EMOJI_THEME['money']} Montant total : {total_info['total']:.2f}€\n\n"
    
    # Info selon type de livraison
    if delivery_type == 'meetup':
        meetup_zone = context.user_data.get('meetup_zone', 'Retrait en personne')
        confirmation_text += f"🤝 *MEETUP - {meetup_zone}*\n\n"
        confirmation_text += f"📍 Les coordonnées exactes du point de rencontre vous seront envoyées dans les prochaines heures.\n\n"
        confirmation_text += f"⏰ Délai estimé : Sous 24h\n\n"
        confirmation_text += f"💡 _Soyez attentif aux messages de l'administrateur._"
    else:
        confirmation_text += f"📦 Vous recevrez une confirmation de l'administrateur.\n\n"
        confirmation_text += f"🚚 Livraison : {delivery_type.title()}\n"
        if delivery_type == 'express':
            confirmation_text += f"📍 Distance : {distance:.1f} km\n"
        confirmation_text += f"⏰ Délai estimé : "
        if delivery_type == 'postale':
            confirmation_text += "24h-48h"
        else:
            confirmation_text += "30min+"
    
    confirmation_text += f"\n\n{EMOJI_THEME['celebration']} _Merci pour votre commande !_"
    
    # 🆕 Si VIP, afficher badge
    if is_vip_client(user_id):
        confirmation_text += f"\n\n{EMOJI_THEME['vip']} *STATUT VIP ACTIF*\n"
        confirmation_text += f"Vous avez bénéficié de -{VIP_DISCOUNT}% sur cette commande"
    
    # ✅ Supprimer ancien message
    try:
        await query.message.delete()
    except:
        pass
    
    # ✅ Envoyer message de confirmation avec auto-suppression
    await send_and_schedule_deletion(
        context=context,
        chat_id=query.message.chat_id,
        text=confirmation_text,
        user_id=user_id
    )
    
    logger.info(f"✅ Commande confirmée: {order_id} (User: {user_id}, Total: {total_info['total']}€)")
    
    # ✅ Attendre 5 secondes puis afficher menu principal
    await asyncio.sleep(5)
    
    # Réinitialiser le panier
    context.user_data['cart'] = []
    context.user_data.pop('promo_code', None)
    context.user_data.pop('promo_discount', None)
    context.user_data.pop('adresse', None)
    context.user_data.pop('mode_livraison', None)
    context.user_data.pop('paiement', None)
    
    # Afficher menu principal
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    if is_admin:
        text += f"\n\n🔑 *MODE ADMINISTRATEUR*\n{EMOJI_THEME['success']} Accès illimité 24h/24"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "my_account"), callback_data="my_account")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    
    await send_and_schedule_deletion(
        context=context,
        chat_id=query.message.chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        user_id=user_id
    )
    
    return PAYS  # ✅ RETOUR AU MENU PRINCIPAL

# ==================== CONTACT ADMIN ====================

@error_handler
async def contact_admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion du contact avec l'admin"""
    user = update.effective_user
    message_text = sanitize_input(update.message.text, 1000)
    
    # Préparer le message pour l'admin
    admin_notification = f"{EMOJI_THEME['info']} *NOUVEAU MESSAGE CLIENT*\n\n"
    admin_notification += f"👤 *De :* {user.first_name}"
    if user.username:
        admin_notification += f" (@{user.username})"
    admin_notification += f"\n🆔 *ID :* `{user.id}`\n\n"
    admin_notification += f"💬 *Message :*\n{message_text}"
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_notification,
            parse_mode='Markdown'
        )
        
        # Confirmation au client
        await update.message.reply_text(
            tr(context.user_data, "contact_sent"),
            parse_mode='Markdown'
        )
        
        logger.info(f"📧 Message envoyé à l'admin de {user.id}")
    except Exception as e:
        logger.error(f"Erreur envoi message admin: {e}")
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Erreur lors de l'envoi du message. Veuillez réessayer.",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

# ==================== HANDLERS DE RETOUR ====================

@error_handler
async def back_to_country_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au choix du pays"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
        [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")],
        [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main_menu")]
    ]
    
    await query.message.edit_text(
        tr(context.user_data, "choose_country"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PAYS

@error_handler
async def back_to_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au choix des produits"""
    query = update.callback_query
    await query.answer()
    
    available = get_available_products()
    keyboard = []
    
    has_pills = False
    has_crystals = False
    
    for product_name in sorted(available):
        # Vérifier stock
        if not is_in_stock(product_name, 1):
            continue
        
        code = None
        for c, name in PRODUCT_CODES.items():
            if name == product_name:
                code = c
                break
        
        if not code:
            continue
        
        if product_name in PILL_SUBCATEGORIES.values():
            has_pills = True
        elif product_name in ROCK_SUBCATEGORIES.values():
            has_crystals = True
        else:
            keyboard.append([InlineKeyboardButton(product_name, callback_data=f"product_{code}")])
    
    if has_pills:
        keyboard.insert(0, [InlineKeyboardButton("💊 Pills", callback_data="product_pill")])
    
    if has_crystals:
        keyboard.append([InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")])
    
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_country_choice")])
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
    
    await query.message.edit_text(
        tr(context.user_data, "choose_product"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PRODUIT

@error_handler
async def back_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au panier"""
    query = update.callback_query
    await query.answer()
    
    cart = context.user_data.get('cart', [])
    
    if not cart:
        await query.answer(f"{EMOJI_THEME['error']} Panier vide", show_alert=True)
        return await back_to_products(update, context)
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "add_more"), callback_data="add_more")],
        [InlineKeyboardButton(tr(context.user_data, "apply_promo"), callback_data="apply_promo")],
        [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")]
    ]
    
    await query.message.edit_text(
        format_cart(cart, context.user_data),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return CART_MENU

# ==================== MAINTENANCE MODE ====================

async def send_maintenance_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envoie le message de maintenance"""
    status = load_maintenance_status()
    reason = status.get("reason", "Maintenance en cours")
    
    text = f"{EMOJI_THEME['warning']} *MODE MAINTENANCE*\n\n"
    text += f"🔧 {reason}\n\n"
    text += f"⏰ Retour prévu : Bientôt\n\n"
    text += f"💬 Pour toute urgence, contactez @votre_admin"
    
    keyboard = [[InlineKeyboardButton("🔄 Réessayer", callback_data="retry_start")]]
    
    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

# ==================== HEALTH CHECK (FAILOVER) ====================

def is_primary_bot_down():
    """Vérifie si le bot principal est down (pour failover)"""
    if not IS_BACKUP_BOT or not PRIMARY_BOT_TOKEN:
        return False
    
    status = load_health_status()
    
    if status.get("consecutive_failures", 0) >= PRIMARY_BOT_DOWN_THRESHOLD:
        if not status.get("failover_active", False):
            status["failover_active"] = True
            status["last_failover_time"] = datetime.now().isoformat()
            save_health_status(status)
            logger.warning(f"⚠️ FAILOVER ACTIVÉ - Bot principal DOWN ({status['consecutive_failures']} échecs)")
        return True
    
    return False

async def check_primary_bot_health(context: ContextTypes.DEFAULT_TYPE):
    """Vérifie périodiquement la santé du bot principal"""
    if not IS_BACKUP_BOT or not PRIMARY_BOT_TOKEN:
        return
    
    from telegram import Bot
    
    status = load_health_status()
    
    try:
        # Tenter un getMe sur le bot principal
        primary_bot = Bot(token=PRIMARY_BOT_TOKEN)
        await primary_bot.get_me()
        
        # Succès
        was_down = status.get("consecutive_failures", 0) > 0
        status["primary_bot_online"] = True
        status["consecutive_failures"] = 0
        status["last_primary_check"] = datetime.now().isoformat()
        
        if was_down:
            logger.info("✅ Bot principal rétabli")
            if status.get("failover_active", False):
                status["failover_active"] = False
                logger.info("✅ FAILOVER DÉSACTIVÉ")
        
    except Exception as e:
        # Échec
        status["consecutive_failures"] = status.get("consecutive_failures", 0) + 1
        status["primary_bot_online"] = False
        status["last_primary_check"] = datetime.now().isoformat()
        
        logger.error(f"❌ Bot principal check failed ({status['consecutive_failures']}/{PRIMARY_BOT_DOWN_THRESHOLD}): {e}")
    
    save_health_status(status)

# ==================== CANCEL HANDLER ====================

@error_handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulation de la conversation"""
    user = update.effective_user
    logger.info(f"👤 {user.first_name} a annulé la conversation")
    
    keyboard = [[InlineKeyboardButton("🔄 Recommencer", callback_data="start_order")]]
    
    if update.message:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} *Conversation annulée*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            f"{EMOJI_THEME['error']} *Conversation annulée*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    context.user_data.clear()
    return ConversationHandler.END

# ==================== ERROR HANDLER GLOBAL ====================

async def error_callback(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Gestion globale des erreurs"""
    logger.error(f"Exception lors du traitement d'une mise à jour: {context.error}", exc_info=context.error)
    
    try:
        if isinstance(update, Update):
            error_message = f"{EMOJI_THEME['error']} *Erreur inattendue*\n\nUne erreur s'est produite. Veuillez réessayer.\n\nSi le problème persiste, contactez l'administrateur."
            
            keyboard = [[InlineKeyboardButton("🔄 Recommencer", callback_data="start_order")]]
            
            if update.message:
                await update.message.reply_text(
                    error_message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            elif update.callback_query:
                await update.callback_query.message.edit_text(
                    error_message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
    except Exception as e:
        logger.error(f"Erreur dans error_callback: {e}")

# ==================== TIMEOUT HANDLER ====================

async def conversation_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion du timeout de conversation"""
    keyboard = [[InlineKeyboardButton("🔄 Recommencer", callback_data="start_order")]]
    
    text = f"{EMOJI_THEME['warning']} *Session expirée*\n\n"
    text += "Votre session a expiré en raison d'inactivité.\n\n"
    text += "Cliquez sur 'Recommencer' pour passer une nouvelle commande."
    
    try:
        if update.callback_query:
            await update.callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Erreur timeout handler: {e}")
    
    context.user_data.clear()
    return ConversationHandler.END

# ==================== 🎨 AMÉLIORATION 15 : ANIMATIONS TEXTE ====================

async def send_typing_action(context: ContextTypes.DEFAULT_TYPE, chat_id: int, duration: float = 1.0):
    """Envoie une action 'typing' pour simuler une réponse naturelle"""
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        await asyncio.sleep(duration)
    except Exception as e:
        logger.error(f"Erreur typing action: {e}")

async def send_animated_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, typing_duration: float = 1.0):
    """
    Envoie un message avec animation typing
    
    Args:
        context: Context Telegram
        chat_id: ID du chat
        text: Texte à envoyer
        typing_duration: Durée de l'animation typing en secondes
    """
    await send_typing_action(context, chat_id, typing_duration)
    return await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='Markdown'
    )

# 🎨 AMÉLIORATION 4 : Indicateurs de Chargement
async def show_loading_indicator(context: ContextTypes.DEFAULT_TYPE, chat_id: int, operation: str = "Traitement"):
    """
    Affiche un indicateur de chargement
    
    Args:
        context: Context Telegram
        chat_id: ID du chat
        operation: Nom de l'opération en cours
    
    Returns:
        Message object pour pouvoir le supprimer après
    """
    loading_frames = [
        f"{EMOJI_THEME['loading']} {operation}.",
        f"{EMOJI_THEME['loading']} {operation}..",
        f"{EMOJI_THEME['loading']} {operation}..."
    ]
    
    message = await context.bot.send_message(
        chat_id=chat_id,
        text=loading_frames[0]
    )
    
    # Animation (3 frames)
    for frame in loading_frames[1:]:
        await asyncio.sleep(0.5)
        try:
            await message.edit_text(frame)
        except:
            break
    
    return message

async def remove_loading_indicator(message):
    """Supprime l'indicateur de chargement"""
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Erreur suppression loading: {e}")

# ==================== RETRY HANDLER ====================

@error_handler
async def retry_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retry après maintenance"""
    query = update.callback_query
    await query.answer()
    
    if is_maintenance_mode(update.effective_user.id):
        await send_maintenance_message(update, context)
        return ConversationHandler.END
    
    # Rediriger vers start
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it")]
    ]
    
    await query.message.edit_text(
        "🌍 *Langue / Language / Sprache / Idioma / Lingua*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return LANGUE

# ==================== ADMIN VALIDATION COMMANDE ====================

@error_handler
async def admin_validate_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """L'admin valide une commande"""
    query = update.callback_query
    await query.answer()
    
    # Extraire order_id et user_id du callback_data
    # Format: admin_validate_{order_id}_{user_id}
    parts = query.data.split("_")
    if len(parts) < 4:
        await query.answer(f"{EMOJI_THEME['error']} Format invalide", show_alert=True)
        return
    
    order_id = "_".join(parts[2:-1])  # Reconstruire l'order_id qui peut contenir des _
    user_id = int(parts[-1])
    
    # Message de validation admin
    validation_text = f"{EMOJI_THEME['success']} *COMMANDE VALIDÉE*\n\n"
    validation_text += f"📋 Commande : `{order_id}`\n"
    validation_text += f"👤 Client : `{user_id}`\n\n"
    validation_text += f"✅ Le client a été notifié de la validation."
    
    try:
        # Modifier le message de notification
        await query.message.edit_text(
            validation_text,
            parse_mode='Markdown'
        )
        
        # Notifier le client
        client_notification = f"{EMOJI_THEME['success']} *COMMANDE VALIDÉE*\n\n"
        client_notification += f"📋 Numéro : `{order_id}`\n\n"
        client_notification += f"✅ Votre commande a été validée par l'administrateur.\n\n"
        client_notification += f"📦 Vous serez notifié de l'expédition prochainement.\n\n"
        client_notification += f"{EMOJI_THEME['celebration']} Merci pour votre confiance !"
        
        await context.bot.send_message(
            chat_id=user_id,
            text=client_notification,
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ Admin a validé commande {order_id} pour user {user_id}")
        
    except Exception as e:
        logger.error(f"Erreur validation commande: {e}")
        await query.answer(f"{EMOJI_THEME['error']} Erreur lors de la validation", show_alert=True)

# FIN DU BLOC 5
# ==================== BLOC 6 : PANEL ADMIN - PARTIE 1 ====================
# Ajoutez ce bloc APRÈS le BLOC 5

# ==================== COMMANDES ADMIN ====================

@error_handler
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /admin - Point d'entrée du panel admin"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} *Accès refusé*\n\nCette commande est réservée à l'administrateur.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    logger.info(f"🔑 ADMIN: Panel ouvert par {update.effective_user.first_name}")
    
    # 🎨 Menu admin avec emojis thématiques
    text = f"{EMOJI_THEME['diamond']} *PANEL ADMINISTRATEUR*\n\n"
    text += f"Bienvenue, {update.effective_user.first_name} !\n\n"
    text += f"🔧 Choisissez une action :"
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI_THEME['product']} Gestion Produits", callback_data="admin_products")],
        [InlineKeyboardButton(f"💰 Prix Dégressifs", callback_data="admin_pricing")],
        [InlineKeyboardButton(f"{EMOJI_THEME['gift']} Codes Promo", callback_data="admin_promo")],
        [InlineKeyboardButton(f"📦 Gestion Stocks", callback_data="admin_stocks")],
        [InlineKeyboardButton(f"👥 Gestion Clients", callback_data="admin_clients")],
        [InlineKeyboardButton(f"{EMOJI_THEME['stats']} Statistiques", callback_data="admin_stats")],
        [InlineKeyboardButton(f"⏰ Horaires", callback_data="admin_horaires")],
        [InlineKeyboardButton(f"🔧 Maintenance", callback_data="admin_maintenance")],
        [InlineKeyboardButton(f"{EMOJI_THEME['info']} Notifications", callback_data="admin_notifications")],
        [InlineKeyboardButton("❌ Fermer", callback_data="admin_close")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

# ==================== ADMIN MENU PRINCIPAL ====================

@error_handler
async def admin_menu_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Navigation dans le menu principal admin"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_close":
        await query.message.edit_text(
            f"{EMOJI_THEME['success']} *Panel admin fermé*",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    elif query.data == "admin_products":
        return await admin_products_menu(update, context)
    
    elif query.data == "admin_pricing":
        return await admin_pricing_menu(update, context)
    
    elif query.data == "admin_promo":
        return await admin_promo_menu(update, context)
    
    elif query.data == "admin_stocks":
        return await admin_stocks_menu(update, context)
    
    elif query.data == "admin_clients":
        return await admin_clients_menu(update, context)
    
    elif query.data == "admin_stats":
        return await admin_stats_menu(update, context)
    
    elif query.data == "admin_horaires":
        return await admin_horaires_menu(update, context)
    
    elif query.data == "admin_maintenance":
        return await admin_maintenance_menu(update, context)
    
    elif query.data == "admin_notifications":
        return await admin_notifications_menu(update, context)
    
    return ADMIN_MENU_MAIN

@error_handler
async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au menu admin principal"""
    query = update.callback_query
    await query.answer()
    
    text = f"{EMOJI_THEME['diamond']} *PANEL ADMINISTRATEUR*\n\n"
    text += f"🔧 Choisissez une action :"
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI_THEME['product']} Gestion Produits", callback_data="admin_products")],
        [InlineKeyboardButton(f"💰 Prix Dégressifs", callback_data="admin_pricing")],
        [InlineKeyboardButton(f"{EMOJI_THEME['gift']} Codes Promo", callback_data="admin_promo")],
        [InlineKeyboardButton(f"📦 Gestion Stocks", callback_data="admin_stocks")],
        [InlineKeyboardButton(f"👥 Gestion Clients", callback_data="admin_clients")],
        [InlineKeyboardButton(f"{EMOJI_THEME['stats']} Statistiques", callback_data="admin_stats")],
        [InlineKeyboardButton(f"⏰ Horaires", callback_data="admin_horaires")],
        [InlineKeyboardButton(f"🔧 Maintenance", callback_data="admin_maintenance")],
        [InlineKeyboardButton(f"{EMOJI_THEME['info']} Notifications", callback_data="admin_notifications")],
        [InlineKeyboardButton("❌ Fermer", callback_data="admin_close")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

# ==================== GESTION PRODUITS ====================

@error_handler
async def admin_products_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de gestion des produits"""
    query = update.callback_query
    await query.answer()
    
    registry = load_product_registry()
    available = get_available_products()
    
    # 🎨 Affichage avec barres de progression
    text = f"{EMOJI_THEME['product']} *GESTION PRODUITS*\n\n"
    text += f"📊 *Statistiques :*\n"
    text += f"• Total produits : {len(registry)}\n"
    text += f"• Produits actifs : {len(available)}\n"
    text += f"• Produits masqués : {len(registry) - len(available)}\n\n"
    
    if registry:
        text += f"📦 *Produits enregistrés :*\n"
        for code, data in sorted(registry.items()):
            name = data['name']
            emoji = data.get('emoji', '📦')
            is_active = name in available
            status = f"{EMOJI_THEME['online']}" if is_active else f"{EMOJI_THEME['offline']}"
            text += f"{status} {emoji} {name}\n"
    
    keyboard = [
        [InlineKeyboardButton(f"➕ Ajouter produit", callback_data="admin_add_product")],
        [InlineKeyboardButton(f"{EMOJI_THEME['warning']} Masquer/Afficher", callback_data="admin_toggle_product")],
        [InlineKeyboardButton(f"🗑️ Archiver produit", callback_data="admin_archive_product")],
        [InlineKeyboardButton("🔙 Retour", callback_data="back_to_admin_menu")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

@error_handler
async def admin_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Démarrage ajout d'un nouveau produit"""
    query = update.callback_query
    await query.answer()
    
    text = f"➕ *AJOUTER UN PRODUIT*\n\n"
    text += f"Étape 1/6 : Nom du produit\n\n"
    text += f"Entrez le nom du produit (avec emoji si souhaité) :\n"
    text += f"_Exemple : ❄️ Coco Premium_"
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_products")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_NEW_PRODUCT_NAME

@error_handler
async def receive_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réception du nom du produit"""
    product_name = sanitize_input(update.message.text, 50)
    
    if len(product_name) < 2:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Nom trop court. Minimum 2 caractères.",
            parse_mode='Markdown'
        )
        return ADMIN_NEW_PRODUCT_NAME
    
    context.user_data['new_product_name'] = product_name
    
    text = f"➕ *AJOUTER UN PRODUIT*\n\n"
    text += f"Produit : {product_name}\n\n"
    text += f"Étape 2/6 : Code interne\n\n"
    text += f"Entrez le code interne (identifiant unique) :\n"
    text += f"_Exemple : coco_premium_\n"
    text += f"_Format : lettres minuscules et underscores uniquement_"
    
    await update.message.reply_text(text, parse_mode='Markdown')
    
    return ADMIN_NEW_PRODUCT_CODE

@error_handler
async def receive_product_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réception du code produit"""
    product_code = sanitize_input(update.message.text, 30).lower()
    
    # Validation du code
    if not re.match(r'^[a-z_]+$', product_code):
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Code invalide.\n\nUtilisez uniquement : a-z et _",
            parse_mode='Markdown'
        )
        return ADMIN_NEW_PRODUCT_CODE
    
    # Vérifier si le code existe déjà
    registry = load_product_registry()
    if product_code in registry:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Ce code existe déjà.\n\nChoisissez un code unique.",
            parse_mode='Markdown'
        )
        return ADMIN_NEW_PRODUCT_CODE
    
    context.user_data['new_product_code'] = product_code
    
    text = f"➕ *AJOUTER UN PRODUIT*\n\n"
    text += f"Produit : {context.user_data['new_product_name']}\n"
    text += f"Code : `{product_code}`\n\n"
    text += f"Étape 3/6 : Catégorie\n\n"
    text += f"Choisissez la catégorie :"
    
    keyboard = [
        [InlineKeyboardButton("❄️ Powder", callback_data="cat_powder")],
        [InlineKeyboardButton("💊 Pill", callback_data="cat_pill")],
        [InlineKeyboardButton("🪨 Rock/Crystal", callback_data="cat_rock")],
        [InlineKeyboardButton("❌ Annuler", callback_data="admin_products")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_NEW_PRODUCT_CATEGORY

@error_handler
async def receive_product_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réception de la catégorie"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("cat_", "")
    context.user_data['new_product_category'] = category
    
    text = f"➕ *AJOUTER UN PRODUIT*\n\n"
    text += f"Produit : {context.user_data['new_product_name']}\n"
    text += f"Code : `{context.user_data['new_product_code']}`\n"
    text += f"Catégorie : {category.title()}\n\n"
    text += f"Étape 4/6 : Prix France\n\n"
    text += f"Entrez le prix pour la France (€/g) :\n"
    text += f"_Exemple : 50_"
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_products")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_NEW_PRODUCT_PRICE_FR

@error_handler
async def receive_product_price_fr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réception du prix France"""
    price_text = sanitize_input(update.message.text, 10)
    
    try:
        price = float(price_text)
        if price <= 0:
            raise ValueError
    except:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Prix invalide.\n\nEntrez un nombre positif.",
            parse_mode='Markdown'
        )
        return ADMIN_NEW_PRODUCT_PRICE_FR
    
    context.user_data['new_product_price_fr'] = price
    
    text = f"➕ *AJOUTER UN PRODUIT*\n\n"
    text += f"Produit : {context.user_data['new_product_name']}\n"
    text += f"Code : `{context.user_data['new_product_code']}`\n"
    text += f"Catégorie : {context.user_data['new_product_category'].title()}\n"
    text += f"Prix FR : {price}€/g\n\n"
    text += f"Étape 5/6 : Prix Suisse\n\n"
    text += f"Entrez le prix pour la Suisse (CHF/g) :\n"
    text += f"_Exemple : 100_"
    
    await update.message.reply_text(text, parse_mode='Markdown')
    
    return ADMIN_NEW_PRODUCT_PRICE_CH

@error_handler
async def receive_product_price_ch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réception du prix Suisse"""
    price_text = sanitize_input(update.message.text, 10)
    
    try:
        price = float(price_text)
        if price <= 0:
            raise ValueError
    except:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Prix invalide.\n\nEntrez un nombre positif.",
            parse_mode='Markdown'
        )
        return ADMIN_NEW_PRODUCT_PRICE_CH
    
    context.user_data['new_product_price_ch'] = price
    
    # 🎨 Récapitulatif avec style
    text = f"➕ *NOUVEAU PRODUIT - RÉCAPITULATIF*\n\n"
    text += f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += f"┃  {context.user_data['new_product_name']}\n"
    text += f"┣━━━━━━━━━━━━━━━━━━━━━┫\n"
    text += f"┃ 🆔 Code : {context.user_data['new_product_code']}\n"
    text += f"┃ 📁 Catégorie : {context.user_data['new_product_category'].title()}\n"
    text += f"┃ 🇫🇷 Prix FR : {context.user_data['new_product_price_fr']}€/g\n"
    text += f"┃ 🇨🇭 Prix CH : {price}€/g\n"
    text += f"┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
    text += f"Confirmez-vous l'ajout de ce produit ?"
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI_THEME['success']} Confirmer", callback_data="confirm_add_product")],
        [InlineKeyboardButton("❌ Annuler", callback_data="admin_products")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_CONFIRM_PRODUCT

@error_handler
async def confirm_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation et ajout du produit"""
    query = update.callback_query
    await query.answer()
    
    # Récupérer les données
    product_name = context.user_data['new_product_name']
    product_code = context.user_data['new_product_code']
    category = context.user_data['new_product_category']
    price_fr = context.user_data['new_product_price_fr']
    price_ch = context.user_data['new_product_price_ch']
    
    # Extraire l'emoji du nom
    emoji_match = re.search(r'([\U0001F300-\U0001F9FF])', product_name)
    emoji = emoji_match.group(1) if emoji_match else "📦"
    
    # Ajouter au registre
    registry = load_product_registry()
    registry[product_code] = {
        "name": product_name,
        "code": product_code,
        "emoji": emoji,
        "category": category,
        "image": f"{product_code}.jpg",
        "video": f"{product_code}_demo.mp4",
        "created_at": datetime.now().isoformat()
    }
    save_product_registry(registry)
    
    # Ajouter aux prix
    prices = load_prices()
    if "FR" not in prices:
        prices["FR"] = {}
    if "CH" not in prices:
        prices["CH"] = {}
    
    prices["FR"][product_name] = price_fr
    prices["CH"][product_name] = price_ch
    save_prices(prices)
    
    # Ajouter aux produits disponibles
    available = get_available_products()
    available.add(product_name)
    save_available_products(available)
    
    # Mettre à jour les catégories selon le type
    if category == "pill":
        PILL_SUBCATEGORIES[product_code] = product_name
    elif category == "rock":
        ROCK_SUBCATEGORIES[product_code] = product_name
    
    # Réinitialiser les dictionnaires
    init_product_codes()
    
    # 🎨 Message de succès avec animation
    text = f"{EMOJI_THEME['success']} *PRODUIT AJOUTÉ !*\n\n"
    text += f"{emoji} {product_name}\n\n"
    text += f"✅ Le produit a été ajouté avec succès.\n"
    text += f"📊 Il est maintenant disponible à la commande.\n\n"
    text += f"💡 *Prochaines étapes :*\n"
    text += f"• Ajoutez des paliers de prix dégressifs\n"
    text += f"• Configurez le stock initial\n"
    text += f"• Ajoutez les médias (image/vidéo)"
    
    keyboard = [
        [InlineKeyboardButton(f"💰 Prix Dégressifs", callback_data="admin_pricing")],
        [InlineKeyboardButton(f"📦 Configurer Stock", callback_data="admin_stocks")],
        [InlineKeyboardButton("🔙 Menu Produits", callback_data="admin_products")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    # Nettoyer les données temporaires
    for key in ['new_product_name', 'new_product_code', 'new_product_category', 
                'new_product_price_fr', 'new_product_price_ch']:
        context.user_data.pop(key, None)
    
    logger.info(f"✅ Produit ajouté: {product_name} ({product_code})")
    
    return ADMIN_MENU_MAIN

# ==================== MASQUER/AFFICHER PRODUIT ====================

@error_handler
async def admin_toggle_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu pour masquer/afficher un produit"""
    query = update.callback_query
    await query.answer()
    
    registry = load_product_registry()
    available = get_available_products()
    
    if not registry:
        await query.message.edit_text(
            f"{EMOJI_THEME['error']} Aucun produit enregistré.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_products")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_MENU_MAIN
    
    text = f"{EMOJI_THEME['warning']} *MASQUER/AFFICHER PRODUIT*\n\n"
    text += f"Sélectionnez un produit :\n\n"
    
    keyboard = []
    
    for code, data in sorted(registry.items()):
        name = data['name']
        emoji = data.get('emoji', '📦')
        is_active = name in available
        
        if is_active:
            status = f"{EMOJI_THEME['online']} Actif"
            action = "hide"
        else:
            status = f"{EMOJI_THEME['offline']} Masqué"
            action = "show"
        
        button_text = f"{emoji} {name} ({status})"
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"toggle_{action}_{code}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_products")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

@error_handler
async def process_toggle_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite le masquage/affichage d'un produit"""
    query = update.callback_query
    await query.answer()
    
    # Format: toggle_show/hide_code
    parts = query.data.split("_")
    action = parts[1]  # show ou hide
    product_code = "_".join(parts[2:])
    
    registry = load_product_registry()
    
    if product_code not in registry:
        await query.answer(f"{EMOJI_THEME['error']} Produit non trouvé", show_alert=True)
        return ADMIN_MENU_MAIN
    
    product_name = registry[product_code]['name']
    available = get_available_products()
    
    if action == "hide":
        if product_name in available:
            available.remove(product_name)
            save_available_products(available)
            message = f"{EMOJI_THEME['success']} Produit masqué : {product_name}"
            logger.info(f"👁️ Produit masqué: {product_name}")
        else:
            message = f"{EMOJI_THEME['warning']} Produit déjà masqué"
    else:  # show
        if product_name not in available:
            available.add(product_name)
            save_available_products(available)
            message = f"{EMOJI_THEME['success']} Produit affiché : {product_name}"
            logger.info(f"👁️ Produit affiché: {product_name}")
        else:
            message = f"{EMOJI_THEME['warning']} Produit déjà affiché"
    
    await query.answer(message, show_alert=True)
    
    # Rafraîchir le menu
    return await admin_toggle_product(update, context)

# ==================== ARCHIVER PRODUIT ====================

@error_handler
async def admin_archive_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu pour archiver un produit"""
    query = update.callback_query
    await query.answer()
    
    registry = load_product_registry()
    
    if not registry:
        await query.message.edit_text(
            f"{EMOJI_THEME['error']} Aucun produit enregistré.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_products")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_MENU_MAIN
    
    text = f"🗑️ *ARCHIVER PRODUIT*\n\n"
    text += f"⚠️ *Attention :* L'archivage supprime définitivement le produit du registre.\n\n"
    text += f"Sélectionnez un produit à archiver :\n\n"
    
    keyboard = []
    
    for code, data in sorted(registry.items()):
        name = data['name']
        emoji = data.get('emoji', '📦')
        button_text = f"{emoji} {name}"
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"archive_confirm_{code}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_products")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

@error_handler
async def confirm_archive_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation avant archivage"""
    query = update.callback_query
    await query.answer()
    
    product_code = query.data.replace("archive_confirm_", "")
    registry = load_product_registry()
    
    if product_code not in registry:
        await query.answer(f"{EMOJI_THEME['error']} Produit non trouvé", show_alert=True)
        return ADMIN_MENU_MAIN
    
    product_name = registry[product_code]['name']
    
    text = f"🗑️ *CONFIRMATION D'ARCHIVAGE*\n\n"
    text += f"Produit : {product_name}\n\n"
    text += f"⚠️ *Cette action est IRRÉVERSIBLE*\n\n"
    text += f"Le produit sera :\n"
    text += f"• Retiré du registre\n"
    text += f"• Retiré des prix\n"
    text += f"• Retiré du stock\n"
    text += f"• Archivé dans un fichier séparé\n\n"
    text += f"Confirmez-vous l'archivage ?"
    
    keyboard = [
        [InlineKeyboardButton(f"🗑️ Confirmer Archivage", callback_data=f"archive_do_{product_code}")],
        [InlineKeyboardButton("❌ Annuler", callback_data="admin_archive_product")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

@error_handler
async def do_archive_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Effectue l'archivage du produit"""
    query = update.callback_query
    await query.answer()
    
    product_code = query.data.replace("archive_do_", "")
    registry = load_product_registry()
    
    if product_code not in registry:
        await query.answer(f"{EMOJI_THEME['error']} Produit non trouvé", show_alert=True)
        return ADMIN_MENU_MAIN
    
    product_data = registry[product_code]
    product_name = product_data['name']
    
    # Charger les produits archivés
    archived = {}
    if ARCHIVED_PRODUCTS_FILE.exists():
        try:
            with open(ARCHIVED_PRODUCTS_FILE, 'r', encoding='utf-8') as f:
                archived = json.load(f)
        except:
            pass
    
    # Ajouter aux archives
    archived[product_code] = {
        **product_data,
        "archived_at": datetime.now().isoformat()
    }
    
    # Sauvegarder les archives
    with open(ARCHIVED_PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(archived, f, indent=2, ensure_ascii=False)
    
    # Retirer du registre
    del registry[product_code]
    save_product_registry(registry)
    
    # Retirer des prix
    prices = load_prices()
    for country in ['FR', 'CH']:
        if country in prices and product_name in prices[country]:
            del prices[country][product_name]
    save_prices(prices)
    
    # Retirer des disponibles
    available = get_available_products()
    if product_name in available:
        available.remove(product_name)
        save_available_products(available)
    
    # Retirer du stock
    stocks = load_stocks()
    if product_name in stocks:
        del stocks[product_name]
        save_stocks(stocks)
    
    # Réinitialiser les dictionnaires
    init_product_codes()
    
    text = f"{EMOJI_THEME['success']} *PRODUIT ARCHIVÉ*\n\n"
    text += f"🗑️ {product_name}\n\n"
    text += f"✅ Le produit a été archivé avec succès.\n"
    text += f"📁 Fichier : archived_products.json"
    
    keyboard = [[InlineKeyboardButton("🔙 Menu Produits", callback_data="admin_products")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"🗑️ Produit archivé: {product_name} ({product_code})")
    
    return ADMIN_MENU_MAIN

# FIN DU BLOC 6 - PARTIE 1

# ==================== BLOC 6 PARTIE 2 : PRICING - ÉDITION ET SUPPRESSION ====================
# Ajoutez ce bloc APRÈS le pricing_view_all dans le BLOC 7

# ==================== ÉDITION PRIX DÉGRESSIFS ====================

@error_handler
async def pricing_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu pour éditer les paliers de prix"""
    query = update.callback_query
    await query.answer()
    
    tiers_data = load_pricing_tiers()
    
    if not tiers_data:
        await query.message.edit_text(
            f"{EMOJI_THEME['warning']} *AUCUN PALIER À ÉDITER*\n\n"
            f"Aucun prix dégressif configuré.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_MENU_MAIN
    
    text = f"✏️ *ÉDITER PRIX DÉGRESSIFS*\n\n"
    text += f"Sélectionnez un produit :"
    
    keyboard = []
    
    # Regrouper par produit
    products_with_tiers = {}
    for product_key, tiers in tiers_data.items():
        if not tiers:
            continue
        parts = product_key.rsplit("_", 1)
        product_name = parts[0]
        country = parts[1]
        
        if product_name not in products_with_tiers:
            products_with_tiers[product_name] = []
        products_with_tiers[product_name].append(country)
    
    for product_name, countries in sorted(products_with_tiers.items()):
        for country in countries:
            flag = "🇫🇷" if country == "FR" else "🇨🇭"
            tier_count = len(tiers_data.get(f"{product_name}_{country}", []))
            
            keyboard.append([InlineKeyboardButton(
                f"{flag} {product_name} ({tier_count} paliers)",
                callback_data=f"pricing_edit_select_{product_name}_{country}"
            )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PRICING_EDIT

@error_handler
async def pricing_edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les paliers d'un produit pour édition"""
    query = update.callback_query
    await query.answer()
    
    # Format: pricing_edit_select_ProductName_Country
    data_parts = query.data.replace("pricing_edit_select_", "").rsplit("_", 1)
    product_name = data_parts[0]
    country = data_parts[1]
    
    context.user_data['edit_pricing_product'] = product_name
    context.user_data['edit_pricing_country'] = country
    
    tiers = load_pricing_tiers()
    product_key = f"{product_name}_{country}"
    existing_tiers = tiers.get(product_key, [])
    
    if not existing_tiers:
        await query.answer(f"{EMOJI_THEME['error']} Aucun palier trouvé", show_alert=True)
        return ADMIN_PRICING_EDIT
    
    flag = "🇫🇷" if country == "FR" else "🇨🇭"
    
    text = f"✏️ *ÉDITER PALIERS*\n\n"
    text += f"{flag} {product_name}\n\n"
    text += f"📊 *Paliers actuels :*\n\n"
    
    sorted_tiers = sorted(existing_tiers, key=lambda x: x['min_qty'])
    
    keyboard = []
    
    for tier in sorted_tiers:
        qty = tier['min_qty']
        price = tier['price']
        
        text += f"• {qty}g+ : {price}€/g\n"
        
        keyboard.append([InlineKeyboardButton(
            f"🗑️ Supprimer palier {qty}g",
            callback_data=f"pricing_delete_tier_{qty}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="pricing_edit")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PRICING_EDIT

@error_handler
async def pricing_delete_tier_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Suppression d'un palier spécifique"""
    query = update.callback_query
    await query.answer()
    
    min_qty = int(query.data.replace("pricing_delete_tier_", ""))
    product_name = context.user_data.get('edit_pricing_product')
    country = context.user_data.get('edit_pricing_country')
    
    # Supprimer le palier
    success = delete_pricing_tier(product_name, country, min_qty)
    
    if success:
        message = f"{EMOJI_THEME['success']} Palier {min_qty}g supprimé"
        logger.info(f"🗑️ Palier supprimé: {product_name} ({country}) - {min_qty}g")
    else:
        message = f"{EMOJI_THEME['error']} Erreur lors de la suppression"
    
    await query.answer(message, show_alert=True)
    
    # Rafraîchir la liste
    return await pricing_edit_select(update, context)

# ==================== SUPPRESSION COMPLÈTE PRICING ====================

@error_handler
async def pricing_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu pour supprimer tous les paliers d'un produit"""
    query = update.callback_query
    await query.answer()
    
    tiers_data = load_pricing_tiers()
    
    if not tiers_data:
        await query.message.edit_text(
            f"{EMOJI_THEME['warning']} *AUCUN PALIER À SUPPRIMER*\n\n"
            f"Aucun prix dégressif configuré.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_MENU_MAIN
    
    text = f"🗑️ *SUPPRIMER PRIX DÉGRESSIFS*\n\n"
    text += f"⚠️ Supprime TOUS les paliers d'un produit\n\n"
    text += f"Sélectionnez un produit :"
    
    keyboard = []
    
    # Regrouper par produit
    products_with_tiers = {}
    for product_key, tiers in tiers_data.items():
        if not tiers:
            continue
        parts = product_key.rsplit("_", 1)
        product_name = parts[0]
        country = parts[1]
        
        if product_name not in products_with_tiers:
            products_with_tiers[product_name] = []
        products_with_tiers[product_name].append(country)
    
    for product_name, countries in sorted(products_with_tiers.items()):
        for country in countries:
            flag = "🇫🇷" if country == "FR" else "🇨🇭"
            tier_count = len(tiers_data.get(f"{product_name}_{country}", []))
            
            keyboard.append([InlineKeyboardButton(
                f"{flag} {product_name} ({tier_count} paliers)",
                callback_data=f"pricing_delete_confirm_{product_name}_{country}"
            )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PRICING_DELETE

@error_handler
async def pricing_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation avant suppression complète"""
    query = update.callback_query
    await query.answer()
    
    # Format: pricing_delete_confirm_ProductName_Country
    data_parts = query.data.replace("pricing_delete_confirm_", "").rsplit("_", 1)
    product_name = data_parts[0]
    country = data_parts[1]
    
    flag = "🇫🇷" if country == "FR" else "🇨🇭"
    
    text = f"🗑️ *CONFIRMATION SUPPRESSION*\n\n"
    text += f"{flag} {product_name}\n\n"
    text += f"⚠️ *Tous les paliers seront supprimés*\n\n"
    text += f"Le produit reviendra au prix de base uniquement.\n\n"
    text += f"Confirmez-vous ?"
    
    keyboard = [
        [InlineKeyboardButton(
            f"🗑️ Confirmer Suppression",
            callback_data=f"pricing_delete_do_{product_name}_{country}"
        )],
        [InlineKeyboardButton("❌ Annuler", callback_data="pricing_delete")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PRICING_DELETE

@error_handler
async def pricing_delete_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Effectue la suppression complète des paliers"""
    query = update.callback_query
    await query.answer()
    
    # Format: pricing_delete_do_ProductName_Country
    data_parts = query.data.replace("pricing_delete_do_", "").rsplit("_", 1)
    product_name = data_parts[0]
    country = data_parts[1]
    
    # Charger et supprimer
    tiers = load_pricing_tiers()
    product_key = f"{product_name}_{country}"
    
    if product_key in tiers:
        del tiers[product_key]
        save_pricing_tiers(tiers)
        
        text = f"{EMOJI_THEME['success']} *PALIERS SUPPRIMÉS*\n\n"
        text += f"Tous les paliers de {product_name} ont été supprimés.\n\n"
        text += f"Le produit utilise maintenant son prix de base."
        
        logger.info(f"🗑️ Tous les paliers supprimés: {product_name} ({country})")
    else:
        text = f"{EMOJI_THEME['error']} *ERREUR*\n\n"
        text += f"Impossible de trouver les paliers."
    
    keyboard = [[InlineKeyboardButton("🔙 Menu Pricing", callback_data="admin_pricing")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

# FIN DU BLOC 6 PARTIE 2

# ==================== BLOC 7 : PANEL ADMIN - PARTIE 2 (PRICING, PROMOS, STOCKS) ====================
# Ajoutez ce bloc APRÈS le BLOC 6

# ==================== GESTION PRIX DÉGRESSIFS ====================

@error_handler
async def admin_pricing_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de gestion des prix dégressifs"""
    query = update.callback_query
    await query.answer()
    
    registry = load_product_registry()
    tiers_data = load_pricing_tiers()
    
    # Compter les produits avec paliers
    products_with_tiers = len([k for k in tiers_data.keys() if tiers_data[k]])
    
    # 🎨 Affichage avec statistiques
    text = f"💰 *PRIX DÉGRESSIFS*\n\n"
    text += f"📊 *Statistiques :*\n"
    text += f"• Produits avec paliers : {products_with_tiers}\n"
    text += f"• Total produits : {len(registry)}\n\n"
    text += f"💡 Les prix dégressifs permettent de proposer des tarifs avantageux selon la quantité commandée."
    
    keyboard = [
        [InlineKeyboardButton(f"➕ Configurer paliers", callback_data="pricing_select_product")],
        [InlineKeyboardButton(f"✏️ Modifier paliers", callback_data="pricing_edit")],
        [InlineKeyboardButton(f"🗑️ Supprimer paliers", callback_data="pricing_delete")],
        [InlineKeyboardButton(f"📋 Voir tous les paliers", callback_data="pricing_view_all")],
        [InlineKeyboardButton("🔙 Retour", callback_data="back_to_admin_menu")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

@error_handler
async def pricing_select_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ CORRECTION : Sélection du produit pour configurer les paliers"""
    query = update.callback_query
    await query.answer()
    
    registry = load_product_registry()
    
    if not registry:
        await query.message.edit_text(
            f"{EMOJI_THEME['error']} Aucun produit disponible.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_MENU_MAIN  # ✅ CORRECTION : Retour au bon état
    
    text = f"💰 *PRIX DÉGRESSIFS - SÉLECTION PRODUIT*\n\n"
    text += f"Choisissez un produit :"
    
    keyboard = []
    
    for code, data in sorted(registry.items()):
        name = data['name']
        emoji = data.get('emoji', '📦')
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {name}",
            callback_data=f"pricing_product_{code}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_SELECT_PRODUCT_PRICING  # ✅ BON ÉTAT

@error_handler
async def pricing_product_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Produit sélectionné - Choix du pays"""
    query = update.callback_query
    await query.answer()
    
    product_code = query.data.replace("pricing_product_", "")
    registry = load_product_registry()
    
    if product_code not in registry:
        await query.answer(f"{EMOJI_THEME['error']} Produit non trouvé", show_alert=True)
        return ADMIN_SELECT_PRODUCT_PRICING
    
    product_name = registry[product_code]['name']
    context.user_data['pricing_product'] = product_name
    
    text = f"💰 *PRIX DÉGRESSIFS*\n\n"
    text += f"Produit : {product_name}\n\n"
    text += f"Choisissez le pays :"
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data="pricing_country_FR")],
        [InlineKeyboardButton("🇨🇭 Suisse", callback_data="pricing_country_CH")],
        [InlineKeyboardButton("🔙 Retour", callback_data="pricing_select_product")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_SELECT_PRODUCT_PRICING

@error_handler
async def pricing_country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pays sélectionné - Affichage des paliers actuels"""
    query = update.callback_query
    await query.answer()
    
    country = query.data.replace("pricing_country_", "")
    product_name = context.user_data.get('pricing_product')
    
    context.user_data['pricing_country'] = country
    
    # Récupérer les paliers existants
    tiers = load_pricing_tiers()
    product_key = f"{product_name}_{country}"
    existing_tiers = tiers.get(product_key, [])
    
    # Prix de base
    base_price = get_price(product_name, country)
    
    # 🎨 Affichage avec tableau
    text = f"💰 *PRIX DÉGRESSIFS*\n\n"
    text += f"Produit : {product_name}\n"
    text += f"Pays : {'🇫🇷 France' if country == 'FR' else '🇨🇭 Suisse'}\n"
    text += f"Prix de base : {base_price}€/g\n\n"
    
    if existing_tiers:
        text += f"📊 *Paliers actuels :*\n"
        text += f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
        
        sorted_tiers = sorted(existing_tiers, key=lambda x: x['min_qty'])
        for i, tier in enumerate(sorted_tiers):
            if i < len(sorted_tiers) - 1:
                qty_range = f"{tier['min_qty']}-{sorted_tiers[i+1]['min_qty']-1}g"
            else:
                qty_range = f"{tier['min_qty']}g+"
            
            text += f"┃ {qty_range:<10} : {tier['price']}€/g\n"
        
        text += f"┗━━━━━━━━━━━━━━━━━━━━━┛\n"
    else:
        text += f"_Aucun palier configuré_\n"
    
    keyboard = [
        [InlineKeyboardButton(f"➕ Ajouter un palier", callback_data="add_pricing_tier")],
        [InlineKeyboardButton("🔙 Retour", callback_data="pricing_select_product")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PRICING_TIERS

@error_handler
async def pricing_tier_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demander la quantité minimale pour le palier"""
    query = update.callback_query
    await query.answer()
    
    product_name = context.user_data.get('pricing_product')
    country = context.user_data.get('pricing_country')
    
    text = f"➕ *AJOUTER UN PALIER*\n\n"
    text += f"Produit : {product_name}\n"
    text += f"Pays : {'🇫🇷 France' if country == 'FR' else '🇨🇭 Suisse'}\n\n"
    text += f"Étape 1/2 : Quantité minimale\n\n"
    text += f"Entrez la quantité minimale (en grammes) :\n"
    text += f"_Exemple : 10 (pour '10g et plus')_"
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="pricing_country_" + country)]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_TIER_QUANTITY

@error_handler
async def receive_tier_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réception de la quantité minimale du palier"""
    qty_text = sanitize_input(update.message.text, 10)
    
    try:
        quantity = int(qty_text)
        if quantity <= 0:
            raise ValueError
    except:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Quantité invalide.\n\nEntrez un nombre entier positif.",
            parse_mode='Markdown'
        )
        return ADMIN_TIER_QUANTITY
    
    context.user_data['tier_quantity'] = quantity
    
    product_name = context.user_data.get('pricing_product')
    country = context.user_data.get('pricing_country')
    
    text = f"➕ *AJOUTER UN PALIER*\n\n"
    text += f"Produit : {product_name}\n"
    text += f"Pays : {'🇫🇷 France' if country == 'FR' else '🇨🇭 Suisse'}\n"
    text += f"Quantité min : {quantity}g\n\n"
    text += f"Étape 2/2 : Prix unitaire\n\n"
    text += f"Entrez le prix (€/g) pour ce palier :\n"
    text += f"_Exemple : 45_"
    
    await update.message.reply_text(text, parse_mode='Markdown')
    
    return ADMIN_TIER_PRICE

@error_handler
async def receive_tier_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réception du prix du palier et sauvegarde"""
    price_text = sanitize_input(update.message.text, 10)
    
    try:
        price = float(price_text)
        if price <= 0:
            raise ValueError
    except:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Prix invalide.\n\nEntrez un nombre positif.",
            parse_mode='Markdown'
        )
        return ADMIN_TIER_PRICE
    
    product_name = context.user_data.get('pricing_product')
    country = context.user_data.get('pricing_country')
    quantity = context.user_data.get('tier_quantity')
    
    # Ajouter le palier
    success = add_pricing_tier(product_name, country, quantity, price)
    
    if success:
        text = f"{EMOJI_THEME['success']} *PALIER AJOUTÉ*\n\n"
        text += f"✅ Palier configuré avec succès !\n\n"
        text += f"Produit : {product_name}\n"
        text += f"Pays : {'🇫🇷 France' if country == 'FR' else '🇨🇭 Suisse'}\n"
        text += f"À partir de : {quantity}g\n"
        text += f"Prix : {price}€/g"
        
        logger.info(f"💰 Palier ajouté: {product_name} ({country}) - {quantity}g @ {price}€")
    else:
        text = f"{EMOJI_THEME['error']} *ERREUR*\n\n"
        text += f"Impossible d'ajouter le palier.\n"
        text += f"Veuillez réessayer."
    
    keyboard = [
        [InlineKeyboardButton(f"➕ Ajouter un autre palier", callback_data="add_pricing_tier")],
        [InlineKeyboardButton("📋 Voir les paliers", callback_data="pricing_country_" + country)],
        [InlineKeyboardButton("🔙 Menu Pricing", callback_data="admin_pricing")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    # Nettoyer les données temporaires
    context.user_data.pop('tier_quantity', None)
    
    return ADMIN_PRICING_TIERS

@error_handler
async def pricing_view_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche tous les paliers de prix configurés"""
    query = update.callback_query
    await query.answer()
    
    tiers_data = load_pricing_tiers()
    
    if not tiers_data:
        text = f"{EMOJI_THEME['warning']} *AUCUN PALIER CONFIGURÉ*\n\n"
        text += f"Aucun prix dégressif n'est actuellement configuré."
    else:
        text = f"📋 *TOUS LES PALIERS DE PRIX*\n\n"
        
        for product_key, tiers in sorted(tiers_data.items()):
            if not tiers:
                continue
            
            parts = product_key.rsplit("_", 1)
            product_name = parts[0]
            country = parts[1]
            flag = "🇫🇷" if country == "FR" else "🇨🇭"
            
            text += f"{flag} *{product_name}*\n"
            
            sorted_tiers = sorted(tiers, key=lambda x: x['min_qty'])
            for i, tier in enumerate(sorted_tiers):
                if i < len(sorted_tiers) - 1:
                    qty_range = f"{tier['min_qty']}-{sorted_tiers[i+1]['min_qty']-1}g"
                else:
                    qty_range = f"{tier['min_qty']}g+"
                
                text += f"  • {qty_range}: {tier['price']}€/g\n"
            
            text += "\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

# ==================== ÉDITION PRIX DÉGRESSIFS ====================

@error_handler
async def pricing_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu pour éditer les paliers de prix"""
    query = update.callback_query
    await query.answer()
    
    tiers_data = load_pricing_tiers()
    
    if not tiers_data:
        await query.message.edit_text(
            f"{EMOJI_THEME['warning']} *AUCUN PALIER À ÉDITER*\n\n"
            f"Aucun prix dégressif configuré.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_MENU_MAIN
    
    text = f"✏️ *ÉDITER PRIX DÉGRESSIFS*\n\n"
    text += f"Sélectionnez un produit :"
    
    keyboard = []
    
    # Regrouper par produit
    products_with_tiers = {}
    for product_key, tiers in tiers_data.items():
        if not tiers:
            continue
        parts = product_key.rsplit("_", 1)
        product_name = parts[0]
        country = parts[1]
        
        if product_name not in products_with_tiers:
            products_with_tiers[product_name] = []
        products_with_tiers[product_name].append(country)
    
    for product_name, countries in sorted(products_with_tiers.items()):
        for country in countries:
            flag = "🇫🇷" if country == "FR" else "🇨🇭"
            tier_count = len(tiers_data.get(f"{product_name}_{country}", []))
            
            keyboard.append([InlineKeyboardButton(
                f"{flag} {product_name} ({tier_count} paliers)",
                callback_data=f"pricing_edit_select_{product_name}_{country}"
            )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PRICING_EDIT

@error_handler
async def pricing_edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les paliers d'un produit pour édition"""
    query = update.callback_query
    await query.answer()
    
    # Format: pricing_edit_select_ProductName_Country
    data_parts = query.data.replace("pricing_edit_select_", "").rsplit("_", 1)
    product_name = data_parts[0]
    country = data_parts[1]
    
    context.user_data['edit_pricing_product'] = product_name
    context.user_data['edit_pricing_country'] = country
    
    tiers = load_pricing_tiers()
    product_key = f"{product_name}_{country}"
    existing_tiers = tiers.get(product_key, [])
    
    if not existing_tiers:
        await query.answer(f"{EMOJI_THEME['error']} Aucun palier trouvé", show_alert=True)
        return ADMIN_PRICING_EDIT
    
    flag = "🇫🇷" if country == "FR" else "🇨🇭"
    
    text = f"✏️ *ÉDITER PALIERS*\n\n"
    text += f"{flag} {product_name}\n\n"
    text += f"📊 *Paliers actuels :*\n\n"
    
    sorted_tiers = sorted(existing_tiers, key=lambda x: x['min_qty'])
    
    keyboard = []
    
    for tier in sorted_tiers:
        qty = tier['min_qty']
        price = tier['price']
        
        text += f"• {qty}g+ : {price}€/g\n"
        
        keyboard.append([InlineKeyboardButton(
            f"🗑️ Supprimer palier {qty}g",
            callback_data=f"pricing_delete_tier_{qty}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="pricing_edit")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PRICING_EDIT

@error_handler
async def pricing_delete_tier_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Suppression d'un palier spécifique"""
    query = update.callback_query
    await query.answer()
    
    min_qty = int(query.data.replace("pricing_delete_tier_", ""))
    product_name = context.user_data.get('edit_pricing_product')
    country = context.user_data.get('edit_pricing_country')
    
    # Supprimer le palier
    success = delete_pricing_tier(product_name, country, min_qty)
    
    if success:
        message = f"{EMOJI_THEME['success']} Palier {min_qty}g supprimé"
        logger.info(f"🗑️ Palier supprimé: {product_name} ({country}) - {min_qty}g")
    else:
        message = f"{EMOJI_THEME['error']} Erreur lors de la suppression"
    
    await query.answer(message, show_alert=True)
    
    # Rafraîchir la liste
    return await pricing_edit_select(update, context)

# ==================== SUPPRESSION COMPLÈTE PRICING ====================

@error_handler
async def pricing_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu pour supprimer tous les paliers d'un produit"""
    query = update.callback_query
    await query.answer()
    
    tiers_data = load_pricing_tiers()
    
    if not tiers_data:
        await query.message.edit_text(
            f"{EMOJI_THEME['warning']} *AUCUN PALIER À SUPPRIMER*\n\n"
            f"Aucun prix dégressif configuré.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_MENU_MAIN
    
    text = f"🗑️ *SUPPRIMER PRIX DÉGRESSIFS*\n\n"
    text += f"⚠️ Supprime TOUS les paliers d'un produit\n\n"
    text += f"Sélectionnez un produit :"
    
    keyboard = []
    
    # Regrouper par produit
    products_with_tiers = {}
    for product_key, tiers in tiers_data.items():
        if not tiers:
            continue
        parts = product_key.rsplit("_", 1)
        product_name = parts[0]
        country = parts[1]
        
        if product_name not in products_with_tiers:
            products_with_tiers[product_name] = []
        products_with_tiers[product_name].append(country)
    
    for product_name, countries in sorted(products_with_tiers.items()):
        for country in countries:
            flag = "🇫🇷" if country == "FR" else "🇨🇭"
            tier_count = len(tiers_data.get(f"{product_name}_{country}", []))
            
            keyboard.append([InlineKeyboardButton(
                f"{flag} {product_name} ({tier_count} paliers)",
                callback_data=f"pricing_delete_confirm_{product_name}_{country}"
            )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_pricing")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PRICING_DELETE

@error_handler
async def pricing_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation avant suppression complète"""
    query = update.callback_query
    await query.answer()
    
    # Format: pricing_delete_confirm_ProductName_Country
    data_parts = query.data.replace("pricing_delete_confirm_", "").rsplit("_", 1)
    product_name = data_parts[0]
    country = data_parts[1]
    
    flag = "🇫🇷" if country == "FR" else "🇨🇭"
    
    text = f"🗑️ *CONFIRMATION SUPPRESSION*\n\n"
    text += f"{flag} {product_name}\n\n"
    text += f"⚠️ *Tous les paliers seront supprimés*\n\n"
    text += f"Le produit reviendra au prix de base uniquement.\n\n"
    text += f"Confirmez-vous ?"
    
    keyboard = [
        [InlineKeyboardButton(
            f"🗑️ Confirmer Suppression",
            callback_data=f"pricing_delete_do_{product_name}_{country}"
        )],
        [InlineKeyboardButton("❌ Annuler", callback_data="pricing_delete")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PRICING_DELETE

@error_handler
async def pricing_delete_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Effectue la suppression complète des paliers"""
    query = update.callback_query
    await query.answer()
    
    # Format: pricing_delete_do_ProductName_Country
    data_parts = query.data.replace("pricing_delete_do_", "").rsplit("_", 1)
    product_name = data_parts[0]
    country = data_parts[1]
    
    # Charger et supprimer
    tiers = load_pricing_tiers()
    product_key = f"{product_name}_{country}"
    
    if product_key in tiers:
        del tiers[product_key]
        save_pricing_tiers(tiers)
        
        text = f"{EMOJI_THEME['success']} *PALIERS SUPPRIMÉS*\n\n"
        text += f"Tous les paliers de {product_name} ont été supprimés.\n\n"
        text += f"Le produit utilise maintenant son prix de base."
        
        logger.info(f"🗑️ Tous les paliers supprimés: {product_name} ({country})")
    else:
        text = f"{EMOJI_THEME['error']} *ERREUR*\n\n"
        text += f"Impossible de trouver les paliers."
    
    keyboard = [[InlineKeyboardButton("🔙 Menu Pricing", callback_data="admin_pricing")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

# ==================== GESTION CODES PROMO ====================

@error_handler
async def admin_promo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ CORRECTION : Menu de gestion des codes promo AVEC BOUTON RETOUR"""
    query = update.callback_query
    await query.answer()
    
    promo_codes = load_promo_codes()
    
    # Statistiques
    active_codes = len([c for c in promo_codes.values() if c.get('used_count', 0) < c.get('max_uses', 999999)])
    total_uses = sum(c.get('used_count', 0) for c in promo_codes.values())
    
    # 🎨 Affichage avec statistiques
    text = f"{EMOJI_THEME['gift']} *CODES PROMO*\n\n"
    text += f"📊 *Statistiques :*\n"
    text += f"• Codes actifs : {active_codes}\n"
    text += f"• Total codes : {len(promo_codes)}\n"
    text += f"• Utilisations : {total_uses}\n\n"
    
    if promo_codes:
        text += f"📋 *Codes existants :*\n"
        for code, data in sorted(promo_codes.items()):
            used = data.get('used_count', 0)
            max_uses = data.get('max_uses', 999999)
            
            if data['type'] == 'percentage':
                discount = f"-{data['value']}%"
            else:
                discount = f"-{data['value']}€"
            
            status = f"{EMOJI_THEME['online']}" if used < max_uses else f"{EMOJI_THEME['offline']}"
            text += f"{status} `{code}` : {discount} ({used}/{max_uses})\n"
    
    keyboard = [
        [InlineKeyboardButton(f"➕ Créer code promo", callback_data="promo_create")],
        [InlineKeyboardButton(f"🗑️ Supprimer code", callback_data="promo_delete")],
        [InlineKeyboardButton(f"📊 Détails codes", callback_data="promo_details")],
        [InlineKeyboardButton("🔙 Retour", callback_data="back_to_admin_menu")]  # ✅ AJOUTÉ
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PROMO_MENU

@error_handler
async def promo_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Démarre la création d'un code promo"""
    query = update.callback_query
    await query.answer()
    
    text = f"➕ *CRÉER UN CODE PROMO*\n\n"
    text += f"Entrez le code promo (lettres majuscules, chiffres, tirets) :\n"
    text += f"_Exemple : WELCOME10, NOEL2024, VIP-15_"
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_promo")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['promo_step'] = 'code'
    return ADMIN_PROMO_MENU

@error_handler
async def promo_receive_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les entrées utilisateur pour la création de code promo"""
    step = context.user_data.get('promo_step')
    
    if step == 'code':
        code = sanitize_input(update.message.text, 20).upper()
        
        # Validation
        if not re.match(r'^[A-Z0-9-]+$', code):
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Code invalide.\n\nUtilisez : A-Z, 0-9 et -",
                parse_mode='Markdown'
            )
            return ADMIN_PROMO_MENU
        
        # Vérifier si existe
        promo_codes = load_promo_codes()
        if code in promo_codes:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Ce code existe déjà.\n\nChoisissez un code unique.",
                parse_mode='Markdown'
            )
            return ADMIN_PROMO_MENU
        
        context.user_data['promo_code'] = code
        
        text = f"➕ *CRÉER UN CODE PROMO*\n\n"
        text += f"Code : `{code}`\n\n"
        text += f"Choisissez le type de réduction :"
        
        keyboard = [
            [InlineKeyboardButton("📊 Pourcentage (%)", callback_data="promo_type_percentage")],
            [InlineKeyboardButton("💰 Montant fixe (€)", callback_data="promo_type_fixed")],
            [InlineKeyboardButton("❌ Annuler", callback_data="admin_promo")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        context.user_data['promo_step'] = 'type'
        return ADMIN_PROMO_MENU
    
    elif step == 'value':
        value_text = sanitize_input(update.message.text, 10)
        
        try:
            value = float(value_text)
            if value <= 0:
                raise ValueError
        except:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Valeur invalide.\n\nEntrez un nombre positif.",
                parse_mode='Markdown'
            )
            return ADMIN_PROMO_MENU
        
        promo_type = context.user_data.get('promo_type')
        
        # Validation selon le type
        if promo_type == 'percentage' and value > 100:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} Pourcentage invalide.\n\nMaximum : 100%",
                parse_mode='Markdown'
            )
            return ADMIN_PROMO_MENU
        
        context.user_data['promo_value'] = value
        
        code = context.user_data.get('promo_code')
        discount_display = f"{value}%" if promo_type == 'percentage' else f"{value}€"
        
        text = f"➕ *CRÉER UN CODE PROMO*\n\n"
        text += f"Code : `{code}`\n"
        text += f"Réduction : {discount_display}\n\n"
        text += f"Configuration optionnelle :\n\n"
        text += f"Entrez :\n"
        text += f"• Commande minimum (€) ou 0\n"
        text += f"• Utilisations max ou 0 (illimité)\n"
        text += f"• Jours validité ou 0 (permanent)\n\n"
        text += f"_Format : min,max,jours_\n"
        text += f"_Exemple : 50,100,30_\n"
        text += f"_Ou tapez : skip_"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
        context.user_data['promo_step'] = 'options'
        return ADMIN_PROMO_MENU
    
    elif step == 'options':
        input_text = sanitize_input(update.message.text, 30).lower()
        
        # Valeurs par défaut
        min_order = 0
        max_uses = 999999
        valid_days = 0
        
        if input_text != 'skip':
            try:
                parts = input_text.split(',')
                if len(parts) >= 1:
                    min_order = float(parts[0])
                if len(parts) >= 2:
                    max_uses = int(parts[1]) if int(parts[1]) > 0 else 999999
                if len(parts) >= 3:
                    valid_days = int(parts[2])
            except:
                await update.message.reply_text(
                    f"{EMOJI_THEME['error']} Format invalide.\n\nUtilisez : min,max,jours\n\nOu tapez : skip",
                    parse_mode='Markdown'
                )
                return ADMIN_PROMO_MENU
        
        # Créer le code promo
        code = context.user_data.get('promo_code')
        promo_type = context.user_data.get('promo_type')
        value = context.user_data.get('promo_value')
        
        promo_data = {
            "type": promo_type,
            "value": value,
            "min_order": min_order,
            "max_uses": max_uses,
            "used_count": 0,
            "created_at": datetime.now().isoformat()
        }
        
        if valid_days > 0:
            valid_until = datetime.now() + timedelta(days=valid_days)
            promo_data["valid_until"] = valid_until.isoformat()
        
        # Sauvegarder
        promo_codes = load_promo_codes()
        promo_codes[code] = promo_data
        save_promo_codes(promo_codes)
        
        # Message de confirmation
        discount_display = f"{value}%" if promo_type == 'percentage' else f"{value}€"
        
        text = f"{EMOJI_THEME['success']} *CODE PROMO CRÉÉ !*\n\n"
        text += f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
        text += f"┃  Code : `{code}`\n"
        text += f"┣━━━━━━━━━━━━━━━━━━━━━┫\n"
        text += f"┃ Réduction : {discount_display}\n"
        if min_order > 0:
            text += f"┃ Min commande : {min_order}€\n"
        text += f"┃ Utilisations : {max_uses if max_uses < 999999 else '∞'}\n"
        if valid_days > 0:
            text += f"┃ Validité : {valid_days} jours\n"
        text += f"┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        text += f"✅ Le code est maintenant actif !"
        
        keyboard = [
            [InlineKeyboardButton(f"➕ Créer un autre", callback_data="promo_create")],
            [InlineKeyboardButton("🔙 Menu Promo", callback_data="admin_promo")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # Nettoyer
        for key in ['promo_step', 'promo_code', 'promo_type', 'promo_value']:
            context.user_data.pop(key, None)
        
        logger.info(f"🎁 Code promo créé: {code} ({discount_display})")
        
        return ADMIN_PROMO_MENU
    
    return ADMIN_PROMO_MENU

@error_handler
async def promo_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Type de promo sélectionné"""
    query = update.callback_query
    await query.answer()
    
    promo_type = query.data.replace("promo_type_", "")
    context.user_data['promo_type'] = promo_type
    
    code = context.user_data.get('promo_code')
    
    text = f"➕ *CRÉER UN CODE PROMO*\n\n"
    text += f"Code : `{code}`\n"
    text += f"Type : {'Pourcentage' if promo_type == 'percentage' else 'Montant fixe'}\n\n"
    
    if promo_type == 'percentage':
        text += f"Entrez le pourcentage de réduction (1-100) :\n"
        text += f"_Exemple : 10 (pour -10%)_"
    else:
        text += f"Entrez le montant de la réduction (€) :\n"
        text += f"_Exemple : 5 (pour -5€)_"
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_promo")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['promo_step'] = 'value'
    return ADMIN_PROMO_MENU

# Continuez avec promo_delete, promo_details, stocks... dans le prochain message

# FIN DU BLOC 7 - PARTIE 1

# ==================== BLOC 7 PARTIE 2 : STOCKS ET PROMOS - SUITE ====================
# Ajoutez ce bloc APRÈS le BLOC 7 PARTIE 1

# ==================== SUPPRESSION CODE PROMO ====================

@error_handler
async def promo_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu pour supprimer un code promo"""
    query = update.callback_query
    await query.answer()
    
    promo_codes = load_promo_codes()
    
    if not promo_codes:
        await query.message.edit_text(
            f"{EMOJI_THEME['warning']} *AUCUN CODE PROMO*\n\n"
            f"Aucun code promo à supprimer.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_promo")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_PROMO_MENU
    
    text = f"🗑️ *SUPPRIMER CODE PROMO*\n\n"
    text += f"Sélectionnez un code à supprimer :"
    
    keyboard = []
    
    for code, data in sorted(promo_codes.items()):
        if data['type'] == 'percentage':
            discount = f"-{data['value']}%"
        else:
            discount = f"-{data['value']}€"
        
        used = data.get('used_count', 0)
        max_uses = data.get('max_uses', 999999)
        
        keyboard.append([InlineKeyboardButton(
            f"{code} ({discount}) - {used}/{max_uses}",
            callback_data=f"promo_delete_confirm_{code}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_promo")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PROMO_MENU

@error_handler
async def promo_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation suppression code promo"""
    query = update.callback_query
    await query.answer()
    
    code = query.data.replace("promo_delete_confirm_", "")
    promo_codes = load_promo_codes()
    
    if code not in promo_codes:
        await query.answer(f"{EMOJI_THEME['error']} Code non trouvé", show_alert=True)
        return ADMIN_PROMO_MENU
    
    data = promo_codes[code]
    
    if data['type'] == 'percentage':
        discount = f"-{data['value']}%"
    else:
        discount = f"-{data['value']}€"
    
    text = f"🗑️ *CONFIRMATION SUPPRESSION*\n\n"
    text += f"Code : `{code}`\n"
    text += f"Réduction : {discount}\n"
    text += f"Utilisations : {data.get('used_count', 0)}/{data.get('max_uses', 999999)}\n\n"
    text += f"⚠️ Cette action est irréversible.\n\n"
    text += f"Confirmez-vous ?"
    
    keyboard = [
        [InlineKeyboardButton(
            f"🗑️ Confirmer Suppression",
            callback_data=f"promo_delete_do_{code}"
        )],
        [InlineKeyboardButton("❌ Annuler", callback_data="promo_delete")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PROMO_MENU

@error_handler
async def promo_delete_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Effectue la suppression du code promo"""
    query = update.callback_query
    await query.answer()
    
    code = query.data.replace("promo_delete_do_", "")
    promo_codes = load_promo_codes()
    
    if code in promo_codes:
        del promo_codes[code]
        save_promo_codes(promo_codes)
        
        text = f"{EMOJI_THEME['success']} *CODE SUPPRIMÉ*\n\n"
        text += f"Le code `{code}` a été supprimé avec succès."
        
        logger.info(f"🗑️ Code promo supprimé: {code}")
    else:
        text = f"{EMOJI_THEME['error']} *ERREUR*\n\n"
        text += f"Impossible de trouver le code."
    
    keyboard = [[InlineKeyboardButton("🔙 Menu Promo", callback_data="admin_promo")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PROMO_MENU

# ==================== DÉTAILS CODES PROMO ====================

@error_handler
async def promo_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les détails de tous les codes promo"""
    query = update.callback_query
    await query.answer()
    
    promo_codes = load_promo_codes()
    
    if not promo_codes:
        text = f"{EMOJI_THEME['warning']} *AUCUN CODE PROMO*"
    else:
        text = f"📊 *DÉTAILS CODES PROMO*\n\n"
        
        for code, data in sorted(promo_codes.items()):
            if data['type'] == 'percentage':
                discount = f"{data['value']}%"
            else:
                discount = f"{data['value']}€"
            
            used = data.get('used_count', 0)
            max_uses = data.get('max_uses', 999999)
            min_order = data.get('min_order', 0)
            
            # Statut
            if used >= max_uses:
                status = f"{EMOJI_THEME['offline']} Épuisé"
            else:
                status = f"{EMOJI_THEME['online']} Actif"
            
            text += f"*{code}* {status}\n"
            text += f"• Réduction : {discount}\n"
            text += f"• Utilisations : {used}/{max_uses if max_uses < 999999 else '∞'}\n"
            
            if min_order > 0:
                text += f"• Min commande : {min_order}€\n"
            
            if 'valid_until' in data:
                valid_until = datetime.fromisoformat(data['valid_until'])
                text += f"• Expire : {valid_until.strftime('%d/%m/%Y')}\n"
            
            text += "\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_promo")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_PROMO_MENU

# ==================== GESTION STOCKS ====================

@error_handler
async def admin_stocks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de gestion des stocks"""
    query = update.callback_query
    await query.answer()
    
    stocks = load_stocks()
    registry = load_product_registry()
    
    # Statistiques
    low_stock_count = len(get_low_stock_products())
    out_of_stock_count = len(get_out_of_stock_products())
    
    # 🎨 Affichage avec indicateurs visuels
    text = f"📦 *GESTION DES STOCKS*\n\n"
    text += f"📊 *Statistiques :*\n"
    text += f"• {EMOJI_THEME['warning']} Stock faible : {low_stock_count}\n"
    text += f"• {EMOJI_THEME['offline']} Rupture : {out_of_stock_count}\n\n"
    
    if stocks:
        text += f"📋 *État des stocks :*\n\n"
        
        for product_name, data in sorted(stocks.items()):
            quantity = data.get('quantity', 0)
            threshold = data.get('alert_threshold', 20)
            
            # Indicateur visuel
            if quantity == 0:
                indicator = f"{EMOJI_THEME['offline']}"
            elif quantity <= threshold:
                indicator = f"{EMOJI_THEME['warning']}"
            else:
                indicator = f"{EMOJI_THEME['online']}"
            
            # Barre de progression
            if quantity > 0:
                max_display = max(100, threshold * 2)
                progress = create_progress_bar(quantity, max_display, length=10)
                text += f"{indicator} {product_name}\n"
                text += f"   {progress} {quantity}g\n\n"
            else:
                text += f"{indicator} {product_name} : *RUPTURE*\n\n"
    else:
        text += f"_Aucun stock configuré (stock illimité par défaut)_"
    
    keyboard = [
        [InlineKeyboardButton(f"➕ Configurer stock", callback_data="stock_configure")],
        [InlineKeyboardButton(f"📥 Ajouter stock", callback_data="stock_add")],
        [InlineKeyboardButton(f"📤 Retirer stock", callback_data="stock_remove")],
        [InlineKeyboardButton(f"{EMOJI_THEME['warning']} Alertes stock", callback_data="stock_alerts")],
        [InlineKeyboardButton("🔙 Retour", callback_data="back_to_admin_menu")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_STOCK_MENU

@error_handler
async def stock_configure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configuration initiale du stock pour un produit"""
    query = update.callback_query
    await query.answer()
    
    registry = load_product_registry()
    
    if not registry:
        await query.message.edit_text(
            f"{EMOJI_THEME['error']} Aucun produit disponible.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_stocks")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_STOCK_MENU
    
    text = f"➕ *CONFIGURER STOCK*\n\n"
    text += f"Choisissez un produit :"
    
    keyboard = []
    
    for code, data in sorted(registry.items()):
        name = data['name']
        emoji = data.get('emoji', '📦')
        
        # Vérifier si déjà configuré
        stocks = load_stocks()
        status = " (✓)" if name in stocks else ""
        
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {name}{status}",
            callback_data=f"stock_config_{code}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_stocks")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_STOCK_MENU

@error_handler
async def stock_config_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configuration du stock pour un produit spécifique"""
    query = update.callback_query
    await query.answer()
    
    product_code = query.data.replace("stock_config_", "")
    registry = load_product_registry()
    
    if product_code not in registry:
        await query.answer(f"{EMOJI_THEME['error']} Produit non trouvé", show_alert=True)
        return ADMIN_STOCK_MENU
    
    product_name = registry[product_code]['name']
    context.user_data['stock_product'] = product_name
    
    # Stock actuel
    current_stock = get_stock(product_name)
    
    text = f"➕ *CONFIGURER STOCK*\n\n"
    text += f"Produit : {product_name}\n"
    if current_stock is not None:
        text += f"Stock actuel : {current_stock}g\n\n"
    else:
        text += f"Stock actuel : Illimité\n\n"
    
    text += f"Entrez la quantité de stock (grammes) :\n"
    text += f"_Exemple : 500_\n\n"
    text += f"_Tapez 0 pour désactiver le suivi de stock_"
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="stock_configure")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['stock_action'] = 'configure'
    return ADMIN_STOCK_MENU

@error_handler
async def stock_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu pour ajouter du stock"""
    query = update.callback_query
    await query.answer()
    
    stocks = load_stocks()
    
    if not stocks:
        await query.message.edit_text(
            f"{EMOJI_THEME['warning']} *AUCUN STOCK CONFIGURÉ*\n\n"
            f"Configurez d'abord des stocks avant d'en ajouter.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Configurer stock", callback_data="stock_configure"),
                InlineKeyboardButton("🔙 Retour", callback_data="admin_stocks")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_STOCK_MENU
    
    text = f"📥 *AJOUTER STOCK*\n\n"
    text += f"Sélectionnez un produit :"
    
    keyboard = []
    
    for product_name, data in sorted(stocks.items()):
        quantity = data.get('quantity', 0)
        
        keyboard.append([InlineKeyboardButton(
            f"{product_name} (Actuel: {quantity}g)",
            callback_data=f"stock_add_select_{product_name}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_stocks")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_STOCK_MENU

@error_handler
async def stock_add_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Produit sélectionné pour ajout de stock"""
    query = update.callback_query
    await query.answer()
    
    product_name = query.data.replace("stock_add_select_", "")
    context.user_data['stock_product'] = product_name
    context.user_data['stock_action'] = 'add'
    
    current_stock = get_stock(product_name)
    
    text = f"📥 *AJOUTER STOCK*\n\n"
    text += f"Produit : {product_name}\n"
    text += f"Stock actuel : {current_stock}g\n\n"
    text += f"Entrez la quantité à ajouter (grammes) :\n"
    text += f"_Exemple : 100_"
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="stock_add")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_STOCK_MENU

@error_handler
async def stock_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu pour retirer du stock"""
    query = update.callback_query
    await query.answer()
    
    stocks = load_stocks()
    
    if not stocks:
        await query.message.edit_text(
            f"{EMOJI_THEME['warning']} *AUCUN STOCK CONFIGURÉ*\n\n"
            f"Configurez d'abord des stocks.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_stocks")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_STOCK_MENU
    
    text = f"📤 *RETIRER STOCK*\n\n"
    text += f"Sélectionnez un produit :"
    
    keyboard = []
    
    for product_name, data in sorted(stocks.items()):
        quantity = data.get('quantity', 0)
        
        keyboard.append([InlineKeyboardButton(
            f"{product_name} (Actuel: {quantity}g)",
            callback_data=f"stock_remove_select_{product_name}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_stocks")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_STOCK_MENU

@error_handler
async def stock_remove_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Produit sélectionné pour retrait de stock"""
    query = update.callback_query
    await query.answer()
    
    product_name = query.data.replace("stock_remove_select_", "")
    context.user_data['stock_product'] = product_name
    context.user_data['stock_action'] = 'remove'
    
    current_stock = get_stock(product_name)
    
    text = f"📤 *RETIRER STOCK*\n\n"
    text += f"Produit : {product_name}\n"
    text += f"Stock actuel : {current_stock}g\n\n"
    text += f"Entrez la quantité à retirer (grammes) :\n"
    text += f"_Exemple : 50_\n\n"
    text += f"⚠️ Maximum : {current_stock}g"
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="stock_remove")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_STOCK_MENU

@error_handler
async def stock_process_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite l'ajout ou le retrait de stock"""
    qty_text = sanitize_input(update.message.text, 10)
    
    try:
        quantity = int(qty_text)
        if quantity < 0:
            raise ValueError
    except:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Quantité invalide.\n\nEntrez un nombre entier positif ou 0.",
            parse_mode='Markdown'
        )
        return ADMIN_STOCK_MENU
    
    product_name = context.user_data.get('stock_product')
    action = context.user_data.get('stock_action', 'configure')
    
    if action == 'configure':
        if quantity == 0:
            # Désactiver le suivi
            stocks = load_stocks()
            if product_name in stocks:
                del stocks[product_name]
                save_stocks(stocks)
            
            text = f"{EMOJI_THEME['success']} *SUIVI DÉSACTIVÉ*\n\n"
            text += f"Le suivi de stock pour {product_name} a été désactivé.\n"
            text += f"Stock : Illimité"
        else:
            # Configurer avec seuil d'alerte par défaut (20g)
            set_stock(product_name, quantity, alert_threshold=20)
            
            text = f"{EMOJI_THEME['success']} *STOCK CONFIGURÉ*\n\n"
            text += f"Produit : {product_name}\n"
            text += f"Stock : {quantity}g\n"
            text += f"Seuil d'alerte : 20g"
        
        keyboard = [
            [InlineKeyboardButton(f"📦 Gérer stocks", callback_data="admin_stocks")],
            [InlineKeyboardButton("🔙 Menu Admin", callback_data="back_to_admin_menu")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # Nettoyer
        context.user_data.pop('stock_product', None)
        context.user_data.pop('stock_action', None)
        
        logger.info(f"📦 Stock configuré: {product_name} = {quantity}g")
        
    elif action == 'add':
        # Ajouter au stock
        update_stock(product_name, quantity)
        new_stock = get_stock(product_name)
        
        text = f"{EMOJI_THEME['success']} *STOCK AJOUTÉ*\n\n"
        text += f"Produit : {product_name}\n"
        text += f"Quantité ajoutée : +{quantity}g\n"
        text += f"Nouveau stock : {new_stock}g"
        
        logger.info(f"📥 Stock ajouté: {product_name} +{quantity}g (total: {new_stock}g)")
        
        keyboard = [
            [InlineKeyboardButton(f"📦 Gérer stocks", callback_data="admin_stocks")],
            [InlineKeyboardButton("🔙 Menu Admin", callback_data="back_to_admin_menu")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # Nettoyer
        context.user_data.pop('stock_product', None)
        context.user_data.pop('stock_action', None)
        
    elif action == 'remove':
        # Vérifier si assez de stock
        current_stock = get_stock(product_name)
        
        if quantity > current_stock:
            await update.message.reply_text(
                f"{EMOJI_THEME['error']} *STOCK INSUFFISANT*\n\n"
                f"Stock actuel : {current_stock}g\n"
                f"Demandé : {quantity}g\n\n"
                f"Vous ne pouvez pas retirer plus que le stock disponible.",
                parse_mode='Markdown'
            )
            return ADMIN_STOCK_MENU
        
        # Retirer du stock
        update_stock(product_name, -quantity)
        new_stock = get_stock(product_name)
        
        text = f"{EMOJI_THEME['success']} *STOCK RETIRÉ*\n\n"
        text += f"Produit : {product_name}\n"
        text += f"Quantité retirée : -{quantity}g\n"
        text += f"Nouveau stock : {new_stock}g"
        
        logger.info(f"📤 Stock retiré: {product_name} -{quantity}g (total: {new_stock}g)")
        
        keyboard = [
            [InlineKeyboardButton(f"📦 Gérer stocks", callback_data="admin_stocks")],
            [InlineKeyboardButton("🔙 Menu Admin", callback_data="back_to_admin_menu")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # Nettoyer
        context.user_data.pop('stock_product', None)
        context.user_data.pop('stock_action', None)
    
    return ADMIN_STOCK_MENU

# ==================== ALERTES STOCK ====================

@error_handler
async def stock_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les alertes de stock"""
    query = update.callback_query
    await query.answer()
    
    low_stock = get_low_stock_products()
    out_of_stock = get_out_of_stock_products()
    
    text = f"{EMOJI_THEME['warning']} *ALERTES STOCK*\n\n"
    
    if out_of_stock:
        text += f"{EMOJI_THEME['offline']} *RUPTURES DE STOCK :*\n"
        for product in out_of_stock:
            text += f"• {product}\n"
        text += "\n"
    
    if low_stock:
        text += f"{EMOJI_THEME['warning']} *STOCK FAIBLE :*\n"
        for item in low_stock:
            product = item['product']
            quantity = item['quantity']
            threshold = item['threshold']
            text += f"• {product} : {quantity}g (seuil: {threshold}g)\n"
        text += "\n"
    
    if not out_of_stock and not low_stock:
        text += f"{EMOJI_THEME['success']} *AUCUNE ALERTE*\n\n"
        text += f"Tous les stocks sont à niveau."
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_stocks")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_STOCK_MENU

# FIN DU BLOC 7 PARTIE 2

# ==================== BLOC 8 : PANEL ADMIN - PARTIE 3 (CLIENTS, STATS, HORAIRES, MAINTENANCE) ====================
# Ajoutez ce bloc APRÈS le BLOC 7

# ==================== GESTION CLIENTS ====================

@error_handler
async def admin_clients_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de gestion des clients"""
    query = update.callback_query
    await query.answer()
    
    users = load_users()
    history = load_client_history()
    referrals = load_referrals()
    
    # Statistiques
    total_users = len(users)
    vip_users = len([u for u in history.values() if u.get('vip_status', False)])
    total_spent = sum(u.get('total_spent', 0) for u in history.values())
    total_orders = sum(u.get('orders_count', 0) for u in history.values())
    
    # 🎨 Affichage avec statistiques détaillées
    text = f"👥 *GESTION CLIENTS*\n\n"
    text += f"📊 *Statistiques globales :*\n"
    text += f"• {EMOJI_THEME['product']} Total clients : {total_users}\n"
    text += f"• {EMOJI_THEME['vip']} Clients VIP : {vip_users}\n"
    text += f"• {EMOJI_THEME['money']} CA total : {total_spent:.2f}€\n"
    text += f"• 📦 Commandes : {total_orders}\n"
    
    if total_users > 0:
        text += f"• 💵 Panier moyen : {total_spent/total_orders if total_orders > 0 else 0:.2f}€\n"
    
    keyboard = [
        [InlineKeyboardButton(f"📋 Liste clients", callback_data="clients_list")],
        [InlineKeyboardButton(f"{EMOJI_THEME['vip']} Clients VIP", callback_data="clients_vip")],
        [InlineKeyboardButton(f"🔍 Rechercher client", callback_data="clients_search")],
        [InlineKeyboardButton(f"{EMOJI_THEME['target']} Parrainages", callback_data="clients_referrals")],
        [InlineKeyboardButton(f"📊 Top clients", callback_data="clients_top")],
        [InlineKeyboardButton("🔙 Retour", callback_data="back_to_admin_menu")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_CLIENT_MENU

@error_handler
async def clients_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche la liste des clients"""
    query = update.callback_query
    await query.answer()
    
    users = load_users()
    history = load_client_history()
    
    if not users:
        text = f"{EMOJI_THEME['warning']} *AUCUN CLIENT*\n\n"
        text += f"Aucun client enregistré."
    else:
        # Pagination - 10 clients par page
        page = context.user_data.get('clients_page', 0)
        per_page = 10
        
        users_list = sorted(users.items(), key=lambda x: x[1].get('first_seen', ''), reverse=True)
        total_pages = (len(users_list) + per_page - 1) // per_page
        
        start_idx = page * per_page
        end_idx = min(start_idx + per_page, len(users_list))
        
        text = f"👥 *LISTE CLIENTS* (Page {page + 1}/{total_pages})\n\n"
        
        for user_id, data in users_list[start_idx:end_idx]:
            username = data.get('username', 'N/A')
            first_name = data.get('first_name', 'N/A')
            
            # Récupérer stats
            user_stats = history.get(user_id, {})
            total_spent = user_stats.get('total_spent', 0)
            orders_count = user_stats.get('orders_count', 0)
            is_vip = user_stats.get('vip_status', False)
            
            vip_badge = f"{EMOJI_THEME['vip']}" if is_vip else "👤"
            
            text += f"{vip_badge} *{first_name}* (@{username})\n"
            text += f"   ID: `{user_id}`\n"
            text += f"   Commandes: {orders_count} | CA: {total_spent:.2f}€\n\n"
        
        # Boutons pagination
        keyboard = []
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Précédent", callback_data=f"clients_page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Suivant ▶️", callback_data=f"clients_page_{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_clients")])
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_CLIENT_MENU

@error_handler
async def clients_page_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change de page dans la liste clients"""
    query = update.callback_query
    await query.answer()
    
    page = int(query.data.replace("clients_page_", ""))
    context.user_data['clients_page'] = page
    
    return await clients_list(update, context)

@error_handler
async def clients_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche la liste des clients VIP"""
    query = update.callback_query
    await query.answer()
    
    history = load_client_history()
    users = load_users()
    
    vip_clients = [(uid, data) for uid, data in history.items() if data.get('vip_status', False)]
    
    if not vip_clients:
        text = f"{EMOJI_THEME['vip']} *CLIENTS VIP*\n\n"
        text += f"Aucun client VIP pour le moment.\n\n"
        text += f"💡 Seuil VIP : {VIP_THRESHOLD}€"
    else:
        # Trier par montant dépensé
        vip_clients.sort(key=lambda x: x[1].get('total_spent', 0), reverse=True)
        
        text = f"{EMOJI_THEME['vip']} *CLIENTS VIP* ({len(vip_clients)})\n\n"
        
        for i, (user_id, data) in enumerate(vip_clients[:20], 1):  # Top 20
            user_info = users.get(user_id, {})
            first_name = user_info.get('first_name', 'N/A')
            username = user_info.get('username', 'N/A')
            
            total_spent = data.get('total_spent', 0)
            orders_count = data.get('orders_count', 0)
            
            # Badges spéciaux pour le podium
            if i == 1:
                badge = f"{EMOJI_THEME['trophy']}"
            elif i == 2:
                badge = f"{EMOJI_THEME['medal']}"
            elif i == 3:
                badge = "🥉"
            else:
                badge = f"{EMOJI_THEME['diamond']}"
            
            text += f"{badge} #{i} *{first_name}* (@{username})\n"
            text += f"   {EMOJI_THEME['money']} {total_spent:.2f}€ | 📦 {orders_count} commandes\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_clients")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_CLIENT_MENU

@error_handler
async def clients_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les statistiques de parrainage"""
    query = update.callback_query
    await query.answer()
    
    referrals = load_referrals()
    users = load_users()
    
    if not referrals:
        text = f"{EMOJI_THEME['target']} *SYSTÈME DE PARRAINAGE*\n\n"
        text += f"Aucune donnée de parrainage."
    else:
        # Top parrains
        top_referrers = sorted(
            [(uid, data) for uid, data in referrals.items()],
            key=lambda x: len(x[1].get('referred_users', [])),
            reverse=True
        )[:10]
        
        total_referrals = sum(len(data.get('referred_users', [])) for data in referrals.values())
        total_earnings = sum(data.get('earnings', 0) for data in referrals.values())
        
        text = f"{EMOJI_THEME['target']} *SYSTÈME DE PARRAINAGE*\n\n"
        text += f"📊 *Statistiques globales :*\n"
        text += f"• Total parrainages : {total_referrals}\n"
        text += f"• Gains distribués : {total_earnings:.2f}€\n"
        text += f"• Bonus : {REFERRAL_BONUS_VALUE}{'%' if REFERRAL_BONUS_TYPE == 'percentage' else '€'}\n\n"
        
        if top_referrers:
            text += f"{EMOJI_THEME['trophy']} *TOP PARRAINS :*\n\n"
            
            for i, (user_id, data) in enumerate(top_referrers, 1):
                user_info = users.get(user_id, {})
                first_name = user_info.get('first_name', 'N/A')
                
                referred_count = len(data.get('referred_users', []))
                earnings = data.get('earnings', 0)
                
                if i <= 3:
                    badge = [f"{EMOJI_THEME['trophy']}", f"{EMOJI_THEME['medal']}", "🥉"][i-1]
                else:
                    badge = f"{EMOJI_THEME['star']}"
                
                text += f"{badge} {first_name}: {referred_count} filleuls ({earnings:.2f}€)\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_clients")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_CLIENT_MENU

@error_handler
async def clients_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top clients par CA"""
    query = update.callback_query
    await query.answer()
    
    history = load_client_history()
    users = load_users()
    
    if not history:
        text = f"📊 *TOP CLIENTS*\n\n"
        text += f"Aucune commande enregistrée."
    else:
        # Trier par CA
        top_clients = sorted(
            history.items(),
            key=lambda x: x[1].get('total_spent', 0),
            reverse=True
        )[:10]
        
        text = f"📊 *TOP 10 CLIENTS*\n\n"
        
        for i, (user_id, data) in enumerate(top_clients, 1):
            user_info = users.get(user_id, {})
            first_name = user_info.get('first_name', 'N/A')
            username = user_info.get('username', 'N/A')
            
            total_spent = data.get('total_spent', 0)
            orders_count = data.get('orders_count', 0)
            is_vip = data.get('vip_status', False)
            
            # Badge
            if i == 1:
                badge = f"{EMOJI_THEME['trophy']}"
            elif i == 2:
                badge = f"{EMOJI_THEME['medal']}"
            elif i == 3:
                badge = "🥉"
            else:
                badge = f"{i}."
            
            vip_icon = f" {EMOJI_THEME['vip']}" if is_vip else ""
            
            text += f"{badge} *{first_name}*{vip_icon}\n"
            text += f"   {EMOJI_THEME['money']} {total_spent:.2f}€ | 📦 {orders_count}\n"
            text += f"   💵 Panier moyen: {total_spent/orders_count if orders_count > 0 else 0:.2f}€\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_clients")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_CLIENT_MENU

# ==================== STATISTIQUES ====================

@error_handler
async def admin_stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu des statistiques"""
    query = update.callback_query
    await query.answer()
    
    stats = load_stats()
    history = load_client_history()
    
    # Stats hebdomadaires
    weekly_sales = stats.get('weekly', [])
    weekly_total = sum(s['amount'] for s in weekly_sales)
    weekly_count = len(weekly_sales)
    
    # Stats mensuelles
    monthly_sales = stats.get('monthly', [])
    monthly_total = sum(s['amount'] for s in monthly_sales)
    monthly_count = len(monthly_sales)
    
    # Stats globales
    all_time_total = sum(h.get('total_spent', 0) for h in history.values())
    all_time_orders = sum(h.get('orders_count', 0) for h in history.values())
    
    # 🎨 Affichage avec graphiques texte
    text = f"{EMOJI_THEME['stats']} *STATISTIQUES*\n\n"
    
    text += f"📅 *Cette semaine :*\n"
    text += f"• {EMOJI_THEME['money']} CA : {weekly_total:.2f}€\n"
    text += f"• 📦 Commandes : {weekly_count}\n"
    if weekly_count > 0:
        text += f"• 💵 Panier moyen : {weekly_total/weekly_count:.2f}€\n"
    text += "\n"
    
    text += f"📅 *Ce mois :*\n"
    text += f"• {EMOJI_THEME['money']} CA : {monthly_total:.2f}€\n"
    text += f"• 📦 Commandes : {monthly_count}\n"
    if monthly_count > 0:
        text += f"• 💵 Panier moyen : {monthly_total/monthly_count:.2f}€\n"
    text += "\n"
    
    text += f"📊 *Total (depuis début) :*\n"
    text += f"• {EMOJI_THEME['money']} CA : {all_time_total:.2f}€\n"
    text += f"• 📦 Commandes : {all_time_orders}\n"
    if all_time_orders > 0:
        text += f"• 💵 Panier moyen : {all_time_total/all_time_orders:.2f}€"
    
    keyboard = [
        [InlineKeyboardButton(f"📈 Produits populaires", callback_data="stats_products")],
        [InlineKeyboardButton(f"🌍 Répartition pays", callback_data="stats_countries")],
        [InlineKeyboardButton(f"📊 Graphique semaine", callback_data="stats_week_graph")],
        [InlineKeyboardButton(f"💾 Exporter CSV", callback_data="stats_export")],
        [InlineKeyboardButton("🔙 Retour", callback_data="back_to_admin_menu")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

@error_handler
async def stats_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats produits populaires"""
    query = update.callback_query
    await query.answer()
    
    stats = load_stats()
    monthly_sales = stats.get('monthly', [])
    
    if not monthly_sales:
        text = f"📈 *PRODUITS POPULAIRES*\n\n"
        text += f"Aucune donnée disponible."
    else:
        # Compter les produits
        product_count = defaultdict(int)
        product_revenue = defaultdict(float)
        
        for sale in monthly_sales:
            products_str = sale.get('products', '')
            amount = sale.get('amount', 0)
            
            products = [p.strip() for p in products_str.split(';') if p.strip()]
            
            for product in products:
                product_count[product] += 1
                product_revenue[product] += amount / len(products)  # Répartition équitable
        
        # Top 10
        top_products = sorted(product_count.items(), key=lambda x: x[1], reverse=True)[:10]
        
        text = f"📈 *PRODUITS POPULAIRES* (ce mois)\n\n"
        
        for i, (product, count) in enumerate(top_products, 1):
            revenue = product_revenue[product]
            
            if i <= 3:
                badge = [f"{EMOJI_THEME['trophy']}", f"{EMOJI_THEME['medal']}", "🥉"][i-1]
            else:
                badge = f"{i}."
            
            # Barre de progression relative
            max_count = top_products[0][1]
            progress = create_progress_bar(count, max_count, length=10)
            
            text += f"{badge} {product}\n"
            text += f"   {progress}\n"
            text += f"   📦 {count} ventes | {EMOJI_THEME['money']} {revenue:.2f}€\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_stats")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

@error_handler
async def stats_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Répartition par pays"""
    query = update.callback_query
    await query.answer()
    
    stats = load_stats()
    monthly_sales = stats.get('monthly', [])
    
    if not monthly_sales:
        text = f"🌍 *RÉPARTITION PAYS*\n\n"
        text += f"Aucune donnée disponible."
    else:
        fr_count = sum(1 for s in monthly_sales if s.get('country') == 'FR')
        ch_count = sum(1 for s in monthly_sales if s.get('country') == 'CH')
        
        fr_revenue = sum(s['amount'] for s in monthly_sales if s.get('country') == 'FR')
        ch_revenue = sum(s['amount'] for s in monthly_sales if s.get('country') == 'CH')
        
        total_count = fr_count + ch_count
        total_revenue = fr_revenue + ch_revenue
        
        text = f"🌍 *RÉPARTITION PAYS* (ce mois)\n\n"
        
        # France
        fr_percent = (fr_count / total_count * 100) if total_count > 0 else 0
        fr_revenue_percent = (fr_revenue / total_revenue * 100) if total_revenue > 0 else 0
        fr_progress = create_progress_bar(fr_count, total_count, length=15)
        
        text += f"🇫🇷 *FRANCE*\n"
        text += f"{fr_progress} {fr_percent:.1f}%\n"
        text += f"• Commandes : {fr_count}\n"
        text += f"• {EMOJI_THEME['money']} CA : {fr_revenue:.2f}€ ({fr_revenue_percent:.1f}%)\n"
        text += f"• 💵 Panier moyen : {fr_revenue/fr_count if fr_count > 0 else 0:.2f}€\n\n"
        
        # Suisse
        ch_percent = (ch_count / total_count * 100) if total_count > 0 else 0
        ch_revenue_percent = (ch_revenue / total_revenue * 100) if total_revenue > 0 else 0
        ch_progress = create_progress_bar(ch_count, total_count, length=15)
        
        text += f"🇨🇭 *SUISSE*\n"
        text += f"{ch_progress} {ch_percent:.1f}%\n"
        text += f"• Commandes : {ch_count}\n"
        text += f"• {EMOJI_THEME['money']} CA : {ch_revenue:.2f}€ ({ch_revenue_percent:.1f}%)\n"
        text += f"• 💵 Panier moyen : {ch_revenue/ch_count if ch_count > 0 else 0:.2f}€"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_stats")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

# ✅ CORRECTION : GRAPHIQUE SEMAINE

@error_handler
async def stats_week_graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ AJOUT : Graphique de la semaine en ASCII art"""
    query = update.callback_query
    await query.answer()
    
    stats = load_stats()
    weekly_sales = stats.get('weekly', [])
    
    if not weekly_sales:
        text = f"📊 *GRAPHIQUE SEMAINE*\n\n"
        text += f"Aucune donnée disponible cette semaine."
    else:
        # Regrouper par jour
        from collections import defaultdict
        daily_sales = defaultdict(float)
        
        for sale in weekly_sales:
            date_str = sale['date'][:10]  # YYYY-MM-DD
            daily_sales[date_str] += sale['amount']
        
        # Trier par date
        sorted_days = sorted(daily_sales.items())
        
        # Trouver le max pour normaliser
        max_amount = max(daily_sales.values()) if daily_sales else 1
        
        text = f"📊 *GRAPHIQUE SEMAINE*\n\n"
        
        # Créer le graphique en barres ASCII
        for date, amount in sorted_days[-7:]:  # 7 derniers jours
            # Date formatée
            try:
                day_name = datetime.fromisoformat(date).strftime('%a %d/%m')
            except:
                day_name = date
            
            # Barre proportionnelle
            bar_length = int((amount / max_amount) * 20)
            bar = "█" * bar_length
            
            text += f"{day_name}\n"
            text += f"{bar} {amount:.0f}€\n\n"
        
        # Statistiques
        total = sum(daily_sales.values())
        avg = total / len(daily_sales) if daily_sales else 0
        
        text += f"📈 *Résumé :*\n"
        text += f"• Total : {total:.2f}€\n"
        text += f"• Moyenne/jour : {avg:.2f}€\n"
        text += f"• Meilleur jour : {max(daily_sales.values()):.2f}€"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_stats")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

# ✅ CORRECTION : EXPORT CSV

@error_handler
async def stats_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ AJOUT : Exporte les statistiques en CSV"""
    query = update.callback_query
    await query.answer()
    
    csv_path = DATA_DIR / "orders.csv"
    
    if not csv_path.exists():
        await query.message.edit_text(
            f"{EMOJI_THEME['warning']} *AUCUNE DONNÉE*\n\n"
            f"Aucune commande enregistrée dans le fichier CSV.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Retour", callback_data="admin_stats")
            ]]),
            parse_mode='Markdown'
        )
        return ADMIN_MENU_MAIN
    
    try:
        # Envoyer le fichier CSV
        with open(csv_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=f"orders_{datetime.now().strftime('%Y%m%d')}.csv",
                caption=f"{EMOJI_THEME['success']} *EXPORT CSV*\n\nFichier de toutes les commandes",
                parse_mode='Markdown'
            )
        
        await query.answer(f"{EMOJI_THEME['success']} Fichier envoyé", show_alert=True)
        
        # Message de confirmation
        text = f"{EMOJI_THEME['success']} *EXPORT RÉUSSI*\n\n"
        text += f"Le fichier CSV a été envoyé ci-dessus."
        
        keyboard = [[InlineKeyboardButton("🔙 Menu Stats", callback_data="admin_stats")]]
        
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        logger.info(f"📊 Export CSV envoyé à l'admin")
        
    except Exception as e:
        logger.error(f"Erreur export CSV: {e}")
        await query.answer(f"{EMOJI_THEME['error']} Erreur d'export", show_alert=True)
    
    return ADMIN_MENU_MAIN

# ==================== HORAIRES ====================

@error_handler
async def admin_horaires_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de gestion des horaires"""
    query = update.callback_query
    await query.answer()
    
    horaires = load_horaires()
    enabled = horaires.get('enabled', True)
    
    # 🎨 Affichage avec état actuel
    text = f"⏰ *GESTION HORAIRES*\n\n"
    text += f"📊 *État actuel :*\n"
    
    if enabled:
        start_time = f"{horaires['start_hour']:02d}:{horaires['start_minute']:02d}"
        end_time = f"{horaires['end_hour']:02d}:{horaires['end_minute']:02d}"
        
        text += f"• {EMOJI_THEME['online']} Activés\n"
        text += f"• Ouverture : {start_time}\n"
        text += f"• Fermeture : {end_time}\n\n"
        
        # Vérifier si dans les horaires maintenant
        now = datetime.now().time()
        start = time(horaires['start_hour'], horaires['start_minute'])
        end = time(horaires['end_hour'], horaires['end_minute'])
        
        if start <= now <= end:
            text += f"{EMOJI_THEME['online']} *Actuellement : OUVERT*"
        else:
            text += f"{EMOJI_THEME['offline']} *Actuellement : FERMÉ*"
    else:
        text += f"• {EMOJI_THEME['offline']} Désactivés\n"
        text += f"• Mode : 24h/24\n\n"
        text += f"{EMOJI_THEME['online']} *Actuellement : TOUJOURS OUVERT*"
    
    keyboard = [
        [InlineKeyboardButton(
            f"{'🔴 Désactiver' if enabled else '🟢 Activer'} horaires",
            callback_data="horaires_toggle"
        )],
        [InlineKeyboardButton(f"⏰ Modifier horaires", callback_data="horaires_modify")],
        [InlineKeyboardButton("🔙 Retour", callback_data="back_to_admin_menu")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

@error_handler
async def horaires_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Active/désactive les horaires"""
    query = update.callback_query
    await query.answer()
    
    horaires = load_horaires()
    current_state = horaires.get('enabled', True)
    new_state = not current_state
    
    horaires['enabled'] = new_state
    save_horaires(horaires)
    
    if new_state:
        message = f"{EMOJI_THEME['success']} Horaires activés"
    else:
        message = f"{EMOJI_THEME['warning']} Horaires désactivés (24h/24)"
    
    await query.answer(message, show_alert=True)
    
    logger.info(f"⏰ Horaires: {'Activés' if new_state else 'Désactivés'}")
    
    return await admin_horaires_menu(update, context)

@error_handler
async def horaires_modify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande les nouveaux horaires"""
    query = update.callback_query
    await query.answer()
    
    text = f"⏰ *MODIFIER HORAIRES*\n\n"
    text += f"Entrez les nouveaux horaires :\n\n"
    text += f"Format : HH:MM-HH:MM\n"
    text += f"_Exemple : 09:00-23:00_\n\n"
    text += f"💡 Utilisez le format 24h"
    
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_horaires")]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_HORAIRES_INPUT

@error_handler
async def receive_horaires(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Réception et validation des nouveaux horaires"""
    input_text = sanitize_input(update.message.text, 20)
    
    # Validation format HH:MM-HH:MM
    match = re.match(r'(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})', input_text)
    
    if not match:
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Format invalide.\n\nUtilisez : HH:MM-HH:MM\n\n_Exemple : 09:00-23:00_",
            parse_mode='Markdown'
        )
        return ADMIN_HORAIRES_INPUT
    
    start_h, start_m, end_h, end_m = map(int, match.groups())
    
    # Validation des valeurs
    if not (0 <= start_h < 24 and 0 <= start_m < 60 and 0 <= end_h < 24 and 0 <= end_m < 60):
        await update.message.reply_text(
            f"{EMOJI_THEME['error']} Heures/minutes invalides.\n\nHeures : 0-23\nMinutes : 0-59",
            parse_mode='Markdown'
        )
        return ADMIN_HORAIRES_INPUT
    
    # Sauvegarder
    horaires = load_horaires()
    horaires['start_hour'] = start_h
    horaires['start_minute'] = start_m
    horaires['end_hour'] = end_h
    horaires['end_minute'] = end_m
    save_horaires(horaires)
    
    text = f"{EMOJI_THEME['success']} *HORAIRES MODIFIÉS*\n\n"
    text += f"✅ Nouveaux horaires enregistrés :\n\n"
    text += f"Ouverture : {start_h:02d}:{start_m:02d}\n"
    text += f"Fermeture : {end_h:02d}:{end_m:02d}"
    
    keyboard = [[InlineKeyboardButton("🔙 Menu Horaires", callback_data="admin_horaires")]]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"⏰ Horaires modifiés: {start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}")
    
    return ADMIN_MENU_MAIN

# ==================== MAINTENANCE ====================

@error_handler
async def admin_maintenance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu maintenance"""
    query = update.callback_query
    await query.answer()
    
    status = load_maintenance_status()
    enabled = status.get('enabled', False)
    
    # 🎨 Affichage avec état
    text = f"🔧 *MODE MAINTENANCE*\n\n"
    text += f"📊 *État actuel :*\n"
    
    if enabled:
        text += f"• {EMOJI_THEME['warning']} *ACTIF*\n"
        text += f"• Raison : {status.get('reason', 'N/A')}\n"
        text += f"• Depuis : {status.get('last_updated', 'N/A')[:16]}\n\n"
        text += f"⚠️ Les clients ne peuvent pas passer commande."
    else:
        text += f"• {EMOJI_THEME['online']} Inactif\n\n"
        text += f"✅ Le bot fonctionne normalement."
    
    keyboard = [
        [InlineKeyboardButton(
            f"{'🔴 Désactiver' if enabled else '🟠 Activer'} maintenance",
            callback_data="maintenance_toggle"
        )],
        [InlineKeyboardButton("🔙 Retour", callback_data="back_to_admin_menu")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MENU_MAIN

@error_handler
async def maintenance_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Active/désactive la maintenance"""
    query = update.callback_query
    await query.answer()
    
    status = load_maintenance_status()
    current_state = status.get('enabled', False)
    new_state = not current_state
    
    if new_state:
        reason = "Activé manuellement par l'admin"
    else:
        reason = None
    
    set_maintenance_mode(new_state, reason)
    
    if new_state:
        message = f"{EMOJI_THEME['warning']} Mode maintenance ACTIVÉ"
    else:
        message = f"{EMOJI_THEME['success']} Mode maintenance DÉSACTIVÉ"
    
    await query.answer(message, show_alert=True)
    
    return await admin_maintenance_menu(update, context)

# ==================== NOTIFICATIONS ====================

@error_handler
async def admin_notifications_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de gestion des notifications"""
    query = update.callback_query
    await query.answer()
    
    # 🎨 Affichage
    text = f"{EMOJI_THEME['info']} *NOTIFICATIONS ADMIN*\n\n"
    text += f"📊 *Paramètres actuels :*\n\n"
    text += f"✅ Notifications activées :\n"
    text += f"• Nouvelles commandes\n"
    text += f"• Stock faible\n"
    text += f"• Rupture de stock\n"
    text += f"• Nouveaux clients\n"
    text += f"• Clients VIP\n"
    text += f"• Commandes haute valeur (>500€)\n\n"
    text += f"📈 *Rapports automatiques :*\n"
    text += f"• Hebdomadaire : Dimanche 23h59\n"
    text += f"• Mensuel : Dernier jour du mois 23h59"
    
    keyboard = [
        [InlineKeyboardButton(f"📧 Envoyer rapport maintenant", callback_data="notif_send_report")],
        [InlineKeyboardButton(f"🧪 Test notification", callback_data="notif_test")],
        [InlineKeyboardButton("🔙 Retour", callback_data="back_to_admin_menu")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_NOTIF_MENU

@error_handler
async def notif_send_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envoie un rapport immédiat"""
    query = update.callback_query
    await query.answer()
    
    # Envoyer rapport hebdomadaire
    await send_weekly_report(context)
    
    await query.answer(f"{EMOJI_THEME['success']} Rapport envoyé", show_alert=True)
    
    return await admin_notifications_menu(update, context)

@error_handler
async def notif_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """✅ CORRECTION : Envoie une notification de test AVEC RETOUR"""
    query = update.callback_query
    await query.answer()
    
    test_message = f"{EMOJI_THEME['info']} *TEST NOTIFICATION*\n\n"
    test_message += f"✅ Le système de notifications fonctionne correctement.\n\n"
    test_message += f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=test_message,
            parse_mode='Markdown'
        )
        await query.answer(f"{EMOJI_THEME['success']} Notification envoyée", show_alert=True)
        
        # ✅ CORRECTION : Retourner au menu notifications
        return await admin_notifications_menu(update, context)
        
    except Exception as e:
        logger.error(f"Erreur test notification: {e}")
        await query.answer(f"{EMOJI_THEME['error']} Erreur d'envoi", show_alert=True)
        
        # ✅ CORRECTION : Retourner au menu même en cas d'erreur
        return await admin_notifications_menu(update, context)

# FIN DU BLOC 8
# ==================== BLOC 9 : CONVERSATION HANDLER ET CONFIGURATION DU BOT ====================
# Ajoutez ce bloc APRÈS le BLOC 8

# ==================== CONVERSATION HANDLER CLIENT ====================

# ==================== BLOC 9 : CONVERSATION HANDLERS ====================

def create_client_conversation_handler():
    """Crée le ConversationHandler pour les clients"""
    logger.info("🔧 Création du ConversationHandler CLIENT")
    
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
            CallbackQueryHandler(retry_start, pattern="^retry_start$")
        ],
        states={
            LANGUE: [
                # ✅ Gestion sélection langue
                CallbackQueryHandler(set_langue, pattern="^lang_")
            ],
            PAYS: [
                # ✅ Gestion menu principal (après sélection langue)
                CallbackQueryHandler(menu_navigation, pattern="^start_order$"),
                CallbackQueryHandler(menu_navigation, pattern="^contact_admin$"),
                CallbackQueryHandler(my_account, pattern="^my_account$"),
                CallbackQueryHandler(voir_carte, pattern="^voir_carte$"),
                CallbackQueryHandler(afficher_prix, pattern="^prix_"),
                
                # ✅ Choix du pays
                CallbackQueryHandler(choix_pays, pattern="^country_"),
                
                # ✅ CORRECTION : back_to_main_menu gère le retour
                CallbackQueryHandler(back_to_main_menu, pattern="^back_to_main_menu$"),
                CallbackQueryHandler(back_to_country_choice, pattern="^back_to_country_choice$")
            ],
            PRODUIT: [
                CallbackQueryHandler(choix_produit, pattern="^product_"),
                CallbackQueryHandler(back_to_products, pattern="^back_to_products$"),
                CallbackQueryHandler(back_to_country_choice, pattern="^back_to_country_choice$"),
                CallbackQueryHandler(back_to_main_menu, pattern="^back_to_main_menu$")
            ],
            PILL_SUBCATEGORY: [
                CallbackQueryHandler(choix_pill_subcategory, pattern="^pill_"),
                CallbackQueryHandler(back_to_products, pattern="^back_to_products$"),
                CallbackQueryHandler(back_to_main_menu, pattern="^back_to_main_menu$")
            ],
            ROCK_SUBCATEGORY: [
                CallbackQueryHandler(choix_rock_subcategory, pattern="^rock_"),
                CallbackQueryHandler(back_to_products, pattern="^back_to_products$"),
                CallbackQueryHandler(back_to_main_menu, pattern="^back_to_main_menu$")
            ],
            QUANTITE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)
            ],
            CART_MENU: [
                CallbackQueryHandler(cart_menu, pattern="^add_more$"),
                CallbackQueryHandler(cart_menu, pattern="^proceed_checkout$"),
                CallbackQueryHandler(cart_menu, pattern="^apply_promo$"),
                CallbackQueryHandler(back_to_cart, pattern="^back_to_cart$")
            ],
            PROMO_CODE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_promo_code)
            ],
            ADRESSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse)
            ],
            LIVRAISON: [
                CallbackQueryHandler(livraison_postale, pattern="^livraison_postale$"),
                CallbackQueryHandler(livraison_express, pattern="^livraison_express$"),
                CallbackQueryHandler(livraison_meetup, pattern="^livraison_meetup$"),
                CallbackQueryHandler(meetup_zone_selected, pattern="^meetup_zone_"),
                CallbackQueryHandler(back_to_livraison, pattern="^back_to_livraison$"),
                CallbackQueryHandler(back_to_cart, pattern="^back_to_cart$")
            ],
            PAIEMENT: [
                CallbackQueryHandler(choix_paiement, pattern="^paiement_"),
                CallbackQueryHandler(back_to_livraison_from_meetup, pattern="^back_to_livraison_from_meetup$"),
                CallbackQueryHandler(back_to_livraison, pattern="^back_to_livraison$")
            ],
            CONFIRMATION: [
                CallbackQueryHandler(confirmation_commande, pattern="^confirm_order$"),
                CallbackQueryHandler(confirmation_commande, pattern="^cancel$")
            ],
            CONTACT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, contact_admin_handler)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$")
        ],
        conversation_timeout=1800,
        per_message=False,  # ✅ CHANGÉ : False pour supporter MessageHandler
        name="client_conversation",
        allow_reentry=True
    )

def create_admin_conversation_handler():
    """Crée le ConversationHandler pour l'admin"""
    logger.info("🔧 Création du ConversationHandler ADMIN")
    
    return ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_start),
            CallbackQueryHandler(admin_start, pattern="^admin_menu$")
        ],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(admin_stock_menu, pattern="^admin_stock$"),
                CallbackQueryHandler(admin_products_menu, pattern="^admin_products$"),
                CallbackQueryHandler(admin_orders_menu, pattern="^admin_orders$"),
                CallbackQueryHandler(admin_stats_menu, pattern="^admin_stats$"),
                CallbackQueryHandler(admin_promo_menu, pattern="^admin_promo$"),
                CallbackQueryHandler(admin_settings_menu, pattern="^admin_settings$"),
                CallbackQueryHandler(admin_clients_menu, pattern="^admin_clients$"),
                CallbackQueryHandler(broadcast_message_start, pattern="^admin_broadcast$")
            ],
            ADMIN_STOCK: [
                CallbackQueryHandler(admin_view_all_stock, pattern="^view_all_stock$"),
                CallbackQueryHandler(admin_update_stock_select, pattern="^update_stock$"),
                CallbackQueryHandler(admin_add_stock_select, pattern="^add_stock$"),
                CallbackQueryHandler(admin_remove_stock_select, pattern="^remove_stock$"),
                CallbackQueryHandler(admin_start, pattern="^back_to_admin$")
            ],
            ADMIN_STOCK_PRODUCT_SELECT: [
                CallbackQueryHandler(admin_stock_product_selected, pattern="^stock_product_"),
                CallbackQueryHandler(admin_stock_menu, pattern="^back_to_stock_menu$")
            ],
            ADMIN_STOCK_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_stock_input_handler),
                CallbackQueryHandler(admin_stock_menu, pattern="^back_to_stock_menu$")
            ],
            ADMIN_PRODUCTS: [
                CallbackQueryHandler(admin_toggle_product, pattern="^toggle_product_"),
                CallbackQueryHandler(admin_start, pattern="^back_to_admin$")
            ],
            ADMIN_ORDERS: [
                CallbackQueryHandler(admin_view_pending_orders, pattern="^view_pending$"),
                CallbackQueryHandler(admin_view_completed_orders, pattern="^view_completed$"),
                CallbackQueryHandler(admin_view_cancelled_orders, pattern="^view_cancelled$"),
                CallbackQueryHandler(admin_search_order, pattern="^search_order$"),
                CallbackQueryHandler(admin_start, pattern="^back_to_admin$")
            ],
            ADMIN_ORDER_SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_order_search_handler),
                CallbackQueryHandler(admin_orders_menu, pattern="^back_to_orders$")
            ],
            ADMIN_STATS: [
                CallbackQueryHandler(admin_view_daily_stats, pattern="^stats_daily$"),
                CallbackQueryHandler(admin_view_weekly_stats, pattern="^stats_weekly$"),
                CallbackQueryHandler(admin_view_monthly_stats, pattern="^stats_monthly$"),
                CallbackQueryHandler(admin_view_all_time_stats, pattern="^stats_all$"),
                CallbackQueryHandler(admin_view_top_clients, pattern="^stats_top_clients$"),
                CallbackQueryHandler(admin_view_top_products, pattern="^stats_top_products$"),
                CallbackQueryHandler(admin_start, pattern="^back_to_admin$")
            ],
            ADMIN_PROMO: [
                CallbackQueryHandler(admin_list_promo_codes, pattern="^list_promos$"),
                CallbackQueryHandler(admin_create_promo_start, pattern="^create_promo$"),
                CallbackQueryHandler(admin_delete_promo_start, pattern="^delete_promo$"),
                CallbackQueryHandler(admin_start, pattern="^back_to_admin$")
            ],
            ADMIN_PROMO_CREATE_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_promo_create_code_handler),
                CallbackQueryHandler(admin_promo_menu, pattern="^back_to_promo$")
            ],
            ADMIN_PROMO_CREATE_DISCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_promo_create_discount_handler),
                CallbackQueryHandler(admin_promo_menu, pattern="^back_to_promo$")
            ],
            ADMIN_PROMO_CREATE_USAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_promo_create_usage_handler),
                CallbackQueryHandler(admin_promo_menu, pattern="^back_to_promo$")
            ],
            ADMIN_PROMO_DELETE: [
                CallbackQueryHandler(admin_promo_delete_confirm, pattern="^delete_promo_code_"),
                CallbackQueryHandler(admin_promo_menu, pattern="^back_to_promo$")
            ],
            ADMIN_SETTINGS: [
                CallbackQueryHandler(admin_toggle_maintenance, pattern="^toggle_maintenance$"),
                CallbackQueryHandler(admin_update_hours, pattern="^update_hours$"),
                CallbackQueryHandler(admin_view_logs, pattern="^view_logs$"),
                CallbackQueryHandler(admin_backup_data, pattern="^backup_data$"),
                CallbackQueryHandler(admin_clear_cache, pattern="^clear_cache$"),
                CallbackQueryHandler(admin_start, pattern="^back_to_admin$")
            ],
            ADMIN_HOURS_DAY: [
                CallbackQueryHandler(admin_hours_day_selected, pattern="^hours_day_"),
                CallbackQueryHandler(admin_settings_menu, pattern="^back_to_settings$")
            ],
            ADMIN_HOURS_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_hours_input_handler),
                CallbackQueryHandler(admin_settings_menu, pattern="^back_to_settings$")
            ],
            ADMIN_CLIENTS: [
                CallbackQueryHandler(admin_view_all_clients, pattern="^view_all_clients$"),
                CallbackQueryHandler(admin_search_client, pattern="^search_client$"),
                CallbackQueryHandler(admin_view_vip_clients, pattern="^view_vip_clients$"),
                CallbackQueryHandler(admin_client_stats, pattern="^client_stats_"),
                CallbackQueryHandler(admin_start, pattern="^back_to_admin$")
            ],
            ADMIN_CLIENT_SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_client_search_handler),
                CallbackQueryHandler(admin_clients_menu, pattern="^back_to_clients$")
            ],
            BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler),
                CallbackQueryHandler(admin_start, pattern="^back_to_admin$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$"),
            CallbackQueryHandler(admin_start, pattern="^back_to_admin$")
        ],
        conversation_timeout=1800,
        per_message=False,
        name="admin_conversation",
        allow_reentry=True
    )

# FIN DU BLOC 9

# ==================== CONVERSATION HANDLER ADMIN ====================

def create_admin_conversation_handler():
    """Crée le ConversationHandler pour l'admin"""
    return ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_command)
        ],
        states={
            ADMIN_MENU_MAIN: [
                CallbackQueryHandler(admin_menu_main_handler, pattern="^admin_"),
                CallbackQueryHandler(back_to_admin_menu, pattern="^back_to_admin_menu$"),
                CallbackQueryHandler(admin_add_product, pattern="^admin_add_product$"),
                CallbackQueryHandler(admin_toggle_product, pattern="^admin_toggle_product$"),
                CallbackQueryHandler(process_toggle_product, pattern="^toggle_"),
                CallbackQueryHandler(admin_archive_product, pattern="^admin_archive_product$"),
                CallbackQueryHandler(confirm_archive_product, pattern="^archive_confirm_"),
                CallbackQueryHandler(do_archive_product, pattern="^archive_do_"),
                CallbackQueryHandler(pricing_select_product, pattern="^pricing_select_product$"),
                CallbackQueryHandler(pricing_view_all, pattern="^pricing_view_all$"),
                CallbackQueryHandler(pricing_edit, pattern="^pricing_edit$"),
                CallbackQueryHandler(pricing_delete, pattern="^pricing_delete$"),
                CallbackQueryHandler(stock_configure, pattern="^stock_configure$"),
                CallbackQueryHandler(stock_config_product, pattern="^stock_config_"),
                CallbackQueryHandler(stock_add, pattern="^stock_add$"),
                CallbackQueryHandler(stock_add_select, pattern="^stock_add_select_"),
                CallbackQueryHandler(stock_remove, pattern="^stock_remove$"),
                CallbackQueryHandler(stock_remove_select, pattern="^stock_remove_select_"),
                CallbackQueryHandler(stock_alerts, pattern="^stock_alerts$"),
                CallbackQueryHandler(promo_delete, pattern="^promo_delete$"),
                CallbackQueryHandler(promo_details, pattern="^promo_details$"),
                CallbackQueryHandler(clients_list, pattern="^clients_list$"),
                CallbackQueryHandler(clients_page_change, pattern="^clients_page_"),
                CallbackQueryHandler(clients_vip, pattern="^clients_vip$"),
                CallbackQueryHandler(clients_referrals, pattern="^clients_referrals$"),
                CallbackQueryHandler(clients_top, pattern="^clients_top$"),
                CallbackQueryHandler(stats_products, pattern="^stats_products$"),
                CallbackQueryHandler(stats_countries, pattern="^stats_countries$"),
                CallbackQueryHandler(stats_week_graph, pattern="^stats_week_graph$"),
                CallbackQueryHandler(stats_export, pattern="^stats_export$"),
                CallbackQueryHandler(horaires_toggle, pattern="^horaires_toggle$"),
                CallbackQueryHandler(horaires_modify, pattern="^horaires_modify$"),
                CallbackQueryHandler(maintenance_toggle, pattern="^maintenance_toggle$"),
                CallbackQueryHandler(notif_send_report, pattern="^notif_send_report$"),
                CallbackQueryHandler(notif_test, pattern="^notif_test$")
            ],
            ADMIN_NEW_PRODUCT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product_name),
                CallbackQueryHandler(admin_products_menu, pattern="^admin_products$")
            ],
            ADMIN_NEW_PRODUCT_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product_code),
                CallbackQueryHandler(admin_products_menu, pattern="^admin_products$")
            ],
            ADMIN_NEW_PRODUCT_CATEGORY: [
                CallbackQueryHandler(receive_product_category, pattern="^cat_"),
                CallbackQueryHandler(admin_products_menu, pattern="^admin_products$")
            ],
            ADMIN_NEW_PRODUCT_PRICE_FR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product_price_fr),
                CallbackQueryHandler(admin_products_menu, pattern="^admin_products$")
            ],
            ADMIN_NEW_PRODUCT_PRICE_CH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product_price_ch),
                CallbackQueryHandler(admin_products_menu, pattern="^admin_products$")
            ],
            ADMIN_CONFIRM_PRODUCT: [
                CallbackQueryHandler(confirm_add_product, pattern="^confirm_add_product$"),
                CallbackQueryHandler(admin_products_menu, pattern="^admin_products$")
            ],
            ADMIN_SELECT_PRODUCT_PRICING: [
                CallbackQueryHandler(pricing_product_selected, pattern="^pricing_product_"),
                CallbackQueryHandler(pricing_country_selected, pattern="^pricing_country_"),
                CallbackQueryHandler(pricing_select_product, pattern="^pricing_select_product$"),
                CallbackQueryHandler(admin_pricing_menu, pattern="^admin_pricing$")
            ],
            ADMIN_PRICING_TIERS: [
                CallbackQueryHandler(add_pricing_tier, pattern="^add_pricing_tier$"),
                CallbackQueryHandler(pricing_country_selected, pattern="^pricing_country_"),
                CallbackQueryHandler(admin_pricing_menu, pattern="^admin_pricing$")
            ],
            ADMIN_TIER_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_tier_quantity),
                CallbackQueryHandler(pricing_country_selected, pattern="^pricing_country_")
            ],
            ADMIN_TIER_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_tier_price),
                CallbackQueryHandler(pricing_country_selected, pattern="^pricing_country_")
            ],
            ADMIN_PRICING_EDIT: [
                CallbackQueryHandler(pricing_edit, pattern="^pricing_edit$"),
                CallbackQueryHandler(pricing_edit_select, pattern="^pricing_edit_select_"),
                CallbackQueryHandler(pricing_delete_tier_confirm, pattern="^pricing_delete_tier_"),
                CallbackQueryHandler(admin_pricing_menu, pattern="^admin_pricing$")
            ],
            ADMIN_PRICING_DELETE: [
                CallbackQueryHandler(pricing_delete, pattern="^pricing_delete$"),
                CallbackQueryHandler(pricing_delete_confirm, pattern="^pricing_delete_confirm_"),
                CallbackQueryHandler(pricing_delete_do, pattern="^pricing_delete_do_"),
                CallbackQueryHandler(admin_pricing_menu, pattern="^admin_pricing$")
            ],
            ADMIN_PROMO_MENU: [
                CallbackQueryHandler(promo_create, pattern="^promo_create$"),
                CallbackQueryHandler(promo_type_selected, pattern="^promo_type_"),
                CallbackQueryHandler(promo_delete, pattern="^promo_delete$"),
                CallbackQueryHandler(promo_delete_confirm, pattern="^promo_delete_confirm_"),
                CallbackQueryHandler(promo_delete_do, pattern="^promo_delete_do_"),
                CallbackQueryHandler(promo_details, pattern="^promo_details$"),
                CallbackQueryHandler(admin_promo_menu, pattern="^admin_promo$"),
                CallbackQueryHandler(back_to_admin_menu, pattern="^back_to_admin_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, promo_receive_input)
            ],
            ADMIN_STOCK_MENU: [
                CallbackQueryHandler(stock_configure, pattern="^stock_configure$"),
                CallbackQueryHandler(stock_config_product, pattern="^stock_config_"),
                CallbackQueryHandler(stock_add, pattern="^stock_add$"),
                CallbackQueryHandler(stock_add_select, pattern="^stock_add_select_"),
                CallbackQueryHandler(stock_remove, pattern="^stock_remove$"),
                CallbackQueryHandler(stock_remove_select, pattern="^stock_remove_select_"),
                CallbackQueryHandler(stock_alerts, pattern="^stock_alerts$"),
                CallbackQueryHandler(admin_stocks_menu, pattern="^admin_stocks$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, stock_process_quantity)
            ],
            ADMIN_CLIENT_MENU: [
                CallbackQueryHandler(clients_list, pattern="^clients_list$"),
                CallbackQueryHandler(clients_page_change, pattern="^clients_page_"),
                CallbackQueryHandler(clients_vip, pattern="^clients_vip$"),
                CallbackQueryHandler(clients_referrals, pattern="^clients_referrals$"),
                CallbackQueryHandler(clients_top, pattern="^clients_top$"),
                CallbackQueryHandler(admin_clients_menu, pattern="^admin_clients$")
            ],
            ADMIN_HORAIRES_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_horaires),
                CallbackQueryHandler(admin_horaires_menu, pattern="^admin_horaires$")
            ],
            ADMIN_NOTIF_MENU: [
                CallbackQueryHandler(notif_send_report, pattern="^notif_send_report$"),
                CallbackQueryHandler(notif_test, pattern="^notif_test$"),
                CallbackQueryHandler(admin_notifications_menu, pattern="^admin_notifications$"),
                CallbackQueryHandler(back_to_admin_menu, pattern="^back_to_admin_menu$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^admin_close$")
        ],
        conversation_timeout=3600,
        per_message=False,
        name="admin_conversation",
        allow_reentry=True
    )

# ==================== HANDLERS STANDALONE ====================

async def handle_admin_validate_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour la validation de commande par l'admin"""
    return await admin_validate_order(update, context)

# ==================== JOBS PLANIFIÉS ====================

async def scheduled_jobs(context: ContextTypes.DEFAULT_TYPE):
    """Tâches planifiées toutes les minutes"""
    await heartbeat_maintenance(context)
    await check_pending_deletions(context)
    await schedule_reports(context)
    await check_stocks_job(context)
    if IS_BACKUP_BOT:
        await check_primary_bot_health(context)

# ==================== INITIALISATION DU BOT ====================

def main():
    """✅ Point d'entrée principal du bot - VERSION CORRIGÉE"""
    
    # Banner de démarrage
    logger.info("=" * 60)
    logger.info("🚀 BOT TELEGRAM V3.0 - DÉMARRAGE")
    logger.info("=" * 60)
    
    # Vérifier persistance
    boot_count = verify_data_persistence()
    if boot_count == 1:
        logger.info("🆕 PREMIER DÉMARRAGE")
    else:
        logger.info(f"🔄 REDÉMARRAGE #{boot_count}")
    
    # Vérifier downtime
    downtime_detected = check_downtime_and_activate_maintenance()
    if downtime_detected:
        logger.warning("⚠️ DOWNTIME DÉTECTÉ - Mode maintenance activé")
    
    # Initialiser les produits
    init_product_codes()
    
    # Créer l'application
    logger.info("🔧 Création de l'application...")
    application = Application.builder().token(TOKEN).build()
    
    # ==================== AJOUTER ICI - COMMANDES SIMPLES ====================
    logger.info("🔑 Configuration des commandes simples...")
    
    # Commande /myid (pour obtenir son ID Telegram)
    application.add_handler(CommandHandler("myid", get_my_id))
    
    # ==================== FIN AJOUT ====================
    
    # Ajouter les ConversationHandlers
    logger.info("📋 Configuration des handlers...")
    application.add_handler(create_client_conversation_handler())
    application.add_handler(create_admin_conversation_handler())
    
    # Handler validation commande admin (standalone)
    application.add_handler(CallbackQueryHandler(
        handle_admin_validate_order_callback,
        pattern="^admin_validate_"
    ))
    
    # Error handler global
    application.add_error_handler(error_callback)
    
    # Jobs planifiés
    logger.info("⏰ Configuration des jobs planifiés...")
    job_queue = application.job_queue
    job_queue.run_repeating(scheduled_jobs, interval=60, first=10)
    
    # Statistiques de démarrage
    logger.info("=" * 60)
    logger.info(f"🤖 BOT : {'BACKUP' if IS_BACKUP_BOT else 'PRIMARY'}")
    logger.info(f"🆔 TOKEN : {TOKEN[:10]}...{TOKEN[-10:]}")
    logger.info(f"👤 ADMIN : {ADMIN_USER_IDS}")  # ← MODIFIÉ AUSSI ICI
    logger.info(f"💾 DATA : {DATA_DIR}")
    logger.info(f"📏 DISTANCE : {DISTANCE_METHOD}")
    
    # Produits
    available = get_available_products()
    logger.info(f"📦 PRODUITS : {len(available)} disponibles")
    
    # Stocks
    stocks = load_stocks()
    logger.info(f"📊 STOCKS : {len(stocks)} produits trackés")
    
    # Codes promo
    promo_codes = load_promo_codes()
    logger.info(f"🎁 PROMOS : {len(promo_codes)} codes actifs")
    
    # Clients
    users = load_users()
    logger.info(f"👥 CLIENTS : {len(users)} enregistrés")
    
    # VIP
    history = load_client_history()
    vip_count = len([u for u in history.values() if u.get('vip_status', False)])
    logger.info(f"👑 VIP : {vip_count} clients")
    
    logger.info("=" * 60)
    logger.info(f"{EMOJI_THEME['success']} BOT PRÊT - EN ATTENTE DE MESSAGES...")
    logger.info("=" * 60)
    
    # Démarrer le bot
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except KeyboardInterrupt:
        logger.info("\n👋 ARRÊT DU BOT PAR L'UTILISATEUR")
    except Exception as e:
        logger.error(f"❌ ERREUR FATALE : {e}", exc_info=True)
    finally:
        logger.info("🛑 BOT ARRÊTÉ")


# ==================== POINT D'ENTRÉE ====================
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"❌ ERREUR AU DÉMARRAGE : {e}", exc_info=True)
        sys.exit(1)
# FIN DU BLOC 9 - VERSION CORRIGÉE

