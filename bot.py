import os
import sys
import logging
import re
import csv
import math
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps
from collections import defaultdict
from datetime import datetime, timedelta

# ============================================================================
# CONFIGURATION DU LOGGING
# ============================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Réduire les logs verbeux des librairies externes
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# ============================================================================
# CHARGEMENT DES VARIABLES D'ENVIRONNEMENT
# ============================================================================
dotenv_path = Path(__file__).parent / "infos.env"
load_dotenv(dotenv_path)

def validate_environment():
    """Valide que toutes les variables d'environnement nécessaires sont présentes"""
    required_vars = ['TELEGRAM_BOT_TOKEN', 'ADMIN_ID']
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"❌ Variables manquantes dans infos.env: {', '.join(missing)}")
        logger.error("📝 Créez un fichier 'infos.env' avec:")
        logger.error("   TELEGRAM_BOT_TOKEN=votre_token")
        logger.error("   ADMIN_ID=votre_id")
        return False
    
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_id = os.getenv("ADMIN_ID", "").strip()
    
    if not token or ':' not in token or len(token) < 40:
        logger.error("❌ TELEGRAM_BOT_TOKEN invalide (doit contenir ':' et faire plus de 40 caractères)")
        return False
    
    if not admin_id.isdigit():
        logger.error("❌ ADMIN_ID doit être un nombre")
        return False
    
    logger.info("✅ Variables d'environnement validées")
    return True

# Validation AVANT de charger les variables
if not validate_environment():
    logger.error("❌ ARRÊT: Configuration invalide")
    if __name__ == '__main__':
        sys.exit(1)

# Chargement des variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CRYPTO_WALLET = os.getenv("CRYPTO_WALLET", "").strip()
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS", "Chamonix-Mont-Blanc, France").strip()

logger.info(f"✅ Bot Token: {TOKEN[:15]}...")
logger.info(f"✅ Admin ID: {ADMIN_ID}")
logger.info(f"✅ Admin Address: {ADMIN_ADDRESS}")

# ============================================================================
# IMPORTS TELEGRAM
# ============================================================================
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, WebAppInfo
    from telegram.ext import (
        Application, ContextTypes, CallbackQueryHandler,
        ConversationHandler, MessageHandler, CommandHandler, filters
    )
    from telegram.error import NetworkError, TimedOut, Conflict
    logger.info("✅ Modules Telegram importés")
except ImportError as e:
    logger.error(f"❌ Erreur import Telegram: {e}")
    logger.error("👉 Installez: pip install python-telegram-bot")
    sys.exit(1)

# ============================================================================
# IMPORTS GÉOLOCALISATION
# ============================================================================
try:
    from geopy.geocoders import Nominatim
    from geopy.distance import geodesic
    GEOPY_AVAILABLE = True
    logger.info("✅ Module geopy disponible")
except ImportError:
    GEOPY_AVAILABLE = False
    logger.warning("⚠️ Module geopy non disponible (pip install geopy)")

# ============================================================================
# CONFIGURATION GÉNÉRALE
# ============================================================================
USE_WHITELIST = False
AUTHORIZED_USERS = []
AUTO_DELETE_MESSAGES = False  # Désactivé pour éviter les erreurs de permissions

user_message_timestamps = defaultdict(list)
MAX_MESSAGES_PER_MINUTE = 30
RATE_LIMIT_WINDOW = 60
SESSION_TIMEOUT_MINUTES = 30
MAX_QUANTITY_PER_PRODUCT = 100
FRAIS_POSTAL = 10

# ============================================================================
# ÉTATS DE CONVERSATION
# ============================================================================
LANGUE, PAYS, PRODUIT, PILL_SUBCATEGORY, ROCK_SUBCATEGORY, QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(11)

# ============================================================================
# DONNÉES PRODUITS
# ============================================================================
PRODUCT_MAP = {
    "snow": "❄️ COCO",
    "pill": "💊 Exta Pills",
    "olive": "🫒 Hash",
    "clover": "🍀 Weed",
    "rock": "🪨 MDMA, 4MMC"
}

PILL_SUBCATEGORIES = {
    "squid_game": "💊 Squid Game",
    "punisher": "💊 Punisher"
}

ROCK_SUBCATEGORIES = {
    "mdma": "🪨 MDMA",
    "fourmmc": "🪨 4MMC"
}

PRIX_FR = {
    "❄️ Coco": 80,
    "💊 Squid Game": 10,
    "💊 Punisher": 10,
    "🫒 Hash": 7,
    "🍀 Weed": 10,
    "🪨 MDMA": 50,
    "🪨 4MMC": 50
}

PRIX_CH = {
    "❄️ Coco": 100,
    "💊 Squid Game": 15,
    "💊 Punisher": 15,
    "🫒 Hash": 8,
    "🍀 Weed": 12,
    "🪨 MDMA": 70,
    "🪨 4MMC": 70
}

