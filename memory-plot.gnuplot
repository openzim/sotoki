set term png small size 1024,1024
set output "out.png"

set ylabel "VSZ"
set y2label "%MEM"

set ytics nomirror
set y2tics nomirror in

set yrange [0:*]
set y2range [0:*]

plot "memory.log" using 3 with lines axes x1y1 title "VSZ", \
     "memory.log" using 2 with lines axes x1y2 title "%MEM"