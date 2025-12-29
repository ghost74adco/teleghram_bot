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
OPENROUTE_API_KEY = os.getenv("OPENROUTE_API_KEY", "").strip()

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

# ==================== CONFIGURATION CALCUL DE DISTANCE ====================

distance_client = None
DISTANCE_METHOD = "simulation"

if OPENROUTE_API_KEY:
    try:
        import openrouteservice
        distance_client = openrouteservice.Client(key=OPENROUTE_API_KEY)
        DISTANCE_METHOD = "openroute"
        logger.info("✅ OpenRouteService - Distance réelle activée")
    except ImportError:
        logger.warning("⚠️ pip install openrouteservice")
    except Exception as e:
        logger.error(f"❌ OpenRouteService: {e}")

if DISTANCE_METHOD == "simulation":
    try:
        from geopy.geocoders import Nominatim
        from geopy.distance import geodesic
        distance_client = Nominatim(user_agent="telegram_bot_v2_2")
        DISTANCE_METHOD = "geopy"
        logger.info("✅ Geopy - Distance approximative")
    except:
        pass

if DISTANCE_METHOD == "simulation":
    logger.warning("⚠️ DISTANCE SIMULÉE")

# ==================== CONFIGURATION MÉDIAS ====================

MEDIA_DIR = Path(__file__).parent / "sampleFolder"

IMAGES_PRODUITS = {}
VIDEOS_PRODUITS = {}

IMAGE_PRIX_FRANCE = MEDIA_DIR / "catalogue.png"
IMAGE_PRIX_SUISSE = MEDIA_DIR / "catalogue.png"

MAX_QUANTITY_PER_PRODUCT = 100
FRAIS_POSTAL = 10

# États de la conversation
LANGUE, PAYS, PRODUIT, PILL_SUBCATEGORY, ROCK_SUBCATEGORY = range(5)
QUANTITE, CART_MENU, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION, CONTACT = range(5, 12)
ADMIN_HORAIRES_INPUT = 12
ADMIN_PRODUCT_MENU = 13
ADMIN_NEW_PRODUCT_NAME = 14
ADMIN_NEW_PRODUCT_CODE = 15
ADMIN_NEW_PRODUCT_CATEGORY = 16
ADMIN_NEW_PRODUCT_PRICE_FR = 17
ADMIN_NEW_PRODUCT_PRICE_CH = 18
ADMIN_CONFIRM_PRODUCT = 19
ADMIN_NEW_PRODUCT_IMAGE = 20
ADMIN_NEW_PRODUCT_VIDEO = 21
ADMIN_MENU_MAIN = 22
ADMIN_MENU_PRODUCTS = 23
ADMIN_MENU_PRICES = 24
ADMIN_MENU_STATS = 25
ADMIN_MENU_USERS = 26
ADMIN_MENU_HORAIRES = 27
ADMIN_MENU_MEDIA = 28
ADMIN_MENU_MAINTENANCE = 29

PILL_SUBCATEGORIES = {}
ROCK_SUBCATEGORIES = {}

# Mapping des codes produits
PRODUCT_CODES = {}

# Prix par défaut
PRIX_FR = {
    "❄️ Coco": 80, 
    "💊 Squid Game": 10, 
    "💊 Punisher": 10, 
    "🫒 Hash": 7, 
    "🍀 Weed": 8,
    "🪨 MDMA": 12,
    "🪨 4MMC": 12
}

PRIX_CH = {
    "❄️ Coco": 100, 
    "💊 Squid Game": 15, 
    "💊 Punisher": 15, 
    "🫒 Hash": 8, 
    "🍀 Weed": 10,
    "🪨 MDMA": 18,
    "🪨 4MMC": 18
}

# Fichiers de configuration
HORAIRES_FILE = Path(__file__).parent / "horaires.json"
STATS_FILE = Path(__file__).parent / "stats.json"
PENDING_MESSAGES_FILE = Path(__file__).parent / "pending_messages.json"
AVAILABLE_PRODUCTS_FILE = Path(__file__).parent / "available_products.json"
PRICES_FILE = Path(__file__).parent / "prices.json"
ARCHIVED_PRODUCTS_FILE = Path(__file__).parent / "archived_products.json"
USERS_FILE = Path(__file__).parent / "users.json"
PRODUCT_REGISTRY_FILE = Path(__file__).parent / "product_registry.json"

