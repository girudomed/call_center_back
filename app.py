from quart import jsonify, render_template
import logging
from async_db_connection import execute_async_query

logger = logging.getLogger(__name__)

def setup_routes(app, pool):
    """Регистрация маршрутов для приложения."""
    
    @app.route('/api/calls', methods=['GET'])
    async def get_calls():
        """Получение звонков из базы данных."""
        query = "SELECT * FROM calls"
        try:
            result = await execute_async_query(pool, query)
            if result is None:
                return jsonify({'error': 'Ошибка выполнения запроса к базе данных'}), 500
            return jsonify([dict(row) for row in result])
        except Exception as e:
            logger.exception(f"Ошибка при выполнении запроса к базе данных: {e}")
            return jsonify({'error': 'Ошибка выполнения запроса к базе данных'}), 500

    @app.route('/')
    async def index():
        """Рендер главной страницы."""
        return await render_template('index.html')

    @app.route('/call_history')
    async def call_history():
        """Рендер страницы истории звонков."""
        return await render_template('call_history.html')