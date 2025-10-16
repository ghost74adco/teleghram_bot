import os
import sys
import logging
import re
import csv
import math
import requests
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps
from collections import defaultdict
from datetime import datetime, timedelta

# Configuration des logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Chargement des variables d'environnement
for env_file in ['.env', 'infos.env']:
    dotenv_path = Path(__file__).parent / env_file
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
        logger.info(f"✅ Variables chargées depuis: {env_file}")
        break
else:
    load_dotenv()
    logger.info("✅ Variables d'environnement chargées")

# Variables d'environnement
TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
ADMIN_ID_STR = (os.getenv("ADMIN_ID") or os.getenv("ADMIN_USER_IDS") or os.getenv("TELEGRAM_ADMIN_ID") or "").strip()
ADMIN_ADDRESS = (os.getenv("ADMIN_ADDRESS") or "858 Rte du Chef Lieu, 74250 Fillinges").strip()
API_BASE_URL = os.getenv("API_BASE_URL", "https://carte-du-pirate.onrender.com")

# Vérification du TOKEN
if not TOKEN or ':' not in TOKEN:
    logger.error("❌ TOKEN Telegram invalide ou manquant!")
    logger.error("   Ajoutez TELEGRAM_BOT_TOKEN dans votre fichier .env")
    sys.exit(1)

# Vérification de l'ADMIN_ID
if not ADMIN_ID_STR or not ADMIN_ID_STR.isdigit():
    logger.error(f"❌ ADMIN_ID invalide: {ADMIN_ID_STR}")
    logger.error("   Ajoutez ADMIN_ID dans votre fichier .env")
    sys.exit(1)

ADMIN_ID = int(ADMIN_ID_STR)
logger.info(f"✅ Configuration OK - Admin ID: {ADMIN_ID}")

# Import des modules Telegram
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, 
        ContextTypes, 
        CallbackQueryHandler, 
        ConversationHandler, 
        MessageHandler, 
        CommandHandler, 
        filters
    )
    logger.info("✅ Modules Telegram importés")
except ImportError as e:
    logger.error("❌ Erreur d'importation: installez python-telegram-bot")
    logger.error("   pip install python-telegram-bot --upgrade")
    sys.exit(1)

# Configuration
USE_WHITELIST = False
AUTHORIZED_USERS = []
user_message_timestamps = defaultdict(list)
MAX_MESSAGES_PER_MINUTE = 30
RATE_LIMIT_WINDOW = 60
MAX_QUANTITY_PER_PRODUCT = 100
FRAIS_POSTAL = 10

# États de la conversation
LANGUE, PAYS, PRODUIT, PILL_SUBCATEGORY, ROCK_SUBCATEGORY, QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(11)

# Catégories de produits
PILL_SUBCATEGORIES = {
    "squid_game": "💊 Squid Game",
    "punisher": "💊 Punisher"
}

ROCK_SUBCATEGORIES = {
    "mdma": "🪨 MDMA",
    "fourmmc": "🪨 4MMC"
}

# Prix par pays
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
        "choose_delivery": "📦 *Choisissez le type de livraison :*\n\n✉️ *Postale* : 48h-72h, 10€ de frais\n⚡ *Express* : Livraison en 30min minimum par coursier",
        "calculating_distance": "📏 Calcul en cours...",
        "distance_calculated": "📏 *Distance :* {distance} km\n💶 *Frais de livraison :* {fee}€",
        "geocoding_error": "❌ Adresse introuvable. Veuillez réessayer.",
        "choose_payment": "💳 *Choisissez le mode de paiement :*",
        "order_summary": "✅ *RÉSUMÉ DE VOTRE COMMANDE :*",
        "confirm": "✅ Confirmer",
        "cancel": "❌ Annuler",
        "order_confirmed": "✅ *Commande confirmée !*\n\nVotre commande a été envoyée à notre équipe.\n\n📞 Vous serez contacté très prochainement.",
        "order_cancelled": "❌ *Commande annulée.*",
        "add_more": "➕ Ajouter un produit",
        "proceed": "✅ Valider le panier",
        "invalid_quantity": "❌ Quantité invalide. Entrez un nombre entre 1 et {max}.",
        "cart_title": "🛒 *VOTRE PANIER :*",
        "start_order": "🛒 Commander",
        "price_menu": "🏴‍☠️ Voir la Carte",
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Suisse",
        "postal": "✉️ Postale (48-72h)",
        "express": "⚡ Express (30min min)",
        "cash": "💵 Espèces",
        "crypto": "₿ Crypto",
        "total": "💰 *TOTAL :*",
        "delivery_fee": "📦 *Frais de livraison :*",
        "subtotal": "💵 *Sous-total produits :*",
        "back": "🔙 Retour"
    }
}

