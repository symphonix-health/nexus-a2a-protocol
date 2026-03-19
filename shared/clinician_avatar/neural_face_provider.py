"""Neural Face Animation Provider — GPU-accelerated talking head generation.

Provides a ``NeuralFaceProvider`` that can drive realistic face animation via:

1. **Audio-to-blendshape prediction** (preferred, lower latency):
   - Uses ONNX Runtime with CUDA/DirectML GPU backend
   - Input: audio waveform (PCM 16kHz)
   - Output: per-frame ARKit blendshape weights (52 values × 30 fps)
   - The browser's GpuAvatarRenderer applies blendshapes in real-time

2. **Neural talking head generation** (highest quality, higher latency):
   - Integrates with SadTalker / Wav2Lip / similar models
   - Input: reference image + audio
   - Output: video frames streamed to the browser
   - Requires significant GPU VRAM (4-8 GB)

Environment variables:
    NEURAL_FACE_BACKEND     — 'blendshape' (default) or 'video'
    NEURAL_FACE_MODEL_PATH  — path to ONNX model file
    NEURAL_FACE_DEVICE      — 'cuda', 'directml', or 'cpu' (auto-detected)
    NEURAL_FACE_FPS         — blendshape output FPS (default 30)
    SADTALKER_PATH          — path to SadTalker installation (video mode)

Usage:
    provider = get_neural_face_provider()
    if provider.is_available():
        blendshapes = await provider.audio_to_blendshapes(pcm_bytes, sample_rate=24000)
        # blendshapes: list of dicts, one per frame at 30fps
        # each dict: {"jawOpen": 0.3, "mouthSmileLeft": 0.1, ...}

This module is designed to be imported but gracefully no-ops when GPU
libraries are not installed.  All imports are lazy.
"""

from __future__ import annotations

import asyncio
import logging
import os
import struct
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── ARKit blendshape names (52 shapes) ─────────────────────────────────
ARKIT_BLENDSHAPES = [
    "eyeBlinkLeft", "eyeBlinkRight", "eyeWideLeft", "eyeWideRight",
    "eyeLookUpLeft", "eyeLookUpRight", "eyeLookDownLeft", "eyeLookDownRight",
    "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight",
    "browDownLeft", "browDownRight", "browInnerUp",
    "browOuterUpLeft", "browOuterUpRight",
    "jawOpen", "jawForward", "jawLeft", "jawRight",
    "mouthClose", "mouthFunnel", "mouthPucker",
    "mouthLeft", "mouthRight",
    "mouthSmileLeft", "mouthSmileRight",
    "mouthFrownLeft", "mouthFrownRight",
    "mouthDimpleLeft", "mouthDimpleRight",
    "mouthStretchLeft", "mouthStretchRight",
    "mouthRollLower", "mouthRollUpper",
    "mouthShrugLower", "mouthShrugUpper",
    "mouthPressLeft", "mouthPressRight",
    "mouthLowerDownLeft", "mouthLowerDownRight",
    "mouthUpperUpLeft", "mouthUpperUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "noseSneerLeft", "noseSneerRight",
    "tongueOut",
]


def _detect_device() -> str:
    """Auto-detect the best available compute device."""
    device_env = os.getenv("NEURAL_FACE_DEVICE", "").strip().lower()
    if device_env in ("cuda", "directml", "cpu"):
        return device_env

    # Try CUDA first (NVIDIA GPU)
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if "CUDAExecutionProvider" in providers:
            return "cuda"
        if "DmlExecutionProvider" in providers:
            return "directml"
    except ImportError:
        pass

    return "cpu"


def _get_ort_providers(device: str) -> list[str]:
    """Map device name to ONNX Runtime execution providers."""
    if device == "cuda":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if device == "directml":
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


