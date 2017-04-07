import os
import sys
import re

sep='"'

f1=open(sys.argv[2],"r")
f2=open(sys.argv[4],"r")
f3=open(sys.argv[6],"r")

line_2=f2.readline()
line_2_id=line_2.split(sep)[int(sys.argv[3])-1]

line_3=f3.readline()
line_3_id=line_3.split(sep)[int(sys.argv[5])-1]
print '<?xml version="1.0" encoding="utf-8"?>'
print '<root>'
for line in f1:
	line_id=line.split(sep)[int(sys.argv[1])-1]
	line_to_print= re.sub("<\/row>\n$","",  re.sub("^  <row", "<post", line))
	answers=""
	while line_id == line_2_id: #get all answers
		answers += re.sub("\n$","",line_2)
		line_2=f2.readline()
		if line_2:
			line_2_id=line_2.split(sep)[int(sys.argv[3])-1]
		else:
			break
	line_to_print += "<answers>" + answers + "</answers>"
	link=""
	while line_id == line_3_id:
		link += re.sub("\n$", "", line_3) 
		line_3=f3.readline()
		if line_3:
			line_3_id=line_3.split(sep)[int(sys.argv[5])-1]
		else:
			break
	line_to_print += link
	print line_to_print + "</post>"
print '</root>'

f1.close()
f2.close()
f3.close()