# Fonctions utilitaires
def tr(user_data, key):
    """Fonction de traduction"""
    lang = user_data.get("langue", "fr")
    t = TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)
    return t.replace("{max}", str(MAX_QUANTITY_PER_PRODUCT)) if "{max}" in t else t

def sanitize_input(text, max_length=200):
    """Nettoie les entrées utilisateur"""
    if not text:
        return ""
    return re.sub(r'[<>{}[\]\\`|]', '', text.strip()[:max_length])

def is_authorized(user_id):
    """Vérifie si l'utilisateur est autorisé"""
    return not USE_WHITELIST or user_id in AUTHORIZED_USERS

def check_rate_limit(user_id):
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

def update_last_activity(user_data):
    """Met à jour la dernière activité"""
    user_data['last_activity'] = datetime.now()

def calculate_delivery_fee(delivery_type, distance=0, subtotal=0):
    """Calcule les frais de livraison"""
    if delivery_type == "postal":
        return FRAIS_POSTAL
    elif delivery_type == "express":
        # Formule : (distance * 2 + subtotal * 3%) arrondi à la dizaine supérieure
        return math.ceil(((distance * 2) + (subtotal * 0.03)) / 10) * 10
    return 0

async def get_distance_from_api(address):
    """Récupère la distance via l'API"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/calculate-distance",
            json={"address": address},
            timeout=15
        )
        if response.status_code == 200:
            data = response.json()
            return (data.get('distance_km', 0), True, None)
        else:
            return (0, False, "Erreur API")
    except Exception as e:
        logger.error(f"Erreur calcul distance: {e}")
        return (0, False, str(e))

def calculate_total(cart, country, delivery_type=None, distance=0):
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
    text = "\n" + tr(user_data, 'cart_title') + "\n"
    for item in cart:
        text += f"• {item['produit']} x {item['quantite']}\n"
    return text

def save_order_to_csv(order_data):
    """Sauvegarde la commande dans un CSV"""
    csv_path = Path(__file__).parent / "orders.csv"
    try:
        file_exists = csv_path.exists()
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            fieldnames = [
                'date', 'order_id', 'user_id', 'username', 'first_name',
                'products', 'country', 'address', 'delivery_type', 'distance_km',
                'payment_method', 'subtotal', 'delivery_fee', 'total', 'status'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(order_data)
        logger.info(f"✅ Commande sauvegardée: {order_data['order_id']}")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde CSV: {e}")
        return False

def error_handler(func):
    """Décorateur pour gérer les erreurs"""
    @wraps(func)
    async def wrapper(update, context):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"Erreur dans {func.__name__}: {e}", exc_info=True)
            try:
                if update.callback_query:
                    await update.callback_query.answer("❌ Une erreur est survenue")
                elif update.message:
                    await update.message.reply_text("❌ Erreur. Tapez /start pour recommencer.")
            except:
                pass
            return ConversationHandler.END
    return wrapper

# Handlers de conversation
@error_handler
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation de la commande"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_order":
        user = update.effective_user
        total, subtotal, delivery_fee = calculate_total(
            context.user_data['cart'],
            context.user_data['pays'],
            context.user_data['livraison'],
            context.user_data.get('distance', 0)
        )
        
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user.id}"
        
        # Données de la commande
        order_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'order_id': order_id,
            'user_id': user.id,
            'username': user.username or "N/A",
            'first_name': user.first_name or "N/A",
            'products': "; ".join([
                f"{item['produit']} x{item['quantite']}" 
                for item in context.user_data['cart']
            ]),
            'country': context.user_data['pays'],
            'address': context.user_data['adresse'],
            'delivery_type': context.user_data['livraison'],
            'distance_km': context.user_data.get('distance', 0) if context.user_data['livraison'] == "express" else 0,
            'payment_method': context.user_data['paiement'],
            'subtotal': str(round(subtotal, 2)),
            'delivery_fee': str(round(delivery_fee, 2)),
            'total': str(round(total, 2)),
            'status': 'En attente'
        }
        
        # Sauvegarde dans le CSV
        save_order_to_csv(order_data)
        
        # Formatage du message pour l'admin
        user_name = user.first_name or "N/A"
        user_tag = f" (@{user.username})" if user.username else ""
        cart_fmt = format_cart(context.user_data['cart'], context.user_data)
        
        admin_message = (
            f"🆕 *NOUVELLE COMMANDE*\n\n"
            f"📋 `{order_id}`\n"
            f"👤 {user_name}{user_tag}\n"
            f"🆔 ID: `{user.id}`\n\n"
            f"{cart_fmt}\n"
            f"💵 Sous-total: {subtotal}€\n"
            f"📦 Livraison ({context.user_data['livraison']}): {delivery_fee}€\n"
            f"💰 *TOTAL: {total}€*\n\n"
            f"📍 Adresse:\n{context.user_data['adresse']}\n\n"
            f"💳 Paiement: {context.user_data['paiement'].title()}\n"
            f"🌍 Pays: {'France' if context.user_data['pays'] == 'FR' else 'Suisse'}"
        )
        
        admin_keyboard = [[
            InlineKeyboardButton(
                "✅ Valider la commande",
                callback_data=f"admin_validate_{order_id}_{user.id}"
            )
        ]]
        
        # Envoi à l'admin
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message,
                reply_markup=InlineKeyboardMarkup(admin_keyboard),
                parse_mode='Markdown'
            )
            logger.info(f"✅ Commande envoyée à l'admin: {order_id}")
        except Exception as e:
            logger.error(f"❌ Erreur envoi à l'admin: {e}")
        
        # Confirmation au client
        conf_msg = (
            f"{tr(context.user_data, 'order_confirmed')}\n\n"
            f"📋 Numéro de commande:\n`{order_id}`\n\n"
            f"💰 Montant total: {round(total, 2)}€"
        )
        
        await query.message.edit_text(conf_msg, parse_mode='Markdown')
        context.user_data.clear()
        return ConversationHandler.END
    
    elif query.data == "cancel":
        return await cancel(update, context)

@error_handler
async def admin_validation_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validation de la livraison par l'admin"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Non autorisé", show_alert=True)
        return
    
    # Extraction de l'order_id et du client_id
    data_parts = query.data.split("_")
    order_id = "_".join(data_parts[2:-1])
    client_id = int(data_parts[-1])
    
    try:
        # Mise à jour du message admin
        old_text = query.message.text
        await query.message.edit_text(
            f"{old_text}\n\n✅ *COMMANDE VALIDÉE*\n⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            parse_mode='Markdown'
        )
        
        # Notification au client
        await context.bot.send_message(
            chat_id=client_id,
            text=(
                f"✅ *Commande validée !*\n\n"
                f"📋 `{order_id}`\n\n"
                f"Votre commande a été confirmée.\n"
                f"Vous serez contacté sous peu pour la livraison.\n\n"
                f"Merci de votre confiance ! 💚"
            ),
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ Commande validée par admin: {order_id}")
    except Exception as e:
        logger.error(f"❌ Erreur validation: {e}")
    
    await query.answer("✅ Commande validée avec succès!", show_alert=True)

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

async def error_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback d'erreur globale"""
    logger.error(f"Exception: {context.error}", exc_info=context.error)

