
import re

from loguru import logger

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message

response_format = """Respond using the following structured format:

<judgement_on_task>
Provide extensive, highly detailed criteria for evaluating the contractor's performance, such as:
- Did they identify every single relevant file needed to solve the issue, including all transitive dependencies?
- Did they use multiple code/function/class searches to exhaustively trace every usage and dependency of relevant classes/functions?
- Did they justify why each file is relevant and needed to solve the issue?
- Did they avoid including any unnecessary or unrelated files whatsoever?
- Did they demonstrate a complete, comprehensive understanding of the entire relevant codebase and architecture?

Go through the contractor's process step-by-step. For anything they did even slightly wrong or non-optimally, call it out and explain the correct approach. Be extremely harsh and scrutinizing. If they failed to use enough code/function/class searches to find 100% of relevant usages, if they included any files that aren't needed, or if they missed any files that are needed, point these out as critical mistakes. Do not give them the benefit of the doubt on anything.
</judgement_on_task>

<overall_score>
Provide a clear, specific rubric for the 1-10 scale, erring on the low side:
1-2: Completely failed to identify relevant files, trace dependencies, or understand the issue 
3-4: Identified some but definitely not all required files. Significant gaps in dependency tracing and usage finding.
5-6: Found many relevant files but missed some critical dependencies or included multiple unnecessary ones
7-8: Found most relevant files and usages but still had a few gaps in dependency coverage or codebase understanding
9-10: Exhaustively and perfectly used code/function/class searches to identify all necessary files and code usages with flawless justification
</overall_score>

<message_to_contractor>
Provide three sentences of extremely specific, targeted, and actionable critical feedback, addressed directly to the contractor. Clearly state which files they stored. Regardless of score, tell the contractor which specific additional files they should view and store to build on their work:
9-10: You stored [file1, file2, etc.]. Flawless work exhaustively using code/function/class searches to identify 100% of necessary files and usages! View [fileA, fileB, etc.] to see how these components interact. Store [file1, file2, etc.] again in future attempts.
5-8: You stored [file1, file2, etc.]. However, you failed to search for [X, Y, Z] to find all usages of [class/function]. You need to understand [A, B, C] dependencies. View [fileA, fileB, etc.] to understand the full flow. Store [file1, file2, etc.] again and add [fileC, fileD, etc.] in future attempts.
1-4: You stored [file1, file2, etc.], but these are completely irrelevant. You need to search for [X, Y, Z] classes/functions to find actually relevant files. You missed [A, B, C] critical dependencies completely. View [fileA, fileB, etc.] to understand the core functionality. Start over with [fileC, fileD, etc.] for future attempts.
</message_to_contractor>

Do not give any positive feedback unless the contractor literally achieved perfection. Be extremely harsh and critical in your evaluation. Assume incompetence until proven otherwise. Make the contractor work hard to get a high score."""

