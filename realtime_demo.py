import json
import os
import pyaudio
import time
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

audio_frames = []
recording_idx = 0

url = 'wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17'
headers = [
    'Authorization: Bearer ' + OPENAI_API_KEY,
    'OpenAI-Beta: realtime=v1'
]

audio_obj = pyaudio.PyAudio()

def on_open(ws):
    print('Connected to server.')


def on_message(ws, message):
    data = json.loads(message)
    print('Received event:', json.dumps(data, indent=2))


def start_voice_recording(audio):
    global IS_RECORDING
    global audio_frames
    global SAMPLE_WIDTH

    print('Listening, say something.')
    
    SAMPLE_WIDTH = audio.get_sample_size(FORMAT)
    stream = audio.open(format=FORMAT, 
                        channels=CHANNELS, 
                        rate=RATE, 
                        input=True)
    while IS_RECORDING:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_frames.append(data)
        except KeyboardInterrupt:
            break
    stream.stop_stream()
    stream.close()



def stop_and_save_voice_recording():
    print('Stopped listening, saving recording.')
    global recording_idx
    global audio_frames
    with wave.open(f'test_file_{recording_idx}.wave', 'wb') as wave_file:
        wave_file.setnchannels(CHANNELS)
        wave_file.setsampwidth(SAMPLE_WIDTH)
        wave_file.setframerate(RATE)
        wave_file.writeframes(b''.join(audio_frames))
    audio_frames = []
    recording_idx += 1
    

def key_press(key):
    global IS_RECORDING
    if key == Key.space:
        if not IS_RECORDING:
            IS_RECORDING = True
            t1 = Thread(target=start_voice_recording, name='start_record_t', args=(audio_obj,))
            t1.start()
        else:
            IS_RECORDING = False
            stop_and_save_voice_recording()

ws = websocket.WebSocketApp(
    url,
    header=headers,
    on_open=on_open,
    on_message=on_message
)


keyboard_listener = Listener(on_press=key_press)
keyboard_listener.start()
print('Press SPACE to start recording.')
while True:
    time.sleep(3)
audio_obj.terminate()

# ws.run_forever()


