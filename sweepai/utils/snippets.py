import modal
from loguru import logger

from sweepai.core.entities import Snippet
from sweepai.utils.config.server import UTILS_MODAL_INST_NAME

chunker = modal.Function.lookup(UTILS_MODAL_INST_NAME, "Chunking.chunk")


def format_snippets(snippets: list[Snippet]):
    snippets: list[Snippet] = snippets[::-1]

    num_full_files = 3
    num_extended_snippets = 5

    most_relevant_snippets = snippets[-num_full_files:]
    snippets = snippets[:-num_full_files]
    logger.info("Expanding snippets...")
    for snippet in most_relevant_snippets:
        current_snippet = snippet
        _chunks, metadatas, _ids = chunker.call(
            current_snippet.content,
            current_snippet.file_path
        )
        segmented_snippets = [
            Snippet(
                content=current_snippet.content,
                start=metadata["start"],
                end=metadata["end"],
                file_path=metadata["file_path"],
            ) for metadata in metadatas
        ]
        index = 0
        while index < len(segmented_snippets) and segmented_snippets[index].start <= current_snippet.start:
            index += 1
        index -= 1
        for i in range(index + 1, min(index + num_extended_snippets + 1, len(segmented_snippets))):
            current_snippet += segmented_snippets[i]
        for i in range(index - 1, max(index - num_extended_snippets - 1, 0), -1):
            current_snippet = segmented_snippets[i] + current_snippet
        snippets.append(current_snippet)
    return snippets
