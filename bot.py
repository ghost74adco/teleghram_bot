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
PAYS, PRODUIT, QUANTITE, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(7)

# --- Prix ---
PRIX_FR = {"❄️": 80, "💊": 10, "🫒": 7, "🍀": 10}
PRIX_CH = {"❄️": 100, "💊": 15, "🫒": 8, "🍀": 12}

# --- Gestionnaire d'erreurs ---
async def notify_admin_error(context: ContextTypes.DEFAULT_TYPE, error_msg: str):
    """Envoie une notification d'erreur à l'admin"""
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 ERREUR BOT\n\n{error_msg}"
        )
    except Exception as e:
        logger.error(f"Impossible d'envoyer la notification: {e}")

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
            
            if update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Une erreur s'est produite. L'administrateur a été notifié."
                )
    return wrapper

async def error_callback(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire global d'erreurs"""
    logger.error("Exception lors du traitement:", exc_info=context.error)
    
    error_type = type(context.error).__name__
    error_msg = str(context.error)
    
    if isinstance(context.error, NetworkError):
        logger.warning("Erreur réseau - retry automatique...")
        return
    
    elif isinstance(context.error, TimedOut):
        logger.warning("Timeout - l'opération prendra plus de temps")
        return
    
    admin_msg = f"🚨 ERREUR BOT\n\nType: {error_type}\nMessage: {error_msg}"
    
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
    except Exception as e:
        logger.error(f"Impossible de notifier l'admin: {e}")

# --- Commande /start ---
@error_handler_decorator
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Démarrer la commande", callback_data="start_order")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Bienvenue ! Cliquez sur le bouton pour démarrer votre commande :",
        reply_markup=reply_markup
    )

