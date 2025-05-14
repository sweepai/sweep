import re

from loguru import logger

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.utils.diff import generate_diff

response_format = """Respond using the following structured format:

<judgement_on_task>
Provide extensive, highly detailed criteria for evaluating the contractor's performance, such as:
- Did they identify every single relevant file needed to solve the issue, including all transitive dependencies?
- Did they use multiple code/function/class searches to exhaustively trace every usage and dependency of relevant classes/functions?
- Did they justify why each file is relevant and needed to solve the issue?
- Did they demonstrate a complete, comprehensive understanding of the entire relevant codebase and architecture?

Go through the contractor's process step-by-step. For anything they did even slightly wrong or non-optimally, call it out and explain the correct approach. Be extremely harsh and scrutinizing. If they failed to use enough code/function/class searches to find 100% of relevant usages or if they missed any files that are needed, point these out as critical mistakes. Do not give them the benefit of the doubt on anything.
</judgement_on_task>

<overall_score>
Evaluate the contractor from 1-10, erring on the low side:
1 - Completely failed to identify relevant files, trace dependencies, or understand the issue
2 - Identified a couple files from the issue description but missed many critical dependencies 
3 - Found some relevant files but had major gaps in dependency tracing and codebase understanding
4 - Identified several key files but still missed important usages and lacked justification
5 - Found many relevant files but missed a few critical dependencies
6 - Identified most key files and dependencies but still had some gaps in usage tracing
7 - Found nearly all relevant files but missed a couple edge case usages or minor dependencies
8 - Exhaustively traced nearly all dependencies with robust justification, only minor omissions
9 - Perfectly identified every single relevant file and usage with airtight justification 
10 - Flawless, absolutely exhaustive dependency tracing and codebase understanding
</overall_score>

<message_to_contractor>
Provide a single sentence of extremely specific, targeted, and actionable critical feedback, addressed directly to the contractor.
9-10: Flawless work exhaustively using code/function/class searches to identify 100% of necessary files and usages!
5-8: You failed to search for [X, Y, Z] to find all usages of [class/function]. You need to understand [A, B, C] dependencies.
1-4: You need to search for [X, Y, Z] classes/functions to find actually relevant files. You missed [A, B, C] critical dependencies completely.
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

No relevant files seem to have been missed. The contractor used a comprehensive set of searches for relevant classes, functions, and terms to systematically map out the entire payment processing codebase. Overall, this shows an excellent understanding of the payment architecture and all its nuances.
</judgement_on_task>
<overall_score>9</overall_score>
<message_to_contractor>
Excellent work identifying Payment.java, PaymentController.java, PaymentService.java, and all critical dependencies.
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
Failed to search for "authenticateUser", "UserAccount", "login", "credentials". Missed LoginService.java, UserRepository.java, PasswordEncryptor.java.
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
index.html, styles.css, ProductList.vue are irrelevant. Search api/products/ for "Product", "Price", "Discount" classes/functions.
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
Missed UserProfileRepository.java and application-profiles.yml dependencies. Search for "UserProfile" and "profile" to find remaining relevant files.
</message_to_contractor>
</examples>"""

modify_eval_response_format = """Please provide your critical evaluation of this submission using the following structured format:

<judgement_on_task>
Your judgement here explaining in detail how you are evaluating the contractor's work against the original requirements. Call out specific issues, gaps, or places where the contractor went wrong. Provide clear justification and examples to support your assessment.
</judgement_on_task>

<overall_score>
Evaluate the contractor from 1-10, erring on the low side:
1 - No attempt made to complete the task
2 - Minimal attempt with little to no functional code changes
3 - Significant gaps in completion of the task, code largely non-functional
4 - Partial completion of the task with major issues and errors
5 - Task partially satisfied but with significant issues remaining
6 - Most requirements addressed but some notable gaps or issues
7 - Task mostly satisfied with a few minor issues or improvements needed
8 - Task fully satisfied with working code, minor improvements possible
9 - Task fully satisfied with high-quality, efficient, and maintainable code
10 - Superhuman completion of the task, exceptional code quality and design
</overall_score>

<message_to_contractor>
Provide 3-5 specific, actionable pieces of feedback here for the contractor to focus on in their next attempt. For example:

1. Import the missing XYZ library at the top of file A to avoid compilation errors.
2. The FooBar() method called on line 127 of file B is not defined anywhere. Implement this method or remove the call.
3. The current changes do not handle the edge case of X. Add logic to check for this case and respond appropriately.
4. Consider refactoring the code in function ABC to be more readable and maintainable. It is currently very complex and difficult to follow.

Focus on the most critical issues that are blocking functional completion of the task first, then cover code quality and best practices.
</message_to_contractor>"""

