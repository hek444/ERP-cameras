FROM python:3.13

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
WORKDIR /app

EXPOSE 8000

CMD ["python", "src/manage.py", "runserver", "0:8000"]