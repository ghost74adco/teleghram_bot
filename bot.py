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

# --- Variables d'environnement ---
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

# --- Gestionnaire d'erreurs ---
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

# --- Fonctions de conversation ---
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
        await update.message.reply_text("🌍 Choisissez votre langue / Select your language:", reply_markup=reply_markup)
    return LANGUE

@error_handler_decorator
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['langue'] = query.data
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data="FR")],
        [InlineKeyboardButton("🇨🇭 Suisse", callback_data="CH")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    await query.message.edit_text("Choisissez votre pays :", reply_markup=InlineKeyboardMarkup(keyboard))
    return PAYS

# --- Définition de toutes les fonctions manquantes ---
@error_handler_decorator
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['pays'] = query.data
    keyboard = [[InlineKeyboardButton(p, callback_data=p)] for p in ["❄️", "💊", "🫒", "🍀"]]
    await query.message.edit_text("Choisissez votre produit :", reply_markup=InlineKeyboardMarkup(keyboard))
    return PRODUIT

@error_handler_decorator
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['produit'] = query.data
    await query.message.edit_text("Entrez la quantité désirée :")
    return QUANTITE

@error_handler_decorator
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['quantite'] = update.message.text
    await update.message.reply_text("Entrez votre adresse :")
    return ADRESSE

@error_handler_decorator
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['adresse'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Standard", callback_data="standard")],
        [InlineKeyboardButton("Express", callback_data="express")]
    ]
    await update.message.reply_text("Choisissez le type de livraison :", reply_markup=InlineKeyboardMarkup(keyboard))
    return LIVRAISON

@error_handler_decorator
async def choix_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['livraison'] = query.data
    keyboard = [
        [InlineKeyboardButton("Crypto", callback_data="crypto")],
        [InlineKeyboardButton("Carte bancaire", callback_data="card")]
    ]
    await query.message.edit_text("Choisissez le mode de paiement :", reply_markup=InlineKeyboardMarkup(keyboard))
    return PAIEMENT

@error_handler_decorator
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['paiement'] = query.data
    summary = f"✅ Résumé de votre commande :\nProduit: {context.user_data['produit']}\nQuantité: {context.user_data['quantite']}\nAdresse: {context.user_data['adresse']}\nLivraison: {context.user_data['livraison']}\nPaiement: {context.user_data['paiement']}"
    keyboard = [[InlineKeyboardButton("Confirmer", callback_data="confirm")], [InlineKeyboardButton("Annuler", callback_data="Annuler")]]
    await query.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRMATION

@error_handler_decorator
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm":
        await query.message.edit_text("✅ Commande confirmée ! Merci.")
    else:
        await query.message.edit_text("❌ Commande annulée.")
    return ConversationHandler.END

@error_handler_decorator
async def annuler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("❌ Commande annulée.")
    return ConversationHandler.END

# --- Main ---
if __name__ == "__main__":
    application = Application.builder().token(TOKEN).build()
    application.add_error_handler(error_callback)

    # /start
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(set_langue, pattern="^(fr|en|es|de)$"))

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

    # Démarrage du bot
    logger.info("🚀 Bot en ligne !")
    application.run_polling()
