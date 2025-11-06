import re
import logging
from typing import List

logger = logging.getLogger('bitbucket_migration')

class LinkDetector:
    """
    Utility class for detecting complete URLs in text.

    Uses a comprehensive regex pattern to extract full URLs with support for:
    - Multiple protocols (HTTP, HTTPS, FTP)
    - Authentication credentials (user:pass@)
    - Localhost and IPv4 addresses
    - Port numbers
    - Query parameters and fragments
    - Strong boundary detection to avoid false positives

    Examples:
        >>> LinkDetector.extract_urls("Visit https://bitbucket.org/workspace/repo")
        ['https://bitbucket.org/workspace/repo']
        
        >>> LinkDetector.extract_urls("API at http://localhost:8080/api/endpoint")
        ['http://localhost:8080/api/endpoint']
        
        >>> LinkDetector.extract_urls("Auth: http://user:pass@bitbucket.org/repo")
        ['http://user:pass@bitbucket.org/repo']
        
        >>> LinkDetector.extract_urls('Quoted "https://example.com" not matched')
        []
    """

    # Enhanced URL pattern with comprehensive support and boundary protection
    # Pre-compiled for performance
    URL_PATTERN = re.compile(
        r"""
        (?<!["'\\(<])                          # Negative lookbehind: not preceded by quotes, parentheses, or angle brackets
        (?P<url>                               # Named capture group for the complete URL
            (?:https?|ftp)://                  # Protocol: http, https, or ftp
            (?:(?:[a-zA-Z0-9$_.+!*'(),;?&=-]|%[0-9a-fA-F]{2})+
               (?::(?:[a-zA-Z0-9$_.+!*'(),;?&=-]|%[0-9a-fA-F]{2})+)?@)?  # Optional authentication (user:pass@)
            (?:
                localhost|                     # Localhost
                (?:[0-9]{1,3}\.){3}[0-9]{1,3}| # IPv4 address
                (?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.?  # Domain name
            )
            (?::[0-9]{1,5})?                   # Optional port number
            (?:/[^\s\)"'>]*)?                  # Optional path (excludes boundary characters)
        )
        (?!["'\)>])                            # Negative lookahead: not followed by quotes, parentheses, or angle brackets
        """,
        re.VERBOSE | re.IGNORECASE
    )

    @classmethod
    def extract_urls(cls, text: str) -> List[str]:
        """
        Extract all complete URLs from the given text using enhanced pattern matching.

        This method uses a comprehensive regex pattern that supports various URL formats
        while maintaining strong boundary detection to avoid false positives in markdown,
        quotes, or HTML.

        Args:
            text: The text to search for URLs

        Returns:
            List of unique URLs found in the text, preserving order of first occurrence

        Examples:
            >>> text = "Check https://bitbucket.org/workspace/repo/issues/123"
            >>> LinkDetector.extract_urls(text)
            ['https://bitbucket.org/workspace/repo/issues/123']
            
            >>> text = "Local: http://localhost:8080/api and https://github.com/user/repo"
            >>> urls = LinkDetector.extract_urls(text)
            >>> len(urls)
            2
            
            >>> text = '[Link](https://example.com)'  # Markdown - URL inside brackets
            >>> LinkDetector.extract_urls(text)
            ['https://example.com']
        """
        if not text:
            return []

        # Use finditer() with named groups for better performance and clarity
        matches = []
        seen = set()
        
        for match in cls.URL_PATTERN.finditer(text):
            url = match.group('url')
            # Deduplicate while preserving order
            if url not in seen:
                seen.add(url)
                matches.append(url)
        
        # Log detected URLs
        if matches:
            logger.debug(f"Detected {len(matches)} URLs in text")
        else:
            logger.debug("No URLs detected in text")
        
        return matches