# ============================================================================
# TRADUCTIONS
# ============================================================================
TRANSLATIONS = {
    "fr": {
        "welcome": "🌿 *BIENVENUE* 🌿\n\n⚠️ *IMPORTANT :*\nToutes les conversations doivent être établies en *ÉCHANGE SECRET*.\n\n🙏 *Merci* 💪💚",
        "choose_language": "🌍 *Choisissez votre langue :*",
        "main_menu": "\n\n📱 *MENU PRINCIPAL :*\n\n👇 Choisissez une option :",
        "choose_country": "🌍 *Choisissez votre pays de livraisons :*",
        "choose_product": "🛒 *Choisissez votre produit :*",
        "choose_pill_type": "💊 *Choisissez le type de pilule :*",
        "choose_rock_type": "🪨 *Choisissez le type de crystal :*",
        "enter_quantity": "🔢 *Entrez la quantité désirée :*",
        "enter_address": "📍 *Entrez votre adresse complète :*",
        "choose_delivery": "📦 *Choisissez le type de livraison :*",
        "calculating_distance": "📏 Calcul de la distance en cours...",
        "distance_calculated": "📏 *Distance calculée :* {distance} km\n💶 *Frais de livraison :* {fee}€\n\n{formula}",
        "geocoding_error": "❌ Impossible de localiser l'adresse.",
        "choose_payment": "💳 *Choisissez le mode de paiement :*",
        "order_summary": "✅ *Résumé de votre commande :*",
        "confirm": "✅ Confirmer",
        "cancel": "❌ Annuler",
        "order_confirmed": "✅ *Commande confirmée !*\n\nMerci pour votre commande.\nVous serez contacté prochainement. 📞",
        "order_cancelled": "❌ *Commande annulée.*",
        "add_more": "➕ Ajouter un produit",
        "proceed": "✅ Valider le panier",
        "invalid_quantity": "❌ Veuillez entrer un nombre valide entre 1 et {max}.",
        "cart_title": "🛒 *Votre panier :*",
        "start_order": "🛒 Commander",
        "informations": "ℹ️ Informations",
        "contact": "📞 Contact",
        "back": "🔙 Retour",
        "price_menu": "🏴‍☠️ Carte du Pirate",
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Suisse",
        "postal": "✉️📭 Postale (+10€)",
        "express": "🎁⚡ Express",
        "cash": "💵 Espèces",
        "crypto": "₿ Crypto",
        "total": "💰 *Total :*",
        "delivery_fee": "📦 *Frais de livraison :*",
        "subtotal": "💵 *Sous-total produits :*"
    }
}

# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def tr(user_data, key):
    """Récupère une traduction"""
    lang = user_data.get("langue", "fr")
    translation = TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)
    if "{max}" in translation:
        translation = translation.replace("{max}", str(MAX_QUANTITY_PER_PRODUCT))
    return translation

def sanitize_input(text: str, max_length: int = 200) -> str:
    """Nettoie et sécurise les entrées utilisateur"""
    if not text:
        return ""
    text = text.strip()[:max_length]
    text = re.sub(r'[<>{}[\]\\`|]', '', text)
    text = re.sub(r'[\x00-\x1F\x7F]', '', text)
    return text

def is_authorized(user_id: int) -> bool:
    """Vérifie si un utilisateur est autorisé"""
    if not USE_WHITELIST:
        return True
    return user_id in AUTHORIZED_USERS

def check_rate_limit(user_id: int) -> bool:
    """Vérifie le rate limiting"""
    now = datetime.now()
    user_message_timestamps[user_id] = [
        ts for ts in user_message_timestamps[user_id]
        if now - ts < timedelta(seconds=RATE_LIMIT_WINDOW)
    ]
    
    if len(user_message_timestamps[user_id]) >= MAX_MESSAGES_PER_MINUTE:
        logger.warning(f"⚠️ Rate limit dépassé pour user {user_id}")
        return False
    
    user_message_timestamps[user_id].append(now)
    return True

def check_session_timeout(user_data: dict) -> bool:
    """Vérifie si la session a expiré"""
    last_activity = user_data.get('last_activity')
    if not last_activity:
        return False
    return datetime.now() - last_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES)

def update_last_activity(user_data: dict):
    """Met à jour l'heure de dernière activité"""
    user_data['last_activity'] = datetime.now()

async def delete_user_message(update: Update):
    """Supprime le message de l'utilisateur si activé"""
    if not AUTO_DELETE_MESSAGES or not update.message:
        return
    
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Impossible de supprimer message utilisateur: {e}")

async def delete_last_bot_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Supprime le dernier message du bot si activé"""
    if not AUTO_DELETE_MESSAGES or 'last_bot_message_id' not in context.user_data:
        return
    
    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=context.user_data['last_bot_message_id']
        )
    except Exception as e:
        logger.debug(f"Impossible de supprimer message bot: {e}")

def save_bot_message_id(context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Sauvegarde l'ID du message du bot"""
    if AUTO_DELETE_MESSAGES:
        context.user_data['last_bot_message_id'] = message_id

