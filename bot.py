import os
import sys
import logging
import re
import signal
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps
from collections import defaultdict
from datetime import datetime, timedelta

# --- Configuration du Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Réduire les logs verbeux
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# --- Chargement des variables d'environnement ---
dotenv_path = Path(__file__).parent / "infos.env"
load_dotenv(dotenv_path)

def validate_environment():
    """Valide les variables d'environnement"""
    required_vars = ['TELEGRAM_TOKEN', 'ADMIN_ID', 'CRYPTO_WALLET']
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        msg = f"❌ Variables manquantes: {', '.join(missing)}"
        logger.error(msg)
        sys.exit(1)
    
    token = os.getenv("TELEGRAM_TOKEN").strip()
    admin_id = os.getenv("ADMIN_ID").strip()
    
    if ':' not in token or len(token) < 40:
        logger.error("❌ TELEGRAM_TOKEN invalide")
        sys.exit(1)
    
    if not admin_id.isdigit():
        logger.error("❌ ADMIN_ID doit être un nombre")
        sys.exit(1)
    
    logger.info("✅ Configuration validée")

validate_environment()

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CRYPTO_WALLET = os.getenv("CRYPTO_WALLET")

# --- Imports Telegram ---
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ContextTypes, CallbackQueryHandler,
    ConversationHandler, MessageHandler, CommandHandler, filters
)
from telegram.error import NetworkError, TimedOut, Conflict
import asyncio

# --- Configuration ---
USE_WHITELIST = False
AUTHORIZED_USERS = []

# Rate limiting
user_message_timestamps = defaultdict(list)
MAX_MESSAGES_PER_MINUTE = 15
RATE_LIMIT_WINDOW = 60

SESSION_TIMEOUT_MINUTES = 30
MAX_QUANTITY_PER_PRODUCT = 100

# États de conversation
LANGUE, PAYS, PRODUIT, QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(9)

# Produits
PRODUCT_MAP = {
    "snow": "❄️",
    "pill": "💊",
    "olive": "🫒",
    "clover": "🍀"
}

# Prix
PRIX_FR = {"❄️": 80, "💊": 10, "🫒": 7, "🍀": 10}
PRIX_CH = {"❄️": 100, "💊": 15, "🫒": 8, "🍀": 12}

