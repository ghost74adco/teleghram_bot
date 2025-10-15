# bot.py
import os
import sys
import logging
import re
import csv
import math
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps
from collections import defaultdict
from datetime import datetime, timedelta

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# --- Load .env (if present) ---
for env_file in ['.env', 'infos.env']:
    dotenv_path = Path(__file__).parent / env_file
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
        logger.info(f"✅ Chargement variables: {env_file}")
        break
else:
    load_dotenv()

# --- Env vars ---
TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
ADMIN_ID_STR = (os.getenv("ADMIN_ID") or "").strip()

if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN introuvable. Ajoute TELEGRAM_BOT_TOKEN dans les variables d'env.")
    sys.exit(1)

if not ADMIN_ID_STR or not ADMIN_ID_STR.isdigit():
    logger.error("❌ ADMIN_ID invalide ou introuvable. Ajoute ADMIN_ID (entier).")
    sys.exit(1)

ADMIN_ID = int(ADMIN_ID_STR)
logger.info(f"✅ Bot configuré - ADMIN_ID: {ADMIN_ID}")

# --- Imports Telegram ---
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, CommandHandler, filters

# --- Geopy (optionnel) ---
try:
    from geopy.geocoders import Nominatim
    from geopy.distance import geodesic
    GEOPY_AVAILABLE = True
    logger.info("✅ geopy disponible (géocodage activé)")
except Exception:
    GEOPY_AVAILABLE = False
    logger.info("⚠️ geopy non disponible (géocodage désactivé)")

# --- Configuration / Limits ---
USE_WHITELIST = False
AUTHORIZED_USERS = []  # si USE_WHITELIST True, ajoute des IDs ici
user_message_timestamps = defaultdict(list)
MAX_MESSAGES_PER_MINUTE = 30
RATE_LIMIT_WINDOW = 60  # seconds
MAX_QUANTITY_PER_PRODUCT = 100
FRAIS_POSTAL = 10
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS") or "858 Rte du Chef Lieu, 74250 Fillinges"

# --- States ---
LANGUE, PAYS, PRODUIT, PILL_SUBCATEGORY, ROCK_SUBCATEGORY, QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(11)

# --- Produits (légaux - exemple) ---
PRODUCT_CATALOG = {
    "tshirt": "👕 T-Shirt",
    "mug": "☕ Mug",
    "poster": "🖼️ Poster",
    "sticker": "🏷️ Sticker"
}
PRICES_FR = {"👕 T-Shirt": 25, "☕ Mug": 12, "🖼️ Poster": 15, "🏷️ Sticker": 3}
PRICES_CH = {"👕 T-Shirt": 30, "☕ Mug": 15, "🖼️ Poster": 18, "🏷️ Sticker": 4}

# --- Traductions simples ---
TRANSLATIONS = {
    "fr": {
        "welcome": "🌿 *BIENVENUE* 🌿\n\nBienvenue sur la boutique de démonstration.",
        "main_menu": "\n\n👇 Choisissez une option :",
        "choose_country": "🌍 *Choisissez votre pays de livraison :*",
        "choose_product": "🛒 *Choisissez votre produit :*",
        "enter_quantity": "🔢 *Entrez la quantité désirée :*",
        "enter_address": "📍 *Entrez votre adresse complète :*",
        "choose_delivery": "📦 *Choisissez le type de livraison :*",
        "calculating_distance": "📏 Calcul en cours...",
        "distance_calculated": "📏 *Distance :* {distance} km\n💶 *Frais :* {fee}€",
        "geocoding_error": "❌ Adresse introuvable.",
        "choose_payment": "💳 *Choisissez le mode de paiement :*",
        "order_summary": "✅ *Résumé de votre commande :*",
        "confirm": "✅ Confirmer", "cancel": "❌ Annuler",
        "order_confirmed": "✅ *Commande confirmée !*\n\nMerci !",
        "order_cancelled": "❌ *Commande annulée.*",
        "add_more": "➕ Ajouter", "proceed": "✅ Valider",
        "invalid_quantity": "❌ Nombre entre 1 et {max}.",
        "cart_title": "🛒 *Votre panier :*",
        "start_order": "🛒 Commander", "price_menu": "🏷️ Catalogue",
        "france": "🇫🇷 France", "switzerland": "🇨🇭 Suisse",
        "postal": "✉️ Postale (+10€)", "express": "⚡ Express",
        "cash": "💵 Espèces", "crypto": "₿ Crypto",
        "total": "💰 *Total :*", "delivery_fee": "📦 *Frais :*", "subtotal": "💵 *Sous-total :*", "back": "🔙 Retour"
    }
}

