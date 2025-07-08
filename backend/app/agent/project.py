import json
from pathlib import Path
from typing import Dict, Any
from qdrant_client.http import models 

from app.services.embeddings_service import EmbeddingService
from app.external_services.claude_ai_client import ClaudeAIClient
from app.models.api.agent_router import ProjectResponse
from app.utils.projects_utils import format_context_texts, extract_source_info

class ProjectAgent:
    """Handles project validation and queries using embeddings and vector DB matching"""
    def __init__(self):
        prompt_path = Path(__file__).parent / "prompt" / "project_prompt.json"
        with open(prompt_path) as f:
            self.prompt_config = json.load(f)['project_agent_prompt']
    
    async def process(self, user_message: str) -> Dict[str, Any]:
        try:
            user_message_embeddings = EmbeddingService.create_embeddings(user_message)
            print("Query vector:", user_message_embeddings[:5]) 
    
            query_response = await EmbeddingService.get_embeddings(
                vector=user_message_embeddings,
                limit=self.prompt_config['rag_settings'].get('search_depth', 5),
                # threshold=self.prompt_config['rag_settings'].get('relevance_threshold', 0.6)
                threshold=None
            )
            print("===== Raw Query Response Metadata Preview =====")
            for item in query_response:
                print(json.dumps(item.get('metadata', {}), indent=2))

            expanded_contexts = []
            available_sources = set()

            if query_response and isinstance(query_response[0], dict):
                seen_docs = set()

                for item in query_response:
                    if 'metadata' not in item:
                        continue
                    
                    doc_id = item['metadata'].get('document_id')
                    if not doc_id or doc_id in seen_docs:
                        continue
                    
                    seen_docs.add(doc_id)

                    filter_conditions = [
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=doc_id)
                        )
                    ]

                    parent_id = item['metadata'].get('parent_id')
                    if parent_id:
                        filter_conditions.append(
                            models.FieldCondition(
                                key="parent_id",
                                match=models.MatchValue(value=parent_id)
                            )
                        )

                    doc_chunks = await EmbeddingService.get_embeddings(
                        vector=user_message_embeddings,
                        limit=20, 
                        threshold=0.6, 
                        filter_condition=models.Filter(must=filter_conditions)    
                    )
                    print(f"Doc Chuks: {doc_chunks}")
                    for idx, chunk in enumerate(doc_chunks):
                        print(f"[Chunk #{idx}] Text Preview: {chunk['metadata'].get('text', '')[:100]}...")  # Log first 100 chars

                    print(f"[Expanded Context Count]: {len(expanded_contexts)}")
                    print(f"[Query matched documents]: {seen_docs}")

                    doc_chunks.sort(key=lambda x: x['metadata'].get('record_type') == 'json_field_chunk', reverse=True)
                    for chunk in doc_chunks:
                        if 'metadata' not in chunk:
                            continue
                            
                        chunk = extract_source_info(chunk)
                        text = chunk['metadata'].get('text', '')
                        if text:
                            expanded_contexts.append(text)
                            
                        if all(k in chunk['metadata'] for k in ['source_name', 'source_url']):
                            source = {
                                'source_name': chunk['metadata']['source_name'],
                                'source_url': chunk['metadata']['source_url']
                            }
                            available_sources.add(json.dumps(source, sort_keys=True))

            expanded_contexts = list(dict.fromkeys(expanded_contexts))

            if not expanded_contexts:
                expanded_contexts = format_context_texts(query_response)
            print(f"Expanded Context: {expanded_contexts}")

            available_sources = [json.loads(s) for s in available_sources]
            print(f"Available Sources: {available_sources}")
            
            formatted_user_message = self.prompt_config['user_message_template'].format(
                user_message=user_message,
                context="\n".join(expanded_contexts),
                available_sources=json.dumps(available_sources)
            )
            print(f"Formatted User Message: {formatted_user_message}")

            # TODO - Returning the mock response for testing 
            print("Returning mocked response for testing context retrieval...")
            return {
                "response": ["[MOCKED] Context retrieval completed."],
                "relevant_projects": [],
                "sources": available_sources,
                "retrieved_chunks": expanded_contexts 
            }
            
            # try:
            #     result: ProjectResponse = await ClaudeAIClient.generate(
            #         model_class=ProjectResponse,
            #         user_message=formatted_user_message,
            #         system_message=self.prompt_config['base_system_message'],
            #         temperature=self.prompt_config['parameters'].get('temperature', 0.7),
            #         max_tokens=self.prompt_config['parameters'].get('max_tokens', 1500),
            #         top_p=self.prompt_config['parameters'].get('top_p', 0.95)
            #     )
            #     print(f"Claude Response: {result}")
            # except Exception as e:
            #     print(f"Failed to validate response: {str(e)}")
            #     result = ProjectResponse(
            #         response=["• I couldn't process the response properly"],
            #         is_greeting=False,
            #         exists_in_data=False,
            #         exists_elsewhere=False,
            #         relevant_projects=[],
            #         sources=[]
            #     )    

            # return {
            #     "response": result.response,
            #     "relevant_projects": result.relevant_projects,
            #     "sources": result.sources
            # }

        except Exception as e:
            print(f"Processing error: {str(e)}")
            return {
                "response": self.prompt_config['response_structure']['fallback_response'],
                "relevant_projects": [],
                "sources": [] 
            }