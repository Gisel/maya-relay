from __future__ import annotations

import hmac
import logging
from typing import Any, Protocol

from fastapi import HTTPException
from gotrue.errors import AuthApiError
from supabase import Client, create_client

from app.auth import OperatorProfile
from app.config import Settings, normalize_phone_number


logger = logging.getLogger(__name__)


class OperatorAuthService(Protocol):
    def authenticate(self, *, email: str, password: str) -> OperatorProfile:
        ...

    def request_password_reset(self, *, email: str, redirect_to: str) -> None:
        ...

    def update_password(
        self,
        *,
        password: str,
        access_token: str | None = None,
        refresh_token: str | None = None,
        code: str | None = None,
        redirect_to: str | None = None,
    ) -> None:
        ...


class MayaOperatorAuthService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._auth_client: Client | None = None
        self._service_client: Client | None = None

    def authenticate(self, *, email: str, password: str) -> OperatorProfile:
        normalized_email = email.strip().lower()
        if not normalized_email or not password:
            raise HTTPException(status_code=401)

        if self._supabase_configured:
            return self._authenticate_with_supabase(normalized_email, password)

        if self.settings.supabase_url and self.settings.supabase_service_role_key and not self.settings.supabase_anon_key:
            raise HTTPException(status_code=503, detail="SUPABASE_ANON_KEY is required for operator login.")

        return self._authenticate_with_seed(normalized_email, password)

    def request_password_reset(self, *, email: str, redirect_to: str) -> None:
        normalized_email = email.strip().lower()
        if not normalized_email:
            return
        if not self._supabase_configured:
            raise HTTPException(status_code=503, detail="Supabase Auth is not configured correctly.")
        try:
            self.auth_client.auth.reset_password_for_email(normalized_email, {"redirect_to": redirect_to})
        except AuthApiError as error:
            error_message = str(error).lower()
            if "invalid api key" in error_message:
                raise HTTPException(status_code=503, detail="Supabase Auth is not configured correctly.") from error
            if "rate limit" in error_message:
                raise HTTPException(
                    status_code=429,
                    detail="Password reset email was requested too recently. Please wait a few minutes before trying again.",
                ) from error
            logger.warning("Supabase password reset request failed for %s: %s", normalized_email, error)
            raise HTTPException(status_code=503, detail="Password reset email could not be sent.") from error
        except Exception as error:
            if "rate limit" in str(error).lower():
                raise HTTPException(
                    status_code=429,
                    detail="Password reset email was requested too recently. Please wait a few minutes before trying again.",
                ) from error
            logger.warning("Supabase password reset request failed for %s: %s", normalized_email, error)
            raise HTTPException(status_code=503, detail="Password reset email could not be sent.") from error

    def update_password(
        self,
        *,
        password: str,
        access_token: str | None = None,
        refresh_token: str | None = None,
        code: str | None = None,
        redirect_to: str | None = None,
    ) -> None:
        clean_password = password.strip()
        if len(clean_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
        if not self._supabase_configured:
            raise HTTPException(status_code=503, detail="Supabase Auth is not configured correctly.")
        try:
            if access_token and refresh_token:
                self.auth_client.auth.set_session(access_token, refresh_token)
            elif code:
                self.auth_client.auth.exchange_code_for_session(
                    {"auth_code": code, "redirect_to": redirect_to or ""}
                )
            else:
                raise HTTPException(status_code=400, detail="Password reset link is missing recovery tokens.")
            self.auth_client.auth.update_user({"password": clean_password})
        except HTTPException:
            raise
        except AuthApiError as error:
            logger.warning("Supabase password update failed: %s", error)
            raise HTTPException(status_code=400, detail="Password reset link is invalid or expired.") from error
        except Exception as error:
            logger.warning("Supabase password update failed: %s", error)
            raise HTTPException(status_code=400, detail="Password reset link is invalid or expired.") from error

    @property
    def _supabase_configured(self) -> bool:
        return bool(self.settings.supabase_url and self.settings.supabase_anon_key and self.settings.supabase_service_role_key)

    @property
    def auth_client(self) -> Client:
        if self._auth_client is None:
            self._auth_client = create_client(self.settings.supabase_url, self.settings.supabase_auth_key)
        return self._auth_client

    @property
    def service_client(self) -> Client:
        if self._service_client is None:
            self._service_client = create_client(self.settings.supabase_url, self.settings.supabase_service_role_key)
        return self._service_client

    def _authenticate_with_supabase(self, email: str, password: str) -> OperatorProfile:
        try:
            auth_response = self.auth_client.auth.sign_in_with_password({"email": email, "password": password})
        except AuthApiError as error:
            if "invalid api key" in str(error).lower():
                logger.error("Supabase anon key is missing or invalid for operator auth.")
                raise HTTPException(status_code=503, detail="Supabase Auth is not configured correctly.") from error
            logger.warning("Supabase operator auth failed for %s: %s", email, error)
            raise HTTPException(status_code=401) from error
        except Exception as error:
            logger.warning("Supabase operator auth failed for %s: %s", email, error)
            raise HTTPException(status_code=503, detail="Supabase Auth is unavailable.") from error

        user = getattr(auth_response, "user", None)
        user_id = str(getattr(user, "id", "") or "")
        user_email = str(getattr(user, "email", "") or email).strip().lower()
        if not user_id or user_email != email:
            raise HTTPException(status_code=401)

        profile = self._get_profile(supabase_user_id=user_id, email=email)
        if profile is not None:
            if profile.supabase_user_id is None:
                profile = self._link_profile_to_supabase_user(profile_id=profile.id, supabase_user_id=user_id)
            if not profile.active:
                raise HTTPException(status_code=403, detail="Operator is inactive.")
            return profile

        seed = self._seed_for_email(email)
        if seed is None:
            raise HTTPException(status_code=403, detail="Operator profile is not configured.")

        profile = self._sync_seed_profile(seed, supabase_user_id=user_id)
        if not profile.active:
            raise HTTPException(status_code=403, detail="Operator is inactive.")
        return profile

    def _authenticate_with_seed(self, email: str, password: str) -> OperatorProfile:
        seed = self._seed_for_email(email)
        if seed is None or not seed.get("password") or not hmac.compare_digest(password, seed["password"]):
            raise HTTPException(status_code=401)
        return OperatorProfile(
            id=seed.get("supabase_user_id") or f"local:{email}",
            email=email,
            display_name=seed["display_name"],
            role="operator",
            routing_line=seed["routing_line"],
            click_to_call_phone=seed["click_to_call_phone"],
            active=True,
            supabase_user_id=seed.get("supabase_user_id") or None,
        )

    def _seed_for_email(self, email: str) -> dict[str, str] | None:
        for seed in self.settings.operator_seed_configs:
            if seed["email"] == email:
                return seed
        return None

    def _get_profile(self, *, supabase_user_id: str, email: str) -> OperatorProfile | None:
        response = (
            self.service_client.table("operator_profiles")
            .select("id, supabase_user_id, email, display_name, role, routing_line, click_to_call_phone, active")
            .or_(f"supabase_user_id.eq.{supabase_user_id},email.eq.{email}")
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None
        return _profile_from_row(rows[0])

    def _sync_seed_profile(self, seed: dict[str, str], *, supabase_user_id: str) -> OperatorProfile:
        row = {
            "supabase_user_id": supabase_user_id,
            "email": seed["email"],
            "display_name": seed["display_name"],
            "role": "operator",
            "routing_line": seed["routing_line"],
            "click_to_call_phone": seed["click_to_call_phone"],
            "active": True,
        }
        response = (
            self.service_client.table("operator_profiles")
            .upsert(row, on_conflict="email")
            .execute()
        )
        rows = response.data or []
        if not rows:
            profile = self._get_profile(supabase_user_id=supabase_user_id, email=seed["email"])
            if profile is None:
                raise HTTPException(status_code=503, detail="Operator profile could not be synced.")
            return profile
        return _profile_from_row(rows[0])

    def _link_profile_to_supabase_user(self, *, profile_id: str, supabase_user_id: str) -> OperatorProfile:
        response = (
            self.service_client.table("operator_profiles")
            .update({"supabase_user_id": supabase_user_id})
            .eq("id", profile_id)
            .execute()
        )
        rows = response.data or []
        if not rows:
            raise HTTPException(status_code=503, detail="Operator profile could not be linked to Supabase Auth.")
        return _profile_from_row(rows[0])


def _profile_from_row(row: dict[str, Any]) -> OperatorProfile:
    return OperatorProfile(
        id=str(row["id"]),
        email=str(row["email"]).strip().lower(),
        display_name=str(row.get("display_name") or row["email"]),
        role=str(row.get("role") or "operator"),
        routing_line=str(row.get("routing_line") or ""),
        click_to_call_phone=normalize_phone_number(str(row.get("click_to_call_phone") or "")),
        active=bool(row.get("active", True)),
        supabase_user_id=str(row["supabase_user_id"]) if row.get("supabase_user_id") else None,
    )
