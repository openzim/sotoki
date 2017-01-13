import os
import sys
import re



f1=open(sys.argv[1],"r")
f2=open(sys.argv[2],"r")

line_2=f2.readline()
line_2_id=int(line_2.split(",")[0] )
#print '<?xml version="1.0" encoding="utf-8"?>'
#print '<postlinks>'
for line in f1:
	line_id=int(line.split('"')[5])
	while (line_2_id < line_id):
        	line_2=f2.readline()
		if line_2:
        		line_2_id=int(line_2.split(",")[0])
	        else:
	                break



	if line_id == line_2_id:
		print re.sub(' PostId=\"[0-9]*\"', " PostId=\"" + re.sub("\n$","", re.sub("\"", "", line_2.split(",")[1])) + "\"", re.sub("\n$","",line))
	#else => Title doesn't exist
#print '</postlinks>'
