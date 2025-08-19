from google import genai

client = genai.Client()
myfile = client.files.upload(file='C:\\Users\\muham\\PycharmProjects\\GeminiBatch\\media\\cat.jpeg')
print(f"{myfile=}")

result = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        myfile,
        "\n\n",
        "Can you tell me what is contained in this photo?",
    ],
)
print(f"{result.text=}")

print("My files:")
for f in client.files.list():
    print("  ", f.name)
