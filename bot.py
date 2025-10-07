import os
import sys
import logging
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps

# --- Configuration du logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot_errors.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Validation des variables d'environnement ---
def validate_environment():
    """Valide les variables d'environnement au démarrage"""
    required_vars = {
        'TELEGRAM_TOKEN': 'Token du bot Telegram',
        'ADMIN_ID': 'ID de l\'administrateur',
        'CRYPTO_WALLET': 'Adresse du wallet crypto'
    }
    
    missing = []
    invalid = []
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value:
            missing.append(f"{var} ({description})")
        else:
            value = value.strip()
            if var == 'TELEGRAM_TOKEN':
                if ':' not in value or len(value) < 40:
                    invalid.append(f"{var}: format invalide (doit être NUMBER:HASH)")
            elif var == 'ADMIN_ID':
                if not value.isdigit():
                    invalid.append(f"{var}: doit être un nombre")
            elif var == 'CRYPTO_WALLET':
                if len(value) < 20:
                    invalid.append(f"{var}: format invalide")
    
    if missing or invalid:
        error_msg = "❌ ERREURS DE CONFIGURATION:\n"
        if missing:
            error_msg += "\nVariables manquantes:\n" + "\n".join(f"  - {v}" for v in missing)
        if invalid:
            error_msg += "\n\nVariables invalides:\n" + "\n".join(f"  - {v}" for v in invalid)
        
        logger.error(error_msg)
        print(error_msg)
        sys.exit(1)
    
    logger.info("✅ Toutes les variables d'environnement sont valides")
    return True

# --- Chargement des variables ---
dotenv_path = Path(__file__).parent / "infos.env"
load_dotenv(dotenv_path)
validate_environment()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CRYPTO_WALLET = os.getenv("CRYPTO_WALLET")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# --- Imports Telegram ---
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    filters,
)
from telegram.error import TelegramError, NetworkError, TimedOut

# --- États de la conversation ---
LANGUE, PAYS, PRODUIT, QUANTITE, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(8)

# --- Prix ---
PRIX_FR = {"❄️": 80, "💊": 10, "🫒": 7, "🍀": 10}
PRIX_CH = {"❄️": 100, "💊": 15, "🫒": 8, "🍀": 12}

# --- Gestionnaire d'erreurs ---
async def notify_admin_error(context: ContextTypes.DEFAULT_TYPE, error_msg: str):
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 ERREUR BOT\n\n{error_msg}")
    except Exception as e:
        logger.error(f"Impossible d'envoyer la notification: {e}")

def error_handler_decorator(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            user_id = update.effective_user.id if update.effective_user else "Unknown"
            error_msg = f"Erreur dans {func.__name__}\nUser: {user_id}\nErreur: {str(e)}"
            logger.error(error_msg, exc_info=True)
            await notify_admin_error(context, error_msg)
            if update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Une erreur s'est produite. L'administrateur a été notifié."
                )
    return wrapper

async def error_callback(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception lors du traitement:", exc_info=context.error)
    error_type = type(context.error).__name__
    error_msg = str(context.error)
    
    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning("Erreur réseau ou timeout")
        return
    
    admin_msg = f"🚨 ERREUR BOT\n\nType: {error_type}\nMessage: {error_msg}"
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
    except Exception as e:
        logger.error(f"Impossible de notifier l'admin: {e}")

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
        await update.message.reply_text(
            "🌍 Choisissez votre langue / Select your language:",
            reply_markup=reply_markup
        )
    return LANGUE

# --- Callback après sélection de la langue ---
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
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("Choisissez votre pays :", reply_markup=reply_markup)
    return PAYS

# --- Les autres handlers restent identiques ---
# choix_pays, set_pays, choix_produit, saisie_quantite, saisie_adresse, 
# choix_livraison, choix_paiement, confirmation, annuler
# (ils doivent être copiés depuis ton code actuel sans modification des commentaires)

# --- Main ---
if __name__ == "__main__":
    logger.info("🚀 Démarrage du bot...")
    
    application = Application.builder().token(TOKEN).build()
    
    # Gestionnaire d'erreurs global
    application.add_error_handler(error_callback)

    # Handler /start
    application.add_handler(CommandHandler("start", start_command))
    
    # Callback pour la sélection de la langue
    application.add_handler(CallbackQueryHandler(set_langue, pattern="^(fr|en|es|de)$"))

    # ConversationHandler (inchangé)
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(choix_pays, pattern="start_order")],
        states={
            PAYS: [CallbackQueryHandler(set_pays)],
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

    # Bouton Démarrer (équivaut à /start)
    application.add_handler(CallbackQueryHandler(start_command, pattern="^start_macro$"))

    try:
        logger.info("✅ Bot en ligne!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"Erreur critique au démarrage: {e}", exc_info=True)
        sys.exit(1)
