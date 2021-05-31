FROM python:3.8-slim

RUN apt-get update -y \
    && apt-get install -y --no-install-recommends unzip p7zip tzdata wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN echo "UTC" >  /etc/timezone
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

# TEMP: install pylibzim and scraperlib through built wheels (until release)
RUN wget http://tmp.kiwix.org/wheels/libzim-1.0.0.dev0-cp38-cp38-manylinux1_x86_64.whl \
    && wget http://tmp.kiwix.org/wheels/zimscraperlib-1.4.0.dev0-py3-none-any.whl \
    && pip install  --no-cache-dir *.whl

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir -r /tmp/requirements.txt
COPY . /app/
RUN cd /app && python setup.py install && cd - && rm -rf /app

CMD ["sotoki", "--help"]
