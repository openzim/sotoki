FROM redis:6.2.4-buster AS redis

FROM python:3.8-slim

RUN groupadd -r -g 999 redis && useradd -r -g redis -u 999 redis
COPY --from=redis /usr/local/bin/redis-server /usr/local/bin/redis-server
COPY --from=redis /usr/local/bin/redis-benchmark /usr/local/bin/redis-benchmark
COPY --from=redis /usr/local/bin/redis-check-aof /usr/local/bin/redis-check-aof
COPY --from=redis /usr/local/bin/redis-check-rdb /usr/local/bin/redis-check-rdb
COPY --from=redis /usr/local/bin/redis-cli /usr/local/bin/redis-cli
RUN mkdir /data && chown redis:redis /data
VOLUME /data

RUN echo "UTC" >  /etc/timezone
ENV TZ "UTC"

RUN apt-get update -y \
    && apt-get install -y --no-install-recommends unzip p7zip tzdata libmagic1 wget locales \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# setup locale
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

# TEMP: install pylibzim and scraperlib through built wheels (until release)
RUN wget --progress=dot:giga http://tmp.kiwix.org/wheels/libzim-1.0.0.dev1-cp38-cp38-manylinux1_x86_64.whl \
    && wget --progress=dot:giga http://tmp.kiwix.org/wheels/zimscraperlib-1.4.0.dev1-py3-none-any.whl \
    && pip install --no-cache-dir ./*.whl && rm -f *.whl

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir -r /tmp/requirements.txt
COPY . /app/
RUN cd /app && python setup.py install && cd - && rm -rf /app

# start redis
RUN printf "#!/bin/sh\necho \"Starting redis\"...\nredis-server --daemonize yes --save \"\" --appendonly no --unixsocket /var/run/redis.sock --unixsocketperm 744 --port 0 --bind 127.0.0.1\n\nexec \"\$@\"\n" > /usr/local/bin/start-redis-daemon && chmod +x /usr/local/bin/start-redis-daemon
ENTRYPOINT ["start-redis-daemon"]

CMD ["sotoki", "--help"]
