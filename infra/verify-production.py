#!/usr/bin/env python3
"""Mentor AI — Production Deployment Health & Security Verification Suite.

Usage:
    python infra/verify-production.py [--api-url https://your-api.onrender.com/api/v1] [--frontend-url https://your-web.vercel.app]
"""

import argparse
import sys
import uuid
from typing import Any
import httpx

PASS_BADGE = "\033[92m[PASS]\033[0m"
FAIL_BADGE = "\033[91m[FAIL]\033[0m"
WARN_BADGE = "\033[93m[WARN]\033[0m"
INFO_BADGE = "\033[94m[INFO]\033[0m"


class ProductionVerifier:
    def __init__(self, api_base_url: str, frontend_url: str | None = None) -> None:
        self.api_url = api_base_url.rstrip("/")
        self.frontend_url = frontend_url.rstrip("/") if frontend_url else None
        self.failures: list[str] = []
        self.warnings: list[str] = []

        # If testing local server, attempt real socket or gracefully fallback to in-memory ASGI transport
        if "localhost" in self.api_url or "127.0.0.1" in self.api_url:
            use_asgi = False
            try:
                probe = httpx.get(f"{self.api_url}/health", timeout=0.5)
                if probe.status_code == 200:
                    self.client = httpx.Client(timeout=30.0)
                else:
                    use_asgi = True
            except Exception:
                use_asgi = True

            if use_asgi:
                from starlette.testclient import TestClient
                from app.main import app

                self.client = TestClient(app, base_url="http://testserver")  # type: ignore[assignment]
                self.api_url = "/api/v1"
                print(f" {INFO_BADGE} Running in in-memory ASGI transport mode")
        else:
            self.client = httpx.Client(timeout=30.0)

    def log_pass(self, title: str, detail: str = "") -> None:
        print(f" {PASS_BADGE} {title} {f'({detail})' if detail else ''}")

    def log_fail(self, title: str, detail: str) -> None:
        print(f" {FAIL_BADGE} {title}: {detail}")
        self.failures.append(f"{title}: {detail}")

    def log_warn(self, title: str, detail: str) -> None:
        print(f" {WARN_BADGE} {title}: {detail}")
        self.warnings.append(f"{title}: {detail}")

    def run_all_checks(self) -> bool:
        print("=" * 80)
        print(f" MENTOR AI PRODUCTION VERIFICATION SUITE")
        print(f" Target Backend:  {self.api_url}")
        print(f" Target Frontend: {self.frontend_url or 'Not specified (skipping bundle scan)'}")
        print("=" * 80)

        # 1. Liveness Probe
        self.check_liveness()

        # 2. Readiness Probe & Secret Leakage Screening
        self.check_readiness_and_secrets()

        # 3. HTTP Security Response Headers
        self.check_security_headers()

        # 4. CORS Origins Preflight
        self.check_cors_headers()

        # 5. Authentication Failure Protection
        self.check_unauthorized_rejections()

        # 6. E2E User Journey & Cross-User IDOR Isolation
        self.check_e2e_user_lifecycle_and_idor()

        # 7. Frontend Secret Exposure Screening
        if self.frontend_url:
            self.check_frontend_bundle_for_secrets()

        print("\n" + "=" * 80)
        if not self.failures:
            print(" \033[92mALL PRODUCTION SANITY CHECKS PASSED SUCCESSFULLY!\033[0m")
            if self.warnings:
                print(f" Total Warnings: {len(self.warnings)}")
            return True
        else:
            print(f" \033[91mVERIFICATION FAILED: {len(self.failures)} check(s) reported errors.\033[0m")
            for f in self.failures:
                print(f"  - {f}")
            return False

    def check_liveness(self) -> None:
        try:
            res = self.client.get(f"{self.api_url}/health")
            if res.status_code == 200:
                data = res.json()
                self.log_pass("Liveness Probe (/health)", f"Status: {data.get('status')}, Env: {data.get('environment')}, v{data.get('version')}")
            else:
                self.log_fail("Liveness Probe (/health)", f"Expected 200, got HTTP {res.status_code}")
        except Exception as e:
            self.log_fail("Liveness Probe (/health)", f"Connection error: {e}")

    def check_readiness_and_secrets(self) -> None:
        try:
            res = self.client.get(f"{self.api_url}/health/ready")
            if res.status_code == 200:
                text_lower = res.text.lower()
                for secret_kw in ["password", "secret", "service_role", "bearer", "private"]:
                    if secret_kw in text_lower:
                        self.log_fail("Secret Exposure in Readiness", f"Found keyword '{secret_kw}' in response body")
                        return

                data = res.json()
                self.log_pass("Readiness Probe (/health/ready)", f"Overall: {data.get('status')}, DB: {data.get('database')}, AI: {data.get('ai_service')}")
            else:
                self.log_fail("Readiness Probe (/health/ready)", f"Expected 200, got HTTP {res.status_code}")
        except Exception as e:
            self.log_fail("Readiness Probe (/health/ready)", f"Connection error: {e}")

    def check_security_headers(self) -> None:
        try:
            res = self.client.get(f"{self.api_url}/health")
            headers = res.headers

            checks = [
                ("X-Content-Type-Options", "nosniff"),
                ("X-Frame-Options", "DENY"),
                ("X-XSS-Protection", "1; mode=block"),
                ("Referrer-Policy", "strict-origin-when-cross-origin"),
            ]
            for h_key, h_val in checks:
                if headers.get(h_key) == h_val:
                    self.log_pass(f"Header '{h_key}'", h_val)
                else:
                    self.log_fail(f"Header '{h_key}'", f"Expected '{h_val}', got '{headers.get(h_key)}'")

            if "X-Request-ID" in headers:
                self.log_pass("Header 'X-Request-ID'", headers.get("X-Request-ID")[:8] + "...")
            else:
                self.log_warn("Header 'X-Request-ID'", "Missing trace ID header")
        except Exception as e:
            self.log_fail("Security Headers", f"Connection error: {e}")

    def check_cors_headers(self) -> None:
        try:
            try:
                from app.core.config import settings
                allowed = (
                    settings.ALLOWED_ORIGINS[0]
                    if isinstance(settings.ALLOWED_ORIGINS, list) and settings.ALLOWED_ORIGINS
                    else "http://localhost:3000"
                )
            except Exception:
                allowed = "http://localhost:3000"

            res = self.client.options(
                f"{self.api_url}/tasks",
                headers={
                    "Origin": allowed,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
            allow_origin = res.headers.get("access-control-allow-origin")
            if allow_origin in [allowed, "*"] or res.status_code in (200, 204):
                self.log_pass("CORS Preflight Policy", f"Allowed origin '{allowed}' accepted (HTTP {res.status_code})")
            else:
                self.log_warn("CORS Preflight Policy", f"Origin {allowed} got status {res.status_code}")
        except Exception as e:
            self.log_warn("CORS Preflight Policy", f"Connection warning: {e}")

    def check_unauthorized_rejections(self) -> None:
        try:
            res = self.client.get(f"{self.api_url}/tasks")
            if res.status_code == 401:
                data = res.json()
                if data.get("error_code") == "UNAUTHORIZED":
                    self.log_pass("Authentication Gate (/tasks)", "Correctly rejected missing auth with 401 UNAUTHORIZED")
                else:
                    self.log_fail("Authentication Gate (/tasks)", f"Expected error_code UNAUTHORIZED, got {data}")
            else:
                self.log_fail("Authentication Gate (/tasks)", f"Expected 401, got {res.status_code}")
        except Exception as e:
            self.log_fail("Authentication Gate (/tasks)", f"Connection error: {e}")

    def check_e2e_user_lifecycle_and_idor(self) -> None:
        try:
            # 1. Signup User A
            email_a = f"prod.test.a.{uuid.uuid4().hex[:6]}@example.com"
            res_a = self.client.post(
                f"{self.api_url}/auth/signup",
                json={"email": email_a, "password": "ProductionPassword123!", "full_name": "User Alpha"},
            )
            if res_a.status_code != 201:
                self.log_fail("User A Signup", f"Status {res_a.status_code}: {res_a.text}")
                return
            token_a = res_a.json()["access_token"]
            headers_a = {"Authorization": f"Bearer {token_a}"}
            self.log_pass("User A Registration", f"Created {email_a}")

            # 2. Signup User B
            email_b = f"prod.test.b.{uuid.uuid4().hex[:6]}@example.com"
            res_b = self.client.post(
                f"{self.api_url}/auth/signup",
                json={"email": email_b, "password": "ProductionPassword123!", "full_name": "User Beta"},
            )
            if res_b.status_code != 201:
                self.log_fail("User B Signup", f"Status {res_b.status_code}: {res_b.text}")
                return
            token_b = res_b.json()["access_token"]
            headers_b = {"Authorization": f"Bearer {token_b}"}
            self.log_pass("User B Registration", f"Created {email_b}")

            # 3. User A creates private task
            task_res = self.client.post(
                f"{self.api_url}/tasks",
                headers=headers_a,
                json={"title": "Alpha Confidential Deliverable", "duration_minutes": 60, "priority": "P1"},
            )
            if task_res.status_code != 201:
                self.log_fail("Task Creation", f"Status {task_res.status_code}: {task_res.text}")
                return
            task_id = task_res.json()["id"]
            self.log_pass("User A Task Persistence", f"Task ID {task_id[:8]}... persisted")

            # 4. User B attempts IDOR read of User A's task -> MUST return 404
            idor_res = self.client.get(f"{self.api_url}/tasks/{task_id}", headers=headers_b)
            if idor_res.status_code == 404:
                self.log_pass("IDOR Protection Gate", "User B received 404 NOT_FOUND attempting to access User A's task")
            else:
                self.log_fail("IDOR Protection Gate", f"SECURITY BREACH: User B received status {idor_res.status_code}")

            # 5. User A generates draft plan
            draft_res = self.client.post(
                f"{self.api_url}/planner/draft",
                headers=headers_a,
                json={
                    "message": "Plan my day tomorrow: team sync from 10am to 11am and complete alpha report for 60 minutes.",
                    "client_timezone": "UTC",
                },
            )
            if draft_res.status_code == 200:
                draft_data = draft_res.json()
                self.log_pass("AI Planner Draft Pipeline", f"Extracted {len(draft_data['tasks'])} tasks, Parser: {draft_data['parser_used']}")
            else:
                self.log_fail("AI Planner Draft Pipeline", f"Draft plan failed with status {draft_res.status_code}")

        except Exception as e:
            self.log_fail("E2E User Journey & IDOR", f"Unexpected error: {e}")

    def check_frontend_bundle_for_secrets(self) -> None:
        try:
            res = self.client.get(self.frontend_url)  # type: ignore[arg-type]
            if res.status_code != 200:
                self.log_warn("Frontend Root Access", f"HTTP {res.status_code} at {self.frontend_url}")
                return

            html = res.text
            leaked_keywords = [
                "service_role",
                "SUPABASE_SERVICE_ROLE",
                "FERNET_ENCRYPTION_KEY",
                "AIzaSy",  # Google AI Studio API key prefix
                "gsk_",    # Groq API key prefix
                "GOCSPX-", # Google OAuth secret prefix
            ]
            for kw in leaked_keywords:
                if kw in html:
                    self.log_fail("Frontend HTML Bundle Security", f"Found sensitive secret signature '{kw}' in rendered HTML")
                    return

            self.log_pass("Frontend Bundle Security", "Scanned rendered HTML — zero server-side credentials or API secret signatures found")
        except Exception as e:
            self.log_warn("Frontend Bundle Security", f"Could not scan frontend: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mentor AI Production Deployment Verifier")
    parser.add_argument("--api-url", default="http://localhost:8000/api/v1", help="Base URL of Mentor AI API v1")
    parser.add_argument("--frontend-url", default=None, help="Base URL of deployed frontend (optional)")
    args = parser.parse_args()

    verifier = ProductionVerifier(api_base_url=args.api_url, frontend_url=args.frontend_url)
    success = verifier.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
