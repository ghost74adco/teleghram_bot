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
LANGUE, PAYS, PRODUIT, QUANTITE, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(8)

# --- Prix ---
PRIX_FR = {"❄️": 80, "💊": 10, "🫒": 7, "🍀": 10}
PRIX_CH = {"❄️": 100, "💊": 15, "🫒": 8, "🍀": 12}

# --- Traductions statiques ---
TRANSLATIONS = {
    "fr": {
        "choose_language": "🌍 Choisissez votre langue :",
        "choose_country": "Choisissez votre pays :",
        "choose_product": "Choisissez votre produit :",
        "enter_quantity": "Entrez la quantité désirée :",
        "enter_address": "Entrez votre adresse :",
        "choose_delivery": "Choisissez le type de livraison :",
        "choose_payment": "Choisissez le mode de paiement :",
        "order_summary": "✅ Résumé de votre commande :",
        "confirm": "Confirmer",
        "cancel": "Annuler",
        "order_confirmed": "✅ Commande confirmée ! Merci.",
        "order_cancelled": "❌ Commande annulée.",
        "add_more": "Ajouter un autre produit",
        "proceed": "Passer à la commande",
        "invalid_quantity": "❌ Veuillez entrer un nombre valide supérieur à 0."
    },
    "en": {
        "choose_language": "🌍 Select your language:",
        "choose_country": "Choose your country:",
        "choose_product": "Choose your product:",
        "enter_quantity": "Enter desired quantity:",
        "enter_address": "Enter your address:",
        "choose_delivery": "Choose delivery type:",
        "choose_payment": "Choose payment method:",
        "order_summary": "✅ Your order summary:",
        "confirm": "Confirm",
        "cancel": "Cancel",
        "order_confirmed": "✅ Order confirmed! Thank you.",
        "order_cancelled": "❌ Order cancelled.",
        "add_more": "Add another product",
        "proceed": "Proceed to checkout",
        "invalid_quantity": "❌ Please enter a valid number greater than 0."
    },
    "es": {
        "choose_language": "🌍 Seleccione su idioma:",
        "choose_country": "Elija su país:",
        "choose_product": "Elija su producto:",
        "enter_quantity": "Ingrese la cantidad deseada:",
        "enter_address": "Ingrese su dirección:",
        "choose_delivery": "Elija el tipo de envío:",
        "choose_payment": "Elija el método de pago:",
        "order_summary": "✅ Resumen de su pedido:",
        "confirm": "Confirmar",
        "cancel": "Cancelar",
        "order_confirmed": "✅ Pedido confirmado! Gracias.",
        "order_cancelled": "❌ Pedido cancelado.",
        "add_more": "Agregar otro producto",
        "proceed": "Proceder al pago",
        "invalid_quantity": "❌ Por favor ingrese un número válido mayor a 0."
    },
    "de": {
        "choose_language": "🌍 Wählen Sie Ihre Sprache:",
        "choose_country": "Wählen Sie Ihr Land:",
        "choose_product": "Wählen Sie Ihr Produkt:",
        "enter_quantity": "Geben Sie die gewünschte Menge ein:",
        "enter_address": "Geben Sie Ihre Adresse ein:",
        "choose_delivery": "Wählen Sie die Versandart:",
        "choose_payment": "Wählen Sie die Zahlungsmethode:",
        "order_summary": "✅ Zusammenfassung Ihrer Bestellung:",
        "confirm": "Bestätigen",
        "cancel": "Abbrechen",
        "order_confirmed": "✅ Bestellung bestätigt! Danke.",
        "order_cancelled": "❌ Bestellung abgebrochen.",
        "add_more": "Weiteres Produkt hinzufügen",
        "proceed": "Zur Kasse gehen",
        "invalid_quantity": "❌ Bitte geben Sie eine gültige Zahl größer als 0 ein."
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

# --- Commande /start ---
@error_handler_decorator
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Réinitialiser les données utilisateur
    context.user_data.clear()
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(tr({}, "choose_language"), reply_markup=reply_markup)
    return LANGUE

@error_handler_decorator
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang_code = query.data.replace("lang_", "")
    context.user_data['langue'] = lang_code
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data="country_FR")],
        [InlineKeyboardButton("🇨🇭 Suisse", callback_data="country_CH")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    await query.message.edit_text(tr(context.user_data, "choose_country"), reply_markup=InlineKeyboardMarkup(keyboard))
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
        [InlineKeyboardButton(p, callback_data=f"product_{p}")] for p in ["❄️", "💊", "🫒", "🍀"]
    ]
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")])
    await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard))
    return PRODUIT

@error_handler_decorator
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product = query.data.replace("product_", "")
    context.user_data['current_product'] = product
    
    await query.message.edit_text(tr(context.user_data, "enter_quantity"))
    return QUANTITE