TRANSLATIONS = {
    "fr": {
        "welcome": "🌿 *BIENVENUE* 🌿\n\n⚠️ *VERSION 2.2*\n\nConversations en *ÉCHANGE SECRET*.\n\n🙏 *Merci* 💪💚",
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
        "confirm": "✅ Confirmer",
        "cancel": "❌ Annuler",
        "order_confirmed": "✅ *Confirmé !*\n\n📞 Contact sous peu.",
        "order_cancelled": "❌ *Annulé.*",
        "add_more": "➕ Ajouter",
        "proceed": "✅ Valider",
        "invalid_quantity": "❌ Invalide (1-{max}).",
        "cart_title": "🛒 *PANIER :*",
        "start_order": "🛒 Commander",
        "contact_admin": "📞 Contacter",
        "contact_message": "📞 *CONTACT*\n\nÉcrivez votre message.\n\n💬 Message ?",
        "contact_sent": "✅ *Envoyé !*\n\nRéponse sous peu.",
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Suisse",
        "postal": "✉️ Postale",
        "express": "⚡ Express",
        "cash": "💵 Espèces",
        "crypto": "₿ Crypto",
        "total": "💰 *TOTAL :*",
        "delivery_fee": "📦 *Frais :*",
        "subtotal": "💵 *Sous-total :*",
        "back": "🔙 Retour",
        "pirate_card": "🏴‍☠️ Carte du Pirate",
        "choose_country_prices": "🏴‍☠️ *CARTE DU PIRATE*\n\nChoisissez votre pays :",
        "prices_france": "🇫🇷 Prix France",
        "prices_switzerland": "🇨🇭 Prix Suisse",
        "back_to_card": "🔙 Retour carte",
        "main_menu_btn": "🏠 Menu principal",
        "price_list_fr": "🇫🇷 *PRIX FRANCE*\n\n",
        "price_list_ch": "🇨🇭 *PRIX SUISSE*\n\n",
        "new_order": "🔄 Nouvelle commande",
        "address_too_short": "❌ Adresse trop courte",
        "outside_hours": "⏰ Livraisons fermées.\n\nHoraires : {hours}",
        "tuto_menu_title": "📚 *TUTORIEL CLIENT*\n\nGuide d'utilisation du bot.\n\nQue voulez-vous consulter ?",
        "tuto_step1_btn": "1️⃣ Démarrage & Langue",
        "tuto_step2_btn": "2️⃣ Consultation prix",
        "tuto_step3_btn": "3️⃣ Passer commande",
        "tuto_step4_btn": "4️⃣ Choix livraison",
        "tuto_step5_btn": "5️⃣ Paiement & Confirmation",
        "tuto_step6_btn": "6️⃣ Contacter le vendeur",
        "tuto_send_all_btn": "📤 Envoyer tutoriel complet",
        "tuto_back": "🔙 Retour tutoriel",
        "tuto_next": "➡️ Étape suivante",
        "tuto_prev": "⬅️ Étape précédente",
        "tuto_restart": "🔄 Retour au début",
        "tuto_step1_title": "1️⃣ *DÉMARRAGE & LANGUE*",
        "tuto_step1_start": "📱 *Pour commencer :*\n1. Ouvrez Telegram\n2. Cherchez le bot\n3. Cliquez sur *DÉMARRER* ou tapez `/start`",
        "tuto_step1_lang": "🌍 *Choisir sa langue :*\n• 🇫🇷 Français\n• 🇬🇧 English\n• 🇩🇪 Deutsch\n• 🇪🇸 Español\n• 🇮🇹 Italiano",
        "tuto_step1_menu": "✅ *Après sélection :*\nLe menu principal s'affiche avec 3 options :\n• 🛒 Commander\n• 🏴‍☠️ Carte du Pirate (voir les prix)\n• 📞 Contacter",
        "tuto_step2_title": "2️⃣ *CONSULTATION DES PRIX*",
        "tuto_step2_intro": "🏴‍☠️ *Carte du Pirate :*\nPour voir les prix sans commander :",
        "tuto_step2_how": "1. Menu principal → *🏴‍☠️ Carte du Pirate*\n2. Choisir votre pays :\n   • 🇫🇷 Prix France\n   • 🇨🇭 Prix Suisse",
        "tuto_step2_display": "📋 *Affichage :*\n• Liste complète des produits disponibles\n• Prix par gramme ou par unité\n• Frais de livraison postale\n• Information livraison express",
        "tuto_step2_tip": "💡 *Astuce :*\nVous pouvez consulter les prix autant de fois que vous voulez avant de commander.",
        "tuto_step3_title": "3️⃣ *PASSER UNE COMMANDE*",
        "tuto_step3_start": "🛒 *Démarrer la commande :*\n1. Menu principal → *🛒 Commander*",
        "tuto_step3_country": "🌍 *Étape 1 - Choisir le pays :*\n• 🇫🇷 France\n• 🇨🇭 Suisse",
        "tuto_step3_product": "📦 *Étape 2 - Choisir le produit :*\n• ❄️ Coco (poudre)\n• 💊 Pills (Squid Game / Punisher)\n• 🫒 Hash\n• 🍀 Weed\n• 🪨 Crystal (MDMA / 4MMC)",
        "tuto_step3_quantity": "🔢 *Étape 3 - Indiquer la quantité :*\n• Tapez le nombre souhaité (ex: 5)\n• Maximum : 100 unités",
        "tuto_step3_add": "➕ *Ajouter d'autres produits :*\nCliquez sur *➕ Ajouter* pour un autre produit\nOU\nCliquez sur *✅ Valider* pour continuer",
        "tuto_step4_title": "4️⃣ *CHOIX DE LIVRAISON*",
        "tuto_step4_address": "📍 *Adresse de livraison :*\n• Tapez votre adresse complète\n• Format : Rue, Code postal, Ville\n• Minimum 15 caractères\n• Exemple : _123 Rue de Paris, 75001 Paris_",
        "tuto_step4_type": "📦 *Type de livraison :*",
        "tuto_step4_postal": "✉️ *Livraison Postale :*\n• Délai : 48-72 heures\n• Prix fixe : 10€\n• Discret et sûr",
        "tuto_step4_express": "⚡ *Livraison Express :*\n• Délai : 30 minutes à 2 heures\n• Prix : 10€ par kilomètre\n• Distance calculée automatiquement\n• Livraison en main propre",
        "tuto_step4_hours": "⏰ *Horaires de livraison :*\n• {hours}",
        "tuto_step4_tip": "💡 *Bon à savoir :*\nPour la livraison express, le bot calcule automatiquement la distance depuis votre adresse.",
        "tuto_step5_title": "5️⃣ *PAIEMENT & CONFIRMATION*",
        "tuto_step5_method": "💳 *Méthode de paiement :*",
        "tuto_step5_cash": "💵 *Espèces :*\n• Paiement en main propre\n• Pour livraison express\n• Montant exact apprécié",
        "tuto_step5_crypto": "₿ *Crypto-monnaie :*\n• Bitcoin, Ethereum, etc.\n• Adresse fournie après validation\n• Livraison après confirmation du paiement",
        "tuto_step5_summary": "✅ *Résumé de commande :*\nLe bot affiche :\n• 🛒 Liste des produits et quantités\n• 💵 Sous-total\n• 📦 Frais de livraison\n• 💰 TOTAL\n• 📍 Adresse\n• 📦 Type de livraison\n• 💳 Méthode de paiement",
        "tuto_step5_validate": "🎯 *Validation :*\n• Vérifiez attentivement\n• Cliquez *✅ Confirmer*\n• Ou *❌ Annuler* pour recommencer",
        "tuto_step5_after": "📞 *Après confirmation :*\n• Vous recevez un numéro de commande\n• L'admin est notifié immédiatement\n• Il vous contactera sous peu",
        "tuto_step6_title": "6️⃣ *CONTACTER LE VENDEUR*",
        "tuto_step6_intro": "📞 *Pour poser une question :*",
        "tuto_step6_step1": "1. Menu principal → *📞 Contacter*",
        "tuto_step6_step2": "2. Tapez votre message :\n• Question sur un produit\n• Demande de renseignement\n• Problème avec une commande\n• Information sur la livraison",
        "tuto_step6_step3": "3. Envoyez le message",
        "tuto_step6_confirm": "✅ *Confirmation :*\n• Message envoyé à l'admin\n• Réponse sous peu\n• L'admin vous contactera directement",
        "tuto_step6_tips": "💡 *Conseils :*\n• Soyez clair et précis\n• Indiquez votre numéro de commande si besoin\n• Privilégiez les messages courts",
        "tuto_step6_new": "🔄 *Nouvelle commande :*\nAprès une commande validée, cliquez sur *🔄 Nouvelle commande* pour recommencer.",
        "tuto_sending": "📤 *ENVOI DU TUTORIEL COMPLET*\n\nLe tutoriel complet en 6 parties va être envoyé.\n\nVous pourrez :\n• Le transférer à vos clients\n• L'épingler dans un canal\n• Le partager par message\n\n⏳ Envoi en cours...",
        "tuto_sent": "✅ *TUTORIEL ENVOYÉ*\n\nLes 6 parties du tutoriel ont été envoyées avec succès.\n\nVous pouvez maintenant les transférer à vos clients.",
        "tuto_part": "📚 *TUTORIEL BOT - PARTIE {n}/6*",
        "tuto_end": "━━━━━━━━━━━━━━━━━\n✅ Fin du tutoriel\nBonne utilisation du bot ! 🌿",
    },
    "en": {
        "welcome": "🌿 *WELCOME* 🌿\n\n⚠️ *VERSION 2.2*\n\nConversations in *SECRET EXCHANGE*.\n\n🙏 *Thank you* 💪💚",
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
        "confirm": "✅ Confirm",
        "cancel": "❌ Cancel",
        "order_confirmed": "✅ *Confirmed!*\n\n📞 Contact soon.",
        "order_cancelled": "❌ *Cancelled.*",
        "add_more": "➕ Add more",
        "proceed": "✅ Proceed",
        "invalid_quantity": "❌ Invalid (1-{max}).",
        "cart_title": "🛒 *CART:*",
        "start_order": "🛒 Order",
        "contact_admin": "📞 Contact",
        "contact_message": "📞 *CONTACT*\n\nWrite your message.\n\n💬 Message?",
        "contact_sent": "✅ *Sent!*\n\nReply soon.",
        "france": "🇫🇷 France",
        "switzerland": "🇨🇭 Switzerland",
        "postal": "✉️ Postal",
        "express": "⚡ Express",
        "cash": "💵 Cash",
        "crypto": "₿ Crypto",
        "total": "💰 *TOTAL:*",
        "delivery_fee": "📦 *Fee:*",
        "subtotal": "💵 *Subtotal:*",
        "back": "🔙 Back",
        "pirate_card": "🏴‍☠️ Pirate Card",
        "choose_country_prices": "🏴‍☠️ *PIRATE CARD*\n\nChoose your country:",
        "prices_france": "🇫🇷 France Prices",
        "prices_switzerland": "🇨🇭 Switzerland Prices",
        "back_to_card": "🔙 Back to card",
        "main_menu_btn": "🏠 Main menu",
        "price_list_fr": "🇫🇷 *FRANCE PRICES*\n\n",
        "price_list_ch": "🇨🇭 *SWITZERLAND PRICES*\n\n",
        "new_order": "🔄 New order",
        "address_too_short": "❌ Address too short",
        "outside_hours": "⏰ Deliveries closed.\n\nHours: {hours}",
    },
    "de": {
        "welcome": "🌿 *WILLKOMMEN* 🌿\n\n⚠️ *VERSION 2.2*\n\nGespräche im *GEHEIMEN AUSTAUSCH*.\n\n🙏 *Danke* 💪💚",
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
        "confirm": "✅ Bestätigen",
        "cancel": "❌ Abbrechen",
        "order_confirmed": "✅ *Bestätigt!*\n\n📞 Kontakt in Kürze.",
        "order_cancelled": "❌ *Abgebrochen.*",
        "add_more": "➕ Mehr hinzufügen",
        "proceed": "✅ Weiter",
        "invalid_quantity": "❌ Ungültig (1-{max}).",
        "cart_title": "🛒 *WARENKORB:*",
        "start_order": "🛒 Bestellen",
        "contact_admin": "📞 Kontakt",
        "contact_message": "📞 *KONTAKT*\n\nSchreiben Sie Ihre Nachricht.\n\n💬 Nachricht?",
        "contact_sent": "✅ *Gesendet!*\n\nAntwort in Kürze.",
        "france": "🇫🇷 Frankreich",
        "switzerland": "🇨🇭 Schweiz",
        "postal": "✉️ Post",
        "express": "⚡ Express",
        "cash": "💵 Bargeld",
        "crypto": "₿ Krypto",
        "total": "💰 *GESAMT:*",
        "delivery_fee": "📦 *Gebühr:*",
        "subtotal": "💵 *Zwischensumme:*",
        "back": "🔙 Zurück",
        "pirate_card": "🏴‍☠️ Piratenkarte",
        "choose_country_prices": "🏴‍☠️ *PIRATENKARTE*\n\nWählen Sie Ihr Land:",
        "prices_france": "🇫🇷 Preise Frankreich",
        "prices_switzerland": "🇨🇭 Preise Schweiz",
        "back_to_card": "🔙 Zurück zur Karte",
        "main_menu_btn": "🏠 Hauptmenü",
        "price_list_fr": "🇫🇷 *PREISE FRANKREICH*\n\n",
        "price_list_ch": "🇨🇭 *PREISE SCHWEIZ*\n\n",
        "new_order": "🔄 Neue Bestellung",
        "address_too_short": "❌ Adresse zu kurz",
        "outside_hours": "⏰ Lieferungen geschlossen.\n\nÖffnungszeiten: {hours}",
    },
    "es": {
        "welcome": "🌿 *BIENVENIDO* 🌿\n\n⚠️ *VERSIÓN 2.2*\n\nConversaciones en *INTERCAMBIO SECRETO*.\n\n🙏 *Gracias* 💪💚",
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
        "confirm": "✅ Confirmar",
        "cancel": "❌ Cancelar",
        "order_confirmed": "✅ *¡Confirmado!*\n\n📞 Contacto pronto.",
        "order_cancelled": "❌ *Cancelado.*",
        "add_more": "➕ Añadir más",
        "proceed": "✅ Continuar",
        "invalid_quantity": "❌ Inválido (1-{max}).",
        "cart_title": "🛒 *CARRITO:*",
        "start_order": "🛒 Pedir",
        "contact_admin": "📞 Contacto",
        "contact_message": "📞 *CONTACTO*\n\nEscriba su mensaje.\n\n💬 ¿Mensaje?",
        "contact_sent": "✅ *¡Enviado!*\n\nRespuesta pronto.",
        "france": "🇫🇷 Francia",
        "switzerland": "🇨🇭 Suiza",
        "postal": "✉️ Postal",
        "express": "⚡ Express",
        "cash": "💵 Efectivo",
        "crypto": "₿ Cripto",
        "total": "💰 *TOTAL:*",
        "delivery_fee": "📦 *Gastos:*",
        "subtotal": "💵 *Subtotal:*",
        "back": "🔙 Volver",
        "pirate_card": "🏴‍☠️ Carta del Pirata",
        "choose_country_prices": "🏴‍☠️ *CARTA DEL PIRATA*\n\nElija su país:",
        "prices_france": "🇫🇷 Precios Francia",
        "prices_switzerland": "🇨🇭 Precios Suiza",
        "back_to_card": "🔙 Volver a carta",
        "main_menu_btn": "🏠 Menú principal",
        "price_list_fr": "🇪🇸 *PRECIOS FRANCIA*\n\n",
        "price_list_ch": "🇨🇭 *PRECIOS SUIZA*\n\n",
        "new_order": "🔄 Nuevo pedido",
        "address_too_short": "❌ Dirección demasiado corta",
        "outside_hours": "⏰ Entregas cerradas.\n\nHorario: {hours}",
    },
    "it": {
        "welcome": "🌿 *BENVENUTO* 🌿\n\n⚠️ *VERSIONE 2.2*\n\nConversazioni in *SCAMBIO SEGRETO*.\n\n🙏 *Grazie* 💪💚",
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
        "confirm": "✅ Confermare",
        "cancel": "❌ Annullare",
        "order_confirmed": "✅ *Confermato!*\n\n📞 Contatto a breve.",
        "order_cancelled": "❌ *Annullato.*",
        "add_more": "➕ Aggiungere",
        "proceed": "✅ Procedere",
        "invalid_quantity": "❌ Non valido (1-{max}).",
        "cart_title": "🛒 *CARRELLO:*",
        "start_order": "🛒 Ordinare",
        "contact_admin": "📞 Contatto",
        "contact_message": "📞 *CONTATTO*\n\nScriva il suo messaggio.\n\n💬 Messaggio?",
        "contact_sent": "✅ *Inviato!*\n\nRisposta a breve.",
        "france": "🇫🇷 Francia",
        "switzerland": "🇨🇭 Svizzera",
        "postal": "✉️ Postale",
        "express": "⚡ Express",
        "cash": "💵 Contanti",
        "crypto": "₿ Cripto",
        "total": "💰 *TOTALE:*",
        "delivery_fee": "📦 *Spese:*",
        "subtotal": "💵 *Subtotale:*",
        "back": "🔙 Indietro",
        "pirate_card": "🏴‍☠️ Carta del Pirata",
        "choose_country_prices": "🏴‍☠️ *CARTA DEL PIRATA*\n\nScelga il suo paese:",
        "prices_france": "🇫🇷 Prezzi Francia",
        "prices_switzerland": "🇨🇭 Prezzi Svizzera",
        "back_to_card": "🔙 Torna alla carta",
        "main_menu_btn": "🏠 Menu principale",
        "price_list_fr": "🇫🇷 *PREZZI FRANCIA*\n\n",
        "price_list_ch": "🇨🇭 *PREZZI SVIZZERA*\n\n",
        "new_order": "🔄 Nuovo ordine",
        "address_too_short": "❌ Indirizzo troppo corto",
        "outside_hours": "⏰ Consegne chiuse.\n\nOrari: {hours}",
    }
}

def error_handler(func):
    """Décorateur pour gérer les erreurs"""
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
# ==================== SYSTÈME DE PERSISTANCE ====================

