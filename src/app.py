import streamlit as st
import os
from dotenv import load_dotenv
from datetime import datetime
import json
import asyncio
from typing import Dict, List
import pandas as pd

from crawler import WebCrawler
from feature_extractor import FeatureExtractor

# Load environment variables
load_dotenv()

# Set page config
st.set_page_config(
    page_title="Web Feature Analyzer",
    page_icon="🔍",
    layout="wide"
)

# Initialize session state
if 'crawled_data' not in st.session_state:
    st.session_state.crawled_data = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None

def save_crawled_data(data: List[Dict], output_dir: str = "crawled_data") -> str:
    """Save crawled data to JSON file."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"crawled_data_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return filepath

def display_analysis_results(results: Dict):
    """Display analysis results in a structured format."""
    st.header("Analysis Results")
    
    # Site Overview
    st.subheader("Site Overview")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Pages Analyzed", results["site_overview"]["total_pages"])
    with col2:
        st.metric("Analysis Time", results["site_overview"]["analysis_timestamp"])
    
    # Aggregated Features
    st.subheader("Aggregated Features")
    
    # UI Features
    with st.expander("User Interface Features"):
        for feature in results["aggregated_features"]["ui_features"]:
            st.write(f"• {feature}")
    
    # Functionality
    with st.expander("Functionality"):
        for feature in results["aggregated_features"]["functionality"]:
            st.write(f"• {feature}")
    
    # Business Features
    with st.expander("Business Features"):
        for feature in results["aggregated_features"]["business_features"]:
            st.write(f"• {feature}")
    
    # Workflows
    with st.expander("Workflows"):
        for workflow in results["aggregated_features"]["workflows"]:
            st.write(f"• {workflow}")
    
    # Page Details
    st.subheader("Page Details")
    for page in results["page_details"]:
        with st.expander(f"{page['title']} ({page['url']})"):
            st.write("**Features:**")
            for category, features in page["features"].items():
                st.write(f"**{category.replace('_', ' ').title()}:**")
                for feature in features:
                    st.write(f"• {feature}")

def main():
    st.title("Web Feature Analyzer")
    st.write("Analyze website features and workflows using GPT-4")
    
    # Input fields
    url = st.text_input("Enter URL to analyze:", placeholder="https://example.com")
    api_key = st.text_input("OpenAI API Key:", type="password", 
                           value=os.getenv("OPENAI_API_KEY", ""))
    
    # Crawling options
    col1, col2 = st.columns(2)
    with col1:
        max_pages = st.number_input("Maximum pages to crawl:", 
                                  min_value=1, max_value=100, value=10)
    with col2:
        timeout = st.number_input("Timeout (seconds):", 
                                min_value=10, max_value=300, value=30)
    
    # Start analysis button
    if st.button("Start Analysis"):
        if not url or not api_key:
            st.error("Please provide both URL and API key")
            return
        
        try:
            with st.spinner("Crawling website..."):
                # Initialize crawler
                crawler = WebCrawler(
                    base_url=url,
                    max_pages=max_pages,
                    timeout=timeout * 1000  # Convert to milliseconds
                )
                
                # Run crawler
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                crawled_data = loop.run_until_complete(crawler.start_crawling())
                loop.close()
                
                # Save crawled data
                if crawled_data:
                    filepath = save_crawled_data(crawled_data)
                    st.session_state.crawled_data = crawled_data
                    st.success(f"Crawled {len(crawled_data)} pages. Data saved to {filepath}")
                else:
                    st.error("Failed to crawl website")
                    return
            
            with st.spinner("Analyzing features with GPT-4..."):
                # Initialize feature extractor
                extractor = FeatureExtractor(api_key=api_key)
                
                # Analyze site
                try:
                    analysis_results = extractor.analyze_site(crawled_data)
                except TypeError as e:
                    st.error(f"Error analyzing site: {str(e)}")
                    st.code(json.dumps(crawled_data[:2], indent=2))  # Show the first 2 pages for debugging
                    raise
                st.session_state.analysis_results = analysis_results
                
                # Display results
                display_analysis_results(analysis_results)
                
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            st.stop()
    
    # Display previous results if available
    if st.session_state.analysis_results:
        st.write("---")
        st.subheader("Previous Analysis Results")
        display_analysis_results(st.session_state.analysis_results)

if __name__ == "__main__":
    main() 