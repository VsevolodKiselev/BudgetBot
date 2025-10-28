import os
import json
import requests
from datetime import datetime
import calendar
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

BOT_TOKEN = os.environ['BOT_TOKEN']
YANDEX_TOKEN = os.environ['YANDEX_TOKEN']
YANDEX_DIR = 'BudgetBot'  # папка на Яндекс.Диске

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

# ---------------- Шаблон бюджета ----------------
def new_month_template(month: str, year: int):
    return {
        'month': month,
        'year': year,
        'expenses': [],
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
    for idx, inc in enumerate(data['income'], 1):
        text += f"{idx}. {inc['name']} — {inc['amount']} ₽\n"
    return text

# ---------------- Telegram ----------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text('Привет! Бот бюджета запущен. Вводи команды для расходов, доходов и месяца.')

def handle_message(update: Update, context: CallbackContext):
    text = update.message.text
    chat_id = update.message.chat_id
    now = datetime.now()
    month_name = now.strftime('%B')
    year = now.year
    filename = f'budget_{month_name}_{year}.json'

    # Проверяем есть ли файл на Яндекс.Диске
    try:
        data = download_from_yandex(filename)
    except:
        data = new_month_template(month_name, year)

    # --------- Ожидание смайлика для нового расхода ----------
    if data.get('awaiting_emoji'):
        emoji = text.strip()[0]  # первый символ как смайлик
        new_exp = data['awaiting_emoji']
        data['expenses'].append({
            'name': new_exp['name'],
            'amount': new_exp['amount'],
            'emoji': emoji,
            'account': new_exp['account']
        })
        data['awaiting_emoji'] = None
        update.message.reply_text(f'Расход "{new_exp["name"]}" добавлен с смайликом {emoji}')

    else:
        ltext = text.lower()

        # --------- Новый месяц (авто следующий) ----------
        if ltext.startswith('новый месяц'):
            # Определяем текущий месяц и год
            month_index = now.month
            year_new = now.year

            # Следующий месяц
            if month_index == 12:
                next_month_index = 1
                year_new += 1
            else:
                next_month_index = month_index + 1

            next_month_name = calendar.month_name[next_month_index]
            month_name = next_month_name

            # Создаём новый шаблон
            data = new_month_template(month_name, year_new)
            filename = f'budget_{month_name}_{year_new}.json'

            # Отправляем пользователю сообщение
            update.message.reply_text(f'Создан новый месяц: {month_name} {year_new}')

        # --------- Редактировать месяц ----------
        elif ltext.startswith('редактировать'):
            parts = text.split()
            if len(parts) >= 3:
                month_name = parts[1]
                year = int(parts[2])
            filename = f'budget_{month_name}_{year}.json'
            try:
                data = download_from_yandex(filename)
                update.message.reply_text(f'Редактируем месяц: {month_name} {year}')
            except:
                update.message.reply_text(f'Файл для {month_name} {year} не найден')
                return

        # --------- Добавление расхода ----------
        elif ltext.startswith('расход'):
            parts = text.split()
            try:
                amount = int(parts[1])
                name = parts[2]
                account = ' '.join(parts[3:]) if len(parts) > 3 else ''
            except:
                update.message.reply_text('Ошибка формата. Используй: расход <сумма> <название> [аванс/зарплата]')
                return
            # Проверяем есть ли расход
            for exp in data['expenses']:
                if exp['name'] == name:
                    exp['amount'] += amount
                    break
            else:
                # Новый расход → ждём смайлик
                data['awaiting_emoji'] = {'name': name, 'amount': amount, 'account': account}
                update.message.reply_text(f'Введите смайлик для нового расхода "{name}"')
                upload_to_yandex(filename, data)
                return

        # --------- Удаление расхода ----------
        elif ltext.startswith('удали'):
            parts = text.split()
            if len(parts) < 2:
                update.message.reply_text('Укажи название расхода для удаления: удали <название>')
                return
            name = parts[1]
            before_len = len(data['expenses'])
            data['expenses'] = [exp for exp in data['expenses'] if exp['name'] != name]
            if len(data['expenses']) < before_len:
                update.message.reply_text(f'Расход "{name}" удалён')
            else:
                update.message.reply_text(f'Расход "{name}" не найден')

        # --------- Добавление дохода ----------
        elif ltext.startswith('доход'):
            parts = text.split()
            try:
                amount = int(parts[1])
                name = ' '.join(parts[2:])
            except:
                update.message.reply_text('Ошибка формата. Используй: доход <сумма> <название>')
                return
            for inc in data['income']:
                if inc['name'] == name:
                    inc['amount'] += amount
                    break
            else:
                data['income'].append({'name': name, 'amount': amount})

    # --------- Отправка шаблона ----------
    template_text = generate_template_text(data)
    # Удаляем старое сообщение шаблона
    if data.get('last_message_id'):
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=data['last_message_id'])
        except:
            pass
    msg = update.message.reply_text(template_text)
    data['last_message_id'] = msg.message_id

    # Сохраняем на Яндекс.Диск
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
