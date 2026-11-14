"""Synthetic fixtures. No real personal data: names, employers and numbers are invented."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent

CV_TEXT = """\
RINA PRATAMA
Backend Engineer
rina.pratama@example.com | +62 811 000 111 | Jakarta, Indonesia
https://example.com/portfolio

SUMMARY
Backend engineer with 6 years building payment and reporting services in Go and Python.

EXPERIENCE
Senior Backend Engineer, Nusantara Payments (2021 - present)
- Led the migration of the settlement service from a monolith to four Go services.
- Cut p99 latency of the payout API from 900 ms to 240 ms by adding a Redis read cache.
- Wrote the reconciliation job in Python that matches 1.2 million daily transactions.

Backend Engineer, Kopi Digital (2019 - 2021)
- Built the order service in Go with PostgreSQL and gRPC.
- Introduced integration tests that raised coverage of the checkout package to 78%.

EDUCATION
BSc Computer Science, Universitas Contoh (2019)

SKILLS
Go, Python, PostgreSQL, Redis, gRPC, Docker, Kubernetes, Terraform, Kafka

CERTIFICATIONS
AWS Certified Solutions Architect - Associate (2022)
"""

JD_CLEAN = """\
Senior Backend Engineer - Payments
Kopi Nusantara, Jakarta (hybrid)

About the role
We are hiring a senior backend engineer for our payments platform. You will own
settlement and reconciliation services and work with the risk team on payout limits.

What we ask
- 5+ years of professional backend engineering experience.
- Strong Go. Our services are written in Go and we expect you to read and write it daily.
- Experience with PostgreSQL, including query tuning on tables above 10 million rows.
- Hands-on experience with Kubernetes in production.
- Familiarity with Kafka or another event streaming platform.
- Excellent written English; the team documents design decisions in English.
- A degree in computer science or equivalent practical experience is required.

Nice to have
- Experience in fintech or payments.
- Terraform for infrastructure as code.

Benefits
Health insurance, annual learning budget, 20 days of leave.
"""

JD_NOISY = """\
Jobs you may also like

Backend Engineer - Remote
PT Angin Segar | Jakarta

Apply now

Senior Backend Engineer - Payments
Kopi Nusantara | Jakarta | Hybrid

About the role
We are hiring a senior backend engineer for our payments platform. You will own
settlement and reconciliation services.

What we ask
- 5+ years of professional backend engineering experience.
- Strong Go.
- Experience with PostgreSQL.
- Hands-on experience with Kubernetes.

Recommended for you
Frontend Engineer at Toko Online
Data Analyst at Gudang Data
Read more
"""

JD_MULTI = """\
Two open roles at Nusantara Digital

Role 1: Senior Backend Engineer
- 5+ years of backend engineering experience.
- Strong Go and PostgreSQL.
- Kubernetes in production.

Role 2: Data Engineer
- 3+ years building batch and streaming pipelines.
- Strong Python and dbt.
- Experience with Snowflake or BigQuery.
"""

NON_JOB_TEXT = """\
Sign in to continue

Your session has expired. Please sign in again to view this page.

Email address
Password
Remember me
Forgot your password?

By continuing you agree to the Terms of Service and the Privacy Policy.
"""


def fixture_files() -> dict[str, str]:
    return {
        "cv_rina.txt": CV_TEXT,
        "jd_clean.txt": JD_CLEAN,
        "jd_noisy.txt": JD_NOISY,
        "jd_multi.txt": JD_MULTI,
        "non_job.txt": NON_JOB_TEXT,
    }


def write_fixtures(target: Path) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, text in fixture_files().items():
        path = target / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    print(json.dumps([str(path) for path in write_fixtures(FIXTURES_DIR)]))
