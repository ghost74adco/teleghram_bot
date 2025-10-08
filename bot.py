import os
import sys
import logging
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler('bot_errors.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- Chargement des variables d'environnement ---
dotenv_path = Path(__file__).parent / "infos.env"
load_dotenv(dotenv_path)

def validate_environment():
    required_vars = {
        'TELEGRAM_TOKEN': '8474087335:AAGQnYnj5gTmtHphvfUHME8h84ygwQejl7Y',
        'ADMIN_ID': '8450278584',
        'CRYPTO_WALLET': '3AbkDZtRVXUMdBSejXMNg6pEGMcxfCRpQL'
    }
    missing, invalid = [], []
    for var, desc in required_vars.items():
        value = os.getenv(var)
        if not value:
            missing.append(f"{var} ({desc})")
        else:
            value = value.strip()
            if var == 'TELEGRAM_TOKEN' and (':' not in value or len(value) < 40):
                invalid.append(f"{var}: format invalide (NUMBER:HASH)")
            elif var == 'ADMIN_ID' and not value.isdigit():
                invalid.append(f"{var}: doit être un nombre")
            elif var == 'CRYPTO_WALLET' and len(value) < 20:
                invalid.append(f"{var}: format invalide")
    if missing or invalid:
        msg = "❌ ERREURS DE CONFIGURATION:\n"
        if missing:
            msg += "\nVariables manquantes:\n" + "\n".join(f"- {v}" for v in missing)
        if invalid:
            msg += "\nVariables invalides:\n" + "\n".join(f"- {v}" for v in invalid)
        logger.error(msg)
        print(msg)
        sys.exit(1)
    logger.info("✅ Toutes les variables d'environnement sont valides")

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
from telegram.error import NetworkError, TimedOut, TelegramError
import asyncio

# --- États ---
LANGUE, PAYS, PRODUIT, QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(9)

# --- Mapping produit ---
PRODUCT_MAP = {
    "snow": "❄️",
    "pill": "💊",
    "olive": "🫒",
    "clover": "🍀"
}

PRODUCT_REVERSE_MAP = {v: k for k, v in PRODUCT_MAP.items()}

# --- Prix ---
PRIX_FR = {"❄️": 80, "💊": 10, "🫒": 7, "🍀": 10}
PRIX_CH = {"❄️": 100, "💊": 15, "🫒": 8, "🍀": 12}

# --- Traductions statiques ---
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
        "invalid_quantity": "❌ Veuillez entrer un nombre valide supérieur à 0.",
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
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Suisse",
        "standard": "📦 Standard",
        "express": "⚡ Express",
        "cash": "💵 Espèces",
        "crypto": "₿ Crypto"
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
        "invalid_quantity": "❌ Please enter a valid number greater than 0.",
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
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Switzerland",
        "standard": "📦 Standard",
        "express": "⚡ Express",
        "cash": "💵 Cash",
        "crypto": "₿ Crypto"
    },
    "es": {
        "welcome": "🌿 *BIENVENIDO* 🌿\n\n⚠️ *IMPORTANTE:*\nTodas las conversaciones deben establecerse en *INTERCAMBIO SECRETO*.\n\n🙏 *Gracias* 💪💚",
        "choose_language": "🌍 *Seleccione su idioma:*",
        "main_menu": "\n\n📱 *MENÚ PRINCIPAL:*\n\n👇 Elija una opción:",
        "choose_country": "🌍 *Elija su país:*",
        "choose_product": "🛍️ *Elija su producto:*",
        "enter_quantity": "📝 *Ingrese la cantidad deseada:*",
        "enter_address": "📍 *Ingrese su dirección completa:*",
        "choose_delivery": "📦 *Elija el tipo de envío:*",
        "choose_payment": "💳 *Elija el método de pago:*",
        "order_summary": "✅ *Resumen de su pedido:*",
        "confirm": "✅ Confirmar",
        "cancel": "❌ Cancelar",
        "order_confirmed": "✅ *¡Pedido confirmado!*\n\nGracias por su pedido.\nSerá contactado pronto. 📞",
        "order_cancelled": "❌ *Pedido cancelado.*",
        "add_more": "➕ Agregar producto",
        "proceed": "✅ Finalizar",
        "invalid_quantity": "❌ Por favor ingrese un número válido mayor a 0.",
        "cart_title": "🛒 *Su carrito:*",
        "info_title": "ℹ️ *INFORMACIÓN*",
        "info_shop": "🛍️ *Nuestra tienda:*\n• Entrega Francia 🇫🇷 & Suiza 🇨🇭\n• Productos de calidad\n• Servicio al cliente receptivo",
        "info_delivery": "📦 *Entrega:*\n• Estándar: 3-5 días\n• Express: 24-48h",
        "info_payment": "💳 *Pago:*\n• Efectivo contra entrega\n• Crypto (Bitcoin, USDT)",
        "info_security": "🔒 *Seguridad:*\nTodos los intercambios están encriptados y son confidenciales.",
        "contact_title": "📞 *CONTACTO*",
        "contact_text": "Para cualquier pregunta o asistencia, puede:\n\n• Continuar con el pedido\n• Contactar al administrador\n\n¡Nuestro equipo está disponible 24/7 para ayudarle! 💬",
        "start_order": "🛍️ Ordenar",
        "informations": "ℹ️ Información",
        "contact": "📞 Contacto",
        "back": "🔙 Volver",
        "contact_admin": "💬 Contactar Admin",
        "france": "🇫🇷 Francia",
        "switzerland": "🇨🇭 Suiza",
        "standard": "📦 Estándar",
        "express": "⚡ Express",
        "cash": "💵 Efectivo",
        "crypto": "₿ Crypto"
    },
    "de": {
        "welcome": "🌿 *WILLKOMMEN* 🌿\n\n⚠️ *WICHTIG:*\nAlle Gespräche müssen im *GEHEIMEN AUSTAUSCH* geführt werden.\n\n🙏 *Danke* 💪💚",
        "choose_language": "🌍 *Wählen Sie Ihre Sprache:*",
        "main_menu": "\n\n📱 *HAUPTMENÜ:*\n\n👇 Wählen Sie eine Option:",
        "choose_country": "🌍 *Wählen Sie Ihr Land:*",
        "choose_product": "🛍️ *Wählen Sie Ihr Produkt:*",
        "enter_quantity": "📝 *Geben Sie die gewünschte Menge ein:*",
        "enter_address": "📍 *Geben Sie Ihre vollständige Adresse ein:*",
        "choose_delivery": "📦 *Wählen Sie die Versandart:*",
        "choose_payment": "💳 *Wählen Sie die Zahlungsmethode:*",
        "order_summary": "✅ *Zusammenfassung Ihrer Bestellung:*",
        "confirm": "✅ Bestätigen",
        "cancel": "❌ Abbrechen",
        "order_confirmed": "✅ *Bestellung bestätigt!*\n\nVielen Dank für Ihre Bestellung.\nSie werden bald kontaktiert. 📞",
        "order_cancelled": "❌ *Bestellung abgebrochen.*",
        "add_more": "➕ Produkt hinzufügen",
        "proceed": "✅ Zur Kasse",
        "invalid_quantity": "❌ Bitte geben Sie eine gültige Zahl größer als 0 ein.",
        "cart_title": "🛒 *Ihr Warenkorb:*",
        "info_title": "ℹ️ *INFORMATION*",
        "info_shop": "🛍️ *Unser Shop:*\n• Lieferung Frankreich 🇫🇷 & Schweiz 🇨🇭\n• Qualitätsprodukte\n• Reaktiver Kundenservice",
        "info_delivery": "📦 *Lieferung:*\n• Standard: 3-5 Tage\n• Express: 24-48h",
        "info_payment": "💳 *Zahlung:*\n• Barzahlung bei Lieferung\n• Krypto (Bitcoin, USDT)",
        "info_security": "🔒 *Sicherheit:*\nAlle Austausche sind verschlüsselt und vertraulich.",
        "contact_title": "📞 *KONTAKT*",
        "contact_text": "Für Fragen oder Unterstützung können Sie:\n\n• Mit der Bestellung fortfahren\n• Den Administrator kontaktieren\n\nUnser Team ist 24/7 verfügbar, um Ihnen zu helfen! 💬",
        "start_order": "🛍️ Bestellen",
        "informations": "ℹ️ Information",
        "contact": "📞 Kontakt",
        "back": "🔙 Zurück",
        "contact_admin": "💬 Admin Kontaktieren",
        "france": "🇫🇷 Frankreich",
        "switzerland": "🇨🇭 Schweiz",
        "standard": "📦 Standard",
        "express": "⚡ Express",
        "cash": "💵 Bargeld",
        "crypto": "₿ Krypto"
    }
}