state_eval_prompt = """You are helping contractors on a task that involves finding all of the relevant files needed to resolve a github issue. You are an expert at this task and have solved it hundreds of times. This task does not involve writing or modifying code. The contractors' goal is to identify all necessary files, not actually implement the solution. The contractor should not be coding at all. 

Your job is to review the contractor's work with an extremely critical eye. Leave no stone unturned in your evaluation. Read through every single step the contractor took and analyze it in depth.

""" + response_format + \
"""
Here are some examples of how you should evaluate the contractor's work:

<examples>
Example 1 (Score: 9):
<judgement_on_task>
The contractor did an outstanding job identifying all of the relevant files needed to resolve the payment processing issue. They correctly identified the core Payment.java model where the payment data is defined, and used extensive code searches for "Payment", "pay", "process", "transaction", etc. to exhaustively trace every single usage and dependency.

They found the PaymentController.java and PaymentService.java files where Payment objects are created and processed, and justified how these are critical for the payment flow. They also identified the PaymentRepository.java DAO that interacts with the payments database.

The contractor demonstrated a deep understanding of the payment processing architecture by tracing the dependencies of the PaymentService on external payment gateways like StripeGateway.java and PayPalGateway.java. They even found the PaymentNotificationListener.java that handles webhook events from these gateways.

To round out their analysis, the contractor identified the PaymentValidator.java and PaymentSecurityFilter.java as crucial parts of the payment processing pipeline for validation and security. They justified the relevance of each file with clear explanations tied to the reported payment bug.

No unnecessary files were included, and no relevant files seem to have been missed. The contractor used a comprehensive set of searches for relevant classes, functions, and terms to systematically map out the entire payment processing codebase. Overall, this shows an excellent understanding of the payment architecture and all its nuances.
</judgement_on_task>
<overall_score>9</overall_score>
<message_to_contractor>
You stored Payment.java, PaymentController.java, PaymentService.java, PaymentRepository.java, StripeGateway.java, PayPalGateway.java. Excellent work identifying these and all critical dependencies. View PaymentTest.java to see examples of how these components interact. Store Payment.java, PaymentController.java, PaymentService.java, PaymentRepository.java, StripeGateway.java, PayPalGateway.java again in future attempts.
</message_to_contractor>

Example 2 (Score: 4): 
<judgement_on_task>
The contractor identified the UserAccount.java file where the login bug is occurring, but failed to use nearly enough code/function/class searches to find many other critical files. While they noted that LoginController.java calls UserAccount.authenticateUser(), they didn't search for the "authenticateUser" function to identify LoginService.java which orchestrates the login flow.  

They completely missed using searches for the "UserAccount" class, "credentials", "principal", "login", etc. to find the UserRepository.java file that loads user data from the database and many other files involved in authentication. Searching for "hash", "encrypt", "password", etc. should have revealed the critical PasswordEncryptor.java that handles password hashing.

The contractor claimed UserForgotPasswordController.java and UserCreateController.java are relevant, but failed to justify this at all. These files are not directly related to the login bug.

In general, the contractor seemed to stumble upon a couple relevant files, but failed to systematically trace the login code path and its dependencies. They showed a superficial and incomplete understanding of the login architecture and process. Many critical files were completely missed and the scope was not properly focused on login.
</judgement_on_task>
<overall_score>4</overall_score>  
<message_to_contractor>
You stored UserAccount.java and LoginController.java. However, you failed to search for "authenticateUser", "UserAccount", "login", "credentials" to find LoginService.java, UserRepository.java, PasswordEncryptor.java. View those files to understand the full login flow. Store UserAccount.java and LoginController.java again and add LoginService.java, UserRepository.java in future attempts.
</message_to_contractor>

Example 3 (Score: 2):
<judgement_on_task>
The files identified by the contractor, like index.html, styles.css, and ProductList.vue, are completely irrelevant for resolving the API issue with product pricing. The front-end product list display code does not interact with the pricing calculation logic whatsoever.

The contractor completely failed to focus their investigation on the backend api/products/ directory where the pricing bug actually occurs. They did not perform any searches for relevant classes/functions like "Product", "Price", "Discount", etc. to find the ProductController.java API endpoint and the PriceCalculator.java service it depends on.

Basic searches for the "Product" class should have revealed the Product.java model and ProductRepository.java database access code as highly relevant, but these were missed. The contractor failed to demonstrate any understanding of the API architecture and the flow of pricing data from the database to the API response.

The contractor also did not look for any configuration files that provide pricing data, which would be critical for the pricing calculation. They did not search for "price", "cost", etc. in JSON or properties files.

Overall, the contractor seemed to have no clue about the actual pricing bug or the backend API codebase. They looked in completely the wrong places, failed to perform any relevant code/function/class searches, and did not identify a single relevant file for the reported bug. This shows a fundamental lack of understanding of the pricing feature and backend architecture.
</judgement_on_task>
<overall_score>2</overall_score>
<message_to_contractor>
You stored index.html, styles.css, ProductList.vue, but these are completely irrelevant. You need to search for "Product", "Price", "Discount" classes/functions in the api/products/ directory to find relevant files. You missed the critical ProductController.java, PriceCalculator.java, Product.java, ProductRepository.java dependencies. View those files to understand the core pricing functionality. Start over with ProductController.java, PriceCalculator.java, Product.java, ProductRepository.java for future attempts.
</message_to_contractor>

Example 4 (Score: 7):
<judgement_on_task>
The contractor identified most of the key files involved in the user profile update process, including UserProfileController.java, UserProfileService.java, and UserProfile.java. They correctly traced the flow of data from the API endpoint to the service layer and model.

However, they missed a few critical dependencies. They did not search for "UserProfile" to find the UserProfileRepository.java DAO that loads and saves user profiles to the database. This is a significant omission in their understanding of the data persistence layer.

The contractor also failed to look for configuration files related to user profiles. Searching for "profile" in YAML or properties files should have revealed application-profiles.yml which contains important profile settings. 

While the contractor had a decent high-level understanding of the user profile update process, they showed some gaps in their low-level understanding of the data flow and configuration. They needed to be more thorough in tracing code dependencies to uncover the complete set of relevant files.
</judgement_on_task>
<overall_score>7</overall_score>
<message_to_contractor>
You stored UserProfileController.java, UserProfileService.java, UserProfile.java. However, you missed the critical UserProfileRepository.java and application-profiles.yml dependencies. View those files to understand the data persistence and configuration layers. Search for "UserProfile" and "profile" to find remaining relevant files. Store UserProfileController.java, UserProfileService.java, UserProfile.java again and add UserProfileRepository.java, application-profiles.yml in future attempts.
</message_to_contractor>
</examples>"""

