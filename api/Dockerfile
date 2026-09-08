FROM python:3.12-slim
WORKDIR /app

# Install system dependencies for mysqlclient if needed, 
# but we use pymysql which is pure python.
# RUN apt-get update && apt-get install -y default-libmysqlclient-dev build-essential

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use PYTHONPATH to allow 'import api'
ENV PYTHONPATH=/app

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
