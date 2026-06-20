from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    verify_twilio_signature: bool = Field(default=False, alias="VERIFY_TWILIO_SIGNATURE")
    enable_twilio_lookup: bool = Field(default=False, alias="ENABLE_TWILIO_LOOKUP")
    enable_ai_triage: bool = Field(default=False, alias="ENABLE_AI_TRIAGE")
    enable_call_recording_automation: bool = Field(default=True, alias="ENABLE_CALL_RECORDING_AUTOMATION")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5-mini", alias="OPENAI_MODEL")
    assemblyai_api_key: str = Field(default="", alias="ASSEMBLYAI_API_KEY")
    assemblyai_poll_timeout_seconds: int = Field(default=600, alias="ASSEMBLYAI_POLL_TIMEOUT_SECONDS")
    assemblyai_poll_interval_seconds: int = Field(default=3, alias="ASSEMBLYAI_POLL_INTERVAL_SECONDS")
    admin_password: str = Field(default="", alias="ADMIN_PASSWORD")
    auth_session_secret: str = Field(default="", alias="AUTH_SESSION_SECRET")
    enable_admin_password_fallback: bool = Field(default=False, alias="ENABLE_ADMIN_PASSWORD_FALLBACK")
    app_base_url: str = Field(default="", alias="APP_BASE_URL")
    customer_action_token_secret: str = Field(default="", alias="CUSTOMER_ACTION_TOKEN_SECRET")

    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_messaging_service_sid: str = Field(default="", alias="TWILIO_MESSAGING_SERVICE_SID")
    whatsapp_template_proof_ready_content_sid: str = Field(default="", alias="WHATSAPP_TEMPLATE_PROOF_READY_CONTENT_SID")
    whatsapp_template_assets_needed_content_sid: str = Field(default="", alias="WHATSAPP_TEMPLATE_ASSETS_NEEDED_CONTENT_SID")
    whatsapp_template_new_customer_intro_content_sid: str = Field(default="", alias="WHATSAPP_TEMPLATE_NEW_CUSTOMER_INTRO_CONTENT_SID")
    whatsapp_template_quote_follow_up_content_sid: str = Field(default="", alias="WHATSAPP_TEMPLATE_QUOTE_FOLLOW_UP_CONTENT_SID")
    whatsapp_template_pickup_reminder_content_sid: str = Field(default="", alias="WHATSAPP_TEMPLATE_PICKUP_REMINDER_CONTENT_SID")
    whatsapp_template_payment_reminder_content_sid: str = Field(default="", alias="WHATSAPP_TEMPLATE_PAYMENT_REMINDER_CONTENT_SID")
    whatsapp_template_owner_message_content_sid: str = Field(
        default="",
        alias="WHATSAPP_TEMPLATE_OWNER_MESSAGE_CONTENT_SID",
    )
    twilio_studio_webhook_secret: str = Field(default="", alias="TWILIO_STUDIO_WEBHOOK_SECRET")
    maya_business_number: str = Field(default="", alias="MAYA_BUSINESS_NUMBER")
    francisco_phone: str = Field(default="", alias="FRANCISCO_PHONE")
    employee_phone_numbers: str = Field(default="", alias="EMPLOYEE_PHONE_NUMBERS")
    business_hours_text: str = Field(
        default="M-F: 9:00am - 5:30pm | SAT: By Appointment",
        alias="BUSINESS_HOURS_TEXT",
    )

    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_attachments_bucket: str = Field(default="attachments", alias="SUPABASE_ATTACHMENTS_BUCKET")

    operator_1_email: str = Field(default="", alias="OPERATOR_1_EMAIL")
    operator_1_password: str = Field(default="", alias="OPERATOR_1_PASSWORD")
    operator_1_name: str = Field(default="", alias="OPERATOR_1_NAME")
    operator_1_call_phone: str = Field(default="", alias="OPERATOR_1_CALL_PHONE")
    operator_1_routing_line: str = Field(default="", alias="OPERATOR_1_ROUTING_LINE")
    operator_1_supabase_user_id: str = Field(default="", alias="OPERATOR_1_SUPABASE_USER_ID")

    operator_2_email: str = Field(default="", alias="OPERATOR_2_EMAIL")
    operator_2_password: str = Field(default="", alias="OPERATOR_2_PASSWORD")
    operator_2_name: str = Field(default="", alias="OPERATOR_2_NAME")
    operator_2_call_phone: str = Field(default="", alias="OPERATOR_2_CALL_PHONE")
    operator_2_routing_line: str = Field(default="", alias="OPERATOR_2_ROUTING_LINE")
    operator_2_supabase_user_id: str = Field(default="", alias="OPERATOR_2_SUPABASE_USER_ID")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def francisco_phone_e164(self) -> str:
        return normalize_phone_number(self.francisco_phone)

    @property
    def maya_business_number_e164(self) -> str:
        return normalize_phone_number(self.maya_business_number)

    @property
    def employee_phones(self) -> frozenset[str]:
        phones = {
            normalize_phone_number(phone)
            for phone in self.employee_phone_numbers.split(",")
            if normalize_phone_number(phone)
        }
        if self.francisco_phone_e164:
            phones.add(self.francisco_phone_e164)
        return frozenset(phones)

    @property
    def auth_cookie_secret(self) -> str:
        return self.auth_session_secret or self.customer_action_token_secret or self.admin_password

    @property
    def supabase_auth_key(self) -> str:
        return self.supabase_anon_key

    @property
    def operator_seed_configs(self) -> tuple[dict[str, str], ...]:
        seeds: list[dict[str, str]] = []
        for prefix in ("operator_1", "operator_2"):
            email = getattr(self, f"{prefix}_email").strip().lower()
            if not email:
                continue
            seeds.append(
                {
                    "email": email,
                    "password": getattr(self, f"{prefix}_password"),
                    "display_name": getattr(self, f"{prefix}_name").strip() or email,
                    "click_to_call_phone": normalize_phone_number(getattr(self, f"{prefix}_call_phone")),
                    "routing_line": getattr(self, f"{prefix}_routing_line").strip() or "operator",
                    "supabase_user_id": getattr(self, f"{prefix}_supabase_user_id").strip(),
                }
            )
        return tuple(seeds)

    @property
    def operator_auth_configured(self) -> bool:
        return bool(self.operator_seed_configs or (self.supabase_url and self.supabase_anon_key and self.supabase_service_role_key))


def normalize_phone_number(phone_number: str) -> str:
    stripped = phone_number.strip()
    if not stripped:
        return ""

    digits = "".join(character for character in stripped if character.isdigit())
    if stripped.startswith("+") and digits:
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return stripped


@lru_cache
def get_settings() -> Settings:
    return Settings()