# --- Message de bienvenue automatique ---
@error_handler_decorator
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche un bouton Démarrer dès que l'utilisateur rejoint le bot"""
    keyboard = [
        [InlineKeyboardButton("🚀 Démarrer", callback_data="start_macro")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Bienvenue 👋\nAppuyez sur le bouton ci-dessous pour commencer.",
        reply_markup=reply_markup
    )

# --- Choix du pays ---
@error_handler_decorator
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data="FR")],
        [InlineKeyboardButton("🇨🇭 Suisse", callback_data="CH")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Choisissez votre pays :", reply_markup=reply_markup)
    return PAYS

# --- Sélection du pays ---
@error_handler_decorator
async def set_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Annuler":
        await query.message.reply_text("Commande annulée.")
        return ConversationHandler.END

    context.user_data['pays'] = query.data

    keyboard = [
        [InlineKeyboardButton("❄️", callback_data="❄️")],
        [InlineKeyboardButton("💊", callback_data="💊")],
        [InlineKeyboardButton("🫒", callback_data="🫒")],
        [InlineKeyboardButton("🍀", callback_data="🍀")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Sélectionnez un produit :", reply_markup=reply_markup)
    return PRODUIT

# --- Choix produit ---
@error_handler_decorator
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Annuler":
        await query.message.reply_text("Commande annulée.")
        return ConversationHandler.END

    produit = query.data
    context.user_data.setdefault('produits', []).append({'produit': produit, 'quantite': 0})
    await query.message.reply_text(f"Produit choisi : {produit}\nIndiquez la quantité en grammes :")
    return QUANTITE

# --- Saisie quantité ---
@error_handler_decorator
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = update.message.text

    if not texte.isdigit():
        await update.message.reply_text("Veuillez entrer un nombre en grammes.")
        return QUANTITE

    quantite = int(texte)
    context.user_data['produits'][-1]['quantite'] = quantite

    if 'adresse' in context.user_data:
        await update.message.reply_text(f"Adresse conservée : {context.user_data['adresse']}")
        keyboard = [
            [InlineKeyboardButton("Standard", callback_data="Standard")],
            [InlineKeyboardButton("Express", callback_data="Express")],
            [InlineKeyboardButton("Annuler", callback_data="Annuler")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choisissez le mode de livraison :", reply_markup=reply_markup)
        return LIVRAISON
    else:
        await update.message.reply_text("Veuillez saisir votre adresse :")
        return ADRESSE

# --- Saisie adresse ---
@error_handler_decorator
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = update.message.text.strip()

    if len(texte) < 5:
        await update.message.reply_text("Veuillez saisir une adresse valide.")
        return ADRESSE

    context.user_data['adresse'] = texte

    keyboard = [
        [InlineKeyboardButton("Standard", callback_data="Standard")],
        [InlineKeyboardButton("Express", callback_data="Express")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choisissez le mode de livraison :", reply_markup=reply_markup)
    return LIVRAISON

# --- Choix livraison ---
@error_handler_decorator
async def choix_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Annuler":
        await query.message.reply_text("Commande annulée.")
        return ConversationHandler.END

    context.user_data['livraison'] = query.data

    keyboard = [
        [InlineKeyboardButton("Crypto", callback_data="Crypto")],
        [InlineKeyboardButton("Espèces", callback_data="Especes")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Choisissez le mode de paiement :", reply_markup=reply_markup)
    return PAIEMENT

# --- Choix paiement ---
@error_handler_decorator
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Annuler":
        await query.message.reply_text("Commande annulée.")
        return ConversationHandler.END

    context.user_data['paiement'] = query.data

    total = 0
    prix_dict = PRIX_FR if context.user_data['pays'] == "FR" else PRIX_CH

    for item in context.user_data['produits']:
        total += item['quantite'] * prix_dict[item['produit']]

    context.user_data['montant'] = total

    resume = f"Résumé de votre commande :\nPays : {context.user_data['pays']}\nAdresse : {context.user_data['adresse']}\nLivraison : {context.user_data['livraison']}\nPaiement : {context.user_data['paiement']}\nProduits :\n"

    for item in context.user_data['produits']:
        resume += f"• {item['produit']} — {item['quantite']}g — {item['quantite']*prix_dict[item['produit']]} {('€' if context.user_data['pays']=='FR' else 'CHF')}\n"

    resume += f"Total : {total} {('€' if context.user_data['pays']=='FR' else 'CHF')}"

    keyboard = [
        [InlineKeyboardButton("Ajouter un produit", callback_data="add_product")],
        [InlineKeyboardButton("Confirmer la commande", callback_data="confirm")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(resume, reply_markup=reply_markup)
    return CONFIRMATION

# --- Confirmation ---
@error_handler_decorator
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Annuler":
        await query.message.reply_text("Commande annulée.")
        return ConversationHandler.END

    if query.data == "add_product":
        keyboard = [
            [InlineKeyboardButton("❄️", callback_data="❄️")],
            [InlineKeyboardButton("💊", callback_data="💊")],
            [InlineKeyboardButton("🫒", callback_data="🫒")],
            [InlineKeyboardButton("🍀", callback_data="🍀")],
            [InlineKeyboardButton("Annuler", callback_data="Annuler")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Sélectionnez un produit supplémentaire :", reply_markup=reply_markup)
        return PRODUIT

    if query.data == "confirm":
        total = context.user_data['montant']
        produits = context.user_data['produits']
        adresse = context.user_data['adresse']
        pays = context.user_data['pays']
        livraison = context.user_data['livraison']
        paiement = context.user_data['paiement']
        prix_dict = PRIX_FR if pays == "FR" else PRIX_CH

        resume = f"Résumé de votre commande :\nPays : {pays}\nAdresse : {adresse}\nLivraison : {livraison}\nPaiement : {paiement}\nProduits :\n"

        for item in produits:
            resume += f"• {item['produit']} — {item['quantite']}g — {item['quantite']*prix_dict[item['produit']]} {('€' if pays=='FR' else 'CHF')}\n"

        resume += f"Total : {total} {('€' if pays=='FR' else 'CHF')}"

        if paiement == "Crypto":
            await query.message.reply_text(resume + f"\nVeuillez payer sur ce portefeuille BTC : {CRYPTO_WALLET}")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"Nouvelle commande crypto :\n{resume}")
        else:
            await query.message.reply_text(resume + "\nVous paierez à la livraison")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"Nouvelle commande espèces :\n{resume}")

        await query.message.reply_text("✅ Commande confirmée, merci !")
        return ConversationHandler.END

# --- Annuler ---
@error_handler_decorator
async def annuler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Commande annulée.")
    return ConversationHandler.END

# --- Main ---
if __name__ == "__main__":
    logger.info("🚀 Démarrage du bot...")
    
    application = Application.builder().token(TOKEN).build()
    
    # Gestionnaire d'erreurs global
    application.add_error_handler(error_callback)

    # Handler /start — doit toujours être déclaré avant tout le reste
    application.add_handler(CommandHandler("start", start_command))

    # ConversationHandler
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
