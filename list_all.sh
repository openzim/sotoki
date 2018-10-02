#/bin/bash
#curl -s https://archive.org/details/stackexchange | egrep "stealth download-pill.*7z.*" | grep -v meta | sed -e "s/.*\///" | sed -e "s/\.7z.*//"  | sed -e "s/-.*//" | sort -u
curl https://ia800107.us.archive.org/27/items/stackexchange/stackexchange_files.xml | grep "<file" |sed 's/  <file name="//' | sed "s/\.7z.*//"
