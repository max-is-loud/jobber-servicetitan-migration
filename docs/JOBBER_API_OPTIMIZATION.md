# Jobber API Optimization Guide for TightBeam v2

## Executive Summary

Based on our analysis and real-world testing, we've identified the optimal configuration for maximizing TightBeam v2's performance while respecting Jobber's API limits.

### Key Findings

- **GraphQL Query Cost**: Hard limit of 10,000 points per query
- **DDoS Protection**: 2,500 requests per 5 minutes (500 req/min)
- **Current Query Cost**: ~6,365 points (well under limit)
- **Actual Cost**: 500-700 points per request
- **Current Performance**: ~3 requests/second sustained

## Jobber API Limits

### 1. GraphQL Query Cost Limit

- **Hard Limit**: 10,000 points per query
- **Calculation**: Based on query complexity (not publicly documented)
- **Our Queries**: Currently using ~6,365 points (63.65% of limit)

### 2. DDoS Protection Middleware

- **Limit**: 2,500 requests per 5 minutes
- **Effective Rate**: 500 requests per minute (8.33 req/sec max)
- **Per App/Account**: Not IP-based

### 3. Leaky Bucket Algorithm

- Points deducted per query
- Points restored over time
- Allows burst traffic while maintaining average rate

## Current Configuration Analysis

```python
# Current Settings (Conservative)
TokenBucketRateLimiter(
    capacity=300,          # Max burst capacity
    refill_rate=180,       # Tokens per minute (3/sec)
    initial_tokens=20      # Start conservatively
)
```

**Performance**: ~3 requests/second sustained

## Optimization Strategy

### Option 1: Moderate Optimization (Recommended)

```python
TokenBucketRateLimiter(
    capacity=400,          # Higher burst capacity
    refill_rate=360,       # 6 requests/second
    initial_tokens=60      # 15% of capacity
)
```

- **Target Rate**: 6 requests/second
- **Safety Margin**: 28% below DDoS limit
- **Risk**: Low

### Option 2: Aggressive Optimization

```python
TokenBucketRateLimiter(
    capacity=500,          # Maximum burst
    refill_rate=480,       # 8 requests/second
    initial_tokens=100     # 20% of capacity
)
```

- **Target Rate**: 8 requests/second
- **Safety Margin**: 4% below DDoS limit
- **Risk**: Medium (close to limits)

### Option 3: Ultra-Safe Configuration

```python
TokenBucketRateLimiter(
    capacity=250,          # Conservative burst
    refill_rate=240,       # 4 requests/second
    initial_tokens=40      # 16% of capacity
)
```

- **Target Rate**: 4 requests/second
- **Safety Margin**: 52% below DDoS limit
- **Risk**: Very Low

## Additional Optimizations

### 1. Query Cost Reduction

Current deferred notes implementation is already optimal:

- Fetches only note IDs initially
- Individual note queries later
- Reduces query complexity from 21,205 to ~6,365 points

### 2. Parallel Processing

```python
# Enable multi-threaded extraction
--parallel-workers 3  # Run 3 extractors in parallel
```

- Each worker gets its own rate limiter
- Theoretical max: 18-24 requests/second total
- Requires careful coordination

### 3. Intelligent Batching

```python
# Optimize page size based on entity density
--clients-per-page 100    # Default, works well
--invoices-per-page 50    # Reduce if many line items
--quotes-per-page 75      # Balance between requests and cost
```

### 4. Caching Strategy

```python
# Implement response caching
--enable-cache            # Cache unchanged entities
--cache-ttl 3600         # 1 hour cache lifetime
```

### 5. Adaptive Rate Limiting

```python
class AdaptiveRateLimiter:
    """Dynamically adjust rate based on response headers"""
    
    def adjust_rate(self, response_headers):
        if 'x-ratelimit-remaining' in response_headers:
            remaining = int(response_headers['x-ratelimit-remaining'])
            if remaining < 100:
                self.reduce_rate()
            elif remaining > 1000:
                self.increase_rate()
```

## Implementation Recommendations

### Phase 1: Immediate Optimizations

1. Increase rate limit to 360/minute (6 req/sec)
2. Monitor GraphQL cost in responses
3. Track actual vs requested costs

### Phase 2: Advanced Optimizations

1. Implement parallel workers
2. Add response caching
3. Deploy adaptive rate limiting

### Phase 3: Fine-tuning

1. Analyze cost patterns per entity type
2. Optimize query fields based on usage
3. Implement predictive rate adjustment

## Monitoring and Alerting

### Key Metrics to Track

1. **Query Cost**: Actual vs Requested
2. **Rate Limit Headers**:
   - `x-ratelimit-remaining`
   - `x-ratelimit-reset`
3. **Throttling Events**: Count and frequency
4. **Migration Speed**: Entities/minute

### Alert Thresholds

- Query cost > 8,000 points (80% of limit)
- Rate limit remaining < 200
- Throttling errors > 5 per minute
- Migration speed < 100 entities/minute

## Performance Projections

### With Moderate Optimization (6 req/sec)

- **Clients**: 600 per minute (100 per page)
- **Invoices**: 300 per minute (50 per page)
- **Total Migration Time**: ~50% faster

### With Parallel Processing (3 workers @ 6 req/sec)

- **Effective Rate**: 18 requests/second
- **Clients**: 1,800 per minute
- **Total Migration Time**: ~66% faster

## Best Practices

1. **Start Conservative**: Begin with moderate settings and increase gradually
2. **Monitor Actively**: Watch rate limit headers and adjust accordingly
3. **Handle Failures Gracefully**: Implement exponential backoff
4. **Test Thoroughly**: Run tests during different times of day
5. **Document Changes**: Keep logs of configuration adjustments

## Conclusion

The optimal configuration balances speed with reliability:

- **Recommended Rate**: 360 tokens/minute (6 req/sec)
- **Burst Capacity**: 400 tokens
- **Initial Tokens**: 60 (15% of capacity)

This provides:

- 2x improvement over current speed
- 28% safety margin from DDoS limits
- Room for burst traffic
- Stable, predictable performance

With parallel processing, we can achieve 3-6x performance improvement while maintaining system stability.
