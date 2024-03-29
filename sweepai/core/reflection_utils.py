
import re

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message

response_format = """Respond using the following structured format:

<judgement_on_task>
Provide clear criteria for evaluating the contractor's performance:
- Did they use code searches to find all instances where a class, type, or function is used, not just where it is defined?
- Did they carefully trace dependencies and imports to find related files?
- Did they avoid including unnecessary or unrelated files?
- If they modified a class, did they identify all usages of that class? Example: if they modified the Booking class, did they search for "Booking" to find all usages in the codebase?
- Did they identify all relevant files needed to solve the issue? 

Examine each file read and step taken by the contractor. Call out anything done incorrectly or any files/usages that were missed, being specific. Provide a detailed explanation of the correct approach.
</judgement_on_task>

<overall_score>
Provide a clear rubric for the 1-10 scale:
1-3: Completely failed to identify relevant files or understand the issue. Focused on irrelevant code. 
4-5: Identified some but not all required files. Only found definitions, not all usages. Missed key dependencies.
6-7: Found most but not all relevant files and usages. Included some unnecessary files. Understanding of issue is incomplete.
8-10: Successfully identified all and only the files and code usages needed to resolve the issue. Demonstrated deep understanding.
</overall_score>

<message_to_contractor>
Provide direct, specific and actionable feedback to the contractor in 1-2 sentences:
9-10: Excellent work identifying all necessary files and code usages! Your understanding of the codebase and issue is top-notch.
6-8: Good effort, but make sure to use code searches to find all usages of [specific class/function]. Don't forget to trace [specific dependency/import] as well.
1-5: The files you identified, such as [irrelevant files], are not actually relevant to this [specific issue]. Focus your search on [specific directory/file] instead. Use code searches to find all instances where [specific class/function] is used.
</message_to_contractor>"""

state_eval_prompt = """You are helping contractors on a task that involves finding all of the relevant files needed to resolve an issue. This task does not involve writing or modifying code. The contractors' goal is to identify all necessary files, not actually implement the solution. The contractor should not be coding. Be extremely critical and thorough in your evaluation. The contractor will often think and say they've succeeded, but you must evaluate them based on the criteria provided.

""" + response_format + \
"""

Example 1 (Score: 9):
<judgement_on_task>
The contractor did an excellent job identifying all the relevant files needed to resolve the booking confirmation email issue. They correctly identified the Booking.java model where the core booking data is defined. 

They also used code searches for "Booking" to find the BookingController.java and BookingService.java files where Booking objects are created and processed. This shows they traced the usage and dependencies thoroughly.

Furthermore, they searched for "sendEmail" to identify the EmailService.java file responsible for actually sending the confirmation emails, and the booking-confirmation.html template that provides the email content. They even checked the application.properties config file to verify the email server settings.

No unnecessary files were included, and the contractor demonstrated a thorough understanding of the booking flow and email dependencies by tracing the code paths completely.
</judgement_on_task>
<overall_score>9</overall_score>
<message_to_contractor>
Great work using code searches to identify all the files involved in the booking confirmation email flow, tracing the code from the core Booking model to the email service and HTML template!
</message_to_contractor>

Example 2 (Score: 5): 
<judgement_on_task>
The contractor identified the UserAccount.java file where the login bug is occurring, but failed to use code searches to find several other critical files. While they noted that the LoginController.java file calls the authenticateUser() method in UserAccount, they didn't search for "authenticateUser" to identify the LoginService.java file which is actually responsible for orchestrating the whole login flow.  

They also missed using a search for "UserAccount" to find the UserRepository.java file which loads the user data from the database and is used by UserAccount.authenticateUser(). Additionally, searching for "hash" or "encrypt" should have revealed the PasswordEncryptor.java that handles password salt and hashing during authentication.

So while the contractor identified the core UserAccount class, they failed to use code searches to trace its dependencies and usages, missing several other key files that would likely need to be investigated and possibly modified to fully resolve the login issue.
</judgement_on_task>
<overall_score>5</overall_score>  
<message_to_contractor>
Use code searches for "UserAccount", "authenticateUser", "hash", etc to find all relevant files involved in the login process, not just the UserAccount definition, to improve.
</message_to_contractor>

Example 3 (Score: 2):
<judgement_on_task>
The files identified by the contractor, like index.html, styles.css, and ProductList.vue, are not relevant to resolving the API issue with product pricing. The front-end product list display code does not interact with the actual price calculation logic.

The contractor should have focused their investigation on the backend api/products/ directory, especially searching for keywords like "price", "cost" or "discount" to find the ProductController.java API endpoint and the PriceCalculator.java service it depends on. Searching for "Product" should have also revealed the Product.java model and ProductRepository.java database access code as relevant.  

Additionally, the contractor failed to look for any configuration files that provide pricing data, which could have been found by searching for "price" in JSON or properties files. By focusing solely on irrelevant front-end code and not using code searches to trace the actual pricing logic, the contractor demonstrated a complete lack of understanding of the actual bug and API architecture.
</judgement_on_task>
<overall_score>2</overall_score>  
<message_to_contractor>  
The front-end ProductList.vue file is not relevant for an API pricing bug. Code search for "price", "cost", "discount" etc to find the relevant backend code in the api/products/ directory instead.
</message_to_contractor>"""

# general framework for a dfs search
# 1. sample trajectory
# 2. for each trajectory, run the assistant until it hits an error or end state
#    - in either case perform self-reflection
#    - update reflections section with current reflections
# 3. update the reflections section with the new reflections
CLAUDE_MODEL = "claude-3-sonnet-20240229"

class EvaluatorAgent(ChatGPT):
    def evaluate_run(self, problem_statement: str, run_text: str):
        self.model = CLAUDE_MODEL
        self.messages = [Message(role="system", content=state_eval_prompt)]
        formatted_problem_statement = f"This is the task for the contractor to research:\n<task_to_research>\n{problem_statement}\n</task_to_research>"
        evaluate_response = self.chat_anthropic(
            content=formatted_problem_statement + "\n\n" + f"<contractor_attempt>\n{run_text}\n<\contractor_attempt>" + "\n\n" + response_format,
            stop_sequences=["</message_to_contractor>"],
            model=CLAUDE_MODEL,
            message_key="user_request",
        )
        evaluate_response += "</message_to_contractor>" # add the stop sequence back in, if it stopped for another reason we've crashed
        overall_score = None
        message_to_contractor = None
        overall_score_pattern = r"<overall_score>(.*?)</overall_score>"
        message_to_contractor_pattern = r"<message_to_contractor>(.*?)</message_to_contractor>"

        overall_score_match = re.search(overall_score_pattern, evaluate_response, re.DOTALL)
        message_to_contractor_match = re.search(message_to_contractor_pattern, evaluate_response, re.DOTALL)

        if overall_score_match is None or message_to_contractor_match is None:
            return overall_score, message_to_contractor

        overall_score = overall_score_match.group(1).strip()
        # check if 1 through 10 are a match
        if not re.match(r"^[1-9]|10$", overall_score):
            return None, None
        
        overall_score = int(overall_score)

        message_to_contractor = message_to_contractor_match.group(1).strip()
        return overall_score, message_to_contractor

reflections_prompt = """Here are some tips from previous attempts for you:
{reflections_string}"""

if __name__ == "__main__":
    try:
        pass
    except Exception as e:
        import sys
        info = sys.exc_info()
        import pdb
        pdb.post_mortem(info[2])
        raise e