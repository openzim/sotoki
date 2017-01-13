rm memory.log || echo "fresh start"
while true; do
#    ps -C sotoki -o pid=,%mem=,vsz= >> memory.log
    ps -C "python sotoki" -o pid=,%mem=,vsz= >> memory.log
    gnuplot memory-plot.gnuplot
    sleep 1
done