modify_eval_examples = """Example 1:

<judgement_on_task>
The contractor has done an exceptional job completing the task of optimizing the database queries and improving the overall performance of the application. They accurately identified the bottlenecks in the existing code and made targeted, efficient changes to address them. The updated queries now utilize appropriate indexes, avoid unnecessary joins, and minimize data transfer. The contractor also added helpful comments explaining their optimization strategies, making the code more maintainable. All the original requirements have been fully satisfied, and the code changes demonstrate a deep understanding of database performance best practices.
</judgement_on_task>

<overall_score>9</overall_score>

<message_to_contractor>
Great work on this optimization task! Your code changes have significantly improved the efficiency of the database queries. A few minor suggestions for further enhancement:

1. Consider using a parameterized query on line 95 of `queries.py` to avoid potential SQL injection vulnerabilities.
2. The `get_user_data` function in `utils.py` could benefit from some additional error handling to gracefully deal with potential edge cases, such as a user ID not being found.

Overall, this is a high-quality submission. Keep up the excellent work!
</message_to_contractor>

Example 2:

<judgement_on_task>
The contractor has made an attempt to implement the new feature for generating PDF reports, but there are several gaps and issues in their code changes. While they have correctly added a new endpoint for triggering the report generation, the actual PDF creation logic is incomplete. The code is currently missing the necessary imports for the PDF library, and there are several undefined variables and functions being used. Additionally, the error handling is insufficient, which could lead to uncaught exceptions. The contractor has also not included any unit tests to verify the functionality of the new feature. More work is needed to fully satisfy the requirements and ensure a reliable, maintainable solution.
</judgement_on_task>

<overall_score>5</overall_score>

<message_to_contractor>
Thank you for your efforts on implementing the PDF report feature. However, there are several areas that need improvement:

1. Add the necessary imports for the PDF library at the top of `report_generator.py`. Currently, the `import pdf_lib` statement is missing.
2. Implement the missing `generate_pdf` function that is currently being called on line 42 of `report_generator.py`. This function should contain the core logic for creating the PDF report.
3. Fix the undefined variables `report_data` and `user_id` in the `generate_report` endpoint. Ensure that these variables are properly initialized before being used.
4. Add proper error handling to the `generate_report` endpoint to catch and handle any exceptions that may occur during the PDF generation process.
5. Write unit tests for the new feature to verify its functionality and catch any potential bugs.

Please address these issues and resubmit your code changes for further review.
</message_to_contractor>

Example 3:

<judgement_on_task>
The contractor's submission for the task of implementing a new user authentication system is severely lacking and does not meet the requirements. The code changes are minimal and do not include any of the core functionality needed for user registration, login, or password hashing. The contractor has merely added a few empty functions and commented out some existing code, without any actual implementation. There are no changes made to the database schema to support storing user credentials securely. The submission also introduces several syntax errors and undefined variables, indicating a lack of basic coding proficiency. Overall, this submission falls far short of the expected solution and does not demonstrate any meaningful progress towards completing the task.
</judgement_on_task>

<overall_score>2</overall_score>

<message_to_contractor>
I regret to inform you that your submission for the user authentication task is unacceptable and requires significant improvement. The following critical issues must be addressed:

1. Implement the core functionality for user registration, including validating input data, securely storing user credentials in the database, and handling duplicate username/email scenarios.
2. Add the necessary code for user login, including verifying the provided credentials against the stored data and generating a secure authentication token upon successful login.
3. Integrate a secure password hashing algorithm, such as bcrypt or scrypt, to store and compare passwords instead of storing them in plain text.
4. Update the database schema to include the required tables and fields for storing user information and authentication data.
5. Fix all syntax errors and undefined variables in your code. Ensure that your code is free of basic compilation errors before submitting.

I recommend reviewing the task requirements carefully, studying best practices for user authentication, and taking the time to implement a complete and secure solution. If you need further guidance or clarification, please don't hesitate to ask.
</message_to_contractor>"""

modify_eval_prompt = """You are an evaluator agent tasked with grading and providing critical feedback on code changes submitted by an outside contractor in response to a given coding task. You will be provided with the original task description as well as a series of file changes in unified diff format.

Your job is to carefully review the code changes and provide feedback focused on the following:

1. Identify any missing import statements that would prevent the code from compiling. Call out the specific imports that are needed.

2. Look for any variables or methods that are referenced but not defined in the provided code changes. These may indicate the contractor hallucinated or made invalid assumptions. 

3. Analyze whether the code changes, as submitted, fully satisfy the requirements of the original coding task. Identify any gaps or ways in which the solution falls short.

Remember, your goal is to be a harsh critic and really scrutinize the work to ensure only high-quality, complete code changes are accepted. Do not praise mediocre work.

""" + modify_eval_response_format + modify_eval_examples

