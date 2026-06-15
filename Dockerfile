FROM python:3.11-slim
WORKDIR /app
COPY requirements_dashboard.txt .
RUN pip install --no-cache-dir -r requirements_dashboard.txt
COPY config_dashboard.py database_dashboard.py binance_client_dashboard.py app_dashboard.py gunicorn_conf_dashboard.py ./
EXPOSE 5000
CMD ["gunicorn", "-c", "gunicorn_conf_dashboard.py", "app_dashboard:app"]
