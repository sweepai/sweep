import openai
from openai import OpenAI

client = OpenAI()

INSTRUCTIONS = """\
You are a brilliant and meticulous engineer assigned to write code to complete the user's request. You specialize in Python programming.

# Instructions
Extract code verbatim from the snippets above using EXTRACT sections. These snippets will be used later to refactor the code according to the user request.
* Choose specific and informative names for these functions under new_function_name.
* We must copy the code verbatim, so any extra leading or trailing code will cause us to fail.
* The code must be extracted in contiguous blocks.
* Keep whitespace and comments.
* Extracted functions should be roughly 25 lines unless the function behavior dictates otherwise.

Respond in the following format:

<contextual_request_analysis>
Analyze the user request to identify each section of the code that should be extracted.
These sections should not overlap.
For each new function outline the first and last few lines of code that should be extracted.
</contextual_request_analysis>

<new_function_names>
"new_function_name"
...
</new_function_names>

<extractions>
```
<<<<<<< EXTRACT
first few lines to be extracted from original_code
...
last few lines to be extracted from original_code
>>>>>>>
...
```
</extractions>"""

my_assistant = openai.beta.assistants.create(
    instructions=INSTRUCTIONS,
    name="Python Coding Assistant",
    tools=[{"type": "code_interpreter"}],
    model="gpt-4-1106-preview",
)
thread = client.beta.threads.create()

EXTRACTION_USER_MSG = """\
# Repo & Issue Metadata
Repo: privateGPT - Interact with your documents using the power of GPT, 100% privately, no data leaks
Issue Title: refactor the retrieve_relevant function in private_gpt/server/chunks/chunks_service.py to become more modular
Choose parts of functions that can be extracted to reduce the complexity of the code. If a single function would be too large, refactor it into multiple smaller subfunctions.
Issue Description:
# Code
File path: private_gpt/server/chunks/chunks_service.py


<original_code>
from typing import TYPE_CHECKING

from injector import inject, singleton
from llama_index import ServiceContext, StorageContext, VectorStoreIndex
from llama_index.schema import NodeWithScore
from pydantic import BaseModel, Field

from private_gpt.components.embedding.embedding_component import EmbeddingComponent
from private_gpt.components.llm.llm_component import LLMComponent
from private_gpt.components.node_store.node_store_component import NodeStoreComponent
from private_gpt.components.vector_store.vector_store_component import (
    VectorStoreComponent,
)
from private_gpt.open_ai.extensions.context_filter import ContextFilter
from private_gpt.server.ingest.ingest_service import IngestedDoc

if TYPE_CHECKING:
    from llama_index.schema import RelatedNodeInfo


class Chunk(BaseModel):
    object: str = Field(enum=["context.chunk"])
    score: float = Field(examples=[0.023])
    document: IngestedDoc
    text: str = Field(examples=["Outbound sales increased 20%, driven by new leads."])
    previous_texts: list[str] | None = Field(
        examples=[["SALES REPORT 2023", "Inbound didn't show major changes."]]
    )
    next_texts: list[str] | None = Field(
        examples=[
            [
                "New leads came from Google Ads campaign.",
                "The campaign was run by the Marketing Department",
            ]
        ]
    )


@singleton
class ChunksService:
    @inject
    def __init__(
        self,
        llm_component: LLMComponent,
        vector_store_component: VectorStoreComponent,
        embedding_component: EmbeddingComponent,
        node_store_component: NodeStoreComponent,
    ) -> None:
        self.vector_store_component = vector_store_component
        self.storage_context = StorageContext.from_defaults(
            vector_store=vector_store_component.vector_store,
            docstore=node_store_component.doc_store,
            index_store=node_store_component.index_store,
        )
        self.query_service_context = ServiceContext.from_defaults(
            llm=llm_component.llm, embed_model=embedding_component.embedding_model
        )

    def _get_sibling_nodes_text(
        self, node_with_score: NodeWithScore, related_number: int, forward: bool = True
    ) -> list[str]:
        explored_nodes_texts = []
        current_node = node_with_score.node
        for _ in range(related_number):
            explored_node_info: RelatedNodeInfo | None = (
                current_node.next_node if forward else current_node.prev_node
            )
            if explored_node_info is None:
                break

            explored_node = self.storage_context.docstore.get_node(
                explored_node_info.node_id
            )

            explored_nodes_texts.append(explored_node.get_content())
            current_node = explored_node

        return explored_nodes_texts

    def retrieve_relevant(
        self,
        text: str,
        context_filter: ContextFilter | None = None,
        limit: int = 10,
        prev_next_chunks: int = 0,
    ) -> list[Chunk]:
        index = VectorStoreIndex.from_vector_store(
            self.vector_store_component.vector_store,
            storage_context=self.storage_context,
            service_context=self.query_service_context,
            show_progress=True,
        )
        vector_index_retriever = self.vector_store_component.get_retriever(
            index=index, context_filter=context_filter, similarity_top_k=limit
        )
        nodes = vector_index_retriever.retrieve(text)
        nodes.sort(key=lambda n: n.score or 0.0, reverse=True)

        retrieved_nodes = []
        for node in nodes:
            doc_id = node.node.ref_doc_id if node.node.ref_doc_id is not None else "-"
            retrieved_nodes.append(
                Chunk(
                    object="context.chunk",
                    score=node.score or 0.0,
                    document=IngestedDoc(
                        object="ingest.document",
                        doc_id=doc_id,
                        doc_metadata=node.metadata,
                    ),
                    text=node.get_content(),
                    previous_texts=self._get_sibling_nodes_text(
                        node, prev_next_chunks, False
                    ),
                    next_texts=self._get_sibling_nodes_text(node, prev_next_chunks),
                )
            )

        return retrieved_nodes

</original_code>

# Instructions
Extract code verbatim from the snippets above using EXTRACT sections. These snippets will be used later to refactor the code according to the user request.
* Choose specific and informative names for these functions under new_function_name.
* We must copy the code verbatim, so any extra leading or trailing code will cause us to fail.
* The code must be extracted in contiguous blocks.
* Keep whitespace and comments.
* Extracted functions should be roughly 25 lines unless the function behavior dictates otherwise.

Respond in the following format:

<contextual_request_analysis>
First, determine the function(s) you want to make more modular.
Analyze the user request to identify each section of the code that should be extracted.
These sections should not overlap.
For each new function outline the first and last few lines of code that should be extracted.
</contextual_request_analysis>

<new_function_names>
"new_function_name"
...
</new_function_names>

<extractions>
```
<<<<<<< EXTRACT
first few lines to be extracted from original_code
...
last few lines to be extracted from original_code
>>>>>>>
...
```
</extractions>"""

message = client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content=EXTRACTION_USER_MSG,
)
run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=my_assistant.id)
run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
messages = client.beta.threads.messages.list(thread_id=thread.id)
latest_message = messages.data[0].content[0].text.value
import pdb

pdb.set_trace()
run