modify_eval_patch_prompt = """\
You are a meticulous code reviewer providing critical and specific feedback on a contractor's code changes to help resolve a GitHub issue.
Inputs:
- Task description
- Code patch (diff) 
- Completed changes
- Current plan
- Current file
Steps:
1. Review CURRENT TASK for requirements.
2. Analyze code patch:
   - Purpose and impact of each change
   - Check for LLM failures: 
     - Logic errors
     - Unhandled edge cases
     - Missing imports
     - Incomplete changes
     - Undefined variables/functions
     - Usage of nullable attributes
     - Non-functional code
   - Alignment with plan and requirements
3. Perform critical contextual analysis:
   - Break down changes 
   - Explain reasoning
   - Identify logic issues, edge cases, plan deviations
   - Consider all scenarios and pitfalls
   - Consider backwards compatibility and future-proofing
   - Suggest fixes for problems
4. Be extremely critical. Do not overlook ANY issues.
Format:
<task_summary>
Provide a brief summary of the task requirements, the contractor's plan, and the current file changes.
</task_summary>
<patch_integration>
Critically analyze patch fit, behavior changes, conflicts, issues, consequences. 
</patch_integration>
<code_examination>
Break down changes. Explain purpose. Call out logic errors and integration issues in detail:
- Unhandled edge cases: [list]
- Logic errors: [list]
- Missing imports: [list]
- Incomplete changes: [list] 
- Undefined variables/functions: [list]
- Non-functional code: [list]
Require justification for plan deviations. Criticize behavior changes not handled. Overlook NOTHING.
</code_examination>
<feedback>
Give critical, specific feedback on logic and integration ONLY. LIMIT FEEDBACK TO CURRENT TASK'S SCOPE. NO EXTRA SUGGESTIONS.
</feedback>
<next_step>
COMPLETE - mark the CURRENT TASK as complete
CONTINUE - apply the current changes, but make additional fixes before marking the CURRENT TASK as complete
REJECT - generate the code again
</next_step>

Focus on functional changes, logic errors and other issues. Do not provide feedback on code style,comments or docstrings unless they're necessary."""

modify_eval_suffix_prompt = """Again, you will critically review the code changes and consider the following concerns and respond in the following format. Your feedback will be very specific.

Inputs:
- Task description
- Code patch (diff) 
- Completed changes
- Current plan
- Current file
Steps:
1. Review CURRENT TASK for requirements.
2. Analyze code patch:
   - Purpose and impact of each change
   - Check for LLM failures: 
     - Logic errors
     - Unhandled edge cases
     - Missing imports
     - Incomplete changes
     - Undefined variables/functions
     - Usage of nullable attributes
     - Non-functional code
   - Alignment with plan and requirements
3. Perform critical contextual analysis:
   - Break down changes 
   - Explain reasoning
   - Identify logic issues, edge cases, plan deviations
   - Consider all scenarios and pitfalls
   - Consider backwards compatibility and future-proofing
   - Suggest fixes for problems
   - Evaluate error handling and fallback mechanisms
4. Be extremely critical. Do not overlook ANY issues.

Format:

<patch_integration>
Critically analyze patch fit, behavior changes, conflicts, issues, consequences. 
</patch_integration>

<code_examination>
Break down changes. Explain purpose. Call out logic errors and integration issues in detail:
- Unhandled edge cases: [list]
- Logic errors: [list]
- Missing imports: [list]
- Incomplete changes: [list] 
- Undefined variables/functions: [list]
- Non-functional code: [list]
Require justification for plan deviations. Criticize behavior changes not handled. Overlook NOTHING.
</code_examination>

<feedback>
Give critical, specific feedback on logic and integration ONLY. LIMIT FEEDBACK TO THE SCOPE OF THE CURRENT TASK. NO EXTRA SUGGESTIONS.
</feedback>

<next_step>
REJECT - the code is a step backwards, so we should revert the patch and generate the code again
CONTINUE - apply the current changes, but make additional tweaks before moving on to the next task of the plan
COMPLETE - mark the CURRENT TASK as complete as there are no concerns or missed edge cases
</next_step>

Note: Only mark the task as complete if you are confident that all requirements have been met, edge cases have been handled, error handling and fallback mechanisms are in place, and no further specific improvements are necessary. If there are any specific doubts or actionable suggestions for enhancements, provide feedback and mark the task as "CONTINUE". Again, limit the feedback to the scope of the current task.

Focus on functional changes, logic errors and other issues. Do not provide feedback on code style,comments or docstrings unless they're necessary.

Respond with your extremely critical analysis and feedback."""

# general framework for a dfs search
# 1. sample trajectory
# 2. for each trajectory, run the assistant until it hits an error or end state
#    - in either case perform self-reflection
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

