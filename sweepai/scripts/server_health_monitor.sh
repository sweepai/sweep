#!/bin/bash

while true
do
    # Get CPU usage
    cpu_usage=$(top -b -n1 | grep "Cpu(s)" | awk '{print $2 + $4}%')

    # Get memory usage
    mem_usage=$(free -m | awk 'NR==2{printf "%.2f%%", $3*100/$2 }')

    # Get disk usage
    disk_usage=$(df -h | awk '$NF=="/"{printf "%s", $5}')

    # Display the usage percentages
    echo "CPU Usage: $cpu_usage"
    echo "Memory Usage: $mem_usage"
    echo "Disk Usage: $disk_usage"

    # Pause for 1 second
    sleep 1
done