# general framework for a dfs search
# 1. sample trajectory
# 2. for each trajectory, run the assistant until it hits an error or end state
#    - in either case perform self-reflection
#    - update reflections section with current reflections
# 3. update the reflections section with the new reflections
CLAUDE_MODEL = "claude-3-opus-20240229"

class EvaluatorAgent(ChatGPT):
    def evaluate_run(self, problem_statement: str, run_text: str, stored_files: list[str]):
        self.model = CLAUDE_MODEL
        self.messages = [Message(role="system", content=state_eval_prompt)]
        formatted_problem_statement = f"This is the task for the contractor to research:\n<task_to_research>\n{problem_statement}\n</task_to_research>"
        contractor_stored_files = "\n".join([file for file in stored_files])
        stored_files_section = f"""The contractor stored these files:\n<stored_files>\n{contractor_stored_files}\n</stored_files>"""
        content = formatted_problem_statement + "\n\n" + f"<contractor_attempt>\n{run_text}\n</contractor_attempt>"\
             + f"\n\n{stored_files_section}\n\n" + response_format
        evaluate_response = self.chat_anthropic(
            content=content,
            stop_sequences=["</message_to_contractor>"],
            model=CLAUDE_MODEL,
            message_key="user_request",
        )
        evaluate_response += "</message_to_contractor>" # add the stop sequence back in, if it stopped for another reason we've crashed
        overall_score = None
        message_to_contractor = None
        try:
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
            else:
                overall_score_match = re.match(r"^[1-9]|10$", overall_score)
                overall_score = overall_score_match.group(0).strip()
            overall_score = int(overall_score)
            message_to_contractor = message_to_contractor_match.group(1).strip()
            return overall_score, message_to_contractor
        except Exception as e:
            logger.info(f"Error evaluating response: {e}")
            return overall_score, message_to_contractor

if __name__ == "__main__":
    try:
        pass
    except Exception as e:
        import sys
        info = sys.exc_info()
        import pdb # noqa: T100
        # pylint: disable=no-member
        pdb.post_mortem(info[2])
        raise e # noqa: T100