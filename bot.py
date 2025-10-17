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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

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
    logger.error(f"❌ ADMIN_ID invalide")
    sys.exit(1)

ADMIN_ID = int(ADMIN_ID_STR)

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, CommandHandler, filters
except ImportError:
    logger.error("❌ pip install python-telegram-bot")
    sys.exit(1)

MAX_QUANTITY_PER_PRODUCT = 100
FRAIS_POSTAL = 10

LANGUE, PAYS, PRODUIT, PILL_SUBCATEGORY, ROCK_SUBCATEGORY = range(5)
QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION, CONTACT = range(5, 12)

PILL_SUBCATEGORIES = {"squid_game": "💊 Squid Game", "punisher": "💊 Punisher"}
ROCK_SUBCATEGORIES = {"mdma": "🪨 MDMA", "fourmmc": "🪨 4MMC"}

PRIX_FR = {"❄️ Coco": 80, "💊 Squid Game": 10, "💊 Punisher": 10, "🫒 Hash": 7, "🍀 Weed": 10, "🪨 MDMA": 50, "🪨 4MMC": 50}
PRIX_CH = {"❄️ Coco": 100, "💊 Squid Game": 15, "💊 Punisher": 15, "🫒 Hash": 8, "🍀 Weed": 12, "🪨 MDMA": 70, "🪨 4MMC": 70}

