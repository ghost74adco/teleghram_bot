import os
import sys
import logging
import re
import csv
import math
import asyncio
import json
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps
from collections import defaultdict
from datetime import datetime, timedelta, time

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

# États de la conversation
LANGUE, PAYS, PRODUIT, PILL_SUBCATEGORY, ROCK_SUBCATEGORY = range(5)
QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION, CONTACT = range(5, 12)
ADMIN_HORAIRES_INPUT = 12

PILL_SUBCATEGORIES = {"squid_game": "💊 Squid Game", "punisher": "💊 Punisher"}
ROCK_SUBCATEGORIES = {"mdma": "🪨 MDMA", "fourmmc": "🪨 4MMC"}

PRIX_FR = {"❄️ Coco": 80, "💊 Squid Game": 10, "💊 Punisher": 10, "🫒 Hash": 7, "🍀 Weed": 10, "🪨 MDMA": 50, "🪨 4MMC": 50}
PRIX_CH = {"❄️ Coco": 100, "💊 Squid Game": 15, "💊 Punisher": 15, "🫒 Hash": 8, "🍀 Weed": 12, "🪨 MDMA": 70, "🪨 4MMC": 70}

# Fichiers de configuration
HORAIRES_FILE = Path(__file__).parent / "horaires.json"
STATS_FILE = Path(__file__).parent / "stats.json"
PENDING_MESSAGES_FILE = Path(__file__).parent / "pending_messages.json"

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
        "price_list_fr": "🇫🇷 *PRIX FRANCE*\n\n❄️ *Coco* : 80€/g\n💊 *Pills* :\n  • Squid Game : 10€\n  • Punisher : 10€\n🫒 *Hash* : 7€/g\n🍀 *Weed* : 10€/g\n🪨 *Crystal* :\n  • MDMA : 50€/g\n  • 4MMC : 50€/g\n\n📦 *Livraison* :\n  • Postale (48-72h) : 10€\n  • Express (30min+) : 10€/km",
        "price_list_ch": "🇨🇭 *PRIX SUISSE*\n\n❄️ *Coco* : 100€/g\n💊 *Pills* :\n  • Squid Game : 15€\n  • Punisher : 15€\n🫒 *Hash* : 8€/g\n🍀 *Weed* : 12€/g\n🪨 *Crystal* :\n  • MDMA : 70€/g\n  • 4MMC : 70€/g\n\n📦 *Livraison* :\n  • Postale (48-72h) : 10€\n  • Express (30min+) : 10€/km",
        "new_order": "🔄 Nouvelle commande",
        "address_too_short": "❌ Adresse trop courte",
        "outside_hours": "⏰ Livraisons fermées.\n\nHoraires : {hours}"
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
        "price_list_fr": "🇫🇷 *FRANCE PRICES*\n\n❄️ *Coco*: 80€/g\n💊 *Pills*:\n  • Squid Game: 10€\n  • Punisher: 10€\n🫒 *Hash*: 7€/g\n🍀 *Weed*: 10€/g\n🪨 *Crystal*:\n  • MDMA: 50€/g\n  • 4MMC: 50€/g\n\n📦 *Delivery*:\n  • Postal (48-72h): 10€\n  • Express (30min+): 10€/km",
        "price_list_ch": "🇨🇭 *SWITZERLAND PRICES*\n\n❄️ *Coco*: 100€/g\n💊 *Pills*:\n  • Squid Game: 15€\n  • Punisher: 15€\n🫒 *Hash*: 8€/g\n🍀 *Weed*: 12€/g\n🪨 *Crystal*:\n  • MDMA: 70€/g\n  • 4MMC: 70€/g\n\n📦 *Delivery*:\n  • Postal (48-72h): 10€\n  • Express (30min+): 10€/km",
        "new_order": "🔄 New order",
        "address_too_short": "❌ Address too short",
        "outside_hours": "⏰ Deliveries closed.\n\nHours: {hours}"
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
        "price_list_fr": "🇫🇷 *PREISE FRANKREICH*\n\n❄️ *Coco*: 80€/g\n💊 *Pillen*:\n  • Squid Game: 10€\n  • Punisher: 10€\n🫒 *Hash*: 7€/g\n🍀 *Weed*: 10€/g\n🪨 *Kristall*:\n  • MDMA: 50€/g\n  • 4MMC: 50€/g\n\n📦 *Lieferung*:\n  • Post (48-72h): 10€\n  • Express (30min+): 10€/km",
        "price_list_ch": "🇨🇭 *PREISE SCHWEIZ*\n\n❄️ *Coco*: 100€/g\n💊 *Pillen*:\n  • Squid Game: 15€\n  • Punisher: 15€\n🫒 *Hash*: 8€/g\n🍀 *Weed*: 12€/g\n🪨 *Kristall*:\n  • MDMA: 70€/g\n  • 4MMC: 70€/g\n\n📦 *Lieferung*:\n  • Post (48-72h): 10€\n  • Express (30min+): 10€/km",
        "new_order": "🔄 Neue Bestellung",
        "address_too_short": "❌ Adresse zu kurz",
        "outside_hours": "⏰ Lieferungen geschlossen.\n\nZeiten: {hours}"
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
        "price_list_fr": "🇫🇷 *PRECIOS FRANCIA*\n\n❄️ *Coco*: 80€/g\n💊 *Pastillas*:\n  • Squid Game: 10€\n  • Punisher: 10€\n🫒 *Hash*: 7€/g\n🍀 *Weed*: 10€/g\n🪨 *Cristal*:\n  • MDMA: 50€/g\n  • 4MMC: 50€/g\n\n📦 *Entrega*:\n  • Postal (48-72h): 10€\n  • Express (30min+): 10€/km",
        "price_list_ch": "🇨🇭 *PRECIOS SUIZA*\n\n❄️ *Coco*: 100€/g\n💊 *Pastillas*:\n  • Squid Game: 15€\n  • Punisher: 15€\n🫒 *Hash*: 8€/g\n🍀 *Weed*: 12€/g\n🪨 *Cristal*:\n  • MDMA: 70€/g\n  • 4MMC: 70€/g\n\n📦 *Entrega*:\n  • Postal (48-72h): 10€\n  • Express (30min+): 10€/km",
        "new_order": "🔄 Nuevo pedido",
        "address_too_short": "❌ Dirección muy corta",
        "outside_hours": "⏰ Entregas cerradas.\n\nHorario: {hours}"
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
        "price_list_fr": "🇫🇷 *PREZZI FRANCIA*\n\n❄️ *Coco*: 80€/g\n💊 *Pillole*:\n  • Squid Game: 10€\n  • Punisher: 10€\n🫒 *Hash*: 7€/g\n🍀 *Weed*: 10€/g\n🪨 *Cristallo*:\n  • MDMA: 50€/g\n  • 4MMC: 50€/g\n\n📦 *Consegna*:\n  • Postale (48-72h): 10€\n  • Express (30min+): 10€/km",
        "price_list_ch": "🇨🇭 *PREZZI SVIZZERA*\n\n❄️ *Coco*: 100€/g\n💊 *Pillole*:\n  • Squid Game: 15€\n  • Punisher: 15€\n🫒 *Hash*: 8€/g\n🍀 *Weed*: 12€/g\n🪨 *Cristallo*:\n  • MDMA: 70€/g\n  • 4MMC: 70€/g\n\n📦 *Consegna*:\n  • Postale (48-72h): 10€\n  • Express (30min+): 10€/km",
        "new_order": "🔄 Nuovo ordine",
        "address_too_short": "❌ Indirizzo troppo corto",
        "outside_hours": "⏰ Consegne chiuse.\n\nOrari: {hours}"
    }
}

