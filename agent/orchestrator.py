"""Main orchestrator for email classification workflow."""

import asyncio
from datetime import datetime
from typing import List, Optional, Callable
from enum import Enum

from models.schemas import (
    Email,
    EmailClassification,
    ClassificationResult,
    BatchClassificationStats,
    EmailProvider
)
from config.settings import ConfigurationManager
from agent.classifier import EmailClassifier, ClassificationCache
from mcp_clients.gmail_direct_client import GmailDirectClient
from mcp_clients.outlook_client import OutlookMCPClient


class OrchestratorStatus(str, Enum):
    """Orchestrator status."""
    IDLE = "idle"
    CONNECTING = "connecting"
    FETCHING = "fetching"
    CLASSIFYING = "classifying"
    APPLYING = "applying"
    COMPLETED = "completed"
    ERROR = "error"


class EmailClassificationOrchestrator:
    """
    Main orchestrator for email classification workflow.

    Coordinates email fetching, OpenAI classification, and label application.
    """

    def __init__(self, config: ConfigurationManager, log_callback: Optional[Callable[[str], None]] = None):
        """
        Initialize orchestrator.

        Args:
            config: Configuration manager
            log_callback: Optional callback for logging messages
        """
        self.config = config
        self.log_callback = log_callback or print

        # Initialize classifier and cache
        self.classifier = EmailClassifier(
            settings=config.settings,
            categories=config.classification_config.categories
        )
        self.cache = ClassificationCache()
        
        # Initialize email clients
        self.gmail_client: Optional[GmailDirectClient] = None
        self.outlook_client: Optional[OutlookMCPClient] = None
        
        self.status = OrchestratorStatus.IDLE
        self.stats: Optional[BatchClassificationStats] = None

    def log(self, message: str) -> None:
        """Log a message."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        self.log_callback(log_msg)

    def _get_classification_label_names(self) -> List[str]:
        """get all possible label names that could be applied by classifier"""
        labels = []
        for category in self.config.classification_config.categories:
            # normalize same way as when applying labels
            label_name = category.name.replace('_', ' ').title()
            labels.append(label_name)
            # also add original name in case it's stored differently
            labels.append(category.name)
        return labels

    def _is_already_labeled(self, email: Email) -> bool:
        """check if email already has a classification label/category"""
        classification_labels = self._get_classification_label_names()
        email_labels_lower = [label.lower().strip() for label in email.existing_labels]
        
        for cls_label in classification_labels:
            cls_label_lower = cls_label.lower().strip()
            # check exact match (case-insensitive)
            if cls_label_lower in email_labels_lower:
                return True
        return False

    async def _fetch_emails(self, provider: str = "gmail", limit: int = 50) -> List[Email]:
        """
        Fetch emails from specified provider, excluding already labeled ones.

        Args:
            provider: Email provider ("gmail", "outlook", or "both")
            limit: Maximum emails to fetch

        Returns:
            List of Email objects (only unlabeled ones)
        """
        emails = []
        providers_to_fetch = []
        
        # Determine which providers to fetch from
        if provider.lower() == "both":
            providers_to_fetch = ["gmail", "outlook"]
        else:
            providers_to_fetch = [provider.lower()]
        
        try:
            for prov in providers_to_fetch:
                if prov == "gmail":
                    try:
                        if not self.gmail_client:
                            self.log("Initializing Gmail API client...")
                            self.gmail_client = GmailDirectClient(self.config.settings)
                            await self.gmail_client.connect()
                            self.log("Connected to Gmail API")
                        
                        # fetch more than limit to account for filtering
                        fetch_limit = limit * 2  # fetch extra to filter out labeled ones
                        self.log(f"Fetching {fetch_limit} emails from Gmail...")
                        gmail_emails = await self.gmail_client.fetch_recent_emails(limit=fetch_limit, query="in:inbox")
                        
                        # filter out already labeled emails
                        unlabeled = [e for e in gmail_emails if not self._is_already_labeled(e)]
                        emails.extend(unlabeled[:limit])  # take up to limit
                        
                        self.log(f"Fetched {len(gmail_emails)} emails, {len(unlabeled)} unlabeled")
                    except Exception as e:
                        self.log(f"Error fetching from Gmail: {e}")
                
                elif prov == "outlook":
                    try:
                        if not self.outlook_client:
                            self.log("Initializing Outlook MCP client...")
                            self.outlook_client = OutlookMCPClient(self.config.settings)
                            await self.outlook_client.connect()
                            self.log("Connected to Outlook MCP server")
                        
                        # fetch more than limit to account for filtering
                        fetch_limit = limit * 2
                        self.log(f"Fetching {fetch_limit} emails from Outlook...")
                        outlook_emails = await self.outlook_client.fetch_recent_emails(limit=fetch_limit)
                        
                        # filter out already labeled emails
                        unlabeled = [e for e in outlook_emails if not self._is_already_labeled(e)]
                        emails.extend(unlabeled[:limit])
                        
                        self.log(f"Fetched {len(outlook_emails)} emails, {len(unlabeled)} unlabeled")
                    except Exception as e:
                        self.log(f"Error fetching from Outlook: {e}")
            
            # If no emails fetched, try mock emails
            if not emails:
                self.log("No emails fetched from providers, using mock emails for testing...")
                emails = self._create_mock_emails()
                
        except Exception as e:
            self.log(f"Error in email fetching: {e}")
            # Fallback to mock emails if real fetch fails
            self.log("Falling back to mock emails for testing...")
            emails = self._create_mock_emails()
        
        return emails

    def _create_mock_emails(self) -> List[Email]:
        """Create mock emails for testing when real emails unavailable."""
        return [
            Email(
                id="mock-1",
                provider=EmailProvider.GMAIL,
                subject="Your 2FA code is 123456",
                sender="noreply@google.com",
                recipient="user@example.com",
                date=datetime.now(),
                body_preview="Your Google Account 2-Step Verification code is: 123456",
                body_full="Your Google Account 2-Step Verification code is: 123456",
                is_read=False,
                has_attachments=False,
                existing_labels=[]
            ),
            Email(
                id="mock-2",
                provider=EmailProvider.GMAIL,
                subject="Meeting tomorrow at 2 PM",
                sender="colleague@work.com",
                recipient="user@example.com",
                date=datetime.now(),
                body_preview="Don't forget about our meeting tomorrow",
                body_full="Don't forget about our meeting tomorrow at 2 PM to discuss the project.",
                is_read=False,
                has_attachments=False,
                existing_labels=[]
            ),
        ]

    async def classify_emails(
        self,
        limit: Optional[int] = None,
        provider: Optional[str] = None
    ) -> BatchClassificationStats:
        """
        Classify emails from specified provider using AI.

        Args:
            limit: Maximum emails to process
            provider: Email provider to use (overrides config)

        Returns:
            Batch classification statistics
        """
        start_time = datetime.now()
        
        try:
            self.status = OrchestratorStatus.CLASSIFYING
            
            # Determine provider
            active_provider = provider or self.config.settings.email_provider
            self.log(f"Starting email classification from {active_provider}...")
            
            # Fetch emails
            self.status = OrchestratorStatus.FETCHING
            fetch_limit = limit or self.config.settings.max_emails_per_run
            emails = await self._fetch_emails(provider=active_provider, limit=fetch_limit)
            
            if not emails:
                self.log("No emails to classify")
                return BatchClassificationStats()
            
            # Classify emails
            self.status = OrchestratorStatus.CLASSIFYING
            successful = 0
            failed = 0
            categories_breakdown = {}
            confidences = []
            
            for email in emails[:limit] if limit else emails:
                try:
                    self.log(f"Classifying: {email.subject[:50]}...")
                    
                    classification = await self.classifier.classify_email(email)
                    
                    if classification:
                        successful += 1
                        category = classification.category
                        categories_breakdown[category] = categories_breakdown.get(category, 0) + 1
                        confidences.append(classification.confidence)
                        self.log(f"  → {category} ({classification.confidence:.1%} confidence)")
                        
                        # Apply label/category based on provider
                        try:
                            # Normalize category name: capitalize words, lowercase rest
                            label_name = category.replace('_', ' ').title()
                            
                            if email.provider == EmailProvider.GMAIL and self.gmail_client:
                                # Apply Gmail label
                                label_applied = await self.gmail_client.apply_label(email.id, label_name)
                                if label_applied:
                                    self.log(f"     Applied Gmail label '{label_name}'")
                                else:
                                    self.log(f"     Could not apply Gmail label (may need creation)")
                            
                            elif email.provider == EmailProvider.OUTLOOK and self.outlook_client:
                                # Apply Outlook category
                                category_applied = await self.outlook_client.apply_category(email.id, label_name)
                                if category_applied:
                                    self.log(f"     Applied Outlook category '{label_name}'")
                                else:
                                    self.log(f"     Could not apply Outlook category")
                            
                        except Exception as le:
                            self.log(f"     Label/category error: {le}")
                    else:
                        failed += 1
                        self.log(f"  → Failed to classify")
                        
                except Exception as e:
                    failed += 1
                    self.log(f"  → Error: {e}")
            
            # Calculate stats
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            processing_time = (datetime.now() - start_time).total_seconds()
            
            stats = BatchClassificationStats(
                total_emails=len(emails),
                successful=successful,
                failed=failed,
                average_confidence=avg_confidence,
                processing_time_seconds=processing_time,
                categories_breakdown=categories_breakdown
            )

            self.status = OrchestratorStatus.COMPLETED
            self.stats = stats
            self.log(f"✓ Classification completed: {successful}/{len(emails)} successful in {processing_time:.2f}s")
            
            return stats

        except Exception as e:
            self.status = OrchestratorStatus.ERROR
            self.log(f"✗ Classification error: {e}")
            raise

    async def cleanup(self) -> None:
        """Clean up resources and disconnect from MCP servers."""
        try:
            if self.gmail_client:
                self.log("Disconnecting Gmail MCP client...")
                await self.gmail_client.disconnect()
                self.log("✓ Gmail client disconnected")
            
            if self.outlook_client:
                self.log("Disconnecting Outlook MCP client...")
                await self.outlook_client.disconnect()
                self.log("✓ Outlook client disconnected")
        except Exception as e:
            self.log(f"Error during cleanup: {e}")

    async def __aenter__(self):
        """Async context manager entry."""
        self.log("Initializing orchestrator...")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()
        self.log("Orchestrator shutdown.")
