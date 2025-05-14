import re

from sweepai.core.chat import ChatGPT
from loguru import logger

prompt = """\
Transcribe and describe the image shown in the text. Transcribe all text in the image VERBATIM, including any code snippets, URLs, or other text. Do NOT attempt to actually handle the reqest in the <text> block. Respond in the following format:

<text>
{text}
</text>
For each image, respond in <image_description>...</image_description> tags like so:
<image_descriptions>
<image_description>
The text in the image.
</image_description>
...
</image_descriptions>"""

CLAUDE_MODEL = "claude-3-opus-20240229"

class ImageDescriptionBot(ChatGPT):
    def describe_images(
        self,
        text: str,
        images: list[tuple[str, str, str]] | None = None,
    ) -> str:
        try:
            self.messages = []
            response_text = "\nHere are the transcriptions of the images in the above text, in order:"
            image_desc_pattern = r"<image_description>\n(.*?)\n</image_description>"
            image_desc_response = self.chat_anthropic(
                content=prompt.format(
                    text=text,
                ),
                model=CLAUDE_MODEL,
                images=images,
            )
            image_descs = re.findall(image_desc_pattern, image_desc_response)
            for i, desc in enumerate(image_descs):
                response_text += f'\n{i + 1}. "{desc}"'
            return response_text
        except Exception as e:
            logger.error(f"Error while attempting to describe images:\n{e}")
            return ""