def load_product_registry():
    """Charge le registre complet des produits"""
    if PRODUCT_REGISTRY_FILE.exists():
        try:
            with open(PRODUCT_REGISTRY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("products", {})
        except Exception as e:
            logger.error(f"Erreur chargement registre: {e}")
    return {}

def save_product_registry(registry):
    """Sauvegarde le registre des produits"""
    try:
        with open(PRODUCT_REGISTRY_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "products": registry,
                "last_updated": datetime.now().isoformat(),
                "version": "2.2"
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Registre sauvegardé: {len(registry)} produits")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde registre: {e}")
        return False

def create_initial_registry():
    """Crée le registre initial avec les produits de base"""
    return {
        "coco": {"name": "❄️ Coco", "code": "coco", "emoji": "❄️", "category": "powder", "image": "coco.jpg", "video": "coco_demo.mp4", "created_at": datetime.now().isoformat()},
        "squid_game": {"name": "💊 Squid Game", "code": "squid_game", "emoji": "💊", "category": "pill", "image": "squid_game.jpg", "video": "squid_game_demo.mp4", "created_at": datetime.now().isoformat()},
        "punisher": {"name": "💊 Punisher", "code": "punisher", "emoji": "💊", "category": "pill", "image": "punisher.jpg", "video": "punisher_demo.mp4", "created_at": datetime.now().isoformat()},
        "hash": {"name": "🫒 Hash", "code": "hash", "emoji": "🫒", "category": "powder", "image": "hash.jpg", "video": "hash_demo.mp4", "created_at": datetime.now().isoformat()},
        "weed": {"name": "🍀 Weed", "code": "weed", "emoji": "🍀", "category": "powder", "image": "weed.jpg", "video": "weed_demo.mp4", "created_at": datetime.now().isoformat()},
        "mdma": {"name": "🪨 MDMA", "code": "mdma", "emoji": "🪨", "category": "rock", "image": "mdma.jpg", "video": "mdma_demo.mp4", "created_at": datetime.now().isoformat()},
        "fourmmc": {"name": "🪨 4MMC", "code": "fourmmc", "emoji": "🪨", "category": "rock", "image": "fourmmc.jpg", "video": "fourmmc_demo.mp4", "created_at": datetime.now().isoformat()}
    }

def init_product_codes():
    """Initialise tous les dictionnaires produits depuis le registre"""
    global PRODUCT_CODES, PILL_SUBCATEGORIES, ROCK_SUBCATEGORIES, IMAGES_PRODUITS, VIDEOS_PRODUITS
    
    logger.info("🔄 Initialisation des produits depuis le registre...")
    
    registry = load_product_registry()
    
    if not registry:
        logger.info("📦 Création du registre initial...")
        registry = create_initial_registry()
        save_product_registry(registry)
    
    PRODUCT_CODES.clear()
    PILL_SUBCATEGORIES.clear()
    ROCK_SUBCATEGORIES.clear()
    IMAGES_PRODUITS.clear()
    VIDEOS_PRODUITS.clear()
    
    for code, product_data in registry.items():
        name = product_data["name"]
        category = product_data.get("category", "powder")
        
        PRODUCT_CODES[code] = name
        
        if category == "pill":
            PILL_SUBCATEGORIES[code] = name
        elif category == "rock":
            ROCK_SUBCATEGORIES[code] = name
        
        if product_data.get("image"):
            image_path = MEDIA_DIR / product_data["image"]
            IMAGES_PRODUITS[name] = image_path
        
        if product_data.get("video"):
            video_path = MEDIA_DIR / product_data["video"]
            VIDEOS_PRODUITS[name] = video_path
    
    logger.info(f"✅ {len(PRODUCT_CODES)} produits chargés")
    logger.info(f"   • Pills: {len(PILL_SUBCATEGORIES)}")
    logger.info(f"   • Crystal: {len(ROCK_SUBCATEGORIES)}")
    logger.info(f"   • Images: {len(IMAGES_PRODUITS)}")
    logger.info(f"   • Vidéos: {len(VIDEOS_PRODUITS)}")

def add_product_to_registry(code, name, emoji, category, price_fr, price_ch, image_file=None, video_file=None):
    """Ajoute un produit au registre"""
    registry = load_product_registry()
    
    if not registry:
        registry = create_initial_registry()
    
    registry[code] = {
        "name": name,
        "code": code,
        "emoji": emoji,
        "category": category,
        "image": image_file,
        "video": video_file,
        "created_at": datetime.now().isoformat()
    }
    
    success = save_product_registry(registry)
    
    if success:
        PRODUCT_CODES[code] = name
        
        if category == "pill":
            PILL_SUBCATEGORIES[code] = name
        elif category == "rock":
            ROCK_SUBCATEGORIES[code] = name
        
        if image_file:
            IMAGES_PRODUITS[name] = MEDIA_DIR / image_file
        if video_file:
            VIDEOS_PRODUITS[name] = MEDIA_DIR / video_file
        
        logger.info(f"✅ Produit ajouté au registre: {name} ({code})")
    
    return success

def remove_product_from_registry(code):
    """Retire un produit du registre"""
    registry = load_product_registry()
    
    if code in registry:
        product_data = registry[code]
        del registry[code]
        save_product_registry(registry)
        
        name = product_data["name"]
        
        if code in PRODUCT_CODES:
            del PRODUCT_CODES[code]
        
        if code in PILL_SUBCATEGORIES:
            del PILL_SUBCATEGORIES[code]
        
        if code in ROCK_SUBCATEGORIES:
            del ROCK_SUBCATEGORIES[code]
        
        if name in IMAGES_PRODUITS:
            del IMAGES_PRODUITS[name]
        
        if name in VIDEOS_PRODUITS:
            del VIDEOS_PRODUITS[name]
        
        logger.info(f"🗑️ Produit retiré du registre: {name} ({code})")
        return product_data
    
    return None

def get_product_from_registry(code):
    """Récupère les infos d'un produit depuis le registre"""
    registry = load_product_registry()
    return registry.get(code)

def update_product_media_in_registry(code, image_file=None, video_file=None):
    """Met à jour les médias d'un produit dans le registre"""
    registry = load_product_registry()
    
    if code in registry:
        if image_file:
            registry[code]["image"] = image_file
            name = registry[code]["name"]
            IMAGES_PRODUITS[name] = MEDIA_DIR / image_file
        
        if video_file:
            registry[code]["video"] = video_file
            name = registry[code]["name"]
            VIDEOS_PRODUITS[name] = MEDIA_DIR / video_file
        
        save_product_registry(registry)
        logger.info(f"✅ Médias mis à jour pour {code}")
        return True
    
    return False

def load_available_products():
    if AVAILABLE_PRODUCTS_FILE.exists():
        try:
            with open(AVAILABLE_PRODUCTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get("available", list(PRIX_FR.keys())))
        except:
            pass
    return set(PRIX_FR.keys())

def save_available_products(products):
    try:
        with open(AVAILABLE_PRODUCTS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"available": list(products), "updated": datetime.now().isoformat()}, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde produits: {e}")
        return False

def is_product_available(product_name):
    available = load_available_products()
    return product_name in available

def get_available_products():
    return load_available_products()

def load_prices():
    if PRICES_FILE.exists():
        try:
            with open(PRICES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"FR": PRIX_FR.copy(), "CH": PRIX_CH.copy()}

def save_prices(prices):
    try:
        with open(PRICES_FILE, 'w', encoding='utf-8') as f:
            json.dump(prices, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde prix: {e}")
        return False

def get_price(product_name, country):
    prices = load_prices()
    return prices.get(country, {}).get(product_name, 0)

def set_price(product_name, country, new_price):
    prices = load_prices()
    if country not in prices:
        prices[country] = {}
    prices[country][product_name] = new_price
    return save_prices(prices)

def load_archived_products():
    if ARCHIVED_PRODUCTS_FILE.exists():
        try:
            with open(ARCHIVED_PRODUCTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_archived_products(archived):
    with open(ARCHIVED_PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(archived, f, indent=2, ensure_ascii=False)

def add_new_product(name, code, emoji, category, price_fr, price_ch, image_file=None, video_file=None):
    """Ajoute un nouveau produit avec synchronisation COMPLÈTE"""
    
    logger.info(f"🔄 Création produit : {name} ({code})")
    
    success = add_product_to_registry(code, name, emoji, category, price_fr, price_ch, image_file, video_file)
    
    if not success:
        logger.error(f"❌ Échec ajout registre: {name}")
        return False
    
    logger.info(f"✅ Étape 1/5 : Registre OK")
    
    prices = load_prices()
    if "FR" not in prices:
        prices["FR"] = {}
    if "CH" not in prices:
        prices["CH"] = {}
    
    prices["FR"][name] = price_fr
    prices["CH"][name] = price_ch
    save_prices(prices)
    logger.info(f"✅ Étape 2/5 : Prix OK (FR: {price_fr}€, CH: {price_ch}€)")
    
    available = load_available_products()
    if not isinstance(available, set):
        available = set(available) if available else set()
    
    if name not in available:
        available.add(name)
        save_available_products(available)
        logger.info(f"✅ Étape 3/5 : Available_products OK")
    else:
        logger.info(f"⚠️ Étape 3/5 : Déjà dans available_products")
    
    global PRODUCT_CODES, PILL_SUBCATEGORIES, ROCK_SUBCATEGORIES, IMAGES_PRODUITS, VIDEOS_PRODUITS
    
    PRODUCT_CODES[code] = name
    
    if category == "pill":
        PILL_SUBCATEGORIES[code] = name
        logger.info(f"✅ Étape 4/5 : Ajouté aux PILL_SUBCATEGORIES")
    elif category == "rock":
        ROCK_SUBCATEGORIES[code] = name
        logger.info(f"✅ Étape 4/5 : Ajouté aux ROCK_SUBCATEGORIES")
    else:
        logger.info(f"✅ Étape 4/5 : Mémoire mise à jour (catégorie: {category})")
    
    if image_file:
        IMAGES_PRODUITS[name] = MEDIA_DIR / image_file
    if video_file:
        VIDEOS_PRODUITS[name] = MEDIA_DIR / video_file
    
    verification_ok = True
    
    registry = load_product_registry()
    if code not in registry:
        logger.error(f"❌ Vérification registre ÉCHOUÉE")
        verification_ok = False
    
    available_check = get_available_products()
    if name not in available_check:
        logger.error(f"❌ Vérification available ÉCHOUÉE")
        verification_ok = False
    
    prices_check = load_prices()
    if name not in prices_check.get("FR", {}) or name not in prices_check.get("CH", {}):
        logger.error(f"❌ Vérification prix ÉCHOUÉE")
        verification_ok = False
    
    if code not in PRODUCT_CODES:
        logger.error(f"❌ Vérification mémoire ÉCHOUÉE")
        verification_ok = False
    
    if verification_ok:
        logger.info(f"✅ Étape 5/5 : Vérification complète OK")
        logger.info(f"🎉 Produit créé avec succès : {name} ({code})")
        logger.info(f"   └─ Visible dans /products : OUI")
        logger.info(f"   └─ Visible dans Carte : OUI")
        logger.info(f"   └─ Visible dans menu client : OUI")
        return True
    else:
        logger.error(f"❌ Échec vérification finale pour {name}")
        return False

def repair_product_visibility(code):
    """Répare un produit invisible avec diagnostic complet"""
    logger.info(f"🔧 ===== RÉPARATION PRODUIT : {code} =====")
    
    registry = load_product_registry()
    
    if code not in registry:
        logger.error(f"❌ Produit non trouvé dans le registre: {code}")
        logger.info(f"💡 Produits dans le registre : {list(registry.keys())}")
        return False
    
    product_data = registry[code]
    name = product_data["name"]
    category = product_data.get("category", "powder")
    
    logger.info(f"✅ 1/5 : Produit trouvé dans registre")
    logger.info(f"   └─ Nom : {name}")
    logger.info(f"   └─ Catégorie : {category}")
    
    available = load_available_products()
    if not isinstance(available, set):
        available = set(available) if available else set()
    
    was_missing = name not in available
    
    if was_missing:
        available.add(name)
        save_available_products(available)
        logger.info(f"✅ 2/5 : Ajouté à available_products")
    else:
        logger.info(f"⚠️ 2/5 : Déjà dans available_products")
    
    prices = load_prices()
    
    if "FR" not in prices:
        prices["FR"] = {}
    if "CH" not in prices:
        prices["CH"] = {}
    
    prix_manquants = False
    
    if name not in prices["FR"]:
        prices["FR"][name] = 50
        prix_manquants = True
        logger.warning(f"⚠️ 3/5 : Prix FR ajouté (défaut 50€)")
    else:
        logger.info(f"✅ 3/5 : Prix FR existe ({prices['FR'][name]}€)")
    
    if name not in prices["CH"]:
        prices["CH"][name] = 70
        prix_manquants = True
        logger.warning(f"⚠️ 3/5 : Prix CH ajouté (défaut 70€)")
    else:
        logger.info(f"✅ 3/5 : Prix CH existe ({prices['CH'][name]}€)")
    
    if prix_manquants:
        save_prices(prices)
    
    global PRODUCT_CODES, PILL_SUBCATEGORIES, ROCK_SUBCATEGORIES, IMAGES_PRODUITS, VIDEOS_PRODUITS
    
    memoire_mise_a_jour = False
    
    if code not in PRODUCT_CODES:
        PRODUCT_CODES[code] = name
        memoire_mise_a_jour = True
        logger.info(f"✅ 4/5 : Ajouté à PRODUCT_CODES")
    else:
        logger.info(f"⚠️ 4/5 : Déjà dans PRODUCT_CODES")
    
    if category == "pill":
        if code not in PILL_SUBCATEGORIES:
            PILL_SUBCATEGORIES[code] = name
            memoire_mise_a_jour = True
            logger.info(f"✅ 4/5 : Ajouté aux PILL_SUBCATEGORIES")
        else:
            logger.info(f"⚠️ 4/5 : Déjà dans PILL_SUBCATEGORIES")
    elif category == "rock":
        if code not in ROCK_SUBCATEGORIES:
            ROCK_SUBCATEGORIES[code] = name
            memoire_mise_a_jour = True
            logger.info(f"✅ 4/5 : Ajouté aux ROCK_SUBCATEGORIES")
        else:
            logger.info(f"⚠️ 4/5 : Déjà dans ROCK_SUBCATEGORIES")
    
    if product_data.get("image"):
        IMAGES_PRODUITS[name] = MEDIA_DIR / product_data["image"]
    if product_data.get("video"):
        VIDEOS_PRODUITS[name] = MEDIA_DIR / product_data["video"]
    
    logger.info(f"🔍 5/5 : Vérification finale...")
    
    verification = {
        "registre": code in load_product_registry(),
        "available": name in get_available_products(),
        "prix_fr": name in load_prices().get("FR", {}),
        "prix_ch": name in load_prices().get("CH", {}),
        "memoire_code": code in PRODUCT_CODES,
        "memoire_category": (
            code in PILL_SUBCATEGORIES if category == "pill" 
            else code in ROCK_SUBCATEGORIES if category == "rock" 
            else True
        )
    }
    
    tous_ok = all(verification.values())
    
    logger.info(f"")
    logger.info(f"📊 RÉSULTAT RÉPARATION :")
    logger.info(f"   ✅ Registre : {verification['registre']}")
    logger.info(f"   ✅ Available : {verification['available']}")
    logger.info(f"   ✅ Prix FR : {verification['prix_fr']} ({prices['FR'].get(name, 0)}€)")
    logger.info(f"   ✅ Prix CH : {verification['prix_ch']} ({prices['CH'].get(name, 0)}€)")
    logger.info(f"   ✅ Mémoire code : {verification['memoire_code']}")
    logger.info(f"   ✅ Mémoire catégorie : {verification['memoire_category']}")
    logger.info(f"")
    
    if tous_ok:
        logger.info(f"🎉 RÉPARATION RÉUSSIE pour {name}")
        logger.info(f"   └─ Visible dans /products : OUI")
        logger.info(f"   └─ Visible dans Carte du Pirate : OUI")
        logger.info(f"   └─ Visible dans menu client : OUI")
    else:
        logger.error(f"❌ RÉPARATION INCOMPLÈTE pour {name}")
        problemes = [k for k, v in verification.items() if not v]
        logger.error(f"   └─ Problèmes restants : {problemes}")
    
    return tous_ok

def archive_product(product_name):
    """Archive un produit"""
    
    product_code = None
    for code, name in PRODUCT_CODES.items():
        if name == product_name:
            product_code = code
            break
    
    if not product_code:
        logger.error(f"❌ Code non trouvé pour {product_name}")
        return False
    
    product_data = get_product_from_registry(product_code)
    
    if not product_data:
        logger.error(f"❌ Produit non trouvé dans le registre: {product_name}")
        return False
    
    prices = load_prices()
    
    archived = load_archived_products()
    archived[product_name] = {
        "name": product_name,
        "code": product_code,
        "emoji": product_data.get("emoji", product_name.split()[0] if product_name else ""),
        "category": product_data.get("category", "powder"),
        "price_fr": prices["FR"].get(product_name, 0),
        "price_ch": prices["CH"].get(product_name, 0),
        "image": product_data.get("image"),
        "video": product_data.get("video"),
        "archived_at": datetime.now().isoformat()
    }
    save_archived_products(archived)
    
    remove_product_from_registry(product_code)
    
    available = load_available_products()
    if product_name in available:
        available.remove(product_name)
    save_available_products(available)
    
    if product_name in prices.get("FR", {}):
        del prices["FR"][product_name]
    if product_name in prices.get("CH", {}):
        del prices["CH"][product_name]
    save_prices(prices)
    
    logger.info(f"📦 Produit archivé: {product_name}")
    return True

def restore_product(product_name):
    """Restaure un produit archivé"""
    archived = load_archived_products()
    
    if product_name not in archived:
        logger.error(f"❌ Produit non trouvé dans les archives: {product_name}")
        return False
    
    info = archived[product_name]
    
    success = add_new_product(
        name=info["name"],
        code=info["code"],
        emoji=info.get("emoji", info["name"].split()[0] if info["name"] else ""),
        category=info["category"],
        price_fr=info["price_fr"],
        price_ch=info["price_ch"],
        image_file=info.get("image"),
        video_file=info.get("video")
    )
    
    if success:
        del archived[product_name]
        save_archived_products(archived)
        logger.info(f"♻️ Produit restauré: {product_name}")
    
    return success

def load_users():
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def is_new_user(user_id):
    users = load_users()
    return str(user_id) not in users

def add_user(user_id, user_data):
    users = load_users()
    users[str(user_id)] = {
        "first_seen": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
        "username": user_data.get("username"),
        "first_name": user_data.get("first_name"),
        "last_name": user_data.get("last_name"),
        "visit_count": 1
    }
    save_users(users)
    return True

def update_user_visit(user_id):
    users = load_users()
    if str(user_id) in users:
        users[str(user_id)]["last_seen"] = datetime.now().isoformat()
        users[str(user_id)]["visit_count"] = users[str(user_id)].get("visit_count", 0) + 1
        save_users(users)

async def notify_admin_new_user(context, user_id, user_data):
    username = user_data.get("username", "N/A")
    first_name = user_data.get("first_name", "N/A")
    last_name = user_data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()
    notification = f"""🆕 *NOUVELLE CONNEXION*

👤 *Utilisateur :*
- Nom : {full_name}
- Username : @{username if username != 'N/A' else 'Non défini'}
- ID : `{user_id}`

📅 *Date :* {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

💬 _L'utilisateur vient de démarrer le bot_
"""
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=notification, parse_mode='Markdown')
        logger.info(f"✅ Admin notifié - Nouveau user: {user_id}")
    except Exception as e:
        logger.error(f"❌ Erreur notification admin: {e}")

def get_formatted_price_list(country_code):
    """Génère la liste formatée des prix - VERSION CORRIGÉE SANS DOUBLONS"""
    prices = load_prices()
    country = "FR" if country_code == "fr" else "CH"
    country_prices = prices.get(country, PRIX_FR if country == "FR" else PRIX_CH)
    
    available = get_available_products()
    
    if not available:
        return "_Aucun produit disponible_"
    
    text = ""
    
    # Afficher TOUS les produits disponibles, triés par ordre alphabétique
    for product_name in sorted(available):
        price = country_prices.get(product_name, 0)
        text += f"{product_name} : {price}€/g\n"
    
    # Informations de livraison
    text += f"\n📦 *Livraison* :\n"
    text += f"  • Postale (48-72h) : 10€\n"
    text += f"  • Express (30min+) : 10€/km"
    
    return text

def load_horaires():
    if HORAIRES_FILE.exists():
        try:
            with open(HORAIRES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"enabled": True, "start_hour": 9, "start_minute": 0, "end_hour": 23, "end_minute": 0}

def save_horaires(horaires):
    try:
        with open(HORAIRES_FILE, 'w', encoding='utf-8') as f:
            json.dump(horaires, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde horaires: {e}")
        return False

def is_within_delivery_hours(user_id=None):
    if user_id and user_id == ADMIN_ID:
        return True
    horaires = load_horaires()
    if not horaires.get("enabled", True):
        return True
    now = datetime.now().time()
    start = time(horaires["start_hour"], horaires["start_minute"])
    end = time(horaires["end_hour"], horaires["end_minute"])
    return start <= now <= end

def get_horaires_text():
    horaires = load_horaires()
    if not horaires.get("enabled", True):
        return "24h/24 (toujours ouvert)"
    return f"{horaires['start_hour']:02d}:{horaires['start_minute']:02d} - {horaires['end_hour']:02d}:{horaires['end_minute']:02d}"

def load_pending_messages():
    if PENDING_MESSAGES_FILE.exists():
        try:
            with open(PENDING_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []

def save_pending_messages(messages):
    try:
        with open(PENDING_MESSAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde messages: {e}")
        return False

def add_pending_message(chat_id, message_id, delete_at):
    messages = load_pending_messages()
    messages.append({"chat_id": chat_id, "message_id": message_id, "delete_at": delete_at.isoformat()})
    save_pending_messages(messages)

async def check_pending_deletions(context: ContextTypes.DEFAULT_TYPE):
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
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"weekly": [], "monthly": [], "last_weekly_report": None, "last_monthly_report": None}

def save_stats(stats):
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde stats: {e}")
        return False

def add_sale(amount, country, products, subtotal=0, delivery_fee=0):
    stats = load_stats()
    sale_data = {"date": datetime.now().isoformat(), "amount": amount, "subtotal": subtotal, "delivery_fee": delivery_fee, "country": country, "products": products}
    stats["weekly"].append(sale_data)
    stats["monthly"].append(sale_data)
    save_stats(stats)

async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    stats = load_stats()
    weekly_sales = stats.get("weekly", [])
    if not weekly_sales:
        return
    
    total = sum(sale["amount"] for sale in weekly_sales)
    total_subtotal = sum(sale.get("subtotal", sale["amount"]) for sale in weekly_sales)
    total_delivery_fees = sum(sale.get("delivery_fee", 0) for sale in weekly_sales)
    count = len(weekly_sales)
    fr_count = sum(1 for sale in weekly_sales if sale.get("country") == "FR")
    ch_count = sum(1 for sale in weekly_sales if sale.get("country") == "CH")
    
    report = f"📊 *RAPPORT HEBDOMADAIRE*\n\n📅 Semaine du {datetime.now().strftime('%d/%m/%Y')}\n\n💰 *CA TOTAL :* {total:.2f}€\n🛍️ *Ventes :* {total_subtotal:.2f}€\n📦 *Frais :* {total_delivery_fees:.2f}€\n\n📦 *Commandes :* {count}\n🇫🇷 France : {fr_count}\n🇨🇭 Suisse : {ch_count}\n💵 *Panier moyen :* {total/count:.2f}€\n"
    
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode='Markdown')
        stats["weekly"] = []
        stats["last_weekly_report"] = datetime.now().isoformat()
        save_stats(stats)
        logger.info("✅ Rapport hebdomadaire envoyé")
    except Exception as e:
        logger.error(f"Erreur envoi rapport hebdo: {e}")

async def send_monthly_report(context: ContextTypes.DEFAULT_TYPE):
    stats = load_stats()
    monthly_sales = stats.get("monthly", [])
    if not monthly_sales:
        return
    
    total = sum(sale["amount"] for sale in monthly_sales)
    total_subtotal = sum(sale.get("subtotal", sale["amount"]) for sale in monthly_sales)
    total_delivery_fees = sum(sale.get("delivery_fee", 0) for sale in monthly_sales)
    count = len(monthly_sales)
    fr_count = sum(1 for sale in monthly_sales if sale.get("country") == "FR")
    ch_count = sum(1 for sale in monthly_sales if sale.get("country") == "CH")
    
    product_count = defaultdict(int)
    for sale in monthly_sales:
        for product in sale.get("products", "").split(";"):
            if product.strip():
                product_count[product.strip()] += 1
    top_products = sorted(product_count.items(), key=lambda x: x[1], reverse=True)[:5]
    
    report = f"📊 *RAPPORT MENSUEL*\n\n📅 Mois de {datetime.now().strftime('%B %Y')}\n\n💰 *CA TOTAL :* {total:.2f}€\n🛍️ *Ventes :* {total_subtotal:.2f}€\n📦 *Frais :* {total_delivery_fees:.2f}€\n\n📦 *Commandes :* {count}\n🇫🇷 France : {fr_count}\n🇨🇭 Suisse : {ch_count}\n💵 *Panier moyen :* {total/count:.2f}€\n\n🏆 *Top 5 :*\n"
    
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
        distance_arrondie = math.ceil(distance)
        frais_brut = distance_arrondie * 10
        frais_final = math.ceil(frais_brut / 10) * 10
        return frais_final
    return 0

def calculate_distance_openroute(origin, destination):
    try:
        geocode_origin = distance_client.pelias_search(text=origin)
        geocode_dest = distance_client.pelias_search(text=destination)
        
        if not geocode_origin["features"] or not geocode_dest["features"]:
            raise Exception("Adresse non trouvée")
        
        coords_origin = geocode_origin["features"][0]["geometry"]["coordinates"]
        coords_dest = geocode_dest["features"][0]["geometry"]["coordinates"]
        
        route = distance_client.directions(coordinates=[coords_origin, coords_dest], profile="driving-car", format="geojson")
        
        distance_m = route["features"][0]["properties"]["segments"][0]["distance"]
        distance_km = math.ceil(distance_m / 1000)
        logger.info(f"📍 Distance: {distance_km} km (OpenRouteService)")
        return distance_km
    except Exception as e:
        logger.error(f"❌ OpenRouteService: {e}")
        return None

def calculate_distance_geopy(origin, destination):
    try:
        loc_origin = distance_client.geocode(origin)
        loc_dest = distance_client.geocode(destination)
        
        if not loc_origin or not loc_dest:
            raise Exception("Adresse non trouvée")
        
        coords_origin = (loc_origin.latitude, loc_origin.longitude)
        coords_dest = (loc_dest.latitude, loc_dest.longitude)
        
        distance_km = geodesic(coords_origin, coords_dest).kilometers * 1.3
        distance_km = math.ceil(distance_km)
        logger.info(f"📍 Distance: {distance_km} km (Geopy approximatif)")
        return distance_km
    except Exception as e:
        logger.error(f"❌ Geopy: {e}")
        return None

def calculate_distance_simulation(address):
    import hashlib
    hash_val = int(hashlib.md5(address.encode()).hexdigest()[:8], 16)
    distance = (hash_val % 50) + 5
    logger.info(f"📍 Distance: {distance} km (simulée)")
    return distance

def calculate_distance_simple(address):
    distance = None
    
    if DISTANCE_METHOD == "openroute":
        distance = calculate_distance_openroute(ADMIN_ADDRESS, address)
    elif DISTANCE_METHOD == "geopy":
        distance = calculate_distance_geopy(ADMIN_ADDRESS, address)
    
    if distance is None:
        logger.warning("⚠️ Fallback sur simulation")
        distance = calculate_distance_simulation(address)
    
    return distance

def calculate_total(cart, country, delivery_type=None, distance=0):
    prices = load_prices()
    prix_table = prices.get(country, PRIX_FR if country == "FR" else PRIX_CH)
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

async def send_product_media(context, chat_id, product_name, caption):
    product_video_path = VIDEOS_PRODUITS.get(product_name)
    product_image_path = IMAGES_PRODUITS.get(product_name)
    
    if product_video_path and product_video_path.exists():
        try:
            with open(product_video_path, 'rb') as video:
                await context.bot.send_video(chat_id=chat_id, video=video, caption=caption, parse_mode='Markdown', supports_streaming=True)
            logger.info(f"✅ Vidéo envoyée: {product_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur vidéo {product_name}: {e}")
    
    if product_image_path and product_image_path.exists():
        try:
            with open(product_image_path, 'rb') as photo:
                await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, parse_mode='Markdown')
            logger.info(f"✅ Image envoyée: {product_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur image {product_name}: {e}")
    
    logger.warning(f"⚠️ Aucun média pour {product_name}")
    await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode='Markdown')
    return False
    # ==================== HANDLERS PRINCIPAUX ====================

@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    is_admin = user_id == ADMIN_ID
    
    is_new = is_new_user(user_id)
    if is_new:
        user_data_dict = {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
        add_user(user_id, user_data_dict)
        asyncio.create_task(notify_admin_new_user(context, user_id, user_data_dict))
        logger.info(f"🆕 Nouvel utilisateur: {user_id} (@{user.username})")
    else:
        update_user_visit(user_id)
        logger.info(f"🔄 Utilisateur connu: {user_id}")
    
    logger.info(f"👤 /start: {user.first_name} (ID: {user.id}){' 🔑 ADMIN' if is_admin else ''}")
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
    user_id = update.effective_user.id
    
    logger.info(f"👤 Langue: {lang_code} (User: {user_id})")
    
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    if user_id == ADMIN_ID:
        text += "\n\n🔑 *MODE ADMINISTRATEUR*\n✅ Accès illimité 24h/24"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def voir_carte(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    query = update.callback_query
    await query.answer()
    
    if query.data == "prix_france":
        text = tr(context.user_data, "price_list_fr") + get_formatted_price_list("fr")
        image_path = IMAGE_PRIX_FRANCE
    else:
        text = tr(context.user_data, "price_list_ch") + get_formatted_price_list("ch")
        image_path = IMAGE_PRIX_SUISSE
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "back_to_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")]
    ]
    
    if image_path.exists():
        try:
            await query.message.delete()
            with open(image_path, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo,
                    caption=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Erreur envoi image: {e}")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    else:
        logger.warning(f"⚠️ Image non trouvée : {image_path}")
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    if user_id == ADMIN_ID:
        text += "\n\n🔑 *MODE ADMINISTRATEUR*\n✅ Accès illimité 24h/24"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Erreur edit_text: {e}")
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    return PAYS

@error_handler
async def menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"👤 Nav: {query.data}")
    
    if query.data == "contact_admin":
        await query.message.edit_text(tr(context.user_data, "contact_message"), parse_mode='Markdown')
        return CONTACT
    
    user_id = update.effective_user.id
    
    if not is_within_delivery_hours(user_id):
        if user_id == ADMIN_ID:
            hours_msg = f"\n\n⚠️ *MODE ADMIN* - Horaires fermés pour les clients\nHoraires : {get_horaires_text()}"
        else:
            await query.message.edit_text(tr(context.user_data, "outside_hours"), parse_mode='Markdown')
            return ConversationHandler.END
    else:
        hours_msg = ""
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
        [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")],
        [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main_menu")]
    ]
    
    message_text = tr(context.user_data, "choose_country") + hours_msg
    await query.message.edit_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['pays'] = query.data.replace("country_", "")
    context.user_data['cart'] = []
    logger.info(f"👤 Pays: {context.user_data['pays']}")
    
    available = get_available_products()
    keyboard = []
    
    # Groupes pour Pills et Crystal
    has_pills = False
    has_crystals = False
    
    # Parcourir tous les produits disponibles
    for product_name in sorted(available):
        # Trouver le code du produit
        code = None
        for c, name in PRODUCT_CODES.items():
            if name == product_name:
                code = c
                break
        
        if not code:
            continue
        
        # Vérifier la catégorie
        if product_name in PILL_SUBCATEGORIES.values():
            # C'est une pill
            has_pills = True
        elif product_name in ROCK_SUBCATEGORIES.values():
            # C'est un crystal
            has_crystals = True
        else:
            # Produit direct (Coco, Hash, Weed, K, etc.)
            emoji = product_name.split()[0] if product_name else ""
            keyboard.append([InlineKeyboardButton(product_name, callback_data=f"product_{code}")])
    
    # Ajouter Pills si disponibles
    if has_pills:
        keyboard.insert(0, [InlineKeyboardButton("💊 Pills", callback_data="product_pill")])
    
    # Ajouter Crystal si disponibles
    if has_crystals:
        keyboard.append([InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")])
    
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_country_choice")])
    keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
    
    await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PRODUIT

@error_handler
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_code = query.data.replace("product_", "")
    available = get_available_products()
    
    if product_code == "pill":
        keyboard = []
        # Chercher tous les produits de type "pill" dans available
        for name in available:
            if name in PILL_SUBCATEGORIES.values():
                # Trouver le code correspondant
                code = [k for k, v in PILL_SUBCATEGORIES.items() if v == name][0]
                keyboard.append([InlineKeyboardButton(name, callback_data=f"pill_{code}")])
        
        if not keyboard:
            await query.answer("❌ Aucune pilule disponible", show_alert=True)
            return PRODUIT
        
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_products")])
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
        
        await query.message.edit_text(tr(context.user_data, "choose_pill_type"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PILL_SUBCATEGORY
    
    elif product_code == "rock":
        keyboard = []
        # Chercher tous les produits de type "rock" dans available
        for name in available:
            if name in ROCK_SUBCATEGORIES.values():
                # Trouver le code correspondant
                code = [k for k, v in ROCK_SUBCATEGORIES.items() if v == name][0]
                keyboard.append([InlineKeyboardButton(name, callback_data=f"rock_{code}")])
        
        if not keyboard:
            await query.answer("❌ Aucun crystal disponible", show_alert=True)
            return PRODUIT
        
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_products")])
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
        
        await query.message.edit_text(tr(context.user_data, "choose_rock_type"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return ROCK_SUBCATEGORY
    
    # Produits directs - chercher par code
    product_name = PRODUCT_CODES.get(product_code)
    
    if not product_name:
        await query.answer("❌ Produit non trouvé", show_alert=True)
        return PRODUIT
    
    if not is_product_available(product_name):
        await query.answer("❌ Produit indisponible", show_alert=True)
        return PRODUIT
    
    context.user_data['current_product'] = product_name
    
    text = f"✅ {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}"
    await query.message.delete()
    await send_product_media(context, query.message.chat_id, context.user_data['current_product'], text)
    
    return QUANTITE

@error_handler
async def choix_pill_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_name = PILL_SUBCATEGORIES.get(query.data.replace("pill_", ""), "💊")
    
    if not is_product_available(product_name):
        await query.answer("❌ Produit indisponible", show_alert=True)
        return PILL_SUBCATEGORY
    
    context.user_data['current_product'] = product_name
    
    text = f"✅ {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}"
    await query.message.delete()
    await send_product_media(context, query.message.chat_id, context.user_data['current_product'], text)
    
    return QUANTITE

@error_handler
async def choix_rock_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_name = ROCK_SUBCATEGORIES.get(query.data.replace("rock_", ""), "🪨")
    
    if not is_product_available(product_name):
        await query.answer("❌ Produit indisponible", show_alert=True)
        return ROCK_SUBCATEGORY
    
    context.user_data['current_product'] = product_name
    
    text = f"✅ {context.user_data['current_product']}\n\n{tr(context.user_data, 'enter_quantity')}"
    await query.message.delete()
    await send_product_media(context, query.message.chat_id, context.user_data['current_product'], text)
    
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
        available = get_available_products()
        keyboard = []
        
        # Groupes pour Pills et Crystal
        has_pills = False
        has_crystals = False
        
        # Parcourir tous les produits disponibles
        for product_name in sorted(available):
            # Trouver le code du produit
            code = None
            for c, name in PRODUCT_CODES.items():
                if name == product_name:
                    code = c
                    break
            
            if not code:
                continue
            
            # Vérifier la catégorie
            if product_name in PILL_SUBCATEGORIES.values():
                has_pills = True
            elif product_name in ROCK_SUBCATEGORIES.values():
                has_crystals = True
            else:
                # Produit direct
                keyboard.append([InlineKeyboardButton(product_name, callback_data=f"product_{code}")])
        
        # Ajouter Pills si disponibles
        if has_pills:
            keyboard.insert(0, [InlineKeyboardButton("💊 Pills", callback_data="product_pill")])
        
        # Ajouter Crystal si disponibles
        if has_crystals:
            keyboard.append([InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")])
        
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
        
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
        
        if DISTANCE_METHOD == "openroute":
            distance_text += "\n📍 _Distance routière réelle_"
        elif DISTANCE_METHOD == "geopy":
            distance_text += "\n📏 _Distance approximative_"
        else:
            distance_text += "\n⚠️ _Distance estimée_"
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
        add_sale(amount=total, country=context.user_data['pays'], products=order_data['products'], subtotal=subtotal, delivery_fee=delivery_fee)
        
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
    
    user_id = update.effective_user.id
    text = tr(context.user_data, "welcome") + tr(context.user_data, "main_menu")
    
    if user_id == ADMIN_ID:
        text += "\n\n🔑 *MODE ADMINISTRATEUR*\n✅ Accès illimité 24h/24"
    
    keyboard = [
        [InlineKeyboardButton(tr(context.user_data, "start_order"), callback_data="start_order")],
        [InlineKeyboardButton(tr(context.user_data, "pirate_card"), callback_data="voir_carte")],
        [InlineKeyboardButton(tr(context.user_data, "contact_admin"), callback_data="contact_admin")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return PAYS

@error_handler
async def back_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_country_choice":
        keyboard = [
            [InlineKeyboardButton(tr(context.user_data, "france"), callback_data="country_FR")],
            [InlineKeyboardButton(tr(context.user_data, "switzerland"), callback_data="country_CH")],
            [InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_main_menu")]
        ]
        await query.message.edit_text(tr(context.user_data, "choose_country"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PAYS
    
    elif query.data == "back_to_products":
        available = get_available_products()
        keyboard = []
        
        has_pills = False
        has_crystals = False
        
        for product_name in sorted(available):
            code = None
            for c, name in PRODUCT_CODES.items():
                if name == product_name:
                    code = c
                    break
            
            if not code:
                continue
            
            if product_name in PILL_SUBCATEGORIES.values():
                has_pills = True
            elif product_name in ROCK_SUBCATEGORIES.values():
                has_crystals = True
            else:
                keyboard.append([InlineKeyboardButton(product_name, callback_data=f"product_{code}")])
        
        if has_pills:
            keyboard.insert(0, [InlineKeyboardButton("💊 Pills", callback_data="product_pill")])
        
        if has_crystals:
            keyboard.append([InlineKeyboardButton("🪨 Crystal", callback_data="product_rock")])
        
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "back"), callback_data="back_to_country_choice")])
        keyboard.append([InlineKeyboardButton(tr(context.user_data, "main_menu_btn"), callback_data="back_to_main_menu")])
        
        await query.message.edit_text(tr(context.user_data, "choose_product"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return PRODUIT

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
        client_msg = await context.bot.send_message(chat_id=client_id, text=f"✅ *Validée !*\n\n📋 `{order_id}`\n\n💚", parse_mode='Markdown')
        delete_time = datetime.now() + timedelta(minutes=30)
        add_pending_message(ADMIN_ID, query.message.message_id, delete_time)
        add_pending_message(client_id, client_msg.message_id, delete_time)
        logger.info(f"✅ Messages programmés suppression: {delete_time.strftime('%H:%M:%S')}")
    except Exception as e:
        logger.error(f"Validation: {e}")
    await query.answer("✅ Validé! (suppression 30min)", show_alert=True)

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
    # ==================== COMMANDES ADMIN ====================

@error_handler
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /admin - Menu principal admin"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin uniquement.")
        return ConversationHandler.END
    
    text = "🎛️ *PANNEAU ADMIN*\n\nChoisissez une section :"
    
    keyboard = [
        [
            InlineKeyboardButton("📦 Produits", callback_data="admin_menu_products"),
            InlineKeyboardButton("💰 Prix", callback_data="admin_menu_prices")
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_menu_stats"),
            InlineKeyboardButton("👥 Users", callback_data="admin_menu_users")
        ],
        [
            InlineKeyboardButton("⏰ Horaires", callback_data="admin_menu_horaires"),
            InlineKeyboardButton("❌ Fermer", callback_data="admin_close")
        ]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_MENU_MAIN

@error_handler
async def admin_menu_products_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sous-menu produits"""
    query = update.callback_query
    await query.answer()
    
    available = get_available_products()
    archived = load_archived_products()
    
    text = f"📦 *GESTION PRODUITS*\n\n✅ Disponibles : {len(available)}\n📦 Archivés : {len(archived)}\n\nQue faire ?"
    
    keyboard = [
        [InlineKeyboardButton("➕ Créer", callback_data="admin_create_product")],
        [InlineKeyboardButton("🗑️ Archiver", callback_data="admin_archive_product")],
        [InlineKeyboardButton("♻️ Restaurer", callback_data="admin_restore_product")],
        [InlineKeyboardButton("🔙 Retour", callback_data="admin_back_main")]
    ]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_MENU_MAIN

@error_handler
async def admin_menu_prices_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sous-menu prix"""
    query = update.callback_query
    await query.answer()
    
    prices = load_prices()
    
    text = "💰 *GESTION PRIX*\n\n🇫🇷 *France :*\n"
    for product in sorted(get_available_products()):
        price_fr = prices.get("FR", {}).get(product, 0)
        text += f"  • {product} : {price_fr}€\n"
    
    text += "\n🇨🇭 *Suisse :*\n"
    for product in sorted(get_available_products()):
        price_ch = prices.get("CH", {}).get(product, 0)
        text += f"  • {product} : {price_ch}€\n"
    
    text += "\n💡 Modifier : `/setprice <code> <pays> <prix>`"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_back_main")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_MENU_MAIN

@error_handler
async def admin_menu_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sous-menu stats"""
    query = update.callback_query
    await query.answer()
    
    stats = load_stats()
    weekly = stats.get("weekly", [])
    monthly = stats.get("monthly", [])
    
    text = "📊 *STATISTIQUES*\n\n"
    
    if weekly:
        total_week = sum(s["amount"] for s in weekly)
        text += f"📅 *Cette semaine :*\n💰 {total_week:.2f}€\n📦 {len(weekly)} commandes\n\n"
    else:
        text += "📅 *Cette semaine :* Aucune vente\n\n"
    
    if monthly:
        total_month = sum(s["amount"] for s in monthly)
        text += f"📆 *Ce mois :*\n💰 {total_month:.2f}€\n📦 {len(monthly)} commandes"
    else:
        text += "📆 *Ce mois :* Aucune vente"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_back_main")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_MENU_MAIN

@error_handler
async def admin_menu_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sous-menu users"""
    query = update.callback_query
    await query.answer()
    
    users = load_users()
    total = len(users)
    
    week_ago = datetime.now() - timedelta(days=7)
    active_7d = sum(1 for u in users.values() if datetime.fromisoformat(u.get("last_seen", "2020-01-01")) > week_ago)
    
    text = f"👥 *UTILISATEURS*\n\n📊 Total : {total}\n🟢 Actifs (7j) : {active_7d}\n\n💡 Détails : `/users`"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_back_main")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_MENU_MAIN

@error_handler
async def admin_menu_horaires_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sous-menu horaires"""
    query = update.callback_query
    await query.answer()
    
    horaires = load_horaires()
    enabled = horaires.get("enabled", True)
    
    if enabled:
        status = f"🟢 Activés : {get_horaires_text()}"
    else:
        status = "🔴 Désactivés (24h/24)"
    
    text = f"⏰ *HORAIRES*\n\n{status}\n\n💡 Modifier : `/horaires`"
    
    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="admin_back_main")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_MENU_MAIN

@error_handler
async def admin_back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au menu principal admin"""
    query = update.callback_query
    await query.answer()
    
    text = "🎛️ *PANNEAU ADMIN*\n\nChoisissez une section :"
    
    keyboard = [
        [
            InlineKeyboardButton("📦 Produits", callback_data="admin_menu_products"),
            InlineKeyboardButton("💰 Prix", callback_data="admin_menu_prices")
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_menu_stats"),
            InlineKeyboardButton("👥 Users", callback_data="admin_menu_users")
        ],
        [
            InlineKeyboardButton("⏰ Horaires", callback_data="admin_menu_horaires"),
            InlineKeyboardButton("❌ Fermer", callback_data="admin_close")
        ]
    ]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_MENU_MAIN

@error_handler
async def admin_del_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /del <code> - Masque un produit (rupture de stock)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin uniquement.")
        return
    
    if not context.args:
        text = "❌ *MASQUER UN PRODUIT*\n\n*Usage :* `/del <code>`\n\n*Codes disponibles :*\n"
        
        registry = load_product_registry()
        available = get_available_products()
        
        for code, data in sorted(registry.items()):
            name = data['name']
            status = "✅" if name in available else "❌"
            text += f"  {status} `{code}` → {name}\n"
        
        text += "\n*Exemple :* `/del weed`\n\n💡 Pour réactiver : `/add <code>`"
        await update.message.reply_text(text, parse_mode='Markdown')
        return
    
    code = context.args[0].lower()
    product_name = PRODUCT_CODES.get(code)
    
    if not product_name:
        await update.message.reply_text(f"❌ Code invalide: `{code}`\n\nUtilisez `/del` sans argument pour voir les codes.", parse_mode='Markdown')
        return
    
    available = get_available_products()
    
    if product_name not in available:
        await update.message.reply_text(f"⚠️ {product_name} est déjà masqué.\n\n💡 Pour réactiver : `/add {code}`", parse_mode='Markdown')
        return
    
    available.remove(product_name)
    save_available_products(available)
    
    text = f"✅ *PRODUIT MASQUÉ*\n\n❌ {product_name}\nCode : `{code}`\n\n*Effet :*\n• Invisible dans la Carte du Pirate\n• Impossible à commander\n• Prix conservés\n\n💡 Réactiver : `/add {code}`"
    
    await update.message.reply_text(text, parse_mode='Markdown')
    logger.info(f"🔴 Produit masqué: {product_name} ({code})")

@error_handler
async def admin_add_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /add <code> - Affiche un produit (remise en stock)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin uniquement.")
        return
    
    if not context.args:
        text = "❌ *ACTIVER UN PRODUIT*\n\n*Usage :* `/add <code>`\n\n*Codes disponibles :*\n"
        
        registry = load_product_registry()
        available = get_available_products()
        
        for code, data in sorted(registry.items()):
            name = data['name']
            status = "✅" if name in available else "❌"
            text += f"  {status} `{code}` → {name}\n"
        
        text += "\n*Exemple :* `/add weed`\n\n💡 Pour masquer : `/del <code>`"
        await update.message.reply_text(text, parse_mode='Markdown')
        return
    
    code = context.args[0].lower()
    product_name = PRODUCT_CODES.get(code)
    
    if not product_name:
        await update.message.reply_text(f"❌ Code invalide: `{code}`\n\nUtilisez `/add` sans argument pour voir les codes.", parse_mode='Markdown')
        return
    
    available = get_available_products()
    
    if product_name in available:
        await update.message.reply_text(f"⚠️ {product_name} est déjà disponible.\n\n💡 Pour masquer : `/del {code}`", parse_mode='Markdown')
        return
    
    available.add(product_name)
    save_available_products(available)
    
    text = f"✅ *PRODUIT ACTIVÉ*\n\n✅ {product_name}\nCode : `{code}`\n\n*Effet :*\n• Visible dans la Carte du Pirate\n• Les clients peuvent commander\n\n💡 Masquer : `/del {code}`"
    
    await update.message.reply_text(text, parse_mode='Markdown')
    logger.info(f"🟢 Produit activé: {product_name} ({code})")

@error_handler
async def admin_repair_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin uniquement.")
        return
    
    if not context.args:
        text = "🔧 *RÉPARER UN PRODUIT*\n\nUsage : `/repair <code>`\n\n*Exemples :*\n• `/repair coco`\n• `/repair fourmmc`\n\n*Codes disponibles :*\n"
        
        registry = load_product_registry()
        for code, data in sorted(registry.items()):
            text += f"  • `{code}` → {data['name']}\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        return
    
    code = context.args[0].lower()
    
    await update.message.reply_text(f"🔧 Réparation de `{code}` en cours...", parse_mode='Markdown')
    
    if repair_product_visibility(code):
        registry = load_product_registry()
        product_data = registry.get(code, {})
        name = product_data.get("name", code)
        
        text = f"✅ *Produit réparé !*\n\n📦 {name}\nCode : `{code}`\n\n*Vérifications :*\n"
        
        available = get_available_products()
        text += f"{'✅' if name in available else '❌'} Visible dans `/products`\n"
        
        prices = load_prices()
        price_fr = prices.get("FR", {}).get(name, 0)
        price_ch = prices.get("CH", {}).get(name, 0)
        text += f"{'✅' if price_fr > 0 else '❌'} Prix FR : {price_fr}€\n"
        text += f"{'✅' if price_ch > 0 else '❌'} Prix CH : {price_ch}€\n\n"
        
        text += f"*Testez maintenant :*\n• `/products`\n• Carte du Pirate\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    else:
        text = f"❌ *Impossible de réparer* `{code}`\n\n*Produits existants :*\n"
        
        registry = load_product_registry()
        for c, data in sorted(registry.items()):
            text += f"  • `{c}` → {data['name']}\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')

@error_handler
async def admin_debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin uniquement.")
        return
    
    text = "🔍 *DEBUG PRODUITS*\n\n"
    
    text += f"📦 *PRODUCT_CODES* : {len(PRODUCT_CODES)}\n"
    for code, name in sorted(PRODUCT_CODES.items()):
        text += f"  • `{code}` → {name}\n"
    
    available = get_available_products()
    text += f"\n✅ *Available* : {len(available)}\n"
    for name in sorted(available):
        text += f"  • {name}\n"
    
    registry = load_product_registry()
    text += f"\n📋 *Registry* : {len(registry)}\n"
    
    prices = load_prices()
    text += f"\n💰 *Prix FR* : {len(prices.get('FR', {}))}\n"
    text += f"💰 *Prix CH* : {len(prices.get('CH', {}))}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

@error_handler
async def admin_products_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin uniquement.")
        return
    
    available = get_available_products()
    registry = load_product_registry()
    all_products = set(PRODUCT_CODES.values())
    
    text = "📦 *GESTION DES PRODUITS*\n\n"
    
    text += f"*Produits disponibles :* ({len(available)})\n"
    for product in sorted(available):
        text += f"✅ {product}\n"
    
    hidden = all_products - available
    if hidden:
        text += f"\n*Produits masqués :* ({len(hidden)})\n"
        for product in sorted(hidden):
            text += f"❌ {product}\n"
    
    text += f"\n💡 *Commandes :*\n"
    text += f"• `/del <code>` - Masquer un produit\n"
    text += f"• `/add <code>` - Activer un produit\n"
    text += f"• `/repair <code>` - Réparer un produit"
    
    keyboard = [
        [InlineKeyboardButton("➕ Créer", callback_data="admin_create_product")],
        [InlineKeyboardButton("🗑️ Archiver", callback_data="admin_archive_product")],
        [InlineKeyboardButton("♻️ Restaurer", callback_data="admin_restore_product")],
        [InlineKeyboardButton("🔙 Fermer", callback_data="admin_close")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

@error_handler
async def admin_create_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['creating_product'] = {}
    text = "➕ *CRÉER UN PRODUIT*\n\nÉtape 1/5\n\nQuel est le *nom complet* du produit ?\n_(Incluez l'emoji, ex: 🔥 Crack)_"
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_cancel_product")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_NEW_PRODUCT_NAME

@error_handler
async def receive_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data['creating_product']['name'] = name
    text = f"➕ *CRÉER UN PRODUIT*\n\nNom: {name}\n\nÉtape 2/5\n\nQuel est le *code* ?\n_(Ex: crack, heroine)_"
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_cancel_product")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_NEW_PRODUCT_CODE

@error_handler
async def receive_product_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().lower()
    if code in PRODUCT_CODES:
        await update.message.reply_text(f"❌ Le code '{code}' existe déjà.")
        return ADMIN_NEW_PRODUCT_CODE
    context.user_data['creating_product']['code'] = code
    text = f"➕ *CRÉER UN PRODUIT*\n\nÉtape 3/5\n\nQuelle est la *catégorie* ?"
    keyboard = [
        [InlineKeyboardButton("❄️ Poudre", callback_data="category_powder")],
        [InlineKeyboardButton("💊 Pilule", callback_data="category_pill")],
        [InlineKeyboardButton("🪨 Crystal", callback_data="category_rock")],
        [InlineKeyboardButton("❌ Annuler", callback_data="admin_cancel_product")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_NEW_PRODUCT_CATEGORY

@error_handler
async def receive_product_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("category_", "")
    context.user_data['creating_product']['category'] = category
    text = f"➕ *CRÉER UN PRODUIT*\n\nÉtape 4/5\n\n*Prix en France* (€) ?\n_(Ex: 50)_"
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_cancel_product")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_NEW_PRODUCT_PRICE_FR

@error_handler
async def receive_product_price_fr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price_fr = float(update.message.text.strip())
        if price_fr <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Prix invalide.")
        return ADMIN_NEW_PRODUCT_PRICE_FR
    context.user_data['creating_product']['price_fr'] = price_fr
    text = f"➕ *CRÉER UN PRODUIT*\n\nÉtape 5/5\n\n*Prix en Suisse* (€) ?\n_(Ex: 70)_"
    keyboard = [[InlineKeyboardButton("❌ Annuler", callback_data="admin_cancel_product")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_NEW_PRODUCT_PRICE_CH

@error_handler
async def receive_product_price_ch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price_ch = float(update.message.text.strip())
        if price_ch <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Prix invalide.")
        return ADMIN_NEW_PRODUCT_PRICE_CH
    context.user_data['creating_product']['price_ch'] = price_ch
    product_data = context.user_data['creating_product']
    text = f"➕ *CRÉER UN PRODUIT*\n\n*Récapitulatif :*\n\n• Nom: {product_data['name']}\n• Code: {product_data['code']}\n• Prix FR: {product_data['price_fr']}€\n• Prix CH: {price_ch}€\n\nConfirmer ?"
    keyboard = [
        [InlineKeyboardButton("✅ Créer", callback_data="admin_confirm_create")],
        [InlineKeyboardButton("❌ Annuler", callback_data="admin_cancel_product")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_CONFIRM_PRODUCT

@error_handler
async def confirm_create_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_data = context.user_data['creating_product']
    
    success = add_new_product(
        name=product_data['name'],
        code=product_data['code'],
        emoji=product_data['name'].split()[0] if product_data['name'] else "",
        category=product_data['category'],
        price_fr=product_data['price_fr'],
        price_ch=product_data['price_ch']
    )
    
    if success:
        text = f"✅ *PRODUIT CRÉÉ !*\n\n• {product_data['name']}\n• Code: `{product_data['code']}`\n• Prix FR: {product_data['price_fr']}€\n• Prix CH: {product_data['price_ch']}€\n\n*Le produit est maintenant :*\n✅ Visible dans la Carte du Pirate\n✅ Disponible à la commande\n\n💡 Pour masquer : `/del {product_data['code']}`"
    else:
        text = "❌ Erreur création."
    
    await query.message.edit_text(text, parse_mode='Markdown')
    del context.user_data['creating_product']
    return ConversationHandler.END

@error_handler
async def admin_archive_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    available = get_available_products()
    if not available:
        await query.message.edit_text("❌ Aucun produit disponible.")
        return ConversationHandler.END
    text = "🗑️ *ARCHIVER UN PRODUIT*\n\nSélectionnez :"
    keyboard = []
    for product in sorted(available):
        keyboard.append([InlineKeyboardButton(f"🗑️ {product}", callback_data=f"archive_{product[:30]}")])
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_close")])
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

@error_handler
async def confirm_archive_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_name = query.data.replace("archive_", "")
    available = list(get_available_products())
    full_name = None
    for name in available:
        if name.startswith(product_name):
            full_name = name
            break
    if not full_name:
        await query.message.edit_text("❌ Produit non trouvé.")
        return ConversationHandler.END
    text = f"🗑️ Archiver {full_name} ?\n\nConfirmer ?"
    keyboard = [
        [InlineKeyboardButton("✅ Archiver", callback_data=f"confirmarchive_{full_name[:30]}")],
        [InlineKeyboardButton("❌ Annuler", callback_data="admin_close")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

@error_handler
async def execute_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_name = query.data.replace("confirmarchive_", "")
    available = list(get_available_products())
    full_name = None
    for name in available:
        if name.startswith(product_name):
            full_name = name
            break
    if full_name and archive_product(full_name):
        text = f"✅ *ARCHIVÉ*\n\n{full_name}"
    else:
        text = "❌ Erreur."
    await query.message.edit_text(text, parse_mode='Markdown')
    return ConversationHandler.END

@error_handler
async def admin_restore_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    archived = load_archived_products()
    if not archived:
        await query.message.edit_text("❌ Aucun produit archivé.")
        return ConversationHandler.END
    text = "♻️ *RESTAURER UN PRODUIT*\n\nSélectionnez :"
    keyboard = []
    for product_name in archived.keys():
        keyboard.append([InlineKeyboardButton(f"♻️ {product_name}", callback_data=f"restore_{product_name[:30]}")])
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="admin_close")])
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

@error_handler
async def execute_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_name = query.data.replace("restore_", "")
    archived = load_archived_products()
    full_name = None
    for name in archived.keys():
        if name.startswith(product_name):
            full_name = name
            break
    if full_name and restore_product(full_name):
        text = f"✅ *RESTAURÉ*\n\n{full_name}"
    else:
        text = "❌ Erreur."
    await query.message.edit_text(text, parse_mode='Markdown')
    return ConversationHandler.END

@error_handler
async def admin_cancel_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if 'creating_product' in context.user_data:
        del context.user_data['creating_product']
    await query.message.edit_text("❌ Annulé.")
    return ConversationHandler.END

@error_handler
async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    return ConversationHandler.END

@error_handler
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    users = load_users()
    text = f"👥 *UTILISATEURS*\n\n📊 Total : {len(users)}"
    await update.message.reply_text(text, parse_mode='Markdown')

@error_handler
async def admin_prices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin uniquement.")
        return
    
    prices = load_prices()
    available = get_available_products()
    
    text = "💰 *PRIX*\n\n🇫🇷 *France :*\n"
    for product in sorted(available):
        current_price = prices.get("FR", {}).get(product, 0)
        text += f"  • {product} : {current_price}€\n"
    
    text += "\n🇨🇭 *Suisse :*\n"
    for product in sorted(available):
        current_price = prices.get("CH", {}).get(product, 0)
        text += f"  • {product} : {current_price}€\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

@error_handler
async def admin_setprice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin uniquement.")
        return
    
    if len(context.args) != 3:
        text = "❌ *Usage :* `/setprice <code> <pays> <prix>`\n\n*Exemple :* `/setprice coco fr 85`"
        await update.message.reply_text(text, parse_mode='Markdown')
        return
    
    code = context.args[0].lower()
    country_code = context.args[1].lower()
    
    product_name = PRODUCT_CODES.get(code)
    if not product_name:
        await update.message.reply_text(f"❌ Code invalide: `{code}`", parse_mode='Markdown')
        return
    
    if country_code not in ['fr', 'ch']:
        await update.message.reply_text("❌ Pays invalide. Utilisez `fr` ou `ch`.", parse_mode='Markdown')
        return
    
    country = "FR" if country_code == "fr" else "CH"
    
    try:
        new_price = float(context.args[2])
        if new_price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Prix invalide.")
        return
    
    if set_price(product_name, country, new_price):
        text = f"✅ *Prix modifié*\n\n{product_name}\nNouveau : {new_price}€"
        await update.message.reply_text(text, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Erreur.")

@error_handler
async def admin_horaires_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin uniquement.")
        return ConversationHandler.END
    horaires = load_horaires()
    current = get_horaires_text()
    text = f"⏰ *HORAIRES*\n\nActuels : {current}\n\nFormat : `HH:MM-HH:MM`\nExemple : `09:00-23:00`\n\nCommandes : `off` | `on` | `cancel`"
    await update.message.reply_text(text, parse_mode='Markdown')
    return ADMIN_HORAIRES_INPUT

@error_handler
async def admin_horaires_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    text = update.message.text.strip().lower()
    if text == "cancel":
        await update.message.reply_text("❌ Annulé.")
        return ConversationHandler.END
    horaires = load_horaires()
    if text == "off":
        horaires["enabled"] = False
        save_horaires(horaires)
        await update.message.reply_text("✅ Horaires désactivés (24h/24).")
        return ConversationHandler.END
    if text == "on":
        horaires["enabled"] = True
        save_horaires(horaires)
        await update.message.reply_text(f"✅ Réactivés : {get_horaires_text()}")
        return ConversationHandler.END
    match = re.match(r'^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$', text)
    if not match:
        await update.message.reply_text("❌ Format invalide.")
        return ADMIN_HORAIRES_INPUT
    start_h, start_m, end_h, end_m = map(int, match.groups())
    if not (0 <= start_h < 24 and 0 <= end_h < 24):
        await update.message.reply_text("❌ Heures invalides.")
        return ADMIN_HORAIRES_INPUT
    horaires.update({"start_hour": start_h, "start_minute": start_m, "end_hour": end_h, "end_minute": end_m, "enabled": True})
    save_horaires(horaires)
    await update.message.reply_text(f"✅ Mis à jour : {get_horaires_text()}")
    return ConversationHandler.END

@error_handler
async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin uniquement.")
        return
    stats = load_stats()
    weekly = stats.get("weekly", [])
    
    text = "📊 *STATISTIQUES*\n\n"
    
    if weekly:
        total_week = sum(s["amount"] for s in weekly)
        text += f"📅 *Cette semaine :*\n💰 Total : {total_week:.2f}€\n📦 Commandes : {len(weekly)}"
    else:
        text += f"📅 *Cette semaine :* Aucune vente"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def error_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)

# ==================== FONCTION PRINCIPALE ====================

async def main_async():
    """Fonction principale asynchrone"""
    
    init_product_codes()
    
    logger.info("=" * 60)
    logger.info("🤖 BOT TELEGRAM V2.2 - COMPLET")
    logger.info("=" * 60)
    logger.info(f"📱 Token: {TOKEN[:5]}***")
    logger.info(f"👤 Admin: ***{str(ADMIN_ID)[-3:]}")
    logger.info(f"⏰ Horaires: {get_horaires_text()}")
    logger.info("=" * 60)
    
    application = Application.builder().token(TOKEN).concurrent_updates(True).build()
    logger.info("✅ Application créée")
    
    await application.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook supprimé")
    
    try:
        await application.bot.get_updates(offset=-1, timeout=1)
        logger.info("✅ Connexions libérées")
    except:
        pass
    
    horaires_handler = ConversationHandler(
        entry_points=[CommandHandler('horaires', admin_horaires_command)],
        states={ADMIN_HORAIRES_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_horaires_input)]},
        fallbacks=[],
        allow_reentry=False,
        name="horaires_conv"
    )
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            LANGUE: [CallbackQueryHandler(set_langue, pattern='^lang_')],
            PAYS: [
                CallbackQueryHandler(menu_navigation, pattern='^start_order$'),
                CallbackQueryHandler(choix_pays, pattern='^country_'),
                CallbackQueryHandler(restart_order, pattern='^restart_order$'),
                CallbackQueryHandler(voir_carte, pattern='^voir_carte$'),
                CallbackQueryHandler(afficher_prix, pattern='^prix_(france|suisse)$'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$'),
                CallbackQueryHandler(menu_navigation, pattern='^contact_admin$'),
                CallbackQueryHandler(back_navigation, pattern='^back_to_country_choice$')
            ],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_handler)],
            PRODUIT: [
                CallbackQueryHandler(choix_produit, pattern='^product_'),
                CallbackQueryHandler(back_navigation, pattern='^back_(to_main|to_country_choice|to_products)$'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$')
            ],
            PILL_SUBCATEGORY: [
                CallbackQueryHandler(choix_pill_subcategory, pattern='^pill_'),
                CallbackQueryHandler(back_navigation, pattern='^back_to_products$'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$')
            ],
            ROCK_SUBCATEGORY: [
                CallbackQueryHandler(choix_rock_subcategory, pattern='^rock_'),
                CallbackQueryHandler(back_navigation, pattern='^back_to_products$'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$')
            ],
            QUANTITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)],
            CART_MENU: [
                CallbackQueryHandler(cart_menu, pattern='^(add_more|proceed_checkout)$'),
                CallbackQueryHandler(back_to_main_menu, pattern='^back_to_main_menu$')
            ],
            ADRESSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse)],
            LIVRAISON: [CallbackQueryHandler(choix_livraison, pattern='^delivery_')],
            PAIEMENT: [CallbackQueryHandler(choix_paiement, pattern='^payment_')],
            CONFIRMATION: [CallbackQueryHandler(confirmation, pattern='^(confirm_order|cancel)$')]
        },
        fallbacks=[CommandHandler('start', start_command)],
        allow_reentry=True,
        per_message=False,
        name="main_conv"
    )
    
    product_management_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_create_product, pattern="^admin_create_product$"),
            CallbackQueryHandler(admin_archive_product, pattern="^admin_archive_product$"),
            CallbackQueryHandler(admin_restore_product, pattern="^admin_restore_product$"),
        ],
        states={
            ADMIN_NEW_PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product_name)],
            ADMIN_NEW_PRODUCT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product_code)],
            ADMIN_NEW_PRODUCT_CATEGORY: [CallbackQueryHandler(receive_product_category, pattern="^category_")],
            ADMIN_NEW_PRODUCT_PRICE_FR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product_price_fr)],
            ADMIN_NEW_PRODUCT_PRICE_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product_price_ch)],
            ADMIN_CONFIRM_PRODUCT: [
                CallbackQueryHandler(confirm_create_product, pattern="^admin_confirm_create$"),
                CallbackQueryHandler(admin_cancel_product, pattern="^admin_cancel_product$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(admin_cancel_product, pattern="^admin_cancel_product$"),
            CallbackQueryHandler(admin_close, pattern="^admin_close$"),
        ],
        name="product_management",
        persistent=False,
        per_message=False
    )
    
    admin_menu_handler = ConversationHandler(
        entry_points=[CommandHandler('admin', admin_command)],
        states={
            ADMIN_MENU_MAIN: [
                CallbackQueryHandler(admin_menu_products_callback, pattern="^admin_menu_products$"),
                CallbackQueryHandler(admin_menu_prices_callback, pattern="^admin_menu_prices$"),
                CallbackQueryHandler(admin_menu_stats_callback, pattern="^admin_menu_stats$"),
                CallbackQueryHandler(admin_menu_users_callback, pattern="^admin_menu_users$"),
                CallbackQueryHandler(admin_menu_horaires_callback, pattern="^admin_menu_horaires$"),
                CallbackQueryHandler(admin_back_main, pattern="^admin_back_main$"),
                CallbackQueryHandler(admin_close, pattern="^admin_close$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(admin_close, pattern="^admin_close$")],
        name="admin_menu",
        persistent=False,
        per_message=False
    )
    
    application.add_handler(horaires_handler)
    application.add_handler(conv_handler)
    application.add_handler(product_management_handler)
    application.add_handler(admin_menu_handler)
    application.add_handler(CommandHandler('products', admin_products_command))
    application.add_handler(CommandHandler('prices', admin_prices_command))
    application.add_handler(CommandHandler('setprice', admin_setprice_command))
    application.add_handler(CommandHandler('del', admin_del_product_command))
    application.add_handler(CommandHandler('add', admin_add_product_command))
    application.add_handler(CommandHandler('users', users_command))
    application.add_handler(CommandHandler('repair', admin_repair_command))
    application.add_handler(CommandHandler('debug', admin_debug_command))
    application.add_handler(CommandHandler('stats', admin_stats_command))
    
    application.add_handler(CallbackQueryHandler(admin_validation_livraison, pattern='^admin_validate_'))
    application.add_handler(CallbackQueryHandler(confirm_archive_product, pattern="^archive_"))
    application.add_handler(CallbackQueryHandler(execute_archive, pattern="^confirmarchive_"))
    application.add_handler(CallbackQueryHandler(execute_restore, pattern="^restore_"))
    application.add_handler(CallbackQueryHandler(admin_close, pattern="^admin_close$"))
    
    application.add_error_handler(error_callback)
    
    if application.job_queue is not None:
        application.job_queue.run_repeating(check_pending_deletions, interval=60, first=10)
        application.job_queue.run_repeating(schedule_reports, interval=60, first=10)
        logger.info("✅ Tasks programmées")
    
    logger.info("✅ Handlers configurés")
    logger.info("=" * 60)
    logger.info("🚀 BOT V2.2 EN LIGNE")
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
