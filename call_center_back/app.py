from quart import Quart, jsonify, render_template
import aiosqlite
import logging

# Инициализация приложения Quart
app = Quart(__name__, static_folder='frontend', static_url_path='/static')
logger = logging.getLogger(__name__)

# Асинхронная функция для получения соединения с базой данных
async def get_db_connection():
    try:
        conn = await aiosqlite.connect('database.db')
        conn.row_factory = aiosqlite.Row
        return conn
    except Exception as e:
        logger.exception(f"Ошибка при подключении к базе данных: {e}")
        return None

# Маршрут для получения звонков из базы данных
@app.route('/api/calls', methods=['GET'])
async def get_calls():
    conn = await get_db_connection()
    if conn is None:
        return jsonify({'error': 'Ошибка подключения к базе данных'}), 500

    try:
        async with conn.execute('SELECT * FROM calls') as cursor:
            calls = await cursor.fetchall()
            return jsonify([dict(ix) for ix in calls])
    except Exception as e:
        logger.exception(f"Ошибка при выполнении запроса к базе данных: {e}")
        return jsonify({'error': 'Ошибка при выполнении запроса к базе данных'}), 500
    finally:
        if conn:
            await conn.close()

# Маршрут для главной страницы
@app.route('/')
async def index():
    return await render_template('index.html')

# Маршрут для страницы истории звонков
@app.route('/call_history')
async def call_history():
    return await render_template('call_history.html')

# Запуск приложения
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(debug=True, use_reloader=False)
