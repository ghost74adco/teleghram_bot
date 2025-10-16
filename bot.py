import os
import sys
import logging
import re
import csv
import math
import asyncio
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps
from collections import defaultdict
from datetime import datetime, timedelta

# FIX PYTHON 3.13
if sys.version_info >= (3, 13):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

# Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Variables d'environnement
for env_file in ['.env', 'infos.env']:
    dotenv_path = Path(__file__).parent / env_file
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
        logger.info(f"✅ Variables: {env_file}")
        break
else:
    load_dotenv()

TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
ADMIN_ID_STR = (os.getenv("ADMIN_ID") or os.getenv("ADMIN_USER_IDS") or "").strip()
ADMIN_ADDRESS = (os.getenv("ADMIN_ADDRESS") or "858 Rte du Chef Lieu, 74250 Fillinges").strip()

if not TOKEN or ':' not in TOKEN:
    logger.error("❌ TOKEN invalide")
    sys.exit(1)

if not ADMIN_ID_STR or not ADMIN_ID_STR.isdigit():
    logger.error(f"❌ ADMIN_ID invalide: {ADMIN_ID_STR}")
    sys.exit(1)

ADMIN_ID = int(ADMIN_ID_STR)

# Import Telegram
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, ContextTypes, CallbackQueryHandler,
        ConversationHandler, MessageHandler, CommandHandler, filters
    )
except ImportError:
    logger.error("❌ pip install python-telegram-bot")
    sys.exit(1)

# Config
MAX_QUANTITY_PER_PRODUCT = 100
FRAIS_POSTAL = 10

# États
LANGUE, PAYS, PRODUIT, PILL_SUBCATEGORY, ROCK_SUBCATEGORY = range(5)
QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION, CONTACT = range(5, 12)

PILL_SUBCATEGORIES = {"squid_game": "💊 Squid Game", "punisher": "💊 Punisher"}
ROCK_SUBCATEGORIES = {"mdma": "🪨 MDMA", "fourmmc": "🪨 4MMC"}

PRIX_FR = {
    "❄️ Coco": 80, "💊 Squid Game": 10, "💊 Punisher": 10,
    "🫒 Hash": 7, "🍀 Weed": 10, "🪨 MDMA": 50, "🪨 4MMC": 50
}
PRIX_CH = {
    "❄️ Coco": 100, "💊 Squid Game": 15, "💊 Punisher": 15,
    "🫒 Hash": 8, "🍀 Weed": 12, "🪨 MDMA": 70, "🪨 4MMC": 70
}

TRANSLATIONS = {
    "fr": {
        "welcome": "🌿 *BIENVENUE* 🌿\n\n⚠️ *VERSION 2.0 - NOUVEAU BOT*\n\n⚠️ *IMPORTANT :*\nConversations en *ÉCHANGE SECRET*.\n\n🙏 *Merci* 💪💚",
        "main_menu": "\n\n📱 *MENU PRINCIPAL :*",
        "choose_country": "🌍 *Pays de livraison :*",
        "choose_product": "🛒 *Choisissez votre produit :*",
        "choose_pill_type": "💊 *Type de pilule :*",
        "choose_rock_type": "🪨 *Type de crystal :*",
        "enter_quantity": "🔢 *Quantité désirée :*",
        "enter_address": "📍 *Adresse complète :*",
        "choose_delivery": "📦 *Type de livraison :*\n\n✉️ Postale: 48-72h, 10€\n⚡ Express: 30min+",
        "calculating_distance": "📏 Calcul...",
        "distance_calculated": "📏 Distance: {distance} km\n💶 Frais: {fee}€",
        "choose_payment": "💳 *Mode de paiement :*",
        "order_summary": "✅ *RÉSUMÉ*",
        "confirm": "✅ Confirmer", "cancel": "❌ Annuler",
        "order_confirmed": "✅ *Confirmé !*\n\n📞 Contact sous peu.",
        "order_cancelled": "❌ *Annulé.*",
        "add_more": "➕ Ajouter", "proceed": "✅ Valider",
        "invalid_quantity": "❌ Invalide (1-{max}).",
        "cart_title": "🛒 *PANIER :*",
        "start_order": "🛒 Commander",
        "contact_admin": "📞 Contacter",
        "contact_message": "📞 *CONTACT*\n\nÉcrivez votre message.\nIl sera transmis à l'admin.\n\n💬 Que souhaitez-vous dire ?",
        "contact_sent": "✅ *Message envoyé !*\n\nL'admin vous répondra sous peu.",
        "france": "🇫🇷 France", "switzerland": "🇨🇭 Suisse",
        "postal": "✉️ Postale", "express": "⚡ Express",
        "cash": "💵 Espèces", "crypto": "₿ Crypto",
        "total": "💰 *TOTAL :*", "delivery_fee": "📦 *Frais :*",
        "subtotal": "💵 *Sous-total :*", "back": "🔙 Retour"
    }
}

