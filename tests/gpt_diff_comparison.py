import re
import numpy as np
from openai import OpenAI
import colorsys  # Import for color calculations
from IPython.display import display, HTML
from openai.resources.chat.completions import ChatCompletion

def highlight_text(api_response: ChatCompletion):
    tokens = api_response.choices[0].logprobs.content

    html_output = ""
    num_tokens = len(tokens)

    for token in tokens:
        token_str = bytes(token.bytes).decode("utf-8")

        # Calculate color based on token position (from blue to red)
        h = np.exp(token.logprob)*100  # Normalized position (0.0 to 1.0)
        r, g, b = colorsys.hsv_to_rgb(h * 0.66, 1.0, 1.0)  # HSV to RGB (blue to red)
        color = f"rgb({int(r*255)}, {int(g*255)}, {int(b*255)})"

        # Add colored token to HTML output
        html_output += f"<span style='color: {color}'>{token_str}</span>" 

    display(HTML(html_output)) 
    print(f"Total number of tokens: {num_tokens}")

client = OpenAI()

system_prompt = """You are an expert software developer. We need to compare two git patches to determine whether they are functionally equivalent or different. Ignore changes such as logs or comments. Ignore implementation differences if the resulting behavior is the same.\n\nBe exceptionally meticulous to determine whether or not they perform the same functional.\n\nRespond in the following format:\n\n<summary_of_patch_one>\nsummarize the first patch's functional changes\n</summary_of_patch_one>\n\n<summary_of_patch_two>\nsummarize the second patch's functional changes\n</summary_of_patch_two>\n\n<equivalent_or_different>\nreturn equivalent or different **only**\n</equivalent_or_different>"""

example_prompt = """<patch_one>
---
+++
@@ -516,17 +516,37 @@ def clone(self):
     def __eq__(self, other):
         # Needed for @total_ordering
         if isinstance(other, Field):
-            return self.creation_counter == other.creation_counter
+            return (
+                self.creation_counter == other.creation_counter and
+                getattr(self, 'model', None) == getattr(other, 'model', None)
+            )
         return NotImplemented

     def __lt__(self, other):
         # This is needed because bisect does not take a comparison function.
+        # Order by creation_counter first for backward compatibility.
         if isinstance(other, Field):
-            return self.creation_counter < other.creation_counter
+            if (
+                self.creation_counter != other.creation_counter or
+                not hasattr(self, 'model') and not hasattr(other, 'model')
+            ):
+                return self.creation_counter < other.creation_counter
+            elif hasattr(self, 'model') != hasattr(other, 'model'):
+                return not hasattr(self, 'model')  # Order no-model fields first
+            else:
+                # creation_counter's are equal, compare only models.
+                return (
+                    (self.model._meta.app_label, self.model._meta.model_name) <
+                    (other.model._meta.app_label, other.model._meta.model_name)
+                )
         return NotImplemented

     def __hash__(self):
-        return hash(self.creation_counter)
+        return hash((
+            self.creation_counter,
+            self.model._meta.app_label if hasattr(self, 'model') else None,
+            self.model._meta.model_name if hasattr(self, 'model') else None,
+        ))

     def __deepcopy__(self, memodict):
         # We don't have to deepcopy very much here, since most things are not
</patch_one>

<patch_two>
---
+++
@@ -516,17 +516,37 @@ def clone(self):
     def __eq__(self, other):
         # Needed for @total_ordering
         if isinstance(other, Field):
-            return self.creation_counter == other.creation_counter
+            return (
+                self.creation_counter == other.creation_counter and
+                getattr(self, 'model', None) == getattr(other, 'model', None)
+            )
         return NotImplemented

     def __lt__(self, other):
         # This is needed because bisect does not take a comparison function.
+        # Order by creation_counter first for backward compatibility.
         if isinstance(other, Field):
-            return self.creation_counter < other.creation_counter
+            if (
+                self.creation_counter != other.creation_counter or
+                not hasattr(self, 'model') and not hasattr(other, 'model')
+            ):
+                return self.creation_counter < other.creation_counter
+            elif hasattr(self, 'model') != hasattr(other, 'model'):
+                return not hasattr(self, 'model')  # Order no-model fields first
+            else:
+                # creation_counter's are equal, compare only models.
+                return (
+                    (self.model._meta.app_label, self.model._meta.model_name) <
+                    (other.model._meta.app_label, other.model._meta.model_name)
+                )
         return NotImplemented

     def __hash__(self):
-        return hash(self.creation_counter)
+        return hash((
+            self.creation_counter,
+            self.model._meta.app_label if hasattr(self, 'model') else None,
+            self.model._meta.model_name if hasattr(self, 'model') else None,
+        ))

     def __deepcopy__(self, memodict):
         # We don't have to deepcopy very much here, since most things are not
</patch_two>"""

# parse diff_comparison.csv using csvreader to get equivalent_patch, non_equivalent_patch, and patch_to_compare
def parse_diff_comparison():
    equivalent_patch = []
    non_equivalent_patch = []
    patch_to_compare = []
    with open('tests/diff_comparison.csv', 'r') as file:
        for line in file.readlines()[1:]:
            line = line.split('<diff>')
            equivalent_patch.append(line[0])
            non_equivalent_patch.append(line[1])
            patch_to_compare.append(line[2])
    return equivalent_patch, non_equivalent_patch, patch_to_compare


def generate_call_from_patches(patch_one, patch_two):
    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[
            {
            "role": "system",
            "content": system_prompt
            },
            {
            "role": "user",
            # "content": f"<patch_one>{patch_one}</patch_one>\n\n<patch_two>{patch_two}</patch_two>"
            "content": example_prompt
            },
        ],
        temperature=0.2,
        max_tokens=512,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        logprobs=True,
        top_logprobs=2,
    )
    acc = {np.round(np.exp(logprob.logprob)*100,2): logprob.token for logprob in response.choices[0].logprobs.content[0].top_logprobs}
    logprobs = response.choices[0].logprobs.content[0].top_logprobs
    response_content = response.choices[0].message.content
    
    # regex match xml tags of equivalent_or_different
    match = re.search(r'<equivalent_or_different>(.*?)</equivalent_or_different>', response_content, re.DOTALL)
    equivalent_or_different = match.group(1)
    return equivalent_or_different

generate_call_from_patches(example_prompt, example_prompt)