"""Outlook/Microsoft 365 client using Microsoft Graph API directly."""

import asyncio
import re
from datetime import datetime
from typing import List, Optional

from azure.identity.aio import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.users.item.messages.messages_request_builder import MessagesRequestBuilder
from msgraph.generated.models.message import Message

from models.schemas import Email, EmailProvider
from config.settings import Settings


class OutlookMCPClient:
    """Client for interacting with Outlook/Microsoft 365 via Microsoft Graph API."""

    def __init__(self, settings: Settings):
        """
        Initialize Outlook Graph API client.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.client: Optional[GraphServiceClient] = None
        self.credential: Optional[ClientSecretCredential] = None
        self.user_id: Optional[str] = None

    async def connect(self) -> None:
        """
        Connect to Microsoft Graph API.

        Raises:
            ConnectionError: If connection fails
        """
        try:
            if not self.settings.outlook_client_id:
                raise ValueError("Outlook client ID not configured")
            if not self.settings.outlook_client_secret:
                raise ValueError("Outlook client secret not configured")
            if not self.settings.outlook_tenant_id:
                raise ValueError("Outlook tenant ID not configured")

            # create credential for client credentials flow
            self.credential = ClientSecretCredential(
                tenant_id=self.settings.outlook_tenant_id,
                client_id=self.settings.outlook_client_id,
                client_secret=self.settings.outlook_client_secret
            )

            # create graph client
            scopes = ["https://graph.microsoft.com/.default"]
            self.client = GraphServiceClient(
                credentials=self.credential,
                scopes=scopes
            )

            # get user ID (required for app-only auth)
            # for app-only auth, we need a user principal name or user ID
            if not self.settings.outlook_user_id:
                raise ValueError("Outlook user ID not configured (required for app-only authentication)")
            self.user_id = self.settings.outlook_user_id

        except Exception as e:
            raise ConnectionError(f"Failed to connect to Microsoft Graph API: {e}")

    async def disconnect(self) -> None:
        """Disconnect from Microsoft Graph API."""
        try:
            # GraphServiceClient doesn't need explicit close
            # just clean up the credential
            if self.credential:
                await self.credential.close()
        except Exception as e:
            # log but don't raise on disconnect errors
            print(f"Error during disconnect: {e}")

    async def fetch_recent_emails(self, limit: int = 50, folder: str = "inbox") -> List[Email]:
        """
        Fetch recent emails from Outlook.

        Args:
            limit: Maximum number of emails to fetch
            folder: Folder name (default: inbox) - not used for now, always fetches from inbox

        Returns:
            List of Email objects
        """
        if not self.client:
            raise RuntimeError("Not connected to Microsoft Graph API")

        try:
            # build query parameters
            query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
                select=[
                    "id",
                    "subject",
                    "from",
                    "toRecipients",
                    "receivedDateTime",
                    "body",
                    "bodyPreview",
                    "isRead",
                    "hasAttachments",
                    "categories"
                ],
                top=min(limit, 100),  # cap at 100 per API limits
                orderby=["receivedDateTime DESC"]
            )

            request_config = MessagesRequestBuilder.MessagesRequestBuilderGetRequestConfiguration(
                query_parameters=query_params
            )
            request_config.headers.add("prefer", "outlook.body-content-type=text")

            # fetch messages
            messages_response = await self.client.users.by_user_id(self.user_id).messages.get(
                request_configuration=request_config
            )

            if not messages_response or not messages_response.value:
                return []

            # convert to Email objects
            emails = []
            for msg in messages_response.value[:limit]:
                try:
                    email = self._parse_graph_message(msg)
                    if email:
                        emails.append(email)
                except Exception as e:
                    print(f"Failed to parse message {msg.id if hasattr(msg, 'id') else 'unknown'}: {e}")
                    continue

            return emails

        except Exception as e:
            raise RuntimeError(f"Failed to fetch emails from Outlook: {e}")

    def _parse_graph_message(self, msg: Message) -> Optional[Email]:
        """
        Parse Microsoft Graph Message into Email object.

        Args:
            msg: Message object from Graph API

        Returns:
            Email object or None if parsing fails
        """
        try:
            # extract fields
            message_id = msg.id or ""
            subject = msg.subject or "(No Subject)"

            # parse sender
            sender = "unknown@unknown.com"
            sender_name = None
            if msg.from_escaped and msg.from_escaped.email_address:
                sender = msg.from_escaped.email_address.address or sender
                sender_name = msg.from_escaped.email_address.name

            # parse recipient (first To recipient)
            recipient = ""
            if msg.to_recipients and len(msg.to_recipients) > 0:
                if msg.to_recipients[0].email_address:
                    recipient = msg.to_recipients[0].email_address.address or ""

            # parse date
            date = datetime.now()
            if msg.received_date_time:
                date = msg.received_date_time

            # get body
            body_text = ""
            if msg.body:
                body_text = msg.body.content or ""
                # if HTML, strip tags (simple approach)
                if msg.body.content_type and "html" in str(msg.body.content_type).lower():
                    body_text = re.sub(r'<[^>]+>', '', body_text)

            # fallback to preview if body empty
            if not body_text and msg.body_preview:
                body_text = msg.body_preview

            # get categories (Outlook's labels)
            categories = msg.categories or []

            # check if read
            is_read = msg.is_read if hasattr(msg, 'is_read') else False

            # check attachments
            has_attachments = msg.has_attachments if hasattr(msg, 'has_attachments') else False

            return Email(
                id=message_id,
                provider=EmailProvider.OUTLOOK,
                subject=subject,
                sender=sender,
                sender_name=sender_name,
                recipient=recipient,
                date=date,
                body_preview=body_text[:500] if body_text else "",
                body_full=body_text if len(body_text) < 10000 else body_text[:10000],
                is_read=is_read,
                has_attachments=has_attachments,
                existing_labels=categories
            )

        except Exception as e:
            print(f"Error parsing Outlook message: {e}")
            return None

    async def apply_category(self, message_id: str, category_name: str) -> bool:
        """
        Apply a category to an Outlook message.

        Args:
            message_id: Outlook message ID
            category_name: Category name to apply

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            raise RuntimeError("Not connected to Microsoft Graph API")

        try:
            # get current message to retrieve existing categories
            msg = await self.client.users.by_user_id(self.user_id).messages.by_message_id(message_id).get()

            if not msg:
                return False

            # get existing categories
            existing_categories = list(msg.categories) if msg.categories else []

            # add new category if not already present
            if category_name not in existing_categories:
                existing_categories.append(category_name)

            # create update message
            update_msg = Message()
            update_msg.categories = existing_categories

            # update message
            await self.client.users.by_user_id(self.user_id).messages.by_message_id(message_id).patch(update_msg)

            return True

        except Exception as e:
            print(f"Failed to apply category '{category_name}' to message {message_id}: {e}")
            return False

    async def apply_multiple_categories(self, message_id: str, categories: List[str]) -> dict[str, bool]:
        """
        Apply multiple categories to a message.

        Args:
            message_id: Outlook message ID
            categories: List of category names

        Returns:
            Dictionary mapping category names to success status
        """
        if not self.client:
            raise RuntimeError("Not connected to Microsoft Graph API")

        try:
            # get current message
            msg = await self.client.users.by_user_id(self.user_id).messages.by_message_id(message_id).get()

            if not msg:
                return {cat: False for cat in categories}

            # get existing categories
            existing_categories = set(msg.categories) if msg.categories else set()

            # add all new categories
            all_categories = list(existing_categories.union(set(categories)))

            # create update message
            update_msg = Message()
            update_msg.categories = all_categories

            # update message
            await self.client.users.by_user_id(self.user_id).messages.by_message_id(message_id).patch(update_msg)

            # return success for all categories
            return {cat: True for cat in categories}

        except Exception as e:
            print(f"Failed to apply categories to message {message_id}: {e}")
            return {cat: False for cat in categories}

    async def create_master_category_list(self, categories: List[str]) -> bool:
        """
        Create master category list in Outlook.

        Note: Categories are created automatically when first applied in Outlook.

        Args:
            categories: List of category names to create

        Returns:
            True if successful, False otherwise
        """
        # categories are created automatically when first applied
        # no explicit API call needed
        return True

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