# --- Traductions ---
TRANSLATIONS = {
    "fr": {
        "welcome": "🌿 *BIENVENUE* 🌿\n\n⚠️ *IMPORTANT :*\nToutes les conversations doivent être établies en *ÉCHANGE SECRET*.\n\n🙏 *Merci* 💪💚",
        "choose_language": "🌍 *Choisissez votre langue :*",
        "main_menu": "\n\n📱 *MENU PRINCIPAL :*\n\n👇 Choisissez une option :",
        "choose_country": "🌍 *Choisissez votre pays :*",
        "choose_product": "🛍️ *Choisissez votre produit :*",
        "enter_quantity": "📝 *Entrez la quantité désirée :*",
        "enter_address": "📍 *Entrez votre adresse complète :*",
        "choose_delivery": "📦 *Choisissez le type de livraison :*",
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
        "info_title": "ℹ️ *INFORMATIONS*",
        "info_shop": "🛍️ *Notre boutique :*\n• Livraison France 🇫🇷 & Suisse 🇨🇭\n• Produits de qualité\n• Service client réactif",
        "info_delivery": "📦 *Livraison :*\n• Standard : 3-5 jours\n• Express : 24-48h",
        "info_payment": "💳 *Paiement :*\n• Espèces à la livraison\n• Crypto (Bitcoin, USDT)",
        "info_security": "🔒 *Sécurité :*\nTous les échanges sont cryptés et confidentiels.",
        "contact_title": "📞 *CONTACT*",
        "contact_text": "Pour toute question ou besoin d'assistance, vous pouvez :\n\n• Continuer avec la commande\n• Contacter l'administrateur\n\nNotre équipe est disponible 24/7 pour vous aider ! 💬",
        "start_order": "🛍️ Commander",
        "informations": "ℹ️ Informations",
        "contact": "📞 Contact",
        "back": "🔙 Retour",
        "contact_admin": "💬 Contacter Admin",
        "price_menu": "🏴‍☠️ Carte du Pirate",
        "price_menu_title": "🏴‍☠️ *CARTE DU PIRATE*",
        "price_menu_fr": "\n\n🇫🇷 *FRANCE:*\n• ❄️ Snow: 80€\n• 💊 Pill: 10€\n• 🫒 Olive: 7€\n• 🍀 Clover: 10€",
        "price_menu_ch": "\n\n🇨🇭 *SUISSE:*\n• ❄️ Snow: 100€\n• 💊 Pill: 15€\n• 🫒 Olive: 8€\n• 🍀 Clover: 12€",
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Suisse",
        "standard": "📦 Standard",
        "express": "⚡ Express",
        "cash": "💵 Espèces",
        "crypto": "₿ Crypto",
        "unauthorized": "❌ Accès non autorisé.",
        "rate_limit": "⚠️ Trop de requêtes. Attendez 1 minute.",
        "session_expired": "⏱️ Session expirée. Utilisez /start pour recommencer.",
        "invalid_address": "❌ Adresse invalide. Elle doit contenir au moins 15 caractères."
    },
    "en": {
        "welcome": "🌿 *WELCOME* 🌿\n\n⚠️ *IMPORTANT:*\nAll conversations must be established in *SECRET EXCHANGE*.\n\n🙏 *Thank you* 💪💚",
        "choose_language": "🌍 *Select your language:*",
        "main_menu": "\n\n📱 *MAIN MENU:*\n\n👇 Choose an option:",
        "choose_country": "🌍 *Choose your country:*",
        "choose_product": "🛍️ *Choose your product:*",
        "enter_quantity": "📝 *Enter desired quantity:*",
        "enter_address": "📍 *Enter your complete address:*",
        "choose_delivery": "📦 *Choose delivery type:*",
        "choose_payment": "💳 *Choose payment method:*",
        "order_summary": "✅ *Your order summary:*",
        "confirm": "✅ Confirm",
        "cancel": "❌ Cancel",
        "order_confirmed": "✅ *Order confirmed!*\n\nThank you for your order.\nYou will be contacted soon. 📞",
        "order_cancelled": "❌ *Order cancelled.*",
        "add_more": "➕ Add product",
        "proceed": "✅ Checkout",
        "invalid_quantity": "❌ Please enter a valid number between 1 and {max}.",
        "cart_title": "🛒 *Your cart:*",
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Switzerland",
        "standard": "📦 Standard",
        "express": "⚡ Express",
        "cash": "💵 Cash",
        "crypto": "₿ Crypto",
        "start_order": "🛍️ Order Now",
        "informations": "ℹ️ Information",
        "contact": "📞 Contact",
        "back": "🔙 Back",
        "contact_admin": "💬 Contact Admin",
        "price_menu": "🏴‍☠️ Pirate's Menu",
        "price_menu_title": "🏴‍☠️ *PIRATE'S MENU*",
        "price_menu_fr": "\n\n🇫🇷 *FRANCE:*\n• ❄️ Snow: €80\n• 💊 Pill: €10\n• 🫒 Olive: €7\n• 🍀 Clover: €10",
        "price_menu_ch": "\n\n🇨🇭 *SWITZERLAND:*\n• ❄️ Snow: €100\n• 💊 Pill: €15\n• 🫒 Olive: €8\n• 🍀 Clover: €12",
        "info_title": "ℹ️ *INFORMATION*",
        "info_shop": "🛍️ *Our shop:*\n• Delivery France 🇫🇷 & Switzerland 🇨🇭\n• Quality products\n• Responsive customer service",
        "contact_title": "📞 *CONTACT*",
        "contact_text": "For any questions or assistance, you can:\n\n• Continue with the order\n• Contact the administrator\n\nOur team is available 24/7 to help you! 💬"
    }
}

# --- Fonctions utilitaires ---
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
    text = re.sub(r'[\x00-\x1F\x7F]', '', text)
    return text

def is_authorized(user_id: int) -> bool:
    """Vérifie l'autorisation"""
    if not USE_WHITELIST:
        return True
    return user_id in AUTHORIZED_USERS

def check_rate_limit(user_id: int) -> bool:
    """Vérifie le rate limit"""
    now = datetime.now()
    user_message_timestamps[user_id] = [
        ts for ts in user_message_timestamps[user_id]
        if now - ts < timedelta(seconds=RATE_LIMIT_WINDOW)
    ]
    if len(user_message_timestamps[user_id]) >= MAX_MESSAGES_PER_MINUTE:
        return False
    user_message_timestamps[user_id].append(now)
    return True

def check_session_timeout(user_data: dict) -> bool:
    """Vérifie le timeout de session"""
    last_activity = user_data.get('last_activity')
    if not last_activity:
        return False
    return datetime.now() - last_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES)

def update_last_activity(user_data: dict):
    """Met à jour l'activité"""
    user_data['last_activity'] = datetime.now()

