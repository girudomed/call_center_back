import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# Создаём клиента OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

if not client.api_key:
    raise ValueError("API ключ для OpenAI не найден. Добавьте его в файл .env как OPENAI_API_KEY")

# Настройка логирования
logging.basicConfig(filename='analyzer.log', level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

# Конфигурации для OpenAI
MAX_TOKENS_PER_REQUEST = 3000  # Ограничение токенов на запрос
MODEL = "gpt-4o-mini-2024-07-18"
TEMPERATURE = 0.7

def scan_project_files(directory):
    """Сканирование всех файлов в проекте и возврат их путей."""
    project_files = []
    for root, dirs, files in os.walk(directory):
        # Исключаем системные директории или виртуальные среды
        dirs[:] = [d for d in dirs if d not in ['.git', 'venv', '__pycache__']]
        for file in files:
            if file.endswith('.py'):  # Анализируем только Python файлы
                file_path = os.path.join(root, file)
                project_files.append(file_path)
    return project_files

def split_code_into_chunks(code, max_chunk_size=1500):
    """
    Разбиваем код на части, чтобы избежать превышения лимитов по токенам.
    :param code: Полный код файла.
    :param max_chunk_size: Максимальный размер одного куска текста.
    :return: Список кусочков кода для анализа.
    """
    lines = code.split('\n')
    chunks = []
    current_chunk = []

    for line in lines:
        current_chunk.append(line)
        if len(current_chunk) >= max_chunk_size:
            chunks.append("\n".join(current_chunk))
            current_chunk = []

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks

def analyze_code_with_gpt(code_chunk):
    """Запрос к OpenAI GPT для анализа кода в рамках одной части."""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Вы — обучающий модуль для анализа программного проекта. Создайте структурное описание проекта."},
                {"role": "user", "content": code_chunk}
            ],
            max_tokens=MAX_TOKENS_PER_REQUEST,
            temperature=TEMPERATURE
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Ошибка анализа с GPT: {str(e)}")
        return f"Ошибка анализа с GPT: {str(e)}"

def analyze_file(file_path):
    """Анализирует один файл, разбивая его на части и анализируя каждую часть."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            code = file.read()
    except Exception as e:
        logger.error(f"Не удалось прочитать файл {file_path}: {e}")
        return

    if not code.strip():
        logger.info(f"Файл {file_path} пуст.")
        return

    code_chunks = split_code_into_chunks(code)
    logger.info(f"Разбивка файла {file_path} на {len(code_chunks)} частей для анализа.")

    full_analysis = ""
    for idx, chunk in enumerate(code_chunks):
        logger.info(f"Анализ части {idx + 1} из {len(code_chunks)} для файла {file_path}.")
        gpt_analysis = analyze_code_with_gpt(chunk)
        full_analysis += f"\n--- Часть {idx + 1} ---\n{gpt_analysis}\n"

    logger.info(f"Результат анализа для файла {file_path}:\n{full_analysis}")

def analyze_project(directory):
    """Запуск анализа проекта: анализ всех файлов с разбиением на части."""
    files = scan_project_files(directory)
    if not files:
        print("Файлы для анализа не найдены.")
        logger.info("Файлы для анализа не найдены.")
        return

    logger.info(f"Найдено файлов для анализа: {len(files)}")
    for file in files:
        logger.info(f"Начало анализа файла: {file}")
        analyze_file(file)

if __name__ == "__main__":
    project_directory = os.getcwd()  # Текущая директория проекта
    print(f"Запуск анализа проекта в директории: {project_directory}")
    logger.info(f"Запуск анализа проекта в директории: {project_directory}")
    analyze_project(project_directory)