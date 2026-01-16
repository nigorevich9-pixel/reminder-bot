"""Jira API service for polling issue changes."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config.settings import settings


class JiraService:
    """Service for interacting with Jira Cloud API."""

    def __init__(self) -> None:
        self.base_url = settings.jira_base_url.rstrip("/")
        self._auth_header = self._make_auth_header()

    def _make_auth_header(self) -> str:
        """Create Basic Auth header from email:token."""
        if not settings.jira_email or not settings.jira_api_token:
            raise ValueError("JIRA_EMAIL and JIRA_API_TOKEN must be set")
        credentials = f"{settings.jira_email}:{settings.jira_api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    async def search_issues(self, jql: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
        """Search issues using JQL."""
        fields = fields or ["key", "summary", "status", "assignee", "updated"]
        url = f"{self.base_url}/rest/api/3/search"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"jql": jql, "fields": ",".join(fields)},
                headers={
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("issues", [])

    async def get_issue(self, issue_key: str) -> dict[str, Any]:
        """Get single issue by key."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_issue_changelog(
        self, issue_key: str, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Get issue changelog (history of changes)."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/changelog"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            
            changes = data.get("values", [])
            
            if since:
                # Filter changes after 'since' timestamp
                filtered = []
                for change in changes:
                    created_str = change.get("created", "")
                    if created_str:
                        # Jira format: 2024-01-15T10:30:00.000+0000
                        created = datetime.fromisoformat(
                            created_str.replace("+0000", "+00:00")
                        )
                        if created > since:
                            filtered.append(change)
                return filtered
            
            return changes

    async def get_recently_updated_issues(
        self, 
        project_keys: list[str], 
        minutes: int = 5
    ) -> list[dict[str, Any]]:
        """Get issues updated in the last N minutes for given projects."""
        projects_jql = ", ".join(f'"{p}"' for p in project_keys)
        jql = f"project IN ({projects_jql}) AND updated >= -{minutes}m ORDER BY updated DESC"
        
        return await self.search_issues(
            jql, 
            fields=["key", "summary", "status", "assignee", "updated", "project"]
        )

    async def get_my_issues(self, project_key: str | None = None) -> list[dict[str, Any]]:
        """Get issues assigned to current user."""
        jql = "assignee = currentUser() AND resolution = Unresolved"
        if project_key:
            jql = f'project = "{project_key}" AND {jql}'
        jql += " ORDER BY updated DESC"
        
        return await self.search_issues(jql)

    async def test_connection(self) -> bool:
        """Test if credentials are valid."""
        try:
            url = f"{self.base_url}/rest/api/3/myself"
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={
                        "Authorization": self._auth_header,
                        "Accept": "application/json",
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                return True
        except Exception:
            return False

    async def get_current_user(self) -> dict[str, Any]:
        """Get current authenticated user info."""
        url = f"{self.base_url}/rest/api/3/myself"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()


def format_issue_update(issue: dict[str, Any], changes: list[dict[str, Any]] | None = None) -> str:
    """Format issue update for Telegram message."""
    fields = issue.get("fields", {})
    key = issue.get("key", "???")
    summary = fields.get("summary", "No summary")
    status = fields.get("status", {}).get("name", "Unknown")
    
    assignee_data = fields.get("assignee")
    assignee = assignee_data.get("displayName", "Unassigned") if assignee_data else "Unassigned"
    
    project = fields.get("project", {}).get("key", "")
    
    lines = [
        f"🎫 <b>{key}</b>",
        f"📋 {summary}",
        f"📊 Status: <b>{status}</b>",
        f"👤 Assignee: {assignee}",
    ]
    
    if changes:
        lines.append("\n📝 <b>Changes:</b>")
        for change in changes[:3]:  # Limit to 3 most recent
            author = change.get("author", {}).get("displayName", "Unknown")
            for item in change.get("items", []):
                field = item.get("field", "")
                from_val = item.get("fromString", "") or "—"
                to_val = item.get("toString", "") or "—"
                lines.append(f"  • {field}: {from_val} → {to_val}")
    
    # Add link
    base_url = settings.jira_base_url.rstrip("/")
    lines.append(f"\n🔗 <a href='{base_url}/browse/{key}'>Open in Jira</a>")
    
    return "\n".join(lines)
