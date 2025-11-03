#!/bin/bash
# Quick test script to verify the rate limiter setup
# This demonstrates the steps from the README

set -e

echo "=========================================="
echo "Rate Limiter Quick Start Test"
echo "=========================================="
echo ""

# Check if services are running
echo "1. Checking if services are running..."
if ! docker-compose ps | grep -q "rate_limiter_app.*Up"; then
    echo "   Services not running. Please start with: docker-compose up -d --build"
    exit 1
fi
echo "   ✓ Services are running"
echo ""

# Test health endpoint
echo "2. Testing health endpoint..."
curl -s http://localhost:5000/health | jq '.'
echo "   ✓ API server is healthy"
echo ""

# Make a single request
echo "3. Making a single request..."
echo "   curl http://localhost:5000/api/user?user_id=alice"
curl -s "http://localhost:5000/api/user?user_id=alice" | jq '.'
echo ""

# Check status
echo "4. Checking rate limit status..."
echo "   curl http://localhost:5000/status/user?user_id=alice"
curl -s "http://localhost:5000/status/user?user_id=alice" | jq '.'
echo ""

# Generate load to trigger rate limiting
echo "5. Generating load to trigger rate limiting..."
echo "   Sending 10 rapid requests (limit: 5/sec)..."
for i in {1..10}; do
  status=$(curl -s "http://localhost:5000/api/user?user_id=bob" | jq -r '.status')
  echo "   Request $i: $status"
  sleep 0.1
done
echo ""

# Check logs
echo "6. Checking logs for rate limiting events..."
if [ -f "logs/rate_limiter.jsonl" ]; then
    echo "   Recent rate limited events:"
    cat logs/rate_limiter.jsonl | jq -c 'select(.message | contains("RATE_LIMITED"))' | tail -5
else
    echo "   Log file not found yet. Check docker logs:"
    echo "   docker-compose logs rate_limiter_app | grep RATE_LIMITED"
fi
echo ""

echo "=========================================="
echo "✓ Quick Start Test Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  - View logs: docker-compose logs -f"
echo "  - Test more: curl http://localhost:5000/api/burst?user_id=test"
echo "  - Redis info: curl http://localhost:5000/redis-info | jq"
echo ""