def calculate_total(cart, country):
    """Calcule le total"""
    prix_table = PRIX_FR if country == "FR" else PRIX_CH
    return sum(prix_table[item["produit"]] * item["quantite"] for item in cart)

def format_cart(cart, user_data):
    """Formate le panier"""
    if not cart:
        return ""
    cart_text = f"\n{tr(user_data, 'cart_title')}\n"
    for item in cart:
        cart_text += f"• {item['produit']} x {item['quantite']}\n"
    return cart_text

# --- Décorateurs ---
def security_check(func):
    """Décorateur de sécurité"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if not is_authorized(user_id):
            logger.warning(f"Accès refusé: {user_id}")
            msg = "unauthorized"
            if update.message:
                await update.message.reply_text(tr(context.user_data, msg))
            elif update.callback_query:
                await update.callback_query.answer(tr(context.user_data, msg))
            return ConversationHandler.END
        
        if not check_rate_limit(user_id):
            logger.warning(f"Rate limit: {user_id}")
            return
        
        if check_session_timeout(context.user_data):
            logger.info(f"Session expirée: {user_id}")
            context.user_data.clear()
            return ConversationHandler.END
        
        update_last_activity(context.user_data)
        return await func(update, context)
    return wrapper

def error_handler(func):
    """Gestion des erreurs"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            user_id = update.effective_user.id if update.effective_user else "Unknown"
            logger.error(f"Erreur dans {func.__name__} (User {user_id}): {e}", exc_info=True)
            
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

# --- Handlers ---
@security_check
@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    context.user_data.clear()
    update_last_activity(context.user_data)
    
    welcome_text = (
        "🌍 *Choisissez votre langue / Select your language*\n"
        "🌍 *Seleccione su idioma / Wählen Sie Ihre Sprache*"
    )
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")]
    ]
    
    image_path = Path(__file__).parent / "welcome_image.jpg"
    
    if image_path.exists():
        try:
            with open(image_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=welcome_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except:
            await update.message.reply_text(
                welcome_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    return LANGUE

@security_check
@error_handler
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit la langue"""
    query = update.callback_query
    await query.answer()
    
    lang_code = query.data.replace("lang_", "")
    context.user_data['langue'] = lang_code
    
    welcome_text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "price_menu"), callback_data="price_menu")],
        [InlineKeyboardButton(tr(context.user_data, "informations"), callback_data="info")],
        [InlineKeyboardButton(tr(context.user_data, "contact"), callback_data="contact_admin")]
    ]
    
    try:
        await query.message.edit_caption(
            caption=welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except:
        await query.message.edit_text(
            text=welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    return PAYS

@security_check
@error_handler
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Navigation dans les menus"""
    query = update.callback_query
    await query.answer()
    
    if 'langue' not in context.user_data:
        context.user_data['langue'] = 'fr'
    
    if query.data == "start_order":
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
            [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_menu")]
        ]
        text = tr(context.user_data, "choose_country")
    
    elif query.data == "price_menu":
        text = (
            f"{tr(context.user_data, 'price_menu_title')}"
            f"{tr(context.user_data, 'price_menu_fr')}"
            f"{tr(context.user_data, 'price_menu_ch')}"
        )
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_menu")]
        ]
    
    elif query.data == "info":
        text = (
            f"{tr(context.user_data, 'info_title')}\n\n"
            f"{tr(context.user_data, 'info_shop')}"
        )
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_menu")]
        ]
    
    elif query.data == "contact_admin":
        text = f"{tr(context.user_data, 'contact_title')}\n\n{tr(context.user_data, 'contact_text')}"
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "contact_admin"), url=f"tg://user?id={ADMIN_ID}")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_menu")]
        ]
    
    elif query.data == "back_menu":
        text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
            [InlineKeyboardButton(tr(context.user_data, "price_menu"), callback_data="price_menu")],
            [InlineKeyboardButton(tr(context.user_data, "informations"), callback_data="info")],
            [InlineKeyboardButton(tr(context.user_data, "contact"), callback_data="contact_admin")]
        ]
    
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except:
        await query.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    return PAYS