# --- Gestionnaire d'erreurs et notification admin ---
async def notify_admin_error(context: ContextTypes.DEFAULT_TYPE, msg: str):
    """Notifie l'admin en cas d'erreur critique"""
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 ERREUR BOT\n\n{msg}")
    except Exception as e:
        logger.error(f"Impossible d'envoyer la notification admin: {e}")

def error_handler_decorator(func):
    """Décorateur pour gérer les erreurs dans les handlers"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            user_id = update.effective_user.id if update.effective_user else "Unknown"
            error_msg = f"Erreur dans {func.__name__}\nUser: {user_id}\nErreur: {str(e)}"
            logger.error(error_msg, exc_info=True)
            await notify_admin_error(context, error_msg)
            
            # Message utilisateur
            try:
                if hasattr(update, "callback_query") and update.callback_query:
                    await update.callback_query.answer("❌ Une erreur s'est produite.")
                    await update.callback_query.message.reply_text(
                        "❌ Une erreur s'est produite. L'admin a été notifié.\n"
                        "Utilisez /start pour recommencer."
                    )
                elif hasattr(update, "message") and update.message:
                    await update.message.reply_text(
                        "❌ Une erreur s'est produite. L'admin a été notifié.\n"
                        "Utilisez /start pour recommencer."
                    )
            except Exception as notify_error:
                logger.error(f"Erreur lors de la notification utilisateur: {notify_error}")
            
            return ConversationHandler.END
    return wrapper

async def error_callback(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Callback global pour les erreurs non gérées"""
    logger.error("Exception non gérée:", exc_info=context.error)
    
    # Ignorer les erreurs réseau temporaires
    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.info("Erreur réseau temporaire ignorée")
        return
    
    # Notifier l'admin pour les autres erreurs
    error_msg = f"Type: {type(context.error).__name__}\nMessage: {str(context.error)}"
    await notify_admin_error(context, error_msg)