TRANSLATIONS = {
    "fr": {
        "welcome": "🌿 *BIENVENUE* 🌿\n\n⚠️ *VERSION 2.0*\n\nConversations en *ÉCHANGE SECRET*.\n\n🙏 *Merci* 💪💚",
        "main_menu": "\n\n📱 *MENU :*",
        "choose_country": "🌍 *Pays :*",
        "choose_product": "🛒 *Produit :*",
        "choose_pill_type": "💊 *Type :*",
        "choose_rock_type": "🪨 *Type :*",
        "enter_quantity": "🔢 *Quantité :*",
        "enter_address": "📍 *Adresse :*",
        "choose_delivery": "📦 *Livraison :*\n\n✉️ Postale: 48-72h, 10€\n⚡ Express: 30min+",
        "distance_calculated": "📏 {distance} km\n💶 {fee}€",
        "choose_payment": "💳 *Paiement :*",
        "order_summary": "✅ *RÉSUMÉ*",
        "confirm": "✅ Confirmer", "cancel": "❌ Annuler",
        "order_confirmed": "✅ *Confirmé !*\n\n📞 Contact sous peu.",
        "order_cancelled": "❌ *Annulé.*",
        "add_more": "➕ Ajouter", "proceed": "✅ Valider",
        "invalid_quantity": "❌ Invalide (1-{max}).",
        "cart_title": "🛒 *PANIER :*",
        "start_order": "🛒 Commander",
        "contact_admin": "📞 Contacter",
        "contact_message": "📞 *CONTACT*\n\nÉcrivez votre message.\n\n💬 Message ?",
        "contact_sent": "✅ *Envoyé !*\n\nRéponse sous peu.",
        "france": "🇫🇷 France", "switzerland": "🇨🇭 Suisse",
        "postal": "✉️ Postale", "express": "⚡ Express",
        "cash": "💵 Espèces", "crypto": "₿ Crypto",
        "total": "💰 *TOTAL :*", "delivery_fee": "📦 *Frais :*",
        "subtotal": "💵 *Sous-total :*", "back": "🔙 Retour",
        "pirate_card": "🏴‍☠️ Carte du Pirate",
        "choose_country_prices": "🏴‍☠️ *CARTE DU PIRATE*\n\nChoisissez votre pays :",
        "prices_france": "🇫🇷 Prix France",
        "prices_switzerland": "🇨🇭 Prix Suisse",
        "back_to_card": "🔙 Retour carte",
        "main_menu_btn": "🏠 Menu principal",
        "price_list_fr": "🇫🇷 *PRIX FRANCE*\n\n❄️ *Coco* : 80€/g\n💊 *Pills* :\n  • Squid Game : 10€\n  • Punisher : 10€\n🫒 *Hash* : 7€/g\n🍀 *Weed* : 10€/g\n🪨 *Crystal* :\n  • MDMA : 50€/g\n  • 4MMC : 50€/g\n\n📦 *Livraison* :\n  • Postale (48-72h) : 10€\n  • Express (30min+) : calculée",
        "price_list_ch": "🇨🇭 *PRIX SUISSE*\n\n❄️ *Coco* : 100€/g\n💊 *Pills* :\n  • Squid Game : 15€\n  • Punisher : 15€\n🫒 *Hash* : 8€/g\n🍀 *Weed* : 12€/g\n🪨 *Crystal* :\n  • MDMA : 70€/g\n  • 4MMC : 70€/g\n\n📦 *Livraison* :\n  • Postale (48-72h) : 10€\n  • Express (30min+) : calculée",
        "new_order": "🔄 Nouvelle commande",
        "address_too_short": "❌ Adresse trop courte"
    },
    "en": {
        "welcome": "🌿 *WELCOME* 🌿\n\n⚠️ *VERSION 2.0*\n\nConversations in *SECRET EXCHANGE*.\n\n🙏 *Thank you* 💪💚",
        "main_menu": "\n\n📱 *MENU:*",
        "choose_country": "🌍 *Country:*",
        "choose_product": "🛒 *Product:*",
        "choose_pill_type": "💊 *Type:*",
        "choose_rock_type": "🪨 *Type:*",
        "enter_quantity": "🔢 *Quantity:*",
        "enter_address": "📍 *Address:*",
        "choose_delivery": "📦 *Delivery:*\n\n✉️ Postal: 48-72h, 10€\n⚡ Express: 30min+",
        "distance_calculated": "📏 {distance} km\n💶 {fee}€",
        "choose_payment": "💳 *Payment:*",
        "order_summary": "✅ *SUMMARY*",
        "confirm": "✅ Confirm", "cancel": "❌ Cancel",
        "order_confirmed": "✅ *Confirmed!*\n\n📞 Contact soon.",
        "order_cancelled": "❌ *Cancelled.*",
        "add_more": "➕ Add more", "proceed": "✅ Proceed",
        "invalid_quantity": "❌ Invalid (1-{max}).",
        "cart_title": "🛒 *CART:*",
        "start_order": "🛒 Order",
        "contact_admin": "📞 Contact",
        "contact_message": "📞 *CONTACT*\n\nWrite your message.\n\n💬 Message?",
        "contact_sent": "✅ *Sent!*\n\nReply soon.",
        "france": "🇫🇷 France", "switzerland": "🇨🇭 Switzerland",
        "postal": "✉️ Postal", "express": "⚡ Express",
        "cash": "💵 Cash", "crypto": "₿ Crypto",
        "total": "💰 *TOTAL:*", "delivery_fee": "📦 *Fee:*",
        "subtotal": "💵 *Subtotal:*", "back": "🔙 Back",
        "pirate_card": "🏴‍☠️ Pirate Card",
        "choose_country_prices": "🏴‍☠️ *PIRATE CARD*\n\nChoose your country:",
        "prices_france": "🇫🇷 France Prices",
        "prices_switzerland": "🇨🇭 Switzerland Prices",
        "back_to_card": "🔙 Back to card",
        "main_menu_btn": "🏠 Main menu",
        "price_list_fr": "🇫🇷 *FRANCE PRICES*\n\n❄️ *Coco*: 80€/g\n💊 *Pills*:\n  • Squid Game: 10€\n  • Punisher: 10€\n🫒 *Hash*: 7€/g\n🍀 *Weed*: 10€/g\n🪨 *Crystal*:\n  • MDMA: 50€/g\n  • 4MMC: 50€/g\n\n📦 *Delivery*:\n  • Postal (48-72h): 10€\n  • Express (30min+): calculated",
        "price_list_ch": "🇨🇭 *SWITZERLAND PRICES*\n\n❄️ *Coco*: 100€/g\n💊 *Pills*:\n  • Squid Game: 15€\n  • Punisher: 15€\n🫒 *Hash*: 8€/g\n🍀 *Weed*: 12€/g\n🪨 *Crystal*:\n  • MDMA: 70€/g\n  • 4MMC: 70€/g\n\n📦 *Delivery*:\n  • Postal (48-72h): 10€\n  • Express (30min+): calculated",
        "new_order": "🔄 New order",
        "address_too_short": "❌ Address too short"
    },
    "de": {
        "welcome": "🌿 *WILLKOMMEN* 🌿\n\n⚠️ *VERSION 2.0*\n\nGespräche im *GEHEIMEN AUSTAUSCH*.\n\n🙏 *Danke* 💪💚",
        "main_menu": "\n\n📱 *MENÜ:*",
        "choose_country": "🌍 *Land:*",
        "choose_product": "🛒 *Produkt:*",
        "choose_pill_type": "💊 *Typ:*",
        "choose_rock_type": "🪨 *Typ:*",
        "enter_quantity": "🔢 *Menge:*",
        "enter_address": "📍 *Adresse:*",
        "choose_delivery": "📦 *Lieferung:*\n\n✉️ Post: 48-72h, 10€\n⚡ Express: 30min+",
        "distance_calculated": "📏 {distance} km\n💶 {fee}€",
        "choose_payment": "💳 *Zahlung:*",
        "order_summary": "✅ *ZUSAMMENFASSUNG*",
        "confirm": "✅ Bestätigen", "cancel": "❌ Abbrechen",
        "order_confirmed": "✅ *Bestätigt!*\n\n📞 Kontakt bald.",
        "order_cancelled": "❌ *Abgebrochen.*",
        "add_more": "➕ Mehr hinzufügen", "proceed": "✅ Weiter",
        "invalid_quantity": "❌ Ungültig (1-{max}).",
        "cart_title": "🛒 *WARENKORB:*",
        "start_order": "🛒 Bestellen",
        "contact_admin": "📞 Kontakt",
        "contact_message": "📞 *KONTAKT*\n\nSchreiben Sie Ihre Nachricht.\n\n💬 Nachricht?",
        "contact_sent": "✅ *Gesendet!*\n\nAntwort bald.",
        "france": "🇫🇷 Frankreich", "switzerland": "🇨🇭 Schweiz",
        "postal": "✉️ Post", "express": "⚡ Express",
        "cash": "💵 Bar", "crypto": "₿ Krypto",
        "total": "💰 *GESAMT:*", "delivery_fee": "📦 *Gebühr:*",
        "subtotal": "💵 *Zwischensumme:*", "back": "🔙 Zurück",
        "pirate_card": "🏴‍☠️ Piratenkarte",
        "choose_country_prices": "🏴‍☠️ *PIRATENKARTE*\n\nWählen Sie Ihr Land:",
        "prices_france": "🇫🇷 Preise Frankreich",
        "prices_switzerland": "🇨🇭 Preise Schweiz",
        "back_to_card": "🔙 Zurück zur Karte",
        "main_menu_btn": "🏠 Hauptmenü",
        "price_list_fr": "🇫🇷 *PREISE FRANKREICH*\n\n❄️ *Coco*: 80€/g\n💊 *Pillen*:\n  • Squid Game: 10€\n  • Punisher: 10€\n🫒 *Hash*: 7€/g\n🍀 *Weed*: 10€/g\n🪨 *Kristall*:\n  • MDMA: 50€/g\n  • 4MMC: 50€/g\n\n📦 *Lieferung*:\n  • Post (48-72h): 10€\n  • Express (30min+): berechnet",
        "price_list_ch": "🇨🇭 *PREISE SCHWEIZ*\n\n❄️ *Coco*: 100€/g\n💊 *Pillen*:\n  • Squid Game: 15€\n  • Punisher: 15€\n🫒 *Hash*: 8€/g\n🍀 *Weed*: 12€/g\n🪨 *Kristall*:\n  • MDMA: 70€/g\n  • 4MMC: 70€/g\n\n📦 *Lieferung*:\n  • Post (48-72h): 10€\n  • Express (30min+): berechnet",
        "new_order": "🔄 Neue Bestellung",
        "address_too_short": "❌ Adresse zu kurz"
    },
    "es": {
        "welcome": "🌿 *BIENVENIDO* 🌿\n\n⚠️ *VERSIÓN 2.0*\n\nConversaciones en *INTERCAMBIO SECRETO*.\n\n🙏 *Gracias* 💪💚",
        "main_menu": "\n\n📱 *MENÚ:*",
        "choose_country": "🌍 *País:*",
        "choose_product": "🛒 *Producto:*",
        "choose_pill_type": "💊 *Tipo:*",
        "choose_rock_type": "🪨 *Tipo:*",
        "enter_quantity": "🔢 *Cantidad:*",
        "enter_address": "📍 *Dirección:*",
        "choose_delivery": "📦 *Entrega:*\n\n✉️ Postal: 48-72h, 10€\n⚡ Express: 30min+",
        "distance_calculated": "📏 {distance} km\n💶 {fee}€",
        "choose_payment": "💳 *Pago:*",
        "order_summary": "✅ *RESUMEN*",
        "confirm": "✅ Confirmar", "cancel": "❌ Cancelar",
        "order_confirmed": "✅ *¡Confirmado!*\n\n📞 Contacto pronto.",
        "order_cancelled": "❌ *Cancelado.*",
        "add_more": "➕ Añadir más", "proceed": "✅ Continuar",
        "invalid_quantity": "❌ Inválido (1-{max}).",
        "cart_title": "🛒 *CARRITO:*",
        "start_order": "🛒 Pedir",
        "contact_admin": "📞 Contactar",
        "contact_message": "📞 *CONTACTO*\n\nEscriba su mensaje.\n\n💬 ¿Mensaje?",
        "contact_sent": "✅ *¡Enviado!*\n\nRespuesta pronto.",
        "france": "🇫🇷 Francia", "switzerland": "🇨🇭 Suiza",
        "postal": "✉️ Postal", "express": "⚡ Express",
        "cash": "💵 Efectivo", "crypto": "₿ Cripto",
        "total": "💰 *TOTAL:*", "delivery_fee": "📦 *Gastos:*",
        "subtotal": "💵 *Subtotal:*", "back": "🔙 Volver",
        "pirate_card": "🏴‍☠️ Carta Pirata",
        "choose_country_prices": "🏴‍☠️ *CARTA PIRATA*\n\nElija su país:",
        "prices_france": "🇫🇷 Precios Francia",
        "prices_switzerland": "🇨🇭 Precios Suiza",
        "back_to_card": "🔙 Volver a carta",
        "main_menu_btn": "🏠 Menú principal",
        "price_list_fr": "🇫🇷 *PRECIOS FRANCIA*\n\n❄️ *Coco*: 80€/g\n💊 *Pastillas*:\n  • Squid Game: 10€\n  • Punisher: 10€\n🫒 *Hash*: 7€/g\n🍀 *Weed*: 10€/g\n🪨 *Cristal*:\n  • MDMA: 50€/g\n  • 4MMC: 50€/g\n\n📦 *Entrega*:\n  • Postal (48-72h): 10€\n  • Express (30min+): calculado",
        "price_list_ch": "🇨🇭 *PRECIOS SUIZA*\n\n❄️ *Coco*: 100€/g\n💊 *Pastillas*:\n  • Squid Game: 15€\n  • Punisher: 15€\n🫒 *Hash*: 8€/g\n🍀 *Weed*: 12€/g\n🪨 *Cristal*:\n  • MDMA: 70€/g\n  • 4MMC: 70€/g\n\n📦 *Entrega*:\n  • Postal (48-72h): 10€\n  • Express (30min+): calculado",
        "new_order": "🔄 Nuevo pedido",
        "address_too_short": "❌ Dirección muy corta"
    },
    "it": {
        "welcome": "🌿 *BENVENUTO* 🌿\n\n⚠️ *VERSIONE 2.0*\n\nConversazioni in *SCAMBIO SEGRETO*.\n\n🙏 *Grazie* 💪💚",
        "main_menu": "\n\n📱 *MENU:*",
        "choose_country": "🌍 *Paese:*",
        "choose_product": "🛒 *Prodotto:*",
        "choose_pill_type": "💊 *Tipo:*",
        "choose_rock_type": "🪨 *Tipo:*",
        "enter_quantity": "🔢 *Quantità:*",
        "enter_address": "📍 *Indirizzo:*",
        "choose_delivery": "📦 *Consegna:*\n\n✉️ Postale: 48-72h, 10€\n⚡ Express: 30min+",
        "distance_calculated": "📏 {distance} km\n💶 {fee}€",
        "choose_payment": "💳 *Pagamento:*",
        "order_summary": "✅ *RIEPILOGO*",
        "confirm": "✅ Confermare", "cancel": "❌ Annullare",
        "order_confirmed": "✅ *Confermato!*\n\n📞 Contatto presto.",
        "order_cancelled": "❌ *Annullato.*",
        "add_more": "➕ Aggiungi altro", "proceed": "✅ Continua",
        "invalid_quantity": "❌ Non valido (1-{max}).",
        "cart_title": "🛒 *CARRELLO:*",
        "start_order": "🛒 Ordina",
        "contact_admin": "📞 Contatta",
        "contact_message": "📞 *CONTATTO*\n\nScrivi il tuo messaggio.\n\n💬 Messaggio?",
        "contact_sent": "✅ *Inviato!*\n\nRisposta presto.",
        "france": "🇫🇷 Francia", "switzerland": "🇨🇭 Svizzera",
        "postal": "✉️ Postale", "express": "⚡ Express",
        "cash": "💵 Contanti", "crypto": "₿ Crypto",
        "total": "💰 *TOTALE:*", "delivery_fee": "📦 *Spese:*",
        "subtotal": "💵 *Subtotale:*", "back": "🔙 Indietro",
        "pirate_card": "🏴‍☠️ Carta Pirata",
        "choose_country_prices": "🏴‍☠️ *CARTA PIRATA*\n\nScegli il tuo paese:",
        "prices_france": "🇫🇷 Prezzi Francia",
        "prices_switzerland": "🇨🇭 Prezzi Svizzera",
        "back_to_card": "🔙 Torna alla carta",
        "main_menu_btn": "🏠 Menu principale",
        "price_list_fr": "🇫🇷 *PREZZI FRANCIA*\n\n❄️ *Coco*: 80€/g\n💊 *Pillole*:\n  • Squid Game: 10€\n  • Punisher: 10€\n🫒 *Hash*: 7€/g\n🍀 *Weed*: 10€/g\n🪨 *Cristallo*:\n  • MDMA: 50€/g\n  • 4MMC: 50€/g\n\n📦 *Consegna*:\n  • Postale (48-72h): 10€\n  • Express (30min+): calcolato",
        "price_list_ch": "🇨🇭 *PREZZI SVIZZERA*\n\n❄️ *Coco*: 100€/g\n💊 *Pillole*:\n  • Squid Game: 15€\n  • Punisher: 15€\n🫒 *Hash*: 8€/g\n🍀 *Weed*: 12€/g\n🪨 *Cristallo*:\n  • MDMA: 70€/g\n  • 4MMC: 70€/g\n\n📦 *Consegna*:\n  • Postale (48-72h): 10€\n  • Express (30min+): calcolato",
        "new_order": "🔄 Nuovo ordine",
        "address_too_short": "❌ Indirizzo troppo corto"
    }
}

