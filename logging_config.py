#logging_config.py
import logging
import os

LOG_FILE = 'analyze_calls.log'
MAX_LOG_LINES = 50000

def setup_logging(enable_logging=True):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO if enable_logging else logging.CRITICAL)
    
    # Создаем обработчик для файла логов
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # Создаем обработчик для вывода в консоль
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # Добавляем обработчики к логгеру
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def check_and_clear_logs():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r') as f:
                lines = f.readlines()
                if len(lines) > MAX_LOG_LINES:
                    with open(LOG_FILE, 'w') as f:
                        f.truncate(0)
                    logging.info("Файл логов очищен, так как превышен лимит в 50 000 строк.")
        except Exception as e:
            logging.exception(f"Ошибка при проверке и очистке логов: {e}")

def clear_logs():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'w') as f:
                f.truncate(0)
            logging.info(f"Файл логов {LOG_FILE} успешно очищен.")
        except Exception as e:
            logging.exception(f"Ошибка при очистке логов: {e}")