@error_handler_decorator
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qty = update.message.text.strip()
    
    if not qty.isdigit() or int(qty) <= 0:
        await update.message.reply_text(tr(context.user_data, "invalid_quantity"))
        return QUANTITE
    
    context.user_data['cart'].append({
        "produit": context.user_data['current_product'],
        "quantite": qty
    })
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "add_more"), callback_data="add_more")],
        [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    
    cart_summary = "🛒 " + tr(context.user_data, "order_summary") + "\n"
    for item in context.user_data['cart']:
        cart_summary += f"• {item['produit']} x {item['quantite']}\n"
    
    await update.message.reply_text(cart_summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return PRODUIT

@error_handler_decorator
async def add_more_or_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_more":
        keyboard = [
            [InlineKeyboardButton(p, callback_data=f"product_{p}")] for p in ["❄️", "💊", "🫒", "🍀"]
        ]
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")])
        await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard))
        return PRODUIT
    else:
        await query.message.edit_text(tr(context.user_data, "enter_address"))
        return ADRESSE

@error_handler_decorator
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['adresse'] = update.message.text
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
    
    for item in context.user_data['cart']:
        prix_table = PRIX_FR if context.user_data['pays'] == "FR" else PRIX_CH
        prix_unitaire = prix_table[item['produit']]
        summary += f"• {item['produit']} x {item['quantite']} = {prix_unitaire * int(item['quantite'])}€\n"
    
    summary += f"\n📍 Adresse: {context.user_data['adresse']}\n"
    summary += f"📦 Livraison: {context.user_data['livraison']}\n"
    summary += f"💳 Paiement: {context.user_data['paiement']}\n"
    summary += f"\n💰 Total: {total}€"
    
    if context.user_data['paiement'] == 'crypto':
        summary += f"\n\n₿ Wallet: {CRYPTO_WALLET}"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "confirm"), callback_data="confirm_order")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]
    ]
    await query.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRMATION

@error_handler_decorator
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_order":
        await query.message.edit_text(tr(context.user_data, "order_confirmed"))
        
        # Envoi au admin avec formatage amélioré
        total = calculate_total(context.user_data['cart'], context.user_data['pays'])
        user = query.from_user
        
        order_details = f"🔔 NOUVELLE COMMANDE\n\n"
        order_details += f"👤 Client:\n"
        order_details += f"  • ID: {user.id}\n"
        order_details += f"  • Username: @{user.username if user.username else 'N/A'}\n"
        order_details += f"  • Nom: {user.first_name} {user.last_name if user.last_name else ''}\n\n"
        
        order_details += f"🛒 Produits:\n"
        prix_table = PRIX_FR if context.user_data['pays'] == "FR" else PRIX_CH
        for item in context.user_data['cart']:
            prix_unitaire = prix_table[item['produit']]
            order_details += f"  • {item['produit']} x {item['quantite']} = {prix_unitaire * int(item['quantite'])}€\n"
        
        order_details += f"\n📍 Adresse: {context.user_data['adresse']}\n"
        order_details += f"🌍 Pays: {context.user_data['pays']}\n"
        order_details += f"📦 Livraison: {context.user_data['livraison']}\n"
        order_details += f"💳 Paiement: {context.user_data['paiement']}\n"
        order_details += f"\n💰 TOTAL: {total}€"
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=order_details)
    else:
        await query.message.edit_text(tr(context.user_data, "order_cancelled"))
    
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

    # Handler pour /start
    application.add_handler(CommandHandler("start", start_command))
    
    # Handler pour sélection de langue
    application.add_handler(CallbackQueryHandler(set_langue, pattern="^lang_(fr|en|es|de)$"))

    # ConversationHandler principal
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(choix_pays, pattern="^country_(FR|CH)$")],
        states={
            PAYS: [CallbackQueryHandler(choix_pays, pattern="^country_(FR|CH)$")],
            PRODUIT: [
                CallbackQueryHandler(choix_produit, pattern="^product_[❄️💊🫒🍀]$"),
                CallbackQueryHandler(add_more_or_checkout, pattern="^(add_more|proceed_checkout)$")
            ],
            QUANTITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)],
            ADRESSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse)],
            LIVRAISON: [CallbackQueryHandler(choix_livraison, pattern="^delivery_(standard|express)$")],
            PAIEMENT: [CallbackQueryHandler(choix_paiement, pattern="^payment_(cash|crypto)$")],
            CONFIRMATION: [CallbackQueryHandler(confirmation, pattern="^confirm_order$")],
        },
        fallbacks=[CallbackQueryHandler(annuler, pattern="^cancel$")],
        per_message=False
    )

    application.add_handler(conv_handler)

    logger.info("🚀 Bot en ligne !")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