# --- Fonctions utilitaires ---
def tr(user_data, key):
    """Récupère une traduction selon la langue de l'utilisateur"""
    lang = user_data.get("langue", "fr")
    return TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)

def calculate_total(cart, country):
    """Calcule le total du panier"""
    prix_table = PRIX_FR if country == "FR" else PRIX_CH
    total = 0
    for item in cart:
        total += prix_table[item["produit"]] * int(item["quantite"])
    return total

def format_cart(cart, user_data):
    """Formate le panier pour l'affichage"""
    if not cart:
        return ""
    
    cart_text = f"\n{tr(user_data, 'cart_title')}\n"
    for item in cart:
        cart_text += f"• {item['produit']} x {item['quantite']}\n"
    return cart_text

async def delete_conversation(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_ids: list):
    """Supprime tous les messages de la conversation après 1 minute"""
    await asyncio.sleep(60)  # Attendre 1 minute
    
    deleted_count = 0
    failed_count = 0
    
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            deleted_count += 1
        except TelegramError as e:
            logger.warning(f"Impossible de supprimer le message {msg_id}: {e}")
            failed_count += 1
    
    logger.info(f"🗑️ Conversation supprimée: {deleted_count} messages supprimés, {failed_count} échecs")
    
    # Notification admin (optionnelle)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🗑️ Conversation auto-supprimée\n└─ User ID: {chat_id}\n└─ Messages: {deleted_count}/{deleted_count + failed_count}"
        )
    except Exception as e:
        logger.error(f"Erreur notification suppression: {e}")

async def safe_edit_message(query, text=None, caption=None, reply_markup=None, parse_mode='Markdown'):
    """Édite un message de manière sécurisée (photo ou texte)"""
    try:
        if query.message.photo:
            if caption:
                await query.message.edit_caption(
                    caption=caption, 
                    reply_markup=reply_markup, 
                    parse_mode=parse_mode
                )
        else:
            if text:
                await query.message.edit_text(
                    text=text, 
                    reply_markup=reply_markup, 
                    parse_mode=parse_mode
                )
    except TelegramError as e:
        logger.warning(f"Erreur lors de l'édition du message: {e}")
        # Fallback: envoyer un nouveau message
        if text:
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        elif caption:
            await query.message.reply_text(caption, reply_markup=reply_markup, parse_mode=parse_mode)

