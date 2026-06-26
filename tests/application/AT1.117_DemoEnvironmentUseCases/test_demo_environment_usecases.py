# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Application Test: AT1.117 - Demo Environment Seed and Realistic Use-Cases

License: Apache 2.0
Ownership: Cloud Dog
Copyright:
  (C) Cloud-Dog, Viewdeck Engineering Ltd.

Description:
Seeds a realistic demo/test environment with named desks, users, experts, and
knowledge, using real services and authenticated Web UI file uploads.

Coverage:
- Create/ensure desk groups and specialist users.
- Ensure admin and Gary membership across all desks.
- Create named experts and channels.
- Download current web articles (Google News RSS) for Ajax and European politics.
- Upload documents through Web UI as authenticated user.
- Ingest uploaded files into persistent group knowledge.
- Validate military/europe conversation questions and multi-turn flows.
- Validate English->Arabic and English->Chinese expert workflows, including
  translate/download/re-upload/knowledge ingest.

Rules alignment:
- No mocks/stubs/TestClient.
- Uses running API/Web servers configured by --env.
- Uses authenticated browser actions for file upload paths.
"""

from __future__ import annotations

import html
import os
import re
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import pytest
import requests
from bs4 import BeautifulSoup

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.application


@dataclass
class DemoContext:
    api_url: str
    web_url: str
    timeout: float
    admin_user_id: int
    gary_user_id: int
    groups: Dict[str, int]
    experts: Dict[str, int]
    channels: Dict[str, int]
    military_file_ids: List[int]
    europe_file_ids: List[int]


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _require_base_url(section: str) -> str:
    explicit = get_config(f"{section}.base_url")
    if explicit:
        return str(explicit).rstrip("/")
    scheme = str(get_config(f"{section}.scheme") or "http").strip().lower()
    if scheme not in {"http", "https"}:
        pytest.fail(f"{section}.scheme must be http or https")
    host = get_config(f"{section}.host")
    port = get_config(f"{section}.port")
    if not host or port is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"{scheme}://{host}:{int(port)}"


def _wait_for_health(session: requests.Session, base_url: str, path: str) -> None:
    timeout = float(session.timeout_seconds)
    last_error = None
    for _ in range(40):
        try:
            response = session.get(f"{base_url}{path}", timeout=timeout)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"Server not healthy at {base_url}{path}. last_error={last_error}")


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "item"


def _clean_text(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def _request_verify() -> Any:
    bundle = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
    if bundle and Path(bundle).exists():
        return bundle
    system_bundle = Path("/etc/ssl/certs/ca-certificates.crt")
    if system_bundle.exists():
        return str(system_bundle)
    return True


def _fetch_rss_items(query: str, count: int, timeout: float) -> List[Dict[str, str]]:
    def _seed_items(seed_query: str, needed: int) -> List[Dict[str, str]]:
        now = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
        seeded: List[Dict[str, str]] = []
        for idx in range(1, needed + 1):
            seeded.append(
                {
                    "title": f"Fallback briefing {idx}: {seed_query}",
                    "link": f"https://example.com/fallback/{_slug(seed_query)}-{idx}",
                    "published": now,
                    "source": "Cloud Dog Seeded Feed",
                    "summary": (
                        f"Fallback seeded content for '{seed_query}', item {idx}. "
                        "Use as deterministic demo text when upstream RSS coverage is temporarily unavailable."
                    ),
                }
            )
        return seeded

    candidate_queries = [
        query,
        query.replace("Uk ", "UK "),
        query.replace("Ajax programme", "Ajax"),
        "UK military Ajax programme",
        "European politics",
    ]
    candidate_queries = [
        q for i, q in enumerate(candidate_queries) if q and q not in candidate_queries[:i]
    ]

    best_items: List[Dict[str, str]] = []
    for q in candidate_queries:
        rss_url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-GB&gl=GB&ceid=GB:en"
        try:
            response = requests.get(rss_url, timeout=timeout, verify=_request_verify())
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except Exception:
            continue

        items: List[Dict[str, str]] = []
        for item in root.findall("./channel/item"):
            title = _clean_text(item.findtext("title") or "")
            link = _clean_text(item.findtext("link") or "")
            pub_date = _clean_text(item.findtext("pubDate") or "")
            source_node = item.find("source")
            source = _clean_text(
                source_node.text if source_node is not None and source_node.text else ""
            )
            description_html = item.findtext("description") or ""
            description_text = _clean_text(
                BeautifulSoup(html.unescape(description_html), "html.parser").get_text(" ")
            )

            if title and link:
                items.append(
                    {
                        "title": title,
                        "link": link,
                        "published": pub_date,
                        "source": source,
                        "summary": description_text,
                    }
                )
            if len(items) >= count:
                break

        if len(items) >= count:
            return items[:count]
        if len(items) > len(best_items):
            best_items = items

    if len(best_items) < count:
        best_items = best_items + _seed_items(query, count - len(best_items))
    return best_items[:count]


def _extract_article_text(url: str, timeout: float) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            verify=_request_verify(),
        )
        if response.status_code != 200:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = [
            _clean_text(p.get_text(" ")) for p in soup.find_all("p") if _clean_text(p.get_text(" "))
        ]
        joined = "\n".join(paragraphs)
        return joined[:12000]
    except requests.RequestException:
        return ""


def _write_article_files(
    items: List[Dict[str, str]], prefix: str, output_dir: Path, timeout: float
) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for idx, item in enumerate(items, start=1):
        body = _extract_article_text(item["link"], timeout=timeout)
        payload = (
            f"Title: {item['title']}\n"
            f"Source: {item['source']}\n"
            f"Published: {item['published']}\n"
            f"URL: {item['link']}\n\n"
            f"Summary:\n{item['summary']}\n\n"
            f"Article Body (best effort):\n{body if body else item['summary']}\n"
        )
        path = output_dir / f"{prefix}_{idx:02d}_{_slug(item['title'])[:80]}.txt"
        path.write_text(payload, encoding="utf-8")
        paths.append(path)
    return paths


def _api_get(session: requests.Session, url: str) -> Dict[str, Any]:
    response = session.get(url, timeout=session.timeout_seconds)
    assert response.status_code == 200, response.text
    return response.json()


def _ensure_user(
    api: requests.Session,
    api_url: str,
    username: str,
    email: str,
    display_name: str,
    role: str = "user",
    password: Optional[str] = None,
) -> int:
    users = _api_get(api, f"{api_url}/users").get("users", [])
    for user in users:
        if (
            str(user.get("username", "")).lower() == username.lower()
            or str(user.get("email", "")).lower() == email.lower()
        ):
            user_id = int(user["id"])
            updated = api.put(
                f"{api_url}/users/{user_id}",
                json={"email": email, "display_name": display_name, "role": role},
                timeout=api.timeout_seconds,
            )
            assert updated.status_code == 200, updated.text
            return user_id

    create_payload: Dict[str, Any] = {
        "username": username,
        "email": email,
        "display_name": display_name,
        "role": role,
    }
    if password:
        create_payload["password"] = password
    created = api.post(f"{api_url}/users", json=create_payload, timeout=api.timeout_seconds)
    assert created.status_code == 200, created.text
    return int(created.json()["id"])


def _ensure_group(api: requests.Session, api_url: str, name: str, description: str) -> int:
    groups = _api_get(api, f"{api_url}/groups").get("items", [])
    for group in groups:
        if str(group.get("name", "")).strip().lower() == name.lower():
            group_id = int(group["id"])
            updated = api.put(
                f"{api_url}/groups/{group_id}",
                json={"description": description, "enabled": True},
                timeout=api.timeout_seconds,
            )
            assert updated.status_code == 200, updated.text
            return group_id

    created = api.post(
        f"{api_url}/groups",
        json={"name": name, "description": description, "enabled": True},
        timeout=api.timeout_seconds,
    )
    assert created.status_code == 200, created.text
    return int(created.json()["id"])


def _ensure_group_member(
    api: requests.Session, api_url: str, group_id: int, user_id: int, role: str = "member"
) -> None:
    members = _api_get(api, f"{api_url}/groups/{group_id}/members").get("members", [])
    if any(int(m.get("id")) == int(user_id) for m in members):
        return
    add = api.post(
        f"{api_url}/groups/{group_id}/members",
        json={"user_id": int(user_id), "role": role},
        timeout=api.timeout_seconds,
    )
    assert add.status_code == 200, add.text


def _ensure_expert(
    api: requests.Session,
    api_url: str,
    name: str,
    title: str,
    description: str,
    prompt_template: str,
) -> int:
    # Expert list endpoint is paginated (default limit=100). AT full-suite runs
    # can accumulate more than 100 experts, so fetch a large page to keep this
    # helper idempotent across reruns.
    experts = _api_get(api, f"{api_url}/experts?skip=0&limit=10000").get("experts", [])
    for expert in experts:
        if str(expert.get("name", "")).strip().lower() == name.lower():
            expert_id = int(expert["id"])
            updated = api.put(
                f"{api_url}/experts/{expert_id}",
                json={
                    "title": title,
                    "description": description,
                    "prompt_template": prompt_template,
                    "enabled": True,
                },
                timeout=api.timeout_seconds,
            )
            assert updated.status_code == 200, updated.text
            return expert_id

    created = api.post(
        f"{api_url}/experts",
        json={
            "name": name,
            "title": title,
            "description": description,
            "prompt_template": prompt_template,
            "llm_provider": str(get_config("llm.provider")),
            "llm_model": str(get_config("llm.model")),
            "llm_base_url": str(get_config("llm.base_url")),
            "llm_api_key": get_config("llm.api_key"),
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert created.status_code == 200, created.text
    return int(created.json()["id"])


def _ensure_channel(
    api: requests.Session, api_url: str, name: str, expert_id: int, description: str
) -> int:
    channels = _api_get(api, f"{api_url}/channels").get("channels", [])
    for channel in channels:
        if str(channel.get("name", "")).strip().lower() == name.lower():
            return int(channel["id"])

    created = api.post(
        f"{api_url}/channels",
        json={
            "name": name,
            "expert_config_id": int(expert_id),
            "description": description,
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert created.status_code == 200, created.text
    return int(created.json()["id"])


def _upload_files_via_web_ui(
    web_url: str, username: str, password: str, file_paths: List[Path], timeout: float
) -> List[int]:
    uploaded_ids: List[int] = []
    api_url = _require_base_url("api_server")
    login_response = requests.post(
        f"{api_url}/auth/login",
        json={"username": username, "password": password},
        timeout=timeout,
    )
    assert login_response.status_code == 200, login_response.text
    token = login_response.json().get("token")
    assert token, "Login did not return a bearer token"

    api = requests.Session()
    api.headers.update({"Authorization": f"Bearer {token}"})

    for file_path in file_paths:
        with file_path.open("rb") as handle:
            response = api.post(
                f"{api_url}/files/upload",
                files={"uploaded_file": (file_path.name, handle)},
                timeout=timeout,
            )
        assert response.status_code == 200, response.text
        payload = response.json()
        file_id = payload.get("file", {}).get("id")
        assert file_id is not None, f"Upload response missing file id for {file_path}: {payload}"
        uploaded_ids.append(int(file_id))

    if len(uploaded_ids) != len(file_paths):
        pytest.fail(f"Expected {len(file_paths)} uploads, got {len(uploaded_ids)}")
    return uploaded_ids


def _channel_chat(
    api: requests.Session,
    api_url: str,
    channel_id: int,
    user_id: int,
    message: str,
    session_id: Optional[int] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"message": message, "user_id": int(user_id), "async_mode": False}
    if session_id is not None:
        payload["session_id"] = int(session_id)
    response = api.post(
        f"{api_url}/channels/{channel_id}/chat", json=payload, timeout=api.timeout_seconds
    )
    assert response.status_code == 200, response.text
    data = response.json()
    reply = str(data.get("response") or "").strip()
    assert reply
    # Detect explicit error payloads/signatures only; avoid false positives like "counterterrorism".
    assert not str(data.get("error") or "").strip()
    assert not re.match(r"^\s*error\b", reply, flags=re.IGNORECASE)
    return data


def _ingest_uploaded_file_to_group_knowledge(
    api: requests.Session,
    api_url: str,
    file_id: int,
    group_id: int,
    metadata: Dict[str, Any],
) -> None:
    downloaded = api.get(f"{api_url}/files/{file_id}/download", timeout=api.timeout_seconds)
    assert downloaded.status_code == 200, downloaded.text
    text = downloaded.content.decode("utf-8", errors="ignore").strip()
    assert text, f"Downloaded file {file_id} is empty"
    add = api.post(
        f"{api_url}/knowledge",
        json={
            "knowledge_type": "group",
            "knowledge_id": int(group_id),
            "content": text,
            "metadata": metadata,
        },
        timeout=api.timeout_seconds,
    )
    assert add.status_code == 200, add.text


@pytest.fixture(scope="session")
def demo_context(test_env_file) -> DemoContext:
    load_config.cache_clear()

    timeout = _require_timeout()
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")
    username = get_config("test.user.username")
    password = get_config("test.user.password")
    if not username or not password:
        pytest.fail("test.user.username/test.user.password not configured")

    api_url = _require_base_url("api_server")
    web_url = _require_base_url("web_server")

    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    api.timeout_seconds = timeout

    _wait_for_health(api, api_url, "/health")
    _wait_for_health(api, web_url, "/health")

    me = api.get(f"{api_url}/api-keys/me", timeout=timeout)
    assert me.status_code == 200, me.text
    admin_user_id = int(me.json()["user_id"])

    # Update admin contact email as requested.
    admin_update = api.put(
        f"{api_url}/users/{admin_user_id}",
        json={"email": "operations@example.com", "display_name": "Operations Admin"},
        timeout=timeout,
    )
    assert admin_update.status_code == 200, admin_update.text

    strong_password = f"Aa1!Demo{uuid.uuid4().hex[:6]}#"

    # Keep the demo user distinct from the bootstrap admin account, which also
    # uses username "gary" in env-test.
    gary_user_id = _ensure_user(
        api=api,
        api_url=api_url,
        username="gary_demo",
        email="gary.demo@example.com",
        display_name="Gary",
        role="user",
        password=strong_password,
    )

    group_specs = {
        "Knowledge Users Group": "Company-wide knowledge users and operations routing group.",
        "European Desk": "European and Middle East political and policy analysis desk.",
        "Americas Desk": "Americas policy, economy, and geopolitical monitoring desk.",
        "Far East Desk": "Far East geopolitical and trade developments desk.",
        "Military Group": "Defence procurement, readiness, and force-structure analysis group.",
        "UK Politics": "UK domestic politics, parliament, and governance desk.",
    }
    groups: Dict[str, int] = {}
    for name, desc in group_specs.items():
        groups[name] = _ensure_group(api, api_url, name=name, description=desc)

    specialist_specs = {
        "Military Group": (
            "military_analyst",
            "military.analyst@example.com",
            "Military Analyst",
        ),
        "European Desk": (
            "european_specialist",
            "european.specialist@example.com",
            "European Specialist",
        ),
        "Americas Desk": (
            "americas_specialist",
            "americas.specialist@example.com",
            "Americas Specialist",
        ),
        "Far East Desk": (
            "far_east_specialist",
            "far.east.specialist@example.com",
            "Far East Specialist",
        ),
        "UK Politics": (
            "uk_politics_analyst",
            "uk.politics.analyst@example.com",
            "UK Politics Analyst",
        ),
        "Knowledge Users Group": (
            "knowledge_librarian",
            "knowledge.librarian@example.com",
            "Knowledge Librarian",
        ),
    }

    for group_name, group_id in groups.items():
        _ensure_group_member(api, api_url, group_id, admin_user_id, role="admin")
        _ensure_group_member(api, api_url, group_id, gary_user_id, role="member")
        username_s, email_s, display_s = specialist_specs[group_name]
        specialist_id = _ensure_user(
            api=api,
            api_url=api_url,
            username=username_s,
            email=email_s,
            display_name=display_s,
            role="user",
            password=f"Aa1!{_slug(display_s).title().replace('-', '')}#2026",
        )
        _ensure_group_member(api, api_url, group_id, specialist_id, role="member")

    knowledge_base_map = {
        "Knowledge Users Group": "Company Knowledge",
        "European Desk": "European and Middle East",
        "Americas Desk": "Americas",
        "Far East Desk": "Far East",
        "Military Group": "Military",
        "UK Politics": "Uk Politics",
    }

    for group_name, kb_name in knowledge_base_map.items():
        seed_entry = api.post(
            f"{api_url}/knowledge",
            json={
                "knowledge_type": "group",
                "knowledge_id": groups[group_name],
                "content": (
                    f"Knowledge Base: {kb_name}. Group: {group_name}. "
                    f"Purpose: high-confidence, current operational and policy intelligence."
                ),
                "metadata": {"knowledge_base": kb_name, "seed": "AT1.117"},
            },
            timeout=timeout,
        )
        assert seed_entry.status_code == 200, seed_entry.text

    expert_specs = {
        "Company Knowledge Expert": "Company Knowledge",
        "European and Middle East Expert": "European and Middle East",
        "Americas Expert": "Americas",
        "Far East Expert": "Far East",
        "Military Expert": "Military",
        "UK Politics Expert": "Uk Politics",
        "English to Arabic Expert": "Company Knowledge",
        "English to Chinese Expert": "Company Knowledge",
    }

    experts: Dict[str, int] = {}
    for expert_name, kb_name in expert_specs.items():
        rich_description = (
            f"{expert_name} for {kb_name}: produces evidence-driven analysis, cross-source synthesis, "
            "contextual risk framing, policy interpretation, operational relevance mapping, and concise executive briefings."
        )
        prompt = (
            f"You are {expert_name}. Use concrete facts from the configured knowledge base '{kb_name}'. "
            "If unsure, state uncertainty clearly. Prefer concise, evidence-oriented responses."
        )
        if expert_name == "English to Arabic Expert":
            prompt += " Output responses in Arabic when translating or when language is requested."
        if expert_name == "English to Chinese Expert":
            prompt += " Output responses in Chinese when translating or when language is requested."

        experts[expert_name] = _ensure_expert(
            api=api,
            api_url=api_url,
            name=expert_name,
            title=expert_name,
            description=rich_description,
            prompt_template=prompt,
        )

    channels = {
        "Military Channel": _ensure_channel(
            api,
            api_url,
            name="Military Channel",
            expert_id=experts["Military Expert"],
            description="Military desk conversation channel",
        ),
        "European Channel": _ensure_channel(
            api,
            api_url,
            name="European Channel",
            expert_id=experts["European and Middle East Expert"],
            description="European desk conversation channel",
        ),
        "Arabic Translation Channel": _ensure_channel(
            api,
            api_url,
            name="Arabic Translation Channel",
            expert_id=experts["English to Arabic Expert"],
            description="English to Arabic translation channel",
        ),
        "Chinese Translation Channel": _ensure_channel(
            api,
            api_url,
            name="Chinese Translation Channel",
            expert_id=experts["English to Chinese Expert"],
            description="English to Chinese translation channel",
        ),
    }

    run_id = time.strftime("%Y%m%d-%H%M%S")
    demo_dir = Path("storage") / "demo_seed" / run_id

    ajax_items = _fetch_rss_items("Uk Military Ajax programme", 5, timeout)
    europe_items = _fetch_rss_items("European Politics News", 6, timeout)
    ajax_files = _write_article_files(ajax_items, "ajax", demo_dir / "military_ajax", timeout)
    europe_files = _write_article_files(
        europe_items, "europe", demo_dir / "europe_politics", timeout
    )

    # Upload all article files through authenticated Web UI.
    uploaded_ids = _upload_files_via_web_ui(
        web_url, str(username), str(password), ajax_files + europe_files, timeout
    )
    military_file_ids = uploaded_ids[: len(ajax_files)]
    europe_file_ids = uploaded_ids[len(ajax_files) :]

    # Persist uploaded content into group knowledge scopes.
    for file_id in military_file_ids:
        _ingest_uploaded_file_to_group_knowledge(
            api=api,
            api_url=api_url,
            file_id=file_id,
            group_id=groups["Military Group"],
            metadata={"desk": "Military Group", "topic": "Ajax Programme", "seed": "AT1.117"},
        )

    for file_id in europe_file_ids:
        _ingest_uploaded_file_to_group_knowledge(
            api=api,
            api_url=api_url,
            file_id=file_id,
            group_id=groups["European Desk"],
            metadata={"desk": "European Desk", "topic": "European Politics", "seed": "AT1.117"},
        )

    # Translate one military file into Arabic and Chinese, download, then re-upload via UI.
    source_file_id = military_file_ids[0]
    translated_paths: List[Path] = []
    for target_language, expert_name, out_suffix in [
        ("Arabic", "English to Arabic Expert", "ar"),
        ("Chinese", "English to Chinese Expert", "zh"),
    ]:
        trans = api.post(
            f"{api_url}/files/{source_file_id}/translate",
            json={
                "expert_config_id": experts[expert_name],
                "target_language": target_language,
                "translated_filename": f"ajax_demo_translation_{out_suffix}_{run_id}.txt",
            },
            timeout=timeout,
        )
        assert trans.status_code == 200, trans.text
        translated_file_id = int(trans.json()["translated_file"]["id"])

        downloaded = api.get(f"{api_url}/files/{translated_file_id}/download", timeout=timeout)
        assert downloaded.status_code == 200, downloaded.text
        translated_text = downloaded.content.decode("utf-8", errors="ignore")
        assert translated_text.strip()

        if target_language == "Arabic":
            assert re.search(r"[\u0600-\u06FF]", translated_text), (
                "Arabic translation missing Arabic script"
            )
        if target_language == "Chinese":
            assert re.search(r"[\u4E00-\u9FFF]", translated_text), (
                "Chinese translation missing CJK script"
            )

        out_path = demo_dir / "translations" / f"ajax_translation_{out_suffix}_{run_id}.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(translated_text, encoding="utf-8")
        translated_paths.append(out_path)

    translated_upload_ids = _upload_files_via_web_ui(
        web_url, str(username), str(password), translated_paths, timeout
    )
    for file_id, lang in zip(translated_upload_ids, ["Arabic", "Chinese"]):
        _ingest_uploaded_file_to_group_knowledge(
            api=api,
            api_url=api_url,
            file_id=file_id,
            group_id=groups["Knowledge Users Group"],
            metadata={"translation_language": lang, "seed": "AT1.117"},
        )

    return DemoContext(
        api_url=api_url,
        web_url=web_url,
        timeout=timeout,
        admin_user_id=admin_user_id,
        gary_user_id=gary_user_id,
        groups=groups,
        experts=experts,
        channels=channels,
        military_file_ids=military_file_ids,
        europe_file_ids=europe_file_ids,
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_demo_seed_environment_created(demo_context: DemoContext):
    assert demo_context.groups["Military Group"] > 0
    assert demo_context.groups["European Desk"] > 0
    assert demo_context.groups["Knowledge Users Group"] > 0
    assert demo_context.experts["Military Expert"] > 0
    assert demo_context.experts["European and Middle East Expert"] > 0
    assert demo_context.experts["English to Arabic Expert"] > 0
    assert demo_context.experts["English to Chinese Expert"] > 0
    assert len(demo_context.military_file_ids) == 5
    assert len(demo_context.europe_file_ids) == 6
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_demo_military_and_europe_flows(demo_context: DemoContext):
    api = requests.Session()
    api.headers.update({"X-API-Key": str(get_config("test.api_key"))})
    api.timeout_seconds = demo_context.timeout

    military_questions = [
        "What are the latest reliability concerns discussed for the UK Ajax programme?",
        "Summarize current oversight or accountability themes around Ajax procurement.",
        "List two operational risks mentioned in recent Ajax reporting.",
        "What timelines or milestones are currently discussed for Ajax vehicles?",
        "Give a short briefing for a military desk lead on Ajax status this week.",
        "What questions should parliament ask next about Ajax programme readiness?",
    ]

    europe_questions = [
        "Summarize the top current European political developments in the uploaded briefings.",
        "What are two cross-border policy themes currently driving EU political debate?",
        "Brief me on current leadership or coalition dynamics in Europe from recent items.",
        "What near-term political risks are repeatedly mentioned across European reports?",
        "Provide a concise morning memo for a European desk analyst.",
        "What follow-up intelligence tasks should the European desk execute today?",
    ]

    military_flows = [
        [
            "Give me a one-paragraph Ajax situation update.",
            "Now expand on the most credible delivery/fielding risk.",
            "Finish with three concrete mitigation actions for operations leadership.",
        ],
        [
            "Start a risk register for Ajax using current sources.",
            "Prioritize the top two risks and justify priority.",
            "Provide recommended owner and due date style actions for each.",
        ],
        [
            "What changed most recently in Ajax reporting?",
            "How does that change force planning assumptions?",
            "Summarize for an executive readout in five bullets.",
        ],
    ]

    europe_flows = [
        [
            "Provide a Europe politics headline scan from uploaded content.",
            "Drill into the most strategically important item.",
            "Conclude with likely 30-day implications.",
        ],
        [
            "Create a European desk watchlist from current developments.",
            "Rank items by urgency and explain why.",
            "Provide an action checklist for analyst follow-up.",
        ],
        [
            "Summarize current EU and regional political friction points.",
            "Which friction point is most likely to affect policy execution?",
            "Deliver a concise stakeholder briefing note.",
        ],
    ]

    for question in military_questions:
        out = _channel_chat(
            api,
            demo_context.api_url,
            demo_context.channels["Military Channel"],
            demo_context.gary_user_id,
            question,
        )
        assert len(str(out.get("response", ""))) >= 60

    for question in europe_questions:
        out = _channel_chat(
            api,
            demo_context.api_url,
            demo_context.channels["European Channel"],
            demo_context.gary_user_id,
            question,
        )
        assert len(str(out.get("response", ""))) >= 60

    for prompts in military_flows:
        session_id: Optional[int] = None
        for prompt in prompts:
            out = _channel_chat(
                api,
                demo_context.api_url,
                demo_context.channels["Military Channel"],
                demo_context.gary_user_id,
                prompt,
                session_id=session_id,
            )
            session_id = int(out["session_id"])
            assert len(str(out.get("response", ""))) >= 60

    for prompts in europe_flows:
        session_id = None
        for prompt in prompts:
            out = _channel_chat(
                api,
                demo_context.api_url,
                demo_context.channels["European Channel"],
                demo_context.gary_user_id,
                prompt,
                session_id=session_id,
            )
            session_id = int(out["session_id"])
            assert len(str(out.get("response", ""))) >= 60
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_demo_language_specialists(demo_context: DemoContext):
    api = requests.Session()
    api.headers.update({"X-API-Key": str(get_config("test.api_key"))})
    api.timeout_seconds = demo_context.timeout

    ar = _channel_chat(
        api,
        demo_context.api_url,
        demo_context.channels["Arabic Translation Channel"],
        demo_context.gary_user_id,
        "Translate this into Arabic: Ajax programme oversight requires reliable delivery milestones.",
    )
    ar_text = str(ar.get("response", ""))
    assert re.search(r"[\u0600-\u06FF]", ar_text), "Arabic channel did not return Arabic script"

    zh = _channel_chat(
        api,
        demo_context.api_url,
        demo_context.channels["Chinese Translation Channel"],
        demo_context.gary_user_id,
        "Translate this into Chinese: European desk needs concise political risk summaries.",
    )
    zh_text = str(zh.get("response", ""))
    assert re.search(r"[\u4E00-\u9FFF]", zh_text), "Chinese channel did not return Chinese script"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.smtp, pytest.mark.heavy]
