#!/usr/bin/env python3
"""
Script de diagnostic pour l'application Flask Catalogue
Usage: python diagnostic.py
"""

import os
import sys
import json
from pathlib import Path

def print_header(title):
    """Affiche un en-tête formaté"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def print_section(title):
    """Affiche un titre de section"""
    print(f"\n📋 {title}")
    print("-" * 70)

def check_env_file():
    """Vérifie l'existence du fichier .env"""
    print_section("Fichiers d'environnement")
    
    env_files = ['infos.env', '.env']
    found = False
    
    for env_file in env_files:
        if os.path.exists(env_file):
            print(f"✅ {env_file} trouvé")
            found = True
            try:
                from dotenv import load_dotenv
                load_dotenv(env_file)
                print(f"   ✅ Chargé avec succès")
            except ImportError:
                print(f"   ⚠️  python-dotenv non installé (pip install python-dotenv)")
            except Exception as e:
                print(f"   ❌ Erreur de chargement: {e}")
        else:
            print(f"⚠️  {env_file} non trouvé")
    
    if not found:
        print("\n💡 Pour tests locaux : créez un fichier infos.env")
        print("   Pour Render : utilisez le Dashboard Environment")
    
    return found

def check_env_vars():
    """Vérifie les variables d'environnement"""
    print_section("Variables d'environnement")
    
    required_vars = {
        'SECRET_KEY': 'Clé secrète Flask',
        'BOT_TOKEN': 'Token du bot Telegram',
        'ADMIN_PASSWORD': 'Mot de passe admin',
        'CLOUDINARY_CLOUD_NAME': 'Cloudinary Cloud Name',
        'CLOUDINARY_API_KEY': 'Cloudinary API Key',
        'CLOUDINARY_API_SECRET': 'Cloudinary API Secret'
    }
    
    optional_vars = {
        'ADMIN_USER_IDS': 'IDs des admins Telegram',
        'ADMIN_ID': 'ID admin principal',
        'ADMIN_ADDRESS': 'Adresse admin',
        'CRYPTO_WALLET': 'Wallet crypto',
        'BACKGROUND_IMAGE': 'Image de fond',
        'PORT': 'Port (défaut: 5000)',
        'PYTHON_VERSION': 'Version Python'
    }
    
    all_ok = True
    
    print("\n🔴 Variables REQUISES:")
    for var, description in required_vars.items():
        value = os.environ.get(var, '')
        # Chercher aussi les variantes
        if not value and var.startswith('CLOUDINARY_'):
            alt_var = 'CLOUD_' + var.replace('CLOUDINARY_', '')
            value = os.environ.get(alt_var, '')
        
        if value:
            # Masquer les valeurs sensibles
            if any(keyword in var for keyword in ['SECRET', 'PASSWORD', 'TOKEN']):
                display_value = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
            else:
                display_value = value[:20] + "..." if len(value) > 20 else value
            print(f"  ✅ {var}")
            print(f"     {description}: {display_value}")
        else:
            print(f"  ❌ {var}")
            print(f"     {description}: NON DÉFINIE")
            all_ok = False
    
    print("\n🟡 Variables OPTIONNELLES:")
    for var, description in optional_vars.items():
        value = os.environ.get(var, '')
        if value:
            display_value = value[:30] + "..." if len(value) > 30 else value
            print(f"  ✅ {var}: {display_value}")
        else:
            print(f"  ⚠️  {var}: non définie (valeur par défaut sera utilisée)")
    
    return all_ok

def check_products_file():
    """Vérifie le fichier products.json"""
    print_section("Fichier products.json")
    
    if not os.path.exists('products.json'):
        print("⚠️  products.json non trouvé")
        print("\n💡 Création automatique d'un fichier vide...")
        try:
            with open('products.json', 'w', encoding='utf-8') as f:
                json.dump([], f)
            print("✅ products.json créé avec succès")
            return True
        except Exception as e:
            print(f"❌ Impossible de créer products.json: {e}")
            return False
    else:
        print("✅ products.json trouvé")
        try:
            with open('products.json', 'r', encoding='utf-8') as f:
                products = json.load(f)
            print(f"✅ Fichier valide - {len(products)} produit(s)")
            
            if products:
                print("\n📦 Produits existants:")
                for p in products[:3]:  # Afficher les 3 premiers
                    print(f"   • ID {p.get('id')}: {p.get('name')} - {p.get('price')}€")
                if len(products) > 3:
                    print(f"   ... et {len(products) - 3} autre(s)")
            
            return True
        except json.JSONDecodeError as e:
            print(f"❌ Fichier JSON invalide: {e}")
            print("\n💡 Contenu actuel:")
            with open('products.json', 'r') as f:
                print(f.read()[:200])
            return False
        except Exception as e:
            print(f"❌ Erreur de lecture: {e}")
            return False

def check_dependencies():
    """Vérifie les dépendances Python"""
    print_section("Dépendances Python")
    
    dependencies = [
        ('flask', 'Flask'),
        ('flask_cors', 'Flask-CORS'),
        ('dotenv', 'python-dotenv'),
        ('cloudinary', 'cloudinary'),
        ('gunicorn', 'gunicorn'),
    ]
    
    all_ok = True
    for module_name, package_name in dependencies:
        try:
            __import__(module_name)
            # Afficher la version si possible
            try:
                mod = __import__(module_name)
                version = getattr(mod, '__version__', 'version inconnue')
                print(f"  ✅ {package_name} ({version})")
            except:
                print(f"  ✅ {package_name}")
        except ImportError:
            print(f"  ❌ {package_name} - NON INSTALLÉ")
            all_ok = False
    
    if not all_ok:
        print("\n💡 Pour installer les dépendances manquantes:")
        print("   pip install -r requirements.txt")
    
    return all_ok