def tr(user_data, key):
    lang = user_data.get("langue", "fr")
    t = TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)
    return t.replace("{max}", str(MAX_QUANTITY_PER_PRODUCT)) if "{max}" in t else t

def sanitize_input(text: str, max_length: int = 200) -> str:
    if not text:
        return ""
    return re.sub(r'[<>{}[\]\\`|]', '', text.strip()[:max_length])

def is_authorized(user_id: int) -> bool:
    return not USE_WHITELIST or user_id in AUTHORIZED_USERS

def check_rate_limit(user_id: int) -> bool:
    now = datetime.now()
    user_message_timestamps[user_id] = [ts for ts in user_message_timestamps[user_id] if now - ts < timedelta(seconds=RATE_LIMIT_WINDOW)]
    if len(user_message_timestamps[user_id]) >= MAX_MESSAGES_PER_MINUTE:
        return False
    user_message_timestamps[user_id].append(now)
    return True

def update_last_activity(user_data: dict):
    user_data['last_activity'] = datetime.now()

def calculate_delivery_fee(delivery_type: str, distance: int = 0, subtotal: float = 0) -> float:
    if delivery_type == "postal":
        return FRAIS_POSTAL
    elif delivery_type == "express":
        # exemple de calcul: fonction de la distance + pourcentage du subtotal, arrondi à 1€
        return math.ceil(((distance * 0.5) + (subtotal * 0.05)))
    return 0

async def get_distance_between_addresses(address1: str, address2: str) -> tuple:
    """
    Retourne (distance_km: float, success: bool, error_msg: str|None)
    """
    if not GEOPY_AVAILABLE:
        return (0, False, "Géolocalisation non disponible")
    try:
        geolocator = Nominatim(user_agent="telegram_shop_bot_example")
        loc1 = geolocator.geocode(address1, timeout=10)
        loc2 = geolocator.geocode(address2, timeout=10)
        if not loc1 or not loc2:
            return (0, False, "Adresse introuvable")
        dist = round(geodesic((loc1.latitude, loc1.longitude), (loc2.latitude, loc2.longitude)).kilometers, 1)
        return (dist, True, None)
    except Exception as e:
        logger.error(f"Géocodage erreur: {e}")
        return (0, False, str(e))

def calculate_total(cart, country, delivery_type: str = None, distance: int = 0):
    prix_table = PRICES_FR if country == "FR" else PRICES_CH
    subtotal = sum(prix_table[item["produit"]] * item["quantite"] for item in cart)
    if delivery_type:
        delivery_fee = calculate_delivery_fee(delivery_type, distance, subtotal)
        return subtotal + delivery_fee, subtotal, delivery_fee
    return subtotal, subtotal, 0

def format_cart(cart, user_data):
    if not cart:
        return ""
    cart_title = tr(user_data, 'cart_title')
    items_text = "".join([f"• {item['produit']} x {item['quantite']}\n" for item in cart])
    return f"\n{cart_title}\n{items_text}"