@security_check
@error_handler
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix du pays"""
    query = update.callback_query
    await query.answer()
    
    country_code = query.data.replace("country_", "")
    context.user_data['pays'] = country_code
    context.user_data['cart'] = []
    
    keyboard = [
        [InlineKeyboardButton("❄️", callback_data="product_snow")],
        [InlineKeyboardButton("💊", callback_data="product_pill")],
        [InlineKeyboardButton("🫒", callback_data="product_olive")],
        [InlineKeyboardButton("🍀", callback_data="product_clover")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    
    try:
        await query.message.edit_text(
            tr(context.user_data, "choose_product"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except:
        await query.message.edit_caption(
            caption=tr(context.user_data, "choose_product"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    return PRODUIT

@security_check
@error_handler
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix du produit"""
    query = update.callback_query
    await query.answer()
    
    product_code = query.data.replace("product_", "")
    product_emoji = PRODUCT_MAP.get(product_code, product_code)
    context.user_data['current_product'] = product_emoji
    
    text = f"{tr(context.user_data, 'choose_product')}\n\n✅ Produit: {product_emoji}\n\n{tr(context.user_data, 'enter_quantity')}"
    
    try:
        await query.message.edit_text(text, parse_mode='Markdown')
    except:
        await query.message.edit_caption(caption=text, parse_mode='Markdown')
    
    return QUANTITE

