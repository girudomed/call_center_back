#data_processing.py
###Этот модуль работает с чек-листами. Мы через метод def get_checklist_data получаем чек листы из БД
### Модуль gpt_config.py не получает чек листы напрямую (там не содержится метод), он их получает через аргумент
### weight_criteria удалили отсюда как сам параметр, к нему не обращаемся

import logging
from datetime import datetime
import aiomysql
from mysql.connector import Error
logger = logging.getLogger()

###Этот метод работает с чек-листами. Мы через метод def get_checklist_data получаем чек листы из БД
async def get_checklist_data(pool, category_number):
    if category_number is None:
        logger.warning("Категорийный номер не определен.")
        return None, "Не определено"
    
    logger.info(f"Получение чек-листа для категории: {category_number}")
    query = """
        SELECT Number_check_list, Check_list_categories, description, criteria_check_list, type_criteria, criterion_category, scoring_method, fatal_error, max_score
        FROM check_list 
        WHERE Check_list_categories = (
            SELECT Call_categories 
            FROM categories 
            WHERE Number = %s
        )
        """
    try:
        async with pool.get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, (category_number,))
                checklist = await cursor.fetchall()
                if checklist:
                    return checklist[0]['Number_check_list'], checklist[0]['Info_check_list']
                else:
                    logger.warning("Чек-лист не найден.")
                    return None, "Не определено"
    except Error as e:
        logger.error(f"Ошибка при получении данных чек-листа: {e}")
        return None, "Не определено"
    except Exception as e:
        logger.error(f"Неизвестная ошибка при получении чек-листа: {e}")
        return None, "Не определено"
    
async def save_call_score(pool, call_id, score, call_category, call_date, called_info, 
                          caller_info, talk_duration, transcript, result, 
                          category_number, checklist_number, checklist_category):
    """Сохранение данных звонка в базу."""
    required_fields = [call_id, score, call_date, called_info, caller_info, 
                       talk_duration, transcript, result, category_number, 
                       checklist_number, checklist_category]
    missing_fields = [field for field, value in zip(
        ["call_id", "score", "call_date", "called_info", "caller_info", 
         "talk_duration", "transcript", "result", "category_number", 
         "checklist_number", "checklist_category"], required_fields
    ) if not value]
    if missing_fields:
        logger.warning(f"Отсутствуют значения для полей: {missing_fields}")
        return

    logger.info(f"Сохранение данных звонка: {call_id} с оценкой {score}")
    query = """
    INSERT INTO call_scores (history_id, call_score, score_date, call_date, call_category, 
                             called_info, caller_info, talk_duration, transcript, result, 
                             number_category, number_checklist, category_checklist)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        async with pool.get_connection() as connection:
            async with connection.cursor() as cursor:
                score_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                await cursor.execute(query, (
                    call_id, score, score_date, call_date, str(call_category), 
                    str(called_info), str(caller_info), str(talk_duration), 
                    str(transcript), str(result), category_number, 
                    checklist_number, checklist_category
                ))
                await connection.commit()
                logger.info("Данные звонка успешно сохранены в call_scores")
    except Error as e:
        logger.error(f"Ошибка при сохранении данных звонка: {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при сохранении данных звонка: {e}")


# Функция для получения последнего записанного звонка
async def fetch_last_recorded_call(pool, config):
    """Получение последнего записанного звонка."""
    logger.info("Получение последнего записанного звонка")
    
    # Используем START_DATE из config
    query = f"""
    SELECT history_id, call_score, call_category, call_date, called_info, 
           caller_info, talk_duration, transcript, result 
    FROM call_scores 
    WHERE call_date >= '{config['START_DATE']}'
    ORDER BY id DESC
    """
    try:
        async with pool.get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query)
                result = await cursor.fetchall()
                if result:
                    for recorded_call in result:
                        logger.debug(f"Записанный звонок: ID {recorded_call['history_id']} с оценкой {recorded_call['call_score']}")
                    return result
                else:
                    logger.info("Нет записанных звонков за указанный период.")
                    return None
    except aiomysql.Error as e:
        logger.error(f"Ошибка при получении записанных звонков: {e}")
        return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка при получении записанных звонков: {e}")
        return None