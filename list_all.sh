#/bin/bash
curl -s https://archive.org/details/stackexchange | egrep "stealth download-pill.*7z.*" | grep -v meta | sed -e "s/.*\///" | sed -e "s/\.7z.*//" 
