from openai import OpenAI

c = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
tools = [{"type": "function", "function": {
    "name": "somma", "description": "somma due numeri",
    "parameters": {"type": "object",
                   "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                   "required": ["a", "b"]}}}]

for m in ["tinyllama:latest", "llama3.2:3b-instruct-q4_K_M", "nemotron-mini:latest","llama3.2:1b" ,"deepseek-r1:1.5b" ,"smollm2:1.7b"]:
    try:
        r = c.chat.completions.create(
            model=m, tools=tools,
            messages=[{"role": "user", "content": "Quanto fa 2+3? Usa lo strumento."}])
        tc = r.choices[0].message.tool_calls
        print(m, "->", "CHIAMATA AL TOOL" if tc else "nessuna chiamata (solo testo)")
    except Exception as e:
        print(m, "-> ERRORE:", str(e)[:120])