import { getJSONPrefix } from "@/lib/str_utils";
import { ReadableStreamDefaultReadResult } from "stream/web";


async function* streamMessages(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  isStream?: React.MutableRefObject<boolean>,
  timeout: number = 90000
): AsyncGenerator<any, void, unknown> {
  let done = false;
  let buffer = "";
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  while (!done && (isStream ? isStream.current : true)) {
    try {
      const { value, done: streamDone } = await Promise.race([
        reader.read(),
        new Promise<ReadableStreamDefaultReadResult<Uint8Array>>((_, reject) => {
          if (timeoutId) {
            clearTimeout(timeoutId)
          }
          timeoutId = setTimeout(() => reject(new Error("Stream timeout after " + timeout / 1000 + " seconds, this is likely caused by the LLM freezing. You can try again by editing your last message. Further, decreasing the number of snippets to retrieve in the settings will help mitigate this issue.")), timeout)
        })
      ]);

      if (streamDone) {
        done = true;
        continue;
      }
      
      if (value) {
        const decodedValue = new TextDecoder().decode(value);
        buffer += decodedValue;

        const [parsedObjects, currentIndex] = getJSONPrefix(buffer)
        for (let parsedObject of parsedObjects) {
          yield parsedObject
        }
        buffer = buffer.slice(currentIndex)
      }
    } catch (error) {
      console.error("Error during streaming:", error);
      throw error;
    } finally {
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
    }
  }
  if (buffer) {
    console.warn("Buffer:", buffer)
  }
}

export { streamMessages }