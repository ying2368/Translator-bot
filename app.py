import sys
import configparser

# Azure Speech
import os
import azure.cognitiveservices.speech as speechsdk
import librosa

# Azure Translation
from azure.ai.translation.text import TextTranslationClient
# from azure.ai.translation.text.models import InputTextItem
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError


# Azure Text Analytics
from azure.ai.textanalytics import TextAnalyticsClient

from flask import Flask, request, abort, render_template, url_for, jsonify
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    AudioMessage
)

#Config Parser
config = configparser.ConfigParser()
config.read('config.ini')
#Config Azure Analytics
credential = AzureKeyCredential(config['AzureLanguage']['API_KEY'])

# Azure Speech Settings
speech_config = speechsdk.SpeechConfig(subscription=config['AzureSpeech']['SPEECH_KEY'], 
                                       region=config['AzureSpeech']['SPEECH_REGION'])
audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
UPLOAD_FOLDER = 'static'

# Translator Setup
text_translator = TextTranslationClient(
    credential=AzureKeyCredential(config["AzureTranslator"]["Key"]),
    endpoint=config["AzureTranslator"]["EndPoint"],
    region=config["AzureTranslator"]["Region"],
)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

channel_access_token = config['Line']['CHANNEL_ACCESS_TOKEN']
channel_secret = config['Line']['CHANNEL_SECRET']
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

handler = WebhookHandler(channel_secret)

configuration = Configuration(
    access_token=channel_access_token
)

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # parse webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def message_text(event):
    sentiment = azure_sentiment(event.message.text)
    translation_result, detected_language = azure_translate(event.message.text)
    audio_duration = azure_speech(translation_result,detected_language,sentiment)
    #translation_result_2 = azure_translate2(translation_result, detected_language)
    print(translation_result)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=sentiment),
                          TextMessage(text=translation_result),
                          #TextMessage(text=translation_result_2),
                          AudioMessage(originalContentUrl=config["Deploy"]["URL"]+"/static/outputaudio.wav", duration=audio_duration)
                ]
            )
        )

def azure_sentiment(user_input):
    text_analytics_client = TextAnalyticsClient(
        endpoint=config['AzureLanguage']['END_POINT'], 
        credential=credential)
    documents = [user_input]
    response = text_analytics_client.analyze_sentiment(
        documents, 
        show_opinion_mining=True)
    #print(response)
    docs = [doc for doc in response if not doc.is_error]
    for idx, doc in enumerate(docs):
        print(f"Document text : {documents[idx]}")
        print(f"Overall sentiment : {doc.sentiment}")
    return docs[0].sentiment

def azure_speech(user_input,detected_language,sentiment):
    # The language of the voice that speaks.

    print(detected_language,sentiment)

    if(detected_language=='zh-Hant'):  # 繁體中文 -> 使用日文語音
        speech_config.speech_synthesis_voice_name = "ja-JP-NanamiNeural"
        file_name = "outputaudio_" + sentiment +".wav"
        file_config = speechsdk.audio.AudioOutputConfig(filename="static/" + file_name)
        speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config, audio_config=file_config
        )

        ssml_user_input = '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="ja-JP">'
        ssml_user_input += '<voice name="ja-JP-NanamiNeural">'
       
        if(sentiment=='positive'):
            ssml_user_input += '<mstts:express-as style="Cheerful" styledegree="2">'
        else:
            ssml_user_input += '<mstts:express-as style="Default" styledegree="2">'

    else:   # 日文 -> 使用中文語音
        speech_config.speech_synthesis_voice_name = "zh-CN-XiaoxiaoMultilingualNeural"
        file_name = "outputaudio.wav"
        file_config = speechsdk.audio.AudioOutputConfig(filename="static/" + file_name)
        speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config, audio_config=file_config
        )

        ssml_user_input = '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="zh-CN">'
        ssml_user_input += '<voice name="zh-CN-XiaoxiaoMultilingualNeural">'
        if(sentiment=='negative'):
            ssml_user_input += '<mstts:express-as style="Sorrt" styledegree="2">'
        elif(sentiment=='positive'):
            ssml_user_input += '<mstts:express-as style="Cheerful" styledegree="2">'
        else:
            ssml_user_input += '<mstts:express-as style="Default" styledegree="2">'

    ssml_user_input += user_input
    ssml_user_input += "</mstts:express-as>"
    ssml_user_input += "</voice>"
    ssml_user_input += "</speak>"

    # Receives a text from console input and synthesizes it to wave file.
    # result = speech_synthesizer.speak_text_async(user_input).get()
    result = speech_synthesizer.speak_ssml_async(ssml_user_input).get()
    # Check result
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(
            "Speech synthesized for text [{}], and the audio was saved to [{}]".format(
                user_input, file_name
            )
        )
        audio_duration = round(
            librosa.get_duration(path="static/outputaudio.wav") * 1000
        )
        print(audio_duration)
        return audio_duration
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            print("Error details: {}".format(cancellation_details.error_details))

