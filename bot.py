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
        "order_cancelled": "❌ Commande annulée."
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
        "order_cancelled": "❌ Order cancelled."
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
        "order_cancelled": "❌ Pedido cancelado."
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
        "order_cancelled": "❌ Bestellung abgebrochen."
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
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="en")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="es")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="de")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(tr({}, "choose_language"), reply_markup=reply_markup)
    return LANGUE

@error_handler_decorator
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['langue'] = query.data
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data="FR")],
        [InlineKeyboardButton("🇨🇭 Suisse", callback_data="CH")],
        [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="Annuler")]
    ]
    await query.message.edit_text(tr(context.user_data, "choose_country"), reply_markup=InlineKeyboardMarkup(keyboard))
    return PAYS

# --- Gestion du panier multi-produits ---
@error_handler_decorator
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['pays'] = query.data
    context.user_data['cart'] = []  # panier vide
    keyboard = [[InlineKeyboardButton(p, callback_data=p)] for p in ["❄️", "💊", "🫒", "🍀"]]
    await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard))
    return PRODUIT

@error_handler_decorator
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['current_product'] = query.data
    await query.message.edit_text(tr(context.user_data, "enter_quantity"))
    return QUANTITE

@error_handler_decorator
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qty = update.message.text
    if not qty.isdigit() or int(qty) <= 0:
        await update.message.reply_text(tr(context.user_data, "enter_quantity"))
        return QUANTITE
    context.user_data['cart'].append({"produit": context.user_data['current_product'], "quantite": qty})
    keyboard = [
        [InlineKeyboardButton("Ajouter un autre produit", callback_data="add_more")],
        [InlineKeyboardButton(tr(context.user_data, "confirm"), callback_data="proceed_checkout")]
    ]
    await update.message.reply_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard))
    return PRODUIT

@error_handler_decorator
async def add_more_or_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "add_more":
        keyboard = [[InlineKeyboardButton(p, callback_data=p)] for p in ["❄️", "💊", "🫒", "🍀"]]
        await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard))
        return PRODUIT
    else:
        await query.message.edit_text(tr(context.user_data, "enter_address"))
        return ADRESSE

@error_handler_decorator
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['adresse'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Standard", callback_data="standard")],
        [InlineKeyboardButton("Express", callback_data="express")]
    ]
    await update.message.reply_text(tr(context.user_data, "choose_delivery"), reply_markup=InlineKeyboardMarkup(keyboard))
    return LIVRAISON

@error_handler_decorator
async def choix_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['livraison'] = query.data
    keyboard = [
        [InlineKeyboardButton("Espèces", callback_data="cash")],
        [InlineKeyboardButton("Crypto", callback_data="crypto")]
    ]
    await query.message.edit_text(tr(context.user_data, "choose_payment"), reply_markup=InlineKeyboardMarkup(keyboard))
    return PAIEMENT

@error_handler_decorator
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['paiement'] = query.data
    total = calculate_total(context.user_data['cart'], context.user_data['pays'])
    summary = f"{tr(context.user_data, 'order_summary')}\n"
    for item in context.user_data['cart']:
        summary += f"{item['produit']} x {item['quantite']}\n"
    summary += f"Livraison: {context.user_data['livraison']}\n"
    summary += f"Paiement: {context.user_data['paiement']}\n"
    summary += f"Montant total: {total}€"
    keyboard = [[InlineKeyboardButton(tr(context.user_data, "confirm"), callback_data="confirm")],
                [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="Annuler")]]
    await query.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRMATION

@error_handler_decorator
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm":
        await query.message.edit_text(tr(context.user_data, "order_confirmed"))
        # Envoi au admin
        total = calculate_total(context.user_data['cart'], context.user_data['pays'])
        order_details = f"Nouvelle commande:\nClient: {query.from_user.id}\nProduits: {context.user_data['cart']}\nAdresse: {context.user_data['adresse']}\nLivraison: {context.user_data['livraison']}\nPaiement: {context.user_data['paiement']}\nTotal: {total}€"
        await context.bot.send_message(chat_id=ADMIN_ID, text=order_details)
    else:
        await query.message.edit_text(tr(context.user_data, "order_cancelled"))
    return ConversationHandler.END

@error_handler_decorator
async def annuler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(tr(context.user_data, "order_cancelled"))
    return ConversationHandler.END

@error_handler_decorator
async def back_to_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Pour ajouter un produit supplémentaire
    keyboard = [[InlineKeyboardButton(p, callback_data=p)] for p in ["❄️", "💊", "🫒", "🍀"]]
    await update.callback_query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard))
    return PRODUIT

# --- Main ---
if __name__ == "__main__":
    application = Application.builder().token(TOKEN).build()
    application.add_error_handler(error_callback)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(set_langue, pattern="^(fr|en|es|de)$"))
    application.add_handler(CallbackQueryHandler(add_more_or_checkout, pattern="^(add_more|proceed_checkout)$"))

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(choix_pays, pattern="^(FR|CH)$")],
        states={
            PAYS: [CallbackQueryHandler(choix_pays)],
            PRODUIT: [CallbackQueryHandler(choix_produit)],
            QUANTITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)],
            ADRESSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse)],
            LIVRAISON: [CallbackQueryHandler(choix_livraison)],
            PAIEMENT: [CallbackQueryHandler(choix_paiement)],
            CONFIRMATION: [CallbackQueryHandler(confirmation)],
        },
        fallbacks=[CallbackQueryHandler(annuler, pattern="Annuler")],
        per_message=False
    )

    application.add_handler(conv_handler)

    logger.info("🚀 Bot en ligne !")
    application.run_polling()
