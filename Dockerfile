FROM python:3.12-slim
WORKDIR /app
COPY requirements-richy.txt .
RUN pip install --no-cache-dir -r requirements-richy.txt
COPY richy ./richy
CMD ["python", "-m", "richy.cli", "backtest"]