# --- Commande /start ---
@error_handler_decorator
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Point d'entrée principal du bot"""
    context.user_data.clear()
    
    # Initialiser la liste de tracking des messages
    context.user_data['message_ids'] = []
    
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
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Envoyer l'image de bienvenue si elle existe
    image_path = Path(__file__).parent / "welcome_image.jpg"
    
    if update.message:
        # Stocker l'ID du message de l'utilisateur
        context.user_data['message_ids'].append(update.message.message_id)
        
        if image_path.exists():
            try:
                with open(image_path, 'rb') as photo:
                    sent_msg = await update.message.reply_photo(
                        photo=photo,
                        caption=welcome_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    context.user_data['message_ids'].append(sent_msg.message_id)
            except Exception as e:
                logger.warning(f"Impossible de charger l'image: {e}")
                sent_msg = await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
                context.user_data['message_ids'].append(sent_msg.message_id)
        else:
            sent_msg = await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
            context.user_data['message_ids'].append(sent_msg.message_id)
    
    return LANGUE

@error_handler_decorator
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit la langue et affiche le menu principal"""
    query = update.callback_query
    await query.answer()
    
    lang_code = query.data.replace("lang_", "")
    context.user_data['langue'] = lang_code
    
    welcome_text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "informations"), callback_data="info")],
        [InlineKeyboardButton(tr(context.user_data, "contact"), callback_data="contact_admin")]
    ]
    
    await safe_edit_message(query, text=welcome_text, caption=welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
    return PAYS

@error_handler_decorator
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la navigation dans les menus (info, contact, retour)"""
    query = update.callback_query
    await query.answer()
    
    # Vérifier si la langue est définie
    if 'langue' not in context.user_data:
        context.user_data['langue'] = 'fr'
    
    # Bouton "Commander"
    if query.data == "start_order":
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
            [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_menu")]
        ]
        await safe_edit_message(
            query, 
            text=tr(context.user_data, "choose_country"),
            caption=tr(context.user_data, "choose_country"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return PAYS
    
    # Bouton "Informations"
    elif query.data == "info":
        info_text = (
            f"{tr(context.user_data, 'info_title')}\n\n"
            f"{tr(context.user_data, 'info_shop')}\n\n"
            f"{tr(context.user_data, 'info_delivery')}\n\n"
            f"{tr(context.user_data, 'info_payment')}\n\n"
            f"{tr(context.user_data, 'info_security')}"
        )
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_menu")]
        ]
        await safe_edit_message(query, text=info_text, caption=info_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return PAYS
    
    # Bouton "Contact"
    elif query.data == "contact_admin":
        contact_text = f"{tr(context.user_data, 'contact_title')}\n\n{tr(context.user_data, 'contact_text')}"
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "contact_admin"), url=f"tg://user?id={ADMIN_ID}")],
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_menu")]
        ]
        await safe_edit_message(query, text=contact_text, caption=contact_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return PAYS
    
    # Bouton "Retour au menu"
    elif query.data == "back_menu":
        welcome_text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
            [InlineKeyboardButton(tr(context.user_data, "informations"), callback_data="info")],
            [InlineKeyboardButton(tr(context.user_data, "contact"), callback_data="contact_admin")]
        ]
        await safe_edit_message(query, text=welcome_text, caption=welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return PAYS
    
    return PAYS

# --- Gestion du processus de commande ---
@error_handler_decorator
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du pays et initialisation du panier"""
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
    
    # ✅ CORRECTION : Utilisation de safe_edit_message
    await safe_edit_message(
        query,
        text=tr(context.user_data, "choose_product"),
        caption=tr(context.user_data, "choose_product"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return PRODUIT

@error_handler_decorator
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du produit"""
    query = update.callback_query
    await query.answer()
    
    product_code = query.data.replace("product_", "")
    product_emoji = PRODUCT_MAP.get(product_code, product_code)
    context.user_data['current_product'] = product_emoji
    
    # ✅ CORRECTION : utilisation de safe_edit_message au lieu de edit_text
    await safe_edit_message(
        query,
        text=f"{tr(context.user_data, 'choose_product')}\n\n✅ Produit: {product_emoji}\n\n{tr(context.user_data, 'enter_quantity')}",
        caption=f"{tr(context.user_data, 'choose_product')}\n\n✅ Produit: {product_emoji}\n\n{tr(context.user_data, 'enter_quantity')}",
        parse_mode='Markdown'
    )
    return QUANTITE

@error_handler_decorator
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validation et ajout de la quantité au panier"""
    qty = update.message.text.strip()
    
    # Stocker l'ID du message de l'utilisateur
    context.user_data['message_ids'].append(update.message.message_id)
    
    if not qty.isdigit() or int(qty) <= 0:
        sent_msg = await update.message.reply_text(tr(context.user_data, "invalid_quantity"))
        context.user_data['message_ids'].append(sent_msg.message_id)
        return QUANTITE
    
    # Ajouter au panier
    context.user_data['cart'].append({
        "produit": context.user_data['current_product'],
        "quantite": qty
    })
    
    # Afficher le panier
    cart_summary = format_cart(context.user_data['cart'], context.user_data)
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "add_more"), callback_data="add_more")],
        [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    
    sent_msg = await update.message.reply_text(
        cart_summary, 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    context.user_data['message_ids'].append(sent_msg.message_id)
    return CART_MENU

@error_handler_decorator
async def cart_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion du menu du panier (ajouter/valider)"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_more":
        # Retour au choix de produit
        keyboard = [
            [InlineKeyboardButton("❄️", callback_data="product_snow")],
            [InlineKeyboardButton("💊", callback_data="product_pill")],
            [InlineKeyboardButton("🫒", callback_data="product_olive")],
            [InlineKeyboardButton("🍀", callback_data="product_clover")],
            [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
        ]
        # ✅ CORRECTION : safe_edit_message
        await safe_edit_message(
            query,
            text=tr(context.user_data, "choose_product"), 
            caption=tr(context.user_data, "choose_product"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return PRODUIT
    
    elif query.data == "proceed_checkout":
        # Passer à l'adresse
        # ✅ CORRECTION : safe_edit_message
        await safe_edit_message(
            query,
            text=tr(context.user_data, "enter_address"),
            caption=tr(context.user_data, "enter_address"),
            parse_mode='Markdown'
        )
        return ADRESSE
    
    return CART_MENU

@error_handler_decorator
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validation de l'adresse de livraison"""
    context.user_data['adresse'] = update.message.text.strip()
    
    # Stocker l'ID du message de l'utilisateur
    context.user_data['message_ids'].append(update.message.message_id)
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "standard"), callback_data="delivery_standard")],
        [InlineKeyboardButton(tr(context.user_data, "express"), callback_data="delivery_express")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    sent_msg = await update.message.reply_text(
        tr(context.user_data, "choose_delivery"), 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    context.user_data['message_ids'].append(sent_msg.message_id)
    return LIVRAISON

@error_handler_decorator
async def choix_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du mode de livraison"""
    query = update.callback_query
    await query.answer()
    
    delivery_type = query.data.replace("delivery_", "")
    context.user_data['livraison'] = delivery_type
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "cash"), callback_data="payment_cash")],
        [InlineKeyboardButton(tr(context.user_data, "crypto"), callback_data="payment_crypto")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    # ✅ CORRECTION : safe_edit_message
    await safe_edit_message(
        query,
        text=tr(context.user_data, "choose_payment"), 
        caption=tr(context.user_data, "choose_payment"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PAIEMENT

@error_handler_decorator
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du mode de paiement et affichage du résumé"""
    query = update.callback_query
    await query.answer()
    
    payment_type = query.data.replace("payment_", "")
    context.user_data['paiement'] = payment_type
    
    # Calcul du total
    total = calculate_total(context.user_data['cart'], context.user_data['pays'])
    summary = f"{tr(context.user_data, 'order_summary')}\n\n"
    
    # Détail des produits
    prix_table = PRIX_FR if context.user_data['pays'] == "FR" else PRIX_CH
    for item in context.user_data['cart']:
        prix_unitaire = prix_table[item['produit']]
        subtotal = prix_unitaire * int(item['quantite'])
        summary += f"• {item['produit']} x {item['quantite']} = {subtotal}€\n"
    
    summary += f"\n📍 Adresse: {context.user_data['adresse']}\n"
    summary += f"📦 Livraison: {context.user_data['livraison']}\n"
    summary += f"💳 Paiement: {context.user_data['paiement']}\n"
    summary += f"\n💰 TOTAL: {total}€"
    
    # Ajout du wallet crypto si nécessaire
    if context.user_data['paiement'] == 'crypto':
        summary += f"\n\n₿ Wallet: `{CRYPTO_WALLET}`"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "confirm"), callback_data="confirm_order")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    # ✅ CORRECTION : safe_edit_message
    await safe_edit_message(
        query,
        text=summary, 
        caption=summary,
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='Markdown'
    )
    return CONFIRMATION

