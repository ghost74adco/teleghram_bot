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
        'TELEGRAM_TOKEN': 'Token du bot Telegram',
        'ADMIN_ID': 'ID de l\'administrateur',
        'CRYPTO_WALLET': 'Adresse du wallet crypto'
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
from telegram.error import NetworkError, TimedOut

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
        "info_delivery": "📦 *Livraison :*\n• Standard : 1-3 jours\n• Express",
        "info_payment": "💳 *Paiement :*\n• Espèces à la livraison\n• Crypto (Bitcoin)",
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
        "info_delivery": "📦 *Delivery:*\n• Standard: 1-3 days\n• Express",
        "info_payment": "💳 *Payment:*\n• Cash on delivery\n• Crypto (Bitcoin)",
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
        "info_delivery": "📦 *Entrega:*\n• Estándar: 1-3 días\n• Express",
        "info_payment": "💳 *Pago:*\n• Efectivo contra entrega\n• Crypto (Bitcoin)",
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
        "info_delivery": "📦 *Lieferung:*\n• Standard: 1-3 Tage\n• Express",
        "info_payment": "💳 *Zahlung:*\n• Barzahlung bei Lieferung\n• Krypto (Bitcoin)",
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
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 ERREUR BOT\n\n{msg}")
    except Exception as e:
        logger.error(f"Impossible d'envoyer la notification: {e}")

