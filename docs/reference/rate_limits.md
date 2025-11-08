---
hide:
  - navigation
  - toc
---

# Rate Limits Reference

**Version:** 1.0  **Last Updated:** 2025-11-05

---

## Overview

GitHub enforces two types of API rate limits that can affect migration performance and reliability:

- **Primary Rate Limits**: Quota-based limits (5,000 requests/hour) tracked via HTTP headers
- **Secondary Rate Limits**: Pattern-based abuse detection with no fixed quota or reset time

The migration tool automatically handles both types with exponential backoff, user interaction, and configurable delays.

---

## Primary Rate Limits

### Characteristics

- **Quota**: 5,000 requests per hour for authenticated requests
- **Reset**: Hourly at the start of each hour (UTC)
- **Tracking**: Via `X-RateLimit-Remaining` and `X-RateLimit-Reset` headers
- **Scope**: Per user/token

### Detection

The tool detects primary rate limits by checking:

```python
response.headers.get('X-RateLimit-Remaining') == '0'
```

### Handling

- Waits until the reset time indicated in `X-RateLimit-Reset` header
- No user interaction required (automatic)
- Exponential backoff not needed (fixed reset time)

---

## Secondary Rate Limits (Abuse Detection)

### Characteristics

- **No fixed quota**: Triggered by request patterns GitHub considers abusive
- **No fixed reset time**: Typically clears in 5-10 minutes, but can vary
- **Triggers**: Too many requests in short time, concurrent requests, unusual patterns
- **Response**: HTTP 403 with abuse detection message

### Common Triggers

- Multiple concurrent API calls
- High-frequency requests without delays
- Unusual request patterns
- Large batch operations

### Detection

The tool detects secondary limits by parsing error responses for keywords:

```python
is_secondary = any(keyword in error_msg for keyword in ['abuse', 'secondary'])
```

### Handling

- **Exponential backoff**: Starts at 180 seconds, doubles each retry (180s → 360s → 720s → 1440s, capped at 8x multiplier)
- **User interaction**: Prompts for manual retry after maximum backoff attempts
- **Configurable delays**: `request_delay_seconds` setting spaces out requests

---

## Configuration Options

### Request Delay

Configure spacing between mutative requests:

```json
{
  "options": {
    "request_delay_seconds": 1.5
  }
}
```

- **Default**: 1.5 seconds
- **Purpose**: Prevents triggering secondary rate limits
- **Applied to**: Issue creation, PR creation, comment posting, label updates, milestone operations

### Best Practice Values

| Scenario | Recommended Delay | Rationale |
|----------|------------------|-----------|
| Small repositories (< 100 issues) | 1.0s | Faster migration for simple cases |
| Medium repositories (100-1000 issues) | 1.5s | Balance speed and reliability |
| Large repositories (> 1000 issues) | 2.0s | Conservative approach for big migrations |
| Problematic tokens | 3.0s | Extra caution for rate limit history |

---

## User Interaction

When automatic retries are exhausted, the tool prompts for user action:

### User Interaction Prompts

When automatic retries are exhausted, the tool displays detailed information and prompts for user action:

```
============================================================
⚠️  GITHUB API RATE LIMIT - ALL RETRIES EXHAUSTED
============================================================
Error: GitHub API secondary rate limit (abuse detection) exceeded. Please wait before retrying.
URL: https://api.github.com/repos/owner/repo/issues
Max retries: 5

This appears to be GitHub's abuse detection (secondary rate limit).
Unlike primary rate limits, secondary limits don't have specific reset times.

Recommended actions:
  1. Wait 5-10 minutes before retrying (allows abuse detection to clear)
  2. Increase config.options.request_delay_seconds (currently controls delays)
  3. Continue with migration (may hit limit again if pattern persists)

What would you like to do? (t)ry again, (w)ait longer, (c)ontinue, or (q)uit:
```

**"(t)ry again" vs "(w)ait longer"**: Both options prompt for a wait time, but they provide different default values based on the rate limit type:

- **"(t)ry again"**: Retries immediately without waiting (user can override with custom wait time)
- **"(w)ait longer"**: Uses a longer default wait time (15 minutes for secondary limits, 60 minutes for primary limits)

If the user chooses either option, they are prompted for wait time:

```
How many minutes to wait before retrying? (default 10):
```

---

## Prevention Strategies

### 1. Token Selection

- Use a **Personal Access Token (PAT)** with `repo` scope
- Avoid using OAuth tokens with broader scopes
- Consider using a secondary account if primary has rate limit history

### 2. Timing

- Run migrations during **off-peak hours** (UTC nighttime)
- Avoid running multiple migrations simultaneously
- Schedule large migrations during weekends if possible

### 3. Configuration Tuning

```json
{
  "options": {
    "request_delay_seconds": 2.0
  }
}
```

### 4. Batch Size Awareness

- Large repositories may need longer delays
- Monitor initial migration runs and adjust delays accordingly
- Consider splitting very large migrations into phases

---

## Troubleshooting

### Common Issues

#### "Abuse detection triggered immediately"

**Symptoms**: Rate limit error on first few requests

**Solutions**:

- Increase `request_delay_seconds` to 3.0
- Use a different GitHub token
- Wait 10-15 minutes before retrying

#### "Rate limit persists after waiting"

**Symptoms**: Continues failing even after backoff periods

**Solutions**:

- Check token permissions and validity
- Verify network connectivity
- Consider using a different GitHub account/token
- Contact GitHub support if issue persists

#### "Inconsistent rate limiting"

**Symptoms**: Works sometimes, fails other times

**Solutions**:

- Increase delays consistently
- Run during off-peak hours
- Monitor GitHub status page for API issues

### Diagnostic Information

The tool provides detailed logging for rate limit events:

```
2025-11-08 00:33:53 - INFO -   Created update comment for PR #62
2025-11-08 00:33:54 - ERROR - GitHub API rate limit exceeded. Please wait before retrying.
2025-11-08 00:33:54 - INFO - Rate limit type: secondary (abuse detection)
2025-11-08 00:33:54 - INFO - Waiting 180 seconds before retry...
```

### Recovery Steps

1. **Identify limit type** from error message and logs
2. **Wait appropriate time** (5-10 min for secondary, until reset for primary)
3. **Retry with increased delays** if needed
4. **Consider token rotation** for persistent issues

---

## API Reference

### Rate Limit Headers

GitHub provides rate limit information in response headers:

- `X-RateLimit-Limit`: Maximum requests per hour
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when limit resets
- `X-RateLimit-Used`: Requests used in current window (GitHub Apps only)

### Error Response Format

Primary rate limit (HTTP 403):
```json
{
  "message": "API rate limit exceeded for user ID 12345.",
  "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting"
}
```

Secondary rate limit (HTTP 403):
```json
{
  "message": "You have triggered an abuse detection mechanism. Please wait a few minutes before you try again.",
  "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api#secondary-rate-limits"
}
```

---

## Related Documentation

- [GitHub API Rate Limiting](https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting)
- [Secondary Rate Limits](https://docs.github.com/rest/overview/resources-in-the-rest-api#secondary-rate-limits)
- [Migration Config Reference](migration_config.md)
- [CLI Reference](cli_reference.md)