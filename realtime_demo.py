import base64
import json
import logging
import os
import pyaudio
import sys
import wave
import websocket

from threading import Thread

from pynput.keyboard import Listener, Key

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
CHUNK = 1024
IS_RECORDING = False
SAMPLE_WIDTH = 0
LANGUAGE = 'Thai'

audio_frames_input = []
audio_frames_output = []
recording_idx = 0

url = 'wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17'
headers = [
    'Authorization: Bearer ' + OPENAI_API_KEY,
    'OpenAI-Beta: realtime=v1'
]

logger = logging.getLogger(__name__)
logging.basicConfig(filename='open_ai_realtime_demo.log', encoding='utf-8', level=logging.DEBUG)


audio_obj = pyaudio.PyAudio()


def start_voice_recording(audio):
    global IS_RECORDING
    global audio_frames_input
    global SAMPLE_WIDTH
    sys.stdout.flush()
    print('Listening, say something.')

    SAMPLE_WIDTH = audio.get_sample_size(FORMAT)
    stream = audio.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True)
    while IS_RECORDING:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_frames_input.append(data)
        except KeyboardInterrupt:
            break
    stream.stop_stream()
    stream.close()


def play_voice_response(audio):
    global audio_frames_output
    stream = audio.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=24000,
                        input=False,
                        output=True)
    audio_data = b''.join(audio_frames_output)
    for i in range(0, len(audio_data), CHUNK):
        stream.write(audio_data[i:i+CHUNK])
    stream.stop_stream()
    stream.close()
    audio_frames_output = []


def stop_and_save_voice_recording():
    sys.stdout.flush()
    print('Stopped listening, saving recording.')
    global recording_idx
    global audio_frames_input
    with wave.open(f'test_file_{recording_idx}.wave', 'wb') as wave_file:
        wave_file.setnchannels(CHANNELS)
        wave_file.setsampwidth(SAMPLE_WIDTH)
        wave_file.setframerate(RATE)
        wave_file.writeframes(b''.join(audio_frames_input))
    audio_frames_input = []
    recording_idx += 1


def stop_and_send_voice_recording_to_server(ws):
    sys.stdout.flush()
    print('Stopped listening, saving recording.')
    global audio_frames_input
    audio_bytes = b''.join(audio_frames_input)
    audio_base64_str = base64.b64encode(audio_bytes).decode('ascii')

    event = {
        'type': 'conversation.item.create',
        'item': {
            'type': 'message',
            'role': 'user',
            'content': [
                {
                    'type': 'input_audio',
                    'audio': audio_base64_str
                }
            ]
        }

    }
    ws.send(json.dumps(event))
    event = {
        'type': 'response.create',
        'response': {
            'instructions': f'Repeat user input in {LANGUAGE}. Attempt to literally translate user input. The exception is when the user \
            asks to switch language then the system should call the function to switch language.'
        }
    }
    ws.send(json.dumps(event))
    audio_frames_input = []


def on_open(ws):
    print('Connected to server.')
    event = {
        'type': 'session.update',
        'session': {
            'modalities': ['text', 'audio'],
            'instructions': f'You are a professional multi-language interpreter who will provide both oral and written translations from English to {LANGUAGE}.',
            'turn_detection': None,
            'tools': [{
                'type': 'function',
                'name': 'select_language',
                'description': 'Set the desired target language for the assistant.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'language': {
                            'type': 'string',
                            'description': 'The target language for the assistant to speak.',
                            'enum': [
                                'Thai',
                                'Mandarin',
                                'French',
                                'German',
                                'Spanish',
                                'Swedish',
                                'Italian',
                                'Japanese',
                                'Burmese',
                                'Lao'
                            ]
                        }
                    },
                    'required': ['language']
                }
            }
            ],
            'tool_choice': 'auto',
        }
    }
    ws.send(json.dumps(event))
    welcome_prompt = f"""
        Say exactly the following:
        Hello, I am your friendly interpreter,
        speak to me and I will reply back to you
        in your desired language.

        The target language for translation is {LANGUAGE}
        but you can ask me to change it any time  .
        """

    event = {
        'type': 'response.create',
        'response': {
            'input': [],
            'instructions': welcome_prompt
        }
    }
    ws.sent(json.dumps(event))



def select_language(input_language):
    LANGUAGE = input_language
    print(f'Switching language to {LANGUAGE}')


def on_message(ws, message):
    global audio_frames_output
    server_event = json.loads(message)
    if server_event['type'] == 'response.audio.delta':
        audio_bytes = base64.b64decode(server_event['delta'].encode('ascii'))
        audio_frames_output.append(audio_bytes)
    if server_event['type'] == 'response.audio.done':
        play_voice_response(audio_obj)
    if server_event['type'] == 'response.audio_transcript.done':
        print(f'Assistant: {server_event["transcript"]}')
    if server_event['type'] == 'response.done':
        if server_event['response']['output'][0]['type'] == 'function_call' and \
                server_event['response']['output'][0]['name'] == 'select_language':
            args = json.loads(server_event['response']['output'][0]['arguments'])
            select_language(args['language'])

    logger.info(f'Received event:\n{json.dumps(server_event, indent=2)}')


ws = websocket.WebSocketApp(
    url,
    header=headers,
    on_open=on_open,
    on_message=on_message)


def key_press(key):
    global IS_RECORDING
    if key == Key.space:
        if not IS_RECORDING:
            IS_RECORDING = True
            t1 = Thread(target=start_voice_recording, name='start_record_t', args=(audio_obj,))
            t1.start()
        else:
            IS_RECORDING = False
            stop_and_send_voice_recording_to_server(ws)


keyboard_listener = Listener(on_press=key_press)
keyboard_listener.start()
print('Press SPACE to start recording.')
ws.run_forever()
# audio_obj.terminate()
