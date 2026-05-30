import logging
import os
import platform
import shutil
import subprocess
import sys

from ollama import Client
from pydantic import BaseModel
from typing import Optional, Type

logger = logging.getLogger(__name__)


class OllamaModelSetup:
    def __init__(self, model_name: str, host: Optional[str] = None):
        logger.info("Initializing Ollama model setup for '%s'", model_name)
        self.model_name = model_name
        self.host = host
        self.client = Client(host=host) if host else Client()
        if host:
            logger.info("Using remote Ollama server at %s (skipping local install/pull/device probe)", host)
            self.device_info = f"Remote ({host})"
        else:
            self._install_ollama()
            self._pull_model(self.model_name)
            self.device_info = self.check_device_usage()
        logger.info("Ollama device usage: %s", self.device_info)
    
    def _install_ollama(self):
        """Detect OS and install Ollama if not already installed."""
        if shutil.which("ollama"):
            logger.info("Ollama is already installed")
            return
        system = platform.system().lower()
        logger.info("Detected operating system: %s", system)
        if system == "darwin":  # macOS
            logger.info("Installing Ollama for macOS")
            subprocess.run(["/bin/bash", "-c", "$(curl -fsSL https://ollama.com/install.sh)"], check=True)
        elif system == "linux":
            logger.info("Installing Ollama for Linux")
            subprocess.run(["curl", "-fsSL", "https://ollama.com/install.sh", "|", "sh"], shell=True, check=True)
        elif system == "windows":
            ollama_url = "https://ollama.com/download/windows"
            logger.error("Windows installation is manual. Download from %s", ollama_url)
            sys.exit(1)
        else:
            logger.error("Unsupported operating system: %s", system)
            raise OSError("Unsupported operating system.")

    def _pull_model(self, model_name: str) -> None:
        """Pull the specified model."""
        logger.info("Ensuring Ollama model '%s' is available", model_name)
        result = subprocess.run(["ollama", "pull", model_name], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("Model '%s' downloaded successfully", model_name)
        else:
            logger.error("Failed to download model '%s': %s", model_name, result.stderr.strip())
            sys.exit(1)

    def check_device_usage(self) -> str:
        """
        Check if Ollama is using CPU or GPU for inference.
        
        Returns:
            str: Device usage information (e.g., "GPU (CUDA)", "GPU (Metal)", "CPU", "Unknown")
        """
        system = platform.system().lower()
        device_info = "Unknown"
        
        # Method 1: Check ollama ps for running models
        try:
            result = subprocess.run(
                ["ollama", "ps"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout:
                # Check if output mentions GPU/CUDA/Metal
                output_lower = result.stdout.lower()
                if "cuda" in output_lower or "nvidia" in output_lower:
                    device_info = "GPU (CUDA)"
                elif "metal" in output_lower:
                    device_info = "GPU (Metal)"
                elif "cpu" in output_lower and "100%" in result.stdout:
                    device_info = "CPU"
        except Exception as e:
            logger.debug("Could not check ollama ps: %s", e)
        
        # Method 2: Check for GPU availability based on OS
        if device_info == "Unknown":
            if system == "linux":
                # Check for NVIDIA GPU
                try:
                    result = subprocess.run(
                        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                        capture_output=True,
                        text=True,
                        timeout=3
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        gpu_name = result.stdout.strip().split("\n")[0]
                        logger.info("Detected NVIDIA GPU: %s", gpu_name)
                        device_info = "GPU (CUDA) - Available"
                except Exception:
                    pass
                
                # Check for AMD GPU (ROCm)
                try:
                    result = subprocess.run(
                        ["rocm-smi", "--showid"],
                        capture_output=True,
                        text=True,
                        timeout=3
                    )
                    if result.returncode == 0:
                        logger.info("Detected AMD GPU (ROCm)")
                        device_info = "GPU (ROCm) - Available"
                except Exception:
                    pass
                    
            elif system == "darwin":  # macOS
                # Check for Metal support (Apple Silicon or AMD GPUs)
                try:
                    result = subprocess.run(
                        ["system_profiler", "SPDisplaysDataType"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        output = result.stdout.lower()
                        if "apple" in output or "metal" in output or "m1" in output or "m2" in output or "m3" in output:
                            device_info = "GPU (Metal) - Available"
                        else:
                            device_info = "CPU - No Metal GPU detected"
                except Exception:
                    pass
                    
            elif system == "windows":
                # On Windows, GPU is typically available if CUDA drivers are installed
                # We can't easily detect without additional tools
                device_info = "GPU (CUDA) - Likely available (check Task Manager)"
        
        # Method 3: Check Ollama environment variables
        if device_info == "Unknown":
            # Check OLLAMA_NUM_GPU or other environment hints
            if "OLLAMA_NUM_GPU" in os.environ:
                num_gpu = os.environ.get("OLLAMA_NUM_GPU", "0")
                if num_gpu and num_gpu != "0":
                    device_info = f"GPU - {num_gpu} GPU(s) configured"
                else:
                    device_info = "CPU - No GPU configured"
        
        # Final fallback
        if device_info == "Unknown":
            device_info = "CPU - Unable to detect GPU (likely using CPU)"
        
        return device_info

    def get_device_info(self) -> str:
        """
        Get the current device usage information.
        
        Returns:
            str: Device usage information (e.g., "GPU (CUDA)", "GPU (Metal)", "CPU")
        """
        if hasattr(self, 'device_info'):
            return self.device_info
        # If not cached, check again
        self.device_info = self.check_device_usage()
        return self.device_info

    def inference(
        self,
        text: Optional[str] = None,
        prompt: Optional[str] = None,
        schema: Optional[Type[BaseModel]] = None,
    ) -> Optional[BaseModel]:
        """
        Run schema-constrained inference and return the validated result.

        Args:
            text: The input text to classify.
            prompt: The system prompt instructing the model.
            schema: The Pydantic model the response is constrained to and validated against.

        Returns:
            An instance of `schema` populated from the model's response.
        """
        if not text or not prompt or not schema:
            raise ValueError("text, prompt, and schema are all required.")
        logger.debug("Running inference with model '%s'", self.model_name)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ]
        response = self.client.chat(
            model=self.model_name,
            messages=messages,
            format=schema.model_json_schema(),
            options={
                "num_predict": 256,
                "num_ctx": 2048,
                "num_gpu": 999,
            },
            keep_alive="30m",
            think=False,
        )
        return schema.model_validate_json(response.message.content)

if __name__ == "__main__":
    # Configure logging when running directly
    from src.config.settings import OLLAMA_HOST, configure_logging
    configure_logging()

    class Capital(BaseModel):
        capital: str

    ollama_model_setup = OllamaModelSetup(model_name="gemma4:e4b", host=OLLAMA_HOST)
    print(
        ollama_model_setup.inference(
            text="What is the capital of France?",
            prompt="Answer with the capital city as JSON: {\"capital\": \"<city>\"}",
            schema=Capital,
        )
    )