"""
Script de diagnostic pour identifier le problème du bot Telegram
"""
import os
import sys
import requests
from dotenv import load_dotenv

print("=" * 60)
print("🔍 DIAGNOSTIC DU BOT TELEGRAM")
print("=" * 60)

# 1. Vérification du fichier .env
print("\n1️⃣ Vérification du fichier .env...")
if os.path.exists('.env'):
    print("   ✅ Fichier .env trouvé")
    load_dotenv()
else:
    print("   ❌ Fichier .env NON TROUVÉ")
    print("   Créez un fichier .env avec:")
    print("   TELEGRAM_BOT_TOKEN=votre_token")
    print("   ADMIN_ID=votre_id")
    sys.exit(1)

# 2. Vérification du TOKEN
print("\n2️⃣ Vérification du TOKEN...")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if TOKEN:
    print(f"   ✅ TOKEN trouvé: {TOKEN[:20]}...")
else:
    print("   ❌ TOKEN NON TROUVÉ dans .env")
    sys.exit(1)

# 3. Test de connexion à l'API Telegram
print("\n3️⃣ Test de connexion à l'API Telegram...")
try:
    response = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=10)
    if response.status_code == 200:
        data = response.json()
        if data.get('ok'):
            bot_info = data.get('result', {})
            print(f"   ✅ Bot connecté: @{bot_info.get('username')}")
            print(f"   ✅ Nom: {bot_info.get('first_name')}")
            print(f"   ✅ ID: {bot_info.get('id')}")
        else:
            print(f"   ❌ Réponse API: {data}")
            sys.exit(1)
    else:
        print(f"   ❌ Erreur HTTP {response.status_code}")
        print(f"   Réponse: {response.text}")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Erreur de connexion: {e}")
    sys.exit(1)

# 4. Vérification de l'ADMIN_ID
print("\n4️⃣ Vérification de l'ADMIN_ID...")
ADMIN_ID = os.getenv("ADMIN_ID") or os.getenv("ADMIN_USER_IDS") or os.getenv("TELEGRAM_ADMIN_ID")
if ADMIN_ID and ADMIN_ID.isdigit():
    print(f"   ✅ ADMIN_ID trouvé: {ADMIN_ID}")
else:
    print(f"   ⚠️  ADMIN_ID invalide: {ADMIN_ID}")

# 5. Vérification de python-telegram-bot
print("\n5️⃣ Vérification de python-telegram-bot...")
try:
    import telegram
    print(f"   ✅ Version installée: {telegram.__version__}")
    if telegram.__version__.startswith('20'):
        print("   ✅ Version compatible (20.x)")
    else:
        print(f"   ⚠️  Version ancienne détectée")
        print("   Exécutez: pip install python-telegram-bot --upgrade")
except ImportError:
    print("   ❌ Module non installé")
    print("   Exécutez: pip install python-telegram-bot")
    sys.exit(1)

# 6. Test des webhooks actifs
print("\n6️⃣ Vérification des webhooks...")
try:
    response = requests.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo", timeout=10)
    if response.status_code == 200:
        webhook_info = response.json().get('result', {})
        webhook_url = webhook_info.get('url', '')
        if webhook_url:
            print(f"   ⚠️  WEBHOOK ACTIF DÉTECTÉ: {webhook_url}")
            print("   ❗ Ceci empêche le polling de fonctionner!")
            print("\n   🔧 SOLUTION: Supprimez le webhook avec:")
            print(f"   curl -X POST https://api.telegram.org/bot{TOKEN}/deleteWebhook")
            
            # Proposition de suppression automatique
            print("\n   Voulez-vous que je le supprime maintenant? (o/n)")
            choice = input("   > ").lower()
            if choice == 'o':
                del_response = requests.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
                if del_response.json().get('ok'):
                    print("   ✅ Webhook supprimé avec succès!")
                else:
                    print("   ❌ Erreur lors de la suppression")
        else:
            print("   ✅ Pas de webhook actif")
    else:
        print(f"   ⚠️  Impossible de vérifier les webhooks")
except Exception as e:
    print(f"   ⚠️  Erreur: {e}")

# 7. Test de polling minimal
print("\n7️⃣ Test de polling minimal...")
print("   Lancement d'un bot de test pendant 10 secondes...")
print("   Envoyez /start à votre bot maintenant!")

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    
    async def test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("✅ LE BOT FONCTIONNE!")
        print(f"   ✅ /start reçu de {update.effective_user.first_name}")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", test_start))
    
    print("   🟢 Bot de test en écoute...")
    print("   📱 Envoyez /start à votre bot dans Telegram")
    
    import asyncio
    async def run_test():
        async with app:
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            await asyncio.sleep(10)
            await app.updater.stop()
            await app.stop()
    
    asyncio.run(run_test())
    print("\n   Test terminé.")
    
except Exception as e:
    print(f"   ❌ Erreur lors du test: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("🏁 DIAGNOSTIC TERMINÉ")
print("=" * 60)
print("\nSi le test ci-dessus a fonctionné, votre bot est OK!")
print("Sinon, partagez les erreurs ci-dessus pour plus d'aide.")