def error_handler_decorator(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            user_id = update.effective_user.id if update.effective_user else "Unknown"
            error_msg = f"Erreur dans {func.__name__} | User: {user_id}\n{e}"
            logger.error(error_msg, exc_info=True)
            await notify_admin_error(context, error_msg)
            if update.effective_message:
                await update.effective_message.reply_text("❌ Une erreur s'est produite. L'admin a été notifié.")
            return ConversationHandler.END
    return wrapper

async def error_callback(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception:", exc_info=context.error)
    if isinstance(context.error, (NetworkError, TimedOut)):
        return
    await notify_admin_error(context, f"Type: {type(context.error).__name__}\nMessage: {context.error}")

# --- Fonctions utilitaires ---
def tr(user_data, key):
    lang = user_data.get("langue", "fr")
    return TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)

def calculate_total(cart, country):
    prix_table = PRIX_FR if country == "FR" else PRIX_CH
    total = 0
    for item in cart:
        total += prix_table[item["produit"]] * int(item["quantite"])
    return total

def format_cart(cart, user_data):
    """Formatte le panier pour l'affichage"""
    if not cart:
        return ""
    
    cart_text = f"\n{tr(user_data, 'cart_title')}\n"
    for item in cart:
        cart_text += f"• {item['produit']} x {item['quantite']}\n"
    return cart_text

# --- Commande /start ---
@error_handler_decorator
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    
    # Message de bienvenue avec design
    welcome_text = (
        "🌿 *BIENVENUE, WELCOME* 🌿\n\n"
        "⚠️ *IMPORTANT :*\n"
        "Toutes les conversations doivent être établies en *ÉCHANGE SECRET*.\n\n"
        "🙏 *Merci* 💪💚\n\n"
        "📞 Pour me joindre : utilisez le bouton *Contact*\n"
        "ℹ️ Infos : consultez la rubrique *Informations*\n"
        "📱 Menu : accédez à la *Mini App*\n\n"
        "👇 *Sélectionnez votre langue pour commencer :*"
    )
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
        [InlineKeyboardButton("ℹ️ Informations", callback_data="info")],
        [InlineKeyboardButton("📞 Contact", callback_data="contact_admin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Envoyer l'image de bienvenue (vous devez mettre votre image dans le dossier du bot)
    image_path = Path(__file__).parent / "welcome_image.jpg"
    
    if update.message:
        # Si l'image existe, l'envoyer
        if image_path.exists():
            with open(image_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=welcome_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            # Sinon, envoyer juste le texte
            await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    return LANGUE

@error_handler_decorator
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Gestion des boutons spéciaux
    if query.data == "info":
        info_text = (
            "ℹ️ *INFORMATIONS*\n\n"
            "🛍️ *Notre boutique :*\n"
            "• Livraison France 🇫🇷 & Suisse 🇨🇭\n"
            "• Produits de qualité\n"
            "• Service client réactif\n\n"
            "📦 *Livraison :*\n"
            "• Standard : 1-3 jours\n"
            "• Express\n\n"
            "💳 *Paiement :*\n"
            "• Espèces à la livraison\n"
            "• Crypto (Bitcoin\n\n"
            "🔒 *Sécurité :*\n"
            "Tous les échanges sont cryptés et confidentiels.\n\n"
            "👇 Choisissez votre langue pour commander :"
        )
        keyboard = [
            [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
            [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
            [InlineKeyboardButton("🔙 Retour", callback_data="back_start")]
        ]
        # Vérifier si c'est une photo ou du texte
        if query.message.photo:
            await query.message.edit_caption(caption=info_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await query.message.edit_text(text=info_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return LANGUE
    
    if query.data == "contact_admin":
        contact_text = (
            "📞 *CONTACT*\n\n"
            "Pour toute question ou besoin d'assistance, vous pouvez :\n\n"
            "• Continuer avec la commande\n"
            "• Contacter l'administrateur\n\n"
            "Notre équipe est disponible 24/7 pour vous aider ! 💬\n\n"
            "👇 Choisissez votre langue pour commencer :"
        )
        keyboard = [
            [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
            [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
            [InlineKeyboardButton("💬 Contacter Admin", url=f"tg://user?id={ADMIN_ID}")],
            [InlineKeyboardButton("🔙 Retour", callback_data="back_start")]
        ]
        # Vérifier si c'est une photo ou du texte
        if query.message.photo:
            await query.message.edit_caption(caption=contact_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await query.message.edit_text(text=contact_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return LANGUE
    
    if query.data == "back_start":
        # Retourner au message de bienvenue
        welcome_text = (
            "🌿 *BIENVENUE, WELCOME* 🌿\n\n"
            "⚠️ *IMPORTANT :*\n"
            "Toutes les conversations doivent être établies en *ÉCHANGE SECRET*.\n\n"
            "🙏 *Merci* 💪💚\n\n"
            "📞 Pour me joindre : utilisez le bouton *Contact*\n"
            "ℹ️ Infos : consultez la rubrique *Informations*\n"
            "📱 Menu : accédez à la *Mini App*\n\n"
            "👇 *Sélectionnez votre langue pour commencer :*"
        )
        keyboard = [
            [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
            [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
            [InlineKeyboardButton("ℹ️ Informations", callback_data="info")],
            [InlineKeyboardButton("📞 Contact", callback_data="contact_admin")]
        ]
        # Vérifier si c'est une photo ou du texte
        if query.message.photo:
            await query.message.edit_caption(caption=welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await query.message.edit_text(text=welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return LANGUE
    
    # Sélection de langue normale
    lang_code = query.data.replace("lang_", "")
    context.user_data['langue'] = lang_code
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data="country_FR")],
        [InlineKeyboardButton("🇨🇭 Suisse", callback_data="country_CH")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    
    # Vérifier si c'est une photo ou du texte
    if query.message.photo:
        await query.message.edit_caption(caption=tr(context.user_data, "choose_country"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await query.message.edit_text(text=tr(context.user_data, "choose_country"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

# --- Gestion du panier multi-produits ---
@error_handler_decorator
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard))
    return PRODUIT

@error_handler_decorator
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_code = query.data.replace("product_", "")
    product_emoji = PRODUCT_MAP.get(product_code, product_code)
    context.user_data['current_product'] = product_emoji
    
    await query.message.edit_text(f"{tr(context.user_data, 'choose_product')}\n\n✅ Produit: {product_emoji}\n\n{tr(context.user_data, 'enter_quantity')}")
    return QUANTITE

@error_handler_decorator
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qty = update.message.text.strip()
    
    if not qty.isdigit() or int(qty) <= 0:
        await update.message.reply_text(tr(context.user_data, "invalid_quantity"))
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
    
    await update.message.reply_text(cart_summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return CART_MENU

@error_handler_decorator
async def cart_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard))
        return PRODUIT
    elif query.data == "proceed_checkout":
        # Passer à l'adresse
        await query.message.edit_text(tr(context.user_data, "enter_address"))
        return ADRESSE
    
    return CART_MENU

@error_handler_decorator
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['adresse'] = update.message.text.strip()
    
    keyboard = [
        [InlineKeyboardButton("📦 Standard", callback_data="delivery_standard")],
        [InlineKeyboardButton("⚡ Express", callback_data="delivery_express")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    await update.message.reply_text(tr(context.user_data, "choose_delivery"), reply_markup=InlineKeyboardMarkup(keyboard))
    return LIVRAISON

@error_handler_decorator
async def choix_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    delivery_type = query.data.replace("delivery_", "")
    context.user_data['livraison'] = delivery_type
    
    keyboard = [
        [InlineKeyboardButton("💵 Espèces", callback_data="payment_cash")],
        [InlineKeyboardButton("₿ Crypto", callback_data="payment_crypto")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    await query.message.edit_text(tr(context.user_data, "choose_payment"), reply_markup=InlineKeyboardMarkup(keyboard))
    return PAIEMENT

@error_handler_decorator
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payment_type = query.data.replace("payment_", "")
    context.user_data['paiement'] = payment_type
    
    total = calculate_total(context.user_data['cart'], context.user_data['pays'])
    summary = f"{tr(context.user_data, 'order_summary')}\n\n"
    
    prix_table = PRIX_FR if context.user_data['pays'] == "FR" else PRIX_CH
    for item in context.user_data['cart']:
        prix_unitaire = prix_table[item['produit']]
        subtotal = prix_unitaire * int(item['quantite'])
        summary += f"• {item['produit']} x {item['quantite']} = {subtotal}€\n"
    
    summary += f"\n📍 Adresse: {context.user_data['adresse']}\n"
    summary += f"📦 Livraison: {context.user_data['livraison']}\n"
    summary += f"💳 Paiement: {context.user_data['paiement']}\n"
    summary += f"\n💰 TOTAL: {total}€"
    
    if context.user_data['paiement'] == 'crypto':
        summary += f"\n\n₿ Wallet: `{CRYPTO_WALLET}`"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "confirm"), callback_data="confirm_order")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    await query.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CONFIRMATION

@error_handler_decorator
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_order":
        await query.message.edit_text(tr(context.user_data, "order_confirmed"))
        
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
        except Exception as e:
            logger.error(f"Erreur envoi notification admin: {e}")
    
    context.user_data.clear()
    return ConversationHandler.END

@error_handler_decorator
async def annuler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(tr(context.user_data, "order_cancelled"))
    context.user_data.clear()
    return ConversationHandler.END

# --- Main ---
if __name__ == "__main__":
    application = Application.builder().token(TOKEN).build()
    application.add_error_handler(error_callback)

    # Handler global pour /start (accessible à tout moment)
    application.add_handler(CommandHandler("start", start_command))
    
    # Handler pour sélection de langue et menus spéciaux (en dehors du ConversationHandler)
    application.add_handler(CallbackQueryHandler(set_langue, pattern="^(lang_(fr|en|es|de)|info|contact_admin|back_start)$"))

    # ConversationHandler principal
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(choix_pays, pattern="^country_(FR|CH)$")
        ],
        states={
            PAYS: [
                CallbackQueryHandler(choix_pays, pattern="^country_(FR|CH)$")
            ],
            PRODUIT: [
                CallbackQueryHandler(choix_produit, pattern="^product_")
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
                CallbackQueryHandler(choix_livraison, pattern="^delivery_")
            ],
            PAIEMENT: [
                CallbackQueryHandler(choix_paiement, pattern="^payment_")
            ],
            CONFIRMATION: [
                CallbackQueryHandler(confirmation, pattern="^confirm_order$")
            ],
        },
        fallbacks=[
            CallbackQueryHandler(annuler, pattern="^cancel$"),
            CommandHandler("start", start_command)
        ],
        per_message=False,
        allow_reentry=True
    )

    application.add_handler(conv_handler)

    logger.info("🚀 Bot démarré avec succès!")
    logger.info(f"📊 États disponibles: {list(range(9))}")
    logger.info(f"🔑 Admin ID: {ADMIN_ID}")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)
