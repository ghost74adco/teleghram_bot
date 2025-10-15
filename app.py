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

# Configuration du Logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# Chargement des variables d'environnement
for env_file in ['.env', 'infos.env']:
    dotenv_path = Path(__file__).parent / env_file
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
        logger.info(f"✅ Variables chargées: {env_file}")
        break
else:
    load_dotenv()
    logger.info("✅ Variables système chargées")

# Charger les variables avec tous les alias possibles
TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or 
         os.getenv("BOT_TOKEN") or 
         os.getenv("TELEGRAM_TOKEN") or "").strip()

ADMIN_ID_STR = (os.getenv("ADMIN_ID") or 
                os.getenv("ADMIN_USER_IDS") or 
                os.getenv("TELEGRAM_ADMIN_ID") or "").strip()

ADMIN_ADDRESS = (os.getenv("ADMIN_ADDRESS") or 
                 "858 Rte du Chef Lieu, 74250 Fillinges").strip()

# Validation
if not TOKEN or ':' not in TOKEN:
    logger.error("❌ TOKEN invalide!")
    sys.exit(1)

if not ADMIN_ID_STR or not ADMIN_ID_STR.isdigit():
    logger.error(f"❌ ADMIN_ID invalide: {ADMIN_ID_STR}")
    sys.exit(1)

ADMIN_ID = int(ADMIN_ID_STR)
logger.info(f"✅ Bot configuré - Token: {TOKEN[:15]}...{TOKEN[-5:]}")
logger.info(f"✅ Admin ID: {ADMIN_ID}")

# Imports Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ContextTypes, CallbackQueryHandler,
    ConversationHandler, MessageHandler, CommandHandler, filters
)

# Géolocalisation
try:
    from geopy.geocoders import Nominatim
    from geopy.distance import geodesic
    GEOPY_AVAILABLE = True
    logger.info("✅ Géolocalisation disponible")
except ImportError:
    GEOPY_AVAILABLE = False
    logger.warning("⚠️ Géolocalisation non disponible")

# Configuration
USE_WHITELIST = False
AUTHORIZED_USERS = []
user_message_timestamps = defaultdict(list)
MAX_MESSAGES_PER_MINUTE = 30
RATE_LIMIT_WINDOW = 60
MAX_QUANTITY_PER_PRODUCT = 100
FRAIS_POSTAL = 10

# États de conversation
LANGUE, PAYS, PRODUIT, PILL_SUBCATEGORY, ROCK_SUBCATEGORY, QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(11)

# Produits
PILL_SUBCATEGORIES = {"squid_game": "💊 Squid Game", "punisher": "💊 Punisher"}
ROCK_SUBCATEGORIES = {"mdma": "🪨 MDMA", "fourmmc": "🪨 4MMC"}

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

# Traductions
TRANSLATIONS = {
    "fr": {
        "welcome": "🌿 *BIENVENUE* 🌿\n\n⚠️ *IMPORTANT :*\nToutes les conversations doivent être établies en *ÉCHANGE SECRET*.\n\n🙏 *Merci* 💪💚",
        "main_menu": "\n\n📱 *MENU PRINCIPAL :*\n\n👇 Choisissez une option :",
        "choose_country": "🌍 *Choisissez votre pays de livraison :*",
        "choose_product": "🛒 *Choisissez votre produit :*",
        "choose_pill_type": "💊 *Choisissez le type de pilule :*",
        "choose_rock_type": "🪨 *Choisissez le type de crystal :*",
        "enter_quantity": "🔢 *Entrez la quantité désirée :*",
        "enter_address": "📍 *Entrez votre adresse complète :*",
        "choose_delivery": "📦 *Choisissez le type de livraison :*",
        "calculating_distance": "📏 Calcul de la distance...",
        "distance_calculated": "📏 *Distance :* {distance} km\n💶 *Frais :* {fee}€",
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
        "price_menu": "🏴‍☠️ Carte du Pirate",
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Suisse",
        "postal": "✉️ Postale (+10€)",
        "express": "⚡ Express",
        "cash": "💵 Espèces",
        "crypto": "₿ Crypto",
        "total": "💰 *Total :*",
        "delivery_fee": "📦 *Frais de livraison :*",
        "subtotal": "💵 *Sous-total produits :*",
        "back": "🔙 Retour"
    }
}

def tr(user_data, key):
    """Récupère une traduction"""
    lang = user_data.get("langue", "fr")
    translation = TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)
    if "{max}" in translation:
        translation = translation.replace("{max}", str(MAX_QUANTITY_PER_PRODUCT))
    return translation

