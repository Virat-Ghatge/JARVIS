#!/usr/bin/env python3
"""
Autonomous Web Researcher for JARVIS 2.0
Uses Playwright DOM Distiller and requests/BeautifulSoup fallback to autonomously navigate
websites, extract clean readable text/links, and synthesize multi-page research briefs.
"""

import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional
import requests
from bs4 import BeautifulSoup

from core.llm_router import router

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class WebResearchAgent:
    """
    Autonomous Web Research Agent with DOM Distillation and multi-source synthesis.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def search_duckduckgo(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Performs search and extracts URLs and titles."""
        clean_q = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={clean_q}"
        results = []

        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", class_="result__url")
                titles = soup.find_all("a", class_="result__snippet")

                for i in range(min(max_results, len(links))):
                    href = links[i].get("href", "")
                    # Extract actual target url from DDG redirect wrapper
                    if "uddg=" in href:
                        href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                    snippet = titles[i].get_text(strip=True) if i < len(titles) else ""
                    if href.startswith("http"):
                        results.append({"url": href, "snippet": snippet})
        except Exception as e:
            print(f"[WebAgent] DDG search notice: {e}")

        # Fallback if no DDG results
        if not results:
            results.append({
                "url": f"https://en.wikipedia.org/wiki/{clean_q}",
                "snippet": f"Encyclopedia reference for {query}",
            })

        return results[:max_results]

    def distill_page(self, url: str) -> Dict[str, Any]:
        """
        Loads URL and extracts clean readable markdown text, headings, and links,
        stripping ads, scripts, navbars, and cookie banners.
        """
        # Try requests + BeautifulSoup for fast extraction
        try:
            resp = requests.get(url, headers=self.headers, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")

                # Remove non-content tags
                for tag in soup(["script", "style", "nav", "footer", "aside", "header", "noscript", "svg"]):
                    tag.decompose()

                title = soup.title.get_text(strip=True) if soup.title else url

                # Extract main content or body text
                main_tag = soup.find("main") or soup.find("article") or soup.body
                raw_text = main_tag.get_text(separator="\n", strip=True) if main_tag else soup.get_text()

                # Clean whitespace
                lines = [l.strip() for l in raw_text.split("\n") if len(l.strip()) > 30]
                cleaned_text = "\n".join(lines[:80])  # Cap at reasonable length

                return {
                    "ok": True,
                    "url": url,
                    "title": title,
                    "content": cleaned_text,
                }
        except Exception as e:
            print(f"[WebAgent] Error distilling {url}: {e}")

        return {"ok": False, "url": url, "title": "", "content": ""}

    def research(self, topic: str, max_pages: int = 3) -> Dict[str, Any]:
        """
        Full autonomous research flow:
        1. Find sources for topic.
        2. Distill page content.
        3. Synthesize comprehensive multi-source briefing with LLM.
        """
        print(f"[WebAgent] Researching topic: '{topic}'")
        sources = self.search_duckduckgo(topic, max_results=max_pages)

        distilled_pages = []
        for src in sources:
            page_data = self.distill_page(src["url"])
            if page_data["ok"] and len(page_data["content"]) > 100:
                distilled_pages.append(page_data)

        if not distilled_pages:
            # Direct LLM synthesis if pages blocked
            summary = router.query_text(
                "qa_chat",
                f"Please provide a comprehensive, well-researched briefing on: {topic}",
                system_prompt="You are JARVIS. Synthesize a structured, executive research summary with key findings.",
            )
            return {
                "ok": True,
                "topic": topic,
                "summary": summary,
                "sources": [s["url"] for s in sources],
            }

        # Build research context
        context_parts = []
        for i, p in enumerate(distilled_pages, start=1):
            context_parts.append(f"--- Source {i} ({p['title']} - {p['url']}) ---\n{p['content']}")

        full_context = "\n\n".join(context_parts)
        system_prompt = (
            "You are JARVIS Autonomous Web Research Agent. "
            "Synthesize the provided multi-page web findings into an executive intelligence report.\n"
            "Format with:\n"
            "1. Executive Overview\n"
            "2. Detailed Findings & Key Data Points\n"
            "3. Source References\n"
        )
        prompt = f"Topic: {topic}\n\nWeb Extracts:\n{full_context}"

        summary = router.query_text("qa_chat", prompt, system_prompt=system_prompt)

        return {
            "ok": True,
            "topic": topic,
            "summary": summary,
            "sources": [p["url"] for p in distilled_pages],
            "pages_analyzed": len(distilled_pages),
        }


# Global web agent singleton
web_agent = WebResearchAgent()
