FROM python:2.7.13-stretch

COPY . /usr/src/oauth2_synchronization_service
WORKDIR /usr/src/oauth2_synchronization_service

RUN pip install -r requirements.txt

EXPOSE 80

CMD ["/usr/local/bin/gunicorn", "-b0.0.0.0:80", "-kflask_sockets.worker", "main:app"]
