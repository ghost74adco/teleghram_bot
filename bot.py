from infos import TOKEN, CRYPTO_WALLET, ADMIN_ID
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    filters,
)

# --- États ---
PAYS, PRODUIT, QUANTITE, ADRESSE, LIVRAISON, PAIEMENT, CONFIRMATION = range(7)

# --- Variables d'environnement ---
TOKEN = "8474087335:AAGQnYnj5gTmtHphvfUHME8h84ygwQejl7Y"
CRYPTO_WALLET = "3AbkDZtRVXUMdBSejXMNg6pEGMcxfCRpQL"
ADMIN_ID = 8450278584

# --- Prix ---
PRIX_FR = {"❄️": 80, "💊": 10, "🫒": 7, "🍀": 10}
PRIX_CH = {"❄️": 100, "💊": 15, "🫒": 8, "🍀": 12}

# --- Commande /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Démarrer la commande", callback_data="start_order")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Bienvenue ! Cliquez sur le bouton pour démarrer votre commande :",
        reply_markup=reply_markup
    )

# --- Choix du pays ---
async def choix_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 France", callback_data="FR")],
        [InlineKeyboardButton("🇨🇭 Suisse", callback_data="CH")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Choisissez votre pays :", reply_markup=reply_markup)
    return PAYS

# --- Sélection du pays ---
async def set_pays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Annuler":
        await query.message.reply_text("Commande annulée.")
        return ConversationHandler.END

    context.user_data['pays'] = query.data

    keyboard = [
        [InlineKeyboardButton("❄️", callback_data="❄️")],
        [InlineKeyboardButton("💊", callback_data="💊")],
        [InlineKeyboardButton("🫒", callback_data="🫒")],
        [InlineKeyboardButton("🍀", callback_data="🍀")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Sélectionnez un produit :", reply_markup=reply_markup)
    return PRODUIT

# --- Choix produit ---
async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Annuler":
        await query.message.reply_text("Commande annulée.")
        return ConversationHandler.END

    produit = query.data
    context.user_data.setdefault('produits', []).append({'produit': produit, 'quantite': 0})
    await query.message.reply_text(f"Produit choisi : {produit}\nIndiquez la quantité en grammes :")
    return QUANTITE

# --- Saisie quantité ---
async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = update.message.text

    if not texte.isdigit():
        await update.message.reply_text("Veuillez entrer un nombre en grammes.")
        return QUANTITE

    quantite = int(texte)
    context.user_data['produits'][-1]['quantite'] = quantite

    if 'adresse' in context.user_data:
        await update.message.reply_text(f"Adresse conservée : {context.user_data['adresse']}")
        keyboard = [
            [InlineKeyboardButton("Standard", callback_data="Standard")],
            [InlineKeyboardButton("Express", callback_data="Express")],
            [InlineKeyboardButton("Annuler", callback_data="Annuler")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choisissez le mode de livraison :", reply_markup=reply_markup)
        return LIVRAISON
    else:
        await update.message.reply_text("Veuillez saisir votre adresse :")
        return ADRESSE

# --- Saisie adresse ---
async def saisie_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = update.message.text.strip()

    if len(texte) < 5:
        await update.message.reply_text("Veuillez saisir une adresse valide.")
        return ADRESSE

    context.user_data['adresse'] = texte

    keyboard = [
        [InlineKeyboardButton("Standard", callback_data="Standard")],
        [InlineKeyboardButton("Express", callback_data="Express")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choisissez le mode de livraison :", reply_markup=reply_markup)
    return LIVRAISON

# --- Choix livraison ---
async def choix_livraison(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Annuler":
        await query.message.reply_text("Commande annulée.")
        return ConversationHandler.END

    context.user_data['livraison'] = query.data

    keyboard = [
        [InlineKeyboardButton("Crypto", callback_data="Crypto")],
        [InlineKeyboardButton("Espèces", callback_data="Especes")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Choisissez le mode de paiement :", reply_markup=reply_markup)
    return PAIEMENT

# --- Choix paiement ---
async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Annuler":
        await query.message.reply_text("Commande annulée.")
        return ConversationHandler.END

    context.user_data['paiement'] = query.data

    # Calcul total
    total = 0
    prix_dict = PRIX_FR if context.user_data['pays'] == "FR" else PRIX_CH

    for item in context.user_data['produits']:
        total += item['quantite'] * prix_dict[item['produit']]

    context.user_data['montant'] = total

    # Résumé avec boutons
    resume = f"Résumé de votre commande :\nPays : {context.user_data['pays']}\nAdresse : {context.user_data['adresse']}\nLivraison : {context.user_data['livraison']}\nPaiement : {context.user_data['paiement']}\nProduits :\n"

    for item in context.user_data['produits']:
        resume += f"• {item['produit']} — {item['quantite']}g — {item['quantite']*prix_dict[item['produit']]} {('€' if context.user_data['pays']=='FR' else 'CHF')}\n"

    resume += f"Total : {total} {('€' if context.user_data['pays']=='FR' else 'CHF')}"

    keyboard = [
        [InlineKeyboardButton("Ajouter un produit", callback_data="add_product")],
        [InlineKeyboardButton("Confirmer la commande", callback_data="confirm")],
        [InlineKeyboardButton("Annuler", callback_data="Annuler")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(resume, reply_markup=reply_markup)
    return CONFIRMATION

# --- Confirmation / Ajouter produit ---
async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "Annuler":
        await query.message.reply_text("Commande annulée.")
        return ConversationHandler.END

    if query.data == "add_product":
        keyboard = [
            [InlineKeyboardButton("❄️", callback_data="❄️")],
            [InlineKeyboardButton("💊", callback_data="💊")],
            [InlineKeyboardButton("🫒", callback_data="🫒")],
            [InlineKeyboardButton("🍀", callback_data="🍀")],
            [InlineKeyboardButton("Annuler", callback_data="Annuler")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Sélectionnez un produit supplémentaire :", reply_markup=reply_markup)
        return PRODUIT

    if query.data == "confirm":
        total = context.user_data['montant']
        produits = context.user_data['produits']
        adresse = context.user_data['adresse']
        pays = context.user_data['pays']
        livraison = context.user_data['livraison']
        paiement = context.user_data['paiement']
        prix_dict = PRIX_FR if pays == "FR" else PRIX_CH

        resume = f"Résumé de votre commande :\nPays : {pays}\nAdresse : {adresse}\nLivraison : {livraison}\nPaiement : {paiement}\nProduits :\n"

        for item in produits:
            resume += f"• {item['produit']} — {item['quantite']}g — {item['quantite']*prix_dict[item['produit']]} {('€' if pays=='FR' else 'CHF')}\n"

        resume += f"Total : {total} {('€' if pays=='FR' else 'CHF')}"

        if paiement == "Crypto":
            await query.message.reply_text(resume + f"\nVeuillez payer sur ce portefeuille BTC : {CRYPTO_WALLET}")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"Nouvelle commande crypto :\n{resume}")
        else:
            await query.message.reply_text(resume + "\nVous paierez à la livraison")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"Nouvelle commande espèces :\n{resume}")

        await query.message.reply_text("✅ Commande confirmée, merci !")
        return ConversationHandler.END

# --- Annuler ---
async def annuler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Commande annulée.")
    return ConversationHandler.END

# --- Main ---
if __name__ == "__main__":
    application = ApplicationBuilder().token(TOKEN).build()

    # Ajout du handler pour /start
    application.add_handler(CommandHandler("start", start_command))

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(choix_pays, pattern="start_order")],
        states={
            PAYS: [CallbackQueryHandler(set_pays)],
            PRODUIT: [CallbackQueryHandler(choix_produit)],
            QUANTITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)],
            ADRESSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_adresse)],
            LIVRAISON: [CallbackQueryHandler(choix_livraison)],
            PAIEMENT: [CallbackQueryHandler(choix_paiement)],
            CONFIRMATION: [CallbackQueryHandler(confirmation)],
        },
        fallbacks=[CallbackQueryHandler(annuler, pattern="Annuler")],
        per_message=False
    )

    application.add_handler(conv_handler)

    print("🤖 Bot en ligne...")
    application.run_polling()
