1:from copy import deepcopy
2:import json
3:import os
4:from typing import Iterator, Literal, Self
5:
6:import modal
7:import openai
8:import anthropic
9:from loguru import logger
10:from pydantic import BaseModel
11:import backoff
12:
13:from sweepai.core.entities import (
14:    Function,
15:    Message,
16:)
17:from sweepai.core.prompts import (
18:    system_message_prompt,
19:    system_message_issue_comment_prompt,
20:)
21:from sweepai.utils.constants import UTILS_NAME
22:from sweepai.utils.prompt_constructor import HumanMessagePrompt
23:from sweepai.core.entities import Message, Function
24:from sweepai.utils.chat_logger import ChatLogger
25:
26:# TODO: combine anthropic and openai
27:
28:AnthropicModel = (
29:    Literal["claude-v1"]
30:    | Literal["claude-v1.3-100k"]
31:    | Literal["claude-instant-v1.1-100k"]
32:)
33:OpenAIModel = Literal["gpt-3.5-turbo"] | Literal["gpt-4"] | Literal["gpt-4-32k"] | Literal["gpt-4-0613"] | Literal["gpt-4-32k-0613"] | Literal["gpt-3.5-turbo-16k-0613"]
34:ChatModel = OpenAIModel | AnthropicModel
35:model_to_max_tokens = {
36:    "gpt-3.5-turbo": 4096,
37:    "gpt-4": 8192,
38:    "gpt-4-0613": 8192,
39:    "gpt-4-32k": 32000,
40:    "gpt-4-32k-0613": 32000,
41:    "claude-v1": 9000,
42:    "claude-v1.3-100k": 100000,
43:    "claude-instant-v1.3-100k": 100000,
44:    "gpt-3.5-turbo-16k-0613": 16000,
45:}
46:temperature = 0.1
47:
48:def format_for_anthropic(messages: list[Message]) -> str:
49:    if len(messages) > 1:
50:        new_messages: list[Message] = [Message(role="system", content=messages[0].content + "\n" + messages[1].content)]
51:        messages = messages[2:] if len(messages) >= 3 else []
52:    else:
53:        new_messages: list[Message] = []
54:    for message in messages:
55:        new_messages.append(message)
56:    return "\n".join(
57:        f"{anthropic.HUMAN_PROMPT if message.role != 'assistant' else anthropic.AI_PROMPT} {message.content}"
58:        for message in new_messages
59:    ) + (anthropic.AI_PROMPT if new_messages[-1].role != "assistant" else "")
60:
61:
62:class ChatGPT(BaseModel):
63:    messages: list[Message] = [
64:        Message(
65:            role="system",
66:            content=system_message_prompt,
67:        )
68:    ]
69:    prev_message_states: list[list[Message]] = []
70:    model: ChatModel = "gpt-4-32k-0613"
71:    human_message: HumanMessagePrompt | None = None
72:    file_change_paths = []
73:    chat_logger: ChatLogger | None = None
74:
75:    @classmethod
76:    def from_system_message_content(
77:        cls, human_message: HumanMessagePrompt, is_reply: bool = False, **kwargs
78:    ) -> Self:
79:        if is_reply:
80:            system_message_content = system_message_issue_comment_prompt
81:
82:        # Todo: This moves prompts away from unified system message prompt
83:        # system_message_prompt + "\n\n" + human_message.construct_prompt()
84:        messages = [
85:           Message(role="system", content=system_message_prompt, key="system")
86:       ]
87:
88:        added_messages = human_message.construct_prompt() # [ { role, content }, ... ]
89:        for msg in added_messages:
90:            messages.append(Message(**msg))
91:
92:        return cls(
93:            messages = messages,
94:            human_message=human_message,
95:            **kwargs,
96:        )
97:
98:    @classmethod
99:    def from_system_message_string(cls, prompt_string, **kwargs) -> Self:
100:        return cls(
101:            messages=[Message(role="system", content=prompt_string, key="system")],
102:            **kwargs,
103:        )
104:
105:    def select_message_from_message_key(
106:        self, message_key: str, message_role: str = None
107:    ):
108:        if message_role:
109:            return [
110:                message
111:                for message in self.messages
112:                if message.key == message_key and message.role == message_role
113:            ][0]
114:        return [message for message in self.messages if message.key == message_key][0]
115:
116:    def delete_messages_from_chat(self, key_to_delete: str):
117:        self.messages = [
118:            message for message in self.messages if key_to_delete not in (message.key or '')
119:        ]
120:
121:    def delete_file_from_system_message(self, file_path: str):
122:        self.human_message.delete_file(file_path)
123:
124:    def get_message_content_from_message_key(
125:        self, message_key: str, message_role: str = None
126:    ):
127:        return self.select_message_from_message_key(
128:            message_key, message_role=message_role
129:        ).content
130:
131:    def update_message_content_from_message_key(
132:        self, message_key: str, new_content: str, message_role: str = None
133:    ):
134:        self.select_message_from_message_key(
135:            message_key, message_role=message_role
136:        ).content = new_content
137:
138:    def chat(
139:        self,
140:        content: str,
141:        model: ChatModel | None = None,
142:        message_key: str | None = None,
143:        functions: list[Function] = [],
144:        function_name: dict | None = None,
145:    ):
146:        if self.messages[-1].function_call is None:
147:            self.messages.append(Message(role="user", content=content, key=message_key))
148:        else:
149:            name = self.messages[-1].function_call["name"]
150:            self.messages.append(Message(role="function", content=content, key=message_key, name=name))
151:        model = model or self.model
152:        is_function_call = False
153:        if model in [args.__args__[0] for args in OpenAIModel.__args__]:
154:            # might be a bug here in all of this
155:            if functions:
156:                response = self.call_openai(model=model, functions=functions, function_name=function_name)
157:                response, is_function_call = response
158:                if is_function_call:
159:                    self.messages.append(
160:                        Message(role="assistant", content=None, function_call=response, key=message_key)
161:                    )
162:                    self.prev_message_states.append(self.messages)
163:                    return self.messages[-1].function_call
164:                else:
165:                    self.messages.append(
166:                        Message(role="assistant", content=response, key=message_key)
167:                    )
168:            else:
169:                response = self.call_openai(model=model, functions=functions)
170:                self.messages.append(
171:                    Message(role="assistant", content=response, key=message_key)
172:                )
173:        else:
174:            response = self.call_anthropic(model=model)
175:            self.messages.append(
176:                Message(role="assistant", content=response, key=message_key)
177:            )
178:        self.prev_message_states.append(self.messages)
179:        return self.messages[-1].content
180:    
181:    def call_openai(
182:        self, 
183:        model: ChatModel | None = None,
184:        functions: list[Function] = [],
185:        function_name: dict | None = None,
186:    ):
187:        if model is None:
188:            model = self.model
189:        count_tokens = modal.Function.lookup(UTILS_NAME, "Tiktoken.count")
190:        messages_length = sum(
191:            [count_tokens.call(message.content or "") for message in self.messages]
192:        )
193:        max_tokens = model_to_max_tokens[model] - int(messages_length) - 400 # this is for the function tokens
194:        # TODO: Add a check to see if the message is too long
195:        logger.info("file_change_paths" + str(self.file_change_paths))
196:        if len(self.file_change_paths) > 0:
197:            self.file_change_paths.remove(self.file_change_paths[0])
198:        if max_tokens < 0:
199:            if len(self.file_change_paths) > 0:
200:                pass
201:            else:
202:                raise ValueError(f"Message is too long, max tokens is {max_tokens}")
203:        messages_raw = "\n".join([(message.content or "") for message in self.messages])
204:        logger.info(f"Input to call openai:\n{messages_raw}")
205:
206:        gpt_4_buffer = 800
207:        if int(messages_length) + gpt_4_buffer < 6000 and model == "gpt-4-32k-0613":
208:            model = "gpt-4-0613"
209:            max_tokens = model_to_max_tokens[model] - int(messages_length) - gpt_4_buffer # this is for the function tokens
210:        if "gpt-4" in model:
211:            max_tokens = min(max_tokens, 5000)
212:        logger.info(f"Using the model {model}, with {max_tokens} tokens remaining")
213:        global retry_counter
214:        retry_counter = 0
215:        if functions:
216:            @backoff.on_exception(
217:                backoff.expo,
218:                Exception,
219:                max_tries=12,
220:                jitter=backoff.random_jitter,
221:
222:            )
223:            def fetch():
224:                global retry_counter
225:                retry_counter += 1
226:                token_sub = retry_counter * 200
227:                try:
228:                    output = None
229:                    if function_name:
230:                        output = (
231:                            openai.ChatCompletion.create(
232:                                model=model,
233:                                messages=self.messages_dicts,
234:                                max_tokens=max_tokens - token_sub,
235:                                temperature=temperature,
236:                                functions=[json.loads(function.json()) for function in functions],
237:                                function_call=function_name,
238:                            )
239:                            .choices[0].message
240:                        )
241:                    else:
242:                        output = (
243:                            openai.ChatCompletion.create(
244:                                model=model,
245:                                messages=self.messages_dicts,
246:                                max_tokens=max_tokens - token_sub,
247:                                temperature=temperature,
248:                                functions=[json.loads(function.json()) for function in functions],
249:                            )
250:                            .choices[0].message
251:                        )
252:                    if self.chat_logger is not None: self.chat_logger.add_chat({
253:                        'model': model,
254:                        'messages': self.messages_dicts,
255:                        'max_tokens': max_tokens - token_sub,
256:                        'temperature': temperature,
257:                        'functions': [json.loads(function.json()) for function in functions],
258:                        'function_call': function_name,
259:                        'output': output,
260:                    })
261:                    return output
262:                except Exception as e:
263:                    logger.warning(e)
264:                    raise e
265:            result = fetch()
266:            if "function_call" in result:
267:                result = dict(result["function_call"]), True
268:            else:
269:                result = result["content"], False
270:            logger.info(f"Output to call openai:\n{result}")
271:            return result
272:
273:        else:
274:            @backoff.on_exception(
275:                backoff.expo,
276:                Exception,
277:                max_tries=12,
278:                jitter=backoff.random_jitter,
279:            )
280:            def fetch():
281:                global retry_counter
282:                retry_counter += 1
283:                token_sub = retry_counter * 200
284:                try:
285:                    output = openai.ChatCompletion.create(
286:                            model=model,
287:                            messages=self.messages_dicts,
288:                            max_tokens=max_tokens - token_sub,
289:                            temperature=temperature,
290:                        ) \
291:                        .choices[0] \
292:                        .message["content"]
293:                    if self.chat_logger is not None: self.chat_logger.add_chat({
294:                        'model': model,
295:                        'messages': self.messages_dicts,
296:                        'max_tokens': max_tokens - token_sub,
297:                        'temperature': temperature,
298:                        'output': output
299:                    })
300:                    return output
301:                except Exception as e:
302:                    logger.warning(e)
303:                    raise e
304:            result = fetch()
305:            logger.info(f"Output to call openai:\n{result}")
306:            return result
307:    
308:    def call_anthropic(self, model: ChatModel | None = None) -> str:
309:        if model is None:
310:            model = self.model
311:        count_tokens = modal.Function.lookup(UTILS_NAME, "Tiktoken.count")
312:        messages_length = sum(
313:            [int(count_tokens.call(message.content) * 1.1) for message in self.messages]
314:        )
315:        max_tokens = model_to_max_tokens[model] - int(messages_length) - 1000
316:        logger.info(f"Number of tokens: {max_tokens}")
317:        messages_raw = format_for_anthropic(self.messages)
318:        logger.info(f"Input to call anthropic:\n{messages_raw}")
319:
320:        assert os.environ.get("ANTHROPIC_API_KEY"), "Please set ANTHROPIC_API_KEY"
321:        client = anthropic.Client(api_key=os.environ.get("ANTHROPIC_API_KEY"))
322:
323:        @backoff.on_exception(
324:            backoff.expo,
325:            Exception,
326:            max_tries=12,
327:            jitter=backoff.random_jitter,
328:        )
329:        def fetch() -> tuple[str, str]:
330:            logger.warning(f"Calling anthropic...")
331:            results = client.completion(
332:                prompt=messages_raw,
333:                stop_sequences=[anthropic.HUMAN_PROMPT],
334:                model=model,
335:                max_tokens_to_sample=max_tokens,
336:                disable_checks=True,
337:                temperature=temperature,
338:            )
339:            return results["completion"], results["stop_reason"]
340:
341:        result, stop_reason = fetch()
342:        logger.warning(f"Stop reasons: {stop_reason}")
343:        if stop_reason == "max_tokens":
344:            logger.warning("Hit max tokens, running for more tokens.")
345:            _self = deepcopy(self)
346:            _self.messages.append(Message(role="assistant", content=result, key=""))
347:            extension = _self.call_anthropic(model=model)
348:            print(len(result), len(extension), len(result + extension))
349:            return result + extension
350:        logger.info(f"Output to call anthropic:\n{result}")
351:        return result
352:    
353:    def chat_stream(
354:        self,
355:        content: str,
356:        model: ChatModel | None = None,
357:        message_key: str | None = None,
358:        functions: list[Function] = [],
359:        function_call: dict | None = None,
360:    ) -> Iterator[dict]:
361:        if self.messages[-1].function_call is None:
362:            self.messages.append(Message(role="user", content=content, key=message_key))
363:        else:
364:            name = self.messages[-1].function_call["name"]
365:            self.messages.append(Message(role="function", content=content, key=message_key, name=name))
366:        model = model or self.model
367:        is_function_call = False
368:        # might be a bug here in all of this
369:        # return self.stream_openai(model=model, functions=functions, function_name=function_name)
370:        return self.stream_openai(model=model, functions=functions, function_call=function_call)
371:    
372:    def stream_openai(
373:        self,
374:        model: ChatModel | None = None,
375:        functions: list[Function] = [],
376:        function_call: dict | None = None,
377:    ) -> Iterator[dict]:
378:        model = model or self.model
379:        count_tokens = modal.Function.lookup(UTILS_NAME, "Tiktoken.count")
380:        messages_length = sum(
381:            [count_tokens.call(message.content or "") for message in self.messages]
382:        )
383:        max_tokens = model_to_max_tokens[model] - int(messages_length) - 400 # this is for the function tokens
384:        # TODO: Add a check to see if the message is too long
385:        logger.info("file_change_paths" + str(self.file_change_paths))
386:        if len(self.file_change_paths) > 0:
387:            self.file_change_paths.remove(self.file_change_paths[0])
388:        if max_tokens < 0:
389:            if len(self.file_change_paths) > 0:
390:                pass
391:            else:
392:                raise ValueError(f"Message is too long, max tokens is {max_tokens}")
393:        messages_raw = "\n".join([(message.content or "") for message in self.messages])
394:        logger.info(f"Input to call openai:\n{messages_raw}")
395:
396:        gpt_4_buffer = 800
397:        if int(messages_length) + gpt_4_buffer < 6000 and model == "gpt-4-32k-0613":
398:            model = "gpt-4-0613"
399:            max_tokens = model_to_max_tokens[model] - int(messages_length) - gpt_4_buffer # this is for the function tokens
400:
401:        logger.info(f"Using the model {model}, with {max_tokens} tokens remaining")
402:        def generator() -> Iterator[str]:
403:            stream = openai.ChatCompletion.create(
404:                model=model,
405:                messages=self.messages_dicts,
406:                temperature=temperature,
407:                functions=[json.loads(function.json()) for function in functions],
408:                function_call=function_call or "auto",
409:                stream=True
410:            ) if functions else openai.ChatCompletion.create(
411:                model=model,
412:                messages=self.messages_dicts,
413:                temperature=temperature,
414:                stream=True
415:            )
416:            for data in stream:
417:                chunk = data.choices[0].delta
418:                yield chunk
419:        return generator()
420:
421:    @property
422:    def messages_dicts(self):
423:        # Remove the key from the message object before sending to OpenAI
424:        cleaned_messages = [
425:            message.to_openai()
426:            for message in self.messages
427:        ]
428:        return cleaned_messages
429:
430:    def undo(self):
431:        if len(self.prev_message_states) > 0:
432:            self.messages = self.prev_message_states.pop()
433:        return self.messages
434:
