import asyncio
import logging
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page, TimeoutError, Error
import json
import os
from datetime import datetime
from collections import defaultdict
import re

class WebCrawler:
    def __init__(
        self,
        base_url: str,
        max_pages: int = 100,
        timeout: int = 30000,
        max_retries: int = 3,
        headless: bool = True,
        retry_delay: int = 2,
        # progress_callback: Optional[Callable[[float], None]] = None
    ):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.max_pages = max_pages
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        # self.progress_callback = progress_callback
        self.headless = headless
        # Track visited and failed URLs
        self.visited_urls: Set[str] = set()
        self.failed_urls: Set[str] = set()
        self.results: List[Dict] = []
        self.to_visit: Set[str] = set()
        self.crawled_data = []

        # Track link depth
        self.url_depth: Dict[str, int] = defaultdict(int)

        self.route_stats: Dict[str, Dict] = defaultdict(lambda: {
        "success_count": 0,
        "error_count": 0,
        "avg_content_length": 0,
        "last_visited": None,
        "priority": 0.5  # Initial priority
        })
        
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.DEBUG)

    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and belongs to the same domain."""
        try:
            parsed_url = urlparse(url)
            base_domain = urlparse(self.base_url).netloc
            return (
                parsed_url.scheme in ['http', 'https'] and
                parsed_url.netloc.endswith(base_domain)  # allow subdomains
            )
        except Exception as e:
            self.logger.error(f"Error validating URL {url}: {str(e)}")
            return False

    # def normalize_url(self, url: str) -> str:
    #     """Normalize URL by removing fragments and query parameters."""
    #     try:
    #         parsed = urlparse(url)
    #         # return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    #         return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{parsed.query}".rstrip('?')
    #     except Exception as e:
    #         self.logger.error(f"Error normalizing URL {url}: {str(e)}")
    #         return url

    def normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragments and query parameters."""
        try:
            parsed = urlparse(url)
            # Keep query parameters for Wikipedia URLs as they might be important
            if parsed.netloc.endswith('.wikipedia.org'):
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{'?' + parsed.query if parsed.query else ''}"
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except Exception as e:
            self.logger.error(f"Error normalizing URL {url}: {str(e)}")
            return url

    def analyze_route(self, url: str) -> Tuple[float, str]:
        """Analyze a URL to determine its priority and category."""
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()
            query = parse_qs(parsed.query)
            
            # Route categorization
            if path.endswith('.html') or path.endswith('.php'):
                return 0.8, 'dynamic_page'
            elif '/wiki/' in path:
                return 1.0, 'article'
            elif '/category/' in path:
                return 0.9, 'category'
            elif '/search' in path:
                return 0.3, 'search'
            elif '/user/' in path:
                return 0.2, 'user_profile'
            elif '/admin/' in path:
                return 0.1, 'admin'
            else:
                return 0.5, 'other'
        except Exception as e:
            self.logger.error(f"Error analyzing route {url}: {str(e)}")
            return 0.5, 'unknown'

    def update_route_stats(self, url: str, success: bool, content_length: int):
        """Update statistics for a route."""
        route = urlparse(url).path
        stats = self.route_stats[route]
        
        if success:
            stats["success_count"] += 1
            # Update average content length
            if stats["avg_content_length"] == 0:
                stats["avg_content_length"] = content_length
            else:
                stats["avg_content_length"] = (stats["avg_content_length"] + content_length) / 2
        else:
            stats["error_count"] += 1
        
        stats["last_visited"] = datetime.now().isoformat()
        
        # Calculate priority based on success rate and content length
        total_attempts = stats["success_count"] + stats["error_count"]
        success_rate = stats["success_count"] / total_attempts if total_attempts > 0 else 0
        content_factor = min(1.0, stats["avg_content_length"] / 10000)  # Normalize content length
        
        stats["priority"] = (success_rate * 0.7 + content_factor * 0.3)

    def get_next_url(self) -> Optional[str]:
        """Get the next URL to visit based on priority."""
        if not self.to_visit:
            return None
            
        # Sort URLs by priority
        sorted_urls = sorted(
            self.to_visit,
            key=lambda url: self.route_stats[urlparse(url).path]["priority"],
            reverse=True
        )
        
        return sorted_urls[0] if sorted_urls else None

    # async def extract_links(self, page: Page) -> List[str]:
    #     try:
    #         page_url = page.url

    #         # Get raw hrefs using JavaScript
    #         raw_links = await page.evaluate("""() => 
    #             Array.from(document.querySelectorAll('a'))
    #                 .map(a => a.getAttribute('href'))
    #                 .filter(href => href && !href.startsWith('javascript:'));
    #         """)

    #         all_links = []
    #         for link in raw_links:
    #             joined_link = urljoin(page_url, link)  # handles protocol-relative and relative links
    #             normalized = self.normalize_url(joined_link)

    #             if self.is_valid_url(normalized):
    #                 all_links.append(normalized)

    #         print(f"[extract_links] {page_url} -> {len(all_links)} valid links found")
    #         return list(set(all_links))  # deduplicate
    #     except Exception as e:
    #         self.logger.error(f"Error extracting links: {str(e)}")
    #         return []


    async def extract_links(self, page: Page, current_url: str) -> List[str]:
        """Extract all valid links from the page with depth tracking."""
        try:
            await page.wait_for_load_state("networkidle")
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                # Skip special Wikipedia links
                if href.startswith(('#', '/wiki/Special:', '/wiki/Help:', '/wiki/File:')):
                    continue
                    
                absolute_url = urljoin(self.base_url, href)
                
                if self.is_valid_url(absolute_url):
                    normalized_url = self.normalize_url(absolute_url)
                    if normalized_url not in self.visited_urls and normalized_url not in self.failed_urls:
                        # Track link depth
                        self.url_depth[normalized_url] = self.url_depth[current_url] + 1
                        links.append(normalized_url)
            
            return list(set(links))
        except Exception as e:
            self.logger.error(f"Error extracting links: {str(e)}")
            return []


    # async def extract_page_data(self, page: Page) -> Dict:
    #     """Extract relevant data from the page."""
    #     try:
    #         content = await page.content()
    #         soup = BeautifulSoup(content, 'html.parser')

    #         forms = []
    #         for form in soup.find_all('form'):
    #             form_data = {
    #                 'action': form.get('action', ''),
    #                 'method': form.get('method', 'get'),
    #                 'inputs': [
    #                     {
    #                         'name': input.get('name', ''),
    #                         'type': input.get('type', 'text')
    #                     }
    #                     for input in form.find_all('input')
    #                 ]
    #             }
    #             forms.append(form_data)

    #         return {
    #             'url': page.url,
    #             'title': await page.title(),
    #             'content': soup.get_text(separator=' ', strip=True)[:500],  # clip for brevity
    #             'forms': forms,
    #             'links': await self.extract_links(page)
    #         }

    #     except Exception as e:
    #         self.logger.error(f"Error extracting page data: {str(e)}")
    #         return {
    #             'url': page.url,
    #             'title': '',
    #             'content': '',
    #             'forms': [],
    #             'links': []
    #         }


    async def extract_page_data(self, page: Page, url: str) -> Dict:
        """Extract relevant data from the page."""
        try:
            await page.wait_for_load_state("networkidle")
            content = await page.content()
            title = await page.title()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script, style, and navigation elements
            for element in soup(["script", "style", "nav", "header", "footer"]):
                element.decompose()
            
            # Get text content
            text = soup.get_text(separator=' ', strip=True)
            
            # Extract metadata
            metadata = {
                "url": url,
                "title": title,
                "timestamp": datetime.now().isoformat(),
                "headers": [h.get_text().strip() for h in soup.find_all(['h1', 'h2', 'h3'])],
                "forms": len(soup.find_all('form')),
                "links": len(soup.find_all('a')),
                "images": len(soup.find_all('img')),
                "depth": self.url_depth[url]
            }
            
            return {
                "url": url,
                "title": title,
                "content": text,
                "metadata": metadata
            }
        except Exception as e:
            self.logger.error(f"Error extracting data from {url}: {str(e)}")
            return {
                "url": url,
                "title": "",
                "content": "",
                "metadata": {}
            }

    # async def crawl_page(self, url: str, browser: Browser) -> Optional[Dict]:
    #     """Crawl a single page and return its data."""
    #     normalized_url = self.normalize_url(url)
    #     if normalized_url in self.visited_urls:
    #         print(f"[crawl_page] Already visited: {normalized_url}")
    #         return None

    #     print(f"[crawl_page] Crawling: {normalized_url}")
    #     self.visited_urls.add(normalized_url)

    #     try:
    #         page = await browser.new_page()
    #         await page.goto(normalized_url, timeout=self.timeout)
    #         await page.wait_for_load_state('networkidle')

    #         data = await self.extract_page_data(page)
    #         self.crawled_data.append(data)

    #         if self.progress_callback:
    #             progress = len(self.visited_urls) / self.max_pages
    #             self.progress_callback(progress)

    #         return data
    #     except Exception as e:
    #         self.logger.error(f"Error crawling page {url}: {str(e)}")
    #         return None
    #     finally:
    #         try:
    #             await page.close()
    #         except Exception:
    #             pass

    async def crawl_page(self, page: Page, url: str) -> None:
        """Crawl a single page with improved error handling."""
        if url in self.visited_urls or url in self.failed_urls or len(self.visited_urls) >= self.max_pages:
            return

        for retry in range(self.max_retries):
            try:
                self.logger.info(f"Crawling: {url} (attempt {retry + 1}/{self.max_retries})")
                
                response = await page.goto(url, timeout=self.timeout, wait_until="networkidle")
                
                if response and response.status == 200:
                    self.visited_urls.add(url)
                    
                    # Extract data and links
                    page_data = await self.extract_page_data(page, url)
                    self.results.append(page_data)
                    
                    # Save intermediate results
                    self.save_results()
                    
                    # self.save_markdown_report()
                    # self.save_json_summary()
                    # Extract and add new links to the queue
                    links = await self.extract_links(page, url)
                    self.to_visit.update(links)
                    
                    break  # Success, exit retry loop
                else:
                    self.logger.warning(f"Failed to load {url} (status: {response.status if response else 'unknown'})")
                    if retry == self.max_retries - 1:
                        self.failed_urls.add(url)
                    
            except TimeoutError:
                self.logger.warning(f"Timeout while crawling {url}")
                if retry == self.max_retries - 1:
                    self.failed_urls.add(url)
            except Error as e:
                self.logger.error(f"Playwright error while crawling {url}: {str(e)}")
                if retry == self.max_retries - 1:
                    self.failed_urls.add(url)
            except Exception as e:
                self.logger.error(f"Error crawling {url}: {str(e)}")
                if retry == self.max_retries - 1:
                    self.failed_urls.add(url)
            
            if retry < self.max_retries - 1:
                self.logger.info(f"Retrying in {self.retry_delay} seconds...")
                await asyncio.sleep(self.retry_delay)



    def save_results(self) -> None:
        """Save crawling results to JSON file."""
        try:
            output_file = os.path.join(self.output_dir, "crawled_data.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Error saving results: {str(e)}")



    async def start_crawling(self) -> List[Dict]:
        """Start the crawling process with improved link traversal."""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                page = await browser.new_page()
                
                await page.set_viewport_size({"width": 1280, "height": 800})
                
                # Start with the base URL
                self.to_visit.add(self.base_url)
                self.url_depth[self.base_url] = 0
                
                # Process URLs until we reach max_pages or run out of URLs
                while self.to_visit and len(self.visited_urls) < self.max_pages:
                    # Get the next URL to visit
                    next_url = self.to_visit.pop()
                    
                    # Skip if already visited or failed
                    if next_url in self.visited_urls or next_url in self.failed_urls:
                        continue
                    
                    # Skip if depth is too deep (optional)
                    if self.url_depth[next_url] > 5:  # Limit depth to 5 levels
                        self.logger.info(f"Skipping deep URL: {next_url} (depth: {self.url_depth[next_url]})")
                        continue
                    
                    await self.crawl_page(page, next_url)
                
                await browser.close()
                
                # Print summary
                self.logger.info(f"\nCrawling completed!")
                self.logger.info(f"Total pages crawled: {len(self.visited_urls)}")
                self.logger.info(f"Failed URLs: {len(self.failed_urls)}")
                # self.logger.info(f"Results saved to: {self.output_dir}/crawled_data.json")
                
            return self.results
        except Exception as e:
            self.logger.error(f"Error during crawling: {str(e)}")
            return [] 