class NeuralFaceProvider(ABC):
    """Base class for neural face animation providers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider has all prerequisites (model, GPU, libs)."""

    @abstractmethod
    async def audio_to_blendshapes(
        self,
        audio_pcm: bytes,
        sample_rate: int = 24000,
    ) -> list[dict[str, float]]:
        """Convert audio to per-frame blendshape weights.

        Args:
            audio_pcm: Raw PCM audio bytes (16-bit signed, little-endian, mono)
            sample_rate: Audio sample rate in Hz

        Returns:
            List of blendshape dicts, one per frame at configured FPS.
            Each dict maps ARKit blendshape names to weights [0..1].
        """

    @abstractmethod
    async def generate_video(
        self,
        audio_pcm: bytes,
        reference_image_path: str,
        sample_rate: int = 24000,
    ) -> bytes | None:
        """Generate a talking head video from audio + reference image.

        Args:
            audio_pcm: Raw PCM audio
            reference_image_path: Path to the reference face image
            sample_rate: Audio sample rate

        Returns:
            MP4 video bytes, or None if generation fails.
        """


class OnnxBlendshapeProvider(NeuralFaceProvider):
    """ONNX Runtime-based audio-to-blendshape prediction.

    This provider loads an ONNX model that takes audio features as input
    and outputs per-frame ARKit blendshape weights.  The model should
    accept mel-spectrogram features and output (N_frames, 52) blendshape weights.

    When no trained model is available, falls back to a rule-based audio
    analysis that extracts blendshape weights from spectral features.
    """

    def __init__(self) -> None:
        self._device = _detect_device()
        self._model_path = os.getenv("NEURAL_FACE_MODEL_PATH", "")
        self._fps = int(os.getenv("NEURAL_FACE_FPS", "30"))
        self._session = None
        self._ort_available = False

        try:
            import onnxruntime  # noqa: F401
            self._ort_available = True
        except ImportError:
            pass

    def is_available(self) -> bool:
        """Available if ONNX Runtime is installed (with or without model)."""
        return self._ort_available or True  # always available via rule-based fallback

    def _load_model(self) -> bool:
        """Load ONNX model if available."""
        if self._session is not None:
            return True
        if not self._model_path or not Path(self._model_path).is_file():
            return False
        try:
            import onnxruntime as ort
            providers = _get_ort_providers(self._device)
            self._session = ort.InferenceSession(
                self._model_path,
                providers=providers,
            )
            logger.info(
                "Loaded neural face model from %s on %s",
                self._model_path, self._device,
            )
            return True
        except Exception as exc:
            logger.warning("Failed to load neural face model: %s", exc)
            return False

    async def audio_to_blendshapes(
        self,
        audio_pcm: bytes,
        sample_rate: int = 24000,
    ) -> list[dict[str, float]]:
        """Convert audio to per-frame blendshape weights.

        If an ONNX model is loaded, runs neural inference.
        Otherwise, uses rule-based spectral analysis.
        """
        if self._load_model() and self._session is not None:
            return await self._neural_inference(audio_pcm, sample_rate)
        return await self._rule_based_analysis(audio_pcm, sample_rate)

    async def _neural_inference(
        self,
        audio_pcm: bytes,
        sample_rate: int,
    ) -> list[dict[str, float]]:
        """Run ONNX model inference in a thread pool."""
        import numpy as np

        def _run():
            # Decode PCM to float32
            n_samples = len(audio_pcm) // 2
            samples = np.array(
                struct.unpack(f"<{n_samples}h", audio_pcm[:n_samples * 2]),
                dtype=np.float32,
            ) / 32768.0

            # Compute mel spectrogram (simple approximation)
            # Real implementation would use librosa or torchaudio
            hop_length = sample_rate // self._fps
            n_frames = max(1, n_samples // hop_length)

            # Reshape audio into frames
            frames = []
            for i in range(n_frames):
                start = i * hop_length
                end = min(start + hop_length, n_samples)
                frame = samples[start:end]
                if len(frame) < hop_length:
                    frame = np.pad(frame, (0, hop_length - len(frame)))
                # Simple spectral features: FFT magnitude
                spectrum = np.abs(np.fft.rfft(frame * np.hanning(len(frame))))
                # Reduce to mel-scale approximation (40 bins)
                mel_bins = 40
                bin_edges = np.linspace(0, len(spectrum), mel_bins + 1, dtype=int)
                mel = np.zeros(mel_bins, dtype=np.float32)
                for j in range(mel_bins):
                    mel[j] = np.mean(spectrum[bin_edges[j]:bin_edges[j + 1]] + 1e-8)
                frames.append(mel)

            mel_input = np.stack(frames).reshape(1, n_frames, mel_bins).astype(np.float32)

            # Run inference
            input_name = self._session.get_inputs()[0].name
            outputs = self._session.run(None, {input_name: mel_input})

            # Output shape: (1, N_frames, 52)
            weights = outputs[0][0]  # (N_frames, 52)

            results = []
            for frame_weights in weights:
                bs = {}
                for idx, name in enumerate(ARKIT_BLENDSHAPES):
                    if idx < len(frame_weights):
                        bs[name] = float(np.clip(frame_weights[idx], 0, 1))
                results.append(bs)
            return results

        return await asyncio.get_event_loop().run_in_executor(None, _run)

    async def _rule_based_analysis(
        self,
        audio_pcm: bytes,
        sample_rate: int,
    ) -> list[dict[str, float]]:
        """Extract blendshape weights from audio using spectral analysis.

        This is the fallback when no trained ONNX model is available.
        Uses frequency-band energy analysis similar to the browser's
        RealtimeClient spectral lip sync, but produces full 52-blendshape
        output for the 3D renderer.
        """
        import math

        def _run():
            n_samples = len(audio_pcm) // 2
            if n_samples == 0:
                return [_zero_blendshapes()]

            # Decode PCM
            samples = list(
                struct.unpack(f"<{n_samples}h", audio_pcm[:n_samples * 2])
            )

            hop_length = sample_rate // self._fps
            n_frames = max(1, n_samples // hop_length)

            results = []
            for i in range(n_frames):
                start = i * hop_length
                end = min(start + hop_length, n_samples)
                frame = samples[start:end]
                if not frame:
                    results.append(_zero_blendshapes())
                    continue

                # RMS energy
                rms = math.sqrt(sum(s * s for s in frame) / len(frame)) / 32768.0

                # Simple spectral bands (via DFT approximation)
                # Low: 80-400 Hz, Mid: 400-2200 Hz, High: 2200-6500 Hz
                n = len(frame)
                low_e = 0.0
                mid_e = 0.0
                high_e = 0.0

                # Compute DFT energy in bands
                for k_band, (lo_hz, hi_hz) in enumerate([
                    (80, 400), (400, 2200), (2200, 6500)
                ]):
                    lo_bin = max(1, int(lo_hz * n / sample_rate))
                    hi_bin = min(n // 2, int(hi_hz * n / sample_rate))
                    band_e = 0.0
                    count = 0
                    for k in range(lo_bin, hi_bin + 1):
                        # Goertzel-like magnitude estimation (simplified)
                        re_sum = sum(
                            frame[j] * math.cos(2 * math.pi * k * j / n)
                            for j in range(min(n, 256))  # limit for perf
                        )
                        im_sum = sum(
                            frame[j] * math.sin(2 * math.pi * k * j / n)
                            for j in range(min(n, 256))
                        )
                        mag = math.sqrt(re_sum * re_sum + im_sum * im_sum) / (32768.0 * n)
                        band_e += mag
                        count += 1
                    avg = band_e / max(1, count)
                    if k_band == 0:
                        low_e = avg
                    elif k_band == 1:
                        mid_e = avg
                    else:
                        high_e = avg

                total_e = (low_e + mid_e + high_e) / 3

                # Map spectral features to blendshapes
                bs = _zero_blendshapes()

                # Jaw openness from total energy
                jaw = min(1.0, total_e * 50)
                bs["jawOpen"] = jaw

                # Mouth width from high-freq energy (sibilants → spread)
                freq_sum = mid_e + high_e + 1e-8
                hi_ratio = high_e / freq_sum
                bs["mouthStretchLeft"] = min(1.0, hi_ratio * 0.6)
                bs["mouthStretchRight"] = min(1.0, hi_ratio * 0.6)

                # Lip pucker from low-freq dominance
                lo_ratio = low_e / (total_e + 1e-8)
                if lo_ratio > 0.55 and high_e < low_e * 0.4:
                    pucker = min(1.0, (lo_ratio - 0.4) * 2.5)
                    bs["mouthPucker"] = pucker
                    bs["mouthFunnel"] = pucker * 0.5

                # Smile from expression (warm during speech)
                smile = min(0.3, rms * 3)
                bs["mouthSmileLeft"] = smile
                bs["mouthSmileRight"] = smile

                # Upper lip raise
                bs["mouthUpperUpLeft"] = min(0.4, jaw * 0.3)
                bs["mouthUpperUpRight"] = min(0.4, jaw * 0.3)

                # Lower lip
                bs["mouthLowerDownLeft"] = min(0.5, jaw * 0.4)
                bs["mouthLowerDownRight"] = min(0.5, jaw * 0.4)

                # Cheek squint (subtle, correlated with smile)
                bs["cheekSquintLeft"] = smile * 0.4
                bs["cheekSquintRight"] = smile * 0.4

                # Brow movement (subtle emphasis)
                if rms > 0.02:
                    bs["browInnerUp"] = min(0.2, rms * 4)

                results.append(bs)

            return results

        return await asyncio.get_event_loop().run_in_executor(None, _run)

    async def generate_video(
        self,
        audio_pcm: bytes,
        reference_image_path: str,
        sample_rate: int = 24000,
    ) -> bytes | None:
        """Not supported by blendshape provider."""
        return None


class SadTalkerProvider(NeuralFaceProvider):
    """SadTalker-based neural talking head video generation.

    Requires:
    - SadTalker installed (SADTALKER_PATH env var)
    - NVIDIA GPU with CUDA support
    - torch, torchvision, torchaudio

    This provider generates high-quality talking head videos by:
    1. Extracting 3DMM coefficients from audio
    2. Generating facial motion from audio features
    3. Rendering video frames with face reenactment

    The output is streamed as MP4 video frames to the browser.
    """

    def __init__(self) -> None:
        self._sadtalker_path = os.getenv("SADTALKER_PATH", "")
        self._device = _detect_device()

    def is_available(self) -> bool:
        if not self._sadtalker_path or not Path(self._sadtalker_path).is_dir():
            return False
        try:
            import torch  # noqa: F401
            return torch.cuda.is_available()
        except ImportError:
            return False

    async def audio_to_blendshapes(
        self,
        audio_pcm: bytes,
        sample_rate: int = 24000,
    ) -> list[dict[str, float]]:
        """SadTalker produces video, not blendshapes. Returns empty."""
        return []

    async def generate_video(
        self,
        audio_pcm: bytes,
        reference_image_path: str,
        sample_rate: int = 24000,
    ) -> bytes | None:
        """Generate talking head video using SadTalker.

        This runs the full SadTalker pipeline:
        1. Save audio to temp WAV
        2. Run SadTalker inference
        3. Return output MP4 bytes
        """
        import tempfile
        import wave

        if not self.is_available():
            return None

        # Save audio to temp WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
            wav_path = wav_file.name
            wf = wave.open(wav_file, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_pcm)
            wf.close()

        output_path = wav_path.replace(".wav", "_output.mp4")

        try:
            proc = await asyncio.create_subprocess_exec(
                "python",
                os.path.join(self._sadtalker_path, "inference.py"),
                "--driven_audio", wav_path,
                "--source_image", reference_image_path,
                "--result_dir", os.path.dirname(output_path),
                "--enhancer", "gfpgan",
                "--still",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._sadtalker_path,
            )
            await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                logger.error("SadTalker inference failed with code %d", proc.returncode)
                return None

            if os.path.isfile(output_path):
                with open(output_path, "rb") as f:
                    return f.read()
            return None
        except Exception as exc:
            logger.error("SadTalker generation failed: %s", exc)
            return None
        finally:
            # Cleanup temp files
            for p in [wav_path, output_path]:
                try:
                    os.unlink(p)
                except OSError:
                    pass


class Wav2LipProvider(NeuralFaceProvider):
    """Wav2Lip-based lip sync overlay provider.

    Wav2Lip produces highly accurate lip movements on existing video/images.
    It requires less GPU memory than SadTalker but produces less head motion.

    Requires:
    - Wav2Lip installed (WAV2LIP_PATH env var)
    - NVIDIA GPU with CUDA support
    - Wav2Lip checkpoint (wav2lip_gan.pth)
    """

    def __init__(self) -> None:
        self._wav2lip_path = os.getenv("WAV2LIP_PATH", "")
        self._checkpoint = os.getenv(
            "WAV2LIP_CHECKPOINT",
            os.path.join(self._wav2lip_path, "checkpoints", "wav2lip_gan.pth")
            if self._wav2lip_path else "",
        )
        self._device = _detect_device()

    def is_available(self) -> bool:
        if not self._wav2lip_path or not Path(self._wav2lip_path).is_dir():
            return False
        if not self._checkpoint or not Path(self._checkpoint).is_file():
            return False
        try:
            import torch  # noqa: F401
            return torch.cuda.is_available()
        except ImportError:
            return False

    async def audio_to_blendshapes(
        self,
        audio_pcm: bytes,
        sample_rate: int = 24000,
    ) -> list[dict[str, float]]:
        """Wav2Lip produces video, not blendshapes."""
        return []

    async def generate_video(
        self,
        audio_pcm: bytes,
        reference_image_path: str,
        sample_rate: int = 24000,
    ) -> bytes | None:
        """Generate lip-synced video using Wav2Lip."""
        import tempfile
        import wave

        if not self.is_available():
            return None

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
            wav_path = wav_file.name
            wf = wave.open(wav_file, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_pcm)
            wf.close()

        output_path = wav_path.replace(".wav", "_wav2lip.mp4")

        try:
            proc = await asyncio.create_subprocess_exec(
                "python",
                os.path.join(self._wav2lip_path, "inference.py"),
                "--checkpoint_path", self._checkpoint,
                "--face", reference_image_path,
                "--audio", wav_path,
                "--outfile", output_path,
                "--nosmooth",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._wav2lip_path,
            )
            await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                return None

            if os.path.isfile(output_path):
                with open(output_path, "rb") as f:
                    return f.read()
            return None
        except Exception as exc:
            logger.error("Wav2Lip generation failed: %s", exc)
            return None
        finally:
            for p in [wav_path, output_path]:
                try:
                    os.unlink(p)
                except OSError:
                    pass


def _zero_blendshapes() -> dict[str, float]:
    """Return a blendshape dict with all weights at zero."""
    return {name: 0.0 for name in ARKIT_BLENDSHAPES}


def get_neural_face_provider() -> NeuralFaceProvider:
    """Factory: return the best available neural face provider.

    Priority:
    1. SadTalker (if installed + GPU) — highest quality video output
    2. Wav2Lip (if installed + GPU) — accurate lip sync overlay
    3. OnnxBlendshapeProvider — always available (rule-based fallback)
    """
    backend = os.getenv("NEURAL_FACE_BACKEND", "blendshape").strip().lower()

    if backend == "sadtalker":
        provider = SadTalkerProvider()
        if provider.is_available():
            logger.info("Using SadTalker neural face provider (GPU)")
            return provider
        logger.warning("SadTalker requested but not available, falling back")

    if backend == "wav2lip":
        provider = Wav2LipProvider()
        if provider.is_available():
            logger.info("Using Wav2Lip neural face provider (GPU)")
            return provider
        logger.warning("Wav2Lip requested but not available, falling back")

    if backend == "video":
        # Auto-select best video provider
        for cls in [SadTalkerProvider, Wav2LipProvider]:
            provider = cls()
            if provider.is_available():
                logger.info("Using %s neural face provider (GPU)", cls.__name__)
                return provider

    # Default: ONNX blendshape (always available with rule-based fallback)
    provider = OnnxBlendshapeProvider()
    device = _detect_device()
    logger.info("Using ONNX blendshape provider (device=%s)", device)
    return provider
