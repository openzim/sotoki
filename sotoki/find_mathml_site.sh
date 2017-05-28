#!/bin/bash

sites=$(curl -L https://archive.org/download/stackexchange/stackexchange_files.xml | grep "file name=" | grep "7z" | sed 's/  <file name="\(.*\).7z" source="original">/http:\/\/\1/'| grep -v "stackoverflow")

for site in $sites
do
  curl -L $site | grep "mathjax" > /dev/null
  if [[ $? -eq 0 ]]
  then
    echo $site
  fi

done
