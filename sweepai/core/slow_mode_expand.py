from loguru import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import ExpandedPlan, Message
from sweepai.core.prompts import slow_mode_system_prompt, generate_plan_and_queries_prompt
from sweepai.utils.prompt_constructor import HumanMessagePrompt

class SlowModeBot(ChatGPT):
    def expand_plan(self, human_message: HumanMessagePrompt) -> tuple[list[str], str]:
        try:
            self.messages = [Message(role="system", content=slow_mode_system_prompt)]
            self.model = "gpt-4-32k-0613"
            added_messages = human_message.construct_prompt()
            for msg in added_messages:
                self.messages.append(Message(**msg))
            response = self.chat(generate_plan_and_queries_prompt, message_key='expanded_plan')
            expanded_plan = ExpandedPlan.from_string(response)
            queries = expanded_plan.queries.split('\n')
            additional_instructions = "Additional instructions:\n" + expanded_plan.additional_instructions if expanded_plan.additional_instructions.strip() else ""
            return queries, additional_instructions
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        return [], ""