import os
import sys
import re



f1=open(sys.argv[1],"r")
f2=open(sys.argv[2],"r")

import csv
csvreader = csv.reader(f2, delimiter=',', quotechar='"')

line_2=csvreader.next()
line_2_id=int(line_2[0])
for line in f1:
	line_id=int(line.split('"')[5])
	while (line_2_id < line_id):
		try:
	        	line_2=csvreader.next()
		except:
			break
		if line_2:
        		line_2_id=int(line_2[0])
	        else:
	                break

	if line_id == line_2_id:
		line_split=line.split('"')
	        #line_split[5]=line_2[1]
	        new_line=line_split[0:6] + [ " PostName=" , line_2[1] ] + line_split[6:]
		print re.sub("\n$","", '"'.join(new_line))
	#else => Title doesn't exist