def calculate_delivery_fee(delivery_type: str, distance: int = 0, subtotal: float = 0) -> float:
    """Calcule les frais de livraison"""
    if delivery_type == "postal":
        return FRAIS_POSTAL
    elif delivery_type == "express":
        base_fee = (distance * 2) + (subtotal * 0.03)
        return math.ceil(base_fee / 10) * 10
    return 0

async def get_distance_between_addresses(address1: str, address2: str) -> tuple:
    """Calcule la distance entre deux adresses"""
    if not GEOPY_AVAILABLE:
        return (0, False, "Module de géolocalisation non disponible")
    
    try:
        geolocator = Nominatim(user_agent="telegram_shop_bot")
        location1 = geolocator.geocode(address1, timeout=10)
        location2 = geolocator.geocode(address2, timeout=10)
        
        if not location1:
            return (0, False, f"Adresse de départ introuvable: {address1}")
        if not location2:
            return (0, False, f"Adresse de livraison introuvable: {address2}")
        
        coords1 = (location1.latitude, location1.longitude)
        coords2 = (location2.latitude, location2.longitude)
        
        distance = geodesic(coords1, coords2).kilometers
        distance_rounded = round(distance, 1)
        
        logger.info(f"📏 Distance calculée: {distance_rounded} km")
        return (distance_rounded, True, None)
    except Exception as e:
        logger.error(f"❌ Erreur calcul distance: {e}")
        return (0, False, str(e))

def calculate_total(cart, country, delivery_type: str = None, distance: int = 0):
    """Calcule le total de la commande"""
    prix_table = PRIX_FR if country == "FR" else PRIX_CH
    subtotal = sum(prix_table[item["produit"]] * item["quantite"] for item in cart)
    
    if delivery_type:
        delivery_fee = calculate_delivery_fee(delivery_type, distance, subtotal)
        return subtotal + delivery_fee, subtotal, delivery_fee
    
    return subtotal, subtotal, 0

def format_cart(cart, user_data):
    """Formate l'affichage du panier"""
    if not cart:
        return ""
    cart_text = f"\n{tr(user_data, 'cart_title')}\n"
    for item in cart:
        cart_text += f"• {item['produit']} x {item['quantite']}\n"
    return cart_text

def save_order_to_csv(order_data: dict):
    """Sauvegarde une commande dans le CSV"""
    csv_path = Path(__file__).parent / "orders.csv"
    file_exists = csv_path.exists()
    
    try:
        with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'date', 'order_id', 'user_id', 'username', 'first_name',
                'products', 'country', 'address', 'delivery_type', 
                'distance_km', 'payment_method', 'subtotal', 'delivery_fee', 
                'total', 'status'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(order_data)
        
        logger.info(f"✅ Commande sauvegardée: {order_data['order_id']}")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde CSV: {e}")
        return False

# ============================================================================
# DÉCORATEURS DE SÉCURITÉ
# ============================================================================

def security_check(func):
    """Décorateur pour vérifier la sécurité"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        # Vérification autorisation
        if not is_authorized(user_id):
            logger.warning(f"❌ Utilisateur non autorisé: {user_id}")
            return ConversationHandler.END
        
        # Vérification rate limit
        if not check_rate_limit(user_id):
            try:
                if update.message:
                    await update.message.reply_text("⚠️ Trop de messages. Attendez quelques secondes.")
                elif update.callback_query:
                    await update.callback_query.answer("⚠️ Trop rapide!", show_alert=True)
            except:
                pass
            return
        
        # Vérification timeout session
        if check_session_timeout(context.user_data):
            logger.info(f"⏱️ Session expirée pour user {user_id}")
            context.user_data.clear()
            try:
                if update.message:
                    await update.message.reply_text("⏱️ Session expirée. Utilisez /start")
                elif update.callback_query:
                    await update.callback_query.message.reply_text("⏱️ Session expirée. Utilisez /start")
            except:
                pass
            return ConversationHandler.END
        
        update_last_activity(context.user_data)
        return await func(update, context)
    return wrapper

def error_handler(func):
    """Décorateur pour gérer les erreurs"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            user_id = update.effective_user.id if update.effective_user else "Unknown"
            logger.error(f"❌ Erreur dans {func.__name__} (User {user_id}): {e}", exc_info=True)
            
            try:
                if update.callback_query:
                    await update.callback_query.answer("❌ Erreur technique")
                    await update.callback_query.message.reply_text(
                        "❌ Une erreur s'est produite.\nUtilisez /start pour recommencer."
                    )
                elif update.message:
                    await update.message.reply_text(
                        "❌ Une erreur s'est produite.\nUtilisez /start pour recommencer."
                    )
            except Exception as reply_error:
                logger.error(f"❌ Impossible d'envoyer message d'erreur: {reply_error}")
            
            return ConversationHandler.END
    return wrapper