def main():
    """Fonction principale"""
    logger.info("=" * 60)
    logger.info("🤖 DÉMARRAGE DU BOT TELEGRAM")
    logger.info("=" * 60)
    logger.info(f"📱 Token: {TOKEN[:15]}...")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    logger.info(f"📍 Adresse admin: {ADMIN_ADDRESS}")
    
    try:
        # Création de l'application
        application = Application.builder().token(TOKEN).build()
        logger.info("✅ Application créée")
        
        # Configuration du ConversationHandler
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
                    CallbackQueryHandler(choix_produit, pattern='^product_')
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
            fallbacks=[CommandHandler('start', start_command)],
            allow_reentry=True
        )
        
        # Ajout des handlers
        application.add_handler(conv_handler)
        application.add_handler(
            CallbackQueryHandler(admin_validation_livraison, pattern='^admin_validate_')
        )
        application.add_error_handler(error_callback)
        
        logger.info("✅ Handlers configurés")
        logger.info("=" * 60)
        logger.info("🚀 BOT EN LIGNE - En attente de messages...")
        logger.info("=" * 60)
        
        # Démarrage du bot
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    user = update.effective_user
    logger.info(f"👤 /start de {user.first_name} ({user.id})")
    
    context.user_data.clear()
    update_last_activity(context.user_data)
    
    if not is_authorized(user.id):
        await update.message.reply_text("❌ Vous n'êtes pas autorisé à utiliser ce bot.")
        return ConversationHandler.END
    
    if not check_rate_limit(user.id):
        await update.message.reply_text("⚠️ Trop de messages. Attendez un moment.")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
    ]
    
    await update.message.reply_text(
        "🌍 *Choisissez votre langue / Select your language*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return LANGUE

@error_handler
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit la langue"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['langue'] = query.data.replace("lang_", "")
    update_last_activity(context.user_data)
    
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "price_menu"), callback_data="price_menu")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PAYS

