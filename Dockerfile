FROM python:3.8

# add zimwriterfs
RUN wget http://download.openzim.org/release/zimwriterfs/zimwriterfs_linux-x86_64-1.3.8.tar.gz
RUN tar -C /usr/bin --strip-components 1 -xf zimwriterfs_linux-x86_64-1.3.8.tar.gz
RUN rm -f zimwriterfs_linux-x86_64-1.3.8.tar.gz
RUN chmod +x /usr/bin/zimwriterfs
RUN zimwriterfs --version

# Install necessary packages
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends advancecomp libxml2-dev libxslt1-dev libbz2-dev p7zip-full gif2apng imagemagick libjpeg-dev libpng-dev locales && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install jpegoptim
RUN wget http://www.kokkonen.net/tjko/src/jpegoptim-1.4.4.tar.gz && \
    tar xvf jpegoptim-1.4.4.tar.gz && \
    cd jpegoptim-1.4.4 && ./configure && make all install && \
    rm -rf jpegoptim-1.4.4*

# Install pngquant
RUN wget http://pngquant.org/pngquant-2.9.0-src.tar.gz && \
    tar xvf pngquant-2.9.0-src.tar.gz && \
    cd pngquant-2.9.0 && ./configure && make all install && \
    rm -rf pngquant-2.9.0*

# Install gifsicle
RUN wget https://www.lcdf.org/gifsicle/gifsicle-1.88.tar.gz && \
    tar xvf gifsicle-1.88.tar.gz && \
    cd gifsicle-1.88 && ./configure && make all install && \
    rm -rf gifsicle-1.88*

# Install sotoki
RUN locale-gen "en_US.UTF-8"
COPY . /app
WORKDIR /app
RUN pip3 install .
WORKDIR /
RUN rm -rf /app

# Boot commands
CMD sotoki ; /bin/bash