# ============================================================================
# HANDLERS DE COMMANDES
# ============================================================================

@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Point d'entrée du bot"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Inconnu"
    logger.info(f"🚀 /start par User {user_id} (@{username})")
    
    # Réinitialiser les données utilisateur
    context.user_data.clear()
    update_last_activity(context.user_data)
    
    # Vérifier l'autorisation
    if not is_authorized(user_id):
        logger.warning(f"❌ Utilisateur non autorisé: {user_id}")
        await update.message.reply_text("❌ Accès non autorisé.")
        return ConversationHandler.END
    
    # Vérifier le rate limit
    if not check_rate_limit(user_id):
        logger.warning(f"⚠️ Rate limit dépassé: {user_id}")
        await update.message.reply_text("⚠️ Trop de messages. Attendez quelques secondes.")
        return
    
    # Message de bienvenue
    welcome_text = "🌍 *Choisissez votre langue / Select your language*"
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
    ]
    
    # Supprimer le message /start si activé
    await delete_user_message(update)
    
    # Envoyer le message
    try:
        sent_message = await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        save_bot_message_id(context, sent_message.message_id)
        logger.info(f"✅ /start envoyé avec succès à {user_id}")
        
        return LANGUE
    except Exception as e:
        logger.error(f"❌ Erreur envoi message start: {e}")
        raise

