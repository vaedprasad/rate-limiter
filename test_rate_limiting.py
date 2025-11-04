#!/usr/bin/env python3
"""
Test script for rate limiting functionality.
Tests both sequential and parallel request patterns.
"""

import requests
import time
import concurrent.futures
import json
from collections import Counter

API_URL = "http://localhost:5000/api/user"

def make_request(user_id, request_num):
    """Make a single request and return the status."""
    try:
        response = requests.get(f"{API_URL}?user_id={user_id}", timeout=5)
        data = response.json()
        return {
            'request_num': request_num,
            'status': data.get('status'),
            'sleep_time': data.get('sleep_time', 0)
        }
    except Exception as e:
        return {
            'request_num': request_num,
            'status': 'error',
            'error': str(e)
        }

def test_sequential(user_id, num_requests=20):
    """Test with sequential requests."""
    print(f"\n{'='*60}")
    print(f"TEST 1: Sequential Requests")
    print(f"{'='*60}")
    print(f"User: {user_id}")
    print(f"Rate limit: 5 req/sec, 10 req/min")
    print(f"Making {num_requests} requests sequentially...\n")

    results = []
    start = time.time()

    for i in range(num_requests):
        # Sleep after first 5 to let the per-second window slide
        if i == 5:
            print("  [Sleeping 1s to avoid per-second limit...]")
            time.sleep(1)

        result = make_request(user_id, i+1)
        results.append(result)
        print(f"Request {result['request_num']:2d}: {result['status']}")

    elapsed = time.time() - start

    # Summary
    status_counts = Counter(r['status'] for r in results)
    success_count = status_counts['success']
    rate_limited_count = status_counts['rate_limited']

    print(f"\n{'='*60}")
    print(f"Sequential Test Results:")
    print(f"  Total time: {elapsed:.2f}s")
    print(f"  Success: {success_count}")
    print(f"  Rate-limited: {rate_limited_count}")

    # Assert: Should not allow more than 10 requests per minute
    try:
        assert success_count <= 10, f"Expected at most 10 successful requests, got {success_count}"
        print(f"  ✓ PASSED: Rate limiting working correctly")
    except AssertionError as e:
        print(f"  ✗ FAILED: {e}")

    print(f"{'='*60}")

    return results, status_counts

def test_parallel(user_id, num_requests=20):
    """Test with parallel requests."""
    print(f"\n{'='*60}")
    print(f"TEST 2: Parallel Requests")
    print(f"{'='*60}")
    print(f"User: {user_id}")
    print(f"Rate limit: 10 req/min")
    print(f"Making {num_requests} requests in parallel...\n")

    results = []
    start = time.time()

    # Fire all requests in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
        futures = [executor.submit(make_request, user_id, i+1) for i in range(num_requests)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    elapsed = time.time() - start

    # Sort by request number for display
    results.sort(key=lambda x: x['request_num'])

    for result in results:
        print(f"Request {result['request_num']:2d}: {result['status']}")

    # Summary
    status_counts = Counter(r['status'] for r in results)
    success_count = status_counts['success']
    rate_limited_count = status_counts['rate_limited']

    print(f"\n{'='*60}")
    print(f"Parallel Test Results:")
    print(f"  Total time: {elapsed:.2f}s")
    print(f"  Success: {success_count}")
    print(f"  Rate-limited: {rate_limited_count}")

    # Assert: Should not allow more than 10 requests per minute
    try:
        assert success_count <= 10, f"Expected at most 10 successful requests, got {success_count}"
        print(f"  ✓ PASSED: Rate limiting working correctly")
    except AssertionError as e:
        print(f"  ✗ FAILED: {e}")

    print(f"{'='*60}")

    return results, status_counts

def check_redis_entries(user_id):
    """Check Redis entries for a user."""
    try:
        response = requests.get(f"http://localhost:5000/status/user?user_id={user_id}")
        data = response.json()
        usage = data.get('status', {}).get('current_usage', {})
        rpm = usage.get('requests_per_minute', {})
        print(f"\nCurrent usage for {user_id}:")
        print(f"  RPM: {rpm.get('current', 0)}/{rpm.get('limit', 10)}")
    except Exception as e:
        print(f"Error checking status: {e}")

def main():
    print("\n" + "="*60)
    print("RATE LIMITING TESTS")
    print("="*60)
    print("\nTesting rate limiter with sequential and parallel requests")
    print("Rate limit: 5 req/sec, 10 req/min\n")

    # Test 1: Sequential
    seq_results, seq_counts = test_sequential("sequential_user", 20)
    check_redis_entries("sequential_user")

    time.sleep(2)

    print("\nStarting parallel test in 1 second...")
    time.sleep(1)

    # Test 2: Parallel
    par_results, par_counts = test_parallel("parallel_user", 20)
    check_redis_entries("parallel_user")

    # Final summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Sequential: {seq_counts['success']} success, {seq_counts['rate_limited']} rate-limited")
    print(f"Parallel:   {par_counts['success']} success, {par_counts['rate_limited']} rate-limited")
    print("="*60)

if __name__ == "__main__":
    main()
