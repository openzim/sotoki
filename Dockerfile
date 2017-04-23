FROM openzim/zimwriterfs:latest

# Install necessary packages
RUN apt-get install -y advancecomp
RUN apt-get install -y python-pip
RUN apt-get install -y python-dev
RUN apt-get install -y libxml2-dev
RUN apt-get install -y libxslt1-dev
RUN apt-get install -y libbz2-dev
RUN apt-get install -y p7zip-full
RUN apt-get install -y python-pillow
RUN apt-get install -y gif2apng
RUN apt-get install -y imagemagick

# Install jpegoptim
RUN apt-get install -y libjpeg-dev
RUN wget http://www.kokkonen.net/tjko/src/jpegoptim-1.4.4.tar.gz
RUN tar xvf jpegoptim-1.4.4.tar.gz
RUN cd jpegoptim-1.4.4 && ./configure
RUN cd jpegoptim-1.4.4 && make all install

# Install pngquant
RUN apt-get install -y libpng16-dev
RUN wget http://pngquant.org/pngquant-2.9.0-src.tar.gz
RUN tar xvf pngquant-2.9.0-src.tar.gz
RUN cd pngquant-2.9.0 && ./configure
RUN cd pngquant-2.9.0 && make all install

# Install gifsicle
RUN wget https://www.lcdf.org/gifsicle/gifsicle-1.88.tar.gz
RUN tar xvf gifsicle-1.88.tar.gz
RUN cd gifsicle-1.88 && ./configure
RUN cd gifsicle-1.88 && make all install

# Install sotoki
RUN locale-gen "en_US.UTF-8"
RUN pip install sotoki

# Boot commands
CMD sotoki ; /bin/bash