@security_check
@error_handler
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit la langue de l'utilisateur"""
    query = update.callback_query
    await query.answer()
    
    lang_code = query.data.replace("lang_", "")
    context.user_data['langue'] = lang_code
    
    logger.info(f"🌍 Langue sélectionnée: {lang_code} par {query.from_user.id}")
    
    welcome_text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "price_menu"), callback_data="price_menu")]
    ]
    
    await query.message.edit_text(
        text=welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return PAYS

@security_check
@error_handler
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la navigation dans le menu principal"""
    query = update.callback_query
    await query.answer()
    
    if 'langue' not in context.user_data:
        context.user_data['langue'] = 'fr'
    
    if query.data == "start_order":
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
            [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")]
        ]
        text = tr(context.user_data, "choose_country")
        
    elif query.data == "price_menu":
        text = "🏴‍☠️ *CARTE DU PIRATE*\n\n"
        text += "🇫🇷 *France:*\n"
        text += "❄️ Coco: 80€/g\n"
        text += "💊 Pills: 10€/unité\n"
        text += "🫒 Hash: 7€/g\n"
        text += "🍀 Weed: 10€/g\n"
        text += "🪨 MDMA/4MMC: 50€/g\n\n"
        text += "🇨🇭 *Suisse:*\n"
        text += "❄️ Coco: 100€/g\n"
        text += "💊 Pills: 15€/unité\n"
        text += "🫒 Hash: 8€/g\n"
        text += "🍀 Weed: 12€/g\n"
        text += "🪨 MDMA/4MMC: 70€/g"
        
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")]
        ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PAYS

@security_check
@error_handler
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le choix du pays"""
    query = update.callback_query
    await query.answer()
    
    country_code = query.data.replace("country_", "")
    context.user_data['pays'] = country_code
    context.user_data['cart'] = []
    
    logger.info(f"🌍 Pays sélectionné: {country_code} par {query.from_user.id}")
    
    keyboard = [
        [InlineKeyboardButton("❄️ COCO", callback_data="product_snow")],
        [InlineKeyboardButton("💊 Pills", callback_data="product_pill")],
        [InlineKeyboardButton("🫒 Hash", callback_data="product_olive")],
        [InlineKeyboardButton("🍀 Weed", callback_data="product_clover")],
        [InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")]
    ]
    
    await query.message.edit_text(
        tr(context.user_data, "choose_product"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return PRODUIT

@security_check
@error_handler
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le choix du produit"""
    query = update.callback_query
    await query.answer()
    
    product_code = query.data.replace("product_", "")
    
    # Sous-catégories pour les pilules
    if product_code == "pill":
        keyboard = [
            [InlineKeyboardButton("💊 Squid Game", callback_data="pill_squid_game")],
            [InlineKeyboardButton("💊 Punisher", callback_data="pill_punisher")]
        ]
        await query.message.edit_text(
            tr(context.user_data, "choose_pill_type"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return PILL_SUBCATEGORY
    
    # Sous-catégories pour les crystaux
    elif product_code == "rock":
        keyboard = [
            [InlineKeyboardButton("🪨 MDMA", callback_data="rock_mdma")],
            [InlineKeyboardButton("🪨 4MMC", callback_data="rock_fourmmc")]
        ]
        await query.message.edit_text(
            tr(context.user_data, "choose_rock_type"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ROCK_SUBCATEGORY
    
    # Produits directs (sans sous-catégorie)
    product_names = {
        "snow": "❄️ Coco",
        "olive": "🫒 Hash",
        "clover": "🍀 Weed"
    }
    
    context.user_data['current_product'] = product_names.get(product_code, product_code)
    logger.info(f"🛒 Produit sélectionné: {context.user_data['current_product']} par {query.from_user.id}")
    
    text = f"✅ Produit : {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}"
    await query.message.edit_text(text, parse_mode='Markdown')
    
    return QUANTITE

@security_check
@error_handler
async def choix_pill_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le choix de la sous-catégorie de pilules"""
    query = update.callback_query
    await query.answer()
    
    pill_type = query.data.replace("pill_", "")
    product_name = PILL_SUBCATEGORIES.get(pill_type, "💊")
    context.user_data['current_product'] = product_name
    
    logger.info(f"💊 Pilule sélectionnée: {product_name} par {query.from_user.id}")
    
    text = f"✅ Produit : {product_name}\n\n{tr(context.user_data, 'enter_quantity')}"
    await query.message.edit_text(text, parse_mode='Markdown')
    
    return QUANTITE

@security_check
@error_handler
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la saisie de la quantité"""
    qty = sanitize_input(update.message.text, max_length=10)
    user_id = update.effective_user.id
    
    # Supprimer les messages si activé
    await delete_user_message(update)
    await delete_last_bot_message(context, update.effective_chat.id)
    
    # Validation de la quantité
    if not qty.isdigit():
        sent_message = await update.message.reply_text(
            tr(context.user_data, "invalid_quantity"),
            parse_mode='Markdown'
        )
        save_bot_message_id(context, sent_message.message_id)
        return QUANTITE
    
    qty_int = int(qty)
    if qty_int <= 0 or qty_int > MAX_QUANTITY_PER_PRODUCT:
        sent_message = await update.message.reply_text(
            tr(context.user_data, "invalid_quantity"),
            parse_mode='Markdown'
        )
        save_bot_message_id(context, sent_message.message_id)
        return QUANTITE
    
    # Ajouter au panier
    context.user_data['cart'].append({
        "produit": context.user_data['current_product'],
        "quantite": qty_int
    })
    
    logger.info(f"🛒 Ajout panier: {context.user_data['current_product']} x{qty_int} par {user_id}")
    
    # Afficher le panier
    cart_summary = format_cart(context.user_data['cart'], context.user_data)
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "add_more"), callback_data="add_more")],
        [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")]
    ]
    
    sent_message = await update.message.reply_text(
        cart_summary,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    save_bot_message_id(context, sent_message.message_id)
    
    return CART_MENU

@security_check
@error_handler
async def cart_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le menu du panier"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_more":
        # Retour à la sélection de produits
        keyboard = [
            [InlineKeyboardButton("❄️ COCO", callback_data="product_snow")],
            [InlineKeyboardButton("💊 Pills", callback_data="product_pill")],
            [InlineKeyboardButton("🫒 Hash", callback_data="product_olive")],
            [InlineKeyboardButton("🍀 Weed", callback_data="product_clover")],
            [InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")]
        ]
        await query.message.edit_text(
            tr(context.user_data, "choose_product"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return PRODUIT
        
    elif query.data == "proceed_checkout":
        # Passer à l'adresse
        text = tr(context.user_data, 'enter_address')
        await query.message.edit_text(text, parse_mode='Markdown')
        return ADRESSE

@security_check
@error_handler
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la saisie de l'adresse"""
    # Si c'est un callback (retour)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        text = tr(context.user_data, 'enter_address')
        await query.message.edit_text(text, parse_mode='Markdown')
        return ADRESSE
    
    # Sinon c'est un message texte
    address = sanitize_input(update.message.text, max_length=300)
    user_id = update.effective_user.id
    
    await delete_user_message(update)
    await delete_last_bot_message(context, update.effective_chat.id)
    
    # Validation de l'adresse
    if len(address) < 15:
        sent_message = await update.message.reply_text(
            "❌ Adresse trop courte (minimum 15 caractères)",
            parse_mode='Markdown'
        )
        save_bot_message_id(context, sent_message.message_id)
        return ADRESSE
    
    context.user_data['adresse'] = address
    logger.info(f"📍 Adresse saisie par {user_id}: {address[:30]}...")
    
    # Choix du mode de livraison
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "postal"), callback_data="delivery_postal")],
        [InlineKeyboardButton(tr(context.user_data, "express"), callback_data="delivery_express")]
    ]
    
    sent_message = await update.message.reply_text(
        tr(context.user_data, "choose_delivery"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    save_bot_message_id(context, sent_message.message_id)
    
    return LIVRAISON

@security_check
@error_handler
async def choix_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le choix du mode de livraison"""
    query = update.callback_query
    await query.answer()
    
    delivery_type = query.data.replace("delivery_", "")
    context.user_data['livraison'] = delivery_type
    
    logger.info(f"📦 Livraison choisie: {delivery_type} par {query.from_user.id}")
    
    # Si livraison express, calculer la distance
    if delivery_type == "express":
        client_address = context.user_data.get('adresse', '')
        
        # Message de calcul en cours
        await query.message.edit_text(
            tr(context.user_data, "calculating_distance"),
            parse_mode='Markdown'
        )
        
        # Calculer la distance
        distance_km, success, error_msg = await get_distance_between_addresses(
            ADMIN_ADDRESS,
            client_address
        )
        
        # Si erreur de géolocalisation
        if not success:
            error_text = tr(context.user_data, "geocoding_error")
            if error_msg:
                error_text += f"\n\n⚠️ {error_msg}"
            
            keyboard = [[InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_address")]]
            await query.message.edit_text(
                error_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return LIVRAISON
        
        # Calculer les frais
        cart = context.user_data['cart']
        country = context.user_data['pays']
        subtotal, _, _ = calculate_total(cart, country)
        delivery_fee = calculate_delivery_fee("express", distance_km, subtotal)
        
        context.user_data['distance'] = distance_km
        
        # Formule de calcul détaillée
        formula_detail = f"📊 Calcul: {distance_km} km × 2€ = {distance_km * 2}€"
        
        distance_text = tr(context.user_data, "distance_calculated").format(
            distance=distance_km,
            fee=delivery_fee,
            formula=formula_detail
        )
        
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "cash"), callback_data="payment_cash")],
            [InlineKeyboardButton(tr(context.user_data, "crypto"), callback_data="payment_crypto")]
        ]
        
        await query.message.edit_text(
            distance_text + "\n\n" + tr(context.user_data, "choose_payment"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return PAIEMENT
    
    # Si livraison postale
    else:
        context.user_data['distance'] = 0
        
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "cash"), callback_data="payment_cash")],
            [InlineKeyboardButton(tr(context.user_data, "crypto"), callback_data="payment_crypto")]
        ]
        
        await query.message.edit_text(
            tr(context.user_data, "choose_payment"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return PAIEMENT

@security_check
@error_handler
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le choix du mode de paiement"""
    query = update.callback_query
    await query.answer()
    
    payment_type = query.data.replace("payment_", "")
    context.user_data['paiement'] = payment_type
    
    logger.info(f"💳 Paiement choisi: {payment_type} par {query.from_user.id}")
    
    # Calculer le total
    cart = context.user_data['cart']
    country = context.user_data['pays']
    delivery_type = context.user_data['livraison']
    distance = context.user_data.get('distance', 0)
    
    total, subtotal, delivery_fee = calculate_total(cart, country, delivery_type, distance)
    
    # Résumé de la commande
    summary = f"{tr(context.user_data, 'order_summary')}\n\n"
    summary += format_cart(cart, context.user_data)
    summary += f"\n{tr(context.user_data, 'subtotal')} {subtotal}€\n"
    summary += f"{tr(context.user_data, 'delivery_fee')} {delivery_fee}€\n"
    summary += f"{tr(context.user_data, 'total')} *{total}€*\n\n"
    summary += f"📍 {context.user_data['adresse']}\n"
    summary += f"📦 {delivery_type.title()}\n"
    summary += f"💳 {payment_type.title()}"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "confirm"), callback_data="confirm_order")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    
    await query.message.edit_text(
        summary,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return CONFIRMATION

@security_check
@error_handler
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la confirmation de la commande"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_order":
        user = update.effective_user
        
        # Récupérer les données
        cart = context.user_data['cart']
        country = context.user_data['pays']
        delivery_type = context.user_data['livraison']
        distance = context.user_data.get('distance', 0)
        
        # Calculer le total
        total, subtotal, delivery_fee = calculate_total(cart, country, delivery_type, distance)
        
        # Générer l'ID de commande
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user.id}"
        
        # Formater les produits pour le CSV
        products_str = "; ".join([f"{item['produit']} x{item['quantite']}" for item in cart])
        
        # Préparer les données de commande
        order_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'order_id': order_id,
            'user_id': user.id,
            'username': user.username or "N/A",
            'first_name': user.first_name or "N/A",
            'products': products_str,
            'country': country,
            'address': context.user_data['adresse'],
            'delivery_type': delivery_type,
            'distance_km': distance if delivery_type == "express" else 0,
            'payment_method': context.user_data['paiement'],
            'subtotal': f"{subtotal:.2f}",
            'delivery_fee': f"{delivery_fee:.2f}",
            'total': f"{total:.2f}",
            'status': 'En attente validation'
        }
        
        # Sauvegarder dans le CSV
        save_order_to_csv(order_data)
        
        logger.info(f"✅ Commande confirmée: {order_id}")
        
        # Message pour l'admin
        admin_message = f"🆕 *NOUVELLE COMMANDE*\n\n"
        admin_message += f"📋 `{order_id}`\n"
        admin_message += f"👤 {user.first_name}"
        if user.username:
            admin_message += f" (@{user.username})"
        admin_message += f"\n🆔 ID: `{user.id}`\n\n"
        admin_message += format_cart(cart, context.user_data)
        admin_message += f"\n💵 Sous-total: {subtotal}€\n"
        admin_message += f"📦 Livraison: {delivery_fee}€\n"
        admin_message += f"💰 *Total: {total}€*\n\n"
        admin_message += f"📍 {context.user_data['adresse']}\n"
        admin_message += f"📦 {delivery_type.title()}\n"
        admin_message += f"💳 {context.user_data['paiement'].title()}"
        
        if delivery_type == "express":
            admin_message += f"\n📏 Distance: {distance} km"
        
        # Bouton de validation pour l'admin
        admin_keyboard = [
            [InlineKeyboardButton(
                "✅ Valider la livraison", 
                callback_data=f"admin_validate_{order_id}_{user.id}"
            )]
        ]
        
        # Envoyer à l'admin
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message,
                reply_markup=InlineKeyboardMarkup(admin_keyboard),
                parse_mode='Markdown'
            )
            logger.info(f"✅ Notification admin envoyée pour {order_id}")
        except Exception as e:
            logger.error(f"❌ Erreur envoi admin: {e}")
        
        # Message de confirmation pour le client
        confirmation_text = tr(context.user_data, "order_confirmed")
        confirmation_text += f"\n\n📋 Commande: `{order_id}`"
        confirmation_text += f"\n💰 Montant: {total:.2f}€"
        
        await query.message.edit_text(
            confirmation_text,
            parse_mode='Markdown'
        )
        
        # Nettoyer les données utilisateur
        context.user_data.clear()
        return ConversationHandler.END
    
    elif query.data == "cancel":
        return await cancel(update, context)