# Eval agent specific to modify step
class ModifyEvaluatorAgent(ChatGPT):
    def evaluate_patch(
        self, 
        problem_statement: str, 
        patch: str, 
        changed_files: dict[str, dict[str, str]], 
        new_file_contents: str,
        current_plan: str, 
        current_task: str,
        file_name: str,
        warning_message: str = "",
        previous_attempt: str = "",
        chat_logger_messages: list[dict[str, str]] | None = None
    ):
        self.model = CLAUDE_MODEL
        self.messages = [Message(role="system", content=modify_eval_patch_prompt)]
        formatted_problem_statement = f"This is the task for the contractor to complete:\n<task_to_complete>\n{problem_statement}\n</task_to_complete>\n\n"
        formatted_patch_and_contents = f"This is the CURRENT PATCH that the contractor has submitted for evaluation:\n<current_patch file_name={file_name}>\n{patch}\n</current_patch>\n\n" + f"This is the current file after modifications:\n<current_file>\n{new_file_contents}\n</current_file>\n\n"
        formatted_plan = f"This is the current plan that we must follow:\n<entire_plan>\n{current_plan}\n</entire_plan>\n\n"
        contractor_changes_made: dict[str, str] = {}
        for file_name, file_data in changed_files.items():
            if "original_contents" not in file_data or "contents" not in file_data:
                continue
            diff = generate_diff(file_data["original_contents"], file_data["contents"])
            if diff:
                contractor_changes_made[file_name] = diff
        contractor_changed_files = "\n".join([f"<completed_patch file_name={file_name}>\n{diff}\n</completed_patch>" for file_name, diff in contractor_changes_made.items()])
        changed_files_section = f"""The contractor has already completed these changes as part of the completed tasks:\n<completed_changes>\n{contractor_changed_files}\n</completed_changes>\n\n"""
        content = formatted_problem_statement + formatted_plan + changed_files_section + formatted_patch_and_contents
        if warning_message:
            content += f"The changes also trigger the following warnings:\n<warnings>\n{warning_message}\n</warnings>\n\n"
        content += current_task
        if previous_attempt:
            content += "\n\n" + previous_attempt
        content += "\n\n" + modify_eval_suffix_prompt
        evaluate_response = self.chat_anthropic(
            content=content,
            stop_sequences=["</message_to_contractor>"],
            model=CLAUDE_MODEL,
            message_key="user_request",
        )
        evaluate_response += "</message_to_contractor>" # add the stop sequence back in, if it stopped for another reason we've crashed
        # update chat_logger_messages in place if they are passed in
        if chat_logger_messages:
            chat_logger_messages.append({"role": "assistant", "content": content})
            chat_logger_messages.append({"role": "user", "content": evaluate_response})
        next_step = None
        feedback = ""
        try:
            next_step_pattern = r"<next_step>(.*?)</next_step>"
            message_to_contractor_pattern = r"<feedback>(.*?)</feedback>"

            next_step_match = re.search(next_step_pattern, evaluate_response, re.DOTALL)
            message_to_contractor_match = re.search(message_to_contractor_pattern, evaluate_response, re.DOTALL)

            if next_step_match is None or message_to_contractor_match is None:
                return next_step, feedback

            next_step = next_step_match.group(1).strip()
            # check if 1 through 10 are a match
            if not any(["COMPLETE" in next_step, "CONTINUE" in next_step, "REJECT" in next_step]):
                return None, ""
            else:
                if "COMPLETE" in next_step:
                    next_step = "COMPLETE"
                elif "CONTINUE" in next_step:
                    next_step = "CONTINUE"
                else:
                    next_step = "REJECT"
            feedback = message_to_contractor_match.group(1).strip()
            return next_step, feedback
        except Exception as e:
            logger.info(f"Error evaluating response: {e}")
            return next_step, feedback


    def evaluate_run(self, problem_statement: str, run_text: str, changed_files: dict[str, dict[str, str]]):
        self.model = CLAUDE_MODEL
        self.messages = [Message(role="system", content=modify_eval_prompt)]
        formatted_problem_statement = f"This is the task for the contractor to complete:\n<task_to_complete>\n{problem_statement}\n</task_to_complete>"
        contractor_changes_made: dict[str, str] = {}
        for file_name, file_data in changed_files.items():
            diff = generate_diff(file_data["original_contents"], file_data["contents"])
            if diff:
                contractor_changes_made[file_name] = diff
        contractor_changed_files = "\n".join([f"Changes made to file {file_name}:\n\n{diff}\n\n" for file_name, diff in contractor_changes_made.items()])
        changed_files_section = f"""The contractor made these changes to the following files:\n<changed_files>\n{contractor_changed_files}\n</changed_files>"""
        content = formatted_problem_statement + "\n\n" + f"<contractor_attempt>\n{run_text}\n</contractor_attempt>"\
             + f"\n\n{changed_files_section}\n\n" + modify_eval_response_format
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
        import pdb # noqa
        # pylint: disable=no-member
        pdb.post_mortem(info[2])
        raise e