# import tempfile
# import soundfile as sf

# from speechbrain.inference.speaker import SpeakerRecognition
# from speechbrain.utils.fetching import LocalStrategy

# SAMPLE_RATE = 16000
# THRESHOLD = 0.45

# verification = SpeakerRecognition.from_hparams(
#     source="speechbrain/spkrec-ecapa-voxceleb",
#     savedir="pretrained_models/spkrec-ecapa-voxceleb",
#     local_strategy=LocalStrategy.COPY
# )

# def is_correct_speaker(audio_bytes):
#     with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
#         sf.write(
#             tmp.name,
#             memoryview(audio_bytes).cast("h"),
#             SAMPLE_RATE,
#             subtype="PCM_16"
#         )

#         score, _ = verification.verify_files(
#             "referenz.wav",
#             tmp.name
#         )

#         return float(score) > THRESHOLD, float(score)