@security_check
@error_handler
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saisie de la quantité"""
    qty = sanitize_input(update.message.text, max_length=10)
    
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
    
    cart_summary = format_cart(context.user_data['cart'], context.user_data)
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "add_more"), callback_data="add_more")],
        [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    
    await update.message.reply_text(
        cart_summary,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return CART_MENU

@security_check
@error_handler
async def cart_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu du panier"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_more":
        keyboard = [
            [InlineKeyboardButton("❄️", callback_data="product_snow")],
            [InlineKeyboardButton("💊", callback_data="product_pill")],
            [InlineKeyboardButton("🫒", callback_data="product_olive")],
            [InlineKeyboardButton("🍀", callback_data="product_clover")],
            [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
        ]
        await query.message.edit_text(
            tr(context.user_data, "choose_product"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return PRODUIT
    
    elif query.data == "proceed_checkout":
        await query.message.edit_text(
            tr(context.user_data, "enter_address"),
            parse_mode='Markdown'
        )
        return ADRESSE
    
    return CART_MENU

@security_check
@error_handler
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saisie de l'adresse"""
    adresse = sanitize_input(update.message.text, max_length=300)
    
    if len(adresse) < 15:
        await update.message.reply_text(tr(context.user_data, "invalid_address"))
        return ADRESSE
    
    context.user_data['adresse'] = adresse
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "standard"), callback_data="delivery_standard")],
        [InlineKeyboardButton(tr(context.user_data, "express"), callback_data="delivery_express")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    
    await update.message.reply_text(
        tr(context.user_data, "choose_delivery"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return LIVRAISON

@security_check
@error_handler
async def choix_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix de la livraison"""
    query = update.callback_query
    await query.answer()
    
    delivery_type = query.data.replace("delivery_", "")
    context.user_data['livraison'] = delivery_type
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "cash"), callback_data="payment_cash")],
        [InlineKeyboardButton(tr(context.user_data, "crypto"), callback_data="payment_crypto")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
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
    """Choix du paiement"""
    query = update.callback_query
    await query.answer()
    
    payment_type = query.data.replace("payment_", "")
    context.user_data['paiement'] = payment_type
    
    total = calculate_total(context.user_data['cart'], context.user_data['pays'])
    summary = f"{tr(context.user_data, 'order_summary')}\n\n"
    
    prix_table = PRIX_FR if context.user_data['pays'] == "FR" else PRIX_CH
    for item in context.user_data['cart']:
        prix_unitaire = prix_table[item['produit']]
        subtotal = prix_unitaire * item['quantite']
        summary += f"• {item['produit']} x {item['quantite']} = {subtotal}€\n"
    
    summary += f"\n📍 Adresse: {context.user_data['adresse'][:50]}...\n"
    summary += f"📦 Livraison: {context.user_data['livraison']}\n"
    summary += f"💳 Paiement: {context.user_data['paiement']}\n"
    summary += f"\n💰 TOTAL: {total}€"
    
    if context.user_data['paiement'] == 'crypto':
        summary += f"\n\n₿ Wallet: `{CRYPTO_WALLET}`"
    
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
    """Confirmation de commande"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_order":
        await query.message.edit_text(
            tr(context.user_data, "order_confirmed"),
            parse_mode='Markdown'
        )
        
        # Notification admin
        total = calculate_total(context.user_data['cart'], context.user_data['pays'])
        user = query.from_user
        
        order_details = "🔔 NOUVELLE COMMANDE\n"
        order_details += "=" * 30 + "\n\n"
        order_details += "👤 CLIENT:\n"
        order_details += f"├─ ID: {user.id}\n"
        order_details += f"└─ Username: @{user.username if user.username else 'N/A'}\n\n"
        order_details += "🛒 PRODUITS:\n"
        
        prix_table = PRIX_FR if context.user_data['pays'] == "FR" else PRIX_CH
        for idx, item in enumerate(context.user_data['cart'], 1):
            prix_unitaire = prix_table[item['produit']]
            subtotal = prix_unitaire * item['quantite']
            order_details += f"├─ {idx}. {item['produit']} x {item['quantite']} = {subtotal}€\n"
        
        order_details += f"\n📦 LIVRAISON:\n"
        order_details += f"├─ Pays: {context.user_data['pays']}\n"
        order_details += f"├─ Adresse: {context.user_data['adresse']}\n"
        order_details += f"└─ Type: {context.user_data['livraison']}\n\n"
        order_details += f"💳 PAIEMENT: {context.user_data['paiement']}\n"
        order_details += f"💰 TOTAL: {total}€\n"
        order_details += "=" * 30
        
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=order_details)
            logger.info(f"✅ Commande confirmée - User: {user.id}")
        except Exception as e:
            logger.error(f"Erreur notification admin: {e}")
    
    context.user_data.clear()
    return ConversationHandler.END

@security_check
@error_handler
async def annuler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulation"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        tr(context.user_data, "order_cancelled"),
        parse_mode='Markdown'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def error_callback(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Gestion globale des erreurs"""
    logger.error("Erreur non gérée:", exc_info=context.error)
    
    # Ignorer les erreurs réseau temporaires
    if isinstance(context.error, (NetworkError, TimedOut, Conflict)):
        logger.info("Erreur réseau temporaire ignorée")
        return
    
    # Notifier l'admin pour les erreurs critiques
    try:
        error_msg = f"🚨 ERREUR BOT\n\nType: {type(context.error).__name__}\n{str(context.error)[:200]}"
        await context.bot.send_message(chat_id=ADMIN_ID, text=error_msg)
    except:
        pass

async def shutdown(application: Application):
    """Arrêt propre du bot"""
    logger.info("🛑 Arrêt du bot...")
    await application.stop()
    await application.shutdown()
    logger.info("✅ Bot arrêté proprement")

def main():
    """Fonction principale"""
    # Construction de l'application
    application = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )
    
    # Gestionnaire d'erreurs global
    application.add_error_handler(error_callback)
    
    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            LANGUE: [
                CallbackQueryHandler(set_langue, pattern="^lang_(fr|en|es|de)$")
            ],
            PAYS: [
                CallbackQueryHandler(choix_pays, pattern="^country_(FR|CH)$"),
                CallbackQueryHandler(menu_navigation, pattern="^(start_order|info|price_menu|contact_admin|back_menu)$")
            ],
            PRODUIT: [
                CallbackQueryHandler(choix_produit, pattern="^product_(snow|pill|olive|clover)$")
            ],
            QUANTITE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)
            ],
            CART_MENU: [
                CallbackQueryHandler(cart_menu_handler, pattern="^(add_more|proceed_checkout)$")
            ],
            ADRESSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse)
            ],
            LIVRAISON: [
                CallbackQueryHandler(choix_livraison, pattern="^delivery_(standard|express)$")
            ],
            PAIEMENT: [
                CallbackQueryHandler(choix_paiement, pattern="^payment_(cash|crypto)$")
            ],
            CONFIRMATION: [
                CallbackQueryHandler(confirmation, pattern="^confirm_order$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(annuler, pattern="^cancel$"),
            CommandHandler("start", start_command)
        ],
        per_message=False,
        allow_reentry=True,
        conversation_timeout=1800  # 30 minutes
    )
    
    application.add_handler(conv_handler)
    
    # Gestion de l'arrêt propre
    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} reçu, arrêt du bot...")
        import asyncio
        asyncio.create_task(shutdown(application))
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Informations de démarrage
    logger.info("=" * 50)
    logger.info("🚀 Bot démarré avec succès!")
    logger.info(f"🔒 Whitelist: {'Activée' if USE_WHITELIST else 'Désactivée'}")
    logger.info(f"⏱️ Rate limit: {MAX_MESSAGES_PER_MINUTE} msg/min")
    logger.info(f"⏳ Session timeout: {SESSION_TIMEOUT_MINUTES} min")
    logger.info(f"📊 Max quantité: {MAX_QUANTITY_PER_PRODUCT}")
    logger.info("=" * 50)
    
    # Démarrage du polling avec gestion robuste
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,  # Important: évite les conflits
            close_loop=False
        )
    except Conflict as e:
        logger.error("❌ CONFLIT: Une autre instance du bot est déjà en cours d'exécution!")
        logger.error("Solution: Arrêtez toutes les autres instances du bot avant de redémarrer.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
