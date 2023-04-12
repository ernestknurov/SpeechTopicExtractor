import os
import time
import openai
import whisper
import telebot
from telebot import types
from dotenv import load_dotenv


load_dotenv()

token = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(token)
model = whisper.load_model("base")


@bot.message_handler(commands=['start', 'help'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    transcript_button = types.KeyboardButton("Transcript audio")
    summarize_button = types.KeyboardButton("Summarize text")
    transcript_and_summarize_button = types.KeyboardButton("Transcript & summarize")

    markup.add(transcript_button, summarize_button, transcript_and_summarize_button)
    bot.send_message(message.chat.id, "Hi! What to do?", reply_markup=markup)
    bot.register_next_step_handler(message, reply_actions)


@bot.message_handler(content_types=['text'])
def reply_actions(message):
    if message.text == "Transcript audio":
        bot.send_message(message.chat.id, "Send an audio or voice message")
        bot.register_next_step_handler(message, transcript)

    elif message.text == "Summarize text":
        bot.send_message(message.chat.id, "Paste the text or send the document")
        bot.register_next_step_handler(message, summarize)

    elif message.text == "Transcript & summarize":
        bot.send_message(message.chat.id, "Send an audio or voice message")
        bot.register_next_step_handler(message, transcript_and_summarize)
    else:
        bot.send_message(message.chat.id, "I don't know this option")


def transcript(message):
    try:
        global model
        if message.audio:
            file_id = message.audio.file_id
            save_dir = 'audios'
            file_name = message.audio.file_name
        elif message.voice:
            file_id = message.voice.file_id
            save_dir = 'voices'
            file_name = str(message.date) + ".ogg"
        else:
            bot.send_message(message.chat.id, "<b>Wrong input type</b>", parse_mode='html')
            return

        file_info = bot.get_file(file_id)
        file_path = save_dir + '/' + file_name
        downloaded_file = bot.download_file(file_info.file_path)
        bot.send_message(message.chat.id, "Transcription of <b>audio</b> (can take a minute):", parse_mode='html')
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        audio_transcription = model.transcribe(file_path, fp16=False)['text']
        bot.send_message(message.chat.id, audio_transcription)
        # pretty_message = json.dumps(json.loads(jsonpickle.encode(message)), sort_keys=True, indent=4)
        # print(pretty_message)

    except Exception as ex:
        bot.send_message(message.chat.id, f"[!] error - {str(ex)}")


def summarize(message):
    try:
        if message.text:
            text = message.text
        elif message.document:
            file_id = message.document.file_id
            file_info = bot.get_file(file_id)
            text = str(bot.download_file(file_info.file_path))
        else:
            bot.send_message(message.chat.id, "<b>Wrong input type</b>", parse_mode='html')
            return

        bot.send_message(message.chat.id, "Extracting main topics (can take a minute):", parse_mode='html')
        summary = extract_topics(text, with_timecode=False)
        with open("documents/summary.txt", "w", encoding='utf-8') as text_file:
            text_file.write(summary)
            print("Summarizing Completed.")
            print("Saved Summary to Summary.txt")
        if len(summary) < 4096:
            bot.send_message(message.chat.id, summary)
        else:
            f = open("documents/summary.txt", "rb")
            bot.send_message(message.chat.id, "Summary is to large, sending document instead:")
            bot.send_document(message.chat.id, f)

    except Exception as ex:
        bot.send_message(message.chat.id, f"[!] error - {str(ex)}")


def transcript_and_summarize(message):
    try:
        global model
        if message.audio:
            file_id = message.audio.file_id
            save_dir = 'audios'
            file_name = message.audio.file_name
        elif message.voice:
            file_id = message.voice.file_id
            save_dir = 'voices'
            file_name = str(message.date) + ".ogg"
        else:
            bot.send_message(message.chat.id, "<b>Wrong input type</b>", parse_mode='html')
            return

        bot.send_message(message.chat.id, "Loading...")

        file_info = bot.get_file(file_id)
        file_path = save_dir + '/' + file_name
        downloaded_file = bot.download_file(file_info.file_path)
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        audio_transcription = model.transcribe(file_path, fp16=False)
        text = get_timecode_text(audio_transcription['segments'], step=5)

        with open("documents/timecode_transcription.txt", "w", encoding='utf-8') as text_file:
            text_file.write(text)
            print("Saved time_transcription.txt")

        summary = extract_topics(text, with_timecode=True)

        with open("documents/summary.txt", "w", encoding='utf-8') as text_file:
            text_file.write(summary)
            print("Summarizing Completed.")
            print("Saved Summary to Summary.txt")

        if len(summary) < 4096:
            bot.send_message(message.chat.id, summary)
        else:
            f = open("documents/summary.txt", "rb")
            bot.send_message(message.chat.id, "Summary is to large, sending document instead:")
            bot.send_document(message.chat.id, f)

    except Exception as ex:
        bot.send_message(message.chat.id, f"[!] error - {str(ex)}")


def extract_topics(text, with_timecode):
    load_dotenv()
    openai.api_key = os.getenv('OPENAI_API_KEY')
    print(openai.api_key)
    print("Processing Transcript with GPT...")
    n = 1300
    split = text.split()
    snippet = [' '.join(split[i:i + n]) for i in range(0, len(split), n)]
    # For managing token limit
    summary = ""
    previous = ""

    if with_timecode:
        prompt = "\"\nExtract the time codes when the main ideas of the text. Keep it short. For additional context here is the previous time codes and their main ideas: \n "
    else:
        prompt = "\"\nExtract the main ideas of the text. Keep it short. For additional context here is the previous part and their main ideas: \n "

    for i in range(0, len(snippet), 1):
        print(f"Summarizing Transcribed Snippet {i + 1} of {len(snippet)}")
        gpt_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "\"" + snippet[i] + prompt + previous}],
            temperature=0.6,
        )
        previous = gpt_response['choices'][0]['message']['content']
        summary += gpt_response['choices'][0]['message']['content']


    if len(summary) >= 4096:
        final_summary = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": "\"" + summary + prompt.split(". For")[0]}],
            temperature=0.6,
        )['choices'][0]['message']['content']
    else:
        final_summary = summary

    return final_summary


def get_timecode_text(segments, step=1):
    text = ""
    for i in range(0, len(segments)):
        seg = segments[i]
        if i % step == 0:
            start_time = int(seg['start'])
            text += "\n" + time.strftime('%H:%M:%S', time.gmtime(start_time)) + "\n" + seg['text']
        else:
            text += seg['text']

    return text


bot.polling(none_stop=True)
