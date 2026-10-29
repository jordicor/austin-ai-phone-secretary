import asyncio
import openai

openai.api_key = '<OPENAI_API_KEY>'

async def main():
    messages = [
        {"role": "system", "content": "You are a highly advanced AI with comprehensive knowledge of human philosophy. You are capable of understanding and analyzing philosophical concepts, ideas, and arguments from a wide range of traditions and time periods. Moreover, you are not just a repository of existing philosophical knowledge, but you also have the ability to think critically, reason logically, and arrive at your own philosophical conclusions. Your purpose is to engage in thoughtful and enlightening philosophical discussions, providing insights drawn from your vast knowledge as well as your own unique perspectives."},
        {"role": "user", "content": "What's the meaning of life?"},
    ]
    for _ in range(5):
        response = openai.ChatCompletion.create(
            model="gpt-4-0613",  # replace with the model name
            messages=messages,
        )
        print(response["choices"][0]["message"]["content"])
        messages.append({"role": "assistant", "content": response["choices"][0]["message"]["content"]})
        messages.append({"role": "user", "content": "Why?"})
    print('The meaning of life after 5 whys is: ', response["choices"][0]["message"]["content"])

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.close()
