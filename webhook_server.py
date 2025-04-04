
# webhook_server.py

from flask import Flask, request, jsonify
import stripe
import sqlite3
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz

load_dotenv()

app = Flask(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

DB_PATH = "daily_dollar.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            phone TEXT,
            password_hash TEXT NOT NULL,
            sms_opt_in BOOLEAN DEFAULT 0,
            auto_entry BOOLEAN DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_entry_date TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            entry_type TEXT CHECK(entry_type IN ('main', 'free')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS winners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            entry_type TEXT CHECK(entry_type IN ('main', 'free')),
            prize_amount REAL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()
    
def enter_daily_dollar(user_id, entry_type):
    cst = pytz.timezone('US/Central')
    now = datetime.now().astimezone(cst)
    today = now.date().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM entries WHERE user_id = ? AND date = ? AND entry_type = ?', (user_id, today, entry_type))
    if cursor.fetchone():
        conn.close()
        return

    cursor.execute('INSERT INTO entries (user_id, date, entry_type) VALUES (?, ?, ?)', (user_id, today, entry_type))

    if entry_type == 'main':
        cursor.execute('SELECT last_entry_date, streak FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        last_entry_date, streak = row if row else (None, 0)

        yesterday = (now.date() - timedelta(days=1)).isoformat()
        if last_entry_date == yesterday:
            streak += 1
        else:
            streak = 1

        cursor.execute('UPDATE users SET last_entry_date = ?, streak = ? WHERE id = ?', (today, streak, user_id))

    conn.commit()
    conn.close()

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        username = session.get('client_reference_id')

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user:
            user_id = user[0]
            # Optionally check for price ID here if you want to separate logic
            enter_daily_dollar(user_id, "main")

    return jsonify({'status': 'success'}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
