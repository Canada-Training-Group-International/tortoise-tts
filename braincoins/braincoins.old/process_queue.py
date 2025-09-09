import argparse
import os
import sys
from time import time

import torch
import torchaudio

from tortoise.api_fast import TextToSpeech, MODELS_DIR
from tortoise.utils.audio import load_audio, load_voices
from tortoise.utils.text import split_and_recombine_text

def tortoise_handler(voice, text, file_name):
    args = type('', (object, ), {
    'textfile': 'tortoise/data/riding_hood.txt',
    'text': text,
    'voice': voice,
    'output_path': 'results/longform/',
    'output_name': file_name,
    #'preset': 'fast',
    #'preset': 'standard',
    'preset': 'high_quality',
    'regenerate': None,
    'model_dir': MODELS_DIR,
    'seed': None,
    'use_deepspeed': False,
    'kv_cache': True,
    'half': True
    })
    print(args)
    print(args.text)
    print(args.model_dir)
    #return
    #parser = argparse.ArgumentParser()
    #parser.add_argument('--textfile', type=str, help='A file containing the text to read.', default="tortoise/data/riding_hood.txt")
    #parser.add_argument('--voice', type=str, help='Selects the voice to use for generation. See options in voices/ directory (and add your own!) '
    #                                             'Use the & character to join two voices together. Use a comma to perform inference on multiple voices.', default='lj')
    #parser.add_argument('--output_path', type=str, help='Where to store outputs.', default='results/longform/')
    #parser.add_argument('--output_name', type=str, help='How to name the output file', default='combined.wav')
    #parser.add_argument('--preset', type=str, help='Which voice preset to use.', default='standard')
    #parser.add_argument('--regenerate', type=str, help='Comma-separated list of clip numbers to re-generate, or nothing.', default=None)
    #parser.add_argument('--model_dir', type=str, help='Where to find pretrained model checkpoints. Tortoise automatically downloads these to .models, so this'
    #                                                  'should only be specified if you have custom checkpoints.', default=MODELS_DIR)
    #parser.add_argument('--seed', type=int, help='Random seed which can be used to reproduce results.', default=None)
    #parser.add_argument('--use_deepspeed', type=bool, help='Use deepspeed for speed bump.', default=False)
    #parser.add_argument('--kv_cache', type=bool, help='If you disable this please wait for a long a time to get the output', default=True)
    #parser.add_argument('--half', type=bool, help="float16(half) precision inference if True it's faster and take less vram and ram", default=True)


    #args = parser.parse_args()
    if torch.backends.mps.is_available():
        args.use_deepspeed = False
    tts = TextToSpeech(models_dir=args.model_dir, use_deepspeed=args.use_deepspeed, kv_cache=args.kv_cache, half=args.half)

    outpath = args.output_path
    outname = args.output_name
    selected_voices = args.voice.split(',')
    regenerate = args.regenerate
    if regenerate is not None:
        regenerate = [int(e) for e in regenerate.split(',')]

    # Process text
    #with open(args.textfile, 'r', encoding='utf-8') as f:
    #    text = ' '.join([l for l in f.readlines()])

    if '|' in text:
        print("Found the '|' character in your text, which I will use as a cue for where to split it up. If this was not"
              "your intent, please remove all '|' characters from the input.")
        texts = text.split('|')
    else:
        texts = split_and_recombine_text(text)

    seed = int(time()) if args.seed is None else args.seed
    output_files = []
    for selected_voice in selected_voices:
        voice_outpath = os.path.join(outpath, selected_voice)
        os.makedirs(voice_outpath, exist_ok=True)

        if '&' in selected_voice:
            voice_sel = selected_voice.split('&')
        else:
            voice_sel = [selected_voice]

        voice_samples, conditioning_latents = load_voices(voice_sel)
        all_parts = []
        for j, text in enumerate(texts):
            if regenerate is not None and j not in regenerate:
                all_parts.append(load_audio(os.path.join(voice_outpath, f'{j}.wav'), 24000))
                continue
            start_time = time()
            gen = tts.tts(text, voice_samples=voice_samples, use_deterministic_seed=seed)
            end_time = time()
            audio_ = gen.squeeze(0).cpu()
            print("Time taken to generate the audio: ", end_time - start_time, "seconds")
            print("RTF: ", (end_time - start_time) / (audio_.shape[1] / 24000))
            torchaudio.save(os.path.join(voice_outpath, f'{j}.wav'), audio_, 24000)
            all_parts.append(audio_)
        full_audio = torch.cat(all_parts, dim=-1)
        file_out_path = os.path.join(voice_outpath, f"{outname}")
        torchaudio.save(file_out_path, full_audio, 24000)
        output_files.append(file_out_path)
    return output_files



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Queue Client.')
    #parser.add_argument('message', nargs='?', default=None)
    #parser.add_argument('command', nargs='?', choices=['listen', 'send'], default='send',
    #                    help='Command: "listen" or "send" (default is "send")')
    #parser.add_argument('--listen', default=None, help='')
    #parser.add_argument('-l', '--listen', action='store_true', help='Listen for messages')
    #parser.add_argument('-p', '--process', action='store_true', help='Process pending tasks')

    parser.add_argument('-v', '--voice', help='voice to use')
    parser.add_argument('-o', '--output', help='file to output to')
    parser.add_argument('-t', '--text', help='text to convert to speech')
    
    args = parser.parse_args()
    print(args)

    if args.voice is None or args.output is None or args.text is None or args.voice == '' or args.output == '' or args.text == '':
        print('Missing arguments')
        sys.exit(1)

    output_file_name = args.output.split('.')[0] + '.wav'
    output_file_name = args.output+'.wav'
    output_files = tortoise_handler(args.voice, args.text, output_file_name)
    print(output_files)
    os.system("start " + output_files[0])
    #C:/thepathyouwant/file")




