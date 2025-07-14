import json
from pathlib import Path
from typing import Dict, Any
from qdrant_client.http import models 

from app.services.embeddings_service import EmbeddingService
from app.external_services.claude_ai_client import ClaudeAIClient
from app.models.api.agent_router import ProjectResponse
from app.utils.projects_utils import format_context_texts, extract_source_info, sort_priority, truncate_contexts, find_urls_in_metadata

class ProjectAgent:
    """Handles project validation and queries using embeddings and vector DB matching"""
    def __init__(self):
        prompt_path = Path(__file__).parent / "prompt" / "project_prompt.json"
        with open(prompt_path) as f:
            self.prompt_config = json.load(f)['project_agent_prompt']
    
    async def process(self, user_message: str) -> Dict[str, Any]:
        try:
            user_message_embeddings = EmbeddingService.create_embeddings(user_message)
    
            query_response = await EmbeddingService.get_embeddings(
                vector=user_message_embeddings,
                limit=self.prompt_config['rag_settings'].get('search_depth', 5),
                threshold=None
            )

            expanded_contexts = []
            available_sources = set()

            if query_response and isinstance(query_response[0], dict):
                seen_docs = set()

                for item in query_response:
                    metadata = item.get('metadata', {})
                    doc_id = metadata.get('document_id')
                    if not doc_id or doc_id in seen_docs:
                        continue
                    
                    seen_docs.add(doc_id)

                    filter_conditions = [
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=doc_id)
                        )
                    ]

                    doc_chunks = await EmbeddingService.get_embeddings(
                        vector=user_message_embeddings,
                        limit=20, 
                        threshold=0.6, 
                        filter_condition=models.Filter(should=filter_conditions)    
                    )

                    # Sort by priority
                    doc_chunks.sort(key=sort_priority, reverse=True)

                    # Deduplicate by json_key or path
                    seen_paths = set()
                    unique_chunks = []
                    for chunk in doc_chunks:
                        meta = chunk.get("metadata", {})
                        path = meta.get("json_key") or meta.get("path")
                        if not path or path in seen_paths:
                            continue
                        seen_paths.add(path)
                        unique_chunks.append(chunk)

                    doc_chunks = unique_chunks[:15]

                    for chunk in doc_chunks:
                        if 'metadata' not in chunk:
                            continue
                            
                        chunk = extract_source_info(chunk)
                        text = chunk['metadata'].get('text', '')
                        if text:
                            expanded_contexts.append(text)
                            
                            for key, value in chunk['metadata'].items():
                                if isinstance(value, str) and value.startswith("http"):
                                    source = {
                                        "source_name": key,
                                        "source_url": value
                                    }
                                    available_sources.add(json.dumps(source, sort_keys=True))
                    
                    if not doc_chunks:
                        text = metadata.get('text', '')
                        if text:
                            expanded_contexts.append(text)

                        extracted_urls = find_urls_in_metadata(metadata)

                        for url in extracted_urls:
                            source_name = "Detected Source" 
                            try:
                                source_name = url.split('/')[2]
                            except IndexError:
                                pass
                                
                            source = {
                                "source_name": source_name,
                                "source_url": url
                            }
                            available_sources.add(json.dumps(source, sort_keys=True))

                        continue

            expanded_contexts = list(dict.fromkeys(expanded_contexts))
            expanded_contexts = truncate_contexts(expanded_contexts, max_chars=10000)

            if not expanded_contexts:
                expanded_contexts = format_context_texts(query_response)

            available_sources = [json.loads(s) for s in available_sources]
            
            formatted_user_message = self.prompt_config['user_message_template'].format(
                user_message=user_message,
                context="\n".join(expanded_contexts),
                available_sources=json.dumps(available_sources)
            )
            
            try:
                result: ProjectResponse = await ClaudeAIClient.generate(
                    model_class=ProjectResponse,
                    user_message=formatted_user_message,
                    system_message=self.prompt_config['base_system_message'],
                    temperature=self.prompt_config['parameters'].get('temperature', 0.7),
                    max_tokens=self.prompt_config['parameters'].get('max_tokens', 1500),
                    top_p=self.prompt_config['parameters'].get('top_p', 0.95)
                )
            except Exception as e:
                print(f"Failed to validate response: {str(e)}")
                error_message = str(e).lower()
                if "rate limit" in error_message or "429" in error_message:
                    result = ProjectResponse(
                        response=[
                            "• I'm currently experiencing high traffic and couldn't process your request.",
                            "• Please try again after a short while."
                        ],
                        is_greeting=False,
                        exists_in_data=False,
                        exists_elsewhere=False,
                        relevant_projects=[],
                        sources=[]
                    )
                else:
                    result = ProjectResponse(
                        response=["• I couldn't process the response properly"],
                        is_greeting=False,
                        exists_in_data=False,
                        exists_elsewhere=False,
                        relevant_projects=[],
                        sources=[]
                    )

            return {
                "response": result.response,
                "relevant_projects": result.relevant_projects,
                "sources": result.sources
            }

        except Exception as e:
            print(f"Processing error: {str(e)}")
            return {
                "response": self.prompt_config['response_structure']['fallback_response'],
                "relevant_projects": [],
                "sources": [] 
            }