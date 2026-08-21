FROM python:3.12-slim
WORKDIR /app
COPY bot.py /app/bot.py
RUN mkdir -p /data
ENV DB_PATH=/data/bot.db
CMD ["python", "/app/bot.py"]
