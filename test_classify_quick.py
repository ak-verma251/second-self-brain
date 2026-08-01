import os
import re
import sys
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv

def fix_and_test():
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY not found!")
        return

    client = Groq(api_key=api_key)
    
    print("Fetching active models from Groq...")
    try:
        models = client.models.list().data
        model_ids = [m.id for m in models]
        print(f"Available models: {', '.join(model_ids)}")
        
        # Prefer llama 3.3 70b, then 3.1 70b, then any llama 70b, then any llama
        llama_models = [m for m in model_ids if "llama" in m.lower() and "-8b" not in m.lower()]
        
        if "llama-3.3-70b-versatile" in model_ids:
            best_model = "llama-3.3-70b-versatile"
        elif "llama-3.3-70b-specdec" in model_ids:
            best_model = "llama-3.3-70b-specdec"
        elif "llama-3.1-70b-versatile" in model_ids:
            best_model = "llama-3.1-70b-versatile"
        elif llama_models:
            best_model = llama_models[0]
        else:
            best_model = model_ids[0] # fallback to whatever is first

        print(f"\nSelecting best active model: {best_model}")
        
        # Patch config.py
        config_path = Path("src/secondself/config.py")
        content = config_path.read_text(encoding="utf-8")
        new_content = re.sub(r'LLM_MODEL\s*=\s*".*"', f'LLM_MODEL = "{best_model}"', content)
        config_path.write_text(new_content, encoding="utf-8")
        print("Successfully updated src/secondself/config.py")
        
    except Exception as e:
        print(f"Error fetching models: {e}")
        return

    # Add src to path so we can import
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from secondself.classify import classify

    sample_text = """
    Attention Is All You Need. The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.
    """

    print("\nTesting Classification API with new model...")
    try:
        result = classify(sample_text)
        print("\n--- Success! ---")
        print(f"Category: {result.category}")
        print(f"Suggested Title: {result.suggested_title}")
        print(f"Summary: {result.summary}")
        print(f"Tags: {', '.join(result.tags)}")
        print(f"Confidence: {result.confidence}")
    except Exception as e:
        print(f"\n--- Error ---")
        print(str(e))

if __name__ == "__main__":
    fix_and_test()
