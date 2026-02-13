# Используем официальный Python runtime как базовый образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код приложения
COPY . .

# Создаем директорию для базы данных
RUN mkdir -p instance

# Создаем директорию для QR кодов если её нет
RUN mkdir -p static/qr_codes

# Экспортируем порт, на котором работает приложение
EXPOSE 5000

# Устанавливаем переменные окружения
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Запускаем приложение
CMD ["python", "app.py"]
