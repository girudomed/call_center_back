import os

# Ручной код для очистки логов, если автоматическая не работает. Определяем текущий каталог, в котором находится скрипт
current_directory = os.path.dirname(os.path.abspath(__file__))

# Определяем путь к файлу логов относительно текущего каталога
log_file_path = os.path.join(current_directory, 'analyze_calls.log')

# Очищаем файл логов
with open(log_file_path, 'w') as file:
    pass  # Это действие очистит файл
# команда для запуска скрипта: /opt/anaconda3/envs/myenv/bin/python /Users/vitalyefimov/Projects/call_center/clear_logs.py