def tr(user_data, key):
    t = TRANSLATIONS.get("fr", {}).get(key, key)
    return t.replace("{max}", str(MAX_QUANTITY_PER_PRODUCT)) if "{max}" in t else t

def sanitize_input(text, max_length=300):
    if not text:
        return ""
    return re.sub(r'[<>{}[\]\\`|]', '', text.strip()[:max_length])

def calculate_delivery_fee(delivery_type, distance=0, subtotal=0):
    if delivery_type == "postal":
        return FRAIS_POSTAL
    elif delivery_type == "express":
        return math.ceil(((distance * 2) + (subtotal * 0.03)) / 10) * 10
    return 0

def calculate_distance_simple(address):
    import hashlib
    hash_val = int(hashlib.md5(address.encode()).hexdigest()[:8], 16)
    return (hash_val % 50) + 5

def calculate_total(cart, country, delivery_type=None, distance=0):
    prix_table = PRIX_FR if country == "FR" else PRIX_CH
    subtotal = sum(prix_table.get(item["produit"], 0) * item["quantite"] for item in cart)
    if delivery_type:
        delivery_fee = calculate_delivery_fee(delivery_type, distance, subtotal)
        return subtotal + delivery_fee, subtotal, delivery_fee
    return subtotal, subtotal, 0

def format_cart(cart, user_data):
    if not cart:
        return ""
    text = "\n" + tr(user_data, 'cart_title') + "\n"
    for item in cart:
        text += f"• {item['produit']} x {item['quantite']}\n"
    return text

def save_order_to_csv(order_data):
    csv_path = Path(__file__).parent / "orders.csv"
    try:
        file_exists = csv_path.exists()
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ['date', 'order_id', 'user_id', 'username', 'first_name',
                         'products', 'country', 'address', 'delivery_type', 'distance_km',
                         'payment_method', 'subtotal', 'delivery_fee', 'total', 'status']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(order_data)
        logger.info(f"✅ Commande: {order_data['order_id']}")
        return True
    except Exception as e:
        logger.error(f"❌ CSV: {e}")
        return False

def error_handler(func):
    @wraps(func)
    async def wrapper(update, context):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"Erreur {func.__name__}: {e}", exc_info=True)
            try:
                if update.callback_query:
                    await update.callback_query.answer("❌ Erreur")
                elif update.message:
                    await update.message.reply_text("❌ Erreur. /start")
            except:
                pass
            return ConversationHandler.END
    return wrapper

