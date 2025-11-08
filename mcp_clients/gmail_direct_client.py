"""Direct Gmail API client - bypasses MCP for reliable email fetching."""

import json
import base64
import asyncio
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.transport.urllib3 import Request as UrllibRequest
import urllib3
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from models.schemas import Email, EmailProvider
from config.settings import Settings


class GmailDirectClient:
    """Direct Gmail API client for reliable email fetching without MCP."""

    def __init__(self, settings: Settings):
        """Initialize Gmail Direct client."""
        self.settings = settings
        self.service = None
        self.creds = None

    async def connect(self) -> None:
        """
        Connect to Gmail API using stored credentials.
        
        Raises:
            ConnectionError: If connection fails
        """
        try:
            # Try to load token from home directory (where it's stored)
            token_file = Path.home() / '.gmail-mcp' / 'token.json'
            
            # Fall back to project config directory
            if not token_file.exists() and self.settings.gmail_token_path:
                token_file = Path(self.settings.gmail_token_path)
            
            if not token_file.exists():
                raise FileNotFoundError(f"Token file not found at {token_file}")
            
            with open(token_file) as f:
                token_data = json.load(f)
            
            self.creds = Credentials.from_authorized_user_info(
                token_data,
                scopes=['https://mail.google.com/']
            )
            
            # Refresh if needed
            if not self.creds.valid:
                self.creds.refresh(UrllibRequest(urllib3.PoolManager()))
            
            # Build Gmail service
            self.service = build('gmail', 'v1', credentials=self.creds)
            
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Gmail API: {e}")

    async def disconnect(self) -> None:
        """Disconnect from Gmail API."""
        if self.service:
            self.service.close()
            self.service = None
        self.creds = None

    async def list_available_tools(self) -> List[str]:
        """
        List available tools (for compatibility).
        
        Returns:
            List of available tools
        """
        return [
            'get_recent_emails',
            'search_emails',
            'get_message',
            'apply_label',
            'create_label'
        ]

    async def fetch_recent_emails(self, limit: int = 50, query: str = "in:inbox") -> List[Email]:
        """
        Fetch recent emails from Gmail.

        Args:
            limit: Maximum number of emails to fetch
            query: Gmail search query (default: inbox)

        Returns:
            List of Email objects
        """
        if not self.service:
            raise RuntimeError("Not connected to Gmail API")

        try:
            # Search for messages
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=min(limit, 100)
            ).execute()

            messages = results.get('messages', [])
            
            if not messages:
                return []

            # Fetch full message details for each message
            emails = []
            for message in messages[:limit]:
                try:
                    email = await self._fetch_message_details(message['id'])
                    if email:
                        emails.append(email)
                except Exception as e:
                    print(f"Failed to fetch message {message['id']}: {e}")
                    continue

            return emails

        except HttpError as e:
            raise RuntimeError(f"Failed to fetch emails from Gmail: {e}")

    async def _fetch_message_details(self, message_id: str) -> Optional[Email]:
        """
        Fetch detailed information for a specific message.

        Args:
            message_id: Gmail message ID

        Returns:
            Email object or None if fetch fails
        """
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            payload = message.get('payload', {})
            headers = {h['name']: h['value'] for h in payload.get('headers', [])}

            subject = headers.get('Subject', '(No Subject)')
            sender = headers.get('From', 'unknown@unknown.com')
            recipient = headers.get('To', '')
            date_str = headers.get('Date', '')

            # Parse sender name if present
            sender_name = None
            if '<' in sender and '>' in sender:
                sender_name = sender.split('<')[0].strip().strip('"')
                sender = sender.split('<')[1].split('>')[0].strip()

            # Parse date
            try:
                # Gmail date format: "Wed, 15 Jan 2025 10:30:00 -0800"
                date = datetime.strptime(date_str.split(' (')[0], "%a, %d %b %Y %H:%M:%S %z")
            except:
                date = datetime.now()

            # Get email body
            body = self._extract_body(payload)

            # Get labels
            labels = message.get('labelIds', [])

            # Check if read
            is_read = 'UNREAD' not in labels

            # Check attachments
            has_attachments = self._has_attachments(payload)

            return Email(
                id=message_id,
                provider=EmailProvider.GMAIL,
                subject=subject,
                sender=sender,
                sender_name=sender_name,
                recipient=recipient,
                date=date,
                body_preview=body[:500] if body else '',
                body_full=body if len(body) < 10000 else body[:10000],
                is_read=is_read,
                has_attachments=has_attachments,
                existing_labels=labels
            )

        except Exception as e:
            print(f"Error fetching message details for {message_id}: {e}")
            return None

    def _extract_body(self, payload: dict) -> str:
        """Extract email body from Gmail message payload."""
        # Try to get plain text body
        if 'body' in payload and payload['body'].get('data'):
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')

        # Check parts for text/plain
        if 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')

                # Recursively check nested parts
                if 'parts' in part:
                    body = self._extract_body(part)
                    if body:
                        return body

        return ''

    def _has_attachments(self, payload: dict) -> bool:
        """Check if message has attachments."""
        if 'parts' in payload:
            for part in payload['parts']:
                if part.get('filename'):
                    return True
                if 'parts' in part and self._has_attachments(part):
                    return True
        return False

    async def apply_label(self, message_id: str, label_name: str) -> bool:
        """Apply a label to a Gmail message."""
        if not self.service:
            raise RuntimeError("Not connected to Gmail API")

        try:
            # Get or create label
            label_id = await self._get_or_create_label(label_name)
            if not label_id:
                return False

            # Apply label
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [label_id]}
            ).execute()

            return True

        except Exception as e:
            print(f"Failed to apply label '{label_name}' to message {message_id}: {e}")
            return False

    async def _get_or_create_label(self, label_name: str) -> Optional[str]:
        """Get existing label ID or create new label (case-insensitive deduplication)."""
        try:
            # List existing labels
            results = self.service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])

            # Check if label exists (case-insensitive)
            label_name_lower = label_name.lower()
            for label in labels:
                if label.get('name', '').lower() == label_name_lower:
                    # Label already exists, return its ID
                    return label.get('id')

            # Create new label (with exact case as requested)
            label_body = {
                'name': label_name,
                'labelListVisibility': 'labelShow',
                'messageListVisibility': 'show'
            }
            created_label = self.service.users().labels().create(
                userId='me',
                body=label_body
            ).execute()

            return created_label.get('id')

        except Exception as e:
            print(f"Failed to get or create label '{label_name}': {e}")
            return None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

