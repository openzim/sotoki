import os
import sys
import re



f1=open(sys.argv[1],"r")
f2=open(sys.argv[2],"r")

import csv
csvreader = csv.reader(f2, delimiter=',', quotechar='"')

line_2=csvreader.next()
line_2_id=int(line_2[0])
#print '<?xml version="1.0" encoding="utf-8"?>'
#print '<postlinks>'
for line in f1:
	line_id=int(line.split('"')[5])
	while (line_2_id < line_id):
        	line_2=csvreader.next()
		if line_2:
        		line_2_id=int(line_2[0])
	        else:
	                break

	if line_id == line_2_id:
		#print re.sub(r'\\(.)', r'\1', re.sub(' PostId=\"[0-9]*\"', " PostId=\"" + re.sub("\n$","", re.escape(re.sub("\"", "", line_2.split(",")[1]))) + "\"", re.sub("\n$","", line)))
		line_split=line.split('"')
		#line_split[5]=re.sub("^\"","",re.sub("\"$","", re.sub("\n$","", line_2.split(",")[1])))
		line_split[5]=line_2[1]
		print re.sub("\n$","", '"'.join(line_split))
	#else => Title doesn't exist
#print '</postlinks>'