@security_check
@error_handler
async def admin_validation_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la validation de livraison par l'admin"""
    query = update.callback_query
    await query.answer()
    
    # Vérifier que c'est bien l'admin
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Action non autorisée", show_alert=True)
        return
    
    # Extraire les données du callback
    data_parts = query.data.split("_")
    if len(data_parts) >= 4:
        order_id = "_".join(data_parts[2:-1])
        client_id = int(data_parts[-1])
    else:
        await query.answer("❌ Erreur de données", show_alert=True)
        return
    
    logger.info(f"✅ Admin valide la commande {order_id}")
    
    # Mettre à jour le statut dans le CSV
    csv_path = Path(__file__).parent / "orders.csv"
    if csv_path.exists():
        try:
            rows = []
            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if row['order_id'] == order_id:
                        row['status'] = 'Livraison validée'
                    rows.append(row)
            
            if rows:
                with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                
                logger.info(f"✅ CSV mis à jour pour {order_id}")
        except Exception as e:
            logger.error(f"❌ Erreur mise à jour CSV: {e}")
    
    # Mettre à jour le message admin
    try:
        new_text = query.message.text + "\n\n✅ *LIVRAISON VALIDÉE*"
        await query.message.edit_text(new_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ Erreur édition message admin: {e}")
    
    # Notifier le client
    try:
        client_message = f"✅ *Livraison confirmée !*\n\n"
        client_message += f"📋 Commande: `{order_id}`\n\n"
        client_message += f"Merci pour votre confiance ! 💚"
        
        await context.bot.send_message(
            chat_id=client_id,
            text=client_message,
            parse_mode='Markdown'
        )
        logger.info(f"✅ Client {client_id} notifié pour {order_id}")
    except Exception as e:
        logger.error(f"❌ Erreur notification client: {e}")
    
    await query.answer("✅ Livraison validée !", show_alert=True)

@security_check
@error_handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annule la commande en cours"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"❌ Commande annulée par {query.from_user.id}")
    
    await query.message.edit_text(
        tr(context.user_data, "order_cancelled"),
        parse_mode='Markdown'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# ============================================================================
# GESTION GLOBALE DES ERREURS
# ============================================================================

async def error_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire global d'erreurs"""
    logger.error(f"❌ EXCEPTION GLOBALE: {context.error}", exc_info=context.error)
    
    if update and update.effective_user:
        logger.error(f"   User ID: {update.effective_user.id}")
    
    if update and update.message:
        logger.error(f"   Message: {update.message.text}")

# ============================================================================
# CONFIGURATION WEBAPP MENU
# ============================================================================

async def setup_webapp_menu(application):
    """Configure le menu WebApp"""
    try:
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="🏴‍☠️ Carte du Pirate",
                web_app=WebAppInfo(url="https://carte-du-pirate.onrender.com/catalogue")
            )
        )
        logger.info("✅ Menu WebApp configuré")
    except Exception as e:
        logger.warning(f"⚠️ Erreur config WebApp menu: {e}")

