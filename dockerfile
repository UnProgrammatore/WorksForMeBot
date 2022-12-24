FROM python:3

ADD requirements.txt /
RUN pip install -r requirements.txt
RUN rm /requirements.txt

ADD works-for-me.py /

WORKDIR /data
WORKDIR /

CMD ["python", "/works-for_me.py", "$BOT_TOKEN", "/data/data.db"]