import requests
import os
from dotenv import load_dotenv

load_dotenv('infos.env')

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('BOT_TOKEN')
WEBHOOK_URL = input("Entrez l'URL publique de votre application (ex: https://votre-app.com): ").strip()

if not WEBHOOK_URL:
    print("❌ URL requise")
    exit(1)

if not TELEGRAM_BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN manquant dans infos.env")
    exit(1)

# Construction de l'URL complète du webhook
full_webhook_url = f"{WEBHOOK_URL}/api/telegram/webhook"

print(f"\n🔧 Configuration du webhook Telegram...")
print(f"📍 URL: {full_webhook_url}")

# Enregistrement du webhook
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
response = requests.post(url, json={"url": full_webhook_url})

if response.status_code == 200:
    data = response.json()
    if data.get('ok'):
        print(f"✅ Webhook configuré avec succès!")
        print(f"📝 Description: {data.get('description', 'N/A')}")
    else:
        print(f"❌ Erreur: {data.get('description', 'Erreur inconnue')}")
else:
    print(f"❌ Erreur HTTP {response.status_code}")
    print(response.text)

# Vérification du webhook
print(f"\n🔍 Vérification du webhook...")
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    if data.get('ok'):
        info = data.get('result', {})
        print(f"✅ Webhook actuel: {info.get('url', 'Aucun')}")
        print(f"📊 Pending updates: {info.get('pending_update_count', 0)}")
        if info.get('last_error_message'):
            print(f"⚠️ Dernière erreur: {info.get('last_error_message')}")
            print(f"   Date: {info.get('last_error_date')}")
    else:
        print(f"❌ Erreur lors de la vérification")
else:
    print(f"❌ Erreur HTTP {response.status_code}")

print("\n" + "="*50)
print("📌 IMPORTANT:")
print("1. Votre application doit être accessible publiquement (HTTPS recommandé)")
print("2. Si vous utilisez ngrok, l'URL change à chaque redémarrage")
print("3. Vous devrez reconfigurer le webhook après chaque changement d'URL")
print("="*50)
