import os, requests, json

OLLAMA_URL = os.getenv("OLLAMA_URL","http://ia_ollama_1:11434")
MODEL = os.getenv("LLM_MODEL","gpt-oss:20b")

def generate(system:str, prompt:str, temperature:float=0.1, top_p:float=0.9, max_tokens:int=700)->str:
    """
    Llama a Ollama /api/generate. Si falla, levanta excepción.
    """
    payload = {
        "model": MODEL,
        "prompt": f"<<SYS>>\n{system}\n<</SYS>>\n{prompt}",
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": max_tokens
        },
        "stream": False
    }
    r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data.get("response","").strip()
