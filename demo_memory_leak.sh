#!/bin/bash
# Demonstration of Redis memory accumulation with idle users.
# Creates 100 users making sequential requests, then monitors Redis.

API_HOST="${API_HOST:-localhost:5000}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

# Colors for dramatic effect
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${PURPLE}"
cat << "EOF"
╔══════════════════════════════════════════════════════╗
║  REDIS MEMORY DEMONSTRATION                         ║
║                                                      ║
║  This will show Redis memory with 100 idle users    ║
║  after they've exceeded their rate limits           ║
╚══════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if services are running
echo -e "${BLUE}🔍 Checking services...${NC}"
if ! curl -s "$API_HOST/health" > /dev/null; then
    echo -e "${RED}❌ API not running. Start with: python api_server.py${NC}"
    exit 1
fi

if ! docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}❌ Redis not running. Start with: docker-compose up -d${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Services running${NC}"

# Clear Redis for clean demo
echo -e "${YELLOW}🧹 Clearing Redis...${NC}"
docker-compose exec -T redis redis-cli FLUSHALL > /dev/null

# Show initial state
echo -e "\n${CYAN}📊 INITIAL STATE:${NC}"
initial_memory=$(docker-compose exec -T redis redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r\n')
echo -e "   Redis Memory: ${GREEN}$initial_memory${NC}"
echo -e "   Redis Keys: ${GREEN}0${NC}"

echo -e "\n${PURPLE}🚀 STARTING LOAD TEST...${NC}"

# Create progress bar function
show_progress() {
    local current=$1
    local total=$2
    local width=50
    local percentage=$((current * 100 / total))
    local completed=$((current * width / total))

    printf "\r${YELLOW}["
    for ((i=0; i<completed; i++)); do printf "█"; done
    for ((i=completed; i<width; i++)); do printf "░"; done
    printf "] %d%% (%d/%d users)${NC}" "$percentage" "$current" "$total"
}

# Create 100 users making requests in parallel
echo -e "${CYAN}Creating 100 users (each making 15 sequential requests)...${NC}"
total_users=100
requests_per_user=15

# Function to make sequential requests for a single user
make_user_requests() {
    local user_id=$1
    local num_requests=$2
    for j in $(seq 1 $num_requests); do
        curl -s "$API_HOST/api/user?user_id=leak_demo_user_$user_id" > /dev/null
    done
}

# Launch all users in parallel (but each user makes sequential requests)
for i in $(seq 1 $total_users); do
    make_user_requests $i $requests_per_user &

    # Show progress
    if [ $((i % 10)) -eq 0 ]; then
        show_progress $i $total_users
    fi
done

# Wait for all background processes to complete
wait
echo -e "\n${GREEN}✅ All users created and now idle${NC}"

# Show immediate post-creation state
echo -e "\n${CYAN}📊 POST-CREATION STATE:${NC}"
post_keys=$(docker-compose exec -T redis redis-cli eval "return #redis.call('keys', 'rate_limiter:*')" 0)
post_entries=$(docker-compose exec -T redis redis-cli eval "
    local keys = redis.call('keys', 'rate_limiter:*')
    local total = 0
    for i=1,#keys do
        total = total + redis.call('zcard', keys[i])
    end
    return total
" 0)
post_memory=$(docker-compose exec -T redis redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r\n')

echo -e "   Redis Keys: ${YELLOW}$post_keys${NC}"
echo -e "   Total Entries: ${YELLOW}$post_entries${NC}"
echo -e "   Redis Memory: ${YELLOW}$post_memory${NC}"

# Show sample of worst offenders
echo -e "\n${CYAN}🔍 Sample of accumulated entries:${NC}"
docker-compose exec -T redis redis-cli eval "
    local keys = redis.call('keys', 'rate_limiter:*')
    local samples = {}
    for i=1,math.min(5, #keys) do
        local count = redis.call('zcard', keys[i])
        table.insert(samples, keys[i] .. '|' .. count)
    end
    return samples
" 0 | while IFS='|' read -r key count; do
    if [ -n "$key" ]; then
        echo -e "   ${RED}$key: $count entries${NC}"
    fi
done

echo -e "\n${PURPLE}⏰ IDLE PERIOD (60 seconds)${NC}"
echo -e "${CYAN}Monitoring Redis memory during idle period...${NC}"

# Dramatic countdown with memory monitoring
for second in {60..1}; do
    current_memory=$(docker-compose exec -T redis redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r\n')
    current_entries=$(docker-compose exec -T redis redis-cli eval "
        local keys = redis.call('keys', 'rate_limiter:*')
        local total = 0
        for i=1,#keys do
            total = total + redis.call('zcard', keys[i])
        end
        return total
    " 0 2>/dev/null || echo "?")

    printf "\r${YELLOW}⏰ %02ds remaining | Memory: %s | Entries: %s${NC}" "$second" "$current_memory" "$current_entries"
    sleep 1
done

echo ""

# Final analysis
echo -e "\n${PURPLE}📊 FINAL ANALYSIS:${NC}"
final_keys=$(docker-compose exec -T redis redis-cli eval "return #redis.call('keys', 'rate_limiter:*')" 0)
final_entries=$(docker-compose exec -T redis redis-cli eval "
    local keys = redis.call('keys', 'rate_limiter:*')
    local total = 0
    for i=1,#keys do
        total = total + redis.call('zcard', keys[i])
    end
    return total
" 0)
final_memory=$(docker-compose exec -T redis redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r\n')

echo -e "   Initial Memory: ${GREEN}$initial_memory${NC}"
echo -e "   Final Memory:   ${RED}$final_memory${NC}"
echo -e "   Final Keys:     ${RED}$final_keys${NC}"
echo -e "   Final Entries:  ${RED}$final_entries${NC}"

# Calculate retention percentage
retention_percentage=$((final_entries * 100 / post_entries))

echo -e "\n${YELLOW}📈 RETENTION ANALYSIS:${NC}"
echo -e "   Entries Created: ${CYAN}$post_entries${NC}"
echo -e "   Entries Remaining: ${RED}$final_entries${NC}"
echo -e "   Retention Rate: ${RED}$retention_percentage%${NC}"

# Analysis
echo ""
if [ "$retention_percentage" -gt 80 ]; then
    echo -e "${RED}⚠️  Over 80% of entries remain after 60s idle period${NC}"
elif [ "$retention_percentage" -gt 50 ]; then
    echo -e "${YELLOW}⚠️  Over 50% of entries remain after 60s idle period${NC}"
elif [ "$retention_percentage" -gt 20 ]; then
    echo -e "${YELLOW}⚠️  Over 20% of entries remain after 60s idle period${NC}"
else
    echo -e "${GREEN}✅ Most entries cleaned up after idle period${NC}"
fi

echo -e "\n${BLUE}🔍 INVESTIGATION COMMANDS:${NC}"
echo -e "${CYAN}# Check specific user entries:${NC}"
echo -e "docker-compose exec -T redis redis-cli ZCARD rate_limiter:user_leak_demo_user_1:rps"
echo -e "\n${CYAN}# Check entry timestamps:${NC}"
echo -e "docker-compose exec -T redis redis-cli ZRANGEBYSCORE rate_limiter:user_leak_demo_user_1:rps -inf +inf WITHSCORES"
echo -e "\n${CYAN}# Check all leaked keys:${NC}"
echo -e "curl -s http://$API_HOST/redis-info | jq '.key_details'"

echo -e "\n${GREEN}Demo complete! 🎬${NC}"