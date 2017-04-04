import os
import sys
import re

sep='"'

f1=open(sys.argv[2],"r")
f2=open(sys.argv[4],"r")

line_2=f2.readline()
line_2_id=line_2.split(sep)[int(sys.argv[3])-1]

for line in f1:
	line_id=line.split(sep)[int(sys.argv[1])-1]
	line_to_print= re.sub("\r", "", re.sub("/>", ">", re.sub("\n$","",line)))
	comments=""
	while line_id == line_2_id:
		comments += re.sub("<row", "<comment", re.sub("\n$","",line_2))
		line_2=f2.readline()
		if line_2:
			line_2_id=line_2.split(sep)[int(sys.argv[3])-1]
		else:
			break
	if comments != "":
		line_to_print+="<comments>" + comments + "</comments>"
	print line_to_print + "</row>"
