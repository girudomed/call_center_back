import time
import os

# Путь к файлу сканирования
SCAN_LOG_PATH = 'scaning_all_system.log'

def check_and_create_log_file():
    """Создание файла лога, если он не существует."""
    if not os.path.isfile(SCAN_LOG_PATH):
        with open(SCAN_LOG_PATH, 'w') as file:
            file.write("Время начала, Время окончания, Продолжительность (сек.), Дополнительная информация\n")

def monitor_performance(start_time, additional_info):
    """Сбор данных о производительности и запись в лог."""
    end_time = time.time()
    elapsed_time = end_time - start_time

    performance_data = {
        "Время начала": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time)),
        "Время окончания": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time)),
        "Продолжительность (сек.)": f"{elapsed_time:.2f}",
        "Дополнительная информация": additional_info
    }

    with open(SCAN_LOG_PATH, 'a') as file:
        file.write(f"{performance_data['Время начала']}, {performance_data['Время окончания']}, {performance_data['Продолжительность (сек.)']}, {performance_data['Дополнительная информация']}\n")

    print("Лог производительности обновлен.")
