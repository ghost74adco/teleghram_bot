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
LANGUE, PAYS, PRODUIT, PILL_SUBCATEGORY, QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(10)

# Produits
PRODUCT_MAP = {
    "snow": "❄️",
    "pill": "💊",
    "olive": "🫒",
    "clover": "🍀"
}

# Sous-catégories pour Pills
PILL_SUBCATEGORIES = {
    "squid_game": "💊 Squid Game",
    "punisher": "💊 Punisher"
}

# Prix (avec sous-catégories pour pills)
PRIX_FR = {
    "❄️": 80,
    "💊 Squid Game": 10,
    "💊 Punisher": 12,
    "🫒": 7,
    "🍀": 10
}

PRIX_CH = {
    "❄️": 100,
    "💊 Squid Game": 15,
    "💊 Punisher": 18,
    "🫒": 8,
    "🍀": 12
}

# --- Traductions Complètes ---
TRANSLATIONS = {
    "fr": {
        "welcome": "🌿 *BIENVENUE* 🌿\n\n⚠️ *IMPORTANT :*\nToutes les conversations doivent être établies en *ÉCHANGE SECRET*.\n\n🙏 *Merci* 💪💚",
        "choose_language": "🌍 *Choisissez votre langue :*",
        "main_menu": "\n\n📱 *MENU PRINCIPAL :*\n\n👇 Choisissez une option :",
        "choose_country": "🌍 *Choisissez votre pays :*",
        "choose_product": "🛍️ *Choisissez votre produit :*",
        "choose_pill_type": "💊 *Choisissez le type de pilule :*",
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
        "price_menu_fr": "\n\n🇫🇷 *FRANCE:*\n• ❄️ Snow: 80€\n• 💊 Squid Game: 10€\n• 💊 Punisher: 12€\n• 🫒 Olive: 7€\n• 🍀 Clover: 10€",
        "price_menu_ch": "\n\n🇨🇭 *SUISSE:*\n• ❄️ Snow: 100€\n• 💊 Squid Game: 15€\n• 💊 Punisher: 18€\n• 🫒 Olive: 8€\n• 🍀 Clover: 12€",
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Suisse",
        "standard": "📦 Standard",
        "express": "⚡ Express",
        "cash": "💵 Espèces",
        "crypto": "₿ Crypto",
        "unauthorized": "❌ Accès non autorisé.",
        "rate_limit": "⚠️ Trop de requêtes. Attendez 1 minute.",
        "session_expired": "⏱️ Session expirée. Utilisez /start pour recommencer.",
        "invalid_address": "❌ Adresse invalide. Elle doit contenir au moins 15 caractères.",
        "product_selected": "✅ Produit sélectionné :",
        "total": "💰 *Total :*"
    },
    "en": {
        "welcome": "🌿 *WELCOME* 🌿\n\n⚠️ *IMPORTANT:*\nAll conversations must be established in *SECRET EXCHANGE*.\n\n🙏 *Thank you* 💪💚",
        "choose_language": "🌍 *Select your language:*",
        "main_menu": "\n\n📱 *MAIN MENU:*\n\n👇 Choose an option:",
        "choose_country": "🌍 *Choose your country:*",
        "choose_product": "🛍️ *Choose your product:*",
        "choose_pill_type": "💊 *Choose pill type:*",
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
        "info_title": "ℹ️ *INFORMATION*",
        "info_shop": "🛍️ *Our shop:*\n• Delivery France 🇫🇷 & Switzerland 🇨🇭\n• Quality products\n• Responsive customer service",
        "info_delivery": "📦 *Delivery:*\n• Standard: 3-5 days\n• Express: 24-48h",
        "info_payment": "💳 *Payment:*\n• Cash on delivery\n• Crypto (Bitcoin, USDT)",
        "info_security": "🔒 *Security:*\nAll exchanges are encrypted and confidential.",
        "contact_title": "📞 *CONTACT*",
        "contact_text": "For any questions or assistance, you can:\n\n• Continue with the order\n• Contact the administrator\n\nOur team is available 24/7 to help you! 💬",
        "start_order": "🛍️ Order Now",
        "informations": "ℹ️ Information",
        "contact": "📞 Contact",
        "back": "🔙 Back",
        "contact_admin": "💬 Contact Admin",
        "price_menu": "🏴‍☠️ Pirate's Menu",
        "price_menu_title": "🏴‍☠️ *PIRATE'S MENU*",
        "price_menu_fr": "\n\n🇫🇷 *FRANCE:*\n• ❄️ Snow: €80\n• 💊 Squid Game: €10\n• 💊 Punisher: €12\n• 🫒 Olive: €7\n• 🍀 Clover: €10",
        "price_menu_ch": "\n\n🇨🇭 *SWITZERLAND:*\n• ❄️ Snow: €100\n• 💊 Squid Game: €15\n• 💊 Punisher: €18\n• 🫒 Olive: €8\n• 🍀 Clover: €12",
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Switzerland",
        "standard": "📦 Standard",
        "express": "⚡ Express",
        "cash": "💵 Cash",
        "crypto": "₿ Crypto",
        "unauthorized": "❌ Unauthorized access.",
        "rate_limit": "⚠️ Too many requests. Wait 1 minute.",
        "session_expired": "⏱️ Session expired. Use /start to restart.",
        "invalid_address": "❌ Invalid address. It must contain at least 15 characters.",
        "product_selected": "✅ Product selected:",
        "total": "💰 *Total:*"
    },
    "es": {
        "welcome": "🌿 *BIENVENIDO* 🌿\n\n⚠️ *IMPORTANTE:*\nTodas las conversaciones deben establecerse en *INTERCAMBIO SECRETO*.\n\n🙏 *Gracias* 💪💚",
        "choose_language": "🌍 *Seleccione su idioma:*",
        "main_menu": "\n\n📱 *MENÚ PRINCIPAL:*\n\n👇 Elija una opción:",
        "choose_country": "🌍 *Elija su país:*",
        "choose_product": "🛍️ *Elija su producto:*",
        "choose_pill_type": "💊 *Elija el tipo de píldora:*",
        "enter_quantity": "📝 *Ingrese la cantidad deseada:*",
        "enter_address": "📍 *Ingrese su dirección completa:*",
        "choose_delivery": "📦 *Elija el tipo de entrega:*",
        "choose_payment": "💳 *Elija el método de pago:*",
        "order_summary": "✅ *Resumen de su pedido:*",
        "confirm": "✅ Confirmar",
        "cancel": "❌ Cancelar",
        "order_confirmed": "✅ *¡Pedido confirmado!*\n\nGracias por su pedido.\nSerá contactado pronto. 📞",
        "order_cancelled": "❌ *Pedido cancelado.*",
        "add_more": "➕ Agregar producto",
        "proceed": "✅ Finalizar compra",
        "invalid_quantity": "❌ Por favor ingrese un número válido entre 1 y {max}.",
        "cart_title": "🛒 *Su carrito:*",
        "info_title": "ℹ️ *INFORMACIÓN*",
        "info_shop": "🛍️ *Nuestra tienda:*\n• Entrega Francia 🇫🇷 & Suiza 🇨🇭\n• Productos de calidad\n• Servicio al cliente receptivo",
        "info_delivery": "📦 *Entrega:*\n• Estándar: 3-5 días\n• Express: 24-48h",
        "info_payment": "💳 *Pago:*\n• Efectivo contra entrega\n• Crypto (Bitcoin, USDT)",
        "info_security": "🔒 *Seguridad:*\nTodos los intercambios están encriptados y son confidenciales.",
        "contact_title": "📞 *CONTACTO*",
        "contact_text": "Para cualquier pregunta o asistencia, puede:\n\n• Continuar con el pedido\n• Contactar al administrador\n\n¡Nuestro equipo está disponible 24/7 para ayudarle! 💬",
        "start_order": "🛍️ Ordenar ahora",
        "informations": "ℹ️ Información",
        "contact": "📞 Contacto",
        "back": "🔙 Volver",
        "contact_admin": "💬 Contactar Admin",
        "price_menu": "🏴‍☠️ Menú del Pirata",
        "price_menu_title": "🏴‍☠️ *MENÚ DEL PIRATA*",
        "price_menu_fr": "\n\n🇫🇷 *FRANCIA:*\n• ❄️ Snow: 80€\n• 💊 Squid Game: 10€\n• 💊 Punisher: 12€\n• 🫒 Olive: 7€\n• 🍀 Clover: 10€",
        "price_menu_ch": "\n\n🇨🇭 *SUIZA:*\n• ❄️ Snow: 100€\n• 💊 Squid Game: 15€\n• 💊 Punisher: 18€\n• 🫒 Olive: 8€\n• 🍀 Clover: 12€",
        "france": "🇫🇷 Francia",
        "switzerland": "🇨🇭 Suiza",
        "standard": "📦 Estándar",
        "express": "⚡ Express",
        "cash": "💵 Efectivo",
        "crypto": "₿ Crypto",
        "unauthorized": "❌ Acceso no autorizado.",
        "rate_limit": "⚠️ Demasiadas solicitudes. Espere 1 minuto.",
        "session_expired": "⏱️ Sesión expirada. Use /start para reiniciar.",
        "invalid_address": "❌ Dirección inválida. Debe contener al menos 15 caracteres.",
        "product_selected": "✅ Producto seleccionado:",
        "total": "💰 *Total:*"
    },
    "de": {
        "welcome": "🌿 *WILLKOMMEN* 🌿\n\n⚠️ *WICHTIG:*\nAlle Gespräche müssen in *GEHEIMEM AUSTAUSCH* geführt werden.\n\n🙏 *Danke* 💪💚",
        "choose_language": "🌍 *Wählen Sie Ihre Sprache:*",
        "main_menu": "\n\n📱 *HAUPTMENÜ:*\n\n👇 Wählen Sie eine Option:",
        "choose_country": "🌍 *Wählen Sie Ihr Land:*",
        "choose_product": "🛍️ *Wählen Sie Ihr Produkt:*",
        "choose_pill_type": "💊 *Wählen Sie den Pillentyp:*",
        "enter_quantity": "📝 *Geben Sie die gewünschte Menge ein:*",
        "enter_address": "📍 *Geben Sie Ihre vollständige Adresse ein:*",
        "choose_delivery": "📦 *Wählen Sie die Lieferart:*",
        "choose_payment": "💳 *Wählen Sie die Zahlungsmethode:*",
        "order_summary": "✅ *Ihre Bestellübersicht:*",
        "confirm": "✅ Bestätigen",
        "cancel": "❌ Abbrechen",
        "order_confirmed": "✅ *Bestellung bestätigt!*\n\nVielen Dank für Ihre Bestellung.\nSie werden bald kontaktiert. 📞",
        "order_cancelled": "❌ *Bestellung storniert.*",
        "add_more": "➕ Produkt hinzufügen",
        "proceed": "✅ Zur Kasse",
        "invalid_quantity": "❌ Bitte geben Sie eine gültige Zahl zwischen 1 und {max} ein.",
        "cart_title": "🛒 *Ihr Warenkorb:*",
        "info_title": "ℹ️ *INFORMATION*",
        "info_shop": "🛍️ *Unser Shop:*\n• Lieferung Frankreich 🇫🇷 & Schweiz 🇨🇭\n• Qualitätsprodukte\n• Reaktionsschneller Kundenservice",
        "info_delivery": "📦 *Lieferung:*\n• Standard: 3-5 Tage\n• Express: 24-48h",
        "info_payment": "💳 *Zahlung:*\n• Barzahlung bei Lieferung\n• Krypto (Bitcoin, USDT)",
        "info_security": "🔒 *Sicherheit:*\nAlle Transaktionen sind verschlüsselt und vertraulich.",
        "contact_title": "📞 *KONTAKT*",
        "contact_text": "Bei Fragen oder für Unterstützung können Sie:\n\n• Mit der Bestellung fortfahren\n• Den Administrator kontaktieren\n\nUnser Team ist 24/7 für Sie da! 💬",
        "start_order": "🛍️ Jetzt bestellen",
        "informations": "ℹ️ Information",
        "contact": "📞 Kontakt",
        "back": "🔙 Zurück",
        "contact_admin": "💬 Admin kontaktieren",
        "price_menu": "🏴‍☠️ Piraten-Menü",
        "price_menu_title": "🏴‍☠️ *PIRATEN-MENÜ*",
        "price_menu_fr": "\n\n🇫🇷 *FRANKREICH:*\n• ❄️ Snow: 80€\n• 💊 Squid Game: 10€\n• 💊 Punisher: 12€\n• 🫒 Olive: 7€\n• 🍀 Clover: 10€",
        "price_menu_ch": "\n\n🇨🇭 *SCHWEIZ:*\n• ❄️ Snow: 100€\n• 💊 Squid Game: 15€\n• 💊 Punisher: 18€\n• 🫒 Olive: 8€\n• 🍀 Clover: 12€",
        "france": "🇫🇷 Frankreich",
        "switzerland": "🇨🇭 Schweiz",
        "standard": "📦 Standard",
        "express": "⚡ Express",
        "cash": "💵 Bargeld",
        "crypto": "₿ Krypto",
        "unauthorized": "❌ Unbefugter Zugriff.",
        "rate_limit": "⚠️ Zu viele Anfragen. Warten Sie 1 Minute.",
        "session_expired": "⏱️ Sitzung abgelaufen. Verwenden Sie /start zum Neustarten.",
        "invalid_address": "❌ Ungültige Adresse. Sie muss mindestens 15 Zeichen enthalten.",
        "product_selected": "✅ Produkt ausgewählt:",
        "total": "💰 *Gesamt:*"
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
    """Commande /start - Sélection de la langue"""
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
    """Définit la langue et affiche le menu principal"""
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
    
    # Si c'est une pilule, afficher le sous-menu
    if product_code == "pill":
        keyboard = [
            [InlineKeyboardButton("💊 Squid Game", callback_data="pill_squid_game")],
            [InlineKeyboardButton("💊 Punisher", callback_data="pill_punisher")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_products")],
            [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
        ]
        
        try:
            await query.message.edit_text(
                tr(context.user_data, "choose_pill_type"),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except:
            await query.message.edit_caption(
                caption=tr(context.user_data, "choose_pill_type"),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        return PILL_SUBCATEGORY
    
    # Pour les autres produits, continuer normalement
    product_emoji = PRODUCT_MAP.get(product_code, product_code)
    context.user_data['current_product'] = product_emoji
    
    text = f"{tr(context.user_data, 'product_selected')} {product_emoji}\n\n{tr(context.user_data, 'enter_quantity')}"
    
    try:
        await query.message.edit_text(text, parse_mode='Markdown')
    except:
        await query.message.edit_caption(caption=text, parse_mode='Markdown')
    
    return QUANTITE

@security_check
@error_handler
async def choix_pill_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix de la sous-catégorie de pilule"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_products":
        # Retour au menu des produits
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
    
    # Récupérer la sous-catégorie choisie
    pill_type = query.data.replace("pill_", "")
    product_name = PILL_SUBCATEGORIES.get(pill_type, "💊")
    context.user_data['current_product'] = product_name
    
    text = f"{tr(context.user_data, 'product_selected')} {product_name}\n\n{tr(context.user_data, 'enter_quantity')}"
    
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
async def cart_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        text = f"{tr(context.user_data, 'enter_address')}"
        await query.message.edit_text(text, parse_mode='Markdown')
        return ADRESSE

@security_check
@error_handler
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saisie de l'adresse"""
    address = sanitize_input(update.message.text, max_length=300)
    
    if len(address) < 15:
        await update.message.reply_text(tr(context.user_data, "invalid_address"))
        return ADRESSE
    
    context.user_data['adresse'] = address
    
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
    
    # Résumé de la commande
    cart = context.user_data['cart']
    country = context.user_data['pays']
    total = calculate_total(cart, country)
    
    summary = f"{tr(context.user_data, 'order_summary')}\n\n"
    summary += format_cart(cart, context.user_data)
    summary += f"\n{tr(context.user_data, 'total')} {total}€\n\n"
    summary += f"📍 {context.user_data['adresse']}\n"
    summary += f"📦 {tr(context.user_data, context.user_data['livraison'])}\n"
    summary += f"💳 {tr(context.user_data, context.user_data['paiement'])}\n"
    
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
    """Confirmation de la commande"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_order":
        # Envoi de la commande à l'admin
        cart = context.user_data['cart']
        country = context.user_data['pays']
        total = calculate_total(cart, country)
        
        admin_message = f"🆕 *NOUVELLE COMMANDE*\n\n"
        admin_message += f"👤 Client: {update.effective_user.first_name} (@{update.effective_user.username})\n"
        admin_message += f"🆔 User ID: {update.effective_user.id}\n\n"
        admin_message += format_cart(cart, context.user_data)
        admin_message += f"\n💰 Total: {total}€\n\n"
        admin_message += f"🌍 Pays: {country}\n"
        admin_message += f"📍 Adresse: {context.user_data['adresse']}\n"
        admin_message += f"📦 Livraison: {context.user_data['livraison']}\n"
        admin_message += f"💳 Paiement: {context.user_data['paiement']}\n"
        
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Erreur envoi admin: {e}")
        
        await query.message.edit_text(
            tr(context.user_data, "order_confirmed"),
            parse_mode='Markdown'
        )
        
        context.user_data.clear()
        return ConversationHandler.END

@security_check
@error_handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulation de la commande"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        tr(context.user_data, "order_cancelled"),
        parse_mode='Markdown'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Gestion des erreurs globales ---
async def error_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion des erreurs globales"""
    logger.error(f"Exception: {context.error}", exc_info=context.error)

# --- Configuration du bot ---
def main():
    """Fonction principale"""
    logger.info("🚀 Démarrage du bot...")
    
    application = Application.builder().token(TOKEN).build()
    
    # ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            LANGUE: [
                CallbackQueryHandler(set_langue, pattern='^lang_')
            ],
            PAYS: [
                CallbackQueryHandler(menu_navigation, pattern='^(start_order|price_menu|info|contact_admin|back_menu)),
                CallbackQueryHandler(choix_pays, pattern='^country_')
            ],
            PRODUIT: [
                CallbackQueryHandler(choix_produit, pattern='^product_'),
                CallbackQueryHandler(cancel, pattern='^cancel)
            ],
            PILL_SUBCATEGORY: [
                CallbackQueryHandler(choix_pill_subcategory, pattern='^(pill_|back_to_products)'),
                CallbackQueryHandler(cancel, pattern='^cancel)
            ],
            QUANTITE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)
            ],
            CART_MENU: [
                CallbackQueryHandler(cart_menu, pattern='^(add_more|proceed_checkout)),
                CallbackQueryHandler(cancel, pattern='^cancel)
            ],
            ADRESSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse)
            ],
            LIVRAISON: [
                CallbackQueryHandler(choix_livraison, pattern='^delivery_'),
                CallbackQueryHandler(cancel, pattern='^cancel)
            ],
            PAIEMENT: [
                CallbackQueryHandler(choix_paiement, pattern='^payment_'),
                CallbackQueryHandler(cancel, pattern='^cancel)
            ],
            CONFIRMATION: [
                CallbackQueryHandler(confirmation, pattern='^confirm_order),
                CallbackQueryHandler(cancel, pattern='^cancel)
            ]
        },
        fallbacks=[
            CommandHandler('start', start_command),
            CallbackQueryHandler(cancel, pattern='^cancel)
        ]
    )
    
    application.add_handler(conv_handler)
    application.add_error_handler(error_callback)
    
    logger.info("✅ Bot démarré avec succès!")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Bot arrêté par l'utilisateur")
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}", exc_info=True)
        sys.exit(1)