# ==================== FONCTIONS UTILITAIRES ====================

def load_horaires():
    """Charge les horaires depuis le fichier JSON"""
    if HORAIRES_FILE.exists():
        try:
            with open(HORAIRES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"enabled": True, "start_hour": 9, "start_minute": 0, "end_hour": 23, "end_minute": 0}

def save_horaires(horaires):
    """Sauvegarde les horaires dans le fichier JSON"""
    try:
        with open(HORAIRES_FILE, 'w', encoding='utf-8') as f:
            json.dump(horaires, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde horaires: {e}")
        return False

def is_within_delivery_hours():
    """Vérifie si on est dans les horaires de livraison"""
    horaires = load_horaires()
    if not horaires.get("enabled", True):
        return True
    now = datetime.now().time()
    start = time(horaires["start_hour"], horaires["start_minute"])
    end = time(horaires["end_hour"], horaires["end_minute"])
    return start <= now <= end

def get_horaires_text():
    """Retourne le texte des horaires actuels"""
    horaires = load_horaires()
    if not horaires.get("enabled", True):
        return "24h/24 (toujours ouvert)"
    return f"{horaires['start_hour']:02d}:{horaires['start_minute']:02d} - {horaires['end_hour']:02d}:{horaires['end_minute']:02d}"

def load_pending_messages():
    """Charge les messages en attente de suppression"""
    if PENDING_MESSAGES_FILE.exists():
        try:
            with open(PENDING_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []

def save_pending_messages(messages):
    """Sauvegarde les messages en attente"""
    try:
        with open(PENDING_MESSAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde messages: {e}")
        return False

def add_pending_message(chat_id, message_id, delete_at):
    """Ajoute un message à supprimer plus tard"""
    messages = load_pending_messages()
    messages.append({"chat_id": chat_id, "message_id": message_id, "delete_at": delete_at.isoformat()})
    save_pending_messages(messages)

async def check_pending_deletions(context: ContextTypes.DEFAULT_TYPE):
    """Vérifie et supprime les messages programmés"""
    messages = load_pending_messages()
    now = datetime.now()
    to_keep = []
    for msg in messages:
        delete_time = datetime.fromisoformat(msg["delete_at"])
        if now >= delete_time:
            try:
                await context.bot.delete_message(chat_id=msg["chat_id"], message_id=msg["message_id"])
                logger.info(f"✅ Message supprimé: {msg['message_id']}")
            except Exception as e:
                logger.error(f"Erreur suppression message: {e}")
        else:
            to_keep.append(msg)
    save_pending_messages(to_keep)

def load_stats():
    """Charge les statistiques"""
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"weekly": [], "monthly": [], "last_weekly_report": None, "last_monthly_report": None}

def save_stats(stats):
    """Sauvegarde les statistiques"""
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde stats: {e}")
        return False

def add_sale(amount, country, products):
    """Ajoute une vente aux statistiques"""
    stats = load_stats()
    sale_data = {"date": datetime.now().isoformat(), "amount": amount, "country": country, "products": products}
    stats["weekly"].append(sale_data)
    stats["monthly"].append(sale_data)
    save_stats(stats)

async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Envoie le rapport hebdomadaire"""
    stats = load_stats()
    weekly_sales = stats.get("weekly", [])
    if not weekly_sales:
        return
    total = sum(sale["amount"] for sale in weekly_sales)
    count = len(weekly_sales)
    fr_count = sum(1 for sale in weekly_sales if sale.get("country") == "FR")
    ch_count = sum(1 for sale in weekly_sales if sale.get("country") == "CH")
    report = f"📊 *RAPPORT HEBDOMADAIRE*\n\n📅 Semaine du {datetime.now().strftime('%d/%m/%Y')}\n\n💰 *Chiffre d'affaires :* {total:.2f}€\n📦 *Commandes :* {count}\n🇫🇷 France : {fr_count}\n🇨🇭 Suisse : {ch_count}\n💵 *Panier moyen :* {total/count:.2f}€\n"
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode='Markdown')
        stats["weekly"] = []
        stats["last_weekly_report"] = datetime.now().isoformat()
        save_stats(stats)
        logger.info("✅ Rapport hebdomadaire envoyé")
    except Exception as e:
        logger.error(f"Erreur envoi rapport hebdo: {e}")

async def send_monthly_report(context: ContextTypes.DEFAULT_TYPE):
    """Envoie le rapport mensuel"""
    stats = load_stats()
    monthly_sales = stats.get("monthly", [])
    if not monthly_sales:
        return
    total = sum(sale["amount"] for sale in monthly_sales)
    count = len(monthly_sales)
    fr_count = sum(1 for sale in monthly_sales if sale.get("country") == "FR")
    ch_count = sum(1 for sale in monthly_sales if sale.get("country") == "CH")
    product_count = defaultdict(int)
    for sale in monthly_sales:
        for product in sale.get("products", "").split(";"):
            if product.strip():
                product_count[product.strip()] += 1
    top_products = sorted(product_count.items(), key=lambda x: x[1], reverse=True)[:5]
    report = f"📊 *RAPPORT MENSUEL*\n\n📅 Mois de {datetime.now().strftime('%B %Y')}\n\n💰 *Chiffre d'affaires :* {total:.2f}€\n📦 *Commandes :* {count}\n🇫🇷 France : {fr_count}\n🇨🇭 Suisse : {ch_count}\n💵 *Panier moyen :* {total/count:.2f}€\n\n🏆 *Top 5 produits :*\n"
    for i, (product, qty) in enumerate(top_products, 1):
        report += f"{i}. {product} ({qty}x)\n"
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode='Markdown')
        stats["monthly"] = []
        stats["last_monthly_report"] = datetime.now().isoformat()
        save_stats(stats)
        logger.info("✅ Rapport mensuel envoyé")
    except Exception as e:
        logger.error(f"Erreur envoi rapport mensuel: {e}")

async def schedule_reports(context: ContextTypes.DEFAULT_TYPE):
    """Vérifie et envoie les rapports programmés"""
    now = datetime.now()
    stats = load_stats()
    if now.weekday() == 6 and now.hour == 23 and now.minute == 59:
        last_weekly = stats.get("last_weekly_report")
        if not last_weekly or (now - datetime.fromisoformat(last_weekly)).days >= 7:
            await send_weekly_report(context)
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    last_day = (next_month - timedelta(days=1)).day
    if now.day == last_day and now.hour == 23 and now.minute == 59:
        last_monthly = stats.get("last_monthly_report")
        if not last_monthly or (now - datetime.fromisoformat(last_monthly)).days >= 28:
            await send_monthly_report(context)

def tr(user_data, key):
    lang = user_data.get('langue', 'fr')
    t = TRANSLATIONS.get(lang, TRANSLATIONS['fr']).get(key, key)
    t = t.replace("{max}", str(MAX_QUANTITY_PER_PRODUCT))
    t = t.replace("{hours}", get_horaires_text())
    return t

def sanitize_input(text, max_length=300):
    if not text:
        return ""
    return re.sub(r'[<>{}[\]\\`|]', '', text.strip()[:max_length])

def calculate_delivery_fee(delivery_type, distance=0, subtotal=0):
    if delivery_type == "postal":
        return FRAIS_POSTAL
    elif delivery_type == "express":
        # 10€ par kilomètre, arrondi à la dizaine supérieure
        fee = distance * 10
        return math.ceil(fee / 10) * 10
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

# ==================== HANDLERS ====================

@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"👤 /start: {user.first_name} (ID: {user.id})")
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
    logger.info(f"👤 Langue sélectionnée: {lang_code}")
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
    logger.info(f"👤 Navigation: {query.data}")
    
    if query.data == "contact_admin":
        await query.message.edit_text(tr(context.user_data, "contact_message"), parse_mode='Markdown')
        return CONTACT
    
    if not is_within_delivery_hours():
        await query.message.edit_text(tr(context.user_data, "outside_hours"), parse_mode='Markdown')
        return ConversationHandler.END
    
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
    admin_message = f"📞 *MESSAGE* ({user_lang.upper()})\n\n👤 {user.first_name} (@{user.username or 'N/A'})\n🆔 `{user.id}`\n\n💬 {message_text}"
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, parse_mode='Markdown')
        await update.message.reply_text(tr(context.user_data, "contact_sent"), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Contact: {e}")
        await update.message.reply_text("❌ Erreur.")
    return ConversationHandler.END

@error_handler
async def admin_horaires_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /horaires pour gérer les horaires (admin uniquement)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Commande réservée à l'administrateur.")
        return ConversationHandler.END
    
    horaires = load_horaires()
    current = get_horaires_text()
    enabled_text = "✅ Activés" if horaires.get("enabled", True) else "❌ Désactivés"
    
    text = f"⏰ *GESTION DES HORAIRES*\n\n📋 Horaires actuels : {current}\n🔔 Statut : {enabled_text}\n\nEnvoyez les horaires au format :\n`HH:MM-HH:MM`\n\nExemples :\n• `09:00-23:00`\n• `10:30-22:30`\n\nOu envoyez :\n• `off` pour désactiver\n• `on` pour réactiver\n• `cancel` pour annuler"
    
    await update.message.reply_text(text, parse_mode='Markdown')
    return ADMIN_HORAIRES_INPUT

@error_handler
async def admin_horaires_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite l'input des horaires"""
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    text = update.message.text.strip().lower()
    
    if text == "cancel":
        await update.message.reply_text("❌ Modification annulée.")
        return ConversationHandler.END
    
    horaires = load_horaires()
    
    if text == "off":
        horaires["enabled"] = False
        save_horaires(horaires)
        await update.message.reply_text("✅ Horaires désactivés. Le bot accepte les commandes 24h/24.")
        return ConversationHandler.END
    
    if text == "on":
        horaires["enabled"] = True
        save_horaires(horaires)
        current = get_horaires_text()
        await update.message.reply_text(f"✅ Horaires réactivés : {current}")
        return ConversationHandler.END
    
    match = re.match(r'^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$', text)
    if not match:
        await update.message.reply_text("❌ Format invalide. Utilisez : HH:MM-HH:MM")
        return ADMIN_HORAIRES_INPUT
    
    start_h, start_m, end_h, end_m = map(int, match.groups())
    
    if not (0 <= start_h < 24 and 0 <= end_h < 24 and 0 <= start_m < 60 and 0 <= end_m < 60):
        await update.message.reply_text("❌ Heures invalides.")
        return ADMIN_HORAIRES_INPUT
    
    horaires["start_hour"] = start_h
    horaires["start_minute"] = start_m
    horaires["end_hour"] = end_h
    horaires["end_minute"] = end_m
    horaires["enabled"] = True
    
    save_horaires(horaires)
    await update.message.reply_text(f"✅ Horaires mis à jour : {get_horaires_text()}")
    return ConversationHandler.END

@error_handler
async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /stats pour voir les statistiques (admin uniquement)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Commande réservée à l'administrateur.")
        return
    
    stats = load_stats()
    weekly = stats.get("weekly", [])
    monthly = stats.get("monthly", [])
    
    text = "📊 *STATISTIQUES*\n\n"
    
    if weekly:
        total_week = sum(s["amount"] for s in weekly)
        text += f"📅 *Cette semaine :*\n💰 {total_week:.2f}€ ({len(weekly)} commandes)\n\n"
    else:
        text += f"📅 *Cette semaine :* Aucune vente\n\n"
    
    if monthly:
        total_month = sum(s["amount"] for s in monthly)
        text += f"📆 *Ce mois :*\n💰 {total_month:.2f}€ ({len(monthly)} commandes)\n"
    else:
        text += f"📆 *Ce mois :* Aucune vente\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def error_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)

async def main_async():
    logger.info("=" * 60)
    logger.info("🤖 BOT TELEGRAM - VERSION 2.0 ENHANCED")
    logger.info("=" * 60)
    logger.info(f"📱 Token: {TOKEN[:15]}...")
    logger.info(f"👤 Admin: {ADMIN_ID}")
    logger.info(f"⏰ Horaires: {get_horaires_text()}")
    logger.info("=" * 60)
    
    # Créer l'application avec job_queue activé
    from telegram.ext import JobQueue
    application = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )
    logger.info("✅ Application créée")
    
    # S'assurer que le job_queue existe
    if application.job_queue is None:
        logger.warning("⚠️ Job queue non disponible - fonctionnalités programmées désactivées")
    
    await application.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook supprimé")
    
    # Handler de gestion des horaires (admin)
    horaires_handler = ConversationHandler(
        entry_points=[CommandHandler('horaires', admin_horaires_command)],
        states={ADMIN_HORAIRES_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_horaires_input)]},
        fallbacks=[],
        allow_reentry=False,
        name="horaires_conversation"
    )
    
    # Handler principal
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            LANGUE: [CallbackQueryHandler(set_langue, pattern='^lang_')],
            PAYS: [CallbackQueryHandler(menu_navigation, pattern='^(start_order|contact_admin)$')],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_handler)]
        },
        fallbacks=[CommandHandler('start', start_command)],
        allow_reentry=True,
        per_message=False,
        name="main_conversation"
    )
    
    application.add_handler(horaires_handler)
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('stats', admin_stats_command))
    application.add_error_handler(error_callback)
    
    # Job queue pour les tâches programmées (si disponible)
    if application.job_queue is not None:
        # Vérification des suppressions toutes les minutes
        application.job_queue.run_repeating(check_pending_deletions, interval=60, first=10)
        logger.info("✅ Task: Suppression messages (60s)")
        
        # Vérification des rapports toutes les minutes
        application.job_queue.run_repeating(schedule_reports, interval=60, first=10)
        logger.info("✅ Task: Rapports automatiques (60s)")
    else:
        logger.warning("⚠️ Job queue indisponible - suppressions et rapports désactivés")
    
    logger.info("✅ Handlers configurés")
    logger.info("=" * 60)
    logger.info("🚀 EN LIGNE - /start pour commencer")
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
