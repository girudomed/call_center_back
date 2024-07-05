import datetime as dt

# Параметры

START_DATE = '2024-06-16 00:00:00'
START_DATE_DT = dt.datetime.strptime('2024-06-16 00:00:00', '%Y-%m-%d %H:%M:%S').timestamp()
print(int(START_DATE_DT+3*60*60*60))

# date_timeA = timestamp('')
# SELECT `id`, `call_...` WHERE `context_call` BETWEEN 'date_timeA' AND 'date_timeB' LIMIT LIMIT

#скопирвоал из того файла, что Сергей комментил
##RETRIES = 3
#START_DATE = '2023-06-16 00:00:00'
#START_DATE_DT = dt.datetime.strptime('2023-06-16 00:00:00').timestamp()
#BATCH_SIZE = 30
#ENABLE_LOGGING = True
# date_timeA = timestamp('')
# SELECT `id`, `call_...` WHERE `context_call` BETWEEN 'date_timeA' AND 'date_timeB' LIMIT LIMIT
# Настройка логирования
###logger = setup_logging(ENABLE_LOGGING)

# Функция для подключения к базе данных SQLite
#async def get_db_connection():