from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Sentinel Backend"
    version: str = "0.1.0"
    
    # WebSocket Configuration
    ws_host: str = "127.0.0.1"
    ws_port: int = 8000
    
    class Config:
        env_file = ".env"

settings = Settings()
