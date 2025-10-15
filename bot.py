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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

for env_file in ['.env', 'infos.env']:
    dotenv_path = Path(__file__).parent / env_file
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
        logger.info("✅ Variables: " + env_file)
        break
else:
    load_dotenv()

TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
ADMIN_ID_STR = (os.getenv("ADMIN_ID") or os.getenv("ADMIN_USER_IDS") or os.getenv("TELEGRAM_ADMIN_ID") or "").strip()
ADMIN_ADDRESS = (os.getenv("ADMIN_ADDRESS") or "858 Rte du Chef Lieu, 74250 Fillinges").strip()
API_BASE_URL = os.getenv("API_BASE_URL", "https://carte-du-pirate.onrender.com")

if not TOKEN or ':' not in TOKEN:
    logger.error("❌ TOKEN invalide!")
    sys.exit(1)

if not ADMIN_ID_STR or not ADMIN_ID_STR.isdigit():
    logger.error("❌ ADMIN_ID invalide: " + ADMIN_ID_STR)
    sys.exit(1)

ADMIN_ID = int(ADMIN_ID_STR)
logger.info("✅ Bot prêt - Admin: " + str(ADMIN_ID))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, CommandHandler, filters

USE_WHITELIST = False
AUTHORIZED_USERS = []
user_message_timestamps = defaultdict(list)
MAX_MESSAGES_PER_MINUTE = 30
RATE_LIMIT_WINDOW = 60
MAX_QUANTITY_PER_PRODUCT = 100
FRAIS_POSTAL = 10

LANGUE, PAYS, PRODUIT, PILL_SUBCATEGORY, ROCK_SUBCATEGORY, QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(11)

PILL_SUBCATEGORIES = {"squid_game": "💊 Squid Game", "punisher": "💊 Punisher"}
ROCK_SUBCATEGORIES = {"mdma": "🪨 MDMA", "fourmmc": "🪨 4MMC"}
PRIX_FR = {"❄️ Coco": 80, "💊 Squid Game": 10, "💊 Punisher": 10, "🫒 Hash": 7, "🍀 Weed": 10, "🪨 MDMA": 50, "🪨 4MMC": 50}
PRIX_CH = {"❄️ Coco": 100, "💊 Squid Game": 15, "💊 Punisher": 15, "🫒 Hash": 8, "🍀 Weed": 12, "🪨 MDMA": 70, "🪨 4MMC": 70}

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
        "choose_delivery": "📦 *Choisissez le type de livraison :*",
        "calculating_distance": "📏 Calcul...",
        "distance_calculated": "📏 *Distance :* {distance} km\n💶 *Frais :* {fee}€",
        "geocoding_error": "❌ Adresse introuvable.",
        "choose_payment": "💳 *Choisissez le mode de paiement :*",
        "order_summary": "✅ *Résumé de votre commande :*",
        "confirm": "✅ Confirmer", "cancel": "❌ Annuler",
        "order_confirmed": "✅ *Commande confirmée !*\n\nMerci ! 📞",
        "order_cancelled": "❌ *Commande annulée.*",
        "add_more": "➕ Ajouter", "proceed": "✅ Valider",
        "invalid_quantity": "❌ Nombre entre 1 et {max}.",
        "cart_title": "🛒 *Votre panier :*",
        "start_order": "🛒 Commander", "price_menu": "🏴‍☠️ Carte",
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

def sanitize_input(text, max_length=200):
    if not text:
        return ""
    return re.sub(r'[<>{}[\]\\`|]', '', text.strip()[:max_length])

def is_authorized(user_id):
    return not USE_WHITELIST or user_id in AUTHORIZED_USERS

def check_rate_limit(user_id):
    now = datetime.now()
    user_message_timestamps[user_id] = [ts for ts in user_message_timestamps[user_id] if now - ts < timedelta(seconds=RATE_LIMIT_WINDOW)]
    if len(user_message_timestamps[user_id]) >= MAX_MESSAGES_PER_MINUTE:
        return False
    user_message_timestamps[user_id].append(now)
    return True

def update_last_activity(user_data):
    user_data['last_activity'] = datetime.now()

def calculate_delivery_fee(delivery_type, distance=0, subtotal=0):
    if delivery_type == "postal":
        return FRAIS_POSTAL
    elif delivery_type == "express":
        return math.ceil(((distance * 2) + (subtotal * 0.03)) / 10) * 10
    return 0