def tr(user_data, key):
    lang = user_data.get('langue', 'fr')
    t = TRANSLATIONS.get(lang, TRANSLATIONS['fr']).get(key, key)
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
            fieldnames = ['date', 'order_id', 'user_id', 'username', 'first_name', 'language', 'products', 'country', 'address', 'delivery_type', 'distance_km', 'payment_method', 'subtotal', 'delivery_fee', 'total', 'status']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(order_data)
        return True
    except Exception as e:
        logger.error(f"CSV: {e}")
        return False

def error_handler(func):
    @wraps(func)
    async def wrapper(update, context):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"{func.__name__}: {e}", exc_info=True)
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
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"👤 /start: {user.first_name}")
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it")]
    ]
    await update.message.reply_text("🌍 *Langue / Language / Sprache / Idioma / Lingua*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return LANGUE

@error_handler
async def set_langue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang_code = query.data.replace("lang_", "")
    context.user_data['langue'] = lang_code
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def voir_carte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu de sélection France/Suisse pour les prix"""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "prices_france"), callback_data="prix_france")],
        [InlineKeyboardButton(tr(context.user_data, "prices_switzerland"), callback_data="prix_suisse")],
        [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main_menu")]
    ]
    await query.message.edit_text(tr(context.user_data, "choose_country_prices"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def afficher_prix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les prix selon le pays"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "prix_france":
        text = tr(context.user_data, "price_list_fr")
    else:  # prix_suisse
        text = tr(context.user_data, "price_list_ch")
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "back_to_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au menu principal"""
    query = update.callback_query
    await query.answer()
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "contact_admin":
        await query.message.edit_text(tr(context.user_data, "contact_message"), parse_mode='Markdown')
        return CONTACT
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
        [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")]
    ]
    await query.message.edit_text(tr(context.user_data, "choose_country"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = sanitize_input(update.message.text, 1000)
    user_lang = context.user_data.get('langue', 'fr')
    lang_names = {'fr': 'Français', 'en': 'English', 'de': 'Deutsch', 'es': 'Español', 'it': 'Italiano'}
    admin_message = f"📞 *MESSAGE* ({lang_names.get(user_lang, user_lang)})\n\n👤 {user.first_name} (@{user.username or 'N/A'})\n🆔 `{user.id}`\n\n💬 {message_text}"
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, parse_mode='Markdown')
        await update.message.reply_text(tr(context.user_data, "contact_sent"), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Contact: {e}")
        await update.message.reply_text("❌ Erreur.")
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
    await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
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
        await query.message.edit_text(tr(context.user_data, "choose_pill_type"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PILL_SUBCATEGORY
    elif product_code == "rock":
        keyboard = [
            [InlineKeyboardButton("🪨 MDMA", callback_data="rock_mdma")],
            [InlineKeyboardButton("🪨 4MMC", callback_data="rock_fourmmc")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_products")]
        ]
        await query.message.edit_text(tr(context.user_data, "choose_rock_type"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return ROCK_SUBCATEGORY
    product_names = {"snow": "❄️ Coco", "olive": "🫒 Hash", "clover": "🍀 Weed"}
    context.user_data['current_product'] = product_names.get(product_code, product_code)
    await query.message.edit_text(f"✅ {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}", parse_mode='Markdown')
    return QUANTITE

@error_handler
async def choix_pill_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['current_product'] = PILL_SUBCATEGORIES.get(query.data.replace("pill_", ""), "💊")
    await query.message.edit_text(f"✅ {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}", parse_mode='Markdown')
    return QUANTITE

@error_handler
async def choix_rock_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['current_product'] = ROCK_SUBCATEGORIES.get(query.data.replace("rock_", ""), "🪨")
    await query.message.edit_text(f"✅ {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}", parse_mode='Markdown')
    return QUANTITE

@error_handler
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qty = sanitize_input(update.message.text, 10)
    if not qty.isdigit() or not (0 < int(qty) <= MAX_QUANTITY_PER_PRODUCT):
        await update.message.reply_text(tr(context.user_data, "invalid_quantity"))
        return QUANTITE
    context.user_data['cart'].append({"produit": context.user_data['current_product'], "quantite": int(qty)})
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "add_more"), callback_data="add_more")],
        [InlineKeyboardButton(tr(context.user_data, "proceed"), callback_data="proceed_checkout")]
    ]
    await update.message.reply_text(format_cart(context.user_data['cart'], context.user_data), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CART_MENU

@error_handler
async def cart_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "add_more":
        keyboard = [
            [InlineKeyboardButton("❄️ COCO", callback_data="product_snow")],
            [InlineKeyboardButton("💊 Pills", callback_data="product_pill")],
            [InlineKeyboardButton("🫒 Hash", callback_data="product_olive")],
            [InlineKeyboardButton("🍀 Weed", callback_data="product_clover")],
            [InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main")]
        ]
        await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PRODUIT
    else:
        await query.message.edit_text(tr(context.user_data, 'enter_address'), parse_mode='Markdown')
        return ADRESSE

@error_handler
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = sanitize_input(update.message.text, 300)
    if len(address) < 15:
        await update.message.reply_text(tr(context.user_data, "address_too_short"))
        return ADRESSE
    context.user_data['adresse'] = address
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "postal"), callback_data="delivery_postal")],
        [InlineKeyboardButton(tr(context.user_data, "express"), callback_data="delivery_express")]
    ]
    await update.message.reply_text(tr(context.user_data, "choose_delivery"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
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
        distance_text = tr(context.user_data, "distance_calculated").format(distance=distance_km, fee=delivery_fee)
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "cash"), callback_data="payment_cash")],
            [InlineKeyboardButton(tr(context.user_data, "crypto"), callback_data="payment_crypto")]
        ]
        await query.message.edit_text(f"{distance_text}\n\n{tr(context.user_data, 'choose_payment')}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PAIEMENT
    else:
        context.user_data['distance'] = 0
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "cash"), callback_data="payment_cash")],
            [InlineKeyboardButton(tr(context.user_data, "crypto"), callback_data="payment_crypto")]
        ]
        await query.message.edit_text(tr(context.user_data, "choose_payment"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PAIEMENT

@error_handler
async def back_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "back_to_main":
        text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
            [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
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
            [InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")]
        ]
        await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PRODUIT

@error_handler
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['paiement'] = query.data.replace("payment_", "")
    total, subtotal, delivery_fee = calculate_total(context.user_data['cart'], context.user_data['pays'], context.user_data['livraison'], context.user_data.get('distance', 0))
    summary = f"{tr(context.user_data, 'order_summary')}\n\n{format_cart(context.user_data['cart'], context.user_data)}\n{tr(context.user_data, 'subtotal')} {subtotal}€\n{tr(context.user_data, 'delivery_fee')} {delivery_fee}€\n{tr(context.user_data, 'total')} *{total}€*\n\n📍 {context.user_data['adresse']}\n📦 {context.user_data['livraison'].title()}\n💳 {context.user_data['paiement'].title()}"
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
        total, subtotal, delivery_fee = calculate_total(context.user_data['cart'], context.user_data['pays'], context.user_data['livraison'], context.user_data.get('distance', 0))
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user.id}"
        user_lang = context.user_data.get('langue', 'fr')
        lang_names = {'fr': 'Français', 'en': 'English', 'de': 'Deutsch', 'es': 'Español', 'it': 'Italiano'}
        
        order_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
            'order_id': order_id, 
            'user_id': user.id, 
            'username': user.username or "N/A", 
            'first_name': user.first_name or "N/A",
            'language': lang_names.get(user_lang, user_lang),
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
        
        # Message admin toujours en français
        admin_message = f"🆕 *COMMANDE* ({lang_names.get(user_lang, user_lang)})\n\n📋 `{order_id}`\n👤 {user.first_name} (@{user.username or 'N/A'})\n\n🛒 *PANIER :*\n"
        for item in context.user_data['cart']:
            admin_message += f"• {item['produit']} x {item['quantite']}\n"
        admin_message += f"\n💰 *TOTAL : {total}€*\n💵 Sous-total : {subtotal}€\n📦 Frais : {delivery_fee}€\n\n📍 {context.user_data['adresse']}\n📦 {context.user_data['livraison'].title()}\n💳 {context.user_data['paiement'].title()}"
        
        admin_keyboard = [[InlineKeyboardButton("✅ Valider", callback_data=f"admin_validate_{order_id}_{user.id}")]]
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Admin: {e}")
        
        keyboard = [[InlineKeyboardButton(tr(context.user_data, "new_order"), callback_data="restart_order")]]
        await query.message.edit_text(f"{tr(context.user_data, 'order_confirmed')}\n\n📋 `{order_id}`\n💰 {total}€", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return ConversationHandler.END
    else:
        await query.message.edit_text(tr(context.user_data, "order_cancelled"), parse_mode='Markdown')
        context.user_data.clear()
        return ConversationHandler.END

@error_handler
async def restart_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    saved_lang = context.user_data.get('langue', 'fr')
    context.user_data.clear()
    context.user_data['langue'] = saved_lang
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

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
        await query.message.edit_text(f"{query.message.text}\n\n✅ *VALIDÉE*", parse_mode='Markdown')
        await context.bot.send_message(chat_id=client_id, text=f"✅ *Validée !*\n\n📋 `{order_id}`\n\n💚", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Validation: {e}")
    await query.answer("✅ Validé!", show_alert=True)

async def error_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)

async def main_async():
    logger.info("=" * 60)
    logger.info("🤖 BOT TELEGRAM MULTILINGUE")
    logger.info("=" * 60)
    logger.info(f"📱 Token: {TOKEN[:15]}...")
    logger.info(f"👤 Admin: {ADMIN_ID}")
    logger.info("🌍 Langues: FR, EN, DE, ES, IT")
    logger.info("=" * 60)
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Application créée")
    await application.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook supprimé")
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command)
        ],
        states={
            LANGUE: [CallbackQueryHandler(set_langue, pattern='^lang_')],
            PAYS: [
                CallbackQueryHandler(menu_navigation, pattern='^(start_order|contact_admin)'),
                CallbackQueryHandler(choix_pays, pattern='^country_'),
                CallbackQueryHandler(restart_order, pattern='^restart_order'),
                CallbackQueryHandler(voir_carte, pattern='^voir_carte'),
                CallbackQueryHandler(afficher_prix, pattern='^prix_(france|suisse)'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu')
            ],
            ConversationHandler.TIMEOUT: [
                CallbackQueryHandler(restart_order, pattern='^restart_order')
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
            LIVRAISON: [CallbackQueryHandler(choix_livraison, pattern='^delivery_')],
            PAIEMENT: [CallbackQueryHandler(choix_paiement, pattern='^payment_')],
            CONFIRMATION: [CallbackQueryHandler(confirmation, pattern='^(confirm_order|cancel)')]
        },
        fallbacks=[
            CommandHandler('start', start_command),
            CallbackQueryHandler(restart_order, pattern='^restart_order')
        ],
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
