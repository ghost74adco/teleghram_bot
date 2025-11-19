#!/usr/bin/env python3
"""
🔒 CORRECTIONS DE SÉCURITÉ RAPIDES
Appliquez ces modifications pour améliorer la sécurité de votre bot
"""

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta

# ==================== 1. RATE LIMITING ====================

user_requests = defaultdict(list)

def check_rate_limit(user_id, max_requests=10, window_minutes=1):
    """
    Empêche le spam en limitant le nombre de requêtes par utilisateur.
    
    Args:
        user_id: ID de l'utilisateur
        max_requests: Nombre max de requêtes autorisées
        window_minutes: Fenêtre de temps en minutes
    
    Returns:
        bool: True si l'utilisateur peut continuer, False si bloqué
    """
    now = datetime.now()
    
    # Nettoyer les anciennes requêtes
    user_requests[user_id] = [
        req for req in user_requests[user_id] 
        if now - req < timedelta(minutes=window_minutes)
    ]
    
    # Vérifier la limite
    if len(user_requests[user_id]) >= max_requests:
        return False
    
    user_requests[user_id].append(now)
    return True


# ==================== 2. VALIDATION AVANCÉE ====================

import html
import re

def sanitize_input_advanced(text, max_length=300):
    """
    Validation stricte des inputs utilisateur.
    Protège contre les injections et caractères malveillants.
    """
    if not text:
        return ""
    
    # Échapper HTML
    text = html.escape(text)
    
    # Limiter longueur
    text = text.strip()[:max_length]
    
    # Supprimer caractères dangereux
    text = re.sub(r'[<>{}[\]\\`|;$&]', '', text)
    
    # Supprimer URL suspectes
    text = re.sub(r'https?://\S+', '', text)
    
    # Supprimer emails
    text = re.sub(r'\S+@\S+', '', text)
    
    return text


# ==================== 3. CHIFFREMENT DONNÉES ====================

from cryptography.fernet import Fernet
import base64
import os

def generate_encryption_key():
    """
    Génère une clé de chiffrement.
    À FAIRE UNE SEULE FOIS, puis stocker dans .env
    """
    key = Fernet.generate_key()
    print(f"Votre clé de chiffrement (à ajouter dans .env) :")
    print(f"ENCRYPTION_KEY={key.decode()}")
    return key

def encrypt_data(data: str, key: str) -> str:
    """Chiffre une donnée sensible (adresse, nom, etc.)"""
    cipher = Fernet(key.encode())
    encrypted = cipher.encrypt(data.encode())
    return base64.urlsafe_b64encode(encrypted).decode()

def decrypt_data(encrypted_data: str, key: str) -> str:
    """Déchiffre une donnée"""
    cipher = Fernet(key.encode())
    decrypted = cipher.decrypt(base64.urlsafe_b64decode(encrypted_data))
    return decrypted.decode()


# ==================== 4. ANONYMISATION LOGS ====================

def anonymize_user_id(user_id: int) -> str:
    """
    Anonymise un user ID pour les logs.
    Même utilisateur = même hash (traçabilité conservée)
    """
    user_hash = hashlib.sha256(str(user_id).encode()).hexdigest()[:8]
    return f"User#{user_hash}"

def anonymize_name(name: str) -> str:
    """Anonymise un nom pour les logs"""
    if not name or len(name) < 2:
        return "User"
    return f"{name[0]}***{name[-1]}"


# ==================== 5. BACKUP AUTOMATIQUE ====================

import shutil
from pathlib import Path

def backup_data(backup_dir="backups"):
    """
    Sauvegarde tous les fichiers critiques.
    À exécuter quotidiennement (cron ou scheduler).
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = Path(backup_dir)
    backup_path.mkdir(exist_ok=True)
    
    files_to_backup = [
        'orders.csv',
        'stats.json',
        'horaires.json',
        'pending_messages.json'
    ]
    
    backed_up = []
    for filename in files_to_backup:
        source = Path(filename)
        if source.exists():
            dest = backup_path / f"{source.stem}_{timestamp}{source.suffix}"
            shutil.copy2(source, dest)
            backed_up.append(filename)
    
    return backed_up


# ==================== 6. VÉRIFICATION PERMISSIONS ====================

import stat

def check_file_permissions(filepath):
    """
    Vérifie que les permissions du fichier sont sécurisées.
    Retourne True si OK, False si trop permissif.
    """
    file_path = Path(filepath)
    if not file_path.exists():
        return None
    
    file_stat = file_path.stat()
    mode = stat.S_IMODE(file_stat.st_mode)
    
    # Permissions recommandées : 600 (rw-------)
    # L'utilisateur peut lire/écrire, personne d'autre ne peut rien
    recommended_mode = stat.S_IRUSR | stat.S_IWUSR  # 0o600
    
    if mode != recommended_mode:
        return False
    return True

def fix_file_permissions(filepath):
    """
    Corrige les permissions d'un fichier sensible.
    """
    file_path = Path(filepath)
    if not file_path.exists():
        return False
    
    # rw------- (600)
    os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)
    return True


# ==================== EXEMPLE D'UTILISATION ====================

if __name__ == "__main__":
    print("🔒 OUTILS DE SÉCURITÉ\n")
    
    print("1. Générer une clé de chiffrement :")
    print("-" * 50)
    # generate_encryption_key()  # Décommenter pour générer
    
    print("\n2. Exemple chiffrement :")
    print("-" * 50)
    key = ""  # À récupérer depuis .env
    # encrypted = encrypt_data("858 Rte du Chef Lieu", key)
    # print(f"Chiffré : {encrypted}")
    # print(f"Déchiffré : {decrypt_data(encrypted, key)}")
    
    print("\n3. Anonymisation :")
    print("-" * 50)
    print(f"ID 123456789 → {anonymize_user_id(123456789)}")
    print(f"Nom 'Jean Dupont' → {anonymize_name('Jean Dupont')}")
    
    print("\n4. Rate limiting :")
    print("-" * 50)
    user_id = 12345
    for i in range(12):
        allowed = check_rate_limit(user_id, max_requests=10)
        status = "✅ OK" if allowed else "❌ BLOQUÉ"
        print(f"Requête {i+1}: {status}")
    
    print("\n5. Backup :")
    print("-" * 50)
    # backed_up = backup_data()
    # print(f"Fichiers sauvegardés : {backed_up}")
    
    print("\n6. Vérification permissions :")
    print("-" * 50)
    files = ['orders.csv', 'stats.json', '.env']
    for f in files:
        perm = check_file_permissions(f)
        if perm is None:
            print(f"{f}: ⚪ Fichier introuvable")
        elif perm:
            print(f"{f}: ✅ Sécurisé (600)")
        else:
            print(f"{f}: ⚠️ TROP PERMISSIF - Corriger avec fix_file_permissions()")