# ============================================================================
# FONCTION PRINCIPALE
# ============================================================================

def main():
    """Initialise et configure le bot"""
    logger.info("=" * 60)
    logger.info("🚀 DÉMARRAGE DU BOT TELEGRAM")
    logger.info("=" * 60)
    logger.info(f"🔑 Token: {TOKEN[:20]}...")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    logger.info(f"📍 Admin Address: {ADMIN_ADDRESS}")
    logger.info(f"🔒 Whitelist: {'Activée' if USE_WHITELIST else 'Désactivée'}")
    logger.info(f"🗑️ Auto-delete: {'Activé' if AUTO_DELETE_MESSAGES else 'Désactivé'}")
    logger.info(f"📍 Geopy: {'Disponible' if GEOPY_AVAILABLE else 'Non disponible'}")
    logger.info("=" * 60)
    
    # Vérifier le token
    if not TOKEN or TOKEN == "":
        logger.error("❌ TOKEN vide ou invalide!")
        logger.error("👉 Vérifiez votre fichier infos.env")
        sys.exit(1)
    
    # Créer l'application
    try:
        application = Application.builder().token(TOKEN).build()
        logger.info("✅ Application créée")
    except Exception as e:
        logger.error(f"❌ Erreur création application: {e}")
        sys.exit(1)
    
    # Créer le gestionnaire de conversation
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command)
        ],
        states={
            LANGUE: [
                CallbackQueryHandler(set_langue, pattern='^lang_')
            ],
            PAYS: [
                CallbackQueryHandler(menu_navigation, pattern='^(start_order|price_menu)'),
                CallbackQueryHandler(choix_pays, pattern='^country_')
            ],
            PRODUIT: [
                CallbackQueryHandler(choix_produit, pattern='^product_'),
                CallbackQueryHandler(cancel, pattern='^cancel')
            ],
            PILL_SUBCATEGORY: [
                CallbackQueryHandler(choix_pill_subcategory, pattern='^pill_')
            ],
            ROCK_SUBCATEGORY: [
                CallbackQueryHandler(choix_rock_subcategory, pattern='^rock_')
            ],
            QUANTITE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)
            ],
            CART_MENU: [
                CallbackQueryHandler(cart_menu, pattern='^(add_more|proceed_checkout)')
            ],
            ADRESSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse),
                CallbackQueryHandler(saisie_adresse, pattern='^back_to_address')
            ],
            LIVRAISON: [
                CallbackQueryHandler(choix_livraison, pattern='^delivery_')
            ],
            PAIEMENT: [
                CallbackQueryHandler(choix_paiement, pattern='^payment_')
            ],
            CONFIRMATION: [
                CallbackQueryHandler(confirmation, pattern='^(confirm_order|cancel)')
            ]
        },
        fallbacks=[
            CommandHandler('start', start_command),
            CallbackQueryHandler(cancel, pattern='^cancel')
        ],
        per_chat=True,
        per_user=True,
        per_message=False
    )
    
    # Ajouter les handlers
    application.add_handler(conv_handler)
    application.add_handler(
        CallbackQueryHandler(admin_validation_livraison, pattern='^admin_validate_')
    )
    application.add_error_handler(error_callback)
    
    logger.info("✅ Handlers configurés")
    logger.info("✅ Bot prêt à démarrer")
    logger.info("=" * 60)
    
    return application

