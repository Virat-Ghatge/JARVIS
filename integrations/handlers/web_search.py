#!/usr/bin/env python3
"""
Web Search Module
Handles multi-engine web search queries with DuckDuckGo, Wikipedia API fallback, and browser search.
"""

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Dict, List, Optional


class WebSearchHandler:
    """Handles web search operations with multi-engine fallback and structured responses."""

    def __init__(self, jarvis: Optional[Any] = None) -> None:
        self.jarvis: Optional[Any] = jarvis
        self.default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

    def _extract_query(self, command: str) -> str:
        """Cleanly extracts the core search query from a voice or text command."""
        cmd = command.strip()
        low = cmd.lower()

        # Remove leading trigger phrases
        prefixes = [
            "search the web for",
            "search google for",
            "search duckduckgo for",
            "search web for",
            "web search for",
            "search for",
            "look up",
            "find info about",
            "find information on",
            "find information about",
            "what is the definition of",
            "who is",
            "what is",
            "where is",
            "google",
            "search",
            "web search",
        ]
        for p in prefixes:
            if low.startswith(p):
                cmd = cmd[len(p):].strip()
                break

        # Remove trailing noise words
        cmd = re.sub(r"\b(on google|on the web|on internet|online)\b", "", cmd, flags=re.IGNORECASE).strip()
        cmd = cmd.strip("\"'.,?!")
        return cmd if cmd else command.strip()

    def _query_duckduckgo(self, query: str) -> List[Dict[str, str]]:
        """Queries DuckDuckGo HTML/lite interface for fast headless search snippets."""
        results: List[Dict[str, str]] = []
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"

        req = urllib.request.Request(url, headers=self.default_headers)
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    raw_html = resp.read().decode("utf-8", errors="ignore")
                    # Extract result links and snippets
                    # Pattern matches DuckDuckGo HTML results
                    snippets = re.findall(
                        r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                        raw_html,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    titles = re.findall(
                        r'<a[^>]*class="[^"]*result__url[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                        raw_html,
                        flags=re.DOTALL | re.IGNORECASE,
                    )

                    for i in range(min(len(snippets), 5)):
                        clean_snip = html.unescape(re.sub(r"<[^>]+>", "", snippets[i])).strip()
                        raw_href = titles[i][0] if i < len(titles) else ""
                        raw_title = html.unescape(re.sub(r"<[^>]+>", "", titles[i][1])) if i < len(titles) else query

                        # Decode DDG redirect URL if present
                        if "uddg=" in raw_href:
                            try:
                                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                                actual_url = parsed.get("uddg", [raw_href])[0]
                            except Exception:
                                actual_url = raw_href
                        else:
                            actual_url = raw_href

                        if clean_snip:
                            results.append({
                                "title": raw_title or query,
                                "snippet": clean_snip,
                                "url": actual_url or f"https://duckduckgo.com/?q={encoded}",
                            })
        except Exception as e:
            print(f"[WebSearchHandler] DuckDuckGo query error: {e}")

        return results

    def _query_wikipedia(self, query: str) -> List[Dict[str, str]]:
        """Queries Wikipedia API for entity summaries and conceptual definitions."""
        results: List[Dict[str, str]] = []
        encoded = urllib.parse.quote_plus(query)
        api_url = (
            f"https://en.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={encoded}&format=json&utf8=1"
        )
        headers = {"User-Agent": "JARVIS-Assistant/3.0 (https://github.com/jarvis)"}
        req = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    search_items = data.get("query", {}).get("search", [])
                    for item in search_items[:3]:
                        title = item.get("title", "")
                        raw_snip = item.get("snippet", "")
                        clean_snip = html.unescape(re.sub(r"<[^>]+>", "", raw_snip)).strip()
                        wiki_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                        if clean_snip:
                            results.append({
                                "title": title,
                                "snippet": clean_snip,
                                "url": wiki_url,
                            })
        except Exception as e:
            print(f"[WebSearchHandler] Wikipedia API error: {e}")

        return results

    def web_search(self, command: str) -> Dict[str, Any]:
        """
        Executes multi-engine search:
        1. DuckDuckGo HTML headless search
        2. Wikipedia conceptual API fallback
        3. Browser search fallback if headless queries fail
        Returns structured dictionary.
        """
        query = self._extract_query(command)
        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://www.google.com/search?q={encoded}"

        results: List[Dict[str, str]] = []

        # 1. Try DuckDuckGo headless
        if query:
            results = self._query_duckduckgo(query)

        # 2. Try Wikipedia fallback if no results
        if not results and query:
            results = self._query_wikipedia(query)

        # 3. Fallback to browser search if headless requests returned nothing or failed
        if not results:
            try:
                webbrowser.open(search_url)
            except Exception:
                pass
            reply = f"Searching Google for '{query}', sir."
        else:
            top_snippet = results[0].get("snippet", "")
            if len(top_snippet) > 280:
                top_snippet = top_snippet[:280] + "..."
            reply = f"Here is what I found for '{query}': {top_snippet}"

        if self.jarvis and hasattr(self.jarvis, "speak"):
            self.jarvis.speak(reply)

        return {
            "reply": reply,
            "action": "web_search",
            "data": {
                "query": query,
                "results": results,
                "url": results[0].get("url") if results else search_url,
            },
        }


# Module-level singleton and helper functions for functional routing
web_search_handler: WebSearchHandler = WebSearchHandler(None)

def web_search(command: str) -> Dict[str, Any]:
    """Module-level entry point for web search."""
    return web_search_handler.web_search(command)

def handle_search(command: str) -> Dict[str, Any]:
    """Alias for web_search."""
    return web_search_handler.web_search(command)

def search_web(command: str) -> Dict[str, Any]:
    """Alias for web_search."""
    return web_search_handler.web_search(command)
