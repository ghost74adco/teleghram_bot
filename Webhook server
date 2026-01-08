#!/usr/bin/env python3
"""
Serveur Webhook pour les paiements CoinGate et NOWPayments

Déploiement:
    gunicorn -w 4 -b 0.0.0.0:5000 webhook_server:app

Ou pour développement:
    python webhook_server.py
"""

from flask import Flask, request, jsonify
import csv
import os
import logging
from datetime import datetime
from pathlib import Path

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = Path("/data")
CSV_PATH = DATA_DIR / "orders.csv"

app = Flask(__name__)

def mark_order_paid(order_id, provider, amount=None):
    """Marque une commande comme payée dans le CSV"""
    if not CSV_PATH.exists():
        logger.error(f"❌ CSV introuvable: {CSV_PATH}")
        return False
    
    try:
        # Lire toutes les commandes
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            orders = list(reader)
            fieldnames = reader.fieldnames
        
        order_found = False
        for order in orders:
            if order.get('order_id') == order_id:
                # Marquer comme payée
                order['payment_status'] = 'Paid'
                order['paid_at'] = datetime.now().isoformat()
                order['payment_provider'] = provider
                if amount:
                    order['paid_amount'] = str(amount)
                
                order_found = True
                logger.info(f"✅ Commande {order_id} marquée payée via {provider}")
                break
        
        if not order_found:
            logger.warning(f"⚠️ Commande {order_id} introuvable dans CSV")
            return False
        
        # Sauvegarder
        # Ajouter les nouveaux champs si nécessaires
        if 'payment_status' not in fieldnames:
            fieldnames = list(fieldnames) + ['payment_status', 'paid_at', 'payment_provider', 'paid_amount']
        
        with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(orders)
        
        logger.info(f"💾 CSV mis à jour pour {order_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur mark_order_paid: {e}")
        return False

@app.route('/webhook/coingate', methods=['POST'])
def coingate_webhook():
    """
    Webhook CoinGate
    
    Documentation: https://developer.coingate.com/docs/webhooks
    """
    try:
        data = request.json
        
        logger.info(f"📩 Webhook CoinGate reçu: {data}")
        
        order_id = data.get('order_id')
        status = data.get('status')
        price_amount = data.get('price_amount')
        
        if not order_id:
            return jsonify({'error': 'order_id manquant'}), 400
        
        logger.info(f"💳 CoinGate: Commande {order_id} - Statut: {status}")
        
        # Statuts possibles: new, pending, confirming, paid, invalid, expired, canceled, refunded
        if status == 'paid':
            success = mark_order_paid(order_id, 'CoinGate', price_amount)
            
            if success:
                # TODO: Notifier le bot Telegram
                logger.info(f"✅ Paiement CoinGate confirmé: {order_id}")
            
        return jsonify({'success': True, 'order_id': order_id, 'status': status})
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook CoinGate: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/webhook/nowpayments', methods=['POST'])
def nowpayments_webhook():
    """
    Webhook NOWPayments
    
    Documentation: https://documenter.getpostman.com/view/7907941/S1a32n38#9998079f-dcc8-4e07-9ac7-3d52f0fd733a
    """
    try:
        data = request.json
        
        logger.info(f"📩 Webhook NOWPayments reçu: {data}")
        
        order_id = data.get('order_id')
        payment_status = data.get('payment_status')
        price_amount = data.get('price_amount')
        
        if not order_id:
            return jsonify({'error': 'order_id manquant'}), 400
        
        logger.info(f"₿ NOWPayments: Commande {order_id} - Statut: {payment_status}")
        
        # Statuts possibles: waiting, confirming, confirmed, sending, partially_paid, finished, failed, refunded, expired
        if payment_status in ['finished', 'confirmed']:
            success = mark_order_paid(order_id, 'NOWPayments', price_amount)
            
            if success:
                # TODO: Notifier le bot Telegram
                logger.info(f"✅ Paiement NOWPayments confirmé: {order_id}")
        
        return jsonify({'success': True, 'order_id': order_id, 'payment_status': payment_status})
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook NOWPayments: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'service': 'webhook_server',
        'csv_exists': CSV_PATH.exists(),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/', methods=['GET'])
def index():
    """Page d'accueil"""
    return """
    <h1>Webhook Server</h1>
    <p>Serveur de webhooks pour les paiements crypto</p>
    <ul>
        <li>POST /webhook/coingate - Webhook CoinGate</li>
        <li>POST /webhook/nowpayments - Webhook NOWPayments</li>
        <li>GET /health - Health check</li>
    </ul>
    """

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 DÉMARRAGE SERVEUR WEBHOOK")
    logger.info("=" * 60)
    logger.info(f"📁 CSV Path: {CSV_PATH}")
    logger.info(f"✅ CSV existe: {CSV_PATH.exists()}")
    logger.info("=" * 60)
    
    # Mode développement
    app.run(host='0.0.0.0', port=5000, debug=True)
