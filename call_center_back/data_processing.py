import logging
from datetime import datetime
from mysql.connector import Error
from db_connection import create_connection, execute_query, close_connection

logger = logging.getLogger()

def get_checklist_data(category_number):
    if category_number is None:
        logger.warning("Категорийный номер не определен.")
        return None, "Не определено"
    
    logger.info(f"Получение чек-листа для категории: {category_number}")
    connection = create_connection()
    if connection:
        try:
            query = """
            SELECT Number_check_list, Check_list_categories, Info_check_list 
            FROM check_list 
            WHERE Check_list_categories = (
                SELECT Call_categories 
                FROM categories 
                WHERE Number = %s
            )
            """
            checklist = execute_query(connection, query, (category_number,))
            if checklist:
                return checklist[0]['Number_check_list'], checklist[0]['Info_check_list']
        except Error as e:
            logger.error(f"Произошла ошибка '{e}' при получении данных чек-листа")
        finally:
            close_connection(connection)
    return None, "Не определено"

def save_call_score(connection, call_id, score, call_category, call_date, called_info, caller_info, talk_duration, transcript, result, category_number, checklist_number, checklist_category):
    if not all([call_id, score, call_date, called_info, caller_info, talk_duration, transcript, result, category_number, checklist_number, checklist_category]):
        logger.warning("Одно или несколько полей данных звонка отсутствуют.")
        return
    
    logger.info(f"Попытка сохранения данных звонка: {call_id} с оценкой {score}, call_category {call_category}, call_date {call_date}, called_info {called_info}, caller_info {caller_info}, talk_duration {talk_duration}, transcript и result")
    cursor = connection.cursor()
    try:
        score_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Данные для вставки: history_id={call_id}, call_score={str(score)}, score_date={score_date}, call_date={call_date}, call_category={str(call_category)}, called_info={str(called_info)}, caller_info={str(caller_info)}, talk_duration={str(talk_duration)}, transcript={str(transcript)}, result={str(result)}, number_category={str(category_number)}, number_checklist={str(checklist_number)}, category_checklist={str(checklist_category)}")

        insert_score_query = """
        INSERT INTO call_scores (history_id, call_score, score_date, call_date, call_category, called_info, caller_info, talk_duration, transcript, result, number_category, number_checklist, category_checklist)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_score_query, (call_id, str(score), score_date, call_date, str(call_category), str(called_info), str(caller_info), str(talk_duration), str(transcript), str(result), str(category_number), str(checklist_number), str(checklist_category)))
        connection.commit()
        logger.info("Данные звонка успешно сохранены в call_scores")
    except Error as e:
        logger.error(f"Произошла ошибка '{e}' при сохранении данных звонка")
        connection.rollback()
    finally:
        cursor.close()

def fetch_last_recorded_call(connection):
    logger.info("Попытка получения последнего записанного звонка")
    try:
        query = """
        SELECT history_id, call_score, call_category, call_date, called_info, caller_info, talk_duration, transcript, result 
        FROM call_scores 
        WHERE call_date >= '2023-06-16 00:00:00'
        ORDER BY id DESC
        """
        result = execute_query(connection, query)
        if result:
            for recorded_call in result:
                logger.info(f"Записанный звонок: ID {recorded_call['history_id']} с оценкой {recorded_call['call_score']}, call_category {recorded_call['call_category']}, call_date {recorded_call['call_date']}, called_info {recorded_call['called_info']}, caller_info {recorded_call['caller_info']}, talk_duration {recorded_call['talk_duration']}, transcript {recorded_call['transcript']} и result {recorded_call['result']}")
            return result
        else:
            logger.info("Не удалось получить записанные звонки")
            return None
    except Error as e:
        logger.error(f"Произошла ошибка '{e}' при получении записанных звонков")
        return None

# Пример использования функций:
if __name__ == "__main__":
    connection = create_connection()
    if connection:
        get_checklist_data(1)
        fetch_last_recorded_call(connection)
        close_connection(connection)
