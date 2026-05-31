import asyncio
import os
import sys
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Load .env file
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    with open(_env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

from openharness.config.settings import ImageGenerationConfig
from openharness.tools.image_generation_tool import ImageGenerationTool, ImageGenerationToolInput
from openharness.tools.base import ToolExecutionContext

async def run_test():
    tool = ImageGenerationTool()
    
    # Resolve config
    env_cfg = ImageGenerationConfig.from_env()
    print("Resolved Configuration:")
    print(f"  Model: {env_cfg.model}")
    print(f"  Base URL: {env_cfg.base_url}")
    print(f"  API Key: {env_cfg.api_key[:10]}...{env_cfg.api_key[-5:]}" if env_cfg.api_key else "  API Key: Not Found")
    
    # Prepare arguments
    args = ImageGenerationToolInput(
        prompt="A single glowing red candle on a rough dark stone floor, casting long dramatic shadows in a medieval dungeon, cinematic lighting, 8k, photorealistic",
        output_path="scratch/test_candle.png",
        overwrite=True
    )
    
    # Context with configuration metadata
    context = ToolExecutionContext(
        cwd=Path(__file__).parent.parent,
        metadata={
            "image_generation_config": {
                "provider": env_cfg.provider,
                "model": env_cfg.model,
                "api_key": env_cfg.api_key,
                "base_url": env_cfg.base_url,
            }
        }
    )
    
    print("\nStarting generation...")
    
    # Check if MLflow is enabled and run within its context
    mlflow_enabled = os.environ.get("GRAPHITI_MLFLOW_ENABLED", "1").lower() not in {"0", "false", "no"}
    if mlflow_enabled:
        try:
            import mlflow
            tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment("openharness")
            print(f"MLflow active: logged to experiment 'openharness' at tracking URI: {tracking_uri}")
            
            with mlflow.start_run(run_name="test_image_generation_kwai"):
                mlflow.log_param("prompt", args.prompt)
                mlflow.log_param("model", env_cfg.model)
                res = await tool.execute(args, context)
                print(f"Result Output:\n{res.output}")
                print(f"Result Metadata: {res.metadata}")
        except Exception as e:
            print(f"Running MLflow context failed: {e}. Executing without MLflow...")
            res = await tool.execute(args, context)
            print(f"Result Output:\n{res.output}")
    else:
        res = await tool.execute(args, context)
        print(f"Result Output:\n{res.output}")

if __name__ == "__main__":
    asyncio.run(run_test())
