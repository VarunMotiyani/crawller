import json
import logging
from typing import Dict, List, Any
from datetime import datetime
from openai import OpenAI

class FeatureExtractor:
    def __init__(self, api_key: str):
        """Initialize the feature extractor with OpenAI API key."""
        self.client = OpenAI(api_key=api_key)
        self.logger = logging.getLogger(__name__)
        
    def analyze_page(self, page_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single page's content using GPT-4."""
        try:
            # Prepare content for analysis
            content = f"""
            Title: {page_data.get('title', '')}
            URL: {page_data.get('url', '')}
            Content: {page_data.get('content', '')}
            Forms: {page_data.get('forms', [])}
            """
            
            # Construct prompt for GPT-4
            prompt = f"""
            Analyze the following webpage content and extract features and workflows.
            Focus on identifying:
            1. UI features (navigation, forms, buttons, etc.)
            2. Functionality (what users can do)
            3. Business features (e-commerce, user management, etc.)
            4. Workflows (multi-step processes)
            
            Content:
            {content}
            
            Return a JSON object with the following structure:
            {{
                "ui_features": ["list of UI features"],
                "functionality": ["list of functionality"],
                "business_features": ["list of business features"],
                "workflows": ["list of workflows"]
            }}
            
            IMPORTANT: Return ONLY the JSON object, with no additional text or explanation.
            """
            
            # Call GPT-4
            response = self.client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18",
                messages=[
                    {"role": "system", "content": "You are a web feature analyzer. Extract features and workflows from web content. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000,
                response_format={ "type": "json_object" }
            )
            
            # Get the response content
            response_content = response.choices[0].message.content
            
            # Try to parse the JSON response
            try:
                result = json.loads(response_content)
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON response: {str(e)}")
                self.logger.error(f"Response content: {response_content}")
                # Return default structure if parsing fails
                result = {
                    "ui_features": [],
                    "functionality": [],
                    "business_features": [],
                    "workflows": []
                }
            
            # Validate the result structure
            if not isinstance(result, dict):
                self.logger.error(f"Invalid response type: {type(result)}")
                result = {
                    "ui_features": [],
                    "functionality": [],
                    "business_features": [],
                    "workflows": []
                }
            
            # Ensure all required fields are present
            for field in ["ui_features", "functionality", "business_features", "workflows"]:
                if field not in result or not isinstance(result[field], list):
                    result[field] = []
            
            return {
                "url": page_data.get("url", ""),
                "title": page_data.get("title", ""),
                "features": result
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing page {page_data.get('url', '')}: {str(e)}")
            return {
                "url": page_data.get("url", ""),
                "title": page_data.get("title", ""),
                "features": {
                    "ui_features": [],
                    "functionality": [],
                    "business_features": [],
                    "workflows": []
                }
            }
    
    # def analyze_site(self, crawled_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    #     """Analyze all crawled pages and generate a comprehensive report."""
    #     page_analyses = []
    #     unique_features = {
    #         "ui_features": set(),
    #         "functionality": set(),
    #         "business_features": set(),
    #         "workflows": set()
    #     }
        
    #     # Analyze each page
    #     for page_data in crawled_data:
    #         analysis = self.analyze_page(page_data)
    #         page_analyses.append(analysis)
            
    #         # Collect unique features
    #         for category in unique_features:
    #             unique_features[category].update(analysis["features"][category])
        
    #     # Generate final report
    #     return {
    #         "site_overview": {
    #             "total_pages": len(page_analyses),
    #             "analysis_timestamp": datetime.now().isoformat()
    #         },
    #         "aggregated_features": {
    #             category: list(features)
    #             for category, features in unique_features.items()
    #         },
    #         "page_details": page_analyses
    #     } 

    def analyze_site(self, crawled_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze all crawled pages and generate a comprehensive report."""
        page_analyses = []
        unique_features = {
            "ui_features": set(),
            "functionality": set(),
            "business_features": set(),
            "workflows": set()
        }

        seen_urls = set()  # Track already analyzed URLs

        # Analyze each page
        for page_data in crawled_data:
            url = page_data.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            analysis = self.analyze_page(page_data)
            page_analyses.append(analysis)

            # Safely collect only hashable items (e.g., feature names)
            for category in unique_features:
                for feature in analysis["features"][category]:
                    if isinstance(feature, dict):
                        # Assume each feature dict has a "name" key
                        feature_name = feature.get("name")
                        if feature_name:
                            unique_features[category].add(feature_name)
                    elif isinstance(feature, str):
                        unique_features[category].add(feature)

        # Generate final report
        return {
            "site_overview": {
                "total_pages": len(page_analyses),
                "analysis_timestamp": datetime.now().isoformat()
            },
            "aggregated_features": {
                category: list(features)
                for category, features in unique_features.items()
            },
            "page_details": page_analyses
        }

