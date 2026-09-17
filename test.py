from google import genai

client = genai.Client(api_key="AIzaSyAnDqjHOJUWN7_ujDrBbxYBd23Vvilk3kQ")

print("AVAILABLE MODELS:\n")

for model in client.models.list():
    print(model.name)