def web_azure_speech(user_input, language, sentiment):
    speech_config.speech_synthesis_voice_name = "ja-JP-NanamiNeural"
    name = "ja-JP-NanamiNeural"

    file_name = f"outputaudio_{sentiment}.wav"  # 根據不同情感生成不同的文件名
    file_config = speechsdk.audio.AudioOutputConfig(filename="static/" + file_name)
    speech_synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=file_config
    )
    ssml_user_input = ""
    ssml_user_input += '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="zh-CN">'
    ssml_user_input += f'<voice name="{name}">'
    ssml_user_input += f'<mstts:express-as style="{sentiment}" styledegree="2">'
    ssml_user_input += user_input
    ssml_user_input += '</mstts:express-as>'
    ssml_user_input += '</voice>'
    ssml_user_input += '</speak>'
    # Receives a text from console input and synthesizes it to wave file.
    # result = speech_synthesizer.speak_text_async(user_input).get()
     # 將文本轉換為音頻
    result = speech_synthesizer.speak_ssml_async(ssml_user_input).get()

    # 確認結果並返回音頻文件時長
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(f"Speech synthesized for text [{user_input}], and the audio was saved to [{file_name}]")
        audio_duration = round(librosa.get_duration(path="static/" + file_name) * 1000)  # 獲取音頻時長（毫秒）
        return file_name, audio_duration
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            print("Error details: {}".format(cancellation_details.error_details))
        return None, 0
    
def azure_translate(user_input):

    try:
        target_languages = ["zh-hant"]
        target_languages2 = ["ja"]
        # input_text_elements = [InputTextItem(text=user_input)]
        input_text_elements = [user_input]

        response = text_translator.translate(body=input_text_elements, to_language=target_languages)
        print(response)
        if response:
            detected_language = response[0].detected_language.language
            #print(f"Detected language: {detected_language}")
            
            # 如果偵測到的是繁體中文，則進行日文翻譯
            if detected_language == "zh-Hans":
                response = text_translator.translate(body=input_text_elements, to_language=target_languages2)

        translation = response[0] if response else None

        if translation:
            return translation.translations[0].text, detected_language

    except HttpResponseError as exception:
        print(f"Error Code: {exception.error}")
        print(f"Message: {exception.error.message}")

def azure_translate2(user_input, detected_language): #拼音化
    try:
        # 默認處理日文的拼音化
        language = "ja"
        from_script = "jpan"
        to_script = "Latn"

        if detected_language == "ja":
            language = "zh-Hant"
            from_script = "Hant"
            to_script = "Latn"
        
        input_text_elements = [user_input]

        response = text_translator.transliterate(
            body=input_text_elements,
            language=language,
            from_script=from_script,
            to_script=to_script,
        )
        transliteration = response[0] if response else None

        if transliteration:
            print(f"Input text was transliterated to '{transliteration.script}' script. Transliterated text: '{transliteration.text}'.")
            return transliteration.text
        
    except HttpResponseError as exception:
        if exception.error is not None:
            print(f"Error Code: {exception.error.code}")
            print(f"Message: {exception.error.message}")
        raise

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/azure_translate", methods=["POST"])
def call_llm():
    if request.method == "POST":
        print("POST!")
        data = request.form
        print(data)
        chinese_text = data["message"]
        print(chinese_text)
        translation_result, detected_language = azure_translate(chinese_text)
        print(translation_result)

        language = "zh-Hant"
        if detected_language == "zh-Hant":
                language = "ja"
                
        sentiments = ["default", "chat", "cheerful", "customerservice"]
        audio_files = {}
        
        # 為每種情感生成對應的語音文件
        for sentiment in sentiments:
            audio_file_name, audio_duration = web_azure_speech(translation_result, language, sentiment)
            print(f"生成語音檔案: {audio_file_name}, 時長: {audio_duration}ms")
            audio_files[sentiment] = {
                "file": audio_file_name,
                "duration": audio_duration
            }
        
    return jsonify({
        "japanese": translation_result,
        "audioFiles": audio_files
    })

if __name__ == "__main__":
    app.run()
