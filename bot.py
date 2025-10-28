import os
import json
import requests
from datetime import datetime
import calendar
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ---------------- Загрузка токенов ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")
YANDEX_DIR = os.getenv("YANDEX_DIR", "BudgetBot")

# ---------------- Работа с Яндекс.Диском ----------------
def upload_to_yandex(filename, data):
    url = f'https://cloud-api.yandex.net/v1/disk/resources/upload?path={YANDEX_DIR}/{filename}&overwrite=true'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    r = requests.get(url, headers=headers).json()
    upload_url = r['href']
    requests.put(upload_url, data=json.dumps(data).encode('utf-8'))

def download_from_yandex(filename):
    url = f'https://cloud-api.yandex.net/v1/disk/resources/download?path={YANDEX_DIR}/{filename}'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    r = requests.get(url, headers=headers).json()
    download_url = r['href']
    resp = requests.get(download_url)
    return json.loads(resp.content)

# ---------------- Шаблон нового месяца ----------------
def new_month_template(month: str, year: int):
    return {
        'month': month,
        'year': year,
        'expenses': [
            {'emoji': '🎁', 'name': 'Подарок', 'amount': 0},
            {'emoji': '🏠', 'name': 'Ипотека', 'amount': 0},
            {'emoji': '💳', 'name': 'Кредиты', 'amount': 0},
            {'emoji': '📌', 'name': 'Долг Гоше', 'amount': 0},
            {'emoji': '🏢', 'name': 'Коммуналка', 'amount': 0},
            {'emoji': '🚌', 'name': 'Проездной', 'amount': 0},
            {'emoji': '🧪', 'name': 'Анализы ВНЖ', 'amount': 0},
            {'emoji': '🛁', 'name': 'Акрил ванны', 'amount': 0},
            {'emoji': '🚗', 'name': 'Проезд', 'amount': 0},
            {'emoji': '🍴', 'name': 'Еда в офисе', 'amount': 0},
            {'emoji': '💄', 'name': 'Бьюти', 'amount': 0},
            {'emoji': '📝', 'name': 'Англ. язык', 'amount': 0},
            {'emoji': '💅', 'name': 'Косметика', 'amount': 0},
        ],
        'income': [],
        'last_message_id': None,
        'awaiting_emoji': None
    }

# ---------------- Генерация текста шаблона ----------------
def generate_template_text(data):
    text = f"💸 Расходы/Доходы {data['month']} {data['year']}\n\n"
    for idx, exp in enumerate(data['expenses'], 1):
        text += f"{idx}. {exp['emoji']} {exp['name']} — {exp['amount']} ₽\n"
    text += "\n💰 Доходы\n"
    if data['income']:
        for idx, inc in enumerate(data['income'], 1):
            text += f"{idx}. {inc['name']} — {inc['amount']} ₽\n"
    else:
        text += "Доходов пока нет\n"
    return text

# ---------------- Telegram ----------------
def start(update: Update, context: CallbackContext):
    now = datetime.now()
    month_name = now.strftime('%B')
    year = now.year
    filename = f'budget_{month_name}_{year}.json'

    # создаём новый месяц, если файла нет
    try:
        data = download_from_yandex(filename)
    except:
        data = new_month_template(month_name, year)
        upload_to_yandex(filename, data)

    update.message.reply_text(
        "Привет! Бот бюджета запущен.\n"
        "Используй команды:\n"
        "- новый месяц\n"
        "- расход <сумма> <название>\n"
        "- доход <сумма> <название>\n"
        "- редактировать <месяц> <год>\n"
        "- удали <название>"
    )

def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    chat_id = update.message.chat_id
    now = datetime.now()
    month_name = now.strftime('%B')
    year = now.year
    filename = f'budget_{month_name}_{year}.json'

    # загружаем данные
    try:
        data = download_from_yandex(filename)
    except:
        data = new_month_template(month_name, year)

    ltext = text.lower()

    # --------- Новый месяц ----------
    if ltext.startswith('новый месяц'):
        month_index = now.month
        year_new = now.year
        if month_index == 12:
            next_month_index = 1
            year_new += 1
        else:
            next_month_index = month_index + 1
        next_month_name = calendar.month_name[next_month_index]
        data = new_month_template(next_month_name, year_new)
        filename = f'budget_{next_month_name}_{year_new}.json'
        upload_to_yandex(filename, data)
        update.message.reply_text(f'Создан новый месяц: {next_month_name} {year_new}')

    # --------- Добавление расхода ----------
    elif ltext.startswith('расход'):
        parts = text.split()
        if len(parts) < 3:
            update.message.reply_text('Ошибка формата. Используй: расход <сумма> <название>')
            return
        try:
            amount = int(parts[1])
            name = parts[2]
            account = ' '.join(parts[3:]) if len(parts) > 3 else ''
        except:
            update.message.reply_text('Ошибка формата. Используй: расход <сумма> <название>')
            return
        # Новый расход → ждём смайлик
        data['awaiting_emoji'] = {'name': name, 'amount': amount, 'account': account}
        update.message.reply_text(f'Введите смайлик для нового расхода "{name}"')

    # --------- Обработка смайлика ----------
    elif data.get('awaiting_emoji'):
        emoji = text[0]
        new_exp = data['awaiting_emoji']
        data['expenses'].append({
            'name': new_exp['name'],
            'amount': new_exp['amount'],
            'emoji': emoji,
            'account': new_exp['account']
        })
        data['awaiting_emoji'] = None
        update.message.reply_text(f'Расход "{new_exp["name"]}" добавлен с смайликом {emoji}')

    # --------- Добавление дохода ----------
    elif ltext.startswith('доход'):
        parts = text.split()
        if len(parts) < 2:
            update.message.reply_text('Ошибка формата. Используй: доход <сумма> <название>')
            return
        try:
            amount = int(parts[1])
            name = ' '.join(parts[2:]).strip()
            if not name:
                name = "Доход"
        except:
            update.message.reply_text('Ошибка формата. Используй: доход <сумма> <название>')
            return
        for inc in data['income']:
            if inc['name'] == name:
                inc['amount'] += amount
                break
        else:
            data['income'].append({'name': name, 'amount': amount})
        update.message.reply_text(f'Добавлен новый доход "{name}"')

    # --------- Генерация и отправка шаблона ----------
    template_text = generate_template_text(data)
    if data.get('last_message_id'):
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=data['last_message_id'])
        except:
            pass
    msg = update.message.reply_text(template_text)
    data['last_message_id'] = msg.message_id

    # --------- Сохраняем на Яндекс.Диск ----------
    upload_to_yandex(filename, data)

def main():
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
