import openai
# Обновлённый вызов функции fine-tuning
async def create_fine_tune_model(training_file_id, model_name="gpt-3.5-turbo"):
    logger.info("Начало задачи fine-tuning на сервере OpenAI.")
    try:
        fine_tune_job = await openai.FineTuningJob.acreate(  # Обратите внимание на `acreate` для асинхронного вызова
            model=model_name,
            training_file=training_file_id
        )
        logger.info(f"Задача fine-tuning успешно запущена с ID: {fine_tune_job['id']}")
    except openai.OpenAIError as e:
        logger.error(f"Ошибка при запуске fine-tuning: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при запуске fine-tuning: {e}")
        
        

