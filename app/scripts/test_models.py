import os
from dotenv import load_dotenv
from openai import OpenAI

# Load .env if present
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY", "pass here api key")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=api_key
)

print("Fetching available models from Groq API...\n")
models = client.models.list()

print("=" * 60)
print("✅ AVAILABLE GROQ MODELS RIGHT NOW:")
print("=" * 60)

chat_capable = []
other_models = []

for m in models.data:
    model_id = m.id
    print(f"• {model_id} (owned by: {getattr(m, 'owned_by', 'groq')})")
    
    # Try a quick test completion
    try:
        res = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Say hello in 3 words"}],
            max_tokens=10,
        )
        chat_capable.append((model_id, res.choices[0].message.content.strip().replace("\n", " ")))
    except Exception:
        other_models.append(model_id)

print("\n" + "=" * 60)
print("💬 WORKING CHAT / TEXT COMPLETION MODELS:")
print("=" * 60)
for model_id, sample in chat_capable:
    print(f"  ✓ {model_id} -> Test response: \"{sample}\"")

if other_models:
    print("\n" + "=" * 60)
    print("🎙️ / 🛡️ SPECIALIZED MODELS (Audio, Moderation, etc.):")
    print("=" * 60)
    for model_id in other_models:
        print(f"  • {model_id}")