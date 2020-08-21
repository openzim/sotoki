FROM python:3.8

# Install necessary packages
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends advancecomp libxml2-dev libxslt1-dev libbz2-dev p7zip-full gif2apng imagemagick libjpeg-dev libpng-dev locales && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install jpegoptim
RUN wget http://www.kokkonen.net/tjko/src/jpegoptim-1.4.6.tar.gz && \
    tar xvf jpegoptim-1.4.6.tar.gz && \
    cd jpegoptim-1.4.6 && ./configure && make all install && \
    rm -rf jpegoptim-1.4.6*

# Install pngquant
RUN wget http://pngquant.org/pngquant-2.12.5-src.tar.gz && \
    tar xvf pngquant-2.12.5-src.tar.gz && \
    cd pngquant-2.12.5 && ./configure && make all install && \
    rm -rf pngquant-2.12.5*

# Install gifsicle
RUN wget https://www.lcdf.org/gifsicle/gifsicle-1.92.tar.gz && \
    tar xvf gifsicle-1.92.tar.gz && \
    cd gifsicle-1.92 && ./configure && make all install && \
    rm -rf gifsicle-1.92*

# Install sotoki
RUN locale-gen "en_US.UTF-8"
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt
COPY . /app
WORKDIR /app
RUN python3 setup.py install
WORKDIR /
RUN rm -rf /app

# Boot commands
CMD sotoki ; /bin/bash
