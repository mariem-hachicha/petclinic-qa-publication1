"""Vérifie que la clé Gemini fonctionne et liste les modèles disponibles."""
import os
from google import genai

# Le client lit automatiquement la variable d'environnement GEMINI_API_KEY
client = genai.Client()

print("Modèles disponibles pour générer du texte :")
for model in client.models.list():
    if "generateContent" in (model.supported_actions or []):
        print("  ", model.name)

model_name = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
print(f"\nTest d'appel avec le modèle : {model_name}")
response = client.models.generate_content(
    model=model_name,
    contents="Réponds uniquement par le mot : OK",
)
print("Réponse :", response.text)