# HANDLERS
@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"👤 /start: {user.first_name} ({user.id})")
    context.user_data.clear()
    
    keyboard = [[InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")]]
    await update.message.reply_text(
        "🌍 *Langue / Language*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return LANGUE

@error_handler
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['langue'] = 'fr'
    
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "contact_admin":
        await query.message.edit_text(
            tr(context.user_data, "contact_message"),
            parse_mode='Markdown'
        )
        return CONTACT
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
        [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")]
    ]
    await query.message.edit_text(
        tr(context.user_data, "choose_country"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PAYS

@error_handler
async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = sanitize_input(update.message.text, 1000)
    
    admin_message = (
        f"📞 *MESSAGE UTILISATEUR*\n\n"
        f"👤 {user.first_name} (@{user.username or 'N/A'})\n"
        f"🆔 `{user.id}`\n\n"
        f"💬 Message:\n{message_text}"
    )
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_message,
            parse_mode='Markdown'
        )
        logger.info(f"📞 Contact de {user.first_name}")
        await update.message.reply_text(
            tr(context.user_data, "contact_sent"),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"❌ Contact: {e}")
        await update.message.reply_text("❌ Erreur d'envoi.")
    
    return ConversationHandler.END

@error_handler
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['pays'] = query.data.replace("country_", "")
    context.user_data['cart'] = []
    
    keyboard = [
        [InlineKeyboardButton("❄️ COCO", callback_data="product_snow")],
        [InlineKeyboardButton("💊 Pills", callback_data="product_pill")],
        [InlineKeyboardButton("🫒 Hash", callback_data="product_olive")],
        [InlineKeyboardButton("🍀 Weed", callback_data="product_clover")],
        [InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")],
        [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main")]
    ]
    await query.message.edit_text(
        tr(context.user_data, "choose_product"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PRODUIT

@error_handler
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_code = query.data.replace("product_", "")
    
    if product_code == "pill":
        keyboard = [
            [InlineKeyboardButton("💊 Squid Game", callback_data="pill_squid_game")],
            [InlineKeyboardButton("💊 Punisher", callback_data="pill_punisher")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_products")]
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
            [InlineKeyboardButton("🪨 4MMC", callback_data="rock_fourmmc")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_products")]
        ]
        await query.message.edit_text(
            tr(context.user_data, "choose_rock_type"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ROCK_SUBCATEGORY
    
    product_names = {"snow": "❄️ Coco", "olive": "🫒 Hash", "clover": "🍀 Weed"}
    context.user_data['current_product'] = product_names.get(product_code, product_code)
    await query.message.edit_text(
        f"✅ {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}",
        parse_mode='Markdown'
    )
    return QUANTITE

@error_handler
async def choix_pill_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['current_product'] = PILL_SUBCATEGORIES.get(
        query.data.replace("pill_", ""), "💊"
    )
    await query.message.edit_text(
        f"✅ {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}",
        parse_mode='Markdown'
    )
    return QUANTITE

@error_handler
async def choix_rock_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['current_product'] = ROCK_SUBCATEGORIES.get(
        query.data.replace("rock_", ""), "🪨"
    )
    await query.message.edit_text(
        f"✅ {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}",
        parse_mode='Markdown'
    )
    return QUANTITE

@error_handler
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qty = sanitize_input(update.message.text, 10)
    
    logger.info(f"📦 Quantité: '{qty}' de {update.effective_user.first_name}")
    
    if not qty.isdigit() or not (0 < int(qty) <= MAX_QUANTITY_PER_PRODUCT):
        await update.message.reply_text(tr(context.user_data, "invalid_quantity"))
        return QUANTITE
    
    context.user_data['cart'].append({
        "produit": context.user_data['current_product'],
        "quantite": int(qty)
    })
    
    logger.info(f"✅ Panier: {context.user_data['cart']}")
    
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
    query = update.callback_query
    await query.answer()
    
    logger.info(f"🛒 Cart: {query.data}")
    
    if query.data == "add_more":
        keyboard = [
            [InlineKeyboardButton("❄️ COCO", callback_data="product_snow")],
            [InlineKeyboardButton("💊 Pills", callback_data="product_pill")],
            [InlineKeyboardButton("🫒 Hash", callback_data="product_olive")],
            [InlineKeyboardButton("🍀 Weed", callback_data="product_clover")],
            [InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main")]
        ]
        await query.message.edit_text(
            tr(context.user_data, "choose_product"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return PRODUIT
    else:
        await query.message.edit_text(
            tr(context.user_data, 'enter_address'),
            parse_mode='Markdown'
        )
        return ADRESSE

@error_handler
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = sanitize_input(update.message.text, 300)
    if len(address) < 15:
        await update.message.reply_text("❌ Adresse trop courte (min 15)")
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
    query = update.callback_query
    await query.answer()
    delivery_type = query.data.replace("delivery_", "")
    context.user_data['livraison'] = delivery_type
    
    if delivery_type == "express":
        distance_km = calculate_distance_simple(context.user_data.get('adresse', ''))
        context.user_data['distance'] = distance_km
        subtotal, _, _ = calculate_total(context.user_data['cart'], context.user_data['pays'])
        delivery_fee = calculate_delivery_fee("express", distance_km, subtotal)
        
        distance_text = tr(context.user_data, "distance_calculated").format(
            distance=distance_km,
            fee=delivery_fee
        )
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "cash"), callback_data="payment_cash")],
            [InlineKeyboardButton(tr(context.user_data, "crypto"), callback_data="payment_crypto")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_address")]
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
            [InlineKeyboardButton(tr(context.user_data, "crypto"), callback_data="payment_crypto")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_address")]
        ]
        await query.message.edit_text(
            tr(context.user_data, "choose_payment"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return PAIEMENT

@error_handler
async def back_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_main":
        text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
            [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PAYS
    
    elif query.data == "back_to_products":
        keyboard = [
            [InlineKeyboardButton("❄️ COCO", callback_data="product_snow")],
            [InlineKeyboardButton("💊 Pills", callback_data="product_pill")],
            [InlineKeyboardButton("🫒 Hash", callback_data="product_olive")],
            [InlineKeyboardButton("🍀 Weed", callback_data="product_clover")],
            [InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main")]
        ]
        await query.message.edit_text(
            tr(context.user_data, "choose_product"),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return PRODUIT
    
    elif query.data == "back_to_address":
        await query.message.edit_text(
            tr(context.user_data, 'enter_address'),
            parse_mode='Markdown'
        )
        return ADRESSE

@error_handler
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['paiement'] = query.data.replace("payment_", "")
    
    total, subtotal, delivery_fee = calculate_total(
        context.user_data['cart'],
        context.user_data['pays'],
        context.user_data['livraison'],
        context.user_data.get('distance', 0)
    )
    
    summary = (
        f"{tr(context.user_data, 'order_summary')}\n\n"
        f"{format_cart(context.user_data['cart'], context.user_data)}\n"
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
    await query.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CONFIRMATION

@error_handler
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            'distance_km': context.user_data.get('distance', 0),
            'payment_method': context.user_data['paiement'],
            'subtotal': str(round(subtotal, 2)),
            'delivery_fee': str(round(delivery_fee, 2)),
            'total': str(round(total, 2)),
            'status': 'En attente'
        }
        save_order_to_csv(order_data)
        
        admin_message = (
            f"🆕 *COMMANDE*\n\n"
            f"📋 `{order_id}`\n"
            f"👤 {user.first_name} (@{user.username or 'N/A'})\n\n"
            f"{format_cart(context.user_data['cart'], context.user_data)}\n"
            f"💰 *{total}€*\n\n"
            f"📍 {context.user_data['adresse']}\n"
            f"💳 {context.user_data['paiement'].title()}"
        )
        
        admin_keyboard = [[InlineKeyboardButton(
            "✅ Valider",
            callback_data=f"admin_validate_{order_id}_{user.id}"
        )]]
        
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message,
                reply_markup=InlineKeyboardMarkup(admin_keyboard),
                parse_mode='Markdown'
            )
            logger.info(f"✅ Commande: {order_id}")
        except Exception as e:
            logger.error(f"❌ Admin: {e}")
        
        await query.message.edit_text(
            f"{tr(context.user_data, 'order_confirmed')}\n\n📋 `{order_id}`\n💰 {total}€",
            parse_mode='Markdown'
        )
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await query.message.edit_text(
            tr(context.user_data, "order_cancelled"),
            parse_mode='Markdown'
        )
        context.user_data.clear()
        return ConversationHandler.END

@error_handler
async def admin_validation_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Non autorisé", show_alert=True)
        return
    
    data_parts = query.data.split("_")
    order_id = "_".join(data_parts[2:-1])
    client_id = int(data_parts[-1])
    
    try:
        await query.message.edit_text(
            f"{query.message.text}\n\n✅ *VALIDÉE*",
            parse_mode='Markdown'
        )
        await context.bot.send_message(
            chat_id=client_id,
            text=f"✅ *Validée !*\n\n📋 `{order_id}`\n\n💚",
            parse_mode='Markdown'
        )
        logger.info(f"✅ Validée: {order_id}")
    except Exception as e:
        logger.error(f"❌ Validation: {e}")
    
    await query.answer("✅ Validé!", show_alert=True)

async def error_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)

async def main_async():
    logger.info("=" * 60)
    logger.info("🤖 BOT TELEGRAM")
    logger.info("=" * 60)
    logger.info(f"📱 Token: {TOKEN[:15]}...")
    logger.info(f"👤 Admin: {ADMIN_ID}")
    logger.info("=" * 60)
    
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Application créée")
    
    await application.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook supprimé")
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            LANGUE: [CallbackQueryHandler(set_langue, pattern='^lang_')],
            PAYS: [
                CallbackQueryHandler(menu_navigation, pattern='^(start_order|contact_admin)'),
                CallbackQueryHandler(choix_pays, pattern='^country_')
            ],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_handler)],
            PRODUIT: [
                CallbackQueryHandler(choix_produit, pattern='^product_'),
                CallbackQueryHandler(back_navigation, pattern='^back_')
            ],
            PILL_SUBCATEGORY: [
                CallbackQueryHandler(choix_pill_subcategory, pattern='^pill_'),
                CallbackQueryHandler(back_navigation, pattern='^back_')
            ],
            ROCK_SUBCATEGORY: [
                CallbackQueryHandler(choix_rock_subcategory, pattern='^rock_'),
                CallbackQueryHandler(back_navigation, pattern='^back_')
            ],
            QUANTITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)],
            CART_MENU: [
                CallbackQueryHandler(cart_menu, pattern='^(add_more|proceed_checkout)'),
                CallbackQueryHandler(back_navigation, pattern='^back_')
            ],
            ADRESSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse)],
            LIVRAISON: [
                CallbackQueryHandler(choix_livraison, pattern='^delivery_'),
                CallbackQueryHandler(back_navigation, pattern='^back_')
            ],
            PAIEMENT: [
                CallbackQueryHandler(choix_paiement, pattern='^payment_'),
                CallbackQueryHandler(back_navigation, pattern='^back_')
            ],
            CONFIRMATION: [CallbackQueryHandler(confirmation, pattern='^(confirm_order|cancel)')]
        },
        fallbacks=[CommandHandler('start', start_command)],
        allow_reentry=True,
        per_message=False
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(admin_validation_livraison, pattern='^admin_validate_'))
    application.add_error_handler(error_callback)
    
    logger.info("✅ Handlers configurés")
    logger.info("=" * 60)
    logger.info("🚀 EN LIGNE")
    logger.info("=" * 60)
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    
    import signal
    stop_event = asyncio.Event()
    
    def stop_handler(signum, frame):
        stop_event.set()
    
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    
    await stop_event.wait()
    
    await application.updater.stop()
    await application.stop()
    await application.shutdown()

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("\n⏹️  Arrêt...")
    except Exception as e:
        logger.error(f"❌ Erreur: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
