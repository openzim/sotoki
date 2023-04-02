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
RUN pip install --upgrade pip
RUN pip install pipenv
COPY Pipfile .
COPY Pipfile.lock .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv sync --dev --system
COPY setup.py LICENSE MANIFEST.in README.md /app/
COPY src /app/src
RUN PIPENV_VENV_IN_PROJECT=1 pipenv requirements > /app/requirements.txt
RUN cd /app && python setup.py install && cd - && rm -rf /app

# redis-restart script is use to start redis initally (redis-restart 0)
# but also to restart it later-on using --defrag-redis param.
# in this case, the param is the redis PID.
# environment variable REDIS_PID provides it.
RUN printf "#!/bin/sh\n\
pid=\$1\n\
if [ -z \"\$pid\" ];\n\
then\n\
    echo \"Missing REDIS PID.\"\n\
    exit 1\n\
fi\n\
\n\
if [ ! \"\$pid\" = \"0\" ];\n\
then\n\
    echo \"Killing REDIS at \$pid\"\n\
    kill \$pid\n\
    sleep 3\n\
fi\n\
echo -n \"Starting redis\"\n\
redis-server --daemonize yes --save \"\" --appendonly no \
--unixsocket /var/run/redis.sock --unixsocketperm 744 \
--dir /output \
--port 6379 --bind 0.0.0.0 --pidfile /var/run/redis.pid\n\
\n\
while ! test -f /var/run/redis.pid; do\n\
  sleep 1\n\
  echo -n "."\n\
done\n\
REDIS_PID=\$(/bin/cat /var/run/redis.pid)\n\
echo \". PID: \${REDIS_PID}\"\n" > /usr/local/bin/redis-restart && \
chmod a+x /usr/local/bin/redis-restart

# entrypoint starts redis then executes CMD
RUN printf "#!/bin/sh\n\
redis-restart 0\n\n\
export REDIS_PID=\$(/bin/cat /var/run/redis.pid)\n\
exec \"\$@\"\n" > /usr/local/bin/start-redis-daemon && \
chmod +x /usr/local/bin/start-redis-daemon

RUN mkdir -p /output

EXPOSE 6379
ENTRYPOINT ["start-redis-daemon"]

CMD ["sotoki", "--help"]