@error_handler_decorator
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation finale de la commande"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_order":
        # ✅ CORRECTION : safe_edit_message au lieu de edit_text
        await safe_edit_message(
            query,
            text=tr(context.user_data, "order_confirmed"),
            caption=tr(context.user_data, "order_confirmed"),
            parse_mode='Markdown'
        )
        
        # Notification admin détaillée
        total = calculate_total(context.user_data['cart'], context.user_data['pays'])
        user = query.from_user
        
        order_details = "🔔 NOUVELLE COMMANDE\n"
        order_details += "=" * 30 + "\n\n"
        
        order_details += "👤 INFORMATIONS CLIENT:\n"
        order_details += f"├─ ID: {user.id}\n"
        order_details += f"├─ Username: @{user.username if user.username else 'N/A'}\n"
        order_details += f"└─ Nom: {user.first_name} {user.last_name or ''}\n\n"
        
        order_details += "🛒 PRODUITS COMMANDÉS:\n"
        prix_table = PRIX_FR if context.user_data['pays'] == "FR" else PRIX_CH
        for idx, item in enumerate(context.user_data['cart'], 1):
            prix_unitaire = prix_table[item['produit']]
            subtotal = prix_unitaire * int(item['quantite'])
            order_details += f"├─ {idx}. {item['produit']} x {item['quantite']} = {subtotal}€\n"
        
        order_details += f"\n📦 DÉTAILS LIVRAISON:\n"
        order_details += f"├─ Pays: {context.user_data['pays']}\n"
        order_details += f"├─ Adresse: {context.user_data['adresse']}\n"
        order_details += f"└─ Type: {context.user_data['livraison']}\n\n"
        
        order_details += f"💳 PAIEMENT:\n"
        order_details += f"├─ Méthode: {context.user_data['paiement']}\n"
        order_details += f"└─ MONTANT TOTAL: {total}€\n"
        order_details += "=" * 30
        
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=order_details)
            logger.info(f"✅ Commande confirmée pour l'utilisateur {user.id}")
            
            # Récupérer tous les IDs de messages pour suppression
            message_ids = context.user_data.get('message_ids', [])
            
            # Ajouter l'ID du message de confirmation
            message_ids.append(query.message.message_id)
            
            # Lancer la suppression automatique après 1 minute
            chat_id = query.message.chat_id
            logger.info(f"⏰ Suppression auto programmée pour {len(message_ids)} messages (User: {user.id})")
            
            # Créer une tâche asynchrone pour la suppression
            asyncio.create_task(delete_conversation(context, chat_id, message_ids))
            
        except Exception as e:
            logger.error(f"Erreur envoi notification admin: {e}")
    
    context.user_data.clear()
    return ConversationHandler.END