@error_handler
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Navigation dans le menu"""
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
        text = (
            "🏴‍☠️ *CARTE DES PRIX*\n\n"
            "🇫🇷 *France:*\n"
            "❄️ Coco: 80€/g\n"
            "💊 Pills: 10€/pièce\n"
            "🫒 Hash: 7€/g\n"
            "🍀 Weed: 10€/g\n"
            "🪨 MDMA/4MMC: 50€/g\n\n"
            "🇨🇭 *Suisse:*\n"
            "❄️ Coco: 100€/g\n"
            "💊 Pills: 15€/pièce\n"
            "🫒 Hash: 8€/g\n"
            "🍀 Weed: 12€/g\n"
            "🪨 MDMA/4MMC: 70€/g"
        )
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")]
        ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PAYS

@error_handler
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix du pays"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    context.user_data['pays'] = query.data.replace("country_", "")
    context.user_data['cart'] = []
    
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
    
    await query.message.edit_text(
        f"✅ Produit sélectionné : {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}",
        parse_mode='Markdown'
    )
    return QUANTITE

@error_handler
async def choix_pill_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix de la sous-catégorie de pilules"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    context.user_data['current_product'] = PILL_SUBCATEGORIES.get(
        query.data.replace("pill_", ""), "💊"
    )
    
    await query.message.edit_text(
        f"✅ Produit sélectionné : {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}",
        parse_mode='Markdown'
    )
    return QUANTITE

@error_handler
async def choix_rock_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choix de la sous-catégorie de crystal"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    context.user_data['current_product'] = ROCK_SUBCATEGORIES.get(
        query.data.replace("rock_", ""), "🪨"
    )
    
    await query.message.edit_text(
        f"✅ Produit sélectionné : {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}",
        parse_mode='Markdown'
    )
    return QUANTITE

@error_handler
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saisie de la quantité"""
    qty = sanitize_input(update.message.text, 10)
    update_last_activity(context.user_data)
    
    if not qty.isdigit() or not (0 < int(qty) <= MAX_QUANTITY_PER_PRODUCT):
        await update.message.reply_text(tr(context.user_data, "invalid_quantity"))
        return QUANTITE
    
    context.user_data['cart'].append({
        "produit": context.user_data['current_product'],
        "quantite": int(qty)
    })
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "add_more"), callback_data="add_more")],
        [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")]
    ]
    
    await update.message.reply_text(
        format_cart(context.user_data['cart'], context.user_data),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return CART_MENU

@error_handler
async def cart_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu du panier"""
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
        await query.message.edit_text(
            tr(context.user_data, 'enter_address'),
            parse_mode='Markdown'
        )
        return ADRESSE

@error_handler
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saisie de l'adresse"""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(
            tr(context.user_data, 'enter_address'),
            parse_mode='Markdown'
        )
        return ADRESSE
    
    address = sanitize_input(update.message.text, 300)
    update_last_activity(context.user_data)
    
    if len(address) < 15:
        await update.message.reply_text("❌ Adresse trop courte (minimum 15 caractères)")
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
    """Choix du mode de livraison"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    delivery_type = query.data.replace("delivery_", "")
    context.user_data['livraison'] = delivery_type
    
    if delivery_type == "express":
        await query.message.edit_text(
            tr(context.user_data, "calculating_distance"),
            parse_mode='Markdown'
        )
        
        distance_km, success, error_msg = await get_distance_from_api(
            context.user_data.get('adresse', '')
        )
        
        if not success:
            keyboard = [[InlineKeyboardButton(
                tr(context.user_data, "back"),
                callback_data="back_to_address"
            )]]
            await query.message.edit_text(
                tr(context.user_data, "geocoding_error"),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return LIVRAISON
        
        context.user_data['distance'] = distance_km
        subtotal, _, _ = calculate_total(context.user_data['cart'], context.user_data['pays'])
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
            f"{distance_text}\n\n{tr(context.user_data, 'choose_payment')}",
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
    """Choix du mode de paiement"""
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    context.user_data['paiement'] = query.data.replace("payment_", "")
    
    total, subtotal, delivery_fee = calculate_total(
        context.user_data['cart'],
        context.user_data['pays'],
        context.user_data['livraison'],
        context.user_data.get('distance', 0)
    )
    
    cart_text = format_cart(context.user_data['cart'], context.user_data)
    
    summary = (
        f"{tr(context.user_data, 'order_summary')}\n\n"
        f"{cart_text}\n"
        f"{tr(context.user_data, 'subtotal')} {subtotal}€\n"
        f"{tr(context.user_data, 'delivery_fee')} {delivery_fee}€\n"
        f"{tr(context.user_data, 'total')} *{total}€*\n\n"
        f"📍 {context.user_data['adresse']}\n"
        f"📦 {context.user_data['livraison'].title()}\n"
        f"💳 {context.user_data['paiement'].title()}"
    )
    
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

@error_