# ============================================================================
# INITIALISATION
# ============================================================================

# Créer l'application bot
bot_application = main()

# Configurer le WebApp menu
import asyncio
try:
    # Essayer avec asyncio.run()
    asyncio.run(setup_webapp_menu(bot_application))
    logger.info("✅ WebApp menu configuré (asyncio.run)")
except RuntimeError:
    # Si l'event loop existe déjà (mode import par app.py)
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(setup_webapp_menu(bot_application))
        logger.info("✅ WebApp menu configuré (event loop existant)")
    except Exception as e:
        logger.warning(f"⚠️ WebApp menu non configuré: {e}")
except Exception as e:
    logger.warning(f"⚠️ WebApp menu non configuré: {e}")

# ============================================================================
# POINT D'ENTRÉE
# ============================================================================

if __name__ == '__main__':
    logger.warning("=" * 60)
    logger.warning("⚠️ CE FICHIER NE DOIT PAS ÊTRE EXÉCUTÉ DIRECTEMENT")
    logger.warning("=" * 60)
    logger.warning("👉 Utilisez: python app.py")
    logger.warning("👉 Ce fichier doit être importé par app.py")
    logger.warning("=" * 60)
    sys.exit(0)}\n\n{tr(context.user_data, 'enter_quantity')}"
    await query.message.edit_text(text, parse_mode='Markdown')
    
    return QUANTITE

@security_check
@error_handler
async def choix_rock_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le choix de la sous-catégorie de crystaux"""
    query = update.callback_query
    await query.answer()
    
    rock_type = query.data.replace("rock_", "")
    product_name = ROCK_SUBCATEGORIES.get(rock_type, "🪨")
    context.user_data['current_product'] = product_name
    
    logger.info(f"🪨 Crystal sélectionné: {product_name} par {query.from_user.id}")
    
    text = f"✅ Produit : {product_name