async def get_distance_from_api(address):
    try:
        response = requests.post(
            API_BASE_URL + "/api/calculate-distance",
            json={"address": address},
            timeout=15
        )
        if response.status_code == 200:
            data = response.json()
            return (data.get('distance_km', 0), True, None)
        else:
            return (0, False, "Erreur API")
    except Exception as e:
        logger.error("Erreur calcul distance: " + str(e))
        return (0, False, str(e))

def calculate_total(cart, country, delivery_type=None, distance=0):
    prix_table = PRIX_FR if country == "FR" else PRIX_CH
    subtotal = sum(prix_table[item["produit"]] * item["quantite"] for item in cart)
    if delivery_type:
        delivery_fee = calculate_delivery_fee(delivery_type, distance, subtotal)
        return subtotal + delivery_fee, subtotal, delivery_fee
    return subtotal, subtotal, 0

def format_cart(cart, user_data):
    if not cart:
        return ""
    text = "\n" + tr(user_data, 'cart_title') + "\n"
    for item in cart:
        text += "• " + item['produit'] + " x " + str(item['quantite']) + "\n"
    return text

def save_order_to_csv(order_data):
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
        logger.error("CSV: " + str(e))
        return False

def error_handler(func):
    @wraps(func)
    async def wrapper(update, context):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(func.__name__ + ": " + str(e), exc_info=True)
            try:
                if update.callback_query:
                    await update.callback_query.answer("❌ Erreur")
                elif update.message:
                    await update.message.reply_text("❌ Erreur. /start")
            except:
                pass
            return ConversationHandler.END
    return wrapper

