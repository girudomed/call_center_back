import logging

# Настройка логирования для результатов анализа
def setup_result_logging(enable_console_logging=True):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levellevel)s - %(message)s',
        filename='analyze_results.log',
        filemode='w'
    )
    result_logger = logging.getLogger('result_logger')
    
    if enable_console_logging:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        result_logger.addHandler(console_handler)
    
    return result_logger

result_logger = setup_result_logging()

def log_analysis_result(call_id, result):
    result_logger = logging.getLogger('result_logger')
    result_logger.info(f"Звонок {call_id} - Результат анализа: {result}")
