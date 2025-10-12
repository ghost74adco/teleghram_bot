import requests
import os
from dotenv import load_dotenv

load_dotenv('infos.env')

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('BOT_TOKEN')

# URL CORRIGÉE avec "du"
WEBHOOK_URL = "https://carte-du-pirate.onrender.com/api/telegram/webhook"

if not TELEGRAM_BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN manquant dans infos.env")
    exit(1)

print("="*60)
print("🔧 CONFIGURATION DU WEBHOOK TELEGRAM")
print("="*60)
print(f"📍 URL du webhook: {WEBHOOK_URL}")
print(f"🔑 Token: {TELEGRAM_BOT_TOKEN[:10]}...")
print("="*60)

# 1. Suppression de l'ancien webhook (au cas où)
print("\n🗑️  Suppression de l'ancien webhook...")
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"
response = requests.post(url)
if response.status_code == 200:
    print("✅ Ancien webhook supprimé")
else:
    print("⚠️  Pas d'ancien webhook à supprimer")

# 2. Configuration du nouveau webhook
print(f"\n📤 Configuration du nouveau webhook...")
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
response = requests.post(url, json={"url": WEBHOOK_URL})

if response.status_code == 200:
    data = response.json()
    if data.get('ok'):
        print(f"✅ Webhook configuré avec succès!")
        print(f"📝 Description: {data.get('description', 'N/A')}")
    else:
        print(f"❌ Erreur: {data.get('description', 'Erreur inconnue')}")
        exit(1)
else:
    print(f"❌ Erreur HTTP {response.status_code}")
    print(response.text)
    exit(1)

# 3. Vérification du webhook
print(f"\n🔍 Vérification du webhook...")
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    if data.get('ok'):
        info = data.get('result', {})
        print("\n" + "="*60)
        print("✅ WEBHOOK CONFIGURÉ AVEC SUCCÈS")
        print("="*60)
        print(f"📍 URL: {info.get('url', 'Aucune')}")
        print(f"📊 Updates en attente: {info.get('pending_update_count', 0)}")
        print(f"🔢 Max connexions: {info.get('max_connections', 'N/A')}")
        print(f"🌐 IP: {info.get('ip_address', 'N/A')}")
        
        if info.get('last_error_message'):
            print(f"\n⚠️  DERNIÈRE ERREUR:")
            print(f"   Message: {info.get('last_error_message')}")
            print(f"   Date: {info.get('last_error_date')}")
        else:
            print(f"\n✅ Aucune erreur")
        
        print("="*60)
        print("\n🎉 Le webhook est maintenant actif!")
        print("📱 Testez en cliquant sur le bouton dans Telegram")
    else:
        print(f"❌ Erreur lors de la vérification")
else:
    print(f"❌ Erreur HTTP {response.status_code}")

print("\n" + "="*60)
print("📌 PROCHAINES ÉTAPES:")
print("1. Passez une commande test sur votre site")
print("2. Cliquez sur 'Valider la livraison' dans Telegram")
print("3. Vérifiez les logs Render pour voir le webhook fonctionner")
print("="*60)
