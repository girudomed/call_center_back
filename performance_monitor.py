import time
import os
import psutil
from datetime import datetime
import traceback
from termcolor import colored
import platform

try:
    import GPUtil
except ImportError:
    GPUtil = None  # Если библиотека не установлена, не используем её

# Пути к файлам логов
SCAN_LOG_PATH = 'scaning_all_system.log'
ERROR_LOG_PATH = 'error_log.log'

# Пороговые значения
CPU_THRESHOLD = 70.0  # %
MEMORY_THRESHOLD = 70.0  # %
TEMPERATURE_THRESHOLD = 70.0  # C

# Проверка модели MacBook
system_info = platform.uname()
if "MacBookAir5,2" in system_info.machine:
    print(colored("Система работает на MacBook Air 2012 года. Пороговые значения будут снижены для защиты системы.", 'yellow'))

def check_and_create_log_file():
    """Создание файла лога, если он не существует."""
    if not os.path.isfile(SCAN_LOG_PATH):
        with open(SCAN_LOG_PATH, 'w') as file:
            headers = [
                "Время начала", "Время окончания", "Продолжительность (сек.)", "CPU (%)", "Memory (%)", "Disk (%)", "GPU (%)", "GPU Memory (%)", "Температура (C)", "Дополнительная информация"
            ]
            file.write(f"{headers[0]:<20} {headers[1]:<20} {headers[2]:<25} {headers[3]:<10} {headers[4]:<10} {headers[5]:<10} {headers[6]:<10} {headers[7]:<15} {headers[8]:<15} {headers[9]:<30}\n")
    if not os.path.isfile(ERROR_LOG_PATH):
        with open(ERROR_LOG_PATH, 'w') as file:
            file.write("Время, Ошибка\n")

def get_system_performance():
    """Сбор данных о производительности системы."""
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage('/').percent
    temperatures = psutil.sensors_temperatures()
    temperature = temperatures['coretemp'][0].current if 'coretemp' in temperatures else 'N/A'

    gpu_usage = 'N/A'
    gpu_memory_usage = 'N/A'

    if GPUtil:
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]
            gpu_usage = gpu.load * 100
            gpu_memory_usage = gpu.memoryUtil * 100

    return {
        "CPU (%)": cpu_usage,
        "Memory (%)": memory_usage,
        "Disk (%)": disk_usage,
        "GPU (%)": gpu_usage,
        "GPU Memory (%)": gpu_memory_usage,
        "Температура (C)": temperature
    }

def log_error(error_message):
    """Запись ошибки в лог."""
    with open(ERROR_LOG_PATH, 'a') as file:
        file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, {error_message}\n")

def monitor_performance():
    """Сбор данных о производительности и запись в лог."""
    try:
        start_time = time.time()
        additional_info = "Мониторинг системы"
        performance_data = get_system_performance()
        end_time = time.time()
        elapsed_time = end_time - start_time

        warnings = []
        if performance_data["CPU (%)"] > CPU_THRESHOLD:
            warnings.append(f"Warning: CPU usage is very high: {performance_data['CPU (%)']}%")
        if performance_data["Memory (%)"] > MEMORY_THRESHOLD:
            warnings.append(f"Warning: Memory usage is very high: {performance_data['Memory (%)']}%")
        if performance_data["Температура (C)"] != 'N/A' and performance_data["Температура (C)"] > TEMPERATURE_THRESHOLD:
            warnings.append(f"Warning: Temperature is very high: {performance_data['Температура (C)']}C")

        if warnings:
            additional_info = " | ".join(warnings)

        performance_data.update({
            "Время начала": datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S'),
            "Время окончания": datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S'),
            "Продолжительность (сек.)": f"{elapsed_time:.2f}",
            "Дополнительная информация": additional_info
        })

        with open(SCAN_LOG_PATH, 'a') as file:
            file.write(
                f"{performance_data['Время начала']:<20} {performance_data['Время окончания']:<20} {performance_data['Продолжительность (сек.)']:<25} {performance_data['CPU (%)']:<10} {performance_data['Memory (%)']:<10} {performance_data['Disk (%)']:<10} {performance_data['GPU (%)']:<10} {performance_data['GPU Memory (%)']:<15} {performance_data['Температура (C)']:<15} {performance_data['Дополнительная информация']:<30}\n"
            )

        print("Лог производительности обновлен.")

        # Вывод предупреждений в консоль
        for warning in warnings:
            print(colored(warning, 'red'))

    except Exception as e:
        error_message = traceback.format_exc()
        log_error(error_message)
        print(colored("Ошибка при обновлении лога производительности. Подробности в error_log.log.", 'red'))

if __name__ == "__main__":
    check_and_create_log_file()
    while True:
        try:
            monitor_performance()
            time.sleep(30)  # Интервал между проверками (например, каждые 30 секунд)
        except KeyboardInterrupt:
            print("Мониторинг остановлен.")
            break
        except Exception as e:
            error_message = traceback.format_exc()
            log_error(error_message)
            print(colored("Неожиданная ошибка. Подробности в error_log.log.", 'red'))