def check_required_files():
    """Vérifie les fichiers requis"""
    print_section("Fichiers du projet")
    
    required_files = {
        'app.py': 'Application Flask principale',
        'requirements.txt': 'Dépendances Python',
        'products.json': 'Base de données produits',
        '.gitignore': 'Fichiers à ignorer par Git'
    }
    
    optional_files = {
        'runtime.txt': 'Version Python (Render/Heroku)',
        '.python-version': 'Version Python (alternative)',
        'Procfile': 'Configuration Heroku',
        'render.yaml': 'Configuration Render'
    }
    
    all_ok = True
    
    print("\n🔴 Fichiers REQUIS:")
    for file, description in required_files.items():
        if os.path.exists(file):
            size = os.path.getsize(file)
            print(f"  ✅ {file} ({size} octets)")
            print(f"     {description}")
        else:
            print(f"  ❌ {file}")
            print(f"     {description} - MANQUANT")
            all_ok = False
    
    print("\n🟡 Fichiers OPTIONNELS:")
    for file, description in optional_files.items():
        if os.path.exists(file):
            print(f"  ✅ {file}")
        else:
            print(f"  ⚠️  {file} (non requis)")
    
    return all_ok

def test_cloudinary():
    """Test la configuration Cloudinary"""
    print_section("Configuration Cloudinary")
    
    try:
        import cloudinary
        
        # Tenter de configurer
        cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME') or os.environ.get('CLOUD_NAME')
        api_key = os.environ.get('CLOUDINARY_API_KEY') or os.environ.get('CLOUD_API_KEY')
        api_secret = os.environ.get('CLOUDINARY_API_SECRET') or os.environ.get('CLOUD_API_SECRET')
        
        if not all([cloud_name, api_key, api_secret]):
            print("❌ Variables Cloudinary incomplètes")
            print(f"   Cloud Name: {'✅' if cloud_name else '❌'}")
            print(f"   API Key: {'✅' if api_key else '❌'}")
            print(f"   API Secret: {'✅' if api_secret else '❌'}")
            return False
        
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True
        )
        
        print(f"✅ Cloud Name: {cloud_name}")
        print(f"✅ API Key: {api_key[:8]}...")
        print(f"✅ API Secret: configuré")
        print("✅ Configuration Cloudinary OK")
        return True
        
    except ImportError:
        print("❌ Module cloudinary non installé")
        return False
    except Exception as e:
        print(f"❌ Erreur Cloudinary: {e}")
        return False

def check_git_status():
    """Vérifie le statut Git"""
    print_section("Vérification Git")
    
    if not os.path.exists('.git'):
        print("⚠️  Pas de repo Git initialisé")
        print("\n💡 Pour initialiser:")
        print("   git init")
        print("   git add .")
        print("   git commit -m 'Initial commit'")
        return False
    
    print("✅ Repository Git trouvé")
    
    # Vérifier si des fichiers sensibles sont trackés
    sensitive_files = ['.env', 'infos.env', '*.env', 'render_env_vars.txt']
    
    try:
        import subprocess
        result = subprocess.run(['git', 'ls-files'], capture_output=True, text=True)
        tracked_files = result.stdout.split('\n')
        
        found_sensitive = False
        for sensitive in sensitive_files:
            if any(sensitive.replace('*', '') in f for f in tracked_files):
                print(f"⚠️  ATTENTION: Fichier sensible détecté: {sensitive}")
                found_sensitive = True
        
        if found_sensitive:
            print("\n💡 Pour retirer ces fichiers de Git:")
            print("   git rm --cached infos.env .env")
            print("   git commit -m 'Remove sensitive files'")
            return False
        else:
            print("✅ Aucun fichier sensible dans Git")
            return True
            
    except:
        print("⚠️  Impossible de vérifier les fichiers Git")
        return True

def main():
    """Fonction principale"""
    print_header("🔍 DIAGNOSTIC DE L'APPLICATION CATALOGUE")
    
    checks = []
    
    # Exécuter tous les tests
    checks.append(("Fichiers du projet", check_required_files()))
    checks.append(("Fichier env", check_env_file()))
    checks.append(("Variables d'environnement", check_env_vars()))
    checks.append(("Dépendances Python", check_dependencies()))
    checks.append(("Fichier products.json", check_products_file()))
    checks.append(("Configuration Cloudinary", test_cloudinary()))
    checks.append(("Statut Git", check_git_status()))
    
    # Résumé
    print_header("📊 RÉSUMÉ DU DIAGNOSTIC")
    
    for name, status in checks:
        emoji = "✅" if status else "❌"
        print(f"{emoji} {name}")
    
    all_passed = all(status for _, status in checks)
    
    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 TOUS LES TESTS SONT PASSÉS!")
        print("\n✅ Votre application est prête !")
        print("\n📝 Prochaines étapes:")
        print("   1. Ajoutez les variables d'environnement dans Render Dashboard")
        print("   2. Poussez votre code sur Git:")
        print("      git add .")
        print("      git commit -m 'Ready for deployment'")
        print("      git push origin main")
        print("   3. Render déploiera automatiquement votre app")
    else:
        print("⚠️  CERTAINS TESTS ONT ÉCHOUÉ")
        print("\n📝 Corrigez les erreurs ci-dessus avant de déployer")
    print("=" * 70)
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())