@error_handler_decorator
async def annuler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulation de la commande"""
    query = update.callback_query
    await query.answer()
    
    # ✅ CORRECTION : safe_edit_message
    await safe_edit_message(
        query,
        text=tr(context.user_data, "order_cancelled"),
        caption=tr(context.user_data, "order_cancelled"),
        parse_mode='Markdown'
    )
    context.user_data.clear()
    return ConversationHandler.END

# --- Main ---
if __name__ == "__main__":
    # Création de l'application
    application = Application.builder().token(TOKEN).build()
    
    # Ajout du gestionnaire d'erreurs global
    application.add_error_handler(error_callback)

    # ConversationHandler principal avec CORRECTION
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command)
        ],
        states={
            LANGUE: [
                CallbackQueryHandler(set_langue, pattern="^lang_(fr|en|es|de)$")
            ],
            PAYS: [
                # ✅ CORRECTION CRITIQUE : choix_pays AVANT menu_navigation
                CallbackQueryHandler(choix_pays, pattern="^country_(FR|CH)$"),
                CallbackQueryHandler(menu_navigation, pattern="^(start_order|info|contact_admin|back_menu)$")
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
        allow_reentry=True
    )

    application.add_handler(conv_handler)

    logger.info("=" * 50)
    logger.info("🚀 Bot démarré avec succès!")
    logger.info(f"📊 États disponibles: LANGUE, PAYS, PRODUIT, QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION")
    logger.info(f"🔑 Admin ID: {ADMIN_ID}")
    logger.info(f"💬 Langues disponibles: FR, EN, ES, DE")
    logger.info("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)
