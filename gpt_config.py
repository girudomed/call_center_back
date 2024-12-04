#gpt_config.py
import openai
import logging
import re
import os
from datetime import datetime
from pymysql import Error
from dotenv import load_dotenv
import asyncio
from openai import OpenAI
client = OpenAI()
# Загрузка переменных окружения
load_dotenv()

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

# Установка API-ключа OpenAI
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    logger.error("OpenAI API key is not provided. Please set the API key in the environment variable 'OPENAI_API_KEY'.")
    raise ValueError("OpenAI API key is missing.")
else:
    openai.api_key = api_key

async def analyze_call_with_gpt(transcript, checklists):
    logger.info(f"Анализ звонка с использованием GPT для расшифровки: {transcript}")
    if not transcript:
        logger.info("Отсутствует расшифровка звонка. Пропуск анализа.")
        return None, None, None, None, None

    # Проверка структуры checklists и правильного формата
    if not isinstance(checklists, list):
        logger.error(f"Ошибка: Ожидался список, но получили {type(checklists)}. Проверьте источник данных.")
        raise ValueError(f"Ошибка: Ожидался список, но получили {type(checklists)}")

    # Проверка, что все элементы в checklists — это словари
    for i, item in enumerate(checklists):
        if not isinstance(item, dict):
            logger.error(f"Ошибка: Элемент {i} не является словарем. Получен {type(item)}")
            raise ValueError(f"Ошибка: Элемент {i} не является словарем. Получен {type(item)}")

    # Формирование списка категорий и критериев для анализа
    try:
        categories_text = "\n".join([f"{checklist['Check_list_categories']}: {checklist['criterion_category']}" for checklist in checklists])
        criteria_text = "\n".join([checklist['criteria_check_list'] for checklist in checklists])
    except KeyError as e:
        logger.error(f"Ошибка: ключ {e} не найден в checklists. Проверьте структуру данных.")
        return None, None, None, None, None
    
    ###Критерии:
    ###{criteria_text}###
    
    prompt = f"""
    Анализ звонка:
    Расшифровка звонка: {transcript}

    Пожалуйста, проведите анализ данного звонка по следующим категориям и критериям:
    Категории:
    {categories_text}


    Дайте оценку по каждому пункту от 0 до 10. Ответ необходимо дать в формате:
    "Категория звонка: <Название категории>"
    Номер категории: <Номер категории>
    <Название критерия>: <оценка>

    1. <Название критерия>: <оценка>/10 — <Подробное объяснение по данному критерию с рекомендациями при необходимости>
    2. <Название критерия>: <оценка>/10 — <Подробное объяснение по данному критерию с рекомендациями при необходимости>
    ...
    Средняя оценка: <общая оценка>/10

    Заключение: <Заключительный вывод, который суммирует впечатления о звонке>

    Рекомендации:
    1. <Рекомендация 1>
    2. <Рекомендация 2>
    ...
    """

    try:
        completion = client.chat.completions.create(
            model="ft:gpt-4o-mini-2024-07-18:personal:assistentoperators:ATrNVXNY",
            messages=[
                {"role": "system", "content": "Вы — аналитик, который помогает классифицировать звонки и оценивать их по системе критериев. "
                "Оценки выставляются по следующим критериям: инициативность оператора, успешность записи, "
                "полнота предоставленной информации, реакция на отказ, уточнение об адресе, удовлетворенность клиента. "
                "Оценки даются по шкале от 0 до 10. Если оценка выше 10, приравнивайте её к 10. "
                "Общая оценка звонка <Общая оценка звонка< call_score  вычисляется как взвешенная средняя по критериям, где каждый критерий имеет свою весомость. "
                "Ваш ответ должен следовать следующему формату: отдельные оценки с детализированными объяснениями по каждому критерию, средней оценкой, заключением и рекомендациями, как описано в сообщении пользователя. You are an analytical assistant specialized in evaluating call center interactions based on predefined criteria. Your responses provide objective feedback and scoring across multiple categories of service quality, such as greeting quality, information accuracy, politeness, and responsiveness."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.4,
            presence_penalty=0.5,
            frequency_penalty=0.5
        )
        print(completion.choices[0].message)
        result_text = completion.choices[0].message.content if completion.choices else None
        if result_text:
            result_text = result_text.strip()
        else:
            logger.error("Ответ от модели отсутствует или имеет пустое значение")
            return None, None, None, None, None
        
        # Извлечение общей оценки из текста ответа модели
        average_score_match = re.search(r'Средняя оценка: (\d+(\.\d+)?)/10', result_text)
        average_score = float(average_score_match.group(1)) if average_score_match else None

        if average_score is not None:
            logger.info(f"Извлеченная средняя оценка: {average_score}/10")
        else:
            logger.error("Не удалось извлечь среднюю оценку из ответа модели")

        # Установка `score` как извлеченного среднего значения или 0, если значение отсутствует
        score = average_score if average_score is not None else 0

        # Извлечение категории звонка
        category_match = re.search(r'Категория звонка: (.+)', result_text)
        call_category = category_match.group(1).strip() if category_match else "Не определено"

        # Извлечение номера категории
        number_category_match = re.search(r'Номер категории: (\d+)', result_text)
        category_number = int(number_category_match.group(1)) if number_category_match else None

        
        # Убираем "number_category" из call_category
        call_category_clean = re.sub(r' number_category=\d+', '', call_category).strip()

        logger.info(f"Общая оценка звонка: {score}, Категория звонка: {call_category_clean}, Номер категории: {category_number}")

        # Поиск чек-листа по номеру категории
        try:
            checklist = next((checklist for checklist in checklists if checklist.get('Number_check_list') == category_number), None)
            if checklist is None:
                logger.error("Чек-лист не найден")
                return None, None, None, None, None

            checklist_result = checklist['criteria_check_list']
        except TypeError as e:
            logger.error(f"Ошибка при поиске чек-листа: {e}")
            
            return None, None, None, None, None

        checklist_result = checklist['criteria_check_list'] if checklist else "Чек-лист не найден"

        # Генерация оценок по каждому пункту чек-листа
        criteria_scores = []
        for criterion in checklist_result.split("\n"):
            criterion = criterion.strip()
            if not criterion:
                continue  # Пропускаем пустые строки
            criterion = str(criterion)  # Преобразуем в строку или используем аннотацию типа
            # Ищем оценку по текущему критерию в тексте ответа модели
            escaped_criterion = re.escape(criterion)
            pattern = rf'{escaped_criterion}: (\d+(\.\d+)?)/10'
            criterion_score_match = re.search(pattern, result_text)
            if criterion_score_match:
                criterion_score = float(criterion_score_match.group(1))
                criteria_scores.append((criterion, criterion_score))
        # Если не требуется добавлять раздел с чек-листом и оценками, просто используем result_text
        analyzed_result = result_text

        # Формирование строки результата
        #analyzed_result = f"{result_text}\nЧек-лист и оценки:\n" + "\n".join([f"{criterion}: {score}" for criterion, score in criteria_scores])

        logger.info(f"Returning from analyze_call_with_gpt: score={score}, analyzed_result={analyzed_result}, call_category_clean={call_category_clean}, category_number={category_number}, checklist_result={checklist_result}")
        return score, analyzed_result,call_category_clean, category_number, checklist_result
    except openai.OpenAIError as e:
        logger.error(f"Ошибка при вызове OpenAI API: {e}")
        return None, None, None, None, None
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}")
        return None, None, None, None, None

async def save_call_score(connection, call_id, score, call_category, call_date, called_info, caller_info, talk_duration, transcript, result, category_number, checklist_number, checklist_category):
    if score is None or result is None:
        logger.info(f"Пропуск сохранения данных звонка: {call_id} из-за отсутствия анализа.")
        return

    logger.info(f"Попытка сохранения данных звонка: {call_id} с оценкой {score}, call_category {call_category}, call_date {call_date}, called_info {called_info}, caller_info {caller_info}, talk_duration {talk_duration}, transcript и result")
    async with connection.cursor() as cursor:
        try:
            score_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"Данные для вставки: history_id={call_id}, call_score={str(score)}, score_date={score_date}, call_date={call_date}, call_category={str(call_category)}, called_info={str(called_info)}, caller_info={str(caller_info)}, talk_duration={str(talk_duration)}, transcript={str(transcript)}, result={str(result)}, number_category={str(category_number)}, number_checklist={str(checklist_number)}, category_checklist={str(checklist_category)}")

            insert_score_query = """
            INSERT INTO call_scores (history_id, call_score, score_date, call_date, call_category, called_info, caller_info, talk_duration, transcript, result, number_category, number_checklist, category_checklist)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            await cursor.execute(insert_score_query, (call_id, str(score), score_date, call_date, str(call_category), str(called_info), str(caller_info), str(talk_duration), str(transcript), str(result), str(category_number), str(checklist_number), str(checklist_category)))
            await connection.commit()
            logger.info("Данные звонка успешно сохранены в call_scores")
        except Error as e:
            logger.error(f"Произошла ошибка '{e}' при сохранении данных звонка")
            await connection.rollback()

# Пример вызова функции
if __name__ == "__main__":
    transcript = "Example transcript"
    checklists = [{"Check_list_categories": "Category 1", "criterion_category": "Criterion 1", "criteria_check_list": "Criterion details", "Number_check_list": 1}]
    asyncio.run(analyze_call_with_gpt(transcript, checklists))
