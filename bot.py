import os
import json
import datetime
import requests
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, MessageHandler, Filters
from dotenv import load_dotenv

load_dotenv()

# --- Конфигурация ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")
WEBHOOK_URL = f"{os.getenv('RAILWAY_URL')}/{TOKEN}"
DATA_FILE = "budget_data.json"

bot = Bot(token=TOKEN)
app = Flask(__name__)

# --- Хранилище данных ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def upload_to_yandex(filename, data):
    url = "https://cloud-api.yandex.net/v1/disk/resources/upload"
    params = {"path": filename, "overwrite": "true"}
    headers = {"Authorization": f"OAuth {YANDEX_TOKEN}"}
    r = requests.get(url, headers=headers, params=params).json()
    href = r.get("href")
    if href:
        requests.put(href, data=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

# --- Основной шаблон ---
TEMPLATE = """💸 Расходы/Доходы {month}
1. 🎁 Подарок — ₽
2. 🏠 Ипотека — ₽
3. 💳 Кредиты — ₽
4. 📌 Долг Гоше — ₽
5. 🏢 Коммуналка — ₽
6. 🚌 Проездной — ₽
7. 🧪 Анализы ВНЖ — ₽
8. 🛁 Акрил ванны — ₽
9. 🚗 Проезд — ₽
10. 🍴 Еда в офисе (средн. ₽ в день) — ₽
11. 💄 Бьюти — ₽
12. 📝 Англ. язык — ₽
13. 💅 Косметика — ₽

Итог: ₽

💰 Зарплаты

Зарплата
• Доход: ₽
• Расходы: п.
• Остаток: ₽

Аванс
• Доход: ₽
• Расходы: п.
• Остаток: ₽

Дополнительные доходы
• Доход: ₽
• Расходы: п.
• Остаток: ₽

🧾 Итог месяца
• Общий доход: ₽
• Общие расходы: ₽
• Остаток: ₽
"""

# --- Обработка сообщений ---
def handle_message(update: Update, context):
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    month = datetime.datetime.now().strftime("%B %Y")
    data = load_data()

    if user_id not in data:
        data[user_id] = {"month": month, "expenses": [], "incomes": []}
        update.message.reply_text(TEMPLATE.format(month=month))
        save_data(data)
        upload_to_yandex(f"{user_id}_budget.json", data)
        return

    user_data = data[user_id]

    if text.lower().startswith("расход"):
        try:
            value = int(text.split()[1])
            user_data["expenses"].append(value)
            update.message.reply_text(f"Добавлен расход: {value} ₽")
        except:
            update.message.reply_text("❌ Формат: Расход 1000")
    elif text.lower().startswith("доход"):
        try:
            value = int(text.split()[1])
            user_data["incomes"].append(value)
            update.message.reply_text(f"Добавлен доход: {value} ₽")
        except:
            update.message.reply_text("❌ Формат: Доход 5000")
    else:
        update.message.reply_text("Введите 'Доход 5000' или 'Расход 1000'")

    save_data(data)
    upload_to_yandex(f"{user_id}_budget.json", data)

# --- Flask webhook ---
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return "Бот работает!", 200

# --- Инициализация Telegram Dispatcher ---
from telegram.ext import Dispatcher
dispatcher = Dispatcher(bot, None, workers=0)
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# --- Запуск ---
if __name__ == "__main__":
    bot.delete_webhook()
    bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook установлен: {WEBHOOK_URL}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
