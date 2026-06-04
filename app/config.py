from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    verify_twilio_signature: bool = Field(default=False, alias="VERIFY_TWILIO_SIGNATURE")
    enable_twilio_lookup: bool = Field(default=False, alias="ENABLE_TWILIO_LOOKUP")

    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_messaging_service_sid: str = Field(default="", alias="TWILIO_MESSAGING_SERVICE_SID")
    maya_business_number: str = Field(default="+13852208404", alias="MAYA_BUSINESS_NUMBER")
    francisco_phone: str = Field(default="", alias="FRANCISCO_PHONE")

    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_attachments_bucket: str = Field(default="attachments", alias="SUPABASE_ATTACHMENTS_BUCKET")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
