import logging

import requests

from app_pkg.repositories.integration_settings import load_tg_config


def send_tg_notification(message):
    tg_config = load_tg_config()
    bot_token = tg_config.get('bot_token')
    chat_id = tg_config.get('chat_id')
    if not bot_token or not chat_id:
        logging.info('Telegram bot_token或chat_id未配置，跳过发送。')
        return
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logging.info(f'Telegram消息已成功发送至 Chat ID: {chat_id}')
        else:
            logging.error(f'发送Telegram消息失败: {response.status_code} - {response.text}')
    except requests.RequestException as e:
        logging.error(f'发送Telegram消息时发生网络错误: {e}')
    except Exception as e:
        logging.error(f'发送Telegram消息时发生未知错误: {e}')