def sanitize_input(text: str, max_length: int = 200) -> str:
    """Nettoie les entrées utilisateur"""
    if not text:
        return ""
    text = text.strip()[:max_length]
    text = re.sub(r'[<>{}[\]\\`|]', '', text)
    return text

def is_authorized(user_id: int) -> bool:
    """Vérifie si un utilisateur est autorisé"""
    return not USE_WHITELIST or user_id in AUTHORIZED_USERS

def check_rate_limit(user_id: int) -> bool:
    """Vérifie le rate limiting"""
    now = datetime.now()
    user_message_timestamps[user_id] = [
        ts for ts in user_message_timestamps[user_id]
        if now - ts < timedelta(seconds=RATE_LIMIT_WINDOW)
    ]
    if len(user_message_timestamps[user_id]) >= MAX_MESSAGES_PER_MINUTE:
        logger.warning(f"⚠️ Rate limit dépassé: user {user_id}")
        return False
    user_message_timestamps[user_id].append(now)
    return True

def update_last_activity(user_data: dict):
    """Met à jour l'activité"""
    user_data['last_activity'] = datetime.now()

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
        
        if not location1 or not location2:
            return (0, False, "Adresse introuvable")
        
        coords1 = (location1.latitude, location1.longitude)
        coords2 = (location2.latitude, location2.longitude)
        distance = round(geodesic(coords1, coords2).kilometers, 1)
        
        logger.info(f"📏 Distance calculée: {distance} km")
        return (distance, True, None)
    except Exception as e:
        logger.error(f"❌ Erreur géolocalisation: {e}")
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
        logger.error(f"❌ Erreur CSV: {e}")
        return False

