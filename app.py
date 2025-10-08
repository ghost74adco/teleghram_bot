from flask import Flask, render_template, request, jsonify
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Telegram Bot Mini App</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #0088cc;
            }
            .status {
                padding: 10px;
                background-color: #d4edda;
                border-left: 4px solid #28a745;
                margin: 20px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Telegram Bot Mini App</h1>
            <div class="status">
                ✅ L'application est en ligne et fonctionne !
            </div>
            <p>Bienvenue sur la mini app de votre bot Telegram.</p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "Mini app is running"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