@error_handler
async def start_command(update, context):
    user = update.effective_user
    logger.info("👤 /start: " + user.first_name + " (" + str(user.id) + ")")
    context.user_data.clear()
    update_last_activity(context.user_data)
    
    if not is_authorized(user.id):
        await update.message.reply_text("❌ Non autorisé")
        return ConversationHandler.END
    
    if not check_rate_limit(user.id):
        await update.message.reply_text("⚠️ Trop rapide")
        return
    
    keyboard = [[InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")], [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]]
    await update.message.reply_text("🌍 *Choisissez votre langue / Select your language*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return LANGUE

@error_handler
async def set_langue(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['langue'] = query.data.replace("lang_", "")
    update_last_activity(context.user_data)
    
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    keyboard = [[InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")], [InlineKeyboardButton(tr(context.user_data, "price_menu"), callback_data="price_menu")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def menu_navigation(update, context):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    if 'langue' not in context.user_data:
        context.user_data['langue'] = 'fr'
    
    if query.data == "start_order":
        keyboard = [[InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")], [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")]]
        text = tr(context.user_data, "choose_country")
    elif query.data == "price_menu":
        text = "🏴‍☠️ *CARTE*\n\n🇫🇷 *France:*\n❄️ Coco: 80€/g\n💊 Pills: 10€\n🫒 Hash: 7€/g\n🍀 Weed: 10€/g\n🪨 MDMA/4MMC: 50€/g\n\n🇨🇭 *Suisse:*\n❄️ Coco: 100€/g\n💊 Pills: 15€\n🫒 Hash: 8€/g\n🍀 Weed: 12€/g\n🪨 MDMA/4MMC: 70€/g"
        keyboard = [[InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def choix_pays(update, context):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    context.user_data['pays'] = query.data.replace("country_", "")
    context.user_data['cart'] = []
    
    keyboard = [[InlineKeyboardButton("❄️ COCO", callback_data="product_snow")], [InlineKeyboardButton("💊 Pills", callback_data="product_pill")], [InlineKeyboardButton("🫒 Hash", callback_data="product_olive")], [InlineKeyboardButton("🍀 Weed", callback_data="product_clover")], [InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")]]
    await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PRODUIT

@error_handler
async def choix_produit(update, context):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    product_code = query.data.replace("product_", "")
    
    if product_code == "pill":
        keyboard = [[InlineKeyboardButton("💊 Squid Game", callback_data="pill_squid_game")], [InlineKeyboardButton("💊 Punisher", callback_data="pill_punisher")]]
        await query.message.edit_text(tr(context.user_data, "choose_pill_type"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PILL_SUBCATEGORY
    elif product_code == "rock":
        keyboard = [[InlineKeyboardButton("🪨 MDMA", callback_data="rock_mdma")], [InlineKeyboardButton("🪨 4MMC", callback_data="rock_fourmmc")]]
        await query.message.edit_text(tr(context.user_data, "choose_rock_type"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return ROCK_SUBCATEGORY
    
    product_names = {"snow": "❄️ Coco", "olive": "🫒 Hash", "clover": "🍀 Weed"}
    context.user_data['current_product'] = product_names.get(product_code, product_code)
    
    prod = context.user_data['current_product']
    qty_text = tr(context.user_data, 'enter_quantity')
    await query.message.edit_text("✅ Produit : " + prod + "\n\n" + qty_text, parse_mode='Markdown')
    return QUANTITE

@error_handler
async def choix_pill_subcategory(update, context):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    context.user_data['current_product'] = PILL_SUBCATEGORIES.get(query.data.replace("pill_", ""), "💊")
    
    prod = context.user_data['current_product']
    qty_text = tr(context.user_data, 'enter_quantity')
    await query.message.edit_text("✅ Produit : " + prod + "\n\n" + qty_text, parse_mode='Markdown')
    return QUANTITE

@error_handler
async def choix_rock_subcategory(update, context):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    context.user_data['current_product'] = ROCK_SUBCATEGORIES.get(query.data.replace("rock_", ""), "🪨")
    
    prod = context.user_data['current_product']
    qty_text = tr(context.user_data, 'enter_quantity')
    await query.message.edit_text("✅ Produit : " + prod + "\n\n" + qty_text, parse_mode='Markdown')
    return QUANTITE

@error_handler
async def saisie_quantite(update, context):
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
async def cart_menu(update, context):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    
    if query.data == "add_more":
        keyboard = [[InlineKeyboardButton("❄️ COCO", callback_data="product_snow")], [InlineKeyboardButton("💊 Pills", callback_data="product_pill")], [InlineKeyboardButton("🫒 Hash", callback_data="product_olive")], [InlineKeyboardButton("🍀 Weed", callback_data="product_clover")], [InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")]]
        await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PRODUIT
    elif query.data == "proceed_checkout":
        await query.message.edit_text(tr(context.user_data, 'enter_address'), parse_mode='Markdown')
        return ADRESSE

@error_handler
async def saisie_adresse(update, context):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(tr(context.user_data, 'enter_address'), parse_mode='Markdown')
        return ADRESSE
    
    address = sanitize_input(update.message.text, 300)
    update_last_activity(context.user_data)
    
    if len(address) < 15:
        await update.message.reply_text("❌ Adresse trop courte (min 15 car.)")
        return ADRESSE
    
    context.user_data['adresse'] = address
    keyboard = [[InlineKeyboardButton(tr(context.user_data, "postal"), callback_data="delivery_postal")], [InlineKeyboardButton(tr(context.user_data, "express"), callback_data="delivery_express")]]
    await update.message.reply_text(tr(context.user_data, "choose_delivery"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return LIVRAISON

@error_handler
async def choix_livraison(update, context):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    delivery_type = query.data.replace("delivery_", "")
    context.user_data['livraison'] = delivery_type
    
    if delivery_type == "express":
        await query.message.edit_text(tr(context.user_data, "calculating_distance"), parse_mode='Markdown')
        distance_km, success, error_msg = await get_distance_from_api(context.user_data.get('adresse', ''))
        
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
async def choix_paiement(update, context):
    query = update.callback_query
    await query.answer()
    update_last_activity(context.user_data)
    context.user_data['paiement'] = query.data.replace("payment_", "")
    
    total, subtotal, delivery_fee = calculate_total(context.user_data['cart'], context.user_data['pays'], context.user_data['livraison'], context.user_data.get('distance', 0))
    
    cart_text = format_cart(context.user_data['cart'], context.user_data)
    addr = context.user_data['adresse']
    livr = context.user_data['livraison'].title()
    paie = context.user_data['paiement'].title()
    
    summary = tr(context.user_data, 'order_summary') + "\n\n" + cart_text + "\n" + tr(context.user_data, 'subtotal') + " " + str(subtotal) + "€\n" + tr(context.user_data, 'delivery_fee') + " " + str(delivery_fee) + "€\n" + tr(context.user_data, 'total') + " *" + str(total) + "€*\n\n📍 " + addr + "\n📦 " + livr + "\n💳 " + paie
    
    keyboard = [[InlineKeyboardButton(tr(context.user_data, "confirm"), callback_data="confirm_order")], [InlineKeyboardButton(tr(context.user_data, "cancel"), callback_data="cancel")]]
    await query.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CONFIRMATION

@error_handler
async def confirmation(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_order":
        user = update.effective_user
        total, subtotal, delivery_fee = calculate_total(context.user_data['cart'], context.user_data['pays'], context.user_data['livraison'], context.user_data.get('distance', 0))
        order_id = "ORD-" + datetime.now().strftime('%Y%m%d%H%M%S') + "-" + str(user.id)
        
        order_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
            'order_id': order_id, 
            'user_id': user.id, 
            'username': user.username or "N/A", 
            'first_name': user.first_name or "N/A",
            'products': "; ".join([item['produit'] + " x" + str(item['quantite']) for item in context.user_data['cart']]),
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
        save_order_to_csv(order_data)
        
        user_name = user.first_name or "N/A"
        user_tag = " (@" + user.username + ")" if user.username else ""
        cart_fmt = format_cart(context.user_data['cart'], context.user_data)
        
        admin_message = "🆕 *COMMANDE*\n\n📋 `" + order_id + "`\n👤 " + user_name + user_tag + "\n\n" + cart_fmt + "\n💰 *Total: " + str(total) + "€*"
        admin_keyboard = [[InlineKeyboardButton("✅ Valider", callback_data="admin_validate_" + order_id + "_" + str(user.id))]]
        
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode='Markdown')
        except Exception as e:
            logger.error("Admin: " + str(e))
        
        conf_msg = tr(context.user_data, "order_confirmed") + "\n\n📋 `" + order_id + "`\n💰 " + str(round(total, 2)) + "€"
        await query.message.edit_text(conf_msg, parse_mode='Markdown')
        context.user_data.clear()
        return ConversationHandler.END
    
    elif query.data == "cancel":
        return await cancel(update, context)

@error_handler
async def admin_validation_livraison(update, context):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Non autorisé", show_alert=True)
        return
    
    data_parts = query.data.split("_")
    order_id = "_".join(data_parts[2:-1])
    client_id = int(data_parts[-1])
    
    try:
        old_text = query.message.text
        await query.message.edit_text(old_text + "\n\n✅ *VALIDÉE*", parse_mode='Markdown')
        await context.bot.send_message(chat_id=client_id, text="✅ *Livraison confirmée !*\n\n📋 `" + order_id + "`\n\nMerci ! 💚", parse_mode='Markdown')
    except Exception as e:
        logger.error("Validation: " + str(e))
    
    await query.answer("✅ Validé!", show_alert=True)

@error_handler
async def cancel(update, context):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(tr(context.user_data, "order_cancelled"), parse_mode='Markdown')
    context.user_data.clear()
    return ConversationHandler.END

async def error_callback(update, context):
    logger.error("Exception: " + str(context.error), exc_info=context.error)

def main():
    logger.info("🤖 Configuration du bot...")
    logger.info("📱 Token: " + TOKEN[:10] + "...")
    
    try:
        application = Application.builder().token(TOKEN).build()
    except Exception as e:
        logger.error("❌ Erreur création application: " + str(e))
        sys.exit(1)
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            LANGUE: [CallbackQueryHandler(set_langue, pattern='^lang_')],
            PAYS: [
                CallbackQueryHandler(menu_navigation, pattern='^(start_order|price_menu)'),
                CallbackQueryHandler(choix_pays, pattern='^country_')
            ],
            PRODUIT: [CallbackQueryHandler(choix_produit, pattern='^product_')],
            PILL_SUBCATEGORY: [CallbackQueryHandler(choix_pill_subcategory, pattern='^pill_')],
            ROCK_SUBCATEGORY: [CallbackQueryHandler(choix_rock_subcategory, pattern='^rock_')],
            QUANTITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)],
            CART_MENU: [CallbackQueryHandler(cart_menu, pattern='^(add_more|proceed_checkout)')],
            ADRESSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse),
                CallbackQueryHandler(saisie_adresse, pattern='^back_to_address')
            ],
            LIVRAISON: [CallbackQueryHandler(choix_livraison, pattern='^delivery_')],
            PAIEMENT: [CallbackQueryHandler(choix_paiement, pattern='^payment_')],
            CONFIRMATION: [CallbackQueryHandler(confirmation, pattern='^(confirm_order|cancel)')]
        },
        fallbacks=[CommandHandler('start', start_command)],
        allow_reentry=True
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(admin_validation_livraison, pattern='^admin_validate_'))
    application.add_error_handler(error_callback)
    
    logger.info("✅ Handlers configurés")
    logger.info("🚀 Démarrage du polling...")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except Exception as e:
        logger.error("❌ Erreur polling: " + str(e))
        sys.exit(1)

if __name__ == '__main__':
    main()