def error_handler(func):
    """Gère les erreurs"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            user_id = update.effective_user.id if update.effective_user else "Unknown"
            logger.error(f"❌ Erreur dans {func.__name__} (User {user_id}): {e}", exc_info=True)
            
            try:
                if update.callback_query:
                    await update.callback_query.answer("❌ Erreur")
                    await update.callback_query.message.reply_text("❌ Erreur. Utilisez /start")
                elif update.message:
                    await update.message.reply_text("❌ Erreur. Utilisez /start")
            except:
                pass
            
            return ConversationHandler.END
    return wrapper

# ============================================================================
# HANDLERS
# ============================================================================

@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Point d'entrée du bot"""
    user = update.effective_user
    logger.info(f"👤 /start de {user.first_name} (ID: {user.id})")
    
    # Réinitialiser les données
    context.user_data.clear()
    update_last_activity(context.user_data)
    
    # Vérifications
    if not is_authorized(user.id):
        logger.warning(f"❌ User non autorisé: {user.id}")
        await update.message.reply_text("❌ Accès non autorisé")
        return ConversationHandler.END
    
    if not check_rate_limit(user.id):
        await update.message.reply_text("⚠️ Trop rapide. Attendez un peu.")
        return
    
    # Menu de langue
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
    ]
    
    await update.message.reply_text(
        "🌍 *Choisissez votre langue / Select your language*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"✅ Menu langue envoyé à {user.id}")
    return LANGUE

@error_handler
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit la langue"""
    query = update.callback_query
    await query.answer()
    
    lang_code = query.data.replace("lang_", "")
    context.user_data['langue'] = lang_code
    update_last_activity(context.user_data)
    
    logger.info(f"🌍 Langue: {lang_code} pour user {query.from_user.id}")
    
    welcome_text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "price_menu"), callback_data="price_menu")]
    ]
    
    await query.message.edit_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return PAYS

@error_handler
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Navigation menu"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    if 'langue' not in context.user_data:
        context.user_data['langue'] = 'fr'
    
    if query.data == "start_order":
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
            [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")]
        ]
        text = tr(context.user_data, "choose_country")
        
    elif query.data == "price_menu":
        text = ("🏴‍☠️ *CARTE DU PIRATE*\n\n"
                "🇫🇷 *France:*\n"
                "❄️ Coco: 80€/g\n💊 Pills: 10€\n🫒 Hash: 7€/g\n🍀 Weed: 10€/g\n🪨 MDMA/4MMC: 50€/g\n\n"
                "🇨🇭 *Suisse:*\n"
                "❄️ Coco: 100€/g\n💊 Pills: 15€\n🫒 Hash: 8€/g\n🍀 Weed: 12€/g\n🪨 MDMA/4MMC: 70€/g")
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")]
        ]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix du pays"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    country_code = query.data.replace("country_", "")
    context.user_data['pays'] = country_code
    context.user_data['cart'] = []
    
    logger.info(f"🌍 Pays: {country_code} pour user {query.from_user.id}")
    
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

@error_handler
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix du produit"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    product_code = query.data.replace("product_", "")
    
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
    
    product_names = {
        "snow": "❄️ Coco",
        "olive": "🫒 Hash",
        "clover": "🍀 Weed"
    }
    
    context.user_data['current_product'] = product_names.get(product_code, product_code)
    
    text = f"✅ Produit : {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}"
    await query.message.edit_text(text, parse_mode='Markdown')
    
    return QUANTITE

@error_handler
async def choix_pill_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sous-catégorie pilules"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    pill_type = query.data.replace("pill_", "")
    product_name = PILL_SUBCATEGORIES.get(pill_type, "💊")
    context.user_data['current_product'] = product_name
    
    text = f"✅ Produit : {product_name}\n\n{tr(context.user_data, 'enter_quantity')}"
    await query.message.edit_text(text, parse_mode='Markdown')
    
    return QUANTITE

@error_handler
async def choix_rock_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sous-catégorie crystaux"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    rock_type = query.data.replace("rock_", "")
    product_name = ROCK_SUBCATEGORIES.get(rock_type, "🪨")
    context.user_data['current_product'] = product_name
    
    text = f"✅ Produit : {product_name}\n\n{tr(context.user_data, 'enter_quantity')}"
    await query.message.edit_text(text, parse_mode='Markdown')
    
    return QUANTITE

@error_handler
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saisie quantité"""
    qty = sanitize_input(update.message.text, max_length=10)
    update_last_activity(context.user_data)
    
    if not qty.isdigit():
        await update.message.reply_text(tr(context.user_data, "invalid_quantity"))
        return QUANTITE
    
    qty_int = int(qty)
    if qty_int <= 0 or qty_int > MAX_QUANTITY_PER_PRODUCT:
        await update.message.reply_text(tr(context.user_data, "invalid_quantity"))
        return QUANTITE
    
    context.user_data['cart'].append({
        "produit": context.user_data['current_product'],
        "quantite": qty_int
    })
    
    logger.info(f"🛒 Panier: {context.user_data['current_product']} x{qty_int}")
    
    cart_summary = format_cart(context.user_data['cart'], context.user_data)
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "add_more"), callback_data="add_more")],
        [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")]
    ]
    
    await update.message.reply_text(
        cart_summary,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return CART_MENU

@error_handler
async def cart_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu panier"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    if query.data == "add_more":
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
        await query.message.edit_text(tr(context.user_data, 'enter_address'), parse_mode='Markdown')
        return ADRESSE

@error_handler
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saisie adresse"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.message.edit_text(tr(context.user_data, 'enter_address'), parse_mode='Markdown')
        return ADRESSE
    
    address = sanitize_input(update.message.text, max_length=300)
    update_last_activity(context.user_data)
    
    if len(address) < 15:
        await update.message.reply_text("❌ Adresse trop courte (min 15 caractères)")
        return ADRESSE
    
    context.user_data['adresse'] = address
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "postal"), callback_data="delivery_postal")],
        [InlineKeyboardButton(tr(context.user_data, "express"), callback_data="delivery_express")]
    ]
    
    await update.message.reply_text(
        tr(context.user_data, "choose_delivery"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return LIVRAISON

@error_handler
async def choix_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix livraison"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    delivery_type = query.data.replace("delivery_", "")
    context.user_data['livraison'] = delivery_type
    
    if delivery_type == "express":
        await query.message.edit_text(tr(context.user_data, "calculating_distance"), parse_mode='Markdown')
        
        distance_km, success, error_msg = await get_distance_between_addresses(
            ADMIN_ADDRESS,
            context.user_data.get('adresse', '')
        )
        
        if not success:
            keyboard = [[InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_address")]]
            await query.message.edit_text(
                tr(context.user_data, "geocoding_error"),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return LIVRAISON
        
        context.user_data['distance'] = distance_km
        cart = context.user_data['cart']
        country = context.user_data['pays']
        subtotal, _, _ = calculate_total(cart, country)
        delivery_fee = calculate_delivery_fee("express", distance_km, subtotal)
        
        distance_text = tr(context.user_data, "distance_calculated").format(
            distance=distance_km,
            fee=delivery_fee
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

@error_handler
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix paiement"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    payment_type = query.data.replace("payment_", "")
    context.user_data['paiement'] = payment_type
    
    cart = context.user_data['cart']
    country = context.user_data['pays']
    delivery_type = context.user_data['livraison']
    distance = context.user_data.get('distance', 0)
    
    total, subtotal, delivery_fee = calculate_total(cart, country, delivery_type, distance)
    
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

@error_handler
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation commande"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_order":
        user = update.effective_user
        cart = context.user_data['cart']
        country = context.user_data['pays']
        delivery_type = context.user_data['livraison']
        distance = context.user_data.get('distance', 0)
        
        total, subtotal, delivery_fee = calculate_total(cart, country, delivery_type, distance)
        
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user.id}"
        
        products_str = "; ".join([f"{item['produit']} x{item['quantite']}" for item in cart])
        
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
        
        save_order_to_csv(order_data)
        
        logger.info(f"✅ Commande confirmée: {order_id}")
        
        admin_message = f"🆕 *NOUVELLE COMMANDE*\n\n"
        admin_message += f"📋 `{order_id}`\n"
        admin_message += f"👤 {user.first_name}"
        if user.username:
            admin_message += f" (@{user.username})"
        admin_message += f"\n🆔 ID: `{user.id}`\n\n"
        admin_message += format_cart(cart, context.user_data)
        admin_message += f"\n💰 Total: {total}€"
        
        admin_keyboard = [
            [InlineKeyboardButton(
                "✅ Valider la livraison", 
                callback_data=f"admin_validate_{order_id}_{user.id}"
            )]
        ]
        
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message,
                reply_markup=InlineKeyboardMarkup(admin_keyboard),
                parse_mode='Markdown'
            )
            logger.info(f"✅ Admin notifié: {order_id}")
        except Exception as e:
            logger.error(f"❌ Erreur notification admin: {e}")
        
        confirmation_text = tr(context.user_data, "order_confirmed")
        confirmation_text += f"\n\n📋 `{order_id}`"
        confirmation_text += f"\n💰 {total:.2f}€"
        
        await query.message.edit_text(
            confirmation_text,
            parse_mode='Markdown'
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    elif query.data == "cancel":
        return await cancel(update, context)

@error_handler
async def admin_validation_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validation admin"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Action non autorisée", show_alert=True)
        return
    
    data_parts = query.data.split("_")
    if len(data_parts) >= 4:
        order_id = "_".join(data_parts[2:-1])
        client_id = int(data_parts[-1])
    else:
        await query.answer("❌ Erreur de données", show_alert=True)
        return
    
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
        except Exception as e:
            logger.error(f"❌ Erreur CSV: {e}")
    
    try:
        new_text = query.message.text + "\n\n✅ *LIVRAISON VALIDÉE*"
        await query.message.edit_text(new_text, parse_mode='Markdown')
    except:
        pass
    
    try:
        client_message = f"✅ *Livraison confirmée !*\n\n"
        client_message += f"📋 `{order_id}`\n\n"
        client_message += f"Merci ! 💚"
        
        await context.bot.send_message(
            chat_id=client_id,
            text=client_message,
            parse_mode='Markdown'
        )
        logger.info(f"✅ Client notifié: {client_id}")
    except Exception as e:
        logger.error(f"❌ Erreur notification client: {e}")
    
    await query.answer("✅ Livraison validée !", show_alert=True)

@error_handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulation"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"❌ Annulation par {query.from_user.id}")
    
    await query.message.edit_text(
        tr(context.user_data, "order_cancelled"),
        parse_mode='Markdown'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def error_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire d'erreurs global"""
    logger.error(f"❌ Exception globale: {context.error}", exc_info=context.error)

# ============================================================================
# FONCTION PRINCIPALE
# ============================================================================

def main():
    """Initialise le bot"""
    logger.info("=" * 70)
    logger.info("🤖 CONFIGURATION DU BOT")
    logger.info("=" * 70)
    
    application = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
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
    
    application.add_handler(conv_handler)
    
    application.add_handler(CallbackQueryHandler(
        admin_validation_livraison, 
        pattern='^admin_validate_'
    ))
    
    application.add_error_handler(error_callback)
    
    logger.info("✅ Bot configuré avec succès")
    logger.info("=" * 70)
    
    return application

# Créer l'application
bot_application = main()

logger.info("✅ Bot prêt à être lancé")
logger.info("=" * 70)

if __name__ == '__main__':
    logger.warning("⚠️ N'exécutez pas bot.py directement")
    logger.warning("👉 Utilisez: python app.py")
    sys.exit(0)
