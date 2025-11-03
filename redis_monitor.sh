#!/bin/bash
# Real-time Redis monitoring script.
# Run this in a separate terminal while running demo_memory_leak.sh

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🔍 Redis Memory Monitor Started${NC}"
echo -e "${BLUE}Press Ctrl+C to stop${NC}"
echo "=================================================="

# Initialize previous values
prev_keys=0
prev_entries=0
prev_memory=0

while true; do
    # Check if docker-compose is available
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}docker-compose not available${NC}"
        sleep 2
        continue
    fi

    # Get current metrics using docker-compose
    keys=$(docker-compose exec -T redis redis-cli eval "return #redis.call('keys', 'rate_limiter:*')" 0 2>/dev/null || echo "0")

    entries=$(docker-compose exec -T redis redis-cli eval "
        local keys = redis.call('keys', 'rate_limiter:*')
        local total = 0
        for i=1,#keys do
            local count = redis.call('zcard', keys[i])
            total = total + count
        end
        return total
    " 0 2>/dev/null || echo "0")

    memory=$(docker-compose exec -T redis redis-cli info memory | grep used_memory: | cut -d: -f2 | tr -d '\r\n')
    memory_mb=$(echo $memory | awk '{print int($1/1024/1024)}')

    # Calculate changes
    key_change=$((keys - prev_keys))
    entry_change=$((entries - prev_entries))
    memory_change=$((memory - prev_memory))
    memory_change_mb=$(echo $memory_change | awk '{print int($1/1024/1024)}')

    # Format timestamp
    timestamp=$(date '+%H:%M:%S')

    # Color code based on changes
    if [ "$entry_change" -gt 100 ]; then
        entry_color=$RED
        alert=" 🚨"
    elif [ "$entry_change" -gt 0 ]; then
        entry_color=$YELLOW
        alert=" ⚠️"
    elif [ "$entry_change" -lt -50 ]; then
        entry_color=$GREEN
        alert=" ✅"
    else
        entry_color=$CYAN
        alert=""
    fi

    # Display current state
    printf "${BLUE}%s${NC} " "$timestamp"
    printf "Keys: ${CYAN}%4d${NC} " "$keys"
    printf "Entries: ${entry_color}%6d${NC} " "$entries"
    printf "Memory: ${CYAN}%4dMB${NC} " "$memory_mb"

    # Show changes if not first iteration
    if [ "$prev_keys" -ne 0 ]; then
        if [ "$entry_change" -ne 0 ]; then
            printf "${entry_color}(%+d entries)${NC}" "$entry_change"
        fi
        if [ "$memory_change_mb" -ne 0 ]; then
            printf " ${YELLOW}(%+dMB)${NC}" "$memory_change_mb"
        fi
    fi

    printf "%s\n" "$alert"

    # Show alert if high entry count
    if [ "$entries" -gt 1000 ]; then
        echo -e "${RED}   ⚠️  HIGH ENTRY COUNT: $entries entries${NC}"
    fi

    # Update previous values
    prev_keys=$keys
    prev_entries=$entries
    prev_memory=$memory

    sleep 2
done