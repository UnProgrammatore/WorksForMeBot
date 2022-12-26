FROM python:3.11

ADD requirements.txt /
RUN pip install -r requirements.txt
RUN rm /requirements.txt

ADD works-for-me.py /

WORKDIR /data
WORKDIR /

ADD run.sh /
RUN chmod 111 /run.sh

ENTRYPOINT ["/run.sh"]