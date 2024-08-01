import openai
import logging
import re
import os
from datetime import datetime
from pymysql import Error
from dotenv import load_dotenv
import asyncio

# Загрузка переменных окружения
load_dotenv()

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

# Установка API-ключа OpenAI
api_key = os.getenv('OPENAI_API_KEY', 'sk-proj-dWlINNFTxpaktU96B4qyT3BlbkFJgAXRiIHWI5DRbMoUWGPG')
if not api_key:
    logger.error("OpenAI API key is not provided. Please set the API key in the environment variable 'OPENAI_API_KEY'.")
else:
    openai.api_key = api_key

async def analyze_call_with_gpt(transcript, checklists):
    logger.info(f"Анализ звонка с использованием GPT для расшифровки: {transcript}")
    if not transcript:
        logger.info("Отсутствует расшифровка звонка. Пропуск анализа.")
        return None, None, None, None, None

    # Проверка структуры checklists и приведение к списку словарей
    if isinstance(checklists, tuple):
        logger.warning(f"checklists является кортежем. Преобразование в список.")
        checklists = list(checklists)
    if not isinstance(checklists, list) or not all(isinstance(item, dict) for item in checklists):
        logger.error("checklists должен быть списком словарей.")
        return None, None, None, None, None

    # Формирование списка категорий и критериев для анализа
    categories_text = "\n".join([f"{checklist['Check_list_categories']}: {checklist['criterion_category']}" for checklist in checklists])
    criteria_text = "\n".join([checklist['criteria_check_list'] for checklist in checklists])

    prompt = f"""
    Анализ звонка:
    Расшифровка звонка: {transcript}

    Пожалуйста, проведите анализ данного звонка по следующим категориям и критериям:
    Категории:
    {categories_text}

    Критерии:
    {criteria_text}

    Дайте оценку по каждому пункту от 0 до 10 и укажите общую оценку звонка. Ответ необходимо дать в формате:
    "Категория звонка: <Название категории> number_category=<Номер категории>"
    <Название критерия>: <оценка>
    """

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Вы помощник, который помогает классифицировать звонки и анализировать эффективность операторов."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3,
            presence_penalty=0.5,
            frequency_penalty=0.5
        )
        result_text = response['choices'][0]['message']['content'].strip()
        logger.info(f"Анализ звонка: {result_text}")

        # Поиск оценки, категории и номера категории в ответе GPT
        score_match = re.search(r'Общая оценка звонка: (\d+(\.\d+)?)', result_text)
        category_match = re.search(r'Категория звонка: ([\w\s]+)', result_text)
        number_category_match = re.search(r'number_category=(\d+)', result_text)

        score = float(score_match.group(1)) if score_match else 0
        call_category = category_match.group(1).strip() if category_match else "Не определено"
        category_number = int(number_category_match.group(1)) if number_category_match else None

        # Убираем "number_category" из call_category
        call_category_clean = re.sub(r' number_category=\d+', '', call_category).strip()

        logger.info(f"Общая оценка звонка: {score}, Категория звонка: {call_category_clean}, Номер категории: {category_number}")

        # Поиск чек-листа по номеру категории
        checklist = next((checklist for checklist in checklists if checklist['Number_check_list'] == category_number), None)
        checklist_result = checklist['criteria_check_list'] if checklist else "Чек-лист не найден"

        # Генерация оценок по каждому пункту чек-листа
        criteria_scores = []
        for criterion in checklist_result.split("\n"):
            criterion_score_match = re.search(rf'{re.escape(criterion.strip())}: (\d+(\.\d+)?)', result_text)
            criterion_score = float(criterion_score_match.group(1)) if criterion_score_match else 0
            criteria_scores.append((criterion.strip(), criterion_score))

        # Формирование строки результата
        analyzed_result = f"{result_text}\nЧек-лист и оценки:\n" + "\n".join([f"{criterion}: {score}" for criterion, score in criteria_scores])

        return score, analyzed_result, call_category_clean, category_number, checklist_result
    except openai.error.OpenAIError as e:
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