def save_order_to_csv(order_data: dict):
    csv_path = Path(__file__).parent / "orders.csv"
    try:
        file_exists = csv_path.exists()
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['date', 'order_id', 'user_id', 'username', 'first_name', 'products', 'country', 'address', 'delivery_type', 'distance_km', 'payment_method', 'subtotal', 'delivery_fee', 'total', 'status'])
            if not file_exists:
                writer.writeheader()
            writer.writerow(order_data)
        return True
    except Exception as e:
        logger.error(f"CSV save error: {e}")
        return False

# --- Error handler decorator (doit être défini avant usage) ---
def error_handler(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {e}", exc_info=True)
            try:
                if update.callback_query:
                    await update.callback_query.answer("❌ Erreur")
                elif update.message:
                    await update.message.reply_text("❌ Erreur. Tapez /start")
            except:
                pass
            return ConversationHandler.END
    return wrapper

# --- Handlers ---
@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"/start from {user.first_name} ({user.id})")
    context.user_data.clear()
    update_last_activity(context.user_data)

    if not is_authorized(user.id):
        await update.message.reply_text("❌ Non autorisé")
        return ConversationHandler.END

    if not check_rate_limit(user.id):
        await update.message.reply_text("⚠️ Trop rapide. Réessaie dans un instant.")
        return

    keyboard = [[InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")], [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]]
    await update.message.reply_text("🌍 *Choisissez votre langue / Select your language*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return LANGUE

@error_handler
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['langue'] = query.data.replace("lang_", "")
    update_last_activity(context.user_data)

    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    keyboard = [[InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")], [InlineKeyboardButton(tr(context.user_data, "price_menu"), callback_data="price_menu")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)

    if 'langue' not in context.user_data:
        context.user_data['langue'] = 'fr'

    if query.data == "start_order":
        keyboard = [[InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")], [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")]]
        text = tr(context.user_data, "choose_country")
    else:
        # Price / catalogue
        price_lines = []
        prix_table = PRICES_FR
        for name, price in prix_table.items():
            price_lines.append(f"{name}: {price}€")
        text = "🏷️ *CATALOGUE*\n\n" + "\n".join(price_lines)
        keyboard = [[InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")]]

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    context.user_data['pays'] = query.data.replace("country_", "")
    context.user_data['cart'] = []

    keyboard = [[InlineKeyboardButton(PRODUCT_CATALOG[k], callback_data=f"product_{k}")] for k in PRODUCT_CATALOG.keys()]
    await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PRODUIT

@error_handler
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    product_code = query.data.replace("product_", "")
    product_name = PRODUCT_CATALOG.get(product_code, product_code)
    context.user_data['current_product'] = product_name
    quantity_text = tr(context.user_data, 'enter_quantity')
    await query.message.edit_text(f"✅ Produit : {product_name}\n\n{quantity_text}", parse_mode='Markdown')
    return QUANTITE

@error_handler
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qty = sanitize_input(update.message.text, 10)
    update_last_activity(context.user_data)

    if not qty.isdigit() or not (0 < int(qty) <= MAX_QUANTITY_PER_PRODUCT):
        await update.message.reply_text(tr(context.user_data, "invalid_quantity"))
        return QUANTITE

    context.user_data['cart'].append({"produit": context.user_data['current_product'], "quantite": int(qty)})
    keyboard = [[InlineKeyboardButton(tr(context.user_data, "add_more"), callback_data="add_more")], [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")]]
    await update.message.reply_text(format_cart(context.user_data['cart'], context.user_data), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CART_MENU

@error_handler
async def cart_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)

    if query.data == "add_more":
        keyboard = [[InlineKeyboardButton(PRODUCT_CATALOG[k], callback_data=f"product_{k}")] for k in PRODUCT_CATALOG.keys()]
        await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PRODUIT
    elif query.data == "proceed_checkout":
        await query.message.edit_text(tr(context.user_data, 'enter_address'), parse_mode='Markdown')
        return ADRESSE

@error_handler
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(tr(context.user_data, 'enter_address'), parse_mode='Markdown')
        return ADRESSE

    address = sanitize_input(update.message.text, 300)
    update_last_activity(context.user_data)

    if len(address) < 10:
        await update.message.reply_text("❌ Adresse trop courte (min 10 car.)")
        return ADRESSE

    context.user_data['adresse'] = address
    keyboard = [[InlineKeyboardButton(tr(context.user_data, "postal"), callback_data="delivery_postal")], [InlineKeyboardButton(tr(context.user_data, "express"), callback_data="delivery_express")]]
    await update.message.reply_text(tr(context.user_data, "choose_delivery"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return LIVRAISON

@error_handler
async def choix_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    delivery_type = query.data.replace("delivery_", "")
    context.user_data['livraison'] = delivery_type

    if delivery_type == "express":
        await query.message.edit_text(tr(context.user_data, "calculating_distance"), parse_mode='Markdown')
        distance_km, success, error_msg = await get_distance_between_addresses(ADMIN_ADDRESS, context.user_data.get('adresse', ''))
        if not success:
            keyboard = [[InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_address")]]
            await query.message.edit_text(tr(context.user_data, "geocoding_error"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return LIVRAISON

        context.user_data['distance'] = distance_km
        subtotal, _, _ = calculate_total(context.user_data['cart'], context.user_data['pays'])
        delivery_fee = calculate_delivery_fee("express", distance_km, subtotal)

        distance_text = tr(context.user_data, "distance_calculated").format(distance=distance_km, fee=delivery_fee)
        keyboard = [[InlineKeyboardButton(tr(context.user_data, "cash"), callback_data="payment_cash")], [InlineKeyboardButton(tr(context.user_data, "crypto"), callback_data="payment_crypto")]]
        await query.message.edit_text(distance_text + "\n\n" + tr(context.user_data, "choose_payment"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PAIEMENT
    else:
        context.user_data['distance'] = 0
        keyboard = [[InlineKeyboardButton(tr(context.user_data, "cash"), callback_data="payment_cash")], [InlineKeyboardButton(tr(context.user_data, "crypto"), callback_data="payment_crypto")]]
        await query.message.edit_text(tr(context.user_data, "choose_payment"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PAIEMENT

@error_handler
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    context.user_data['paiement'] = query.data.replace("payment_", "")

    total, subtotal, delivery_fee = calculate_total(context.user_data['cart'], context.user_data['pays'], context.user_data['livraison'], context.user_data.get('distance', 0))

    cart_text = format_cart(context.user_data['cart'], context.user_data)
    subtotal_text = tr(context.user_data, 'subtotal')
    delivery_text = tr(context.user_data, 'delivery_fee')
    total_text = tr(context.user_data, 'total')

    address = context.user_data['adresse']
    livraison = context.user_data['livraison'].title()
    paiement = context.user_data['paiement'].title()

    summary = f"{tr(context.user_data, 'order_summary')}\n\n{cart_text}\n{subtotal_text} {subtotal}€\n{delivery_text} {delivery_fee}€\n{total_text} *{total}€*\n\n📍 {address}\n📦 {livraison}\n💳 {paiement}"

    keyboard = [[InlineKeyboardButton(tr(context.user_data, "confirm"), callback_data="confirm_order")], [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]]
    await query.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CONFIRMATION

@error_handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.edit_text(tr(context.user_data, "order_cancelled"), parse_mode='Markdown')
    else:
        if update.message:
            await update.message.reply_text(tr(context.user_data, "order_cancelled"))
    context.user_data.clear()
    return ConversationHandler.END

@error_handler
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_order":
        user = update.effective_user
        total, subtotal, delivery_fee = calculate_total(context.user_data['cart'], context.user_data['pays'], context.user_data['livraison'], context.user_data.get('distance', 0))
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user.id}"

        order_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'order_id': order_id,
            'user_id': user.id,
            'username': user.username or "N/A",
            'first_name': user.first_name or "N/A",
            'products': "; ".join([f"{item['produit']} x{item['quantite']}" for item in context.user_data['cart']]),
            'country': context.user_data['pays'],
            'address': context.user_data['adresse'],
            'delivery_type': context.user_data['livraison'],
            'distance_km': context.user_data.get('distance', 0) if context.user_data['livraison'] == "express" else 0,
            'payment_method': context.user_data['paiement'],
            'subtotal': f"{subtotal:.2f}",
            'delivery_fee': f"{delivery_fee:.2f}",
            'total': f"{total:.2f}",
            'status': 'En attente'
        }
        save_order_to_csv(order_data)

        user_first = user.first_name or "N/A"
        user_username = f" (@{user.username})" if user.username else ""
        cart_formatted = format_cart(context.user_data['cart'], context.user_data)

        admin_message = f"🆕 *COMMANDE*\n\n📋 `{order_id}`\n👤 {user_first}{user_username}\n\n{cart_formatted}\n💰 *Total: {total}€*"
        admin_keyboard = [[InlineKeyboardButton("✅ Valider", callback_data=f"admin_validate_{order_id}_{user.id}")]]
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Erreur envoi admin: {e}")

        confirmation_msg = tr(context.user_data, "order_confirmed") + f"\n\n📋 `{order_id}`\n💰 {total:.2f}€"
        await query.message.edit_text(confirmation_msg, parse_mode='Markdown')
        context.user_data.clear()
        return ConversationHandler.END

    elif query.data == "cancel":
        return await cancel(update, context)

@error_handler
async def admin_validation_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Non autorisé", show_alert=True)
        return

    # data: admin_validate_{order_id}_{client_id}
    parts = query.data.split("_")
    # remove the first two pieces 'admin' 'validate'
    try:
        client_id = int(parts[-1])
        order_id = "_".join(parts[2:-1])
    except Exception:
        await query.answer("Données invalides", show_alert=True)
        return

    # Ici : on notifie le client que la livraison est validée
    try:
        await context.bot.send_message(chat_id=client_id, text=f"✅ Votre commande `{order_id}` a été validée par l'admin.", parse_mode='Markdown')
        await query.message.edit_text(f"✅ Validé: {order_id}")
    except Exception as e:
        logger.error(f"Admin validate error: {e}")

# --- Construction de l'application (factory) ---
def build_application():
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            LANGUE: [CallbackQueryHandler(set_langue, pattern='^lang_')],
            PAYS: [
                CallbackQueryHandler(menu_navigation, pattern='^(start_order|price_menu)$'),
                CallbackQueryHandler(choix_pays, pattern='^country_')
            ],
            PRODUIT: [CallbackQueryHandler(choix_produit, pattern='^product_')],
            QUANTITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)],
            CART_MENU: [CallbackQueryHandler(cart_menu, pattern='^(add_more|proceed_checkout)$')],
            ADRESSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse),
                CallbackQueryHandler(saisie_adresse, pattern='^back_to_address')
            ],
            LIVRAISON: [CallbackQueryHandler(choix_livraison, pattern='^delivery_')],
            PAIEMENT: [CallbackQueryHandler(choix_paiement, pattern='^payment_')],
            CONFIRMATION: [CallbackQueryHandler(confirmation, pattern='^(confirm_order|cancel)$')]
        },
        fallbacks=[CommandHandler('start', start_command), CallbackQueryHandler(cancel, pattern='^cancel$')],
        per_chat=True,
        per_user=True,
        per_message=False
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(admin_validation_livraison, pattern='^admin_validate_'))
    # Error handler global
    async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Global error: {context.error}", exc_info=context.error)
    application.add_error_handler(global_error_handler)

    return application

# Expose application object for app.py
bot_application = build_application()
logger.info("✅ bot_application prêt (importable depuis app.py)")
