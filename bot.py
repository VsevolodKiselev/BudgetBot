import os
import json
import requests
import calendar
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ---------------- Переменные окружения ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")
YANDEX_DIR = os.getenv("YANDEX_DIR") or "BudgetBot"

# ---------------- Работа с Яндекс.Диском ----------------
def upload_to_yandex(filename, data):
    url = f'https://cloud-api.yandex.net/v1/disk/resources/upload?path={YANDEX_DIR}/{filename}&overwrite=true'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    r = requests.get(url, headers=headers).json()
    if 'href' not in r:
        raise Exception(f"Ошибка загрузки на Яндекс.Диск: {r}")
    upload_url = r['href']
    requests.put(upload_url, data=json.dumps(data).encode('utf-8'))

def download_from_yandex(filename):
    url = f'https://cloud-api.yandex.net/v1/disk/resources/download?path={YANDEX_DIR}/{filename}'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    r = requests.get(url, headers=headers).json()
    if 'href' not in r:
        return None  # файла нет
    download_url = r['href']
    resp = requests.get(download_url)
    return json.loads(resp.content)

# ---------------- Шаблон бюджета ----------------
def new_month_template(month: str, year: int):
    expenses = [
        {"emoji": "🎁", "name": "Подарок", "amount": 0},
        {"emoji": "🏠", "name": "Ипотека", "amount": 0},
        {"emoji": "💳", "name": "Кредиты", "amount": 0},
        {"emoji": "📌", "name": "Долг Гоше", "amount": 0},
        {"emoji": "🏢", "name": "Коммуналка", "amount": 0},
        {"emoji": "🚌", "name": "Проездной", "amount": 0},
        {"emoji": "🧪", "name": "Анализы ВНЖ", "amount": 0},
        {"emoji": "🛁", "name": "Акрил ванны", "amount": 0},
        {"emoji": "🚗", "name": "Проезд", "amount": 0},
        {"emoji": "🍴", "name": "Еда в офисе (средн. ₽ в день)", "amount": 0},
        {"emoji": "💄", "name": "Бьюти", "amount": 0},
        {"emoji": "📝", "name": "Англ. язык", "amount": 0},
        {"emoji": "💅", "name": "Косметика", "amount": 0},
    ]
    income = [
        {"name": "Зарплата", "amount": 0},
        {"name": "Аванс", "amount": 0},
        {"name": "Дополнительные доходы", "amount": 0},
    ]
    return {
        "month": month,
        "year": year,
        "expenses": expenses,
        "income": income,
        "awaiting_emoji": None,
    }

# ---------------- Генерация текста шаблона ----------------
def generate_template_text(data):
    text = f"💸 Расходы/Доходы {data['month']} {data['year']}\n\n"
    for idx, exp in enumerate(data['expenses'], 1):
        text += f"{idx}. {exp['emoji']} {exp['name']} — {exp['amount']} ₽\n"
    text += "\n💰 Доходы\n"
    for inc in data['income']:
        text += f"{inc['name']} — {inc['amount']} ₽\n"
    return text

# ---------------- Telegram ----------------
def start(update: Update, context: CallbackContext):
    now = datetime.now()
    month_name = now.strftime("%B")
    year = now.year
    filename = f"budget_{month_name}_{year}.json"
    data = download_from_yandex(filename) or new_month_template(month_name, year)
    upload_to_yandex(filename, data)
    update.message.reply_text(
        "Привет! Бот бюджета запущен.\n\n" + generate_template_text(data)
    )

def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    now = datetime.now()
    month_name = now.strftime("%B")
    year = now.year
    filename = f"budget_{month_name}_{year}.json"
    data = download_from_yandex(filename) or new_month_template(month_name, year)

    if text.startswith("расход"):
        parts = update.message.text.split()
        if len(parts) < 3:
            update.message.reply_text(
                'Ошибка формата. Используй: расход <сумма> <название>'
            )
            return
        try:
            amount = int(parts[1])
        except:
            update.message.reply_text("Сумма должна быть числом")
            return
        name = " ".join(parts[2:])
        # ищем расход
        for exp in data['expenses']:
            if exp['name'].lower() == name.lower():
                exp['amount'] += amount
                break
        else:
            update.message.reply_text("Такого расхода нет в шаблоне")
            return
        upload_to_yandex(filename, data)
        update.message.reply_text(f"Добавлен расход {name} — {amount} ₽")

    elif text.startswith("доход"):
        parts = update.message.text.split()
        if len(parts) < 2:
            update.message.reply_text(
                'Ошибка формата. Используй: доход <сумма> <название>'
            )
            return
        try:
            amount = int(parts[1])
        except:
            update.message.reply_text("Сумма должна быть числом")
            return
        name = " ".join(parts[2:]) if len(parts) > 2 else parts[1]
        for inc in data['income']:
            if inc['name'].lower() == name.lower():
                inc['amount'] += amount
                break
        else:
            data['income'].append({"name": name, "amount": amount})
        upload_to_yandex(filename, data)
        update.message.reply_text(f"Добавлен доход {name} — {amount} ₽")

    update.message.reply_text(generate_template_text(data))

def main():
    from telegram.ext import Dispatcher, CallbackContext
    from telegram import Bot
    from flask import Flask, request

    app = Flask(__name__)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(bot, None, workers=0)

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    @app.route(f"/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        update = Update.de_json(request.get_json(force=True), bot)
        dp.process_update(update)
        return "ok"

    @app.route("/")
    def index():
        return "Бот работает!"

    # Устанавливаем webhook (замени <URL> на ссылку Railway)
    WEBHOOK_URL = f"https:///railway.com/project/2f7afa43-e7fd-4079-8e2a-4636172245b9/service/b3b06929-351b-42be-b6e3-5d629708b5d8?environmentId=f1ed4dff-52d5-4e5d-839f-1358865809b9/{BOT_TOKEN}"
    bot.set_webhook(WEBHOOK_URL)

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if __name__ == "__main__":
    main()
